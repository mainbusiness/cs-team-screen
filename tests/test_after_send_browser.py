"""Owner, 2026-10-09: an agent's message is always sent. What it promised and the system could not do (a subscription that was not cancelled)
comes back with the send's answer and stays on screen as a reminder until the agent says it is handled; a cancellation that was done is a toast."""
import json

import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def _send_with(pg, base, after):
    def add_after(route, req):
        r = route.fetch()
        j = r.json()
        if j.get("ok"):
            j["after"] = after
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/rozela/apiSend", add_after)
    pg.goto(base + "/cs#/b/rozela")
    pg.wait_for_selector("#list-pane > a.row.email")
    pg.locator("#list-pane > a.row.email").first.click()
    pg.wait_for_selector("[data-test=send-btn]")
    pg.click("[data-test=send-btn]")
    pg.wait_for_timeout(350)
    pg.click("[data-test=send-btn]")


def test_reminder_stays_until_the_agent_says_it_is_handled(page):
    pg, base = page
    _send_with(pg, base, {"reminders": ["sub_several", "<script>"], "messages": ["x"]})
    pg.wait_for_selector("[data-test=after-send]")
    text = pg.inner_text("[data-test=after-send]")
    assert "נשלחה" in text and "כמה מנויים פעילים" in text
    assert "<script>" not in text and "as_" not in text          # an unknown code is dropped, never shown raw
    pg.reload()
    pg.wait_for_selector("[data-test=after-send]")                # survives a reload
    pg.click("[data-test=after-send-done]")
    assert pg.locator("[data-test=after-send]").count() == 0
    pg.reload()
    pg.wait_for_load_state("load")
    pg.wait_for_timeout(1500)
    assert pg.locator("[data-test=after-send]").count() == 0


def test_a_cancellation_that_was_done_leaves_no_reminder(page):
    pg, base = page
    _send_with(pg, base, {"cancelled": "gid://shopify/SubscriptionContract/1", "reminders": [], "messages": []})
    pg.wait_for_timeout(2500)
    assert pg.locator("[data-test=after-send]").count() == 0
