"""Owner, 2026-10-07: WhatsApp allows free text only within 24 hours of the customer's last message. The screen says so on the row and on
the ticket, gives those chats their own tab, never offers a free-text send for them, and puts a chat that is about to close first."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def test_over_24h_tab_lists_the_chat_with_its_label(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/wa24")
    pg.wait_for_selector("#list-pane > a.row")
    assert "מעל 24 שעות" in pg.inner_text("a.tab.wa24")
    ids = pg.eval_on_selector_all("#list-pane > a.row", "els => els.map(e => e.getAttribute('data-id'))")
    assert "w8ab77f2" in ids                                         # the customer wrote 30 hours ago
    assert "w8ab77c1" not in ids and "w8ab77f1" not in ids           # 0.6 h and 2 h ago: inside the window
    assert pg.inner_text("a.tab.wa24 .n") == str(len(ids))
    assert pg.inner_text("a.row[data-id=w8ab77f2] [data-test=wa-win-chip]") == "🕓 מעל 24 שעות — רק תבנית"
    assert pg.locator("a.row[data-id=w8ab77f2] [data-test=wa-fail-chip]").count() == 0       # one message, not two


def test_inside_the_window_there_is_no_label_and_send_works(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/action")
    pg.wait_for_selector("a.row[data-id=w8ab77c1]")
    assert pg.locator("a.row[data-id=w8ab77c1] [data-test=wa-win-chip]").count() == 0
    assert pg.locator("a.row[data-id=t18f2a03] [data-test=wa-win-chip]").count() == 0      # an email never has a window
    pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
    pg.wait_for_selector("[data-test=send-btn]")
    assert pg.locator("[data-test=wa-win-note]").count() == 0


def test_past_24h_the_ticket_explains_and_free_text_cannot_be_sent(page):
    pg, base = page
    sends = []
    pg.on("request", lambda r: sends.append(r.url) if r.url.endswith("/apiSend") else None)
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f2")
    pg.wait_for_selector("[data-test=wa-win-note]")
    assert "24 שעות" in pg.inner_text("[data-test=wa-win-note]")
    assert "רק תבנית" in pg.inner_text(".tk-head [data-test=wa-win-chip]")
    btn = pg.locator("[data-test=send-btn]")
    if btn.count():
        assert btn.is_disabled()
        btn.click(force=True)
        pg.wait_for_timeout(400)
    assert sends == []


def test_a_chat_about_to_close_is_first_in_its_tab(page):
    pg, base = page
    soon = (datetime.now(timezone.utc) - timedelta(hours=22)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def older(route, req):                       # the engine's list, with ONE inside-the-window chat made 22 hours old
        r = route.fetch()
        j = r.json()
        for t in j.get("tickets") or []:
            if t.get("id") == "w8ab77c1":
                t["wa_last_in"] = soon
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/rozela/list", older)
    pg.route("**/api/rozela/changes", lambda route, req: route.fulfill(status=200, content_type="application/json", body='{"ok":true,"changed":[],"removed":[]}'))
    pg.goto(base + "/cs#/b/rozela/action")
    pg.evaluate("() => { for (const k of Object.keys(sessionStorage)) sessionStorage.removeItem(k); }")
    pg.reload()                                  # the list is read again, through the route
    pg.wait_for_selector("a.row[data-id=w8ab77c1] [data-test=wa-win-chip]")
    assert pg.get_attribute("a.row[data-id=w8ab77c1] [data-test=wa-win-chip]", "data-state") == "soon"
    assert "נסגר בעוד" in pg.inner_text("a.row[data-id=w8ab77c1] [data-test=wa-win-chip]")
    ids = pg.eval_on_selector_all("#list-pane > a.row", "els => els.map(e => e.getAttribute('data-id'))")
    assert ids[0] == "w8ab77c1" and len(ids) > 1, ids


def test_past_24h_a_template_is_picked_and_sent_with_the_reply_that_waits(page):
    pg, base = page
    calls = []

    def seen(r):
        if r.url.endswith("/apiSendTemplate"):
            calls.append(json.loads(r.post_data or "{}"))
    pg.on("request", seen)
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f2")
    pg.wait_for_selector("[data-test=tpl-select] option", state="attached")
    names = pg.eval_on_selector_all("[data-test=tpl-select] option", "els => els.map(e => e.textContent)")
    assert names == ["Check 2", "Start"]
    assert "זמן נוח להמשיך" in pg.inner_text("[data-test=tpl-preview]")
    pg.select_option("[data-test=tpl-select]", label="Start")
    assert pg.inner_text("[data-test=tpl-preview]") == "היי מה נשמע?"
    pg.select_option("[data-test=tpl-select]", label="Check 2")       # (by label: index=0 is ignored by this client)
    pg.fill(".draft textarea", "ההזמנה שלך יצאה אתמול.")
    if not pg.is_checked("[data-test=tpl-then]"):
        pg.check("[data-test=tpl-then]")
    pg.click("[data-test=tpl-send]")                    # first click arms
    pg.wait_for_timeout(300)
    assert calls == []
    pg.click("[data-test=tpl-send]")                    # second click sends
    for _ in range(100):                                # (the page's CSP forbids evaluating a string, so poll from here)
        if calls or pg.locator("[data-test=tpl-error]:not([hidden])").count():
            break
        pg.wait_for_timeout(100)
    pg.wait_for_timeout(500)
    assert len(calls) == 1 and calls[0]["args"] == {"id": "w8ab77f2", "template": "Check 2", "then": "ההזמנה שלך יצאה אתמול."}, calls


def test_inside_the_window_no_template_box_is_offered(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
    pg.wait_for_selector("[data-test=send-btn]")
    assert pg.locator("[data-test=tpl-box]").count() == 0


def test_english_desk_past_24h_shows_the_template_picker_and_no_review_button():
    """The English desk draws its own draft card: it must offer the template too (a missing variable once left it blank, live, 2026-10-07)."""
    from browser_server import start
    from pw_launch import launch
    base, pwd, proc = start(users=(("lyra-test", ["agent"], ["rozela"], "en"),))
    try:
        with pw.sync_playwright() as p:
            browser = launch(p)
            pg = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(base + "/cs/en/login")
            pg.fill("input[name=username]", "lyra-test")
            pg.fill("input[name=password]", pwd)
            pg.click("button[type=submit]")
            pg.goto(base + "/cs/en#/b/rozela/t/w8ab77f2")
            pg.wait_for_selector("[data-test=en-draft] [data-test=tpl-select] option", state="attached")
            assert "24 hours" in pg.inner_text("[data-test=en-draft] [data-test=wa-win-note]")
            assert pg.eval_on_selector_all("[data-test=tpl-select] option", "els => els.map(e => e.textContent)") == ["Check 2", "Start"]
            assert not pg.is_visible("[data-test=en-review-btn]")
            assert errors == [], errors
            pg.goto(base + "/cs/en#/b/rozela/t/w8ab77c1")                     # inside the window: the normal English flow, no template box
            pg.wait_for_selector("[data-test=en-review-btn]")
            assert pg.locator("[data-test=tpl-box]").count() == 0
            assert errors == [], errors
            browser.close()
    finally:
        proc.terminate()
