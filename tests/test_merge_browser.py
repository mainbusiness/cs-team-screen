""""מיזוג פניות" (the CS team, 2026-10-31): merge a duplicate email ticket of the customer into the ticket on screen (mock engine, real
browser). The related card offers the merge on every email ticket; a duplicate from another address is found by the card's own search;
one confirm step; the other ticket then reads "merged". WhatsApp tickets and archived tickets are never offered."""
import pytest

from browser_server import start
from pw_launch import launch, pw

MICHAL = "/cs#/b/rozela/t/t18f2a01"       # open, email, michal.levi@ — her old ticket t17aa001 is archived
YOSSI = "/cs#/b/rozela/t/t18f2a03"        # open, email, yossi.m@ — another customer address for the search
SHANI_WA = "/cs#/b/rozela/t/w8ab77c2"     # a WhatsApp chat


@pytest.fixture()
def srv():
    base, pwd, proc = start(users=(("agent1", ["agent"], ["rozela"], "he"), ("agent-en", ["agent"], ["rozela"], "en")))
    yield base, pwd
    proc.terminate()


def _login(p, base, pwd, user="agent1", width=1280):
    browser = launch(p)
    pg = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def test_find_a_duplicate_from_another_address_and_merge_it(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + MICHAL)
        rel = pg.locator("#related-card")
        rel.locator("[data-test=mg-more] summary").wait_for()
        assert rel.locator("[data-test=mg-btn][data-id=t17aa001]").count() == 0, "an archived ticket is never offered"
        rel.locator("[data-test=mg-more] summary").click()
        rel.locator("[data-test=mg-in]").fill("yossi.m@example.com")
        rel.locator("[data-test=mg-find]").click()
        btn = rel.locator("[data-test=mg-out] [data-test=mg-btn][data-id=t18f2a03]")
        btn.wait_for()
        assert btn.inner_text() == "⤵ מיזוג לפנייה הזו"
        btn.click()
        dlg = pg.locator("#confirm-dlg")
        dlg.wait_for()
        assert "יוסי מזרחי" in dlg.inner_text() and "אי אפשר לבטל" in dlg.inner_text()
        dlg.locator("button", has_text="למזג").click()
        pg.locator("#toast", has_text="הפניות מוזגו").wait_for()
        pg.locator(".notes-list", has_text="מוזגה לכאן פנייה t18f2a03").wait_for()       # the reopened ticket says what happened
        # the merged ticket now reads closed + merged, and offers no merge of its own
        pg.goto(base + YOSSI)
        pg.locator(".tk-head .chip.st-done").first.wait_for()
        pg.locator("#related-card").wait_for()
        assert pg.locator("#related-card [data-test=mg-more]").count() == 0
        assert not errors, errors
        browser.close()


def test_cancel_in_the_confirm_step_changes_nothing(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + MICHAL)
        rel = pg.locator("#related-card")
        rel.locator("[data-test=mg-more] summary").wait_for()
        rel.locator("[data-test=mg-more] summary").click()
        rel.locator("[data-test=mg-in]").fill("yossi")
        rel.locator("[data-test=mg-find]").click()
        btn = rel.locator("[data-test=mg-out] [data-test=mg-btn][data-id=t18f2a03]")
        btn.wait_for()
        btn.click()
        pg.locator("#confirm-dlg").wait_for()
        pg.locator("#confirm-dlg button.ghost").click()
        pg.goto(base + YOSSI)
        pg.locator("#related-card [data-test=mg-more]").wait_for()                      # still its own open ticket
        assert not errors, errors
        browser.close()


def test_whatsapp_tickets_get_no_merge(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + SHANI_WA)
        pg.locator("#related-card").wait_for()
        pg.wait_for_timeout(500)
        assert pg.locator("#related-card [data-test=mg-more]").count() == 0
        assert pg.locator("#related-card [data-test=mg-btn]").count() == 0
        assert not errors, errors
        browser.close()


def test_english_screen_and_phone_width(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, user="agent-en", width=390)
        pg.goto(base + "/cs/en" + MICHAL[3:])
        rel = pg.locator("#related-card")
        rel.locator("[data-test=mg-more] summary").wait_for()
        assert "Merge a duplicate" in rel.locator("[data-test=mg-more] summary").inner_text()
        rel.locator("[data-test=mg-more] summary").click()
        rel.locator("[data-test=mg-in]").fill("yossi")
        rel.locator("[data-test=mg-find]").click()
        btn = rel.locator("[data-test=mg-out] [data-test=mg-btn][data-id=t18f2a03]")
        btn.wait_for()
        assert btn.inner_text() == "⤵ Merge into this ticket"
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "no horizontal scroll at phone width"
        assert not errors, errors
        browser.close()
