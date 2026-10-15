"""
pgstore.py — the screen's durable state in the core Postgres (2026-10-16: the Render persistent disk is gone).

Why: a service with a persistent disk makes Render stop the OLD instance before it starts the new one, so every
deploy was downtime. Without a disk Render keeps the old instance until the new one passes /healthz.

What lives here (own `screen_*` tables, nothing shared with the core engine's tables):
  screen_users     one row per user (the record exactly as users.json held it)
  screen_audit     the user-manager audit log (append-only)
  screen_activity  the agents' activity log + presence (prefix 'act' | 'pres', one row per event, per Israel day)
  screen_snap      the midnight brand-overview snapshots (not recomputable: tickets change)
  screen_snooze    live "answer later" snoozes
  screen_translate English-mode translation cache (cheap to keep, costs LLM money to rebuild)
  screen_backup    full tar.gz of the old disk (taken once, by the first boot that sees the disk)
  screen_meta      import marker + counts

Two instances run side by side during a deploy, so correctness never depends on an in-process lock: every
read-modify-write is a transaction holding a Postgres advisory lock.
"""
import contextlib
import hashlib
import io
import json
import logging
import os
import queue
import tarfile
import threading
import time

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger("cs.pgstore")

LOCK_USERS, LOCK_SNOOZE, LOCK_INIT, LOCK_IMPORT = 7301, 7302, 7303, 7304

SCHEMA = """
create table if not exists screen_users(username text primary key, data jsonb not null);
create table if not exists screen_audit(id bigserial primary key, line jsonb not null);
create table if not exists screen_activity(id bigserial primary key, prefix text not null, day text not null, obj jsonb not null);
create index if not exists screen_activity_pd on screen_activity(prefix, day);
create table if not exists screen_snap(day text primary key, obj jsonb not null);
create table if not exists screen_snooze(key text primary key, data jsonb not null);
create table if not exists screen_translate(key text primary key, val jsonb not null, at double precision not null);
create table if not exists screen_backup(name text primary key, created timestamptz not null default now(),
                                         sha256 text not null, size bigint not null, files jsonb not null, data bytea not null);
create table if not exists screen_meta(key text primary key, value jsonb not null);
"""

# pure caches that are never worth copying: regenerable from the engines / Shopify in seconds
BACKUP_SKIP_DIRS = ("ticket-cache", "zipfix-cache", "zipfix-jobs")


class DB:
    """A tiny bounded connection pool (psycopg3 without psycopg_pool). Reconnects when Render closes an idle socket."""

    def __init__(self, url, size=8):
        self.url = url
        self.size = size
        self._q = queue.LifoQueue()
        self._made = 0
        self._lk = threading.Lock()

    def _connect(self):
        c = psycopg.connect(self.url, autocommit=True, connect_timeout=10,
                            options="-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000")
        return c

    def _checkout(self):
        try:
            return self._q.get_nowait()
        except queue.Empty:
            pass
        with self._lk:
            if self._made < self.size:
                self._made += 1
                try:
                    return self._connect()
                except BaseException:
                    self._made -= 1
                    raise
        return self._q.get(timeout=20)

    def _checkin(self, c, bad=False):
        if bad or c.closed or c.broken:
            with contextlib.suppress(Exception):
                c.close()
            with self._lk:
                self._made -= 1
            return
        self._q.put(c)

    def run(self, fn, tx=False):
        """fn(conn) -> value. One retry on a dead connection (reads and our idempotent writes)."""
        last = None
        for attempt in (0, 1):
            c = self._checkout()
            bad = False
            try:
                if c.closed or c.broken:
                    raise psycopg.OperationalError("stale connection")
                if tx:
                    with c.transaction():
                        return fn(c)
                return fn(c)
            except psycopg.OperationalError as e:
                bad, last = True, e
            finally:
                self._checkin(c, bad)
        raise last

    def q(self, sql, params=()):
        return self.run(lambda c: c.execute(sql, params).fetchall())

    def x(self, sql, params=()):
        return self.run(lambda c: c.execute(sql, params).rowcount)


def init(db):
    def go(c):
        c.execute("select pg_advisory_xact_lock(%s)", (LOCK_INIT,))
        c.execute(SCHEMA)
    db.run(go, tx=True)


# ---------------------------------------------------------------- one-time backup + import from the old disk

def _tar_disk(disk_dir):
    buf = io.BytesIO()
    names = []
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for dp, dns, fns in os.walk(disk_dir):
            rel = os.path.relpath(dp, disk_dir)
            top = rel.split(os.sep)[0]
            if top in BACKUP_SKIP_DIRS:
                dns[:] = []
                continue
            dns[:] = [d for d in dns if d != "lost+found"]
            for fn in sorted(fns):
                if fn.endswith((".lock", ".tmp")):
                    continue
                full = os.path.join(dp, fn)
                arc = os.path.normpath(os.path.join(rel, fn)) if rel != "." else fn
                try:
                    tf.add(full, arcname=arc, recursive=False)
                    names.append({"name": arc, "size": os.path.getsize(full)})
                except OSError as e:
                    log.warning("backup skipped %s: %s", full, e)
    return buf.getvalue(), names


def _jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def backup_and_import(db, disk_dir, users_file=None):
    """Idempotent. 1) backup row of the whole disk (once). 2) import, per table only when that table is empty.
    Returns a summary dict (also stored in screen_meta 'import')."""
    if not disk_dir or not os.path.isdir(disk_dir):
        return {"skipped": "no disk"}
    users_file = users_file or os.path.join(disk_dir, "users.json")
    summary = {"at": time.time(), "disk_dir": disk_dir}
    have_backup = db.q("select count(*) from screen_backup")[0][0] > 0
    if not have_backup and any(os.scandir(disk_dir)):
        blob, names = _tar_disk(disk_dir)
        sha = hashlib.sha256(blob).hexdigest()
        db.x("insert into screen_backup(name, sha256, size, files, data) values (%s,%s,%s,%s,%s) on conflict do nothing",
             ("disk-%s" % time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), sha, len(blob), Jsonb(names), blob))
        summary["backup"] = {"sha256": sha, "bytes": len(blob), "files": len(names)}
        log.warning("pgstore: disk backup stored (%d files, %d bytes, sha256 %s)", len(names), len(blob), sha)

    def go(c):
        c.execute("select pg_advisory_xact_lock(%s)", (LOCK_IMPORT,))
        cnt = {}
        if c.execute("select count(*) from screen_users").fetchone()[0] == 0 and os.path.exists(users_file):
            with open(users_file, encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users") if isinstance(data, dict) else None
            if not isinstance(users, dict):
                raise RuntimeError("users.json on the disk is not a users file — refusing to start with an empty user table")
            n = 0
            for name, rec in users.items():
                n += c.execute("insert into screen_users(username, data) values (%s,%s) on conflict do nothing", (name, Jsonb(rec))).rowcount
            cnt["users"] = n
            if n != len(users):
                raise RuntimeError("users import mismatch: %d of %d inserted" % (n, len(users)))
        if c.execute("select count(*) from screen_audit").fetchone()[0] == 0:
            lines = _jsonl(os.path.join(disk_dir, "users-audit.jsonl"))
            with c.cursor() as cur:
                cur.executemany("insert into screen_audit(line) values (%s)", [(Jsonb(l),) for l in lines])
            cnt["audit"] = len(lines)
        if c.execute("select count(*) from screen_activity").fetchone()[0] == 0:
            adir = os.path.join(disk_dir, "activity")
            rows, days = [], set()
            if os.path.isdir(adir):
                for fn in sorted(os.listdir(adir)):
                    for pre in ("act", "pres"):
                        if fn.startswith(pre + "-") and fn.endswith(".jsonl"):
                            day = fn[len(pre) + 1:-len(".jsonl")]
                            if pre == "act":
                                days.add(day)
                            rows += [(pre, day, Jsonb(o)) for o in _jsonl(os.path.join(adir, fn))]
            with c.cursor() as cur:
                cur.executemany("insert into screen_activity(prefix, day, obj) values (%s,%s,%s)", rows)
            cnt["activity_events"] = sum(1 for r in rows if r[0] == "act")
            cnt["presence_rows"] = sum(1 for r in rows if r[0] == "pres")
            cnt["activity_days"] = len(days)
        if c.execute("select count(*) from screen_snap").fetchone()[0] == 0:
            adir, n = os.path.join(disk_dir, "activity"), 0
            if os.path.isdir(adir):
                for fn in sorted(os.listdir(adir)):
                    if fn.startswith("snap-") and fn.endswith(".json"):
                        try:
                            with open(os.path.join(adir, fn), encoding="utf-8") as f:
                                obj = json.load(f)
                        except (OSError, ValueError):
                            continue
                        n += c.execute("insert into screen_snap(day, obj) values (%s,%s) on conflict do nothing", (fn[5:-5], Jsonb(obj))).rowcount
            cnt["snapshots"] = n
        if c.execute("select count(*) from screen_snooze").fetchone()[0] == 0:
            sp = os.path.join(disk_dir, "snooze.json")
            n = 0
            try:
                with open(sp, encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                d = {}
            for k, rec in (d.items() if isinstance(d, dict) else []):
                n += c.execute("insert into screen_snooze(key, data) values (%s,%s) on conflict do nothing", (k, Jsonb(rec))).rowcount
            cnt["snoozes"] = n
        c.execute("insert into screen_meta(key, value) values ('import', %s) on conflict (key) do update set value = excluded.value",
                  (Jsonb(dict(summary, imported=cnt)),))
        return cnt

    summary["imported"] = db.run(go, tx=True)
    log.warning("pgstore: import from %s -> %s", disk_dir, summary["imported"])
    return summary


# ---------------------------------------------------------------- translate cache

class PgTranslateCache:
    """Same get/put contract as assistant.DiskCache (the value is any JSON: a string or the approved-Hebrew dict)."""

    def __init__(self, db, ttl_s=30 * 86400):
        self.db, self.ttl_s = db, ttl_s

    def get(self, key):
        try:
            rows = self.db.q("select val, at from screen_translate where key=%s", (key,))
        except Exception:
            return None
        if not rows:
            return None
        if time.time() - float(rows[0][1]) > self.ttl_s:
            with contextlib.suppress(Exception):
                self.db.x("delete from screen_translate where key=%s and at=%s", (key, rows[0][1]))
            return None
        return rows[0][0]

    def put(self, key, text):
        with contextlib.suppress(Exception):          # a cache that cannot write is only slower
            self.db.x("insert into screen_translate(key, val, at) values (%s,%s,%s) "
                      "on conflict (key) do update set val=excluded.val, at=excluded.at", (key, Jsonb(text), time.time()))


def reset_all(url):
    """TESTS ONLY: empty every screen_* table of a throwaway database."""
    if "127.0.0.1" not in url and "localhost" not in url:
        raise RuntimeError("reset_all refuses to touch a non-local database")
    db = DB(url, size=1)
    init(db)
    for t in ("screen_users", "screen_audit", "screen_activity", "screen_snap", "screen_snooze", "screen_translate", "screen_backup", "screen_meta"):
        db.x("truncate %s restart identity" % t)
    for c in list(db._q.queue):
        c.close()
