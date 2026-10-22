"""Managers' notes to the AI (2026-10-11): the three fns are admin-only in Flask too, and their arguments are rebuilt and checked
before anything reaches an engine."""
import pytest

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


# 2026-10-22: suggestions from the team's corrections (engine AiLearn.gs). A read and a write, both admin only; the decision is bound to
# THAT suggestion, and an approval must carry the note the engine made (id = the suggestion's id without its 's').
SID = "s0123456789abcdef"


def sugg_reply(url, body):
    a = body.get("args") or {}
    fn = body["fn"]
    if fn == "apiAiNoteSuggestions":
        return {"ok": True, "suggestions": [{"id": SID, "text": "t", "count": 3, "state": "pending", "examples": []}], "corrections": 41}
    if fn == "apiAiNoteSuggestDecide":
        s = {"id": a["id"], "text": "t", "state": "approved" if a["decision"] == "approve" else "rejected"}
        return {"ok": True, "suggestion": s, "note": {"id": a["id"][1:], "scope": "brand", "text": a.get("text", "t")}} if a["decision"] == "approve" \
            else {"ok": True, "suggestion": s}
    if fn == "apiResult":
        return {"ok": True, "found": False}
    return {"ok": True}


def test_suggestions_are_admin_only_and_nothing_reaches_the_engine(app, pw_hash, transport):
    import engine_proxy
    assert engine_proxy.FN_TABLE["apiAiNoteSuggestions"][0] == engine_proxy.ADMIN_ONLY
    assert engine_proxy.FN_TABLE["apiAiNoteSuggestDecide"][0] == engine_proxy.ADMIN_ONLY
    assert engine_proxy.is_read("apiAiNoteSuggestions", {}) and not engine_proxy.is_read("apiAiNoteSuggestDecide", {})   # a decide is never retried blind
    for name, roles in (("noa", ["agent"]), ("um", ["user-manager"])):
        c, tok = logged_in(app, pw_hash, name, roles, ["rozela"])
        for fn, args in (("apiAiNoteSuggestions", {}), ("apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"})):
            r = call(c, tok, "rozela", fn, args)
            assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role", (name, fn)
    assert transport.calls == []


def test_decide_args_are_rebuilt_and_bad_ones_never_leave_flask(app, pw_hash, transport):
    transport.reply = sugg_reply
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    bad = [({"id": "0123456789abcdef", "decision": "approve"}, "bad_request"),          # no 's'
           ({"id": "s0123456789ABCDEF", "decision": "approve"}, "bad_request"),         # upper case
           ({"id": "s0123456789abcde", "decision": "approve"}, "bad_request"),          # 15 hex
           ({"id": SID, "decision": "approved"}, "bad_request"),
           ({"id": SID}, "bad_request"),
           ({"id": SID, "decision": "approve", "text": "   "}, "bad_ai_note"),
           ({"id": SID, "decision": "approve", "text": "x" * 601}, "bad_ai_note")]
    for args, code in bad:
        r = call(c, tok, "rozela", "apiAiNoteSuggestDecide", args)
        assert r.status_code == 400 and r.get_json()["error"] == code, (args, r.get_json())
    assert transport.calls == []
    r = call(c, tok, "rozela", "apiAiNoteSuggestDecide", {"id": SID, "decision": "approve", "text": "  edited  ", "scope": "all", "brand": "celesta"})
    assert r.status_code == 200 and r.get_json()["note"]["id"] == SID[1:]
    sent = [b for _, b in transport.calls if b["fn"] == "apiAiNoteSuggestDecide"]
    assert sent[-1]["args"] == {"id": SID, "decision": "approve", "text": "edited", "brand": "rozela"}       # trimmed; extra keys dropped
    assert sent[-1].get("rid"), "a write carries a rid (lost replies are resolved by it, never re-run blind)"
    call(c, tok, "rozela", "apiAiNoteSuggestDecide", {"id": SID, "decision": "reject", "text": "ignored"})
    assert [b for _, b in transport.calls if b["fn"] == "apiAiNoteSuggestDecide"][-1]["args"] == {"id": SID, "decision": "reject", "brand": "rozela"}
    call(c, tok, "rozela", "apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"})
    assert [b for _, b in transport.calls if b["fn"] == "apiAiNoteSuggestDecide"][-1]["args"] == {"id": SID, "decision": "approve", "brand": "rozela"}
    j = call(c, tok, "rozela", "apiAiNoteSuggestions").get_json()
    assert j["ok"] is True and j["corrections"] == 41 and j["suggestions"][0]["id"] == SID


@pytest.mark.parametrize("fn,args,reply", [
    ("apiAiNoteSuggestions", {}, {"ok": True}),                                                    # the bare doGet answer
    ("apiAiNoteSuggestions", {}, {"ok": True, "suggestions": [], "corrections": True}),            # a bool is not a count
    ("apiAiNoteSuggestions", {}, {"ok": True, "suggestions": {}, "corrections": 3}),
    ("apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"}, {"ok": True}),
    ("apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"},                                 # an answer about ANOTHER suggestion
     {"ok": True, "suggestion": {"id": "sffffffffffffffff", "state": "approved"}, "note": {"id": "ffffffffffffffff"}}),
    ("apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"},                                 # "approved" without the note
     {"ok": True, "suggestion": {"id": SID, "state": "approved"}}),
    ("apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"},                                 # a note with another id
     {"ok": True, "suggestion": {"id": SID, "state": "approved"}, "note": {"id": "abcdefabcdefabcd"}}),
    ("apiAiNoteSuggestDecide", {"id": SID, "decision": "reject"},                                  # asked to reject, told approved
     {"ok": True, "suggestion": {"id": SID, "state": "approved"}}),
])
def test_a_reply_that_is_not_about_this_suggestion_is_never_used(app, pw_hash, transport, monkeypatch, fn, args, reply):
    import engine_proxy
    monkeypatch.setattr(engine_proxy, "_sleep", lambda s: None)
    monkeypatch.setattr(engine_proxy, "RESEND_MIN_AGE_S", 0)
    transport.reply = lambda url, body: {"ok": True, "found": False} if body["fn"] == "apiResult" else dict(reply)
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    j = call(c, tok, "rozela", fn, args).get_json()
    assert j["ok"] is False and "suggestion" not in j and "suggestions" not in j, j


def test_a_decision_made_before_is_a_noop_the_screen_can_use(app, pw_hash, transport):
    transport.reply = lambda url, body: {"ok": True, "noop": True, "suggestion": {"id": SID, "state": "rejected"}}
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    j = call(c, tok, "rozela", "apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"}).get_json()
    assert j["ok"] is True and j["noop"] is True and j["suggestion"]["state"] == "rejected"


def test_suggestion_errors_get_their_own_hebrew_and_english_lines(app, pw_hash, transport):
    import messages
    c, tok = logged_in(app, pw_hash, "guy", ["admin"], ["rozela"])
    for code, he in (("bad_decision", "החלטה לא מוכרת על ההצעה"), ("not_found", "ההצעה כבר לא קיימת"), ("too_many", "הגעתם ל-60 הערות"),
                     ("bad_text", "נוסח ההערה: בין 1 ל-600 תווים")):
        transport.reply = lambda url, body, code=code: {"ok": False, "error": code}
        j = call(c, tok, "rozela", "apiAiNoteSuggestDecide", {"id": SID, "decision": "approve"}).get_json()
        assert j["ok"] is False and he in j["msg"], (code, j)
    assert "suggestion" in messages.engine_error_msg({"error": "not_found"}, "apiAiNoteSuggestDecide", "en")
    assert "note no longer exists" in messages.engine_error_msg({"error": "not_found"}, "apiAiNoteDelete", "en")   # the notes keep theirs


def test_mock_suggestions_match_the_engine_contract():
    import mock_engine
    e = mock_engine.MockEngines("k" * 48, 0)
    admin = {"user": "guy", "role": "admin", "lang": "he"}
    r = e.apiAiNoteSuggestions("rozela", {}, admin)
    assert r["ok"] and isinstance(r["corrections"], int) and len(r["suggestions"]) == 2
    assert [s["at"] for s in r["suggestions"]] == sorted([s["at"] for s in r["suggestions"]], reverse=True)    # newest first
    assert all(s["state"] == "pending" and len(s["examples"]) <= 2 for s in r["suggestions"])
    sid = r["suggestions"][0]["id"]
    ok = e.apiAiNoteSuggestDecide("rozela", {"id": sid, "decision": "approve", "text": " edited "}, admin)
    assert ok["suggestion"]["state"] == "approved" and ok["note"]["id"] == sid[1:] and ok["note"]["text"] == "edited" and ok["note"]["scope"] == "brand"
    assert e.apiAiNoteSuggestDecide("rozela", {"id": sid, "decision": "reject"}, admin)["noop"] is True
    assert sid not in [s["id"] for s in e.apiAiNoteSuggestions("rozela", {}, admin)["suggestions"]]          # pending only
    assert e.apiAiNoteSuggestDecide("rozela", {"id": "s" + "0" * 16, "decision": "reject"}, admin) == {"ok": False, "error": "not_found"}
    assert e.apiAiNoteSuggestDecide("rozela", {"id": sid, "decision": "maybe"}, admin)["error"] == "bad_decision"
    # redraft: an active note added / deleted says how many open drafts are rewritten; a note waiting for its file says nothing
    add = e.apiAiNoteAdd("rozela", {"id": "plainnote1", "scope": "brand", "text": "לפתוח בשם"}, admin)
    assert isinstance(add["redraft"], int) and add["redraft"] > 0
    assert "redraft" not in e.apiAiNoteAdd("rozela", {"id": "claimnote1", "scope": "brand", "text": "יש לנו אישור FDA"}, admin)
    assert e.apiAiNoteDelete("rozela", {"id": "plainnote1"}, admin)["redraft"] == add["redraft"]
    assert "redraft" not in e.apiAiNoteDelete("rozela", {"id": "claimnote1"}, admin)
