#!/usr/bin/env python3
"""LIVE acceptance test of the team screen for one brand: a real browser, the real site, a real Gmail send.

  .venv/bin/python tools/live_ui_send.py <brand> [--desk he|en|both]

No person receives anything: the "customer" is cstest-*@example.com (a domain reserved for tests). For each desk it plants an
inbound mail in the brand's mailbox, waits for the ticket and its draft, opens the ticket in the browser as an agent, sends with
the real buttons, and then checks IN GMAIL that exactly that text left, once. Prints timings. Exit code 1 on any failure.
The two temporary test users are disabled again at the end.
"""
import base64, json, os, re, secrets, subprocess, sys, time, uuid
import urllib.request

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'deploy'))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tests'))
import render_deploy as rd          # noqa: E402  (Client, kc_get)
from pw_launch import launch, pw    # noqa: E402

BASE = 'https://cs-team-screen.onrender.com'
GM = 'https://gmail.googleapis.com/gmail/v1/users/me/'
fails = []


def say(ok, name, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ('  ' + extra if extra else ''), flush=True)
    if not ok:
        fails.append(name)


def gmail(token, method, path, body=None):
    req = urllib.request.Request(GM + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def header(m, name):
    return next((h['value'] for h in m['payload'].get('headers', []) if h['name'].lower() == name), '')


def plain(part):
    if not part:
        return None
    if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(part['body']['data'] + '===').decode('utf-8')
    for p in part.get('parts') or []:
        t = plain(p)
        if t is not None:
            return t
    return None


def core(brand, fn, args, user='driver', role='admin'):
    out = subprocess.run(['node', os.path.join(ROOT, 'core', 'tools', 'corecall.js'), brand, fn, json.dumps(args), '--user', user, '--role', role],
                         capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout) if out.stdout.strip() else {'ok': False, 'error': out.stderr[:200]}


def plant(token, mailbox, subject, body):
    customer = 'cstest-%s@example.com' % uuid.uuid4().hex[:10]
    lines = ['From: Test Customer <%s>' % customer, 'To: ' + mailbox, 'Subject: =?UTF-8?B?%s?=' % base64.b64encode(subject.encode()).decode(),
             'Message-ID: <cstest.%s@example.com>' % uuid.uuid4(), 'Date: ' + time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime()), 'MIME-Version: 1.0',
             'Content-Type: text/plain; charset=UTF-8', 'Content-Transfer-Encoding: base64', '', base64.b64encode(body.encode()).decode()]
    m = gmail(token, 'POST', 'messages?internalDateSource=dateHeader', {'raw': base64.urlsafe_b64encode('\r\n'.join(lines).encode()).decode(), 'labelIds': ['INBOX', 'UNREAD']})
    return m['threadId'], customer


def wait_draft(brand, tid, max_s=150):
    t0 = time.time()
    while time.time() - t0 < max_s:
        core(brand, 'apiAdminRun', {'job': 'runAgent', 'budget': 120})
        t = core(brand, 'apiTicketFull', {'id': tid})
        if t.get('ok') and (t.get('ticket') or {}).get('draft_text'):
            return t['ticket'], time.time() - t0
        time.sleep(4)
    return None, time.time() - t0


def ensure_user(admin, name, lang, brands):
    """A temporary agent with a fresh one-time password (created, or reset and re-enabled)."""
    _, page = admin.req('GET', '/api/manage/users')
    users = {u['username']: u for u in json.loads(page).get('users', [])}
    if name in users:
        admin.req('POST', '/api/manage/users/' + name, js={'disabled': False, 'brands': brands, 'lang': lang, 'roles': ['agent']})
        _, page = admin.req('POST', '/api/manage/users/%s/reset' % name, js={})
    else:
        _, page = admin.req('POST', '/api/manage/users', js={'username': name, 'display_name': 'QA core', 'roles': ['agent'], 'brands': brands, 'lang': lang})
    j = json.loads(page)
    if not j.get('ok'):
        raise SystemExit('could not prepare user %s: %s' % (name, page[:200]))
    return j['temp_password']


def login(p, name, temp, lang):
    browser = launch(p)
    pg = browser.new_page(viewport={'width': 1280, 'height': 900})
    pg.goto(BASE + ('/cs/en/login' if lang == 'en' else '/cs/login'))
    pg.fill('input[name=username]', name)
    pg.fill('input[name=password]', temp)
    pg.click('button[type=submit]')
    pg.wait_for_load_state('load')      # not "network idle": a long list keeps translating rows in the background for a while
    if '/cs/password' in pg.url:
        new = secrets.token_urlsafe(18)
        pg.fill('input[name=current]', temp)
        pg.fill('input[name=new]', new)
        pg.fill('input[name=repeat]', new)
        pg.click('button[type=submit]')
        pg.wait_for_load_state('load')
    return browser, pg


def outbox_state(pg, tid):
    items = pg.evaluate("JSON.parse(localStorage.getItem('cs.outbox') || '{}')")
    return [i for i in items.values() if i.get('id') == tid]


def run_desk(p, brand, lang, token, mailbox, admin):
    label = 'English desk' if lang == 'en' else 'Hebrew desk'
    tag = str(secrets.randbelow(900000) + 100000)   # digits only: the delivery check refuses unknown Latin tokens, as it should
    thread, customer = plant(token, mailbox, 'שאלה על המוצר ' + tag, 'היי, רציתי לדעת מתי הכי טוב לקחת את הקפסולות, בבוקר או בערב? תודה. בדיקה ' + tag)
    tid = 't' + thread
    ticket, took = wait_draft(brand, tid)
    say(ticket is not None, '%s: mail became a ticket with a draft' % label, 'in %.1f s' % took)
    if not ticket:
        return
    name = 'qa-core-' + lang
    browser, pg = login(p, name, ensure_user(admin, name, lang, [brand]), lang)
    try:
        sends = []
        pg.on('request', lambda r: sends.append((time.time(), json.loads(r.post_data))) if r.url.endswith('/apiSend') else None)
        t_open = time.time()
        pg.goto(BASE + ('/cs/en' if lang == 'en' else '/cs') + '#/b/%s/t/%s' % (brand, tid))
        if lang == 'en':
            pg.wait_for_selector('[data-test=en-draft] textarea', timeout=60000)
            say(True, '%s: ticket opens' % label, 'in %.2f s' % (time.time() - t_open))
            english = 'Hi, thanks for reaching out. You can take the capsules in the morning or in the evening - what matters is taking them every day, preferably with a meal. System check %s.' % tag
            pg.fill('[data-test=en-draft] textarea', english)
            t_tr = time.time()
            pg.click('[data-test=en-review-btn]')
            pg.wait_for_selector('[data-test=en-confirm]:not([disabled])', timeout=60000)
            approved = pg.inner_text('[data-test=en-review] .out .txt')
            say(bool(re.search('[֐-׿]', approved)) and not re.search('[‒-―]|--', approved) and not re.search(r'[A-Za-z]{4,}', approved.replace(tag, '')),
                '%s: Hebrew preview is Hebrew, with no long dash' % label, 'translated in %.1f s: %s' % (time.time() - t_tr, approved.replace('\n', ' ')[:150]))
            t_click = time.time()
            pg.click('[data-test=en-confirm]')
        else:
            pg.wait_for_selector('[data-test=send-btn]', timeout=60000)
            say(True, '%s: ticket opens' % label, 'in %.2f s' % (time.time() - t_open))
            approved = ticket['draft_text']
            pg.click('[data-test=send-btn]')          # first click arms the button
            pg.wait_for_timeout(350)
            t_click = time.time()
            pg.click('[data-test=send-btn]')          # second click sends
        t_free = None
        state = []
        for _ in range(600):
            state = outbox_state(pg, tid)
            if t_free is None and state:
                t_free = time.time()                  # the action is in the background queue: the agent is already free
            if any(i.get('state') == 'ok' for i in state):
                break
            if any(i.get('state') in ('refused', 'unknown', 'failed') for i in state):
                break
            pg.wait_for_timeout(100)
        t_done = time.time()
        ok = any(i.get('state') == 'ok' for i in state)
        say(ok, '%s: the screen confirms the send' % label, 'agent free after %.2f s, confirmed after %.2f s%s' % ((t_free or t_done) - t_click, t_done - t_click, '' if ok else ' state=%s' % json.dumps(state, ensure_ascii=False)[:300]))
        say(len(sends) == 1, '%s: exactly one send request left the browser' % label, 'requests=%d' % len(sends))
        th = gmail(token, 'GET', 'threads/%s?format=full' % thread)
        out = [m for m in th['messages'] if 'SENT' in m.get('labelIds', [])]
        say(len(out) == 1, '%s: exactly one mail was sent in Gmail' % label, 'sent=%d' % len(out))
        if out:
            body = (plain(out[0]['payload']) or '').replace('\r\n', '\n').strip()
            say(body == approved.replace('\r\n', '\n').strip(), '%s: the mail text is exactly the approved text' % label, '%d chars' % len(body))
            say(customer in header(out[0], 'to') and header(out[0], 'in-reply-to') == header(th['messages'][0], 'message-id'), '%s: right recipient, same thread' % label)
            print('     %s timings: click -> Gmail accepted %.2f s' % (label, int(out[0]['internalDate']) / 1000.0 - t_click), flush=True)
        after = core(brand, 'apiTicketFull', {'id': tid}).get('ticket') or {}
        say(after.get('status') == 'sent' and after.get('handled_by') == name, '%s: ticket marked sent by the agent' % label, 'status %s' % after.get('status'))
        pg.reload()
        pg.wait_for_load_state('load')
        pg.wait_for_timeout(6000)
        th2 = gmail(token, 'GET', 'threads/%s?format=minimal' % thread)
        say(len([m for m in th2['messages'] if 'SENT' in m.get('labelIds', [])]) == 1 and len(sends) == 1, '%s: reloading the page does not send again' % label)
    finally:
        browser.close()
        admin.req('POST', '/api/manage/users/' + name, js={'disabled': True})
        core(brand, 'apiClose', {'id': tid}, user='qa-core', role='agent')


def main():
    brand = sys.argv[1]
    desk = sys.argv[sys.argv.index('--desk') + 1] if '--desk' in sys.argv else 'both'
    with psycopg.connect(rd.kc_get('all/CORE_DB_URL_EXTERNAL')) as c:
        row = c.execute("select access_token, email from cs_tokens where brand = %s and expires_at > now() + interval '8 minutes'", (brand,)).fetchone()
    if not row:
        raise SystemExit('no valid mailbox token for %s on the core' % brand)
    token, mailbox = row
    admin = rd.Client(BASE)
    admin.req('GET', '/cs/login')
    final, _ = admin.req('POST', '/cs/login', {'username': rd.BOT, 'password': rd.kc_get('screen/claude-admin'), 'csrf': admin.csrf})
    admin.req('GET', '/cs')
    with pw.sync_playwright() as p:
        for lang in (['he', 'en'] if desk == 'both' else [desk]):
            try:
                run_desk(p, brand, lang, token, mailbox, admin)
            except Exception as e:   # one desk failing must not hide the other
                say(False, '%s desk: no exception' % lang, repr(e)[:300])
    print('RESULT: ' + ('%d FAILED' % len(fails) if fails else 'ALL PASSED'))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
