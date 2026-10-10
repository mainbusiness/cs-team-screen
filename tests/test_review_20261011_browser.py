"""Front review 2026-10-11 (option 2), reproduced in a real browser: each test fails on the code before the fix."""
import json

from test_resilience_browser import server  # noqa: F401

from pw_launch import launch, pw  # noqa: E402

A, B = "t18f2a01", "t18f2a03"


def login(p, base, pwd, width=1280):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", "agent1")
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.calls = []
    pg.on("request", lambda r: pg.calls.append(r.url.rsplit("/", 1)[-1]) if "/api/rozela/api" in r.url and r.method == "POST" else None)
    return browser, pg


def until(cond, ms=8000):                      # the page's CSP forbids eval, so no wait_for_function
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def confirm_click(pg, sel):                    # two separate clicks, as a person does them
    pg.click(sel)
    pg.wait_for_timeout(600)
    pg.click(sel)


def test_1_an_edited_draft_survives_an_older_server_copy(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/t/" + A)
        pg.wait_for_selector(".draft textarea")
        pg.goto(base + "/cs#/b/rozela/t/" + B)                                      # A is now in the page's memory
        pg.wait_for_selector(".tk-head h2")
        held = []

        def hold(route, req):                  # the engine's copy of A, read BEFORE the agent's save, arrives AFTER it
            body = req.post_data_json or {}
            if body.get("id") == A and not held and not body.get("revalidate"):
                held.append((route, route.fetch()))
                return
            route.continue_()
        pg.route("**/api/rozela/ticket", hold)
        pg.goto(base + "/cs#/b/rozela/t/" + A)                                      # shown from memory at once
        pg.wait_for_selector(".draft textarea")
        for _ in range(100):
            if held:
                break
            pg.wait_for_timeout(20)
        assert held
        old = pg.input_value(".draft textarea")
        mine = "טקסט שהנציג ערך ונשמר"
        pg.fill(".draft textarea", mine)
        with pg.expect_response(lambda r: r.url.endswith("/apiSaveDraft")):
            pg.click(".tk-head h2")                                                 # blur -> save now
        pg.wait_for_timeout(200)
        route, resp = held[0]
        j = resp.json()
        assert j["ticket"]["draft_text"] == old                                     # the copy really is older than the save
        j["ticket"]["summary"] = (j["ticket"].get("summary") or "") + " ·"          # newer than the memo, older than the save
        route.fulfill(status=resp.status, headers=resp.headers, body=json.dumps(j))
        pg.wait_for_timeout(1200)
        assert pg.input_value(".draft textarea") == mine
        browser.close()


def test_9_cancel_lights_only_with_the_right_four_digits(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/t/" + B)
        pg.wait_for_selector(".item-card .btn.danger-outline")
        pg.click(".item-card .btn.danger-outline")
        pg.wait_for_selector("#cancel-dlg input.code")
        num = pg.inner_text("#cancel-dlg .small.muted bdi.ltr").strip()
        last4 = num[-4:]
        wrong = "0000" if last4 != "0000" else "1111"
        go = pg.locator("#cancel-dlg .btn.danger")
        pg.fill("#cancel-dlg input.code", wrong)
        assert go.is_disabled()
        pg.fill("#cancel-dlg input.code", last4)
        assert go.is_enabled()
        browser.close()


def test_2_a_double_click_never_sends(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/t/" + B)
        pg.wait_for_selector("[data-test=send-btn]")
        pg.dblclick("[data-test=send-btn]")
        pg.wait_for_timeout(400)
        assert "apiSend" not in pg.calls
        assert "arm" in (pg.get_attribute("[data-test=send-btn]", "class") or "")  # still waiting for the confirm
        pg.wait_for_timeout(300)
        pg.click("[data-test=send-btn]")                                            # a real second click still sends
        pg.wait_for_timeout(400)
        assert pg.calls.count("apiSend") == 1
        browser.close()


def test_3_the_last_hand_off_leaves_no_send_button_behind(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector(".tab.search")
        pg.click(".tab.search")                                                     # no "next ticket" from search
        pg.wait_for_selector(".search-box input")
        pg.fill(".search-box input", "מיכל")
        pg.wait_for_selector(".results a.row[data-id=%s]" % A)
        pg.click(".results a.row[data-id=%s]" % A)
        pg.wait_for_selector(".draft textarea")
        pg.fill(".draft textarea", "היי, ההזמנה בדרך.")
        confirm_click(pg, "[data-test=send-btn]")
        pg.wait_for_selector("#ticket-pane .placeholder", timeout=4000)
        pg.wait_for_timeout(1500)                                                   # the reply lands: nothing to click again
        assert pg.locator("[data-test=send-btn]").count() == 0
        assert pg.calls.count("apiSend") == 1
        browser.close()


def test_6_a_double_enter_saves_one_note(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a04")
        pg.wait_for_selector(".note-add input")
        pg.fill(".note-add input", "הערה פנימית לבדיקה")
        pg.focus(".note-add input")
        pg.keyboard.press("Enter")
        pg.keyboard.press("Enter")
        pg.wait_for_timeout(1200)
        assert pg.calls.count("apiNote") == 1
        assert pg.input_value(".note-add input") == ""
        browser.close()


def test_7_search_says_searching_until_the_archive_answers(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        held = []
        pg.route("**/api/rozela/apiSearch", lambda route, req: held.append(route))
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector(".tab.search")
        pg.click(".tab.search")
        pg.wait_for_selector(".search-box input")
        pg.fill(".search-box input", "zzqqxxnothing")
        pg.wait_for_selector(".results .empty b")
        assert pg.inner_text(".results .empty b") == "מחפש בארכיון…"
        for _ in range(100):
            if held:
                break
            pg.wait_for_timeout(20)
        held[-1].fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "tickets": []}))
        assert until(lambda: pg.locator(".results .empty b").count() and pg.inner_text(".results .empty b") == "לא נמצא כלום")
        browser.close()


def test_8_a_template_load_failure_offers_a_retry(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, pwd)
        pg.route("**/api/rozela/apiTemplates", lambda route, req: route.fulfill(status=200, content_type="application/json",
                                                                               body=json.dumps({"ok": False, "error": "engine_timeout"})))
        pg.goto(base + "/cs#/b/rozela/t/w8ab77f2")
        pg.wait_for_selector("[data-test=tpl-retry]")
        assert "לא נמצאו תבניות" not in pg.inner_text("[data-test=tpl-status]")
        pg.unroute("**/api/rozela/apiTemplates")
        pg.click("[data-test=tpl-retry]")
        assert until(lambda: pg.locator("[data-test=tpl-select] option").count() > 0 and pg.locator("[data-test=tpl-select]").is_visible())
        browser.close()
