"""Performance layer: instant cached reads, SWR, write-through, prefetch cap, polling, brand isolation."""
import json
import os
import stat
import threading
import time

import pytest

import ticket_cache
from conftest import ENGINES, call, client_for, logged_in

ROZ = {"id": "t1", "status": "ready", "name": "Rozela customer", "email": "r@example.com", "draft_text": "rozela draft", "emails_count": 1}
CEL = {"id": "t1", "status": "action", "name": "Celesta customer", "email": "c@example.com", "draft_text": "celesta draft", "emails_count": 1}


def make_reply(full=True, changes=True, delay=0.0, counter=None):
    by_url = {ENGINES["rozela"]: ROZ, ENGINES["celesta"]: CEL}

    def reply(url, body):
        if counter is not None:                                       # count BEFORE the wait, or calls never overlap
            with counter["lock"]:
                counter["now"] += 1
                counter["max"] = max(counter["max"], counter["now"])
        try:
            if delay:
                time.sleep(delay)
            fn, t = body["fn"], by_url.get(url, ROZ)
            tid = body["args"].get("id")
            mine = dict(t, id=tid) if tid else t
            if fn == "apiTicketFull":
                return {"ok": True, "ticket": mine, "extras": {"conversation": [{"who": "customer", "text": t["name"]}]}, "snapshotAt": "s"} if full \
                    else {"ok": False, "error": "unauthorized"}
            if fn == "apiTicket":
                return {"ok": True, "ticket": mine}
            if fn == "apiTicketExtras":
                return {"ok": True, "extras": {"conversation": []}}
            if fn == "apiBoot":
                return {"ok": True, "user": "whoever", "role": "admin", "lang": "he", "counts": {t["status"]: 1},
                        "tickets": [t], "version": 7, "serverTime": "2026-10-05T10:00:00Z", "dryRun": True}
            if fn == "apiChanges":
                if changes == "reset":
                    return {"ok": True, "version": 9, "reset": True, "tickets": [t]}
                return {"ok": True, "version": 8, "tickets": [dict(t, status="done")], "removed": [], "serverMs": 12} if changes \
                    else {"ok": False, "error": "unauthorized"}
            return {"ok": True}
        finally:
            if counter is not None:
                with counter["lock"]:
                    counter["now"] -= 1
    return reply


def post(c, tok, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": tok})


def cache_of(app):
    return app.extensions["cs"]["ticket_cache"]


def fns(transport):
    return [b["fn"] for _, b in transport.calls]


# ---------- the requirement: a cached open makes no engine call ----------

def test_cached_ticket_open_makes_no_engine_call(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r1 = post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    assert r1.get_json()["cache"]["hit"] is False and fns(transport) == ["apiTicketFull"]
    n = len(transport.calls)
    t0 = time.perf_counter()
    r2 = post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    took = time.perf_counter() - t0
    j = r2.get_json()
    assert j["ok"] and j["cache"]["hit"] is True and j["ticket"]["draft_text"] == "rozela draft"
    assert len(transport.calls) == n                                   # zero engine calls
    assert 'cache;desc="ticket-hit"' in r2.headers["Server-Timing"] and "engine" not in r2.headers["Server-Timing"]
    assert took < 0.3


def test_slow_engine_does_not_slow_a_cached_open(make_app, pw_hash, transport):
    transport.reply = make_reply(delay=1.0)
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})                   # cold: pays the engine once
    t0 = time.perf_counter()
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["cache"]["hit"]
    assert time.perf_counter() - t0 < 0.3


def test_revalidate_goes_to_the_engine_and_updates_the_cache(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    ROZ["draft_text"] = "changed on the server"
    try:
        r = post(c, tok, "/api/rozela/ticket", {"id": "t1", "revalidate": True}).get_json()
        assert r["cache"]["hit"] is False and r["ticket"]["draft_text"] == "changed on the server"
        assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["ticket"]["draft_text"] == "changed on the server"
    finally:
        ROZ["draft_text"] = "rozela draft"


def test_fallback_is_parallel_not_sequential(make_app, pw_hash, transport):
    transport.reply = make_reply(full=False, delay=0.5)
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    t0 = time.perf_counter()
    j = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()
    took = time.perf_counter() - t0
    assert j["ok"] and fns(transport) == ["apiTicketFull", "apiTicket", "apiTicketExtras"] or \
        fns(transport)[:1] == ["apiTicketFull"] and set(fns(transport)[1:]) == {"apiTicket", "apiTicketExtras"}
    assert took < 1.4                                                  # 0.5 (Full) + 0.5 (pair in parallel), not 1.5
    # the engine said it has no apiTicketFull: the next fetch goes straight to the pair
    transport.calls.clear()
    post(c, tok, "/api/rozela/ticket", {"id": "t2"})
    assert "apiTicketFull" not in fns(transport)


# ---------- brand isolation ----------

def test_cache_never_crosses_brands(app, pw_hash, transport, tmp_path):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela", "celesta"])
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["ticket"]["name"] == "Rozela customer"
    assert post(c, tok, "/api/celesta/ticket", {"id": "t1"}).get_json()["ticket"]["name"] == "Celesta customer"
    assert post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()["ticket"]["name"] == "Rozela customer"   # same id, own brand
    post(c, tok, "/api/rozela/list", {})
    # a user without rozela never gets rozela's cached ticket or list
    c2, tok2 = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta"])
    n = len(transport.calls)
    for path, body in (("/api/rozela/ticket", {"id": "t1"}), ("/api/rozela/list", {}), ("/api/rozela/changes", {}),
                       ("/api/rozela/prefetch", {"ids": ["t1"]})):
        r = post(c2, tok2, path, body)
        assert r.status_code == 403 and "Rozela customer" not in r.get_data(as_text=True), path
    assert len(transport.calls) == n
    j = post(c2, tok2, "/api/celesta/ticket", {"id": "t1"}).get_json()
    assert j["ticket"]["name"] == "Celesta customer" and j["cache"]["hit"] is True
    # on disk: one folder per brand, private
    root = tmp_path / "ticket-cache"
    assert stat.S_IMODE(os.stat(root).st_mode) == 0o700
    for b in ("rozela", "celesta"):
        assert stat.S_IMODE(os.stat(root / b).st_mode) == 0o700
        f = root / b / "t" / "t1.json"
        assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
    assert "Celesta" not in (root / "rozela" / "t" / "t1.json").read_text()


def test_bad_keys_never_touch_the_disk(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    for bad in ("../x", "a/b", "", "x" * 81):
        assert post(c, tok, "/api/rozela/ticket", {"id": bad}).status_code == 400
    with pytest.raises(ValueError):
        cache_of(app)._bucket("../rozela")


def test_cached_list_is_per_user_where_it_matters(app, pw_hash, transport):
    transport.reply = make_reply()
    c1, t1 = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    c2, t2 = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    a = post(c1, t1, "/api/rozela/list", {}).get_json()
    n = len(transport.calls)
    b = post(c2, t2, "/api/rozela/list", {}).get_json()
    assert len(transport.calls) == n and b["cache"]["hit"]
    assert (a["user"], a["role"]) == ("manager", "admin") and (b["user"], b["role"]) == ("noa", "agent")
    stored = cache_of(app).mem["rozela"]["boot"]["data"]
    assert not {"user", "role", "lang"} & set(stored)                  # nothing per-user is cached, in memory or on disk
    disk = json.loads(open(os.path.join(cache_of(app).root, "rozela", "boot.json")).read())["data"]
    assert not {"user", "role", "lang"} & set(disk) and "whoever" not in json.dumps(disk)


def test_background_fallback_pairs_stay_within_the_cap(make_app, pw_hash, transport):
    counter = {"now": 0, "max": 0, "lock": threading.Lock()}
    transport.reply = make_reply(full=False, delay=0.15, counter=counter)
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/prefetch", {"ids": ["q%d" % i for i in range(9)]})
    cache_of(app).drain(20)
    assert counter["max"] <= 3                                          # 3 jobs x 2 halves would be 6 without the slots


def test_auth_failure_does_not_disable_apiticketfull(make_app, pw_hash, transport):
    transport.reply = lambda u, b: {"ok": False, "error": "unauthorized"}
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    assert cache_of(app).no_full == {}                                  # the pair failed too: an auth problem, not a missing fn


# ---------- writes ----------

def test_write_through_patches_ticket_and_list_at_once(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    call(c, tok, "rozela", "apiSaveDraft", {"id": "t1", "text": "my new draft"})
    j = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).get_json()
    assert j["cache"]["hit"] and j["ticket"]["draft_text"] == "my new draft"
    call(c, tok, "rozela", "apiClose", {"id": "t1"})
    cache_of(app).drain()
    lst = post(c, tok, "/api/rozela/list", {}).get_json()
    row = [r for r in lst["tickets"] if r["id"] == "t1"][0]
    assert row["status"] == "done" and row["handled_by"] == "noa"
    assert lst["counts"].get("done") == 1 and lst["counts"].get("ready", 0) == 0


def test_refused_write_invalidates_and_revalidates(app, pw_hash, transport):
    base = make_reply()
    transport.reply = base
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    transport.reply = lambda u, b: {"ok": False, "error": "already_handled"} if b["fn"] == "apiSend" else base(u, b)
    transport.calls.clear()
    call(c, tok, "rozela", "apiSend", {"id": "t1", "text": "x"})
    cache_of(app).drain()
    assert "apiTicketFull" in fns(transport)                           # the stale copy was refreshed in the background


# ---------- prefetch + polling ----------

def test_prefetch_warms_with_at_most_three_engine_calls_at_once(make_app, pw_hash, transport):
    counter = {"now": 0, "max": 0, "lock": threading.Lock()}
    transport.reply = make_reply(delay=0.15, counter=counter)
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    ids = ["p%d" % i for i in range(20)]
    j = post(c, tok, "/api/rozela/prefetch", {"ids": ids}).get_json()
    assert j["queued"] == 15                                           # first 15 only
    cache_of(app).drain(15)
    assert counter["max"] == 2                                         # really parallel, and capped at 2 per brand
    n = len(transport.calls)
    assert all(post(c, tok, "/api/rozela/ticket", {"id": i}).get_json()["cache"]["hit"] for i in ids[:15])
    assert len(transport.calls) == n
    assert post(c, tok, "/api/rozela/prefetch", {"ids": ids[:15]}).get_json()["queued"] == 0   # already warm


def test_changes_patch_rows_and_fall_back_to_boot(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    j = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    assert j["via"] == "apiChanges" and j["version"] == 8 and j["changed"][0]["status"] == "done"
    assert [b["args"] for _, b in transport.calls if b["fn"] == "apiChanges"][0]["since"] == 7       # int, final shape
    assert post(c, tok, "/api/rozela/list", {}).get_json()["tickets"][0]["status"] == "done"
    transport.reply = make_reply(changes=False)
    j = post(c, tok, "/api/rozela/changes", {"since": 8}).get_json()
    assert j["via"] == "apiBoot" and j["changed"][0]["status"] == "ready"   # diff vs the cached rows
    transport.calls.clear()
    post(c, tok, "/api/rozela/changes", {"since": 8})
    assert "apiChanges" not in fns(transport)                           # remembered: engine has no apiChanges yet


def test_changes_reset_and_removed(app, pw_hash, transport):
    transport.reply = make_reply(changes="reset")
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    j = post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()
    assert j["via"] == "apiBoot"                                        # reset -> one full apiBoot (counts stay right)
    base = make_reply()
    transport.reply = lambda u, b: {"ok": True, "version": 10, "tickets": [], "removed": ["t1"]} if b["fn"] == "apiChanges" else base(u, b)
    j = post(c, tok, "/api/rozela/changes", {"since": 9}).get_json()
    assert j["removed"] == ["t1"] and post(c, tok, "/api/rozela/list", {}).get_json()["tickets"] == []


def test_user_manager_polls_without_apichanges(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    transport.calls.clear()
    assert post(c, tok, "/api/rozela/changes", {"since": 7}).get_json()["ok"]
    assert fns(transport) == ["apiBoot"]                                 # apiChanges is agent/admin only


def test_fresh_click_asks_the_engine_for_fresh_data(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/ticket", {"id": "t1"})
    post(c, tok, "/api/rozela/ticket", {"id": "t1", "revalidate": True})
    post(c, tok, "/api/rozela/ticket", {"id": "t1", "fresh": True})
    full = [b["args"] for _, b in transport.calls if b["fn"] == "apiTicketFull"]
    assert full == [{"id": "t1", "brand": "rozela"}, {"id": "t1", "brand": "rozela"}, {"id": "t1", "fresh": True, "brand": "rozela"}]


def test_internal_perf_fns_not_reachable_from_browser(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    for fn in ("apiTicketFull", "apiChanges"):
        assert call(c, tok, "rozela", fn, {"id": "t1"}).status_code == 404
    assert transport.calls == []


def test_server_timing_on_api_only(app, pw_hash, transport):
    transport.reply = make_reply()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    h = post(c, tok, "/api/rozela/ticket", {"id": "t1"}).headers["Server-Timing"]
    assert 'engine;desc="apiTicketFull";dur=' in h and "app;dur=" in h
    post(c, tok, "/api/rozela/list", {})
    h = post(c, tok, "/api/rozela/changes", {"since": 7}).headers["Server-Timing"]
    assert 'gas;desc="apiChanges";dur=12.0' in h                         # serverMs from the engine
    assert "Server-Timing" not in c.get("/cs").headers
