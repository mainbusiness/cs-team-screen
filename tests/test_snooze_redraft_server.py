"""Owner, 2026-10-14 (from the CS team): "תשובה אחרת" (apiRedraftOne through the proxy) and "לענות מאוחר יותר" (snooze.py) — the server side."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import engine_proxy
import messages
import snooze
from conftest import logged_in, call, valid_reply, add_user, client_for, login, spa_csrf

TZ = ZoneInfo("Asia/Jerusalem")


def il(y, mo, d, hh, mm):
    return datetime(y, mo, d, hh, mm, tzinfo=TZ).timestamp()


# ---------------------------------------------------------------- the different answer (proxy)

def test_redraft_args_pass_the_allowlist_and_nothing_else_does():
    ok = {"id": "t1", "hint": "יותר קצר", "seen": "2026-10-14T08:00:00Z", "last": "2026-10-14T07:59:00.123Z", "base": "0a1b2c3d"}
    assert engine_proxy.clean_args("apiRedraftOne", dict(ok, junk=1, text="x")) == ok
    assert engine_proxy.clean_args("apiRedraftOne", {"id": "t1", "base": "0a1b2c3d", "undo": True})["undo"] is True
    assert "undo" not in engine_proxy.clean_args("apiRedraftOne", {"id": "t1", "base": "0a1b2c3d", "undo": "yes"})       # only a real true
    for bad in ({"base": "XYZ"}, {"base": ""}, {"hint": "x" * 201}, {"seen": "<b>"}, {"last": 5}, {"hint": 7}):
        with pytest.raises(engine_proxy.ProxyError):
            engine_proxy.clean_args("apiRedraftOne", dict({"id": "t1", "base": "0a1b2c3d"}, **bad))
    with pytest.raises(engine_proxy.ProxyError):
        engine_proxy.clean_args("apiRedraftOne", {"id": "t1"})                     # no base: the engine could replace a draft nobody saw


def test_redraft_goes_to_the_engine_its_answer_must_carry_the_draft_and_refusals_read_as_hebrew(make_app, pw_hash, transport):
    app = make_app()
    c, tok = logged_in(app, pw_hash, "dana", ["agent"], ["rozela"])
    j = call(c, tok, "rozela", "apiRedraftOne", {"id": "t1", "hint": "יותר קצר", "base": "0a1b2c3d", "seen": ""}).get_json()
    assert j["ok"] is True and j["draft"]
    sent = [b for _, b in transport.calls if b["fn"] == "apiRedraftOne"][-1]["args"]
    assert sent["hint"] == "יותר קצר" and sent["base"] == "0a1b2c3d"
    transport.reply = lambda url, body: {"ok": True} if body["fn"] == "apiRedraftOne" else valid_reply(url, body)
    j = call(c, tok, "rozela", "apiRedraftOne", {"id": "t1", "base": "0a1b2c3d"}).get_json()
    assert j["ok"] is False, "a bare ok is not a new draft"
    transport.reply = lambda url, body: ({"ok": False, "error": "rate_limited", "scope": "ticket", "retryAfterSeconds": 600}
                                         if body["fn"] == "apiRedraftOne" else valid_reply(url, body))
    j = call(c, tok, "rozela", "apiRedraftOne", {"id": "t1", "base": "0a1b2c3d"}).get_json()
    assert j["error"] == "rate_limited" and "בעוד 10 דקות" in j["msg"], j["msg"]
    assert "rate_limited" not in j["msg"]
    for code in ("changed_meanwhile", "no_new_draft", "same_draft", "ai_failed", "nothing_to_undo", "wa_send_in_flight", "bad_hint"):
        m = messages.engine_error_msg({"ok": False, "error": code}, "apiRedraftOne", "he")
        assert m and code not in m and any("֐" <= ch <= "׿" for ch in m), (code, m)
        assert messages.engine_error_msg({"ok": False, "error": code}, "apiRedraftOne", "en").isascii()


# ---------------------------------------------------------------- answer later (snooze)

ROW = {"id": "t1", "status": "ready", "channel": "email", "emails_count": 1, "waiting_since": "2026-10-14T07:00:00Z", "name": "דנה"}


def snooze_app(make_app, transport, tmp_path, now, rows=(ROW,)):
    store = snooze.SnoozeStore(str(tmp_path / "snooze.json"), clock=lambda: now[0])
    rows = [dict(r) for r in rows]
    transport.reply = lambda url, body: ({"ok": True, "tickets": rows, "counts": {}, "version": 1} if body["fn"] in ("apiBoot",)
                                         else valid_reply(url, body))
    app = make_app(SNOOZE_STORE=store)
    return app, store, rows


def as_user(app, pw_hash, name, roles=("agent",), brands=("rozela",)):
    c, tok = logged_in(app, pw_hash, name, list(roles), list(brands))
    assert c.post("/api/rozela/list", json={}, headers={"X-CSRF-Token": tok}).get_json()["ok"] is True    # the server's copy of the list
    return c, tok


def snz(c, tok, body, brand="rozela"):
    return c.post("/api/%s/snooze" % brand, json=body, headers={"X-CSRF-Token": tok})


def test_snooze_is_his_own_survives_a_restart_and_is_refused_when_nobody_else_would_see_it(make_app, pw_hash, transport, tmp_path):
    now = [il(2026, 10, 14, 10, 0)]
    app, store, _ = snooze_app(make_app, transport, tmp_path, now)
    dana, dt = as_user(app, pw_hash, "dana")
    lyra, lt = as_user(app, pw_hash, "lyra")
    r = snz(dana, dt, {"id": "t1", "kind": "1h"})
    assert r.status_code == 200, r.get_json()
    rec = r.get_json()["snooze"]
    assert (rec["brand"], rec["id"], rec["until"]) == ("rozela", "t1", now[0] + 3600)
    assert rec["n"] == 1 and rec["ws"] == ROW["waiting_since"], "what the row looked like: a row past it = the customer wrote"
    assert [x["id"] for x in dana.get("/api/snooze").get_json()["snoozes"]] == ["t1"]
    assert lyra.get("/api/snooze").get_json()["snoozes"] == [], "only HIS list"
    # lyra is the only other agent: if she snoozes it too, nobody sees it -> refused
    r = snz(lyra, lt, {"id": "t1", "kind": "30m"})
    assert (r.status_code, r.get_json()["error"]) == (409, "snooze_everyone")
    assert "חייבת להישאר אצל מישהו" in r.get_json()["msg"]
    # a restart: a new store on the same file still has it
    assert [x["id"] for x in snooze.SnoozeStore(store.path, clock=lambda: now[0]).mine("dana")] == ["t1"]
    # back now
    assert snz(dana, dt, {"id": "t1", "cancel": True}).get_json()["ok"] is True
    assert dana.get("/api/snooze").get_json()["snoozes"] == []
    assert snz(lyra, lt, {"id": "t1", "kind": "30m"}).status_code == 200, "now dana sees it again: lyra may"


def test_snooze_refusals_end_of_day_and_roles(make_app, pw_hash, transport, tmp_path):
    now = [il(2026, 10, 14, 16, 50)]
    app, store, rows = snooze_app(make_app, transport, tmp_path, now,
                                  rows=(ROW, dict(ROW, id="t2", status="sent")))
    dana, dt = as_user(app, pw_hash, "dana")
    as_user(app, pw_hash, "lyra")
    assert (snz(dana, dt, {"id": "t1", "kind": "eod"}).get_json()["error"]) == "snooze_too_late"        # 10 minutes before 17:00
    now[0] = il(2026, 10, 14, 11, 20)
    assert snz(dana, dt, {"id": "t1", "kind": "eod"}).get_json()["snooze"]["until"] == il(2026, 10, 14, 17, 0)
    assert snz(dana, dt, {"id": "t2", "kind": "1h"}).get_json()["error"] == "snooze_not_open"
    assert snz(dana, dt, {"id": "nope", "kind": "1h"}).get_json()["error"] == "snooze_not_open"
    assert snz(dana, dt, {"id": "t1", "kind": "3h"}).status_code == 400
    assert snz(dana, dt, {"id": "t1", "kind": "1h"}, brand="celesta").status_code == 403
    add_user(app, pw_hash, "boss", ["user-manager"], ["rozela"])
    c = client_for(app, "10.0.0.9")
    login(c, "boss")
    assert c.get("/api/snooze").status_code == 403


def test_the_customer_writing_again_ends_it_and_the_board_counts_only_live_ones(make_app, pw_hash, transport, tmp_path):
    now = [il(2026, 10, 14, 10, 0)]
    app, store, rows = snooze_app(make_app, transport, tmp_path, now, rows=(ROW, dict(ROW, id="t3", channel="whatsapp", wa_last_in="2026-10-14T06:00:00Z")))
    dana, dt = as_user(app, pw_hash, "dana")
    as_user(app, pw_hash, "lyra")
    assert snz(dana, dt, {"id": "t1", "kind": "2h"}).status_code == 200
    assert snz(dana, dt, {"id": "t3", "kind": "2h"}).status_code == 200
    rec = {r["id"]: r for r in store.mine("dana")}
    assert not snooze.voided(rec["t1"], ROW)
    assert snooze.voided(rec["t1"], dict(ROW, emails_count=2)), "another customer message"
    assert snooze.voided(rec["t1"], dict(ROW, waiting_since="2026-10-14T07:30:00Z")), "a new waiting period after the snooze"
    assert snooze.voided(rec["t3"], dict(rows[1], wa_last_in="2026-10-14T07:05:00Z")), "a newer WhatsApp message"
    assert not snooze.voided(rec["t3"], rows[1])
    add_user(app, pw_hash, "guy", ["admin"], ["rozela"])
    g = client_for(app, "10.0.0.7")
    login(g, "guy")
    agents = {a["user"]: a for a in g.get("/api/dash?range=1").get_json()["agents"]}
    assert agents["dana"]["snoozed_now"] == 2 and agents["lyra"]["snoozed_now"] == 0
    now[0] += 2 * 3600 + 1                                                             # the time is up
    agents = {a["user"]: a for a in g.get("/api/dash?range=1").get_json()["agents"]}
    assert agents["dana"]["snoozed_now"] == 0
    assert [x["id"] for x in sorted(dana.get("/api/snooze").get_json()["snoozes"], key=lambda x: x["id"])] == ["t1", "t3"], \
        "an ended snooze is still listed for a while: the screen puts the row on top until he opens it"
    now[0] += snooze.KEEP_ENDED_S + 5
    snz(dana, dt, {"id": "t1", "cancel": True})                                       # any write prunes the old ones
    assert store.mine("dana") == []
