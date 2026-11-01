"""Why customers cancel a subscription on the managers' board (Owner, 2026-11-01). Engine fn apiCancelReasons (admin read) -> proxy (admin only, reply
schema) -> /api/dash/cancel-reasons (admins only, cached, read in the background) -> the view: per brand and all brands, per week."""
import pytest

import dashboard as D
import engine_proxy
from conftest import call, logged_in, valid_reply

KEYS = D.REASONS_KEYS


def reasons_reply(calls, absent=(), weeks=None):
    weeks = weeks or {"2026-10-23": [10, 2, 3, 1, 4, 1, 2], "2026-10-16": [8, 1, 1, 0, 6, 0, 3]}

    def reply(url, body):
        fn, a = body["fn"], body.get("args") or {}
        if fn != "apiCancelReasons":
            return valid_reply(url, body)
        b = a["brand"]
        calls.append(b)
        if b in absent:
            return {"ok": False, "error": "unauthorized"}
        if b == "selera":
            return {"ok": True, "brand": b, "state": "no_subscriptions", "weeks": [], "taxonomy": [{"key": k, "he": k} for k in KEYS]}
        ws = []
        for wk in sorted(weeks, reverse=True):
            c = dict(zip(KEYS, weeks[wk]))
            ws.append({"week": wk, "to": "x", "read": sum(c.values()) + 3, "sub_cancels": sum(c.values()), "counts": c,
                       "quotes": {"never_agreed": [b + " q1", b + " q2", b + " q3", b + " q4"]}, "run": {"at": wk + "T23:00:00Z", "trigger": "clock", "failed": 0}})
        return {"ok": True, "brand": b, "state": "ok", "version": "v1", "model": "claude-haiku-5-5", "weeks": ws,
                "taxonomy": [{"key": k, "he": "שם " + k, "en": k, "def": "הגדרה"} for k in KEYS] + [{"key": "evil", "he": "x"}],
                "all": {"from": "2026-10-16", "to": "2026-10-29", "read": 99, "sub_cancels": 40, "counts": {k: 2 for k in KEYS}, "quotes": {}},
                "next_run": {"date": "2026-11-06", "local": "2026-11-06 02:00 Asia/Jerusalem"}, "pending": 0}
    return reply


def drain(app):
    app.extensions["cs"]["reasons_drain"]()


def test_admin_only_read_with_no_browser_arguments():
    roles, keys = engine_proxy.FN_TABLE["apiCancelReasons"]
    assert roles == ("admin",) and keys == ()
    assert "apiCancelReasons" in engine_proxy.READ_FNS


@pytest.mark.parametrize("roles", [["agent"], ["user-manager"]])
def test_an_agent_or_user_manager_is_refused_before_the_engine(app, pw_hash, transport, roles):
    calls = []
    transport.reply = reasons_reply(calls)
    c, tok = logged_in(app, pw_hash, "agent-x", roles, ["rozela"])
    assert c.get("/api/dash/cancel-reasons").status_code == 403
    assert call(c, tok, "rozela", "apiCancelReasons", {}).status_code == 403
    assert calls == []


@pytest.mark.parametrize("bad", [{"ok": True}, {"ok": True, "state": "ok", "weeks": [{"week": "last"}], "taxonomy": []},
                                 {"ok": True, "state": "ok", "brand": "celesta", "weeks": [], "taxonomy": []}])
def test_a_reply_that_is_not_this_brands_shape_is_never_drawn(app, pw_hash, transport, bad):
    transport.reply = lambda url, body: dict(bad, fn=body["fn"], rid=body["rid"]) if body["fn"] == "apiCancelReasons" else valid_reply(url, body)
    c, tok = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    assert call(c, tok, "rozela", "apiCancelReasons", {}).get_json()["ok"] is False


def test_the_board_reads_in_the_background_sums_the_brands_and_caches(app, pw_hash, transport):
    calls = []
    transport.reply = reasons_reply(calls, absent=("velora",))
    now = [1_800_000_000.0]
    app.extensions["cs"]["activity"]["log"].clock = lambda: now[0]
    c, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela", "celesta", "velora"])
    first = c.get("/api/dash/cancel-reasons").get_json()
    assert first["ok"] and first["busy"] and first["total"]["weeks"] == []                     # nothing yet: "reading", not zeros
    assert first["pending"] == ["celesta", "rozela", "velora"]                                 # every brand still being read is named
    drain(app)
    o = c.get("/api/dash/cancel-reasons").get_json()
    assert not o["busy"] and o["hidden"] == [] and o["unavailable"] == ["velora"] and o["pending"] == []
    w = o["total"]["weeks"][0]
    assert w["week"] == "2026-10-23" and w["sub_cancels"] == 46 and w["read"] == 52 and w["counts"]["never_agreed"] == 20 and w["counts"]["not_stated"] == 4
    assert w["quotes"]["never_agreed"] == ["celesta q1", "rozela q1", "celesta q2"] or w["quotes"]["never_agreed"] == ["rozela q1", "celesta q1", "rozela q2"]
    assert sorted(w["runs"]) == ["celesta", "rozela"] and w["missing"] == []
    assert o["total"]["weeks"][1]["counts"]["one_time"] == 12
    assert o["total"]["all"]["sub_cancels"] == 80 and o["total"]["all"]["from"] == "2026-10-16"
    assert [t["key"] for t in o["taxonomy"]] == list(KEYS)                                     # an unknown key from the engine is dropped
    assert o["next_run"]["date"] == "2026-11-06" and o["model"] == "claude-haiku-5-5"
    assert o["brands"]["rozela"]["weeks"][0]["quotes"]["never_agreed"] == ["rozela q1", "rozela q2", "rozela q3"]   # at most 3
    good = lambda: sum(1 for b in calls if b != "velora")
    n = good()
    now[0] += D.REASONS_TTL_S - 5
    c.get("/api/dash/cancel-reasons"); drain(app)
    assert good() == n                                                                         # cached
    assert calls.count("velora") == 2                                                          # a failed brand is tried again after a minute, not on every refresh
    now[0] += 10
    c.get("/api/dash/cancel-reasons"); drain(app)
    assert good() == n + 2


def test_reasons_norm_drops_every_non_count():
    o = D.reasons_norm({"state": "ok", "taxonomy": [], "weeks": [{"week": "2026-10-23", "read": "7", "sub_cancels": -1,
                                                                     "counts": {"never_agreed": True, "one_time": 3, "x": 9}, "quotes": {"one_time": ["a", 5, ""]}}]})
    w = o["weeks"][0]
    assert w["read"] is None and w["sub_cancels"] is None and w["counts"]["never_agreed"] == 0 and w["counts"]["one_time"] == 3 and "x" not in w["counts"]
    assert w["quotes"] == {"one_time": ["a"]}


def test_the_same_quote_from_two_brands_is_shown_once():
    def brand(q):
        return {"state": "ok", "data": D.reasons_norm({"state": "ok", "taxonomy": [], "weeks": [{"week": "2026-10-23", "counts": {"one_time": 2}, "sub_cancels": 2, "read": 2,
                                                                                               "quotes": {"one_time": q}}]})}
    v = D.reasons_view({"rozela": brand(["אזמין לבד", "לא צריך"]), "celesta": brand(["אזמין לבד", "יש לי בבית"])})
    q = v["total"]["weeks"][0]["quotes"]["one_time"]
    assert len(q) == 3 and sorted(q) == sorted(["אזמין לבד", "לא צריך", "יש לי בבית"])


def test_a_week_some_brand_has_no_data_for_names_it():
    def brand(weeks):
        return {"state": "ok", "data": D.reasons_norm({"state": "ok", "taxonomy": [], "weeks": [{"week": wk, "counts": {"one_time": 1}, "sub_cancels": 1, "read": 1} for wk in weeks]})}
    v = D.reasons_view({"rozela": brand(["2026-10-23", "2026-10-16"]), "celesta": brand(["2026-10-23"])})
    assert v["total"]["weeks"][1]["week"] == "2026-10-16" and v["total"]["weeks"][1]["missing"] == ["celesta"]
