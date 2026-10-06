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
        pg.wait_for_function("document.querySelector('[data-test=tk-live] .live-text').textContent.startsWith('English message')")
        assert len(calls) > original_count
        assert ta.input_value() == 'My draft must stay exactly as I wrote it.'
        assert pg.evaluate('document.activeElement.tagName') == 'TEXTAREA'
        assert NEW_MSG not in pg.inner_text('#tk-conv')
        assert 'English message' in pg.inner_text('#tk-conv .msg:last-child .mbody')
        browser.close()
