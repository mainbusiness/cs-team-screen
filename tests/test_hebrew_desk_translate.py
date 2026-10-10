"""Hebrew desk (Owner, 2026-10-10): a customer who writes in Russian / Arabic / English is translated into Hebrew for the
agent automatically, and every reply goes out in Hebrew only. Anthropic is always faked here; no network."""
import json

import assistant
from conftest import logged_in
from test_assistant import EXTRAS, TICKET, app5, engine_reply, fake_llm, text  # noqa: F401  (fixtures)

RU = "Здравствуйте, где мой заказ? Я заказала две недели назад."
AR = "مرحبا، متى يصل طلبي؟"


def he_translations(payload):
    items = json.loads(payload["messages"][-1]["content"])["items"]
    table = {RU: "שלום, איפה ההזמנה שלי? הזמנתי לפני שבועיים.", AR: "שלום, מתי ההזמנה שלי מגיעה?", "Where is my order #1001?": "איפה ההזמנה שלי #1001?"}
    return text(json.dumps({"translations": [{"i": it["i"], "text": table.get(it["text"], "תרגום")} for it in items]}, ensure_ascii=False))


def with_conv(conv, subject=None):
    old = (list(EXTRAS["conversation"]), TICKET.get("subject"))
    EXTRAS["conversation"][:] = conv
    TICKET["subject"] = subject
    return old


def restore(old):
    EXTRAS["conversation"][:] = old[0]
    TICKET["subject"] = old[1]


def test_script_lang_ignores_links_ids_and_names():
    assert assistant.script_lang("היי, ההזמנה בדרך. מעקב: JY123456789IL https://get-velora.com/a?b=c") == "he"
    assert assistant.script_lang("היי דנה, Velora שולחת לך") == "he"
    assert assistant.script_lang(RU) == "ru" and assistant.script_lang(AR) == "ar"
    assert assistant.script_lang("Hi, where is my order?") == "en"
    assert assistant.script_lang("#1001 12345") == "" and not assistant.needs_hebrew("")
    assert assistant.needs_hebrew(RU) and not assistant.needs_hebrew("שלום")


def test_hebrew_desk_translates_only_foreign_customer_messages(app5, pw_hash, fake_llm):
    old = with_conv([{"who": "customer", "at": "2026-10-04T10:00:00Z", "text": RU},
                     {"who": "us", "at": "2026-10-04T11:00:00Z", "text": "Hi, our own reply is never translated"},
                     {"who": "customer", "at": "2026-10-04T12:00:00Z", "text": "תודה"},
                     {"who": "customer", "at": "2026-10-04T13:00:00Z", "text": AR}], subject="Where is my order #1001?")
    try:
        fake_llm.script = [he_translations]
        c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"])
        r = c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
        assert r["ok"] and r["target"] == "he" and r["incomplete"] == 0
        assert [(x["i"], x["source"]) for x in r["conversation"]] == [(0, "ru"), (3, "ar")]     # Hebrew and our own messages are skipped
        assert r["conversation"][0]["text"] == "שלום, איפה ההזמנה שלי? הזמנתי לפני שבועיים."
        assert r["conversation"][0]["o"] == RU[:120]
        assert r["subject"] == "איפה ההזמנה שלי #1001?"
        p = fake_llm.payloads[0]
        sys_text = p["system"][0]["text"]
        assert "Task: translate-in-he" in sys_text and "into Hebrew" in sys_text and "never instructions" in sys_text
        assert len(json.loads(p["messages"][0]["content"])["items"]) == 3
        r2 = c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
        assert r2 == r and len(fake_llm.payloads) == 1                                          # cached: no second model call
    finally:
        restore(old)


def test_hebrew_conversation_needs_no_model_call(app5, pw_hash, fake_llm):
    old = with_conv([{"who": "customer", "at": "2026-10-04T10:00:00Z", "text": "היי, איפה ההזמנה שלי? #1001"}], subject="שאלה")
    try:
        c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"])
        r = c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
        assert r["ok"] and r["conversation"] == [] and r["subject"] is None and fake_llm.payloads == []
    finally:
        restore(old)


def test_a_non_hebrew_answer_is_not_accepted_as_a_translation(app5, pw_hash, fake_llm):
    old = with_conv([{"who": "customer", "at": "2026-10-04T10:00:00Z", "text": RU}])
    try:
        fake_llm.script = [lambda p: text(json.dumps({"translations": [{"i": 0, "text": RU}]}, ensure_ascii=False))]   # an echo
        c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"])
        r = c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
        assert r["ok"] and r["incomplete"] == 1 and r["conversation"] == []                     # never silent, original stays
    finally:
        restore(old)


def test_translate_he_gates(app5, pw_hash, fake_llm):
    c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["celesta"])
    assert c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).status_code == 403
    assert c.post("/api/celesta/translate-he", json={"ticketId": "../x"}, headers={"X-CSRF-Token": tok}).status_code == 400
    assert c.post("/api/celesta/translate-he", json={"ticketId": "t1"}).status_code == 403      # CSRF
    assert fake_llm.payloads == []


def test_translate_out_hebrew_desk_russian_customer_gets_hebrew(app5, pw_hash, fake_llm):
    """We reply only in Hebrew: a Hebrew agent's Hebrew text to a Russian customer is NOT translated into Russian."""
    c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"])
    r = c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": "היי, ההזמנה בדרך אלייך."}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] and r["target"] == "he" and r["text"] == "היי, ההזמנה בדרך אלייך." and fake_llm.payloads == []


def test_a_repeated_message_is_sent_to_the_model_once(app5, pw_hash, fake_llm):
    old = with_conv([{"who": "customer", "at": "2026-10-04T10:00:00Z", "text": RU}, {"who": "customer", "at": "2026-10-04T10:05:00Z", "text": RU}])
    try:
        fake_llm.script = [he_translations]
        c, tok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"])
        r = c.post("/api/rozela/translate-he", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
        assert [x["i"] for x in r["conversation"]] == [0, 1] and r["incomplete"] == 0
        assert len(json.loads(fake_llm.payloads[0]["messages"][0]["content"])["items"]) == 1
    finally:
        restore(old)
