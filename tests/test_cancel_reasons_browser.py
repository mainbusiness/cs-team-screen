"""Why customers cancel a subscription, on the managers' board in a real browser against the mock engine (Owner, 2026-11-01)."""
import pytest

from browser_server import start
from pw_launch import launch, pw

USERS = (("guy", ["admin"], ["rozela", "celesta", "apexmen", "selera"], "he"), ("agent-two", ["agent"], ["rozela", "celesta"], "he"),
         ("amit", ["admin"], ["rozela", "celesta"], "en"))


@pytest.fixture(scope="module")
def srv():
    base, pwd, proc = start(extra_env={}, users=USERS)
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


def rows(pg):
    return {r.get_attribute("data-k"): int(r.locator("[data-test=cr-n]").inner_text()) for r in pg.locator("[data-test=cr-row]").all()}


@pytest.mark.parametrize("width", [1280, 390])
def test_admin_sees_the_five_reasons_all_brands_then_one_brand_then_all_data(srv, width):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy", width)
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=cr-table]", timeout=30000)
        sec = pg.locator("[data-test=cr]")
        txt = sec.inner_text()
        for bad in ("null", "undefined", "NaN", "[object", "{b}", "{d}", "{r}", "{s}", "{t}", "{m}"):
            assert bad not in txt, (bad, txt[:500])
        assert "5 הסיבות המרכזיות" in txt and "הריצה הבאה: שישי 6.11 ב-02:00" in txt
        # all brands (the mock: rozela + celesta + apexmen; selera has no subscriptions), the newest week 23.10-29.10
        assert "שבוע 23.10–29.10" in sec.locator("[data-test=cr-range]").inner_text()
        r = rows(pg)
        assert r["never_agreed"] == 56 and r["one_time"] == 11 and r["other_not_stated"] == 3 + 8
        order = [x.get_attribute("data-k") for x in pg.locator("[data-test=cr-row]").all()]
        assert order[0] == "never_agreed" and order[-1] == "other_not_stated" and len(order) == 6     # five + "other / not stated", always shown
        assert "נקראו 98 שיחות, מתוכן 92 בקשות לבטל מנוי" in sec.locator("[data-test=cr-read]").inner_text()
        assert sec.locator("[data-test=cr-row][data-k=never_agreed] [data-test=cr-pct]").inner_text() == "60.9%"
        assert sec.locator("[data-test=cr-row][data-k=never_agreed] [data-test=cr-change]").inner_text() == "+16 · ↑7.6 נק׳"
        assert "בשבוע הקודם אין נתונים מ: ApexMen" in sec.locator("[data-test=cr-prev-missing]").inner_text()   # apexmen has one week only: said, not hidden
        assert "לא הזמנתי מנוי" in sec.locator("[data-test=cr-row][data-k=never_agreed]").inner_text()
        assert "אחר 3 · לא צוין 8" in sec.locator("[data-test=cr-other-split]").inner_text()
        assert "בדיקה ידנית של 25 שיחות" in sec.locator("[data-test=cr-how]").inner_text()
        # one brand
        pg.select_option("[data-test=cr-brand]", "rozela")
        assert rows(pg)["never_agreed"] == 40
        assert sec.locator("[data-test=cr-row][data-k=never_agreed] [data-test=cr-change]").inner_text() == "+10 · ↑8.9 נק׳"
        # all the data
        pg.select_option("[data-test=cr-period]", "all")
        assert rows(pg)["never_agreed"] == 70 and "מ-16.10 עד 29.10" in sec.locator("[data-test=cr-range]").inner_text()
        assert sec.locator("[data-test=cr-row][data-k=never_agreed] [data-test=cr-change]").inner_text() == "—"
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert pg.errors == []


def test_english_desk_and_an_agent_never_sees_it(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "amit", 1280, "/cs/en")
        pg.goto(base + "/cs/en#/dash")
        pg.wait_for_selector("[data-test=cr-table]", timeout=30000)
        t = pg.locator("[data-test=cr]").inner_text()
        assert "the top 5 reasons" in t and "Next run: Friday 6.11 at 02:00" in t and "Other / not stated" in t
        ag = login(p, base, pwd, "agent-two")
        ag.goto(base + "/cs#/dash")
        ag.wait_for_timeout(2500)
        assert ag.locator("[data-test=cr]").count() == 0
