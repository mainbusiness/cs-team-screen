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
import os
import re
import secrets
import threading
import time
from urllib.parse import urlparse

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
    # engine @35/36 (2026-10-05): the open ticket's cheap check. {id, since: ticket v, seen: messages we hold}
    "apiTicketLite": (WORK_ROLES, ("id", "since", "seen")),
    # engine 2026-10-06: the day's numbers from the conversations themselves (managers' dashboard). Chunked: partial + next.
    "apiDayStats": (("admin", "user-manager"), ("date", "cursor")),
    # QA round 4: the stored final reply of a write, by the rid it was sent with (engine keeps it 30 min)
    "apiResult": (WORK_ROLES, ("rid",)),
    "apiTicket": FN_TABLE["apiTicket"],
    "apiTicketExtras": FN_TABLE["apiTicketExtras"],
}

# apiSettings: the only actions, keys and values the screen may send. Anything else never leaves Flask.
SETTINGS_VALUES = {"DRY_RUN": ("on", "off"), "KACHING_WRITES": ("on", "off"), "AUTO_CANCEL": ("off", "shadow", "on"),
                   "AUTO_REPLY": ("off", "shadow", "on")}

def _core_url_re():
    """The core server (Node + Postgres) may replace a brand's Apps Script URL. Only the ONE host named in CORE_ENGINE_HOST is accepted."""
    host = os.environ.get("CORE_ENGINE_HOST", "").strip().lower()
    if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", host):
        return None
    return re.compile(r"^https://" + re.escape(host) + r"/exec/[a-z][a-z0-9]{1,30}$")


class _EngineUrl:
    """Apps Script web-app URLs, plus the core server's per-brand URL when CORE_ENGINE_HOST is set."""
    def __init__(self, gas):
        self.gas = gas

    def match(self, url):
        core = _core_url_re()
        return self.gas.match(url) or (core.match(url) if core else None)


ENGINE_URL_RE = _EngineUrl(re.compile(r"^https://script\.google\.com/(?:a/macros/[A-Za-z0-9.-]+|macros)/s/[A-Za-z0-9_-]{20,200}/exec$"))
KNOWN_BRANDS = ("velora", "rozela", "celesta", "apexmen")    # + EXTRA_BRANDS (selera, elevanu, ...) from the environment

CONNECT_TIMEOUT_S = 5
READ_TIMEOUT_S = 45            # Api.gs holds its lock up to 20s; a Gmail send adds a few seconds
MAX_RESPONSE_BYTES = 3_000_000


log = logging.getLogger("cs_screen.engine")

# Idempotent reads: Apps Script sometimes answers with Google's HTML error page (a few times an hour, often minutes
# after an engine redeploy). Those are retried; a write is NEVER retried (it may have landed). Timeouts are not
# retried either: a slow engine would turn into minutes of waiting.
READ_FNS = frozenset(("apiBoot", "apiChanges", "apiTicket", "apiTicketFull", "apiTicketExtras", "apiTickets", "apiSearch",
                      "apiStatus", "apiAutoReplyList", "apiAutoCancelList", "apiKnowledge", "apiCustomerLookup",
                      "apiResult", "apiTicketLite", "apiDayStats"))   # apiResult is a read: it must NEVER enter write resolution (that recursed)
READ_RETRY_DELAYS_S = (1.5, 3.0)
# Measured live (2026-10-05): many of these HTML answers come after 9-44 s of engine work. Retrying THOSE tripled
# the time a server thread was held (70-110 s), the 16 threads ran out, Render's health check timed out and the
# edge served 502s. So only a FAST failure (a redeploy blip) is retried, inside a total budget, and background work
# (prefetch, revalidation, polling) is never retried at all — its next tick is the retry.
RETRY_FAST_FAIL_S = 8.0
RETRY_TOTAL_BUDGET_S = 20.0
# Engine agent, 2026-10-05: these run in 11-77 ms inside Apps Script; the 8-42 s we saw is Google's front door (302 queue,
# POST->GET, 404) BEFORE the engine runs. So: a short read timeout and ONE immediate retry with the same rid (reads
# only — a write is never retried), and for the open ticket a hedge: a second identical request after HEDGE_AFTER_S,
# only if a SHARED slot is free (never the reserved one, never over the cap of 6).
FAST_READS = frozenset(("apiTicketLite", "apiChanges", "apiTicketFull", "apiTicket", "apiTicketExtras", "apiResult"))
FAST_READ_TIMEOUT_S = 12.0
FAST_RETRY_BUDGET_S = 26.0
HEDGE_AFTER_S = 4.0
_sleep = time.sleep
_clock = time.monotonic


# ---------- per-brand gate (2026-10-05) ----------
# Apps Script runs the web app as the deploying user, and that user has ~30 simultaneous executions in total. Over
# it, calls queue ~30 s and then fail with Google's HTML page — measured: one burst at 02:56-03:04 UTC hit every read
# on three brands at once (our retry deploy + prefetch + verification opens). So this process never has more than
# GATE_CAP calls in flight per brand engine. Interactive calls (an agent's open, send, save, search) wait for a slot
# (at most GATE_WAIT_S, then "busy"); background calls (prefetch, revalidation, list refresh) take only a FREE slot,
# at most GATE_BG_CAP at a time, never while an interactive call is waiting, and are dropped (not queued) otherwise.
# An error answer (HTML/404/unreachable) or engine work (serverMs) > BREAKER_SLOW_S trips a per-brand breaker that stops
# background calls for BREAKER_S. Wall time alone never trips it (2026-10-05: that is Google's gateway, not engine load).
GATE_CAP = 6
GATE_BG_CAP = 2
# P0 speed: of the 6 slots, GATE_RESERVED are kept for the ticket an agent has OPEN and an approved human send.
# A send must not fail busy while the sixth slot sits idle (live incident, 2026-10-06).
# Ordinary interactive calls (list, saves, assistant) use at most GATE_CAP - GATE_RESERVED; background
# calls only that much too. A "top" call may take any free slot and is served before every other waiter.
GATE_RESERVED = 1
GATE_WAIT_S = 15.0
BREAKER_SLOW_S = 10.0
BREAKER_S = 60.0
BREAKER_CODES = ("engine_bad_response", "engine_unreachable")    # error answers; a timeout is wall time (see release)


class BrandGate:
    def __init__(self):
        self.cond = threading.Condition()
        self.inflight = 0
        self.bg_inflight = 0
        self.fg_waiting = 0
        self.top_waiting = 0
        self.top_served = 0
        self.peak = 0
        self.dropped = 0
        self.busy = 0
        self.trip_until = 0.0

    def tripped(self):
        return _clock() < self.trip_until

    def acquire(self, bg, top=False):
        shared = GATE_CAP - GATE_RESERVED            # what everything but the open ticket may use
        with self.cond:
            if bg:
                if (self.inflight >= shared or self.bg_inflight >= GATE_BG_CAP or self.fg_waiting or self.top_waiting
                        or self.tripped()):
                    self.dropped += 1
                    return False
                self.bg_inflight += 1
            elif top:
                self.top_waiting += 1
                try:
                    if not self.cond.wait_for(lambda: self.inflight < GATE_CAP, GATE_WAIT_S):
                        self.busy += 1
                        return False
                finally:
                    self.top_waiting -= 1
                    self.cond.notify_all()
                self.top_served += 1
            else:
                self.fg_waiting += 1
                try:
                    if not self.cond.wait_for(lambda: self.inflight < shared and not self.top_waiting, GATE_WAIT_S):
                        self.busy += 1
                        return False
                finally:
                    self.fg_waiting -= 1
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            return True

    def try_hedge(self):
        """A second copy of an open-ticket read: only a free SHARED slot, nobody waiting, never the reserved one."""
        with self.cond:
            if self.inflight >= GATE_CAP - GATE_RESERVED or self.fg_waiting or self.top_waiting:
                return False
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            self.hedges = getattr(self, "hedges", 0) + 1
            return True

    def release(self, bg, took_s, code, server_ms=None):
        """Coordinator, 2026-10-05: the breaker protects the ENGINE, so it trips on an error answer or on the engine's own
        work (serverMs) over BREAKER_SLOW_S — never on wall time. A slow wall time with a small serverMs is Google's
        gateway (302 queue), not engine load; the cap of 6 per brand and the reserved slot bound our load either way.
        A timeout carries no serverMs: it is wall time, so it does not trip it either."""
        with self.cond:
            self.inflight -= 1
            if bg:
                self.bg_inflight -= 1
            engine_slow = isinstance(server_ms, (int, float)) and not isinstance(server_ms, bool) and server_ms > BREAKER_SLOW_S * 1000
            if code in BREAKER_CODES or engine_slow:
                self.trip_until = _clock() + BREAKER_S
                self.trips = getattr(self, "trips", 0) + 1
            self.cond.notify_all()


_gates = {}
_gates_lock = threading.Lock()


def gate(brand):
    with _gates_lock:
        g = _gates.get(brand)
        if g is None:
            g = _gates[brand] = BrandGate()
        return g


def reset_gates():
    with _gates_lock:
        _gates.clear()


def _wire(args):
    return {k: v for k, v in args.items() if not k.startswith("_")}


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
            if k in ("since", "seen", "cursor"):
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

    def call(url, body, timeout=None):
        try:
            r = s.post(url, data=json.dumps(body), headers={"Content-Type": "application/json"},
                       timeout=(CONNECT_TIMEOUT_S, timeout or READ_TIMEOUT_S), allow_redirects=True)
        except requests.Timeout:
            raise ProxyError("engine_timeout", 504)
        except requests.RequestException:
            raise ProxyError("engine_unreachable", 502)
        if r.status_code != 200:
            raise ProxyError("engine_bad_response", 502)
        # QA round 3 (B1): after a slow redirect the POST can end as a GET on /exec, which is doGet() -> a bare
        # {"ok":true} with no data. The real answer to a doPost always comes from the googleusercontent echo URL.
        if getattr(r, "request", None) is not None and r.request.method == "GET" and urlparse(r.url).path.endswith("/exec"):
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

    call.accepts_timeout = True
    return call


# ---------- reply schemas (QA round 3, B1) ----------
# Every engine reply is checked against the shape its fn must have BEFORE anything uses or caches it. A bare
# {"ok":true} (doGet) once rendered "no tickets" over ~280 open ones, cached empty knowledge, and would have shown
# "sent" for a send that never happened. An invalid reply is treated exactly like Google's HTML page.
LEGIT_BARE = frozenset(("apiMarkHandled", "apiClose", "apiNote", "apiAutoReplyReview"))   # their real reply IS {ok:true}


def _tid_ok(r, key, tid):
    t = r.get(key)
    return isinstance(t, dict) and t.get("id") == tid


SCHEMAS = {
    "apiBoot": lambda r, a: isinstance(r.get("tickets"), list) and isinstance(r.get("counts"), dict),
    "apiChanges": lambda r, a: isinstance(r.get("tickets"), list) and "version" in r,
    "apiTicket": lambda r, a: _tid_ok(r, "ticket", a.get("id")),
    "apiTicketFull": lambda r, a: _tid_ok(r, "ticket", a.get("id")) and isinstance(r.get("extras"), dict),
    "apiTicketLite": lambda r, a: (isinstance(r.get("v"), int) and isinstance(r.get("changed"), bool)
                                   and (r["changed"] is False or isinstance(r.get("newMessages"), list))),
    "apiDayStats": lambda r, a: isinstance(r.get("received"), dict) and isinstance(r.get("answered"), dict),
    "apiTicketExtras": lambda r, a: isinstance(r.get("extras"), dict) and r.get("id") == a.get("id"),
    "apiTickets": lambda r, a: isinstance(r.get("tickets"), list),
    "apiSearch": lambda r, a: isinstance(r.get("tickets"), list),
    "apiStatus": lambda r, a: isinstance(r.get("counts"), dict) or "dryRun" in r,
    "apiKnowledge": lambda r, a: (bool(str(r.get("knowledge") or "").strip()) or bool(str(r.get("ownerKnowledge") or "").strip())
                                  or bool(r.get("policy"))),
    "apiCustomerLookup": lambda r, a: isinstance(r.get("orders"), list) or isinstance(r.get("tickets"), list),
    "apiAutoReplyList": lambda r, a: isinstance(r.get("items"), list),
    "apiAutoCancelList": lambda r, a: isinstance(r.get("items"), list),
    "apiSettings": lambda r, a: isinstance(r.get("settings"), dict) if a.get("action") == "get" else ("key" in r or "to" in r),
    # A ticket id alone is not delivery evidence; sent and queued are distinct outcomes.
    "apiSend": lambda r, a: (r.get("sent") is True) != (r.get("queued") is True),
    "apiSaveDraft": lambda r, a: "problem" in r,
    "apiKachingCancel": lambda r, a: "status" in r or "message" in r,
    "apiAutoCancelApprove": lambda r, a: r.get("id") == a.get("id") or "state" in r,
    "apiAutoCancelReject": lambda r, a: r.get("id") == a.get("id"),
    "apiWaTakeOver": lambda r, a: r.get("id") == a.get("id") or "status" in r,
}


# Brands whose engine has been seen echoing rid/fn. From then on a reply WITHOUT the echo is not an answer (QA round 4:
# ~10% of calls came back as a 404 page, or a POST turned into GET -> {ok:false, error:'get_not_supported'}, no rid).
# Per brand so a brand whose engine is not redeployed yet keeps working on the schema check alone.
ECHO_SEEN = set()


def reply_problem(fn, args, rid, r, brand=None):
    """None when the reply may be used, else a short reason (logged, never shown)."""
    if not isinstance(r, dict) or "ok" not in r:
        return "no ok field"
    if r.get("error") == "get_not_supported":
        return "a GET reached the engine (the POST was lost on the redirect)"
    if "rid" in r or "fn" in r:
        if r.get("rid") != rid:
            return "rid mismatch"                   # a reply to ANOTHER call
        if r.get("fn") != fn:
            return "fn mismatch"
        if brand and brand not in ECHO_SEEN:
            ECHO_SEEN.add(brand)
            log.warning("engine %s echoes rid/fn: replies without the echo are rejected from now on", brand)
    elif brand in ECHO_SEEN:
        return "no rid/fn echo"                     # this engine always echoes: an answer without it is not ours
    if r.get("ok") is not True:
        if r.get("ok") is False and isinstance(r.get("error"), str) and r["error"]:
            return None
        if fn == "apiKachingCancel" and r.get("ok") is False and isinstance(r.get("message"), str):
            return None                             # the gate's refusal: {ok:false, status, message}
        return "refusal without an error code"
    check = SCHEMAS.get(fn)
    if check is not None:
        return None if check(r, args) else "reply does not match the %s schema" % fn
    if fn in LEGIT_BARE:
        return None                                 # verified by the transport (no doGet) and, once echoed, by rid
    return None


# ---------- lost write replies (QA round 4) ----------
WRITE_UNKNOWN_CODES = ("engine_bad_response", "engine_timeout", "engine_unreachable")
RESULT_POLL_DELAYS_S = (1.0, 2.0, 3.0, 4.0, 5.0)        # ~15 s in total
RESEND_MIN_AGE_S = 40.0      # QA round 5: never resend while the original may still be running inside Apps Script
ALREADY_CODES = ("already_handled", "already_sent", "already")


def _result_lookup(engines, transport, secret, user, brand, rid, lang):
    """('found', reply) | ('missing', None) | ('unsupported', None) | ('error', None)."""
    st, out = call(engines, transport, secret, user, brand, "apiResult", {"rid": rid}, lang, internal=True, retry=False)
    if out.get("ok") is True:
        stored = out.get("reply") if isinstance(out.get("reply"), dict) else out.get("result")
        if isinstance(stored, dict):
            return "found", stored
        if out.get("found") is False or out.get("pending"):
            return "missing", None
        return "error", None
    err = out.get("error")
    if err in ("not_found", "no_result", "unknown_rid", "result_not_found", "pending"):
        return "missing", None
    if err == "rid_reuse":
        return "error", None                        # same rid, different call: never treat as an answer
    if err in ("unauthorized", "forbidden_fn", "unknown_fn", "bad_fn"):
        return "unsupported", None                  # an engine without apiResult answers like any unknown fn
    return "error", None


def _effect_visible(engines, transport, secret, user, brand, fn, clean, lang):
    """Read the ticket: did THIS user's write already take effect? Returns a reply to use, or None."""
    if fn not in ("apiSend", "apiMarkHandled", "apiClose") or not clean.get("id"):
        return None
    st, out = call(engines, transport, secret, user, brand, "apiTicket", {"id": clean["id"]}, lang, internal=True, retry=False)
    t = out.get("ticket") if out.get("ok") else None
    if not isinstance(t, dict) or t.get("handled_by") != user.get("username"):
        return None
    if fn == "apiSend":
        # Closing a ticket is not sending. Likewise this user's previous reply is
        # not proof that the CURRENT text was delivered after a lost response.
        channel = t.get("channel") or clean.get("_channel") or "email"
        field = "wa_out" if channel == "whatsapp" else "draft_text"
        if not isinstance(clean.get("text"), str) or not clean["text"].strip() or t.get(field) != clean["text"]:
            return None
        if channel == "whatsapp":
            state = str(t.get("wa_send") or "").split(":", 1)[0]
            if state == "sent":
                return {"ok": True, "sent": True, "recovered": "ticket"}
            if state in ("pending", "claimed"):
                return {"ok": True, "queued": True, "recovered": "ticket"}
        elif t.get("status") == "sent":
            return {"ok": True, "sent": True, "recovered": "ticket"}
    elif t.get("status") == "done":
        return {"ok": True, "recovered": "ticket"}
    return None


def resolve_write(engines, transport, secret, user, brand, fn, clean, lang, rid, token, url, gate_, bg, started=None):
    """The reply to a write was lost (HTML page, GET turned from POST, timeout). The engine stores the final reply of
    every write by rid and treats a repeated rid as the same call. So: ask for the stored reply; if it never appears,
    send the SAME call with the SAME rid once (idempotent); if that is lost too, say so plainly — never "refused"."""
    t0 = _clock()
    started = started if started is not None else t0
    supported = None
    delays = list(RESULT_POLL_DELAYS_S)
    while _clock() - started + sum(delays) < RESEND_MIN_AGE_S:
        delays.append(5.0)                          # keep asking until the original cannot still be running
    for delay in delays:
        _sleep(delay)
        state, stored = _result_lookup(engines, transport, secret, user, brand, rid, lang)
        if state == "unsupported":
            supported = False
            break
        supported = True
        if state == "found":
            why = reply_problem(fn, clean, rid, stored, None)
            if not why:
                log.warning("engine %s %s reply recovered via apiResult after %d ms", brand, fn, int((_clock() - t0) * 1000))
                out = localize(fn, stored, lang)
                out["recovered"] = "apiResult"
                return 200, out
    seen = _effect_visible(engines, transport, secret, user, brand, fn, clean, lang)
    if seen:
        log.warning("engine %s %s outcome read from the ticket (already done by this user)", brand, fn)
        return 200, localize(fn, seen, lang)
    if supported is False:
        log.warning("engine %s %s reply lost; engine has no apiResult yet", brand, fn)
        return 502, {"ok": False, "error": "engine_bad_response", "msg": messages.proxy_msg("engine_bad_response_write", lang),
                     "refresh": True}
    if fn == "apiSend" and clean.get("_channel") == "whatsapp":
        pass                                        # a WhatsApp send is NEVER resent: a second queue entry is a second message
    # not found: one resend with the same rid — the engine returns the stored reply or runs it exactly once
    elif gate_.acquire(bg):
        err = None
        try:
            resp = transport(url, {"fn": fn, "args": _wire(clean), "token": token, "rid": rid})
            if reply_problem(fn, clean, rid, resp, brand):
                err = "invalid"
        except ProxyError as x:
            err = x.code
        finally:
            gate_.release(bg, 0, None if err is None else "engine_bad_response")
        if err is None and resp.get("error") in ALREADY_CODES:
            seen = _effect_visible(engines, transport, secret, user, brand, fn, clean, lang)
            if seen:                                # "someone already handled it" — and that someone is us
                return 200, localize(fn, dict(seen, recovered="resend"), lang)
        if err is None:
            log.warning("engine %s %s resolved by a same-rid resend after %d ms", brand, fn, int((_clock() - t0) * 1000))
            out = localize(fn, resp, lang)
            out["recovered"] = "resend"
            return 200, out
    log.warning("engine %s %s outcome unknown after apiResult + resend (%d ms)", brand, fn, int((_clock() - t0) * 1000))
    return 502, {"ok": False, "error": "write_unknown", "msg": messages.proxy_msg("write_unknown", lang), "refresh": True}


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


CLIENT_RID_RE = re.compile(r"^[A-Za-z0-9_.:-]{16,64}$")


def _attempt(g, bg, transport, url, wire, kw, fn, clean, rid, brand, hedge=False):
    """One engine round-trip on a slot the caller already holds -> (reply, ProxyError|None, seconds). With hedge=True a
    second identical request (same rid) starts after HEDGE_AFTER_S if a shared slot is free; the first VALID answer wins,
    the other finishes in the background and gives its slot back when done (so the cap always counts it)."""
    def one():
        t0 = _clock()
        err, resp = None, None
        try:
            resp = transport(url, wire, **kw)
            why = reply_problem(fn, clean, rid, resp, brand)
            if why:
                log.warning("engine %s %s invalid reply: %s (keys: %s)", brand, fn, why, ",".join(sorted(resp)[:8]) if isinstance(resp, dict) else type(resp).__name__)
                raise ProxyError("engine_bad_response", 502)
        except ProxyError as x:
            err = x
        finally:
            took = _clock() - t0
            g.release(bg, took, err.code if err else None,
                      resp.get("serverMs") if err is None and isinstance(resp, dict) else None)
        return resp, err, took
    if not hedge:
        return one()
    import queue as _q
    box = _q.Queue()
    t_start = _clock()
    threading.Thread(target=lambda: box.put(one()), daemon=True).start()
    try:
        return box.get(timeout=HEDGE_AFTER_S)
    except _q.Empty:
        pass
    n = 1
    if g.try_hedge():
        n = 2
        log.warning("engine %s %s no answer after %.0f s: hedged with a second request", brand, fn, HEDGE_AFTER_S)
        threading.Thread(target=lambda: box.put(one()), daemon=True).start()
    first = None
    for _ in range(n):
        res = box.get()
        if res[1] is None:
            return res[0], None, _clock() - t_start
        first = first or res
    return first[0], first[1], _clock() - t_start


def call(engines, transport, secret, user, brand, fn, args, lang, now=None, internal=False, retry=True, bg=False, rid=None,
         top=False):
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
    if fn == "apiSend" and isinstance(args, dict) and args.get("channel") == "whatsapp":
        clean["_channel"] = "whatsapp"          # local only: stripped before the engine sees it
    try:
        token = security.mint_engine_token(secret, user["username"], role, [brand], user.get("lang", "he"), now=now)
    except ValueError:
        return 500, {"ok": False, "error": "server_misconfigured", "msg": messages.proxy_msg("server_misconfigured", lang)}
    started = _clock()
    # background sends (Owner, 2026-10-05): the browser makes the rid so a reloaded page can still ask apiResult about it
    rid = rid if (isinstance(rid, str) and CLIENT_RID_RE.match(rid)) else secrets.token_hex(8)
    delays = READ_RETRY_DELAYS_S if (retry and is_read(fn, clean)) else ()
    attempt = 0
    g = gate(brand)
    while True:
        attempt += 1
        w0 = _clock()
        if not g.acquire(bg, not bg and (fn == "apiSend" or (top and is_read(fn, clean)))):
            if bg:
                return 200, {"ok": False, "error": "dropped", "background": True}       # quietly: the next tick retries
            log.warning("engine %s %s busy: no slot within %.0f s (in flight %d)", brand, fn, GATE_WAIT_S, g.inflight)
            return 503, {"ok": False, "error": "busy", "msg": messages.proxy_msg("busy", lang)}
        waited = _clock() - w0
        if waited > 1:
            log.warning("engine %s %s waited %.1f s for a slot", brand, fn, waited)
        fast = fn in FAST_READS and is_read(fn, clean)
        kw = {"timeout": FAST_READ_TIMEOUT_S} if fast and getattr(transport, "accepts_timeout", False) else {}
        wire = {"fn": fn, "args": _wire(clean), "token": token, "rid": rid}
        resp, err, took = _attempt(g, bg, transport, url, wire, kw, fn, clean, rid, brand,
                                   hedge=top and fast and not bg)
        if err is None:
            break
        e = err
        if e:
            # timing line: brand, fn, attempt, duration, outcome — never args, never customer data
            log.warning("engine %s %s attempt=%d ms=%d -> %s", brand, fn, attempt, int(took * 1000), e.code)
            if (fast and retry and not bg and attempt == 1
                    and e.code in ("engine_timeout", "engine_bad_response", "engine_unreachable")
                    and (_clock() - started) + FAST_READ_TIMEOUT_S <= FAST_RETRY_BUDGET_S):
                continue                                    # at once, same rid: the front door, not the engine, failed
            if (not fast and e.code == "engine_bad_response" and attempt <= len(delays) and took < RETRY_FAST_FAIL_S
                    and (_clock() - started) + delays[attempt - 1] < RETRY_TOTAL_BUDGET_S):
                _sleep(delays[attempt - 1])
                continue
            code = e.code
            if not is_read(fn, clean) and fn != "apiResult" and code in WRITE_UNKNOWN_CODES:
                # the write may well have run: find out instead of guessing (QA round 4)
                return resolve_write(engines, transport, secret, user, brand, fn, clean, lang, rid, token, url, g, bg, started)
            return e.http, {"ok": False, "error": e.code, "msg": messages.proxy_msg(code, lang)}
    if attempt > 1:
        log.warning("engine %s %s recovered on attempt=%d total_ms=%d", brand, fn, attempt, int((_clock() - started) * 1000))
    if fn == "apiSend" and isinstance(resp, dict) and resp.get("ok") is False and resp.get("error") in ALREADY_CODES:
        # a repeat click after an unconfirmed send: if the ticket shows OUR send, say "sent", not "someone else"
        seen = _effect_visible(engines, transport, secret, user, brand, fn, clean, lang)
        if seen:
            resp = dict(seen, already=True)
    out = localize(fn, resp, lang)
    out["_ms"] = int((_clock() - started) * 1000)
    if attempt > 1:
        out["_attempts"] = attempt
    return 200, out
