"""Owner, 2026-11-24: the Anthropic monthly spend limit was reached and every translation showed "Invalid answer from the AI
service. Try again." These pin: the 400 spend-limit answer has its own code and message, it is not in the outbox's auto-retry
list, admins get a red banner, /healthz/ai reports it (and probes at most every few minutes), and a success clears it."""
import os

import pytest

import llm
import messages
from conftest import logged_in
from test_assistant import FakeLLM, engine_reply, text

QUOTA_MSG = "You have reached your specified API usage limits. You will regain access on 2026-12-01 at 00:00 UTC."


class Resp:
    def __init__(self, status, body):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


class Session:
    def __init__(self, resp):
        self.resp = resp

    def post(self, *a, **kw):
        return self.resp


def transport_answering(status, body):
    return llm.anthropic_transport("k", session=Session(Resp(status, body)))


def test_spend_limit_400_is_its_own_code():
    call = transport_answering(400, {"type": "error", "error": {"type": "invalid_request_error", "message": QUOTA_MSG}})
    with pytest.raises(llm.LLMError) as e:
        call({"model": "m"})
    assert e.value.code == "assistant_quota" and e.value.http == 503 and "2026-12-01" in e.value.detail


def test_credit_balance_is_quota_too():
    call = transport_answering(400, {"error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API."}})
    with pytest.raises(llm.LLMError) as e:
        call({"model": "m"})
    assert e.value.code == "assistant_quota"


def test_other_400_stays_assistant_error():
    call = transport_answering(400, {"error": {"type": "invalid_request_error", "message": "max_tokens: field required"}})
    with pytest.raises(llm.LLMError) as e:
        call({"model": "m"})
    assert e.value.code == "assistant_error"


def test_quota_message_says_retry_will_not_help():
    he, en = messages.proxy_msg("assistant_quota", "he"), messages.proxy_msg("assistant_quota", "en")
    assert "לא יעזור" in he and "will not help" in en


def test_quota_is_never_auto_retried_by_the_outbox():
    src = open(os.path.join(os.path.dirname(__file__), "..", "static", "app.js"), encoding="utf-8").read()
    line = next(l for l in src.splitlines() if "const RETRY_CODES" in l)
    assert "assistant_quota" not in line
    assert src.count("ai_quota:") == 2          # banner text in Hebrew and English


def test_health_remembers_until_a_success():
    t = [1000.0]
    h = llm.Health(clock=lambda: t[0])
    state = {"fail": True}

    def call(p):
        if state["fail"]:
            raise llm.LLMError("assistant_quota", 503, detail=QUOTA_MSG)
        return text("ok")
    w = h.watch(call)
    with pytest.raises(llm.LLMError):
        w({})
    assert h.snapshot()["state"] == "quota" and h.snapshot()["since"] == 1000.0
    t[0] = 2000.0
    with pytest.raises(llm.LLMError):
        w({})
    assert h.snapshot()["since"] == 1000.0         # the outage start is kept
    state["fail"] = False
    w({})
    assert h.snapshot()["state"] == "ok" and h.snapshot()["detail"] == ""


def test_transient_errors_do_not_mark_down():
    h = llm.Health()

    def call(p):
        raise llm.LLMError("assistant_busy", 503)
    with pytest.raises(llm.LLMError):
        h.watch(call)({})
    assert h.snapshot()["state"] == "ok"


@pytest.fixture
def quota_app(make_app, transport, tmp_path):
    transport.reply = engine_reply
    fake = FakeLLM()
    fake.down = True

    def call(payload):
        fake.payloads.append(payload)
        if fake.down:
            raise llm.LLMError("assistant_quota", 503, detail=QUOTA_MSG)
        return text("ok")
    return make_app(LLM=call, TRANSLATE_CACHE_DIR=str(tmp_path / "tc")), fake


def test_translate_shows_quota_and_admin_banner(quota_app, pw_hash):
    app, fake = quota_app
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = c.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok})
    j = r.get_json()
    assert r.status_code == 503 and j["error"] == "assistant_quota", j
    assert "will not help" in j["msg"] or "לא יעזור" in j["msg"]
    assert "ai_quota" not in c.get("/api/me").get_json()["warnings"]          # agents get the message, not the admin banner
    ca, _ = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    assert "ai_quota" in ca.get("/api/me").get_json()["warnings"]


def test_healthz_ai_probes_rarely_and_reports(quota_app, pw_hash):
    app, fake = quota_app
    c = app.test_client()
    j = c.get("/healthz/ai").get_json()
    assert j["ok"] and j["state"] == "quota" and "2026-12-01" in j["detail"]
    assert len(fake.payloads) == 1 and fake.payloads[0]["max_tokens"] == 1
    c.get("/healthz/ai")
    assert len(fake.payloads) == 1                 # no second probe inside 5 minutes
    fake.down = False
    ca, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    ca.post("/api/rozela/translate", json={"ticketId": "t1"}, headers={"X-CSRF-Token": tok})   # a real call succeeds again
    assert c.get("/healthz/ai").get_json()["state"] == "ok"
