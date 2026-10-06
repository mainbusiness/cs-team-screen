"""English desk must preview Hebrew and never send stale / untranslated English."""
import json
import pytest
from browser_server import start
from pw_launch import launch, pw

@pytest.fixture(scope='module')
def english_server():
    base, pwd, proc = start(users=(("english-agent", ["agent"], ["rozela"], "en"),))
    yield base, pwd
    proc.terminate()

@pytest.mark.parametrize('width', [375, 768, 1280])
def test_english_desk_hebrew_preview_and_guard(english_server, width):
    base, pwd = english_server
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={'width': width, 'height': 900})
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.goto(base + '/cs/login')
        pg.fill('input[name=username]', 'english-agent')
        pg.fill('input[name=password]', pwd)
        pg.click('button[type=submit]')
        def english_metadata(route):
            response = route.fetch()
            data = response.json()
            if data.get('ticket'): data['ticket']['language'] = 'en'
            route.fulfill(response=response, json=data)
        pg.route('**/api/rozela/ticket', english_metadata)
        pg.goto(base + '/cs/en#/b/rozela/t/t18f2a03')
        pg.wait_for_selector('[data-test=en-draft] textarea')
        assert pg.locator('[data-test=english-workspace]').inner_text() == 'English desk'
        assert 'Hebrew' in pg.inner_text('[data-test=hebrew-only-notice]')
        ta = pg.locator('[data-test=en-draft] textarea')
        ta.fill('Hello, I will check this for you.')
        pg.route('**/translate-out', lambda r: r.fulfill(content_type='application/json', body=json.dumps({'ok': True, 'text': 'Hello customer', 'target': 'en', 'same': True})))
        pg.click('[data-test=en-review-btn]')
        pg.wait_for_selector('[data-test=en-draft] [role=alert]')
        assert 'Nothing was sent' in pg.inner_text('[data-test=en-draft] [role=alert]')
        assert not pg.locator('[data-test=en-confirm]').count()
        pg.unroute('**/translate-out')
        pg.route('**/translate-out', lambda r: r.fulfill(content_type='application/json', body=json.dumps({'ok': True, 'text': 'היי, אבדוק את זה בשבילך.', 'target': 'he', 'same': False})))
        pg.click('[data-test=en-review-btn]')
        pg.wait_for_selector('[data-test=en-confirm]')
        assert 'היי' in pg.inner_text('[data-test=en-review]')
        pg.screenshot(path='/tmp/english-desk-%s.png' % width, full_page=True)
        ta.fill('I edited the reply.')
        assert not pg.locator('[data-test=en-confirm]').count()
        assert 'translate again' in pg.inner_text('[data-test=en-draft] [role=alert]')
        pg.goto(base + '/cs/en#/b/rozela/t/t18f2a12')
        pg.wait_for_selector('.tk-head h2')
        assert pg.evaluate("localStorage.getItem('cs.draft.en.rozela.t18f2a03')") == 'I edited the reply.'
        assert not errors
        browser.close()


def test_new_message_translates_while_english_draft_is_kept(english_server):
    from test_speed_browser import push_new_message, NEW_MSG
    base, pwd = english_server
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={'width': 1280, 'height': 900})
        pg.goto(base + '/cs/en/login')
        pg.fill('input[name=username]', 'english-agent')
        pg.fill('input[name=password]', pwd)
        pg.click('button[type=submit]')
        calls = []

        def translate(route):
            calls.append(1)
            conversation = [{'i': i, 'text': 'English message %s, revision %s' % (i, len(calls))} for i in range(30)]
            route.fulfill(json={'ok': True, 'source': 'he', 'conversation': conversation,
                                'summary': 'English summary', 'draft': 'An English reply'})

        pg.route('**/api/rozela/translate', translate)
        pg.goto(base + '/cs/en#/b/rozela/t/t18f2a03')
        pg.wait_for_selector('#tk-conv .msg[data-tr="1"]')
        ta = pg.locator('[data-test=en-draft] textarea')
        ta.fill('My draft must stay exactly as I wrote it.')
        ta.focus()
        original_count = len(calls)
        push_new_message(pg, base, 't18f2a03')
        pg.wait_for_selector('[data-test=tk-live]:not([hidden])', timeout=12000)
        pg.wait_for_selector('[data-test=tk-live] .live-text:has-text("English message")')
        assert len(calls) > original_count
        assert ta.input_value() == 'My draft must stay exactly as I wrote it.'
        assert pg.evaluate('document.activeElement.tagName') == 'TEXTAREA'
        assert NEW_MSG not in pg.inner_text('#tk-conv')
        assert 'English message' in pg.inner_text('#tk-conv .msg:last-child .mbody')
        browser.close()


@pytest.fixture
def english_page(english_server):
    base, pwd = english_server
    with pw.sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.goto(base + '/cs/en/login')
        page.fill('input[name=username]', 'english-agent')
        page.fill('input[name=password]', pwd)
        page.click('button[type=submit]')
        page.goto(base + '/cs/en#/b/rozela/t/t18f2a03')
        page.wait_for_selector('[data-test=en-draft] textarea')
        page.wait_for_load_state('networkidle')
        yield page, base
        browser.close()


def test_english_translation_failure_retry_preview_and_single_hebrew_send(english_page):
    page, base = english_page
    calls, sends = [], []
    hebrew = 'שלום, אבדוק עבורך את סטטוס ההזמנה.'
    def translation(route, req):
        calls.append(json.loads(req.post_data))
        if len(calls) == 1:
            route.fulfill(status=503, json={'ok': False, 'error': 'busy', 'msg': 'Translation is busy; try again.'})
        else:
            route.fulfill(json={'ok': True, 'target': 'he', 'text': hebrew, 'same': False})
    def send(route, req):
        sends.append(json.loads(req.post_data))
        route.fulfill(json={'ok': True})
    page.route('**/api/rozela/translate-out', translation)
    page.route('**/api/rozela/apiSend', send)
    text = 'Hello, I will check your order status.'
    page.fill('[data-test=en-draft] textarea', text)
    page.click('[data-test=en-review-btn]')
    page.wait_for_selector('[data-test=en-draft] [role=alert]')
    assert page.input_value('[data-test=en-draft] textarea') == text
    assert page.is_enabled('[data-test=en-review-btn]')
    assert not sends
    page.click('[data-test=en-review-btn]')
    page.wait_for_selector('[data-test=en-confirm]:not([disabled])')
    assert hebrew in page.inner_text('[data-test=en-review]')
    page.click('[data-test=en-confirm]')
    page.wait_for_timeout(500)
    assert len(sends) == 1 and sends[0]['args']['text'] == hebrew
    assert len(calls) == 2 and all(c['text'] == text for c in calls)


def test_english_edit_during_translation_rejects_stale_preview(english_page):
    page, base = english_page
    pending = []
    sends = []
    page.route('**/api/rozela/translate-out', lambda route: pending.append(route))
    page.route('**/api/rozela/apiSend', lambda route: (sends.append(1), route.fulfill(json={'ok': True})))
    page.fill('[data-test=en-draft] textarea', 'Original reply')
    page.click('[data-test=en-review-btn]')
    for _ in range(50):
        if pending: break
        page.wait_for_timeout(50)
    assert pending
    page.fill('[data-test=en-draft] textarea', 'Changed while translating')
    pending.pop().fulfill(json={'ok': True, 'target': 'he', 'text': 'הטקסט הישן', 'same': False})
    page.wait_for_selector('[data-test=en-draft] [role=alert]')
    assert not page.locator('[data-test=en-confirm]').count()
    assert page.is_enabled('[data-test=en-review-btn]')
    assert page.evaluate("localStorage.getItem('cs.draft.en.rozela.t18f2a03')") == 'Changed while translating'
    assert not sends


def test_english_rejected_outbox_handoff_does_not_latch_busy(english_page):
    import time
    page, base = english_page
    rid = 'e' * 32
    item = dict(rid=rid, brand='rozela', id='t18f2a03', fn='apiSend', args={}, channel='email',
                name='Test', state='checking', at=int(time.time() * 1000))
    page.evaluate("v => localStorage.setItem('cs.outbox', v)", json.dumps({rid: item}))
    results, sends = [], []
    page.route('**/api/rozela/result', lambda route: results.append(route))
    page.route('**/api/rozela/translate-out', lambda route: route.fulfill(json={'ok': True, 'target': 'he', 'text': 'שלום, אבדוק עבורך', 'same': False}))
    page.route('**/api/rozela/apiSend', lambda route: (sends.append(1), route.fulfill(json={'ok': True})))
    page.reload()
    page.wait_for_selector('[data-test=en-draft] textarea')
    page.fill('[data-test=en-draft] textarea', 'Check this for me')
    page.click('[data-test=en-review-btn]')
    page.wait_for_selector('[data-test=en-confirm]')
    assert page.is_disabled('[data-test=en-confirm]')
    # A queued click racing with another in-flight action must not permanently latch the editor busy.
    page.dispatch_event('[data-test=en-confirm]', 'click')
    for _ in range(60):
        if results: break
        page.wait_for_timeout(50)
    assert results
    results.pop().fulfill(json={'ok': True, 'found': True, 'reply': {'ok': False, 'error': 'busy'}})
    page.wait_for_timeout(300)
    assert page.is_enabled('[data-test=en-review-btn]')
    assert page.is_enabled('[data-test=en-confirm]')
    assert page.input_value('[data-test=en-draft] textarea') == 'Check this for me'
    assert not sends
