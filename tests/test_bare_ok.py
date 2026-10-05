"""QA round 3, B1: a bare {"ok":true} (Apps Script doGet after a redirect) must never be used, cached or shown."""
import json
import re
import threading
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import engine_proxy
import ticket_cache
from conftest import call, client_for, logged_in, valid_reply
from test_assistant import FakeLLM, KNOW, engine_reply


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: None)


def bare_for(fns, transport, base=valid_reply):
    seen = []

    def reply(url, body):
        seen.append(body["fn"])
        return {"ok": True} if body["fn"] in fns else base(url, body)
    transport.reply = reply
    return seen


def test_bare_boot_is_never_rendered_or_cached(app, pw_hash, transport, no_wait):
    seen = bare_for({"apiBoot"}, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok})
    j = r.get_json()
    assert j["ok"] is False and j["error"] == "engine_bad_response" and "tickets" not in j
    assert seen.count("apiBoot") == 3                                       # a fast bad answer: read retried twice
    assert app.extensions["cs"]["ticket_cache"].mem.get("rozela", {}).get("boot") is None   # nothing cached


def test_bare_ticket_full_is_never_cached(app, pw_hash, transport, no_wait):
    bare_for({"apiTicketFull"}, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    j = c.post("/api/rozela/ticket", json={"id": "t1"}, headers={"X-CSRF-Token": tok}).get_json()
    assert j["ok"] is False and j["error"] == "engine_bad_response"
    assert "t1" not in app.extensions["cs"]["ticket_cache"].mem.get("rozela", {}).get("t", {})


def test_ticket_full_for_another_id_is_rejected(app, pw_hash, transport, no_wait):
    transport.reply = lambda url, body: dict(valid_reply(url, body), ticket={"id": "OTHER"}) if body["fn"] == "apiTicketFull" else valid_reply(url, body)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert c.post("/api/rozela/ticket", json={"id": "t1"}, headers={"X-CSRF-Token": tok}).get_json()["error"] == "engine_bad_response"


def test_bare_send_never_says_sent(app, pw_hash, transport, no_wait):
    seen = bare_for({"apiSend"}, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
    j = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "שלום"}).get_json()
    assert j["ok"] is False and "sent" not in j and "ייתכן שהפעולה בוצעה" in j["msg"]
    assert seen == ["apiSend"]                                               # a write: exactly one attempt


def test_bare_knowledge_is_never_cached_and_a_bad_copy_is_evicted(make_app, pw_hash, transport, tmp_path, no_wait):
    seen = bare_for({"apiKnowledge"}, transport, base=engine_reply)
    fake = FakeLLM()
    app = make_app(LLM=fake, TRANSLATE_CACHE_DIR=str(tmp_path / "tc"))
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    ask = lambda: c.post("/api/rozela/assistant", json={"messages": [{"role": "user", "content": "price list?"}]}, headers={"X-CSRF-Token": tok})
    r = ask()
    assert r.status_code == 503 and r.get_json()["error"] == "knowledge_unavailable" and fake.payloads == []
    kc = app.extensions["cs_assistant"]["knowledge"]
    assert "rozela" not in kc._d
    kc._d["rozela"] = (kc.clock(), {"ok": True})                             # an empty copy cached before this fix
    transport.reply = engine_reply                                          # the engine answers properly again
    assert ask().status_code == 200 and "90-day guarantee" in fake.payloads[-1]["system"][0]["text"]


def test_rid_and_fn_echo_are_checked_when_present(app, pw_hash, transport, no_wait):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = lambda url, body: dict(valid_reply(url, body), fn=body["fn"], rid=body["rid"])
    assert call(c, tok, "rozela", "apiBoot").get_json()["ok"]                               # matching echo
    transport.reply = lambda url, body: dict(valid_reply(url, body), fn=body["fn"], rid="0" * 16)
    assert call(c, tok, "rozela", "apiBoot").get_json()["error"] == "engine_bad_response"   # a reply to another call
    transport.reply = lambda url, body: dict(valid_reply(url, body), fn="apiSearch", rid=body["rid"])
    assert call(c, tok, "rozela", "apiBoot").get_json()["error"] == "engine_bad_response"
    transport.reply = lambda url, body: {"ok": True, "fn": body["fn"], "rid": body["rid"]}  # bare close WITH the echo: fine
    assert call(c, tok, "rozela", "apiClose", {"id": "t1"}).get_json()["ok"]


def test_refusal_without_error_code_is_invalid(app, pw_hash, transport, no_wait):
    transport.reply = lambda url, body: {"ok": False}
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert call(c, tok, "rozela", "apiTicket", {"id": "t1"}).get_json()["error"] == "engine_bad_response"
    transport.reply = lambda url, body: {"ok": False, "status": None, "message": "cancellations are switched off"}
    j = call(c, tok, "rozela", "apiKachingCancel", {"id": "t1", "contractId": "gid://shopify/SubscriptionContract/1", "confirm": "0001"}).get_json()
    assert j["message"] == "cancellations are switched off"                 # the gate's own refusal shape stays valid


# ---------- the doGet path over real HTTP: POST -> redirect -> GET /exec -> {"ok":true} ----------

class DoGetServer(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self.send_response(302)                                             # the slow-redirect failure: back to /exec
        self.send_header("Location", self.path)
        self.end_headers()

    def do_GET(self):
        body = b'{"ok": true}'                                              # what doGet() answers
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def test_doget_answer_is_detected_by_the_transport(make_app, pw_hash, no_wait):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), DoGetServer)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = "http://127.0.0.1:%d/macros/s/AKfycbDOGET000000000000000000/exec" % srv.server_address[1]
        app = make_app(ENGINES_JSON=json.dumps({"rozela": url}), TRANSPORT=None,
                       ENGINE_URL_RE=re.compile(r"^http://127\.0\.0\.1:\d+/macros/s/[A-Za-z0-9_-]{20,200}/exec$"))
        c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
        # apiClose is "legitimately bare" — so only the transport can catch this one
        app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
        j = call(c, tok, "rozela", "apiClose", {"id": "t1"}).get_json()
        assert j["ok"] is False and j["error"] == "engine_bad_response" and "ייתכן שהפעולה בוצעה" in j["msg"]
    finally:
        srv.shutdown()


# ---------- cache sanity, crashes, language ----------

def test_suspicious_empty_list_is_refused_and_the_last_good_kept(app, pw_hash, transport, no_wait):
    rows = [{"id": "t%d" % i, "status": "ready"} for i in range(280)]
    transport.reply = lambda url, body: dict(valid_reply(url, body), tickets=rows, counts={"ready": 280}) if body["fn"] == "apiBoot" else valid_reply(url, body)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert len(c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok}).get_json()["tickets"]) == 280
    transport.reply = valid_reply                                           # schema-valid but suddenly empty
    cache = app.extensions["cs"]["ticket_cache"]
    out = cache._fetch_boot({"username": "noa", "roles": ["agent"], "brands": ["rozela"], "lang": "he"}, "rozela")
    assert out["ok"] is False and len(cache.mem["rozela"]["boot"]["data"]["tickets"]) == 280


def test_waiting_on_an_inflight_fetch_answers_json_not_500(app, pw_hash, transport, monkeypatch):
    monkeypatch.setattr(ticket_cache, "WAIT_FOR_INFLIGHT_S", 0.1)
    cache = app.extensions["cs"]["ticket_cache"]
    cache.inflight[("boot", "rozela")] = Future()                          # someone else's fetch that never finishes
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200 and r.get_json()["error"] == "engine_timeout"
    cache.inflight.clear()


def test_unexpected_crash_on_api_is_json(app, pw_hash, transport, monkeypatch):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    monkeypatch.setattr(app.extensions["cs"]["ticket_cache"], "get_list", lambda *a, **k: 1 / 0)
    app.testing = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 500 and r.is_json and r.get_json()["error"] == "server_error"


def test_messages_follow_the_page_language(app, pw_hash, transport, no_wait):
    transport.reply = lambda url, body: {"ok": True}                        # bare -> engine_bad_response
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"], lang="he")
    he = c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok}).get_json()["msg"]
    en = c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok, "X-UI-Lang": "en"}).get_json()["msg"]
    assert any("֐" <= ch <= "׿" for ch in he) and en.startswith("The engine sent an invalid answer")
    en2 = call(c, tok, "rozela", "apiTicket", {"id": "t1"}).headers  # proxy route too
    r = c.post("/api/rozela/apiTicket", json={"args": {"id": "t1"}}, headers={"X-CSRF-Token": tok, "X-UI-Lang": "en"}).get_json()
    assert r["msg"].startswith("The engine sent an invalid answer")



def test_owner_knowledge_alone_is_valid():
    import assistant
    assert engine_proxy.reply_problem("apiKnowledge", {}, "r", {"ok": True, "ownerKnowledge": "price: 149", "knowledge": "", "policy": []}) is None
    assert assistant.knowledge_ok({"ok": True, "ownerKnowledge": "price: 149"})
    assert engine_proxy.reply_problem("apiKnowledge", {}, "r", {"ok": True, "knowledge": "", "ownerKnowledge": " ", "policy": []})
