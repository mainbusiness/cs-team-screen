"""Hebrew desk, real browser (Owner, 2026-10-10): a Russian customer's message shows in Hebrew automatically, the original is
one click away, and the screen says replies go out in Hebrew only. Hebrew tickets make no translation call."""
import pytest
from browser_server import start
from pw_launch import launch, pw


@pytest.fixture(scope='module')
def hebrew_server():
    base, pwd, proc = start(users=(("hebrew-agent", ["agent"], ["rozela"], "he"),))
    yield base, pwd
    proc.terminate()


def login(pg, base, pwd):
    pg.goto(base + '/cs/login')
    pg.fill('input[name=username]', 'hebrew-agent')
    pg.fill('input[name=password]', pwd)
    pg.click('button[type=submit]')


@pytest.mark.parametrize('width', [375, 1280])
def test_russian_message_is_translated_to_hebrew_with_original_toggle(hebrew_server, width):
    base, pwd = hebrew_server
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={'width': width, 'height': 900})
        errors = []
        pg.on('pageerror', lambda e: errors.append(str(e)))
        login(pg, base, pwd)
        pg.goto(base + '/cs#/b/rozela/t/t18f2a07')
        pg.wait_for_selector('#tk-conv .msg[data-tr="1"]')
        msg = pg.locator('#tk-conv .msg[data-tr="1"]').first
        assert 'הזמנתי לפני 16 ימים ועדיין לא קיבלתי כלום' in msg.inner_text()
        chip = pg.inner_text('[data-test=he-translate]')
        assert 'תורגם אוטומטית מרוסית' in chip and 'עונים ללקוח בעברית בלבד' in chip
        assert 'איפה ההזמנה שלי' in pg.inner_text('#tk-subject')
        msg.locator('[data-test=show-original]').click()
        assert 'ещё ничего не получила' in msg.inner_text()
        assert msg.locator('[data-test=show-original]').inner_text() == 'הצג תרגום'
        msg.locator('[data-test=show-original]').click()
        assert 'הזמנתי לפני 16 ימים' in msg.inner_text()
        pg.screenshot(path='/tmp/hebrew-desk-translate-%s.png' % width, full_page=True)
        assert not errors, errors
        browser.close()


def test_hebrew_ticket_makes_no_translation_call(hebrew_server):
    base, pwd = hebrew_server
    with pw.sync_playwright() as p:
        browser = launch(p)
        pg = browser.new_page(viewport={'width': 1280, 'height': 900})
        calls = []
        pg.on('request', lambda r: calls.append(r.url) if '/translate' in r.url else None)
        login(pg, base, pwd)
        pg.goto(base + '/cs#/b/rozela/t/t18f2a03')
        pg.wait_for_selector('#tk-conv .msg')
        pg.wait_for_timeout(800)
        assert calls == [] and not pg.locator('[data-test=he-translate]').count()
        browser.close()
