"""מילוי מיקודים screen (Owner, 2026-10-10), in a real browser against the real zipfix routes + JobManager.

Only the runner (Shopify + zip sources) is faked: mock_engine.zipfix_runner, MOCK_ZIPFIX_STEP_MS per order.
Covers: entry button + brand/role restriction, one-click run with live progress (2 s polling), exact supplier text and
the copy button, review/ask lists with the Israel Post link, refresh mid-run resumes the same job, the error state,
a dropped poll during a deploy, junk input never becoming "all orders", LTR-safe boxes, and the English desk.
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

from pw_launch import launch, pw  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANDS = ["rozela", "celesta", "apexmen", "selera", "velora"]
RENDER_502 = "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>" + "x" * 2000 + "</body></html>"
STEP_MS = 300


@pytest.fixture(scope="module")
def server():
    sys.path.insert(0, ROOT)
    import security
    from users_store import UserStore
    tmp = tempfile.mkdtemp(prefix="cs-zip-")
    users = os.path.join(tmp, "users.json")
    pwd = secrets.token_urlsafe(12) + "-Aa1"
    st = UserStore(users, os.path.join(tmp, "a.jsonl"))
    for name, roles, brands, lang in [("agent1", ["agent"], ["rozela", "celesta"], "he"), ("solo", ["agent"], ["rozela"], "he"),
                                      ("mgr", ["user-manager"], ["rozela"], "he"), ("eve", ["agent"], ["rozela"], "en")]:
        st.create("t", name, security.hash_password(pwd), {"display_name": name, "roles": roles, "brands": brands, "lang": lang}, BRANDS,
                  must_change=False)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=users, TRUSTED_PROXY_HOPS="0", MOCK_LATENCY_MS="0",
               ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1", MOCK_ZIPFIX_STEP_MS=str(STEP_MS))
    code = ("import mock_engine;from app import create_app;"
            "create_app({'ZIPFIX_RUNNER': mock_engine.zipfix_runner, 'ZIPFIX_CONFIGURED': lambda b: True})"
            ".run(host='127.0.0.1',port=%d,threaded=True)" % port)
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    for _ in range(150):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield base, pwd
    proc.terminate()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = launch(p)
        yield b
        b.close()


def login(browser, base, pwd, user, width=1280):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="he-IL", timezone_id="Asia/Jerusalem")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "403" not in m.text and "404" not in m.text else None)
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return ctx, pg, errs


def until(pg, expr, timeout=10000):
    """Poll a page expression from Python (page.wait_for_function evals inside the page, which our CSP blocks for some forms)."""
    end = time.time() + timeout / 1000.0
    while time.time() < end:
        if pg.evaluate(expr):
            return
        pg.wait_for_timeout(100)
    raise AssertionError("timed out waiting for: " + expr)


def expected(nums):
    sys.path.insert(0, ROOT)
    import mock_engine
    old = os.environ.get("MOCK_ZIPFIX_STEP_MS")
    os.environ["MOCK_ZIPFIX_STEP_MS"] = "0"
    try:
        return mock_engine.zipfix_runner("rozela", nums)
    finally:
        if old is None:
            os.environ.pop("MOCK_ZIPFIX_STEP_MS", None)
        else:
            os.environ["MOCK_ZIPFIX_STEP_MS"] = old


def test_entry_button_and_brand_picker_only_my_brands(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "agent1")
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("[data-test=zip-link]")
    assert "מילוי מיקודים" in pg.inner_text("[data-test=zip-link]")
    pg.click("[data-test=zip-link]")
    pg.wait_for_selector("[data-test=zip-go]")
    assert pg.evaluate("location.hash") == "#/zip/rozela"
    opts = pg.eval_on_selector_all("[data-test=zip-brand] option", "os => os.map(o => o.value)")
    assert sorted(opts) == ["celesta", "rozela"]
    assert pg.inner_text("[data-test=zip-go]") == "הבא מיקודים"
    assert pg.locator("[data-test=zip-link]").count() == 0 and pg.is_hidden("#list-pane")
    # a brand that is not mine in the URL → back to one of mine; the server refuses it too
    pg.goto(base + "/cs#/zip/apexmen")
    until(pg, "location.hash === '#/zip/rozela'")
    st = pg.evaluate("""async () => { const r = await fetch('/api/apexmen/zipfix', {method: 'POST', headers: {'Content-Type': 'application/json',
        'X-CSRF-Token': document.querySelector('meta[name=csrf]').content}, body: JSON.stringify({orders: null})}); return [r.status, (await r.json()).error]; }""")
    assert st == [403, "forbidden_brand"]
    # switching brand in the picker moves the screen to that brand
    pg.select_option("[data-test=zip-brand]", "celesta")
    until(pg, "location.hash === '#/zip/celesta'")
    # also reachable from the menu
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector(".menu-btn")
    pg.click(".menu-btn")
    assert pg.locator("[data-test=zip-menu]").count() == 1
    assert not errs, errs
    ctx.close()


def test_user_manager_has_no_zip_screen(server, browser):
    base, pwd = server
    ctx, pg, _ = login(browser, base, pwd, "mgr")
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_timeout(700)
    assert not pg.evaluate("location.hash").startswith("#/zip") and pg.is_hidden("#zip-pane")
    assert pg.locator("[data-test=zip-link]").count() == 0
    st = pg.evaluate("""async () => (await fetch('/api/rozela/zipfix', {method: 'POST', headers: {'Content-Type': 'application/json',
        'X-CSRF-Token': document.querySelector('meta[name=csrf]').content}, body: JSON.stringify({orders: null})})).status""")
    assert st == 403
    ctx.close()


def test_one_click_run_progress_result_and_copy(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "solo")
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    polls, posts = [], []
    pg.on("request", lambda r: (polls if r.method == "GET" else posts).append(r.url) if "/zipfix" in r.url else None)
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    assert pg.inner_text("[data-test=zip-brand-one]") == "Rozela"          # one brand: shown, not a picker
    assert "כל ההזמנות הפתוחות" in pg.inner_text("[data-test=zip-parse]")
    nums = ["1646", "1647", "1649", "1653", "1660", "1661", "1662", "1663"]
    pg.fill("[data-test=zip-orders]", "#1646, 1647\n1649 1653 #1660,1661;1662 1663 1646")
    assert "זוהו 8 הזמנות" in pg.inner_text("[data-test=zip-parse]")
    pg.click("[data-test=zip-go]")
    pg.wait_for_selector("[data-test=zip-running]")
    assert pg.is_disabled("[data-test=zip-go]")
    until(pg, "document.querySelector('[data-test=zip-count]') && /\\d+ מתוך 8 הזמנות/.test(document.querySelector('[data-test=zip-count]').textContent)")
    until(pg, "/רץ \\d+ שנ׳/.test(document.querySelector('[data-test=zip-elapsed]').textContent)")
    pg.wait_for_selector("[data-test=zip-text]", timeout=20000)
    assert len(posts) == 1
    assert len(polls) >= 2                                                # polled, not one long wait
    exp = expected(nums)
    assert pg.input_value("[data-test=zip-text]") == exp["supplier_text"]
    assert pg.evaluate("getComputedStyle(document.querySelector('[data-test=zip-text]')).direction") == "ltr"
    assert pg.evaluate("getComputedStyle(document.querySelector('[data-test=zip-orders]')).direction") == "ltr"
    c = exp["counts"]
    for k in ("orders", "zips", "review", "ask"):
        assert pg.inner_text("[data-test=zip-c-%s] .v" % k) == str(c[k])
    rv = pg.locator("[data-test=zip-review-item]")
    assert rv.count() == len(exp["review"]) and rv.count() >= 1
    first = exp["review"][0]
    row = pg.locator("[data-test=zip-review-item][data-order='%s']" % first["order"])
    assert row.locator("[data-test=zip-zip]").inner_text() == first["zip"]
    assert row.locator("[data-test=zip-reason]").inner_text() == first["reason"]
    assert first["city"] in row.locator("[data-test=zip-addr]").inner_text() and first["address"] in row.locator("[data-test=zip-addr]").inner_text()
    link = row.locator("[data-test=zip-verify]")
    assert link.get_attribute("href") == "https://doar.israelpost.co.il/locatezip"
    assert link.get_attribute("target") == "_blank" and "noopener" in link.get_attribute("rel")
    assert pg.locator("[data-test=zip-ask-item]").count() == len(exp["ask_customer"]) >= 1
    assert pg.is_enabled("[data-test=zip-go]") and pg.inner_text("[data-test=zip-go]") == "הבא מיקודים"
    # copy: the exact text lands in the clipboard, and the button says so
    pg.evaluate("navigator.clipboard.writeText('sentinel')")
    pg.click("[data-test=zip-copy]")
    until(pg, "document.querySelector('[data-test=zip-copy]').textContent.indexOf('הועתק') >= 0")
    assert pg.evaluate("navigator.clipboard.readText()") == exp["supplier_text"]
    # the second path: Clipboard API refuses → execCommand still copies the exact text
    pg.evaluate("navigator.clipboard.writeText('sentinel')")
    pg.evaluate("(() => { const w = navigator.clipboard.writeText.bind(navigator.clipboard); window.__w = w;"
                " navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); })()")
    until(pg, "document.querySelector('[data-test=zip-copy]').textContent.indexOf('העתק לספקית') >= 0", 4000)
    pg.click("[data-test=zip-copy]")
    until(pg, "document.querySelector('[data-test=zip-copy]').textContent.indexOf('הועתק') >= 0")
    assert pg.evaluate("navigator.clipboard.readText()") == exp["supplier_text"]
    # the result survives a refresh (sessionStorage), with no new run
    pg.reload()
    pg.wait_for_selector("[data-test=zip-text]")
    assert pg.input_value("[data-test=zip-text]") == exp["supplier_text"] and len(posts) == 1
    pg.click("[data-test=zip-new]")
    assert pg.locator("[data-test=zip-text]").count() == 0
    assert not errs, errs
    ctx.close()


def test_refresh_mid_run_resumes_the_same_job(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "solo", width=390)
    posts = []
    pg.on("request", lambda r: posts.append(r.url) if "/zipfix" in r.url and r.method == "POST" else None)
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    pg.click("[data-test=zip-go]")                                        # empty box = all open orders (12 in the mock)
    until(pg, "/\\d+ מתוך 12 הזמנות/.test((document.querySelector('[data-test=zip-count]') || {}).textContent || '')")
    job = json.loads(pg.evaluate("sessionStorage.getItem('cs.zipfix.rozela')"))["job"]
    pg.reload()
    pg.wait_for_selector("[data-test=zip-running]")
    assert json.loads(pg.evaluate("sessionStorage.getItem('cs.zipfix.rozela')"))["job"] == job
    pg.wait_for_selector("[data-test=zip-text]", timeout=20000)
    assert len(posts) == 1                                                # resumed, never started twice
    assert pg.inner_text("[data-test=zip-c-orders] .v") == "12"
    assert pg.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 1
    assert not errs, errs
    ctx.close()


def test_error_state_and_retry(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "solo")
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    pg.fill("[data-test=zip-orders]", "1646 1647 666 1648")
    pg.click("[data-test=zip-go]")
    pg.wait_for_selector("[data-test=zip-error]", timeout=15000)
    txt = pg.inner_text("[data-test=zip-error]")
    assert "הריצה נכשלה" in txt and "לא הצלחנו לקרוא את ההזמנות" in txt
    assert pg.locator("[data-test=zip-running]").count() == 0 and pg.is_enabled("[data-test=zip-go]")
    assert pg.evaluate("sessionStorage.getItem('cs.zipfix.rozela')") is None
    assert pg.locator("[data-test=zip-again]").count() == 1
    pg.fill("[data-test=zip-orders]", "1646")
    pg.click("[data-test=zip-again]")
    pg.wait_for_selector("[data-test=zip-text]", timeout=15000)
    assert pg.locator("[data-test=zip-error]").count() == 0
    # a run the server no longer has (restart, 24 h) says so instead of spinning forever
    pg.evaluate("sessionStorage.setItem('cs.zipfix.rozela', JSON.stringify({job: 'AAAAAAAAAAAAAAAAAAAAAAAA', started: Date.now()}))")
    pg.reload()
    pg.wait_for_selector("[data-test=zip-error]")
    assert "כבר לא נמצאת בשרת" in pg.inner_text("[data-test=zip-error]")
    assert not [e for e in errs if "404" not in e], errs
    ctx.close()


def test_junk_text_never_becomes_all_orders(server, browser):
    base, pwd = server
    ctx, pg, _ = login(browser, base, pwd, "solo")
    posts = []
    pg.on("request", lambda r: posts.append(r.url) if "/zipfix" in r.url and r.method == "POST" else None)
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    pg.fill("[data-test=zip-orders]", "שלום, מה המצב?")
    assert "לא זוהה אף מספר הזמנה" in pg.inner_text("[data-test=zip-parse]")
    pg.click("[data-test=zip-go]")
    pg.wait_for_timeout(500)
    assert posts == [] and pg.locator("[data-test=zip-running]").count() == 0
    ctx.close()


def test_dropped_poll_during_deploy_keeps_going(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "solo")
    n = {"bad": 0}

    def flaky(route, req):
        if req.method == "GET" and n["bad"] < 3:
            n["bad"] += 1
            return route.fulfill(status=502, content_type="text/html", body=RENDER_502)
        return route.continue_()
    pg.route("**/api/rozela/zipfix/**", flaky)
    pg.goto(base + "/cs#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    pg.fill("[data-test=zip-orders]", "1646 1647 1648 1650 1651 1652 1654 1655 1656 1658")
    pg.click("[data-test=zip-go]")
    pg.wait_for_selector("[data-test=zip-reconnecting]", timeout=8000)
    pg.wait_for_selector("[data-test=zip-text]", timeout=20000)
    assert pg.locator("[data-test=zip-reconnecting]").count() == 0 and pg.locator("[data-test=zip-error]").count() == 0
    ctx.close()


def test_english_desk(server, browser):
    base, pwd = server
    ctx, pg, errs = login(browser, base, pwd, "eve")
    pg.goto(base + "/cs/en#/zip/rozela")
    pg.wait_for_selector("[data-test=zip-go]")
    assert pg.inner_text("[data-test=zip-go]") == "Get zip codes" and "Zip-code fill" in pg.inner_text("#zip-pane h2")
    pg.fill("[data-test=zip-orders]", "1646, 1649")
    assert "2 orders found" in pg.inner_text("[data-test=zip-parse]")
    pg.click("[data-test=zip-go]")
    pg.wait_for_selector("[data-test=zip-text]", timeout=15000)
    assert "Copy for supplier" in pg.inner_text("[data-test=zip-copy]") and "Ask the customer" in pg.inner_text("[data-test=zip-ask]")
    assert not errs, errs
    ctx.close()


def test_zip_entry_never_overflows_the_phone_bar(server, browser):
    base, pwd = server
    ctx, pg, _ = login(browser, base, pwd, "agent1", width=390)
    for hsh in ("#/b/rozela/ready", "#/b/rozela/t/t18f2a03", "#/zip/rozela"):
        pg.goto(base + "/cs" + hsh)
        pg.wait_for_timeout(900)
        assert pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0, hsh
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector(".menu-btn")
    pg.click(".menu-btn")                                                 # on a phone the entry is in the menu
    assert pg.inner_text("[data-test=zip-menu]") == "מילוי מיקודים"
    pg.click("[data-test=zip-menu]")
    pg.wait_for_selector("[data-test=zip-go]")
    ctx.close()
