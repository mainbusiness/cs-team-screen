"""snooze.py — "לענות מאוחר יותר" (Owner, 2026-10-14, from the CS team).

One agent hides one open ticket from HIS OWN list for 30 min / 1 h / 2 h / until 17:00 Israel. Everyone else still sees it, the managers' counts
never change, and it comes back to the top of his list when the time is up, or at once when the customer writes again.

Stored on the server's private disk (next to the users file), so it survives reloads, devices and deploys:
  GET  /api/snooze                         -> {ok, now, snoozes: [{brand, id, until, at, n, wl, ws}]}   (this user's own: active and recently ended)
  POST /api/<brand>/snooze {id, kind}      -> {ok, snooze}         kind: 30m | 1h | 2h | eod
  POST /api/<brand>/snooze {id, cancel}    -> {ok}                 back to the list now (also: the agent opened a ticket that came back)

"The customer wrote again" = the list row moved past what it was at snooze time: more customer messages (emails_count), a newer WhatsApp
message (wa_last_in), or a new waiting period (waiting_since after the snooze; an open ticket keeps its OLDEST unanswered time, so this alone
is not enough). The screen (static/app.js Snooze) applies the same rule to its own copy of the row.

Never hides a ticket from everyone: refused when no other enabled agent / admin of the brand would still see it.
"""
import fcntl
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import jsonify, request

TZ = ZoneInfo("Asia/Jerusalem")
KINDS = {"30m": 1800, "1h": 3600, "2h": 7200, "eod": None}
EOD_HOUR = 17                     # service hours end at 17:00 Israel (DECISIONS 2026-10-07)
EOD_MIN_AHEAD_S = 15 * 60         # "end of day" is offered only while 17:00 is at least 15 minutes away
KEEP_ENDED_S = 12 * 3600          # an ended snooze is kept a while: the row is "back" (top of the list) until the agent opens it
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}$")
OPEN = ("ready", "action", "health", "delay")
WORK = {"agent", "admin"}


def parse_ts(s):
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def until_for(kind, now):
    """Epoch seconds the snooze ends, or None when that choice is not possible now (end of day already here)."""
    if kind not in KINDS:
        return None
    if KINDS[kind]:
        return now + KINDS[kind]
    local = datetime.fromtimestamp(now, TZ)
    eod = local.replace(hour=EOD_HOUR, minute=0, second=0, microsecond=0).timestamp()
    return eod if eod - now >= EOD_MIN_AHEAD_S else None


def row_mark(row):
    """What the row looks like now — the snooze remembers it, and a row that moved past it is the customer writing again."""
    row = row or {}
    try:
        n = int(row.get("emails_count") or 0)
    except (TypeError, ValueError):
        n = 0
    return {"n": n, "wl": str(row.get("wa_last_in") or "")[:40], "ws": str(row.get("waiting_since") or "")[:40]}


def voided(rec, row):
    """The customer wrote after the snooze: it is over for this ticket."""
    if not row:
        return False
    m = row_mark(row)
    if m["n"] > int(rec.get("n") or 0):
        return True
    wl_now, wl_was = parse_ts(m["wl"]), parse_ts(rec.get("wl"))
    if wl_now is not None and (wl_was is None or wl_now > wl_was + 1):
        return True
    ws_now = parse_ts(m["ws"])
    return ws_now is not None and ws_now > float(rec.get("at") or 0) + 1


def active(rec, row, now):
    return float(rec.get("until") or 0) > now and not voided(rec, row)


class SnoozeStore:
    """One JSON file: {"<brand>|<id>|<user>": {u, b, id, until, at, n, wl, ws}}. Read-modify-write under a thread lock + flock, temp file + replace."""

    def __init__(self, path, clock=time.time):
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _mutate(self, fn):
        with self._lock:
            fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                d = self._read()
                now = self.clock()
                for k in [k for k, r in d.items() if float((r or {}).get("until") or 0) < now - KEEP_ENDED_S]:
                    del d[k]
                out = fn(d, now)
                tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(os.path.abspath(self.path)), delete=False, encoding="utf-8")
                try:
                    with tmp:
                        json.dump(d, tmp, ensure_ascii=False)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.chmod(tmp.name, 0o600)
                    os.replace(tmp.name, self.path)          # atomic: a reader sees the old file or the new one, never half
                except BaseException:
                    try:
                        os.unlink(tmp.name)                  # never a stray temp file on the disk (Codex 2026-10-14)
                    except OSError:
                        pass
                    raise
                return out
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def records(self):
        now = self.clock()
        return [r for r in self._read().values() if isinstance(r, dict) and float(r.get("until") or 0) >= now - KEEP_ENDED_S]

    def mine(self, user):
        return [r for r in self.records() if r.get("u") == user]

    def put(self, user, brand, tid, until, row):
        def m(d, now):
            rec = dict({"u": user, "b": brand, "id": tid, "until": float(until), "at": now}, **row_mark(row))
            d["%s|%s|%s" % (brand, tid, user)] = rec
            return rec
        return self._mutate(m)

    def drop(self, user, brand, tid):
        return self._mutate(lambda d, now: d.pop("%s|%s|%s" % (brand, tid, user), None) is not None)

    def snoozed_now(self, rows_by_brand, now=None):
        """{user: number of tickets hidden from his list right now} — for the managers' board."""
        now = self.clock() if now is None else now
        out = {}
        for r in self.records():
            row = (rows_by_brand.get(r.get("b")) or {}).get(r.get("id"))
            if row is None or row.get("status") not in OPEN or not active(r, row, now):
                continue
            out[r["u"]] = out.get(r["u"], 0) + 1
        return out


def public(rec):
    return {k: rec.get(k) for k in ("b", "id", "until", "at", "n", "wl", "ws")} | {"brand": rec.get("b")}


def register(app, d):
    """d: api_user, json_error, ui_lang, store (users), cache (ticket cache), snooze (SnoozeStore), is_test_user."""
    snz, cache = d["snooze"], d["cache"]

    def user_or_err(brand=None):
        u, err = d["api_user"]()
        if err:
            return None, err
        lang = d["ui_lang"](u)
        if not (set(u.get("roles", [])) & WORK):
            return None, d["json_error"]("forbidden_role", 403, lang)
        if brand is not None and (not BRAND_RE.match(brand) or brand not in u.get("brands", [])):
            return None, d["json_error"]("forbidden_brand", 403, lang)
        return u, None

    @app.get("/api/snooze")
    def snooze_list():
        u, err = user_or_err()
        if err:
            return err
        return jsonify({"ok": True, "now": snz.clock(), "snoozes": [public(r) for r in snz.mine(u["username"]) if r.get("b") in u.get("brands", [])]})

    @app.post("/api/<brand>/snooze")
    def snooze_set(brand):
        brand = str(brand).lower()
        u, err = user_or_err(brand)
        if err:
            return err
        lang = d["ui_lang"](u)
        body = request.get_json(silent=True) or {}
        tid = body.get("id")
        if not isinstance(tid, str) or not ID_RE.match(tid):
            return d["json_error"]("bad_request", 400, lang)
        if body.get("cancel") is True:
            snz.drop(u["username"], brand, tid)
            return jsonify({"ok": True})
        kind = body.get("kind")
        if kind not in KINDS:
            return d["json_error"]("bad_request", 400, lang)
        now = snz.clock()
        until = until_for(kind, now)
        if until is None:
            return d["json_error"]("snooze_too_late", 409, lang)
        row = (cache.cached_rows(brand) or {}).get(tid)
        if not row or row.get("status") not in OPEN:
            return d["json_error"]("snooze_not_open", 409, lang)
        # never from everyone: another enabled agent / admin of this brand must still see it
        mine = u["username"]
        taken = {r["u"] for r in snz.records() if r.get("b") == brand and r.get("id") == tid and active(r, row, now)}
        others = [x["username"] for x in d["store"].all() if x["username"] != mine and not x.get("disabled")
                  and set(x.get("roles", [])) & WORK and brand in x.get("brands", []) and not d["is_test_user"](x["username"])]
        if not [o for o in others if o not in taken]:
            return d["json_error"]("snooze_everyone", 409, lang)
        rec = snz.put(mine, brand, tid, until, row)
        return jsonify({"ok": True, "snooze": public(rec)})
