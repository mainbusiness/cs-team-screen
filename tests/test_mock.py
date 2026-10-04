"""Mock preview: the real proxy path (token minted, verified by the mock's port) end to end."""
from conftest import call, client_for, logged_in


def mock_app(make_app):
    return make_app(MOCK_ENGINE=True, ENGINES_JSON="", COOKIE_SECURE=False, TRANSPORT=None)


def test_mock_boot_ticket_and_cancel_gate(make_app, pw_hash):
    app = mock_app(make_app)
    app.extensions["cs"]["engines"]   # mock wires its own brands
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela", "celesta"])
    b = call(c, tok, "rozela", "apiBoot").get_json()
    assert b["ok"] and b["counts"]["ready"] >= 2 and b["dryRun"] is False
    t = call(c, tok, "rozela", "apiTicketExtras", {"id": "t18f2a03"}).get_json()
    sub = t["extras"]["subscriptions"][0]["id"]
    bad = call(c, tok, "rozela", "apiKachingCancel", {"id": "t18f2a03", "contractId": sub, "confirm": "0000"}).get_json()
    assert bad["ok"] is False and bad["message"] == "confirmation code does not match the contract"
    assert bad["msg"].startswith("4 הספרות")
    ok = call(c, tok, "rozela", "apiKachingCancel", {"id": "t18f2a03", "contractId": sub, "confirm": sub[-4:]}).get_json()
    assert ok["ok"] and ok["status"] == "CANCELLED"
    off = call(c, tok, "celesta", "apiKachingCancel", {"id": "tcele02", "contractId": "gid://shopify/SubscriptionContract/5550001112223", "confirm": "2223"}).get_json()
    assert off["msg"].startswith("ביטולי מנויים כבויים")
    assert call(c, tok, "celesta", "apiSend", {"id": "tcele01", "text": "היי"}).get_json()["error"] == "dry_run"


def test_mock_auto_cancel_and_settings_shapes(make_app, pw_hash):
    app = mock_app(make_app)
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela"])
    lst = call(c, tok, "rozela", "apiAutoCancelList").get_json()
    assert lst["switch"] in ("off", "shadow", "on") and lst["mode"] in ("off", "shadow", "live")
    states = {i["state"] for i in lst["items"]}
    assert {"shadow_would_cancel", "queued", "cancelled_reply_failed", "aborted_human"} <= states
    r = call(c, tok, "rozela", "apiAutoCancelApprove", {"id": "t18f2b11"}).get_json()
    assert r["error"] == "not_approvable" and "queued" in r["msg"]
    r = call(c, tok, "rozela", "apiAutoCancelApprove", {"id": "t18f2a03", "replyText": "היי, ביטלתי."}).get_json()
    assert r["ok"] and r["state"] == "queued" and r["approvedBy"] == "manager"
    s = call(c, tok, "rozela", "apiSettings", {"action": "get"}).get_json()
    assert set(s["settings"]) == {"DRY_RUN", "KACHING_WRITES", "AUTO_CANCEL"}
    call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "on"})
    refused = call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "AUTO_CANCEL", "value": "on"}).get_json()
    assert refused["error"] == "needs_live_switches" and "AUTO_CANCEL=on needs" in refused["reason"] and "מתגים" in refused["msg"]
    ok = call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "off"}).get_json()
    assert ok == {**ok, "ok": True, "key": "DRY_RUN", "from": "on", "to": "off"}


def test_mock_rejects_forged_tokens(make_app):
    import mock_engine
    eng = mock_engine.MockEngines("k" * 40, latency_ms=0)
    assert eng.dispatch("rozela", {"fn": "apiBoot", "token": "abc.def", "args": {}}) == {"ok": False, "error": "unauthorized"}
