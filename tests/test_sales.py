"""Sales log (Owner, 2026-10-14): what the proxy lets through to engine/Sales.gs — roles, arguments, reply shapes, messages in both desks."""
import pytest

import engine_proxy
import messages
from conftest import call, logged_in

SALE_ADMIN = ("apiSaleList", "apiSaleDecide", "apiSaleSuggestions", "apiSaleSuggestCredit", "apiSaleSuggestDismiss", "apiSaleScan")
SALE_WORK = ("apiSaleCandidates", "apiSaleLog", "apiSaleMine", "apiSaleProof")


def last(transport, fn):
    return [b for _, b in transport.calls if b["fn"] == fn][-1]


def test_every_sale_fn_is_on_the_table_with_the_engine_roles():
    for fn in SALE_ADMIN:
        assert engine_proxy.FN_TABLE[fn][0] == engine_proxy.ADMIN_ONLY, fn
    for fn in SALE_WORK:
        assert engine_proxy.FN_TABLE[fn][0] == engine_proxy.WORK_ROLES, fn


def test_an_agent_is_refused_every_managers_fn_before_the_engine_is_called(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    for fn in SALE_ADMIN:
        r = call(c, tok, "rozela", fn, {"id": "o1", "decision": "approved"})
        assert r.status_code == 403, fn
        assert r.get_json()["error"] == "forbidden_role"
    assert transport.calls == []


def test_a_user_manager_cannot_log_or_see_sales(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    for fn in SALE_WORK + SALE_ADMIN:
        assert call(c, tok, "rozela", fn, {"id": "t1"}).status_code == 403, fn
    assert transport.calls == []


def test_the_agent_can_never_name_the_agent_or_the_amount(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiSaleLog", {"id": "t1", "orderNo": "#4601", "note": "ok", "agent": "amit", "amount": 1, "logged_by": "amit", "status": "verified"})
    assert r.status_code == 200
    sent = last(transport, "apiSaleLog")["args"]
    assert sent == {"id": "t1", "orderNo": "#4601", "note": "ok", "brand": "rozela"}


def test_the_manager_may_name_an_agent_only_for_crediting_a_suggestion(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    call(c, tok, "rozela", "apiSaleSuggestCredit", {"id": "o1", "agent": "agent-two", "amount": 5})
    assert last(transport, "apiSaleSuggestCredit")["args"] == {"id": "o1", "agent": "agent-two", "brand": "rozela"}


def test_malformed_sale_arguments_are_refused_at_the_proxy(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    assert call(c, tok, "rozela", "apiSaleDecide", {"id": "o1", "decision": "delete"}).status_code == 400
    assert call(c, tok, "rozela", "apiSaleLog", {"id": "t1", "orderNo": "1" * 40}).status_code == 400
    assert call(c, tok, "rozela", "apiSaleLog", {"id": "t1", "orderNo": "#1234", "note": "x" * 301}).status_code == 400
    assert call(c, tok, "rozela", "apiSaleLog", {"id": {"$ne": 1}, "orderNo": "#1234"}).status_code == 400
    assert transport.calls == []


def test_a_bare_ok_is_not_a_logged_sale(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = lambda url, body: {"ok": True}
    r = call(c, tok, "rozela", "apiSaleLog", {"id": "t1", "orderNo": "#4601"})
    assert r.get_json().get("ok") is not True


def test_refusals_are_worded_for_each_desk(app, pw_hash, transport):
    refusal = {"ok": False, "error": "order_already_credited", "by": "agent-two"}
    assert "כבר רשומה על" in messages.engine_error_msg(refusal, "apiSaleLog", "he")
    assert "already credited to" in messages.engine_error_msg(refusal, "apiSaleLog", "en")
    for code in ("bad_order", "order_not_found", "shopify_unavailable", "no_agent", "bad_decision"):
        for lang in ("he", "en"):
            msg = messages.engine_error_msg({"ok": False, "error": code}, "apiSaleLog", lang)
            assert msg and code not in msg, (code, lang)
    transport.reply = lambda url, body: dict(refusal, fn=body["fn"], rid=body.get("rid"))
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiSaleLog", {"id": "t1", "orderNo": "#4601"})
    assert r.get_json()["error"] == "order_already_credited" and "agent-two" in r.get_json()["msg"]
