"""Owner, 2026-10-11: another message on an answered / closed ticket (apiSend {followup, seen}), templates on any chat (apiSendTemplate {seen}),
two agents on one ticket (changed_meanwhile) and who else has the ticket open (/watch -> others). The server side of it."""
import pytest

import engine_proxy
from conftest import logged_in, call, valid_reply


def post(c, tok, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": tok})


def test_followup_and_seen_pass_the_allowlist_and_nothing_else_does():
    out = engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "followup": True, "seen": "2026-10-11T08:00:00.123Z", "junk": 1})
    assert out == {"id": "t1", "text": "x", "followup": True, "seen": "2026-10-11T08:00:00.123Z"}
    assert "followup" not in engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "followup": "yes"})   # only a real true
    assert engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "seen": ""})["seen"] == ""             # never handled
    assert engine_proxy.clean_args("apiSendTemplate", {"id": "t1", "template": "A", "seen": "2026-10-11T08:00:00Z"})["seen"]
    for bad in (5, "2" * 41, "<b>", ["x"]):
        with pytest.raises(engine_proxy.ProxyError):
            engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "seen": bad})
    assert engine_proxy.clean_args("apiTicketLite", {"id": "t1", "since": 3, "seen": 4}, engine_proxy.INTERNAL_FNS)["seen"] == 4          # its own `seen` is unchanged


def test_the_proxy_forwards_them_and_a_changed_meanwhile_refusal_is_shown_never_retried(make_app, pw_hash, transport):
    app = make_app()
    c, tok = logged_in(app, pw_hash, "dana", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "hi", "followup": True, "seen": "2026-10-11T08:00:00Z"})
    assert r.get_json()["ok"] is True
    sent = [b for _, b in transport.calls if b["fn"] == "apiSend"][-1]["args"]
    assert sent["followup"] is True and sent["seen"] == "2026-10-11T08:00:00Z"
    transport.calls.clear()
    transport.reply = lambda url, body: (
        {"ok": False, "error": "changed_meanwhile", "by": "lyra", "at": "2026-10-11T08:01:00Z", "status": "sent"} if body["fn"] == "apiSend"
        else valid_reply(url, body))
    j = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "hi", "seen": ""}).get_json()
    assert (j["ok"], j["error"], j["by"], j["at"], j["status"]) == (False, "changed_meanwhile", "lyra", "2026-10-11T08:01:00Z", "sent")
    assert "מישהו אחר כבר ענה" in j["msg"]
    assert sum(1 for _, b in transport.calls if b["fn"] == "apiSend") == 1        # a refusal about the ticket: never sent again


def test_the_cache_keeps_the_engines_own_handled_at(make_app, pw_hash, transport, monkeypatch):
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    cache = app.extensions["cs"]["ticket_cache"]
    monkeypatch.setattr(cache, "_background", lambda *a, **k: None)              # no revalidation racing the patch
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["ok"]
    exact = "2026-10-11T08:00:00.123Z"
    cache.after_write({"username": "noa"}, "rozela", "apiSend", {"id": "t1", "text": "hi"}, {"ok": True, "sent": True, "handled_at": exact})
    tk = cache._entry("rozela", "t1")["full"]["ticket"]
    assert (tk["handled_at"], tk["status"], tk["handled_by"]) == (exact, "sent", "noa")    # the next message's `seen` matches the engine
    cache.after_write({"username": "noa"}, "rozela", "apiSend", {"id": "t1", "text": "hey"}, {"ok": True, "queued": True, "handled_at": exact})
    tk = cache._entry("rozela", "t1")["full"]["ticket"]
    assert (tk["wa_send"], tk["status"], tk["wa_out"]) == ("pending", "wa_queued", "hey")
    cache.after_write({"username": "noa"}, "rozela", "apiSendTemplate", {"id": "t1", "template": "A"}, {"ok": True, "queued": True, "template": "A"})
    assert cache._entry("rozela", "t1")["full"]["ticket"]["status"] == "wa_queued"


def test_watch_says_who_else_has_the_ticket_open_and_who_is_writing(make_app, pw_hash, transport):
    app = make_app()
    noa, tn = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    dana, td = logged_in(app, pw_hash, "dana", ["agent"], ["rozela"])
    assert post(noa, tn, "/api/rozela/watch", {"id": "t1", "at": 0}).get_json()["others"] == []
    j = post(dana, td, "/api/rozela/watch", {"id": "t1", "at": 0}).get_json()
    assert j["others"] == [{"user": "noa", "name": "noa", "editing": False}]
    post(noa, tn, "/api/rozela/watch", {"id": "t1", "at": 0, "ed": True})
    assert post(dana, td, "/api/rozela/watch", {"id": "t1", "at": 0}).get_json()["others"][0]["editing"] is True
    assert post(dana, td, "/api/rozela/watch", {"id": "t2", "at": 0}).get_json()["others"] == []       # per ticket
    opened = post(noa, tn, "/api/rozela/ticket", {"id": "t1", "open": True}).get_json()
    assert [o["user"] for o in opened["others"]] == ["dana"]                                            # the open says it at once too
