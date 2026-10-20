"""the owner's CS team, 2026-10-16: "כפתור במערכת שמאשר שבאמת יבוטל המנוי" — the "לבטל את המנוי" button in the send area (mock engine, real
browser). One click + one confirm step that names the customer and the product, no typed digits; several subscriptions = the agent picks;
the verdict ("✅ ... אומת בקאצ'ינג HH:MM" or a red failure) stays on the ticket after a reload; no Kaching = disabled with the reason."""
import json
import re

import pytest

from browser_server import start
from pw_launch import launch, pw

YOSSI = "/cs#/b/rozela/t/t18f2a03"          # cancel_subscription, one ACTIVE subscription (…0123) + one CANCELLED
RONIT = "/cs#/b/rozela/t/t18f2a02"          # a product question: no cancel request
CID = "gid://shopify/SubscriptionContract/9876543210123"


@pytest.fixture()
def srv():
    base, pwd, proc = start(users=(("agent1", ["agent"], ["rozela"], "he"), ("agent-en", ["agent"], ["rozela"], "en")))
    yield base, pwd
    proc.terminate()


def _login(p, base, pwd, user="agent1", width=390, routes=()):
    browser = launch(p)
    pg = browser.new_page(viewport={"width": width, "height": 900})
    for pattern, handler in routes:               # before the first page load: the app keeps its first answers across hash navigation
        pg.route(pattern, handler)
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def test_one_click_cancel_is_verified_and_stays_on_the_ticket(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + YOSSI)
        btn = pg.locator("[data-test=draft-card] [data-test=subx-btn]")      # inside the send area
        btn.wait_for()
        assert btn.inner_text() == "לבטל את המנוי" and btn.is_enabled()
        btn.click()
        q = pg.locator("[data-test=subx-q]")
        q.wait_for()
        dlg = pg.locator("#subx-dlg")
        assert "יוסי מזרחי" in q.inner_text()                                # names the customer
        assert "רוזלה סלק" in dlg.inner_text()                                # names the product of the subscription
        assert "0123" in dlg.inner_text()                                     # and which subscription it will cancel
        assert dlg.locator("input.code, input[inputmode=numeric]").count() == 0, "no typed digits"
        pg.click("[data-test=subx-go]")
        ok = pg.locator("[data-test=subx-ok]")
        ok.wait_for()
        assert re.search(r"המנוי בוטל — אומת בקאצ'ינג \d{1,2}:\d{2}", ok.inner_text()), ok.inner_text()
        assert pg.locator("[data-test=subx-btn]").count() == 0                # done: no second cancel from here
        assert not dlg.is_visible()
        pg.reload()                                                           # every device: the verdict is on the ticket, not in this page
        pg.locator("[data-test=subx-ok]").wait_for()
        assert "אומת בקאצ'ינג" in pg.inner_text("[data-test=subx-ok]")
        pg.goto(base + "/cs#/b/rozela")                                       # the list row carries the chip
        row = pg.locator("#list-pane > a.row", has_text="יוסי מזרחי").first
        row.wait_for()
        row.locator(".chip", has_text="בוטל דרך המערכת").wait_for(timeout=15000)
        assert not errors, errors
        browser.close()


def test_several_subscriptions_the_agent_picks_never_a_guess(srv):
    base, pwd = srv
    other = {"id": "gid://shopify/SubscriptionContract/1112223334449", "status": "PAUSED", "every": "2 month", "items": [{"title": "מוצר אחר", "quantity": 2}]}
    sent = []

    def two(route):
        r = route.fetch()
        j = r.json()
        if j.get("ok"):
            j["contracts"] = j["contracts"] + [other]
        route.fulfill(response=r, body=json.dumps(j))

    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.route("**/api/rozela/apiSubCancelPreview", two)
        pg.on("request", lambda r: sent.append(json.loads(r.post_data or "{}")) if r.url.endswith("/apiSubCancel") else None)
        pg.goto(base + YOSSI)
        pg.click("[data-test=subx-btn]")
        pg.locator("[data-test=subx-opt]").nth(1).wait_for()
        assert "2 מנויים פעילים" in pg.inner_text("[data-test=subx-q]")
        assert pg.locator("[data-test=subx-opt]").count() == 2
        assert pg.is_disabled("[data-test=subx-go]"), "nothing is preselected"
        pg.locator("[data-test=subx-opt]", has_text="0123").click()
        assert pg.is_enabled("[data-test=subx-go]")
        pg.click("[data-test=subx-go]")
        pg.locator("[data-test=subx-ok]").wait_for()
        assert [s["args"]["contractId"] for s in sent] == [CID]
        assert not errors, errors
        browser.close()


def test_a_failure_is_red_with_the_reason_and_stays(srv):
    base, pwd = srv
    rec = {"state": "failed", "contractId": CID, "status": "ACTIVE", "items": [], "at": "2026-10-16T09:00:00Z", "by": "agent1",
           "reason": "cancellations are frozen: test"}

    def refuse(route):
        route.fulfill(content_type="application/json", body=json.dumps({
            "ok": False, "verified": False, "error": "not_cancelled", "state": "failed", "status": "ACTIVE", "contractId": CID,
            "message": "cancellations are frozen: test", "msg": "ביטולי מנויים מוקפאים (test).", "record": rec}))

    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.route("**/api/rozela/apiSubCancel", refuse)
        pg.goto(base + YOSSI)
        pg.click("[data-test=subx-btn]")
        pg.click("[data-test=subx-go]")
        fail = pg.locator("#subx-dlg [data-test=subx-fail]")
        fail.wait_for()
        txt = fail.inner_text()
        assert "המנוי לא בוטל" in txt and "מוקפאים" in txt and "לבטל ידנית ב-Kaching" in txt
        assert pg.locator("[data-test=subx-go]").is_hidden()
        assert pg.locator("[data-test=subx-ok]").count() == 0, "never shown as cancelled"
        pg.keyboard.press("Escape")
        pg.locator("#tk-subcancel [data-test=subx-fail]").wait_for()        # the ticket itself shows it after the dialog closes
        assert pg.locator("#tk-subcancel [data-test=subx-btn]").is_enabled()  # and the agent can try again
        assert not errors, errors
        browser.close()


def test_hidden_without_a_cancel_request_until_the_reply_says_cancelled(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + RONIT)
        pg.wait_for_selector("[data-test=send-btn]")
        pg.wait_for_timeout(500)
        assert pg.locator("[data-test=subx-btn]").count() == 0
        pg.locator("[data-test=draft-card] textarea").fill("היי רונית, ביטלתי לך את המנוי.")
        pg.locator("[data-test=subx-btn]").wait_for()
        assert not errors, errors
        browser.close()


def test_no_kaching_token_disabled_with_one_line_reason(srv):
    base, pwd = srv

    def no_token(route):
        r = route.fetch()
        j = r.json()
        j["kachingReady"] = False
        route.fulfill(response=r, body=json.dumps(j))

    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, routes=(("**/api/rozela/list", no_token),))   # apiBoot comes through the server's cache (/list)
        pg.goto(base + YOSSI)
        pg.locator("[data-test=subx-btn]").wait_for()
        assert pg.is_disabled("[data-test=subx-btn]")
        assert "אין חיבור לקאצ'ינג" in pg.inner_text("[data-test=subx-why]")
        assert not errors, errors
        browser.close()


def test_english_desk_has_the_same_button(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, user="agent-en", width=1280)
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
        btn = pg.locator("[data-test=subx-btn]")
        btn.wait_for()
        assert btn.inner_text() == "Cancel the subscription"
        btn.click()
        pg.locator("[data-test=subx-q]").wait_for()
        assert "Cancel" in pg.inner_text("[data-test=subx-q]") and "יוסי מזרחי" in pg.inner_text("[data-test=subx-q]")
        pg.click("[data-test=subx-go]")
        pg.locator("[data-test=subx-ok]").wait_for()
        assert "verified in Kaching" in pg.inner_text("[data-test=subx-ok]")
        assert not errors, errors
        browser.close()


# the owner's CS team, 2026-10-20 (order #12057): the subscription WAS cancelled and the dialog said "nothing to cancel", so the agent believed it
# was not done. Already cancelled = a green, verified line naming the subscription; no cancel button.
def test_already_cancelled_says_so_verified_never_nothing_to_cancel(srv):
    base, pwd = srv

    def only_ended(route):
        r = route.fetch()
        j = r.json()
        if j.get("ok"):
            j["ended"] = [dict(c, status="CANCELLED") for c in j["contracts"]] + j.get("ended", [])
            j["contracts"] = []
        route.fulfill(response=r, body=json.dumps(j))

    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.route("**/api/rozela/apiSubCancelPreview", only_ended)
        pg.goto(base + YOSSI)
        pg.click("[data-test=subx-btn]")
        ok = pg.locator("#subx-dlg [data-test=subx-ended]")
        ok.wait_for()
        assert "כבר מבוטל בקאצ'ינג" in ok.inner_text() and "יוסי מזרחי" in ok.inner_text()
        dlg = pg.inner_text("#subx-dlg")
        assert "0123" in dlg and "אין מה לבטל שוב" in dlg
        assert "אין מנוי פעיל" not in dlg
        assert pg.locator("[data-test=subx-go]").count() == 0
        assert not errors, errors
        browser.close()


# the owner's CS team, 2026-10-20: only a WhatsApp phone that is not the order's. The agent asks for the order number and links it in the dialog;
# the dialog then finds the subscription, and the orders panel shows the link for every agent.
def test_unidentified_customer_link_the_order_number_then_cancel(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
        pg.locator("[data-test=lk-open] [data-test=lk-in]").wait_for()           # the orders panel offers the link at once
        assert "מספר ההזמנה" in pg.inner_text("[data-test=lk-open]")
        pg.locator("[data-test=draft-card] textarea").fill("היי עומר, ביטלתי לך את המנוי.")
        pg.click("[data-test=subx-btn]")
        pg.locator("#subx-dlg [data-test=subx-noemail]").wait_for()
        assert "מספר ההזמנה או את המייל" in pg.inner_text("#subx-dlg [data-test=subx-noemail]")
        pg.fill("#subx-dlg [data-test=lk-in]", "#9999")
        pg.click("#subx-dlg [data-test=lk-go]")
        pg.locator("#subx-dlg [data-test=lk-err]").wait_for()                   # none = refused with the reason, never a guess
        assert "לא נמצאו הזמנה או מנוי" in pg.inner_text("#subx-dlg [data-test=lk-err]")
        pg.fill("#subx-dlg [data-test=lk-in]", "#4530")
        pg.keyboard.press("Enter")
        pg.locator("#subx-dlg [data-test=subx-q]").wait_for()
        assert "0123" in pg.inner_text("#subx-dlg")
        assert "yossi.m@example.com" in pg.inner_text("#subx-dlg")
        pg.click("[data-test=subx-go]")
        pg.locator("[data-test=subx-ok]").wait_for()
        box = pg.locator("#orders-card [data-test=lk-box]")
        box.wait_for()
        assert "yossi.m@example.com" in box.inner_text() and "#4530" in box.inner_text()
        pg.reload()
        pg.locator("#orders-card [data-test=lk-box]").wait_for()                 # kept on the ticket
        pg.click("[data-test=lk-unlink]")
        pg.locator("#orders-card [data-test=lk-open]").wait_for()
        assert not errors, errors
        browser.close()
