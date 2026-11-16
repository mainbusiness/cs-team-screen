#!/usr/bin/env python3
"""LIVE read-only check of the "בטוח/ה?" advice in the "לבטל את המנוי" dialog (Owner, 2026-11-15). Per Kaching brand: open a real cancel ticket,
click "לבטל את המנוי" (the engine reads Kaching: a READ), and check the advice card renders above the confirm button, at 1280 and 390, with no
sideways scroll. NOTHING is cancelled: the cancel button is never clicked, and every request to the write function apiSubCancel is ABORTED at
the network layer (a second lock, in case of a misclick). Screenshots go to argv[1] (default: the current directory).
   .venv/bin/python tools/live_ui_cancel_advice.py <out_dir>"""
import hashlib, json, os, subprocess, sys
CS = os.environ.get('CS_ROOT') or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # team_screen/tools -> CS_Engine
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
  for (const b of ['rozela', 'celesta', 'apexmen', 'velora']) {
    const boot = await coreCall(b, 'apiBoot', {}, { role: 'agent', user: 'claude-probe' });
    out[b] = (boot.tickets || boot.rows || []).filter((t) => (/^cancel:/i.test(String(t.action || '')) || t.category === 'cancel_subscription') && !String(t.cancelled || '')).map((t) => t.id).slice(0, 6);
  } console.log(JSON.stringify(out)); })();"""
ids = json.loads(subprocess.run(['node', '-e', JS, CS], capture_output=True, text=True, check=True).stdout)


def block_writes(route, req=None):
    writes.append(route.request.url)
    route.abort()


with pw.sync_playwright() as p:
    for width in (1280, 390):
        b = launch(p)
        pg = b.new_page(viewport={'width': width, 'height': 900})
        pg.route('**/apiSubCancel', block_writes)                       # the write: never reaches the engine from this check
        pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin'))
        pg.click('button[type=submit]'); pg.wait_for_load_state('load')
        if width == 1280:
            src = pg.evaluate("() => Array.from(document.scripts).map(s => s.src).filter(s => /app\\.js/.test(s))[0] || ''")
            live = pg.request.get(src).body() if src else b''
            mine = open(os.path.join(CS, 'deploy', 'render_repo', 'static', 'app.js'), 'rb').read()
            say(bool(live) and hashlib.sha256(live).digest() == hashlib.sha256(mine).digest(), 'the served app.js is the pushed one',
                'sha %s' % hashlib.sha256(live).hexdigest()[:12])
            say(b'subx-adv' in live and 'לבטל בכל זאת'.encode() in live, 'live app.js carries the advice card')
        for brand, tids in ids.items():
            done = False
            for tid in tids:
                pg.goto(BASE + '/cs#/b/%s/t/%s' % (brand, tid)); pg.reload()
                try:
                    pg.wait_for_selector('[data-test=subx-btn]', timeout=45000)
                except Exception:
                    continue
                if not pg.locator('[data-test=subx-btn]').is_enabled():
                    continue
                pg.click('[data-test=subx-btn]')
                try:
                    pg.wait_for_selector('#subx-dlg [data-test=subx-adv], #subx-dlg [data-test=subx-ended], #subx-dlg [data-test=subx-none], '
                                         '#subx-dlg [data-test=subx-noemail], #subx-dlg [data-test=subx-dlg-err]', timeout=60000)
                except Exception:
                    pg.keyboard.press('Escape'); continue
                if pg.locator('#subx-dlg [data-test=subx-adv]').count() == 0:     # nothing live to cancel on this one: the next ticket
                    pg.keyboard.press('Escape'); continue
                card = pg.locator('#subx-dlg [data-test=subx-adv]')
                go = pg.locator('#subx-dlg [data-test=subx-go]')
                verdict = card.get_attribute('data-verdict')
                above = card.bounding_box()['y'] < go.bounding_box()['y']
                fit = pg.evaluate("""() => { const d = document.querySelector('#subx-dlg');
                    return document.documentElement.scrollWidth <= window.innerWidth && d.scrollWidth <= d.clientWidth + 1; }""")
                sure = 'בטוח/ה שרוצה לבטל' in pg.inner_text('#subx-dlg [data-test=subx-q]') or 'מנויים פעילים' in pg.inner_text('#subx-dlg [data-test=subx-q]')
                save = pg.locator('#subx-dlg [data-test=subx-save]').count()
                buttons_ok = (save == 1 and go.inner_text() == 'לבטל בכל זאת') if verdict == 'try_save' else (save == 0 and go.inner_text() == 'כן, לבטל את המנוי')
                say(verdict in ('cancel_ok', 'try_save', 'unknown') and above and fit and sure and buttons_ok,
                    '%s @%d: the advice card renders above the confirm' % (brand, width),
                    '…%s %s | %s' % (tid[-6:], verdict, ' / '.join(card.inner_text().splitlines())[:150]))
                pg.screenshot(path=os.path.join(OUT, 'live_%s_%d.png' % (brand, width)))
                pg.keyboard.press('Escape')                                    # close: nothing clicked inside
                done = True
                break
            if not done:
                say(False, '%s @%d: no open cancel ticket with a live subscription to open' % (brand, width))
        b.close()
say(not writes, 'no write request left the browser', str(writes))
print('ALL PASSED' if not fails else 'FAILED: %d' % len(fails))
sys.exit(1 if fails else 0)
