#!/usr/bin/env python3
"""LIVE check of the AI-notes card (2026-10-22): the suggestions section renders for an admin, per brand, with no load error.
STRICTLY read-only: every AI-note WRITE route is aborted in the browser before the page loads (the card auto-runs apiAiNoteCheck on a
note without a check, which is an engine write — not on a live brand from a probe).   .venv/bin/python tools/live_ui_ainotes.py [shots_dir]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
SHOTS = sys.argv[1] if len(sys.argv) > 1 else ''
WRITES = ('apiAiNoteCheck', 'apiAiNoteAdd', 'apiAiNoteDelete', 'apiAiNoteAttach', 'apiAiNoteSuggestDecide')
fails, blocked, errors = [], [], []


def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok:
        fails.append(name)


def block(route):
    blocked.append(route.request.url.rsplit('/', 1)[-1])
    route.abort()


with pw.sync_playwright() as p:
    b = launch(p)
    pg = b.new_page(viewport={'width': 1280, 'height': 1000})
    for fn in WRITES:
        pg.route('**/' + fn, block)
    pg.route('**/attach', block)
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin'))
    pg.click('button[type=submit]'); pg.wait_for_load_state('load')
    pg.goto(BASE + '/cs#/dash'); pg.wait_for_selector('[data-test=ai-notes]', timeout=60000)
    # the page's CSP forbids eval, so no string wait_for_function: poll a locator
    arrived = pg.locator('[data-test=ai-sugg-section] :is([data-test=ai-sugg-empty],[data-test=ai-sugg],[data-test=ai-sugg-load-err])')
    for _ in range(180):
        if arrived.count():
            break
        pg.wait_for_timeout(500)
    pg.wait_for_timeout(1500)
    # the code that runs is the code that was pushed: sha of the app.js THIS page loaded vs the pushed mirror
    import hashlib
    src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
    body = pg.request.get(src).body() if src else b''
    mirror = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
    say(bool(body) and hashlib.sha256(body).hexdigest() == hashlib.sha256(mirror).hexdigest(), 'the served app.js is the pushed one',
        '%s sha %s' % (src.rsplit('/', 1)[-1], hashlib.sha256(body).hexdigest()[:12]))
    sec = pg.locator('[data-test=ai-sugg-section]')
    say('💡 הצעות מהתיקונים של הצוות' in sec.locator('h4').inner_text(), 'the suggestions section is in the AI-notes card')
    info = pg.evaluate("""() => ({
      brands: Array.from(document.querySelectorAll('[data-test=ai-sugg-brand]')).map(e => [e.getAttribute('data-brand'), e.querySelectorAll('[data-test=ai-sugg]').length]),
      empty: Array.from(document.querySelectorAll('[data-test=ai-sugg-empty]')).map(e => e.innerText),
      errs: Array.from(document.querySelectorAll('[data-test=ai-sugg-load-err]')).map(e => e.innerText),
      help: (document.querySelector('[data-test=ai-notes-help]') || {}).innerText || '',
      notes: document.querySelectorAll('[data-test=ai-note]').length })""")
    print('  suggestions per brand:', json.dumps(info['brands'], ensure_ascii=False))
    print('  empty lines:', json.dumps(info['empty'], ensure_ascii=False))
    print('  notes listed:', info['notes'])
    say(not info['errs'], 'no brand failed to load its suggestions', json.dumps(info['errs'], ensure_ascii=False))
    say('הטיוטות הפתוחות בתור נכתבות מחדש' in info['help'], 'the new help text is live')
    for w in (1280, 390):
        pg.set_viewport_size({'width': w, 'height': 1000})
        pg.wait_for_timeout(400)
        say(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'no horizontal overflow at %d' % w)
        if SHOTS:
            sec.screenshot(path=os.path.join(SHOTS, 'live_sugg_%d.png' % w))
    b.close()
print('  write calls blocked (never sent):', blocked or 'none')
print('  console errors:', [e for e in errors if 'ERR_FAILED' not in e][:5])
print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
sys.exit(1 if fails else 0)
