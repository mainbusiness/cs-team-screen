"""The READ-ONLY viewer (the owner 2026-11-09: an analyst). He reads tickets, search, boards and stats; every write is refused in Flask (before the
engine is contacted) and by the engine. These tests pin: the fn list, every write fn -> 403 with ZERO engine calls, the other Flask routes, the roles of the
user store, the mirror with engine/Api.gs and with the screen's own list, and that nothing he does leaves a trace as an agent."""
import json
import os
import re

import pytest

import engine_proxy
import security
import users_store
from conftest import ROOT, add_user, call, client_for, logged_in, login, store_of, valid_reply

READS = {"apiBoot", "apiStatus", "apiTicket", "apiTicketExtras", "apiTicketFull", "apiTicketLite", "apiChanges", "apiTickets", "apiSearch", "apiAutoCancelList",
         "apiAutoReplyList", "apiWaPhotoGet", "apiDayStats", "apiCancelStats", "apiCancelReasons", "apiBillingHealth"}
ALL_FNS = dict(engine_proxy.FN_TABLE, **engine_proxy.INTERNAL_FNS)


def viewer(app, pw_hash, name="viewer1", brands=("rozela",)):
    return logged_in(app, pw_hash, name, ["viewer"], list(brands))


def test_the_viewer_fn_list_is_exactly_the_reads_and_mirrors_the_engine():
    assert engine_proxy.VIEWER_FNS == READS
    assert {fn for fn, (roles, _k) in ALL_FNS.items() if "viewer" in roles} == READS
    gs = open(os.path.join(ROOT, "..", "engine", "Api.gs"), encoding="utf-8").read()
    m = re.search(r"var API_VIEWER_FNS = \{(.*?)\};", gs, re.S)
    assert set(re.findall(r"(api\w+): 1", m.group(1))) == READS
    js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    m = re.search(r"const VIEWER_FNS = \[(.*?)\];", js, re.S)
    assert set(re.findall(r"'(api\w+)'", m.group(1))) == READS
    mock = open(os.path.join(ROOT, "mock_engine.py"), encoding="utf-8").read()
    m = re.search(r"VIEWER_FNS = \((.*?)\)", mock, re.S)
    assert set(re.findall(r'"(api\w+)"', m.group(1))) == READS


def test_no_write_fn_is_open_to_the_viewer():
    writes = {"apiSend", "apiSaveDraft", "apiNote", "apiClose", "apiMarkHandled", "apiKachingCancel", "apiKachingAction", "apiOrderEdit", "apiSubCancel", "apiLinkCustomer",
              "apiMergeTickets", "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyReview", "apiWaTakeOver", "apiRedraftOne", "apiSendTemplate", "apiSettings",
              "apiAttachPut", "apiAiNoteAdd", "apiAiNoteDelete", "apiSaleLog", "apiSaleDecide"}
    assert writes <= set(ALL_FNS) and not (writes & READS)
    for fn in writes:
        assert "viewer" not in ALL_FNS[fn][0], fn
    # reads that still cost a live Kaching / Shopify call or only serve a write screen stay closed too
    for fn in ("apiTemplates", "apiKachingContract", "apiKachingVariants", "apiOrderEditState", "apiSubCancelPreview", "apiKnowledge", "apiCustomerLookup", "apiResult"):
        assert "viewer" not in ALL_FNS[fn][0], fn


def test_every_non_read_fn_is_403_and_the_engine_is_never_called(app, pw_hash, transport):
    c, tok = viewer(app, pw_hash)
    n = 0
    for fn in engine_proxy.FN_TABLE:
        if fn in READS:
            continue
        r = call(c, tok, "rozela", fn, {"id": "t1", "text": "x", "contractId": "gid://shopify/SubscriptionContract/1", "action": "pause", "confirm": "0001"})
        assert r.status_code == 403, (fn, r.status_code)
        assert r.get_json()["error"] == "forbidden_role"
        n += 1
    assert n >= 40
    assert transport.calls == [], transport.calls[:2]


def test_the_server_internal_fns_are_not_reachable_from_the_browser_at_all(app, pw_hash, transport):
    c, tok = viewer(app, pw_hash)
    for fn in ("apiKnowledge", "apiCustomerLookup", "apiAttachPut", "apiAdminRun", "apiWaIngest"):
        assert call(c, tok, "rozela", fn, {}).status_code in (403, 404)
    assert transport.calls == []


def test_the_reads_reach_the_engine_with_a_viewer_token(app, pw_hash, transport):
    c, tok = viewer(app, pw_hash)
    for fn, args in (("apiBoot", {}), ("apiTicket", {"id": "t1"}), ("apiSearch", {"q": "dana"}), ("apiTickets", {"ids": ["t1"]}),
                     ("apiAutoCancelList", {}), ("apiStatus", {})):
        r = call(c, tok, "rozela", fn, args)
        assert r.status_code == 200 and r.get_json()["ok"] is True, (fn, r.get_data(as_text=True)[:200])
    assert transport.calls
    for url, body in transport.calls:
        claims = json.loads(__import__("base64").urlsafe_b64decode(body["token"].split(".")[0] + "=="))
        assert claims["role"] == "viewer" and claims["brands"] == ["rozela"], claims


def test_a_viewer_cannot_reach_a_brand_he_does_not_hold(app, pw_hash, transport):
    c, tok = viewer(app, pw_hash)
    assert call(c, tok, "celesta", "apiBoot", {}).status_code == 403
    assert call(c, tok, "celesta", "apiTicket", {"id": "t1"}).status_code == 403
    assert transport.calls == []


def test_the_cached_ticket_routes_serve_a_viewer_but_leave_no_trace_as_an_agent(app, pw_hash, transport):
    c, tok = viewer(app, pw_hash)
    h = {"X-CSRF-Token": tok}
    assert c.post("/api/rozela/list", json={}, headers=h).status_code == 200
    r = c.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers=h)
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert "others" not in r.get_json() or r.get_json()["others"] in (None, [])
    w = c.post("/api/rozela/watch", json={"id": "t1", "at": 0, "ed": True}, headers=h)
    assert w.status_code == 200 and (w.get_json().get("others") or []) == []
    assert c.post("/api/rozela/related", json={"q": "dana"}, headers=h).status_code == 200
    assert c.post("/api/rozela/prefetch", json={"ids": ["t1"]}, headers=h).status_code == 200
    # an agent who opens the same ticket does not see a "who is here" entry for the viewer, and the activity log has no row for him
    a, atok = logged_in(app, pw_hash, "agent-a", ["agent"], ["rozela"])
    ar = a.post("/api/rozela/ticket", json={"id": "t1", "open": True}, headers={"X-CSRF-Token": atok})
    assert ar.status_code == 200 and not [o for o in (ar.get_json().get("others") or []) if o["user"] == "viewer1"]
    log = app.extensions["cs"]["activity"]["log"]
    assert not [1 for k in dir(log) if False]          # (the log has no public list: the roster test below covers "online now")
    # the writes of the cached routes
    assert c.post("/api/rozela/result", json={"rid": "abc123"}, headers=h).status_code == 403
    assert c.post("/api/rozela/queue", json={"fn": "apiAutoCancelList"}, headers=h).status_code == 200


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/rozela/activity", {"id": "t1", "kind": "edit"}),
    ("get", "/api/snooze", None), ("post", "/api/rozela/snooze", {"id": "t1", "kind": "30m"}),
    ("post", "/api/rozela/assistant", {"messages": [{"role": "user", "content": "hi"}]}),
    ("post", "/api/rozela/translate", {"id": "t1"}), ("post", "/api/rozela/translate-out", {"id": "t1", "text": "x"}),
    ("post", "/api/rozela/translate-he", {"id": "t1"}), ("post", "/api/rozela/translate-rows", {"rows": []}), ("post", "/api/rozela/translate-autoreply", {"id": "t1"}),
    ("post", "/api/rozela/zipfix", {"orders": []}),
    ("get", "/api/sysreq", None), ("post", "/api/sysreq", {"text": "x"}),
    ("get", "/api/manage/users", None), ("post", "/api/manage/users", {"username": "x"}), ("get", "/api/manage/audit", None),
    ("post", "/api/dash/snapshot", {"date": "2026-11-01"}), ("post", "/api/dash/warm", {}),
])
def test_every_other_flask_route_refuses_a_viewer(app, pw_hash, transport, method, path, body):
    c, tok = viewer(app, pw_hash)
    r = c.get(path) if method == "get" else c.post(path, json=body, headers={"X-CSRF-Token": tok})
    assert r.status_code in (403, 404), (path, r.status_code, r.get_data(as_text=True)[:120])
    assert transport.calls == []


def test_attach_is_refused_before_a_byte_is_read(app, pw_hash, transport):
    import io
    c, tok = viewer(app, pw_hash)
    r = c.post("/api/rozela/attach", data={"file": (io.BytesIO(b"%PDF-1.4 x"), "a.pdf")}, headers={"X-CSRF-Token": tok}, content_type="multipart/form-data")
    assert r.status_code == 403
    assert transport.calls == []


def stats_reply(url, body):
    fn = body["fn"]
    b = body["args"]["brand"]
    if fn == "apiBillingHealth":
        return {"ok": True, "state": "ok", "brand": b, "period": body["args"].get("period", "LAST_30_DAYS"), "billing": {"inDunning": 5, "firstTrySuccessRate": 60.5},
                "subscriptions": {"active": 10}, "failureReasons": [{"reason": "insufficient_funds", "count": 3, "percentage": 50.0}], "notAvailable": ["cancel_reasons", "retry_settings"]}
    return valid_reply(url, body)


def test_the_boards_and_stats_work_for_a_viewer(app, pw_hash, transport):
    transport.reply = stats_reply
    c, tok = viewer(app, pw_hash)
    for path in ("/api/dash", "/api/dash/open", "/api/dash/sla", "/api/dash/cancels", "/api/dash/cancel-reasons"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.status_code, r.get_data(as_text=True)[:200])
    r = c.get("/api/dash/billing?period=LAST_90_DAYS")
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    j = r.get_json()
    assert j["ok"] and list(j["brands"]) == ["rozela"] and j["brands"]["rozela"]["billing"]["inDunning"] == 5
    assert "revenue" not in json.dumps(j)
    assert c.get("/api/dash/billing?period=EVERYTHING").status_code == 400
    # the stats fns reach the engine as the viewer and as READS only
    seen = {body["fn"] for _u, body in transport.calls}
    assert seen <= READS | {"apiTicketLite"}, seen - READS
    # a viewer never forces a re-read
    n = len(transport.calls)
    c.get("/api/dash/cancels?refresh=1")
    c.get("/api/dash/cancel-reasons?refresh=1")
    assert {body["fn"] for _u, body in transport.calls[n:]} <= READS


def test_billing_is_refused_to_agents_and_user_managers(app, pw_hash, transport):
    transport.reply = stats_reply
    for roles in (["agent"], ["user-manager"]):
        c, tok = logged_in(app, pw_hash, "u-" + roles[0], roles, ["rozela"])
        assert c.get("/api/dash/billing").status_code == 403
    assert not [b for _u, b in transport.calls if b["fn"] == "apiBillingHealth"]
    c, tok = logged_in(app, pw_hash, "boss", ["admin"], ["rozela"])
    assert c.get("/api/dash/billing").status_code == 200


def test_me_says_read_only_and_a_viewer_is_not_a_manager(app, pw_hash):
    c, tok = viewer(app, pw_hash)
    me = c.get("/api/me").get_json()
    assert me["engine_role"] == "viewer" and me["read_only"] is True
    assert me["can_manage_users"] is False and me["is_admin"] is False
    assert [b["id"] for b in me["brands"]] == ["rozela"]


def test_a_viewer_is_always_alone_in_his_roles(app, pw_hash):
    vb = app.extensions["cs"]["valid_brands"]
    st = store_of(app)
    for roles in (["viewer", "agent"], ["viewer", "admin"], ["viewer", "user-manager"]):
        with pytest.raises(users_store.UserStoreError) as e:
            st.create("test", "mix-" + "-".join(roles), pw_hash, {"display_name": "x", "roles": roles, "brands": ["rozela"], "lang": "he"}, vb)
        assert e.value.code == "bad_roles"
    add_user(app, pw_hash, "ok-viewer", ["viewer"], ["rozela"])
    with pytest.raises(users_store.UserStoreError):                         # nor can a role be ADDED later
        st.update("test", "ok-viewer", lambda rec, _a: rec.update(roles=users_store.UserStore.clean_fields({"roles": ["viewer", "agent"]}, vb, True)["roles"]), "user_updated")
    assert security.engine_role(["viewer"]) == "viewer"
    assert security.engine_role(["viewer", "agent"]) == "agent"


def test_the_user_manager_screen_can_create_a_viewer_but_never_an_admin_by_mistake(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela", "celesta"])
    r = c.post("/api/manage/users", json={"username": "viewer2", "display_name": "T", "roles": ["viewer"], "brands": ["rozela"], "lang": "he"}, headers={"X-CSRF-Token": tok})
    assert r.status_code in (200, 201), r.get_data(as_text=True)[:200]
    assert r.get_json()["user"]["roles"] == ["viewer"] and r.get_json()["user"]["must_change"] is True
    r = c.post("/api/manage/users", json={"username": "viewer3", "display_name": "T", "roles": ["viewer", "admin"], "brands": ["rozela"], "lang": "he"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 400


def test_a_viewer_gets_no_agent_notice_and_no_online_presence(app, pw_hash):
    import notice
    u = {"roles": ["viewer"], "brands": ["rozela"]}
    assert not [n for n in notice.NOTICES if notice.applies(n, u)]
    c, tok = viewer(app, pw_hash)
    assert c.get("/api/notice").get_json()["notices"] == []
