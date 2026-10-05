"""
engine_proxy.py — the only path from the browser to a brand engine (Apps Script web app).

Safety model:
 - The browser never sees an engine URL or a token. It calls POST /api/<brand>/<fn>; this module
   checks the brand is one the session user holds, the fn is on FN_TABLE, and the user's engine role may
   call it (a mirror of Api.gs apiTable_ — the engine re-checks anyway).
 - Arguments are rebuilt from a per-fn allowlist of keys; anything else the browser sends is dropped.
   `brand` is always set by the server: Api.gs rejects a call whose args.brand is not its own BRAND.
 - The token is minted per call, 10 minutes, and names ONLY the brand being called. If ENGINES_JSON ever
   points brand A's name at brand B's engine, the engine answers "wrong brand" instead of serving B.
 - Engine URLs must look like an Apps Script web app (script.google.com/.../exec); anything else is
   treated as not configured. No customer data is ever put in a URL or a log line here.
"""

import json
import logging
import re
import time

import requests

import messages
import security

ALL_ROLES = ("agent", "admin", "user-manager")
WORK_ROLES = ("agent", "admin")
ADMIN_ONLY = ("admin",)

# fn -> (roles allowed, argument keys the browser may send). Mirrors engine/Api.gs apiTable_.
# NOT here on purpose: apiAdminRun (maintenance, CLI only), apiWa* (the WhatsApp extension's own secret).
FN_TABLE = {
    "apiBoot": (ALL_ROLES, ()),
    "apiStatus": (ALL_ROLES, ()),
    "apiTicket": (WORK_ROLES, ("id",)),
    "apiTicketExtras": (WORK_ROLES, ("id",)),
    "apiTickets": (WORK_ROLES, ("ids",)),
    "apiSearch": (WORK_ROLES, ("q",)),
    "apiSaveDraft": (WORK_ROLES, ("id", "text")),
    "apiSend": (WORK_ROLES, ("id", "text", "override")),
    "apiMarkHandled": (WORK_ROLES, ("id",)),
    "apiClose": (WORK_ROLES, ("id",)),
    "apiNote": (WORK_ROLES, ("id", "text")),
    "apiKachingCancel": (WORK_ROLES, ("id", "contractId", "confirm", "reason")),
    # Auto-cancel queue (Owner, 2026-10-05: the CS team decides). Shapes come from the engine builder later.
    "apiAutoCancelList": (WORK_ROLES, ()),
    "apiAutoCancelApprove": (WORK_ROLES, ("id", "replyText")),
    "apiAutoCancelReject": (WORK_ROLES, ("id", "note")),
    # Auto-reply review queue (Owner, 2026-10-05: easy emails answered by the engine, "only a human eye goes over it")
    "apiAutoReplyList": (WORK_ROLES, ()),
    "apiAutoReplyReview": (WORK_ROLES, ("id", "verdict", "note")),
    # WhatsApp chats the Dondy AI bot is handling (status "bot"): a person takes the conversation back (engine @18)
    "apiWaTakeOver": (WORK_ROLES, ("id",)),
    # System switches. Admin only — checked HERE as well as in the engine.
    "apiSettings": (ADMIN_ONLY, ("action", "key", "value")),
}

# Server-internal only (phase 5 assistant): never reachable from the browser route, only via call(internal=True).
INTERNAL_FNS = {
    "apiKnowledge": (WORK_ROLES, ()),
    "apiCustomerLookup": (WORK_ROLES, ("q",)),
    # performance (2026-10-05): one-call ticket open + incremental list polling
    "apiTicketFull": (WORK_ROLES, ("id", "fresh")),
    "apiAutoReplyList": (WORK_ROLES, ()),
    "apiChanges": (WORK_ROLES, ("since",)),        # final shape: agent/admin, since = int >= 0
    "apiTicket": FN_TABLE["apiTicket"],
    "apiTicketExtras": FN_TABLE["apiTicketExtras"],
}

# apiSettings: the only actions, keys and values the screen may send. Anything else never leaves Flask.
SETTINGS_VALUES = {"DRY_RUN": ("on", "off"), "KACHING_WRITES": ("on", "off"), "AUTO_CANCEL": ("off", "shadow", "on"),
                   "AUTO_REPLY": ("off", "shadow", "on")}

ENGINE_URL_RE = re.compile(r"^https://script\.google\.com/(?:a/macros/[A-Za-z0-9.-]+|macros)/s/[A-Za-z0-9_-]{20,200}/exec$")
KNOWN_BRANDS = ("velora", "rozela", "celesta", "apexmen")    # + EXTRA_BRANDS (selera, elevanu, ...) from the environment

CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 45            # Api.gs holds its lock up to 20s; a Gmail send adds a few seconds
MAX_RESPONSE_BYTES = 3_000_000


log = logging.getLogger("cs_screen.engine")

# Idempotent reads: Apps Script sometimes answers with Google's HTML error page (a few times an hour, often minutes
# after an engine redeploy). Those are retried; a write is NEVER retried (it may have landed). Timeouts are not
# retried either: a slow engine would turn into minutes of waiting.
READ_FNS = frozenset(("apiBoot", "apiChanges", "apiTicket", "apiTicketFull", "apiTicketExtras", "apiTickets", "apiSearch",
                      "apiStatus", "apiAutoReplyList", "apiAutoCancelList", "apiKnowledge", "apiCustomerLookup"))
READ_RETRY_DELAYS_S = (1.5, 3.0)
_sleep = time.sleep


def is_read(fn, args):
    return fn in READ_FNS or (fn == "apiSettings" and isinstance(args, dict) and args.get("action") == "get")


class ProxyError(Exception):
    def __init__(self, code, http=502):
        super().__init__(code)
        self.code = code
        self.http = http


def parse_engines(raw, url_re=ENGINE_URL_RE):
    """ENGINES_JSON -> {brand: url}. Invalid entries are dropped (fail closed) and reported."""
    engines, bad = {}, []
    if not raw:
        return engines, bad
    try:
        data = json.loads(raw)
    except ValueError:
        return {}, ["ENGINES_JSON is not valid JSON"]
    if not isinstance(data, dict):
        return {}, ["ENGINES_JSON must be an object"]
    for brand, url in data.items():
        b = str(brand).lower()
        if not re.match(r"^[a-z0-9][a-z0-9-]{1,29}$", b) or not isinstance(url, str) or not url_re.match(url):
            bad.append("ENGINES_JSON entry rejected: %s" % b[:30])
            continue
        engines[b] = url
    return engines, bad


def clean_args(fn, args, table=None):
    _, keys = (table or FN_TABLE)[fn]
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ProxyError("bad_request", 400)
    out = {}
    for k in keys:
        if k in args:
            v = args[k]
            if k == "since":
                if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                    raise ProxyError("bad_request", 400)
                out[k] = v
                continue
            if k in ("override", "fresh"):
                if v is True:
                    out[k] = True
                continue
            if k == "ids":
                if not isinstance(v, list) or len(v) > 100 or not all(isinstance(x, str) for x in v):
                    raise ProxyError("bad_request", 400)
            elif not isinstance(v, str) or len(v) > 20000:
                raise ProxyError("bad_request", 400)
            out[k] = v
    if fn == "apiSettings":
        action = out.get("action")
        if action == "get":
            out = {"action": "get"}
        elif action == "set":
            key, val = out.get("key"), out.get("value")
            if key not in SETTINGS_VALUES or val not in SETTINGS_VALUES[key]:
                raise ProxyError("bad_request", 400)
            out = {"action": "set", "key": key, "value": val}
        else:
            raise ProxyError("bad_request", 400)
    if fn == "apiAutoCancelReject" and not (2 <= len(out.get("note", "").strip()) <= 300):
        raise ProxyError("bad_note", 400)
    if fn == "apiAutoReplyReview":
        if out.get("verdict") not in ("ok", "problem"):
            raise ProxyError("bad_request", 400)
        note = out.get("note", "").strip()
        if out["verdict"] == "problem" and not (2 <= len(note) <= 300):      # a problem must say what is wrong
            raise ProxyError("bad_note", 400)
        if len(note) > 300:
            raise ProxyError("bad_note", 400)
    return out


def http_transport(session=None):
    """Real engine call: POST, follow Apps Script's 302 to googleusercontent (requests turns it into GET)."""
    s = session or requests.Session()

    def call(url, body):
        try:
            r = s.post(url, data=json.dumps(body), headers={"Content-Type": "application/json"},
                       timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S), allow_redirects=True)
        except requests.Timeout:
            raise ProxyError("engine_timeout", 504)
        except requests.RequestException:
            raise ProxyError("engine_unreachable", 502)
        if r.status_code != 200:
            raise ProxyError("engine_bad_response", 502)
        if len(r.content) > MAX_RESPONSE_BYTES:
            raise ProxyError("engine_bad_response", 502)
        try:
            data = r.json()
        except ValueError:
            raise ProxyError("engine_bad_response", 502)       # e.g. a Google sign-in HTML page
        if not isinstance(data, dict) or "ok" not in data:
            raise ProxyError("engine_bad_response", 502)
        return data

    return call


def localize(fn, resp, lang):
    """Adds `msg` (and `problem_msg`) in the user's language; never removes the engine's own fields."""
    out = dict(resp)
    if fn == "apiKachingCancel" and resp.get("message"):
        out["msg"] = messages.kaching_msg(resp.get("message"), lang)
    elif not resp.get("ok"):
        out["msg"] = messages.engine_error_msg(resp, fn, lang)
    if resp.get("problem"):
        out["problem_msg"] = messages.draft_problem_msg(resp.get("problem"), lang)
    return out


def call(engines, transport, secret, user, brand, fn, args, lang, now=None, internal=False):
    """Returns (http_status, json). Raises nothing for expected failures.
    internal=True is used ONLY by server code (assistant.py) to reach INTERNAL_FNS; the browser route never sets it."""
    roles = user.get("roles", [])
    table = dict(FN_TABLE, **INTERNAL_FNS) if internal else FN_TABLE
    if fn not in table:
        return 404, {"ok": False, "error": "forbidden_fn", "msg": messages.proxy_msg("forbidden_fn", lang)}
    if brand not in user.get("brands", []):
        return 403, {"ok": False, "error": "forbidden_brand", "msg": messages.proxy_msg("forbidden_brand", lang)}
    try:
        role = security.engine_role(roles)
    except ValueError:
        return 403, {"ok": False, "error": "forbidden_role", "msg": messages.proxy_msg("forbidden_role", lang)}
    if role not in table[fn][0]:
        return 403, {"ok": False, "error": "forbidden_role", "msg": messages.proxy_msg("forbidden_role", lang)}
    url = engines.get(brand)
    if not url:
        return 503, {"ok": False, "error": "brand_not_connected", "msg": messages.proxy_msg("brand_not_connected", lang)}
    try:
        clean = clean_args(fn, args, table)
    except ProxyError as e:
        return e.http, {"ok": False, "error": e.code, "msg": messages.proxy_msg(e.code, lang)}
    clean["brand"] = brand
    try:
        token = security.mint_engine_token(secret, user["username"], role, [brand], user.get("lang", "he"), now=now)
    except ValueError:
        return 500, {"ok": False, "error": "server_misconfigured", "msg": messages.proxy_msg("server_misconfigured", lang)}
    started = time.monotonic()
    delays = READ_RETRY_DELAYS_S if is_read(fn, clean) else ()
    attempt = 0
    while True:
        attempt += 1
        t0 = time.monotonic()
        try:
            resp = transport(url, {"fn": fn, "args": clean, "token": token})
            break
        except ProxyError as e:
            ms = int((time.monotonic() - t0) * 1000)
            # timing line: brand, fn, attempt, duration, outcome — never args, never customer data
            log.warning("engine %s %s attempt=%d ms=%d -> %s", brand, fn, attempt, ms, e.code)
            if e.code == "engine_bad_response" and attempt <= len(delays):
                _sleep(delays[attempt - 1])
                continue
            code = e.code
            if code == "engine_bad_response" and not is_read(fn, clean):
                code = "engine_bad_response_write"              # a write may have landed: check before retrying
            return e.http, {"ok": False, "error": e.code, "msg": messages.proxy_msg(code, lang)}
    if attempt > 1:
        log.warning("engine %s %s recovered on attempt=%d total_ms=%d", brand, fn, attempt, int((time.monotonic() - started) * 1000))
    out = localize(fn, resp, lang)
    out["_ms"] = int((time.monotonic() - started) * 1000)
    if attempt > 1:
        out["_attempts"] = attempt
    return 200, out
