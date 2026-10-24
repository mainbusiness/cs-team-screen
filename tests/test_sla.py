"""SLA tracking for the CS managers (Owner, 2026-10-24): business-hours clock, open-ticket breach states, completed first-reply / resolution
numbers, the manager-only endpoint, and that no customer text leaves the module."""
import json
from datetime import datetime

import sla
from conftest import logged_in, valid_reply

TZ = sla.TZ
CFG = sla.config({})


def ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp()


def iso(t):
    return datetime.fromtimestamp(t, sla.ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# 2026-10-22 is a Thursday, 10-23 Friday, 10-24 Saturday, 10-25 Sunday
def test_business_seconds_skip_the_weekend_and_the_friday_afternoon():
    assert sla.bh_seconds(ts(2026, 10, 22, 16), ts(2026, 10, 25, 10), CFG) == (1 + 4 + 1) * 3600      # Thu 16-17, Fri 09-13, Sun 09-10
    assert sla.bh_seconds(ts(2026, 10, 23, 14), ts(2026, 10, 24, 20), CFG) == 0                          # Friday after close + Saturday
    assert sla.bh_seconds(ts(2026, 10, 25, 8), ts(2026, 10, 25, 18), CFG) == 8 * 3600                    # a whole Sunday
    assert sla.bh_seconds(ts(2026, 10, 25, 12), ts(2026, 10, 25, 11), CFG) == 0                          # backwards = 0


def test_in_hours():
    assert sla.in_hours(ts(2026, 10, 25, 9), CFG) and not sla.in_hours(ts(2026, 10, 25, 17), CFG)
    assert not sla.in_hours(ts(2026, 10, 24, 12), CFG) and not sla.in_hours(ts(2026, 10, 23, 13, 30), CFG)


def test_weekday_keys_are_exact():
    c = sla.config({"SLA_CONFIG": json.dumps({"hours": {"10": [9, 17], "66": [9, 17], "": [9, 17], "3": [9, 17]}})})
    assert c["hours"] == {"3": [9, 17]}


def test_env_override_is_validated():
    c = sla.config({"SLA_CONFIG": json.dumps({"first_reply_bh_h": 2, "resolution_h": "x", "hours": {"6": [8, 18], "9": [1, 2], "0": [5, 4]}})})
    assert c["first_reply_bh_h"] == 2.0 and c["resolution_h"] == 36.0 and c["hours"] == {"6": [8, 18]} and c["hours_source"] == "SLA_CONFIG"
    assert sla.config({"SLA_CONFIG": "{not json"}) == sla.config({})


def row(i, status="action", wait=None, handled=None, by="", ch="email", created=None):
    return {"id": i, "status": status, "channel": ch, "waiting_since": iso(wait) if wait else None, "created_at": iso(created or wait or 0),
            "handled_at": iso(handled) if handled else None, "handled_by": by, "name": "SECRET NAME", "email": "x@y.z", "summary": "SECRET TEXT"}


def test_open_ticket_states_use_business_hours_and_the_75_percent_warning():
    now = ts(2026, 10, 25, 14)                                            # Sunday 14:00
    ok = sla.judge_open(row("a", wait=ts(2026, 10, 25, 12)), now, CFG)       # 2 bh
    risk = sla.judge_open(row("b", wait=ts(2026, 10, 25, 10, 55)), now, CFG)  # 3h05 = 77%
    breach = sla.judge_open(row("c", wait=ts(2026, 10, 25, 9)), now, CFG)    # 5 bh
    weekend = sla.judge_open(row("d", wait=ts(2026, 10, 23, 13)), now, CFG)  # Fri 13:00 -> Sun 09:00 = 0 bh, 49 wall h
    assert (ok["state"], risk["state"], breach["state"]) == ("ok", "risk", "breach") and breach["why"] == ["reply"]
    assert weekend["state"] == "breach" and weekend["why"] == ["reply", "resolution"] and weekend["wait_bh_s"] == 5 * 3600     # Sun 09-14 = 5 bh, 49 wall h
    fri = sla.judge_open(row("f", wait=ts(2026, 10, 23, 12)), ts(2026, 10, 25, 9), CFG)                     # Fri 12-13 = 1 bh, 45 wall h
    assert fri["state"] == "breach" and fri["why"] == ["resolution"]


def test_first_vs_followup_kind():
    now = ts(2026, 10, 25, 14)
    assert sla.judge_open(row("a", wait=ts(2026, 10, 25, 12)), now, CFG)["kind"] == "first"
    assert sla.judge_open(row("a", wait=ts(2026, 10, 25, 12), handled=ts(2026, 10, 25, 9), by="agent-two"), now, CFG)["kind"] == "followup"
    assert sla.judge_open(row("a", wait=ts(2026, 10, 25, 12), handled=ts(2026, 10, 25, 9), by="auto-reply"), now, CFG)["kind"] == "first"


def test_completed_numbers_and_agents():
    now = ts(2026, 10, 25, 15)
    rows = [row("s1", "sent", wait=ts(2026, 10, 25, 9), handled=ts(2026, 10, 25, 10), by="agent-two"),      # 1 bh, in target
            row("s2", "sent", wait=ts(2026, 10, 25, 9), handled=ts(2026, 10, 25, 14), by="agent-two"),      # 5 bh, late
            row("s3", "sent", wait=ts(2026, 10, 25, 9), handled=ts(2026, 10, 25, 9, 10), by="auto-reply"),   # automation: not counted
            row("d1", "done", wait=ts(2026, 10, 24, 9), handled=ts(2026, 10, 25, 9), by="noa"),        # 24 h, in target
            row("d2", "done", wait=ts(2026, 10, 20, 9), handled=ts(2026, 10, 25, 9), by="noa")]        # 120 h, late
    c = sla.completed(rows, ts(2026, 10, 25), now, CFG)
    assert (c["first_reply"]["n"], c["first_reply"]["within"]) == (2, 1) and c["first_reply"]["within_pct"] == 50.0
    assert (c["resolution"]["n"], c["resolution"]["within"]) == (2, 1)
    assert c["agents"]["agent-two"]["first_reply"]["n"] == 2 and c["agents"]["noa"]["resolution"]["n"] == 2 and "auto-reply" not in c["agents"]


def test_build_counts_per_brand_orders_alerts_and_carries_no_customer_text():
    now = ts(2026, 10, 25, 14)
    rows = {"rozela": [row("r1", wait=ts(2026, 10, 25, 9)), row("r2", wait=ts(2026, 10, 25, 12)), row("r3", "bot", wait=ts(2026, 10, 20, 9)), row("r4", "sent")],
            "celesta": [row("c1", wait=ts(2026, 10, 25, 10, 55), ch="whatsapp")], "apexmen": []}
    out = sla.build(rows, now, CFG)
    assert out["in_hours"] and out["banner"] == "breach"
    assert out["total"]["open"] == 3 and out["total"]["breach"] == 1 and out["total"]["risk"] == 1 and out["total"]["ok"] == 1     # bot / sent are not waiting for a person
    assert [a["id"] for a in out["alerts"]] == ["r1", "c1"] and out["alerts"][0]["brand"] == "rozela"
    assert out["total"]["oldest"]["id"] == "r1" and out["brands"]["apexmen"]["counts"]["open"] == 0
    blob = json.dumps(out)
    for secret in ("SECRET NAME", "SECRET TEXT", "x@y.z"):
        assert secret not in blob
    assert sla.build(rows, ts(2026, 10, 24, 12), CFG)["banner"] is None            # Saturday: the data stays, the alarm does not ring


def test_day_summary_for_the_snapshot():
    rows = [row("s1", "sent", wait=ts(2026, 10, 22, 9), handled=ts(2026, 10, 22, 10), by="agent-two")]
    s = sla.day_summary(rows, "2026-10-22", ts(2026, 10, 23, 1), CFG)
    assert s["day"] == "2026-10-22" and s["first_reply"]["n"] == 1 and s["first_reply"]["within_pct"] == 100.0


def test_endpoint_is_for_managers_only(app, pw_hash, transport):
    now = ts(2026, 10, 25, 14)
    rows = [row("w1", "ready", wait=now - 7200, ch="whatsapp"), row("e1", "action", wait=now - 3600 * 30)]
    transport.reply = lambda url, body: ({"ok": True, "tickets": rows, "counts": {"ready": 1, "action": 1}, "version": 3} if body["fn"] == "apiBoot" else valid_reply(url, body))
    a, _ = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert a.get("/api/dash/sla").status_code == 403
    m, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    j = m.get("/api/dash/sla").get_json()
    assert j["ok"] and j["config"]["first_reply_bh_h"] == 4.0 and j["known_brands"] == ["rozela"] and j["total"]["open"] == 2
    assert "SECRET" not in json.dumps(j)
    assert "no-store" in m.get("/api/dash/sla").headers["Cache-Control"]
