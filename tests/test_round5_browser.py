"""QA round 5 in a real browser: WhatsApp double send, unknown statuses, stale list, slow opens, instant search."""
import json
import time

import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def test_whatsapp_queued_blocks_a_second_send(page):
    pg, base = page
    sends = []
    pg.on("request", lambda r: sends.append(1) if r.url.endswith("/api/rozela/apiSend") else None)
    pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
    pg.wait_for_selector(".draft textarea")
    pg.fill(".draft textarea", "היי, כן יש משלוח לאילת")
    pg.click("[data-test=send-btn]")
    pg.click("[data-test=send-btn]")
    pg.wait_for_timeout(500)
    pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")                                        # back to it after the hand-off
    pg.wait_for_selector("text=📤 נכנס לתור לוואטסאפ — אל תשלחו שוב", timeout=15000)
    assert pg.locator("[data-test=send-btn]").count() == 0 or pg.is_disabled("[data-test=send-btn]")
    assert len(sends) == 1
    pg.reload()
    pg.wait_for_selector("text=📤 נכנס לתור לוואטסאפ — אל תשלחו שוב", timeout=15000)      # survives a reload
    assert pg.locator("[data-test=send-btn]").count() == 0 or pg.is_disabled("[data-test=send-btn]")



def test_unconfirmed_whatsapp_send_locks_until_the_engine_answers(page):
    """(Its own WhatsApp ticket: the module shares one mock server, and another test queues w8ab77c1.)
    Unknown outcome: locked. Once the original can no longer be running (90 s) and a FRESH engine read shows the
    ticket still open and not queued, the send is offered again."""
    pg, base = page
    fresh_in = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 3600))

    def inside_window(route, req):       # this old test chat is made "the customer wrote an hour ago": this test is about the lock, not about the 24-hour window
        r = route.fetch()
        j = r.json()
        for t in (j.get("tickets") or []) + ([j["ticket"]] if isinstance(j.get("ticket"), dict) else []):
            if t.get("id") == "w8ab7700":
                t["wa_last_in"] = fresh_in
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/rozela/list", inside_window)
    pg.route("**/api/rozela/ticket", inside_window)
    stale = {"r" * 32: {"rid": "r" * 32, "brand": "rozela", "id": "w8ab7700", "fn": "apiSend", "args": {"id": "w8ab7700", "text": "x", "channel": "whatsapp"},
                        "channel": "whatsapp", "name": "לקוחה 00", "state": "unknown", "at": int(time.time() * 1000) - 5000}}
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(stale))
    pg.goto(base + "/cs#/b/rozela/t/w8ab7700")
    pg.reload()
    pg.wait_for_selector("[data-test=outbox-banner][data-state=unknown]")
    pg.fill(".draft textarea", "היי")
    assert pg.is_disabled("[data-test=send-btn]")                                     # 5 s old: the original may still run
    stale["r" * 32]["at"] = int(time.time() * 1000) - 120000                           # two minutes old
    pg.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(stale))
    pg.reload()
    pg.wait_for_selector("[data-test=outbox-banner][data-state=unsent]", timeout=15000)  # a fresh engine read decided
    pg.fill(".draft textarea", "היי!")
    assert not pg.is_disabled("[data-test=send-btn]")



def test_unknown_status_is_never_shown_raw(page):
    pg, base = page

    def odd(route, req):
        resp = route.fetch()
        j = resp.json()
        if j.get("ticket"):
            j["ticket"]["status"] = "brand_new_status"
            j["ticket"]["category"] = "brand_new_cat"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(j))
    pg.route("**/api/rozela/ticket", odd)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector(".draft")                                                # the FULL ticket (the partial view has a header too)
    txt = pg.inner_text("#ticket-pane")
    assert "brand_new_status" not in txt and "st_brand" not in txt and "סטטוס אחר" in txt


def test_stale_list_banner_and_manual_refresh(page):
    pg, base = page
    lists = []
    pg.on("request", lambda r: lists.append(r.post_data or "") if r.url.endswith("/api/rozela/list") else None)
    pg.route("**/api/rozela/changes", lambda route, req: route.fulfill(status=200, content_type="application/json",
             body=json.dumps({"ok": False, "error": "busy", "syncedAge": 1620})))
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("a.row")
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_selector("[data-test=list-stale]", timeout=5000)
    assert "27 דקות" in pg.inner_text("[data-test=list-stale]")
    n = len(lists)
    pg.click("[data-test=list-stale] .btn")
    pg.wait_for_timeout(1000)
    assert any('"maxAge": 0' in d or '"maxAge":0' in d for d in lists[n:])
    pg.wait_for_selector("[data-test=list-stale]", state="detached", timeout=5000)


def test_slow_open_shows_the_row_then_the_ticket(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("a.row")
    tries = []

    def slow(route, req):
        tries.append(1)
        if len(tries) <= 1:
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": False, "error": "engine_slow", "pending": True}))
        else:
            route.continue_()
    pg.route("**/api/rozela/ticket", slow)
    pg.click("a.row[data-id=t18f2a02]")
    pg.wait_for_selector("[data-test=tk-partial]")
    assert "המנוע איטי כרגע" in pg.inner_text("#ticket-pane") and "רונית" in pg.inner_text("#ticket-pane")
    pg.wait_for_selector(".draft textarea", timeout=15000)                       # the retry got the full ticket
    assert "תשובה לא תקינה" not in pg.inner_text("body")


def test_search_answers_from_the_list_before_the_engine(page):
    pg, base = page
    hits = []

    def slow_engine(route, req):                       # never sleep in a sync handler: it freezes Playwright itself
        hits.append(1)
        route.abort() if len(hits) <= 2 else route.continue_()    # the client's read retries take ~3 s
    pg.route("**/api/rozela/apiSearch", slow_engine)
    pg.goto(base + "/cs#/b/rozela/search")
    pg.wait_for_selector(".tab.ready .n")                                          # the list (the local index) is loaded
    pg.wait_for_selector(".search-box input")
    t0 = time.time()
    pg.fill(".search-box input", "michal")
    pg.wait_for_selector(".results .row", timeout=2000)                             # local rows, before the engine answered
    assert time.time() - t0 < 2.0 and "מחפש גם בארכיון" in pg.inner_text(".results")
    pg.wait_for_selector("[data-test=search-note]", state="detached", timeout=10000)   # engine results merged
    assert pg.locator(".results .row").count() >= 2                               # live + archived ticket of the same customer



def test_older_engine_pending_whatsapp_send_also_blocks(page):
    """An engine that only marks wa_send:'pending' (status still open) must block the second send as well."""
    pg, base = page

    def pending(route, req):
        resp = route.fetch()
        j = resp.json()
        if j.get("ticket"):
            j["ticket"].update({"status": "action", "wa_send": "pending", "handled_by": "agent1"})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(j))
    pg.route("**/api/rozela/ticket", pending)
    pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")
    pg.wait_for_selector(".draft textarea")
    pg.fill(".draft textarea", "עוד הודעה")
    assert pg.locator("[data-test=wa-queued] >> text=📤 נכנס לתור לוואטסאפ").count() == 1
    assert pg.is_disabled("[data-test=send-btn]")
