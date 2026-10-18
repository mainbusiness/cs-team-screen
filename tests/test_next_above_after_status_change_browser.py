"""Owner, 2026-10-18 (from the CS team): "when I send a template to a WhatsApp customer past 24 hours, the moment I close the ticket it sends me
back to the NEWEST tickets, instead of moving on to the chat above, like it does with every other close."
A template (and any send that keeps the ticket open, 2026-10-11) changes the open ticket's status out of the tab while the agent is still on it;
the list re-renders without it. Closing it afterwards must still open the ticket that was directly ABOVE it (the 2026-10-15 rule), never the top."""
import time

import pytest

import browser_server
from pw_launch import launch, pw

USERS = (("agent1", ["agent"], ["rozela"], "he"), ("agenten", ["agent"], ["rozela"], "en"))


@pytest.fixture
def server():                                      # a fresh mock per test: every test sends and closes
    base, pwd, proc = browser_server.start({"MOCK_WA_DELIVER_MS": "0"}, users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user):
    pg = launch(p).new_context(viewport={"width": 1280, "height": 700}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("localStorage.clear()")
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    return pg


def until(pg, cond, ms=6000):
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        pg.wait_for_timeout(30)
    return False


ORDER_JS = """() => Array.from(document.querySelectorAll('#list-pane a.row[data-id]'))
  .filter(a => !a.closest('.snz-section')).map(a => a.getAttribute('data-id'))"""


def open_in_list(pg, base, path, tid):
    pg.goto(base + path + "#/b/rozela/ready")
    pg.wait_for_selector("#list-pane a.row")
    order = pg.evaluate(ORDER_JS)
    i = order.index(tid)
    assert i >= 2, "the test needs rows above the ticket: %s" % order          # not the top: the bug lands on order[0]
    pg.click("#list-pane a.row[data-id='%s']" % tid)
    return order, order[i - 1]


def wait_out_of_list(pg, tid):
    """The re-renders that happen while he stays on the ticket: the change feed, the ticket watch, the 10 s list poll."""
    assert until(pg, lambda: pg.locator("#list-pane a.row[data-id='%s']" % tid).count() == 0, 15000), "the ticket left the tab"
    pg.wait_for_timeout(12000)


def close_current(pg):
    pg.click("[data-test=close-btn]")
    pg.wait_for_timeout(600)
    pg.click("[data-test=close-btn]")


@pytest.mark.parametrize("user,path", [("agent1", "/cs"), ("agenten", "/cs/en")])
def test_template_past_24h_then_close_opens_the_one_above(server, user, path):
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user)
        order, above = open_in_list(pg, base, path, "w8ab77f2")                  # WhatsApp, the customer wrote 30 h ago: template only
        pg.wait_for_selector("[data-test=tpl-select] option", state="attached")
        pg.click("[data-test=tpl-send]")                                           # first click arms
        pg.wait_for_timeout(600)
        with pg.expect_response(lambda r: r.url.endswith("/apiSendTemplate")) as resp:
            pg.click("[data-test=tpl-send]")                                       # second click sends
        assert resp.value.json().get("ok"), resp.value.json()
        assert pg.url.endswith("/t/w8ab77f2"), "a template never moves on"
        wait_out_of_list(pg, "w8ab77f2")
        assert pg.url.endswith("/t/w8ab77f2")
        close_current(pg)
        assert until(pg, lambda: not pg.url.endswith("/t/w8ab77f2")), "the close moved on"
        landed = pg.url.rsplit("/", 1)[-1]
        assert landed == above, "landed on %s, expected %s (above w8ab77f2), not the top %s; order %s" % (landed, above, order[0], order)
        assert not pg.errors, pg.errors


def test_a_send_that_stays_on_the_ticket_then_close_opens_the_one_above(server):
    """The same hole for the normal send (2026-10-11: a send keeps the ticket open): the ticket becomes 'wa_queued' and leaves the tab."""
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("#list-pane a.row")
        order = pg.evaluate(ORDER_JS)
        tid = next(x for n, x in enumerate(order) if n >= 2 and x.startswith("t18f2a"))   # an email ticket with rows above it
        order, above = open_in_list(pg, base, "/cs", tid)
        pg.wait_for_selector("[data-test=send-btn]")
        with pg.expect_response(lambda r: r.url.endswith("/apiSend")) as resp:
            pg.click("[data-test=send-btn]")
            pg.wait_for_timeout(600)
            if pg.locator("[data-test=send-btn].arm").count():
                pg.click("[data-test=send-btn]")
        assert resp.value.json().get("ok"), resp.value.json()
        assert pg.url.endswith("/t/" + tid), "a send never moves on"
        wait_out_of_list(pg, tid)
        close_current(pg)
        assert until(pg, lambda: not pg.url.endswith("/t/" + tid)), "the close moved on"
        landed = pg.url.rsplit("/", 1)[-1]
        assert landed == above, "landed on %s, expected %s (above %s), not the top %s; order %s" % (landed, above, tid, order[0], order)
        assert not pg.errors, pg.errors
