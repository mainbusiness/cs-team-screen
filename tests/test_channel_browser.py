"""WhatsApp vs email (Owner, 2026-10-05): "a clear green sign when it's WhatsApp". Real browser against the mock."""
import pytest

from test_resilience_browser import server  # noqa: F401  (module-scoped mock app)

from pw_launch import launch, pw  # noqa: E402  (bundled Chromium, else installed Chrome)


def login(p, base, user, pwd, width=390):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 844}).new_page()
    pg.goto(base + ("/cs/en/login" if user.endswith("-en") else "/cs/login"))
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg


def rgb(pg, sel, prop):
    return pg.locator(sel).first.evaluate("(e, p) => getComputedStyle(e).getPropertyValue(p)", prop)


def test_rows_pills_stripe_and_filter(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/action")
        pg.wait_for_selector("a.row.wa")
        wa = pg.locator("a.row.wa").first
        assert "וואטסאפ" in wa.inner_text() and wa.locator("[data-test=ch-wa] svg").count() == 1
        assert pg.locator("a.row.email [data-test=ch-email]").count() >= 1
        side = "right"                                                     # RTL: the stripe sits on the inline-start edge
        assert rgb(pg, "a.row.wa", "border-%s-color" % side) == "rgb(37, 211, 102)"
        assert rgb(pg, "a.row.wa", "border-%s-width" % side) == "4px"
        assert rgb(pg, "a.row.wa [data-test=ch-wa]", "color") == "rgb(7, 94, 84)"
        # filter
        pg.click("[data-test=chan-filter] .chan-btn.whatsapp")
        assert pg.locator("a.row.email").count() == 0 and pg.locator("a.row.wa").count() >= 1
        pg.click("[data-test=chan-filter] .chan-btn.email")
        assert pg.locator("a.row.wa").count() == 0 and pg.locator("a.row.email").count() >= 1
        pg.click("[data-test=chan-filter] .chan-btn.all")
        assert pg.locator("a.row.wa").count() >= 1 and pg.locator("a.row.email").count() >= 1
        browser.close()


def test_ticket_banner_tint_and_send_labels(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
        pg.wait_for_selector("[data-test=wa-banner]")
        assert pg.locator(".card.wa .msg.customer").count() >= 1
        assert rgb(pg, ".card.wa .msg.customer", "background-color") == "rgb(234, 249, 238)"
        pg.fill(".draft textarea", "היי, כן, יש משלוח לאילת")
        btn = pg.locator("[data-test=send-btn]")
        assert btn.inner_text() == "שליחה בוואטסאפ"
        assert rgb(pg, "[data-test=send-btn]", "background-color") == "rgb(0, 128, 105)"
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
        pg.wait_for_selector("[data-test=email-banner]")
        assert pg.locator("[data-test=send-btn]").inner_text() == "שליחה במייל"
        assert pg.locator(".card.wa").count() == 0
        browser.close()


def test_english_labels(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent-en", pwd)
        pg.goto(base + "/cs/en#/b/rozela/action")
        pg.wait_for_selector("a.row.wa")
        assert "WhatsApp" in pg.locator("a.row.wa [data-test=ch-wa]").first.inner_text()
        assert "Email" in pg.locator("a.row.email [data-test=ch-email]").first.inner_text()
        pg.goto(base + "/cs/en#/b/rozela/t/w8ab77c1")
        pg.wait_for_selector("[data-test=wa-banner]")
        assert "WhatsApp" in pg.inner_text("[data-test=wa-banner]")
        browser.close()
