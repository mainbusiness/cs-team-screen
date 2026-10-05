"""Managers' dashboard (Owner, 2026-10-06): REAL work time, not login time.

Activity log: every agent action the screen sees (open a ticket, edit, send, close, cancel, re-send, ...) is appended to
a per-day file on the private disk — user, brand, ticket id, channel, kind, time. No customer content, ever.
Work sessions are cut from it: actions no more than IDLE_GAP_S apart belong to one session; a longer gap ends it (the
agent was not working). Being logged in is NOT work; it is measured separately (presence) only to compute occupancy.
Sends and closes are also counted from the ENGINE (handled_by / handled_at on the ticket list) and shown side by side.

Everything here reads the activity log and the server's cached ticket lists: the dashboard makes no engine call of its own.
"""
import json
import os
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from concurrent.futures import ThreadPoolExecutor

from flask import g, jsonify, request

import engine_proxy

TZ = ZoneInfo("Asia/Jerusalem")
IDLE_GAP_S = 300            # two actions at most 5 min apart are one work session; a longer gap ends it (documented in README)
SESSION_TAIL_S = 60         # credited after a session's LAST action (reading / typing that produced no event of its own)
HANDLE_MAX_S = 2 * 3600     # an open more than 2 h before a send is not that reply's handle time
DEDUPE_S = {"open": 60, "edit": 60}   # one "open"/"edit" per user+ticket per minute (retries, autosave, typing heartbeats)
KINDS = ("open", "edit", "send", "resend", "close", "cancel", "autocancel", "note", "takeover", "review")
REPLY_KINDS = ("send", "resend")
FN_KIND = {"apiSend": "send", "apiMarkHandled": "close", "apiClose": "close", "apiKachingCancel": "cancel",
           "apiAutoCancelApprove": "autocancel", "apiAutoCancelReject": "autocancel", "apiNote": "note",
           "apiWaTakeOver": "takeover", "apiSaveDraft": "edit", "apiAutoReplyReview": "review"}
OPEN_ST = ("ready", "action", "health", "delay")          # waiting for a person
LIVE_ST = OPEN_ST + ("bot", "wa_queued")                   # not finished
ANSWERED_ST = ("sent", "wa_queued")
AUTO_RE = re.compile(r"^(auto|auto[-_ ]?reply|autoreply|engine|bot)$", re.I)
AGING = (("0-4h", 0, 4 * 3600), ("4-24h", 4 * 3600, 86400), ("1-3d", 86400, 3 * 86400), ("3d+", 3 * 86400, None))
BOOT_CLOSED_MAX = 100       # apiBoot carries every open ticket + only the 100 most recent closed ones
# 2026 industry benchmarks (justcall / kayako / helply), shown next to each number
BENCH = {"frt_email_s": 24 * 3600, "frt_wa_s": 90, "aht_s": [240, 360], "occupancy": [0.75, 0.85],
         "sla_wa_s": 3600, "sla_email_s": 24 * 3600}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
# Owner, 2026-10-06: received / answered / closed / awaiting / FRT come from the engine's dayStats (computed from the
# conversations: our screen, Dondy directly, Gmail directly, bots, templates). The screen's own log is only "on-screen
# activity" (work time, AHT, hours). Read in the background, cached on disk; a running day is re-read every DS_TTL_S.
DS_TTL_S = 600
DS_MAX_CHUNKS = 40
VERIFY_NOTE = "✓ אומת מול השיחות 15/15 (וואטסאפ 10/10 · מייל 5/5) · rozela 2026-10-05"   # final live reconciliation
DS_FINAL_TTL_S = 6 * 3600   # a finished day is still re-read now and then: the engine can backfill (2026-10-06: 95 email replies)
SOURCES = {"fromSystem": ("agent", "auto"), "fromDondy": ("human", "bot", "template", "close"), "fromEmail": ("direct",)}
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------- time ----------

def il_day(ts):
    return datetime.fromtimestamp(ts, TZ).date().isoformat()


def day_start(d):
    y, m, dd = (int(x) for x in d.split("-"))
    return datetime(y, m, dd, tzinfo=TZ).timestamp()


def next_day(d):
    return (date.fromisoformat(d) + timedelta(days=1)).isoformat()


def prev_day(d):
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


def parse_ts(s):
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.timestamp()


# ---------- the log ----------

class ActivityLog:
    def __init__(self, root, clock=time.time):
        self.root, self.clock = root, clock
        os.makedirs(root, mode=0o700, exist_ok=True)
        os.chmod(root, 0o700)
        self.lock = threading.Lock()
        self.last = {}          # (user, brand, ticket, kind) -> ts   (dedupe of open / edit)
        self.present = {}       # (day, user) -> set(minute)          (presence: written once per minute)

    def _path(self, prefix, day):
        return os.path.join(self.root, "%s-%s.jsonl" % (prefix, day))

    def _append(self, path, obj):
        new = not os.path.exists(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if new:
            os.chmod(path, 0o600)

    def record(self, user, brand, tid, channel, kind, category=None, ts=None):
        if kind not in KINDS or not isinstance(user, str) or not isinstance(tid, str) or not ID_RE.match(tid):
            return False
        ts = self.clock() if ts is None else ts
        key = (user, brand, tid, kind)
        with self.lock:
            gap = DEDUPE_S.get(kind)
            if gap and ts - self.last.get(key, -1e18) < gap:
                return False
            self.last[key] = ts
            if len(self.last) > 50000:
                for k, _ in sorted(self.last.items(), key=lambda kv: kv[1])[:25000]:
                    self.last.pop(k, None)
            self._append(self._path("act", il_day(ts)), {"ts": round(ts, 3), "u": user, "b": brand, "t": tid,
                                                         "ch": channel or "", "k": kind, "cat": category or ""})
        return True

    def touch(self, user, ts=None):
        """The screen is open and polling for this user this minute (polls stop while the tab is hidden)."""
        ts = self.clock() if ts is None else ts
        minute = int(ts // 60)
        day = il_day(ts)
        with self.lock:
            s = self.present.setdefault((day, user), set())
            if minute in s:
                return
            s.add(minute)
            if len(self.present) > 2000:
                for k in sorted(self.present)[:1000]:
                    self.present.pop(k, None)
            self._append(self._path("pres", day), {"u": user, "m": minute})

    def _read(self, prefix, day):
        out = []
        try:
            with open(self._path(prefix, day), encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out

    def events(self, day):
        return [e for e in self._read("act", day) if isinstance(e.get("ts"), (int, float)) and e.get("k") in KINDS]

    def presence(self, day):
        out = {}
        for p in self._read("pres", day):
            if isinstance(p.get("m"), int) and isinstance(p.get("u"), str):
                out.setdefault(p["u"], set()).add(p["m"])
        return out

    def first_day(self):
        days = sorted(n[4:14] for n in os.listdir(self.root) if n.startswith("act-") and n.endswith(".jsonl"))
        return days[0] if days else None

    # daily snapshots (midnight Asia/Jerusalem): what the live brand overview said about that day
    def snap_path(self, day):
        return os.path.join(self.root, "snap-%s.json" % day)

    def read_snap(self, day):
        try:
            with open(self.snap_path(day), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def write_snap(self, day, obj):
        tmp = "%s.%d.tmp" % (self.snap_path(day), os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.snap_path(day))


# ---------- pure calculations (unit-tested) ----------

def intervals(evts, gap=IDLE_GAP_S, tail=SESSION_TAIL_S):
    """ONE user's events, sorted -> [(start, end, event)]: the time from each action to the next one when they are at most
    `gap` apart (the same session), else `tail` after it (the session ends). Each piece belongs to the action that began it."""
    out = []
    for i, e in enumerate(evts):
        nxt = evts[i + 1]["ts"] if i + 1 < len(evts) else None
        if nxt is not None and nxt - e["ts"] <= gap:
            out.append((e["ts"], nxt, e))
        else:
            out.append((e["ts"], e["ts"] + tail, e))
    return out


def sessions(evts, gap=IDLE_GAP_S, tail=SESSION_TAIL_S):
    """[(start, end)] of the work sessions (for display / tests)."""
    out = []
    for i, e in enumerate(evts):
        if i == 0 or e["ts"] - evts[i - 1]["ts"] > gap:
            out.append([e["ts"], e["ts"]])
        out[-1][1] = e["ts"]
    return [(s, e + tail) for s, e in out]


def clip(ivs, lo, hi):
    for s, e, ev in ivs:
        s2, e2 = max(s, lo), min(e, hi)
        if e2 > s2:
            yield s2, e2, ev


def split_hours(s, e):
    """Israel's offset is whole hours, so local hour boundaries are epoch multiples of 3600."""
    while s < e:
        cut = min(e, (int(s // 3600) + 1) * 3600)
        yield s, cut
        s = cut


def handle_times(evts):
    """ONE user's events, sorted -> [(send_event, seconds)]: from the user's latest open of that ticket to the send."""
    last_open, out = {}, []
    for e in evts:
        key = (e.get("b"), e.get("t"))
        if e["k"] == "open":
            last_open[key] = e["ts"]
        elif e["k"] in REPLY_KINDS:
            o = last_open.pop(key, None)
            if o is not None and 0 <= e["ts"] - o <= HANDLE_MAX_S:
                out.append((e, e["ts"] - o))
    return out


def _median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def arrived(r):
    """When the customer's message arrived. created_at is when the ENGINE stored the ticket — measured live 2026-10-05: a
    backfill at midnight stamped 289 of celesta's tickets "created today" for messages from late September."""
    ts = [x for x in (parse_ts(r.get("created_at")), parse_ts(r.get("waiting_since"))) if x is not None]
    return min(ts) if ts else None


def _resp_s(r):
    h = parse_ts(r.get("handled_at"))
    w = parse_ts(r.get("waiting_since"))
    c = parse_ts(r.get("created_at"))
    base = w if (w is not None and h is not None and w <= h) else c
    return None if h is None or base is None else max(0.0, h - base)


def is_wa(r):
    return str(r.get("channel") or "").lower() == "whatsapp"


WA_FAIL_STATES = ("failed", "unknown", "template_required")
# the engine's own failure lines (Api.gs apiWaSent). Older failures carry them WITHOUT the warning mark (live rozela 2026-10-06: 4)
WA_FAIL_TEXT = re.compile("^\\u26a0|בדקו בדונדי לפני שליחה חוזרת|חלון 24 השעות נסגר")


def wa_failed(r):
    """An open WhatsApp ticket whose last send failed: `wa_send` (state) when the row carries it, else the engine's action line."""
    if not is_wa(r) or r.get("status") not in OPEN_ST:
        return False
    st = str(r.get("wa_send") or "").split(":")[0]
    if st:
        return st in WA_FAIL_STATES
    return bool(WA_FAIL_TEXT.search(str(r.get("action") or "").strip()))


def overview(rows, day, now):
    """One brand, one Israel day, from its cached ticket list (open tickets are all there; closed ones only the last 100)."""
    lo, hi = day_start(day), day_start(next_day(day))
    inday = lambda ts: ts is not None and lo <= ts < hi          # noqa: E731
    received = [r for r in rows if inday(arrived(r))]
    answered = [r for r in rows if r.get("status") in ANSWERED_ST and inday(parse_ts(r.get("handled_at")))]
    closed = [r for r in rows if r.get("status") == "done" and inday(parse_ts(r.get("handled_at")))]
    awaiting = [r for r in rows if r.get("status") in OPEN_ST]
    aging = {k: 0 for k, _, _ in AGING}
    for r in awaiting:
        w = parse_ts(r.get("waiting_since")) or parse_ts(r.get("created_at"))
        if w is None:
            continue
        age = max(0, now - w)
        for k, a, b in AGING:
            if age >= a and (b is None or age < b):
                aging[k] += 1
    frt = {"email": [], "whatsapp": []}
    for r in answered:
        c, h = arrived(r), parse_ts(r.get("handled_at"))
        if inday(c) and h is not None and h >= c:
            frt["whatsapp" if is_wa(r) else "email"].append(h - c)
    auto = [r for r in answered if AUTO_RE.match(str(r.get("handled_by") or ""))]
    done_rows = [r for r in rows if r.get("status") not in LIVE_ST]
    oldest = min([parse_ts(r.get("handled_at")) or 0 for r in done_rows] or [0])
    return {
        "received": len(received), "answered": len(answered), "closed": len(closed),
        "answered_pct": _pct(len(answered), len(received)), "closed_pct": _pct(len(closed), len(received)),
        "open_now": sum(1 for r in rows if r.get("status") in LIVE_ST), "awaiting": len(awaiting), "aging": aging,
        "frt_median_s": _median(frt["email"] + frt["whatsapp"]), "frt_email_s": _median(frt["email"]),
        "frt_wa_s": _median(frt["whatsapp"]), "auto_pct": _pct(len(auto), len(answered)),
        "wa_failed": sum(1 for r in rows if wa_failed(r)),
        # the list holds only the last 100 closed tickets: if all of them are from this day, the day had more
        "truncated": len(done_rows) >= BOOT_CLOSED_MAX and oldest >= lo,
    }


def ds_overview(o, ds):
    """Replace the list-based day numbers with the engine's dayStats (the conversations themselves)."""
    rec, ans, clo = ds.get("received") or {}, ds.get("answered") or {}, ds.get("closedToday") or {}
    aw, frt = ds.get("awaitingNow") or {}, ds.get("frt") or {}
    mins = lambda x: None if not isinstance(x, dict) or x.get("medianMin") is None else round(x["medianMin"] * 60.0, 1)  # noqa: E731
    hum = frt.get("human") if isinstance(frt.get("human"), dict) else (ds.get("frtHuman") if isinstance(ds.get("frtHuman"), dict) else None)
    hbc = frt.get("humanByChannel") if isinstance(frt.get("humanByChannel"), dict) else {}
    src = ds.get("sources") or {}
    auto = (((src.get("answered") or {}).get("fromSystem") or {}).get("auto")) or 0
    n_ans = ans.get("total") or 0
    o = dict(o, received=rec.get("total", 0), answered=n_ans, closed=clo.get("total", 0),
             answered_pct=_pct(n_ans, rec.get("total", 0)), closed_pct=_pct(clo.get("total", 0), rec.get("total", 0)),
             awaiting=aw.get("total", o.get("awaiting")), frt_median_s=mins(frt.get("all")), frt_email_s=mins(frt.get("email")),
             frt_wa_s=mins(frt.get("whatsapp")),
             frt_human_s=mins(hum), frt_human_email_s=mins(hbc.get("email")), frt_human_wa_s=mins(hbc.get("whatsapp")),
             frt_human_known=hum is not None,
             # engine @47/48: Gmail can be blocked for a while -> email numbers are null (unknown), totals are WhatsApp only
             email_status=(ds.get("sourceStatus") or {}).get("email") or "ok",
             totals_exclude_email=bool(ds.get("totalsExcludeEmail")),
             frt_human_n={"email": (hbc.get("email") or {}).get("n", 0), "whatsapp": (hbc.get("whatsapp") or {}).get("n", 0),
                          "all": (hum or {}).get("n", 0)},
             frt_n={"email": (frt.get("email") or {}).get("n", 0), "whatsapp": (frt.get("whatsapp") or {}).get("n", 0)},
             auto_pct=_pct(auto, n_ans), truncated=False, sources=src, by_channel={"received": rec, "answered": ans, "closed": clo},
             stats="dayStats")
    return o


def _sum_sources(tables):
    out = {}
    for t in tables:
        for metric in ("answered", "closed", "replies"):
            m = out.setdefault(metric, {k: {s: 0 for s in subs + ("total",)} for k, subs in SOURCES.items()})
            for k, subs in SOURCES.items():
                for s in subs + ("total",):
                    m[k][s] += int((((t or {}).get(metric) or {}).get(k) or {}).get(s) or 0)
    return out


def build(log, rows_by_brand, users, brands, end_day, ndays, now, ds_by_brand=None):
    """The whole dashboard for the viewer's brands. rows_by_brand: {brand: [summary rows]} (cached lists)."""
    ds_by_brand = ds_by_brand or {}
    days = [(date.fromisoformat(end_day) - timedelta(days=i)).isoformat() for i in reversed(range(ndays))]
    lo, hi = day_start(days[0]), min(day_start(next_day(days[-1])), max(now, day_start(days[0])))
    evts = []
    for d in [prev_day(days[0])] + days + [next_day(days[-1])]:   # both neighbours: sessions that cross midnight
        evts.extend(e for e in log.events(d) if e.get("b") in brands)
    evts.sort(key=lambda e: e["ts"])
    row_of = {(b, r.get("id")): r for b, rs in rows_by_brand.items() for r in rs}
    present = {}
    for d in days:
        for u, mins in log.presence(d).items():
            present.setdefault(u, set()).update(m for m in mins if lo <= m * 60 < hi)

    by_user = {}
    for e in evts:
        by_user.setdefault(e.get("u"), []).append(e)
    names = {u["username"]: (u.get("display_name") or u["username"]) for u in users}
    roster = {u["username"] for u in users if not u.get("disabled") and set(u.get("roles", [])) & {"agent", "admin"}
              and set(u.get("brands", [])) & set(brands)}
    pie_brand, pie_chan, pie_cat = {}, {}, {}
    heat = {}                     # user -> {day: [24 seconds]}
    hour_total = [0.0] * 24
    agents, all_handles, sent_tickets = [], [], {}
    for user in sorted(roster | {u for u in by_user if isinstance(u, str)}):
        ue = by_user.get(user, [])
        per_day = {d: {"active_s": 0.0, "sends": 0, "closes": 0} for d in days}
        by_b, by_c = {}, {}
        uh = heat.setdefault(user, {d: [0.0] * 24 for d in days})
        active = 0.0
        for s, e, ev in clip(intervals(ue), lo, hi):
            for hs, he in split_hours(s, e):
                d = il_day(hs)
                if d not in per_day:
                    continue
                dur = he - hs
                hr = datetime.fromtimestamp(hs, TZ).hour
                per_day[d]["active_s"] += dur
                uh[d][hr] += dur
                hour_total[hr] += dur
            dur = e - s
            active += dur
            b, ch = ev.get("b") or "", "whatsapp" if ev.get("ch") == "whatsapp" else "email"
            cat = ev.get("cat") or (row_of.get((b, ev.get("t"))) or {}).get("category") or "other"
            by_b.setdefault(b, {"active_s": 0.0, "sends": 0, "closes": 0})["active_s"] += dur
            by_c.setdefault(ch, {"active_s": 0.0, "sends": 0, "closes": 0})["active_s"] += dur
            pie_brand[b] = pie_brand.get(b, 0) + dur
            pie_chan[ch] = pie_chan.get(ch, 0) + dur
            pie_cat[cat] = pie_cat.get(cat, 0) + dur
        inr = [e for e in ue if lo <= e["ts"] < hi]
        sends = [e for e in inr if e["k"] in REPLY_KINDS]
        closes = [e for e in inr if e["k"] == "close"]
        for e in sends + closes:
            k = "sends" if e["k"] in REPLY_KINDS else "closes"
            per_day[il_day(e["ts"])][k] += 1
            ch = "whatsapp" if e.get("ch") == "whatsapp" else "email"
            by_b.setdefault(e.get("b") or "", {"active_s": 0.0, "sends": 0, "closes": 0})[k] += 1
            by_c.setdefault(ch, {"active_s": 0.0, "sends": 0, "closes": 0})[k] += 1
        for e in sends:
            sent_tickets.setdefault((e.get("b"), e.get("t")), []).append(e["ts"])
        hts = [x for ev, x in handle_times(ue) if lo <= ev["ts"] < hi]
        all_handles.extend(hts)
        eng_s = eng_c = 0                       # the engine's own record (handled_by / handled_at)
        for b, rs in rows_by_brand.items():
            for r in rs:
                if r.get("handled_by") != user:
                    continue
                h = parse_ts(r.get("handled_at"))
                if h is None or not lo <= h < hi:
                    continue
                if r.get("status") in ANSWERED_ST:
                    eng_s += 1
                elif r.get("status") == "done":
                    eng_c += 1
        pres_s = len(present.get(user, ())) * 60
        agents.append({
            "user": user, "name": names.get(user, user), "active_s": round(active), "sends": len(sends),
            "resends": sum(1 for e in sends if e["k"] == "resend"), "closes": len(closes),
            "per_hour": round(len(sends) / (active / 3600.0), 1) if active >= 300 else None,
            "aht_s": _median(hts), "handled": len(hts), "present_s": pres_s,
            "occupancy": round(min(1.0, active / pres_s), 3) if pres_s else None,
            "engine_sends": eng_s, "engine_closes": eng_c,
            "by_brand": {k: dict(v, active_s=round(v["active_s"])) for k, v in by_b.items()},
            "by_channel": {k: dict(v, active_s=round(v["active_s"])) for k, v in by_c.items()},
            "days": [dict(day=d, active_s=round(v["active_s"]), sends=v["sends"], closes=v["closes"]) for d, v in per_day.items()],
        })
    by_sender = {}
    for ds in ds_by_brand.values():
        for k, v in ((((ds or {}).get("data") or {}).get("attribution") or {}).get("bySender") or {}).items():
            by_sender[k] = by_sender.get(k, 0) + int(v or 0)
    known = {u["username"] for u in users}
    for k in list(by_sender):
        if k in known and k not in {a["user"] for a in agents}:      # a screen user outside the roster (e.g. an admin)
            agents.append({"user": k, "name": names.get(k, k), "active_s": 0, "sends": 0, "resends": 0, "closes": 0, "per_hour": None,
                           "aht_s": None, "handled": 0, "present_s": 0, "occupancy": None, "engine_sends": 0, "engine_closes": 0,
                           "by_brand": {}, "by_channel": {}, "days": []})
    for a in agents:
        a["ds_answered"] = by_sender.get(a["user"])
    agents.sort(key=lambda a: (-(a.get("ds_answered") or 0), -a["active_s"], -a["sends"], a["name"]))

    # brand overview for the end day: live from the cached list today, from the midnight snapshot for a past day
    today = il_day(now)
    brands_out = {}
    for b in brands:
        if end_day == today:
            brands_out[b] = dict(overview(rows_by_brand.get(b, []), end_day, now), source="live")
        else:
            snap = log.read_snap(end_day)
            if snap and b in (snap.get("brands") or {}):
                brands_out[b] = dict(snap["brands"][b], source="snapshot", snapshot_at=snap.get("at"))
            else:
                brands_out[b] = dict(overview(rows_by_brand.get(b, []), end_day, now), source="rebuilt")
        ds = ds_by_brand.get(b) or {}
        if ds.get("data"):
            brands_out[b] = dict(ds_overview(brands_out[b], ds["data"]), ds_at=ds.get("at"), ds_final=ds.get("final"))
        brands_out[b]["ds_busy"] = bool(ds.get("busy"))
        brands_out[b]["ds_error"] = ds.get("error")

    # KPIs over the range
    answered = [r for rs in rows_by_brand.values() for r in rs
                if r.get("status") in ANSWERED_ST and (lambda h: h is not None and lo <= h < hi)(parse_ts(r.get("handled_at")))]
    frt = {"email": [], "whatsapp": []}
    sla = {"email": [0, 0], "whatsapp": [0, 0]}
    for r in answered:
        ch = "whatsapp" if is_wa(r) else "email"
        c, h = arrived(r), parse_ts(r.get("handled_at"))
        if c is not None and lo <= c < hi and h >= c:
            frt[ch].append(h - c)
        rs_ = _resp_s(r)
        if rs_ is not None:
            sla[ch][1] += 1
            if rs_ <= (BENCH["sla_wa_s"] if ch == "whatsapp" else BENCH["sla_email_s"]):
                sla[ch][0] += 1
    reopened = single = 0
    for key, ts_list in sent_tickets.items():
        r = row_of.get(key) or {}
        w = parse_ts(r.get("waiting_since"))
        again = r.get("status") in OPEN_ST and w is not None and w > max(ts_list)
        reopened += again
        single += (len(ts_list) == 1 and not again)
    auto_n = sum(1 for r in answered if AUTO_RE.match(str(r.get("handled_by") or "")))
    agent_replies = max(sum(a["sends"] for a in agents), sum(a["engine_sends"] for a in agents))
    tot_active = sum(a["active_s"] for a in agents)
    tot_present = sum(a["present_s"] for a in agents)
    ds_ok = bool(brands) and all(o.get("stats") == "dayStats" for o in brands_out.values())
    ds_any = any(o.get("stats") == "dayStats" for o in brands_out.values())

    def wmean(key, ch, nkey="frt_n"):         # only brands counted from the conversations (never mixed with list proxies)
        pts = [(o.get(key), (o.get(nkey) or {}).get(ch, 0)) for o in brands_out.values()
               if o.get("stats") == "dayStats" and o.get(key) is not None]
        n = sum(w for _, w in pts)
        return round(sum(v * w for v, w in pts) / n, 1) if n else None
    kpis = {
        "frt_email_s": wmean("frt_email_s", "email") if ds_any else _median(frt["email"]),
        "frt_wa_s": wmean("frt_wa_s", "whatsapp") if ds_any else _median(frt["whatsapp"]),
        "frt_source": "dayStats" if ds_any else "list",
        # the owner via coordinator 2026-10-06: a bot's instant answer is not service — the person's first reply leads
        "frt_human_known": any(o.get("frt_human_known") for o in brands_out.values()),
        "frt_human_s": wmean("frt_human_s", "all", "frt_human_n"),
        "frt_human_email_s": wmean("frt_human_email_s", "email", "frt_human_n"),
        "frt_human_wa_s": wmean("frt_human_wa_s", "whatsapp", "frt_human_n"),
        "aht_s": _median(all_handles), "fcr_pct": _pct(single, len(sent_tickets)),
        "reopen_pct": _pct(reopened, len(sent_tickets)), "fcr_window_open": now - hi < 72 * 3600,
        "occupancy": round(min(1.0, tot_active / tot_present), 3) if tot_present else None,
        "backlog": sum(o["awaiting"] for o in brands_out.values()),
        "sla_wa_pct": _pct(*sla["whatsapp"]), "sla_email_pct": _pct(*sla["email"]),
        "sla_wa_n": sla["whatsapp"][1], "sla_email_n": sla["email"][1], "csat": None,
    }
    return {
        "ok": True, "generated_at": now, "end_day": end_day, "days": days, "brands": brands_out, "agents": agents,
        "heat": heat, "hour_total": [round(x) for x in hour_total], "kpis": kpis, "bench": BENCH,
        "pies": {"brand": {k: round(v) for k, v in pie_brand.items()}, "channel": {k: round(v) for k, v in pie_chan.items()},
                 "category": {k: round(v) for k, v in pie_cat.items()}, "who": {"agents": agent_replies, "auto": auto_n}},
        "idle_gap_s": IDLE_GAP_S, "session_tail_s": SESSION_TAIL_S, "log_since": log.first_day(),
        # Owner, 2026-10-06: agents also answer in Dondy / Gmail directly, so received/answered/closed/FRT come from the
        # engine's dayStats (computed from the conversations). Brands without it yet say "not final".
        "stats_source": "dayStats" if ds_ok else ("mixed" if any(o.get("stats") == "dayStats" for o in brands_out.values()) else "list"),
        "verify_note": VERIFY_NOTE if ds_any else None,
        "missing_ds": {b: o.get("ds_error") for b, o in brands_out.items() if o.get("stats") != "dayStats"},
        "sources": {"total": _sum_sources([o.get("sources") for o in brands_out.values() if o.get("sources")]),
                    "brands": {b: _sum_sources([o["sources"]]) for b, o in brands_out.items() if o.get("sources")}},
        "senders": by_sender,
    }


# ---------- Flask ----------

def register(app, d):
    """d: api_user, json_error, is_manager, store, cache, engines, log, ui_lang."""
    log, cache = d["log"], d["cache"]

    @app.before_request
    def presence():
        u = g.get("user")
        p = request.path
        if u and p.startswith("/api/") and not p.startswith(("/api/dash", "/api/manage", "/api/me")):
            log.touch(u["username"])

    def rows_for(u, brands):
        out = {}
        for b in brands:
            rows = cache.cached_rows(b)
            if not rows:
                _, lst = cache.get_list(u, b)          # nobody has opened this brand yet: one shared list read
                rows = {r.get("id"): r for r in (lst.get("tickets") or []) if isinstance(r, dict)} if lst.get("ok") else {}
            out[b] = list(rows.values())
        return out

    ds_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cs-daystats")
    ds_busy, ds_lock, ds_futs, ds_err = set(), threading.Lock(), [], {}

    def ds_path(b, day):
        return os.path.join(log.root, "ds-%s-%s.json" % (b, day))

    def ds_read(b, day):
        try:
            with open(ds_path(b, day), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def ds_fetch(u, b, day):
        """All chunks of one brand-day (the engine keeps the running totals; `next` is passed back as `cursor`)."""
        started = log.clock()
        try:
            cursor, data = 0, None
            for _ in range(DS_MAX_CHUNKS):
                args = {"date": day}
                if cursor:
                    args["cursor"] = cursor
                _, out = engine_proxy.call(d["engines"], cache.transport, cache.secret(), u, b, "apiDayStats", args, "he", internal=True)
                if not out.get("ok"):
                    ds_err[(b, day)] = out.get("error") or "error"
                    return
                data = out
                if out.get("partial") and isinstance(out.get("next"), int) and not isinstance(out.get("next"), bool):
                    cursor = out["next"]
                    continue
                break
            if data is None or data.get("partial"):
                ds_err[(b, day)] = "partial"
                return
            ds_err.pop((b, day), None)
            obj = {"at": started, "final": started >= day_start(next_day(day)), "data": {k: v for k, v in data.items() if not k.startswith("_")}}
            tmp = "%s.%d.tmp" % (ds_path(b, day), os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
            os.chmod(tmp, 0o600)
            os.replace(tmp, ds_path(b, day))
        finally:
            with ds_lock:
                ds_busy.discard(b)

    def ds_for(u, brands, day, now, force=False):
        out = {}
        for b in brands:
            e = ds_read(b, day) or {}
            age = now - float(e.get("at", 0))
            stale = force or not e or age > (DS_FINAL_TTL_S if e.get("final") else DS_TTL_S)
            with ds_lock:
                start = stale and b not in ds_busy       # one dayStats per brand at a time (its state is one property)
                if start:
                    ds_busy.add(b)
                busy = b in ds_busy
            if start:
                ds_futs.append(ds_pool.submit(ds_fetch, u, b, day))
                del ds_futs[:-50]
            out[b] = dict(e, busy=busy, error=ds_err.get((b, day)))
        return out

    def ds_drain(timeout=10):
        for f in list(ds_futs):
            f.result(timeout=timeout)

    @app.get("/api/dash")
    def dash():
        u, err = d["api_user"]()
        if err:
            return err
        if not d["is_manager"](u):
            return d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        rng = request.args.get("range", "1")
        ndays = {"1": 1, "7": 7, "30": 30}.get(rng)
        now = log.clock()
        end = request.args.get("date") or il_day(now)
        if ndays is None or not DAY_RE.match(end):
            return d["json_error"]("bad_request", 400, d["ui_lang"](u))
        try:
            if date.fromisoformat(end) > date.fromisoformat(il_day(now)):
                end = il_day(now)
        except ValueError:
            return d["json_error"]("bad_request", 400, d["ui_lang"](u))
        brands = [b for b in u.get("brands", []) if b in d["engines"]]
        force = request.args.get("refresh") == "1" and "admin" in u.get("roles", [])    # admin: re-read the day from the engine now
        return jsonify(build(log, rows_for(u, brands), d["store"].all(), brands, end, ndays, now, ds_for(u, brands, end, now, force)))

    @app.post("/api/<brand>/activity")
    def activity(brand):
        """The screen's own heartbeat while an agent types in a ticket (autosave alone waits for a pause)."""
        u, err = d["api_user"]()
        if err:
            return err
        brand = str(brand).lower()
        body = request.get_json(silent=True) or {}
        tid = body.get("id")
        if (brand not in u.get("brands", []) or brand not in d["engines"]                     # (Codex 2026-10-06)
                or not ("agent" in u.get("roles", []) or "admin" in u.get("roles", []))):
            return d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        if body.get("kind") != "edit" or not isinstance(tid, str) or not ID_RE.match(tid):
            return d["json_error"]("bad_request", 400, d["ui_lang"](u))
        note(u, brand, tid, "edit")
        return jsonify({"ok": True})

    def note(u, brand, tid, kind, channel=None):
        r = cache.cached_rows(brand).get(tid) or {}
        ch = "whatsapp" if (channel == "whatsapp" or is_wa(r)) else "email"
        log.record(u["username"], brand, tid, ch, kind, r.get("category"))

    def after_engine(u, brand, fn, body, out):
        kind = FN_KIND.get(fn)
        args = body.get("args") if isinstance(body.get("args"), dict) else {}
        if not kind or not out.get("ok") or out.get("already") or not isinstance(args.get("id"), str):
            return
        if kind == "send" and body.get("via") == "resend":
            kind = "resend"
        note(u, brand, args["id"], kind, args.get("channel"))

    def after_open(u, brand, tid):
        note(u, brand, tid, "open")

    app.extensions["cs"]["activity"] = {"log": log, "after_engine": after_engine, "after_open": after_open}

    def snapshot_once():
        """Midnight Asia/Jerusalem: keep what the live overview said about the day that just ended."""
        now = log.clock()
        y = prev_day(il_day(now))
        if log.read_snap(y):
            return False
        brands = sorted(d["engines"])
        rows = {b: list(cache.cached_rows(b).values()) for b in brands}
        log.write_snap(y, {"day": y, "at": now, "brands": {b: overview(rows[b], y, now) for b in brands}})
        return True

    app.extensions["cs"]["activity"]["snapshot_once"] = snapshot_once
    app.extensions["cs"]["activity"]["ds_drain"] = ds_drain
    if d.get("start_thread"):
        def loop():
            while True:
                time.sleep(60)
                try:
                    snapshot_once()
                except Exception:                     # noqa: BLE001 — a failed snapshot must never take the screen down
                    app.logger.exception("dashboard snapshot failed")
        threading.Thread(target=loop, name="cs-dash-snapshot", daemon=True).start()
