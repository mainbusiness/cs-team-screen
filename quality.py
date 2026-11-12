"""quality.py — the CS manager's DAILY SAMPLED QUALITY CHECK of the agents' replies (Owner, 2026-11-12: agents click "send" on the AI /
template draft without reading it, and sometimes do not really answer. "A control": the CS manager samples the day's replies of every
agent in every brand, rates them, and the board shows a quality score per agent).

What it reads (no new engine call of its own except the one ticket a manager opens in the check):
  * the screen's own activity log (screen_activity, `dashboard.ActivityLog`): who sent / closed which ticket, and whether the agent typed
    anything in that ticket before the send (the 'edit' heartbeat / autosave). Per agent = that agent's OWN events only (the owner 2026-11-06:
    brand-level or wall-clock numbers are not evidence about an employee).
  * for an item the manager opens: the ticket through the shared ticket cache (conversation + the stored snapshot; the engine keeps the AI's
    own draft there as `aiDraft` the first time a person saves over it — engine/AiLearn.gs).

The sample (per Israel day, shared by all managers):
  * candidates = tickets an AGENT (role `agent`, not a QA / automation account) answered today (`send`), and tickets the agent CLOSED today
    with no reply from anyone in the 24 h before the close (`closed`: "marked handled with no answer" — sometimes right, e.g. a "thanks").
  * per agent per brand up to PER_GROUP (3): at most one `closed` first, the rest in a random order that is FIXED for the day
    (sha256 of day|brand|agent|ticket), capped MAX_PER_AGENT per agent and MAX_TOTAL per day, filled round-robin so every agent and brand
    gets its first item before anyone gets a third.
  * frozen: once drawn, an item never leaves the sample (a reload never reshuffles); later in the day a group below its quota is topped up
    with new candidates; after "done" nothing is added.

Signals per agent (from the log, no rating needed): sends, % sent with NO keystroke in the ticket (the prefilled AI / template text went out
untouched), and closes with no reply. Ratings: 1-5 + four yes/no checks + an optional note, one per item per day (re-rating overwrites).

Routes (admin + user-manager; under /api/dash so a manager's reading is not "presence"; CSRF by app.py like every write):
  GET  /api/dash/quality[?day=]            the day's sample + ratings + the per-agent 7-day table + the last 7 days' check status
  GET  /api/dash/quality/status            light: today's pending count / done, and whether the end-of-day reminder is due
  GET  /api/dash/quality/item?day=&key=    one item's customer message(s), the reply sent, and the AI draft when the snapshot has it
  POST /api/dash/quality/rate {day, key, score, checks, note}
  POST /api/dash/quality/done {day}        refused until every item of the day is rated
Storage: Postgres screen_quality_days + screen_quality_ratings (pgstore.SCHEMA), a JSON file for tests (QUALITY_PATH). Audited.
"""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

from flask import jsonify, request

import dashboard
import messages

PER_GROUP = 3                 # items per agent per brand
MAX_PER_AGENT = 9
MAX_TOTAL = 40
SCORE_DAYS = 7
CHECKS = ("answered", "correct", "personal", "tone")
NOTE_MAX = 500
CLOSE_LOOKBACK_S = 24 * 3600  # a close with no send by anyone in this window before it = "closed with no reply"
MATCH_S = 900                 # the sent message in the conversation: within 15 min of the logged send
SAME = 0.97                   # word overlap at or above this = the same text (engine AiLearn.gs AI_LEARN_SAME)
TEXT_MAX = 2000
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}:[A-Za-z0-9_-]{1,80}:[A-Za-z0-9_.@-]{1,64}$")
OURS = ("us", "agent", "team", "human")


def remind_hour():
    """From this Israel hour the reminder modal opens (env QUALITY_REMIND_HOUR; 24 = never, used by the browser tests)."""
    try:
        v = int(os.environ.get("QUALITY_REMIND_HOUR", "16"))
    except ValueError:
        v = 16
    return min(max(v, 0), 24)


def words(s):
    return set(w for w in re.sub(r"[^\w\s]", " ", str(s or "").lower()).split() if w)


def overlap(a, b):
    A, B = words(a), words(b)
    u = A | B
    return len(A & B) / len(u) if u else 1.0


def mix(day, brand, agent, tid):
    return hashlib.sha256(("%s|%s|%s|%s" % (day, brand, agent, tid)).encode()).hexdigest()


def item_key(brand, tid, agent):
    return "%s:%s:%s" % (brand, tid, agent)


# ---------------------------------------------------------------- signals + candidates (pure)

def analyse(events, day_of=dashboard.il_day):
    """events: activity rows (any days, any order). -> list of per-ticket outcomes:
    {u, b, t, day, kind: send|closed, ts, untouched (send), ch, cat}. One 'send' row per send, one 'closed' row per close without a reply."""
    by_tk = {}
    for e in events:
        if isinstance(e, dict) and isinstance(e.get("ts"), (int, float)) and e.get("k") in dashboard.KINDS:
            by_tk.setdefault((e.get("b"), e.get("t")), []).append(e)
    out = []
    for (b, t), evs in by_tk.items():
        evs.sort(key=lambda e: e["ts"])
        last_send_by = {}
        for i, e in enumerate(evs):
            k, u, ts = e["k"], e.get("u"), e["ts"]
            if k == "send":
                lo = max(last_send_by.get(u, -1), ts - dashboard.HANDLE_MAX_S)
                edited = any(x["k"] == "edit" and x.get("u") == u and lo < x["ts"] <= ts for x in evs[:i])
                out.append({"u": u, "b": b, "t": t, "day": day_of(ts), "kind": "send", "ts": ts, "untouched": not edited,
                            "ch": e.get("ch") or "", "cat": e.get("cat") or ""})
                last_send_by[u] = ts
            elif k == "close":
                replied = any(x["k"] in dashboard.REPLY_KINDS and ts - CLOSE_LOOKBACK_S <= x["ts"] <= ts for x in evs[:i + 1] if x is not e)
                if not replied:
                    out.append({"u": u, "b": b, "t": t, "day": day_of(ts), "kind": "closed", "ts": ts, "untouched": None,
                                "ch": e.get("ch") or "", "cat": e.get("cat") or ""})
    return out


def candidates(outcomes, day, agents):
    """-> {(agent, brand): [cand, ...]} for `day`, one candidate per ticket (a ticket the agent answered is a 'send' even if he also closed it)."""
    per = {}
    for o in outcomes:
        if o["day"] != day or o["u"] not in agents:
            continue
        g = per.setdefault((o["u"], o["b"]), {})
        cur = g.get(o["t"])
        if cur is None or (cur["kind"] == "closed" and o["kind"] == "send") or (cur["kind"] == o["kind"] and o["ts"] > cur["ts"]):
            g[o["t"]] = o
    return {k: list(v.values()) for k, v in per.items()}


def top_up(day, sample, cands):
    """Append-only: the existing sample stays exactly as it is; groups below PER_GROUP get more, round-robin, within the caps."""
    sample = list(sample or [])
    have = {it["key"] for it in sample}
    g_n, a_n = {}, {}
    for it in sample:
        g_n[(it["agent"], it["brand"])] = g_n.get((it["agent"], it["brand"]), 0) + 1
        a_n[it["agent"]] = a_n.get(it["agent"], 0) + 1
    queues = {}
    for (a, b), cs in sorted(cands.items()):
        cs = sorted(cs, key=lambda c: mix(day, b, a, c["t"]))
        closed = [c for c in cs if c["kind"] == "closed"][:1]
        rest = [c for c in cs if c not in closed]
        queues[(a, b)] = [c for c in closed + rest if item_key(b, c["t"], a) not in have]
    for _ in range(PER_GROUP):
        for g in sorted(queues):
            a, b = g
            if len(sample) >= MAX_TOTAL:
                return sample
            if g_n.get(g, 0) >= PER_GROUP or a_n.get(a, 0) >= MAX_PER_AGENT or not queues[g]:
                continue
            c = queues[g].pop(0)
            sample.append({"key": item_key(b, c["t"], a), "brand": b, "tid": c["t"], "agent": a, "kind": c["kind"], "ts": round(c["ts"], 3),
                           "untouched": c["untouched"], "ch": c["ch"], "cat": c["cat"]})
            g_n[g] = g_n.get(g, 0) + 1
            a_n[a] = a_n.get(a, 0) + 1
    return sample


def agent_table(outcomes, ratings, agents, days, brands, names):
    """Per agent over `days`: the ratings (score + each check's yes %) and the log signals. Only the agent's own events / items."""
    rows = {}

    def row(a):
        return rows.setdefault(a, {"user": a, "name": names.get(a) or a, "n": 0, "score_sum": 0, "checks": {c: [0, 0] for c in CHECKS},
                                   "sends": 0, "untouched": 0, "closed": 0, "today_sends": 0, "today_untouched": 0, "today_closed": 0})
    today = days[-1]
    for o in outcomes:
        if o["u"] not in agents or o["day"] not in days or o["b"] not in brands:
            continue
        r = row(o["u"])
        if o["kind"] == "send":
            r["sends"] += 1
            r["untouched"] += 1 if o["untouched"] else 0
            if o["day"] == today:
                r["today_sends"] += 1
                r["today_untouched"] += 1 if o["untouched"] else 0
        else:
            r["closed"] += 1
            if o["day"] == today:
                r["today_closed"] += 1
    for rt in ratings:
        if rt["day"] not in days or rt["brand"] not in brands:
            continue
        r = row(rt["agent"])
        r["n"] += 1
        r["score_sum"] += rt["score"]
        for c in CHECKS:
            v = (rt.get("checks") or {}).get(c)
            if isinstance(v, bool):
                r["checks"][c][1] += 1
                r["checks"][c][0] += 1 if v else 0
    out = []
    for r in rows.values():
        handled = r["sends"] + r["closed"]
        out.append({"user": r["user"], "name": r["name"], "rated": r["n"], "score": round(r["score_sum"] / r["n"], 2) if r["n"] else None,
                    "checks": {c: (round(100.0 * y / n, 1) if n else None) for c, (y, n) in r["checks"].items()},
                    "sends": r["sends"], "untouched_pct": round(100.0 * r["untouched"] / r["sends"], 1) if r["sends"] else None,
                    "closed": r["closed"], "closed_pct": round(100.0 * r["closed"] / handled, 1) if handled else None,
                    "today_sends": r["today_sends"], "today_untouched": r["today_untouched"], "today_closed": r["today_closed"]})
    out.sort(key=lambda r: (r["score"] is None, r["score"] if r["score"] is not None else 0, -r["sends"]))
    return out


# ---------------------------------------------------------------- stores

class QualityError(Exception):
    def __init__(self, code, **kw):
        super().__init__(code)
        self.code, self.kw = code, kw


def check_done(sample, rated_keys):
    left = [it["key"] for it in sample if it["key"] not in rated_keys]
    if not sample:
        raise QualityError("quality_empty")
    if left:
        raise QualityError("quality_unrated", n=len(left))


class QualityStore:
    """{"days": {day: {sample, created_at, done_by, done_at}}, "ratings": {day: {key: rec}}} in one JSON file (flock + temp + fsync + replace)."""

    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            return {"days": {}, "ratings": {}}
        if not isinstance(d, dict) or not isinstance(d.get("days"), dict) or not isinstance(d.get("ratings"), dict):
            raise RuntimeError("quality file is not a quality file")          # never start over an unreadable file
        return d

    def _mutate(self, fn):
        with self._lock:
            fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                d = self._read()
                out = fn(d)
                tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(os.path.abspath(self.path)), delete=False, encoding="utf-8")
                try:
                    with tmp:
                        json.dump(d, tmp, ensure_ascii=False)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.chmod(tmp.name, 0o600)
                    os.replace(tmp.name, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    raise
                return out
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def day(self, day):
        rec = self._read()["days"].get(day)
        return dict(rec) if rec else None

    def days(self, days):
        all_ = self._read()["days"]
        return {d: dict(all_[d]) for d in days if d in all_}

    def ensure(self, day, grow):
        """grow(sample) -> new sample (append-only). Not called once the day is done. -> the day record."""
        def m(d):
            rec = d["days"].get(day) or {"sample": [], "created_at": self.clock(), "done_by": "", "done_at": None}
            if not rec.get("done_by"):
                new = grow(list(rec["sample"]))
                if new != rec["sample"] or day not in d["days"]:
                    rec["sample"] = new
                    d["days"][day] = rec
            return dict(rec)
        return self._mutate(m)

    def ratings(self, days):
        r = self._read()["ratings"]
        return [dict(v) for d in days for v in (r.get(d) or {}).values()]

    def rate(self, day, key, agent, brand, score, checks, note, by):
        def m(d):
            rec = {"day": day, "key": key, "agent": agent, "brand": brand, "score": score, "checks": checks, "note": note, "by": by, "at": self.clock()}
            d["ratings"].setdefault(day, {})[key] = rec
            return dict(rec)
        return self._mutate(m)

    def done(self, day, by):
        """-> (day record, changed). Refused unless every item of the sample is rated."""
        def m(d):
            rec = d["days"].get(day)
            if not rec:
                raise QualityError("quality_empty")
            if rec.get("done_by"):
                return dict(rec), False
            check_done(rec["sample"], set((d["ratings"].get(day) or {}).keys()))
            rec["done_by"], rec["done_at"] = by, self.clock()
            return dict(rec), True
        return self._mutate(m)


class PgQualityStore:
    """Same contract on the core Postgres (pgstore.SCHEMA: screen_quality_days, screen_quality_ratings). Two instances run during a deploy:
    the sample grows inside one transaction holding the day row FOR UPDATE; a rating is one upsert."""

    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    @staticmethod
    def _day(r):
        return {"sample": r[0], "created_at": r[1], "done_by": r[2] or "", "done_at": r[3]}

    def day(self, day):
        r = self.db.q("select sample, created_at, done_by, done_at from screen_quality_days where day=%s", (day,))
        return self._day(r[0]) if r else None

    def days(self, days):
        rows = self.db.q("select day, sample, created_at, done_by, done_at from screen_quality_days where day = any(%s)", (list(days),))
        return {r[0]: self._day(r[1:]) for r in rows}

    def ensure(self, day, grow):
        from psycopg.types.json import Jsonb

        def go(c):
            c.execute("insert into screen_quality_days(day, sample, created_at) values (%s, %s, %s) on conflict (day) do nothing",
                      (day, Jsonb([]), self.clock()))
            r = c.execute("select sample, created_at, done_by, done_at from screen_quality_days where day=%s for update", (day,)).fetchone()
            rec = self._day(r)
            if not rec["done_by"]:
                new = grow(list(rec["sample"]))
                if new != rec["sample"]:
                    c.execute("update screen_quality_days set sample=%s where day=%s", (Jsonb(new), day))
                    rec["sample"] = new
            return rec
        return self.db.run(go, tx=True)

    def ratings(self, days):
        rows = self.db.q("select day, item_key, agent, brand, score, checks, note, rated_by, rated_at from screen_quality_ratings "
                         "where day = any(%s)", (list(days),))
        return [{"day": r[0], "key": r[1], "agent": r[2], "brand": r[3], "score": r[4], "checks": r[5], "note": r[6], "by": r[7], "at": r[8]}
                for r in rows]

    def rate(self, day, key, agent, brand, score, checks, note, by):
        from psycopg.types.json import Jsonb
        at = self.clock()
        self.db.x("insert into screen_quality_ratings(day, item_key, agent, brand, score, checks, note, rated_by, rated_at) "
                  "values (%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (day, item_key) do update set score=excluded.score, checks=excluded.checks, "
                  "note=excluded.note, rated_by=excluded.rated_by, rated_at=excluded.rated_at",
                  (day, key, agent, brand, score, Jsonb(checks), note, by, at))
        return {"day": day, "key": key, "agent": agent, "brand": brand, "score": score, "checks": checks, "note": note, "by": by, "at": at}

    def done(self, day, by):
        def go(c):
            r = c.execute("select sample, created_at, done_by, done_at from screen_quality_days where day=%s for update", (day,)).fetchone()
            if not r:
                raise QualityError("quality_empty")
            rec = self._day(r)
            if rec["done_by"]:
                return rec, False
            keys = {x[0] for x in c.execute("select item_key from screen_quality_ratings where day=%s", (day,)).fetchall()}
            check_done(rec["sample"], keys)
            at = self.clock()
            c.execute("update screen_quality_days set done_by=%s, done_at=%s where day=%s", (by, at, day))
            rec["done_by"], rec["done_at"] = by, at
            return rec, True
        return self.db.run(go, tx=True)


# ---------------------------------------------------------------- the ticket view of one item

def _msgs(conv):
    out = []
    for m in conv if isinstance(conv, list) else []:
        if not isinstance(m, dict):
            continue
        ts = dashboard.parse_ts(m.get("at"))
        if ts is None:
            continue
        out.append({"who": str(m.get("who") or ""), "ts": ts, "text": str(m.get("text") or "")[:TEXT_MAX]})
    out.sort(key=lambda m: m["ts"])
    return out


def item_view(item, full):
    """-> {customer: [{at, text}], sent: {at, text}|None, draft: {text, same}|None, ...}. Pure (the tests feed it tickets)."""
    ex = (full or {}).get("extras") or {}
    msgs = _msgs(ex.get("conversation"))
    ts = float(item["ts"])
    sent = None
    if item["kind"] == "send":
        ours = [m for m in msgs if m["who"] in OURS and abs(m["ts"] - ts) <= MATCH_S]
        if ours:
            sent = min(ours, key=lambda m: abs(m["ts"] - ts))
    cut = sent["ts"] if sent else ts + 5
    before = [m for m in msgs if m["ts"] <= cut and m is not sent]
    cust = []
    for m in reversed(before):                       # the customer's messages since our previous reply (the question this reply answered)
        if m["who"] in OURS:
            if cust:
                break
            continue
        if m["who"] == "customer":
            cust.append(m)
        if len(cust) >= 3:
            break
    cust.reverse()
    ai = ex.get("aiDraft") if isinstance(ex.get("aiDraft"), dict) else None
    draft = None
    if ai and str(ai.get("text") or "").strip():
        txt = str(ai["text"])[:TEXT_MAX]
        draft = {"text": txt, "same": (overlap(txt, sent["text"]) >= SAME) if sent else None,
                 "overlap": round(overlap(txt, sent["text"]), 3) if sent else None}
    iso = lambda t: datetime.fromtimestamp(t, dashboard.TZ).isoformat(timespec="minutes")     # noqa: E731
    t = (full or {}).get("ticket") or {}
    return {"customer": [{"at": iso(m["ts"]), "text": m["text"]} for m in cust],
            "sent": {"at": iso(sent["ts"]), "text": sent["text"]} if sent else None,
            "draft": draft, "status": str(t.get("status") or ""), "subject": str(t.get("subject") or "")[:200]}


# ---------------------------------------------------------------- routes

def register(app, d):
    """d: api_user, json_error, ui_lang, is_manager, store (users), quality (store), log (ActivityLog), cache (TicketCache), engines."""
    q, users, log, cache = d["quality"], d["store"], d["log"], d["cache"]
    ev_cache, ev_lock = {}, threading.Lock()
    app.extensions["cs"]["quality_events"] = ev_cache      # tests clear it instead of waiting out the 60 s

    def now():
        return log.clock()

    def events(day, today):
        """A finished day's events are kept 10 min, today's 60 s (two instances during a deploy: each reads the same table)."""
        ttl = 60 if day >= today else 600
        with ev_lock:
            hit = ev_cache.get(day)
            if hit and now() - hit[0] < ttl:
                return hit[1]
        ev = log.events(day)
        with ev_lock:
            ev_cache[day] = (now(), ev)
            for k in [k for k in ev_cache if k < (date.fromisoformat(today) - timedelta(days=SCORE_DAYS + 2)).isoformat()]:
                ev_cache.pop(k, None)
        return ev

    def roster():
        all_ = users.all()
        names = {u["username"]: u.get("display_name") or u["username"] for u in all_}
        agents = {u["username"] for u in all_ if "agent" in (u.get("roles") or []) and not dashboard.is_test_user(u["username"])}
        return names, agents

    def manager_or_err():
        u, err = d["api_user"]()
        if err:
            return None, err
        if not d["is_manager"](u):                   # admin + user-manager (the CS manager agent-two is both); never an agent or the viewer
            return None, d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        return u, None

    def brands_of(u):
        return [b for b in u.get("brands", []) if b in d["engines"]]

    def outcomes_for(days, today):
        evs = []
        for dd in [(date.fromisoformat(days[0]) - timedelta(days=1)).isoformat()] + list(days):   # the day before: a close's lookback
            evs.extend(events(dd, today))
        return analyse(evs)

    def ensure_today(today, agents):
        outs = outcomes_for([today], today)
        cands = candidates(outs, today, agents)
        return q.ensure(today, lambda sample: top_up(today, sample, cands)), outs

    def public_day(rec, names):
        if not rec:
            return None
        return {"done": bool(rec.get("done_by")), "done_by": rec.get("done_by") or "", "done_by_name": names.get(rec.get("done_by")) or rec.get("done_by") or "",
                "done_at": rec.get("done_at"), "n": len(rec.get("sample") or [])}

    def day_arg(today):
        dd = request.args.get("day") or today
        if not DAY_RE.match(dd):
            return None
        try:
            if date.fromisoformat(dd) > date.fromisoformat(today):
                return None
        except ValueError:
            return None
        return dd

    def no_store(resp):
        resp.headers["Cache-Control"] = "no-store, private"
        return resp

    @app.get("/api/dash/quality/status")
    def quality_status():
        u, err = manager_or_err()
        if err:
            return err
        today = dashboard.il_day(now())
        names, agents = roster()
        rec, _ = ensure_today(today, agents)
        mine = [it for it in rec["sample"] if it["brand"] in brands_of(u)]
        rated = {r["key"] for r in q.ratings([today])}
        hour = datetime.fromtimestamp(now(), dashboard.TZ).hour
        done = bool(rec.get("done_by"))
        return no_store(jsonify({"ok": True, "day": today, "n": len(mine), "rated": sum(1 for it in mine if it["key"] in rated),
                                 "done": done, "day_rec": public_day(rec, names), "remind_hour": remind_hour(),
                                 "remind_modal": bool(mine) and not done and hour >= remind_hour()}))

    @app.get("/api/dash/quality")
    def quality_board():
        u, err = manager_or_err()
        if err:
            return err
        lang = d["ui_lang"](u)
        today = dashboard.il_day(now())
        dd = day_arg(today)
        if not dd:
            return d["json_error"]("bad_request", 400, lang)
        names, agents = roster()
        brands = brands_of(u)
        rec = ensure_today(today, agents)[0] if dd == today else q.day(dd)
        days = [(date.fromisoformat(today) - timedelta(days=i)).isoformat() for i in range(SCORE_DAYS - 1, -1, -1)]
        ratings = [r for r in q.ratings(sorted(set(days + [dd]))) if r["brand"] in brands]     # never another brand's rating (Codex 2026-11-12)
        by_key = {r["key"]: r for r in ratings if r["day"] == dd}
        items = []
        for it in (rec or {}).get("sample") or []:
            if it["brand"] not in brands:
                continue
            r = by_key.get(it["key"])
            items.append(dict(it, agent_name=names.get(it["agent"]) or it["agent"],
                              rating={"score": r["score"], "checks": r["checks"], "note": r["note"], "by": names.get(r["by"]) or r["by"], "at": r["at"]} if r else None))
        recs = q.days(days)
        hist = [dict(public_day(recs.get(x), names) or {"done": False, "n": 0}, day=x) for x in days]
        table = agent_table(outcomes_for(days, today), ratings, agents, days, set(brands), names)
        return no_store(jsonify({"ok": True, "day": dd, "today": today, "items": items, "day_rec": public_day(rec, names), "history": hist,
                                 "agents": table, "per_group": PER_GROUP, "max_per_agent": MAX_PER_AGENT, "max_total": MAX_TOTAL,
                                 "score_days": SCORE_DAYS, "checks": list(CHECKS)}))

    def find_item(u, dd, key):
        rec = q.day(dd)
        for it in (rec or {}).get("sample") or []:
            if it["key"] == key and it["brand"] in brands_of(u):
                return it, rec
        return None, rec

    @app.get("/api/dash/quality/item")
    def quality_item():
        u, err = manager_or_err()
        if err:
            return err
        lang = d["ui_lang"](u)
        today = dashboard.il_day(now())
        dd, key = day_arg(today), request.args.get("key") or ""
        if not dd or not KEY_RE.match(key):
            return d["json_error"]("bad_request", 400, lang)
        it, _ = find_item(u, dd, key)
        if not it:
            return d["json_error"]("quality_not_in_sample", 404, lang)
        full, e, _meta = cache.get_ticket(u, it["brand"], it["tid"])
        if not full:                                  # the engine did not answer in time / not found: said on the card, the rating still works
            code = str((e or {}).get("error") or "engine_error")
            return no_store(jsonify({"ok": False, "error": code, "msg": (e or {}).get("msg") or messages.proxy_msg(code, lang)}))
        return no_store(jsonify(dict(item_view(it, full), ok=True, key=key, untouched=it.get("untouched"), kind=it["kind"])))

    @app.post("/api/dash/quality/rate")
    def quality_rate():
        u, err = manager_or_err()
        if err:
            return err
        lang = d["ui_lang"](u)
        b = request.get_json(silent=True)
        if not isinstance(b, dict):
            return d["json_error"]("bad_request", 400, lang)
        today = dashboard.il_day(now())
        dd, key, score, checks, note = b.get("day"), b.get("key"), b.get("score"), b.get("checks"), b.get("note", "")
        if not isinstance(dd, str) or not DAY_RE.match(dd) or dd > today or not isinstance(key, str) or not KEY_RE.match(key):
            return d["json_error"]("bad_request", 400, lang)
        if type(score) is not int or not 1 <= score <= 5:
            return d["json_error"]("quality_bad_rating", 400, lang)
        if not isinstance(checks, dict) or set(checks) != set(CHECKS) or not all(isinstance(v, bool) for v in checks.values()):
            return d["json_error"]("quality_bad_rating", 400, lang)
        note = note.strip() if isinstance(note, str) else None
        if note is None or len(note) > NOTE_MAX:
            return d["json_error"]("quality_bad_note", 400, lang)
        it, _ = find_item(u, dd, key)
        if not it:
            return d["json_error"]("quality_not_in_sample", 404, lang)
        rec = q.rate(dd, key, it["agent"], it["brand"], score, {c: checks[c] for c in CHECKS}, note, u["username"])
        users.audit(u["username"], "quality_rated", key, {"day": dd, "agent": it["agent"], "brand": it["brand"], "score": score,
                                                           "checks": {c: checks[c] for c in CHECKS}, "note_chars": len(note)})
        return jsonify({"ok": True, "rating": {"score": rec["score"], "checks": rec["checks"], "note": rec["note"],
                                               "by": u.get("display_name") or u["username"], "at": rec["at"]}})

    @app.post("/api/dash/quality/done")
    def quality_done():
        u, err = manager_or_err()
        if err:
            return err
        lang = d["ui_lang"](u)
        b = request.get_json(silent=True)
        today = dashboard.il_day(now())
        dd = b.get("day") if isinstance(b, dict) else None
        if not isinstance(dd, str) or not DAY_RE.match(dd) or dd > today:
            return d["json_error"]("bad_request", 400, lang)
        rec = q.day(dd)
        if rec and any(it["brand"] not in brands_of(u) for it in rec.get("sample") or []) and not rec.get("done_by"):
            return d["json_error"]("quality_other_brands", 403, lang)
        try:
            rec, changed = q.done(dd, u["username"])
        except QualityError as e:
            return d["json_error"](e.code, 409, lang, **e.kw)
        names, _ = roster()
        if changed:
            users.audit(u["username"], "quality_day_done", dd, {"items": len(rec.get("sample") or [])})
        return jsonify({"ok": True, "day_rec": public_day(rec, names), "changed": changed})
