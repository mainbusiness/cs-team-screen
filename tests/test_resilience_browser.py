"""Deploy resilience, in a real browser (Playwright + Chromium) against the mock app.

Render answers a deploy switchover with its own HTML 502 page. Reads must ride through it; writes must never be
re-sent; the background poller must stay silent. Measured live 2026-10-05: 23 such 502s at two deploys.
"""
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

from pw_launch import launch, pw  # noqa: E402  (bundled Chromium, else installed Chrome)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER_502 = "<!DOCTYPE html><html><head><title>502 Bad Gateway</title></head><body>" + "x" * 2000 + "</body></html>"


@pytest.fixture(scope="module")
def server():
    sys.path.insert(0, ROOT)
    import security
    from users_store import UserStore
    tmp = tempfile.mkdtemp(prefix="cs-resil-")
    users = os.path.join(tmp, "users.json")
    pwd = secrets.token_urlsafe(12) + "-Aa1"
    UserStore(users, os.path.join(tmp, "a.jsonl")).create("t", "agent1", security.hash_password(pwd),
                                                          {"display_name": "a", "roles": ["agent"], "brands": ["rozela"], "lang": "he"},
                                                          ["rozela", "celesta", "apexmen", "selera", "velora"], must_change=False)
    UserStore(users, os.path.join(tmp, "a.jsonl")).create("t", "admin1", security.hash_password(pwd),
                                                          {"display_name": "d", "roles": ["admin"], "brands": ["rozela"], "lang": "he"},
                                                          ["rozela", "celesta", "apexmen", "selera", "velora"], must_change=False)
    UserStore(users, os.path.join(tmp, "a.jsonl")).create("t", "agent-en", security.hash_password(pwd),
                                                          {"display_name": "e", "roles": ["agent"], "brands": ["rozela"], "lang": "en"},
                                                          ["rozela", "celesta", "apexmen", "selera", "velora"], must_change=False)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=users, TRUSTED_PROXY_HOPS="0", MOCK_LATENCY_MS="0",
               ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1")
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


@pytest.fixture
def page(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser = launch(p)                     # fails loudly with the reasons; never skips
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.goto(base + "/cs/login")
        pg.fill("input[name=username]", "agent1")
        pg.fill("input[name=password]", pwd)
        pg.click("button[type=submit]")
        pg.wait_for_load_state("networkidle")
        yield pg, base
        browser.close()


def html_502(route):
    route.fulfill(status=502, content_type="text/html", body=RENDER_502)


def no_error_on_screen(pg):
    txt = pg.inner_text("body")
    assert "תשובה לא תקינה" not in txt and "השרת בעדכון" not in txt
    assert pg.locator(".err-box:visible").count() == 0


def test_read_rides_through_two_html_502s(page):
    pg, base = page
    hits = []

    def handler(route, request):
        hits.append(time.time())
        if len(hits) <= 2:
            html_502(route)
        else:
            route.continue_()
    pg.route("**/api/rozela/ticket", handler)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector("[data-test=reconnecting]:not([hidden])", timeout=5000)      # the small pill while retrying
    pg.wait_for_selector(".draft", timeout=15000)                                       # the FULL ticket (not the instant partial view)
    assert pg.inner_text(".tk-head h2") == "מיכל לוי"
    assert len(hits) >= 3 and hits[2] - hits[0] >= 2.5                                 # backoff 1 s + 2 s
    pg.wait_for_selector("[data-test=reconnecting]", state="hidden", timeout=5000)
    no_error_on_screen(pg)


def test_write_is_sent_exactly_once_and_says_check_first(page):
    """Render's HTML 502 on a send: one request, never re-sent; the outbox asks /result instead (background sends)."""
    pg, base = page
    sends = []

    def handler(route, request):
        sends.append(1)
        html_502(route)
    pg.route("**/api/rozela/apiSend", handler)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector(".draft .btn.primary:not([disabled])", timeout=15000)
    pg.click(".draft .btn.primary")
    pg.wait_for_timeout(600)                    # two separate clicks: a double-click never confirms (review 2026-10-11 #2)
    pg.click(".draft .btn.primary")                                                    # armed: second click hands off
    pg.wait_for_selector("[data-test=row-outbox][data-state=checking]", state="attached", timeout=10000)
    pg.wait_for_timeout(4000)                                                          # longer than the first two read backoffs
    assert len(sends) == 1
    assert "תשובה לא תקינה" not in pg.inner_text("body")



def test_poller_stays_silent_and_keeps_the_list(page):
    pg, base = page
    pg.goto(base + "/cs#/b/rozela/ready")
    pg.wait_for_selector("a.row")
    rows = pg.locator("a.row").count()
    polls = []

    def handler(route, request):
        polls.append(1)
        html_502(route)
    pg.route("**/api/rozela/changes", handler)
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")              # what the 20 s tick does
    pg.wait_for_timeout(3500)
    assert len(polls) == 1                                                             # one quiet attempt, no retry storm
    assert pg.locator("[data-test=reconnecting]:visible").count() == 0
    assert pg.locator("a.row").count() == rows
    no_error_on_screen(pg)
    pg.unroute("**/api/rozela/changes")
    pg.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_timeout(800)
    assert pg.locator("a.row").count() == rows


def test_own_json_502_is_an_answer_not_a_restart(page):
    """engine_timeout is OUR JSON answer: never the 45 s restart loop. Since QA round 5 one friendly retry, then the
    partial view says so — never the raw "invalid answer"."""
    pg, base = page
    hits = []

    def handler(route, request):
        hits.append(1)
        route.fulfill(status=504, content_type="application/json",
                      body='{"ok": false, "error": "engine_timeout", "msg": "המנוע לא ענה בזמן."}')
    pg.route("**/api/rozela/ticket", handler)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a02")
    pg.wait_for_selector("text=הפנייה המלאה לא נטענה כרגע.", timeout=10000)
    assert len(hits) == 2                                                               # one quick retry, not a restart loop
    assert pg.locator("[data-test=reconnecting]:visible").count() == 0 and "תשובה לא תקינה" not in pg.inner_text("body")


def test_unknown_write_flags_and_locks_the_ticket(page):
    pg, base = page
    pg.route("**/api/rozela/apiSend", lambda route, req: route.fulfill(status=502, content_type="application/json",
             body='{"ok": false, "error": "write_unknown", "refresh": true, "msg": "לא הצלחנו לאשר אם הפעולה בוצעה — רעננו את הפנייה ובדקו."}'))
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector(".draft .btn.primary:not([disabled])", timeout=15000)
    pg.click(".draft .btn.primary")
    pg.wait_for_timeout(600)                    # two separate clicks: a double-click never confirms (review 2026-10-11 #2)
    pg.click(".draft .btn.primary")
    pg.wait_for_selector("[data-test=row-outbox][data-state=unknown]", state="attached", timeout=10000)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
    pg.wait_for_selector("[data-test=outbox-banner][data-state=unknown]")
    assert "לא אושר — לבדוק" in pg.inner_text("[data-test=outbox-banner]") and "לא הצלחנו לאשר" in pg.inner_text("[data-test=outbox-banner]")
    pg.fill(".draft textarea", "שוב")
    assert pg.is_disabled(".draft .btn.primary") and "סירב" not in pg.inner_text("body")
