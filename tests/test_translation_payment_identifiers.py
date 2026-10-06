"""Real preview failures: currency vocabulary and source-labelled opaque payment IDs."""
import json
from conftest import call
from test_assistant import text
from test_english_safety import setup
from assistant import hebrew_delivery_ok, normalize_hebrew_currency


def result(value):
    return text(json.dumps({'translations': [{'i': 0, 'text': value}]}))


def test_currency_is_hebrew_and_all_numeric_facts_survive(setup):
    app, c, tok, transport, model = setup
    source = 'Payment 149.90 ILS on 06/10/2026, card 1234, order #4512.'
    model.script = [result('התשלום 149.90 ILS בתאריך 06/10/2026, כרטיס 1234, הזמנה #4512.')]
    r = c.post('/api/rozela/translate-out', json={'ticketId': 't1', 'text': source}, headers={'X-CSRF-Token': tok})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['text'] == 'התשלום 149.90 ש״ח בתאריך 06/10/2026, כרטיס 1234, הזמנה #4512.'


def test_source_labelled_payment_ids_survive_preview_and_exact_send(setup):
    app, c, tok, transport, model = setup
    source = 'Please check reference pp-9aX12345. Refund reference is 8AB12345CD678901E.'
    approved = 'נא לבדוק את האסמכתא pp-9aX12345. אסמכתת ההחזר היא 8AB12345CD678901E.'
    model.script = [result(approved)]
    r = c.post('/api/rozela/translate-out', json={'ticketId': 't1', 'text': source}, headers={'X-CSRF-Token': tok})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['text'] == approved
    assert not hebrew_delivery_ok(approved, 'rozela')  # no global Latin allowlist was added
    sent = call(c, tok, 'rozela', 'apiSend', {'id': 't1', 'text': approved})
    assert sent.get_json()['ok']
    writes = [b for _, b in transport.calls if b['fn'] == 'apiSend']
    assert len(writes) == 1 and writes[0]['args']['text'] == approved
    assert len(model.payloads) == 1


def test_payment_id_permission_does_not_allow_added_english(setup):
    app, c, tok, transport, model = setup
    source = 'Please check reference pp-9aX12345.'
    model.script = [result('נא לבדוק pp-9aX12345. Hello1 customer2 Your order is ready.')] * 2
    r = call(c, tok, 'rozela', 'apiSend', {'id': 't1', 'text': source})
    assert r.status_code == 502
    assert not [b for _, b in transport.calls if b['fn'] == 'apiSend']


def test_numeric_change_or_identifier_change_is_refused(setup):
    app, c, tok, transport, model = setup
    model.script = [result('תשלום 199.90 ש״ח, אסמכתא pp-9aX12345.')] * 2
    r = call(c, tok, 'rozela', 'apiSend', {'id': 't1', 'text': 'Payment 149.90 ILS, reference pp-9aX12345.'})
    assert r.status_code == 502
    assert not [b for _, b in transport.calls if b['fn'] == 'apiSend']


def test_currency_rewriting_keeps_links_emails_and_ids_exact():
    assert normalize_hebrew_currency('149.90 ILS https://x.test/ILS support@ILS.example AB-ILS-1234') == '149.90 ש״ח https://x.test/ILS support@ILS.example AB-ILS-1234'


def test_worded_numbers_remain_words_and_numeric_repair_is_bounded(setup):
    app, c, tok, transport, model = setup
    source = 'The refund is one hundred shekels. It can take five business days.'
    approved = 'ההחזר הוא מאה שקלים. זה יכול לקחת חמישה ימי עסקים.'
    model.script = [result('ההחזר הוא 100 שקלים. זה יכול לקחת 5 ימי עסקים.'), result(approved)]
    r = c.post('/api/rozela/translate-out', json={'ticketId': 't1', 'text': source}, headers={'X-CSRF-Token': tok})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['text'] == approved
    assert len(model.payloads) == 2
    assert not [b for _, b in transport.calls if b['fn'] == 'apiSend']


def test_mixed_digit_and_worded_numbers_preserve_each_form(setup):
    app, c, tok, transport, model = setup
    model.script = [result('הזמנה #4512: נא להמתין שני ימי עסקים. הסכום הוא 149.90 ש״ח.')]
    r = c.post('/api/rozela/translate-out', json={'ticketId': 't1', 'text': 'Order #4512: please wait two business days. The amount is 149.90 ILS.'}, headers={'X-CSRF-Token': tok})
    assert r.status_code == 200, r.get_json()
    assert 'שני ימי עסקים' in r.get_json()['text']
