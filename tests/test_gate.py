"""Per-brand engine gate (2026-10-05): Apps Script's ~30 simultaneous executions per deploying user must never be
the limit we hit. Cap per brand, interactive first, background only in free slots, breaker on slow/HTML answers."""
import threading
import time

import pytest

import engine_proxy
from conftest import ENGINES, call, logged_in


class Meter:
    """A transport that counts how many calls are inside the engine at once, per brand."""

    def __init__(self, delay=0.2, block=None, fail=None):
        self.delay, self.block, self.fail = delay, block, fail
        self.now, self.peak, self.calls = {}, {}, []
        self.lock = threading.Lock()

    def __call__(self, url, body):
        brand = [b for b, u in ENGINES.items() if u == url][0]
        with self.lock:
            self.calls.append((brand, body["fn"]))
            self.now[brand] = self.now.get(brand, 0) + 1
            self.peak[brand] = max(self.peak.get(brand, 0), self.now[brand])
        try:
            if self.block is not None:
                self.block.wait(5)
            else:
                time.sleep(self.delay)
            if self.fail:
                raise engine_proxy.ProxyError(self.fail, 502)
            return {"ok": True, "ticket": {"id": body["args"].get("id", "x")}, "extras": {}, "tickets": [], "counts": {}}
        finally:
            with self.lock:
                self.now[brand] -= 1


def direct(meter, brand, fn, args, bg=False, user=None):
    user = user or {"username": "noa", "roles": ["agent"], "brands": [brand], "lang": "he"}
    return engine_proxy.call(ENGINES, meter, "t" * 40, user, brand, fn, args, "he", internal=True, retry=False, bg=bg)


def test_twenty_simultaneous_opens_never_exceed_the_cap():
    m = Meter(delay=0.15)
    res = []
    ts = [threading.Thread(target=lambda i=i: res.append(direct(m, "rozela", "apiTicketFull", {"id": "t%d" % i}))) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert m.peak["rozela"] <= engine_proxy.GATE_CAP and m.peak["rozela"] >= 4      # parallel, and capped
    assert all(st == 200 and out["ok"] for st, out in res) and len(m.calls) == 20     # everyone was served
    assert engine_proxy.gate("rozela").peak <= engine_proxy.GATE_CAP


def test_brands_have_separate_caps():
    m = Meter(delay=0.15)
    ts = [threading.Thread(target=direct, args=(m, b, "apiBoot", {})) for b in ("rozela", "celesta") for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert m.peak["rozela"] <= 6 and m.peak["celesta"] <= 6 and sum(m.peak.values()) > 6


def test_background_uses_only_free_slots_and_is_dropped_under_load():
    release = threading.Event()
    m = Meter(block=release)
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiTicketFull", {"id": "f%d" % i})) for i in range(6)]
    [t.start() for t in fg]
    time.sleep(0.2)                                                       # all 6 slots busy with agents' opens
    st, out = direct(m, "rozela", "apiTicketFull", {"id": "bg"}, bg=True)
    assert out == {"ok": False, "error": "dropped", "background": True} and len(m.calls) == 6
    release.set()
    [t.join() for t in fg]


def test_background_is_capped_at_two_per_brand():
    release = threading.Event()
    m = Meter(block=release)
    outs = []
    ts = [threading.Thread(target=lambda: outs.append(direct(m, "rozela", "apiTicketFull", {"id": "b"}, bg=True)[1])) for _ in range(5)]
    [t.start() for t in ts]
    time.sleep(0.3)
    assert len(m.calls) == 2                                              # 2 reached the engine, 3 were dropped
    release.set()
    [t.join() for t in ts]
    assert sum(1 for o in outs if o.get("error") == "dropped") == 3


def test_interactive_waits_and_background_yields_to_it(monkeypatch):
    release = threading.Event()
    m = Meter(block=release)
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiTicketFull", {"id": "f%d" % i})) for i in range(6)]
    [t.start() for t in fg]
    time.sleep(0.2)
    waiter = threading.Thread(target=direct, args=(m, "rozela", "apiSearch", {"q": "dana"}))
    waiter.start()
    time.sleep(0.2)
    assert engine_proxy.gate("rozela").fg_waiting == 1
    assert direct(m, "rozela", "apiTicketFull", {"id": "bg"}, bg=True)[1]["error"] == "dropped"   # never ahead of an agent
    release.set()
    waiter.join()
    [t.join() for t in fg]
    assert ("rozela", "apiSearch") in m.calls


def test_interactive_gives_up_with_busy_after_the_wait_limit(monkeypatch):
    monkeypatch.setattr(engine_proxy, "GATE_WAIT_S", 0.3)
    release = threading.Event()
    m = Meter(block=release)
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiTicketFull", {"id": "f%d" % i})) for i in range(6)]
    [t.start() for t in fg]
    time.sleep(0.2)
    t0 = time.time()
    st, out = direct(m, "rozela", "apiTicketFull", {"id": "late"})
    assert st == 503 and out["error"] == "busy" and "נסו שוב" in out["msg"] and time.time() - t0 < 1.5
    release.set()
    [t.join() for t in fg]


def test_breaker_trips_on_html_and_on_slow_and_recovers(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(engine_proxy, "_clock", lambda: clock[0])
    g = engine_proxy.gate("rozela")
    m = Meter(delay=0, fail="engine_bad_response")
    direct(m, "rozela", "apiBoot", {})
    assert g.tripped()
    m.fail = None
    assert direct(m, "rozela", "apiTicketFull", {"id": "x"}, bg=True)[1]["error"] == "dropped"     # background stays off
    assert direct(m, "rozela", "apiTicketFull", {"id": "x"})[1]["ok"]                               # agents are still served
    clock[0] += 61
    assert not g.tripped() and direct(m, "rozela", "apiTicketFull", {"id": "y"}, bg=True)[1]["ok"]  # recovered
    # a slow (> 10 s) success trips it too

    def slow(url, body):
        clock[0] += 11
        return {"ok": True}
    direct(slow, "rozela", "apiBoot", {})
    assert g.tripped()


def test_prefetch_is_skipped_while_the_breaker_is_open(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    engine_proxy.gate("rozela").trip_until = engine_proxy._clock() + 60
    r = c.post("/api/rozela/prefetch", json={"ids": ["a", "b", "c"]}, headers={"X-CSRF-Token": tok}).get_json()
    assert r["queued"] == 0 and transport.calls == []
    engine_proxy.gate("rozela").trip_until = 0
    assert c.post("/api/rozela/prefetch", json={"ids": ["a"]}, headers={"X-CSRF-Token": tok}).get_json()["queued"] == 1


def test_a_freed_slot_goes_to_the_waiting_agent_not_to_background():
    """The race window: a slot has just been released, the agent's thread has not woken yet. Background must not take it."""
    g = engine_proxy.gate("rozela")
    with g.cond:
        g.fg_waiting = 1                     # an agent is waiting; inflight is 0 (the slot was just freed)
    try:
        assert g.acquire(bg=True) is False and g.inflight == 0
    finally:
        with g.cond:
            g.fg_waiting = 0
    assert g.acquire(bg=True) is True        # nobody waiting: background may use the free slot
    g.release(True, 0.1, None)
