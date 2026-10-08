#!/usr/bin/env python3
"""LIVE check of the one open list (Owner, 2026-10-07): no "needs decision / health / delay" tabs, every open row carries its status label,
old tab links open the one list, a ticket opens from it. Read-only: nothing is sent or changed.   .venv/bin/python tools/live_ui_onelist.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
fails = []
def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok: fails.append(name)
with pw.sync_playwright() as p:
    b = launch(p); pg = b.new_page(viewport={'width': 1400, 'height': 1000})
    pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin')); pg.click('button[type=submit]'); pg.wait_for_load_state('load')
    for brand, path in (('rozela', '/cs#/b/rozela'), ('celesta', '/cs/en#/b/celesta/action'), ('velora', '/cs#/b/velora/health')):
        pg.goto(BASE + path); pg.reload(); pg.wait_for_selector('a.row', timeout=60000); pg.wait_for_timeout(2500)
        tabs = pg.evaluate("() => Array.from(document.querySelectorAll('#tabs a.tab')).map(e => e.className.replace('tab ', '') + ':' + e.innerText.replace(/\\n/g,' '))")
        st = pg.evaluate("() => { const o = {}; document.querySelectorAll('a.row [data-test=row-status]').forEach(e => { const k = e.getAttribute('data-status') + '=' + e.innerText; o[k] = (o[k]||0)+1; }); return o; }")
        rows = pg.locator('a.row').count()
        nolabel = pg.evaluate("() => Array.from(document.querySelectorAll('a.row')).filter(r => !r.querySelector('[data-test=row-status]')).length")
        sel = pg.evaluate("() => (document.querySelector('#tabs a.tab[aria-selected=true]')||{className:''}).className")
        n = pg.evaluate("() => (document.querySelector('#tabs a.tab.ready .n')||{innerText:''}).innerText")
        print('  %s tabs: %s' % (brand, ' | '.join(tabs)))
        say(not any(t.split(':')[0] in ('action', 'health', 'delay') for t in tabs), brand + ': no separate needs-decision / health / delay tabs')
        say('ready' in sel, brand + ': the link opens the one open list', path)
        say(rows > 0 and nolabel == 0, brand + ': every row carries a status label', 'rows %d, open-list count %s, labels %s' % (rows, n, json.dumps(st, ensure_ascii=False)))
        say(len(st) > 1 or rows < 3, brand + ': the list mixes the kinds', '')
    t0 = time.time(); pg.locator('a.row').first.click()
    pg.wait_for_selector('[data-test=send-btn], [data-test=en-draft] textarea, [data-test=wa-win-chip], [data-test=why-human]', timeout=60000)
    say(True, 'a ticket opens from the one list', 'in %.2f s' % (time.time() - t0))
    b.close()
print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
sys.exit(1 if fails else 0)
