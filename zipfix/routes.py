"""HTTP surface of the zip fill.

 Browser (session + CSRF, same gates as the other /api routes):
   POST /api/<brand>/zipfix            {"orders": "1646, 1647"} or {"orders": null}  -> {"ok":true,"job":id}
   GET  /api/<brand>/zipfix/<job>      -> {"ok":true,"state":"running|done|error","progress":{done,total},"result":{...}}
 WhatsApp bot (no session, no CSRF; header X-Zipbot-Token = ZIPBOT_SECRET, constant-time compare, rate-limited):
   POST /bot/zipfix                    {"brand":"velora","orders":...}
   GET  /bot/zipfix/<job>

 result = {supplier_text, review[], ask_customer[], counts{orders,zips,review,ask}, brand, ran_at, not_found[]}
 supplier_text is the ONLY thing meant for the supplier; review and ask_customer are internal lists.
 Audit: every start/end goes to the users audit log with user, brand and counts only (never an address).
"""
import hmac
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque

from flask import g, jsonify, request

import security
from . import core
from .jobs import Busy, JobManager

log = logging.getLogger("cs_screen.zipfix")

MAX_ORDERS = 300
ORDER_RE = re.compile(r"^\d{1,9}$")
ALLOWED_ROLES = ("admin", "agent")          # engine roles; a pure user-manager has no business with orders

MSG = {
    "bad_orders": ("רשימת ההזמנות לא תקינה: מספרים מופרדים בפסיק או ברווח (עד %d).", "Invalid order list: numbers separated by comma or space (max %d)."),
    "orders_required": ("חסר שדה orders (מספרים, או null לכל ההזמנות הפתוחות).", "Missing 'orders' (numbers, or null for all open orders)."),
    "busy": ("כבר רצות שתי ריצות. נסו שוב בעוד דקה.", "Two runs are already going. Try again in a minute."),
    "brand_unsupported": ("מילוי מיקודים לא פועל במותג הזה.", "Zip fill is not available for this brand."),
    "not_configured": ("מילוי המיקודים עוד לא מחובר לחנות הזאת.", "Zip fill is not connected to this store yet."),
    "job_not_found": ("הריצה לא נמצאה (או שעברו 24 שעות).", "Run not found (or older than 24 hours)."),
    "rate_limited": ("יותר מדי ריצות בזמן קצר. נסו שוב בעוד כמה דקות.", "Too many runs in a short time. Try again in a few minutes."),
    "bot_unauthorized": ("אין הרשאה.", "Unauthorized."),
    "bot_disabled": ("מסלול הבוט לא מופעל בשרת.", "Bot route is not enabled on the server."),
}


class Window:
    """Sliding-window counter per key (in memory; the service runs one worker)."""
    def __init__(self, limit, seconds, now=time.time):
        self.limit, self.seconds, self.now = limit, seconds, now
        self._d, self._lock = defaultdict(deque), threading.Lock()

    def _trim(self, q):
        t = self.now() - self.seconds
        while q and q[0] < t:
            q.popleft()

    def blocked(self, key):
        with self._lock:
            q = self._d[key]; self._trim(q)
            return len(q) >= self.limit

    def hit(self, key):
        with self._lock:
            q = self._d[key]; self._trim(q); q.append(self.now())
            return len(q) > self.limit


def parse_orders(body):
    """-> (None | [str], error_code). Absent key is an error; null = all open; empty list/string is an error."""
    if "orders" not in body:
        return None, "orders_required"
    raw = body["orders"]
    if raw is None:
        return None, None
    if isinstance(raw, (int,)) and not isinstance(raw, bool):
        raw = str(raw)
    if isinstance(raw, str):
        toks = [t for t in re.split(r"[,\s;]+", raw) if t]
    elif isinstance(raw, list):
        toks = []
        for x in raw:
            if isinstance(x, bool) or not isinstance(x, (str, int)):
                return None, "bad_orders"
            toks.append(str(x).strip())
    else:
        return None, "bad_orders"
    nums = []
    for t in toks:
        t = t.lstrip("#")
        if not ORDER_RE.match(t):
            return None, "bad_orders"
        if t not in nums:
            nums.append(t)
    if not nums or len(nums) > MAX_ORDERS:
        return None, "bad_orders"
    return nums, None


def register(app, ctx):
    o = ctx.get("overrides") or {}
    store = ctx["store"]
    api_user, ui_lang = ctx["api_user"], ctx["ui_lang"]
    users_path = ctx["users_path"]
    jobs_dir = o.get("ZIPFIX_JOBS_DIR", os.environ.get("ZIPFIX_JOBS_DIR", os.path.join(os.path.dirname(users_path), "zipfix-jobs")))
    secret = o.get("ZIPBOT_SECRET", os.environ.get("ZIPBOT_SECRET", ""))
    runner = o.get("ZIPFIX_RUNNER") or core.run_brand
    if o.get("ZIPFIX_CACHE_DIR"):
        os.environ["ZIPFIX_CACHE_DIR"] = o["ZIPFIX_CACHE_DIR"]
        core.reset_cache()

    def on_event(kind, rec):
        try:
            if kind == "start":
                store.audit(rec["actor"], "zipfix_run", rec["brand"],
                            {"orders": rec["n_orders"] if rec["n_orders"] is not None else "all", "source": rec["source"], "job": rec["job"][:8]})
            else:
                c = (rec.get("result") or {}).get("counts") or {}
                store.audit(rec["actor"], "zipfix_done", rec["brand"], dict(c, state=rec["state"], error=rec.get("error"), job=rec["job"][:8]))
        except OSError:
            log.warning("zipfix: audit write failed")

    mgr = JobManager(jobs_dir, runner, max_running=int(o.get("ZIPFIX_MAX_RUNNING", 2)), on_event=on_event)
    user_starts = Window(12, 600)
    bot_starts = Window(30, 600)
    bot_fails = Window(10, 900)
    app.extensions["zipfix"] = {"jobs": mgr, "bot_secret_set": len(secret) >= 32}

    def err(code, http, **extra):
        he, en = MSG[code]
        lang = ui_lang()
        msg = (en if lang == "en" else he)
        if "%d" in msg:
            msg = msg % MAX_ORDERS
        return jsonify(dict({"ok": False, "error": code, "msg": msg}, **extra)), http

    def configured_real(brand):
        try:
            core.kc(brand, "SHOPIFY_CLIENT_ID"); core.kc(brand, "SHOPIFY_CLIENT_SECRET")
            return True
        except core.ZipfixConfigError:
            return False

    configured = o.get("ZIPFIX_CONFIGURED") or configured_real

    def start(brand, body, actor, source):
        nums, e = parse_orders(body)
        if e:
            return err(e, 400)
        if not configured(brand):
            return err("not_configured", 503)
        try:
            jid, reused = mgr.start(brand, nums, source, actor)
        except Busy:
            return err("busy", 429, retry_after=60)
        except OSError:
            log.exception("zipfix: could not create the job record")
            return err("not_configured", 503)
        return jsonify({"ok": True, "job": jid, "reused": reused})

    def view(rec):
        out = {"ok": True, "job": rec["job"], "brand": rec["brand"], "state": rec["state"],
               "progress": rec.get("progress") or {"done": 0, "total": 0}}
        if rec["state"] == "done":
            out["result"] = rec["result"]
        elif rec["state"] == "error":
            out["error"], out["msg"] = rec.get("error", "internal"), rec.get("msg", "")
        return jsonify(out)

    # ---------- browser ----------

    def ui_gate(brand):
        u, e = api_user()
        if e:
            return None, None, e
        brand = str(brand).lower()
        if brand not in u.get("brands", []):
            return None, None, err_plain("forbidden_brand", 403)
        try:
            role = security.engine_role(u.get("roles", []))
        except ValueError:
            role = None
        if role not in ALLOWED_ROLES:
            return None, None, err_plain("forbidden_role", 403)
        if brand not in core.STORES:
            return None, None, err("brand_unsupported", 404)
        return u, brand, None

    def err_plain(code, http):
        import messages
        return jsonify({"ok": False, "error": code, "msg": messages.proxy_msg(code, ui_lang())}), http

    @app.post("/api/<brand>/zipfix")
    def zipfix_start(brand):
        u, brand, e = ui_gate(brand)
        if e:
            return e
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("bad_orders", 400)
        if user_starts.hit(u["username"]):
            return err("rate_limited", 429)
        return start(brand, body, u["username"], "ui")

    @app.get("/api/<brand>/zipfix/<job>")
    def zipfix_poll(brand, job):
        u, brand, e = ui_gate(brand)
        if e:
            return e
        rec = mgr.get(job)
        if not rec or rec.get("brand") != brand:
            return err("job_not_found", 404)
        return view(rec)

    # ---------- bot ----------

    def bot_gate():
        ip = request.remote_addr or "?"
        if len(secret) < 32:
            return None, err("bot_disabled", 503)
        if bot_fails.blocked(ip):
            return None, err("rate_limited", 429)
        sent = request.headers.get("X-Zipbot-Token", "")
        if not hmac.compare_digest(sent.encode("utf-8"), secret.encode("utf-8")):
            bot_fails.hit(ip)
            return None, err("bot_unauthorized", 401)
        return ip, None

    @app.post("/bot/zipfix")
    def bot_start():
        ip, e = bot_gate()
        if e:
            return e
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err("bad_orders", 400)
        brand = str(body.get("brand") or "").lower()
        if brand not in core.STORES:
            return err("brand_unsupported", 404)
        if bot_starts.hit("bot"):
            return err("rate_limited", 429)
        return start(brand, body, "zipbot", "bot")

    @app.get("/bot/zipfix/<job>")
    def bot_poll(job):
        ip, e = bot_gate()
        if e:
            return e
        rec = mgr.get(job)
        if not rec:
            return err("job_not_found", 404)
        return view(rec)
