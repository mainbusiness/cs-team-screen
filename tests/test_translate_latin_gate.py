"""2026-11-13 (Paula, English desk): the translation 'stuck and failed even after 10 tries'. Measured on Render logs 11-08..11-13: 244 of
6,571 sends refused, ALL by the Latin-letters gate, 188 of them on her two brands (12.5% vs 1.1% for the others), the repair try rejected for
the same words every time. The gate called a bare web address, a promo code, the STOP keyword and 'Apex Men' English prose. Now: those pass,
real English prose still fails closed, the repair try names the refused words, and a refusal tells the agent which words and offers
'keep as written' (words of her OWN text only)."""
import json
import re
import pytest
from conftest import call
from test_assistant import text
from test_english_safety import setup
import assistant as A


def result(value):
    return text(json.dumps({'translations': [{'i': 0, 'text': value}]}))


def post(c, tok, source, **extra):
    return c.post('/api/rozela/translate-out', json=dict({'ticketId': 't1', 'text': source}, **extra), headers={'X-CSRF-Token': tok})


@pytest.mark.parametrize('he', ['אפשר להזמין ב-try-celesta.com', 'הכניסו בקופה try-celesta.com/pages/track.', 'האתר apexmen-il.com פתוח', 'כתבו לי ל tryrozela.com'])
def test_bare_web_address_is_a_link_not_english(he):
    assert A.hebrew_delivery_ok(he, 'rozela')


def test_names_and_aliases_do_not_need_a_code():
    assert not A.hebrew_delivery_ok('שילמת עם Apple Pay או PayPal', 'celesta')   # house policy: payment services are transliterated
    assert 'אפל פיי' in A.PAY_GLOSSARY and 'פייפאל' in A.PAY_GLOSSARY
    assert A.hebrew_delivery_ok('צוות Apex Men כאן', 'apexmen')
    assert not A.hebrew_delivery_ok('צוות Apex Men כאן', 'celesta')           # an alias belongs to its own brand only


def test_english_prose_still_fails_closed_even_next_to_a_domain():
    assert not A.hebrew_delivery_ok('שלום try-celesta.com Your order is ready', 'celesta')
    assert not A.hebrew_delivery_ok('שלום com', 'rozela')                      # a TLD alone is not a domain
    assert not A.hebrew_delivery_ok('שלום Hello.world', 'rozela')


def test_domain_is_protected_from_the_dash_and_currency_rewrites():
    assert A.humanize_hebrew_dashes('הכנסו -- ל-try-celesta.com/a-b') == 'הכנסו, ל-try-celesta.com/a-b'
    assert A.normalize_hebrew_currency('usd-shop.com 5 USD') == 'usd-shop.com 5 דולר אמריקאי'
    assert not A.has_forbidden_dash('try-celesta.com/a--b')


def test_codes_of_the_source_pass_through_the_route(setup):
    app, c, tok, transport, model = setup
    src = 'Use code VIP40 or FREE150 at try-celesta.com. Reply STOP to unsubscribe. Our DHT blocker has cGMP.'
    out = 'השתמשו בקוד Vip40 או FREE150 ב-try-celesta.com. כתבו Stop להסרה. החוסם DHT שלנו עם cGMP.'
    model.script = [result(out)]
    r = post(c, tok, src)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['text'] == out and len(model.payloads) == 1
    sent = call(c, tok, 'rozela', 'apiSend', {'id': 't1', 'text': out})            # the exact approved text goes out, no new model call
    assert sent.get_json()['ok'] and len(model.payloads) == 1


def test_camel_case_names_are_not_acronyms():
    assert 'paypal' not in A.source_latin_ok('Pay with PayPal or YouTube')
    assert {'cgmp', 'dht', 'stop', 'vip40'} <= A.source_latin_ok('cGMP DHT Stop VIP40')


def test_a_word_the_source_did_not_have_is_never_allowed(setup):
    app, c, tok, transport, model = setup
    model.script = [result('הקוד VIP40 ו-Hello2 שלך מוכן, תודה Customer')] * 2
    r = post(c, tok, 'Your code is VIP40.')
    assert r.status_code == 502
    assert 'Hello2' in r.get_json()['blocked'] and 'VIP40' not in r.get_json()['blocked']


def test_repair_try_names_the_refused_words_and_can_recover(setup):
    app, c, tok, transport, model = setup
    bad = result('לחצו על Manage Subscription ואז על Cancel')
    good = result('לחצו על ניהול מנוי ואז על ביטול')
    model.script = [bad, good]
    r = post(c, tok, 'Click Manage Subscription then Cancel.')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['text'] == 'לחצו על ניהול מנוי ואז על ביטול'
    second = model.payloads[1]['system'][0]['text']
    assert 'Manage' in second and 'Subscription' in second and 'refused' in second
    assert 'refused' not in model.payloads[0]['system'][0]['text']


def test_refusal_names_the_words_and_keep_as_written_unblocks(setup):
    app, c, tok, transport, model = setup
    stuck = result('לחצו על Manage Subscription ואז על ביטול')
    model.script = [stuck, stuck, stuck]
    src = 'Click Manage Subscription then Cancel.'
    r = post(c, tok, src)
    j = r.get_json()
    assert r.status_code == 502 and j['error'] == 'translate_failed'
    assert sorted(j['blocked']) == ['Manage', 'Subscription'] and 'Manage, Subscription' in j['msg']
    # the agent confirms: the words of her own text stay as written
    model.script = [stuck]
    r2 = post(c, tok, src, keep_latin=j['blocked'])
    assert r2.status_code == 200, r2.get_json()
    assert 'Manage Subscription' in r2.get_json()['text']
    assert 'confirmed these words stay in Latin' in model.payloads[-1]['system'][0]['text']
    sent = call(c, tok, 'rozela', 'apiSend', {'id': 't1', 'text': r2.get_json()['text']})
    assert sent.get_json()['ok'], sent.get_json()                                   # and the send of that exact text is accepted
    # without the confirmation the same text is still refused at the send gate
    assert not A.hebrew_delivery_ok(r2.get_json()['text'], 'rozela')


@pytest.mark.parametrize('keep', ['Manage', ['Hello'], ['Manage', 'x' * 40], [1], ['Man age'], ['A'] * 11])
def test_keep_as_written_only_takes_words_of_her_own_text(setup, keep):
    app, c, tok, transport, model = setup
    model.script = [result('שלום')]
    r = post(c, tok, 'Click Manage Subscription.', keep_latin=keep)
    assert r.status_code == 400 and not model.payloads


def test_a_non_latin_failure_has_no_blocked_list(setup):
    app, c, tok, transport, model = setup
    model.script = [result('הסכום 199 ש״ח')] * 2
    r = post(c, tok, 'The amount is 149 ILS.')
    assert r.status_code == 502 and 'blocked' not in r.get_json()


def test_a_link_fragment_can_never_be_confirmed_as_a_word(setup):
    app, c, tok, transport, model = setup
    model.script = [result('שלום')]
    r = post(c, tok, 'Order at try-celesta.com or WWW.EXAMPLE.COM today.', keep_latin=['com'])
    assert r.status_code == 400 and not model.payloads
    assert not A.source_latin_ok('see WWW.EXAMPLE.COM') & {'www', 'example', 'com'}


def test_long_dotted_or_hyphenated_input_is_scanned_in_linear_time():
    import time
    for body in ('a-' * 4000, 'a.' * 4000, 'a-b.' * 2000, 'a' + '-a' * 3999):
        t0 = time.time()
        re.compile(A._BARE_DOMAIN).findall('שלום ' + body)                       # the new pattern alone (the old email pattern is a separate cost)
        assert time.time() - t0 < 0.05, (body[:6], time.time() - t0)
        t0 = time.time()
        A.latin_residue('שלום ' + body, 'rozela')
        assert time.time() - t0 < 0.5, (body[:6], time.time() - t0)
    assert A.hebrew_delivery_ok('כנסו ל-try-celesta.com', 'celesta')        # the Hebrew prefix + hyphen still starts a domain
    assert A.hebrew_delivery_ok('כנסו ל־try-celesta.com/a-b.', 'celesta')


@pytest.mark.parametrize('he,ok', [('ראו try-celesta.com/pages/track.', True), ('ראו (try-celesta.com/pages/track), תודה', True),
                                  ('ראו try-celesta.com/Thanks"Thanks', False), ('ראו try-celesta.com/a)Your order', False),
                                  ('ראו try-celesta.com, Hello there', False), ('ראו try-celesta.com/abc.Please wait', False)])
def test_a_bare_domain_cannot_swallow_the_words_next_to_it(he, ok):
    assert A.hebrew_delivery_ok(he, 'celesta') is ok
