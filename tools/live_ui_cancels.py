#!/usr/bin/env python3
"""LIVE check of the cancellations section on the managers' board (2026-10-23). STRICTLY read-only: every write route the board could fire
(the AI-notes card auto-runs apiAiNoteCheck; sales buttons) is aborted in the browser before the page loads.
  .venv/bin/python tools/live_ui_cancels.py [shots_dir]
Prints: the core /health revision, whether the served app.js is the pushed one, every brand's state, the numbers drawn, and any console error."""
import hashlib, json, os, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
SHOTS = sys.argv[1] if len(sys.argv) > 1 else ''
WRITES = ('apiAiNoteCheck', 'apiAiNoteAdd', 'apiAiNoteDelete', 'apiAiNoteAttach', 'apiAiNoteSuggestDecide', 'apiSaleDecide', 'apiSaleScan',
          'apiSaleSuggestCredit', 'apiSaleSuggestDismiss', 'apiSaleLog', 'apiSettings')
fails, blocked, errors = [], [], []


def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok:
        fails.append(name)


def block(route):
    blocked.append(route.request.url.rsplit('/', 1)[-1])
    route.abort()


core = json.load(open(os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy', 'core_brands.json')))['host']
try:
    health = json.loads(urllib.request.urlopen('https://%s/health' % core, timeout=30).read().decode())
except Exception as e:                       # noqa: BLE001
    health = {'error': str(e)}
print('core /health:', json.dumps({k: health.get(k) for k in ('ok', 'revision', 'commit', 'startedAt', 'error') if k in health}))

with pw.sync_playwright() as p:
    b = launch(p)
    for width in (1280, 390):
        pg = b.new_page(viewport={'width': width, 'height': 1000})
        for fn in WRITES:
            pg.route('**/' + fn, block)
        pg.route('**/attach', block)
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin'))
        pg.click('button[type=submit]'); pg.wait_for_load_state('load')
        pg.goto(BASE + '/cs#/dash'); pg.wait_for_selector('[data-test=cx]', timeout=60000)
        done = pg.locator('[data-test=cx] :is([data-test=cx-unavailable],[data-test=cx-days],[data-test=cx-err])')
        for _ in range(360):                 # the Kaching read is heavy: up to 3 min (the page re-asks every 4 s while a brand counts)
            if done.count() and not pg.locator('[data-test=cx] [data-test=cx-note]:has-text("עוד סופר")').count():
                break
            pg.wait_for_timeout(500)
        pg.wait_for_timeout(800)
        if width == 1280:
            src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
            body = pg.request.get(src).body() if src else b''
            mirror = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
            say(bool(body) and hashlib.sha256(body).hexdigest() == hashlib.sha256(mirror).hexdigest(), 'the served app.js is the pushed one',
                '%s sha %s' % (src.rsplit('/', 1)[-1], hashlib.sha256(body).hexdigest()[:12]))
            api = pg.evaluate("async () => (await fetch('/api/dash/cancels')).json()")
            print('  brands:', json.dumps({k: {'state': v['state'], 'error': v.get('error'), 'busy': v['busy'], 'churn': (v.get('month') or {}).get('churn_pct'),
                                                 'prev': (v.get('prev_month') or {}).get('churn_pct'), 'target': v.get('target'), 'verdict': v.get('verdict')}
                                             for k, v in (api.get('brands') or {}).items()}, ensure_ascii=False))
            print('  unavailable:', api.get('unavailable'), ' hidden:', api.get('hidden'))
            if api.get('dates'):
                print('  today total:', json.dumps({k: v for k, v in (api.get('total') or {}).get(api['dates'][0], {}).items() if not k.endswith('_missing')}))
                print('  agents today:', json.dumps(api.get('agents'), ensure_ascii=False))
            txt = pg.inner_text('[data-test=cx]')
            say(not any(x in txt for x in ('null', 'undefined', 'NaN', '[object')), 'no null / undefined / NaN on the section')
            live = pg.locator('[data-test=cx-days]').count() > 0
            say(live or pg.locator('[data-test=cx-unavailable]').count() > 0, 'the section shows numbers or says it is waiting for the engine',
                'numbers' if live else 'waiting for the engine')
            say(pg.locator('[data-test=dash-live]').count() == 1, 'the rest of the board is there (live strip)')
        say(pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), 'no sideways scroll at %d px' % width)
        if SHOTS:
            pg.locator('[data-test=cx]').screenshot(path=os.path.join(SHOTS, 'live_cx_%d.png' % width))
        pg.close()
say(not errors, 'no console errors', '; '.join(errors[:3]))
print('blocked writes:', blocked)
print('RESULT:', 'ALL PASSED' if not fails else 'FAILED: ' + ', '.join(fails))
sys.exit(1 if fails else 0)
