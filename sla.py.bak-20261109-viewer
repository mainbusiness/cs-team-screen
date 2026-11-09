"""SLA tracking for the CS managers (Owner, 2026-10-24; course law `brandon-support-sla-is-dispute-prevention`: fast support prevents chargebacks).

Targets (config, env SLA_CONFIG may override any key as JSON):
  first_reply_bh_h  4   — a customer waits at most 4 BUSINESS hours for a person's reply
  resolution_h      36  — a ticket is resolved within 36 hours (calendar hours)
  warn_ratio        .75 — "about to breach" from 75% of either target

Business hours (Asia/Jerusalem). Not defined anywhere in the engine except the desk CLOSE (engine/DayStats.gs DS_SERVICE_CLOSE_HOUR = 17).
Measured from the agents' activity log 2026-09-25..10-24: team works Sun-Fri, 09:00-17:00, Friday ends ~13:00-14:00, Saturday ~0.
Default below: Sun-Thu 09:00-17:00, Fri 09:00-13:00, Sat closed.  Python weekday: Mon=0 .. Sun=6.

Data: the server's cached ticket lists (no engine call of its own). A row carries waiting_since (the customer's latest unanswered message),
created_at, handled_at / handled_by (the LAST handling) and status. So:
  - OPEN tickets (ready / action / health / delay = the agents' "פתוחות") are measured live: business seconds since waiting_since.
  - COMPLETED numbers are a proxy from the rows the list holds (every open one, only the last ~100 closed): first reply = waiting_since -> handled_at
    of a ticket a person answered (status sent / wa_queued); resolution = waiting_since -> handled_at of a ticket a person closed (done).
No customer text and no names ever leave this module: ids, counts and times only.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import jsonify

TZ = ZoneInfo("Asia/Jerusalem")
OPEN_ST = ("ready", "action", "health", "delay")
ANSWERED_ST = ("sent", "wa_queued")
AUTO_RE = re.compile(r"^(auto|auto[-_ ]?reply|autoreply|engine|bot|template)$", re.I)
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LIVE_SYNC_S = 30
ALERT_MAX = 25

DEFAULT = {
    "first_reply_bh_h": 4.0,
    "resolution_h": 36.0,
    "warn_ratio": 0.75,
    "window_days": 7,
    # weekday (Mon=0..Sun=6) -> [open_hour, close_hour] Israel time; missing = closed
    "hours": {"6": [9, 17], "0": [9, 17], "1": [9, 17], "2": [9, 17], "3": [9, 17], "4": [9, 13]},
    "hours_source": "default: Sun-Thu 09-17, Fri 09-13 (close 17:00 = engine DS_SERVICE_CLOSE_HOUR; the rest measured from the activity log)",
}


def config(env=None):
    cfg = json.loads(json.dumps(DEFAULT))
    raw = (env if env is not None else os.environ).get("SLA_CONFIG")
    if raw:
        try:
            over = json.loads(raw)
        except ValueError:
            over = {}
        for k in ("first_reply_bh_h", "resolution_h", "warn_ratio", "window_days"):
            if isinstance(over.get(k), (int, float)) and not isinstance(over.get(k), bool) and over[k] > 0:
                cfg[k] = float(over[k])
        h = over.get("hours")
        if isinstance(h, dict):
            clean = {}
            for k, v in h.items():
                if str(k) in ("0", "1", "2", "3", "4", "5", "6") and isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and 0 <= v[0] < v[1] <= 24:
                    clean[str(k)] = [v[0], v[1]]
            cfg["hours"] = clean
            cfg["hours_source"] = "SLA_CONFIG"
    return cfg


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


def il_day(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d")


def _at(day, hour):
    """Epoch of `hour` (may be fractional) on a local date, DST-safe."""
    base = datetime(day.year, day.month, day.day, tzinfo=TZ)
    return (base.replace(hour=int(hour), minute=int(round((hour - int(hour)) * 60))) if hour < 24 else base + timedelta(days=1)).timestamp()


def bh_seconds(a, b, cfg=None):
    """Business seconds between two epochs (0 when b <= a). Capped at 400 days."""
    cfg = cfg or DEFAULT
    if a is None or b is None or b <= a:
        return 0.0
    day = datetime.fromtimestamp(a, TZ).date()
    last = datetime.fromtimestamp(b, TZ).date()
    total, n = 0.0, 0
    while day <= last and n < 400:
        w = cfg["hours"].get(str(day.weekday()))
        if w:
            lo, hi = max(a, _at(day, w[0])), min(b, _at(day, w[1]))
            if hi > lo:
                total += hi - lo
        day += timedelta(days=1)
        n += 1
    return total


def in_hours(now, cfg=None):
    cfg = cfg or DEFAULT
    d = datetime.fromtimestamp(now, TZ)
    w = cfg["hours"].get(str(d.weekday()))
    return bool(w) and _at(d.date(), w[0]) <= now < _at(d.date(), w[1])


def is_human(r):
    by = str(r.get("handled_by") or "").strip()
    return bool(by) and not AUTO_RE.match(by) and parse_ts(r.get("handled_at")) is not None


def _base(r):
    """When the customer's request that this handling answered started waiting."""
    h = parse_ts(r.get("handled_at"))
    w = parse_ts(r.get("waiting_since"))
    c = parse_ts(r.get("created_at"))
    if h is None:
        return None
    return w if (w is not None and w <= h) else (c if (c is not None and c <= h) else None)


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _is_wa(r):
    return str(r.get("channel") or "").lower() == "whatsapp"


def judge_open(r, now, cfg):
    """One open ticket: its waiting time and which target it is at. Returns None for a row that has no clock at all."""
    w = parse_ts(r.get("waiting_since")) or parse_ts(r.get("created_at"))
    if w is None or w > now:
        return None
    wait_bh = bh_seconds(w, now, cfg)
    wall_h = (now - w) / 3600.0
    fr = wait_bh / (cfg["first_reply_bh_h"] * 3600.0)
    rs = wall_h / cfg["resolution_h"]
    why = [k for k, v in (("reply", fr), ("resolution", rs)) if v >= 1]
    state = "breach" if why else "ok"
    if not why:
        why = [k for k, v in (("reply", fr), ("resolution", rs)) if v >= cfg["warn_ratio"]]
        state = "risk" if why else "ok"
    return {"state": state, "why": why, "wait_bh_s": round(wait_bh), "wall_h": round(wall_h, 1), "reply_pct": round(100 * fr), "res_pct": round(100 * rs),
            "kind": "followup" if is_human(r) else "first"}


def _stat(vals, limit):
    n = len(vals)
    return {"n": n, "median": _median(vals), "within": sum(1 for v in vals if v <= limit), "within_pct": round(100.0 * sum(1 for v in vals if v <= limit) / n, 1) if n else None}


def completed(rows, lo, hi, cfg):
    """First-reply and resolution times of tickets a PERSON handled in [lo, hi). Per agent too."""
    fr, rs, by_agent = [], [], {}
    for r in rows:
        if not isinstance(r, dict) or not is_human(r):
            continue
        h = parse_ts(r.get("handled_at"))
        if h is None or not (lo <= h < hi):
            continue
        b = _base(r)
        if b is None:
            continue
        st = r.get("status")
        agent = str(r.get("handled_by"))
        rec = by_agent.setdefault(agent, {"fr": [], "rs": []})
        if st in ANSWERED_ST:
            v = bh_seconds(b, h, cfg)
            fr.append(v)
            rec["fr"].append(v)
        elif st == "done":
            v = (h - b) / 3600.0
            rs.append(v)
            rec["rs"].append(v)
    lim_f, lim_r = cfg["first_reply_bh_h"] * 3600.0, cfg["resolution_h"]
    return {"first_reply": _stat(fr, lim_f), "resolution": _stat(rs, lim_r),
            "agents": {a: {"first_reply": _stat(v["fr"], lim_f), "resolution": _stat(v["rs"], lim_r)} for a, v in by_agent.items()}}


def brand_view(rows, now, cfg):
    rows = [r for r in rows if isinstance(r, dict)]
    open_rows = [r for r in rows if r.get("status") in OPEN_ST]
    counts = {"open": 0, "breach": 0, "risk": 0, "ok": 0, "unknown": 0, "breach_whatsapp": 0, "breach_email": 0, "first": 0, "followup": 0}
    alerts, oldest = [], None
    for r in open_rows:
        j = judge_open(r, now, cfg)
        counts["open"] += 1
        if j is None:
            counts["unknown"] += 1
            continue
        counts[j["state"]] += 1
        counts[j["kind"]] += 1
        if j["state"] == "breach":
            counts["breach_whatsapp" if _is_wa(r) else "breach_email"] += 1
        if oldest is None or j["wait_bh_s"] > oldest["wait_bh_s"]:
            oldest = {"id": r.get("id"), "ch": "whatsapp" if _is_wa(r) else "email", "wait_bh_s": j["wait_bh_s"], "wall_h": j["wall_h"]}
        if j["state"] != "ok":
            alerts.append({"id": r.get("id"), "ch": "whatsapp" if _is_wa(r) else "email", "state": j["state"], "why": j["why"], "kind": j["kind"],
                           "wait_bh_s": j["wait_bh_s"], "wall_h": j["wall_h"], "reply_pct": j["reply_pct"], "res_pct": j["res_pct"]})
    today = il_day(now)
    day_lo = _at(datetime.fromisoformat(today).date(), 0)
    win_lo = now - cfg["window_days"] * 86400
    return {"counts": counts, "oldest": oldest, "alerts": alerts,
            "today": completed(rows, day_lo, now + 1, cfg), "window": completed(rows, win_lo, now + 1, cfg)}


def day_summary(rows, day, now, cfg):
    """What the midnight snapshot keeps for a finished day: the completed numbers of that day + the live counts at the time."""
    lo = _at(datetime.fromisoformat(day).date(), 0)
    v = brand_view(rows, now, cfg)
    c = completed(rows, lo, lo + 86400, cfg)
    return {"day": day, "first_reply": c["first_reply"], "resolution": c["resolution"], "open_breach": v["counts"]["breach"], "open_risk": v["counts"]["risk"], "open": v["counts"]["open"]}


def build(rows_by_brand, now, cfg=None):
    cfg = cfg or config()
    brands = {b: brand_view(rows, now, cfg) for b, rows in rows_by_brand.items()}
    tot = {k: sum(v["counts"][k] for v in brands.values()) for k in ("open", "breach", "risk", "ok", "unknown", "breach_whatsapp", "breach_email", "first", "followup")}
    allrows = [r for rows in rows_by_brand.values() for r in rows]
    alerts = []
    for b, v in brands.items():
        for a in v["alerts"]:
            alerts.append(dict(a, brand=b))
    alerts.sort(key=lambda a: (0 if a["state"] == "breach" else 1, -a["wait_bh_s"]))
    olds = [dict(v["oldest"], brand=b) for b, v in brands.items() if v["oldest"]]
    oldest = max(olds, key=lambda o: o["wait_bh_s"]) if olds else None
    day_lo = _at(datetime.fromisoformat(il_day(now)).date(), 0)
    # the agents, over all brands the manager sees: names are the screen's usernames (no customer data)
    agents = completed(allrows, now - cfg["window_days"] * 86400, now + 1, cfg)["agents"]
    return {
        "ok": True, "at": now, "day": il_day(now), "in_hours": in_hours(now, cfg),
        "config": {"first_reply_bh_h": cfg["first_reply_bh_h"], "resolution_h": cfg["resolution_h"], "warn_ratio": cfg["warn_ratio"], "window_days": cfg["window_days"],
                   "hours": cfg["hours"], "hours_source": cfg["hours_source"]},
        "total": dict(tot, oldest=oldest, today=completed(allrows, day_lo, now + 1, cfg), window=completed(allrows, now - cfg["window_days"] * 86400, now + 1, cfg)),
        "brands": brands, "agents": agents,
        "alerts": alerts[:ALERT_MAX], "alerts_more": max(0, len(alerts) - ALERT_MAX),
        "banner": ("breach" if tot["breach"] else "risk" if tot["risk"] else None) if in_hours(now, cfg) else None,
    }


def register(app, d):
    """d: api_user, json_error, is_manager, cache, engines, ui_lang."""
    cache = d["cache"]

    @app.get("/api/dash/sla")
    def dash_sla():
        u, err = d["api_user"]()
        if err:
            return err
        if not d["is_manager"](u):
            return d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        brands = [b for b in u.get("brands", []) if b in d["engines"]]
        out = {}
        for b in brands:
            try:
                cache.sync_if_older(u, b, LIVE_SYNC_S)
            except Exception:                         # noqa: BLE001 — a slow brand shows its last copy
                app.logger.exception("sla: sync failed for %s", b)
            rows = cache.cached_rows(b)
            if rows or cache.synced_age(b) is not None:          # a stale copy is still data; only "never read" is missing
                out[b] = list(rows.values())
        res = build(out, time.time())
        res["known_brands"] = sorted(out)
        res["missing_brands"] = [b for b in brands if b not in out]
        resp = jsonify(res)
        resp.headers["Cache-Control"] = "no-store, private"
        return resp
