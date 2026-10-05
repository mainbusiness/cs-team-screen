"""P0 speed in a real browser (Owner, 2026-10-05): the open chat updates in place every ~5 s without touching the agent's
draft, a confirmed copy opens with ONE request, the open ticket asks for the reserved slot, the next tickets are warmed."""
import json

import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")

NEW_MSG = "שלום, ההזמנה עדיין לא הגיעה ואני צריכה אותה עד שישי"
NEW_DRAFT = "היי מיכל, בדקנו — החבילה יוצאת מחר ותגיע עד חמישי."


def current(pg, base, tid):
    return pg.evaluate("""async ([tid]) => {
      const tok = document.querySelector('meta[name=csrf]').content;
      const r = await fetch('/api/rozela/ticket', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': tok},
                                                   body: JSON.stringify({id: tid})});
      return r.json(); }""", [tid])


def push_new_message(pg, base, tid):
    """The next /watch answers: a newer copy with one new customer message and a new engine draft."""
    j = current(pg, base, tid)
    conv = list((j.get("extras") or {}).get("conversation") or [])
    conv.append({"who": "customer", "at": "2026-10-05T12:00:00Z", "text": NEW_MSG})
    body = dict(j, changed=True, ticket=dict(j["ticket"], draft_text=NEW_DRAFT), extras=dict(j.get("extras") or {}, conversation=conv),
                cache=dict(j.get("cache") or {}, at=9e9, confirmed=True), syncedAge=0)
    served = []

    def handler(route, req):
        if json.loads(req.post_data or "{}").get("id") == tid and not served:
            served.append(1)
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        return route.continue_()
    pg.route("**/api/rozela/watch", handler)
    return served


def test_new_message_while_typing_never_touches_the_draft(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector(".draft textarea")
    pg.wait_for_timeout(300)
    pg.click(".draft textarea")
    pg.keyboard.press("End")
    pg.keyboard.type(" — עריכה שלי")
    mine = pg.input_value(".draft textarea")
    served = push_new_message(pg, base, "t18f2a01")
    pg.wait_for_selector("[data-test=tk-live]:not([hidden])", timeout=12000)         # within one 5 s tick
    assert served
    assert "התקבלה הודעה חדשה" in pg.inner_text("[data-test=tk-live]") and NEW_MSG in pg.inner_text("[data-test=tk-live]")
    assert NEW_MSG in pg.inner_text("#tk-conv")                                         # the conversation, in place
    assert pg.input_value(".draft textarea") == mine                                    # the agent's text: untouched
    assert pg.evaluate("document.activeElement && document.activeElement.tagName") == "TEXTAREA"   # caret still there
    pg.keyboard.type("!")
    v = pg.input_value(".draft textarea")
    assert "עריכה שלי!" in v and v.replace("!", "", 1) == mine                          # typed exactly where the caret was
    assert pg.is_visible("[data-test=draft-offer]") and pg.is_visible("[data-test=use-new-draft]")
    pg.click("[data-test=use-new-draft]")
    assert pg.input_value(".draft textarea") == NEW_DRAFT
    pg.unroute("**/api/rozela/watch")


def test_new_message_when_idle_redraws_with_the_new_draft(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/t/t18f2a02")
    pg.wait_for_selector(".draft textarea")
    pg.wait_for_timeout(300)
    pg.evaluate("document.activeElement && document.activeElement.blur()")
    push_new_message(pg, base, "t18f2a02")
    pg.wait_for_selector("[data-test=tk-live]:not([hidden])", timeout=12000)
    assert pg.input_value(".draft textarea") == NEW_DRAFT                               # nobody had touched it
    assert NEW_MSG in pg.inner_text("#tk-conv")
    pg.click("[data-test=tk-live] button")
    assert pg.is_hidden("[data-test=tk-live]")
    pg.unroute("**/api/rozela/watch")


def test_open_asks_for_the_reserved_slot_and_a_confirmed_copy_needs_one_request(page):
    pg, base = page
    bodies = []
    pg.on("request", lambda r: bodies.append(json.loads(r.post_data or "{}")) if r.url.endswith("/api/rozela/ticket") else None)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a04")
    pg.wait_for_selector(".draft textarea")
    pg.wait_for_timeout(500)
    mine = [b for b in bodies if b.get("id") == "t18f2a04"]
    assert mine and all(b.get("open") is True for b in mine)
    bodies.clear()
    pg.goto(base + "/cs#/b/rozela/action")
    pg.wait_for_selector("#list-pane > a.row")
    pg.goto(base + "/cs#/b/rozela/t/t18f2a04")                                          # read seconds ago: confirmed
    pg.wait_for_selector(".draft textarea")
    pg.wait_for_timeout(800)
    mine = [b for b in bodies if b.get("id") == "t18f2a04"]
    assert len(mine) == 1 and not mine[0].get("revalidate")                             # no second round-trip
    assert pg.is_hidden("[data-test=tk-sync]")                                          # and nothing says "loading"


def test_opening_a_ticket_warms_the_next_ones(page):
    pg, base = page
    pre = []
    pg.on("request", lambda r: pre.append(json.loads(r.post_data or "{}")) if r.url.endswith("/api/rozela/prefetch") else None)
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("#list-pane > a.row")
    ids = pg.eval_on_selector_all("#list-pane > a.row", "els => els.map(e => e.getAttribute('data-id'))")
    assert len(ids) >= 2
    pre.clear()
    pg.click("a.row[data-id='%s']" % ids[0])
    pg.wait_for_selector(".draft textarea, [data-test=bot-banner]")
    pg.wait_for_timeout(600)
    nxt = [p["ids"] for p in pre if p.get("ids") and ids[0] not in p["ids"]]
    assert nxt and nxt[0][0] == ids[1] and len(nxt[0]) <= 5                              # the next ones, in order


def test_a_saved_edit_is_still_the_agents_text(page):
    """Autosave makes the screen's base equal the agent's text. A new engine draft must still be OFFERED, not applied —
    also when the agent has left the textarea."""
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/t/t18f2a05")
    pg.wait_for_selector(".draft textarea")
    pg.wait_for_timeout(300)
    pg.click(".draft textarea")
    pg.keyboard.press("End")
    pg.keyboard.type(" — שלי")
    mine = pg.input_value(".draft textarea")
    pg.evaluate("document.activeElement.blur()")                                       # blur = save now
    pg.wait_for_selector("text=נשמר ✓", timeout=10000)
    push_new_message(pg, base, "t18f2a05")
    pg.wait_for_selector("[data-test=tk-live]:not([hidden])", timeout=12000)
    assert pg.input_value(".draft textarea") == mine and pg.is_visible("[data-test=use-new-draft]")
    pg.unroute("**/api/rozela/watch")


def test_checking_indicator_is_small_and_never_blocks_send(page):
    """While a check of the open chat runs: a quiet "מתעדכן…", and Send stays usable (rozela is live in the mock)."""
    pg, base = page
    held = []
    pg.goto(base + "/cs#/b/rozela/t/t18f2a03")
    pg.wait_for_selector(".draft textarea")
    pg.fill(".draft textarea", "בדיקה")
    pg.route("**/api/rozela/watch", lambda route, req: held.append(route))          # the check hangs until we let it go
    pg.wait_for_selector("[data-test=tk-check]:not([hidden])", timeout=12000)
    assert "מתעדכן…" in pg.inner_text("[data-test=tk-check]")
    assert not pg.is_disabled("[data-test=send-btn]")                       # never blocks the send
    assert pg.is_hidden("[data-test=tk-sync]")
    pg.unroute("**/api/rozela/watch")
    for r in held:
        r.continue_()
    pg.wait_for_selector("[data-test=tk-check]", state="hidden", timeout=12000)


def test_an_old_confirmed_copy_never_settles_the_send_guards(page):
    """45 s window (2026-10-05): a copy vouched for 30 s ago opens at once, but an unknown WhatsApp send is decided only
    by a FRESH check (the immediate background apiTicketLite), never by that copy."""
    import time as _t
    pg, base = page
    rid = "q" * 32
    item = {rid: {"rid": rid, "brand": "rozela", "id": "w8ab7701", "fn": "apiSend", "args": {"id": "w8ab7701", "text": "x", "channel": "whatsapp"},
                  "channel": "whatsapp", "name": "לקוחה 01", "state": "unknown", "at": int(_t.time() * 1000) - 120000}}
    pg.goto(base + "/cs#/b/rozela/t/w8ab7701")                                      # warm the server's copy
    pg.wait_for_selector(".draft textarea, [data-test=wa-queued], [data-test=bot-banner]")
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(item))

    def old(route, req):
        r = route.fetch()
        j = r.json()
        if j.get("ok") and isinstance(j.get("cache"), dict):
            j["cache"].update(hit=True, confirmed=True, stale=False, vouched_s=30)
        route.fulfill(response=r, body=json.dumps(j))
    held = []
    pg.route("**/api/rozela/ticket", old)
    pg.route("**/api/rozela/watch", lambda route, req: held.append(route))
    pg.reload()
    pg.goto(base + "/cs#/b/rozela/t/w8ab7701")
    pg.wait_for_selector("[data-test=outbox-banner]", timeout=15000)
    pg.wait_for_timeout(1500)
    assert pg.get_attribute("[data-test=outbox-banner]", "data-state") in ("unknown", "checking")   # not decided by the old copy
    assert held                                                                     # a fresh check was asked for at once
    pg.unroute("**/api/rozela/watch")
    for r in held:
        r.continue_()
    pg.wait_for_selector("[data-test=outbox-banner][data-state=unsent]", timeout=15000)   # the fresh check decided
    pg.unroute("**/api/rozela/ticket")
