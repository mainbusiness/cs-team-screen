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
    assert set(s["settings"]) == {"DRY_RUN", "KACHING_WRITES", "AUTO_CANCEL", "AUTO_REPLY"}
    call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "on"})
    refused = call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "AUTO_CANCEL", "value": "on"}).get_json()
    assert refused["error"] == "needs_live_switches" and "AUTO_CANCEL=on needs" in refused["reason"] and "מתגים" in refused["msg"]
    ok = call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "off"}).get_json()
    assert ok == {**ok, "ok": True, "key": "DRY_RUN", "from": "on", "to": "off"}


def test_mock_rejects_forged_tokens(make_app):
    import mock_engine
    eng = mock_engine.MockEngines("k" * 40, latency_ms=0)
    assert eng.dispatch("rozela", {"fn": "apiBoot", "token": "abc.def", "args": {}}) == {"ok": False, "error": "unauthorized"}


def test_mock_manage_subscription_every_action(make_app, pw_hash):
    """The Kaching actions through the real proxy path (Owner, 2026-10-14): pause, resume, skip, unskip, reschedule, discount, products."""
    from datetime import datetime, timedelta, timezone
    app = mock_app(make_app)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    t = call(c, tok, "rozela", "apiTicketExtras", {"id": "t18f2a03"}).get_json()
    sub = t["extras"]["subscriptions"][0]["id"]
    d = call(c, tok, "rozela", "apiKachingContract", {"id": "t18f2a03", "contractId": sub}).get_json()
    assert d["ok"] and d["contract"]["status"] == "ACTIVE" and len(d["contract"]["cycles"]) == 4
    line = d["contract"]["lines"][0]["id"]
    act = lambda action, **kw: call(c, tok, "rozela", "apiKachingAction", dict({"id": "t18f2a03", "contractId": sub, "action": action, "confirm": sub[-4:]}, **kw)).get_json()
    bad = call(c, tok, "rozela", "apiKachingAction", {"id": "t18f2a03", "contractId": sub, "action": "pause", "confirm": "0000"}).get_json()
    assert bad["ok"] is False and bad["msg"].startswith("4 הספרות")
    assert act("pause")["contract"]["status"] == "PAUSED"
    assert "אי אפשר" in act("pause")["msg"]
    assert act("resume")["status"] == "ACTIVE"
    assert act("skip", cycleIndex="1")["contract"]["cycles"][0]["skipped"] is True
    assert act("unskip", cycleIndex="1")["contract"]["cycles"][0]["skipped"] is False
    nd = (datetime.now(timezone.utc) + timedelta(days=40)).strftime("%Y-%m-%d")
    assert act("reschedule", cycleIndex="2", billingDate=nd)["contract"]["cycles"][1]["date"].startswith(nd)
    r = act("add_discount", discountType="PERCENTAGE", value="20", title="שימור", recurringCycleLimit="2")
    assert r["ok"] and r["contract"]["discounts"][0]["title"] == "שימור"
    v = call(c, tok, "rozela", "apiKachingVariants").get_json()["variants"]
    assert act("update_line", lineId=line, quantity="3")["contract"]["lines"][0]["quantity"] == 3
    r = act("add_line", variantId=v[1]["id"], quantity="1")
    assert len(r["contract"]["lines"]) == 2
    assert len(act("remove_line", lineId=line)["contract"]["lines"]) == 1
    assert "המוצר האחרון" in act("remove_line", lineId=r["contract"]["lines"][1]["id"])["msg"]
