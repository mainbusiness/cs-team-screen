#!/usr/bin/env python3
"""LIVE read-only check of the 24-hour WhatsApp features on the real screen for one brand: the tab, the labels, the blocked free-text send
and the template picker with that brand's templates. NOTHING is sent (the template button is never clicked).

  .venv/bin/python tools/live_ui_wa24.py <brand> [he|en]
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_ui_send as L          # noqa: E402  (helpers: login, ensure_user, admin client)
from pw_launch import pw          # noqa: E402


def main():
    brand, lang = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'he')
    admin = L.rd.Client(L.BASE)
    admin.req('GET', '/cs/login')
    admin.req('POST', '/cs/login', {'username': L.rd.BOT, 'password': L.rd.kc_get('screen/claude-admin'), 'csrf': admin.csrf})
    admin.req('GET', '/cs')
    name = 'qa-core-' + lang
    fails = []
    def say(ok, what, extra=''):
        print(('PASS ' if ok else 'FAIL ') + what + ('  ' + extra if extra else ''), flush=True)
        if not ok:
            fails.append(what)
    with pw.sync_playwright() as p:
        browser, pg = L.login(p, name, L.ensure_user(admin, name, lang, [brand]), lang)
        try:
            root = '/cs/en' if lang == 'en' else '/cs'
            t0 = time.time()
            pg.goto(L.BASE + root + '#/b/%s/wa24' % brand)
            pg.wait_for_selector('a.tab.wa24', timeout=60000)
            pg.wait_for_selector('#list-pane > a.row', timeout=60000)
            n = pg.inner_text('a.tab.wa24 .n')
            rows = pg.eval_on_selector_all('#list-pane > a.row', 'els => els.map(e => e.getAttribute("data-id"))')
            say(len(rows) > 0, 'the "over 24 hours" tab lists chats', 'tab count %s, rows %d, loaded in %.1f s' % (n, len(rows), time.time() - t0))
            chips = pg.locator('#list-pane > a.row [data-test=wa-win-chip]').count()
            say(chips == len(rows), 'every row there carries the 24-hour label', '%d of %d' % (chips, len(rows)))
            sends = []
            pg.on('request', lambda r: sends.append(r.url) if ('/apiSend' in r.url) else None)
            pg.goto(L.BASE + root + '#/b/%s/t/%s' % (brand, rows[0]))
            pg.wait_for_selector('[data-test=wa-win-note]', timeout=60000)
            pg.wait_for_selector('[data-test=tpl-select] option', state='attached', timeout=60000)
            names = pg.eval_on_selector_all('[data-test=tpl-select] option', 'els => els.map(e => e.textContent)')
            say(len(names) > 0, 'the template picker offers this brand\'s Dondy templates', json.dumps(names, ensure_ascii=False))
            say(len(pg.inner_text('[data-test=tpl-preview]').strip()) > 5, 'the chosen template\'s text is shown before sending')
            free = pg.locator('[data-test=send-btn]')
            say((not free.count()) or free.is_disabled(), 'a free-text send is not offered for this chat')
            say(not pg.is_disabled('[data-test=tpl-send]'), 'the "send template" button is ready (NOT clicked by this check)')
            say(sends == [], 'nothing was sent by this check')
        finally:
            browser.close()
            admin.req('POST', '/api/manage/users/' + name, js={'disabled': True})
    print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
