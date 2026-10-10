"""Background jobs for the zip fill. A job = one brand + one order list (or "all open") running in its own thread.

 - At most `max_running` jobs at a time (default 2); a third start is refused with 'busy' (the caller retries).
 - The same brand + same order set while one is already running returns that job instead of starting another
   (a double click must not burn a slot or hammer the zip sources twice).
 - Every job is a JSON file on the private disk (0600, atomic write) and is kept 24 h. The file holds addresses,
   so it lives only on the Render disk; nothing here logs an address.
 - A restart kills running threads: at start-up every record still marked 'running' is closed as 'interrupted'.
 - Job ids are 128-bit random; the id is the capability, and the routes also check brand access.
"""
import json
import logging
import os
import re
import secrets
import threading
import time

log = logging.getLogger("cs_screen.zipfix")

ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
TTL_S = 24 * 3600

ERR_HE = {
    "not_configured": "חסרים פרטי החיבור לחנות בשרת.",
    "shopify_failed": "לא הצלחנו לקרוא את ההזמנות מהחנות. נסו שוב בעוד כמה דקות.",
    "interrupted": "השרת הופעל מחדש באמצע הריצה. להריץ שוב.",
    "internal": "הריצה נכשלה בשגיאה לא צפויה. להריץ שוב; אם חוזר — לדווח.",
}


def _classify_error(e):
    name = type(e).__name__
    if name == "ZipfixConfigError":
        return "not_configured"
    if isinstance(e, RuntimeError) and "shopify" in str(e).lower():
        return "shopify_failed"
    if isinstance(e, RuntimeError) and re.match(r"^[a-z]+: ", str(e)):      # core.gql: "<brand>: <graphql errors>"
        return "shopify_failed"
    return "internal"


class JobManager:
    def __init__(self, directory, runner, max_running=2, ttl=TTL_S, now=time.time, on_event=None):
        self.dir, self.runner, self.max_running, self.ttl, self.now = directory, runner, max_running, ttl, now
        self.on_event = on_event or (lambda kind, rec: None)
        self._live = {}                    # id -> record (running jobs, mutated by their thread)
        self._lock = threading.Lock()
        os.makedirs(self.dir, mode=0o700, exist_ok=True)
        self._close_orphans()
        self._sweep()

    # ---------- disk ----------

    def _path(self, job_id):
        return os.path.join(self.dir, job_id + ".json")

    def _write(self, rec):
        tmp = "%s.%d.%d.tmp" % (self._path(rec["job"]), os.getpid(), threading.get_ident())
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps(rec, ensure_ascii=False).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self._path(rec["job"]))

    def _read(self, job_id):
        try:
            with open(self._path(job_id), "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        except (OSError, ValueError):
            return None

    def _files(self):
        try:
            return [n for n in os.listdir(self.dir) if n.endswith(".json") and ID_RE.match(n[:-5])]
        except OSError:
            return []

    def _close_orphans(self):
        for n in self._files():
            rec = self._read(n[:-5])
            if rec and rec.get("state") == "running":
                rec.update(state="error", error="interrupted", msg=ERR_HE["interrupted"], finished=self.now())
                try:
                    self._write(rec)
                except OSError:
                    log.warning("zipfix: could not close orphan job")

    def _sweep(self):
        cutoff = self.now() - self.ttl
        for n in self._files():
            p = os.path.join(self.dir, n)
            try:
                if os.path.getmtime(p) < cutoff and n[:-5] not in self._live:
                    os.remove(p)
            except OSError:
                pass
        try:
            names = os.listdir(self.dir)
        except OSError:
            return                                              # a sweep is housekeeping: never fail a start over it
        for n in names:                                         # stray temp files from a crash mid-write
            if n.endswith(".tmp"):
                try:
                    if os.path.getmtime(os.path.join(self.dir, n)) < self.now() - 3600:
                        os.remove(os.path.join(self.dir, n))
                except OSError:
                    pass

    # ---------- API ----------

    def start(self, brand, nums, source, actor):
        """-> (job_id, reused) or raises Busy."""
        key = (brand, tuple(sorted(nums)) if nums else None)
        with self._lock:
            for jid, rec in self._live.items():
                if rec["_key"] == key:
                    return jid, True
            if len(self._live) >= self.max_running:
                raise Busy()
            jid = secrets.token_urlsafe(18)
            rec = {"job": jid, "brand": brand, "state": "running", "progress": {"done": 0, "total": 0},
                   "created": self.now(), "source": source, "n_orders": len(nums) if nums else None, "_key": key}
            self._live[jid] = rec
        try:
            self._write(self._public_file(rec))
        except OSError:
            with self._lock:
                self._live.pop(jid, None)
            raise
        self._sweep()
        self.on_event("start", dict(rec, actor=actor))
        threading.Thread(target=self._run, args=(rec, nums, actor), name="zipfix-" + jid[:6], daemon=True).start()
        return jid, False

    @staticmethod
    def _public_file(rec):
        return {k: v for k, v in rec.items() if not k.startswith("_")}

    def _run(self, rec, nums, actor):
        """The live record stays 'running' until the final file is on disk and the slot is released, so a client
        that sees 'done' can always start the next run, and a crash between the two leaves 'running' for the orphan sweep."""
        def progress(done, total):
            rec["progress"] = {"done": int(done), "total": int(total)}
        final = self._public_file(rec)
        try:
            res = self.runner(rec["brand"], nums, progress)
            final["result"] = {k: v for k, v in res.items() if not k.startswith("_")}
            final["state"] = "done"
        except BaseException as e:                              # noqa: BLE001 — a job thread must always close its record
            code = _classify_error(e)
            log.warning("zipfix job %s failed: %s (%s)", rec["job"][:6], type(e).__name__, code)
            final.update(state="error", error=code, msg=ERR_HE[code])
        final["progress"] = dict(rec["progress"])
        final["finished"] = self.now()
        try:
            self._write(final)
        except OSError:
            log.error("zipfix: could not write the result of job %s", rec["job"][:6])
            final.update(state="error", error="internal", msg=ERR_HE["internal"])
            final.pop("result", None)
        finally:
            with self._lock:
                self._live.pop(rec["job"], None)
        try:
            self.on_event("end", dict(final, actor=actor))
        except Exception:                                       # noqa: BLE001
            log.exception("zipfix: audit callback failed")

    def get(self, job_id):
        if not isinstance(job_id, str) or not ID_RE.match(job_id):
            return None
        with self._lock:
            rec = self._live.get(job_id)
            if rec:
                return dict(self._public_file(rec), progress=dict(rec["progress"]))
        return self._read(job_id)

    def running(self):
        with self._lock:
            return len(self._live)


class Busy(Exception):
    pass
