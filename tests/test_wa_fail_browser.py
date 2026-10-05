"""Engine @37/38: a failed WhatsApp send is back in "action" with ⚠️. The screen shows it loudly, counts it, and offers
"שלח שוב" ONLY for a plain failure — never for unknown (it may have gone out) or template_required."""
import json

import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def test_failed_tab_counts_and_row_chips(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/failed")
    pg.wait_for_selector("#list-pane > a.row")
    assert pg.inner_text("a.tab.failed .n") == "2" and "נכשלו" in pg.inner_text("a.tab.failed")
    ids = pg.eval_on_selector_all("#list-pane > a.row", "els => els.map(e => e.getAttribute('data-id'))")
    assert sorted(ids) == ["w8ab77f1", "w8ab77f2"]
    assert pg.inner_text("a.row[data-id=w8ab77f1] [data-test=wa-fail-chip]") == "⚠️ השליחה נכשלה"
    assert pg.inner_text("a.row[data-id=w8ab77f2] [data-test=wa-fail-chip]") == "⚠️ עברו 24 שעות — צריך תבנית בדונדי"
    pg.goto(base + "/cs#/b/rozela/action")                                          # the same chip in the normal tab
    pg.wait_for_selector("a.row[data-id=w8ab77f1] [data-test=wa-fail-chip]")
    assert pg.locator("a.row[data-id=t18f2a03] [data-test=wa-fail-chip]").count() == 0


def test_template_required_and_unknown_never_offer_a_resend(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f2")
    pg.wait_for_selector("[data-test=wa-fail]")
    assert pg.inner_text(".tk-head [data-test=wa-fail-chip]") == "⚠️ עברו 24 שעות — צריך תבנית בדונדי"
    assert pg.locator("[data-test=wa-resend]").count() == 0

    def unknown(route, req):
        r = route.fetch()
        j = r.json()
        if j.get("ok") and j.get("ticket", {}).get("id") == "w8ab77f1":
            j["ticket"]["wa_send"] = "unknown:dondy-ext:1"
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/rozela/ticket", unknown)
    pg.route("**/api/rozela/watch", lambda route, req: route.fulfill(status=200, content_type="application/json", body='{"ok":true,"changed":false}'))
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.evaluate("() => { for (const k of Object.keys(sessionStorage)) sessionStorage.removeItem(k); }")
    pg.reload()
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f1")
    pg.wait_for_selector("[data-test=wa-fail]")
    assert "לא ידוע אם ההודעה יצאה" in pg.inner_text("[data-test=wa-fail]") and pg.locator("[data-test=wa-resend]").count() == 0
    pg.unroute("**/api/rozela/ticket")
    pg.unroute("**/api/rozela/watch")


def test_resend_requeues_the_same_text_through_the_outbox_with_a_new_rid(page):
    pg, base = page
    sends = []
    pg.on("request", lambda r: sends.append(json.loads(r.post_data or "{}")) if r.url.endswith("/api/rozela/apiSend") else None)
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.reload()
    pg.goto(base + "/cs#/b/rozela/failed")
    pg.wait_for_selector("a.row[data-id=w8ab77f1]")
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f1")
    pg.wait_for_selector("[data-test=wa-resend]")
    assert pg.inner_text(".tk-head [data-test=wa-fail-chip]") == "⚠️ השליחה נכשלה"
    pg.click("[data-test=wa-resend]")
    assert not sends                                                               # armed: the first click only arms
    pg.click("[data-test=wa-resend]")
    pg.wait_for_function("() => !location.hash.endsWith('/t/w8ab77f1')", timeout=5000)   # handed off, next ticket
    pg.wait_for_timeout(1500)
    assert len(sends) == 1
    s = sends[0]
    assert s["args"] == {"id": "w8ab77f1", "text": "היי נועה, החבילה יצאה אתמול ותגיע עד יום חמישי.", "channel": "whatsapp"}
    assert isinstance(s.get("rid"), str) and len(s["rid"]) >= 16
    pg.goto(base + "/cs#/b/rozela/t/w8ab77f1")
    pg.wait_for_selector("[data-test=wa-queued]", timeout=15000)                    # back in the WhatsApp queue
    assert pg.locator("[data-test=wa-resend]").count() == 0 and pg.locator(".tk-head [data-test=wa-fail-chip]").count() == 0
