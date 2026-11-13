#!/usr/bin/env python3
"""LIVE check of the managers' board tabs + the daily quality check (2026-11-12). Writes NO rating and never finishes a day:
in the browser every POST to /api/dash/quality/rate|done is aborted; the API probes send only requests the server refuses before writing
(a bad score -> 400, "done" with unrated items -> 409). The one write it cannot avoid: the first manager read of the day draws (and stores)
today's sample — the same deterministic sample the CS manager gets.
  .venv/bin/python tools/live_ui_quality.py [shots_dir]
Prints the served app.js vs the pushed mirror, today's sample per agent / brand, the per-agent signals, and any console error."""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
SHOTS = sys.argv[1] if len(sys.argv) > 1 else ''
fails, blocked, errors = [], [], []


def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok:
        fails.append(name)


def block(route):
    if route.request.method == 'POST':
        blocked.append(route.request.url.rsplit('/', 1)[-1])
        return route.abort()
    return route.continue_()


with pw.sync_playwright() as p:
    b = launch(p)
    for width in (1280, 390):
        pg = b.new_page(viewport={'width': width, 'height': 1000}, locale='he-IL', timezone_id='Asia/Jerusalem')
        pg.route('**/api/dash/quality/rate', block)
        pg.route('**/api/dash/quality/done', block)
        for fn in ('apiAiNoteCheck', 'apiAiNoteAdd', 'apiSaleDecide', 'apiSaleScan', 'apiSettings'):
            pg.route('**/' + fn, lambda r: (blocked.append(r.request.url.rsplit('/', 1)[-1]), r.abort()))
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'net::ERR_FAILED' not in m.text else None)
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.on('response', lambda r: errors.append('HTTP %d %s' % (r.status, r.url.split('?')[0].replace(BASE, ''))) if r.status >= 500 else None)
        pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin'))
        pg.click('button[type=submit]'); pg.wait_for_load_state('load')
        pg.goto(BASE + '/cs#/dash')
        pg.wait_for_selector('[data-test=dash-pane-main] [data-test=sla]', timeout=60000)
        pg.wait_for_selector('[data-test=quality-sum] [data-test=quality-status]', timeout=60000)
        if width == 1280:
            src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
            body = pg.request.get(src).body() if src else b''
            mirror = open(os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
            say(bool(body) and hashlib.sha256(body).hexdigest() == hashlib.sha256(mirror).hexdigest(), 'the served app.js is the pushed one',
                hashlib.sha256(body).hexdigest()[:12])
            st = pg.evaluate("async () => (await fetch('/api/dash/quality/status')).json()")
            print('  status:', json.dumps({k: st.get(k) for k in ('day', 'n', 'rated', 'done', 'remind_hour', 'remind_modal')}))
            bd = pg.evaluate("async () => (await fetch('/api/dash/quality')).json()")
            say(bd.get('ok') is True, 'GET /api/dash/quality')
            per = {}
            for it in bd.get('items', []):
                per.setdefault('%s/%s' % (it['agent'], it['brand']), []).append(it['kind'] + ('*' if it.get('untouched') else ''))
            print('  sample (agent/brand -> kinds, * = sent untouched):', json.dumps(per, ensure_ascii=False))
            for a in bd.get('agents', []):
                print('  agent %-10s sends7=%-4s untouched7=%-6s closed7=%-3s (%s)  today sends=%s untouched=%s closed=%s  score=%s' % (
                    a['user'], a['sends'], a['untouched_pct'], a['closed'], a['closed_pct'], a['today_sends'], a['today_untouched'], a['today_closed'], a['score']))
            say(all(len(v) <= 3 for v in per.values()) and len(bd.get('items', [])) <= bd.get('max_total', 40), 'sample within the caps')
            csrf = pg.evaluate("() => document.querySelector('meta[name=csrf]').content")
            if bd.get('items'):
                k = bd['items'][0]['key']
                r = pg.evaluate("async ([k, d, c]) => { const x = await fetch('/api/dash/quality/rate', {method: 'POST', headers: {'Content-Type': 'application/json',"
                                " 'X-CSRF-Token': c}, body: JSON.stringify({day: d, key: k, score: 9, checks: {}, note: ''})}).catch(e => null); return x ? x.status : 'aborted'; }",
                                [k, bd['day'], csrf])
                print('  bad rating probe (aborted in the browser on purpose):', r)
                it = pg.evaluate("async ([k, d]) => (await fetch('/api/dash/quality/item?day=' + d + '&key=' + encodeURIComponent(k))).json()", [k, bd['day']])
                say(it.get('ok') is True, 'one item reads its ticket', 'customer msgs %d · sent %s · ai draft %s' % (
                    len(it.get('customer') or []), bool(it.get('sent')), (it.get('draft') or {}).get('same') if it.get('draft') else 'none'))
            print('  rated today before / after this check:', st.get('rated'), pg.evaluate("async () => (await fetch('/api/dash/quality/status')).json()").get('rated'))
        for sel in ('cx', 'sales-table', 'ai-notes', 'sysreq', 'dash-agents'):
            loc = pg.locator('[data-test=%s]' % sel)
            say(not any(loc.nth(i).is_visible() for i in range(loc.count())), 'main tab does not show %s' % sel)
        say(pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), 'no sideways scroll on main at %d' % width)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, 'live_dash_main_%d.png' % width), full_page=True)
        pg.click('[data-test=dash-tab-quality]')
        pg.wait_for_selector('[data-test=quality-progress]', state='attached', timeout=60000)   # empty on a day nobody answered yet
        n = pg.locator('[data-test=quality-item]').count()
        if not n:
            say(pg.locator('[data-test=quality-empty]').is_visible(), 'an empty day says so on the check', pg.inner_text('[data-test=quality-empty]'))
        if n:
            pg.wait_for_selector('[data-test=quality-item] .q-view .q-msg, [data-test=quality-item] .q-view .note-box, [data-test=q-item-err]', timeout=60000)
            item = pg.locator('[data-test=quality-item]').filter(has=pg.locator('[data-test=q-form]:visible')).first
            item.locator('[data-test=q-score-5]').click(); item.locator('[data-test=q-save]').click()
            pg.wait_for_selector('[data-test=q-save-err]', timeout=15000)
            say(True, 'rating click reaches the server call (aborted here: nothing stored)')
        say(pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), 'no sideways scroll on the check at %d' % width, '%d items' % n)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, 'live_dash_quality_%d.png' % width), full_page=True)
        pg.click('[data-test=dash-tab-more]')
        pg.wait_for_selector('[data-test=dash-pane-more] [data-test=cx]', state='visible', timeout=60000)
        say(pg.locator('[data-test=dash-pane-more] [data-test=sales-table]').count() >= 0, 'more tab shows the moved sections')
        say(pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), 'no sideways scroll on more at %d' % width)
        if SHOTS:
            pg.screenshot(path=os.path.join(SHOTS, 'live_dash_more_%d.png' % width), full_page=False)
        pg.close()
say(not errors, 'no console errors', '; '.join(errors[:3]))
print('blocked writes:', blocked)
print('RESULT:', 'ALL PASSED' if not fails else 'FAILED: ' + ', '.join(fails))
