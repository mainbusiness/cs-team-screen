"""Per-brand engine gate (2026-10-05): Apps Script's ~30 simultaneous executions per deploying user must never be
the limit we hit. Cap per brand, interactive first, background only in free slots, breaker on slow/HTML answers."""
import threading
import time

import pytest

import engine_proxy
from conftest import ENGINES, call, logged_in, valid_reply


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
            return dict(valid_reply(url, body), ticket={"id": body["args"].get("id", "x")}, extras={}, tickets=[], counts={})
        finally:
            with self.lock:
                self.now[brand] -= 1


def direct(meter, brand, fn, args, bg=False, user=None):
    user = user or {"username": "noa", "roles": ["agent"], "brands": [brand], "lang": "he"}
    return engine_proxy.call(ENGINES, meter, "t" * 40, user, brand, fn, args, "he", internal=True, retry=False, bg=bg)


SHARED = engine_proxy.GATE_CAP - engine_proxy.GATE_RESERVED          # what everything but the open ticket may use


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
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiTicketFull", {"id": "f%d" % i})) for i in range(SHARED)]
    [t.start() for t in fg]
    time.sleep(0.2)                                                       # every shared slot busy with agents' calls
    st, out = direct(m, "rozela", "apiTicketFull", {"id": "bg"}, bg=True)
    assert out == {"ok": False, "error": "dropped", "background": True} and len(m.calls) == SHARED
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
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiTicketFull", {"id": "f%d" % i})) for i in range(SHARED)]
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
        return valid_reply(url, body)
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



def test_related_is_cached_and_never_takes_an_agents_slot(app, pw_hash, transport):
    transport.reply = lambda url, body: dict(valid_reply(url, body), tickets=[{"id": "t9", "status": "done"}])
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    H = {"X-CSRF-Token": tok}
    j = c.post("/api/rozela/related", json={"q": "dana@example.com"}, headers=H).get_json()
    assert j["tickets"] == [{"id": "t9", "status": "done"}] and len(transport.calls) == 1
    assert c.post("/api/rozela/related", json={"q": "DANA@example.com"}, headers=H).get_json()["cache"] is True
    assert len(transport.calls) == 1                                       # cached 5 min, case-insensitive
    g = engine_proxy.gate("rozela")
    with g.cond:
        g.inflight = engine_proxy.GATE_CAP                                 # the engine is full of agents' calls
    try:
        j = c.post("/api/rozela/related", json={"q": "other@example.com"}, headers=H).get_json()
        assert j == {"ok": True, "tickets": None, "deferred": True} and len(transport.calls) == 1
    finally:
        with g.cond:
            g.inflight = 0
    c2, tok2 = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta"])
    assert c2.post("/api/rozela/related", json={"q": "dana@example.com"}, headers={"X-CSRF-Token": tok2}).status_code == 403



def _queues_reply(state):
    def reply(url, body):
        fn = body["fn"]
        state[fn] = state.get(fn, 0) + 1
        if fn == "apiAutoReplyList":
            return {"ok": True, "switch": "on", "mode": "live", "items": [{"id": "t1", "review": "pending", "n": state[fn]}]}
        if fn == "apiAutoCancelList":
            return {"ok": True, "switch": "shadow", "mode": "shadow", "items": [{"id": "t2", "state": "shadow_would_cancel", "n": state[fn]}]}
        return valid_reply(url, body)
    return reply


def test_queues_are_cached_shared_and_background(app, pw_hash, transport, monkeypatch):
    state = {}
    transport.reply = _queues_reply(state)
    a, ta = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    b, tb = logged_in(app, pw_hash, "ron", ["agent"], ["rozela"])
    q = lambda c, t, fn: c.post("/api/rozela/queue", json={"fn": fn}, headers={"X-CSRF-Token": t}).get_json()
    assert q(a, ta, "apiAutoReplyList")["items"][0]["n"] == 1
    assert q(b, tb, "apiAutoReplyList")["cache"]["hit"] is True and state["apiAutoReplyList"] == 1   # shared by the brand's agents
    assert q(a, ta, "apiAutoCancelList")["items"][0]["n"] == 1
    # the engine is full of agents' calls: the queue never takes a slot, an expired copy is served instead
    cache = app.extensions["cs"]["ticket_cache"]
    clock = [cache.clock() + 100]
    monkeypatch.setattr(cache, "clock", lambda: clock[0])
    g = engine_proxy.gate("rozela")
    with g.cond:
        g.inflight = engine_proxy.GATE_CAP
    try:
        j = q(a, ta, "apiAutoReplyList")
        assert j["cache"]["stale"] is True and state["apiAutoReplyList"] == 1
    finally:
        with g.cond:
            g.inflight = 0
    assert q(a, ta, "apiAutoReplyList")["items"][0]["n"] == 2                        # free again: refreshed
    assert a.post("/api/rozela/queue", json={"fn": "apiSend"}, headers={"X-CSRF-Token": ta}).status_code == 404
    c, tc = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta"])
    assert c.post("/api/rozela/queue", json={"fn": "apiAutoReplyList"}, headers={"X-CSRF-Token": tc}).status_code == 403


def test_no_copy_and_full_engine_means_deferred(app, pw_hash, transport):
    transport.reply = _queues_reply({})
    a, ta = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    g = engine_proxy.gate("rozela")
    with g.cond:
        g.inflight = engine_proxy.GATE_CAP
    try:
        j = a.post("/api/rozela/queue", json={"fn": "apiAutoCancelList"}, headers={"X-CSRF-Token": ta}).get_json()
        assert j == {"ok": True, "deferred": True, "items": None} and transport.calls == []
    finally:
        with g.cond:
            g.inflight = 0


@pytest.mark.parametrize("fn,args,queue", [("apiAutoReplyReview", {"id": "t1", "verdict": "ok"}, "apiAutoReplyList"),
                                           ("apiAutoCancelApprove", {"id": "t2"}, "apiAutoCancelList"),
                                           ("apiAutoCancelReject", {"id": "t2", "note": "צריך בדיקה"}, "apiAutoCancelList")])
def test_writes_invalidate_their_queue(app, pw_hash, transport, fn, args, queue):
    state = {}
    transport.reply = _queues_reply(state)
    a, ta = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    H = {"X-CSRF-Token": ta}
    a.post("/api/rozela/queue", json={"fn": queue}, headers=H)
    call(a, ta, "rozela", fn, args)
    j = a.post("/api/rozela/queue", json={"fn": queue}, headers=H).get_json()
    assert j["cache"]["hit"] is False and state[queue] == 2                           # read again after the write


def test_switch_change_invalidates_its_queue(app, pw_hash, transport):
    state = {}
    transport.reply = _queues_reply(state)
    d, td = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    H = {"X-CSRF-Token": td}
    d.post("/api/rozela/list", json={}, headers=H)
    d.post("/api/rozela/queue", json={"fn": "apiAutoReplyList"}, headers=H)
    call(d, td, "rozela", "apiSettings", {"action": "set", "key": "AUTO_REPLY", "value": "shadow"})
    assert d.post("/api/rozela/queue", json={"fn": "apiAutoReplyList"}, headers=H).get_json()["cache"]["hit"] is False


# ---------- P0 speed (Owner, 2026-10-05): the open ticket has a reserved, top-priority slot ----------

def top(meter, brand, fn, args):
    user = {"username": "noa", "roles": ["agent"], "brands": [brand], "lang": "he"}
    return engine_proxy.call(ENGINES, meter, "t" * 40, user, brand, fn, args, "he", internal=True, retry=False, top=True)


def test_open_ticket_gets_the_reserved_slot_while_everything_else_is_full():
    release = threading.Event()
    m = Meter(block=release)
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiBoot", {})) for _ in range(SHARED + 3)]
    [t.start() for t in fg]
    time.sleep(0.2)
    assert len(m.calls) == SHARED and engine_proxy.gate("rozela").fg_waiting == 3      # list/other calls queue at 5
    got = []
    t = threading.Thread(target=lambda: got.append(top(m, "rozela", "apiTicketFull", {"id": "open"})))
    t.start()
    time.sleep(0.2)
    assert ("rozela", "apiTicketFull") in m.calls and len(m.calls) == SHARED + 1         # straight in: never queued
    assert engine_proxy.gate("rozela").inflight == engine_proxy.GATE_CAP                  # and the cap of 6 still holds
    release.set()
    t.join()
    [x.join() for x in fg]
    assert got[0][1]["ok"] and m.peak["rozela"] <= engine_proxy.GATE_CAP


def test_open_ticket_is_served_before_every_waiter_when_all_six_are_busy():
    release = threading.Event()
    m = Meter(block=release)
    hold = [threading.Thread(target=top, args=(m, "rozela", "apiTicketFull", {"id": "o%d" % i})) for i in range(engine_proxy.GATE_CAP)]
    [t.start() for t in hold]
    time.sleep(0.2)
    assert len(m.calls) == engine_proxy.GATE_CAP
    order = []
    waiter = threading.Thread(target=lambda: (direct(m, "rozela", "apiBoot", {}), order.append("list")))
    waiter.start()
    time.sleep(0.1)
    opener = threading.Thread(target=lambda: (top(m, "rozela", "apiTicketFull", {"id": "mine"}), order.append("open")))
    opener.start()
    time.sleep(0.1)
    g = engine_proxy.gate("rozela")
    assert g.top_waiting == 1 and g.fg_waiting == 1
    m.calls_before = len(m.calls)
    release.set()
    [t.join() for t in hold + [waiter, opener]]
    i_open = m.calls.index(("rozela", "apiTicketFull"), engine_proxy.GATE_CAP)
    i_list = m.calls.index(("rozela", "apiBoot"))
    assert i_open < i_list                                                  # the open ticket went first
    assert m.peak["rozela"] <= engine_proxy.GATE_CAP


def test_background_never_takes_the_reserved_slot_and_writes_never_get_top():
    release = threading.Event()
    m = Meter(block=release)
    fg = [threading.Thread(target=direct, args=(m, "rozela", "apiBoot", {})) for _ in range(SHARED - 1)]
    [t.start() for t in fg]
    time.sleep(0.2)
    assert direct(m, "rozela", "apiTicketFull", {"id": "bg"}, bg=True)[1].get("error") is None   # 1 shared slot free: ok
    # a write marked top is treated as an ordinary call (it waits for a shared slot; the reserved one is for reads)
    assert not engine_proxy.is_read("apiSend", {})
    release.set()
    [t.join() for t in fg]
