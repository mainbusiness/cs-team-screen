"""Owner, 2026-10-07: what the English desk sends must read as written by a person. Never an em dash, never a double hyphen."""
import json

import assistant
from test_assistant import app5, fake_llm, logged_in, text  # noqa: F401 (fixtures)


def test_dashes_become_commas_and_ranges_keep_a_plain_hyphen():
    h = assistant.humanize_hebrew_dashes
    assert h("שלום — ההזמנה בדרך") == "שלום, ההזמנה בדרך"
    assert h("תודה -- נעדכן") == "תודה, נעדכן"
    assert h("המשלוח לוקח 7–12 ימי עסקים") == "המשלוח לוקח 7-12 ימי עסקים"
    assert h("— היי\nבדקתי — .") == "היי\nבדקתי."
    assert h("מספר הזמנה AB-1234 נשאר") == "מספר הזמנה AB-1234 נשאר"            # a single hyphen is not touched
    assert h("https://x.example/a--b—c") == "https://x.example/a--b—c"            # links are never rewritten
    for bad in ("א — ב", "א – ב", "א -- ב", "א ― ב"):
        assert assistant.has_forbidden_dash(bad)
        assert not assistant.has_forbidden_dash(h(bad))


def test_style_brief_is_sent_for_hebrew_and_forbids_dashes(app5, pw_hash, fake_llm):
    fake_llm.script = [lambda p: text(json.dumps({"translations": [{"i": 0, "text": "שלום דנה — בדקתי -- הכול בסדר"}]}))]
    c, tok = logged_in(app5, pw_hash, "eve", ["agent"], ["rozela"], lang="en")
    r = c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": "Hi Dana, I checked, all good"}, headers={"X-CSRF-Token": tok}).get_json()
    assert r == {"ok": True, "text": "שלום דנה, בדקתי, הכול בסדר", "target": "he"}
    system = fake_llm.payloads[-1]["system"][0]["text"]
    assert "NEVER use the em dash" in system and "word for word" in system
