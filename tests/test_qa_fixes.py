"""Live QA fixes (2026-10-05): favicon, assistant language follows the page, cancel-claim refusal is clear."""
import json

import messages
from conftest import client_for, logged_in
from test_assistant import FakeLLM, engine_reply


def test_favicon(app):
    r = client_for(app).get("/favicon.ico")
    assert r.status_code == 200 and r.mimetype == "image/x-icon" and len(r.data) > 100


def test_assistant_answers_in_the_page_language(make_app, pw_hash, transport, tmp_path):
    transport.reply = engine_reply
    fake = FakeLLM()
    app = make_app(LLM=fake, TRANSLATE_CACHE_DIR=str(tmp_path / "tc"))
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"], lang="he")        # Hebrew profile ...
    q = {"messages": [{"role": "user", "content": "refund policy?"}]}
    c.post("/api/rozela/assistant", json=dict(q, lang="en"), headers={"X-CSRF-Token": tok})   # ... asking from /cs/en
    c.post("/api/rozela/assistant", json=q, headers={"X-CSRF-Token": tok})                    # no page language -> profile
    c.post("/api/rozela/assistant", json=dict(q, lang="xx"), headers={"X-CSRF-Token": tok})   # junk -> profile
    langs = ["Answer in English" in p["system"][0]["text"] for p in fake.payloads]
    assert langs == [True, False, False]


def test_cancel_claim_refusal_is_clear_hebrew():
    for problem in ("draft claims a cancel but contract gid://shopify/SubscriptionContract/1 is still active",
                    "cancel claimed while the contract is ACTIVE"):
        msg = messages.engine_error_msg({"ok": False, "error": "draft_problem", "problem": problem}, "apiSend", "he")
        assert "המנוי עדיין פעיל" in msg, (problem, msg)
    for code in ("cancel_not_done", "cancel_claim"):
        assert "עדיין פעיל" in messages.engine_error_msg({"ok": False, "error": code}, "apiSend", "he")
    # an unknown future code: a plain sentence for the agent, the code only in the `error` field (QA round 4)
    msg = messages.engine_error_msg({"ok": False, "error": "brand_new_code"}, "apiSend", "he")
    assert "brand_new_code" not in msg and "רעננו" in msg


def test_engine_hebrew_cancel_claim_reaches_the_agent_verbatim():
    problem = "הטיוטה אומרת שהמנוי בוטל, אבל במערכת המנוי עדיין פעיל. קודם לבטל בכפתור, ואז לשלוח."
    msg = messages.engine_error_msg({"ok": False, "error": "draft_problem", "problem": problem}, "apiSend", "he")
    assert problem in msg and msg.startswith("בדיקת הבטיחות עצרה את השליחה")
