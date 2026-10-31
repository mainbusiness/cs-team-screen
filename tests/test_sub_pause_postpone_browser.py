"""Owner, 2026-11-01: "a button to POSTPONE the subscription and a button to PAUSE it, from the interface itself, in all brands — pause for a period they
choose, or postpone for a period they choose, like in the Kaching app". Real browser against the mock engine (which mirrors Kaching.gs kachingPlan_)."""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from pw_launch import launch, pw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]


@pytest.fixture(scope="module")
def server():
    sys.path.insert(0, ROOT)
    import security
    from users_store import UserStore
    tmp = tempfile.mkdtemp(prefix="cs-pp-")
    users = os.path.join(tmp, "users.json")
    pwd = secrets.token_urlsafe(12) + "-Aa1"
    for name, lang in (("agent-all", "he"), ("agent-all-en", "en")):
        UserStore(users, os.path.join(tmp, "a.jsonl")).create("t", name, security.hash_password(pwd),
                                                              {"display_name": name, "roles": ["agent"], "brands": list(ALL), "lang": lang}, ALL, must_change=False)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=users, TRUSTED_PROXY_HOPS="0", MOCK_LATENCY_MS="0", ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1")
    import browser_server
    env.update(browser_server.preack_env(users))
    proc = subprocess.Popen([sys.executable, "-c", "from app import create_app;create_app().run(host='127.0.0.1',port=%d,threaded=True)" % port],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield base, pwd
    proc.terminate()


def _login(p, base, pwd, user="agent-all", width=390):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 844}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg


def _day(n):
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


def _he(n):
    """The screen's date for the mock's cycle at +n days (he-IL, Asia/Jerusalem, d.m.yy)."""
    d = datetime.now(timezone.utc) + timedelta(days=n)
    return "%d.%d.%s" % (d.day, d.month, d.strftime("%y"))


TK = {"rozela": ("t18f2a03", "0123")}           # the mock: rozela's cancel ticket; every other subscription brand has t<brand4>02 (contract …2223)


def _tk(brand):
    return TK.get(brand, ("t%s02" % brand[:4], "2223"))


def _ticket(pg, base, brand):
    pg.goto(base + "/cs#/b/%s/t/%s" % (brand, _tk(brand)[0]))
    pg.reload()                                  # a hash change to another brand is not a navigation: load the page for it
    pg.wait_for_selector("#subs-card .item-card")


def _no_overflow(pg):
    return pg.evaluate("""() => {
      const d = document.querySelector('#sub-dlg');
      return { page: document.documentElement.scrollWidth <= window.innerWidth + 1, dlg: !d || d.scrollWidth <= d.clientWidth + 1 };
    }""")


def test_buttons_on_every_subscription_brand_next_to_cancel_and_none_without_subscriptions(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        for brand in ("rozela", "celesta", "apexmen"):           # the mock has no velora engine; velora runs the same code (checked live, read-only)
            _ticket(pg, base, brand)
            cards = pg.locator("#subs-card .item-card")
            active = cards.filter(has_text="פעיל").first
            acts = active.locator(".actions button").all_inner_texts()
            assert acts == ["ניהול מנוי", "⏸ השהיית מנוי", "⏭ דחיית משלוח", "ביטול מנוי"], (brand, acts)
            if brand == "rozela":
                cancelled = cards.filter(has_text="מבוטל").first
                assert cancelled.locator(".actions button").all_inner_texts() == ["ניהול מנוי"]     # a cancelled one: no pause / postpone
        pg.goto(base + "/cs#/b/selera/t/tsele01")
        pg.reload()
        pg.wait_for_selector("#orders-card")
        pg.wait_for_timeout(1500)
        assert pg.locator("[data-test=sub-pause], [data-test=sub-postpone]").count() == 0      # no subscriptions in that brand
        browser.close()


def test_pause_for_two_months_skips_the_deliveries_before_the_return_and_stays_active(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        _ticket(pg, base, "rozela")
        pg.locator("[data-test=sub-pause]").first.click()
        dlg = pg.locator("[data-test=pp-dlg]")
        dlg.wait_for()
        assert "השהיית מנוי לתקופה" in dlg.inner_text()
        assert pg.is_disabled("[data-test=pp-next]")                          # nothing chosen yet
        for k in ("m1", "m2", "m3"):
            assert dlg.locator("[data-test=pp-preset-%s]" % k).is_visible()
        dlg.locator("[data-test=pp-preset-m2]").click()
        what = dlg.locator("[data-test=pp-what]").inner_text()
        # the mock's monthly cycles are at +28 / +58 / +88 / +118 days: two months from today skips +28 and +58, the first charge after is +88
        assert "לא יהיו חיובים ולא משלוחים" in what and "(2 משלוחים ידולגו)" in what, what
        assert "המנוי נשאר פעיל וחוזר לבד" in what
        assert _he(88) in what and _he(28) in what and _he(58) in what, what
        assert dlg.locator("[data-test=pp-preset-m2]").get_attribute("aria-pressed") == "true"
        assert _no_overflow(pg) == {"page": True, "dlg": True}
        dlg.locator("[data-test=pp-next]").click()
        pg.wait_for_selector("[data-test=mg-go]")
        assert "(2 משלוחים ידולגו)" in dlg.inner_text()                      # the confirm step shows the same "what will happen"
        assert pg.is_disabled("[data-test=mg-go]")
        pg.fill("#sub-dlg input.code", "0000")
        assert pg.is_disabled("[data-test=mg-go]")
        pg.fill("#sub-dlg input.code", "0123")
        pg.click("[data-test=mg-go]")
        res = dlg.locator("[data-test=pp-result]")
        res.wait_for()
        txt = res.inner_text()
        assert "בוצע ואומת בקאצ׳ינג" in txt and txt.count("✓ בוצע") == 2, txt
        assert _he(88) in txt                                                 # the next charge per Kaching now
        assert pg.locator("[data-test=mg-go]").count() == 0                   # never left on the confirm step
        dlg.locator("[data-test=pp-full]").click()                            # the full view: the two deliveries are skipped, the contract is still ACTIVE
        pg.wait_for_selector("[data-test=mg-cycle]")
        rows = pg.locator("[data-test=mg-cycle]").all_inner_texts()
        assert ["מדולג" in r for r in rows[:3]] == [True, True, False], rows
        assert "פעיל" in pg.locator("#sub-dlg").inner_text()
        browser.close()


def test_a_partial_failure_shows_every_step_and_leaves_nothing_to_click_again(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        crafted = {"ok": False, "action": "pause_until", "verified": False, "done": 1, "total": 2,
                   "message": "partial: 1 of 2 changes done, then Kaching refused (400): x. Not retried — check in Kaching before trying again.",
                   "msg": "בוצעו רק 1 מתוך 2 השינויים, ואז קצ'ינג סירב (שגיאה 400). לא נוסה שוב — לבדוק בקצ'ינג לפני כל ניסיון נוסף.",
                   "steps": [{"action": "skip", "index": 1, "date": _day(28) + "T09:00:00Z", "state": "done"},
                             {"action": "skip", "index": 2, "date": _day(58) + "T09:00:00Z", "state": "failed", "http": 400}]}
        pg.route("**/api/apexmen/apiKachingAction", lambda route, req: route.fulfill(status=200, content_type="application/json", body=json.dumps(crafted)))
        _ticket(pg, base, "apexmen")
        last4 = _tk("apexmen")[1]
        pg.locator("[data-test=sub-pause]").first.click()
        dlg = pg.locator("[data-test=pp-dlg]")
        dlg.wait_for()
        dlg.locator("[data-test=pp-preset-m2]").click()
        dlg.locator("[data-test=pp-next]").click()
        pg.fill("#sub-dlg input.code", last4)
        pg.click("[data-test=mg-go]")
        res = dlg.locator("[data-test=pp-result].err-box")
        res.wait_for()
        txt = res.inner_text()
        assert "לא בוצע עד הסוף" in txt and "בוצעו רק 1 מתוך 2" in txt and "✓ בוצע" in txt and "✗ קאצ׳ינג סירב" in txt, txt
        assert pg.locator("[data-test=mg-go]").count() == 0
        browser.close()


def test_a_stale_preview_is_refused_and_the_form_comes_back(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        stale = {"ok": False, "action": "postpone", "verified": False, "message": "the subscription changed since the preview — open it again",
                 "msg": "המנוי השתנה בקאצ'ינג מאז שנפתח החלון — לא בוצע כלום. פתחו שוב ובדקו."}
        pg.route("**/api/rozela/apiKachingAction", lambda route, req: route.fulfill(status=200, content_type="application/json", body=json.dumps(stale)))
        _ticket(pg, base, "rozela")
        last4 = _tk("rozela")[1]
        pg.locator("[data-test=sub-postpone]").first.click()
        dlg = pg.locator("[data-test=pp-dlg]")
        dlg.wait_for()
        dlg.locator("[data-test=pp-preset-w1]").click()
        dlg.locator("[data-test=pp-next]").click()
        pg.fill("#sub-dlg input.code", last4)
        pg.click("[data-test=mg-go]")
        dlg.locator("[data-test=pp-preset-w1]").wait_for()
        assert "לא בוצע כלום" in dlg.inner_text()
        assert pg.locator("[data-test=mg-go]").count() == 0
        browser.close()


def test_manage_dialog_names_the_open_pause_honestly_and_offers_the_period_pause(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        _ticket(pg, base, "apexmen")
        pg.locator("[data-test=manage-sub]").first.click()
        pg.wait_for_selector("[data-test=mg-cycle]")
        dlg = pg.locator("#sub-dlg")
        names = dlg.locator(".row-btns.start").first.locator("button").all_inner_texts()
        assert names[:3] == ["⏸ השהיית מנוי", "⏭ דחיית משלוח", "השהיה פתוחה (בלי תאריך חזרה)"], names
        dlg.get_by_role("button", name="⏸ השהיית מנוי").click()
        dlg.locator("[data-test=pp-preset-m1]").wait_for()
        assert dlg.locator("[data-test=pp-next]").is_disabled()            # inside the full dialog too, same form, nothing chosen yet
        browser.close()


def test_english_desk_has_the_same_buttons(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd, user="agent-all-en", width=1280)
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
        pg.reload()
        pg.wait_for_selector("#subs-card .item-card")
        acts = pg.locator("#subs-card .item-card").first.locator(".actions button").all_inner_texts()
        assert "⏸ Pause subscription" in acts and "⏭ Postpone delivery" in acts, acts
        pg.locator("[data-test=sub-postpone]").first.click()
        pg.locator("[data-test=pp-preset-w2]").click()
        assert "The next delivery moves from" in pg.locator("[data-test=pp-what]").inner_text()
        browser.close()
