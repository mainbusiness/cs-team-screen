"""Owner, 2026-10-15: "when you go to the old tickets at the bottom and answer one, it jumps you to the top. Make it like Dondy: from the ticket you are
on, it moves to the ticket ABOVE it, so the old ones can be answered comfortably."
After a close / send & close / snooze the screen opens the ticket that was directly above in the list the agent is looking at (same tab, channel filter,
sort, the 30+ day section too), keeps the list scrolled there (never to the top); nothing above -> the one below. Both desks, desktop and phone width."""
import json
import time

import pytest

import browser_server
from pw_launch import launch, pw

USERS = (("agent1", ["agent"], ["rozela"], "he"), ("agent2", ["agent"], ["rozela"], "he"), ("agenten", ["agent"], ["rozela"], "en"))


@pytest.fixture
def server():                                      # a fresh mock per test: every test closes tickets
    base, pwd, proc = browser_server.start({"MOCK_WA_DELIVER_MS": "0"}, users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user="agent1", width=1280, height=700):
    pg = launch(p).new_context(viewport={"width": width, "height": height}).new_page()
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


def open_list_with_old_open(pg, base, path):
    pg.goto(base + path + "#/b/rozela/ready")
    pg.wait_for_selector("#list-pane a.row")
    pg.click("[data-test=old-section] summary")                  # the 30+ day section, where the owner's agents answer the old ones
    pg.wait_for_selector("[data-test=old-section][open] a.row")
    return pg.evaluate(ORDER_JS)


def close_current(pg):
    pg.click("[data-test=close-btn]")
    pg.wait_for_timeout(600)
    pg.click("[data-test=close-btn]")


@pytest.mark.parametrize("user,path", [("agent1", "/cs"), ("agenten", "/cs/en")])
def test_closing_an_old_ticket_opens_the_one_above_and_the_list_stays_there(server, user, path):
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user)
        order = open_list_with_old_open(pg, base, path)
        assert len(order) >= 4, order
        target, above = order[-2], order[-3]                     # the lowest-but-one, in the old section
        pg.click("#list-pane a.row[data-id='%s']" % target)
        pg.wait_for_selector("[data-test=close-btn]")
        top_before = pg.evaluate("document.getElementById('list-pane').scrollTop")
        assert top_before > 0, "the test needs a scrolled list"
        y_of = "(id) => { const a = document.querySelector('#list-pane a.row[data-id=\"' + id + '\"]'); return a ? a.getBoundingClientRect().top : null; }"
        y_before = pg.evaluate(y_of, above)
        close_current(pg)
        assert until(pg, lambda: pg.url.endswith("/t/" + above)), "landed on %s, expected %s (above %s); order %s" % (pg.url.rsplit("/", 1)[-1], above, target, order)
        pg.wait_for_timeout(400)
        top_after = pg.evaluate("document.getElementById('list-pane').scrollTop")
        assert top_after > 0, "the list jumped to the top"
        y_after = pg.evaluate(y_of, above)
        assert y_after is not None and abs(y_after - y_before) < 150, "the list stayed where he was (row moved %s -> %s px)" % (y_before, y_after)
        vis = pg.evaluate("""(id) => { const lp = document.getElementById('list-pane'), a = lp.querySelector('a.row[data-id="' + id + '"]');
          if (!a) return false; const r = a.getBoundingClientRect(), q = lp.getBoundingClientRect(); return r.top >= q.top - 2 && r.bottom <= q.bottom + 2; }""", above)
        assert vis, "the opened ticket is in view in the list"
        assert not pg.errors, pg.errors


def test_a_fresh_ticket_in_the_middle_send_and_close_opens_the_one_above(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("#list-pane a.row")
        order = pg.evaluate(ORDER_JS)
        i = next(n for n, tid in enumerate(order) if n >= 2 and tid.startswith("t18f2a"))   # an email ticket with something above it
        pg.click("#list-pane a.row[data-id='%s']" % order[i])
        pg.wait_for_selector("[data-test=send-close-btn]")
        pg.click("[data-test=send-close-btn]")
        pg.wait_for_timeout(600)
        pg.click("[data-test=send-close-btn]")
        assert until(pg, lambda: pg.url.endswith("/t/" + order[i - 1])), (pg.url, order[i - 1], order)
        assert not pg.errors, pg.errors


def test_the_top_ticket_moves_down_and_the_neighbour_that_vanished_meanwhile_is_skipped_upwards(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd)
        order = open_list_with_old_open(pg, base, "/cs")
        pg.click("#list-pane a.row[data-id='%s']" % order[0])        # nothing above: the one below
        pg.wait_for_selector("[data-test=close-btn]")
        close_current(pg)
        assert until(pg, lambda: pg.url.endswith("/t/" + order[1])), (pg.url, order)
        # another agent closes the ticket right above while this one works: the screen walks further up
        order = pg.evaluate(ORDER_JS)
        target, gone, above = order[-2], order[-3], order[-4]
        pg.click("#list-pane a.row[data-id='%s']" % target)
        pg.wait_for_selector("[data-test=close-btn]")
        p2 = login(p, base, pwd, "agent2")
        p2.goto(base + "/cs#/b/rozela/t/" + gone)
        p2.wait_for_selector("[data-test=close-btn]")
        close_current(p2)
        until(p2, lambda: not p2.url.endswith("/t/" + gone))
        p2.wait_for_timeout(1500)
        until(pg, lambda: False, 11000)                              # agent1's list poll (10 s) removes it
        close_current(pg)
        assert until(pg, lambda: pg.url.endswith("/t/" + above)), (pg.url, above, order)
        assert not pg.errors, pg.errors


@pytest.mark.parametrize("user,path", [("agent1", "/cs"), ("agenten", "/cs/en")])
def test_phone_width_the_next_is_above_and_back_returns_to_the_same_place(server, user, path):
    base, pwd = server
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user, width=390, height=760)
        order = open_list_with_old_open(pg, base, path)
        target, above = order[-2], order[-3]
        pg.locator("#list-pane a.row[data-id='%s']" % target).scroll_into_view_if_needed()
        assert pg.evaluate("window.scrollY") > 0
        pg.click("#list-pane a.row[data-id='%s']" % target)
        pg.wait_for_selector("[data-test=close-btn]")
        close_current(pg)
        assert until(pg, lambda: pg.url.endswith("/t/" + above)), (pg.url, above, order)
        pg.wait_for_selector("[data-test=close-btn]")
        pg.click(".back-btn")                                         # the ticket's own "חזרה" / "Back"
        pg.wait_for_selector("#list-pane a.row")
        pg.wait_for_timeout(500)
        assert pg.evaluate("window.scrollY") > 0, "back on the list: not at the top"
        box = pg.locator("#list-pane a.row[data-id='%s']" % above).bounding_box()
        assert box and 0 <= box["y"] <= 760, "the ticket he was on is in view"
        assert not pg.errors, pg.errors
