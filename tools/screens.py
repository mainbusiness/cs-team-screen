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
    allb = ["apexmen", "celesta", "rozela", "selera", "velora"]
    for name, disp, roles, brands, lang in [("manager", "המנהל", ["admin", "user-manager"], allb, "he"),
                                            ("agent-one", "נציג א", ["agent"], ["rozela", "velora"], "he"),
                                            ("agent-two", "נציגה ב", ["agent"], ["celesta", "apexmen"], "he"),
                                            ("eve", "Eve", ["agent"], ["rozela"], "en")]:
        store.create("preview", name, h, {"display_name": disp, "roles": roles, "brands": brands, "lang": lang}, allb, must_change=False)

    port = free_port()
    os.environ.setdefault("MOCK_LATENCY_MS", "1500")          # a slow engine, so the cache has to earn its keep
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=users, TRUSTED_PROXY_HOPS="0",
               ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1")
    code = ("import logging;logging.basicConfig(level=logging.WARNING);from app import create_app;"
            "import mock_engine;"            # מילוי מיקודים: the real zipfix routes + jobs, only the Shopify/zip runner is faked
            "create_app({'ZIPFIX_RUNNER': mock_engine.zipfix_runner, 'ZIPFIX_CONFIGURED': lambda b: True})"
            ".run(host='127.0.0.1', port=%d, threaded=True)" % port)
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
            sys.path.insert(0, os.path.join(ROOT, "tests"))
            from pw_launch import launch
            browser = launch(p)

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

            # מילוי מיקודים (2026-10-10), first so its shots exist even if a later step fails: running + result, Hebrew and English, phone and desktop
            zip_orders = "#1646, 1647\n1649 1653 1657 #1660 1661 1663 404"
            for user, path, tag in (("agent-one", "/cs", "he"), ("eve", "/cs/en", "en")):
                for width, height in ((390, 844), (1280, 860)):
                    ctx, page, errs = session(user, width, height)
                    page.goto(base + path + "#/zip/rozela")
                    page.wait_for_selector("[data-test=zip-go]")
                    page.fill("[data-test=zip-orders]", zip_orders)
                    page.click("[data-test=zip-go]")
                    page.wait_for_selector("[data-test=zip-running]")
                    page.wait_for_timeout(1300)
                    if tag == "he":
                        shot(page, errs, "30_zip_running", width)
                    page.wait_for_selector("[data-test=zip-text]", timeout=30000)
                    txt = page.input_value("[data-test=zip-text]")
                    if not txt.startswith("1646 - ") or page.evaluate("getComputedStyle(document.querySelector('[data-test=zip-text]')).direction") != "ltr":
                        problems.append("zip: supplier text wrong or not LTR: %r" % txt[:40])
                    if page.locator("[data-test=zip-review-item]").count() < 1 or page.locator("[data-test=zip-ask-item]").count() < 1:
                        problems.append("zip: review / ask lists empty")
                    shot(page, errs, "31_zip_result" if tag == "he" else "32_zip_result_en", width)
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
            page.wait_for_selector("button.danger-outline:has-text('ביטול מנוי')")   # the button, not the category chip of the same name
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
            # ---------- performance: a prefetched ticket opens from the Render cache while the engine is slow ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/ready")
                page.wait_for_selector("a.row")
                page.wait_for_timeout(int(os.environ.get("MOCK_LATENCY_MS", "120")) * 3 + 1500)   # prefetch (cap 3) finishes
                samples = []
                syncing = False
                for n in range(3):                                   # median of 3: one sample on a loaded box is noise
                    if n:
                        page.goto(base + "/cs#/b/rozela/ready")
                        page.wait_for_selector("a.row")
                    name_before = page.locator(".tk-head h2").inner_text() if page.locator(".tk-head h2").count() else None
                    t0 = time.perf_counter()
                    page.click("a.row >> nth=%d" % n)
                    page.wait_for_selector("a.row.selected >> nth=0", state="attached")   # mobile hides the list pane
                    page.wait_for_selector(".tk-head h2")
                    samples.append((time.perf_counter() - t0) * 1000)
                    syncing = syncing or page.locator("[data-test=tk-sync]:not([hidden])").count() > 0
                ms_open = sorted(samples)[1]
                print("open of a prefetched ticket at %dpx: median %.0f ms of %s (engine latency %s ms), revalidating=%s"
                      % (width, ms_open, [int(x) for x in samples], os.environ.get("MOCK_LATENCY_MS", "120"), syncing))
                if ms_open > 300:
                    problems.append("prefetched ticket took %.0f ms to open (budget 300)" % ms_open)
                if not syncing:
                    problems.append("no 'updating' chip while the cached copy revalidates")
                page.screenshot(path=os.path.join(OUT, "16_cached_open_updating_%d.png" % width))
                shots.append(os.path.join(OUT, "16_cached_open_updating_%d.png" % width))
                page.wait_for_selector("[data-test=tk-sync][hidden]", state="attached", timeout=15000)
                settle(page)
                if errs:
                    problems.append("perf: console errors %s" % errs[:2])
                ctx.close()

            # ---------- optimistic draft save: instant "saved", rollback + sticky error on refusal, text never lost ----------
            ctx, page, errs = session("agent-one", 390, 844)
            page.goto(base + "/cs#/b/rozela/t/t18f2a02")
            page.wait_for_selector(".draft textarea")
            page.click(".draft textarea")
            page.keyboard.press("End")
            page.keyboard.type(" REFUSE-SAVE")
            t0 = time.perf_counter()
            page.locator(".draft textarea").blur()
            page.wait_for_selector(".save-state.opt", timeout=2000)
            opt_ms = (time.perf_counter() - t0) * 1000
            page.wait_for_selector(".save-state.bad", timeout=15000)
            if "REFUSE-SAVE" not in page.input_value(".draft textarea"):
                problems.append("rollback lost the agent's text")
            print("optimistic 'saved' shown after %.0f ms; engine refusal -> sticky error, text kept" % opt_ms)
            if opt_ms > 300:
                problems.append("optimistic save indicator took %.0f ms" % opt_ms)
            page.locator(".draft").scroll_into_view_if_needed()
            shot(page, errs, "17_draft_save_refused_rollback", 390, full=False)
            ctx.close()

            # ---------- live QA fixes (2026-10-05) ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/ready")
                page.wait_for_selector("[data-test=old-section]")
                page.locator("[data-test=old-section]").scroll_into_view_if_needed()
                shot(page, errs, "31_newest_first_old_section", width, full=False)
                if width == 1280:
                    over = page.evaluate("(() => { const t = document.getElementById('tabs'); return t.scrollWidth - t.clientWidth; })()")
                    if over > 1:
                        problems.append("tabs still scroll sideways at 1280 (%dpx)" % over)
                page.goto(base + "/cs#/b/rozela/t/t18f2a03")
                page.wait_for_selector("[data-test=siblings]")
                shot(page, errs, "32_siblings_chip", width, full=False)
                page.goto(base + "/cs#/b/rozela/t/t18f2a11")
                page.wait_for_selector(".ship-line")
                page.locator(".ship-line").scroll_into_view_if_needed()
                shot(page, errs, "33_fact_panel", width, full=False)
                ctx.close()

            # ---------- Dondy bot + WhatsApp photos (engine @18) ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/bot")
                page.wait_for_selector("a.row[data-id=w8ab77c2]")
                shot(page, errs, "29_bot_tab", width, full=False)
                page.goto(base + "/cs#/b/rozela/t/w8ab77c2")
                page.wait_for_selector("[data-test=photo-dondy]")
                page.locator("[data-test=photo-dondy]").scroll_into_view_if_needed()
                shot(page, errs, "30_bot_ticket_photos", width, full=False)
                ctx.close()

            # ---------- WhatsApp vs email (Owner, 2026-10-05) ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/action")
                page.wait_for_selector("a.row.wa")
                shot(page, errs, "26_channels_list", width, full=False)
                page.goto(base + "/cs#/b/rozela/t/w8ab77c1")
                page.wait_for_selector("[data-test=wa-banner]")
                page.fill(".draft textarea", "היי עומר, כן — יש משלוח לאילת, עד הבית או לנקודת איסוף.")
                page.evaluate("window.scrollTo(0, 0); document.getElementById('ticket-pane').scrollTop = 0")
                shot(page, errs, "27_whatsapp_ticket", width, full=False)
                page.locator("[data-test=send-btn]").scroll_into_view_if_needed()
                shot(page, errs, "28_whatsapp_send_button", width, full=False)
                if page.locator("[data-test=send-btn]").inner_text() != "שליחה בוואטסאפ":
                    problems.append("WhatsApp send button label")
                ctx.close()

            # ---------- background sends (Owner, 2026-10-05) ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                tab, tid = ("ready", "t18f2c02") if width == 390 else ("delay", "t18f2a06")   # each pass its own open ticket
                page.goto(base + "/cs#/b/rozela/" + tab)
                page.wait_for_selector("a.row[data-id=%s]" % tid)
                page.click("a.row[data-id=%s]" % tid)
                page.wait_for_selector(".draft textarea:not([readonly])")
                page.fill(".draft textarea", "היי, בדיקה ✓" if width == 390 else "היי, זה 100% מובטח")   # 1280: a refusal
                page.click("[data-test=send-btn]")
                page.click("[data-test=send-btn]")
                page.wait_for_selector("[data-test=outbox-indicator]", timeout=5000)
                if width == 1280:
                    page.wait_for_selector("[data-test=row-outbox][data-state=refused]", state="attached", timeout=15000)
                    page.goto(base + "/cs#/b/rozela/delay")
                    page.wait_for_selector("a.row")
                    page.click("[data-test=outbox-indicator]")
                shot(page, errs, "34_background_send", width, full=False)
                ctx.close()

            # ---------- deploy resilience: the "reconnecting" pill while a read rides through Render's 502 ----------
            ctx, page, errs = session("agent-one", 390, 844)
            page.route("**/api/rozela/ticket", lambda route, req: route.fulfill(status=502, content_type="text/html", body="<html>502</html>"))
            page.goto(base + "/cs#/b/rozela/t/t18f2a05")
            page.wait_for_selector("[data-test=reconnecting]:not([hidden])", timeout=5000)
            page.screenshot(path=os.path.join(OUT, "25_reconnecting_390.png"))
            shots.append(os.path.join(OUT, "25_reconnecting_390.png"))
            if "תשובה לא תקינה" in page.inner_text("body"):
                problems.append("bad-response message shown during a restart")
            ctx.close()

            # ---------- auto-reply review + recommendation (Owner, 2026-10-05) ----------
            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/autoreply")
                page.wait_for_selector("[data-test=ar-item] .ar-q .txt")
                badge = page.locator(".tab.autoreply .n").inner_text()
                if width == 390 and badge != "2":                       # the 390 pass flags one below, so 1280 sees 1
                    problems.append("auto-reply badge shows %r, want 2 (review: pending)" % badge)
                if page.locator("text=🤖 נענה אוטומטית").count() < 1 or page.locator("text=🤖 היה נשלח אוטומטית").count() < 1:
                    problems.append("auto-reply labels missing")
                shot(page, errs, "18_autoreply_review", width, full=False)
                if width == 390:
                    page.locator("[data-test=ar-item] [data-test=ar-problem]").first.click()
                    page.fill("[data-test=ar-item] .note-add input", "הקישור למעקב שגוי")
                    page.locator("[data-test=ar-item] .note-add .btn").first.click()
                    page.wait_for_selector("text=⚠ סומן כבעיה")
                    shot(page, errs, "19_autoreply_flagged", width, full=False)
                    page.goto(base + "/cs#/b/rozela/sent")
                    page.wait_for_selector("[data-test=bot-chip]")
                    if page.locator("a.row [data-test=row-rec]").count() < 1:
                        problems.append("list rows have no recommendation line")
                    shot(page, errs, "20_list_bot_label_and_recommendation", width, full=False)
                page.goto(base + "/cs#/b/rozela/t/t18f2a01")
                page.wait_for_selector("[data-test=what-to-do]")
                if page.locator("[data-test=what-to-do-chip]").count() != 1:
                    problems.append("no 'what to do' chip above the draft")
                shot(page, errs, "21_ticket_what_to_do", width, full=False)
                ctx.close()
            ctx, page, errs = session("manager", 390, 844)
            page.goto(base + "/cs#/settings/rozela")
            page.wait_for_selector(".set-row[data-key=AUTO_REPLY]")
            page.locator(".set-row[data-key=AUTO_REPLY]").scroll_into_view_if_needed()
            shot(page, errs, "22_settings_auto_reply", 390, full=False)
            ctx.close()
            ctx, page, errs = session("eve", 390, 844)
            page.goto(base + "/cs/en#/b/rozela/autoreply")
            page.wait_for_selector("[data-test=ar-item] [data-test=show-original]")
            page.wait_for_timeout(1500)
            if "Hi, when is my order supposed to arrive?" not in page.inner_text("#list-pane"):
                problems.append("English auto-reply card not translated")
            shot(page, errs, "23_english_autoreply", 390, full=False)
            page.goto(base + "/cs/en#/b/rozela/ready")
            page.wait_for_selector("a.row [data-test=row-rec]")
            page.wait_for_timeout(1200)
            if "What to do: Send the draft" not in page.inner_text("#list-pane"):
                problems.append("English list recommendation not translated")
            shot(page, errs, "24_english_list_recommendation", 390, full=False)
            ctx.close()

            # ---------- phase 5 ----------
            def ask(page, q):
                n = page.locator(".as-msg.bot").count()
                page.fill("#assist textarea", q)
                page.click("#assist .as-compose .btn.primary")
                for _ in range(150):                                   # no wait_for_function: the CSP blocks eval (correctly)
                    if page.locator(".as-msg.bot .txt").count() > n or page.locator("#assist .err-box").count():
                        break
                    page.wait_for_timeout(100)

            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("agent-one", width, height)
                page.goto(base + "/cs#/b/rozela/t/t18f2a04")
                page.wait_for_selector(".draft textarea")
                page.click("#assist-fab")
                ask(page, "מה המדיניות על החזר כספי? מה לענות לה?")
                ask(page, "תבדוק את yossi.m@example.com")
                if page.locator(".as-msg.bot .chip").count() < 1:
                    problems.append("assistant: tool chip missing")
                shot(page, errs, "10_assistant", width, full=False)
                if width == 390:
                    page.click("#assist .as-head .btn.ghost")          # new chat
                    ask(page, "מה מדיניות ההחזרים של Celesta?")
                    if "לא זמין כאן" not in page.inner_text("#assist .as-log"):
                        problems.append("assistant did not refuse another brand")
                    shot(page, errs, "11_assistant_other_brand", width, full=False)
                ctx.close()

            for width, height in ((390, 844), (1280, 860)):
                ctx, page, errs = session("eve", width, height)
                page.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
                page.wait_for_selector("[data-test=show-original]")
                first = page.locator(".msg[data-i='0'] .mbody").inner_text()
                if "Why did you charge me again" not in first:
                    problems.append("english mode: message 0 not translated: %r" % first[:80])
                page.locator(".msg[data-i='2'] [data-test=show-original]").click()
                if "כן ברור" not in page.locator(".msg[data-i='2'] .mbody").inner_text():
                    problems.append("show original did not show the Hebrew original")
                page.locator(".msg[data-i='2']").scroll_into_view_if_needed()
                shot(page, errs, "12_english_show_original", width, full=False)
                page.fill("[data-test=en-draft] textarea", "Hi Yossi, I cancelled the subscription right away, so there will be no more charges. "
                          "Your last order is already on its way to you.\n\nYehuda\nRozela Team")
                page.click("[data-test=en-review-btn]")
                page.wait_for_selector("[data-test=en-review] .en-col.out")
                out = page.inner_text("[data-test=en-review] .en-col.out")
                if "ביטלתי את המנוי" not in out:
                    problems.append("send translation not shown: %r" % out[:80])
                if page.is_disabled("[data-test=en-confirm]"):
                    problems.append("confirm disabled on a live brand")
                page.locator("[data-test=en-review]").scroll_into_view_if_needed()
                shot(page, errs, "13_send_translation_confirm", width, full=False)
                ctx.close()

            ctx, page, errs = session("manager", 390, 844)
            page.goto(base + "/cs#/b/selera/t/tsele01")
            page.wait_for_selector(".draft textarea")
            settle(page)
            if page.locator("#subs-card .card").count() or page.locator(".tab.auto").count():
                problems.append("selera shows subscriptions or the auto-cancel tab")
            shot(page, errs, "14_selera_no_subscriptions", 390)
            ctx.close()
            ctx, page, errs = session("agent-one", 390, 844)
            page.goto(base + "/cs#/b/velora/ready")
            page.wait_for_selector("[data-test=not-connected]")
            if page.locator(".err-box").count():
                problems.append("velora shows an error instead of 'not connected'")
            shot(page, errs, "15_brand_not_connected", 390)
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
