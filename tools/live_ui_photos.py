#!/usr/bin/env python3
"""LIVE check: the customer's pictures (WhatsApp + email) are VISIBLE to an agent on https://cs-team-screen.onrender.com (CS request #3, 2026-10-30).
Read-only: logs in as claude-admin, opens each given ticket, waits for its conversation and checks every picture thumbnail really decoded
(naturalWidth > 0), that none fell back to "deleted" / "view in Dondy/Gmail" / "not arrived yet", and that the photo route answers an image.
Optionally checks the served app.js is the pushed mirror.
  team_screen/.venv/bin/python team_screen/tools/live_ui_photos.py <picks.json>      picks = [{"brand","id","ch":"wa"|"email","photos":n,"gone"?:true}]"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(CS, "deploy"))
sys.path.insert(0, os.path.join(CS, "team_screen", "tests"))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402

BASE = "https://cs-team-screen.onrender.com"
picks = json.load(open(sys.argv[1]))
fails = []


def until(pg, js, timeout_s):
    """Poll a JS predicate from Python: the screen's CSP (script-src 'self') refuses Playwright's wait_for_function polling."""
    import time
    end = time.time() + timeout_s
    while time.time() < end:
        if pg.evaluate(js):
            return True
        pg.wait_for_timeout(300)
    raise TimeoutError(js)


def say(ok, name, extra=""):
    print(("PASS " if ok else "FAIL ") + name + ("  " + extra if extra else ""), flush=True)
    if not ok:
        fails.append(name)


with pw.sync_playwright() as p:
    b = launch(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 1000}, extra_http_headers={"X-Claude-Probe": "photos-live-check"})
    pg = ctx.new_page()
    pg.goto(BASE + "/cs/login")
    pg.fill("input[name=username]", rd.BOT)
    pg.fill("input[name=password]", rd.kc_get("screen/claude-admin"))
    pg.click("button[type=submit]")
    pg.wait_for_load_state("load")
    pg.goto(BASE + "/cs#/dash")
    pg.wait_for_timeout(3000)
    src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
    body = pg.request.get(src).body() if src else b""
    mirror = open(os.path.join(CS, "deploy", "render_repo", "static", "app.js"), "rb").read()
    say(hashlib.sha256(body).digest() == hashlib.sha256(mirror).digest(), "the served app.js is the pushed one", hashlib.sha256(body).hexdigest()[:12])
    say("photo_mail" in body.decode("utf-8", "replace"), "the served screen knows email pictures")
    for k in picks:
        name = "%s %s …%s" % (k["brand"], k["ch"], k["id"][-6:])
        pg.goto("about:blank")                                   # a full load per ticket: the previous ticket's pictures can never count
        pg.goto(BASE + "/cs#/b/%s/t/%s" % (k["brand"], k["id"]), wait_until="domcontentloaded")
        try:
            pg.wait_for_selector("[data-test=photo-img], [data-test=photo-gone], [data-test=photo-dondy], [data-test=photo-wait]", timeout=45000)
        except Exception:
            say(False, name + ": the conversation shows a picture")
            continue
        pg.wait_for_timeout(1500)
        imgs = pg.locator("[data-test=photo-img] img")
        n = imgs.count()
        for i in range(n):
            imgs.nth(i).scroll_into_view_if_needed()
        until(pg, "() => [...document.querySelectorAll('[data-test=photo-img] img')].every(i => i.complete)", 60)
        ok = pg.evaluate("() => [...document.querySelectorAll('[data-test=photo-img] img')].map(i => i.naturalWidth)")
        bad = pg.locator("[data-test=photo-gone], [data-test=photo-dondy], [data-test=photo-wait]").count()
        if k.get("gone"):     # older than the 7-day photo rule: the screen must say so (deleted, view in Dondy / Gmail), not show a broken image
            gone = pg.locator("[data-test=photo-gone]").count()
            say(gone == k["photos"] and n == 0, name + ": a picture past 7 days says 'deleted, view in Dondy/Gmail'", "%d deleted labels" % gone)
            continue
        say(n >= k["photos"] and all(w > 0 for w in ok) and bad == 0, name + ": every picture is visible",
            "%d shown (want %d), widths %s, fallbacks %d" % (n, k["photos"], ok, bad))
        if n:
            href = pg.locator("[data-test=photo-img]").first.get_attribute("href")
            r = pg.request.get(BASE + href)
            data = r.body()
            whole = not r.headers.get("content-type", "").startswith("image/jpeg") or b"\xff\xd9" in data[-65536:]   # EOI near the end: not cut after a 1.5 MB part (phones may append a trailer after EOI, e.g. Samsung "Image_UTC_Data")
            say(r.status == 200 and r.headers.get("content-type", "").startswith("image/") and whole, name + ": the full-size picture opens whole",
                "%s %s %d bytes%s" % (r.status, r.headers.get("content-type"), len(data), "" if whole else " CUT"))
    b.close()
print("ALL PASSED" if not fails else "FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
