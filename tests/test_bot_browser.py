"""Real browser: bot tab + take over, photo chips, and a DRY_RUN flip reaching an open ticket without a reload."""
import pytest

from test_resilience_browser import server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def login(p, base, user, pwd, path="/cs/login"):
    browser = p.chromium.launch()
    pg = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    pg.goto(base + path)
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg


def test_bot_tab_takeover_and_photos(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/bot")
        pg.wait_for_selector("a.row[data-id=w8ab77c2]")
        assert pg.locator(".tab.bot .n").inner_text() == "1"
        pg.click("a.row[data-id=w8ab77c2]")
        pg.wait_for_selector("[data-test=bot-banner]")
        assert pg.locator(".draft").count() == 0                                   # no draft while the bot has it
        assert pg.locator("[data-test=photo-dondy]").inner_text() == "📷 תמונה — לצפייה בדונדי"
        assert pg.locator("[data-test=photo-file]").get_attribute("href").startswith("https://drive.google.com/")
        assert pg.locator("[data-test=photo-wait]").count() == 1
        assert pg.locator(".msg img").count() == 0                                  # never a broken image
        pg.click("[data-test=takeover]")
        pg.click("[data-test=takeover]")
        pg.wait_for_selector("text=השיחה אצלך")
        pg.wait_for_selector("[data-test=bot-banner]", state="detached", timeout=15000)
        assert pg.locator(".tk-head .chip.st-action").count() == 1
        browser.close()


def test_dry_run_flip_reaches_an_open_ticket_without_reload(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        ba, admin = login(p, base, "admin1", pwd)
        bb, agent = login(p, base, "agent1", pwd)
        admin.goto(base + "/cs#/settings/rozela")
        admin.wait_for_selector(".set-row[data-key=DRY_RUN] .seg-btn")
        admin.click(".set-row[data-key=DRY_RUN] .seg-btn:has-text('פועל')")           # test mode ON
        admin.click("#confirm-dlg .btn:not(.ghost)")                                   # the confirm button, not Cancel
        admin.wait_for_selector(".set-row[data-key=DRY_RUN] .seg-btn.on:has-text('פועל')")
        agent.goto(base + "/cs#/b/rozela/t/t18f2a01")
        agent.wait_for_selector("[data-test=send-btn][disabled]", timeout=20000)      # opened under test mode
        url = agent.url
        admin.click(".set-row[data-key=DRY_RUN] .seg-btn:has-text('כבוי')")            # Manager turns test mode OFF
        admin.click("#confirm-dlg .btn:not(.ghost)")
        agent.wait_for_selector("[data-test=send-btn]:not([disabled])", timeout=20000) # one 15 s poll at most
        assert agent.url == url                                                        # no reload, same page
        ba.close()
        bb.close()


def test_ticket_open_rereads_switches_before_any_poll(server):
    """The flip happens while the agent sits on the LIST; opening a ticket must not use the stale test-mode state."""
    base, pwd = server
    with pw.sync_playwright() as p:
        ba, admin = login(p, base, "admin1", pwd)
        bb, agent = login(p, base, "agent1", pwd)
        admin.goto(base + "/cs#/settings/rozela")
        admin.wait_for_selector(".set-row[data-key=DRY_RUN] .seg-btn")
        if admin.locator(".set-row[data-key=DRY_RUN] .seg-btn.on:has-text('פועל')").count() == 0:
            admin.click(".set-row[data-key=DRY_RUN] .seg-btn:has-text('פועל')")
            admin.click("#confirm-dlg .btn:not(.ghost)")
            admin.wait_for_selector(".set-row[data-key=DRY_RUN] .seg-btn.on:has-text('פועל')")
        agent.goto(base + "/cs#/b/rozela/ready")
        agent.wait_for_selector("a.row")
        agent.wait_for_selector("[data-test=dry-run]")                                 # the agent's list says: test mode
        admin.click(".set-row[data-key=DRY_RUN] .seg-btn:has-text('כבוי')")
        admin.click("#confirm-dlg .btn:not(.ghost)")
        admin.wait_for_selector(".set-row[data-key=DRY_RUN] .seg-btn.on:has-text('כבוי')")
        agent.click("a.row[data-id=t18f2a01]")                                         # same page, hash navigation
        agent.wait_for_selector("[data-test=send-btn]:not([disabled])", timeout=4000)  # well before the 15 s poll
        ba.close()
        bb.close()
