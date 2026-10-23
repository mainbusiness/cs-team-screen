"""Cancellations on the managers' board (Owner, 2026-10-23: "שים גם בלוח המנהלים שאראה כמה מנויים הצוות מבטל כל יום וכמה ביטולים בכללי הוא
עושה ללקוחות"). Engine fn apiCancelStats (admin read) -> proxy (roles, args, reply schema) -> /api/dash/cancels (admins only, cached, read in
the background, never waits for the engine) -> the view the board draws (totals, per agent, churn vs the target = half of last month)."""
from datetime import date, timedelta

import pytest

import dashboard as D
import engine_proxy
from conftest import add_user, call, logged_in, store_of, valid_reply

TODAY = "2026-10-23"
NOW = D.day_start(TODAY) + 15 * 3600            # 15:00 Israel


def days_back(to, n):
    return [(date.fromisoformat(to) - timedelta(days=i)).isoformat() for i in range(n)]


def stats_reply(calls, states=None, absent=(), nulls=()):
    """A fake engine: apiCancelStats per brand (state from `states`), every other fn schema-valid. `absent` brands answer like an engine
    without the fn; `nulls` brands send null for orders_cancelled / subs_all_kaching."""
    states = states or {}

    def reply(url, body):
        fn, a = body["fn"], body.get("args") or {}
        if fn != "apiCancelStats":
            return valid_reply(url, body)
        b = a["brand"]
        calls.append((b, a["from"], a["to"]))
        if b in absent:
            return {"ok": False, "error": "unauthorized"}
        st = states.get(b, "ok")
        days = []
        for i, dd in enumerate(sorted(days_back(a["to"], (date.fromisoformat(a["to"]) - date.fromisoformat(a["from"])).days + 1))):
            by = {"agent-two": 2, "qa-bot": 5} if dd == TODAY else {"agent-two": 1}
            days.append({"date": dd, "subs_team": sum(by.values()),          # the engine counts the QA account too; the board takes it out
                         "subs_team_by": by, "subs_bot": 1,
                         "subs_all_kaching": None if (b in nulls or st == "no_kaching") else 6,
                         "orders_cancelled": None if b in nulls else 3})
        return {"ok": True, "brand": b, "tz": "Asia/Jerusalem", "kaching": st, "days": days,
                "month": {"month": "2026-10", "active_start": 800, "cancelled": 60, "churn_pct": 7.5, "partial": True},
                "prev_month": {"month": "2026-09", "active_start": 790, "cancelled": 111, "churn_pct": 14.05, "partial": False},
                "sources": {"subs_team": "יומן הביקורת של המנוע", "orders_cancelled": "שופיפיי cancelled_at"}}
    return reply


def clock(app, now):
    app.extensions["cs"]["activity"]["log"].clock = lambda: now[0]


def drain(app):
    app.extensions["cs"]["cancels_drain"]()


# ---------- proxy ----------

def test_cancel_stats_is_an_admin_only_read():
    assert engine_proxy.FN_TABLE["apiCancelStats"][0] == engine_proxy.ADMIN_ONLY
    assert "apiCancelStats" in engine_proxy.READ_FNS


@pytest.mark.parametrize("roles", [["agent"], ["user-manager"]])
def test_an_agent_or_user_manager_is_refused_before_the_engine(app, pw_hash, transport, roles):
    c, tok = logged_in(app, pw_hash, "x1", roles, ["rozela"])
    r = call(c, tok, "rozela", "apiCancelStats", {"from": "2026-10-10", "to": TODAY})
    assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role"
    assert [b for _, b in transport.calls if b["fn"] == "apiCancelStats"] == []
    assert c.get("/api/dash/cancels").status_code == 403


@pytest.mark.parametrize("args", [{"to": TODAY}, {"from": "2026-10-10"}, {"from": "2026-10-1", "to": TODAY}, {"from": "2026-02-30", "to": TODAY},
                                  {"from": TODAY, "to": "2026-10-10"}, {"from": "2026-08-22", "to": TODAY}, {"from": 20261010, "to": TODAY}])
def test_bad_ranges_never_reach_the_engine(app, pw_hash, transport, args):
    c, tok = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    assert call(c, tok, "rozela", "apiCancelStats", args).status_code == 400
    assert transport.calls == []


def test_args_are_rebuilt_and_62_days_is_the_limit(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls)
    c, tok = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    r = call(c, tok, "rozela", "apiCancelStats", {"from": "2026-08-23", "to": TODAY, "agent": "agent-two", "limit": 9})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    body = [b for _, b in transport.calls if b["fn"] == "apiCancelStats"][-1]
    assert body["args"] == {"from": "2026-08-23", "to": TODAY, "brand": "rozela"}


@pytest.mark.parametrize("bad", [
    {"ok": True},                                                                          # the doGet bare answer
    {"ok": True, "kaching": "maybe", "days": []},                                          # an unknown Kaching state
    {"ok": True, "kaching": "ok", "days": [{"date": "2026-09-01", "subs_team": 1}]},       # a day outside the range asked for
    {"ok": True, "brand": "celesta", "kaching": "ok", "days": []},                         # another brand's answer
    {"ok": True, "kaching": "ok", "days": [], "month": "October"},
])
def test_a_reply_that_is_not_this_range_is_never_drawn(app, pw_hash, transport, bad):
    transport.reply = lambda url, body: dict(bad) if body["fn"] == "apiCancelStats" else valid_reply(url, body)
    c, tok = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    r = call(c, tok, "rozela", "apiCancelStats", {"from": "2026-10-10", "to": TODAY})
    assert r.get_json()["ok"] is False and r.get_json()["error"] == "engine_bad_response"


# ---------- /api/dash/cancels ----------

def test_the_board_reads_in_the_background_then_shows_the_numbers_and_caches_them(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls, states={"velora": "no_kaching"})
    now = [NOW]
    clock(app, now)
    store_of(app).create("t", "agent-two", pw_hash, {"display_name": "נציגה ב", "roles": ["agent"], "brands": ["rozela"], "lang": "he"},
                         app.extensions["cs"]["valid_brands"], must_change=False)
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela", "celesta", "velora"])
    first = c.get("/api/dash/cancels").get_json()
    assert first["ok"] and first["busy"] and first["brands"]["rozela"]["state"] == "pending"     # nothing yet: "counting", not zeros
    assert first["brands"]["rozela"]["rows"] == {} and first["total"][TODAY]["subs_team"] is None
    drain(app)
    want = days_back(TODAY, D.CANCEL_DAYS)
    assert sorted(calls) == sorted((b, want[-1], TODAY) for b in ("rozela", "celesta", "velora"))
    o = c.get("/api/dash/cancels").get_json()
    assert o["dates"] == want and o["day"] == TODAY and not o["busy"]
    r = o["brands"]["rozela"]["rows"][TODAY]
    assert (r["subs_team"], r["subs_bot"], r["orders_cancelled"], r["team_total"], r["subs_all_kaching"]) == (2, 1, 3, 5, 6)
    t = o["total"][TODAY]
    assert (t["subs_team"], t["orders_cancelled"], t["team_total"]) == (6, 9, 15)
    assert t["subs_all_kaching"] == 12 and t["subs_all_kaching_missing"] == ["velora"]             # velora has no Kaching: named, not 0
    assert o["brands"]["velora"]["rows"][TODAY]["subs_all_kaching"] is None
    assert o["brands"]["velora"]["month"] is None and o["brands"]["velora"]["verdict"] is None      # "אין חיבור לקאצ'ינג"
    # per agent for the day: display names, test users out, summed over brands
    assert o["agents"] == [{"user": "agent-two", "name": "נציגה ב", "n": 6, "by_brand": {"rozela": 2, "celesta": 2, "velora": 2}}]
    assert o["unnamed"] == 0                                                                         # qa-bot's 5 per brand are out of subs_team
    # churn vs the goal (half of last month)
    m = o["brands"]["rozela"]
    assert (m["target"], m["verdict"], m["level"]) == (7.03, "bad", "healthy")       # 7.5% by day 23 = 10.11% at this pace
    assert (m["projected"], m["days_elapsed"], m["days_in_month"]) == (10.11, 23, 31)
    assert o["sources"]["subs_team"] == "יומן הביקורת של המנוע"
    n = len(calls)
    now[0] += D.CANCEL_TTL_S - 5
    c.get("/api/dash/cancels"); drain(app)
    assert len(calls) == n                                                                           # cached
    now[0] += 10
    c.get("/api/dash/cancels"); drain(app)
    assert len(calls) == n + 3                                                                       # re-read after the TTL


def test_null_fields_stay_unknown_and_a_brand_without_subscriptions_is_not_shown(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls, states={"velora": "no_subscriptions"}, nulls=("celesta",))
    clock(app, [NOW])
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela", "celesta", "velora"])
    c.get("/api/dash/cancels"); drain(app)
    o = c.get("/api/dash/cancels").get_json()
    assert "velora" not in o["brands"] and o["hidden"] == ["velora"]
    r = o["brands"]["celesta"]["rows"][TODAY]
    assert r["orders_cancelled"] is None and r["team_total"] is None and r["subs_team"] == 2       # never 0 for an unknown
    assert o["total"][TODAY]["team_total"] == 5 and o["total"][TODAY]["team_total_missing"] == ["celesta"]


def test_an_engine_without_the_fn_says_not_available_and_the_board_is_unaffected(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls, absent=("rozela", "celesta"))
    now = [NOW]
    clock(app, now)
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela", "celesta"])
    c.get("/api/dash/cancels"); drain(app)
    o = c.get("/api/dash/cancels").get_json()
    assert o["unavailable"] == ["celesta", "rozela"] and o["brands"]["rozela"]["state"] == "not_deployed"
    assert c.get("/api/dash").status_code == 200
    n = len(calls)
    now[0] += D.CANCEL_ERR_TTL_S + 5
    c.get("/api/dash/cancels"); drain(app)
    assert len(calls) == n                              # an old engine is asked again every few minutes, not every refresh
    now[0] += D.CANCEL_TTL_S
    c.get("/api/dash/cancels"); drain(app)
    assert len(calls) == n + 2


def test_a_failed_refresh_keeps_the_last_numbers_and_says_so(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls)
    now = [NOW]
    clock(app, now)
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    c.get("/api/dash/cancels"); drain(app)
    transport.reply = lambda url, body: {"ok": False, "error": "kaching_down"} if body["fn"] == "apiCancelStats" else valid_reply(url, body)
    now[0] += D.CANCEL_TTL_S + 1
    c.get("/api/dash/cancels"); drain(app)
    o = c.get("/api/dash/cancels").get_json()
    b = o["brands"]["rozela"]
    assert b["state"] == "ok" and b["rows"][TODAY]["subs_team"] == 2 and b["error"] == "kaching_down"


def test_an_engine_that_raises_is_tried_again_after_a_minute_not_on_every_refresh(app, pw_hash, transport):
    """Codex 2026-10-23: a failure by exception must be stamped like any other failure, or every board refresh starts a new read."""
    calls, good = [], []
    ok_reply = stats_reply(good)

    def boom(url, body):
        if body["fn"] == "apiCancelStats":
            calls.append(1)
            raise RuntimeError("socket died")
        return valid_reply(url, body)
    now = [NOW]
    clock(app, now)
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela", "celesta"])
    transport.reply = lambda url, body: ok_reply(url, body) if body["fn"] != "apiCancelStats" or body["args"]["brand"] == "rozela" else boom(url, body)
    c.get("/api/dash/cancels"); drain(app)                  # rozela good; celesta raises with no earlier copy
    transport.reply = boom
    now[0] += D.CANCEL_TTL_S + 1                            # rozela's good copy is stale now
    for _ in range(4):
        c.get("/api/dash/cancels"); drain(app)
        now[0] += 10
    assert len(calls) == 3                                  # celesta once at first, then ONE more read per brand — not one per refresh
    b = c.get("/api/dash/cancels").get_json()["brands"]
    assert b["rozela"]["rows"][TODAY]["subs_team"] == 2 and b["rozela"]["error"] == "error"     # last good numbers + "not refreshed"
    assert b["celesta"]["state"] == "error"
    now[0] += D.CANCEL_ERR_TTL_S
    c.get("/api/dash/cancels"); drain(app)
    assert len(calls) == 5


def test_the_day_follows_the_boards_date_and_an_old_day_moves_the_window(app, pw_hash, transport):
    calls = []
    transport.reply = stats_reply(calls)
    clock(app, [NOW])
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    o = c.get("/api/dash/cancels?date=2026-10-15").get_json()
    assert o["day"] == "2026-10-15" and o["dates"][0] == TODAY                      # inside the last 14 days: same window
    o = c.get("/api/dash/cancels?date=2026-09-20").get_json()
    assert o["dates"][0] == "2026-09-20" and o["dates"][-1] == "2026-09-07"
    drain(app)
    assert ("rozela", "2026-09-07", "2026-09-20") in calls
    assert c.get("/api/dash/cancels?date=2026-13-01").status_code == 400
    assert c.get("/api/dash/cancels?date=2027-01-01").get_json()["day"] == TODAY    # a future day is today


# ---------- pure ----------

def test_churn_verdict_is_against_half_of_last_month():
    assert D.churn_verdict({"churn_pct": 8.0}, {"churn_pct": 17.5})["target"] == 8.75
    assert D.churn_verdict({"churn_pct": 8.0}, {"churn_pct": 17.5})["verdict"] == "good"
    assert D.churn_verdict({"churn_pct": 9.0}, {"churn_pct": 17.5})["verdict"] == "bad"
    assert D.churn_verdict({"churn_pct": 13.0}, {"churn_pct": None})["verdict"] is None and D.churn_verdict({"churn_pct": 13.0}, None)["level"] == "high"
    assert D.churn_verdict(None, None) == {"target": None, "verdict": None, "level": None, "projected": None, "days_elapsed": None, "days_in_month": None}


def test_a_running_month_is_judged_by_its_pace_not_by_the_rate_so_far():
    """Live 2026-10-23: rozela 10.4% by day 23 of October looked "healthy" and, in an early November, any rate so far is under a full-month
    target. At this pace it is 14.0% — the ~14% the owner quoted for October."""
    v = D.churn_verdict({"month": "2026-10", "churn_pct": 10.4, "partial": True}, {"churn_pct": 10.3}, "2026-10-23")
    assert (v["projected"], v["days_elapsed"], v["days_in_month"], v["level"]) == (14.02, 23, 31, "high")
    early = D.churn_verdict({"month": "2026-11", "churn_pct": 2.0, "partial": True}, {"churn_pct": 14.0}, "2026-11-05")
    assert early["target"] == 7.0 and early["projected"] == 12.0 and early["verdict"] == "bad"       # 2% so far is NOT under a 7% target
    done = D.churn_verdict({"month": "2026-10", "churn_pct": 14.0, "partial": False}, {"churn_pct": 10.0}, "2026-11-05")
    assert done["projected"] is None and done["verdict"] == "bad"                                    # a finished month is its own rate
    feb = D.churn_verdict({"month": "2028-02", "churn_pct": 1.0, "partial": True}, {"churn_pct": 9.0}, "2028-02-10")
    assert feb["days_in_month"] == 29 and feb["projected"] == 2.9


def test_cancel_norm_turns_every_non_count_into_unknown():
    n = D.cancel_norm({"kaching": "ok", "days": [{"date": TODAY, "subs_team": "3", "subs_bot": -1, "subs_team_by": {"a": 2, "b": True, "c": 0},
                                                  "orders_cancelled": 2, "subs_all_kaching": None}],
                       "month": {"month": "2026-10", "churn_pct": True, "active_start": 5}})
    r = n["days"][TODAY]
    assert (r["subs_team"], r["subs_bot"], r["team_total"], r["subs_all_kaching"], r["by"]) == (None, None, None, None, {"a": 2})
    assert n["month"]["churn_pct"] is None and n["month"]["active_start"] == 5 and n["prev_month"] is None
    n = D.cancel_norm({"kaching": "ok", "days": [{"date": TODAY, "subs_team": 7, "subs_team_by": {"agent-two": 3, "qa-x": 2, "claude-admin": 1}}]})
    assert n["days"][TODAY]["subs_team"] == 4 and n["days"][TODAY]["by"] == {"agent-two": 3} and n["days"][TODAY]["test_excluded"] == 3
