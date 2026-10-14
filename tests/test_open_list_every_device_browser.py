"""Owner, 2026-10-14: "on some devices / users you don't see all the open chats". The device that closed a chat kept a 24 h record of
that close and hid the row for all of it, so a chat the customer reopened was invisible to the agent who had closed it. Every open
ticket the server lists must show on every device; a close hides its row only while on its way (+ a short grace)."""
import json
import time

import pytest

import browser_server
from pw_launch import launch, pw

TID = "t18f2a01"


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start({}, users=(("agent1", ["agent"], ["rozela"], "he"),))
    yield base, pwd
    proc.terminate()


def seeded_page(p, base, pwd, items):
    b = launch(p)
    pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", "agent1")
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps(items))
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.reload()
    pg.wait_for_selector("a.row")
    return b, pg


def close_item(at_ms, ok_at_ms=None):
    it = {"rid": "a" * 32, "fn": "apiClose", "brand": "rozela", "id": TID, "name": "x", "state": "ok", "at": at_ms, "reply": {}}
    if ok_at_ms is not None:
        it["ok_at"] = ok_at_ms
    return {it["rid"]: it}


def visible_ids(pg):
    return [a.get_attribute("data-id") for a in pg.locator("#list-pane a.row").all()]


def open_count(pg):
    return int(pg.locator(".tab.ready .n").inner_text())


def test_an_old_close_on_this_device_never_hides_an_open_chat(server):
    base, pwd = server
    now = int(time.time() * 1000)
    with pw.sync_playwright() as p:
        b, pg = seeded_page(p, base, pwd, close_item(now - 3600_000, now - 3600_000))   # closed here an hour ago, open on the server
        ids = visible_ids(pg)
        assert TID in ids
        assert len(ids) == open_count(pg)                                   # the count and the list are the same tickets
        b.close()


def test_a_record_from_before_the_fix_never_hides_an_open_chat(server):
    base, pwd = server
    now = int(time.time() * 1000)
    with pw.sync_playwright() as p:
        b, pg = seeded_page(p, base, pwd, close_item(now - 60_000))         # no ok_at: what devices hold today
        assert TID in visible_ids(pg)
        b.close()


def test_a_close_that_just_finished_hides_its_row_for_the_grace_only(server):
    base, pwd = server
    now = int(time.time() * 1000)
    with pw.sync_playwright() as p:
        b, pg = seeded_page(p, base, pwd, close_item(now, now))             # the agent just closed it; the server copy lags a poll
        assert TID not in visible_ids(pg)
        b.close()
