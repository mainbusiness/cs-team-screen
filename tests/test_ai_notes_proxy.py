"""Managers' notes to the AI (2026-10-11): the three fns are admin-only in Flask too, and their arguments are rebuilt and checked
before anything reaches an engine."""
from conftest import call, logged_in

FNS = (("apiAiNotes", {}), ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "note"}),
       ("apiAiNoteDelete", {"id": "abcdef123456"}))


def reply(url, body):
    a = body.get("args") or {}
    if body["fn"] == "apiAiNotes":
        return {"ok": True, "notes": []}
    if body["fn"] == "apiAiNoteAdd":
        return {"ok": True, "note": dict(a, by="x", at="2026-10-11T08:00:00Z")}
    return {"ok": True}


def test_agent_and_user_manager_get_403_and_nothing_reaches_the_engine(app, pw_hash, transport):
    for name, roles in (("noa", ["agent"]), ("um", ["user-manager"])):
        c, tok = logged_in(app, pw_hash, name, roles, ["rozela"])
        for fn, args in FNS:
            r = call(c, tok, "rozela", fn, args)
            assert r.status_code == 403, (name, fn)
            assert r.get_json()["error"] == "forbidden_role"
    assert transport.calls == []


def test_admin_reaches_the_engine_with_clean_args(app, pw_hash, transport):
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    r = call(c, tok, "rozela", "apiAiNoteAdd", {"id": "abcdef123456", "scope": "brand", "text": "  hello  ", "by": "someone", "brand": "celesta"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    sent = [b for _, b in transport.calls if b["fn"] == "apiAiNoteAdd"][-1]
    assert sent["args"] == {"id": "abcdef123456", "scope": "brand", "text": "hello", "brand": "rozela"}   # trimmed; extra keys dropped
    assert call(c, tok, "rozela", "apiAiNotes").get_json()["notes"] == []
    assert call(c, tok, "rozela", "apiAiNoteDelete", {"id": "abcdef123456"}).status_code == 200


def test_bad_note_args_never_leave_flask(app, pw_hash, transport):
    transport.reply = reply
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    bad = [("apiAiNoteAdd", {"id": "ABCDEF123456", "scope": "all", "text": "x"}, "bad_request"),      # upper case
           ("apiAiNoteAdd", {"id": "abc", "scope": "all", "text": "x"}, "bad_request"),               # too short
           ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "everyone", "text": "x"}, "bad_request"),
           ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "   "}, "bad_ai_note"),
           ("apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "x" * 601}, "bad_ai_note"),
           ("apiAiNoteAdd", {"scope": "all", "text": "x"}, "bad_request"),
           ("apiAiNoteDelete", {"id": "abcdef12345-"}, "bad_request")]
    for fn, args, code in bad:
        r = call(c, tok, "rozela", fn, args)
        assert r.status_code == 400 and r.get_json()["error"] == code, (fn, args, r.get_json())
    assert transport.calls == []
    assert call(c, tok, "rozela", "apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "x" * 600}).status_code == 200


def test_the_61st_note_gets_a_clear_hebrew_message(app, pw_hash, transport):
    transport.reply = lambda url, body: {"ok": False, "error": "too_many", "max": 60}
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    r = call(c, tok, "rozela", "apiAiNoteAdd", {"id": "abcdef123456", "scope": "all", "text": "x"})
    assert r.get_json()["msg"] == "הגעתם ל-60 הערות — מחקו הערה ישנה כדי להוסיף"


def test_mock_engine_matches_the_deployed_contract():
    import mock_engine
    e = mock_engine.MockEngines("k" * 48, 0)
    admin = {"user": "guy", "role": "admin", "lang": "he"}
    assert e.apiAiNoteAdd("rozela", {"id": "abcdefgh1", "scope": "all", "text": " a "}, admin)["note"]["text"] == "a"
    again = e.apiAiNoteAdd("rozela", {"id": "abcdefgh1", "scope": "all", "text": "different"}, admin)
    assert again["noop"] is True and again["note"]["text"] == "a"                     # repeat id: the stored note, even if the text differs
    for i in range(59):
        assert e.apiAiNoteAdd("rozela", {"id": "n%08d" % i, "scope": "brand", "text": "t"}, admin)["ok"]
    assert e.apiAiNoteAdd("rozela", {"id": "zzzzzzzz9", "scope": "brand", "text": "t"}, admin) == {"ok": False, "error": "too_many", "max": 60}
    assert e.apiAiNotes("rozela", {}, admin)["notes"][0]["id"] == "n00000058"         # newest first
    assert e.apiAiNoteDelete("rozela", {"id": "nothere11"}, admin) == {"ok": True, "noop": True}
    for t in e.brands["rozela"]["tickets"]:
        ex = e.apiTicketFull("rozela", {"id": t["id"]}, admin)["extras"]
        assert ("mailbox" in ex) is (t["channel"] != "whatsapp"), t["id"]          # WhatsApp: no mailbox key at all
    assert e.dispatch is not None and "apiAiNotes" in mock_engine.TABLE and mock_engine.TABLE["apiAiNotes"] == ("admin",)


# 2026-10-18: the note's document and its live check — admin only, the file must be an upload id, and the answer must be about THAT note.
def test_attach_and_check_admin_only_clean_args_and_bound_replies(app, pw_hash, transport):
    def rep(url, body):
        a = body.get("args") or {}
        if body["fn"] == "apiAiNoteAttach":
            return {"ok": True, "note": {"id": a["id"], "file": {"id": a["file"]}, "status": "active"}}
        if body["fn"] == "apiAiNoteCheck":
            return {"ok": True, "note": {"id": a["id"], "check": {"follows": True}}}
        return {"ok": True}
    transport.reply = rep
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    for fn, args in (("apiAiNoteAttach", {"id": "abcdef123456", "file": "a" + "0" * 24}), ("apiAiNoteCheck", {"id": "abcdef123456"})):
        assert call(c, tok, "rozela", fn, args).status_code == 403
    assert transport.calls == []
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    for bad in ({"id": "abcdef123456", "file": "../etc"}, {"id": "abcdef123456"}, {"id": "BAD", "file": "a" + "0" * 24}):
        assert call(c, tok, "rozela", "apiAiNoteAttach", bad).status_code == 400, bad
    assert transport.calls == []
    r = call(c, tok, "rozela", "apiAiNoteAttach", {"id": "abcdef123456", "file": "a" + "1" * 24, "extra": "x"})
    assert r.status_code == 200 and r.get_json()["note"]["file"]["id"] == "a" + "1" * 24
    assert [b for _, b in transport.calls if b["fn"] == "apiAiNoteAttach"][-1]["args"] == {"id": "abcdef123456", "file": "a" + "1" * 24, "brand": "rozela"}
    assert call(c, tok, "rozela", "apiAiNoteCheck", {"id": "abcdef123456"}).get_json()["note"]["check"]["follows"] is True
