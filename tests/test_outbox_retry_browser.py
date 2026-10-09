"""Owner, 2026-10-09: a reply an agent sent is ALWAYS sent. A refusal whose cause passes (the engine's lock, a full gate, a
server error) is sent again by the page itself, 5 s later, with the SAME rid. A refusal about the ticket is not."""
import json
import time

import pytest

import browser_server
from pw_launch import launch, pw


@pytest.fixture
def server():                 # a fresh mock engine for every test: each one sends a ticket for real
    base, pwd, proc = browser_server.start({}, users=(("agent1", ["agent"], ["rozela"], "he"),))
    yield base, pwd
    proc.terminate()


@pytest.fixture
def pg(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b = launch(p)
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto(base + "/cs/login")
        page.fill("input[name=username]", "agent1")
        page.fill("input[name=password]", pwd)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.evaluate("localStorage.removeItem('cs.outbox')")
        yield page, base
        b.close()


def state_of(page, key, value):
    return page.evaluate("([k, v]) => (Object.values(JSON.parse(localStorage.getItem('cs.outbox') || '{}')).filter(i => i[k] === v)[0] || {}).state || null", [key, value])


def wait_state(page, key, value, ok, secs=15):
    for _ in range(secs * 10):
        st = state_of(page, key, value)
        if ok(st):
            return st
        page.wait_for_timeout(100)
    raise AssertionError("outbox state stayed %r" % st)


def open_from(page, base, tab, tid):
    page.goto(base + "/cs#/b/rozela/" + tab)
    page.wait_for_selector("a.row[data-id=%s]" % tid)
    page.click("a.row[data-id=%s]" % tid)
    page.wait_for_selector(".draft textarea")


def refuse_first(page, code, times, http=200):
    """The first `times` sends are answered with `code`; later ones reach the real (mock) engine. Returns the bodies seen."""
    seen = []

    def handler(route, req):
        body = json.loads(req.post_data)
        body["_at"] = time.time()
        seen.append(body)
        if len(seen) <= times:
            route.fulfill(status=http, content_type="application/json",
                          body=json.dumps({"ok": False, "error": code, "msg": "המערכת באמצע פעולה אחרת.", "rid": body["rid"]}))
        else:
            route.continue_()
    page.route("**/api/rozela/apiSend", handler)
    return seen


@pytest.mark.parametrize("code,http,tid", [("busy", 200, "t18f2a01"), ("server_error", 200, "t18f2a02"), ("busy", 503, "t18f2a04")])
def test_a_passing_refusal_is_sent_again_by_itself(pg, code, http, tid):
    page, base = pg
    seen = refuse_first(page, code, 1, http)
    open_from(page, base, "action" if tid == "t18f2a04" else "ready", tid)
    page.fill(".draft textarea", "היי, ההזמנה בדרך אליך.")
    page.click("[data-test=send-btn]")
    page.click("[data-test=send-btn]")
    row = "a.row[data-id=%s] [data-test=row-outbox]" % tid
    page.wait_for_selector(row + "[data-state=retry]", state="attached", timeout=8000)
    assert "מנסה לשלוח שוב" in page.locator(row).first.inner_text()
    assert page.locator("[data-test=outbox-indicator].warn").count() == 0          # not an alarm: nothing for the agent to do
    for _ in range(200):                                                            # the second try, about 5 s later
        if len(seen) >= 2:
            break
        page.wait_for_timeout(100)
    assert len(seen) == 2 and 4.0 < seen[1]["_at"] - seen[0]["_at"] < 9.0, seen                # 5 s later, as the owner asked
    assert seen[1]["rid"] == seen[0]["rid"] and seen[1]["args"] == seen[0]["args"]      # the SAME call: the engine never runs it twice
    assert "attempt" not in seen[0] and seen[1]["attempt"] == 2
    wait_state(page, "id", tid, lambda st: st == "ok")
    assert len(seen) == 2                                                           # sent once, and no third call
    page.unroute("**/api/rozela/apiSend")


def test_a_refusal_about_the_ticket_is_not_retried(pg):
    page, base = pg
    seen = refuse_first(page, "wa_window_closed", 99)
    open_from(page, base, "ready", "t18f2c02")
    page.fill(".draft textarea", "היי אילנה, כן אפשר.")
    page.click("[data-test=send-btn]")
    page.click("[data-test=send-btn]")
    page.wait_for_selector("[data-test=row-outbox][data-state=refused]", state="attached", timeout=8000)
    page.wait_for_timeout(7000)
    assert len(seen) == 1
    page.unroute("**/api/rozela/apiSend")


def seed(page, tid, **over):
    it = {"rid": "a" * 32, "brand": "rozela", "id": tid, "fn": "apiSend", "args": {"id": tid, "text": "היי, ההזמנה בדרך."}, "channel": "email",
          "name": "לקוח", "state": "retry", "at": int(time.time() * 1000) - 60000, "via": None, "tries": 1, "next": 0}
    it.update(over)
    page.evaluate("it => localStorage.setItem('cs.outbox', JSON.stringify({[it.rid]: it}))", it)


def test_a_retry_survives_a_closed_page(pg):
    page, base = pg
    seen = refuse_first(page, "busy", 0)
    seed(page, "t18f2a01")
    page.goto(base + "/cs#/b/rozela/ready")
    page.reload()
    assert wait_state(page, "rid", "a" * 32, lambda st: st not in ("retry", "flight")) == "ok"
    assert len(seen) == 1 and seen[0]["rid"] == "a" * 32 and seen[0]["attempt"] == 2
    page.unroute("**/api/rozela/apiSend")


def test_after_the_last_try_the_agent_is_told(pg):
    page, base = pg
    seen = refuse_first(page, "busy", 99)
    seed(page, "t18f2a02", tries=10)
    page.goto(base + "/cs#/b/rozela/ready")
    page.reload()
    page.wait_for_selector("a.row[data-id=t18f2a02] [data-test=row-outbox][data-state=refused]", state="attached", timeout=15000)
    assert len(seen) == 1
    assert page.locator("#list-pane > a.row").first.get_attribute("data-id") == "t18f2a02"      # flagged, on top
    page.unroute("**/api/rozela/apiSend")



@pytest.mark.parametrize("state", ["retry", "unknown"])
def test_no_automatic_send_after_the_engine_forgot_the_rid(pg, state):
    """The engine keeps a successful rid for 30 min. An item older than 20 min is never sent by the page: a person decides."""
    page, base = pg
    seen = refuse_first(page, "busy", 0)
    seed(page, "t18f2a01", state=state, at=int(time.time() * 1000) - 25 * 60000)
    page.goto(base + "/cs#/b/rozela/ready")
    page.reload()
    assert wait_state(page, "rid", "a" * 32, lambda st: st in ("refused", "unsent")) in ("refused", "unsent")
    page.wait_for_timeout(7000)
    assert seen == []                                                               # nothing went to the customer
    page.unroute("**/api/rozela/apiSend")


def test_a_ticket_already_answered_from_gmail_is_closed_not_flagged(pg):
    """Owner, 2026-10-09 (option A): no second reply, no "needs fixing": the agent is told, and the ticket leaves the queue."""
    page, base = pg
    page.route("**/api/rozela/apiSend", lambda route, req: route.fulfill(status=200, content_type="application/json", body=json.dumps(
        {"ok": False, "error": "replied_elsewhere", "closed": True, "msg": "הלקוח כבר קיבל תשובה ישירות מ-Gmail", "rid": json.loads(req.post_data)["rid"]})))
    open_from(page, base, "ready", "t18f2a01")
    page.fill(".draft textarea", "היי, ההזמנה בדרך אליך.")
    page.click("[data-test=send-btn]")
    page.click("[data-test=send-btn]")
    assert wait_state(page, "id", "t18f2a01", lambda st: st in ("ok", "refused")) == "ok"
    assert page.locator("[data-test=outbox-indicator].warn").count() == 0                 # nothing to fix
    item = page.evaluate("Object.values(JSON.parse(localStorage.getItem('cs.outbox')))[0]")
    assert item["reply"] == {"elsewhere": True}
    page.goto(base + "/cs#/b/rozela/t/t18f2a01")
    page.wait_for_selector("[data-test=outbox-banner][data-state=ok]")
    assert "כבר נענה מ-Gmail" in page.inner_text("[data-test=outbox-banner]")
    page.unroute("**/api/rozela/apiSend")
