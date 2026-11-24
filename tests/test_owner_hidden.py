"""Owner accounts (2026-11-25, owners.py): the owner leaves no trace of WHEN or HOW LONG he is on the screen for anyone else (the
managers' board, "online now", the per-agent tables, the ticket presence chip, the user manager's last sign-in and change log), and
his account can be changed only by himself or by the ops account. Another person with a similar name ("agent-one", an agent) stays
fully visible."""
import os
import re
import time

import dashboard as D
import owners
import sla
from conftest import add_user, call, logged_in, store_of
from users_store import public_user

ALL = ["rozela", "celesta", "apexmen", "velora"]
OWNER = "guy"
AGENT_TWIN = "agent-one"          # a different person, an agent: must stay fully visible


def H(tok):
    return {"X-CSRF-Token": tok}


def manager(app, pw_hash, name="mgr-cs"):
    return logged_in(app, pw_hash, name, ["admin", "user-manager"], ALL)


def owner(app, pw_hash):
    return logged_in(app, pw_hash, OWNER, ["admin", "user-manager"], ALL)


def test_the_default_owner_is_guy_and_only_him():
    assert owners.is_hidden("guy") and owners.is_hidden("GUY")
    assert not owners.is_hidden(AGENT_TWIN) and not owners.is_hidden("claude-admin") and not owners.is_hidden(None)
    assert owners.hidden_from("mgr-cs", "guy") and not owners.hidden_from("guy", "guy") and owners.hidden_from(None, "guy")
    assert owners.may_change("guy", "guy") and owners.may_change("claude-admin", "guy")
    assert not owners.may_change("mgr-cs", "guy") and owners.may_change("mgr-cs", AGENT_TWIN)


# ---------------------------------------------------------------- the activity log is never written for the owner

def test_owner_writes_no_presence_and_no_activity_but_the_agent_twin_does(app, pw_hash, transport):
    log = app.extensions["cs"]["activity"]["log"]
    for name, roles in ((OWNER, ["admin", "user-manager"]), (AGENT_TWIN, ["agent"])):
        c, tok = logged_in(app, pw_hash, name, roles, ALL)
        assert c.post("/api/rozela/list", json={}, headers=H(tok)).status_code == 200
        assert c.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers=H(tok)).status_code == 200
        assert c.post("/api/rozela/activity", json={"id": "t1", "kind": "edit"}, headers=H(tok)).status_code == 200
        r = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "היי, בדקנו ונחזור אלייך היום.", "channel": "email"})
        assert r.status_code == 200 and r.get_json()["ok"], r.get_json()
    day = D.il_day(time.time())
    pres = log.presence(day)
    users_in_log = {e.get("u") for e in log.events(day)}
    assert OWNER not in pres and OWNER not in users_in_log
    assert AGENT_TWIN in pres and AGENT_TWIN in users_in_log
    assert {e["k"] for e in log.events(day) if e.get("u") == AGENT_TWIN} >= {"open", "edit", "send"}


def test_board_has_no_row_for_the_owner_even_from_older_log_rows(tmp_path):
    t0 = D.day_start("2026-11-20")
    now = [t0 + 80000]
    log = D.ActivityLog(str(tmp_path / "act"), clock=lambda: now[0])
    users = [{"username": OWNER, "display_name": "G", "roles": ["admin", "user-manager", "agent"], "brands": ["rozela"]},
             {"username": AGENT_TWIN, "display_name": "GC", "roles": ["agent"], "brands": ["rozela"]}]
    for u in (OWNER, AGENT_TWIN):                         # rows written before 2026-11-25 (the log is append-only)
        log.record(u, "rozela", "t1", "email", "open", "shipping", ts=t0 + 36000)
        log.record(u, "rozela", "t1", "email", "send", "shipping", ts=t0 + 36100)
        log.touch(u, ts=t0 + 36000)
    rows = {"rozela": [{"id": "t1", "status": "sent", "handled_by": OWNER, "handled_at": "2026-11-20T10:00:00Z"},
                       {"id": "t2", "status": "sent", "handled_by": AGENT_TWIN, "handled_at": "2026-11-20T10:00:00Z"}]}
    ds = {"rozela": {"data": {"attribution": {"bySender": {OWNER: 5, AGENT_TWIN: 3}}}}}
    out = D.build(log, rows, users, ["rozela"], "2026-11-20", 1, now[0], ds)
    names = [a["user"] for a in out["agents"]]
    assert OWNER not in names and AGENT_TWIN in names
    assert OWNER not in (out.get("senders") or {}) and (out.get("senders") or {}).get(AGENT_TWIN) == 3
    assert [a for a in out["agents"] if a["user"] == AGENT_TWIN][0]["present_s"] == 60


def test_cancels_board_has_no_owner_row_but_the_brand_total_keeps_his_cancels():
    raw = {"kaching": "ok", "days": [{"date": "2026-11-20", "subs_team": 5, "subs_bot": 0, "orders_cancelled": 1, "subs_all_kaching": 9,
                                      "subs_team_by": {OWNER: 2, AGENT_TWIN: 3}}]}
    per = {"rozela": {"state": "ok", "data": D.cancel_norm(raw)}}
    out = D.cancel_view(per, [{"username": OWNER}, {"username": AGENT_TWIN}], ["2026-11-20"], "2026-11-20", today="2026-11-20")
    assert [a["user"] for a in out["agents"]] == [AGENT_TWIN]
    assert out["total"]["2026-11-20"]["subs_team"] == 5


def test_sla_per_agent_drops_the_owner_and_keeps_him_in_the_totals():
    now = time.time()
    iso = lambda ts: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))       # noqa: E731
    rows = [{"id": "a", "status": "sent", "handled_by": OWNER, "handled_at": iso(now - 600), "waiting_since": iso(now - 1200), "created_at": iso(now - 1200)},
            {"id": "b", "status": "sent", "handled_by": AGENT_TWIN, "handled_at": iso(now - 600), "waiting_since": iso(now - 1200), "created_at": iso(now - 1200)}]
    out = sla.completed(rows, now - 86400, now + 1, sla.DEFAULT)
    assert set(out["agents"]) == {AGENT_TWIN}
    assert out["first_reply"]["n"] == 2


def test_weekly_summary_sent_by_drops_the_owner():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    import datetime as dt
    import driver
    stats = {"rozela": {"received": {"email": 1, "whatsapp": 1}, "sent": {"human": 9, "byAgent": {OWNER: 4, AGENT_TWIN: 5}}}}
    _, body = driver.compose_weekly(stats, dt.datetime(2026, 11, 26, 18, 0))
    assert "%s 5" % AGENT_TWIN in body and "%s 4" % OWNER not in body and "נשלחו: 9 ידנית" in body


def test_quality_check_never_samples_the_owner(app, pw_hash):
    c, _ = manager(app, pw_hash)
    add_user(app, pw_hash, OWNER, ["agent", "admin"], ALL)
    add_user(app, pw_hash, AGENT_TWIN, ["agent"], ALL)
    log = app.extensions["cs"]["activity"]["log"]
    now = time.time() - 600
    for i in range(3):
        log.record(OWNER, "rozela", "o%d" % i, "email", "send", "shipping", ts=now + i)       # an older row
        log.record(AGENT_TWIN, "rozela", "g%d" % i, "email", "send", "shipping", ts=now + i)
    b = c.get("/api/dash/quality").get_json()
    assert {i["agent"] for i in b["items"]} == {AGENT_TWIN}
    table = b.get("agents") or b.get("table") or []
    assert table and OWNER not in [r.get("user") for r in table] and AGENT_TWIN in [r.get("user") for r in table]


# ---------------------------------------------------------------- ticket presence chip

def test_owner_is_never_a_presence_chip_but_sees_the_others(app, pw_hash, transport):
    g, gtok = owner(app, pw_hash)
    twin, ttok = logged_in(app, pw_hash, AGENT_TWIN, ["agent"], ALL)
    m, mtok = manager(app, pw_hash)
    assert g.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers=H(gtok)).status_code == 200
    assert g.post("/api/rozela/watch", json={"id": "t1", "at": 0, "ed": True}, headers=H(gtok)).status_code == 200
    assert twin.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers=H(ttok)).status_code == 200
    r = m.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers=H(mtok)).get_json()
    w = m.post("/api/rozela/watch", json={"id": "t1", "at": 0}, headers=H(mtok)).get_json()
    for others in (r["others"], w["others"]):
        users = [o["user"] for o in others]
        assert OWNER not in users and AGENT_TWIN in users
    seen_by_owner = [o["user"] for o in g.post("/api/rozela/watch", json={"id": "t1", "at": 0}, headers=H(gtok)).get_json()["others"]]
    assert AGENT_TWIN in seen_by_owner and "mgr-cs" in seen_by_owner


# ---------------------------------------------------------------- user manager: last sign-in, change log

def test_manager_sees_no_owner_last_login_but_the_owner_and_the_twin_do(app, pw_hash):
    g, _ = owner(app, pw_hash)                            # he signed in: last_login is set in the store
    logged_in(app, pw_hash, AGENT_TWIN, ["agent"], ALL)
    assert store_of(app).get(OWNER)["last_login"]
    m, _ = manager(app, pw_hash)
    users = {u["username"]: u for u in m.get("/api/manage/users").get_json()["users"]}
    assert OWNER in users                                 # the account is still listed
    assert "last_login" not in users[OWNER] and "updated_at" not in users[OWNER] and users[OWNER]["locked"] is True
    assert users[AGENT_TWIN]["last_login"] and "locked" not in users[AGENT_TWIN]
    own = {u["username"]: u for u in g.get("/api/manage/users").get_json()["users"]}
    assert own[OWNER]["last_login"] and "locked" not in own[OWNER]
    assert g.get("/api/me").get_json()["user"]["last_login"]


def test_ops_account_may_change_the_owner_but_still_sees_no_sign_in_time(app, pw_hash):
    owner(app, pw_hash)
    ops, otok = logged_in(app, pw_hash, "claude-admin", ["admin", "user-manager"], ALL)
    u = {x["username"]: x for x in ops.get("/api/manage/users").get_json()["users"]}[OWNER]
    assert "last_login" not in u and "locked" not in u
    r = ops.post("/api/manage/users/%s/reset" % OWNER, json={}, headers=H(otok))
    assert r.status_code == 200 and r.get_json()["temp_password"]


def test_change_log_hides_every_owner_line_from_the_manager(app, pw_hash):
    g, gtok = owner(app, pw_hash)
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert g.post("/api/manage/users/noa", json={"display_name": "נועה"}, headers=H(gtok)).status_code == 200
    m, _ = manager(app, pw_hash)
    lines = m.get("/api/manage/audit").get_json()["lines"]
    assert lines and not [x for x in lines if OWNER in (x.get("actor"), x.get("target"))]
    mine = g.get("/api/manage/audit").get_json()["lines"]
    assert [x for x in mine if x.get("actor") == OWNER and x.get("action") == "login"]


def test_every_web_call_of_public_user_names_its_viewer():
    """The gate: a new route that forgets the viewer would hand the owner's sign-in time to anyone."""
    import glob
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    calls = []
    for f in glob.glob(os.path.join(root, "*.py")) + glob.glob(os.path.join(root, "*", "*.py")):
        if os.path.basename(f) in ("manage.py", "users_store.py") or "/tests/" in f or "/.venv/" in f:
            continue                                                    # the CLI on the server: the whole record, by design
        calls += [(f, c) for c in re.findall(r"public_user\(([^()]*)\)", open(f, encoding="utf-8").read())]
    assert calls and all("," in c for _, c in calls), calls
    u = {"username": OWNER, "last_login": "2026-11-25T08:00:00Z", "updated_at": "x"}
    assert public_user(u)["last_login"]                                  # the server's command line: the whole record
    assert "last_login" not in public_user(u, "mgr-cs")


# ---------------------------------------------------------------- the owner account is locked

def test_manager_admin_cannot_reset_disable_or_edit_the_owner(app, pw_hash):
    owner(app, pw_hash)
    add_user(app, pw_hash, AGENT_TWIN, ["agent"], ALL)
    m, tok = manager(app, pw_hash)
    before = store_of(app).get(OWNER)
    for path, body in (("/api/manage/users/%s/reset" % OWNER, {}), ("/api/manage/users/%s" % OWNER, {"disabled": True}),
                       ("/api/manage/users/%s" % OWNER, {"roles": ["agent"]}), ("/api/manage/users/%s" % OWNER, {"brands": ["rozela"]}),
                       ("/api/manage/users/%s" % OWNER, {"display_name": "x"}), ("/api/manage/users/%s" % OWNER, {"lang": "en"})):
        r = m.post(path, json=body, headers=H(tok))
        j = r.get_json()
        assert r.status_code == 403 and j["error"] == "owner_protected" and "temp_password" not in j, (path, body, j)
        assert re.search("[א-ת]", j["msg"]), j
    after = store_of(app).get(OWNER)
    assert (after["pw"], after["roles"], after["brands"], after["disabled"], after.get("display_name"), after.get("sv")) == \
           (before["pw"], before["roles"], before["brands"], before["disabled"], before.get("display_name"), before.get("sv"))
    # the twin is an ordinary account
    assert m.post("/api/manage/users/%s/reset" % AGENT_TWIN, json={}, headers=H(tok)).status_code == 200
    assert m.post("/api/manage/users/%s" % AGENT_TWIN, json={"disabled": True}, headers=H(tok)).status_code == 200


def test_the_owner_still_edits_himself(app, pw_hash):
    g, tok = owner(app, pw_hash)
    assert g.post("/api/manage/users/%s" % OWNER, json={"display_name": "G"}, headers=H(tok)).status_code == 200
    assert g.post("/api/manage/users/%s" % OWNER, json={"disabled": True}, headers=H(tok)).get_json()["error"] == "self_lockout"


def test_configure_accepts_any_iterable_and_restores():
    before = (owners.HIDDEN, owners.OPS)
    try:
        owners.configure(hidden=["Guy", 7, None], ops=("claude-admin",))
        assert owners.is_hidden("guy") and not owners.is_hidden("7x")
    finally:
        owners.HIDDEN, owners.OPS = before


def test_change_log_drops_a_line_that_names_the_owner_anywhere(app, pw_hash):
    m, _ = manager(app, pw_hash)
    st = store_of(app)
    st.audit("mgr-cs", "quality_rated", "rozela:t1:x", {"agent": OWNER, "score": 3})
    st.audit("mgr-cs", "quality_rated", "rozela:t2:x", {"agent": AGENT_TWIN, "score": 3})
    lines = m.get("/api/manage/audit").get_json()["lines"]
    agents = [(x.get("detail") or {}).get("agent") for x in lines if x.get("action") == "quality_rated"]
    assert agents == [AGENT_TWIN]
