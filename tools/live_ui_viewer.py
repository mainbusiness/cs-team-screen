#!/usr/bin/env python3
"""Live UI check of the read-only viewer (2026-11-09): sign in with the viewer's Keychain password (cs-engine/screen/<user>), open real tickets and the
dashboard in a real browser; no write control may be drawn and no write request may be sent. Prints counts only - never customer text."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
from pw_launch import launch, pw  # noqa: E402

user = sys.argv[1]
base = subprocess.run(["security", "find-generic-password", "-s", "cs-engine", "-a", "screen/URL", "-w"], capture_output=True, text=True).stdout.strip()
pwd = subprocess.run(["security", "find-generic-password", "-s", "cs-engine", "-a", "screen/" + user, "-w"], capture_output=True, text=True).stdout.strip()
WRITES = ("apiSend", "apiSaveDraft", "apiNote", "apiClose", "apiMarkHandled", "apiKachingCancel", "apiKachingAction", "apiOrderEdit", "apiSubCancel", "apiLinkCustomer", "apiMergeTickets",
          "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyReview", "apiWaTakeOver", "apiRedraftOne", "apiSendTemplate", "apiSettings", "/snooze", "/activity", "/attach", "/assistant")
with pw.sync_playwright() as p:
    pg = launch(p).new_page(viewport={"width": 1280, "height": 1000})
    posts, errors = [], []
    pg.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.wait_for_selector("a[href*='/t/']", timeout=60000)
    n = pg.locator("a[href*='/t/']").count()
    seen = bad = drafts = 0
    for i in range(min(n, 8)):
        pg.goto(base + "/cs#/b/rozela/ready")
        pg.wait_for_selector("a[href*='/t/']", timeout=60000)
        pg.evaluate("(n) => { const a = Array.from(document.querySelectorAll('a[href*=\"/t/\"]'))[n]; if (a) a.click(); }", i)
        pg.wait_for_selector("#ticket-pane .tk-body", timeout=60000)
        pg.wait_for_timeout(1500)
        c = pg.evaluate("""() => { const pane = document.getElementById('ticket-pane');
          return { ta: pane.querySelectorAll('textarea').length, inp: pane.querySelectorAll('input:not([type=hidden])').length,
                   btn: Array.from(pane.querySelectorAll('button')).map(b => (b.getAttribute('data-test') || b.className || '').toString()).filter(x => !/copy|more-btn|back|sg-open/.test(x)) }; }""")
        seen += 1
        drafts += 1 if pg.locator("[data-test=ro-draft]").count() else 0
        if c["ta"] or c["inp"] or c["btn"]:
            bad += 1
            print("write control drawn on ticket", i, c)
    print("tickets opened:", seen, "| with a read-only draft:", drafts, "| tickets with any write control:", bad)
    tabs = pg.evaluate("() => Array.from(document.querySelectorAll('#tabs a')).map(a => a.className.replace('tab ', ''))")
    print("tabs:", tabs, "| assistant button visible:", pg.locator("#assist-fab:visible").count(), "| zip link:", pg.locator("[data-test=zip-link]").count())
    pg.goto(base + "/cs#/dash")
    pg.wait_for_selector("[data-test=bh-brand]", timeout=60000)
    pg.wait_for_selector("[data-test=cr-table]", timeout=60000)
    print("dashboard: billing card", pg.locator("[data-test=bh-brand]").count(), "brand(s) | dunning", pg.locator("[data-test=bh-dunning]").first.inner_text(),
          "| cancel-reasons table rows", pg.locator("[data-test=cr-row]").count(), "| cancellations card", pg.locator("[data-test=cx]").count(),
          "| admin-only cards present:", [s for s in ("#ai-notes", "#sysreq", "[data-test=sales-table]") if pg.locator(s).count()])
    print("billing note:", pg.inner_text("[data-test=bh-na]")[:160].replace("\n", " "))
    wrote = [u for u in posts if any(w in u for w in WRITES)]
    print("write requests the page sent:", wrote, "| page errors:", errors)
    ok = bad == 0 and not wrote and not errors and seen >= 3
    print("RESULT:", "ALL PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)
