"""sysreq.py — system change requests from the CS managers (Owner, 2026-10-25: "תשים למנהל המנהל בממשק שירות לקוחות שהוא יוכל
לשלוח העברות לתקן את המערכת עצמה לא רק את התשובות של ה ai . זה יעבור לפה לאישור שלי אבל שהוא יוכל להציע דברים").

A manager proposes a change to the SYSTEM (screen, workflow, buttons, rules, bugs). Nothing here executes anything: the request
travels to the owner's HQ (the Mac Mini pulls it, CS_Engine/sysreq_sync), the owner approves / rejects there, and the manager reads the status
and the owner's reply back on the managers' board.

  Browser (admins only, the same gate as the AI-notes card; CSRF by app.py like every write):
    GET  /api/sysreq                          -> {ok, items: [...newest first], brands}
    POST /api/sysreq {rid, text, brand, ticket} -> {ok, item, replay}      rid = 32 hex made by the screen: a replay is a no-op
  Machine (the Mini, no browser session; HMAC token in X-HQ-Token, see verify_token):
    GET  /hq/sysreq?since=<epoch>             -> {ok, now, items: [...updated after since, oldest first]}
    POST /hq/sysreq/<id> {status, reply}      -> {ok, item}

Storage: Postgres `screen_system_requests` in production, a JSON file (flock + temp + fsync + rename) for local tests.
"""
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import tempfile
import threading
import time

from flask import jsonify, request

STATUSES = ("pending", "approved", "done", "rejected")
# who may move where: the owner decides; "done" is the end; a rejection can be reversed into an approval (he changed his mind).
# The same status again = a reply edit only.
TRANSITIONS = {
    "pending": {"approved", "rejected", "done"},
    "approved": {"done", "rejected"},
    "rejected": {"approved"},
    "done": set(),
}
DECISION = {"approve": "approved", "reject": "rejected", "done": "done"}   # the CLI's verbs
TEXT_MIN, TEXT_MAX, REPLY_MAX = 10, 2000, 1000
RID_RE = re.compile(r"^[0-9a-f]{32}$")
TICKET_RE = re.compile(r"^[A-Za-z0-9#_.:/-]{1,80}$")
BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}$")
LIST_MAX = 300

# machine token: the engine token format (security.mint_engine_token), but its own audience and role, so a screen / sales-sync token
# is never accepted here and this token is never accepted by an engine (CS_ROLES has no 'hq-sysreq', brands is empty).
HQ_USER = "hq-sysreq"
HQ_AUD = "cs-sysreq"
HQ_TTL_MAX_S = 300
HQ_SKEW_S = 60
MACHINE_PATH_RE = re.compile(r"^/hq/sysreq(?:/[0-9]+)?$")   # the CSRF exemption in app.py: exactly these two routes (Codex 2026-10-25)


def b64url(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def mint_token(secret, now=None, ttl_s=120):
    """Mirror of the Mini's minting (sysreq_sync/sysreq.py) — used by the tests."""
    iat = int(now if now is not None else time.time())
    p = b64url(json.dumps({"user": HQ_USER, "role": HQ_USER, "aud": HQ_AUD, "brands": [], "iat": iat, "exp": iat + ttl_s},
                          separators=(",", ":")).encode())
    return p + "." + b64url(hmac.new(secret.encode(), p.encode("ascii"), hashlib.sha256).digest())


def verify_token(secret, token, now=None):
    """None when valid, else a short reason. Constant-time signature check BEFORE the payload is parsed."""
    if not isinstance(secret, str) or len(secret) < 32:
        return "no secret"
    if not isinstance(token, str) or len(token) < 10 or len(token) > 2048:
        return "malformed"
    parts = token.split(".")
    if len(parts) != 2 or not all(re.match(r"^[A-Za-z0-9_-]+$", x) for x in parts):
        return "malformed"
    want = b64url(hmac.new(secret.encode(), parts[0].encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(want, parts[1]):
        return "bad signature"
    try:
        c = json.loads(base64.urlsafe_b64decode(parts[0] + "=" * (-len(parts[0]) % 4)))
    except ValueError:
        return "unreadable"
    if not isinstance(c, dict):
        return "unreadable"
    now = int(now if now is not None else time.time())
    iat, exp = c.get("iat"), c.get("exp")
    if type(iat) is not int or type(exp) is not int:
        return "no iat/exp"
    if exp <= iat:
        return "bad lifetime"
    if exp <= now:
        return "expired"
    if iat > now + HQ_SKEW_S:
        return "issued in the future"
    if exp - iat > HQ_TTL_MAX_S:
        return "lifetime too long"
    if c.get("aud") != HQ_AUD or c.get("user") != HQ_USER or c.get("role") != HQ_USER:
        return "wrong audience"
    return None


class SysReqError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _now():
    return round(time.time(), 6)


def check_transition(rec, status, reply):
    if status not in STATUSES:
        raise SysReqError("sysreq_bad_status")
    if reply is not None and (not isinstance(reply, str) or len(reply) > REPLY_MAX):
        raise SysReqError("sysreq_bad_reply")
    cur = rec.get("status")
    if status != cur and status not in TRANSITIONS.get(cur, set()):
        raise SysReqError("sysreq_bad_transition")


def same_request(rec, user, brand, ticket, text):
    return rec.get("user") == user and rec.get("brand") == brand and rec.get("ticket") == ticket and rec.get("text") == text


class SysReqStore:
    """{"seq": n, "items": {"<id>": rec}} in one JSON file. Read-modify-write under a thread lock + flock, temp + fsync + replace."""

    def __init__(self, path, clock=_now):
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            return {"seq": 0, "items": {}}
        if not isinstance(d, dict) or not isinstance(d.get("items"), dict):
            raise RuntimeError("system requests file is not a requests file")      # never start over an unreadable file
        return d

    def _mutate(self, fn):
        with self._lock:
            fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                d = self._read()
                out = fn(d)
                tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(os.path.abspath(self.path)), delete=False, encoding="utf-8")
                try:
                    with tmp:
                        json.dump(d, tmp, ensure_ascii=False)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.chmod(tmp.name, 0o600)
                    os.replace(tmp.name, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    raise
                return out
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def create(self, user, brand, ticket, text, rid):
        """-> (rec, created). The same rid again: the stored record (a replay); the same rid with other content: sysreq_rid_conflict."""
        def m(d):
            for rec in d["items"].values():
                if rec.get("rid") == rid:
                    if not same_request(rec, user, brand, ticket, text):
                        raise SysReqError("sysreq_rid_conflict")
                    return dict(rec), False
            d["seq"] = int(d.get("seq") or 0) + 1
            t = self.clock()
            rec = {"id": d["seq"], "rid": rid, "created_at": t, "updated_at": t, "user": user, "brand": brand, "ticket": ticket,
                   "text": text, "status": "pending", "guy_reply": ""}
            d["items"][str(rec["id"])] = rec
            return dict(rec), True
        return self._mutate(m)

    def all(self):
        return sorted((dict(r) for r in self._read()["items"].values()), key=lambda r: -r["id"])

    def since(self, ts, limit=LIST_MAX):
        rows = [dict(r) for r in self._read()["items"].values() if float(r.get("updated_at") or 0) > ts]
        return sorted(rows, key=lambda r: (r["updated_at"], r["id"]))[:limit]

    def decide(self, rid_id, status, reply):
        """-> (rec, changed). reply None = keep the reply as it is."""
        def m(d):
            rec = d["items"].get(str(rid_id))
            if not rec:
                raise SysReqError("not_found")
            check_transition(rec, status, reply)
            new_reply = rec.get("guy_reply", "") if reply is None else reply
            if rec["status"] == status and rec.get("guy_reply", "") == new_reply:
                return dict(rec), False
            rec["status"], rec["guy_reply"], rec["updated_at"] = status, new_reply, max(self.clock(), float(rec["updated_at"]) + 1e-6)
            return dict(rec), True
        return self._mutate(m)


COLS = "id, rid, created_at, updated_at, username, brand, ticket, text, status, guy_reply"


def _row(r):
    return {"id": r[0], "rid": r[1], "created_at": r[2], "updated_at": r[3], "user": r[4], "brand": r[5], "ticket": r[6],
            "text": r[7], "status": r[8], "guy_reply": r[9]}


class PgSysReqStore:
    """Same contract on the core Postgres (pgstore.SCHEMA: screen_system_requests). Two instances run side by side during a
    deploy: the create is one INSERT ... ON CONFLICT (rid), the decide a SELECT ... FOR UPDATE in one transaction."""

    def __init__(self, db, clock=_now):
        self.db, self.clock = db, clock

    def create(self, user, brand, ticket, text, rid):
        def go(c):
            t = self.clock()
            got = c.execute("insert into screen_system_requests(rid, created_at, updated_at, username, brand, ticket, text, status, guy_reply) "
                            "values (%s,%s,%s,%s,%s,%s,%s,'pending','') on conflict (rid) do nothing returning " + COLS,
                            (rid, t, t, user, brand, ticket, text)).fetchone()
            if got:
                return _row(got), True
            rec = _row(c.execute("select " + COLS + " from screen_system_requests where rid=%s", (rid,)).fetchone())
            if not same_request(rec, user, brand, ticket, text):
                raise SysReqError("sysreq_rid_conflict")
            return rec, False
        return self.db.run(go, tx=True)

    def all(self):
        return [_row(r) for r in self.db.q("select " + COLS + " from screen_system_requests order by id desc limit %s", (LIST_MAX,))]

    def since(self, ts, limit=LIST_MAX):
        return [_row(r) for r in self.db.q("select " + COLS + " from screen_system_requests where updated_at > %s "
                                           "order by updated_at, id limit %s", (float(ts), int(limit)))]

    def decide(self, rid_id, status, reply):
        def go(c):
            r = c.execute("select " + COLS + " from screen_system_requests where id=%s for update", (int(rid_id),)).fetchone()
            if not r:
                raise SysReqError("not_found")
            rec = _row(r)
            check_transition(rec, status, reply)
            new_reply = rec["guy_reply"] if reply is None else reply
            if rec["status"] == status and rec["guy_reply"] == new_reply:
                return rec, False
            t = max(self.clock(), float(rec["updated_at"]) + 1e-6)
            r = c.execute("update screen_system_requests set status=%s, guy_reply=%s, updated_at=%s where id=%s returning " + COLS,
                          (status, new_reply, t, int(rid_id))).fetchone()
            return _row(r), True
        return self.db.run(go, tx=True)


def public(rec, names):
    """What a manager's screen gets (no rid)."""
    return {"id": rec["id"], "created_at": rec["created_at"], "updated_at": rec["updated_at"], "user": rec["user"],
            "by": names.get(rec["user"]) or rec["user"], "brand": rec["brand"], "ticket": rec["ticket"] or "",
            "text": rec["text"], "status": rec["status"], "guy_reply": rec["guy_reply"] or ""}


def register(app, d):
    """d: api_user, json_error, ui_lang, store (users: names + audit), sysreq (SysReqStore | PgSysReqStore), token_secret (callable)."""
    reqs, users = d["sysreq"], d["store"]

    def names():
        return {u["username"]: u.get("display_name") or u["username"] for u in users.all()}

    def admin_or_err():
        u, err = d["api_user"]()
        if err:
            return None, err
        if "admin" not in u.get("roles", []):           # the same gate as the AI-notes card: an agent or a pure user-manager never sees it
            return None, d["json_error"]("forbidden_role", 403, d["ui_lang"](u))
        return u, None

    def visible(rec, u):
        return rec["brand"] == "all" or rec["brand"] in u.get("brands", [])

    @app.get("/api/sysreq")
    def sysreq_list():
        u, err = admin_or_err()
        if err:
            return err
        nm = names()
        resp = jsonify({"ok": True, "items": [public(r, nm) for r in reqs.all() if visible(r, u)], "brands": u.get("brands", [])})
        resp.headers["Cache-Control"] = "no-store, private"
        return resp

    @app.post("/api/sysreq")
    def sysreq_create():
        u, err = admin_or_err()
        if err:
            return err
        lang = d["ui_lang"](u)
        b = request.get_json(silent=True)
        if not isinstance(b, dict):
            return d["json_error"]("bad_request", 400, lang)
        rid, text, brand, ticket = b.get("rid"), b.get("text"), b.get("brand"), b.get("ticket")
        if not isinstance(rid, str) or not RID_RE.match(rid):
            return d["json_error"]("bad_request", 400, lang)
        text = text.strip() if isinstance(text, str) else ""
        if not (TEXT_MIN <= len(text) <= TEXT_MAX):
            return d["json_error"]("sysreq_bad_text", 400, lang)
        if brand != "all" and not (isinstance(brand, str) and BRAND_RE.match(brand) and brand in u.get("brands", [])):
            return d["json_error"]("sysreq_bad_brand", 400, lang)
        ticket = ticket.strip() if isinstance(ticket, str) else ""
        if ticket and not TICKET_RE.match(ticket):
            return d["json_error"]("sysreq_bad_ticket", 400, lang)
        try:
            rec, created = reqs.create(u["username"], brand, ticket, text, rid)
        except SysReqError as e:
            return d["json_error"](e.code, 409, lang)
        if created:
            users.audit(u["username"], "sysreq_created", str(rec["id"]), {"brand": brand, "ticket": ticket, "chars": len(text)})
        return jsonify({"ok": True, "item": public(rec, names()), "replay": not created})

    # ---------- machine API (the Mini) ----------

    def machine_or_err():
        why = verify_token(d["token_secret"](), request.headers.get("X-HQ-Token", ""))
        if why:
            app.logger.warning("sysreq machine call refused: %s", why)
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return None

    @app.get("/hq/sysreq")
    def hq_list():
        err = machine_or_err()
        if err:
            return err
        try:
            since = float(request.args.get("since", "0"))
        except ValueError:
            return jsonify({"ok": False, "error": "bad_request"}), 400
        if since != since or since < 0:                  # NaN / negative
            return jsonify({"ok": False, "error": "bad_request"}), 400
        nm = names()
        resp = jsonify({"ok": True, "now": time.time(), "items": [dict(public(r, nm), rid=r["rid"]) for r in reqs.since(since)]})
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/hq/sysreq/<int:rid_id>")
    def hq_decide(rid_id):
        err = machine_or_err()
        if err:
            return err
        b = request.get_json(silent=True)
        if not isinstance(b, dict):
            return jsonify({"ok": False, "error": "bad_request"}), 400
        status, reply = b.get("status"), b.get("reply")
        if reply is not None and not isinstance(reply, str):
            return jsonify({"ok": False, "error": "sysreq_bad_reply"}), 400
        if isinstance(reply, str):
            reply = reply.strip()
        try:
            rec, changed = reqs.decide(rid_id, status, reply)
        except SysReqError as e:
            return jsonify({"ok": False, "error": e.code}), 404 if e.code == "not_found" else 400
        if changed:
            users.audit(HQ_USER, "sysreq_decided", str(rid_id), {"status": status, "reply_chars": len(rec["guy_reply"] or "")})
        return jsonify({"ok": True, "item": public(rec, names()), "changed": changed})
