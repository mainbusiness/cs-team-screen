"""Background sends (Owner, 2026-10-05): an agent never waits for the engine. Real browser, slow mock engine."""
import json
import time

import pytest

import browser_server
from pw_launch import launch, pw

SLOW = {"MOCK_SLOW_FNS": "apiSend:8000,apiClose:6000"}


@pytest.fixture(scope="module")
def slow_server():
    base, pwd, proc = browser_server.start(SLOW, users=(("agent1", ["agent"], ["rozela"], "he"),))
    yield base, pwd
    proc.terminate()


@pytest.fixture
def pg(slow_server):
    base, pwd = slow_server
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
        page.sends = []
        ctx.on("request", lambda r: page.sends.append(r.url.rsplit("/", 1)[-1]) if "/api/rozela/api" in r.url and r.method == "POST" else None)
        yield page, base
        b.close()


def open_from(page, base, tab, tid):
    page.goto(base + "/cs#/b/rozela/" + tab)
    page.wait_for_selector("a.row[data-id=%s]" % tid)
    page.click("a.row[data-id=%s]" % tid)
    page.wait_for_selector(".draft textarea")


def armed_click(page, sel):
    page.click(sel)
    page.click(sel)


def test_send_hands_off_and_the_agent_moves_on(pg):
    page, base = pg
    open_from(page, base, "ready", "t18f2a01")
    page.fill(".draft textarea", "היי מיכל, ההזמנה בדרך.")
    t0 = time.time()
    armed_click(page, "[data-test=send-btn]")
    for _ in range(40):
        if not page.url.endswith("/t18f2a01"):
            break
        page.wait_for_timeout(25)
    moved = time.time() - t0
    assert moved < 1.0 and not page.url.endswith("/t18f2a01"), moved          # on the next ticket within 1 s
    page.wait_for_selector("[data-test=outbox-indicator]")
    assert "(1)" in page.inner_text("[data-test=outbox-indicator]")
    row = page.locator("a.row[data-id=t18f2a01] [data-test=row-outbox]")
    assert row.get_attribute("data-state") == "flight" and "נשלח ברקע" in row.inner_text()
    page.wait_for_selector("[data-test=outbox-indicator]", state="detached", timeout=20000)   # nothing left in progress
    page.goto(base + "/cs#/b/rozela/sent")                                           # sent: it moved to "waiting for customer"
    page.wait_for_selector("a.row[data-id=t18f2a01] [data-test=row-outbox][data-state=ok]")
    assert "נשלח" in page.inner_text("a.row[data-id=t18f2a01] [data-test=row-outbox]")
    assert page.sends.count("apiSend") == 1


def test_refusal_is_flagged_on_top_and_the_text_is_kept(pg):
    page, base = pg
    page.route("**/api/rozela/apiSend", lambda route, req: route.fulfill(status=200, content_type="application/json",
               body=json.dumps({"ok": False, "error": "thread_missing", "rid": json.loads(req.post_data)["rid"]})))
    open_from(page, base, "ready", "t18f2a02")
    text = "היי רונית, ההזמנה בדרך"
    page.fill(".draft textarea", text)
    armed_click(page, "[data-test=send-btn]")
    page.wait_for_selector("[data-test=row-outbox][data-state=refused]", state="attached", timeout=20000)
    page.goto(base + "/cs#/b/rozela/ready")
    page.wait_for_selector("a.row")
    assert page.locator("#list-pane > a.row").first.get_attribute("data-id") == "t18f2a02"      # needs a fix: top
    page.click("a.row[data-id=t18f2a02]")
    page.wait_for_selector("[data-test=outbox-banner][data-state=refused]")
    assert "לא נשלח — צריך תיקון" in page.inner_text("[data-test=outbox-banner]")
    assert page.input_value(".draft textarea") == text                                      # nothing lost
    page.unroute("**/api/rozela/apiSend")


def test_unknown_outcome_locks_the_ticket(pg):
    page, base = pg
    page.route("**/api/rozela/apiSend", lambda route, req: route.fulfill(status=502, content_type="application/json",
               body=json.dumps({"ok": False, "error": "write_unknown", "refresh": True, "msg": "לא הצלחנו לאשר אם הפעולה בוצעה — רעננו את הפנייה ובדקו."})))
    open_from(page, base, "action", "t18f2a04")
    page.fill(".draft textarea", "היי דנה, ההחזר בדרך.")
    armed_click(page, "[data-test=send-btn]")
    page.wait_for_selector("[data-test=row-outbox][data-state=unknown]", state="attached", timeout=10000)
    page.goto(base + "/cs#/b/rozela/t/t18f2a04")
    page.wait_for_selector("[data-test=outbox-banner][data-state=unknown]")
    page.fill(".draft textarea", "עוד ניסיון")
    assert page.is_disabled("[data-test=send-btn]")                                          # locked until the engine tells


def test_reload_mid_send_recovers_without_resending(pg):
    page, base = pg
    open_from(page, base, "ready", "t18f2c02")
    page.fill(".draft textarea", "היי אילנה, כן אפשר עם קפה.")
    armed_click(page, "[data-test=send-btn]")
    page.wait_for_timeout(1000)
    page.reload()                                                                            # the tab dies mid-send
    page.wait_for_selector("[data-test=outbox-indicator]")
    assert "בודק" in page.inner_text("[data-test=outbox-indicator]") or page.locator("[data-test=outbox-indicator]").count()
    page.wait_for_selector("[data-test=outbox-indicator]", state="detached", timeout=30000)  # /result found it
    page.goto(base + "/cs#/b/rozela/sent")
    page.wait_for_selector("a.row[data-id=t18f2c02] [data-test=row-outbox][data-state=ok]")
    assert page.sends.count("apiSend") == 1                                                  # asked, never resent


def test_whatsapp_send_cannot_be_sent_twice(pg):
    page, base = pg
    open_from(page, base, "action", "w8ab77c1")
    page.fill(".draft textarea", "היי עומר, כן יש משלוח לאילת")
    armed_click(page, "[data-test=send-btn]")
    page.wait_for_timeout(300)
    page.goto(base + "/cs#/b/rozela/t/w8ab77c1")                                             # straight back to it
    page.wait_for_selector("[data-test=outbox-banner]")
    page.fill(".draft textarea", "שוב")
    assert page.is_disabled("[data-test=send-btn]")
    page.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=20000)
    assert page.sends.count("apiSend") == 1


def test_close_is_optimistic_and_reverts_with_a_flag(pg):
    page, base = pg
    open_from(page, base, "action", "t18f2a11")
    t0 = time.time()
    armed_click(page, ".draft .btn.ghost:has-text('סגירה')")
    for _ in range(40):
        if not page.url.endswith("/t18f2a11"):
            break
        page.wait_for_timeout(25)
    assert time.time() - t0 < 1.0
    page.goto(base + "/cs#/b/rozela/action")
    page.wait_for_selector("a.row")
    assert page.locator("a.row[data-id=t18f2a11]").count() == 0                              # off the list at once
    page.wait_for_selector("[data-test=outbox-indicator]", state="detached", timeout=20000)
    # a refused close comes back, flagged
    page.route("**/api/rozela/apiClose", lambda route, req: route.fulfill(status=200, content_type="application/json",
               body=json.dumps({"ok": False, "error": "not_found", "msg": "הפנייה לא נמצאה."})))   # a refusal about the ticket; a passing one ("busy") is retried: test_outbox_retry_browser
    open_from(page, base, "action", "t18f2a04")
    armed_click(page, ".draft .btn.ghost:has-text('סגירה')")
    page.goto(base + "/cs#/b/rozela/action")
    page.wait_for_selector("a.row[data-id=t18f2a04] [data-test=row-outbox][data-state=refused]", timeout=10000)
    assert page.locator("#list-pane > a.row").first.get_attribute("data-id") == "t18f2a04"



def test_a_killed_tab_never_resends(pg):
    """A tab that is CLOSED mid-send leaves the item 'in flight'. The next page load asks /result — it never resends."""
    page, base = pg
    rid = "k" * 32
    csrf = page.locator("meta[name=csrf]").get_attribute("content")
    r = page.request.post(base + "/api/rozela/apiSend", headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
                          data=json.dumps({"args": {"id": "t18f2a02", "text": "היי רונית, 2 כמוסות ביום."}, "rid": rid}), timeout=30000)
    assert r.json()["ok"]                                                    # the server finished it (the tab is "gone")
    item = {rid: {"rid": rid, "brand": "rozela", "id": "t18f2a02", "fn": "apiSend", "args": {"id": "t18f2a02", "text": "x"},
                  "channel": "email", "name": "רונית", "state": "flight", "at": int(time.time() * 1000) - 3000}}
    page.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(item))
    n = page.sends.count("apiSend")
    page.goto(base + "/cs#/b/rozela/ready")
    page.reload()
    page.wait_for_selector("[data-test=outbox-indicator]", state="detached", timeout=20000)      # resolved via /result
    assert page.sends.count("apiSend") == n                                  # NOT sent again



def test_a_flagged_draft_goes_out_with_no_safety_note_and_no_override(pg):
    """Owner, 2026-10-06: a person's send is never blocked by a content check. No "בדיקת בטיחות" note after saving, no
    "send anyway" box: the normal Send sends it, without any override flag."""
    page, base = pg
    bodies = []
    page.on("request", lambda r: bodies.append(json.loads(r.post_data or "{}")) if r.url.endswith("/api/rozela/apiSend") else None)
    open_from(page, base, "action", "t18f2a03")
    text = "היי יוסי, זה עובד 100% מובטח"                                                    # the mock's audit flags this
    page.fill(".draft textarea", text)
    page.evaluate("document.activeElement.blur()")                                         # save now
    page.wait_for_selector("text=נשמר ✓", timeout=10000)
    page.wait_for_timeout(500)
    assert page.locator("text=בדיקת בטיחות").count() == 0 and page.locator("text=בדיקת הבטיחות").count() == 0
    armed_click(page, "[data-test=send-btn]")
    page.wait_for_selector("[data-test=outbox-indicator]", state="detached", timeout=20000)    # settled
    page.goto(base + "/cs#/b/rozela/sent")                                                  # it went out
    page.wait_for_selector("a.row[data-id=t18f2a03] [data-test=row-outbox][data-state=ok]", timeout=20000)
    assert len(bodies) == 1 and "override" not in bodies[0]["args"] and bodies[0]["args"]["text"] == text
    assert page.locator("text=לשלוח בכל זאת").count() == 0


def seed_outbox(page, base, entries):
    now = int(time.time() * 1000)
    items = {}
    for n, entry in enumerate(entries):
        rid = ('%032d' % n)
        items[rid] = dict(rid=rid, brand='rozela', id='t18f2a02', fn='apiSend', args={},
                          channel='email', name='רונית', at=now - 30000 + n * 1000, **entry)
    page.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(items))
    page.goto(base + '/cs#/b/rozela/ready')
    page.reload()
    page.wait_for_load_state('networkidle')
    page.wait_for_selector('#list-pane')
    return items


def test_old_refusals_do_not_survive_a_later_success(pg):
    page, base = pg
    seed_outbox(page, base, [dict(state='refused'), dict(state='refused'), dict(state='ok')])
    assert page.locator('[data-test=outbox-indicator]').count() == 0
    assert len(json.loads(page.evaluate("localStorage.getItem('cs.outbox')"))) == 3
    assert not page.sends


def test_later_refusal_is_not_hidden_by_older_success(pg):
    page, base = pg
    seed_outbox(page, base, [dict(state='ok'), dict(state='refused')])
    assert '(1)' in page.inner_text('[data-test=outbox-indicator]')
    assert not page.sends


def test_result_known_refusal_leaves_checking_without_resending(pg):
    page, base = pg
    page.route('**/api/rozela/result', lambda route: route.fulfill(content_type='application/json',
        body=json.dumps(dict(ok=True, found=True, reply=dict(ok=False, error='thread_missing', msg='השרשור לא נמצא')))))
    seed_outbox(page, base, [dict(state='checking')])
    for _ in range(50):
        state = list(json.loads(page.evaluate("localStorage.getItem('cs.outbox')")).values())[0]['state']
        if state == 'refused':
            break
        page.wait_for_timeout(100)
    assert state == 'refused'
    assert not page.sends


@pytest.mark.parametrize('offset, status, expected', [(3000, 'sent', 0), (-60000, 'sent', 1), (3000, 'done', 1)])
def test_boot_reconciles_refusal_only_after_later_engine_success(pg, offset, status, expected):
    from datetime import datetime, timezone
    page, base = pg
    calls = []
    handled_at = datetime.fromtimestamp((int(time.time() * 1000) + offset) / 1000, timezone.utc).isoformat()
    def ticket(route, req):
        calls.append(json.loads(req.post_data))
        route.fulfill(content_type='application/json', body=json.dumps(dict(ok=True,
            ticket=dict(id='t18f2a02', status=status, handled_by='agent1', handled_at=handled_at))))
    page.route('**/api/rozela/ticket', ticket)
    seed_outbox(page, base, [dict(state='refused')])
    page.wait_for_timeout(2500)
    assert page.locator('[data-test=outbox-indicator]').count() == expected
    stored = json.loads(page.evaluate("localStorage.getItem('cs.outbox')"))
    assert len(stored) == 1 and list(stored.values())[0]['state'] == 'refused'
    assert calls and all(x.get('revalidate') and not x.get('fresh') for x in calls)
    assert not page.sends
