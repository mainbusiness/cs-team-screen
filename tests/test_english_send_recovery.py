"""Translation is recoverable without retrying customer delivery or weakening Hebrew validation."""
import json

from assistant import hebrew_delivery_ok
from conftest import call
from test_assistant import text
from test_english_safety import setup


def translation(value):
    return text(json.dumps({"translations": [{"i": 0, "text": value}]}))


def test_legitimate_hyphenated_order_reference_is_not_english_prose():
    assert hebrew_delivery_ok("שלום, ההזמנה AB-1234 בדרך.", "rozela")
    assert not hebrew_delivery_ok("שלום. Your order is on its way.", "rozela")
    assert not hebrew_delivery_ok("שלום Hello1 customer2", "rozela")


def test_english_preview_repairs_translation_then_sends_exact_hebrew_once(setup):
    app, c, tok, transport, model = setup
    source = "Please send a screenshot of the PayPal payment for order AB-1234."
    approved = "נא לשלוח צילום מסך של התשלום בפייפאל עבור הזמנה AB-1234."
    model.script = [translation("נא לשלוח צילום של PayPal עבור הזמנה AB-1234."), translation(approved)]
    r = c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": source},
               headers={"X-CSRF-Token": tok})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["text"] == approved
    assert len(model.payloads) == 2
    assert not [b for _, b in transport.calls if b["fn"] == "apiSend"]
    assert call(c, tok, "rozela", "apiSend", {"id": "t1", "text": r.get_json()["text"]}).get_json()["ok"]
    sends = [b for _, b in transport.calls if b["fn"] == "apiSend"]
    assert len(sends) == 1 and sends[0]["args"]["text"] == approved
    assert len(model.payloads) == 2  # the verified preview is not translated again on send


def test_repair_cannot_change_order_reference_or_reach_sender(setup):
    app, c, tok, transport, model = setup
    model.script = [translation("שלום, ההזמנה AB-9999 בדרך.")] * 2
    response = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "Hello, order AB-1234 is on its way."})
    assert response.status_code == 502
    assert len(model.payloads) == 2
    assert not [b for _, b in transport.calls if b["fn"] == "apiSend"]


def test_failed_repair_is_bounded_and_never_sends_english(setup):
    app, c, tok, transport, model = setup
    model.script = [translation("שלום, Your order is on its way.")] * 3
    response = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "Your order is on its way."})
    assert response.status_code == 502
    assert len(model.payloads) == 2
    assert not [b for _, b in transport.calls if b["fn"] == "apiSend"]
