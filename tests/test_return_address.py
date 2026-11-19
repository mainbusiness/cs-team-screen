"""2026-11-20 (Guy): "the address is never translated into Hebrew for the Philippines desk, because then the post does not accept it and we
have a problem with the customers". Measured: an English-desk agent sent the return address in English, the send translation turned it into
"חדר 201, בניין בי, ..." (Hebrew letters), and customers wrote "לא הבנתי כלום, תכתבו את הכתובת באנגלית". Now the postal block is taken out
before the model translates and put back verbatim; the model never sees it, and a translation that drops or repeats the marker is refused.
Mirror of tests/return_address.test.js (engine, same detector). The block here is FICTITIOUS test data: this repo is public; the real one lives only in engine Config.gs (private core)."""
import json
import pytest
from conftest import call
from test_assistant import text
from test_english_safety import setup
import assistant as A

BLOCK = ("Recipient: Dana\n"
         "Delivery Address: Room 12, Building C, Phase 2, Example Science Park, No. 7, Maple 3rd Road, Riverside Town, "
         "North District, Sample City, Example Province, China (Delivery to your door is required)\n"
         "Mobile: 10000000000")
SOURCE = "Hi Moshe, please send the parcel to this address:\n" + BLOCK + "\nThen send me a photo of the receipt with the tracking number."


def result(value):
    return text(json.dumps({"translations": [{"i": 0, "text": value}]}))


def post(c, tok, source):
    return c.post("/api/rozela/translate-out", json={"ticketId": "t1", "text": source}, headers={"X-CSRF-Token": tok})


def test_detector_finds_the_block_and_leaves_prose():
    spans = A.postal_spans(SOURCE)
    assert len(spans) == 1 and SOURCE[spans[0][0]:spans[0][1]] == BLOCK
    one = "Please ship it to Recipient: Dana, Delivery Address: Room 12, Maple 3rd Road, Sample City"
    (a, b), = A.postal_spans(one)
    assert one[a:b].startswith("Recipient:")
    assert A.postal_spans("Recipient: Dana") == []                                   # no digit: not an address
    assert A.postal_spans("Address: please send me your full address so I can help") == []
    assert A.postal_spans("Your order is on its way, tracking JY123456789IL") == []


@pytest.mark.parametrize("prose", ["Your parcel reached the city sorting center in China on 12/11", "Phone: I tried calling you 3 times today",
                                   "Mobile: 10000000000", "Address: your parcel is in the city center of China since 12/11",
                                   "Room 12, Building C, Maple 3rd Road, Sample City"])
def test_prose_that_only_looks_like_an_address_is_not_one(prose):
    assert A.postal_spans(prose) == []                                              # Codex 2026-11-20: still translated
    assert not A.hebrew_delivery_ok("היי.\n" + prose, "rozela")


def test_a_stray_marker_fails_closed(setup):
    app, c, tok, transport, model = setup
    model.script = [result("היי, [[ADDRESS_A]] תודה"), result("היי, [[ADDRESS_A]] תודה")]
    assert A.mask_postal("send [[ADDRESS_A]] here\n" + BLOCK) == ("send [[ADDRESS_A]] here\n" + BLOCK, {})
    r = post(c, tok, "Hi, thanks for writing to us")
    assert r.status_code == 502


def test_latin_gate_does_not_count_the_block_but_still_blocks_prose():
    he = "היי משה, זו הכתובת למשלוח:\n" + BLOCK + "\nאחרי ששלחת, תשלח לי צילום של הקבלה."
    assert A.hebrew_delivery_ok(he, "rozela")
    assert not A.hebrew_delivery_ok("היי, Please send it back to us.\n" + BLOCK, "rozela")


def test_mask_and_unmask_are_exact():
    masked, blocks = A.mask_postal(SOURCE)
    assert "[[ADDRESS_A]]" in masked and "Dana" not in masked and blocks == {"A": BLOCK}
    assert A.unmask_postal("שלום\n[[ADDRESS_A]]\nתודה", blocks) == "שלום\n" + BLOCK + "\nתודה"
    assert A.unmask_postal("שלום", blocks) is None                                  # dropped
    assert A.unmask_postal("[[ADDRESS_A]] [[ADDRESS_A]]", blocks) is None          # repeated
    assert A.unmask_postal("[[ADDRESS_B]]", blocks) is None                        # unknown


def test_send_keeps_the_address_in_latin_and_the_model_never_sees_it(setup):
    app, c, tok, transport, model = setup
    model.script = [result("היי משה, תשלח את החבילה לכתובת הזאת:\n[[ADDRESS_A]]\nאחר כך תשלח לי צילום של הקבלה עם מספר המעקב.")]
    r = post(c, tok, SOURCE)
    assert r.status_code == 200, r.get_json()
    out = r.get_json()["text"]
    assert BLOCK in out and out.startswith("היי משה")
    sent_to_model = json.dumps(model.payloads, ensure_ascii=False)
    assert "Maple" not in sent_to_model and "10000000000" not in sent_to_model and "[[ADDRESS_A]]" in sent_to_model
    sent = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": out})            # the approved text goes out as is, no new model call
    assert sent.get_json()["ok"] and len(model.payloads) == 1
    assert [b for _, b in transport.calls if b["fn"] == "apiSend"][-1]["args"]["text"] == out


def test_a_translation_that_drops_the_marker_is_repaired_then_refused(setup):
    app, c, tok, transport, model = setup
    hebrew_address = "היי משה, תשלח לכתובת: חדר 12, בניין סי, סמפל סיטי, סין. טלפון 10000000000."
    model.script = [result(hebrew_address), result(hebrew_address)]
    r = post(c, tok, SOURCE)
    assert r.status_code == 502
    assert len(model.payloads) == 2                                                  # one repair try, then refused


def test_hebrew_desk_style_send_of_an_untranslated_block_needs_no_model(setup):
    app, c, tok, transport, model = setup
    he = "היי משה, זו הכתובת למשלוח. צריך לכתוב אותה על החבילה בדיוק ככה, באנגלית:\n" + BLOCK + "\nנועם"
    r = post(c, tok, he)
    assert r.status_code == 200 and r.get_json()["text"] == he and not model.payloads
