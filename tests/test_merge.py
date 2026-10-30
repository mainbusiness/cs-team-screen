"""apiMergeTickets ("מיזוג פניות", the CS team 2026-10-31): the proxy's shapes, the Hebrew refusals, and the cache after a merge."""
import messages
from conftest import call, logged_in
from test_cache import make_reply, post


def merge_reply(base):
    def reply(url, body):
        if body["fn"] == "apiMergeTickets":
            a = body["args"]
            return {"ok": True, "id": a["id"], "from": a["from"], "threads": 2, "reopened": False, "redraft": True}
        return base(url, body)
    return reply


def test_proxy_forwards_only_two_ticket_ids(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = merge_reply(make_reply())
    j = call(c, tok, "rozela", "apiMergeTickets", {"id": "t1", "from": "t2", "brand": "celesta", "role": "admin", "apply": 1}).get_json()
    assert j["ok"] is True and j["id"] == "t1" and j["from"] == "t2"
    sent = next(b for _, b in transport.calls if b.get("fn") == "apiMergeTickets")
    assert set(sent["args"]) <= {"id", "from", "brand"} and sent["args"]["from"] == "t2"   # brand = the engine's own brand check
    for bad in ({"id": "t1"}, {"id": "t1", "from": "x y"}, {"id": "t1", "from": "a" * 81}, {"id": "../t1", "from": "t2"}, {"id": "t1", "from": 7}):
        assert call(c, tok, "rozela", "apiMergeTickets", bad).status_code == 400, bad


def test_a_reply_about_other_tickets_is_never_success(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": True, "id": "t1", "from": "t9", "threads": 2}
    j = call(c, tok, "rozela", "apiMergeTickets", {"id": "t1", "from": "t2"}).get_json()
    assert j["ok"] is not True
    transport.reply = {"ok": True}                                   # a bare doGet answer
    assert call(c, tok, "rozela", "apiMergeTickets", {"id": "t1", "from": "t2"}).get_json()["ok"] is not True


def test_refusals_read_in_hebrew_and_english():
    for code, he_word in (("merge_same", "לתוך עצמה"), ("merge_channel", "וואטסאפ"), ("merge_already", "כבר מוזגה")):
        assert he_word in messages.engine_error_msg({"ok": False, "error": code}, "apiMergeTickets", "he")
        en = messages.engine_error_msg({"ok": False, "error": code}, "apiMergeTickets", "en")
        assert en and "merge" in en.lower()


def test_after_a_merge_the_other_ticket_reads_merged_and_related_searches_are_dropped(app, pw_hash, transport):
    transport.reply = merge_reply(make_reply())
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})                              # the list holds t1
    cache = app.extensions["cs"]["ticket_cache"]
    cache.mem.setdefault("_related", {})[("rozela", "r@example.com")] = (cache.clock(), [{"id": "t1", "status": "ready"}])
    cache.mem["_related"][("celesta", "c@example.com")] = (cache.clock(), [{"id": "t1"}])
    j = call(c, tok, "rozela", "apiMergeTickets", {"id": "t5", "from": "t1"}).get_json()
    assert j["ok"] is True
    rows = cache._bucket("rozela")["boot"]["data"]["tickets"]
    t1 = next(r for r in rows if r["id"] == "t1")
    assert t1["status"] == "done" and t1["category"] == "merged" and t1["handled_by"] == "noa"
    assert ("rozela", "r@example.com") not in cache.mem["_related"]
    assert ("celesta", "c@example.com") in cache.mem["_related"], "another brand's searches are left alone"
    assert not any(r["id"] == "t5" and r.get("category") == "merged" for r in rows)


def test_a_merged_ticket_the_list_never_showed_is_not_added_half_empty(app, pw_hash, transport):
    transport.reply = merge_reply(make_reply())
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    post(c, tok, "/api/rozela/list", {})
    assert call(c, tok, "rozela", "apiMergeTickets", {"id": "t1", "from": "tzz"}).get_json()["ok"] is True
    rows = app.extensions["cs"]["ticket_cache"]._bucket("rozela")["boot"]["data"]["tickets"]
    assert not any(r["id"] == "tzz" for r in rows)


def test_merge_is_a_work_role_call(app, pw_hash, transport):
    transport.reply = merge_reply(make_reply())
    c, tok = logged_in(app, pw_hash, "um", ["user-manager"], ["rozela"])
    r = call(c, tok, "rozela", "apiMergeTickets", {"id": "t1", "from": "t2"})
    assert r.status_code in (401, 403) or r.get_json()["ok"] is False
    assert not any(b.get("fn") == "apiMergeTickets" for _, b in transport.calls)
