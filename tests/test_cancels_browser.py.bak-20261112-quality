"""Cancellations on the managers' board in a real browser against the mock engine (Owner, 2026-10-23): admins see subscriptions the team cancels
per day and per agent, every cancellation the team makes, all Kaching cancels, and the monthly rate against the target (half of last month).
Agents and user-managers never see it; an engine without the fn says "not available yet" and the rest of the board still works."""
import os
import re

import pytest

from browser_server import start
from pw_launch import launch, pw

USERS = (("guy", ["admin"], ["rozela", "celesta", "apexmen", "selera"], "he"), ("agent-two", ["agent"], ["rozela", "celesta"], "he"),
         ("amit", ["agent"], ["rozela"], "en"), ("dan", ["user-manager"], ["rozela", "celesta"], "he"))
CX_FIELDS = ("subs_team", "subs_bot", "orders_cancelled", "team_total", "subs_all_kaching")


def boot(env=None):
    base, pwd, proc = start(extra_env=env or {}, users=USERS)
    return base, pwd, proc


@pytest.fixture
def srv():
    base, pwd, proc = boot()
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user, width=1280, path="/cs"):
    pg = launch(p).new_page(viewport={"width": width, "height": 1000})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(base + path + "/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def num(s):
    s = s.strip()
    return None if s == "—" else int(s)


def no_junk(pg, sel):
    txt = pg.inner_text(sel)
    for bad in ("null", "undefined", "NaN", "[object", "{b}", "{d}", "{m}", "{v}"):
        assert bad not in txt, (bad, txt[:400])
    return txt


@pytest.mark.parametrize("width,path", [(1280, "/cs"), (390, "/cs"), (1280, "/cs/en"), (390, "/cs/en")])   # both desks at phone width
def test_admin_sees_cancellations_per_day_agent_and_month(srv, width, path):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy", width, path)
        pg.goto(base + path + "#/dash")
        pg.wait_for_selector("[data-test=cx]")
        # the section sits right under the live strip, before the service-hours block
        order = pg.evaluate("() => { const a = document.querySelector('[data-test=dash-live]'), b = document.querySelector('[data-test=cx]');"
                            " return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING); }")
        assert order
        pg.wait_for_selector("[data-test=cx-month][data-brand=rozela] [data-test=cx-churn]", timeout=20000)
        pg.wait_for_selector("[data-test=cx-days]", timeout=20000)
        txt = no_junk(pg, "[data-test=cx]")
        # month vs the target BY PACE (the engine's 30-day number): rozela 6.5% (half of 14.1% = 7.0%), celesta over; selera is not shown
        assert pg.locator("[data-test=cx-month][data-brand=selera]").count() == 0
        roz = pg.locator("[data-test=cx-month][data-brand=rozela]")
        assert "good" in roz.get_attribute("class") and "6.5%" in roz.locator("[data-test=cx-pace]").inner_text()
        assert "7.0%" in roz.locator("[data-test=cx-target]").inner_text() and "14.1%" in roz.locator("[data-test=cx-prev]").inner_text()
        cel = pg.locator("[data-test=cx-month][data-brand=celesta]")
        assert "bad" in cel.get_attribute("class") and "8.8%" in cel.locator("[data-test=cx-target]").inner_text()
        if path == "/cs":
            assert "שיעור ביטול חודשי" in txt and "בריא מתחת ל-12%" in txt and "מצוין מתחת ל-8%" in txt and "בקצב הזה: מתחת ליעד" in roz.inner_text()
            assert "לפי הקצב" in txt and "בקצב הזה: 6.5% ל-30 יום" in roz.inner_text() and "מתעדכן כל 6 שעות" in roz.inner_text()
            assert roz.locator("[data-test=cx-pace]").get_attribute("data-from") == "engine"
            assert "אוקטובר" in roz.inner_text() or "נובמבר" in roz.inner_text() or re.search(r"[א-ת]+ עד היום", roz.inner_text())
        else:
            assert "Monthly cancel rate" in txt and "At this pace: below the target" in roz.inner_text()
        # the day: each total card = the sum of its column in the per-brand table; team total = team subs + orders
        rows = pg.locator("[data-test=cx-brand-table] tbody tr")
        assert rows.count() == 3
        for k in CX_FIELDS:
            col = [num(rows.nth(i).locator("td[data-k=%s]" % k).inner_text()) for i in range(rows.count())]
            card = num(pg.inner_text("[data-test=cx-%s] .v" % k))
            assert card == sum(c for c in col if c is not None), (k, card, col)
        for i in range(rows.count()):
            r = {k: num(rows.nth(i).locator("td[data-k=%s]" % k).inner_text()) for k in CX_FIELDS}
            assert r["team_total"] == r["subs_team"] + r["orders_cancelled"]
        # a source line under each number
        assert pg.locator("[data-test=cx-cards] [data-test=cx-src], .cx-cards [data-test=cx-src]").count() == 5
        # per agent: names from the board, the QA account is not an agent, the agents add up to the team's subscription cancels
        agents = pg.locator("[data-test=cx-agent]")
        users = sorted(agents.nth(i).get_attribute("data-user") for i in range(agents.count()))
        assert "qa-check" not in users and set(users) <= {"agent-two", "amit"}
        unnamed = int(pg.inner_text("[data-test=cx-unnamed]").split(":")[-1]) if pg.locator("[data-test=cx-unnamed]").count() else 0
        assert sum(int(agents.nth(i).locator("[data-test=cx-agent-n]").inner_text()) for i in range(agents.count())) + unnamed == num(pg.inner_text("[data-test=cx-subs_team] .v"))
        assert unnamed == 0                                  # the mock names every cancel; the QA account's cancel is out of the team's number
        # 14 days; picking another day moves the day block and its agents
        assert pg.locator("[data-test=cx-day]").count() == 14
        first = pg.locator("[data-test=cx-day]").first.get_attribute("data-day")
        assert "on" in (pg.locator("[data-test=cx-day]").first.get_attribute("class") or "")
        other = pg.locator("[data-test=cx-day]").nth(3)
        day = other.get_attribute("data-day")
        before = pg.inner_text("[data-test=cx-day-title]")
        other.locator("[data-test=cx-day-btn]").click()
        for _ in range(50):                                  # (no wait_for_function: the page's CSP forbids eval)
            if "on" in (pg.locator("[data-test=cx-day][data-day='%s']" % day).get_attribute("class") or ""):
                break
            pg.wait_for_timeout(200)
        assert "on" in (pg.locator("[data-test=cx-day][data-day='%s']" % day).get_attribute("class") or "")
        assert pg.inner_text("[data-test=cx-day-title]") != before and first != day
        allrow = {k: num(pg.locator("[data-test=cx-day][data-day='%s'] td[data-k=%s]" % (day, k)).inner_text()) for k in CX_FIELDS}
        assert allrow["subs_team"] == num(pg.inner_text("[data-test=cx-subs_team] .v"))
        # one brand in the 14-day table = that brand's row of the per-brand table for the chosen day
        pg.select_option("[data-test=cx-brand-sel]", "celesta")
        brow = pg.locator("[data-test=cx-brand-table] tbody tr[data-brand=celesta]")
        for k in CX_FIELDS:
            assert pg.locator("[data-test=cx-day][data-day='%s'] td[data-k=%s]" % (day, k)).inner_text() == brow.locator("td[data-k=%s]" % k).inner_text()
        # the 30 s board refresh does not rebuild the section (the brand choice survives)
        pg.evaluate("() => window.dispatchEvent(new Event('focus'))")
        pg.wait_for_timeout(300)
        assert pg.eval_on_selector("[data-test=cx-brand-sel]", "e => e.value") == "celesta"
        # phone width: the page itself never scrolls sideways
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        if os.environ.get("CX_SHOT_DIR"):                   # pixels for the human check (build-rules §3), off in the deploy gate
            pg.locator("[data-test=cx]").screenshot(path=os.path.join(os.environ["CX_SHOT_DIR"], "cx_%d%s.png" % (width, path.replace("/", "_"))))
        assert not pg.errors, pg.errors


@pytest.mark.parametrize("user", ["agent-two", "dan"])
def test_agents_and_user_managers_never_see_it(srv, user):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user)
        pg.goto(base + "/cs#/dash")
        pg.wait_for_timeout(1500)
        assert pg.locator("[data-test=cx]").count() == 0
        assert pg.evaluate("async () => (await fetch('/api/dash/cancels')).status") == 403
        csrf = pg.evaluate("() => (document.querySelector('meta[name=csrf]') || {}).content || ''")
        st = pg.evaluate("async c => (await fetch('/api/rozela/apiCancelStats', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': c},"
                         " body: JSON.stringify({args: {from: '2026-10-10', to: '2026-10-20'}})})).status", csrf)
        assert st == 403
        if user == "dan":                                    # the user-manager still has the board itself
            pg.wait_for_selector("[data-test=dash-live]")
        assert not pg.errors, pg.errors


def test_an_engine_without_the_fn_says_not_yet_and_the_board_still_works():
    base, pwd, proc = boot({"MOCK_CANCEL_STATS": "absent"})
    try:
        with pw.sync_playwright() as p:
            pg = login(p, base, pwd, "guy")
            pg.goto(base + "/cs#/dash")
            pg.wait_for_selector("[data-test=cx-unavailable]", timeout=20000)
            assert "עוד לא זמינים" in pg.inner_text("[data-test=cx-unavailable]")
            assert pg.locator("[data-test=cx-month]").count() == 0
            pg.wait_for_selector("[data-test=dash-brand][data-brand=rozela]")
            assert pg.locator("[data-test=live-brand]").count() >= 3
            assert not pg.errors, pg.errors
    finally:
        proc.terminate()


def test_a_kaching_copy_still_warming_says_so_instead_of_zeros():
    base, pwd, proc = boot({"MOCK_CANCEL_STATE": "rozela:warming"})
    try:
        with pw.sync_playwright() as p:
            pg = login(p, base, pwd, "guy")
            pg.goto(base + "/cs#/dash")
            pg.wait_for_selector("[data-test=cx-days]", timeout=20000)
            no_junk(pg, "[data-test=cx]")
            assert "קאצ׳ינג מתכונן" in pg.inner_text("[data-test=cx-month][data-brand=rozela]")
            assert any("קאצ׳ינג מתכונן" in t and "Rozela" in t for t in pg.locator("[data-test=cx-note]").all_inner_texts())
            assert pg.locator("[data-test=cx-brand-table] tr[data-brand=rozela] td[data-k=subs_all_kaching]").inner_text() == "—"
            assert "6 שעות" in pg.inner_text("[data-test=cx-month][data-brand=celesta]")            # a ready brand shows its copy's time
            assert not pg.errors, pg.errors
    finally:
        proc.terminate()


def test_no_kaching_and_kaching_errors_are_named_never_zero():
    base, pwd, proc = boot({"MOCK_CANCEL_STATE": "apexmen:no_kaching,celesta:error"})
    try:
        with pw.sync_playwright() as p:
            pg = login(p, base, pwd, "guy", 390)
            pg.goto(base + "/cs#/dash")
            pg.wait_for_selector("[data-test=cx-days]", timeout=20000)
            no_junk(pg, "[data-test=cx]")
            assert "אין חיבור לקאצ׳ינג" in pg.inner_text("[data-test=cx-month][data-brand=apexmen]")
            assert "קאצ׳ינג לא ענה" in pg.inner_text("[data-test=cx-month][data-brand=celesta]")
            # all Kaching cancels: only rozela knows it; the card names the brands that are missing instead of counting them as 0
            miss = pg.inner_text("[data-test=cx-subs_all_kaching] [data-test=cx-miss]")
            assert "Apex" in miss and "Celesta" in miss or "אייפקס" in miss
            cel = pg.locator("[data-test=cx-brand-table] tr[data-brand=celesta]")
            assert cel.locator("td[data-k=orders_cancelled]").inner_text() == "—" and cel.locator("td[data-k=team_total]").inner_text() == "—"
            assert pg.locator("[data-test=cx-brand-table] tr[data-brand=apexmen] td[data-k=subs_all_kaching]").inner_text() == "—"
            assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            assert not pg.errors, pg.errors
    finally:
        proc.terminate()
