"""A closed ticket or an earlier reply must never confirm the current customer send."""
import pytest

import engine_proxy
from conftest import call, logged_in, valid_reply
from test_lost_reply import echo

TEXT = "שלום, ההזמנה בדרך."


@pytest.mark.parametrize("reply", [{"ok": True}, {"ok": True, "id": "t1"},
                                    {"ok": True, "sent": True, "queued": True}])
def test_send_receipt_requires_one_actual_outcome(reply):
    assert engine_proxy.reply_problem("apiSend", {"id": "t1"}, "receipt-rid", reply) is not None


@pytest.mark.parametrize("reply", [{"ok": True, "sent": True}, {"ok": True, "queued": True}])
def test_real_send_and_queue_receipts_are_distinct_and_valid(reply):
    assert engine_proxy.reply_problem("apiSend", {"id": "t1"}, "receipt-rid", reply) is None


@pytest.mark.parametrize("ticket,want", [
    ({"channel": "email", "status": "done", "draft_text": TEXT}, None),
    ({"channel": "email", "status": "sent", "draft_text": "תשובה קודמת"}, None),
    ({"channel": "email", "status": "sent", "draft_text": TEXT}, "sent"),
    ({"channel": "whatsapp", "status": "done", "wa_out": TEXT}, None),
    ({"channel": "whatsapp", "status": "sent", "wa_out": TEXT, "wa_send": "unknown:bridge:42"}, None),
    ({"channel": "whatsapp", "status": "sent", "wa_out": "תשובה קודמת", "wa_send": "sent:bridge"}, None),
    ({"channel": "whatsapp", "status": "sent", "wa_out": TEXT, "wa_send": "sent:bridge"}, "sent"),
    ({"channel": "whatsapp", "status": "done", "wa_out": TEXT, "wa_send": "sent:bridge"}, "sent"),
    ({"channel": "whatsapp", "status": "wa_queued", "wa_out": TEXT, "wa_send": "pending"}, "queued"),
    ({"channel": "whatsapp", "status": "wa_queued", "wa_out": TEXT, "wa_send": "claimed:bridge:42"}, "queued"),
    ({"channel": "whatsapp", "status": "wa_queued", "wa_out": "תשובה קודמת", "wa_send": "pending"}, None),
])
def test_recovery_requires_exact_text_and_channel_receipt(monkeypatch, ticket, want):
    ticket = dict(ticket, id="t1", handled_by="lyra")
    monkeypatch.setattr(engine_proxy, "call", lambda *a, **k: (200, {"ok": True, "ticket": ticket}))
    result = engine_proxy._effect_visible({}, None, "", {"username": "lyra"}, "rozela", "apiSend",
                                          {"id": "t1", "text": TEXT}, "en")
    if want is None:
        assert result is None
    else:
        assert result[want] is True
        assert result.get("queued" if want == "sent" else "sent") is None


@pytest.mark.parametrize("status,saved", [("done", TEXT), ("sent", "תשובה קודמת")])
def test_repeat_click_cannot_turn_unsent_text_into_success(app, pw_hash, transport, status, saved):
    def reply(url, body):
        if body["fn"] == "apiSend":
            return echo(body, {"ok": False, "error": "already_handled"})
        if body["fn"] == "apiTicket":
            return echo(body, {"ok": True, "ticket": {"id": "t1", "status": status, "draft_text": saved,
                                                       "handled_by": "lyra", "channel": "email"}})
        return echo(body, valid_reply(url, body))
    transport.reply = reply
    client, csrf = logged_in(app, pw_hash, "lyra", ["agent"], ["rozela"], lang="en")
    result = call(client, csrf, "rozela", "apiSend", {"id": "t1", "text": TEXT}).get_json()
    assert result["ok"] is False and result["error"] == "already_handled"
    assert not result.get("sent")
    assert len([body for _, body in transport.calls if body["fn"] == "apiSend"]) == 1
