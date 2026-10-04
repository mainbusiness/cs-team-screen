#!/usr/bin/env python3
"""
tools/screens.py — local mock preview + Playwright screenshots at 390px (mobile) and 1280px (desktop).

  python tools/screens.py            # writes screens/*.png, exits non-zero if a check fails

Starts the real Flask app in MOCK_ENGINE mode on 127.0.0.1 (random port, temp users file, random
passwords), logs in through the real login form, and on every screen asserts: no JS console error,
no horizontal overflow at 390px. Nothing here touches a live engine.
"""
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "screens")
sys.path.insert(0, ROOT)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    from playwright.sync_api import sync_playwright

    import security
    from users_store import UserStore

    tmp = tempfile.mkdtemp(prefix="cs-preview-")
    users = os.path.join(tmp, "users.json")
    store = UserStore(users, os.path.join(tmp, "audit.jsonl"))
    pw = secrets.token_urlsafe(12) + "-Aa1"
    h = security.hash_password(pw)
    allb = ["apexmen", "celesta", "rozela", "velora"]
    for name, disp, roles, brands, lang in [("manager", "המנהל", ["admin", "user-manager"], allb, "he"),
                                            ("agent-one", "נציג א", ["agent"], ["rozela", "velora"], "he"),
                                            ("agent-two", "נציגה ב", ["agent"], ["celesta", "apexmen"], "he"),
                                            ("eve", "Eve", ["agent"], ["rozela"], "en")]:
        store.create("preview", name, h, {"display_name": disp, "roles": roles, "brands": brands, "lang": lang}, allb, must_change=False)

    port = free_port()
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=users, TRUSTED_PROXY_HOPS="0", MOCK_LATENCY_MS="120",
               ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1")
    code = ("import logging;logging.basicConfig(level=logging.WARNING);from app import create_app;"
            "create_app().run(host='127.0.0.1', port=%d, threaded=True)" % port)
    srv = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = "http://127.0.0.1:%d" % port
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    os.makedirs(OUT, exist_ok=True)
    problems = []
    shots = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            def session(user, width, height):
                ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2, locale="he-IL",
                                          timezone_id="Asia/Jerusalem")
                page = ctx.new_page()
                errs = []
                page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.goto(base + "/cs/login")
                page.fill("input[name=username]", user)
                page.fill("input[name=password]", pw)
                page.click("button[type=submit]")
                page.wait_for_load_state("networkidle")
                return ctx, page, errs

            def settle(page):
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(450)

            def shot(page, errs, name, width, full=True):
                settle(page)
                path = os.path.join(OUT, "%s_%d.png" % (name, width))
                page.screenshot(path=path, full_page=full)
                shots.append(path)
                if width <= 400:
                    ov = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                    if ov > 1:
                        problems.append("%s: horizontal overflow %dpx" % (name, ov))
                if errs:
                    problems.append("%s: console errors %s" % (name, errs[:3]))
                    errs.clear()
                # stringified JS values leaking into the page ("[object HTMLDivElement]", a lone "null")
                leaks = page.evaluate("""(() => { const t = document.body.innerText; const out = [];
                  if (/\\[object [A-Za-z]+\\]/.test(t)) out.push('[object ...]');
                  t.split('\\n').forEach(l => { if (/^\\s*(null|undefined|NaN)\\s*$/.test(l)) out.push(l.trim()); });
                  return out; })()""")
                if leaks:
                    problems.append("%s: stringified values on screen %s" % (name, leaks[:5]))

            # login page
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = ctx.new_page()
            pg.goto(base + "/cs/login")
            pg.screenshot(path=os.path.join(OUT, "01_login_390.png"))
            shots.append(os.path.join(OUT, "01_login_390.png"))
            ctx.close()

            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/ready")
                shot(page, errs, "02_list_new", width)
                page.goto(base + "/cs#/b/rozela/t/t18f2a03")
                page.wait_for_selector(".msg blockquote")
                shot(page, errs, "03_ticket_cancel_request", width)
                page.goto(base + "/cs#/b/rozela/auto")
                page.wait_for_selector(".ac-item")
                shot(page, errs, "05_auto_cancel_queue", width)
                ctx.close()

            # cancel dialog: wrong digits -> the gate's refusal, translated
            ctx, page, errs = session("agent-one", 390, 844)
            page.goto(base + "/cs#/b/rozela/t/t18f2a03")
            page.wait_for_selector("text=ביטול מנוי")
            page.click(".btn.danger-outline")
            page.fill("#cancel-dlg input.code", "9999")
            page.click("#cancel-dlg .btn.danger")
            page.wait_for_selector("#cancel-dlg .err-box")
            txt = page.inner_text("#cancel-dlg .err-box")
            if "4 הספרות" not in txt or "confirmation code does not match the contract" not in txt:
                problems.append("cancel refusal not shown verbatim+Hebrew: %r" % txt)
            shot(page, errs, "04_cancel_dialog_refused", 390, full=False)
            page.keyboard.press("Escape")
            # draft survives a reload (local mirror) — typed text must come back
            page.goto(base + "/cs#/b/rozela/t/t18f2a01")
            page.wait_for_selector(".draft textarea")
            page.click(".draft textarea")
            page.keyboard.press("End")
            page.keyboard.type(" בדיקת-שמירה")
            page.reload()
            page.wait_for_selector(".draft textarea")
            settle(page)
            if "בדיקת-שמירה" not in page.input_value(".draft textarea"):
                problems.append("typed draft text lost on reload")
            ctx.close()

            # dry-run brand (celesta, agent-two)
            ctx, page, errs = session("agent-two", 390, 844)
            page.goto(base + "/cs#/b/celesta/t/tcele01")
            page.wait_for_selector("[data-test=dry-run]")
            if not page.is_disabled(".draft .btn.primary"):
                problems.append("Send is enabled in DRY_RUN")
            shot(page, errs, "06_dry_run_ticket", 390)
            ctx.close()

            # admin: system mode with a refusal shown verbatim, users manager
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("manager", width, height)
                page.goto(base + "/cs#/settings/celesta")
                page.wait_for_selector(".seg")
                if width == 390:
                    page.click(".set-row:nth-of-type(3) .seg-btn:has-text('פועל')")
                    page.click("#confirm-dlg .btn.danger")
                    page.wait_for_selector("[data-test=refusal-raw]")
                    raw = page.inner_text("[data-test=refusal-raw]")
                    if "needs_live_switches" not in raw:
                        problems.append("settings refusal not verbatim: %r" % raw)
                shot(page, errs, "07_system_mode", width)
                page.goto(base + "/cs#/users")
                page.wait_for_selector(".u-card")
                shot(page, errs, "08_users", width)
                ctx.close()

            # English UI (phase 5 shell)
            ctx, page, errs = session("eve", 390, 844)
            page.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
            page.wait_for_selector(".msg")
            shot(page, errs, "09_english_ticket", 390)
            ctx.close()
            browser.close()
    finally:
        srv.terminate()
        try:
            err = srv.communicate(timeout=5)[1].decode("utf-8", "replace")
        except Exception:
            err = ""
        if "Traceback" in err:
            problems.append("server traceback:\n" + err[-1500:])

    for s in shots:
        print(s)
    if problems:
        print("\nPROBLEMS:")
        for p_ in problems:
            print(" -", p_)
        return 1
    print("\nall screen checks passed (%d shots)" % len(shots))
    return 0


if __name__ == "__main__":
    sys.exit(main())
