"""Managers' dashboard (Owner, 2026-10-06): permissions, real work time (5-min idle gap, midnight), handle time in a burst,
brand counters, the activity log written by real screen actions, snapshots."""
import json

import dashboard as D
from conftest import call, logged_in

DAY = "2026-10-05"
T0 = D.day_start(DAY)                       # 00:00 Asia/Jerusalem
USERS = [{"username": "noa", "display_name": "נועה", "roles": ["agent"], "brands": ["rozela"]},
         {"username": "dana", "display_name": "דנה", "roles": ["agent"], "brands": ["rozela"]}]


def mklog(tmp_path, now):
    return D.ActivityLog(str(tmp_path / "act"), clock=lambda: now[0])


def ev(log, ts, kind, t="t1", u="noa", b="rozela", ch="email", cat="shipping"):
    assert log.record(u, b, t, ch, kind, cat, ts=ts) or kind in D.DEDUPE_S


def agent(out, u="noa"):
    return next(a for a in out["agents"] if a["user"] == u)


# ---------- active time: the 5-minute idle gap ----------

def test_gap_of_exactly_five_minutes_is_one_session(tmp_path):
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    ev(log, T0 + 36000, "open")
    ev(log, T0 + 36000 + D.IDLE_GAP_S, "send")
    a = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    assert a["active_s"] == D.IDLE_GAP_S + D.SESSION_TAIL_S                  # 300 + 60: one session


def test_a_gap_over_five_minutes_ends_the_session(tmp_path):
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    ev(log, T0 + 36000, "open")
    ev(log, T0 + 36000 + D.IDLE_GAP_S + 1, "send")
    a = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    assert a["active_s"] == 2 * D.SESSION_TAIL_S                             # two sessions of one action each
    assert len(D.sessions(log.events(DAY))) == 2


def test_login_time_without_actions_is_not_work(tmp_path):
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    for m in range(60):                                                      # an hour of the screen open and polling
        log.touch("noa", ts=T0 + 36000 + m * 60)
    ev(log, T0 + 36000, "open")
    a = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    assert a["active_s"] == D.SESSION_TAIL_S and a["present_s"] == 3600
    assert a["occupancy"] == round(D.SESSION_TAIL_S / 3600, 3)


def test_a_session_across_midnight_is_split_between_the_days(tmp_path):
    nxt = D.next_day(DAY)
    now = [D.day_start(nxt) + 40000]
    log = mklog(tmp_path, now)
    ev(log, D.day_start(nxt) - 120, "open")                                  # 23:58
    ev(log, D.day_start(nxt) + 120, "send")                                  # 00:02 the next day
    d1 = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    d2 = agent(D.build(log, {}, USERS, ["rozela"], nxt, 1, now[0]))
    assert d1["active_s"] == 120                                             # until midnight
    assert d2["active_s"] == 120 + D.SESSION_TAIL_S                          # the rest — the open was loaded from the day before
    assert d2["aht_s"] == 240 and d2["sends"] == 1 and d1["sends"] == 0
    both = agent(D.build(log, {}, USERS, ["rozela"], nxt, 2, now[0]))
    assert both["active_s"] == 240 + D.SESSION_TAIL_S and [x["active_s"] for x in both["days"]] == [120, 180]


# ---------- handle time ----------

def test_sends_in_a_burst_each_get_their_own_handle_time(tmp_path):
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    b = T0 + 40000
    for t, o, s in (("a", 0, 60), ("b", 61, 90), ("c", 91, 100)):           # send -> next -> send, seconds apart
        ev(log, b + o, "open", t=t)
        ev(log, b + s, "send", t=t)
    a = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    assert a["sends"] == 3 and a["handled"] == 3 and a["aht_s"] == 29        # 60, 29, 9
    assert a["active_s"] == 100 + D.SESSION_TAIL_S


def test_a_send_without_an_open_or_hours_later_has_no_handle_time(tmp_path):
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    ev(log, T0 + 1000, "open", t="x")
    ev(log, T0 + 1000 + D.HANDLE_MAX_S + 1, "send", t="x")
    ev(log, T0 + 20000, "send", t="y")
    a = agent(D.build(log, {}, USERS, ["rozela"], DAY, 1, now[0]))
    assert a["sends"] == 2 and a["handled"] == 0 and a["aht_s"] is None


# ---------- brand counters ----------

def iso(ts):
    return D.datetime.fromtimestamp(ts, D.TZ).isoformat()


def test_brand_overview_counts(tmp_path):
    now = T0 + 15 * 3600                                                     # 15:00
    rows = [
        {"id": "a", "status": "ready", "created_at": iso(now - 3600), "waiting_since": iso(now - 3600)},           # 0-4h
        {"id": "b", "status": "action", "created_at": iso(now - 10 * 3600), "waiting_since": iso(now - 10 * 3600)},  # 4-24h
        {"id": "c", "status": "delay", "created_at": iso(now - 2 * 86400), "waiting_since": iso(now - 2 * 86400)},   # 1-3d
        {"id": "d", "status": "health", "created_at": iso(now - 9 * 86400), "waiting_since": iso(now - 9 * 86400)},  # 3d+
        {"id": "e", "status": "sent", "created_at": iso(now - 5 * 3600), "handled_at": iso(now - 4 * 3600), "handled_by": "noa"},
        {"id": "f", "status": "sent", "created_at": iso(now - 2 * 3600), "handled_at": iso(now - 3600), "handled_by": "auto-reply",
         "channel": "email"},
        {"id": "g", "status": "done", "created_at": iso(now - 3 * 3600), "handled_at": iso(now - 1800), "handled_by": "noa"},
        {"id": "h", "status": "bot", "channel": "whatsapp", "created_at": iso(now - 86400 * 3)},
        {"id": "i", "status": "action", "channel": "whatsapp", "action": "⚠️ בדקו בדונדי לפני שליחה חוזרת",
         "created_at": iso(now - 7200), "waiting_since": iso(now - 7200)},
        {"id": "j", "status": "sent", "created_at": iso(now - 86400 * 2), "handled_at": iso(now - 86400 * 2)},       # not today
    ]
    o = D.overview(rows, DAY, now)
    assert (o["received"], o["answered"], o["closed"]) == (6, 2, 1)          # a b e f g i created today
    assert o["answered_pct"] == 33.3 and o["closed_pct"] == 16.7
    assert o["open_now"] == 6 and o["awaiting"] == 5                         # + bot; awaiting = needs a person
    assert o["aging"] == {"0-4h": 2, "4-24h": 1, "1-3d": 1, "3d+": 1}
    assert o["frt_median_s"] == 3600 and o["auto_pct"] == 50.0 and o["wa_failed"] == 1 and o["truncated"] is False


def test_a_full_closed_list_from_today_is_flagged_as_partial(tmp_path):
    now = T0 + 20 * 3600
    rows = [{"id": "x%d" % i, "status": "done", "created_at": iso(T0 + 60), "handled_at": iso(T0 + 3600 + i)} for i in range(100)]
    assert D.overview(rows, DAY, now)["truncated"] is True


# ---------- permissions and the real screen path ----------

def test_only_admins_and_user_managers_see_the_dashboard(app, pw_hash):
    c, _ = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert c.get("/api/dash").status_code == 403
    assert c.get("/api/me").get_json()["can_manage_users"] is False         # the client hides the tab on this
    m, _ = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert m.get("/api/dash").get_json()["ok"] is True
    a, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    assert a.get("/api/dash?range=7").get_json()["ok"] is True
    assert a.get("/api/dash?range=9").status_code == 400 and a.get("/api/dash?date=../x").status_code == 400
    assert app.test_client().get("/api/dash").status_code == 401


def test_screen_actions_land_in_the_log_and_the_dashboard(app, pw_hash, transport):
    def reply(url, body):
        fn, a = body["fn"], body.get("args") or {}
        if fn == "apiTicketFull":
            return {"ok": True, "ticket": {"id": a["id"], "status": "ready", "channel": "whatsapp"}, "extras": {}}
        if fn == "apiBoot":
            return {"ok": True, "version": 1, "counts": {"ready": 1},
                    "tickets": [{"id": "w1", "status": "ready", "channel": "whatsapp", "category": "shipping"}]}
        if fn == "apiSend":
            return {"ok": True, "queued": True}
        from conftest import valid_reply
        return valid_reply(url, body)
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok})
    c.post("/api/rozela/ticket", json={"id": "w1", "open": True}, headers={"X-CSRF-Token": tok})
    c.post("/api/rozela/ticket", json={"id": "w1", "open": True, "revalidate": True}, headers={"X-CSRF-Token": tok})  # not an open
    assert c.post("/api/rozela/activity", json={"id": "w1", "kind": "edit"}, headers={"X-CSRF-Token": tok}).get_json()["ok"]
    call(c, tok, "rozela", "apiSend", {"id": "w1", "text": "היי", "channel": "whatsapp"})
    c.post("/api/rozela/apiSend", json={"args": {"id": "w1", "text": "היי"}, "via": "resend"}, headers={"X-CSRF-Token": tok})
    transport.reply = lambda u, b: {"ok": True, "queued": True, "already": True} if b["fn"] == "apiSend" else reply(u, b)
    call(c, tok, "rozela", "apiSend", {"id": "w1", "text": "היי"})                                   # a duplicate: not a send
    log = app.extensions["cs"]["activity"]["log"]
    kinds = [(e["k"], e["ch"], e["cat"]) for e in log.events(D.il_day(log.clock()))]
    assert kinds == [("open", "whatsapp", "shipping"), ("edit", "whatsapp", "shipping"), ("send", "whatsapp", "shipping"),
                     ("resend", "whatsapp", "shipping")]
    assert set(json.dumps(e) for e in log.events(D.il_day(log.clock()))) and all("text" not in e for e in log.events(D.il_day(log.clock())))
    a, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    out = a.get("/api/dash").get_json()
    n = next(x for x in out["agents"] if x["user"] == "noa")
    assert n["sends"] == 2 and n["resends"] == 1 and n["handled"] == 1 and n["present_s"] >= 60
    assert n["by_channel"]["whatsapp"]["sends"] == 2 and "whatsapp" in out["pies"]["channel"]   # (live: clipped at now)
    m, mt = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert m.post("/api/rozela/activity", json={"id": "w1", "kind": "edit"}, headers={"X-CSRF-Token": mt}).status_code == 403


def test_midnight_snapshot_keeps_the_day_and_serves_it(app, pw_hash):
    act = app.extensions["cs"]["activity"]
    log = act["log"]
    assert act["snapshot_once"]() is True and act["snapshot_once"]() is False      # once per day
    y = D.prev_day(D.il_day(log.clock()))
    a, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    out = a.get("/api/dash?date=%s" % y).get_json()
    assert out["brands"]["rozela"]["source"] == "snapshot"


def test_handle_time_belongs_to_the_ticket_even_when_the_agent_looks_elsewhere(tmp_path):
    """In a burst the agent opens the next ticket before sending: open A, open B, send A, send B -> 60 s each."""
    now = [T0 + 86000]
    log = mklog(tmp_path, now)
    b = T0 + 50000
    ev(log, b, "open", t="a")
    ev(log, b + 10, "open", t="b")
    ev(log, b + 60, "send", t="a")
    ev(log, b + 70, "send", t="b")
    assert sorted(x for _, x in D.handle_times(log.events(DAY))) == [60, 60]
