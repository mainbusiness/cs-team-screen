"""
ticket_cache.py — the Render-side cache that makes the screen instant whatever the engine's latency is.

Measured before this layer (live, 2026-10-05): Render answers in 0.2-0.8 s, apiBoot 2-3 s, opening a ticket
(apiTicket + apiTicketExtras) 17-18 s. The engine is being made faster; this layer makes it not matter.

What it does
 - Per brand: the ticket list (apiBoot) and a full ticket ({ticket, extras}) for every ticket opened or prefetched.
 - Stale-while-revalidate: a read is served from memory at once; the browser then asks for a revalidation and
   gets the fresh copy when the engine answers. Old entries also refresh in the background.
 - Every write made through the screen patches (draft, status) or invalidates (note, cancel, refusals) the
   ticket at once, and patches the list row and the counts.
 - Prefetch: the first 15 tickets of the visible tab are warmed in the background, at most 3 engine calls at a
   time across the whole process (Apps Script is slow and lock-sensitive).
 - Polling: apiChanges {since} when the engine has it, else apiBoot plus a diff; only changed rows go back.
 - apiTicketFull when the engine has it; otherwise apiTicket + apiTicketExtras IN PARALLEL.

Safety model
 - Every key starts with the brand; brand and ticket id are regex-checked before they touch a path. The routes
   gate on the session user holding the brand (and a work role for tickets), exactly like the proxy, so a cached
   entry is only ever served to someone who could have fetched it from the engine.
 - Per-user fields (user, role, lang) are stripped before a list is cached and re-applied per request.
 - The disk copy (warm restarts) lives under a 0700 directory on the private disk, files 0600, atomic writes,
   7-day horizon. Engine calls go through engine_proxy.call (internal=True), so tokens, brand forcing and the
   role table are the same as for every other call.
"""

import contextlib
import json
import os
import re
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from flask import g, jsonify, request

import engine_proxy
import messages
import security

BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
WORK_ROLES = ("agent", "admin")
PER_USER = ("user", "role", "lang")
LIST_TTL_S = 10            # older list -> served, and refreshed in the background
TICKET_TTL_S = 60          # older ticket -> served, and refreshed in the background
PREFETCH_MAX = 15
PREFETCH_FRESH_S = 120     # a prefetched ticket younger than this is not fetched again
DISK_HORIZON_S = 7 * 86400
MAX_TICKETS_PER_BRAND = 3000
UNSUPPORTED_RETRY_S = 600  # an engine without apiTicketFull / apiChanges is asked again after 10 min


def timing(name, dur_ms=None, desc=None):
    """Server-Timing entry for this request (no-op outside a request)."""
    try:
        g.timings.append((name, dur_ms, desc))
    except (AttributeError, RuntimeError):
        pass


class TicketCache:
    def __init__(self, root, engines, transport, secret_getter, workers=3, clock=time.time):
        self.root, self.engines, self.transport, self.secret = root, engines, transport, secret_getter
        self.clock = clock
        os.makedirs(root, mode=0o700, exist_ok=True)
        os.chmod(root, 0o700)
        self.mem = {}                    # brand -> {"boot": entry|None, "t": {id: entry}}
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cs-cache")
        # THE cap (Codex 2026-10-05): every engine call made for background work — including both halves of the
        # parallel fallback — takes one of these slots. A user's own click never waits behind prefetch.
        self.bg_slots = threading.BoundedSemaphore(workers)
        self._tl = threading.local()
        self.inflight = {}               # key -> Future (dedupe: one engine fetch per key at a time)
        self.no_full = {}
        self.no_changes = {}
        self.bg = []                     # background futures (tests drain them)

    # ---------- plumbing ----------

    def _call(self, user, brand, fn, args, bg=None):
        bg = getattr(self._tl, "bg", False) if bg is None else bg
        t0 = time.perf_counter()
        if bg:
            with self.bg_slots:
                _, out = engine_proxy.call(self.engines, self.transport, self.secret(), user, brand, fn, args,
                                           user.get("lang", "he"), internal=True)
        else:
            _, out = engine_proxy.call(self.engines, self.transport, self.secret(), user, brand, fn, args,
                                       user.get("lang", "he"), internal=True)
        timing("engine", (time.perf_counter() - t0) * 1000, fn)
        if isinstance(out.get("serverMs"), (int, float)):
            timing("gas", float(out["serverMs"]), fn)      # time spent inside Apps Script (final engine shape)
        return out

    def _bucket(self, brand):
        if not BRAND_RE.match(brand):
            raise ValueError("bad brand")
        with self.lock:
            return self.mem.setdefault(brand, {"boot": None, "t": {}})

    def _dir(self, brand, *sub):
        p = os.path.join(self.root, brand, *sub)
        if not os.path.isdir(p):
            os.makedirs(p, mode=0o700, exist_ok=True)
            for d in (os.path.join(self.root, brand), p):
                with contextlib.suppress(OSError):
                    os.chmod(d, 0o700)
        return p

    def _write(self, path, obj):
        d = os.path.dirname(path)
        try:
            fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        except OSError:
            pass                         # the disk copy is only for warm restarts

    def _read(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                e = json.load(f)
        except (OSError, ValueError):
            return None
        return e if self.clock() - float(e.get("at", 0)) < DISK_HORIZON_S else None

    def _once(self, key, fn):
        """Run fn once per key at a time; concurrent callers wait for the same result."""
        with self.lock:
            fut = self.inflight.get(key)
            owner = fut is None
            if owner:
                fut = Future()
                self.inflight[key] = fut
        if not owner:
            return fut.result(timeout=90)
        try:
            res = fn()
            fut.set_result(res)
            return res
        except BaseException as e:
            fut.set_exception(e)
            raise
        finally:
            with self.lock:
                self.inflight.pop(key, None)

    def _background(self, key, fn):
        with self.lock:
            if key in self.inflight:
                return False
        def job():
            self._tl.bg = True
            try:
                with contextlib.suppress(Exception):
                    self._once(key, fn)
            finally:
                self._tl.bg = False
        self.bg.append(self.pool.submit(job))
        self.bg = [f for f in self.bg if not f.done()]
        return True

    def drain(self, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            pending = [f for f in list(self.bg) if not f.done()]
            if not pending and not self.inflight:
                return
            time.sleep(0.01)

    # ---------- the list ----------

    def _store_boot(self, brand, data):
        clean = {k: v for k, v in data.items() if k not in PER_USER and not k.startswith("_") and k != "msg"}
        e = {"data": clean, "at": self.clock()}
        with self.lock:
            self._bucket(brand)["boot"] = e
        self._write(os.path.join(self._dir(brand), "boot.json"), e)
        return e

    def _boot_entry(self, brand):
        b = self._bucket(brand)
        e = b["boot"]
        if e is None:
            e = self._read(os.path.join(self.root, brand, "boot.json"))
            if e:
                with self.lock:
                    b["boot"] = e
        return e

    def cached_rows(self, brand):
        """Public read of the cached summary rows of ONE brand (callers gate the user on that brand first).
        Every work-role user of a brand already sees the whole list via apiBoot, so this is not wider than that."""
        e = self._boot_entry(brand)
        return {r.get("id"): r for r in ((e or {}).get("data", {}).get("tickets") or []) if isinstance(r, dict)}

    def _fetch_boot(self, user, brand):
        out = self._call(user, brand, "apiBoot", {})
        if out.get("ok"):
            self._store_boot(brand, out)
        return out

    @staticmethod
    def _for_user(data, user):
        d = dict(data)
        d["user"] = user["username"]
        try:
            d["role"] = security.engine_role(user.get("roles", []))
        except ValueError:
            d["role"] = None
        d["lang"] = user.get("lang", "he")
        return d

    def get_list(self, user, brand):
        e = self._boot_entry(brand)
        if e:
            age = self.clock() - e["at"]
            timing("cache", None, "list-hit")
            if age > LIST_TTL_S:
                self._background(("boot", brand), lambda: self._fetch_boot(user, brand))
            out = self._for_user(e["data"], user)
            out["ok"] = True
            out["cache"] = {"hit": True, "age_s": round(age, 1)}
            return 200, out
        out = self._once(("boot", brand), lambda: self._fetch_boot(user, brand))
        if not out.get("ok"):
            return 200, out
        out = self._for_user({k: v for k, v in out.items() if k not in PER_USER}, user)
        out["cache"] = {"hit": False, "age_s": 0}
        return 200, out

    @staticmethod
    def _apply_rows(data, rows, removed=()):
        """Merge changed summary rows into a cached list, keeping the counts right."""
        tickets = data.setdefault("tickets", [])
        counts = data.setdefault("counts", {})
        index = {t.get("id"): i for i, t in enumerate(tickets)}
        def bump(st, n):
            if st:
                counts[st] = max(0, int(counts.get(st, 0)) + n)
        for rid in removed:
            if rid in index:
                bump(tickets[index[rid]].get("status"), -1)
                tickets[index[rid]] = None
        for r in rows:
            if not isinstance(r, dict) or not ID_RE.match(str(r.get("id", ""))):
                continue
            gone = r.get("archived") or r.get("removed") or r.get("deleted")
            i = index.get(r["id"])
            if i is not None and tickets[i] is not None:
                old = tickets[i]
                if old.get("status") != r.get("status") or gone:
                    bump(old.get("status"), -1)
                    if not gone:
                        bump(r.get("status"), +1)
                tickets[i] = None if gone else dict(old, **r)
            elif not gone:
                tickets.append(dict(r))
                index[r["id"]] = len(tickets) - 1
                bump(r.get("status"), +1)
        data["tickets"] = [t for t in tickets if t is not None]
        return data

    @staticmethod
    def _int(v):
        if isinstance(v, bool):
            return None
        try:
            i = int(v)
        except (TypeError, ValueError):
            return None
        return i if i >= 0 else None

    def changes(self, user, brand, since):
        """Final engine shape: apiChanges {since:int} -> {version, tickets, removed} | {version, reset:true, tickets:<all>}."""
        e = self._boot_entry(brand)
        now = self.clock()
        try:
            work = security.engine_role(user.get("roles", [])) in WORK_ROLES
        except ValueError:
            work = False
        since_i = self._int(since)
        if since_i is None and e:
            since_i = self._int(e["data"].get("version"))
        if e and work and since_i is not None and now > self.no_changes.get(brand, 0):
            out = self._call(user, brand, "apiChanges", {"since": since_i})
            if out.get("ok") and isinstance(out.get("tickets"), list) and not out.get("reset"):
                rows = out["tickets"]
                removed = [i for i in (out.get("removed") or []) if isinstance(i, str)]
                with self.lock:
                    data = self._apply_rows(json.loads(json.dumps(e["data"])), rows, removed)
                    data["version"] = out.get("version", data.get("version"))
                    data["serverTime"] = out.get("serverTime", data.get("serverTime"))
                    self._bucket(brand)["boot"] = {"data": data, "at": now}
                self._write(os.path.join(self._dir(brand), "boot.json"), {"data": data, "at": now})
                self._stale([r.get("id") for r in rows if isinstance(r, dict)] + removed, brand)
                return 200, {"ok": True, "version": data.get("version"), "changed": rows, "removed": removed,
                             "counts": data.get("counts", {}), "serverTime": data.get("serverTime"), "via": "apiChanges"}
            lacks_changes = out.get("error") in ("unauthorized", "forbidden_fn")
            if lacks_changes:
                pass                                                         # recorded below, only if apiBoot then works
            elif not out.get("ok") and out.get("error") not in ("bad_since",):
                return 200, out
            # reset:true (our version is too old) or bad_since -> one full apiBoot below, so the counts are right
        else:
            lacks_changes = False
        # fallback: a full apiBoot, diffed here so the browser still patches only what changed
        old = {t.get("id"): t for t in (e["data"].get("tickets") or [])} if e else {}
        out = self._once(("boot", brand), lambda: self._fetch_boot(user, brand))
        if not out.get("ok"):
            return 200, out
        if lacks_changes:
            # "unauthorized" is also what Api.gs says for an unknown fn; apiBoot just worked with the same kind of
            # token, so the engine really lacks apiChanges (Codex 2026-10-05: never disable on a plain auth failure)
            self.no_changes[brand] = now + UNSUPPORTED_RETRY_S
        new = {t.get("id"): t for t in (out.get("tickets") or [])}
        changed = [t for i, t in new.items() if old.get(i) != t]
        removed = [i for i in old if i not in new]
        self._stale([t.get("id") for t in changed], brand)
        return 200, {"ok": True, "version": out.get("version") or out.get("serverTime"), "changed": changed, "removed": removed,
                     "counts": out.get("counts", {}), "serverTime": out.get("serverTime"), "via": "apiBoot"}

    # ---------- full tickets ----------

    def _fetch_full(self, user, brand, tid, fresh=False):
        """({ticket, extras, snapshotAt}, None) or (None, engine error). fresh=True asks the engine to re-read the
        store and Kaching (rate-limited there: 30/10 min), so only an explicit refresh click sends it."""
        probed = False
        if self.clock() > self.no_full.get(brand, 0):
            out = self._call(user, brand, "apiTicketFull", {"id": tid, "fresh": True} if fresh else {"id": tid})
            if out.get("ok") and isinstance(out.get("ticket"), dict):
                ex = out.get("extras") if isinstance(out.get("extras"), dict) else {}
                return {"ticket": out["ticket"], "extras": ex, "snapshotAt": out.get("snapshotAt") or ex.get("snapshotAt")}, None
            if out.get("ok") is False and out.get("error") not in ("unauthorized", "forbidden_fn"):
                return None, out                                             # a real answer: not_found, busy, ...
            probed = True
        bg = getattr(self._tl, "bg", False)
        with ThreadPoolExecutor(max_workers=2) as ex:                        # never one after the other
            fa = ex.submit(self._call, user, brand, "apiTicket", {"id": tid}, bg)     # bg -> both halves take a slot
            fb = ex.submit(self._call, user, brand, "apiTicketExtras", {"id": tid}, bg)
            a, b = fa.result(), fb.result()
        if not a.get("ok"):
            return None, a
        if probed:                                                           # the pair works, so the engine lacks apiTicketFull
            self.no_full[brand] = self.clock() + UNSUPPORTED_RETRY_S
        return {"ticket": a.get("ticket") or {}, "extras": (b.get("extras") or {}) if b.get("ok") else {},
                "snapshotAt": None, "extrasError": None if b.get("ok") else (b.get("msg") or b.get("error"))}, None

    def _store_full(self, brand, tid, full):
        e = {"full": full, "at": self.clock(), "stale": False}
        with self.lock:
            t = self._bucket(brand)["t"]
            t[tid] = e
            if len(t) > MAX_TICKETS_PER_BRAND:
                for k, _ in sorted(t.items(), key=lambda kv: kv[1]["at"])[: len(t) - MAX_TICKETS_PER_BRAND]:
                    t.pop(k, None)
        self._write(os.path.join(self._dir(brand, "t"), tid + ".json"), e)
        return e

    def _entry(self, brand, tid):
        b = self._bucket(brand)
        with self.lock:
            e = b["t"].get(tid)
        if e is None:
            e = self._read(os.path.join(self.root, brand, "t", tid + ".json"))
            if e:
                with self.lock:
                    b["t"][tid] = e
        return e

    def _refresh(self, user, brand, tid, fresh=False):
        full, err = self._fetch_full(user, brand, tid, fresh)
        if full:
            self._store_full(brand, tid, full)
        elif err and err.get("error") == "not_found":
            with self.lock:
                self._bucket(brand)["t"].pop(tid, None)
        return full, err

    def get_ticket(self, user, brand, tid, revalidate=False, fresh=False):
        if not ID_RE.match(tid):
            return None, {"ok": False, "error": "bad_id"}, {}
        if not revalidate:
            e = self._entry(brand, tid)
            if e:
                age = self.clock() - e["at"]
                timing("cache", None, "ticket-hit")
                if e.get("stale") or age > TICKET_TTL_S:
                    self._background(("t", brand, tid), lambda: self._refresh(user, brand, tid))
                return e["full"], None, {"hit": True, "age_s": round(age, 1), "stale": bool(e.get("stale"))}
        full, err = self._once(("t", brand, tid), lambda: self._refresh(user, brand, tid, fresh))
        timing("cache", None, "ticket-miss" if not revalidate else "ticket-revalidate")
        return full, err, {"hit": False, "age_s": 0, "stale": False}

    def prefetch(self, user, brand, ids):
        n = 0
        for tid in ids[:PREFETCH_MAX]:
            if not isinstance(tid, str) or not ID_RE.match(tid):
                continue
            e = self._entry(brand, tid)
            if e and not e.get("stale") and self.clock() - e["at"] < PREFETCH_FRESH_S:
                continue
            if self._background(("t", brand, tid), lambda t=tid: self._refresh(user, brand, t)):
                n += 1
        return n

    def _stale(self, ids, brand):
        with self.lock:
            t = self._bucket(brand)["t"]
            for i in ids:
                if i in t:
                    t[i]["stale"] = True

    # ---------- writes made through the screen ----------

    def after_write(self, user, brand, fn, args, out):
        tid = args.get("id") if isinstance(args, dict) else None
        if not isinstance(tid, str) or not ID_RE.match(tid) or not BRAND_RE.match(brand):
            return
        ok = bool(out.get("ok"))
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        patch = None
        if ok and fn == "apiSaveDraft":
            patch = {"draft_text": args.get("text", "")}
        elif ok and fn == "apiSend":
            patch = {"draft_text": args.get("text", ""), "handled_by": user["username"], "handled_at": now_iso}
            if not out.get("queued"):
                patch["status"] = "sent"
        elif ok and fn == "apiAutoReplyReview" and args.get("verdict") == "problem":
            patch = {"status": "action"}                 # "⚠ problem" reopens the ticket (the engine confirms on revalidate)
        elif ok and fn in ("apiMarkHandled", "apiClose"):
            patch = {"status": "done", "handled_by": user["username"], "handled_at": now_iso}
        with self.lock:
            e = self._bucket(brand)["t"].get(tid)
            if e and patch:
                e["full"] = dict(e["full"], ticket=dict(e["full"].get("ticket") or {}, **patch))
                e["at"] = self.clock()                                       # patched now (Codex 2026-10-05)
            if e and (fn != "apiSaveDraft" or not ok):
                e["stale"] = True            # anything the engine adds (notes line, cancelled ids, refusals) comes on revalidate
            b = self._bucket(brand)["boot"]
            if b and patch:
                row_patch = {k: v for k, v in patch.items() if k != "draft_text"}
                if row_patch:
                    b["at"] = self.clock()
                    self._apply_rows(b["data"], [dict(next((r for r in b["data"].get("tickets", []) if r.get("id") == tid), {"id": tid}), **row_patch)])
        if e:
            self._write(os.path.join(self._dir(brand, "t"), tid + ".json"), e)
        if fn != "apiSaveDraft" or not ok:
            self._background(("t", brand, tid), lambda: self._refresh(user, brand, tid))


WRITE_FNS = ("apiSaveDraft", "apiSend", "apiMarkHandled", "apiClose", "apiNote", "apiKachingCancel",
             "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyReview")


def register(app, d):
    """d: api_user, json_error, engines, cache (TicketCache)."""
    cache = d["cache"]

    def gate(brand, work):
        u, err = d["api_user"]()
        if err:
            return None, err
        lang = u.get("lang", "he")
        try:
            role = security.engine_role(u.get("roles", []))
        except ValueError:
            role = None
        if work and role not in WORK_ROLES:
            return None, d["json_error"]("forbidden_role", 403, lang)
        if not BRAND_RE.match(brand) or brand not in u.get("brands", []):
            return None, d["json_error"]("forbidden_brand", 403, lang)
        if brand not in d["engines"]:
            return None, d["json_error"]("brand_not_connected", 503, lang)
        return u, None

    def localized(out, lang, fn):
        if not out.get("ok") and "msg" not in out:
            out = dict(out, msg=messages.engine_error_msg(out, fn, lang))
        return out

    @app.post("/api/<brand>/list")
    def cached_list(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=False)
        if err:
            return err
        st, out = cache.get_list(u, brand)
        return jsonify(localized(out, u.get("lang", "he"), "apiBoot")), st

    @app.post("/api/<brand>/changes")
    def cached_changes(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=False)
        if err:
            return err
        since = (request.get_json(silent=True) or {}).get("since")
        st, out = cache.changes(u, brand, since if isinstance(since, (str, int, float)) else None)
        return jsonify(localized(out, u.get("lang", "he"), "apiBoot")), st

    @app.post("/api/<brand>/ticket")
    def cached_ticket(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        tid = body.get("id")
        if not isinstance(tid, str) or not ID_RE.match(tid):
            return d["json_error"]("bad_request", 400, u.get("lang", "he"))
        fresh = body.get("fresh") is True
        full, e, meta = cache.get_ticket(u, brand, tid, revalidate=body.get("revalidate") is True or fresh, fresh=fresh)
        if not full:
            return jsonify(localized(dict(e or {"ok": False, "error": "server_error"}), u.get("lang", "he"), "apiTicket")), 200
        return jsonify({"ok": True, "ticket": full.get("ticket"), "extras": full.get("extras") or {}, "snapshotAt": full.get("snapshotAt"),
                        "extrasErr": full.get("extrasError"), "cache": meta})

    @app.post("/api/<brand>/prefetch")
    def cached_prefetch(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        ids = (request.get_json(silent=True) or {}).get("ids")
        if not isinstance(ids, list):
            return d["json_error"]("bad_request", 400, u.get("lang", "he"))
        return jsonify({"ok": True, "queued": cache.prefetch(u, brand, ids)})
