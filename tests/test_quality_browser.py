"""Owner, 2026-11-12 — the managers' board: the most important first, the rest in "נתונים נוספים"; the CS manager's daily sampled quality check.
Real browser, mock engines, a pre-written activity log (two agents' sends / a close with no reply):
 - the main tab holds the SLA (response times), the quality card, the live strip and the brand cards; cancellations, the sales table, the AI
   notes and the system requests are NOT visible there, and ARE in "נתונים נוספים" (moved, not deleted);
 - a manager gets the banner on every screen while today's check is open; one click opens the check;
 - the check: items grouped by brand, the closed-with-no-reply item first for its agent, the first unrated one open with the conversation;
   rating needs a score + four answers; "finish" stays disabled until every item is rated, then the banner is gone and the card says done;
 - the end-of-day reminder modal (QUALITY_REMIND_HOUR=0): "later" closes it and a reload in the same tab does not bring it back;
 - an agent sees no tab, no banner, and gets 403; no horizontal overflow at 390 / 1280; no console errors.
"""
import json
import os
import tempfile
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
TZ = ZoneInfo("Asia/Jerusalem")
SHOTS = os.environ.get("QUALITY_SHOTS_DIR")


def write_log(d):
    now = time.time()
    day = datetime.fromtimestamp(now, TZ).date().isoformat()
    ev = []

    def e(u, b, t, k, ago):
        ev.append({"ts": round(now - ago, 3), "u": u, "b": b, "t": t, "ch": "email", "k": k, "cat": "shipping"})
    e("agent1", "rozela", "t18f2a04", "send", 300)          # untouched
    e("agent1", "rozela", "t18f2a03", "edit", 260)
    e("agent1", "rozela", "t18f2a03", "send", 240)          # typed first
    e("agent1", "rozela", "t18f2a05", "close", 200)         # closed, nobody answered
    e("agent2", "celesta", "t18f2a06", "send", 120)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "act-%s.jsonl" % day), "w") as f:
        f.write("\n".join(json.dumps(x) for x in ev) + "\n")


def start(remind_hour="24"):
    d = tempfile.mkdtemp(prefix="cs-quality-")
    write_log(os.path.join(d, "activity"))
    return browser_server.start(extra_env={"ACTIVITY_DIR": os.path.join(d, "activity"), "QUALITY_PATH": os.path.join(d, "quality.json"),
                                           "QUALITY_REMIND_HOUR": remind_hour},
                                users=(("agent-two", ["admin", "user-manager"], ALL, "he"), ("agent1", ["agent"], ["rozela"], "he"),
                                       ("agent2", ["agent"], ["celesta"], "he")))


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = start()
    yield base, pwd
    proc.terminate()
    proc.wait(timeout=10)


def login(p, base, pwd, user, width=1280):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}, locale="he-IL", timezone_id="Asia/Jerusalem").new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def no_overflow(pg):
    return pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_main_tab_is_the_decision_view_and_the_rest_moved(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        for width in (1280, 390):
            browser, pg, errors = login(p, base, pwd, "agent-two", width)
            pg.goto(base + "/cs#/dash")
            pg.wait_for_selector("[data-test=dash-pane-main] [data-test=sla]")
            pg.wait_for_selector("[data-test=quality-sum] [data-test=quality-status]")
            pg.wait_for_selector("[data-test=dash-pane-main] [data-test=dash-live]")
            pg.wait_for_selector("[data-test=dash-pane-main] [data-test=dash-brand]")
            order = pg.evaluate("""() => ['sla', 'quality-sum', 'dash-live'].map(t => { const el = document.querySelector('#dash-main [data-test=' + t + ']');
                return el ? el.getBoundingClientRect().top : -1; })""")
            assert order[0] >= 0 and order[0] < order[1] < order[2], order
            for sel in ("cx", "cr", "bh", "sales-table", "ai-notes", "sysreq", "dash-agents", "dash-onscreen"):
                loc = pg.locator("[data-test=%s]" % sel)
                assert not any(loc.nth(i).is_visible() for i in range(loc.count())), "%s visible on the main tab" % sel
            assert no_overflow(pg), width
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "dash_main_%d.png" % width), full_page=True)
            pg.click("[data-test=dash-tab-more]")
            assert pg.url.endswith("#/dash/more")
            for sel in ("cx", "cr", "bh", "ai-notes", "sysreq", "dash-agents"):
                pg.wait_for_selector("[data-test=dash-pane-more] [data-test=%s]" % sel, state="visible", timeout=15000)
            assert pg.locator("[data-test=dash-pane-main]").is_hidden()
            assert no_overflow(pg), width
            pg.click("[data-test=dash-tab-main]")
            pg.wait_for_selector("[data-test=dash-pane-main] [data-test=sla]", state="visible")
            assert not errors, errors
            browser.close()


def test_agent_sees_nothing_of_it(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "agent1", 390)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("a.row")
        pg.wait_for_timeout(500)
        assert pg.locator("[data-test=quality-banner]").count() == 0
        r = pg.evaluate("async () => (await fetch('/api/dash/quality/status')).status")
        assert r == 403
        pg.goto(base + "/cs#/dash/quality")
        pg.wait_for_timeout(500)
        assert "#/dash" not in pg.url and pg.locator("[data-test=dash-pane-quality]").count() == 0
        browser.close()


def test_banner_check_rate_finish(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "agent-two", 1280)
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("[data-test=quality-banner]")
        assert "בדיקה מדגמית של היום ממתינה" in pg.inner_text("[data-test=quality-banner]")
        pg.click("[data-test=quality-banner-go]")
        pg.wait_for_selector("[data-test=dash-pane-quality] [data-test=quality-item]")
        assert pg.locator("[data-test=quality-banner]").count() == 0, "no banner over the check itself"
        items = pg.locator("[data-test=quality-item]")
        assert items.count() == 4
        kinds = [items.nth(i).get_attribute("data-kind") for i in range(4)]
        keys = [items.nth(i).get_attribute("data-key") for i in range(4)]
        a1 = [k for k, key in zip(kinds, keys) if key.endswith(":agent1")]
        assert a1[0] == "closed", "the closed-with-no-reply item first for its agent"
        assert pg.locator("[data-test=q-untouched-chip]").count() == 2      # agent1 t18f2a04 + agent2 t18f2a06 (t18f2a03 was typed)
        fin = pg.locator("[data-test=quality-finish]").first
        assert fin.is_disabled()
        first = items.nth(0)
        first.locator("[data-test=q-form]").wait_for()
        pg.wait_for_selector("[data-test=quality-item] .q-view .q-msg, [data-test=quality-item] .q-view .note-box", timeout=15000)
        first.locator("[data-test=q-save]").click()
        assert "בחרו ציון" in first.inner_text()                     # nothing chosen: refused on the screen
        first.locator("[data-test=q-score-2]").click()
        first.locator("[data-test=q-save]").click()
        assert "בחרו ציון" in first.inner_text(), "a low score needs the four answers"
        for k in ("answered", "correct", "personal", "tone"):
            first.locator("[data-test=q-%s-false]" % k).click()
        first.locator("[data-test=q-note]").fill("סגרה בלי לענות")
        first.locator("[data-test=q-save]").click()
        pg.wait_for_selector("[data-test=quality-item][data-key='%s'] [data-test=q-badge]:has-text('2')" % keys[0])
        for i in range(1, 4):
            it = items.nth(i)
            it.locator("[data-test=q-form]").wait_for(state="visible", timeout=15000)   # the next unrated one opens by itself
            it.locator("[data-test=q-score-5]").click()                                  # a 5 answers the four questions "yes"
            it.locator("[data-test=q-save]").click()
            pg.wait_for_selector("[data-test=quality-item][data-key='%s'] [data-test=q-badge]:has-text('5')" % keys[i])
        assert not fin.is_disabled()
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, "quality_rated_1280.png"), full_page=True)
        fin.click()
        pg.wait_for_selector("[data-test=quality-finished]")
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("a.row")
        pg.wait_for_timeout(600)
        assert pg.locator("[data-test=quality-banner]").count() == 0
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=quality-status][data-state=done]")
        row = pg.locator("[data-test=quality-agent][data-user=agent1] [data-test=q-score]").inner_text()
        assert row == "4.0 / 5 (3)", row                                                # agent1's three items: (2 + 5 + 5) / 3
        assert not errors, errors
        browser.close()


def test_end_of_day_reminder_modal():
    base, pwd, proc = start(remind_hour="0")
    try:
        with pw.sync_playwright() as p:
            browser, pg, errors = login(p, base, pwd, "agent-two", 390)
            pg.goto(base + "/cs#/b/rozela/ready")
            pg.wait_for_selector("[data-test=quality-remind]", state="visible")
            assert "לוודא שהנציגים באמת עונים לכל פנייה" in pg.inner_text("[data-test=quality-remind]")
            assert no_overflow(pg)
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "quality_remind_390.png"))
            pg.click("[data-test=quality-remind-later]")
            assert pg.locator("[data-test=quality-remind]").is_hidden()
            pg.reload()
            pg.wait_for_selector("[data-test=quality-banner]")
            pg.wait_for_timeout(800)
            assert not pg.locator("[data-test=quality-remind]").is_visible(), "'later' holds for an hour, also after a reload"
            pg.evaluate("() => sessionStorage.clear()")
            pg.reload()
            pg.wait_for_selector("[data-test=quality-remind]", state="visible")
            pg.click("[data-test=quality-remind-go]")
            pg.wait_for_selector("[data-test=dash-pane-quality] [data-test=quality-item]")
            assert pg.url.endswith("#/dash/quality") and no_overflow(pg)
            if SHOTS:
                pg.screenshot(path=os.path.join(SHOTS, "quality_check_390.png"), full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
