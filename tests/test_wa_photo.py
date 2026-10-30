"""WhatsApp photos stored on the core, shown to the agent by the screen (Owner, 2026-10-11)."""
import base64

from conftest import logged_in, valid_reply

JPEG = bytes([0xFF, 0xD8, 0xFF, 0xC0, 0, 0x11, 8, 0, 0x10, 0, 0x10, 3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1]) + bytes(16) + bytes([0xFF, 0xD9])
FID = "m" + "a1" * 12


def photo_engine(store, mimes=None):
    def reply(url, body):
        if body["fn"] == "apiWaPhotoGet":
            fid = (body.get("args") or {}).get("id")
            if fid in store:
                return {"ok": True, "id": fid, "mime": (mimes or {}).get(fid, "image/jpeg"), "data": base64.b64encode(store[fid]).decode()}
            return {"ok": False, "error": "not_found"}
        return valid_reply(url, body)
    return reply


def test_agent_of_the_brand_gets_the_image_bytes(make_app, transport, pw_hash):
    transport.reply = photo_engine({FID: JPEG})
    c, _ = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = c.get("/api/rozela/photo/" + FID)
    assert r.status_code == 200 and r.mimetype == "image/jpeg" and r.data == JPEG
    assert "private" in r.headers["Cache-Control"] and r.headers["X-Content-Type-Options"] == "nosniff"
    sent = [b for _, b in transport.calls if b["fn"] == "apiWaPhotoGet"]
    assert sent and sent[-1]["args"]["id"] == FID and sent[-1]["args"]["brand"] == "rozela"


def test_other_brand_bad_id_cleaned_photo_and_logged_out(make_app, transport, pw_hash):
    transport.reply = photo_engine({FID: JPEG})
    app = make_app()
    c, _ = logged_in(app, pw_hash, "noa", ["agent"], ["celesta"])
    assert c.get("/api/rozela/photo/" + FID).status_code in (403, 404, 502)           # not her brand: never the bytes
    assert c.get("/api/celesta/photo/../../etc").status_code == 404
    assert c.get("/api/celesta/photo/notanid").status_code == 400
    assert c.get("/api/celesta/photo/" + "m" + "b2" * 12).status_code == 404          # cleaned after 7 days
    assert app.test_client().get("/api/celesta/photo/" + FID).status_code == 401


def test_the_browser_cannot_call_the_photo_fn_as_json(make_app, transport, pw_hash):
    transport.reply = photo_engine({FID: JPEG})
    c, tok = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = c.post("/api/rozela/apiWaPhotoGet", json={"args": {"id": FID}}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 404


def test_voice_message_is_served_as_audio_and_only_known_mimes(make_app, transport, pw_hash):
    vid, bad = "m" + "c3" * 12, "m" + "d4" * 12
    transport.reply = photo_engine({vid: b"OggS-voice", bad: b"<script>"}, {vid: "audio/ogg", bad: "text/html"})
    c, _ = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = c.get("/api/rozela/photo/" + vid)
    assert r.status_code == 200 and r.mimetype == "audio/ogg" and r.data == b"OggS-voice"
    assert "private" in r.headers["Cache-Control"]
    assert c.get("/api/rozela/photo/" + bad).status_code == 400, "never serves an unexpected type"


def test_media_markers_are_never_sent_to_translation():
    import assistant
    for m in ("[audio]", "[video]", "[file]", " [Audio] "):
        assert assistant.needs_hebrew(m) is False
    assert assistant.needs_hebrew("where is my order") is True


def test_email_image_is_served_in_parts_and_png_is_allowed(make_app, transport, pw_hash):
    """2026-10-30: a customer's email image can be 10 MB; the engine answers in parts (reply cap 3 MB) and the screen joins them."""
    fid = "m" + "e5" * 12
    blob = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 9000
    cut = [blob[:1000000], blob[1000000:2000000], blob[2000000:]]

    def reply(url, body):
        if body["fn"] == "apiWaPhotoGet":
            p = (body.get("args") or {}).get("part", 0)
            return {"ok": True, "id": fid, "mime": "image/png", "data": base64.b64encode(cut[p]).decode(), "part": p, "parts": 3}
        return valid_reply(url, body)
    transport.reply = reply
    c, _ = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    r = c.get("/api/rozela/photo/" + fid)
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data == blob
    assert [b["args"]["part"] for _, b in transport.calls if b["fn"] == "apiWaPhotoGet"] == [0, 1, 2]


def test_a_part_with_another_type_or_too_many_parts_is_refused(make_app, transport, pw_hash):
    fid = "m" + "f6" * 12

    def reply(url, body):
        if body["fn"] == "apiWaPhotoGet":
            p = (body.get("args") or {}).get("part", 0)
            return {"ok": True, "id": fid, "mime": "image/png" if p == 0 else "text/html", "data": base64.b64encode(b"x").decode(), "part": p, "parts": 2}
        return valid_reply(url, body)
    transport.reply = reply
    c, _ = logged_in(make_app(), pw_hash, "noa", ["agent"], ["rozela"])
    assert c.get("/api/rozela/photo/" + fid).status_code == 400
    transport.reply = lambda url, body: ({"ok": True, "id": fid, "mime": "image/png", "data": "", "parts": 99}
                                         if body["fn"] == "apiWaPhotoGet" else valid_reply(url, body))
    assert c.get("/api/rozela/photo/" + fid).status_code == 502
