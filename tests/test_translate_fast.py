"""2026-11-06 — the English desk's translation wait (measured 11-04/05: open median 2.7 s, 9/10 under 7-10 s, only 30% cache hits;
send median 4 s, one agent 41 of 315 sends refused): (1) an untouched AI draft goes out as the ticket's own Hebrew draft, no model call;
(2) an open translates what is on screen first and the older messages after; (3) the screen's prefetch translates ahead."""
import json
import time

import pytest

from conftest import logged_in
from test_assistant import EXTRAS, TICKET, app5, engine_reply, fake_llm, text, translations   # noqa: F401 (fixtures)


def en_desk(app5, pw_hash):
    return logged_in(app5, pw_hash, "eve", ["agent"], ["rozela"], lang="en")


def test_untouched_ai_draft_is_sent_as_the_hebrew_draft_without_a_model_call(app5, pw_hash, fake_llm):
    fake_llm.script = [translations]
    c, tok = en_desk(app5, pw_hash)
    shown = c.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()["draft"]
    n = len(fake_llm.payloads)
    r = c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": shown + "\n"}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] and r["text"] == TICKET["draft_text"]
    assert len(fake_llm.payloads) == n                                            # no English -> Hebrew round trip


def test_an_edited_draft_is_still_translated(app5, pw_hash, fake_llm):
    fake_llm.script = [translations, lambda p: text(json.dumps({"translations": [{"i": 0, "text": "היי דנה, אין בעיה בכלל."}]}))]
    c, tok = en_desk(app5, pw_hash)
    shown = c.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()["draft"]
    r = c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": shown + " Really."}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["ok"] and r["text"] == "היי דנה, אין בעיה בכלל."
    assert "Task: translate-out" in fake_llm.payloads[-1]["system"][0]["text"]


@pytest.fixture
def long_chat(monkeypatch):
    conv = [{"who": "customer" if i % 2 == 0 else "us", "at": "2026-10-04T1%d:00:00Z" % i, "text": "Сообщение номер %d" % i} for i in range(7)]
    monkeypatch.setitem(EXTRAS, "conversation", conv)
    return conv


def test_open_translates_the_screen_first_then_the_older_messages(app5, pw_hash, fake_llm, long_chat):
    fake_llm.script = [translations, translations]
    c, tok = en_desk(app5, pw_hash)
    first = c.post("/api/rozela/translate", json={"ticketId": "t1", "part": "recent"}, headers={"X-CSRF-Token": tok}).get_json()
    assert first["ok"] and first["more"] == 3 and first["draft"]
    assert [x["i"] for x in first["conversation"]] == [3, 4, 5, 6]
    items = json.loads(fake_llm.payloads[0]["messages"][0]["content"])["items"]
    assert len(items) == 4 + 2                                                    # the 4 newest messages + summary + draft
    rest = c.post("/api/rozela/translate", json={"ticketId": "t1", "part": "rest"}, headers={"X-CSRF-Token": tok}).get_json()
    assert [x["i"] for x in rest["conversation"]] == [0, 1, 2] and rest["more"] == 0 and rest["draft"] is None
    full = c.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
    assert len(full["conversation"]) == 7 and len(fake_llm.payloads) == 2        # both passes filled the same cache
    assert c.post("/api/rozela/translate", json={"ticketId": "t1", "part": "all"}, headers={"X-CSRF-Token": tok}).status_code == 400


def test_prefetch_translates_ahead_for_the_english_desk_only(app5, pw_hash, fake_llm):
    fake_llm.script = [translations]
    c, tok = en_desk(app5, pw_hash)
    r = c.post("/api/rozela/prefetch", json={"ids": ["t1"]}, headers={"X-CSRF-Token": tok, "X-UI-Lang": "en"})
    assert r.status_code == 200
    for _ in range(100):
        if fake_llm.payloads:
            break
        time.sleep(0.05)
    time.sleep(0.1)
    assert len(fake_llm.payloads) == 1
    opened = c.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
    assert opened["ok"] and opened["draft"] and len(fake_llm.payloads) == 1      # the open is a cache hit

    he, htok = logged_in(app5, pw_hash, "noa", ["agent"], ["rozela"], lang="he")
    he.post("/api/rozela/prefetch", json={"ids": ["t1"]}, headers={"X-CSRF-Token": htok, "X-UI-Lang": "he"})
    time.sleep(0.3)
    assert len(fake_llm.payloads) == 1                                            # the Hebrew desk never pays for English
