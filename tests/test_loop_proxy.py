"""Loop pause / resume (Owner, 2026-11-20): the proxy's shapes. A pause is always dated (weeks 2 / 4 / 6 / 8 as a string), the browser can never
send more than the three fields, a reply without the read-back verdict for THIS contract is not an answer, and the viewer / manager roles are refused."""
import pytest

from conftest import call, logged_in

CID = "loop-48597382"


@pytest.mark.parametrize("weeks", [None, "", "0", "1", "3", "5", "9", "28", "4 ", 4, True, "4; drop"])
def test_pause_without_a_valid_dated_duration_never_reaches_the_engine(app, pw_hash, transport, weeks):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    args = {"id": "t1", "contractId": CID}
    if weeks is not None:
        args["weeks"] = weeks
    n = len(transport.calls)
    assert call(c, tok, "rozela", "apiSubPause", args).status_code == 400
    assert len(transport.calls) == n


def test_pause_shapes_stripping_and_the_verdict_check(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert call(c, tok, "rozela", "apiSubPause", {"id": "t1", "contractId": "x" * 201, "weeks": "4"}).status_code == 400
    transport.reply = {"ok": True, "verified": True, "state": "paused", "status": "PAUSED", "contractId": CID, "weeks": 4, "record": {"state": "paused"}}
    j = call(c, tok, "rozela", "apiSubPause", {"id": "t1", "contractId": CID, "weeks": "4", "email": "victim@x.com", "role": "admin", "intervalCount": "999"}).get_json()
    assert j["ok"] and j["verified"] is True
    sent = [b for _, b in transport.calls if b["fn"] == "apiSubPause"][-1]["args"]
    assert sent == {"id": "t1", "contractId": CID, "weeks": "4", "brand": "rozela"}, "only the three fields travel (+ the proxy's own brand)"
    transport.reply = {"ok": True, "state": "paused", "contractId": CID}            # no verified boolean
    assert call(c, tok, "rozela", "apiSubPause", {"id": "t1", "contractId": CID, "weeks": "4"}).get_json().get("ok") is not True
    transport.reply = {"ok": True, "verified": True, "contractId": "loop-1"}        # another contract's answer
    assert call(c, tok, "rozela", "apiSubPause", {"id": "t1", "contractId": CID, "weeks": "4"}).get_json().get("ok") is not True


def test_resume_and_preview_shapes(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": True, "verified": True, "state": "resumed", "status": "ACTIVE", "contractId": CID, "record": {}}
    assert call(c, tok, "rozela", "apiSubResume", {"id": "t1", "contractId": CID, "weeks": "4"}).get_json()["ok"]
    assert "weeks" not in [b for _, b in transport.calls if b["fn"] == "apiSubResume"][-1]["args"]
    transport.reply = {"ok": True, "id": "t1", "contracts": [], "ended": [], "weeks": [2, 4, 6, 8], "loopWrites": True}
    assert call(c, tok, "rozela", "apiSubPausePreview", {"id": "t1", "contractId": "x"}).get_json()["ok"]
    assert "contractId" not in [b for _, b in transport.calls if b["fn"] == "apiSubPausePreview"][-1]["args"]


@pytest.mark.parametrize("fn", ["apiSubPausePreview", "apiSubPause", "apiSubResume"])
def test_only_agents_and_admins_pause(app, pw_hash, transport, fn):
    for roles in (["user-manager"], ["viewer"]):
        c, tok = logged_in(app, pw_hash, "u" + roles[0], roles, ["rozela"])
        n = len(transport.calls)
        assert call(c, tok, "rozela", fn, {"id": "t1", "contractId": CID, "weeks": "4"}).status_code == 403
        assert len(transport.calls) == n


@pytest.mark.parametrize("days", [None, "", "0", "1", "14", "90", "-7", "30 ", 30, True, "30; drop"])
def test_postpone_without_one_of_loops_delay_options_never_reaches_the_engine(app, pw_hash, transport, days):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    args = {"id": "t1", "contractId": CID}
    if days is not None:
        args["days"] = days
    n = len(transport.calls)
    assert call(c, tok, "rozela", "apiSubPostpone", args).status_code == 400
    assert len(transport.calls) == n


def test_postpone_shapes_stripping_the_verdict_check_and_roles(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    transport.reply = {"ok": True, "verified": True, "state": "postponed", "status": "ACTIVE", "contractId": CID, "days": 30, "record": {"state": "postponed"}}
    j = call(c, tok, "rozela", "apiSubPostpone", {"id": "t1", "contractId": CID, "days": "30", "newBillingDateEpoch": "1", "email": "victim@x.com"}).get_json()
    assert j["ok"] and j["verified"] is True
    sent = [b for _, b in transport.calls if b["fn"] == "apiSubPostpone"][-1]["args"]
    assert sent == {"id": "t1", "contractId": CID, "days": "30", "brand": "rozela"}, "the new date is computed by the engine from Loop, never sent by the browser"
    transport.reply = {"ok": True, "state": "postponed", "contractId": CID}
    assert call(c, tok, "rozela", "apiSubPostpone", {"id": "t1", "contractId": CID, "days": "30"}).get_json().get("ok") is not True
    for roles in (["user-manager"], ["viewer"]):
        c2, tok2 = logged_in(app, pw_hash, "u" + roles[0], roles, ["rozela"])
        n = len(transport.calls)
        assert call(c2, tok2, "rozela", "apiSubPostpone", {"id": "t1", "contractId": CID, "days": "30"}).status_code == 403
        assert len(transport.calls) == n
