"""Engine proxy: brand isolation, fn allowlist + roles, token format (ported Api.gs verifier), errors."""
import base64
import hashlib
import hmac
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import engine_proxy
import messages
from conftest import ENGINES, TOKEN_SECRET, call, client_for, logged_in, valid_reply


# ---------- independent port of engine/Api.gs verifyToken_ (do NOT import app code here) ----------

TOKEN_MAX_AGE_S = 12 * 3600
CS_ROLES = ["agent", "admin", "user-manager"]


def gas_b64url_encode(b):            # Utilities.base64EncodeWebSafe(bytes).replace(/=+$/, '')
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def gas_verify_token(token, secret, deployment_brand, now_s):
    if len(secret) < 32:
        return {"ok": False, "reason": "TOKEN_SECRET missing or too short"}
    if not isinstance(token, str) or len(token) < 10 or len(token) > 4096:
        return {"ok": False, "reason": "malformed"}
    parts = token.split(".")
    if len(parts) != 2 or not re.match(r"^[A-Za-z0-9_-]+$", parts[0]) or not re.match(r"^[A-Za-z0-9_-]+$", parts[1]):
        return {"ok": False, "reason": "malformed"}
    # Utilities.computeHmacSha256Signature(message=parts[0], key=secret): both strings, UTF-8
    sig = gas_b64url_encode(hmac.new(secret.encode("utf-8"), parts[0].encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, parts[1]):
        return {"ok": False, "reason": "bad signature"}
    pad = "" if len(parts[0]) % 4 == 0 else "=" * (4 - len(parts[0]) % 4)
    try:
        c = json.loads(base64.urlsafe_b64decode(parts[0] + pad).decode("utf-8"))
    except Exception:
        return {"ok": False, "reason": "unreadable payload"}
    if not isinstance(c, dict):
        return {"ok": False, "reason": "unreadable payload"}
    if not isinstance(c.get("exp"), (int, float)) or not isinstance(c.get("iat"), (int, float)):
        return {"ok": False, "reason": "no exp/iat"}
    if c["exp"] <= now_s:
        return {"ok": False, "reason": "expired"}
    if c["iat"] > now_s + 60:
        return {"ok": False, "reason": "issued in the future"}
    if c["exp"] - c["iat"] > TOKEN_MAX_AGE_S + 60:
        return {"ok": False, "reason": "lifetime too long"}
    if not isinstance(c.get("user"), str) or not c["user"] or len(c["user"]) > 64:
        return {"ok": False, "reason": "no user"}
    if not isinstance(c.get("role"), str) or c["role"] not in CS_ROLES:
        return {"ok": False, "reason": "unknown role"}
    if not isinstance(c.get("brands"), list) or deployment_brand.lower() not in [str(b).lower() for b in c["brands"]]:
        return {"ok": False, "reason": "wrong brand"}
    return {"ok": True, "claims": {"user": c["user"], "role": c["role"], "brands": c["brands"], "lang": str(c.get("lang") or "he")[:5]}}


def payload_of(token):
    p = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


# ---------- token round trip ----------

def test_token_round_trips_through_the_apps_script_algorithm(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela", "celesta"])
    assert call(c, tok, "rozela", "apiBoot").status_code == 200
    url, body = transport.calls[0]
    assert url == ENGINES["rozela"]
    assert set(body) == {"fn", "args", "token", "rid"} and body["fn"] == "apiBoot" and len(body["rid"]) == 16
    now = int(time.time())
    v = gas_verify_token(body["token"], TOKEN_SECRET, "rozela", now)
    assert v["ok"], v
    assert v["claims"] == {"user": "manager", "role": "admin", "brands": ["rozela"], "lang": "he"}
    p = payload_of(body["token"])
    assert set(p) == {"user", "role", "brands", "lang", "iat", "exp"}
    assert abs(p["iat"] - now) <= 2 and 540 <= p["exp"] - p["iat"] <= 660          # ~10 min
    # least privilege: the token names only the called brand, so a mis-wired URL is refused by the engine
    assert gas_verify_token(body["token"], TOKEN_SECRET, "celesta", now)["reason"] == "wrong brand"
    assert gas_verify_token(body["token"], TOKEN_SECRET + "x", "rozela", now)["reason"] == "bad signature"
    assert gas_verify_token(body["token"], TOKEN_SECRET, "rozela", p["exp"] + 1)["reason"] == "expired"
    forged = body["token"].split(".")[0][:-2] + "AA." + body["token"].split(".")[1]
    assert not gas_verify_token(forged, TOKEN_SECRET, "rozela", now)["ok"]
    assert body["token"] not in json.dumps(call(c, tok, "rozela", "apiBoot").get_json())   # never echoed to the browser


def test_token_role_mapping(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta"])
    call(c, tok, "celesta", "apiBoot")
    assert payload_of(transport.calls[-1][1]["token"])["role"] == "agent"
    c2, tok2 = logged_in(app, pw_hash, "mgr", ["user-manager"], ["celesta"])
    call(c2, tok2, "celesta", "apiBoot")
    assert payload_of(transport.calls[-1][1]["token"])["role"] == "user-manager"


def test_mint_refuses_short_secret_and_long_lifetime():
    import security
    with pytest.raises(ValueError):
        security.mint_engine_token("short", "u", "agent", ["rozela"], "he")
    with pytest.raises(ValueError):
        security.mint_engine_token(TOKEN_SECRET, "u", "agent", ["rozela"], "he", ttl_s=13 * 3600)


def test_short_token_secret_refuses_to_start(make_app):
    with pytest.raises(RuntimeError):
        make_app(TOKEN_SECRET="too-short")


def test_short_token_secret_at_call_time_answers_clean_error(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.config["TOKEN_SECRET"] = "x"           # defense in depth behind the startup check
    r = call(c, tok, "rozela", "apiBoot")
    assert r.status_code == 500 and r.get_json()["error"] == "server_misconfigured"
    assert transport.calls == []


# ---------- brand isolation ----------

def test_user_without_rozela_gets_403_on_every_rozela_fn(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta", "apexmen"])
    for fn in engine_proxy.FN_TABLE:
        r = call(c, tok, "rozela", fn, {"id": "t1"})
        assert r.status_code == 403, fn
        assert r.get_json()["error"] == "forbidden_brand"
        assert "אין לך הרשאה למותג" in r.get_json()["msg"]
    assert transport.calls == []
    assert call(c, tok, "celesta", "apiBoot").status_code == 200


def last(transport, fn):
    """The newest call of one fn (writes now also trigger a background revalidation call)."""
    return [b for _, b in transport.calls if b["fn"] == fn][-1]


def test_brand_arg_is_forced_and_unknown_args_dropped(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    call(c, tok, "rozela", "apiTicket", {"id": "t1", "brand": "celesta", "user": "admin", "override": True})
    assert transport.calls[-1][1]["args"] == {"id": "t1", "brand": "rozela"}
    call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "hi", "override": "yes"})
    assert last(transport, "apiSend")["args"] == {"id": "t1", "text": "hi", "brand": "rozela"}       # only literal true passes
    call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "hi", "override": True})
    assert last(transport, "apiSend")["args"]["override"] is True
    assert call(c, tok, "rozela", "apiTicket", {"id": {"$ne": 1}}).status_code == 400


def test_unconnected_brand(make_app, pw_hash, transport):
    app = make_app(ENGINES_JSON=json.dumps({"rozela": ENGINES["rozela"]}))
    c, tok = logged_in(app, pw_hash, "gc", ["agent"], ["rozela", "velora"])
    r = call(c, tok, "velora", "apiBoot")
    assert r.status_code == 503 and "עוד לא מחובר" in r.get_json()["msg"]
    me = c.get("/api/me").get_json()
    assert {"id": "velora", "connected": False} in me["brands"]


def test_engines_json_accepts_only_apps_script_urls():
    good = "https://script.google.com/macros/s/AKfycbwT4PpZsdhAnzm9vbDMLkBTnYWo/exec"
    workspace = "https://script.google.com/a/macros/tryrozela.com/s/AKfycbwT4PpZsdhAnzm9vbDMLkBTnYWo/exec"
    eng, bad = engine_proxy.parse_engines(json.dumps({"rozela": good, "Celesta": workspace, "evil": "https://evil.example/exec",
                                                      "x": "http://script.google.com/macros/s/AKfycbwT4PpZsdhAnzm9vbDMLkBTnYWo/exec"}))
    assert eng == {"rozela": good, "celesta": workspace}
    assert len(bad) == 2
    assert engine_proxy.parse_engines("not json")[0] == {}


# ---------- fn allowlist + roles ----------

@pytest.mark.parametrize("fn", ["apiAdminRun", "apiWaIngest", "apiWaOutbox", "apiWaSent", "bootstrap", "doPost", "__proto__", "apiboot"])
def test_fn_not_on_allowlist_is_refused(app, pw_hash, transport, fn):
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    r = call(c, tok, "rozela", fn)
    assert r.status_code == 404 and r.get_json()["error"] == "forbidden_fn"
    assert transport.calls == []


def test_user_manager_only_reaches_boot_and_status(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert call(c, tok, "rozela", "apiBoot").status_code == 200
    assert call(c, tok, "rozela", "apiStatus").status_code == 200
    for fn in ("apiTicket", "apiSend", "apiKachingCancel", "apiAutoCancelList", "apiAutoCancelApprove", "apiAutoCancelReject", "apiSettings"):
        r = call(c, tok, "rozela", fn, {"id": "t1", "action": "get", "note": "because"})
        assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role", fn
    assert [b["fn"] for _, b in transport.calls] == ["apiBoot", "apiStatus"]


# ---------- auto-cancel + settings role checks (Flask enforces them, not only the engine) ----------

def test_agent_may_use_the_auto_cancel_queue(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert call(c, tok, "rozela", "apiAutoCancelList").status_code == 200
    assert call(c, tok, "rozela", "apiAutoCancelApprove", {"id": "t1", "replyText": "היי", "contractId": "x"}).status_code == 200
    assert last(transport, "apiAutoCancelApprove")["args"] == {"id": "t1", "replyText": "היי", "brand": "rozela"}
    assert call(c, tok, "rozela", "apiAutoCancelReject", {"id": "t1", "note": "צריך בדיקה"}).status_code == 200
    assert last(transport, "apiAutoCancelReject")["args"] == {"id": "t1", "note": "צריך בדיקה", "brand": "rozela"}


@pytest.mark.parametrize("note", ["", "x", "y" * 301])
def test_reject_note_length_checked_before_the_engine(app, pw_hash, transport, note):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiAutoCancelReject", {"id": "t1", "note": note})
    assert r.status_code == 400 and r.get_json()["error"] == "bad_note"
    assert transport.calls == []


@pytest.mark.parametrize("roles", [["agent"], ["user-manager"], ["agent", "user-manager"]])
def test_settings_refused_for_non_admins_in_flask(app, pw_hash, transport, roles):
    c, tok = logged_in(app, pw_hash, "u1", roles, ["rozela"])
    for args in ({"action": "get"}, {"action": "set", "key": "DRY_RUN", "value": "off"}):
        r = call(c, tok, "rozela", "apiSettings", args)
        assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role"
    assert transport.calls == []


def test_settings_allowed_for_admin_with_strict_args(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela"])
    assert call(c, tok, "rozela", "apiSettings", {"action": "get", "key": "junk"}).status_code == 200
    assert transport.calls[-1][1]["args"] == {"action": "get", "brand": "rozela"}
    assert payload_of(transport.calls[-1][1]["token"])["role"] == "admin"
    assert call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "AUTO_CANCEL", "value": "shadow"}).status_code == 200
    assert transport.calls[-1][1]["args"] == {"action": "set", "key": "AUTO_CANCEL", "value": "shadow", "brand": "rozela"}
    n = len(transport.calls)
    for bad in ({"action": "set", "key": "TOKEN_SECRET", "value": "x"}, {"action": "set", "key": "DRY_RUN", "value": "shadow"},
                {"action": "delete"}, {"op": "get"}, {"action": "set", "key": "AUTO_CANCEL", "value": True}):
        assert call(c, tok, "rozela", "apiSettings", bad).status_code == 400, bad
    assert len(transport.calls) == n


# ---------- engine answers + localization ----------

def test_engine_refusals_are_translated(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": False, "error": "dry_run"}
    j = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "x"}).get_json()
    assert j["error"] == "dry_run" and j["msg"] == "מצב ניסיון — שליחה כבויה."
    transport.reply = {"ok": False, "error": "draft_problem", "problem": "price not in policy: 99 ₪"}
    j = call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "x"}).get_json()
    assert "\u2068" in j["msg"]                      # the inserted value is bidi-isolated inside the Hebrew sentence
    assert "מחיר שלא מופיע במדיניות: 99 ₪" in j["msg"].replace("\u2068", "").replace("\u2069", "") and j["problem"] == "price not in policy: 99 ₪"
    transport.reply = {"ok": False, "error": "something_new"}
    j = call(c, tok, "rozela", "apiBoot").get_json()
    assert j["error"] == "something_new" and "something_new" not in j["msg"]          # never a raw code in front of an agent


KACHING_GATE_MESSAGES = [
    "cancellations are switched off",
    "cancellations are frozen: 2026-10-05T09:00:00.000Z — daily limit of 100 cancellations reached",
    'role "user-manager" may not cancel subscriptions',
    "exactly one valid contract id is required",
    "confirmation code does not match the contract",
    "ticket has no customer email",
    "no cancel request from the customer and no written reason",
    "another cancellation is running, try again",
    "limit: 20 cancellations per hour per user",
    "this contract does not belong to the ticket's customer",
    "status EXPIRED cannot be cancelled",
    "Kaching returned 502. Not retried — check in Kaching before trying again.",
    "request accepted but status is ACTIVE — check in Kaching",
    "request sent but the outcome is unknown — check in Kaching, do not retry",
    "error: kaching: contracts lookup failed (500)",
    "cancelled",
    "already cancelled",
]


@pytest.mark.parametrize("raw", KACHING_GATE_MESSAGES)
def test_every_kaching_gate_sentence_has_hebrew(raw):
    he = messages.kaching_msg(raw, "he")
    assert not he.startswith("תשובה מהמנוי"), raw            # fell through to the generic fallback = missing translation
    assert re.search(r"[֐-׿]", he)


def test_kaching_gate_messages_match_the_engine_source():
    """Drift guard: every refuse('...') literal in Kaching.gs must be covered by a pattern here."""
    import os
    src = os.path.join(os.path.dirname(__file__), "..", "..", "engine", "Kaching.gs")
    if not os.path.exists(src):
        pytest.skip("engine source not next to this folder (deployed copy)")
    text = open(src, encoding="utf-8").read()
    lits = []
    for m in re.finditer(r"refuse\((.*?)\);", text):
        # rebuild the runtime string: literals kept, every variable part replaced by "X"
        parts = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|([^+'\"]+)", m.group(1))
        out = "".join((a or b).replace("\\'", "'") if (a or b) else ("" if not c.strip() else "X") for a, b, c in parts)
        if out and out != "X":
            lits.append(out)
    assert len(lits) >= 8, lits
    for lit in lits:
        assert not messages.kaching_msg(lit, "he").startswith("תשובה מהמנוי"), lit


def test_cancel_refusal_carries_raw_and_hebrew(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": False, "status": None, "message": "cancellations are switched off"}
    j = call(c, tok, "rozela", "apiKachingCancel", {"id": "t1", "contractId": "gid://shopify/SubscriptionContract/1234", "confirm": "1234"}).get_json()
    assert j["message"] == "cancellations are switched off"
    assert j["msg"].startswith("ביטולי מנויים כבויים")


@pytest.mark.parametrize("fn,code,extra", [
    ("apiAutoCancelApprove", "bad_id", {}), ("apiAutoCancelApprove", "bad_text", {}), ("apiAutoCancelApprove", "not_found", {}),
    ("apiAutoCancelApprove", "no_auto_record", {}), ("apiAutoCancelApprove", "not_approvable", {"state": "queued"}),
    ("apiAutoCancelApprove", "newer_message", {}), ("apiAutoCancelApprove", "draft_problem", {"problem": "mentions AI"}),
    ("apiAutoCancelApprove", "live_switches_off", {"reason": "DRY_RUN=on"}),
    ("apiAutoCancelReject", "bad_note", {}), ("apiAutoCancelReject", "not_found", {}), ("apiAutoCancelReject", "no_auto_record", {}),
    ("apiAutoCancelReject", "not_rejectable", {}),
    ("apiSettings", "bad_action", {}), ("apiSettings", "bad_key", {}), ("apiSettings", "bad_value", {"allowed": ["off", "shadow", "on"]}),
    ("apiSettings", "needs_live_switches", {"reason": "KACHING_WRITES=off"}),
])
def test_auto_cancel_and_settings_errors_have_hebrew(fn, code, extra):
    msg = messages.engine_error_msg(dict({"ok": False, "error": code}, **extra), fn, "he")
    assert re.search(r"[֐-׿]", msg) and "המנוע סירב:" not in msg, (fn, code, msg)
    if "state" in extra:
        assert extra["state"] in msg
    if code == "draft_problem":
        assert "בינה מלאכותית" in msg


# ---------- real HTTP transport against a local fake Apps Script ----------

class FakeAppsScript(BaseHTTPRequestHandler):
    posts = []
    flaky = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        FakeAppsScript.posts.append(json.loads(self.rfile.read(n)))
        path = self.path
        if path.startswith("/macros/s/AKfycbOK"):
            self.send_response(302)                       # what Apps Script does: 302 to googleusercontent
            self.send_header("Location", "/echo?user_content_key=abc")
            self.end_headers()
        elif path.startswith("/macros/s/AKfycbSLOW"):
            time.sleep(1.5)
            self.send_response(200)
            self.end_headers()
        elif path.startswith("/macros/s/AKfycbFLAKY"):
            FakeAppsScript.flaky += 1
            if FakeAppsScript.flaky == 1:
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><title>Error</title>Google Apps Script: Service unavailable</html>")
            else:
                self.send_response(302)
                self.send_header("Location", "/echo?user_content_key=abc")
                self.end_headers()
        elif path.startswith("/macros/s/AKfycbHTML"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>Sign in - Google Accounts</html>")
        else:
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/echo"):
            body = json.dumps({"ok": True, "echo": FakeAppsScript.posts[-1]["fn"], "tickets": [], "counts": {}, "version": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def fake_gas():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeAppsScript)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    FakeAppsScript.posts = []
    FakeAppsScript.flaky = 0
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def http_app(make_app, base):
    engines = {
        "rozela": base + "/macros/s/AKfycbOK000000000000000000000/exec",
        "celesta": base + "/macros/s/AKfycbSLOW00000000000000000000/exec",
        "velora": base + "/macros/s/AKfycbHTML00000000000000000000/exec",
        "apexmen": base + "/macros/s/AKfycbFAIL00000000000000000000/exec",
    }
    return make_app(ENGINES_JSON=json.dumps(engines), TRANSPORT=None,
                    ENGINE_URL_RE=re.compile(r"^http://127\.0\.0\.1:\d+/macros/s/[A-Za-z0-9_-]{20,200}/exec$"))


def test_http_transport_follows_the_redirect_and_delivers_the_token(make_app, pw_hash, fake_gas):
    app = http_app(make_app, fake_gas)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiBoot")
    assert r.status_code == 200 and r.get_json()["echo"] == "apiBoot"
    sent = FakeAppsScript.posts[-1]
    assert gas_verify_token(sent["token"], TOKEN_SECRET, "rozela", int(time.time()))["ok"]


def test_http_transport_errors_are_clean_hebrew(make_app, pw_hash, fake_gas, monkeypatch):
    monkeypatch.setattr(engine_proxy, "READ_TIMEOUT_S", 0.5)
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: None)
    app = http_app(make_app, fake_gas)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["celesta", "velora", "apexmen", "rozela"])
    r = call(c, tok, "celesta", "apiSend", {"id": "t1", "text": "x"})
    j = r.get_json()                                                    # a send may have happened: resolved, then said plainly
    assert j["error"] == "write_unknown" and j["refresh"] is True and "לא הצלחנו לאשר" in j["msg"]
    r = call(c, tok, "velora", "apiBoot")
    assert r.status_code == 502 and r.get_json()["error"] == "engine_bad_response"
    r = call(c, tok, "apexmen", "apiBoot")
    assert r.status_code == 502 and r.get_json()["error"] == "engine_bad_response"


def test_unreachable_engine(make_app, pw_hash):
    app = make_app(ENGINES_JSON=json.dumps({"rozela": "http://127.0.0.1:9/macros/s/AKfycbDEAD000000000000000000/exec"}), TRANSPORT=None,
                   ENGINE_URL_RE=re.compile(r"^http://127\.0\.0\.1:\d+/macros/s/[A-Za-z0-9_-]{20,200}/exec$"))
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiBoot")
    assert r.status_code == 502 and r.get_json()["error"] == "engine_unreachable"
    assert "אין חיבור" in r.get_json()["msg"]


def test_not_logged_in_api_is_401(app):
    c = client_for(app)
    assert c.post("/api/rozela/apiBoot", json={}).status_code in (401, 403)
    assert c.get("/api/me").status_code == 401



# ---------- Google's HTML error page: reads retry, writes never (2026-10-05) ----------

@pytest.fixture
def fast_retry(monkeypatch):
    slept = []
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: slept.append(s))
    return slept


def flaky(n_bad, transport):
    left = [n_bad]

    def reply(url, body):
        if left[0] > 0:
            left[0] -= 1
            raise engine_proxy.ProxyError("engine_bad_response", 502)
        return valid_reply(url, body)
    transport.reply = reply


@pytest.mark.parametrize("fn,args", [("apiBoot", {}), ("apiTicket", {"id": "t1"}), ("apiSearch", {"q": "dana"}),
                                     ("apiAutoReplyList", {}), ("apiTicketExtras", {"id": "t1"})])
def test_read_survives_one_html_answer(app, pw_hash, transport, fast_retry, fn, args):
    flaky(1, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", fn, args)
    assert r.status_code == 200 and r.get_json()["ok"] and r.get_json()["_attempts"] == 2
    assert [b["fn"] for _, b in transport.calls] == [fn, fn] and fast_retry == [1.5]


def test_read_gives_up_after_two_retries(app, pw_hash, transport, fast_retry):
    flaky(5, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiBoot")
    assert r.status_code == 502 and r.get_json()["error"] == "engine_bad_response"
    assert len(transport.calls) == 3 and fast_retry == [1.5, 3.0]


def test_settings_get_is_a_read_but_set_is_not(app, pw_hash, transport, fast_retry):
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    flaky(1, transport)
    assert call(c, tok, "rozela", "apiSettings", {"action": "get"}).get_json()["ok"]
    assert [b["fn"] for _, b in transport.calls] == ["apiSettings", "apiSettings"]     # a read: plain retry
    transport.calls.clear()
    flaky(1, transport)
    call(c, tok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "off"})
    fns = [b["fn"] for _, b in transport.calls]
    assert fns[0] == "apiSettings" and fns[1] == "apiResult"                          # a write: resolved, not retried


@pytest.mark.parametrize("fn,args", [("apiSend", {"id": "t1", "text": "x"}), ("apiSaveDraft", {"id": "t1", "text": "x"}),
                                     ("apiMarkHandled", {"id": "t1"}), ("apiClose", {"id": "t1"}), ("apiNote", {"id": "t1", "text": "x"}),
                                     ("apiKachingCancel", {"id": "t1", "contractId": "gid://shopify/SubscriptionContract/1", "confirm": "0001"}),
                                     ("apiAutoReplyReview", {"id": "t1", "verdict": "ok"}), ("apiWaTakeOver", {"id": "t1"})])
def test_write_is_never_blindly_retried(app, pw_hash, transport, fast_retry, fn, args):
    """QA round 4 contract: a lost write reply is resolved via apiResult first; only when the engine says "not found"
    is the SAME call resent once with the SAME rid (idempotent on the engine). Never a third time, never a new rid."""
    flaky(1, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    app.extensions["cs"]["ticket_cache"]._background = lambda *a, **k: False
    j = call(c, tok, "rozela", fn, args).get_json()
    writes = [b for _, b in transport.calls if b["fn"] == fn]
    lookups = [b for _, b in transport.calls if b["fn"] == "apiResult"]
    assert len(writes) == 2 and writes[0]["rid"] == writes[1]["rid"]
    assert lookups and all(b["args"]["rid"] == writes[0]["rid"] for b in lookups)
    order = [b["fn"] for _, b in transport.calls]
    assert order.index("apiResult") < len(order) - 1 and order[-1] == fn             # the resend comes after the lookups
    assert j["ok"] is True and j["recovered"] == "resend"
    assert fast_retry == list(engine_proxy.RESULT_POLL_DELAYS_S)                      # no read-style retry of the write itself


def test_real_http_html_then_json(make_app, pw_hash, fake_gas, fast_retry):
    """The real transport against a local fake Apps Script that answers Google's HTML page once, then JSON."""
    engines = {"rozela": fake_gas + "/macros/s/AKfycbFLAKY0000000000000000000/exec"}
    app = make_app(ENGINES_JSON=json.dumps(engines), TRANSPORT=None,
                   ENGINE_URL_RE=re.compile(r"^http://127\.0\.0\.1:\d+/macros/s/[A-Za-z0-9_-]{20,200}/exec$"))
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = call(c, tok, "rozela", "apiBoot")
    assert r.status_code == 200 and r.get_json()["echo"] == "apiBoot" and FakeAppsScript.flaky == 2



def test_slow_failure_is_not_retried(app, pw_hash, transport, fast_retry, monkeypatch):
    """A 30-second engine failure must not be repeated: it would hold a server thread for minutes."""
    t = [0.0]
    monkeypatch.setattr(engine_proxy, "_clock", lambda: t[0])

    def reply(url, body):
        t[0] += 9.0                                    # 9 s of engine work, then an HTML page: slow -> no retry (budget alone would allow one)
        raise engine_proxy.ProxyError("engine_bad_response", 502)
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert call(c, tok, "rozela", "apiBoot").status_code == 502
    assert len(transport.calls) == 1 and fast_retry == []


def test_retry_respects_the_total_budget(app, pw_hash, transport, fast_retry, monkeypatch):
    t = [0.0]
    monkeypatch.setattr(engine_proxy, "_clock", lambda: t[0])
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: (fast_retry.append(s), t.__setitem__(0, t[0] + s)))

    def reply(url, body):
        t[0] += 7.9                                    # fast (<8 s): retried once (t=9.4); after attempt 2 (t=17.3) +3 s breaks 20 s
        raise engine_proxy.ProxyError("engine_bad_response", 502)
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    call(c, tok, "rozela", "apiBoot")
    assert len(transport.calls) == 2 and fast_retry == [1.5]


def test_background_work_is_never_retried(app, pw_hash, transport, fast_retry):
    flaky(10, transport)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    c.post("/api/rozela/prefetch", json={"ids": ["p1", "p2"]}, headers={"X-CSRF-Token": tok})
    app.extensions["cs"]["ticket_cache"].drain()
    per_id = {}
    for _, b in transport.calls:
        per_id[(b["fn"], b["args"].get("id"))] = per_id.get((b["fn"], b["args"].get("id")), 0) + 1
    assert per_id and all(n == 1 for n in per_id.values()) and fast_retry == []
