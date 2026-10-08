#!/usr/bin/env python3
"""LIVE, read-only: tickets that came from a brand's SECOND mailbox are in the screen's one open list, and one of them opens with its
conversation.   .venv/bin/python tools/live_ui_mailbox2.py <brand> <file with a JSON list of ticket ids>"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), 'deploy')); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402
from pw_launch import launch, pw    # noqa: E402
BASE = 'https://cs-team-screen.onrender.com'
brand, ids = sys.argv[1], set(json.load(open(sys.argv[2])))
fails = []
def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok: fails.append(name)
with pw.sync_playwright() as p:
    b = launch(p); pg = b.new_page(viewport={'width': 1400, 'height': 1000})
    pg.goto(BASE + '/cs/login'); pg.fill('input[name=username]', rd.BOT); pg.fill('input[name=password]', rd.kc_get('screen/claude-admin')); pg.click('button[type=submit]'); pg.wait_for_load_state('load')
    pg.goto(BASE + '/cs#/b/' + brand); pg.reload(); pg.wait_for_selector('a.row', timeout=60000); pg.wait_for_timeout(4000)
    shown = set(pg.evaluate("() => Array.from(document.querySelectorAll('a.row')).map(r => r.getAttribute('data-id'))"))
    hit = sorted(ids & shown)
    say(len(hit) == len(ids), 'every open ticket of the second mailbox is in the open list', '%d of %d shown (the list has %d rows)' % (len(hit), len(ids), len(shown)))
    if hit:
        t0 = time.time(); pg.goto(BASE + '/cs#/b/%s/t/%s' % (brand, hit[0]))
        pg.wait_for_selector('[data-test=send-btn], [data-test=why-human]', timeout=60000)
        body = pg.inner_text('#ticket-pane') if pg.locator('#ticket-pane').count() else pg.inner_text('body')
        say(len(body) > 200, 'a ticket from the second mailbox opens with its content', 'in %.2f s, %d characters on screen, send button: %s' % (time.time() - t0, len(body), pg.locator('[data-test=send-btn]').count() > 0))
    b.close()
print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
sys.exit(1 if fails else 0)
