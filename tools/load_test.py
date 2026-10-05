#!/usr/bin/env python3
"""
tools/load_test.py — 4 agents working at once against the MOCK engines, through the real Flask app, cache and gate.
Never point this at a live engine.

Each agent: loads the list of every brand it has (which prefetches 15 tickets), then opens 15 tickets one after the
other (cached open + revalidation), polling /changes every few opens. The mock engine answers in MOCK_LATENCY_MS.
Reports the peak number of calls in flight per brand engine, busy answers, and background calls dropped.
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("MOCK_LATENCY_MS", "800")

import tempfile  # noqa: E402

import engine_proxy  # noqa: E402
import mock_engine  # noqa: E402
import security  # noqa: E402
from app import create_app  # noqa: E402
from users_store import UserStore  # noqa: E402

lat = int(os.environ["MOCK_LATENCY_MS"]) / 1000.0
eng = mock_engine.MockEngines("k" * 40, latency_ms=0)
now, peak, lock = {}, {}, threading.Lock()


def metered(url, body):
    brand = url.split("mock://", 1)[1]
    with lock:
        now[brand] = now.get(brand, 0) + 1
        peak[brand] = max(peak.get(brand, 0), now[brand])
    try:
        time.sleep(lat)
        with eng.lock:
            return eng.dispatch(brand, body)
    finally:
        with lock:
            now[brand] -= 1


tmp = tempfile.mkdtemp(prefix="cs-load-")
app = create_app({"MOCK_ENGINE": True, "ENGINES_JSON": "", "COOKIE_SECURE": False, "USERS_PATH": os.path.join(tmp, "u.json"),
                  "TRUSTED_PROXY_HOPS": 0, "TOKEN_SECRET": "k" * 40, "TRANSPORT": metered, "SECRET_KEY": "s" * 48})
brands = ["rozela", "celesta", "apexmen"]
store = app.extensions["cs"]["store"]
pw = "Load-test-" + os.urandom(4).hex()
h = security.hash_password(pw)
for i in range(4):
    store.create("t", "agent%d" % i, h, {"display_name": "a", "roles": ["agent"], "brands": brands, "lang": "he"},
                 app.extensions["cs"]["valid_brands"], must_change=False)
stats = {"busy": 0, "errors": 0, "opens": 0}


def agent(i):
    c = app.test_client()
    c.environ_base.update({"wsgi.url_scheme": "http", "HTTP_HOST": "x", "REMOTE_ADDR": "10.0.0.%d" % i})
    import re
    tok = re.search(r'name="csrf" value="([^"]+)"', c.get("/cs/login").get_data(as_text=True)).group(1)
    c.post("/cs/login", data={"username": "agent%d" % i, "password": pw, "csrf": tok})
    tok = re.search(r'name="csrf" content="([^"]+)"', c.get("/cs").get_data(as_text=True)).group(1)
    H = {"X-CSRF-Token": tok}
    for b in brands:
        lst = c.post("/api/%s/list" % b, json={}, headers=H).get_json()
        ids = [t["id"] for t in lst.get("tickets", [])][:15]
        c.post("/api/%s/prefetch" % b, json={"ids": ids}, headers=H)
        for n, tid in enumerate(ids):
            for body in ({"id": tid}, {"id": tid, "revalidate": True}):
                r = c.post("/api/%s/ticket" % b, json=body, headers=H)
                j = r.get_json() or {}
                stats["opens"] += 1
                if j.get("error") == "busy":
                    stats["busy"] += 1
                elif not j.get("ok"):
                    stats["errors"] += 1
            if n % 4 == 0:
                c.post("/api/%s/changes" % b, json={"since": lst.get("version", 0)}, headers=H)


t0 = time.time()
ts = [threading.Thread(target=agent, args=(i,)) for i in range(4)]
[t.start() for t in ts]
[t.join() for t in ts]
app.extensions["cs"]["ticket_cache"].drain(30)
print("4 agents x 3 brands, engine latency %.1f s, %.0f s total" % (lat, time.time() - t0))
for b in brands:
    g = engine_proxy.gate(b)
    print("  %-8s peak in flight %d (cap %d) | background dropped %d | busy %d" % (b, peak.get(b, 0), engine_proxy.GATE_CAP, g.dropped, g.busy))
print("  requests %d | busy answers %d | other errors %d" % (stats["opens"], stats["busy"], stats["errors"]))
ok = all(peak.get(b, 0) <= engine_proxy.GATE_CAP for b in brands)
print("RESULT:", "within the cap" if ok else "CAP EXCEEDED")
sys.exit(0 if ok else 1)
