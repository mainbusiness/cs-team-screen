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
from concurrent.futures import TimeoutError as FutureTimeout

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
UNSUPPORTED_RETRY_S = 600
# P0 speed (Owner, 2026-10-05). The brand's change feed (apiChanges) is SHARED: one engine call per brand per window, whoever
# asks; every client gets its own delta from a log kept here. A cached ticket the feed has not marked changed is
# "confirmed" — it is shown without another engine round-trip.
CHANGES_SHARED_S = 4.0     # /changes and /watch reuse a feed read younger than this
CONFIRM_S = 12.0           # a copy is confirmed fresh if the engine (ticket read or change feed) vouched for it this recently
WATCH_WAIT_S = 10.0        # /watch waits at most this long for the shared feed read
WATCH_DIRECT_S = 20.0      # feed unreadable: the open ticket itself is re-read once its copy is older than this
CHLOG_MAX = 3000           # (version, id) pairs kept for client deltas; older clients get the whole list (reset)
WAIT_FOR_INFLIGHT_S = 90   # a request sharing another one's in-flight engine fetch waits at most this long  # an engine without apiTicketFull / apiChanges is asked again after 10 min


_collect = threading.local()   # a worker thread collects its timings here and the request thread re-emits them


def timing(name, dur_ms=None, desc=None):
    """Server-Timing entry for this request (collected on worker threads, no-op elsewhere)."""
    sink = getattr(_collect, "items", None)
    if sink is not None:
        sink.append((name, dur_ms, desc))
        return
    try:
        g.timings.append((name, dur_ms, desc))
    except (AttributeError, RuntimeError):
        pass


class TicketCache:
    def __init__(self, root, engines, transport, secret_getter, workers=6, clock=time.time):
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
        self.brand_bg = {}                           # brand -> semaphore(engine_proxy.GATE_BG_CAP): prefetch fan-out 2/brand
        self.fg_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="cs-open")   # interactive opens (capped wait)
        # the ticket on an agent's screen never waits for a thread behind other reads (Codex 2026-10-05)
        self.top_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="cs-top")
        self.inflight = {}               # key -> Future (dedupe: one engine fetch per key at a time)
        self.no_full = {}
        self.no_changes = {}
        self.bg = []                     # background futures (tests drain them)
        self.chlog = {}                  # brand -> {"floor": version, "items": [(version, id)]}: deltas for /changes
        self.changed_at = {}             # brand -> {id: when the feed last said it changed}
        self.feed = {}                   # brand -> {"v": feed version, "base_t": stale marks complete since, "ok_at": last read}

    # ---------- plumbing ----------

    def _call(self, user, brand, fn, args, bg=None, top=None):
        bg = getattr(self._tl, "bg", False) if bg is None else bg
        top = getattr(self._tl, "top", False) if top is None else top
        t0 = time.perf_counter()
        if bg:                                       # background: never retried, dropped by the brand gate under load
            with self.bg_slots:
                _, out = engine_proxy.call(self.engines, self.transport, self.secret(), user, brand, fn, args,
                                           user.get("lang", "he"), internal=True, retry=False, bg=True)
        else:
            _, out = engine_proxy.call(self.engines, self.transport, self.secret(), user, brand, fn, args,
                                       user.get("lang", "he"), internal=True, top=bool(top))
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

    def _once(self, key, fn, wait=WAIT_FOR_INFLIGHT_S):
        """Run fn once per key at a time; concurrent callers wait (at most `wait` s) for the same result."""
        with self.lock:
            fut = self.inflight.get(key)
            owner = fut is None
            if owner:
                fut = Future()
                self.inflight[key] = fut
        if not owner:
            try:
                return fut.result(timeout=wait)
            except FutureTimeout:
                # QA round 3: this waiter used to raise -> HTTP 500 on /list. Answer like an engine timeout instead.
                err = {"ok": False, "error": "engine_timeout"}
                return (None, err) if key and key[0] == "t" else err
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

    def _brand_sem(self, brand):
        with self.lock:
            s = self.brand_bg.get(brand)
            if s is None:
                s = self.brand_bg[brand] = threading.BoundedSemaphore(engine_proxy.GATE_BG_CAP)
            return s

    def _background(self, key, fn):
        with self.lock:
            if key in self.inflight or (key[0] == "t" and key + ("top",) in self.inflight):
                return False
        brand = key[1] if len(key) > 1 else ""
        if engine_proxy.gate(brand).tripped() and key[0] != "boot":    # breaker: leave the engine alone — except the list
            return False
        def job():
            self._tl.bg = True
            sem = self._brand_sem(brand)
            sem.acquire()                            # queue here (2 per brand), not at the engine
            try:
                if engine_proxy.gate(brand).tripped() and key[0] != "boot":
                    return
                with contextlib.suppress(Exception):
                    self._once(key, fn)
            finally:
                sem.release()
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
        e = {"data": clean, "at": self.clock(), "full_at": self.clock(), "synced_at": self.clock()}
        prev = self._boot_entry(brand)
        old = {t.get("id"): t for t in ((prev or {}).get("data", {}).get("tickets") or []) if isinstance(t, dict)}
        new = {t.get("id"): t for t in (clean.get("tickets") or []) if isinstance(t, dict)}
        moved = [i for i, t in new.items() if old.get(i) != t] + [i for i in old if i not in new]
        with self.lock:
            self._bucket(brand)["boot"] = e
            self._log(brand, self._int((prev or {}).get("data", {}).get("version")), self._int(clean.get("version")), moved)
        if prev:                                     # a first load has nothing to diff against (its copies predate the feed base)
            self._stale(moved, brand)
        self._write(os.path.join(self._dir(brand), "boot.json"), e)
        return e

    def _log(self, brand, prev_v, v, ids):
        """Record which list rows changed at version v (caller holds the lock). A jump we cannot describe resets the log:
        every client then gets the whole list once."""
        lg = self.chlog.get(brand)
        if v is None:
            self.chlog[brand] = {"floor": None, "items": []}
            return
        if lg is None or lg["floor"] is None or prev_v is None or v < prev_v or not (lg["floor"] <= prev_v):
            self.chlog[brand] = lg = {"floor": v, "items": []}
            return
        lg["items"].extend((v, i) for i in ids if isinstance(i, str))
        if len(lg["items"]) > CHLOG_MAX:
            cut = len(lg["items"]) - CHLOG_MAX
            lg["floor"] = max(lg["floor"], lg["items"][cut - 1][0])
            lg["items"] = [x for x in lg["items"][cut:] if x[0] > lg["floor"]]

    def _boot_entry(self, brand):
        b = self._bucket(brand)
        e = b["boot"]
        if e is None:
            e = self._read(os.path.join(self.root, brand, "boot.json"))
            if e and not (isinstance(e.get("data"), dict) and isinstance(e["data"].get("tickets"), list)
                          and isinstance(e["data"].get("counts"), dict)):
                e = None                                   # an invalid copy on disk is never served
            if e:
                with self.lock:
                    b["boot"] = e
        return e

    def cached_rows(self, brand):
        """Public read of the cached summary rows of ONE brand (callers gate the user on that brand first).
        Every work-role user of a brand already sees the whole list via apiBoot, so this is not wider than that."""
        e = self._boot_entry(brand)
        return {r.get("id"): r for r in ((e or {}).get("data", {}).get("tickets") or []) if isinstance(r, dict)}

    @staticmethod
    def _open_count(data):
        counts = (data or {}).get("counts") or {}
        return sum(int(counts.get(s, 0) or 0) for s in ("ready", "action", "health", "delay"))

    def synced_age(self, brand):
        e = self._boot_entry(brand)
        return None if not e else round(self.clock() - e.get("synced_at", e.get("full_at", e["at"])), 1)

    def _fetch_boot(self, user, brand):
        # QA round 5: the rozela list went 27 min stale — the breaker kept dropping every background refresh. The list
        # is the one call that must always get through: background priority while fresh, interactive once starved.
        e0 = self._boot_entry(brand)
        age = (self.clock() - e0.get("synced_at", e0.get("full_at", e0["at"]))) if e0 else 1e9
        starving = age > LIST_STARVE_S or engine_proxy.gate(brand).tripped()
        bg = getattr(self._tl, "bg", False) and not starving
        out = self._call(user, brand, "apiBoot", {}, bg)
        if out.get("ok"):
            prev = self._boot_entry(brand)
            if (prev and self._open_count(prev["data"]) >= 3 and not out.get("tickets") and self._open_count(out) == 0):
                # a list that suddenly says "nothing open" over many open tickets is a broken reply, not a fact
                engine_proxy.log.warning("engine %s apiBoot: empty list after %d open — refused, kept the last good copy",
                                         brand, self._open_count(prev["data"]))
                return {"ok": False, "error": "engine_bad_response"}
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

    def switches(self, brand):
        e = self._boot_entry(brand)
        d = (e or {}).get("data", {})
        return {k: d[k] for k in SWITCH_KEYS if k in d}

    def after_settings(self, brand, args, out):
        """A switch flipped through the screen: patch the cached list at once (every client polling /changes sees it
        within one tick) and mark the switches old, so the next poll re-reads them from the engine."""
        if not out.get("ok") or not isinstance(args, dict) or args.get("action") != "set" or not BRAND_RE.match(brand):
            return
        key, val = args.get("key"), args.get("value")
        if key == "AUTO_CANCEL":
            self.drop_queue(brand, "apiAutoCancelList")
        elif key == "AUTO_REPLY":
            self.drop_queue(brand, "apiAutoReplyList")
        with self.lock:
            e = self._bucket(brand)["boot"]
            if not e:
                return
            if key == "DRY_RUN":
                e["data"]["dryRun"] = val == "on"
            elif key == "KACHING_WRITES":
                e["data"]["cancelEnabled"] = val == "on"
            e["full_at"] = 0
        self._write(os.path.join(self._dir(brand), "boot.json"), e)

    def get_list(self, user, brand, max_age=None):
        e = self._boot_entry(brand)
        if e and max_age is not None and self.clock() - e.get("full_at", e["at"]) > max_age:
            e = None                                  # caller needs switches no older than max_age: read the engine now
        if e:
            age = self.clock() - e["at"]
            timing("cache", None, "list-hit")
            if age > LIST_TTL_S:
                self._background(("boot", brand), lambda: self._fetch_boot(user, brand))
            out = self._for_user(e["data"], user)
            out["ok"] = True
            out["cache"] = {"hit": True, "age_s": round(age, 1)}
            out["syncedAge"] = self.synced_age(brand)
            return 200, out
        out = self._once(("boot", brand), lambda: self._fetch_boot(user, brand))
        if not out.get("ok"):
            return 200, out
        out = self._for_user({k: v for k, v in out.items() if k not in PER_USER}, user)
        out["cache"] = {"hit": False, "age_s": 0}
        out["syncedAge"] = 0
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
        """The client's list delta since ITS version. The engine is read at most once per CHANGES_SHARED_S per brand
        (single-flight, shared by every agent); the answer is cut from the log kept here."""
        if self._boot_entry(brand) is None:
            out = self._once(("boot", brand), lambda: self._fetch_boot(user, brand))
            if not out.get("ok"):
                return 200, out
        else:
            age = self.synced_age(brand)
            if age is None or age > CHANGES_SHARED_S:
                out = self._once(("chg", brand), lambda: self._sync(user, brand))
                if not out.get("ok"):
                    age = self.synced_age(brand)
                    return 200, dict(out, syncedAge=age)
        return 200, self._delta(brand, since)

    def _delta(self, brand, since):
        e = self._boot_entry(brand)
        data = e["data"]
        rows = {t.get("id"): t for t in (data.get("tickets") or []) if isinstance(t, dict)}
        ver = data.get("version")
        s_i, v_i = self._int(since), self._int(ver)
        with self.lock:
            lg = self.chlog.get(brand) or {"floor": None, "items": []}
            items = list(lg["items"])
            floor = lg["floor"]
        out = {"ok": True, "version": ver, "counts": data.get("counts", {}), "serverTime": data.get("serverTime"),
               "via": "feed", "syncedAge": self.synced_age(brand), "switches": {k: data[k] for k in SWITCH_KEYS if k in data}}
        if since is not None and (since == ver or (s_i is not None and v_i is not None and s_i == v_i)):
            out.update(changed=[], removed=[])
        elif s_i is not None and v_i is not None and floor is not None and floor <= s_i <= v_i:
            ids, seen = [], set()
            for v, i in items:
                if v > s_i and i not in seen:
                    seen.add(i)
                    ids.append(i)
            out.update(changed=[rows[i] for i in ids if i in rows], removed=[i for i in ids if i not in rows])
        else:
            out.update(changed=list(rows.values()), removed=[], reset=True)   # the client replaces its whole list
        return out

    def _sync(self, user, brand):
        """One read of the brand's change feed: rows patched into the list, changed tickets marked stale, delta logged.
        Falls back to a full apiBoot when the engine lacks apiChanges, our version is too old, or the list is starving."""
        e = self._boot_entry(brand)
        now = self.clock()
        try:
            work = security.engine_role(user.get("roles", [])) in WORK_ROLES
        except ValueError:
            work = False
        with self.lock:
            feed = self.feed.get(brand)
        since_i = feed["v"] if feed else self._int(e["data"].get("version")) if e else None
        lacks_changes = False
        if e and work and since_i is not None and now > self.no_changes.get(brand, 0):
            out = self._call(user, brand, "apiChanges", {"since": since_i})
            v_chk = self._int(out.get("version"))
            if (out.get("ok") and isinstance(out.get("tickets"), list) and not out.get("reset")
                    and (v_chk is None or v_chk < since_i)):
                # no monotonic version: nothing here can vouch for a cached ticket (Codex 2026-10-05)
                engine_proxy.log.warning("engine %s apiChanges: version %r after since=%s — not trusted", brand, out.get("version"), since_i)
                out = {"ok": False, "error": "engine_bad_response"}
            if out.get("ok") and isinstance(out.get("tickets"), list) and not out.get("reset"):
                rows = [r for r in out["tickets"] if isinstance(r, dict)]
                removed = [i for i in (out.get("removed") or []) if isinstance(i, str)]
                ids = [r.get("id") for r in rows] + removed
                v_new = self._int(out.get("version"))
                with self.lock:
                    cur = self._bucket(brand)["boot"] or e
                    data = self._apply_rows(json.loads(json.dumps(cur["data"])), rows, removed)
                    prev_v = self._int(data.get("version"))
                    if v_new is not None and (prev_v is None or v_new >= prev_v):
                        data["version"] = v_new
                    data["serverTime"] = out.get("serverTime", data.get("serverTime"))
                    full_at = cur.get("full_at", cur["at"])
                    if all(k in out for k in ("dryRun", "cancelEnabled")):    # an engine that sends its switches with the feed
                        for k in SWITCH_KEYS:
                            if k in out:
                                data[k] = out[k]
                        full_at = now
                    entry = {"data": data, "at": now, "full_at": full_at, "synced_at": now}
                    self._bucket(brand)["boot"] = entry
                    self._log(brand, prev_v, self._int(data.get("version")), ids)
                    base_t = feed["base_t"] if feed else cur.get("full_at", cur["at"])
                    self.feed[brand] = {"v": v_new if v_new is not None else since_i, "base_t": base_t, "ok_at": now}
                self._stale(ids, brand)
                self._write(os.path.join(self._dir(brand), "boot.json"), entry)
                if now - full_at > SWITCH_MAX_AGE_S:          # apiChanges has no switches: refresh them behind the poll
                    self._background(("boot", brand), lambda: self._fetch_boot(user, brand))
                return {"ok": True}
            lacks_changes = out.get("error") in ("unauthorized", "forbidden_fn")
            if lacks_changes:
                pass                                                         # recorded below, only if apiBoot then works
            elif out.get("ok") and out.get("reset"):
                self._stale_all(brand)                                       # too far behind: no ticket copy is vouched for
                with self.lock:
                    self.feed.pop(brand, None)
            elif not out.get("ok") and out.get("error") not in ("bad_since",):
                age = self.synced_age(brand)
                if age is None or age < LIST_STARVE_S:
                    return out
                # apiChanges keeps failing and the list is starving: fall through to one full apiBoot
        # fallback: a full apiBoot (diffed and logged in _store_boot, so every client still gets only what changed)
        out = self._once(("boot", brand), lambda: self._fetch_boot(user, brand))
        if not out.get("ok"):
            return out
        if lacks_changes:
            # "unauthorized" is also what Api.gs says for an unknown fn; apiBoot just worked with the same kind of
            # token, so the engine really lacks apiChanges (Codex 2026-10-05: never disable on a plain auth failure)
            self.no_changes[brand] = now + UNSUPPORTED_RETRY_S
        return {"ok": True}

    # ---------- full tickets ----------

    def _fetch_full(self, user, brand, tid, fresh=False):
        top = getattr(self._tl, "top", False)
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
        if bg:                                       # background: one after the other — a pair never takes 2 of the brand's slots
            a = self._call(user, brand, "apiTicket", {"id": tid}, True)
            b = self._call(user, brand, "apiTicketExtras", {"id": tid}, True) if a.get("ok") else {"ok": False}
        else:
            with ThreadPoolExecutor(max_workers=2) as ex:                    # interactive: never one after the other
                fa = ex.submit(self._call, user, brand, "apiTicket", {"id": tid}, False, top)
                fb = ex.submit(self._call, user, brand, "apiTicketExtras", {"id": tid}, False, top)
                a, b = fa.result(), fb.result()
        if not a.get("ok"):
            return None, a
        if b.get("error") == "dropped":              # never cache a ticket without its extras
            return None, b
        if probed:                                                           # the pair works, so the engine lacks apiTicketFull
            self.no_full[brand] = self.clock() + UNSUPPORTED_RETRY_S
        return {"ticket": a.get("ticket") or {}, "extras": (b.get("extras") or {}) if b.get("ok") else {},
                "snapshotAt": None, "extrasError": None if b.get("ok") else (b.get("msg") or b.get("error"))}, None

    def _store_full(self, brand, tid, full, t0=None):
        t0 = self.clock() if t0 is None else t0
        with self.lock:
            t = self._bucket(brand)["t"]
            cur = t.get(tid)
            if cur and float(cur.get("t0", cur.get("at", 0)) or 0) > t0:
                return cur                       # a read that started later already landed: never go back in time
            # the feed saw a change after this read began: the copy may predate it -> keep it marked old
            stale = (self.changed_at.get(brand) or {}).get(tid, -1) > t0
            e = {"full": full, "at": self.clock(), "t0": t0, "stale": stale}
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
            if e and not (isinstance(e.get("full"), dict) and isinstance(e["full"].get("ticket"), dict)
                          and e["full"]["ticket"].get("id") == tid):
                e = None
            if e:
                with self.lock:
                    b["t"][tid] = e
        return e

    def _refresh(self, user, brand, tid, fresh=False):
        t0 = self.clock()
        full, err = self._fetch_full(user, brand, tid, fresh)
        if full:
            full = self._store_full(brand, tid, full, t0)["full"]
        elif err and err.get("error") == "not_found":
            with self.lock:
                self._bucket(brand)["t"].pop(tid, None)
        return full, err

    def confirmed(self, brand, e):
        """Is this cached copy vouched for by the engine within CONFIRM_S — read itself, or covered by a feed read that
        would have marked it changed? Then the open ticket needs no second round-trip."""
        if not e or e.get("stale"):
            return False
        now = self.clock()
        if now - e["at"] <= CONFIRM_S:
            return True
        with self.lock:
            f = self.feed.get(brand)
        return bool(f and now - f["ok_at"] <= CONFIRM_S and float(e.get("t0", e.get("at", 0)) or 0) >= f["base_t"])

    def meta(self, brand, e, hit):
        age = self.clock() - e["at"]
        return {"hit": hit, "age_s": round(age, 1), "stale": bool(e.get("stale")), "at": e["at"],
                "confirmed": self.confirmed(brand, e)}

    def get_ticket(self, user, brand, tid, revalidate=False, fresh=False, top=False):
        if not ID_RE.match(tid):
            return None, {"ok": False, "error": "bad_id"}, {}
        if not revalidate:
            e = self._entry(brand, tid)
            if e:
                age = self.clock() - e["at"]
                timing("cache", None, "ticket-hit")
                if e.get("stale") or age > TICKET_TTL_S:
                    self._background(("t", brand, tid), lambda: self._refresh(user, brand, tid))
                return e["full"], None, self.meta(brand, e, True)
        # QA round 5: an agent waits at most TICKET_WAIT_S; the fetch keeps going and lands in the cache for the retry
        key = ("t", brand, tid, "top") if top else ("t", brand, tid)    # the open ticket never queues behind a prefetch
        def work():
            _collect.items = []
            self._tl.top = top
            try:
                return self._once(key, lambda: self._refresh(user, brand, tid, fresh)), _collect.items
            finally:
                _collect.items = None
                self._tl.top = False
        fut = (self.top_pool if top else self.fg_pool).submit(work)
        try:
            (full, err), tims = fut.result(timeout=TICKET_WAIT_S)
            for t_ in tims:
                timing(*t_)
        except FutureTimeout:
            timing("cache", None, "ticket-slow")
            e = self._entry(brand, tid)
            if e:                                    # an older copy beats a spinner
                return e["full"], None, dict(self.meta(brand, e, True), stale=True, slow=True, confirmed=False)
            return None, {"ok": False, "error": "engine_slow", "pending": True}, {}
        timing("cache", None, "ticket-miss" if not revalidate else "ticket-revalidate")
        e = self._entry(brand, tid) if full else None
        meta = dict(self.meta(brand, e, False), age_s=0) if e else {"hit": False, "age_s": 0, "stale": False}
        return full, err, meta

    def watch(self, user, brand, tid, have_at):
        """The open ticket, every ~5 s per agent. Cheap: it rides the brand's shared feed read (one apiChanges per brand per
        CHANGES_SHARED_S, however many agents watch) and reads the ticket itself only when the feed says it changed.
        -> (copy newer than have_at | None, error | None, meta)"""
        if not ID_RE.match(tid):
            return None, {"ok": False, "error": "bad_id"}, {}
        age = self.synced_age(brand)
        feed_ok = True
        if age is None or age > CHANGES_SHARED_S:
            feed_ok = bool(self._once(("chg", brand), lambda: self._sync(user, brand), wait=WATCH_WAIT_S).get("ok"))
        e = self._entry(brand, tid)
        if (e is None or e.get("stale") or (not feed_ok and not self.confirmed(brand, e)
                                             and self.clock() - e["at"] > WATCH_DIRECT_S)):
            full, err, _ = self.get_ticket(user, brand, tid, revalidate=True, top=True)
            if not full:
                return None, err, {}
            e = self._entry(brand, tid)
        if not e:
            return None, {"ok": False, "error": "engine_slow", "pending": True}, {}
        meta = self.meta(brand, e, True)
        return (e["full"] if e["at"] > have_at + 0.0005 else None), None, meta

    # ---------- related tickets: secondary information, never allowed to crowd out an agent's work ----------
    RELATED_TTL_S = 300

    def related(self, user, brand, q):
        """apiSearch(email/phone) for the "related tickets" card. Cached 5 min per (brand, query); on a miss it runs at
        BACKGROUND priority (free slots only). Measured live 2026-10-05: as an interactive call on every open, these slow
        searches filled the brand's 6 slots and other calls got "busy"."""
        key = (brand, q.strip().lower())
        with self.lock:
            hit = self.mem.setdefault("_related", {}).get(key) if BRAND_RE.match(brand) else None
            if hit and self.clock() - hit[0] < self.RELATED_TTL_S:
                timing("cache", None, "related-hit")
                return {"ok": True, "tickets": hit[1], "cache": True}
        if engine_proxy.gate(brand).tripped():
            return {"ok": True, "tickets": None, "deferred": True}
        out = self._call(user, brand, "apiSearch", {"q": q}, True)
        if out.get("error") == "dropped":
            return {"ok": True, "tickets": None, "deferred": True}
        if not out.get("ok"):
            return out
        rows = out.get("tickets") or []
        with self.lock:
            rel = self.mem.setdefault("_related", {})
            rel[key] = (self.clock(), rows)
            if len(rel) > 5000:
                for k, _ in sorted(rel.items(), key=lambda kv: kv[1][0])[:1000]:
                    rel.pop(k, None)
        return {"ok": True, "tickets": rows}

    # ---------- the auto-cancel / auto-reply queues: shared per brand, background priority ----------
    QUEUE_FNS = ("apiAutoCancelList", "apiAutoReplyList")
    QUEUE_TTL_S = 45
    QUEUE_INVALIDATE = {"apiAutoCancelApprove": "apiAutoCancelList", "apiAutoCancelReject": "apiAutoCancelList",
                        "apiAutoReplyReview": "apiAutoReplyList"}

    def queue(self, user, brand, fn):
        """apiAutoCancelList / apiAutoReplyList for every agent of a brand. Measured live 2026-10-05: reloaded as
        interactive calls on every list load they took agents' slots and returned 502s. Now: cached 45 s, fetched at
        background priority, an expired copy served when the engine is full, "deferred" when there is no copy."""
        key = (brand, fn)
        with self.lock:
            hit = self.mem.setdefault("_queues", {}).get(key) if BRAND_RE.match(brand) else None
        if hit and self.clock() - hit[0] < self.QUEUE_TTL_S:
            timing("cache", None, "queue-hit")
            return dict(hit[1], cache={"hit": True, "age_s": round(self.clock() - hit[0], 1)})
        out = None if engine_proxy.gate(brand).tripped() else self._call(user, brand, fn, {}, True)
        if out is None or out.get("error") == "dropped":
            if hit:
                return dict(hit[1], cache={"hit": True, "stale": True, "age_s": round(self.clock() - hit[0], 1)})
            return {"ok": True, "deferred": True, "items": None}
        if out.get("ok"):
            clean = {k: v for k, v in out.items() if not k.startswith("_") and k != "msg"}
            with self.lock:
                self.mem.setdefault("_queues", {})[key] = (self.clock(), clean)
            return dict(clean, cache={"hit": False})
        return out

    def drop_queue(self, brand, fn):
        with self.lock:
            self.mem.setdefault("_queues", {}).pop((brand, fn), None)

    def prefetch(self, user, brand, ids):
        if engine_proxy.gate(brand).tripped():
            return 0                                 # circuit breaker: no prefetch for ~60 s after a slow/HTML answer
        n = 0
        for tid in ids[:PREFETCH_MAX]:
            if not isinstance(tid, str) or not ID_RE.match(tid):
                continue
            e = self._entry(brand, tid)
            if e and not e.get("stale") and (self.clock() - e["at"] < PREFETCH_FRESH_S or self.confirmed(brand, e)):
                continue
            if self._background(("t", brand, tid), lambda t=tid: self._refresh(user, brand, t)):
                n += 1
        return n

    def _stale(self, ids, brand):
        now = self.clock()
        with self.lock:
            t = self._bucket(brand)["t"]
            ch = self.changed_at.setdefault(brand, {})
            for i in ids:
                if not isinstance(i, str):
                    continue
                ch[i] = now
                if i in t:
                    t[i]["stale"] = True
            if len(ch) > 4 * MAX_TICKETS_PER_BRAND:
                for k, _ in sorted(ch.items(), key=lambda kv: kv[1])[: len(ch) - 2 * MAX_TICKETS_PER_BRAND]:
                    ch.pop(k, None)

    def _stale_all(self, brand):
        with self.lock:
            for e in self._bucket(brand)["t"].values():
                e["stale"] = True

    # ---------- writes made through the screen ----------

    def after_write(self, user, brand, fn, args, out):
        if fn in self.QUEUE_INVALIDATE:              # the next load reads the engine (the write changed the queue)
            self.drop_queue(brand, self.QUEUE_INVALIDATE[fn])
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
            if out.get("queued"):
                patch["wa_send"] = "pending"             # the screen must not offer a second WhatsApp send (QA round 5)
            else:
                patch["status"] = "sent"
        elif ok and fn == "apiAutoReplyReview" and args.get("verdict") == "problem":
            patch = {"status": "action"}                 # "⚠ problem" reopens the ticket (the engine confirms on revalidate)
        elif ok and fn == "apiWaTakeOver":
            patch = {"status": "action"}                 # leaves the bot; the next engine run writes a draft
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
             "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyReview", "apiWaTakeOver")
SWITCH_KEYS = ("dryRun", "cancelEnabled", "cancelFrozen", "subscriptions")
SWITCH_MAX_AGE_S = 15      # how stale DRY_RUN & co may be on a client (live E2E 2026-10-05: send stayed disabled)
LIST_STARVE_S = 60         # QA round 5: a list older than this is refreshed at interactive priority, breaker or not
TICKET_WAIT_S = 15         # an agent waits at most this long for a ticket; the fetch goes on and lands in the cache


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
            return None, d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        if not BRAND_RE.match(brand) or brand not in u.get("brands", []):
            return None, d["json_error"]("forbidden_brand", 403, lang)
        if brand not in d["engines"]:
            return None, d["json_error"]("brand_not_connected", 503, lang)
        return u, None

    def localized(out, lang, fn):
        if not out.get("ok"):                            # always in the language of the page that asked
            code = out.get("error")
            msg = messages.proxy_msg(code, lang) if code in messages.PROXY else messages.engine_error_msg(out, fn, lang)
            out = dict(out, msg=msg)
        return out

    @app.post("/api/<brand>/list")
    def cached_list(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=False)
        if err:
            return err
        ma = (request.get_json(silent=True) or {}).get("maxAge")
        ma = ma if isinstance(ma, (int, float)) and not isinstance(ma, bool) and 0 <= ma <= 3600 else None
        st, out = cache.get_list(u, brand, max_age=ma)
        return jsonify(localized(out, d["ui_lang"](u), "apiBoot")), st

    @app.post("/api/<brand>/changes")
    def cached_changes(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=False)
        if err:
            return err
        since = (request.get_json(silent=True) or {}).get("since")
        st, out = cache.changes(u, brand, since if isinstance(since, (str, int, float)) else None)
        return jsonify(localized(out, d["ui_lang"](u), "apiBoot")), st

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
        if body.get("peek") is True:                    # warming the page's memory: a cached copy or nothing, never the engine
            e = cache._entry(brand, tid)
            if not e:
                return jsonify({"ok": False, "error": "not_cached"})
            return jsonify(ticket_body(e["full"], cache.meta(brand, e, True)))
        fresh = body.get("fresh") is True
        full, e, meta = cache.get_ticket(u, brand, tid, revalidate=body.get("revalidate") is True or fresh, fresh=fresh,
                                         top=body.get("open") is True)       # the ticket on the agent's screen: reserved slot
        if not full:
            return jsonify(localized(dict(e or {"ok": False, "error": "server_error"}), d["ui_lang"](u), "apiTicket")), 200
        return jsonify(ticket_body(full, meta))

    def ticket_body(full, meta):
        return {"ok": True, "ticket": full.get("ticket"), "extras": full.get("extras") or {}, "snapshotAt": full.get("snapshotAt"),
                "extrasErr": full.get("extrasError"), "cache": meta}

    @app.post("/api/<brand>/watch")
    def watch_ticket(brand):
        """The open ticket, polled every ~5 s: {id, at} -> {changed:false} or {changed:true, ticket, extras, ...}."""
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        body = request.get_json(silent=True) or {}
        tid, at = body.get("id"), body.get("at")
        if not isinstance(tid, str) or not ID_RE.match(tid):
            return d["json_error"]("bad_request", 400, d["ui_lang"](u))
        at = float(at) if isinstance(at, (int, float)) and not isinstance(at, bool) else 0.0
        full, e, meta = cache.watch(u, brand, tid, at)
        if e:
            return jsonify(localized(dict(e), d["ui_lang"](u), "apiTicket"))
        if not full:
            return jsonify({"ok": True, "changed": False, "cache": meta, "syncedAge": cache.synced_age(brand)})
        return jsonify(dict(ticket_body(full, meta), changed=True, syncedAge=cache.synced_age(brand)))

    @app.post("/api/<brand>/result")
    def outbox_result(brand):
        """The background-send outbox (after a reload or a lost reply): what became of the write sent with this rid?
        {ok, found, reply} — the stored reply is localized like a direct answer; refusals are never stored."""
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        rid = (request.get_json(silent=True) or {}).get("rid")
        if not isinstance(rid, str) or not engine_proxy.CLIENT_RID_RE.match(rid):
            return d["json_error"]("bad_request", 400, d["ui_lang"](u))
        _, out = engine_proxy.call(d["engines"], cache.transport, cache.secret(), u, brand, "apiResult", {"rid": rid},
                                   d["ui_lang"](u), internal=True)
        if not out.get("ok"):
            return jsonify(localized(out, d["ui_lang"](u), "apiResult"))
        stored, fn = out.get("reply"), out.get("forFn")
        if out.get("found") and isinstance(stored, dict) and isinstance(fn, str) and not engine_proxy.reply_problem(fn, {}, rid, stored, None):
            return jsonify({"ok": True, "found": True, "forFn": fn, "reply": engine_proxy.localize(fn, stored, d["ui_lang"](u))})
        return jsonify({"ok": True, "found": False})

    @app.post("/api/<brand>/related")
    def cached_related(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        q = (request.get_json(silent=True) or {}).get("q")
        if not isinstance(q, str) or not (2 <= len(q.strip()) <= 100):
            return d["json_error"]("bad_request", 400, u.get("lang", "he"))
        return jsonify(localized(cache.related(u, brand, q.strip()), d["ui_lang"](u), "apiSearch"))

    @app.post("/api/<brand>/queue")
    def cached_queue(brand):
        brand = str(brand).lower()
        u, err = gate(brand, work=True)
        if err:
            return err
        fn = (request.get_json(silent=True) or {}).get("fn")
        if fn not in TicketCache.QUEUE_FNS:
            return d["json_error"]("forbidden_fn", 404, u.get("lang", "he"))
        return jsonify(localized(cache.queue(u, brand, fn), d["ui_lang"](u), fn))

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
