"""Owner, 2026-10-14 (from the CS team), in a real browser against the mock engine, on BOTH desks (/cs and /cs/en):
1. "שליחה וסגירה": one armed action sends, closes and moves on at once; the close runs only after the engine accepted the send (never after a
   refusal; it waits through a retry); WhatsApp: the queued send still goes and the chat stays closed.
2. The close button is usable at once after a send (measured live before: 3.7-4.1 s) — the close queues behind the send.
3. "תשובה אחרת": a different AI draft with an optional wish, the previous one a click away; a refusal is shown in words.
4. "לענות מאוחר יותר": the ticket leaves THIS agent's list and count only (server-side: reload / another device agree), comes back to the top
   when the time is up or when the customer writes again; another agent keeps seeing it.
The mock engine answers apiSend after 3 s (MOCK_SLOW_FNS), like the live engine's ~3.7 s."""
import json
import os
import tempfile
import time

import pytest

import browser_server
from mock_engine import MockEngines
from pw_launch import launch, pw

USERS = (("agent1", ["agent"], ["rozela"], "he"), ("agent2", ["agent"], ["rozela"], "he"), ("agenten", ["agent"], ["rozela"], "en"))
SNOOZE = os.path.join(tempfile.mkdtemp(prefix="cs-snz-"), "snooze.json")
SEND_MS = 3000


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start({"MOCK_SLOW_FNS": "apiSend:%d" % SEND_MS, "MOCK_WA_DELIVER_MS": "2500", "SNOOZE_PATH": SNOOZE}, users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user="agent1", width=1280):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("localStorage.clear()")
    pg.reqs, pg.resps, pg.errors = [], [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))

    def on_req(r):
        if "/api/rozela/api" in r.url and r.method == "POST":
            try:
                body = json.loads(r.post_data or "{}")
            except ValueError:
                body = {}
            pg.reqs.append((time.time(), r.url.rsplit("/", 1)[-1], body.get("args") or {}))
    pg.on("request", on_req)
    pg.on("response", lambda r: pg.resps.append((time.time(), r.url.rsplit("/", 1)[-1])) if "/api/rozela/api" in r.url else None)
    return browser, pg


def calls(pg, fn):
    pg.wait_for_timeout(1)                     # sync Playwright delivers request events only while it is called: pump it
    return [a for _, f, a in pg.reqs if f == fn]


def first(pg, fn, kind="req"):
    pg.wait_for_timeout(1)
    xs = [t for t, f, _ in pg.reqs if f == fn] if kind == "req" else [t for t, f in pg.resps if f == fn]
    return xs[0] if xs else None


def until(cond, ms=8000):                      # the page's CSP forbids eval, so no wait_for_function
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def armed_click(pg, sel):                      # two separate clicks, as a person does them; returns the time of the second
    pg.click(sel)
    pg.wait_for_timeout(600)
    t = time.time()
    pg.click(sel)
    return t


def open_ticket(pg, base, tid, path="/cs"):
    pg.goto(base + path + "#/b/rozela/t/" + tid)
    pg.wait_for_selector("[data-test=draft-card] textarea, [data-test=en-draft] textarea")


def outbox(pg, tid):
    return [i for i in pg.evaluate("JSON.parse(localStorage.getItem('cs.outbox') || '{}')").values() if i.get("id") == tid]


def close_state(pg):
    return pg.evaluate("() => { const b = document.querySelector('[data-test=close-btn]'); return b ? [b.getAttribute('data-kind'), b.disabled] : null; }")


def badge(pg):
    return int(pg.inner_text("#tabs a.tab.ready .n") or "0")


def list_ids(pg):
    return pg.evaluate("() => Array.from(document.querySelectorAll('#list-pane > a.row')).map(a => a.getAttribute('data-id'))")


# ---------------------------------------------------------------- 1-2. send, then close at once; send & close

def test_hebrew_close_is_usable_at_once_after_a_send_and_runs_after_the_send(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a01")
        t_click = armed_click(pg, "[data-test=send-btn]")
        assert until(lambda: (close_state(pg) or [None, True])[0] == "close" and not close_state(pg)[1], 3000)
        usable = time.time() - t_click
        assert usable < 0.5, "close usable after %.2f s" % usable
        assert first(pg, "apiSend", "resp") is None, "the send is still on its way: the button did not wait for it"
        t2 = armed_click(pg, "[data-test=close-btn]")
        assert until(lambda: not pg.url.endswith("/t/t18f2a01"), 1500), pg.url
        moved = time.time() - t2
        assert until(lambda: calls(pg, "apiClose"), SEND_MS + 6000)
        assert first(pg, "apiClose") >= first(pg, "apiSend", "resp"), "the close left only after the engine answered the send"
        assert until(lambda: any(i["fn"] == "apiClose" and i["state"] == "ok" for i in outbox(pg, "t18f2a01")), 8000)
        print("\n     close usable %.3f s after the send click; moved on %.3f s after the close click; apiSend answer at %.2f s"
              % (usable, moved, first(pg, "apiSend", "resp") - t_click))
        assert not pg.errors, pg.errors
        browser.close()


def test_hebrew_send_and_close_moves_on_at_once_then_sends_then_closes(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a02")
        assert pg.is_enabled("[data-test=send-close-btn]")
        assert "שליחה וסגירה" in pg.inner_text("[data-test=send-close-btn]")
        t = armed_click(pg, "[data-test=send-close-btn]")
        assert until(lambda: not pg.url.endswith("/t/t18f2a02"), 1000), "the agent never waits"
        moved = time.time() - t
        assert moved < 1.0, moved
        assert until(lambda: calls(pg, "apiClose"), SEND_MS + 6000)
        assert len(calls(pg, "apiSend")) == 1 and len(calls(pg, "apiClose")) == 1
        assert first(pg, "apiClose") >= first(pg, "apiSend", "resp")
        assert until(lambda: any(i["fn"] == "apiClose" and i["state"] == "ok" for i in outbox(pg, "t18f2a02")), 8000)
        assert "t18f2a02" not in list_ids(pg)
        assert not pg.errors, pg.errors
        browser.close()


def test_send_and_close_never_closes_after_a_refused_send_the_ticket_returns_flagged_on_top(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a04")
        pg.fill(".draft textarea", "REFUSE-SEND היי דנה, ההחזר יצא.")
        armed_click(pg, "[data-test=send-close-btn]")
        assert until(lambda: not pg.url.endswith("/t/t18f2a04"), 1000)
        assert until(lambda: any(i["fn"] == "apiSend" and i["state"] == "refused" for i in outbox(pg, "t18f2a04")), SEND_MS + 6000)
        pg.wait_for_timeout(1500)
        assert calls(pg, "apiClose") == [], "a refused send is never followed by its close"
        assert until(lambda: (list_ids(pg) or [None])[0] == "t18f2a04", 4000), list_ids(pg)[:3]
        assert pg.get_attribute("#list-pane > a.row[data-id=t18f2a04] [data-test=row-outbox]", "data-state") == "refused"
        open_ticket(pg, base, "t18f2a04")
        assert "REFUSE-SEND" in pg.input_value(".draft textarea"), "the text came back to the box"
        assert not pg.errors, pg.errors
        browser.close()


def test_send_and_close_waits_through_a_retry_then_closes(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a06")
        pg.fill(".draft textarea", "BUSY-ONCE היי אבי, ההזמנה בדרך.")
        armed_click(pg, "[data-test=send-close-btn]")
        assert until(lambda: any(i["fn"] == "apiSend" and i["state"] == "retry" for i in outbox(pg, "t18f2a06")), SEND_MS + 4000)
        assert calls(pg, "apiClose") == []
        assert until(lambda: len(calls(pg, "apiSend")) == 2 and calls(pg, "apiClose"), 5000 + 2 * SEND_MS + 6000)
        assert first(pg, "apiClose") >= [t for t, f in pg.resps if f == "apiSend"][-1]
        assert until(lambda: any(i["fn"] == "apiClose" and i["state"] == "ok" for i in outbox(pg, "t18f2a06")), 8000)
        assert not pg.errors, pg.errors
        browser.close()


def test_whatsapp_send_and_close_the_queued_send_goes_and_the_chat_stays_closed(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "w8ab77c1")
        pg.fill(".draft textarea", "היי עומר, כן יש משלוח לאילת")
        armed_click(pg, "[data-test=send-close-btn]")
        assert until(lambda: not pg.url.endswith("/t/w8ab77c1"), 1000)
        assert until(lambda: calls(pg, "apiClose"), SEND_MS + 6000)
        assert first(pg, "apiClose") >= first(pg, "apiSend", "resp")
        pg.wait_for_timeout(3500)                                  # the pretend bridge delivers the queued send (2.5 s)
        open_ticket(pg, base, "w8ab77c1")
        assert until(lambda: "נסגרה" in (pg.inner_text("[data-test=fu-note]") if pg.locator("[data-test=fu-note]").is_visible() else ""), 8000), \
            "delivered and still closed"
        assert "היי עומר, כן יש משלוח לאילת" in pg.inner_text("#tk-conv")
        assert not pg.errors, pg.errors
        browser.close()


def test_english_desk_confirm_send_and_close_and_the_close_button_right_after_a_send(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd, user="agenten")
        open_ticket(pg, base, "t18f2a07", path="/cs/en")
        pg.fill("[data-test=en-draft] textarea", "Hi Olga, your order is on its way.")
        pg.click("[data-test=en-review-btn]")
        pg.wait_for_selector("[data-test=en-confirm-close]:not([disabled])", timeout=15000)
        t = time.time()
        pg.click("[data-test=en-confirm-close]")
        assert until(lambda: not pg.url.endswith("/t/t18f2a07"), 1000), "moved on at once"
        assert time.time() - t < 1.0
        assert until(lambda: calls(pg, "apiClose"), SEND_MS + 6000)
        assert first(pg, "apiClose") >= first(pg, "apiSend", "resp")
        # the plain confirm keeps the agent on the ticket; its close button is usable at once
        pg.reqs.clear(); pg.resps.clear()
        open_ticket(pg, base, "t18f2a10", path="/cs/en")                   # a closed ticket: another message
        pg.fill("[data-test=en-draft] textarea", "One more thing: the refund was sent.")
        pg.click("[data-test=en-review-btn]")
        pg.wait_for_selector("[data-test=en-confirm]:not([disabled])", timeout=15000)
        t = time.time()
        pg.click("[data-test=en-confirm]")
        assert until(lambda: (close_state(pg) or [None, True])[0] == "close" and not close_state(pg)[1], 3000)
        assert time.time() - t < 0.5
        assert first(pg, "apiSend", "resp") is None
        assert not pg.errors, pg.errors
        browser.close()


# ---------------------------------------------------------------- 3. a different answer

def test_hebrew_different_answer_with_a_wish_then_undo_and_a_typed_text_comes_back(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a03")
        before = pg.input_value(".draft textarea")
        pg.fill("[data-test=rd-hint]", "יותר קצר")
        pg.click("[data-test=rd-btn]")
        assert until(lambda: "תשובה אחרת מספר 1 (קצרה)" in pg.input_value(".draft textarea"), 6000), pg.input_value(".draft textarea")
        a = calls(pg, "apiRedraftOne")[0]
        assert a["hint"] == "יותר קצר" and a["base"] == MockEngines.draft_fp(before) and isinstance(a["seen"], str), a
        assert "נכתבה תשובה אחרת" in pg.inner_text("[data-test=rd-msg]")
        assert pg.input_value("[data-test=rd-hint]") == ""
        pg.wait_for_timeout(7000)                  # the 5 s watch redraws an idle ticket: the way back must survive it
        assert pg.locator("[data-test=rd-undo]").is_visible(), "undo is still offered after the ticket was redrawn"
        pg.click("[data-test=rd-undo]")
        assert until(lambda: pg.input_value(".draft textarea") == before, 4000)
        assert calls(pg, "apiRedraftOne")[-1].get("undo") is True
        # the agent's own typing is never lost: a different answer replaces it, undo brings it back
        mine = before + "\nועוד שורה שלי."
        pg.fill(".draft textarea", mine)
        pg.wait_for_timeout(300)
        pg.click("[data-test=rd-btn]")
        assert until(lambda: "תשובה אחרת מספר" in pg.input_value(".draft textarea"), 6000)
        pg.click("[data-test=rd-undo]")
        assert until(lambda: pg.input_value(".draft textarea") == mine, 4000)
        assert not calls(pg, "apiSend"), "nothing is ever sent by it"
        assert not pg.errors, pg.errors
        browser.close()


def test_english_desk_different_answer_is_shown_in_english_and_undo(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd, user="agenten")
        open_ticket(pg, base, "t18f2c02", path="/cs/en")
        assert until(lambda: pg.input_value("[data-test=en-draft] textarea").strip() != "", 8000)
        before = pg.input_value("[data-test=en-draft] textarea")
        assert pg.is_visible("[data-test=rd-btn]")
        pg.fill("[data-test=rd-hint]", "שיהיה קצר")
        pg.click("[data-test=rd-btn]")
        assert until(lambda: "a different answer" in pg.input_value("[data-test=en-draft] textarea"), 8000), pg.input_value("[data-test=en-draft] textarea")
        assert "(short)" in pg.input_value("[data-test=en-draft] textarea")
        pg.wait_for_timeout(7000)                  # the 5 s watch redraws an idle ticket: the way back must survive it
        assert pg.locator("[data-test=rd-undo]").is_visible(), "undo is still offered after the ticket was redrawn"
        pg.click("[data-test=en-review-btn]")      # the new answer goes through the normal Hebrew preview
        pg.wait_for_selector("[data-test=en-confirm-close]:not([disabled])", timeout=15000)
        pg.click("[data-test=en-edit]" if pg.locator("[data-test=en-edit]").count() else "[data-test=en-review] .actions .btn.ghost")
        pg.click("[data-test=rd-undo]")
        assert until(lambda: pg.input_value("[data-test=en-draft] textarea") == before, 4000)
        assert not pg.errors, pg.errors
        browser.close()


def test_a_refused_different_answer_is_said_in_words_and_the_draft_stays(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a11")
        for _ in range(6):                                         # 5 per ticket per hour
            pg.click("[data-test=rd-btn]")
            assert until(lambda: pg.is_enabled("[data-test=rd-btn]") and pg.locator("[data-test=rd-msg]").is_visible(), 6000)
            if pg.get_attribute("[data-test=rd-msg]", "data-kind") == "err":
                break
        kept = pg.input_value(".draft textarea")
        assert pg.get_attribute("[data-test=rd-msg]", "data-kind") == "err"
        assert "בעוד" in pg.inner_text("[data-test=rd-msg]") and "rate_limited" not in pg.inner_text("[data-test=rd-msg]")
        assert pg.input_value(".draft textarea") == kept
        assert not pg.errors, pg.errors
        browser.close()


# ---------------------------------------------------------------- 4. answer later

def test_snooze_leaves_his_list_and_count_only_on_every_device_and_comes_back_on_cancel(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b1, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("#list-pane > a.row")
        n0 = badge(pg)
        assert "t18f2a05" in list_ids(pg)
        open_ticket(pg, base, "t18f2a05")
        pg.click("[data-test=snooze-btn]")
        assert pg.is_visible("[data-test=snooze-menu]")
        assert [pg.locator("[data-test=snooze-opt]").nth(i).get_attribute("data-kind") for i in range(4)] == ["30m", "1h", "2h", "eod"]
        pg.click("[data-test=snooze-opt][data-kind='1h']")
        assert until(lambda: not pg.url.endswith("/t/t18f2a05"), 1000), "moved on, like a close"
        assert until(lambda: badge(pg) == n0 - 1, 4000), (badge(pg), n0)
        assert "t18f2a05" not in list_ids(pg)
        assert "1" in pg.inner_text("[data-test=snooze-section] summary")
        # another agent: still there, his count unchanged
        b2, pg2 = login(p, base, pwd, user="agent2")
        pg2.goto(base + "/cs#/b/rozela/ready")
        pg2.wait_for_selector("#list-pane > a.row")
        assert "t18f2a05" in list_ids(pg2) and badge(pg2) == n0
        b2.close()
        # the same agent on another device (a new login, empty storage): the server's copy
        b3, pg3 = login(p, base, pwd)
        pg3.goto(base + "/cs#/b/rozela/ready")
        pg3.wait_for_selector("#list-pane > a.row")
        assert until(lambda: "t18f2a05" not in list_ids(pg3) and badge(pg3) == n0 - 1, 4000)
        open_ticket(pg3, base, "t18f2a05")                                       # a deep link still opens it, and says so
        assert until(lambda: pg3.locator("[data-test=snooze-chip]").is_visible(), 3000)
        assert "נדחה עד" in pg3.inner_text("[data-test=snooze-chip]")
        b3.close()
        # bring it back from the strip
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("[data-test=snooze-section]")
        pg.click("[data-test=snooze-section] summary")
        pg.click("[data-test=snooze-row-cancel]")
        assert until(lambda: "t18f2a05" in list_ids(pg) and badge(pg) == n0, 4000)
        assert not pg.errors, pg.errors
        b1.close()


def test_snooze_comes_back_to_the_top_when_the_time_is_up_and_at_once_when_the_customer_wrote(server):
    base, pwd = server
    now = time.time()
    try:
        with open(SNOOZE, encoding="utf-8") as f:
            d = json.load(f)
    except OSError:                                # this test alone: nothing snoozed yet
        d = {}
    # agent1: one ending in 4 s; one whose customer wrote again since (the row has 1 customer message, the snooze saw 0)
    d["rozela|w8ab77f3|agent1"] = {"u": "agent1", "b": "rozela", "id": "w8ab77f3", "until": now + 4, "at": now - 60, "n": 1, "wl": "2099-01-01T00:00:00Z", "ws": ""}
    d["rozela|t18f2a02x|agent1"] = {"u": "agent1", "b": "rozela", "id": "t18f2c02", "until": now + 3600, "at": now - 60, "n": 0, "wl": "", "ws": ""}
    with open(SNOOZE, "w", encoding="utf-8") as f:
        json.dump(d, f)
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("#list-pane > a.row")
        assert until(lambda: "w8ab77f3" not in list_ids(pg), 3000), "still snoozed"
        assert until(lambda: pg.locator("#list-pane > a.row[data-id=t18f2c02] [data-test=snooze-back]").count() == 1, 3000), "the customer wrote: back at once"
        assert until(lambda: "w8ab77f3" in list_ids(pg), 8000), "the time is up: back"
        ids = list_ids(pg)
        backs = [i for i in ids if pg.locator("#list-pane > a.row[data-id=%s] [data-test=snooze-back]" % i).count()]
        assert set(backs) == {"w8ab77f3", "t18f2c02"}, backs
        flagged = [i for i in ids if pg.locator("#list-pane > a.row[data-id=%s] [data-test=row-outbox]" % i).count()]
        assert ids[len(flagged):len(flagged) + 2] == [x for x in ids if x in backs][:2], "right after the ones that need a fix: the top"
        open_ticket(pg, base, "w8ab77f3")                                         # opened = handled: the mark goes
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("#list-pane > a.row")
        assert until(lambda: pg.locator("#list-pane > a.row[data-id=w8ab77f3] [data-test=snooze-back]").count() == 0, 3000)
        assert not pg.errors, pg.errors
        browser.close()
