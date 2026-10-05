"""QA round 4: ~10% of engine calls lose their reply (404 page, POST turned GET -> get_not_supported, timeouts) while the
work often DID run. Writes are resolved via apiResult {rid} and a same-rid resend; nothing raw ever reaches an agent."""
import pytest

import engine_proxy
from conftest import call, logged_in, valid_reply


@pytest.fixture
def quick(monkeypatch):
    slept = []
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: slept.append(s))
    monkeypatch.setattr(engine_proxy, "RESEND_MIN_AGE_S", 0)          # the 40 s floor has its own test
    return slept


def echo(body, out):
    return dict(out, fn=body["fn"], rid=body["rid"])


def engine(result_mode, send_mode, log):
    """result_mode: 'found' | 'missing' | 'unsupported'. send_mode: list of what each apiSend attempt returns."""
    sends = list(send_mode)

    def reply(url, body):
        fn = body["fn"]
        log.append((fn, body.get("rid"), (body.get("args") or {}).get("rid")))
        if fn == "apiSend":
            what = sends.pop(0)
            if what == "lost":
                return {"ok": False, "error": "get_not_supported"}           # what a POST-turned-GET looks like
            if what == "html":
                raise engine_proxy.ProxyError("engine_bad_response", 502)
            return echo(body, {"ok": True, "sent": True})                     # the engine's (idempotent) reply
        if fn == "apiResult":
            orig = body["args"]["rid"]
            if result_mode == "found":
                return echo(body, {"ok": True, "reply": {"ok": True, "sent": True, "fn": "apiSend", "rid": orig}})
            if result_mode == "missing":
                return echo(body, {"ok": False, "error": "not_found"})
            return echo(body, {"ok": False, "error": "unauthorized"})          # an engine without apiResult
        return echo(body, valid_reply(url, body))
    return reply


def send(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
    return call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "שלום"})


def test_lost_send_then_found_in_apiresult(app, pw_hash, transport, quick):
    log = []
    transport.reply = engine("found", ["lost"], log)
    j = send(app, pw_hash).get_json()
    assert j["ok"] is True and j["sent"] is True and j["recovered"] == "apiResult"
    sends = [x for x in log if x[0] == "apiSend"]
    results = [x for x in log if x[0] == "apiResult"]
    assert len(sends) == 1 and results[0][2] == sends[0][1]               # asked for the stored reply OF THAT rid


def test_lost_and_not_found_then_same_rid_resend(app, pw_hash, transport, quick):
    log = []
    transport.reply = engine("missing", ["lost", "ok"], log)
    j = send(app, pw_hash).get_json()
    assert j["ok"] is True and j["recovered"] == "resend"
    sends = [x for x in log if x[0] == "apiSend"]
    assert len(sends) == 2 and sends[0][1] == sends[1][1]                 # the SAME rid: idempotent on the engine
    assert len([x for x in log if x[0] == "apiResult"]) == len(engine_proxy.RESULT_POLL_DELAYS_S)
    assert sum(quick) == pytest.approx(15.0)


def test_still_unknown_says_so_and_asks_for_a_refresh(app, pw_hash, transport, quick):
    log = []
    transport.reply = engine("missing", ["lost", "html"], log)
    r = send(app, pw_hash)
    j = r.get_json()
    assert j["ok"] is False and j["error"] == "write_unknown" and j["refresh"] is True
    assert j["msg"] == "לא הצלחנו לאשר אם הפעולה בוצעה — רעננו את הפנייה ובדקו."
    assert len([x for x in log if x[0] == "apiSend"]) == 2                 # one resend, never more


def test_old_engine_without_apiresult_never_says_refused(app, pw_hash, transport, quick):
    log = []
    transport.reply = engine("unsupported", ["lost"], log)
    j = send(app, pw_hash).get_json()
    assert j["ok"] is False and j["refresh"] is True and "ייתכן שהפעולה בוצעה" in j["msg"]
    assert "סירב" not in j["msg"] and "get_not_supported" not in j["msg"]
    assert len([x for x in log if x[0] == "apiSend"]) == 1 and len([x for x in log if x[0] == "apiResult"]) == 1


def test_get_not_supported_is_never_shown_raw_and_reads_retry(app, pw_hash, transport, quick):
    n = []

    def reply(url, body):
        n.append(body["fn"])
        return {"ok": False, "error": "get_not_supported"}
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    j = call(c, tok, "rozela", "apiTicket", {"id": "t1"}).get_json()
    assert j["error"] == "engine_bad_response" and "get_not_supported" not in j["msg"] and "סירב" not in j["msg"]
    assert n.count("apiTicket") == 3                                        # a read: retried by the existing rules


def test_missing_rid_is_rejected_once_the_engine_echoes(app, pw_hash, transport, quick):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = lambda url, body: echo(body, valid_reply(url, body))
    assert call(c, tok, "rozela", "apiBoot").get_json()["ok"]               # this engine echoes rid/fn
    transport.reply = valid_reply                                           # a valid-looking reply WITHOUT the echo
    j = call(c, tok, "rozela", "apiBoot").get_json()
    assert j["error"] == "engine_bad_response"
    assert call(c, tok, "rozela", "apiBoot").status_code == 502
    # another brand that has never echoed is judged on its schema alone (not redeployed yet)
    c2, tok2 = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta"])
    assert call(c2, tok2, "celesta", "apiBoot").get_json()["ok"]


def test_reads_never_go_through_write_resolution(app, pw_hash, transport, quick):
    n = []

    def reply(url, body):
        n.append(body["fn"])
        raise engine_proxy.ProxyError("engine_bad_response", 502)
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    call(c, tok, "rozela", "apiSearch", {"q": "dana"})
    assert "apiResult" not in n



def test_apiresult_failing_never_recurses(app, pw_hash, transport, quick):
    """Regression: apiResult was not a read, so its own failure tried to resolve itself -> RecursionError -> HTTP 500."""
    def reply(url, body):
        raise engine_proxy.ProxyError("engine_bad_response", 502)        # everything lost, apiResult included
    transport.reply = reply
    r = send(app, pw_hash)
    assert r.status_code == 502 and r.get_json()["error"] == "write_unknown"
    fns = [b["fn"] for _, b in transport.calls]
    assert fns.count("apiSend") == 2 and fns.count("apiResult") <= 3 * len(engine_proxy.RESULT_POLL_DELAYS_S)


def test_real_apiresult_shape(app, pw_hash, transport, quick):
    """The engine's final shape: {ok, found, forFn, reply} — found:true with the stored reply."""
    log = []

    def reply(url, body):
        log.append(body["fn"])
        if body["fn"] == "apiSend":
            return {"ok": False, "error": "get_not_supported"}
        if body["fn"] == "apiResult":
            orig = body["args"]["rid"]
            return echo(body, {"ok": True, "found": True, "forFn": "apiSend",
                               "reply": {"ok": True, "sent": True, "replayed": False, "fn": "apiSend", "rid": orig}})
        return echo(body, valid_reply(url, body))
    transport.reply = reply
    j = send(app, pw_hash).get_json()
    assert j["ok"] and j["sent"] and log.count("apiSend") == 1


def test_rid_reuse_is_never_an_answer(app, pw_hash, transport, quick):
    def reply(url, body):
        if body["fn"] == "apiSend":
            raise engine_proxy.ProxyError("engine_bad_response", 502)
        if body["fn"] == "apiResult":
            return echo(body, {"ok": False, "error": "rid_reuse"})
        return echo(body, valid_reply(url, body))
    transport.reply = reply
    j = send(app, pw_hash).get_json()
    assert j["ok"] is False and j["error"] == "write_unknown"



# ---------- QA round 5 ----------

def test_no_resend_before_the_original_could_have_finished(app, pw_hash, transport, monkeypatch):
    """The resend waits until RESEND_MIN_AGE_S after the ORIGINAL call started: it may still be running in Apps Script."""
    t = [0.0]
    monkeypatch.setattr(engine_proxy, "_clock", lambda: t[0])
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: t.__setitem__(0, t[0] + s))
    log = []
    transport.reply = engine("missing", ["lost", "ok"], log)
    resent_at = []
    base = transport.reply

    def timed(url, body):
        if body["fn"] == "apiSend" and len([x for x in log if x[0] == "apiSend"]) == 1:
            resent_at.append(t[0])
        return base(url, body)
    transport.reply = timed
    assert send(app, pw_hash).get_json()["recovered"] == "resend"
    assert resent_at and resent_at[0] >= engine_proxy.RESEND_MIN_AGE_S


def test_whatsapp_send_is_never_resent(app, pw_hash, transport, quick):
    log = []
    transport.reply = engine("missing", ["lost", "ok"], log)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
    j = call(c, tok, "rozela", "apiSend", {"id": "w1", "text": "היי", "channel": "whatsapp"}).get_json()
    assert j["error"] == "write_unknown" and j["refresh"] is True
    sends = [b for _, b in transport.calls if b["fn"] == "apiSend"]
    assert len(sends) == 1 and "_channel" not in sends[0]["args"] and "channel" not in sends[0]["args"]


def test_lost_whatsapp_send_resolved_from_the_ticket_as_queued(app, pw_hash, transport, quick):
    def reply(url, body):
        fn = body["fn"]
        if fn == "apiSend":
            return {"ok": False, "error": "get_not_supported"}
        if fn == "apiResult":
            return echo(body, {"ok": True, "found": False})
        if fn == "apiTicket":
            return echo(body, {"ok": True, "ticket": {"id": "w1", "status": "action", "wa_send": "pending", "handled_by": "noa"}})
        return echo(body, valid_reply(url, body))
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
    j = call(c, tok, "rozela", "apiSend", {"id": "w1", "text": "היי", "channel": "whatsapp"}).get_json()
    assert j["ok"] and j["queued"] and j["recovered"] == "ticket"


def test_already_handled_by_us_is_reported_as_sent(app, pw_hash, transport, quick):
    def reply(url, body):
        if body["fn"] == "apiSend":
            return echo(body, {"ok": False, "error": "already_handled"})
        if body["fn"] == "apiTicket":
            return echo(body, {"ok": True, "ticket": {"id": "t1", "status": "sent", "handled_by": "noa"}})
        return echo(body, valid_reply(url, body))
    transport.reply = reply
    j = send(app, pw_hash).get_json()
    assert j["ok"] and j["sent"] and j["already"] is True
    # someone ELSE handled it: the honest refusal stays
    transport.reply = lambda url, body: echo(body, {"ok": False, "error": "already_handled"}) if body["fn"] == "apiSend" else \
        echo(body, {"ok": True, "ticket": {"id": "t1", "status": "sent", "handled_by": "agent-two"}}) if body["fn"] == "apiTicket" else echo(body, valid_reply(url, body))
    c, tok = logged_in(app, pw_hash, "ron", ["agent"], ["rozela"])
    j = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "x"}).get_json()
    assert j["ok"] is False and j["error"] == "already_handled" and "כבר טיפל" in j["msg"]
