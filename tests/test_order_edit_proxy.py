"""Order edits in Shopify (Owner, 2026-10-16): the proxy's shapes, the Hebrew/English lines for every gate sentence, and the drift guard against engine/OrderEdit.gs."""
import os
import re

import pytest

import messages
from conftest import call, logged_in

OID = "gid://shopify/Order/5550001"
BASE = {"id": "t1", "orderId": OID, "kind": "address", "mode": "preview", "address": '{"city":"חיפה"}'}


def test_order_edit_shapes_and_stripping(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    for bad in (dict(BASE, kind="cancel"), dict(BASE, mode="commit"), dict(BASE, orderId="gid://shopify/Order/1; drop"), dict(BASE, orderId="5550001"),
                dict(BASE, address="x" * 1501), dict(BASE, ops="x" * 2501), dict(BASE, reason="r" * 501), dict(BASE, expectDelta="1" * 13), dict(BASE, confirm="1" * 13),
                dict(BASE, address={"city": "x"})):
        assert call(c, tok, "rozela", "apiOrderEdit", bad).status_code == 400, bad
    assert call(c, tok, "rozela", "apiOrderEditState", {"id": "t1", "orderId": "nope"}).status_code == 400
    transport.reply = {"ok": True, "kind": "address", "mode": "preview", "changed": ["city"], "orderId": OID, "needsAdmin": False}
    j = call(c, tok, "rozela", "apiOrderEdit", dict(BASE, email="victim@x.com", role="admin", ticket={"email": "v@x.com"})).get_json()
    assert j["ok"] and j["changed"] == ["city"]
    sent = [b for _, b in transport.calls if b["fn"] == "apiOrderEdit"][-1]["args"]
    assert "email" not in sent and "role" not in sent and "ticket" not in sent
    assert sent["orderId"] == OID and sent["mode"] == "preview" and sent["kind"] == "address"


def test_order_edit_roles(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert call(c, tok, "rozela", "apiOrderEdit", BASE).status_code == 403
    assert call(c, tok, "rozela", "apiOrderEditState", {"id": "t1", "orderId": OID}).status_code == 403


def test_order_edit_refusal_is_localized_and_keeps_the_raw_sentence(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": False, "kind": "address", "message": "order edits are switched off"}
    j = call(c, tok, "rozela", "apiOrderEdit", BASE).get_json()
    assert j["ok"] is False and j["message"] == "order edits are switched off"
    assert "כבויה" in j["msg"]


def test_order_state_gets_localized_reasons(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": True, "id": "t1", "status": "on", "order": {"id": OID, "name": "#1", "lines": [], "can": {"address": "the order is cancelled", "items": ""}}}
    j = call(c, tok, "rozela", "apiOrderEditState", {"id": "t1", "orderId": OID}).get_json()
    assert j["ok"] and "בוטלה" in j["order"]["canMsg"]["address"] and "items" not in j["order"]["canMsg"]


GATE_SENTENCES = [
    "order edits are switched off", "order edits have no write credential", "order edits are frozen: 2026-10-16T09:00:00.000Z — daily limit of 150 order edits reached",
    'role "user-manager" may not edit orders', "exactly one valid order id is required", "ticket has no customer email or phone", "another order edit is running, try again",
    "limit: 30 order edits per hour per user", "the order was not found (orders older than 60 days are not visible)", "this order does not belong to the ticket's customer",
    "the order is cancelled", "the order is not unfulfilled (FULFILLED)", "payment status REFUNDED does not allow item changes", "confirmation code does not match the order",
    "an increase of 50.00 needs an admin", "the price changed since the preview — review it again", "Shopify refused the change: cannot commit. Not retried.",
    "request accepted but the change is not visible yet — check in Shopify, do not repeat", "request sent but the outcome is unknown — check in Shopify, do not retry", "done",
]


@pytest.mark.parametrize("raw", GATE_SENTENCES)
@pytest.mark.parametrize("lang", ["he", "en"])
def test_every_order_edit_sentence_has_a_line(raw, lang):
    out = messages.order_edit_msg(raw, lang)
    assert not out.startswith(("עריכת ההזמנה לא הושלמה", "The order edit did not complete")), raw
    if lang == "he":
        assert re.search(r"[֐-׿]", out)


def test_order_edit_messages_match_the_engine_source():
    """Drift guard: every refuse('...') / { error: '...' } literal in OrderEdit.gs is covered by a pattern in messages.ORDER_EDIT."""
    src = os.path.join(os.path.dirname(__file__), "..", "..", "engine", "OrderEdit.gs")
    if not os.path.exists(src):
        pytest.skip("engine source not next to this folder (deployed copy)")
    text = open(src, encoding="utf-8").read()
    lits = []
    for m in re.finditer(r"(?:refuse\(|\{ error: )(.*?)(?:\);| \})", text):
        parts = re.findall(r"'((?:[^'\\]|\\.)*)'|([^+']+)", m.group(1))
        out = "".join(a.replace("\\'", "'") if a else ("" if not c.strip() else "X") for a, c in parts)
        if out and out != "X":
            lits.append(out)
    assert len(lits) >= 25, lits
    for lit in lits:
        lit = lit[1:] if lit.startswith('XShopify') else lit     # a ternary in the source (direct ? raw : 'Shopify refused...')
        # staging errors reach the screen behind "Shopify refused the change: " (OrderEdit.gs prefixes them), so either form must translate
        outs = [messages.order_edit_msg(lit, "he")] + ([messages.order_edit_msg("Shopify refused the change: " + lit, "he")] if lit.startswith("Shopify ") else [])
        assert any(not o.startswith("עריכת ההזמנה לא הושלמה") for o in outs), lit
