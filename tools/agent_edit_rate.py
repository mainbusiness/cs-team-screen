#!/usr/bin/env python3
"""agent_edit_rate.py — per agent: how many replies went out exactly as the AI draft was prefilled (no keystroke at all).

Owner, 2026-11-01: "does the agent read and adapt the AI template per order, or send it as-is?"  READ-ONLY.

Source: the screen's own activity log (core Postgres `screen_activity`, prefix 'act', since 2026-10-06).
  'edit' = typing heartbeat (pingEdit, both desks, first keystroke then <=1/min) or an autosave (apiSaveDraft)
  'send' = apiSend that succeeded, 'open' = the agent opened the ticket
For every send: window = (that agent's previous send on the ticket, or send - 2 h) .. send.
  unedited   = no 'edit' by that agent in the window -> the prefilled text went out untouched
  open->send = seconds from the first open in the window to the send
  again72h   = the same ticket got another send (anyone) within 72 h  (proxy: the customer had to come back)
Why not the Hebrew text diff (engine ai_learn): on the English desk every send is a re-translation, so the Hebrew
always differs from the AI draft even when nothing was changed; the keystroke log is the same signal on both desks.
Limits: pasting text from outside also counts as an edit; a dropped heartbeat (network) reads as "unedited".

Usage: .venv/bin/python -I tools/agent_edit_rate.py [--since 2026-10-20] [--until 2026-10-31] [--brand rozela] [--daily paula,lyra]
"""
import argparse
import datetime as dt
import statistics
import subprocess
from collections import defaultdict

import psycopg

HANDLE_MAX_S = 2 * 3600
TZ_SHIFT_S = 3 * 3600          # Israel day (IDT/IST difference is irrelevant at day granularity for working hours)


def db_url():
    return subprocess.run(["security", "find-generic-password", "-s", "cs-engine", "-a", "all/CORE_DB_URL_EXTERNAL", "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()


def load():
    with psycopg.connect(db_url(), connect_timeout=20) as c:
        c.execute("set session characteristics as transaction read only")
        users = {r[0]: r[1] or "" for r in c.execute("select username, data->>'lang' from screen_users").fetchall()}
        rows = [r[0] for r in c.execute("select obj from screen_activity where prefix='act' order by id").fetchall()]
    return users, rows


def sends_of(rows):
    by_key = defaultdict(list)
    for e in rows:
        by_key[(e["u"], e["b"], e["t"])].append(e)
    out = []
    for (u, b, t), evs in by_key.items():
        evs.sort(key=lambda e: e["ts"])
        prev = None
        for i, e in enumerate(evs):
            if e["k"] != "send":
                continue
            lo = max(prev if prev is not None else -1, e["ts"] - HANDLE_MAX_S)
            win = [x for x in evs[:i] if x["ts"] > lo]
            opens = [x["ts"] for x in win if x["k"] == "open"]
            out.append({"u": u, "b": b, "t": t, "ts": e["ts"], "cat": e.get("cat", ""), "ch": e.get("ch", ""),
                        "day": dt.datetime.utcfromtimestamp(e["ts"] + TZ_SHIFT_S).strftime("%Y-%m-%d"),
                        "edited": any(x["k"] == "edit" for x in win),
                        "handle": (e["ts"] - min(opens)) if opens else None})
            prev = e["ts"]
    return out


def line(label, ss, by_ticket):
    n = len(ss)
    un = sum(1 for s in ss if not s["edited"])
    hs = [s["handle"] for s in ss if s["handle"] is not None]
    again = sum(1 for s in ss if any(s["ts"] < x <= s["ts"] + 72 * 3600 for x in by_ticket[(s["b"], s["t"])]))
    med = f"{statistics.median(hs):6.0f}s" if hs else "     -"
    return f"{label:24} sends {n:5}   unedited {100 * un / n:5.1f}%   open->send {med}   again<=72h {100 * again / n:5.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2000-01-01")
    ap.add_argument("--until", default="2999-12-31")
    ap.add_argument("--brand", default="")
    ap.add_argument("--daily", default="", help="comma-separated agents to show per day")
    ap.add_argument("--min-sends", type=int, default=20)
    a = ap.parse_args()
    users, rows = load()
    allsends = sends_of(rows)
    by_ticket = defaultdict(list)
    for s in allsends:
        by_ticket[(s["b"], s["t"])].append(s["ts"])
    sel = [s for s in allsends if a.since <= s["day"] <= a.until and (not a.brand or s["b"] == a.brand)]
    print(f"activity events {len(rows)} · sends in range {len(sel)} · {a.since}..{a.until} {a.brand or 'all brands'}")
    per = defaultdict(list)
    for s in sel:
        per[s["u"]].append(s)
    for u, ss in sorted(per.items(), key=lambda kv: -len(kv[1])):
        if len(ss) >= a.min_sends:
            print(line(f"{u} ({users.get(u, '?')})", ss, by_ticket))
    for u in [x for x in a.daily.split(",") if x]:
        print(f"\n-- {u} per day")
        days = defaultdict(list)
        for s in per.get(u, []):
            days[s["day"]].append(s)
        for d in sorted(days):
            print(line(d, days[d], by_ticket))


if __name__ == "__main__":
    main()
