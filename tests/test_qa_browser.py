"""Live QA fixes in a real browser: newest-first + old section, fact panel wording, siblings, tabs fit at 1280."""
import pytest

from test_resilience_browser import server  # noqa: F401

from pw_launch import launch, pw  # noqa: E402  (bundled Chromium, else installed Chrome)


def login(p, base, user, pwd, width=390):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 860}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg


def test_newest_first_and_old_section(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("[data-test=old-section]")
        visible = [a.get_attribute("data-id") for a in pg.locator("#list-pane > a.row").all()]
        assert visible and not any(i.startswith("w8ab7700") or i == "w8ab7701" for i in visible)   # 80+ days are not on top
        waits = [int(a.get_attribute("data-w")) for a in pg.locator("#list-pane > a.row").all()]
        assert len(waits) >= 2 and waits == sorted(waits, reverse=True)                # newest first
        det = pg.locator("[data-test=old-section]")
        assert det.get_attribute("open") is None and "ישנים (30+ יום)" in det.locator("summary").inner_text()
        assert det.locator("summary .n").inner_text() == "2"
        det.locator("summary").click()
        assert det.locator("a.row").count() == 2
        browser.close()


def test_fact_panel_wording_and_siblings(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a11")                                     # order chip, no stored orders
        pg.wait_for_selector(".ship-line")
        body = pg.inner_text("#ticket-pane")
        assert "רגיל עד" not in body and "איחור אחרי" not in body and "מאחר" in body
        assert "לא נמצאה הזמנה" not in body
        pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")                                     # WhatsApp, no email
        pg.wait_for_selector("[data-test=subs-empty]")
        assert pg.inner_text("[data-test=subs-empty]") == "מנויים: לא נבדק (אין מייל)"
        pg.goto(base + "/cs#/b/rozela/t/t18f2a03")
        pg.wait_for_selector("[data-test=siblings]")
        assert pg.inner_text("[data-test=siblings]") == "ללקוח יש עוד פנייה פתוחה אחת"
        pg.click("[data-test=siblings]")
        pg.wait_for_selector(".search-box input")
        assert pg.input_value(".search-box input") == "yossi.m@example.com"
        pg.wait_for_selector(".results .row")
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")                                     # no siblings field -> nothing
        pg.wait_for_selector(".tk-head h2")
        assert pg.locator("[data-test=siblings]").count() == 0
        browser.close()


@pytest.mark.parametrize("width", [1000, 1280])          # 1000 = narrowest desktop; live counts (218, 80) make tabs wider
def test_all_tabs_fit_at_1280(server, width):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd, width=width)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector(".tab.search")
        over = pg.evaluate("(() => { const t = document.getElementById('tabs'); return t.scrollWidth - t.clientWidth; })()")
        assert over <= 1
        box = pg.locator(".tab.search").bounding_box()
        assert box and 0 <= box["x"] and box["x"] + box["width"] <= width
        lp = pg.locator("#list-pane").bounding_box()                                  # the list pane fills the rest of the screen
        assert lp["y"] + lp["height"] <= 861
        browser.close()


def test_engine_notes_drive_the_fact_panel(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a11")                                     # notes: chip_only + subscriptions error
        pg.wait_for_selector("[data-test=orders-note]")
        assert pg.inner_text("[data-test=orders-note]") == "פרטי ההזמנה לא נשמרו"
        assert pg.inner_text("[data-test=subs-empty]") == "לא ניתן לבדוק כרגע"
        txt = pg.inner_text("#ticket-pane")
        assert "לא נמצאה הזמנה" not in txt and "undefined" not in txt and "רגיל עד" not in txt
        pg.goto(base + "/cs#/b/rozela/t/w8ab77c1")                                     # notes: not_checked_no_email
        pg.wait_for_selector("[data-test=subs-empty]")
        assert pg.inner_text("[data-test=subs-empty]") == "מנויים: לא נבדק (אין מייל)"
        assert pg.inner_text("[data-test=orders-note]") == "הזמנות: לא נבדק"
        pg.goto(base + "/cs#/b/rozela/search")                                         # merged = closed, labelled
        pg.fill(".search-box input", "michal.levi")
        pg.wait_for_selector(".results .row[data-id=t18f2a12] .chip.st-merged")
        assert pg.inner_text(".results .row[data-id=t18f2a12] .chip.st-merged") == "אוחד"
        browser.close()


def test_tab_counts_come_from_the_rows(server):
    """QA round 3: rozela showed Health 16 rows / count 0. Open-status counts are derived from the rows."""
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)

        def wrong_counts(route, request):
            resp = route.fetch()
            j = resp.json()
            if isinstance(j.get("counts"), dict):
                j["counts"] = {k: 0 for k in j["counts"]}                      # engine counts out of sync with rows
            route.fulfill(response=resp, body=__import__("json").dumps(j))
        pg.route("**/api/rozela/list", wrong_counts)
        pg.goto(base + "/cs#/b/rozela/action")
        pg.wait_for_selector("a.row")
        rows = pg.locator("#list-pane > a.row").count() + pg.locator("[data-test=old-section] a.row").count()
        assert pg.locator(".tab.action .n").inner_text() == str(rows)
        browser.close()


def test_bare_list_reply_keeps_the_last_good_list(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = login(p, base, "agent1", pwd)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("a.row")
        n = pg.locator("a.row").count()
        bare = lambda route, req: route.fulfill(status=200, content_type="application/json", body='{"ok": true}')
        for pat in ("**/api/rozela/list", "**/api/rozela/changes", "**/api/rozela/queue", "**/api/rozela/ticket"):
            pg.route(pat, bare)
        pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        pg.wait_for_timeout(800)
        assert pg.locator("a.row").count() == n and errs == []                  # no "0 tickets", no JS crash
        pg.goto(base + "/cs#/b/rozela/t/t18f2a02")
        pg.wait_for_timeout(1200)
        assert errs == []
        browser.close()
