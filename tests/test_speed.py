"""P0 speed (Owner, 2026-10-05: "the most important thing in this system is speed").
The brand's change feed is shared (one apiChanges per brand per window, however many agents poll), every client gets its
own delta, a cached copy the feed vouches for is "confirmed" (no second round-trip), and the open ticket is watched cheaply."""
import threading

import engine_proxy
import ticket_cache
from conftest import logged_in
from test_cache import ROZ, cache_of, fns, post

AGENT = {"username": "noa", "roles": ["agent"], "brands": ["rozela"], "lang": "he"}


class Engine:
    """A small stateful rozela engine: a change log with versions, tickets that can change, apiChanges like Api.gs."""

    def __init__(self, lite=True):
        self.lite = lite
        self.v = 7
        self.log = []
        self.tickets = {"t1": dict(ROZ), "t2": dict(ROZ, id="t2", name="Second"), "t3": dict(ROZ, id="t3", name="Third")}
        self.conv = {i: [{"who": "customer", "at": "2026-10-05T10:00:00Z", "text": "hello"}] for i in self.tickets}
        self.calls = []
        self.lock = threading.Lock()

    def change(self, tid, **patch):
        self.tickets[tid].update(patch)
        self.v += 1
        self.log.append((self.v, tid))

    def tv(self, tid):
        return max([v for v, i in self.log if i == tid] or [0])

    def __call__(self, url, body):
        fn, a = body["fn"], body["args"]
        with self.lock:
            self.calls.append(fn)
        if fn == "apiBoot":
            return {"ok": True, "counts": {"ready": len(self.tickets)}, "tickets": [dict(t) for t in self.tickets.values()], "version": self.v,
                    "serverTime": "2026-10-05T10:00:00Z", "dryRun": True, "cancelEnabled": False}
        if fn == "apiChanges":
            ids = []
            for v, i in self.log:
                if v > a["since"] and i not in ids:
                    ids.append(i)
            return {"ok": True, "version": self.v, "tickets": [dict(self.tickets[i], v=self.tv(i)) for i in ids], "removed": [],
                    "serverMs": 5, "dryRun": True, "cancelEnabled": False, "cancelFrozen": False, "subscriptions": "kaching"}
        if fn == "apiTicketLite" and self.lite:
            tid, v = a["id"], self.tv(a["id"])
            if v <= a["since"]:
                return {"ok": True, "v": v, "changed": False, "serverMs": 12}
            conv = self.conv[tid]
            seen = a.get("seen")
            t = self.tickets[tid]
            return {"ok": True, "v": v, "changed": True, "status": t["status"], "draft_text": t.get("draft_text", ""),
                    "action": t.get("action", ""), "handled_by": t.get("handled_by", ""), "msgCount": len(conv),
                    "newMessages": [dict(m) for m in (conv[seen:] if isinstance(seen, int) else conv[-10:])]}
        if fn == "apiTicketFull":
            t = self.tickets[a["id"]]
            return {"ok": True, "ticket": dict(t), "extras": {"conversation": list(self.conv[a["id"]])}, "snapshotAt": "s"}
        return {"ok": False, "error": "unauthorized"}


def setup(make_app, pw_hash, transport, now, lite=True):
    eng = Engine(lite)
    transport.reply = eng
    app = make_app()
    cache = cache_of(app)
    cache.clock = lambda: now[0]
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert post(c, tok, "/api/rozela/list", {}).get_json()["version"] == 7
    return app, cache, c, tok, eng


def count(eng, fn):
    return sum(1 for f in eng.calls if f == fn)


# ---------- the shared feed ----------

def test_ten_agents_polling_make_one_engine_read(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    now[0] += 5
    eng.calls.clear()
    outs = [post(c, tok, "/api/rozela/changes", {"since": 7}).get_json() for _ in range(10)]
    assert count(eng, "apiChanges") == 1                                    # shared: one read for everyone
    assert all(o["ok"] and o["changed"] == [] and o["version"] == 7 for o in outs)


def test_parallel_polls_are_single_flight(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    now[0] += 5
    eng.calls.clear()
    gate = threading.Event()
    real = transport.reply

    def slow(url, body):
        if body["fn"] == "apiChanges":
            gate.wait(2)
        return real(url, body)
    transport.reply = slow
    res = []
    ts = [threading.Thread(target=lambda: res.append(cache.changes(AGENT, "rozela", 7)[1])) for _ in range(8)]
    [t.start() for t in ts]
    gate.set()
    [t.join() for t in ts]
    assert count(eng, "apiChanges") == 1 and len(res) == 8 and all(r["ok"] for r in res)


def test_each_client_gets_its_own_delta(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    eng.change("t2", status="action")                                       # v8
    now[0] += 5
    a = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    assert a["version"] == 8 and [r["id"] for r in a["changed"]] == ["t2"] and a["changed"][0]["status"] == "action"
    eng.change("t3", status="delay")                                        # v9
    now[0] += 5
    b = post(c, tok, "/api/rozela/changes", {"since": 8}).get_json()        # a client already at 8: only t3
    assert [r["id"] for r in b["changed"]] == ["t3"]
    late = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()     # a client still at 7: both, from the log
    assert sorted(r["id"] for r in late["changed"]) == ["t2", "t3"] and count(eng, "apiChanges") == 2
    same = post(c, tok, "/api/rozela/changes", {"since": 9}).get_json()
    assert same["changed"] == [] and same["removed"] == [] and "reset" not in same


def test_a_client_older_than_the_log_gets_the_whole_list(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    j = post(c, tok, "/api/rozela/changes", {"since": 3}).get_json()
    assert j["reset"] is True and sorted(r["id"] for r in j["changed"]) == ["t1", "t2", "t3"]
    j = post(c, tok, "/api/rozela/changes", {"since": "garbage"}).get_json()
    assert j["reset"] is True


def test_full_list_reload_keeps_clients_on_deltas(make_app, pw_hash, transport):
    """A full apiBoot (switch refresh, starving list) is diffed and logged: clients keep getting only what changed."""
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    eng.change("t1", status="action")                                       # v8
    cache._fetch_boot(AGENT, "rozela")
    j = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    assert [r["id"] for r in j["changed"]] == ["t1"] and "reset" not in j


# ---------- confirmed-fresh: the open needs no second round-trip ----------

def test_a_copy_the_feed_vouches_for_is_confirmed(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["confirmed"] is True   # just read
    now[0] += 60
    hit = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]
    assert hit["hit"] and hit["confirmed"] is False                         # a minute old, nobody vouched for it
    post(c, tok, "/api/rozela/changes", {"since": 7})                        # the feed: nothing changed
    hit = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]
    assert hit["confirmed"] is True and hit["stale"] is False
    eng.change("t1", draft_text="new draft")
    now[0] += 5
    post(c, tok, "/api/rozela/changes", {"since": 7})
    hit = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]
    assert hit["confirmed"] is False and hit["stale"] is True               # the feed said it changed


def test_a_copy_older_than_the_feed_base_is_never_confirmed(make_app, pw_hash, transport):
    now = [1000.0]
    eng = Engine()
    transport.reply = eng
    app = make_app()
    cache = cache_of(app)
    cache.clock = lambda: now[0]
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})                          # read BEFORE the list (no feed base yet)
    now[0] += 30
    post(c, tok, "/api/rozela/list", {})
    now[0] += 30
    post(c, tok, "/api/rozela/changes", {"since": 7})
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["confirmed"] is False


def test_a_read_that_raced_a_change_stays_marked_old(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    t0 = now[0]
    now[0] += 1
    cache._stale(["t1"], "rozela")                                           # the feed saw a change while the read ran
    e = cache._store_full("rozela", "t1", {"ticket": dict(ROZ), "extras": {}}, t0)
    assert e["stale"] is True


def test_an_older_read_never_overwrites_a_newer_one(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    cache._store_full("rozela", "t1", {"ticket": dict(ROZ, draft_text="newer"), "extras": {}}, 1005.0)
    cache._store_full("rozela", "t1", {"ticket": dict(ROZ, draft_text="older"), "extras": {}}, 1001.0)   # a slow prefetch
    assert cache._entry("rozela", "t1")["full"]["ticket"]["draft_text"] == "newer"


# ---------- the open ticket ----------

def test_open_flag_reads_at_top_priority(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    before = engine_proxy.gate("rozela").top_served
    post(c, tok, "/api/rozela/ticket", {"id": "t1", "revalidate": True, "open": True})
    assert engine_proxy.gate("rozela").top_served == before + 1
    post(c, tok, "/api/rozela/ticket", {"id": "t2", "revalidate": True})
    assert engine_proxy.gate("rozela").top_served == before + 1             # without the flag: ordinary


def test_watch_is_cheap_while_nothing_changes(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    eng.calls.clear()
    for _ in range(6):                                                       # 30 s of an agent reading a ticket
        now[0] += 5.5
        j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
        assert j["ok"] and j["changed"] is False and j["cache"]["confirmed"] is True
    assert eng.calls == ["apiTicketLite"] * 6                               # "anything new since v?" — never the full ticket


def test_watch_brings_a_new_customer_message_within_one_tick(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    eng.conv["t1"].append({"who": "customer", "at": "2026-10-05T10:05:00Z", "text": "where is my order?"})
    eng.change("t1", draft_text="engine draft v2")
    now[0] += 5.5
    before = engine_proxy.gate("rozela").top_served
    eng.calls.clear()
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert j["changed"] is True and [m["text"] for m in j["extras"]["conversation"]] == ["hello", "where is my order?"]
    assert j["ticket"]["draft_text"] == "engine draft v2" and j["cache"]["at"] > at
    assert eng.calls[0] == "apiTicketLite" and "apiTicketFull" not in eng.calls[:1]   # merged from the lite reply
    assert engine_proxy.gate("rozela").top_served > before                  # the reserved slot
    cache.drain()                                                            # summary/recommendation filled in behind
    now[0] += 5.5
    j2 = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": cache._entry("rozela", "t1")["at"]}).get_json()
    assert j2["changed"] is False and len(j2.get("extras", {}).get("conversation", [])) in (0, 2)


def test_lite_reply_that_cannot_be_merged_falls_back_to_the_full_ticket(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    eng.conv["t1"] = []                                                      # the engine holds FEWER than we do
    eng.change("t1", status="action")
    now[0] += 5.5
    eng.calls.clear()
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert eng.calls[:2] == ["apiTicketLite", "apiTicketFull"] and j["changed"] is True
    assert j["extras"]["conversation"] == [] and j["ticket"]["status"] == "action"


def test_two_agents_on_the_same_ticket_share_one_check(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    c2, tok2 = logged_in(app, pw_hash, "dana", ["agent"], ["rozela"])
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    eng.calls.clear()
    now[0] += 5.5
    post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at})
    post(c2, tok2, "/api/rozela/watch", {"id": "t1", "at": at})
    assert eng.calls == ["apiTicketLite"]


def test_open_revalidate_uses_lite(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    now[0] += 60
    eng.calls.clear()
    j = post(c, tok, "/api/rozela/ticket", {"id": "t1", "revalidate": True, "open": True}).get_json()
    assert eng.calls == ["apiTicketLite"] and j["cache"]["confirmed"] is True
    j = post(c, tok, "/api/rozela/ticket", {"id": "t1", "fresh": True, "open": True}).get_json()
    assert eng.calls[-1] == "apiTicketFull"                                  # an explicit refresh is always the full read


def test_engine_without_lite_watches_through_the_shared_feed(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now, lite=False)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    now[0] += 5.5
    assert post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()["changed"] is False
    eng.change("t1", draft_text="v2")
    eng.calls.clear()
    now[0] += 5.5
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert "apiTicketLite" not in eng.calls and j["changed"] is True and j["ticket"]["draft_text"] == "v2"


def test_watch_reads_the_ticket_itself_when_lite_keeps_failing(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    real = transport.reply
    transport.reply = lambda u, b: {"ok": False, "error": "busy"} if b["fn"] == "apiTicketLite" else real(u, b)
    eng.calls.clear()
    now[0] += 10
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert j["ok"] and j["changed"] is False and "apiTicketFull" not in eng.calls   # young copy: no direct read yet
    now[0] += ticket_cache.WATCH_DIRECT_S
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert "apiTicketFull" in eng.calls and j["changed"] is True              # the open ticket never goes stale silently


def test_switches_come_from_the_feed_not_a_boot_reload(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    now[0] += 5
    post(c, tok, "/api/rozela/changes", {"since": 7})                        # the feed shows it carries the switches
    eng.calls.clear()
    for _ in range(6):
        now[0] += 16                                                         # every open asks for switches <= 15 s old
        j = post(c, tok, "/api/rozela/list", {"maxAge": 15}).get_json()
        assert j["ok"] and j["dryRun"] is True
    cache.drain()
    assert "apiBoot" not in eng.calls and eng.calls.count("apiChanges") == 6


def test_watch_rejects_bad_input_and_non_agents(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    assert post(c, tok, "/api/rozela/watch", {"id": "../x"}).status_code == 400
    m, mtok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert post(m, mtok, "/api/rozela/watch", {"id": "t1"}).status_code == 403
    assert post(c, tok, "/api/celesta/watch", {"id": "t1"}).status_code == 403


def test_prefetch_skips_copies_the_feed_vouches_for(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    now[0] += 300
    post(c, tok, "/api/rozela/changes", {"since": 7})
    assert cache.prefetch(AGENT, "rozela", ["t1"]) == 0                      # 5 min old but confirmed: not read again


def test_an_engine_that_sends_its_switches_with_the_feed_saves_the_boot_reload(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    real = transport.reply
    transport.reply = lambda u, b: dict(real(u, b), dryRun=False, cancelEnabled=True, cancelFrozen=False) if b["fn"] == "apiChanges" else real(u, b)
    eng.calls.clear()
    for _ in range(8):
        now[0] += 5
        j = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    cache.drain()
    assert "apiBoot" not in eng.calls and j["switches"]["dryRun"] is False and j["switches"]["cancelEnabled"] is True


def test_a_feed_without_a_valid_version_vouches_for_nothing(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    now[0] += 50                                                             # past the 45 s window, not starving yet (60 s)
    real = transport.reply
    transport.reply = lambda u, b: {"ok": True, "tickets": [], "removed": [], "version": 3} if b["fn"] == "apiChanges" else real(u, b)
    j = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    assert j["ok"] is False                                                  # version went backwards: refused
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["confirmed"] is False


def test_open_ticket_reads_have_their_own_threads(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    import threading as th
    block = th.Event()
    for _ in range(16):                                                      # every ordinary open thread is stuck
        cache.fg_pool.submit(block.wait, 5)
    j = post(c, tok, "/api/rozela/ticket", {"id": "t2", "revalidate": True, "open": True}).get_json()
    block.set()
    assert j["ok"] and j["cache"]["hit"] is False                            # served anyway


def test_lite_never_merges_a_backwards_version_or_a_malformed_message(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    eng.change("t1", status="action")
    post(c, tok, "/api/rozela/changes", {"since": 7})
    post(c, tok, "/api/rozela/ticket", {"id": "t1", "revalidate": True})
    real = transport.reply
    for bad in ({"ok": True, "v": 1, "changed": False},
                {"ok": True, "v": 99, "changed": True, "status": "x", "draft_text": "", "msgCount": 2, "newMessages": ["junk"]}):
        transport.reply = lambda u, b, bad=bad: bad if b["fn"] == "apiTicketLite" else real(u, b)
        cache._entry("rozela", "t1")["v"] = 8
        assert cache._lite({"username": "noa", "roles": ["agent"], "brands": ["rozela"], "lang": "he"}, "rozela", "t1")["need_full"] is True


def test_a_copy_vouched_for_within_45s_opens_with_no_engine_call(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    now[0] += 40
    eng.calls.clear()
    m = post(c, tok, "/api/rozela/ticket", {"id": "t1", "open": True}).get_json()["cache"]
    assert m["confirmed"] is True and m["vouched_s"] == 40 and eng.calls == []
    now[0] += 6                                                              # 46 s: no longer vouched for
    m = post(c, tok, "/api/rozela/ticket", {"id": "t1", "open": True}).get_json()["cache"]
    assert m["confirmed"] is False
    now[0] += 1                                                              # one lite check vouches for it again, at once
    m = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": m["at"]}).get_json()["cache"]
    assert m["vouched_s"] == 0 and eng.calls == ["apiTicketLite"]


def test_a_change_is_never_hidden_by_the_45s_window(make_app, pw_hash, transport):
    now = [1000.0]
    app, cache, c, tok, eng = setup(make_app, pw_hash, transport, now)
    at = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["at"]
    eng.conv["t1"].append({"who": "customer", "at": "2026-10-05T10:05:00Z", "text": "another one"})
    eng.change("t1", draft_text="v2")
    now[0] += 6                                                              # well inside 45 s
    j = post(c, tok, "/api/rozela/watch", {"id": "t1", "at": at}).get_json()
    assert j["changed"] is True and j["extras"]["conversation"][-1]["text"] == "another one"
