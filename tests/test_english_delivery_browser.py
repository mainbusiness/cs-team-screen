"""English desk delivery: real browser -> Flask -> mock engine -> persisted receipt.
No apiSend/translate-out intercepts; never contacts live customer channels.
"""
import json
import pytest
from browser_server import start
from pw_launch import launch, pw

@pytest.fixture
def delivery_page():
    base, pwd, proc = start({"MOCK_SLOW_FNS": "apiSend:1200"}, users=(("lyra-test", ["agent"], ["rozela"], "en"),))
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(base + "/cs/en/login")
        pg.fill("input[name=username]", "lyra-test")
        pg.fill("input[name=password]", pwd)
        pg.click("button[type=submit]")
        yield pg, base
        browser.close()
    proc.terminate()


def api(pg, fn, args):
    return pg.evaluate("""async ([fn, args]) => (await fetch('/api/rozela/' + fn, {
      method:'POST', headers:{'Content-Type':'application/json',
      'X-CSRF-Token':document.querySelector('meta[name=csrf]').content,'X-UI-Lang':'en'},
      body:JSON.stringify(args)})).json()""", [fn, args])


def wait_outbox(pg, tid, state):
    for _ in range(100):
        items = pg.evaluate("JSON.parse(localStorage.getItem('cs.outbox') || '{}')")
        if any(i['id'] == tid and i['state'] == state for i in items.values()):
            return
        pg.wait_for_timeout(100)
    pytest.fail('Expected outbox state %s, got %r' % (state, items))


def preview(pg, base, tid):
    pg.goto(base + "/cs/en#/b/rozela/t/" + tid)
    pg.wait_for_selector("[data-test=en-draft] textarea")
    pg.fill("[data-test=en-draft] textarea", "Hello, thank you for contacting us. We will check and update you soon.")
    pg.click("[data-test=en-review-btn]")
    pg.wait_for_selector("[data-test=en-confirm]:not([disabled])")
    return pg.inner_text("[data-test=en-review] .out .txt")


@pytest.mark.parametrize('tid,channel,expected_status', [
    ('t18f2a01', 'email', 'sent'), ('w8ab77c1', 'whatsapp', 'wa_queued')])
def test_confirm_delivers_exact_hebrew_to_engine_and_recovers_receipt(delivery_page, tid, channel, expected_status):
    pg, base = delivery_page
    sends = []
    pg.on('request', lambda r: sends.append(json.loads(r.post_data)) if r.url.endswith('/apiSend') else None)
    approved = preview(pg, base, tid)
    assert 'שלום' in approved
    pg.click('[data-test=en-confirm]')
    wait_outbox(pg, tid, "ok")
    assert len(sends) == 1
    assert sends[0]['args']['text'] == approved
    assert sends[0]['lang'] == 'en'
    assert sends[0]['args'].get('channel', 'email') == channel
    receipt = api(pg, 'result', {'rid': sends[0]['rid']})
    assert receipt['ok'] and receipt['found'] and receipt['reply']['ok'], receipt
    ticket = api(pg, 'ticket', {'id': tid, 'revalidate': True})
    assert ticket['ticket']['status'] == expected_status
    assert ticket['ticket']['wa_out' if channel == 'whatsapp' else 'draft_text'] == approved
    if channel == 'email':
        assert ticket['extras']['conversation'][-1]['text'] == approved
    else:
        assert receipt['reply']['queued'] is True  # Queue acceptance is not a delivery claim.
    assert pg.evaluate("key => localStorage.getItem(key)", 'cs.draft.en.rozela.' + tid) is None
    pg.reload()
    pg.wait_for_load_state('networkidle')
    assert len(sends) == 1


@pytest.mark.parametrize('tid', ['t18f2a01', 'w8ab77c1'])
def test_refused_send_keeps_english_draft_and_can_be_retried(delivery_page, tid):
    pg, base = delivery_page
    attempts = []
    def refuse_once(route):
        attempts.append(json.loads(route.request.post_data))
        route.fulfill(json={'ok': False, 'error': 'busy', 'msg': 'Not sent. Please try again.'})
    pg.route('**/api/rozela/apiSend', refuse_once)
    preview(pg, base, tid)
    source = pg.input_value('[data-test=en-draft] textarea')
    pg.click('[data-test=en-confirm]')
    wait_outbox(pg, tid, "refused")
    pg.goto(base + '/cs/en#/b/rozela/t/' + tid)
    pg.wait_for_selector('[data-test=outbox-banner][data-state=refused]')
    assert pg.input_value('[data-test=en-draft] textarea') == source
    assert pg.is_enabled('[data-test=en-review-btn]')
    pg.unroute('**/api/rozela/apiSend')
    pg.click('[data-test=en-review-btn]')
    pg.wait_for_selector('[data-test=en-confirm]:not([disabled])')
    pg.click('[data-test=en-confirm]')
    wait_outbox(pg, tid, "ok")


@pytest.mark.parametrize('tid', ['t18f2a01', 'w8ab77c1'])
def test_reload_during_english_send_recovers_without_second_send(delivery_page, tid):
    pg, base = delivery_page
    sends = []
    pg.on('request', lambda r: sends.append(json.loads(r.post_data)) if r.url.endswith('/apiSend') else None)
    approved = preview(pg, base, tid)
    pg.click('[data-test=en-confirm]')
    pg.wait_for_timeout(150)
    assert len(sends) == 1
    pg.reload()
    wait_outbox(pg, tid, 'ok')
    receipt = api(pg, 'result', {'rid': sends[0]['rid']})
    assert receipt['found'] and receipt['reply']['ok']
    assert sends[0]['args']['text'] == approved
    assert len(sends) == 1


@pytest.mark.parametrize('channel,status,wa_send,match,expected,initial', [
    ('email', 'sent', '', False, 'checking', 'checking'),
    ('email', 'sent', '', True, 'ok', 'checking'),
    ('whatsapp', 'sent', 'failed:dondy-ext', True, 'checking', 'checking'),
    ('whatsapp', 'wa_queued', 'pending', False, 'checking', 'checking'),
    ('whatsapp', 'wa_queued', 'pending', True, 'ok', 'checking'),
    ('whatsapp', 'action', 'claimed', True, 'ok', 'checking'),
    ('whatsapp', 'done', 'sent', True, 'ok', 'checking'),
    ('whatsapp', 'done', 'sent:dondy-ext', True, 'ok', 'checking'),
    ('whatsapp', 'done', 'failed', True, 'checking', 'checking'),
    ('whatsapp', 'sent', 'sent:bridge', True, 'ok', 'ok'),
    ('whatsapp', 'sent', 'sent:bridge', False, 'ok', 'ok'),
    ('whatsapp', 'action', 'failed:bridge', True, 'delivery_issue', 'ok'),
    ('whatsapp', 'action', 'unknown:bridge', True, 'delivery_issue', 'ok'),
    ('whatsapp', 'action', 'template_required:bridge', True, 'delivery_issue', 'ok'),
    ('whatsapp', 'action', 'failed:bridge', False, 'ok', 'ok'),
    ('whatsapp', 'sent', 'sent:bridge', True, 'ok', 'delivery_issue'),
    ('whatsapp', 'wa_queued', 'pending', True, 'ok', 'delivery_issue'),
])
def test_lost_receipt_needs_exact_text_and_channel_evidence(delivery_page, channel, status, wa_send, match, expected, initial):
    import time
    from datetime import datetime, timezone
    pg, base = delivery_page
    tid = 't18f2a01' if channel == 'email' else 'w8ab77c1'
    now = int(time.time() * 1000)
    submitted = 'שלום, נבדוק ונעדכן בהקדם.'
    item = dict(rid='f'*32, brand='rozela', id=tid, fn='apiSend', args={'id':tid,'text':submitted},
                channel=channel, name='Test', state=initial, at=now, reply={'ok': True, 'queued': True})
    tk = dict(id=tid, channel=channel, status=status, wa_send=wa_send, handled_by='lyra-test',
              handled_at=datetime.fromtimestamp((now + 2000) / 1000, timezone.utc).isoformat(),
              draft_text=submitted if match else 'תשובה אחרת', wa_out=submitted if match else 'תשובה אחרת')
    pg.route('**/api/rozela/ticket', lambda route: route.fulfill(json={'ok':True,'ticket':tk,'extras':{},'cache':{'hit':False}}))
    pg.route('**/api/rozela/result', lambda route: route.fulfill(json={'ok':True,'found':False}))
    sends=[]
    pg.on('request', lambda r: sends.append(r.url) if r.url.endswith('/apiSend') else None)
    pg.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps({item['rid']:item}))
    pg.goto(base + "/cs/en#/b/rozela/t/" + tid)
    pg.reload()
    pg.wait_for_timeout(2800)
    stored=pg.evaluate("JSON.parse(localStorage.getItem('cs.outbox'))")
    assert stored[item['rid']]['state'] == expected
    if expected == 'ok':
        assert stored[item['rid']]['reply']['queued'] is (initial == 'ok' and (not match or not wa_send.startswith('sent')) or channel == 'whatsapp' and wa_send.split(':')[0] in ('pending', 'claimed'))
    if expected == 'delivery_issue':
        assert stored[item['rid']]['delivery_state'] == wa_send.split(':')[0]
        banner = pg.locator('[data-test=outbox-banner]')
        assert 'Queued for WhatsApp' not in banner.inner_text()
        assert banner.get_attribute('data-state') == 'delivery_issue'
        resend = pg.locator('[data-test=wa-resend]')
        if resend.count():
            assert resend.is_disabled()
    assert not sends
