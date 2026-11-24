"""Owner, 2026-11-24 ("the workers say it does not work well"): 33 English-desk replies were refused as "identifiers" in 7 days, the
same 2 replies retried ~17 times. Hebrew glues a prefix letter to an id with a hyphen (ב-LP00123456789012) and the old whole-token
check counted 0. Also: the engine Session kept 10 connections for 16+ threads (2,117 "Connection pool is full" in 7 days)."""
import assistant
import engine_proxy

SRC = "Hi Dana, your order #RZ-10234 shipped. Tracking number: LP00123456789012. It will arrive in 7 days."


def counts(text):
    ids = assistant.source_delivery_ids(SRC)
    return {t: len(assistant.id_re(t).findall(text)) for t in ids}


def test_prefix_hyphen_counts_the_id():
    he = "היי דנה, ההזמנה שלך ב-RZ-10234 נשלחה, אפשר לעקוב ב-LP00123456789012. תגיע תוך 7 ימים."
    assert counts(he) == {"LP00123456789012": 1, "RZ-10234": 1}


def test_plain_and_dropped():
    assert counts("ההזמנה RZ-10234 נשלחה. מספר מעקב: LP00123456789012.") == {"LP00123456789012": 1, "RZ-10234": 1}
    assert counts("ההזמנה נשלחה.")["LP00123456789012"] == 0


def test_not_part_of_a_longer_latin_token():
    assert counts("XLP00123456789012 and LP00123456789012X and A-LP00123456789012")["LP00123456789012"] == 0


def test_without_ids_strips_prefixed_id():
    out = assistant.delivery_without_ids("אפשר לעקוב ב-LP00123456789012 עכשיו", ["LP00123456789012"])
    assert "LP00123456789012" not in out and "ב-" in out


def test_engine_session_keeps_enough_connections():
    s = engine_proxy.pooled_session()
    assert s.get_adapter("https://cs-core-fuyv.onrender.com/x")._pool_maxsize >= 32
