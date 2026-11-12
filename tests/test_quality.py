"""The CS manager's daily sampled quality check (quality.py, the owner 2026-11-12).
Roles (admin + user-manager only), CSRF, the sample (per agent per brand, capped, fixed for the day, append-only, closed-with-no-reply first,
only real agents), the per-agent signals from the agent's OWN clicks, rating validation, "done" refused until every item is rated, audit,
restart persistence, the reminder hour, and the one-ticket view (customer message / sent reply / AI draft). The same tests run on Postgres
with CS_TEST_PG=<url>."""
import time

import pytest

import dashboard
import quality
from conftest import audit_text, client_for, logged_in, add_user  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "velora"]
CHK = {"answered": True, "correct": True, "personal": False, "tone": True}


def log_of(app):
    return app.extensions["cs"]["activity"]["log"]


def rec(app, user, brand, tid, kind, ts, ch="email"):
    assert log_of(app).record(user, brand, tid, ch, kind, "shipping", ts=ts) or kind in ("open", "edit")


@pytest.fixture
def mgr(app, pw_hash):
    return logged_in(app, pw_hash, "agent-two", ["admin", "user-manager"], ALL)


def agents(app, pw_hash, *names, brands=ALL):
    for n in names:
        add_user(app, pw_hash, n, ["agent"], brands)


def board(c, day=None):
    r = c.get("/api/dash/quality" + ("?day=" + day if day else ""))
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()


def rate(c, tok, day, key, score=4, checks=None, note=""):
    return c.post("/api/dash/quality/rate", json={"day": day, "key": key, "score": score, "checks": checks or dict(CHK), "note": note},
                  headers={"X-CSRF-Token": tok})


def today():
    return dashboard.il_day(time.time())


# ---------------------------------------------------------------- roles, login, CSRF

def test_agent_viewer_and_anonymous_are_refused(app, pw_hash):
    for name, roles in (("agent1", ["agent"]), ("tamir", ["viewer"])):
        c, tok = logged_in(app, pw_hash, name, roles, ["rozela"])
        for path in ("/api/dash/quality", "/api/dash/quality/status", "/api/dash/quality/item?key=rozela:t1:a"):
            assert c.get(path).status_code == 403, (name, path)
        r = c.post("/api/dash/quality/rate", json={"day": today(), "key": "rozela:t1:a", "score": 5, "checks": CHK, "note": ""}, headers={"X-CSRF-Token": tok})
        assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role"
        assert c.post("/api/dash/quality/done", json={"day": today()}, headers={"X-CSRF-Token": tok}).status_code == 403
    assert client_for(app).get("/api/dash/quality").status_code == 401


def test_pure_user_manager_may_run_the_check(app, pw_hash):
    c, _ = logged_in(app, pw_hash, "um", ["user-manager"], ALL)
    assert c.get("/api/dash/quality/status").status_code == 200


def test_writes_need_csrf_and_same_origin(app, pw_hash, mgr):
    c, tok = mgr
    agents(app, pw_hash, "paula")
    rec(app, "paula", "rozela", "t1", "send", time.time() - 30)
    key = board(c)["items"][0]["key"]
    assert c.post("/api/dash/quality/rate", json={"day": today(), "key": key, "score": 4, "checks": CHK, "note": ""}).status_code == 403
    assert c.post("/api/dash/quality/rate", json={"day": today(), "key": key, "score": 4, "checks": CHK, "note": ""},
                  headers={"X-CSRF-Token": tok, "Origin": "https://evil.example"}).status_code == 403
    assert not app.extensions["cs"]["quality"].ratings([today()])


# ---------------------------------------------------------------- the sample

def test_sample_per_agent_per_brand_capped_fixed_for_the_day_and_only_real_agents(app, pw_hash, mgr):
    c, _ = mgr
    agents(app, pw_hash, "paula", "amit")
    add_user(app, pw_hash, "qa-rozela", ["agent"], ALL)          # a QA account: never sampled
    now = time.time() - 600
    for i in range(8):
        rec(app, "paula", "rozela", "p%d" % i, "send", now + i)
        rec(app, "amit", "rozela", "a%d" % i, "send", now + i)
        rec(app, "qa-rozela", "rozela", "q%d" % i, "send", now + i)
    rec(app, "agent-two", "rozela", "m1", "send", now)                # the manager herself (admin, not an agent): not sampled
    rec(app, "paula", "celesta", "c1", "send", now)
    b1 = board(c)
    keys = [i["key"] for i in b1["items"]]
    by = {}
    for i in b1["items"]:
        by[(i["agent"], i["brand"])] = by.get((i["agent"], i["brand"]), 0) + 1
    assert by == {("amit", "rozela"): 3, ("paula", "celesta"): 1, ("paula", "rozela"): 3}
    assert all(i["agent"] in ("paula", "amit") for i in b1["items"])
    assert [i["key"] for i in board(c)["items"]] == keys, "a reload never reshuffles"
    # the same candidates on a fresh store draw the same sample (deterministic for the day)
    cands = quality.candidates(quality.analyse(log_of(app).events(today())), today(), {"paula", "amit"})
    assert [x["key"] for x in quality.top_up(today(), [], cands)] == keys


def test_sample_is_append_only_and_tops_up_later(app, pw_hash, mgr):
    c, _ = mgr
    agents(app, pw_hash, "paula")
    now = time.time() - 600
    rec(app, "paula", "rozela", "p1", "send", now)
    first = board(c)["items"]
    assert [i["tid"] for i in first] == ["p1"]
    for i in range(2, 9):
        rec(app, "paula", "rozela", "p%d" % i, "send", now + i)
    log_cache_bust(app)
    later = board(c)["items"]
    assert later[0]["key"] == first[0]["key"] and len(later) == 3, "the item drawn first stays; the group is topped up to 3"


def log_cache_bust(app):
    """The board keeps today's events 60 s; a test that adds events clears that copy instead of sleeping."""
    app.extensions["cs"]["quality_events"].clear()


def test_closed_without_reply_enters_first_and_a_closed_after_a_reply_does_not(app, pw_hash, mgr):
    c, _ = mgr
    agents(app, pw_hash, "paula", "amit")
    now = time.time() - 900
    for i in range(5):
        rec(app, "paula", "rozela", "s%d" % i, "send", now + i)
    rec(app, "paula", "rozela", "x1", "close", now + 10)                 # closed, nobody answered: a signal
    rec(app, "amit", "rozela", "y1", "send", now + 20)
    rec(app, "paula", "rozela", "y1", "close", now + 30)                 # closed after amit's reply: fine
    items = [i for i in board(c)["items"] if i["agent"] == "paula"]
    assert items[0]["tid"] == "x1" and items[0]["kind"] == "closed"
    assert "y1" not in [i["tid"] for i in items]


def test_untouched_is_per_agent_own_keystrokes(app, pw_hash, mgr):
    c, _ = mgr
    agents(app, pw_hash, "paula", "amit")
    now = time.time() - 1200
    rec(app, "paula", "rozela", "e1", "edit", now)                       # paula typed in e1, then sent it
    rec(app, "paula", "rozela", "e1", "send", now + 30)
    rec(app, "amit", "rozela", "e2", "edit", now)                        # amit typed in e2 ...
    rec(app, "paula", "rozela", "e2", "send", now + 40)                  # ... paula sent it untouched by HER: untouched
    rec(app, "paula", "rozela", "e3", "send", now + 50)                  # nobody typed
    b = board(c)
    flags = {i["tid"]: i["untouched"] for i in b["items"]}
    assert flags == {"e1": False, "e2": True, "e3": True}
    row = [a for a in b["agents"] if a["user"] == "paula"][0]
    assert row["sends"] == 3 and row["untouched_pct"] == pytest.approx(66.7) and row["today_untouched"] == 2
    assert not [a for a in b["agents"] if a["user"] == "amit"], "amit's keystrokes are not replies of his: no row for him"


# ---------------------------------------------------------------- rating + done

def test_rating_validation(app, pw_hash, mgr):
    c, tok = mgr
    agents(app, pw_hash, "paula")
    rec(app, "paula", "rozela", "t1", "send", time.time() - 30)
    key = board(c)["items"][0]["key"]
    d = today()
    for bad in (dict(score=0), dict(score=6), dict(score="5"), dict(score=True)):
        r = rate(c, tok, d, key, **bad)
        assert r.status_code == 400 and r.get_json()["error"] == "quality_bad_rating", bad
    assert rate(c, tok, d, key, checks={"answered": True}).get_json()["error"] == "quality_bad_rating"
    assert rate(c, tok, d, key, checks=dict(CHK, tone="yes")).get_json()["error"] == "quality_bad_rating"
    assert rate(c, tok, d, key, note="x" * 501).get_json()["error"] == "quality_bad_note"
    assert rate(c, tok, d, "rozela:other:paula").status_code == 404
    assert rate(c, tok, "2999-01-01", key).status_code == 400
    assert not app.extensions["cs"]["quality"].ratings([d])
    r = rate(c, tok, d, key, score=2, note="  לא ענתה על השאלה  ")
    assert r.status_code == 200 and r.get_json()["rating"]["note"] == "לא ענתה על השאלה"
    assert rate(c, tok, d, key, score=3).status_code == 200, "re-rating overwrites"
    rs = app.extensions["cs"]["quality"].ratings([d])
    assert len(rs) == 1 and rs[0]["score"] == 3 and rs[0]["agent"] == "paula" and rs[0]["by"] == "agent-two"
    assert '"quality_rated"' in audit_text(app)


def test_done_refused_until_every_item_is_rated_then_frozen(app, pw_hash, mgr):
    c, tok = mgr
    agents(app, pw_hash, "paula")
    now = time.time() - 600
    for i in range(2):
        rec(app, "paula", "rozela", "t%d" % i, "send", now + i)
    d = today()
    items = board(c)["items"]
    assert len(items) == 2
    r = c.post("/api/dash/quality/done", json={"day": d}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 409 and r.get_json()["error"] == "quality_unrated" and "2" in r.get_json()["msg"]
    assert c.get("/api/dash/quality/status").get_json()["done"] is False
    for it in items:
        assert rate(c, tok, d, it["key"]).status_code == 200
    r = c.post("/api/dash/quality/done", json={"day": d}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200 and r.get_json()["day_rec"]["done"] and r.get_json()["day_rec"]["done_by"] == "agent-two"
    assert c.post("/api/dash/quality/done", json={"day": d}, headers={"X-CSRF-Token": tok}).get_json()["changed"] is False
    assert audit_text(app).count('"quality_day_done"') == 1
    rec(app, "paula", "rozela", "t9", "send", now + 50)
    log_cache_bust(app)
    st = c.get("/api/dash/quality/status").get_json()
    assert st["done"] and st["n"] == 2, "nothing joins after done"
    b = board(c)
    row = [a for a in b["agents"] if a["user"] == "paula"][0]
    assert row["score"] == 4.0 and row["rated"] == 2 and row["checks"]["personal"] == 0.0 and row["checks"]["answered"] == 100.0
    assert b["history"][-1] == {"day": d, "done": True, "done_by": "agent-two", "done_by_name": "agent-two", "done_at": b["history"][-1]["done_at"], "n": 2}


def test_done_on_an_empty_day(app, mgr):
    c, tok = mgr
    r = c.post("/api/dash/quality/done", json={"day": today()}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 409 and r.get_json()["error"] == "quality_empty"


def test_survives_a_restart(make_app, pw_hash, tmp_path):
    a1 = make_app(QUALITY_PATH=str(tmp_path / "q.json"))
    c, tok = logged_in(a1, pw_hash, "agent-two", ["admin", "user-manager"], ALL)
    add_user(a1, pw_hash, "paula", ["agent"], ALL)
    rec(a1, "paula", "rozela", "t1", "send", time.time() - 30)
    key = board(c)["items"][0]["key"]
    assert rate(c, tok, today(), key, score=5).status_code == 200
    a2 = make_app(QUALITY_PATH=str(tmp_path / "q.json"))
    assert [r["score"] for r in a2.extensions["cs"]["quality"].ratings([today()])] == [5]
    assert a2.extensions["cs"]["quality"].day(today())["sample"][0]["key"] == key


# ---------------------------------------------------------------- reminder + status

def test_reminder_hour(app, pw_hash, mgr, monkeypatch):
    c, _ = mgr
    agents(app, pw_hash, "paula")
    monkeypatch.setenv("QUALITY_REMIND_HOUR", "24")
    assert c.get("/api/dash/quality/status").get_json()["remind_modal"] is False, "nothing to check: no reminder"
    rec(app, "paula", "rozela", "t1", "send", time.time() - 30)
    log_cache_bust(app)
    s = c.get("/api/dash/quality/status").get_json()
    assert s["n"] == 1 and s["rated"] == 0 and s["remind_modal"] is False
    monkeypatch.setenv("QUALITY_REMIND_HOUR", "0")
    assert c.get("/api/dash/quality/status").get_json()["remind_modal"] is True


def test_brand_scope(app, pw_hash):
    add_user(app, pw_hash, "paula", ["agent"], ALL)
    c, tok = logged_in(app, pw_hash, "um2", ["user-manager"], ["celesta"])
    rec(app, "paula", "rozela", "t1", "send", time.time() - 30)
    rec(app, "paula", "celesta", "t2", "send", time.time() - 20)
    b = board(c)
    assert [i["brand"] for i in b["items"]] == ["celesta"]
    assert c.get("/api/dash/quality/item?day=%s&key=rozela:t1:paula" % today()).status_code == 404
    r = c.post("/api/dash/quality/done", json={"day": today()}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 403 and r.get_json()["error"] == "quality_other_brands"


# ---------------------------------------------------------------- one item

def iso(ts):
    from datetime import datetime
    return datetime.fromtimestamp(ts, dashboard.TZ).isoformat()


def test_item_view_pure():
    t0 = 1_800_000_000.0
    full = {"ticket": {"status": "sent", "subject": "איפה ההזמנה"}, "extras": {
        "conversation": [{"who": "customer", "at": iso(t0 - 7200), "text": "שאלה ישנה"}, {"who": "us", "at": iso(t0 - 7000), "text": "תשובה ישנה"},
                         {"who": "customer", "at": iso(t0 - 600), "text": "איפה ההזמנה שלי?"}, {"who": "customer", "at": iso(t0 - 500), "text": "הלו?"},
                         {"who": "us", "at": iso(t0 + 20), "text": "היי, ההזמנה בדרך, הנה המעקב."}],
        "aiDraft": {"text": "היי, ההזמנה בדרך, הנה המעקב.", "msg": "m", "at": iso(t0 - 100)}}}
    v = quality.item_view({"kind": "send", "ts": t0}, full)
    assert [m["text"] for m in v["customer"]] == ["איפה ההזמנה שלי?", "הלו?"]
    assert v["sent"]["text"] == "היי, ההזמנה בדרך, הנה המעקב." and v["draft"]["same"] is True
    full["extras"]["conversation"][-1]["text"] = "היי דנה, בדקתי: החבילה בסניף הדואר ברחוב הרצל, אפשר לאסוף מחר."
    v = quality.item_view({"kind": "send", "ts": t0}, full)
    assert v["draft"]["same"] is False and v["draft"]["overlap"] < 0.5
    v = quality.item_view({"kind": "closed", "ts": t0 - 400}, full)
    assert v["sent"] is None and [m["text"] for m in v["customer"]] == ["איפה ההזמנה שלי?", "הלו?"]
    del full["extras"]["aiDraft"]
    assert quality.item_view({"kind": "send", "ts": t0}, full)["draft"] is None


def test_item_route_reads_the_ticket_through_the_cache(app, pw_hash, mgr, transport):
    c, _ = mgr
    agents(app, pw_hash, "paula")
    ts = time.time() - 60
    rec(app, "paula", "rozela", "t1", "send", ts)
    conv = [{"who": "customer", "at": iso(ts - 300), "text": "מתי מגיע?"}, {"who": "us", "at": iso(ts + 2), "text": "תוך 3 ימים."}]

    def reply(url, body):
        if body["fn"] == "apiTicketFull":
            return {"ok": True, "ticket": {"id": "t1", "status": "sent"}, "extras": {"conversation": conv}}
        from conftest import valid_reply
        return valid_reply(url, body)
    transport.reply = reply
    key = board(c)["items"][0]["key"]
    r = c.get("/api/dash/quality/item?day=%s&key=%s" % (today(), key)).get_json()
    assert r["ok"] and r["customer"][0]["text"] == "מתי מגיע?" and r["sent"]["text"] == "תוך 3 ימים." and r["untouched"] is True
    assert not [e for e in log_of(app).events(today()) if e["u"] == "agent-two"], "a manager's check is not agent activity"
