"""System change requests from the CS managers to the owner (2026-10-25, team_screen/sysreq.py).
Roles (admin only, like the AI-notes card), CSRF, validation, idempotent create, the machine API's token, the status transitions,
and the file store surviving a restart. The same tests run on Postgres with CS_TEST_PG=<url>."""
import json
import time

import pytest

import sysreq
from conftest import TOKEN_SECRET, audit_text, call, client_for, logged_in  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "velora"]
RID = "0123456789abcdef0123456789abcdef"
TEXT = "אחרי סגירה בוואטסאפ המסך קופץ לראש הרשימה במקום לפנייה שמעל"


def post(c, tok, body, origin=None):
    h = {"X-CSRF-Token": tok} if tok else {}
    if origin:
        h["Origin"] = origin
    return c.post("/api/sysreq", json=body, headers=h)


def body(**kw):
    b = {"rid": RID, "text": TEXT, "brand": "all", "ticket": ""}
    b.update(kw)
    return b


def mtok(now=None, **over):
    """A machine token; `over` rewrites payload fields (to forge the wrong ones)."""
    iat = int(now if now is not None else time.time())
    p = {"user": sysreq.HQ_USER, "role": sysreq.HQ_USER, "aud": sysreq.HQ_AUD, "brands": [], "iat": iat, "exp": iat + 120}
    p.update(over)
    import hashlib
    import hmac
    pb = sysreq.b64url(json.dumps(p, separators=(",", ":")).encode())
    return pb + "." + sysreq.b64url(hmac.new(TOKEN_SECRET.encode(), pb.encode(), hashlib.sha256).digest())


def hq_get(app, since=0, token=None):
    return client_for(app).get("/hq/sysreq?since=%s" % since, headers={"X-HQ-Token": token if token is not None else mtok()})


def hq_set(app, rid_id, status, reply=None, token=None):
    b = {"status": status}
    if reply is not None:
        b["reply"] = reply
    return client_for(app).post("/hq/sysreq/%s" % rid_id, json=b, headers={"X-HQ-Token": token if token is not None else mtok()})


@pytest.fixture
def admin(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ALL)
    return c, tok


# ---------------------------------------------------------------- roles + CSRF

def test_agent_and_pure_user_manager_are_refused(app, pw_hash):
    for name, roles in (("agent1", ["agent"]), ("um1", ["user-manager"])):
        c, tok = logged_in(app, pw_hash, name, roles, ALL)
        r = post(c, tok, body(rid=("%032x" % len(name))))
        assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role", name
        r = c.get("/api/sysreq")
        assert r.status_code == 403, name
    assert app.extensions["cs"]["sysreq"].all() == [], "nothing was stored"


def test_not_logged_in_is_refused(app):
    c = client_for(app)
    assert c.get("/api/sysreq").status_code == 401


def test_csrf_missing_wrong_or_foreign_origin_is_refused(app, admin):
    c, tok = admin
    assert post(c, None, body()).status_code == 403
    assert post(c, "nope", body()).status_code == 403
    assert post(c, tok, body(), origin="https://evil.example").status_code == 403
    assert app.extensions["cs"]["sysreq"].all() == []
    assert post(c, tok, body()).status_code == 200            # the real same-origin POST runs in the browser test


# ---------------------------------------------------------------- create + list

def test_admin_creates_a_request_listed_newest_first_with_audit(app, admin):
    c, tok = admin
    r = post(c, tok, body(brand="rozela", ticket="#1646"))
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["replay"] is False
    it = j["item"]
    assert it["status"] == "pending" and it["guy_reply"] == "" and it["user"] == "manager" and it["brand"] == "rozela" and it["ticket"] == "#1646"
    assert it["text"] == TEXT and "rid" not in it
    r2 = post(c, tok, body(rid="f" * 32, text="שני: להוסיף כפתור העתקה למספר ההזמנה"))
    items = c.get("/api/sysreq").get_json()["items"]
    assert [x["id"] for x in items] == [r2.get_json()["item"]["id"], it["id"]], "newest first"
    a = audit_text(app)
    assert '"sysreq_created"' in a and '"chars": %d' % len(TEXT) in a
    assert TEXT not in a, "the audit carries counts, not the text"


def test_replay_of_the_same_rid_is_a_no_op_and_other_content_is_a_conflict(app, admin):
    c, tok = admin
    a = post(c, tok, body()).get_json()
    b = post(c, tok, body()).get_json()
    assert b["ok"] and b["replay"] is True and b["item"]["id"] == a["item"]["id"]
    assert len(app.extensions["cs"]["sysreq"].all()) == 1
    r = post(c, tok, body(text=TEXT + " ועוד משהו"))
    assert r.status_code == 409 and r.get_json()["error"] == "sysreq_rid_conflict"
    assert audit_text(app).count('"sysreq_created"') == 1


@pytest.mark.parametrize("over,code", [
    ({"text": "קצר"}, "sysreq_bad_text"),
    ({"text": "          "}, "sysreq_bad_text"),
    ({"text": "א" * 2001}, "sysreq_bad_text"),
    ({"text": 12345678901}, "sysreq_bad_text"),
    ({"brand": "nosuch"}, "sysreq_bad_brand"),
    ({"brand": "selera"}, "sysreq_bad_brand"),          # a real brand the user does not hold
    ({"brand": None}, "sysreq_bad_brand"),
    ({"ticket": "has space"}, "sysreq_bad_ticket"),
    ({"ticket": "x" * 81}, "sysreq_bad_ticket"),
    ({"rid": "short"}, "bad_request"),
    ({"rid": "Z" * 32}, "bad_request"),
    ({"rid": None}, "bad_request"),
])
def test_validation(app, admin, over, code):
    c, tok = admin
    r = post(c, tok, body(**over))
    assert r.status_code == 400 and r.get_json()["error"] == code, r.get_json()
    assert r.get_json()["msg"], "a translated sentence for the screen"
    assert app.extensions["cs"]["sysreq"].all() == []


def test_bounds_are_inclusive_and_text_is_trimmed(app, admin):
    c, tok = admin
    assert post(c, tok, body(text="  " + "א" * 10 + "  ")).get_json()["item"]["text"] == "א" * 10
    assert post(c, tok, body(rid="e" * 32, text="ב" * 2000)).status_code == 200


def test_english_messages_follow_the_page(app, admin):
    c, tok = admin
    r = c.post("/api/sysreq", json=body(text="short"), headers={"X-CSRF-Token": tok, "X-UI-Lang": "en"})
    assert "10 to 2000 characters" in r.get_json()["msg"]


def test_a_manager_sees_only_all_and_his_own_brands(app, pw_hash):
    c1, t1 = logged_in(app, pw_hash, "manager", ["admin"], ALL)
    post(c1, t1, body(brand="velora"))
    post(c1, t1, body(rid="a" * 32, brand="all"))
    c2, t2 = logged_in(app, pw_hash, "boss2", ["admin"], ["rozela"])
    seen = [x["brand"] for x in c2.get("/api/sysreq").get_json()["items"]]
    assert seen == ["all"]


# ---------------------------------------------------------------- machine API

def test_machine_list_and_decide_round_trip(app, admin):
    c, tok = admin
    it = post(c, tok, body()).get_json()["item"]
    j = hq_get(app).get_json()
    assert j["ok"] and [x["id"] for x in j["items"]] == [it["id"]] and j["items"][0]["rid"] == RID and j["items"][0]["by"] == "manager"
    r = hq_set(app, it["id"], "approved", "  מאשר, נבנה השבוע  ")
    assert r.status_code == 200 and r.get_json()["changed"] is True
    seen = c.get("/api/sysreq").get_json()["items"][0]
    assert seen["status"] == "approved" and seen["guy_reply"] == "מאשר, נבנה השבוע"
    assert seen["updated_at"] > it["updated_at"]
    # only what changed after `since` comes back
    assert hq_get(app, since=seen["updated_at"]).get_json()["items"] == []
    assert len(hq_get(app, since=it["updated_at"]).get_json()["items"]) == 1
    assert '"sysreq_decided"' in audit_text(app) and '"actor": "hq-sysreq"' in audit_text(app)


@pytest.mark.parametrize("make", [
    lambda: "",
    lambda: "garbage",
    lambda: mtok()[:-2] + "AA",                                         # bad signature
    lambda: mtok(now=time.time() - 400),                                 # expired
    lambda: mtok(now=time.time() + 600),                                 # issued in the future
    lambda: mtok(exp=int(time.time()) + 3600),                           # lifetime too long
    lambda: mtok(aud="other"),
    lambda: mtok(user="manager"),
    lambda: mtok(role="admin"),
    lambda: mtok(iat="1", exp="2"),
    lambda: mtok(now=time.time() + 50, exp=int(time.time()) + 10),     # exp before iat
    lambda: __import__("security").mint_engine_token(TOKEN_SECRET, "hq-sysreq", "admin", [], "he"),   # an engine token is not this token
])
def test_machine_api_refuses_every_bad_token(app, admin, make):
    c, tok = admin
    it = post(c, tok, body()).get_json()["item"]
    tk = make()
    r1 = hq_get(app, token=tk)
    r2 = hq_set(app, it["id"], "approved", "x", token=tk)
    assert r1.status_code == 401 and r2.status_code == 401
    assert c.get("/api/sysreq").get_json()["items"][0]["status"] == "pending"


def test_a_token_signed_with_another_secret_is_refused(app):
    other = sysreq.mint_token("z" * 48)
    assert hq_get(app, token=other).status_code == 401


def test_a_browser_session_cannot_use_the_machine_api(app, admin):
    c, tok = admin
    it = post(c, tok, body()).get_json()["item"]
    assert c.get("/hq/sysreq?since=0").status_code == 401
    assert c.post("/hq/sysreq/%d" % it["id"], json={"status": "done"}, headers={"X-CSRF-Token": tok}).status_code == 401


@pytest.mark.parametrize("path", ["since=abc", "since=nan", "since=-1"])
def test_machine_list_bad_since(app, path):
    r = client_for(app).get("/hq/sysreq?" + path, headers={"X-HQ-Token": mtok()})
    assert r.status_code == 400


def test_transitions(app, admin):
    c, tok = admin
    i = post(c, tok, body()).get_json()["item"]["id"]
    assert hq_set(app, i, "bogus").get_json()["error"] == "sysreq_bad_status"
    assert hq_set(app, i, None).get_json()["error"] == "sysreq_bad_status"
    assert hq_set(app, i, "approved", "x" * 1001).get_json()["error"] == "sysreq_bad_reply"
    assert hq_set(app, i, "rejected", "לא עכשיו").status_code == 200
    assert hq_set(app, i, "done").get_json()["error"] == "sysreq_bad_transition"        # rejected -> done: no
    assert hq_set(app, i, "pending").get_json()["error"] == "sysreq_bad_transition"     # never back to pending
    assert hq_set(app, i, "approved").status_code == 200                                # he changed his mind
    j = hq_set(app, i, "approved").get_json()
    assert j["changed"] is False and j["item"]["guy_reply"] == "לא עכשיו", "reply None keeps the reply; same status = no-op"
    assert hq_set(app, i, "approved", "עדכון תשובה").get_json()["changed"] is True        # same status, a reply edit
    assert hq_set(app, i, "done", "בוצע").status_code == 200
    for s in ("approved", "rejected", "pending"):
        assert hq_set(app, i, s).get_json()["error"] == "sysreq_bad_transition", "done is the end"
    assert hq_set(app, 99999, "done").status_code == 404
    assert c.get("/api/sysreq").get_json()["items"][0]["status"] == "done"


def test_the_csrf_exemption_is_only_the_machine_path(app, admin):
    c, tok = admin
    r = c.post("/api/sysreq", json=body(), headers={"X-HQ-Token": mtok()})       # a machine token never replaces CSRF on the browser route
    assert r.status_code == 403


def test_file_store_survives_a_restart_and_refuses_a_broken_file(make_app, tmp_path, pw_hash):
    import os
    if os.environ.get("CS_TEST_PG"):
        pytest.skip("file layout only")
    a1 = make_app()
    c, tok = logged_in(a1, pw_hash, "manager", ["admin"], ALL)
    post(c, tok, body())
    a2 = make_app()
    assert len(a2.extensions["cs"]["sysreq"].all()) == 1
    p = a2.extensions["cs"]["sysreq"].path
    open(p, "w").write("[]")
    with pytest.raises(RuntimeError):
        a2.extensions["cs"]["sysreq"].all()


def test_token_lifetime_bounds_are_the_ones_the_mini_mints():
    now = int(time.time())
    assert sysreq.verify_token(TOKEN_SECRET, sysreq.mint_token(TOKEN_SECRET, now=now, ttl_s=120), now=now) is None
    assert sysreq.verify_token(TOKEN_SECRET, sysreq.mint_token(TOKEN_SECRET, now=now, ttl_s=301), now=now) == "lifetime too long"
    assert sysreq.verify_token("short", sysreq.mint_token(TOKEN_SECRET), now=now) == "no secret"


def test_parallel_creates_of_one_rid_store_one_request(app):
    """Two instances / two clicks at once (a deploy runs two side by side): one rid = one row, the other is a replay."""
    import threading
    st = app.extensions["cs"]["sysreq"]
    out = []

    def go():
        out.append(st.create("manager", "all", "", TEXT, RID))
    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(st.all()) == 1
    assert sorted(c for _, c in out) == [False] * 7 + [True]
    assert len({r["id"] for r, _ in out}) == 1


def test_csrf_exemption_is_exactly_the_two_machine_routes():
    m = sysreq.MACHINE_PATH_RE.match
    assert m("/hq/sysreq") and m("/hq/sysreq/12")
    for p in ("/hq/sysreq-x", "/hq/sysreq/", "/hq/sysreq/12/x", "/hq/sysreqs", "/api/sysreq", "/hq/sysreq/abc"):
        assert not m(p), p


# ---------------------------------------------------------------- kind: a system change | a data request (2026-11-25)

def test_kind_round_trips_through_the_api_and_the_machine_api(app, admin):
    c, tok = admin
    r1 = post(c, tok, body(rid="a" * 32))                                           # no kind = a change (the old screen)
    r2 = post(c, tok, body(rid="b" * 32, kind="data", text="כמה ביטולי מנוי ברוזלה ב-7 הימים האחרונים קיבלו הנחת 50% ונשארו?"))
    assert r1.status_code == 200 and r1.get_json()["item"]["kind"] == "change"
    assert r2.status_code == 200 and r2.get_json()["item"]["kind"] == "data"
    lst = {x["id"]: x["kind"] for x in c.get("/api/sysreq").get_json()["items"]}
    assert sorted(lst.values()) == ["change", "data"]
    hq = {x["rid"]: x["kind"] for x in hq_get(app).get_json()["items"]}
    assert hq == {"a" * 32: "change", "b" * 32: "data"}
    assert '"kind": "data"' in audit_text(app)


def test_a_bad_kind_is_refused_and_the_same_rid_with_another_kind_is_a_conflict(app, admin):
    c, tok = admin
    for bad in ("", "Data", "delete", 1, None, ["data"]):
        r = post(c, tok, body(kind=bad))
        assert r.status_code == 400 and r.get_json()["error"] == "sysreq_bad_kind", bad
    assert post(c, tok, body(kind="change")).status_code == 200
    assert post(c, tok, body(kind="change")).get_json()["replay"] is True
    assert post(c, tok, body(kind="data")).get_json()["error"] == "sysreq_rid_conflict"


def test_the_reply_cap_is_per_kind(app, admin):
    c, tok = admin
    ch = post(c, tok, body(rid="c" * 32)).get_json()["item"]["id"]
    da = post(c, tok, body(rid="d" * 32, kind="data")).get_json()["item"]["id"]
    assert hq_set(app, ch, "approved", "x" * (sysreq.REPLY_MAX + 1)).status_code == 400
    assert hq_set(app, ch, "approved", "x" * sysreq.REPLY_MAX).status_code == 200
    long = "\n".join(["שורה %d: 12 ביטולים, 7 נשארו" % i for i in range(120)])[:sysreq.REPLY_MAX_DATA]
    assert len(long) > sysreq.REPLY_MAX
    r = hq_set(app, da, "done", long)
    assert r.status_code == 200 and r.get_json()["item"]["guy_reply"] == long
    assert hq_set(app, da, "done", "x" * (sysreq.REPLY_MAX_DATA + 1)).status_code == 400


def test_a_record_from_before_kinds_reads_as_a_change(tmp_path):
    import json as _j
    p = tmp_path / "sr.json"
    p.write_text(_j.dumps({"seq": 1, "items": {"1": {"id": 1, "rid": "e" * 32, "created_at": 1.0, "updated_at": 1.0, "user": "manager",
                                                       "brand": "all", "ticket": "", "text": TEXT, "status": "done", "guy_reply": "ok"}}}))
    st = sysreq.SysReqStore(str(p))
    assert sysreq.public(st.all()[0], {})["kind"] == "change"
    rec, created = st.create("manager", "all", "", TEXT, "e" * 32)          # its replay (no kind) is still a replay
    assert created is False


def test_the_migration_adds_kind_to_an_existing_table_and_keeps_the_rows():
    import os as _os
    pg = _os.environ.get("CS_TEST_PG", "postgresql://cs:cs@127.0.0.1:54329/cs_test")
    import pgstore
    schema = "sysreq_mig_%d" % _os.getpid()             # its own schema: never touches the tables another run of the suite is using
    try:
        boot = pgstore.DB(pg)
        boot.x("drop schema if exists %s cascade" % schema)
        boot.x("create schema %s" % schema)
    except Exception as e:                                             # noqa: BLE001
        pytest.fail("the local test Postgres is needed (node /Users/Shared/cs_core_pgtest_start.mjs): %s" % e)
    class SchemaDB(pgstore.DB):                         # pgstore.DB sets its own `options`: the search_path goes in the same way
        def _connect(self):
            import psycopg
            return psycopg.connect(self.url, autocommit=True, connect_timeout=10, options="-c search_path=%s" % schema)
    db = SchemaDB(pg)
    db.x("create table screen_system_requests(id bigserial primary key, rid text not null unique, created_at double precision not null, "
         "updated_at double precision not null, username text not null, brand text not null, ticket text not null default '', "
         "text text not null, status text not null, guy_reply text not null default '')")          # the 2026-10-25 shape
    db.x("insert into screen_system_requests(rid, created_at, updated_at, username, brand, ticket, text, status, guy_reply) "
         "values (%s, 1, 1, 'manager', 'all', '', %s, 'done', 'ok')", ("f" * 32, TEXT))
    pgstore.init(db)
    pgstore.init(db)                                                   # idempotent: a second instance / restart runs it again
    st = sysreq.PgSysReqStore(db)
    old = st.all()[0]
    assert old["kind"] == "change" and old["text"] == TEXT and old["guy_reply"] == "ok"
    rec, created = st.create("manager", "all", "", TEXT + " נתונים", "9" * 32, "data")
    assert created and rec["kind"] == "data" and st.since(0)[-1]["kind"] == "data"
    assert db.q("select table_schema from information_schema.tables where table_name='screen_system_requests' and table_schema=%s", (schema,))
    boot.x("drop schema %s cascade" % schema)
