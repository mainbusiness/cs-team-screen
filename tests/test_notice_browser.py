"""Owner, 2026-10-26 — the Kaching subscriptions procedure for the CS manager. Real browser, mock engines:
 - on app open an unacknowledged user gets the modal; Esc does not dismiss it; a reload (= the next login/open) shows it again;
 - "✅ קראתי והבנתי" closes it and the next reload shows nothing; the ☰ menu still opens it (read mode, with the ack time);
 - another user still gets it; a velora-only agent never does; no horizontal overflow at 390 / 768 / 1280; no console errors.
"""
import os
import tempfile

import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
TITLE = "🧾 נוהל חדש: מנויים ב-Kaching — חשוב מאוד"
SHOTS = os.environ.get("NOTICE_SHOTS_DIR")


@pytest.fixture
def p():
    with pw.sync_playwright() as x:
        yield x


@pytest.fixture(scope="module")
def server():
    d = tempfile.mkdtemp(prefix="cs-notice-")
    path = os.path.join(d, "notice-acks.json")
    base, pwd, proc = browser_server.start(extra_env={"NOTICE_PATH": path},
                                           users=(("manager", ["admin", "user-manager"], ALL, "he"), ("agent-two", ["agent"], ["celesta", "apexmen"], "he"),
                                                  ("vel1", ["agent"], ["velora"], "he")))
    yield base, pwd, path
    proc.terminate()
    proc.wait(timeout=10)


def login(p, base, pwd, user, width=1280):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def until(pg, js, ms=8000):
    for _ in range(ms // 100):
        if pg.evaluate(js):
            return True
        pg.wait_for_timeout(100)
    raise AssertionError("timed out: " + js)


CLOSED = "() => !document.getElementById('notice-dlg').open"


def dlg_open(pg):
    return pg.evaluate("() => { const d = document.getElementById('notice-dlg'); return !!(d && d.open); }")


def test_show_until_ack_then_menu(p, server):
    base, pwd, path = server
    browser, pg, errors = login(p, base, pwd, "manager")
    pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)
    assert pg.text_content("[data-test=notice-title]") == TITLE
    body = pg.text_content("[data-test=notice-dlg]")
    for s in ("Send link to update card", "שלחנו לך מייל עם קישור מאובטח לעדכון הכרטיס", "החלפה למורינגה", "שינוי כמות או תדירות",
              "תופעת לוואי או סיבה רפואית", "מבטלים מיד, באותו יום, לפני החיוב הבא"):
        assert s in body, s
    assert pg.locator("[data-test=notice-brands] .notice-brand").count() == 3
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    assert dlg_open(pg), "Esc must not dismiss an unacknowledged notice"
    if SHOTS:
        pg.screenshot(path=os.path.join(SHOTS, "notice_1280.png"))
    pg.reload()
    pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)        # the next open: still there
    pg.click("[data-test=notice-ack]")
    until(pg, CLOSED)
    assert os.path.exists(path)
    pg.reload()
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(800)
    assert not dlg_open(pg), "acknowledged: no modal on the next open"
    pg.click(".menu-btn")
    pg.click("[data-test=notice-menu]")
    pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=4000)
    assert "אישרת שקראת" in pg.text_content("[data-test=notice-acked]")
    assert pg.locator("[data-test=notice-ack]").count() == 0
    pg.keyboard.press("Escape")
    until(pg, CLOSED, 4000)
    assert not errors, errors
    browser.close()


def test_other_users(p, server):
    base, pwd, _ = server
    browser, pg, errors = login(p, base, pwd, "agent-two", width=390)
    pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)          # manager's ack is his, not hers
    assert pg.locator("[data-test=notice-brands] .notice-brand").count() == 2
    for w in (390, 768, 1280):
        pg.set_viewport_size({"width": w, "height": 800})
        pg.wait_for_timeout(150)
        # the dialog's own box (the page behind it is not this feature's: a 2-brand agent's top bar is 6 px wide at 390 without it)
        ov = pg.evaluate("() => { const d = document.getElementById('notice-dlg'); const r = d.getBoundingClientRect(); "
                         "return [d.scrollWidth - d.clientWidth, r.left < 0 || r.right > innerWidth ? 1 : 0]; }")
        assert ov == [0, 0], (w, ov)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, "notice_%d.png" % w))
    assert not errors, errors
    browser.close()
    browser, pg, errors = login(p, base, pwd, "vel1")
    pg.wait_for_timeout(1200)
    assert not dlg_open(pg)
    pg.click(".menu-btn")
    assert pg.locator("[data-test=notice-menu]").count() == 0
    browser.close()


@pytest.mark.parametrize("size", [(768, 700), (390, 700), (360, 560)])
def test_ack_button_is_on_screen_without_scrolling(p, server, size):
    """The body scrolls inside the modal; the footer with the button never leaves the screen."""
    base, pwd, _ = server
    browser, pg, errors = login(p, base, pwd, "agent-two", width=size[0])
    pg.set_viewport_size({"width": size[0], "height": size[1]})
    if not dlg_open(pg):                                        # agent-two may have acked in an earlier test: reopen from the menu
        pg.click(".menu-btn")
        pg.click("[data-test=notice-menu]")
    pg.wait_for_selector("[data-test=notice-dlg][open]", timeout=8000)
    pg.wait_for_timeout(200)
    btn = "[data-test=notice-ack]" if pg.locator("[data-test=notice-ack]").count() else "[data-test=notice-close]"
    r = pg.evaluate("""(sel) => { const b = document.querySelector(sel).getBoundingClientRect(); const x = b.left + b.width / 2, y = b.top + b.height / 2;
        const hit = document.elementFromPoint(x, y); return [b.top >= 0 && b.bottom <= innerHeight, !!hit && !!hit.closest(sel),
        document.querySelector('#notice-dlg .notice-in').scrollHeight > document.querySelector('#notice-dlg .notice-in').clientHeight]; }""", btn)
    assert r[0] and r[1], (size, r)
    if size[1] <= 700:
        assert r[2], "the body is the part that scrolls"
    pg.evaluate("() => { const b = document.querySelector('#notice-dlg .notice-in'); b.scrollTop = b.scrollHeight; }")
    assert pg.evaluate("(sel) => { const b = document.querySelector(sel).getBoundingClientRect(); return b.bottom <= innerHeight; }", btn)
    assert not errors, errors
    browser.close()
