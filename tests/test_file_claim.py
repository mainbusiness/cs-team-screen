"""'I attached a file' with no file (Owner, 2026-11-13, rozela: "don't say 'I sent you a file' and then not add anything; if you can't add
the file, tell the customer you can't"). The composer stops the send before it leaves, with the way out per channel; the engine refuses it
anyway (file_claim_no_file); the agent's explicit 'my message does not say a file is attached' is the only way past it."""
import json
import os
import re

import pytest

import browser_server
import engine_proxy
import messages
from pw_launch import launch, pw

HERE = os.path.dirname(os.path.abspath(__file__))
CLAIM = "היי, שלחתי לך קובץ מצורף, תסתכל עליו בבקשה. תודה!"


def _block(path, start, end):
    s = open(path, encoding="utf-8").read()
    b = s[s.index(start):s.index(end)]
    return [l.strip() for l in b.replace("function fileClaim(", "function fileClaimIn_(").splitlines() if l.strip()]


def test_the_screen_detector_is_the_engine_detector():
    eng = _block(os.path.join(HERE, "..", "..", "engine", "Safety.gs"), "var FILE_CLAIM_DOC_", "/** Short reason string when the draft")
    js = _block(os.path.join(HERE, "..", "static", "app.js"), "var FILE_CLAIM_DOC_", "/** The stop in the composer")
    assert eng == js


def test_proxy_passes_only_a_true_fileClaimOk():
    assert engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "fileClaimOk": True})["fileClaimOk"] is True
    for v in (False, "true", 1, None):
        assert "fileClaimOk" not in engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "fileClaimOk": v})


def test_the_refusal_reads_as_what_to_do():
    he = messages.engine_error_msg({"ok": False, "error": "file_claim_no_file"}, "apiSend", "he")
    en = messages.engine_error_msg({"ok": False, "error": "file_claim_no_file"}, "apiSend", "en")
    assert "📎" in he and "וואטסאפ" in he and "לא נשלחה" in he
    assert "WhatsApp" in en and "Not sent" in en


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start({}, users=(("agent1", ["agent"], ["rozela", "celesta"], "he"),
                                                      ("agent-en", ["agent"], ["rozela"], "en")))   # WhatsApp files off, as live
    yield base, pwd
    proc.terminate()


def session(p, base, pwd, user="agent1"):
    b = launch(p)
    pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("localStorage.removeItem('cs.outbox')")
    sends = []
    pg.on("request", lambda r: sends.append(json.loads(r.post_data)) if r.url.endswith("/apiSend") else None)
    return b, pg, errors, sends


def open_ticket(pg, base, tid, path="/cs", brand="rozela"):
    pg.goto(base + path + "#/b/%s/t/%s" % (brand, tid))
    pg.wait_for_selector("[data-test=draft-card] textarea, [data-test=en-draft] textarea")


def armed_click(pg, sel):
    pg.click(sel)
    pg.wait_for_timeout(600)
    pg.click(sel)


def wait_sends(pg, sends, n=1):
    for _ in range(80):
        if len(sends) >= n:
            return
        pg.wait_for_timeout(100)
    raise AssertionError("no send")


def test_email_claim_is_stopped_then_goes_with_the_file(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors, sends = session(p, base, pwd)
        open_ticket(pg, base, "t18f2a03")
        pg.fill("[data-test=draft-card] textarea", CLAIM)
        armed_click(pg, "[data-test=send-btn]")
        pg.wait_for_selector("[data-test=file-claim]")
        pg.wait_for_timeout(500)
        assert sends == []                                                                 # nothing left the screen
        assert pg.input_value("[data-test=draft-card] textarea") == CLAIM                  # the text stays
        assert "📎" in pg.inner_text("[data-test=file-claim]")
        pg.set_input_files("[data-test=attach-input]", [{"name": "תעודה.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.7\n" + b"A" * 3000}])
        pg.wait_for_selector("[data-test=attach-chip][data-status=ok]")
        armed_click(pg, "[data-test=send-btn]")
        wait_sends(pg, sends)
        assert len(sends[0]["args"]["attachments"]) == 1 and "fileClaimOk" not in sends[0]["args"]
        assert errors == []
        b.close()


def test_not_a_file_sentence_goes_out_with_the_agents_word(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors, sends = session(p, base, pwd)
        open_ticket(pg, base, "t18f2a01")
        pg.fill("[data-test=draft-card] textarea", CLAIM)
        armed_click(pg, "[data-test=send-btn]")
        pg.wait_for_selector("[data-test=file-claim-anyway]")
        pg.click("[data-test=file-claim-anyway]")
        wait_sends(pg, sends)
        assert sends[0]["args"].get("fileClaimOk") is True and not sends[0]["args"].get("attachments")
        assert errors == []
        b.close()


def test_whatsapp_says_files_cannot_go_and_stops_the_claim(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors, sends = session(p, base, pwd)
        open_ticket(pg, base, "w8ab77c1")
        pg.wait_for_selector("[data-test=attach-none-wa]")
        assert pg.locator("[data-test=attach-btn]").count() == 0
        pg.fill("[data-test=draft-card] textarea", CLAIM)
        armed_click(pg, "[data-test=send-btn]")
        pg.wait_for_selector("[data-test=file-claim]")
        assert "בוואטסאפ אי אפשר לשלוח קבצים" in pg.inner_text("[data-test=file-claim]")
        pg.wait_for_timeout(500)
        assert sends == []
        pg.fill("[data-test=draft-card] textarea", "היי, אי אפשר לשלוח קובץ בצ'אט הזה. אפשר לשלוח אותו למייל, לאיזו כתובת?")
        armed_click(pg, "[data-test=send-btn]")
        wait_sends(pg, sends)
        assert errors == []
        b.close()


def test_english_desk_claim_is_stopped(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        b, pg, errors, sends = session(p, base, pwd, user="agent-en")
        open_ticket(pg, base, "t18f2a01", path="/cs/en")
        pg.fill("[data-test=en-draft] textarea", "Hello, I've attached the certificate.")
        pg.click("[data-test=en-review-btn]")
        pg.wait_for_selector("[data-test=en-confirm]:not([disabled])")
        pg.click("[data-test=en-confirm]")
        pg.wait_for_selector("[data-test=file-claim]")
        assert "Attach the file" in pg.inner_text("[data-test=file-claim]")
        pg.wait_for_timeout(500)
        assert sends == []
        assert pg.is_enabled("[data-test=en-confirm]")                                    # the editor is not frozen
        assert errors == []
        b.close()
