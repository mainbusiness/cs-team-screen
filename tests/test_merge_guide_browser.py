"""Owner, 2026-11-20: "the agents did not understand how to merge tickets": a short guide shown ONCE per agent (ack stored server-side per user, like every
notice), reopened from the "❓" next to the merge control and from the ☰ menu; he + en desks. Real browser, mock engine. The steps are checked against the
screen's own merge control (the card, the button text, the "another address" search)."""
import json
import os
import tempfile

import pytest

import browser_server
import notice
from pw_launch import launch, pw  # noqa: F401

ID = "merge-guide-2026-11-20"
CUR = "/cs#/b/rozela/t/t18f2a03"


@pytest.fixture(scope="module")
def server():
    d = tempfile.mkdtemp(prefix="cs-mguide-")
    path = os.path.join(d, "notice-acks.json")
    with open(path, "w") as f:                          # the Kaching procedure is not under test here: acknowledged for everyone
        json.dump({"acks": {u: {notice.KACHING_SUBS["id"]: 1.0} for u in ("ann", "ann390", "ann-en", "bob")}}, f)
    base, pwd, proc = browser_server.start(extra_env={"NOTICE_PATH": path}, users=(("ann", ["agent"], ["rozela"], "he"), ("ann390", ["agent"], ["rozela"], "he"), ("ann-en", ["agent"], ["rozela"], "en"),
                                                                                  ("bob", ["agent"], ["rozela"], "he")))
    yield base, pwd, path
    proc.terminate()
    proc.wait(timeout=10)


def login(p, base, pwd, user, width=1280):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def until_closed(pg, ms=6000):
    for _ in range(ms // 100):
        if not is_open(pg):
            return
        pg.wait_for_timeout(100)
    raise AssertionError("the dialog stayed open")


def is_open(pg):
    return pg.evaluate("() => { const d = document.getElementById('notice-dlg'); return !!(d && d.open); }")


@pytest.mark.parametrize("width", [1280, 390])
def test_the_guide_appears_once_then_reopens_from_the_question_mark_and_the_menu(server, width):
    base, pwd, path = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "ann" if width == 1280 else "ann390", width)
        pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)
        assert pg.text_content("[data-test=notice-title]") == "🔗 איך מאחדים פניות (מיזוג)"
        body = pg.text_content("[data-test=notice-dlg]")
        for s in ("פניות קודמות של הלקוח", "⤵ מיזוג לפנייה הזו", "מיזוג פנייה כפולה מכתובת אחרת", "חיפוש", "למזג", "אי אפשר לבטל מיזוג", "לא וואטסאפ"):
            assert s in body, s
        pg.keyboard.press("Escape")
        assert is_open(pg), "an unacknowledged guide is not dismissed by Esc"
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.click("[data-test=notice-ack]")
        until_closed(pg)
        pg.reload()
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(800)
        assert not is_open(pg), "shown ONCE: the next open shows nothing"
        # a reopen from the card's "❓" (next to the merge control), read mode
        pg.goto(base + CUR)
        q = pg.locator("[data-test=mrg-guide]")
        q.wait_for()
        assert q.inner_text() == "❓ מדריך איחוד פניות"
        q.click()
        pg.wait_for_selector("[data-test=notice-dlg][open]")
        assert pg.locator("[data-test=notice-acked]").count() == 1 and pg.locator("[data-test=notice-ack]").count() == 0
        pg.click("[data-test=notice-close]")
        assert not is_open(pg)
        assert not errors, errors
        browser.close()


def test_another_agent_gets_it_too_and_the_ack_is_per_agent(server):
    base, pwd, path = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "bob")
        pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)                  # ann acked: bob still sees it
        assert pg.text_content("[data-test=notice-title]") == "🔗 איך מאחדים פניות (מיזוג)"
        acks = json.load(open(path))["acks"]
        assert ID in acks["ann"] and ID not in acks.get("bob", {}), "stored server-side, per agent"
        browser.close()


def test_english_desk_gets_the_english_guide(server):
    base, pwd, path = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "ann-en", 390)
        pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)
        assert pg.text_content("[data-test=notice-title]") == "🔗 How to merge tickets"
        assert pg.get_attribute("#notice-dlg", "dir") == "ltr" and pg.get_attribute("#notice-dlg", "lang") == "en"
        body = pg.text_content("[data-test=notice-dlg]")
        for s in ("Customer's other tickets", "⤵ Merge into this ticket", "Merge a duplicate from another address", "Search", "Merge", "cannot be undone", "not WhatsApp"):
            assert s in body, s
        assert pg.inner_text("[data-test=notice-ack]") == "✅ Got it"
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.click("[data-test=notice-ack]")
        until_closed(pg)
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
        q = pg.locator("[data-test=mrg-guide]")
        q.wait_for()
        assert q.inner_text() == "❓ How to merge tickets"
        q.click()
        pg.wait_for_selector("[data-test=notice-dlg][open]")
        assert "✓ You confirmed you read this" in pg.inner_text("[data-test=notice-acked]")
        assert not errors, errors
        browser.close()


def test_the_steps_match_the_screens_own_merge_control(server):
    """The guide names the real controls: the same strings must exist on the card, so a rename of the button breaks this test, not the agents."""
    base, pwd, path = server
    js = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app.js"), encoding="utf-8").read()
    for guide in (notice.MERGE_GUIDE, notice.MERGE_GUIDE["en"]):
        text = json.dumps(guide, ensure_ascii=False).replace("**", "")
        for label in ("⤵ מיזוג לפנייה הזו",) if guide is notice.MERGE_GUIDE else ("⤵ Merge into this ticket",):
            assert label in text and label in js, label
