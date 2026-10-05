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
        assert row.count() == 1 and row.locator("[data-test=ag-replies] b").inner_text() == "1"            # one reply (engine + log agree)
        assert "חסר" in ad.inner_text("[data-test=kpi-csat]") and "75–85%" in ad.inner_text("[data-test=kpi-occ]")
        assert ad.locator("[data-test=heatmap] .hc").count() >= 24 and ad.locator("[data-test=pie-channel] svg").count() == 1
        ad.click("[data-test=range-7]")
        ad.wait_for_selector("[data-test=heat-who]")
        b.close()
