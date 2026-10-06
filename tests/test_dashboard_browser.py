"""Managers' dashboard in a real browser: an agent never sees it; an admin sees real counters, KPIs, agents, charts."""
import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def test_agent_has_no_dashboard_tab_and_no_data(page):
    pg, base = page                                                  # agent1: role agent
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("#list-pane > a.row")
    assert pg.locator("[data-test=dash-link]").count() == 0
    pg.goto(base + "/cs#/dash")
    pg.wait_for_timeout(800)
    assert "/dash" not in pg.evaluate("location.hash") and pg.is_hidden("#dash-pane")
    st = pg.evaluate("async () => (await fetch('/api/dash')).status")
    assert st == 403


def test_admin_sees_live_numbers_from_real_actions(server):
    base, pwd = server
    from pw_launch import launch
    with pw.sync_playwright() as p:
        b = launch(p)
        # an agent works: opens a ticket, types, sends (mock engine, DRY_RUN off on rozela)
        ag = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
        ag.goto(base + "/cs/login"); ag.fill("input[name=username]", "agent1"); ag.fill("input[name=password]", pwd)
        ag.click("button[type=submit]"); ag.wait_for_load_state("networkidle")
        ag.goto(base + "/cs#/b/rozela/t/t18f2a11")
        ag.wait_for_selector(".draft textarea")
        ag.fill(".draft textarea", "היי אגי, ההזמנה בדרך — תגיע עד יום חמישי.")
        ag.click("[data-test=send-btn]"); ag.click("[data-test=send-btn]")
        ag.wait_for_timeout(2500)
        ad = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
        ad.goto(base + "/cs/login"); ad.fill("input[name=username]", "admin1"); ad.fill("input[name=password]", pwd)
        ad.click("button[type=submit]"); ad.wait_for_load_state("networkidle")
        ad.goto(base + "/cs#/b/rozela/ready")
        ad.wait_for_selector("[data-test=dash-link]")
        ad.click("[data-test=dash-link]")
        ad.wait_for_selector("[data-test=dash-brand][data-brand=rozela]")
        assert ad.inner_text("[data-test=dash-brand][data-brand=rozela] [data-test=ov-awaiting] b") not in ("", "0")
        assert int(ad.inner_text("[data-test=dash-brand][data-brand=rozela] [data-test=ov-wafail] b")) >= 1
        row = ad.locator("[data-test=dash-agent][data-user=agent1]")
        assert row.count() == 1 and row.locator("[data-test=ag-replies] b").inner_text() == "1"
        assert "הנתונים בתיקון — לא סופיים" in ad.inner_text("[data-test=dash-fixing]")        # before dayStats has landed            # one reply (engine + log agree)
        assert "חסר" in ad.inner_text("[data-test=kpi-csat]") and "75–85%" in ad.inner_text("[data-test=kpi-occ]")
        assert ad.locator("[data-test=heatmap] .hc").count() >= 24 and ad.locator("[data-test=pie-channel] svg").count() == 1
        assert "פעילות במסך" in ad.inner_text("[data-test=dash-onscreen]")
        # dayStats is read in the background (rozela in two chunks): the next load shows the conversation numbers
        for _ in range(20):
            ad.reload()
            ad.wait_for_selector("[data-test=dash-brand][data-brand=rozela]")
            if ad.locator("[data-test=dash-brand][data-brand=rozela] [data-test=ov-from-conv]").count():
                break
            ad.wait_for_timeout(300)
        assert ad.locator("[data-test=dash-fixing]").count() == 0
        assert "אומת מול השיחות 15/15" in ad.inner_text("[data-test=dash-verify]")
        assert ad.inner_text("[data-test=dash-brand][data-brand=rozela] [data-test=ov-answered] .v") == "5"
        assert ad.inner_text("[data-test=src-answered-total] .v") == "5"
        assert "לפני" in ad.inner_text("[data-test=dash-brand][data-brand=rozela] [data-test=ov-from-conv]")   # the numbers' age
        card = "[data-test=dash-brand][data-brand=rozela] "
        assert ad.inner_text(card + "[data-test=ov-frt] b") == "37 דק׳" and "מענה ראשון של אדם" in ad.inner_text(card + "[data-test=ov-frt]")
        assert "כולל בוט: 0 שנ׳" in ad.inner_text(card + "[data-test=ov-frt-bot]")
        import json as _json

        def blocked(route, req):
            r = route.fetch(); j = r.json()
            j["brands"]["rozela"]["email_status"] = "gmail_blocked"
            route.fulfill(response=r, body=_json.dumps(j))
        ad.route("**/api/dash*", blocked)
        ad.reload()
        ad.wait_for_selector(card + "[data-test=ov-mail-blocked]")
        assert ad.inner_text(card + "[data-test=ov-mail-blocked]") == "מייל: גוגל חסם זמנית — יתעדכן"
        assert ad.inner_text("[data-test=src-answered] [data-test=src-mail-off]") == "—"
        ad.unroute("**/api/dash*")
        ad.reload()
        ad.wait_for_selector(card + "[data-test=ov-from-conv]")
        assert ad.inner_text("[data-test=src-answered-fromDondy] .v") == "1" and "אדם 1" in ad.inner_text("[data-test=src-answered-fromDondy]")
        assert ad.inner_text("[data-test=src-closed-fromDondy] .v") == "1" and "סגירה 1" in ad.inner_text("[data-test=src-closed-fromDondy]")
        assert ad.locator("[data-test=src-answered] svg.donut").count() == 1
        assert ad.inner_text("[data-test=dash-agent][data-user=agent1] [data-test=ag-conv]") == "2"
        assert "ישירות בדונדי 1" in ad.inner_text("[data-test=dash-direct]")
        ad.route("**/api/dash?range=1*", lambda route, req: (__import__("time").sleep(1.5), route.continue_()))   # an old answer, late
        ad.evaluate("() => document.querySelector('[data-test=range-1]').click()")
        ad.click("[data-test=range-7]")
        ad.wait_for_selector("[data-test=heat-who]")
        ad.wait_for_timeout(2500)                                                          # the late range-1 answer has landed
        assert " – " in ad.inner_text("[data-test=dash-shown]") and ad.locator("[data-test=heat-who]").count() == 1
        ad.unroute("**/api/dash?range=1*")
        b.close()


def test_service_hours_block_shows_who_got_no_answer_and_opens_the_ticket(server):
    """Owner, 2026-10-07: every ticket written to before the desk closed (17:00) — answered or not, and the unanswered ones are links."""
    base, pwd = server
    from pw_launch import launch
    with pw.sync_playwright() as p:
        b = launch(p)
        ad = b.new_context(viewport={"width": 390, "height": 800}).new_page()
        ad.goto(base + "/cs/login"); ad.fill("input[name=username]", "admin1"); ad.fill("input[name=password]", pwd)
        ad.click("button[type=submit]"); ad.wait_for_load_state("networkidle")
        ad.goto(base + "/cs#/dash")
        for _ in range(30):                                          # dayStats lands in the background
            ad.wait_for_selector("[data-test=dash-brand]")
            if ad.locator("[data-test=service-table] tr[data-brand=rozela]").count():
                break
            ad.wait_for_timeout(300); ad.reload()
        assert "17:00" in ad.inner_text("[data-test=service] h3") and "17:00" in ad.inner_text("[data-test=service-def]")
        n = ad.locator("[data-test=service-table] tbody tr").count()
        assert n >= 1
        assert ad.inner_text("[data-test=service-received] .v") == str(5 * n) and ad.inner_text("[data-test=service-unanswered] .v") == str(n)
        assert "bad" in ad.get_attribute("[data-test=service-unanswered]", "class")
        row = ad.locator("[data-test=service-table] tr[data-brand=rozela] td")
        assert row.nth(1).inner_text().startswith("5") and row.nth(2).inner_text().startswith("1")     # received, then unanswered
        assert ad.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") == 0
        det = ad.locator("[data-test=service-list][data-brand=rozela]")
        assert "1" in det.locator("summary").inner_text()
        det.locator("summary").click()
        link = det.locator("[data-test=service-ticket]")
        assert link.count() == 1 and any(x in link.inner_text() for x in ("16:05", "15:05"))        # 13:05Z in Israel (summer / winter time)
        link.click()
        ad.wait_for_function("location.hash.indexOf('#/b/rozela/t/') === 0")
        ad.wait_for_selector(".ticket-pane, #ticket-pane")
        assert ad.is_hidden("#dash-pane")
