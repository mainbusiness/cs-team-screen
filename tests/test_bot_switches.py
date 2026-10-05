"""Engine @18 support: Dondy-bot take over, WhatsApp photo slots, and switches that never go stale on a client."""
import json
import time

import pytest

from conftest import call, logged_in
from test_cache import cache_of, fns, post


def boot_reply(state):
    def reply(url, body):
        fn = body["fn"]
        if fn == "apiBoot":
            return {"ok": True, "version": state["v"], "dryRun": state["dry"], "cancelEnabled": False, "counts": {"bot": 1},
                    "tickets": [{"id": "w1", "status": state["st"], "channel": "whatsapp"}]}
        if fn == "apiChanges":
            return {"ok": True, "version": state["v"], "tickets": [], "removed": []}
        if fn == "apiTicketFull":
            return {"ok": True, "ticket": {"id": "w1", "status": state["st"], "channel": "whatsapp"}, "extras": {}}
        if fn == "apiWaTakeOver":
            state["st"] = "action"
            return {"ok": True, "id": "w1", "status": "action"}
        if fn == "apiSettings":
            state["dry"] = body["args"]["value"] == "on"
            return {"ok": True, "key": "DRY_RUN", "from": "on", "to": body["args"]["value"]}
        return {"ok": True}
    return reply


def test_takeover_roles_and_write_through(app, pw_hash, transport):
    state = {"v": 1, "dry": False, "st": "bot"}
    transport.reply = boot_reply(state)
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    post(c, tok, "/api/rozela/ticket", {"id": "w1"})
    j = call(c, tok, "rozela", "apiWaTakeOver", {"id": "w1", "brand": "celesta"}).get_json()
    assert j["ok"] and [b for _, b in transport.calls if b["fn"] == "apiWaTakeOver"][0]["args"] == {"id": "w1", "brand": "rozela"}
    cache = cache_of(app)
    lst = post(c, tok, "/api/rozela/list", {}).get_json()
    assert [r for r in lst["tickets"] if r["id"] == "w1"][0]["status"] == "action"
    assert lst["counts"].get("bot") == 0 and lst["counts"].get("action") == 1
    cache.drain()
    c2, tok2 = logged_in(app, pw_hash, "mgr", ["user-manager"], ["rozela"])
    assert call(c2, tok2, "rozela", "apiWaTakeOver", {"id": "w1"}).status_code == 403


def test_takeover_refusal_has_hebrew():
    import messages
    assert "הבוט" in messages.engine_error_msg({"ok": False, "error": "not_bot"}, "apiWaTakeOver", "he")


def test_screen_settings_change_reaches_every_client_at_once(app, pw_hash, transport):
    state = {"v": 1, "dry": True, "st": "action"}
    transport.reply = boot_reply(state)
    agent, atok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    admin, dtok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    assert post(agent, atok, "/api/rozela/list", {}).get_json()["dryRun"] is True
    call(admin, dtok, "rozela", "apiSettings", {"action": "set", "key": "DRY_RUN", "value": "off"})
    n = len(transport.calls)
    assert post(agent, atok, "/api/rozela/list", {}).get_json()["dryRun"] is False       # patched in the cache, no engine call
    assert len(transport.calls) == n
    j = post(agent, atok, "/api/rozela/changes", {"since": 1}).get_json()                  # what every other open tab polls
    assert j["switches"]["dryRun"] is False


def test_engine_side_flip_is_seen_within_15_seconds(make_app, pw_hash, transport):
    state = {"v": 1, "dry": True, "st": "action"}
    transport.reply = boot_reply(state)
    now = [1000.0]
    import ticket_cache
    from conftest import ENGINES
    app = make_app()
    cache = ticket_cache.TicketCache(cache_of(app).root, cache_of(app).engines, transport, lambda: app.config["TOKEN_SECRET"], clock=lambda: now[0])
    app.extensions["cs"]["ticket_cache"] = cache
    app2 = make_app(TICKET_CACHE=cache)
    c, tok = logged_in(app2, pw_hash, "noa", ["agent"], ["rozela"])
    assert post(c, tok, "/api/rozela/list", {}).get_json()["dryRun"] is True
    state["dry"] = False                                                                    # flipped directly in the engine
    now[0] += 10
    assert post(c, tok, "/api/rozela/list", {"maxAge": 15}).get_json()["dryRun"] is True    # 10 s old: still fine
    now[0] += 6
    j = post(c, tok, "/api/rozela/list", {"maxAge": 15}).get_json()                         # 16 s old: re-read now
    assert j["dryRun"] is False and j["cache"]["hit"] is False
    # the poll path refreshes the switches behind apiChanges once they are older than 15 s
    state["dry"] = True
    now[0] += 16
    post(c, tok, "/api/rozela/changes", {"since": 1})
    cache.drain()
    assert post(c, tok, "/api/rozela/changes", {"since": 1}).get_json()["switches"]["dryRun"] is True
