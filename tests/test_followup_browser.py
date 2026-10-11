"""Owner, 2026-10-11 (from the CS team), in a real browser against the mock engine:
1. a send never closes / moves on: the agent stays, the message shows, the box empties for the next one; "close" is its own button;
   an answered or closed ticket (email or WhatsApp) takes another message;
2. a WhatsApp chat past 24 hours that was answered / closed offers the template box;
3. two agents on one ticket: the second is told who answered and when, keeps the text, sees the answer, and may send anyway;
   who else has the ticket open is shown."""
import json

import pytest

import browser_server
from pw_launch import launch, pw

USERS = (("agent1", ["agent"], ["rozela"], "he"), ("agent2", ["agent"], ["rozela"], "he"), ("agenten", ["agent"], ["rozela"], "en"))


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start({"MOCK_WA_DELIVER_MS": "2500"}, users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user="agent1", width=1280, path="/cs"):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    pg.goto(base + path + "/login" if path == "/cs" else base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("localStorage.clear()")
    pg.bodies = []
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))

    def on_req(r):
        if "/api/rozela/api" in r.url and r.method == "POST":
            try:
                body = json.loads(r.post_data or "{}")
            except ValueError:
                body = {}
            pg.bodies.append((r.url.rsplit("/", 1)[-1], body.get("args") or {}))
    pg.on("request", on_req)
    return browser, pg


def calls(pg, fn):
    return [a for f, a in pg.bodies if f == fn]


def until(cond, ms=8000):                      # the page's CSP forbids eval, so no wait_for_function
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def armed_click(pg, sel):                      # two separate clicks, as a person does them
    pg.click(sel)
    pg.wait_for_timeout(600)
    pg.click(sel)


def open_ticket(pg, base, tid, path="/cs"):
    pg.goto(base + path + "#/b/rozela/t/" + tid)
    pg.wait_for_selector("[data-test=draft-card] textarea, [data-test=en-draft] textarea")


def test_send_stays_on_the_ticket_and_the_box_is_ready_for_another_message(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "t18f2a01")
        assert pg.get_attribute("[data-test=close-btn]", "data-kind") == "nosend"            # never answered: "close without sending"
        pg.fill(".draft textarea", "היי מיכל, ההזמנה בדרך.")
        armed_click(pg, "[data-test=send-btn]")
        pg.wait_for_timeout(400)
        assert pg.url.endswith("/t/t18f2a01"), pg.url                                         # stayed
        assert pg.input_value(".draft textarea") == ""                                         # empty, ready for the next one
        assert "היי מיכל, ההזמנה בדרך." in pg.inner_text("#tk-conv")                          # the sent message is in the conversation
        assert pg.get_attribute("[data-test=close-btn]", "data-kind") == "close"              # "close the ticket" now
        assert until(lambda: len(calls(pg, "apiSend")) == 1)
        pg.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=10000)
        assert pg.is_disabled("[data-test=send-btn]")                                          # nothing to send twice
        pg.wait_for_selector("[data-test=fu-note]")
        first = calls(pg, "apiSend")[0]
        assert first.get("seen") == "" and "followup" not in first                            # an open ticket: a normal send
        # a second message, right away
        pg.fill(".draft textarea", "ועוד דבר: המשלוח יוצא היום.")
        assert until(lambda: pg.is_enabled("[data-test=send-btn]"))
        armed_click(pg, "[data-test=send-btn]")
        assert until(lambda: len(calls(pg, "apiSend")) == 2)
        second = calls(pg, "apiSend")[1]
        assert second.get("followup") is True and second.get("seen"), second                  # another message, with what this screen saw
        pg.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=10000)
        assert until(lambda: "ועוד דבר: המשלוח יוצא היום." in pg.inner_text("#tk-conv"))
        assert pg.url.endswith("/t/t18f2a01")
        # closing is the button that moves on
        armed_click(pg, "[data-test=close-btn]")
        assert until(lambda: not pg.url.endswith("/t/t18f2a01"), 3000), pg.url
        assert until(lambda: len(calls(pg, "apiClose")) == 1)
        assert not pg.errors, pg.errors
        browser.close()


def test_an_answered_and_a_closed_email_ticket_take_another_message(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        for tid, kind, line in (("t18f2a08", "close", "נענתה"), ("t18f2a09", None, "נסגרה")):
            open_ticket(pg, base, tid)
            ta = pg.locator("[data-test=draft-card] textarea")
            assert ta.input_value() == "" and not ta.evaluate("e => e.readOnly")               # empty, never the answer already sent
            assert line in pg.inner_text("[data-test=fu-note]")
            close = pg.locator("[data-test=close-btn]")
            assert (close.get_attribute("data-kind") if close.count() else None) == kind       # a closed ticket has nothing to close
        pg.fill("[data-test=draft-card] textarea", "היי משה, רק לעדכן שההחזר יצא.")
        armed_click(pg, "[data-test=send-btn]")
        assert until(lambda: len(calls(pg, "apiSend")) == 1)
        sent = calls(pg, "apiSend")[0]
        assert sent.get("followup") is True and isinstance(sent.get("seen"), str) and sent["seen"], sent
        pg.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=10000)
        assert pg.url.endswith("/t/t18f2a09")
        assert not pg.errors, pg.errors
        browser.close()


def test_whatsapp_messages_in_a_row_and_a_template_on_a_closed_chat_past_24_hours(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        open_ticket(pg, base, "w8ab77c1")
        pg.fill(".draft textarea", "היי עומר, כן יש משלוח לאילת")
        armed_click(pg, "[data-test=send-btn]")
        assert until(lambda: len(calls(pg, "apiSend")) == 1)
        pg.fill(".draft textarea", "המשלוח לוקח 3 ימי עסקים")                                   # the next one is typed at once
        pg.wait_for_selector("[data-test=fu-wait]:not([hidden])", timeout=5000)               # the first is on its way
        assert pg.is_disabled("[data-test=send-btn]")
        assert until(lambda: pg.is_enabled("[data-test=send-btn]"), 15000)                    # the bridge sent it: Send opens
        armed_click(pg, "[data-test=send-btn]")
        assert until(lambda: len(calls(pg, "apiSend")) == 2)
        assert calls(pg, "apiSend")[1].get("followup") is True
        assert pg.url.endswith("/t/w8ab77c1")
        # a chat past 24 hours that is CLOSED: the template box is there (was: a read-only draft and nothing else)
        open_ticket(pg, base, "w8ab77f2")
        armed_click(pg, "[data-test=close-btn]")
        assert until(lambda: len(calls(pg, "apiClose")) == 1)
        pg.wait_for_timeout(800)
        open_ticket(pg, base, "w8ab77f2")
        pg.wait_for_selector("[data-test=fu-note]")
        pg.wait_for_selector("[data-test=tpl-box] [data-test=tpl-select]")
        assert pg.is_disabled("[data-test=send-btn]") or pg.input_value(".draft textarea") == ""
        armed_click(pg, "[data-test=tpl-send]")
        assert until(lambda: len(calls(pg, "apiSendTemplate")) == 1)
        tpl = calls(pg, "apiSendTemplate")[0]
        assert isinstance(tpl.get("seen"), str) and tpl["seen"], tpl
        pg.wait_for_timeout(500)
        assert pg.url.endswith("/t/w8ab77f2")                                                 # stays: the template shows as on its way
        assert pg.locator("[data-test=msg-outgoing]").count() >= 1
        assert not pg.errors, pg.errors
        browser.close()


def test_two_agents_on_one_ticket(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b1, a1 = login(p, base, pwd, "agent1")
        b2, a2 = login(p, base, pwd, "agent2")
        open_ticket(a1, base, "t18f2a03")
        open_ticket(a2, base, "t18f2a03")
        # presence: each sees the other (the /watch tick runs every 5 s)
        a2.wait_for_selector("[data-test=tk-presence]:not([hidden])", timeout=12000)
        assert "agent1" in a2.inner_text("[data-test=tk-presence]")
        a1.fill(".draft textarea", "היי, ההחזר יצא היום.")                                     # agent1 is writing
        a2.wait_for_selector("[data-test=tk-presence][data-state=editing]", timeout=12000)
        armed_click(a1, "[data-test=send-btn]")
        a1.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=10000)
        # agent2 never saw that answer and sends her own
        mine = "היי, נבדוק ונחזור אלייך עוד היום."
        a2.fill(".draft textarea", mine)
        armed_click(a2, "[data-test=send-btn]")
        a2.wait_for_selector("[data-test=outbox-banner][data-reason=changed_meanwhile]", timeout=10000)
        banner = a2.inner_text("[data-test=outbox-banner]")
        assert "agent1" in banner and "כבר ענה" in banner, banner
        assert until(lambda: a2.input_value(".draft textarea") == mine)                      # her text is kept, in the box
        assert until(lambda: "היי, ההחזר יצא היום." in a2.inner_text("#tk-conv"), 8000)      # and agent1's answer is in front of her
        assert until(lambda: a2.inner_text("[data-test=send-btn]") == "לשלוח בכל זאת כהודעה נוספת")
        armed_click(a2, "[data-test=send-btn]")                                               # one more decision: send anyway
        assert until(lambda: len(calls(a2, "apiSend")) == 2)
        again = calls(a2, "apiSend")[1]
        assert again.get("followup") is True and again.get("seen"), again
        a2.wait_for_selector("[data-test=outbox-banner][data-state=ok]", timeout=10000)
        assert not a1.errors and not a2.errors, (a1.errors, a2.errors)
        b1.close()
        b2.close()


def test_english_desk_answered_ticket_has_an_empty_english_composer(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd, "agenten")
        open_ticket(pg, base, "t18f2a08", path="/cs/en")
        pg.wait_for_selector("[data-test=en-draft] [data-test=fu-note]")
        assert pg.input_value("[data-test=en-draft] textarea") == ""
        assert "Another message" in pg.inner_text("[data-test=en-draft] h3")
        assert pg.get_attribute("[data-test=close-btn]", "data-kind") == "close"
        assert "Answered" in pg.inner_text("[data-test=fu-note]")
        assert not pg.errors, pg.errors
        browser.close()
