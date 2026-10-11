"""Files an agent sends to a customer (Owner, 2026-10-11): POST /api/<brand>/attach (attach.py) -> apiAttachPut part by part; apiSend carries ids."""
import base64
import hashlib
import io
import zipfile

import pytest

import attach
import engine_proxy
from conftest import logged_in, valid_reply


def pdf(n=2000):
    return b"%PDF-1.7\n" + b"A" * (n - 9)


def ooxml(folder, macro=False):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr(folder + "/document.xml", "<x/>")
        if macro:
            z.writestr(folder + "/vbaProject.bin", b"\x00")
    return buf.getvalue()


def attach_engine(store=None, fail=None):
    """A fake engine apiAttachPut: keeps parts, answers ready on the last one. fail: list of error codes to answer first."""
    store = {} if store is None else store
    fail = list(fail or [])

    def reply(url, body):
        if body["fn"] != "apiAttachPut":
            return valid_reply(url, body)
        if fail:
            return {"ok": False, "error": fail.pop(0)}
        a = body["args"]
        store.setdefault(a["id"], {})[a["part"]] = base64.b64decode(a["data"])
        return {"ok": True, "id": a["id"], "part": a["part"], "ready": a["part"] == a["parts"] - 1}
    reply.store = store
    return reply


def up(c, tok, data, name, brand="rozela", channel=None, headers=None):
    form = {"file": (io.BytesIO(data), name)}
    if channel:
        form["channel"] = channel
    h = {"X-CSRF-Token": tok} if headers is None else headers
    return c.post("/api/%s/attach" % brand, data=form, headers=h, content_type="multipart/form-data")


def puts(transport):
    return [b for _, b in transport.calls if b["fn"] == "apiAttachPut"]


def test_a_pdf_is_stored_through_the_engine_and_the_id_comes_back(make_app, transport, pw_hash):
    transport.reply = attach_engine()
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    data = pdf()
    r = up(c, tok, data, "חשבונית 12.pdf")
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] is True, j
    assert j["name"] == "חשבונית 12.pdf" and j["size"] == len(data) and j["mime"] == "application/pdf"
    assert attach.re.match(r"^a[0-9a-f]{24}$", j["id"])
    (p,) = puts(transport)
    a = p["args"]
    assert a["brand"] == "rozela" and a["id"] == j["id"] and a["parts"] == 1 and a["part"] == 0
    assert a["sha256"] == hashlib.sha256(data).hexdigest() and base64.b64decode(a["data"]) == data
    assert transport.reply.store[j["id"]][0] == data


def test_a_big_file_goes_in_parts_of_1_5_mb_each_under_the_engine_body_cap(make_app, transport, pw_hash):
    transport.reply = attach_engine()
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    data = pdf(3_200_000)
    j = up(c, tok, data, "big.pdf").get_json()
    assert j["ok"] is True, j
    ps = puts(transport)
    assert [p["args"]["part"] for p in ps] == [0, 1, 2] and all(p["args"]["parts"] == 3 for p in ps)
    assert all(len(p["args"]["data"]) <= 2_000_000 for p in ps)
    assert b"".join(transport.reply.store[j["id"]][i] for i in range(3)) == data


@pytest.mark.parametrize("data,name", [
    (b"\x89PNG\r\n\x1a\n" + b"x" * 50, "invoice.pdf"),          # a PNG named .pdf
    (pdf(), "invoice.exe"),                                        # not an allowed type at all
    (pdf(), "invoice"),                                            # no extension
    (b"MZ\x90\x00" + b"x" * 50, "x.doc"),                          # not an Office file
    (ooxml("word", macro=True), "x.docx"),                         # macros never go to a customer
    (ooxml("word"), "x.xlsx"),                                     # a Word file named .xlsx
    (b"\xff\xfe\x00\x00binary", "notes.txt"),                      # not UTF-8 text
    (b"RIFF\x00\x00\x00\x00AVI " + b"x" * 20, "a.webp"),
])
def test_the_content_decides_never_the_name(make_app, transport, pw_hash, data, name):
    transport.reply = attach_engine()
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = up(c, tok, data, name)
    assert r.status_code == 400 and r.get_json()["error"] == "attach_type", r.get_json()
    assert puts(transport) == []


@pytest.mark.parametrize("data,name,mime", [
    (ooxml("word"), "מכתב.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (ooxml("xl"), "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 100, "old.xls", "application/vnd.ms-excel"),
    ("שלום\nעולם".encode("utf-8"), "note.TXT", "text/plain"),
    (b"\xFF\xD8\xFF\xE0" + b"\x00" * 50, "photo.jpeg", "image/jpeg"),
    (b"GIF89a" + b"\x00" * 50, "a.gif", "image/gif"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"x" * 20, "a.webp", "image/webp"),
])
def test_allowed_types(make_app, transport, pw_hash, data, name, mime):
    transport.reply = attach_engine()
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    j = up(c, tok, data, name).get_json()
    assert j["ok"] is True and j["mime"] == mime, j


def test_the_name_loses_paths_control_and_bidi_characters_and_keeps_hebrew():
    assert attach.clean_name("C:\\Users\\dana\\חשבונית.pdf") == "חשבונית.pdf"
    assert attach.clean_name("../../etc/passwd.pdf") == "passwd.pdf"
    assert attach.clean_name("invoice\u202Efdp.exe") is None                          # right-to-left override: an .exe dressed as a pdf
    assert attach.clean_name("re\u202Eport.pdf") == "report.pdf"
    assert attach.clean_name('a"b\x07c.PDF') == "abc.pdf"
    assert attach.clean_name(".pdf") is None and attach.clean_name("  .hidden.pdf") == "hidden.pdf"
    long = attach.clean_name("א" * 300 + ".docx")
    assert len(long) == 120 and long.endswith(".docx")


def test_sizes_and_whatsapp_rules(make_app, transport, pw_hash):
    transport.reply = attach_engine()
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = up(c, tok, pdf(attach.FILE_MAX + 1), "big.pdf")
    assert r.status_code in (400, 413) and r.get_json()["error"] == "attach_too_big"
    r = up(c, tok, pdf(attach.WA_FILE_MAX + 1), "big.pdf", channel="whatsapp")
    assert r.status_code == 400 and r.get_json()["error"] == "attach_too_big"
    r = up(c, tok, b"GIF89a" + b"\x00" * 50, "a.gif", channel="whatsapp")
    assert r.get_json()["error"] == "attach_wa_type"
    assert up(c, tok, b"", "empty.pdf").get_json()["error"] == "attach_empty"
    assert c.post("/api/rozela/attach", data={}, headers={"X-CSRF-Token": tok}, content_type="multipart/form-data").get_json()["error"] == "attach_none"
    assert puts(transport) == []
    assert up(c, tok, pdf(attach.WA_FILE_MAX), "ok.pdf", channel="whatsapp").get_json()["ok"] is True


def test_same_door_as_every_api_route_login_csrf_brand_role(make_app, transport, pw_hash):
    transport.reply = attach_engine()
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["celesta"])
    assert up(c, tok, pdf(), "a.pdf", brand="rozela").status_code == 403          # not her brand
    assert up(c, tok, pdf(), "a.pdf", headers={}).status_code in (403, 413)        # no CSRF header
    assert up(c, "wrong", pdf(), "a.pdf").status_code == 403
    anon = app.test_client()
    anon.environ_base.update({"wsgi.url_scheme": "https", "HTTP_HOST": "cs.test"})
    assert up(anon, "x", pdf(), "a.pdf", brand="celesta").status_code in (401, 403)
    m, mtok = logged_in(app, pw_hash, "mgr", ["user-manager"], ["celesta"])
    assert up(m, mtok, pdf(), "a.pdf", brand="celesta").status_code == 403         # a pure user manager sends nothing
    assert puts(transport) == []
    # the engine fn itself is never reachable as JSON from the browser
    r = c.post("/api/celesta/apiAttachPut", json={"args": {"id": "a" + "0" * 24}}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 404


def test_the_large_body_cap_is_only_for_this_route():
    from flask import Flask, Request
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    Req = attach.request_class(Request)
    with app.test_request_context("/api/rozela/attach", method="POST", headers={"X-CSRF-Token": "x"}, data=b"0123456789"):
        from flask import request
        assert Req(request.environ).max_content_length == attach.BODY_MAX
    for path, hdr in (("/api/rozela/apiSend", {"X-CSRF-Token": "x"}), ("/api/rozela/attach", {})):
        with app.test_request_context(path, method="POST", headers=hdr, data=b"0123456789"):
            from flask import request
            assert Req(request.environ).max_content_length == 256 * 1024


def test_a_busy_engine_is_asked_again_a_refusal_is_shown(make_app, transport, pw_hash, monkeypatch):
    monkeypatch.setattr(attach.time, "sleep", lambda s: None)
    transport.reply = attach_engine(fail=["busy"])
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    assert up(c, tok, pdf(), "a.pdf").get_json()["ok"] is True
    assert len(puts(transport)) == 2
    transport.reply = attach_engine(fail=["attach_type"])
    r = up(c, tok, pdf(), "a.pdf")
    assert r.status_code == 400 and r.get_json()["error"] == "attach_type" and r.get_json()["msg"]


def test_a_runaway_page_hits_the_per_user_budget(make_app, transport, pw_hash):
    transport.reply = attach_engine()
    app = make_app()
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    b = app.extensions["cs"]["attach_budget"]
    for _ in range(attach.BUDGET_FILES):
        assert b.take("noa", 10)
    r = up(c, tok, pdf(), "a.pdf")
    assert r.status_code == 429 and r.get_json()["error"] == "attach_budget"


def test_apiSend_carries_attachment_ids_and_nothing_else():
    clean = engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "attachments": ["a" + "1" * 24, "a" + "2" * 24]})
    assert clean["attachments"] == ["a" + "1" * 24, "a" + "2" * 24]
    assert "attachments" not in engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "attachments": []})
    for bad in ("a" + "1" * 24, ["x"], ["a" + "1" * 24] * 2, ["a%024d" % i for i in range(11)], [{"id": 1}]):
        with pytest.raises(engine_proxy.ProxyError):
            engine_proxy.clean_args("apiSend", {"id": "t1", "text": "x", "attachments": bad})
    with pytest.raises(engine_proxy.ProxyError):
        engine_proxy.clean_args("apiAttachPut", {"id": "nope", "part": 0, "parts": 1, "size": 1, "sha256": "x", "name": "a.pdf", "mime": "m", "data": "x"}, engine_proxy.INTERNAL_FNS)


def test_the_send_reaches_the_engine_with_the_ids(make_app, transport, pw_hash):
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    aid = "a" + "ab" * 12
    r = c.post("/api/rozela/apiSend", json={"args": {"id": "t1", "text": "שלום", "attachments": [aid]}, "rid": "r" * 20}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200
    sent = [b for _, b in transport.calls if b["fn"] == "apiSend"]
    assert sent[-1]["args"]["attachments"] == [aid]
