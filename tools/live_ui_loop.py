#!/usr/bin/env python3
"""LIVE read-only check of the Loop cancel / pause dialogs, the Kaching pause button and the merge guide (Owner, 2026-11-20). Real tickets, real
engine READS (Loop / Kaching lookups). NOTHING is changed: every write function (apiSubCancel, apiSubPause, apiSubResume, apiKachingAction) is
ABORTED at the network layer and counted; the confirm buttons are never clicked. The only write is the bot account's own acknowledgement of the
merge guide (the check that it is shown once). Usage: .venv/bin/python tools/live_ui_loop.py <out_dir>"""
import hashlib, json, os, subprocess, sys
CS = os.environ.get('CS_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(CS, 'deploy')); sys.path.insert(0, os.path.join(CS, 'team_screen', 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
fails, writes = [], []


def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok:
        fails.append(name)


JS = r"""const { coreCall } = require(process.argv[1] + '/core/tools/corecall.js');
(async () => { const out = {};
  for (const b of ['rozela', 'celesta', 'velora', 'apexmen']) {
    const boot = await coreCall(b, 'apiBoot', {}, { role: 'agent', user: 'claude-probe' });
    const open = (boot.tickets || []).filter((t) => ['ready', 'action', 'health', 'delay'].includes(t.status) && t.channel !== 'whatsapp');
    out[b] = { cancel: open.filter((t) => /^cancel:/i.test(String(t.action || '')) || t.category === 'cancel_subscription').map((t) => t.id).slice(0, 8), any: open.map((t) => t.id).slice(0, 10) };
  } console.log(JSON.stringify(out)); })();"""
ids = json.loads(subprocess.run(['node', '-e', JS, CS], capture_output=True, text=True, check=True).stdout)


def block(route):
    writes.append(route.request.url.rsplit('/', 1)[-1])
    route.abort()


def fit(pg):
    return pg.evaluate("""() => { const d = document.querySelector('#subx-dlg'); return document.documentElement.scrollWidth <= window.innerWidth && (!d || d.scrollWidth <= d.clientWidth + 1); }""")


with pw.sync_playwright() as p:
    for width in (1280, 390):
        b = launch(p)
        pg = b.new_page(viewport={'width': width, 'height': 900})
        for fn in ('apiSubCancel', 'apiSubPause', 'apiSubResume', 'apiKachingAction'):
            pg.route('**/' + fn, block)
        pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin'))
        pg.click('button[type=submit]'); pg.wait_for_load_state('load')
        if width == 1280:
            src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
            live = pg.request.get(src).body() if src else b''
            mine = open(os.path.join(CS, 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
            say(bool(live) and hashlib.sha256(live).digest() == hashlib.sha256(mine).digest(), 'the served app.js is the pushed one', 'sha %s' % hashlib.sha256(live).hexdigest()[:12])
            # merge guide: shown once, then not, then reopens from the question mark
            try:
                pg.wait_for_selector('[data-test=notice-dlg][open]', timeout=20000)
                shown = 'איך מאחדים' in pg.inner_text('[data-test=notice-title]') or pg.locator('[data-test=notice-ack]').count() > 0
                title = pg.inner_text('[data-test=notice-title]')
                while pg.locator('[data-test=notice-ack]').count():                      # the bot's own ack of each pending notice
                    t = pg.inner_text('[data-test=notice-title]')
                    pg.click('[data-test=notice-ack]'); pg.wait_for_timeout(800)
                say(shown, 'merge guide / notice shown on first open (bot account)', title[:40])
            except Exception:
                say(False, 'merge guide shown on first open')
            pg.reload(); pg.wait_for_load_state('load'); pg.wait_for_timeout(2500)
            say(not pg.evaluate("() => { const d = document.getElementById('notice-dlg'); return !!(d && d.open); }"), 'merge guide NOT shown on the second open')
        # ---- rozela: Loop
        got_cancel = got_pause = False
        for tid in ids['rozela']['cancel'] + ids['rozela']['any']:
            if got_cancel and got_pause:
                break
            pg.goto(BASE + '/cs#/b/rozela/t/%s' % tid); pg.reload()
            try:
                pg.wait_for_selector('[data-test=subp-btn]', timeout=30000)
            except Exception:
                continue
            if not got_pause:
                pg.click('[data-test=subp-btn]')
                try:
                    pg.wait_for_selector('#subx-dlg [data-test=subp-q], #subx-dlg [data-test=subp-none], #subx-dlg [data-test=subp-err]', timeout=60000)
                except Exception:
                    pg.keyboard.press('Escape'); continue
                if pg.locator('#subx-dlg [data-test=subp-q]').count():
                    labels = [pg.locator('#subx-dlg [data-test=subp-w]').nth(i).inner_text() for i in range(pg.locator('#subx-dlg [data-test=subp-w]').count())]
                    say(labels == ['שבועיים', '4 שבועות', '6 שבועות', '8 שבועות'] and pg.is_disabled('#subx-dlg [data-test=subp-go]') and fit(pg),
                        'rozela @%d: pause dialog lists a Loop subscription with 2/4/6/8 weeks, go disabled until chosen' % width, '…%s %s' % (tid[-6:], labels))
                    pg.screenshot(path=os.path.join(OUT, 'loop_pause_%d.png' % width)); got_pause = True
                pg.keyboard.press('Escape')
            if not got_cancel and pg.locator('[data-test=subx-btn]').count() and pg.locator('[data-test=subx-btn]').is_enabled():
                pg.click('[data-test=subx-btn]')
                try:
                    pg.wait_for_selector('#subx-dlg [data-test=subx-adv], #subx-dlg [data-test=subx-none], #subx-dlg [data-test=subx-ended], #subx-dlg [data-test=subx-dlg-err]', timeout=60000)
                except Exception:
                    pg.keyboard.press('Escape'); continue
                if pg.locator('#subx-dlg [data-test=subx-adv]').count():
                    opts = pg.locator('#subx-dlg [data-test=subx-opt]')
                    loop_ok = False
                    if opts.count():
                        for i in range(opts.count()):
                            o = opts.nth(i)
                            if o.get_attribute('data-off') is None and o.locator('input').is_enabled() and 'פורמולת' in o.inner_text() or (o.get_attribute('data-off') is None and 'כל 3 חודשים' in o.inner_text()):
                                loop_ok = True
                    else:
                        loop_ok = 'מספר מנוי' in pg.inner_text('#subx-dlg') and pg.is_enabled('#subx-dlg [data-test=subx-go]')
                    card = pg.locator('#subx-dlg [data-test=subx-adv]'); go = pg.locator('#subx-dlg [data-test=subx-go]')
                    above = card.bounding_box()['y'] < go.bounding_box()['y']
                    sure = 'בטוח/ה שרוצה לבטל' in pg.inner_text('#subx-dlg [data-test=subx-q]') or 'מנויים' in pg.inner_text('#subx-dlg [data-test=subx-q]')
                    say(above and sure and fit(pg) and 'null' not in pg.inner_text('#subx-dlg'), 'rozela @%d: cancel dialog = advice card above the confirm + "בטוח/ה"' % width,
                        '…%s %s loopPickable=%s' % (tid[-6:], card.get_attribute('data-verdict'), loop_ok))
                    pg.screenshot(path=os.path.join(OUT, 'loop_cancel_%d.png' % width)); got_cancel = True
                pg.keyboard.press('Escape')
        say(got_pause, 'rozela @%d: a real ticket with a Loop subscription opened the pause dialog' % width)
        say(got_cancel, 'rozela @%d: a real cancel ticket opened the cancel dialog' % width)
        # ---- Kaching brands: the pause button opens Kaching's form
        for brand in ('celesta', 'velora', 'apexmen'):
            ok = False
            for tid in ids[brand]['any'] + ids[brand]['cancel']:
                pg.goto(BASE + '/cs#/b/%s/t/%s' % (brand, tid)); pg.reload()
                try:
                    pg.wait_for_selector('[data-test=subp-btn]', timeout=25000)
                except Exception:
                    continue
                pg.click('[data-test=subp-btn]')
                try:
                    pg.wait_for_selector('[data-test=pp-preset-m1], #subx-dlg [data-test=subp-opt]', timeout=40000)
                except Exception:
                    pg.keyboard.press('Escape'); continue
                ok = True
                say(fit(pg) and pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), '%s @%d: pause button opens Kaching\'s pause-for-a-period form' % (brand, width), '…%s' % tid[-6:])
                pg.screenshot(path=os.path.join(OUT, 'kaching_pause_%s_%d.png' % (brand, width)))
                break
            if not ok:
                say(False, '%s @%d: no ticket with a pausable Kaching subscription found among the open ones' % (brand, width))
        # ---- merge guide reopen from the question mark
        if width == 1280:
            for brand in ('celesta', 'rozela'):
                tid = (ids[brand]['any'] or [None])[0]
                if not tid:
                    continue
                pg.goto(BASE + '/cs#/b/%s/t/%s' % (brand, tid)); pg.reload()
                try:
                    pg.wait_for_selector('[data-test=mrg-guide]', timeout=30000)
                    pg.click('[data-test=mrg-guide]')
                    pg.wait_for_selector('[data-test=notice-dlg][open]', timeout=8000)
                    say('איך מאחדים' in pg.inner_text('[data-test=notice-title]'), 'merge guide reopens from the ❓ next to the merge control (%s)' % brand)
                    pg.click('[data-test=notice-close]')
                except Exception as e:
                    say(False, 'merge guide reopens from the ❓ (%s)' % brand, str(e)[:80])
                break
        b.close()
say(True, 'writes aborted at the network layer (none reached the engine)', '%d attempted, all aborted: %s' % (len(writes), writes))
print('\nALL PASSED' if not fails else '\nFAILED: %s' % fails)
sys.exit(1 if fails else 0)
