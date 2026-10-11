"""
attach.py — files an agent sends to a customer (Owner, 2026-10-11: "make it possible to attach files in the system, e.g. a PDF").

POST /api/<brand>/attach   multipart/form-data: file=<one file>, channel=email|whatsapp
  -> {ok, id, name, size, mime}   the id goes into apiSend {attachments: [id]}; the bytes never travel with the send.

Same door as every /api/<brand>/... route: logged in, CSRF (X-CSRF-Token), the user holds the brand, a work role (the engine re-checks).
Checked HERE before anything is stored, and again by the engine (engine/Attach.gs):
  - the type comes from the CONTENT (magic bytes) and must match the extension; .docx/.xlsx must really be Office files (zip with
    [Content_Types].xml and word/ or xl/, no macros); .txt must be UTF-8 text. The browser's Content-Type is never used.
  - the name: no path, no control or bidi characters (a right-to-left override can make "fdp.exe" look like "exe.pdf"), at most 120 characters.
  - sizes: 10 MB a file (email), 5 MB on WhatsApp (Dondy's own cap); a per-user budget against a runaway page.
Upload = the engine's apiAttachPut, part by part (1.5 MB raw = 2 MB base64 per call: the core takes 4 MB a request, the engine 2.1 MB,
and the proxy's 3 MB reply cap is never near). A part is idempotent, so a lost reply is simply sent again.

Limits, and why (Gmail: a message may be 25 MB including its encoding; base64 + a line break every 76 characters is x1.368):
  10 MB a file, 18 MB all files of one email (18 x 1.368 = 24.6 MB), 10 files. WhatsApp: 1 file, 5 MB, pdf/jpg/png/doc(x)/xls(x).
"""

import base64
import hashlib
import io
import logging
import re
import secrets
import threading
import time
import unicodedata
import zipfile

from flask import jsonify, request

import engine_proxy
import messages

log = logging.getLogger("cs_screen.attach")

PART_BYTES = 1_500_000            # = engine/Attach.gs ATTACH_PART_BYTES
FILE_MAX = 10 * 1024 * 1024       # = ATTACH_FILE_MAX
WA_FILE_MAX = 5_242_880           # = ATTACH_WA_FILE_MAX (Dondy)
NAME_MAX = 120
BODY_MAX = FILE_MAX + 256 * 1024  # one file per request + the multipart envelope
TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif",
         "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xls": "application/vnd.ms-excel", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "txt": "text/plain"}
WA_EXTS = ("pdf", "jpg", "jpeg", "png", "doc", "docx", "xls", "xlsx")
BUDGET_WINDOW_S = 600
BUDGET_FILES = 60
BUDGET_BYTES = 300 * 1024 * 1024
RETRY_CODES = ("engine_timeout", "engine_bad_response", "engine_unreachable", "busy", "server_error")
PATH_RE = re.compile(r"^/api/[a-z0-9][a-z0-9-]{1,29}/attach$")
OLE = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"


def request_class(base):
    """Flask's body cap is 256 KB for the whole app; only the upload route takes one file (and only with the CSRF header and a known length)."""
    class AttachRequest(base):
        @property
        def max_content_length(self):
            if (self.method == "POST" and PATH_RE.match(self.path or "") and self.headers.get("X-CSRF-Token")
                    and self.content_length is not None):
                return BODY_MAX
            return base.max_content_length.fget(self)
    return AttachRequest


def clean_name(raw):
    """The name the customer will see, or None. Keeps Hebrew; drops any path, control/format characters, quotes and backslashes."""
    if not isinstance(raw, str):
        return None
    n = unicodedata.normalize("NFC", raw.replace("\\", "/").rsplit("/", 1)[-1])
    n = "".join(ch for ch in n if unicodedata.category(ch)[0] != "C" and ch not in '"')
    n = re.sub(r"\s+", " ", n).strip().lstrip(".").strip()
    if not n or "." not in n:
        return None
    stem, ext = n.rsplit(".", 1)
    ext = ext.lower()
    if ext not in TYPES or not stem.strip():
        return None
    stem = stem.strip()[: NAME_MAX - len(ext) - 1].rstrip()
    return stem + "." + ext


def _ooxml(data, folder):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
    except Exception:                                   # noqa: BLE001 — not a zip at all
        return False
    if len(names) > 5000 or "[Content_Types].xml" not in names:
        return False
    if any(x.lower().endswith("vbaproject.bin") for x in names):
        return False                                    # macros: never to a customer
    return any(x.startswith(folder + "/") for x in names)


def sniff(name, data):
    """-> mime, or None when the content is not what the extension says."""
    ext = name.rsplit(".", 1)[-1].lower()
    head = data[:16]
    ok = {
        "pdf": lambda: head.startswith(b"%PDF-"),
        "jpg": lambda: head.startswith(b"\xFF\xD8\xFF"),
        "jpeg": lambda: head.startswith(b"\xFF\xD8\xFF"),
        "png": lambda: head.startswith(b"\x89PNG\r\n\x1a\n"),
        "gif": lambda: head[:6] in (b"GIF87a", b"GIF89a"),
        "webp": lambda: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        "doc": lambda: head.startswith(OLE),
        "xls": lambda: head.startswith(OLE),
        "docx": lambda: head.startswith(b"PK\x03\x04") and _ooxml(data, "word"),
        "xlsx": lambda: head.startswith(b"PK\x03\x04") and _ooxml(data, "xl"),
        "txt": lambda: _utf8_text(data),
    }.get(ext)
    return TYPES[ext] if ok and ok() else None


def _utf8_text(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return "\x00" not in text and not re.search(r"[\x01-\x08\x0e-\x1f]", text)


class _Budget:
    def __init__(self):
        self.lock = threading.Lock()
        self.seen = {}

    def take(self, user, size, now=None):
        now = time.time() if now is None else now
        with self.lock:
            q = [x for x in self.seen.get(user, []) if now - x[0] < BUDGET_WINDOW_S]
            if len(q) >= BUDGET_FILES or sum(x[1] for x in q) + size > BUDGET_BYTES:
                self.seen[user] = q
                return False
            q.append((now, size))
            self.seen[user] = q
            return True


def register(app, ctx):
    """ctx: engines, transport, api_user, ui_lang, store."""
    budget = _Budget()
    app.extensions.setdefault("cs", {})["attach_budget"] = budget

    def fail(code, http, lang):
        return jsonify({"ok": False, "error": code, "msg": messages.proxy_msg(code, lang)}), http

    @app.post("/api/<brand>/attach")
    def attach_upload(brand):
        u, err = ctx["api_user"]()
        if err:
            return err
        lang = ctx["ui_lang"](u)
        brand = str(brand).lower()
        if brand not in u.get("brands", []):
            return fail("forbidden_brand", 403, lang)
        f = request.files.get("file")
        if f is None:
            return fail("attach_none", 400, lang)
        wa = request.form.get("channel") == "whatsapp"
        name = clean_name(f.filename)
        if not name:
            return fail("attach_type", 400, lang)
        cap = WA_FILE_MAX if wa else FILE_MAX
        data = f.stream.read(cap + 1)                   # the request itself is capped at BODY_MAX before this (413)
        if not data:
            return fail("attach_empty", 400, lang)
        if len(data) > cap:
            return fail("attach_too_big", 400, lang)
        mime = sniff(name, data)
        if not mime:
            return fail("attach_type", 400, lang)
        if wa and name.rsplit(".", 1)[-1].lower() not in WA_EXTS:
            return fail("attach_wa_type", 400, lang)
        if not budget.take(u["username"], len(data)):
            return fail("attach_budget", 429, lang)
        sha = hashlib.sha256(data).hexdigest()
        aid = "a" + secrets.token_hex(12)
        parts = (len(data) + PART_BYTES - 1) // PART_BYTES
        out, status = {}, 502
        for p in range(parts):
            args = {"id": aid, "part": p, "parts": parts, "size": len(data), "sha256": sha, "name": name, "mime": mime,
                    "data": base64.b64encode(data[p * PART_BYTES:(p + 1) * PART_BYTES]).decode("ascii")}
            for attempt in range(3):
                status, out = engine_proxy.call(ctx["engines"], ctx["transport"], app.config["TOKEN_SECRET"], u, brand, "apiAttachPut", args, lang,
                                                internal=True)
                if out.get("ok") is True:
                    break
                if out.get("error") in RETRY_CODES and attempt < 2:
                    time.sleep(1.0 + attempt)
                    continue
                code = str(out.get("error") or "attach_failed")
                log.warning("attach not stored: %s user=%s part=%d/%d error=%s", brand[:24], str(u.get("username"))[:40], p, parts, code[:40])
                return jsonify({"ok": False, "error": code, "msg": out.get("msg") or messages.proxy_msg(code, lang)}), status if status >= 400 else 400
        if out.get("ready") is not True:
            return fail("attach_failed", 502, lang)
        ctx["store"].audit(u["username"], "attach_uploaded", brand, {"size": len(data), "mime": mime})   # never the name
        return jsonify({"ok": True, "id": aid, "name": name, "size": len(data), "mime": mime})
