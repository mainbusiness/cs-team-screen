"""
llm.py — the only path from this app to the Anthropic Messages API.

Safety model:
 - ANTHROPIC_API_KEY lives only in the Render environment. It is never logged, never put in an error,
   never sent to the browser. Every failure maps to a short code (messages.py translates it).
 - Timeouts on every call; no automatic retry (a retry is the user's click).
 - The response is validated for shape before anyone reads it.
"""

import json
import logging
import re
import threading
import time

import requests

log = logging.getLogger("cs.llm")

# Owner, 2026-11-24: the account hit its monthly API spend limit; Anthropic answers HTTP 400 "You have reached your specified API
# usage limits. You will regain access on <date>". That was shown as "Invalid answer from the AI service. Try again." for every
# translation, so the team kept retrying something that cannot work until the limit is raised. It now has its own code + message,
# is never auto-retried, shows admins a red banner, and /healthz/ai lets the VPS watcher alert the owner on WhatsApp.
QUOTA_RE = re.compile(r"usage limit|credit balance|spend limit|billing", re.I)
DOWN_CODES = ("assistant_quota", "assistant_misconfigured", "assistant_off")   # outages that never heal by retrying

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(Exception):
    def __init__(self, code, http=502, detail=""):
        super().__init__(code)
        self.code = code
        self.http = http
        self.detail = detail


def error_of(r):
    """(type, message) of an Anthropic error body, cut short. Never raises."""
    try:
        e = (r.json() or {}).get("error") or {}
        return str(e.get("type", ""))[:60], re.sub(r"\s+", " ", str(e.get("message", "")))[:300]
    except Exception:
        return "", ""


class Health:
    """The AI service as this app last saw it. Every model call goes through watch(): an outage that retrying cannot fix
    (spend limit, refused key, no key) is remembered until a call succeeds again. Read by /api/me (admin banner) and /healthz/ai."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.code, self.detail, self.since, self.ok_at, self.probed_at = None, "", None, None, 0.0

    def watch(self, call):
        def wrapped(payload):
            try:
                resp = call(payload)
            except LLMError as e:
                if e.code in DOWN_CODES:
                    with self.lock:
                        if self.code != e.code:
                            self.since = self.clock()
                            log.error("AI service down: %s %s", e.code, e.detail)
                        self.code, self.detail = e.code, e.detail
                raise
            with self.lock:
                if self.code:
                    log.warning("AI service back after %s", self.code)
                self.code, self.detail, self.since, self.ok_at = None, "", None, self.clock()
            return resp
        return wrapped

    def snapshot(self):
        with self.lock:
            return {"state": "ok" if not self.code else self.code.replace("assistant_", ""), "detail": self.detail,
                    "since": self.since, "ok_at": self.ok_at}


def anthropic_transport(api_key, session=None, read_timeout=60):
    s = session or requests.Session()

    def call(payload):
        if not api_key:
            raise LLMError("assistant_off", 503)
        try:
            r = s.post(ANTHROPIC_URL, data=json.dumps(payload),
                       headers={"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
                       timeout=(5, read_timeout))
        except requests.Timeout:
            raise LLMError("assistant_timeout", 504)
        except requests.RequestException:
            raise LLMError("assistant_unreachable", 502)
        if r.status_code in (401, 403):
            log.warning("anthropic http %d: the key was refused", r.status_code)
            raise LLMError("assistant_misconfigured", 500)
        if r.status_code in (429, 529) or r.status_code >= 500:
            raise LLMError("assistant_busy", 503)
        if r.status_code != 200:
            etype, emsg = error_of(r)
            log.warning("anthropic http %d %s: %s", r.status_code, etype, emsg)      # Anthropic's own text; never contains the key
            if r.status_code in (400, 402) and QUOTA_RE.search(emsg):
                raise LLMError("assistant_quota", 503, detail=emsg)
            raise LLMError("assistant_error", 502, detail=emsg)
        try:
            data = r.json()
        except ValueError:
            raise LLMError("assistant_error", 502)
        return check(data)

    return call


def check(data):
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise LLMError("assistant_error", 502)
    return data


def text_of(resp):
    return "".join(b.get("text", "") for b in resp.get("content", []) if isinstance(b, dict) and b.get("type") == "text").strip()


def json_of(text):
    """The JSON object of a model answer (tolerates a code fence or a sentence around it). A model that corrects itself writes
    a SECOND object after a sentence ("Wait, I need to correct this..."); one greedy match over both was not JSON, and 1 in 6
    English-desk sends failed with "translation failed" (Owner, 2026-10-11). The last complete object is the answer."""
    s = text or ""
    dec, found = json.JSONDecoder(), None
    i = s.find("{")
    while i >= 0:
        try:
            obj, end = dec.raw_decode(s, i)
        except ValueError:
            i = s.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            found = obj
        i = s.find("{", end)
    if found is None:
        raise LLMError("translate_failed", 502)
    return found
