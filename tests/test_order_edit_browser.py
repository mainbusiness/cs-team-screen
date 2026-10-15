"""Owner, 2026-10-16: edit the customer's Shopify order from the ticket (mock engine, real browser) — both desks, 1280 and 390 px."""
import json

import pytest
from browser_server import start
from pw_launch import launch, pw

TICKET = "t18f2a03"          # rozela; orders #4530 (unfulfilled) and #4310 (shipped)
DESKS = {"he": ("/cs", "agent1"), "en": ("/cs/en", "agent-en")}
USERS = (("agent1", ["agent"], ["rozela"], "he"), ("agent-en", ["agent"], ["rozela"], "en"), ("admin1", ["admin"], ["rozela"], "he"))


@pytest.fixture()
def srv():
    base, pwd, proc = start(users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user, width, path="/cs"):
    browser = launch(p)
    pg = browser.new_page(viewport={"width": width, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + path + "/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.goto(base + path + "#/b/rozela/t/" + TICKET)
    pg.wait_for_selector("[data-test=oe-btn]")
    pg._oe_base_width = pg.evaluate("document.documentElement.scrollWidth")
    return browser, pg, errors


def fits(pg, width):
    # the page's own tab strip is wider than a phone (pre-existing); the dialog must add nothing to it and sit inside the viewport
    assert pg.evaluate("document.documentElement.scrollWidth") <= pg._oe_base_width, "the dialog widened the page"
    box = pg.locator("#order-dlg").bounding_box()
    assert box and box["x"] >= -1 and box["x"] + box["width"] <= width + 1


def api_calls(pg):
    calls = []
    pg.on("request", lambda r: calls.append(json.loads(r.post_data or "{}")) if r.url.endswith("/apiOrderEdit") else None)
    return calls


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("desk", ["he", "en"])
def test_agent_edits_the_address_and_is_stopped_on_a_price_rise(srv, desk, width):
    base, pwd = srv
    path, user = DESKS[desk]
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, user, width, path)
        calls = api_calls(pg)
        assert pg.locator("[data-test=oe-btn]").count() == 1            # only the unfulfilled order has the button
        assert pg.locator("[data-test=oe-btn]").is_enabled()
        pg.click("[data-test=oe-btn]")
        pg.wait_for_selector("[data-test=oe-items]")
        fits(pg, width)
        # items: raising the price is an admin's call -> the agent sees why and cannot confirm
        pg.locator("[data-test=oe-line-qty]").first.fill("2")
        pg.click("[data-test=oe-next]")
        pg.wait_for_selector("[data-test=oe-confirm]")
        assert pg.locator("[data-test=oe-admin]").is_visible()
        assert pg.locator("[data-test=oe-delta]").is_visible()
        assert pg.locator("[data-test=oe-money-note]").is_visible()
        pg.fill("[data-test=oe-code]", "4530")
        assert pg.is_disabled("[data-test=oe-go]")
        dtxt = pg.inner_text("#order-dlg")
        assert "null" not in dtxt and "undefined" not in dtxt and "NaN" not in dtxt, dtxt
        fits(pg, width)
        pg.screenshot(path="/tmp/oe-%s-%d-items.png" % (desk, width))
        pg.click("[data-test=oe-back]")
        # address: preview, a wrong number keeps the button off, the right one applies
        pg.click("[data-test=oe-tab-address]")
        pg.fill("[data-test=oe-f-city]", "חיפה")
        pg.click("[data-test=oe-next]")
        pg.wait_for_selector("[data-test=oe-summary]")
        assert "חיפה" in pg.inner_text("[data-test=oe-summary]")
        assert pg.locator("[data-test=oe-admin]").count() == 0
        assert "null" not in pg.inner_text("#order-dlg")
        pg.fill("[data-test=oe-code]", "9999")
        assert pg.is_disabled("[data-test=oe-go]")
        pg.fill("[data-test=oe-code]", "4530")
        assert not pg.is_disabled("[data-test=oe-go]")
        pg.screenshot(path="/tmp/oe-%s-%d-confirm.png" % (desk, width))
        pg.click("[data-test=oe-go]")
        pg.wait_for_selector("[data-test=oe-note]")
        assert ("עודכנה" in pg.inner_text("[data-test=oe-note]")) if desk == "he" else ("updated" in pg.inner_text("[data-test=oe-note]"))
        applies = [c for c in calls if c["args"].get("mode") == "apply"]
        assert len(applies) == 1 and applies[0]["args"]["kind"] == "address" and applies[0]["args"]["confirm"] == "4530"
        # reopened, the order shows the new city (a live re-read, not the typed text)
        pg.click("[data-test=oe-tab-address]")
        assert pg.input_value("[data-test=oe-f-city]") == "חיפה"
        fits(pg, width)
        pg.screenshot(path="/tmp/oe-%s-%d-done.png" % (desk, width))
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_admin_adds_a_product_and_the_card_refreshes(srv, width):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "admin1", width)
        calls = api_calls(pg)
        before = pg.locator("#orders-card li").count()
        pg.click("[data-test=oe-btn]")
        pg.wait_for_selector("[data-test=oe-items]")
        pg.wait_for_function("document.querySelector('[data-test=oe-add-sel]').options.length > 1")
        pg.select_option("[data-test=oe-add-sel]", index=1)
        pg.click("[data-test=oe-next]")
        pg.wait_for_selector("[data-test=oe-confirm]")
        assert pg.locator("[data-test=oe-admin]").count() == 0
        assert "189" in pg.inner_text("[data-test=oe-delta]")
        pg.fill("[data-test=oe-code]", "4530")
        pg.click("[data-test=oe-go]")
        pg.wait_for_selector("[data-test=oe-note]")
        pg.click("[data-test=oe-close]")
        pg.wait_for_function("document.querySelectorAll('#orders-card li').length === %d" % (before + 1))
        applies = [c for c in calls if c["args"].get("mode") == "apply"]
        assert len(applies) == 1 and applies[0]["args"]["expectDelta"] == "189.00"
        fits(pg, width) if pg.locator("#order-dlg[open]").count() else None
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("desk", ["he", "en"])
def test_button_is_disabled_with_a_reason_while_the_switch_is_off(srv, desk):
    base, pwd = srv
    path, user = DESKS[desk]
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 390, "height": 900})

        def off(route):
            resp = route.fetch()
            data = resp.json()
            if "orderEdits" in data:
                data["orderEdits"] = "off"
            route.fulfill(response=resp, json=data)
        pg.route("**/api/rozela/list", off)
        pg.route("**/api/rozela/changes", off)
        pg.goto(base + path + "/login")
        pg.fill("input[name=username]", user)
        pg.fill("input[name=password]", pwd)
        pg.click("button[type=submit]")
        pg.wait_for_load_state("networkidle")
        pg.goto(base + path + "#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=oe-btn]")
        assert pg.is_disabled("[data-test=oe-btn]")
        why = pg.inner_text("[data-test=oe-why]")
        assert ("כבויה" in why) if desk == "he" else ("switched off" in why)
        assert "\n" not in why.strip()
        browser.close()
