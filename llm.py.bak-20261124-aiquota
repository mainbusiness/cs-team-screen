"""
llm.py — the only path from this app to the Anthropic Messages API.

Safety model:
 - ANTHROPIC_API_KEY lives only in the Render environment. It is never logged, never put in an error,
   never sent to the browser. Every failure maps to a short code (messages.py translates it).
 - Timeouts on every call; no automatic retry (a retry is the user's click).
 - The response is validated for shape before anyone reads it.
"""

import json
import re

import requests

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(Exception):
    def __init__(self, code, http=502):
        super().__init__(code)
        self.code = code
        self.http = http


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
            raise LLMError("assistant_misconfigured", 500)
        if r.status_code in (429, 529) or r.status_code >= 500:
            raise LLMError("assistant_busy", 503)
        if r.status_code != 200:
            raise LLMError("assistant_error", 502)
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
