"""Owner, 2026-10-11 — three requests, checked in a real browser against the mock engine:
 1. the mailbox an email ticket came to, small, at the very bottom of the ticket (nothing on WhatsApp / when unknown);
 2. clicking an order number opens it in Shopify in a new tab (the order's page by gid, else a search by number),
    and never also opens the row under it;
 3. the managers' dashboard card "improve the AI": general notes fanned out to every brand with ONE id, brand notes,
    honest per-brand failures, delete fanned out; admins only (the card and the proxy).
"""
import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
CONNECTED = ["rozela", "celesta", "apexmen", "selera"]          # the mock has no engine for velora on purpose
STORE = "https://admin.shopify.com/store/achq3j-nj/orders"


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start(users=(("agent1", ["agent"], ["rozela", "apexmen"], "he"),
                                                  ("admin1", ["admin"], ALL, "he"),
                                                  ("mgr1", ["user-manager"], ["rozela"], "he"),
                                                  ("agent-en", ["agent"], ["rozela"], "en")))
    yield base, pwd
    proc.terminate()
    proc.wait(timeout=10)


def until(cond, ms=8000):                      # the page's CSP forbids eval, so no wait_for_function
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def login(p, base, pwd, user, width=1280, path="/cs/login"):
    browser = launch(p)
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    ctx.route("https://admin.shopify.com/**", lambda r: r.fulfill(status=200, body="shopify stub"))   # never the real internet
    pg = ctx.new_page()
    pg.goto(base + path)
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, ctx, pg


def engine_api(pg, base, brand, fn, args=None):
    tok = pg.get_attribute("meta[name=csrf]", "content")
    r = pg.request.post(base + "/api/%s/%s" % (brand, fn), data={"args": args or {}}, headers={"X-CSRF-Token": tok})
    return r.status, r.json()


# ---------------------------------------------------------------- 1. mailbox line
def test_mailbox_line_at_the_bottom_of_an_email_ticket_only(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
        pg.wait_for_selector("[data-test=tk-mailbox]")
        line = pg.locator("[data-test=tk-mailbox]")
        assert line.inner_text().strip() == "התקבל בתיבה: support@tryrozela.com"
        assert line.locator("bdi[dir=ltr]").inner_text() == "support@tryrozela.com"
        # the very bottom: the last element of the ticket body, below every card
        assert pg.locator(".tk-body > :last-child").get_attribute("data-test") == "tk-mailbox"
        box = line.bounding_box()
        assert box and box["width"] > 0
        cards_bottom = max(b["y"] + b["height"] for b in (c.bounding_box() for c in pg.locator(".tk-body > .card").all()) if b)
        assert box["y"] >= cards_bottom - 1
        # an email ticket with no mailbox: nothing
        pg.goto(base + "/cs#/b/rozela/t/t18f2a02")
        assert until(lambda: pg.locator(".tk-head h2").count() and "רונית" in pg.locator(".tk-head h2").inner_text())
        pg.wait_for_selector(".item-card")
        assert pg.locator("[data-test=tk-mailbox]").count() == 0
        # WhatsApp: nothing new — even if a mailbox ever came with a WhatsApp ticket
        import json

        def inject(route, req):
            resp = route.fetch()
            j = resp.json()
            if isinstance(j.get("extras"), dict):
                j["extras"]["mailbox"] = "support@tryrozela.com"
            route.fulfill(status=resp.status, headers=resp.headers, body=json.dumps(j))
        pg.route("**/api/rozela/ticket", inject)
        pg.goto(base + "/cs#/b/rozela/t/w8ab7700")
        pg.wait_for_selector("[data-test=wa-banner]")
        pg.wait_for_timeout(300)
        assert pg.locator("[data-test=tk-mailbox]").count() == 0
        browser.close()


# ---------------------------------------------------------------- 2. order links
def test_order_number_on_a_row_opens_shopify_search_and_not_the_ticket(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/rozela/ready")
        sel = ".row[data-id=t18f2a01] [data-test=row-order] a.order-link"
        pg.wait_for_selector(sel)
        a = pg.locator(sel)
        assert a.inner_text() == "#4512"
        assert a.get_attribute("href") == STORE + "?query=%234512"                # the row knows only the number
        assert a.get_attribute("target") == "_blank"
        assert set((a.get_attribute("rel") or "").split()) >= {"noopener", "noreferrer"}
        before = pg.evaluate("location.hash")
        with ctx.expect_page() as newp:
            a.click()
        newp.value.wait_for_load_state()
        assert newp.value.url == STORE + "?query=%234512"
        pg.wait_for_timeout(400)
        assert pg.evaluate("location.hash") == before                              # the row under it did not open
        assert pg.locator("body.view-ticket").count() == 0 or "/t/t18f2a01" not in pg.evaluate("location.hash")
        browser.close()


def test_order_number_in_the_ticket_opens_the_order_page_by_gid(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
        pg.wait_for_selector(".item-card .hd a.order-link")
        hrefs = pg.locator(".tk-body a.order-link").evaluate_all("els => els.map(e => e.getAttribute('href'))")
        # orders card (ship chip + the order's own card) and the details card: all the order's page, by its gid
        assert hrefs and set(hrefs) == {STORE + "/5004512"}, hrefs
        assert len(hrefs) >= 3
        with ctx.expect_page() as newp:
            pg.locator(".item-card .hd a.order-link").first.click()
        newp.value.wait_for_load_state()
        assert newp.value.url == STORE + "/5004512"
        # a ticket that has only an order number (no order lookup): the search by that number
        pg.goto(base + "/cs#/b/rozela/t/t18f2a11")
        assert until(lambda: pg.locator(".tk-body a.order-link").count() > 0)
        hrefs = set(pg.locator(".tk-body a.order-link").evaluate_all("els => els.map(e => e.getAttribute('href'))"))
        assert hrefs == {STORE + "?query=%234400"}, hrefs
        browser.close()


def test_no_myshopify_keeps_the_order_number_as_plain_text(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/apexmen/ready")                                     # the mock's apexmen has no myshopify
        pg.wait_for_selector(".row[data-id=tapex01] [data-test=row-order]")
        assert pg.locator(".row[data-id=tapex01] [data-test=row-order]").inner_text() == "#2210"
        assert pg.locator("a.order-link").count() == 0
        browser.close()


# ---------------------------------------------------------------- 3. AI notes
def note_ids(pg, base, brand):
    st, j = engine_api(pg, base, brand, "apiAiNotes")
    assert st == 200 and j["ok"], j
    return {n["id"]: n for n in j["notes"]}


def test_ai_notes_general_brand_partial_failure_and_delete(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "admin1")
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=ai-notes]")
        card = pg.locator("[data-test=ai-notes]")
        assert card.locator("h3").inner_text() == "שיפור ה-AI — הערות למנהלים"
        assert "ההערות נכנסות לכל טיוטה שה-AI כותב, מהטיוטה הבאה. הן לא גוברות על כללי המדיניות." in card.inner_text()
        opts = pg.locator("[data-test=ai-note-scope] option").evaluate_all("els => els.map(e => e.value)")
        assert opts == ["all"] + sorted(CONNECTED)
        assert "Velora" in pg.locator("[data-test=ai-note-not-conn]").inner_text()
        assert until(lambda: pg.locator("[data-test=ai-note-empty]").count() == 1)

        # a general note: once in the list, on every brand with ONE id
        text = "לא לפתוח ב'מצטערים על אי הנוחות' — לפתוח ישר בתשובה."
        pg.fill("[data-test=ai-note-text]", text)
        pg.click("[data-test=ai-note-add]")
        assert until(lambda: "נשמר בכל 4 המותגים" in pg.locator("[data-test=ai-note-status]").inner_text())
        assert until(lambda: pg.locator("[data-test=ai-group-all] [data-test=ai-note]").count() == 1)
        assert pg.locator("[data-test=ai-group-all] [data-test=ai-note] .ain-text").inner_text() == text
        assert pg.input_value("[data-test=ai-note-text]") == ""
        gid = pg.locator("[data-test=ai-group-all] [data-test=ai-note]").get_attribute("data-id")
        for b in CONNECTED:
            notes = note_ids(pg, base, b)
            assert gid in notes and notes[gid]["scope"] == "all" and notes[gid]["text"] == text and notes[gid]["by"] == "admin1", b
        assert "admin1" in pg.locator("[data-test=ai-group-all] .ain-meta").inner_text()

        # a brand note: only on that brand
        pg.fill("[data-test=ai-note-text]", "בסלרה: לא להבטיח זמן משלוח.")
        pg.select_option("[data-test=ai-note-scope]", "selera")
        pg.click("[data-test=ai-note-add]")
        assert until(lambda: "נשמר ל-Selera" in pg.locator("[data-test=ai-note-status]").inner_text())
        assert until(lambda: pg.locator("[data-test=ai-group-brand][data-brand=selera] [data-test=ai-note]").count() == 1)
        bid = pg.locator("[data-test=ai-group-brand][data-brand=selera] [data-test=ai-note]").get_attribute("data-id")
        assert note_ids(pg, base, "selera")[bid]["scope"] == "brand"
        for b in ("rozela", "celesta", "apexmen"):
            assert bid not in note_ids(pg, base, b)
        assert pg.locator("[data-test=ai-group-all] [data-test=ai-note]").count() == 1   # the general one is still listed once

        # one brand fails: said by name, the note shows where it is missing, and "complete" finishes it with the same id
        pg.route("**/api/selera/apiAiNoteAdd", lambda r: r.fulfill(status=504, content_type="application/json",
                                                                    body='{"ok": false, "error": "engine_timeout", "msg": "timeout"}'))
        pg.select_option("[data-test=ai-note-scope]", "all")
        pg.fill("[data-test=ai-note-text]", "לחתום תמיד בשם הפרטי בלבד.")
        pg.click("[data-test=ai-note-add]")
        assert until(lambda: "נשמר ב-3 מתוך 4 מותגים — נכשל: Selera" in pg.locator("[data-test=ai-note-status]").inner_text())
        assert until(lambda: pg.locator("[data-test=ai-note-missing]").count() == 1)
        assert "Selera" in pg.locator("[data-test=ai-note-missing]").inner_text()
        assert pg.locator("[data-test=ai-group-all] [data-test=ai-note]").count() == 2
        pid = pg.locator("[data-test=ai-note-missing]").locator("xpath=ancestor::li").get_attribute("data-id")
        assert pid not in note_ids(pg, base, "selera")
        pg.unroute("**/api/selera/apiAiNoteAdd")
        pg.click("[data-test=ai-note-fill]")
        assert until(lambda: pg.locator("[data-test=ai-note-missing]").count() == 0)
        for b in CONNECTED:
            assert pid in note_ids(pg, base, b), b
        assert pg.locator("[data-test=ai-group-all] [data-test=ai-note]").count() == 2

        # delete a general note: two separate clicks, gone from every brand
        btn = pg.locator("[data-test=ai-group-all] [data-test=ai-note][data-id=\"%s\"] [data-test=ai-note-del]" % gid)
        btn.click()
        pg.wait_for_timeout(600)
        btn.click()
        assert until(lambda: pg.locator("[data-test=ai-note][data-id=\"%s\"]" % gid).count() == 0)
        assert "נמחק" in pg.locator("[data-test=ai-note-status]").inner_text()
        for b in CONNECTED:
            assert gid not in note_ids(pg, base, b), b
        # delete the brand note
        btn = pg.locator("[data-test=ai-note][data-id=\"%s\"] [data-test=ai-note-del]" % bid)
        btn.click()
        pg.wait_for_timeout(600)
        btn.click()
        assert until(lambda: pg.locator("[data-test=ai-group-brand]").count() == 0)
        assert bid not in note_ids(pg, base, "selera")
        browser.close()


def test_dashboard_refresh_never_rebuilds_the_note_being_typed(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "admin1")
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=ai-note-text]")
        pg.fill("[data-test=ai-note-text]", "טיוטה של הערה באמצע הקלדה")
        pg.focus("[data-test=ai-note-text]")
        h0 = pg.locator("[data-test=ai-note-text]").element_handle()
        pg.click("[data-test=range-7]")                                            # rebuilds every number on the dashboard
        pg.wait_for_selector("[data-test=range-7][aria-pressed=true]")
        pg.wait_for_timeout(500)
        assert pg.input_value("[data-test=ai-note-text]") == "טיוטה של הערה באמצע הקלדה"
        assert h0.evaluate("e => e.isConnected")                                   # the same element, never rebuilt
        browser.close()


def test_non_admin_sees_no_card_and_the_proxy_refuses(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "mgr1")                             # a user manager sees the dashboard...
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=range-1]")
        pg.wait_for_timeout(800)
        assert pg.locator("[data-test=ai-notes]").count() == 0                     # ...but not the AI card
        assert pg.locator("[data-test=ai-notes-jump]").count() == 0
        for fn, args in (("apiAiNotes", {}), ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "x"}),
                         ("apiAiNoteDelete", {"id": "abcdef123456"})):
            st, j = engine_api(pg, base, "rozela", fn, args)
            assert st == 403 and j["error"] == "forbidden_role", (fn, st, j)
        browser.close()
        browser, ctx, pg = login(p, base, pwd, "agent1")
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector(".row")
        for fn, args in (("apiAiNotes", {}), ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "x"}),
                         ("apiAiNoteDelete", {"id": "abcdef123456"})):
            st, j = engine_api(pg, base, "rozela", fn, args)
            assert st == 403 and j["error"] == "forbidden_role", (fn, st, j)
        browser.close()


def test_deep_linked_ticket_gets_its_order_links_when_the_list_arrives(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        held, gate = [], {"open": False}

        def hold(route, req):                  # the brand's list (with myshopify) arrives AFTER the ticket was drawn
            if gate["open"]:
                route.continue_()
                return
            held.append(route)
        pg.route("**/api/rozela/list", hold)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
        pg.reload()
        pg.wait_for_selector(".item-card .hd bdi[data-order-brand=rozela]")
        assert until(lambda: bool(held))
        assert pg.locator(".tk-body a.order-link").count() == 0                   # no handle yet: plain text, no guessed link
        pg.fill(".draft textarea", "טקסט של הנציג")                               # the agent works meanwhile
        gate["open"] = True
        for r in held:
            r.continue_()
        assert until(lambda: pg.locator(".tk-body a.order-link").count() >= 3)
        hrefs = set(pg.locator(".tk-body a.order-link").evaluate_all("els => els.map(e => e.getAttribute('href'))"))
        assert hrefs == {STORE + "/5004512"}, hrefs
        assert pg.input_value(".draft textarea") == "טקסט של הנציג"              # upgraded in place: nothing rebuilt
        browser.close()


# ---------------------------------------------------------------- 4. one close button (Owner, 2026-10-11)
def test_one_close_without_sending_button_that_closes(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, ctx, pg = login(p, base, pwd, "agent1")
        calls = []
        pg.on("request", lambda r: calls.append(r.url.rsplit("/", 1)[-1]) if "/api/rozela/api" in r.url and r.method == "POST" else None)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a07")
        pg.wait_for_selector(".draft [data-test=send-btn]")
        acts = pg.locator(".draft .actions").first
        assert "טופל בלי שליחה" not in acts.inner_text()
        btn = pg.locator(".draft [data-test=close-btn]")
        assert btn.count() == 1 and btn.inner_text() == "סגירה בלי שליחה"
        assert btn.get_attribute("title") == "הפנייה נסגרת בלי לשלוח ללקוח. בוואטסאפ היא נסגרת גם בדונדי."
        btn.click()
        assert btn.inner_text() == "ללחוץ שוב לסגירה"
        pg.wait_for_timeout(600)
        btn.click()
        assert until(lambda: "apiClose" in calls)
        assert "apiMarkHandled" not in calls
        browser.close()
        browser, ctx, pg = login(p, base, pwd, "agent-en", path="/cs/en/login")      # the English desk: the same single button
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
        pg.wait_for_selector("[data-test=en-draft] [data-test=close-btn]")
        btn = pg.locator("[data-test=en-draft] [data-test=close-btn]")
        assert btn.count() == 1 and btn.inner_text() == "Close without sending"
        assert "Handled without sending" not in pg.locator("[data-test=en-draft]").inner_text()
        browser.close()
