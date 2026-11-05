#!/usr/bin/env python3
"""LIVE read-only check of "למה מבטלים מנוי" on the managers' board (Owner, 2026-11-01). As claude-admin: the served app.js is the pushed one, the section
draws the engine's real numbers (all brands = the sum of every brand's apiCancelReasons, fetched here independently), names the next run (Friday 02:00
Israel), keeps "other / not stated" as its own row, and fits a phone. Screenshots to argv[1] when given.   .venv/bin/python tools/live_ui_cancel_reasons.py [dir]"""
import hashlib, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(CS, 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
SHOTS = sys.argv[1] if len(sys.argv) > 1 else ''
KEYS = ['never_agreed', 'not_effective', 'try_first', 'has_stock', 'one_time', 'other', 'not_stated']
fails = []
def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok: fails.append(name)

JS = r"""const { coreCall } = require(process.argv[1] + '/core/tools/corecall.js');
(async () => { const out = {};
  for (const b of ['rozela', 'celesta', 'apexmen', 'velora', 'selera']) { const r = await coreCall(b, 'apiCancelReasons', {}, { role: 'admin', user: 'claude-probe' });
    out[b] = { state: r.state, week: r.weeks && r.weeks[0] ? { week: r.weeks[0].week, counts: r.weeks[0].counts, sub: r.weeks[0].sub_cancels, read: r.weeks[0].read } : null,
      all: r.all ? { counts: r.all.counts, sub: r.all.sub_cancels } : null, next: r.next_run }; }
  console.log(JSON.stringify(out)); })();"""
eng = json.loads(subprocess.run(['node', '-e', JS, CS], capture_output=True, text=True, check=True).stdout)
subs = [b for b in eng if eng[b]['state'] == 'ok']
say(sorted(subs) == ['apexmen', 'celesta', 'rozela', 'velora'] and eng['selera']['state'] == 'no_subscriptions', 'engine: every subscription brand has backfilled data; selera has none', ','.join(sorted(subs)))
wk = {eng[b]['week']['week'] for b in subs}
say(len(wk) == 1, 'engine: all brands on the same newest week', ','.join(sorted(wk)))
want_week = {k: sum(eng[b]['week']['counts'][k] for b in subs) for k in KEYS}
want_all = {k: sum(eng[b]['all']['counts'][k] for b in subs) for k in KEYS}

def table(pg):
    return {r.get_attribute('data-k'): int(r.locator('[data-test=cr-n]').inner_text()) for r in pg.locator('[data-test=cr-row]').all()}

with pw.sync_playwright() as p:
    b = launch(p)
    for width in (1280, 390):
        pg = b.new_page(viewport={'width': width, 'height': 1000})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin')); pg.click('button[type=submit]'); pg.wait_for_load_state('load')
        if width == 1280:
            src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
            live = pg.request.get(src).body() if src else b''
            mine = open(os.path.join(CS, 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
            say(bool(live) and hashlib.sha256(live).hexdigest() == hashlib.sha256(mine).hexdigest(), 'the served app.js is the pushed one', hashlib.sha256(live).hexdigest()[:12])
            say(b'pp_p_until_one' in live, 'the pause plural fix is live')
        pg.goto(BASE + '/cs#/dash'); pg.reload()
        pg.wait_for_selector('[data-test=cr-table]', timeout=90000)
        try:
            pg.wait_for_selector('[data-test=cr-pending]', state='detached', timeout=90000)   # every brand answered (the board says "still reading" until then)
        except Exception:
            say(False, 'w%d: every brand answered within 90 s' % width)
        sec = pg.locator('[data-test=cr]')
        txt = sec.inner_text()
        say(not any(x in txt for x in ('null', 'undefined', 'NaN', '{b}', '{d}', '{r}', '{s}')), 'w%d: no template junk' % width)
        got = table(pg)
        say(got.get('never_agreed') == want_week['never_agreed'] and got.get('other_not_stated') == want_week['other'] + want_week['not_stated']
            and all(got.get(k) == want_week[k] for k in KEYS[:5]), 'w%d: all brands, newest week = sum of the engines' % width, json.dumps(got))
        say('הריצה הבאה: שישי' in txt and '02:00' in txt, 'w%d: next run named' % width, sec.locator('[data-test=cr-next]').inner_text())
        say(len(got) == 6, 'w%d: five categories + "other / not stated"' % width)
        print('  ', sec.locator('[data-test=cr-range]').inner_text(), '|', sec.locator('[data-test=cr-read]').inner_text())
        if SHOTS: sec.screenshot(path=os.path.join(SHOTS, 'live_cr_week_%d.png' % width))
        pg.select_option('[data-test=cr-period]', 'all')
        got = table(pg)
        say(all(got.get(k) == want_all[k] for k in KEYS[:5]), 'w%d: all data = the engines\' backfill totals' % width, json.dumps(got))
        if SHOTS: sec.screenshot(path=os.path.join(SHOTS, 'live_cr_all_%d.png' % width))
        pg.select_option('[data-test=cr-brand]', 'rozela')
        got = table(pg)
        say(got.get('never_agreed') == eng['rozela']['all']['counts']['never_agreed'], 'w%d: one brand (rozela) = its own engine' % width)
        say(pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), 'w%d: no horizontal overflow' % width)
        say(not errs, 'w%d: no page errors' % width, '; '.join(errs)[:200])
        pg.close()
    b.close()
print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
sys.exit(1 if fails else 0)
