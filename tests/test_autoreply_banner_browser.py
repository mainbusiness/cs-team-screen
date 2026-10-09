"""Owner, 2026-10-09: a mail the bot answered is marked read in Gmail, so the screen itself must tell the agents to check what the bot wrote."""
import pytest

import browser_server
from pw_launch import launch, pw


@pytest.fixture
def pg():
    base, pwd, proc = browser_server.start({}, users=(("agent1", ["agent"], ["rozela"], "he"),))
    with pw.sync_playwright() as p:
        b = launch(p)
        page = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
        page.goto(base + "/cs/login")
        page.fill("input[name=username]", "agent1")
        page.fill("input[name=password]", pwd)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        yield page, base
        b.close()
    proc.terminate()


def test_the_banner_tells_agents_to_check_the_bot_and_leaves_when_they_did(pg):
    page, base = pg
    page.goto(base + "/cs#/b/rozela/ready")
    page.wait_for_selector("[data-test=ar-review-banner]")
    banner = page.locator("[data-test=ar-review-banner]")
    assert banner.get_attribute("data-n") == "1"                      # one reply really sent; the shadow "would send" is not counted
    assert "הבוט ענה לבד" in banner.inner_text() and "שטויות" in banner.inner_text()
    page.click("a.row")                                                # it stays while a ticket is open
    page.wait_for_selector(".draft textarea, [data-test=wa-queued], [data-test=bot-banner]")
    assert page.locator("[data-test=ar-review-banner]").count() == 1
    page.click("[data-test=ar-review-go]")
    page.wait_for_selector("[data-test=ar-ok]")
    assert page.url.endswith("/autoreply") and page.locator("[data-test=ar-review-banner]").count() == 0   # on the list itself: no need
    cards = page.locator("[data-test=ar-ok]")
    for i in range(cards.count()):                                     # review everything that waits
        page.locator("[data-test=ar-ok]").first.click()
        page.wait_for_timeout(1200)
    page.goto(base + "/cs#/b/rozela/ready")
    page.wait_for_selector("a.row")
    page.wait_for_timeout(1500)
    assert page.locator("[data-test=ar-review-banner]").count() == 0   # all reviewed: the reminder is gone
