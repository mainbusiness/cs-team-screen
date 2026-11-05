#!/usr/bin/env python3
"""LIVE read-only check of "⏸ השהיית מנוי" / "⏭ דחיית משלוח" (Owner, 2026-11-01). Per subscription brand: a ticket whose customer has a live
Kaching contract shows both buttons next to the cancel; each opens its dialog, loads the contract (read), previews a plan, and reaches the
4-digit confirm, where a WRONG code keeps "לבצע" disabled. The right code is never typed: nothing is written to Kaching.
   .venv/bin/python tools/live_ui_pause_postpone.py"""
import hashlib, json, os, subprocess, sys, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(CS, 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
fails = []
def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok: fails.append(name)


JS = r"""const { coreCall } = require(process.argv[1] + '/core/tools/corecall.js');
(async () => { const out = {};
  for (const b of ['rozela', 'celesta', 'apexmen', 'velora']) {
    const boot = await coreCall(b, 'apiBoot', {}, { role: 'agent', user: 'claude-probe' });
    out[b] = (boot.tickets || boot.rows || []).filter((t) => /cancel: gid/.test(String(t.action || '')) || t.category === 'cancel_subscription').map((t) => t.id).slice(0, 8);
  } console.log(JSON.stringify(out)); })();"""
ids = json.loads(subprocess.run(['node', '-e', JS, CS], capture_output=True, text=True, check=True).stdout)

with pw.sync_playwright() as p:
    b = launch(p); pg = b.new_page(viewport={'width': 1400, 'height': 1000})
    pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin')); pg.click('button[type=submit]'); pg.wait_for_load_state('load')
    # the code that runs is the code that was pushed: the app.js THIS page loaded vs the pushed mirror
    src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
    live = pg.request.get(src).body() if src else b''
    mine = open(os.path.join(CS, 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
    say(bool(live) and hashlib.sha256(live).hexdigest() == hashlib.sha256(mine).hexdigest(), 'the served app.js is the pushed one', '%s sha %s' % (src.rsplit('/', 1)[-1], hashlib.sha256(live).hexdigest()[:12]))
    for s in (b'sub_pause_btn', "⏸ השהיית מנוי".encode(), "⏭ דחיית משלוח".encode(), b"'pause_until'", b"'postpone'"):
        say(s in live, 'live app.js carries ' + s.decode())
    for brand, tids in ids.items():
        found = False
        for tid in tids:
            pg.goto(BASE + '/cs#/b/%s/t/%s' % (brand, tid)); pg.reload()
            try:
                pg.wait_for_selector('#subs-card .item-card, #subs-card [data-test=subs-empty]', timeout=60000)
            except Exception:
                continue
            if pg.locator('[data-test=sub-pause]').count() == 0:
                continue
            found = True
            acts = pg.locator('[data-test=sub-pause]').first.locator('xpath=..').locator('button').all_inner_texts()
            say(acts[1:3] == ['⏸ השהיית מנוי', '⏭ דחיית משלוח'] and acts[-1] == 'ביטול מנוי', brand + ': both buttons next to the cancel', ' | '.join(acts))
            for kind, preset in (('sub-pause', 'm1'), ('sub-postpone', 'w2')):
                pg.locator('[data-test=%s]' % kind).first.click()
                pg.wait_for_selector('[data-test=pp-dlg] [data-test=pp-preset-%s], #sub-dlg .err-box' % preset, timeout=60000)
                if pg.locator('#sub-dlg .err-box').count():
                    say(False, brand + ': ' + kind + ' dialog loads the contract', pg.locator('#sub-dlg .err-box').inner_text()[:120]); pg.keyboard.press('Escape'); continue
                pg.locator('[data-test=pp-preset-%s]' % preset).click()
                prev = pg.locator('[data-test=pp-preview]').inner_text()
                planned = pg.locator('[data-test=pp-what]').count() > 0
                say(planned or pg.locator('[data-test=pp-err]').count() > 0, brand + ': ' + kind + ' previews', ' / '.join(prev.splitlines()[:2])[:160])
                if planned:
                    pg.locator('[data-test=pp-next]').click()
                    pg.wait_for_selector('[data-test=mg-go]')
                    pg.fill('#sub-dlg input.code', '0000')
                    say(pg.is_disabled('[data-test=mg-go]'), brand + ': ' + kind + ' confirm stays locked on a wrong code (nothing sent)')
                pg.keyboard.press('Escape'); pg.wait_for_timeout(400)
            break
        say(found, brand + ': a ticket with a live subscription was found and checked', '%d candidates' % len(tids))
    b.close()
print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
sys.exit(1 if fails else 0)
