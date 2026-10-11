"""Files an agent sends to a customer (Owner, 2026-10-11), in a real browser against the mock engine: the 📎 row of both desks, the upload,
the send carrying only ids, where the row is hidden (WhatsApp while the brand's switch is off, past 24 hours), and the phone width."""
import json
import os

import pytest

import browser_server
from pw_launch import launch, pw

SHOTS = os.environ.get("ATTACH_SHOTS_DIR")


def pdf(n=4000):
    return b"%PDF-1.7\n" + b"A" * (n - 9)


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start({"MOCK_WA_ATTACH": "rozela"}, users=(("agent1", ["agent"], ["rozela", "celesta"], "he"),
                                                                             ("agent-en", ["agent"], ["rozela"], "en")))
    yield base, pwd
    proc.terminate()


def session(p, base, pwd, user="agent1", width=1280):
    b = launch(p)
    pg = b.new_context(viewport={"width": width, "height": 900}).new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("localStorage.removeItem('cs.outbox')")
    return b, pg, errors


def armed_click(pg, sel):
    pg.click(sel)
    pg.wait_for_timeout(600)
    pg.click(sel)


def open_ticket(pg, base, tid, path="/cs", brand="rozela"):
    pg.goto(base + path + "#/b/%s/t/%s" % (brand, tid))
    pg.wait_for_selector("[data-test=draft-card] textarea, [data-test=en-draft] textarea")


def until(pg, cond, secs=10):
    for _ in range(secs * 10):
        if cond():
            return
        pg.wait_for_timeout(100)
    raise AssertionError("condition not met")


def pick(pg, files):
    pg.set_input_files("[data-test=attach-input]", [{"name": n, "mimeType": "application/octet-stream", "buffer": b} for n, b in files])


def test_email_attach_upload_and_send_carries_only_the_ids(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors = session(p, base, pwd)
        open_ticket(pg, base, "t18f2a03")
        pg.wait_for_selector("[data-test=attach-btn]")
        assert pg.get_attribute("[data-test=attach-input]", "multiple") is not None
        hold = []
        pg.route("**/api/rozela/attach", lambda route, req: hold.append(route))      # the upload waits: the send must wait too
        pick(pg, [("חשבונית מס.pdf", pdf())])
        pg.wait_for_selector("[data-test=attach-chip][data-status=up]")
        pg.fill("[data-test=draft-card] textarea", "היי, מצרפת את החשבונית.")
        assert pg.is_disabled("[data-test=send-btn]") and pg.is_visible("[data-test=attach-wait]")
        pg.unroute("**/api/rozela/attach")
        hold[0].continue_()
        pg.wait_for_selector("[data-test=attach-chip][data-status=ok]")
        assert "חשבונית מס.pdf" in pg.inner_text("[data-test=attach-chip]")
        assert pg.is_enabled("[data-test=send-btn]")
        sends = []
        pg.on("request", lambda r: sends.append(json.loads(r.post_data)) if r.url.endswith("/apiSend") else None)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, "attach_email_1280.png"), full_page=True)
        armed_click(pg, "[data-test=send-btn]")
        for _ in range(50):
            if sends:
                break
            pg.wait_for_timeout(100)
        assert len(sends) == 1
        ids = sends[0]["args"].get("attachments")
        assert isinstance(ids, list) and len(ids) == 1 and ids[0].startswith("a") and len(ids[0]) == 25
        assert "data" not in json.dumps(sends[0]["args"]), "bytes never travel with the send"
        until(pg, lambda: pg.locator("[data-test=attach-chip]").count() == 0)          # handed to the outbox: the row is empty again
        open_ticket(pg, base, "t18f2a03")
        pg.wait_for_selector("[data-test=msg-files]")
        assert "חשבונית מס.pdf" in pg.inner_text("[data-test=msg-files]")
        assert errors == []
        b.close()


def test_refused_types_failed_uploads_and_removal(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors = session(p, base, pwd)
        open_ticket(pg, base, "t18f2a03")
        pg.wait_for_selector("[data-test=attach-btn]")
        ups = []
        pg.on("request", lambda r: ups.append(r.url) if r.url.endswith("/attach") else None)
        pick(pg, [("setup.exe", b"MZ" + b"0" * 100)])
        pg.wait_for_selector("[data-test=attach-err]:not([hidden])")
        assert "setup.exe" in pg.inner_text("[data-test=attach-err]") and ups == []
        pick(pg, [("fake.pdf", b"\x89PNG\r\n\x1a\n" + b"0" * 100)])                     # the server reads the content: refused there
        pg.wait_for_selector("[data-test=attach-chip][data-status=err]")
        assert "PDF" in pg.inner_text("[data-test=attach-chip]")
        pg.fill("[data-test=draft-card] textarea", "היי")
        assert pg.is_disabled("[data-test=send-btn]")                                   # never a send without the file the agent meant
        pg.click("[data-test=attach-remove]")
        assert pg.locator("[data-test=attach-chip]").count() == 0
        assert pg.is_enabled("[data-test=send-btn]")
        assert errors == []
        b.close()


def test_whatsapp_one_file_its_types_and_hidden_past_24h_or_while_switched_off(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors = session(p, base, pwd)
        open_ticket(pg, base, "w8ab77c1")                                               # rozela: switch on (MOCK_WA_ATTACH)
        pg.wait_for_selector("[data-test=attach-btn]")
        assert pg.get_attribute("[data-test=attach-input]", "multiple") is None
        acc = pg.get_attribute("[data-test=attach-input]", "accept")
        assert ".pdf" in acc and ".gif" not in acc and ".txt" not in acc
        pick(pg, [("a.pdf", pdf())])
        pg.wait_for_selector("[data-test=attach-chip][data-status=ok]")
        assert pg.is_disabled("[data-test=attach-btn]")                                  # one file per WhatsApp message
        pg.goto(base + "/cs#/b/rozela/t/w8ab77f2")                                       # past 24 hours: template only, no files
        pg.wait_for_selector("[data-test=wa-win-note]")
        pg.wait_for_timeout(800)
        assert pg.locator("[data-test=attach]").count() == 0
        pg.evaluate("() => { location.hash = '#/b/celesta/action'; }")                    # celesta: switch off (the live default)
        pg.wait_for_selector("#list-pane > a.row")
        wa = pg.eval_on_selector_all("#list-pane > a.row", "els => els.map(e => e.getAttribute('data-id')).filter(i => i && i[0] === 'w')")
        if wa:
            open_ticket(pg, base, wa[0], brand="celesta")
            pg.wait_for_timeout(1200)                                                     # longer than the row's wait for the list
            assert pg.locator("[data-test=attach]").count() == 0
        assert errors == []
        b.close()


def test_english_desk_attach_goes_with_the_approved_hebrew(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors = session(p, base, pwd, user="agent-en")
        open_ticket(pg, base, "t18f2a01", path="/cs/en")
        pg.wait_for_selector("[data-test=attach-btn]")
        assert pg.inner_text("[data-test=attach-btn]") == "📎 Attach file"
        pick(pg, [("invoice.pdf", pdf())])
        pg.wait_for_selector("[data-test=attach-chip][data-status=ok]")
        pg.fill("[data-test=en-draft] textarea", "Hello, the invoice is attached.")
        pg.click("[data-test=en-review-btn]")
        pg.wait_for_selector("[data-test=en-confirm]:not([disabled])")
        sends = []
        pg.on("request", lambda r: sends.append(json.loads(r.post_data)) if r.url.endswith("/apiSend") else None)
        pg.click("[data-test=en-confirm]")
        for _ in range(80):
            if sends:
                break
            pg.wait_for_timeout(100)
        assert len(sends) == 1 and len(sends[0]["args"]["attachments"]) == 1
        assert errors == []
        b.close()


def test_phone_width_the_row_fits(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors = session(p, base, pwd, width=375)
        open_ticket(pg, base, "t18f2a03")
        pg.wait_for_selector("[data-test=attach-btn]")
        width = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        before = pg.evaluate(width)          # a two-brand user's top bar is 8 px too wide at 375 already (not this row: reported separately)
        pick(pg, [("חשבונית מס קבלה מספר 12345 עבור הזמנה של דנה כהן.pdf", pdf()), ("photo.png", b"\x89PNG\r\n\x1a\n" + b"0" * 3000)])
        until(pg, lambda: pg.locator("[data-test=attach-chip][data-status=ok]").count() == 2)
        assert pg.evaluate(width) <= max(before, 0), (before, pg.evaluate(width))      # the 📎 row and its chips add no width
        box = pg.eval_on_selector("[data-test=attach]", "e => { const r = e.getBoundingClientRect(); return [r.left, r.right]; }")
        assert box[0] >= 0 and box[1] <= 375
        if SHOTS:
            pg.locator("[data-test=draft-card]").scroll_into_view_if_needed()
            pg.screenshot(path=os.path.join(SHOTS, "attach_email_375.png"), full_page=True)
        assert errors == []
        b.close()
