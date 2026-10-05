"""
app.py — the CS team screen (Flask). Serves /cs (Hebrew) and /cs/en (English UI strings, phase 5),
logs the team in, proxies engine calls, and hosts the user manager.

Safety model (the parts that live here; see security.py, users_store.py, engine_proxy.py):
 - Session: Flask signed cookie, HttpOnly + Secure + SameSite=Strict, named __Host-cs (no Domain, Path=/).
   It carries {u, sv, iat, csrf}. Every request re-reads the user record: a disabled user, a changed
   session version (password / role / brand change) or a session older than 12h ends the session.
 - CSRF: every state-changing request must carry the session's CSRF token (header X-CSRF-Token or form
   field) AND, when the browser sends an Origin header, it must be this site. SameSite=Strict on top.
 - Login: rate-limited per IP and per username (security.LoginLimiter); same answer and same time for an
   unknown user, a wrong password and a disabled account.
 - A user with must_change (temp password) can reach only the change-password page.
 - Mock mode (MOCK_ENGINE=1) refuses to start when ENGINES_JSON is set, so fake tickets can never be
   shown on the real deployment.
 - Headers: strict CSP (no inline script), no-store on HTML and API, frame-ancestors none, Referrer-Policy
   same-origin (no referrer to other sites; ticket ids live only in the URL fragment anyway).
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from urllib.parse import urlparse

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

import assistant
import engine_proxy
import ticket_cache
import llm
import messages
import security
from users_store import ROLES, UserStore, UserStoreError, public_user

SESSION_MAX_S = 12 * 3600
MANAGER_ROLES = ("admin", "user-manager")
log = logging.getLogger("cs_screen")


def _env_bool(name, default=False):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def create_app(overrides=None):
    o = dict(overrides or {})
    app = Flask(__name__, static_folder="static", static_url_path="/cs/static", template_folder="templates")

    mock = o.get("MOCK_ENGINE", _env_bool("MOCK_ENGINE"))
    engines_raw = o.get("ENGINES_JSON", os.environ.get("ENGINES_JSON", ""))
    if mock and engines_raw:
        raise RuntimeError("MOCK_ENGINE=1 together with ENGINES_JSON: refusing to start (fake tickets on a real deployment)")

    secret_key = o.get("SECRET_KEY", os.environ.get("SECRET_KEY", ""))
    if len(secret_key) < 32:
        if not mock:
            raise RuntimeError("SECRET_KEY must be set (32+ characters)")
        secret_key = secrets.token_urlsafe(48)
    token_secret = o.get("TOKEN_SECRET", os.environ.get("TOKEN_SECRET", ""))
    if len(token_secret) < security.TOKEN_SECRET_MIN:
        if not mock:     # Codex 2026-10-05: fail at start, not on every engine call
            raise RuntimeError("TOKEN_SECRET must be set (32+ characters, same value as the engines' Script Property)")
        token_secret = secrets.token_urlsafe(48)

    cookie_secure = o.get("COOKIE_SECURE", _env_bool("COOKIE_SECURE", True))
    if not cookie_secure and not mock:
        raise RuntimeError("COOKIE_SECURE=0 is allowed only in local mock preview")

    users_path = o.get("USERS_PATH", os.environ.get("USERS_PATH", "/var/data/users.json"))
    audit_path = o.get("AUDIT_PATH", os.environ.get("AUDIT_PATH", os.path.join(os.path.dirname(users_path), "users-audit.jsonl")))

    app.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="__Host-cs" if cookie_secure else "cs_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=cookie_secure,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_PATH="/",
        PERMANENT_SESSION_LIFETIME=SESSION_MAX_S,
        MAX_CONTENT_LENGTH=256 * 1024,
        TOKEN_SECRET=token_secret,
        MOCK=mock,
    )
    try:
        hops = int(o.get("TRUSTED_PROXY_HOPS", os.environ.get("TRUSTED_PROXY_HOPS", "1")))
    except (TypeError, ValueError):
        raise RuntimeError("TRUSTED_PROXY_HOPS must be a whole number")
    if hops < 0 or hops > 5:
        raise RuntimeError("TRUSTED_PROXY_HOPS must be between 0 and 5")
    if hops > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=0)

    url_re = o.get("ENGINE_URL_RE", engine_proxy.ENGINE_URL_RE)
    engines, bad = engine_proxy.parse_engines(engines_raw, url_re)
    for line in bad:
        log.warning(line)
    extra = [b.strip().lower() for b in os.environ.get("EXTRA_BRANDS", "").split(",") if b.strip()]
    valid_brands = sorted(set(engine_proxy.KNOWN_BRANDS) | set(engines) | set(extra))

    if mock:
        import mock_engine
        mock_state = mock_engine.MockEngines(token_secret)
        engines = {b: "mock://" + b for b in mock_engine.MOCK_BRANDS}
        valid_brands = sorted(set(valid_brands) | set(engines))
        transport = o.get("TRANSPORT") or mock_state.transport
    else:
        transport = o.get("TRANSPORT") or engine_proxy.http_transport()

    api_key = o.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    if o.get("LLM"):
        llm_call = o["LLM"]
    elif mock and not api_key:
        import mock_llm
        llm_call = mock_llm.MockClaude()
    else:
        llm_call = llm.anthropic_transport(api_key)

    store = UserStore(users_path, audit_path)
    limiter = o.get("LIMITER") or security.LoginLimiter()
    app.extensions["cs"] = {"store": store, "limiter": limiter, "engines": engines, "valid_brands": valid_brands}

    # ---------- first-run bootstrap ----------
    boot = o.get("ADMIN_BOOTSTRAP", os.environ.get("ADMIN_BOOTSTRAP", ""))
    bootstrap_env_present = bool(boot)
    if boot:
        if store.count() == 0:
            uname, _, pw = boot.partition(":")
            uname = uname.strip().lower()
            prob = security.password_problem(pw, uname)
            if prob:
                log.error("ADMIN_BOOTSTRAP ignored: %s", prob)
            else:
                try:
                    store.create("bootstrap", uname, security.hash_password(pw),
                                 {"display_name": uname, "roles": ["admin", "user-manager"], "brands": valid_brands, "lang": "he"},
                                 valid_brands, must_change=True)
                    log.warning("ADMIN_BOOTSTRAP created admin '%s'. Remove ADMIN_BOOTSTRAP from the environment now.", uname)
                except UserStoreError as e:
                    log.error("ADMIN_BOOTSTRAP failed: %s", e.code)
        else:
            log.warning("ADMIN_BOOTSTRAP is set but users already exist: it was ignored. Remove it from the environment.")

    # ---------- helpers ----------

    asset_versions = {}
    for name in os.listdir(app.static_folder):
        p = os.path.join(app.static_folder, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                asset_versions[name] = hashlib.sha256(f.read()).hexdigest()[:10]

    @app.template_global()
    def asset(name):
        return url_for("static", filename=name, v=asset_versions.get(name, "0"))

    def lang_of(path_lang=None):
        if path_lang in ("he", "en"):
            return path_lang
        u = g.get("user")
        return (u or {}).get("lang", "he")

    def csrf_token():
        t = session.get("csrf")
        if not t:
            t = secrets.token_urlsafe(32)
            session["csrf"] = t
        return t

    app.jinja_env.globals["csrf_token"] = csrf_token

    def is_manager(u):
        return bool(u) and any(r in u.get("roles", []) for r in MANAGER_ROLES)

    def json_error(code, http, lang=None, **kw):
        return jsonify({"ok": False, "error": code, "msg": messages.proxy_msg(code, lang or lang_of(), **kw)}), http

    def home_path(u):
        return "/cs/en" if (u or {}).get("lang") == "en" else "/cs"

    def start_session(u):
        session.clear()
        session.permanent = True
        session["u"] = u["username"]
        session["sv"] = int(u.get("sv", 1))
        session["iat"] = int(time.time())
        session["csrf"] = secrets.token_urlsafe(32)

    # ---------- per request ----------

    @app.before_request
    def start_timer():
        g.t0 = time.perf_counter()
        g.timings = []

    @app.before_request
    def load_user():
        g.user = None
        uname = session.get("u")
        if not uname:
            return
        u = store.get(uname)
        fresh = time.time() - float(session.get("iat", 0)) < SESSION_MAX_S
        if not u or u.get("disabled") or int(u.get("sv", 1)) != int(session.get("sv", -1)) or not fresh:
            session.clear()
            return
        g.user = u

    @app.before_request
    def csrf_protect():
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        origin = request.headers.get("Origin")
        if origin:
            want = urlparse(request.host_url)
            got = urlparse(origin)
            if (got.scheme, got.netloc) != (want.scheme, want.netloc):
                return _csrf_fail()
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf") or ""
        have = session.get("csrf") or ""
        if not have or not hmac.compare_digest(str(sent), str(have)):
            return _csrf_fail()

    def _csrf_fail():
        if request.path.startswith("/api/"):
            return json_error("csrf", 403)
        abort(403)

    @app.after_request
    def headers(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        # same-origin, NOT no-referrer: with no-referrer Chromium sends "Origin: null" on our own form posts and
        # the Origin check above locks everyone out (measured in a real browser, 2026-10-05). same-origin still
        # sends nothing to other sites (17track links), so ticket ids never leave.
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if cookie_secure:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        if not request.path.startswith("/cs/static/"):
            resp.headers["Cache-Control"] = "no-store"
        if request.path.startswith("/api/") and hasattr(g, "t0"):
            # debug timing for the browser's Network panel (durations and cache hit/miss only — no data)
            parts = []
            for name, dur, desc in getattr(g, "timings", []):
                p = name
                if desc:
                    p += ';desc="%s"' % str(desc).replace('"', "")[:40]
                if dur is not None:
                    p += ";dur=%.1f" % dur
                parts.append(p)
            parts.append("app;dur=%.1f" % ((time.perf_counter() - g.t0) * 1000))
            resp.headers["Server-Timing"] = ", ".join(parts)
        return resp

    # ---------- pages ----------

    @app.get("/healthz")
    def healthz():
        try:
            store.count()
        except Exception:
            return "users store unreadable", 500
        return "ok", 200

    @app.get("/favicon.ico")
    def favicon():
        resp = send_from_directory(app.static_folder, "favicon.ico", mimetype="image/x-icon", max_age=7 * 86400)
        return resp

    @app.get("/")
    def root():
        return redirect("/cs")

    def _login_page(path_lang, error=None, status=200, username=""):
        return render_template("login.html", lang=path_lang, error=error, username=username, mock=mock), status

    @app.get("/cs/login")
    @app.get("/cs/en/login")
    def login_form():
        path_lang = "en" if request.path.startswith("/cs/en") else "he"
        if g.user:
            return redirect(home_path(g.user))
        return _login_page(path_lang)

    @app.post("/cs/login")
    @app.post("/cs/en/login")
    def login_submit():
        path_lang = "en" if request.path.startswith("/cs/en") else "he"
        uname = (request.form.get("username") or "").strip().lower()[:64]
        pw = request.form.get("password") or ""
        ip = request.remote_addr or "?"
        wait = limiter.blocked(ip, uname)
        if wait:
            return _login_page(path_lang, messages.proxy_msg("rate_limited", path_lang, wait=max(1, (wait + 59) // 60)), 429, uname)
        u = store.get(uname) if uname else None
        if not u:
            security.burn_time_for_unknown_user(pw)
            ok = False
        else:
            ok = security.verify_password(pw, u["pw"]) and not u.get("disabled")
        if not ok:
            limiter.fail(ip, uname)
            store.audit(uname if u else "?", "login_failed", uname if u else "", {"ip": ip})
            return _login_page(path_lang, messages.proxy_msg("bad_login", path_lang), 401, uname)
        limiter.success(uname)
        if security.needs_rehash(u["pw"]):
            new_hash = security.hash_password(pw)
            store.update(uname, uname, lambda rec, _a: rec.__setitem__("pw", new_hash), None)
            u = store.get(uname)
        store.touch_login(uname)
        store.audit(uname, "login", uname, {"ip": ip})
        start_session(store.get(uname))
        if u.get("must_change"):
            return redirect("/cs/password")
        return redirect(home_path(u))

    @app.post("/cs/logout")
    def logout():
        if g.user:
            store.audit(g.user["username"], "logout", g.user["username"])
        session.clear()
        return redirect("/cs/login")

    @app.route("/cs/password", methods=["GET", "POST"])
    def change_password():
        u = g.user
        if not u:
            return redirect("/cs/login")
        lang = u.get("lang", "he")
        if request.method == "GET":
            return render_template("password.html", lang=lang, error=None, forced=u.get("must_change"), mock=mock)
        cur = request.form.get("current") or ""
        new = request.form.get("new") or ""
        rep = request.form.get("repeat") or ""
        err = None
        if not security.verify_password(cur, u["pw"]):
            err = "wrong_current_password"
        elif new != rep:
            err = "password_mismatch"
        elif new == cur:
            err = "password_same"
        else:
            err = security.password_problem(new, u["username"])
        if err:
            return render_template("password.html", lang=lang, error=messages.proxy_msg(err, lang), forced=u.get("must_change"), mock=mock), 400
        new_hash = security.hash_password(new)

        def m(rec, _all):
            rec["pw"] = new_hash
            rec["must_change"] = False
        store.update(u["username"], u["username"], m, "password_changed", bump_sv=True)
        start_session(store.get(u["username"]))
        return redirect(home_path(u))

    @app.get("/cs")
    @app.get("/cs/")
    @app.get("/cs/en")
    @app.get("/cs/en/")
    def spa():
        path_lang = "en" if request.path.startswith("/cs/en") else "he"
        if not g.user:
            return redirect("/cs/en/login" if path_lang == "en" else "/cs/login")
        if g.user.get("must_change"):
            return redirect("/cs/password")
        return render_template("index.html", lang=path_lang, mock=mock)

    # ---------- JSON API ----------

    def api_user():
        """(user, error_response). Logged in, not in must-change."""
        if not g.user:
            return None, json_error("not_logged_in", 401)
        if g.user.get("must_change"):
            return None, json_error("not_logged_in", 401)
        return g.user, None

    @app.get("/api/me")
    def me():
        u, err = api_user()
        if err:
            return err
        warnings = []
        if bootstrap_env_present and "admin" in u.get("roles", []):
            warnings.append("bootstrap_env")
        try:
            erole = security.engine_role(u.get("roles", []))
        except ValueError:
            erole = None
        return jsonify({
            "ok": True, "user": public_user(u), "engine_role": erole,
            "brands": [{"id": b, "connected": b in engines} for b in u.get("brands", [])],
            "can_manage_users": is_manager(u), "is_admin": "admin" in u.get("roles", []),
            "valid_brands": valid_brands if is_manager(u) else [], "roles": list(ROLES),
            "mock": mock, "warnings": warnings, "assistant": bool(api_key) or mock or bool(o.get("LLM")),
        })

    @app.post("/api/<brand>/<fn>")
    def engine_call(brand, fn):
        u, err = api_user()
        if err:
            return err
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, dict):
            return json_error("bad_request", 400)
        t0 = time.perf_counter()
        status, out = engine_proxy.call(engines, transport, app.config["TOKEN_SECRET"], u, str(brand).lower(), fn,
                                        body.get("args", {}), u.get("lang", "he"))
        ticket_cache.timing("engine", (time.perf_counter() - t0) * 1000, fn)
        if status == 200 and fn in ticket_cache.WRITE_FNS and isinstance(body.get("args"), dict):
            app.extensions["cs"]["ticket_cache"].after_write(u, str(brand).lower(), fn, body["args"], out)
        if status == 200 and fn == "apiSettings" and isinstance(body.get("args"), dict):
            app.extensions["cs"]["ticket_cache"].after_settings(str(brand).lower(), body["args"], out)
        return jsonify(out), status

    # ---------- user manager ----------

    def manager():
        u, err = api_user()
        if err:
            return None, err
        if not is_manager(u):
            return None, json_error("forbidden_role", 403)
        return u, None

    def enabled_admins(all_users):
        return [n for n, r in all_users.items() if "admin" in r.get("roles", []) and not r.get("disabled")]

    @app.get("/api/manage/users")
    def users_list():
        actor, err = manager()
        if err:
            return err
        return jsonify({"ok": True, "users": [public_user(x) for x in store.all()], "valid_brands": valid_brands})

    @app.get("/api/manage/audit")
    def users_audit():
        actor, err = manager()
        if err:
            return err
        return jsonify({"ok": True, "lines": store.audit_tail(100)})

    def store_error(e, lang):
        return jsonify({"ok": False, "error": e.code, "msg": messages.proxy_msg(e.code, lang)}), 400

    @app.post("/api/manage/users")
    def users_create():
        actor, err = manager()
        if err:
            return err
        lang = actor.get("lang", "he")
        b = request.get_json(silent=True) or {}
        roles = b.get("roles") or []
        if isinstance(roles, list) and "admin" in roles and "admin" not in actor["roles"]:
            return json_error("only_admin_grants_admin", 403, lang)
        temp = security.temp_password()
        try:
            rec = store.create(actor["username"], str(b.get("username", "")).strip().lower(), security.hash_password(temp),
                               {k: b.get(k) for k in ("display_name", "roles", "brands", "lang") if k in b}, valid_brands)
        except UserStoreError as e:
            return store_error(e, lang)
        return jsonify({"ok": True, "user": public_user(rec), "temp_password": temp})

    def guard_target(actor, target_name, all_users, new_roles=None, new_disabled=None):
        """Raises UserStoreError when the actor may not make this change."""
        target = all_users.get(target_name)
        actor_admin = "admin" in actor["roles"]
        if target and "admin" in target.get("roles", []) and not actor_admin:
            raise UserStoreError("only_admin_grants_admin")
        if new_roles is not None and "admin" in new_roles and not actor_admin:
            raise UserStoreError("only_admin_grants_admin")
        if target_name == actor["username"]:
            if new_disabled:
                raise UserStoreError("self_lockout")
            if new_roles is not None and set(new_roles) != set(actor["roles"]):
                raise UserStoreError("self_lockout")

    @app.post("/api/manage/users/<username>")
    def users_update(username):
        actor, err = manager()
        if err:
            return err
        lang = actor.get("lang", "he")
        b = request.get_json(silent=True) or {}
        try:
            fields = UserStore.clean_fields({k: b[k] for k in ("display_name", "roles", "brands", "lang", "disabled") if k in b},
                                            valid_brands, partial=True)
        except UserStoreError as e:
            return store_error(e, lang)
        changed_fields = {}

        def m(rec, all_users):
            guard_target(actor, username, all_users, fields.get("roles"), fields.get("disabled"))
            for k, v in fields.items():
                if rec.get(k) != v:
                    changed_fields[k] = v
                    rec[k] = v
            if not enabled_admins(all_users):
                raise UserStoreError("last_admin")

        security_change = any(k in fields for k in ("roles", "brands", "disabled"))
        try:
            rec, changed = store.update(actor["username"], username, m, None, bump_sv=security_change)
        except UserStoreError as e:
            code = 403 if e.code in ("only_admin_grants_admin", "self_lockout", "last_admin") else 400
            return jsonify({"ok": False, "error": e.code, "msg": messages.proxy_msg(e.code, lang)}), code
        if changed:
            store.audit(actor["username"], "user_updated", username, changed_fields)
        return jsonify({"ok": True, "user": public_user(rec), "changed": changed})

    @app.post("/api/manage/users/<username>/reset")
    def users_reset(username):
        actor, err = manager()
        if err:
            return err
        lang = actor.get("lang", "he")
        temp = security.temp_password()
        new_hash = security.hash_password(temp)

        def m(rec, all_users):
            guard_target(actor, username, all_users)
            rec["pw"] = new_hash
            rec["must_change"] = True
        try:
            rec, _ = store.update(actor["username"], username, m, "password_reset", bump_sv=True)
        except UserStoreError as e:
            code = 403 if e.code in ("only_admin_grants_admin", "self_lockout", "last_admin") else 400
            return jsonify({"ok": False, "error": e.code, "msg": messages.proxy_msg(e.code, lang)}), code
        return jsonify({"ok": True, "user": public_user(rec), "temp_password": temp})

    tcache = o.get("TICKET_CACHE") or ticket_cache.TicketCache(
        o.get("TICKET_CACHE_DIR", os.environ.get("TICKET_CACHE_DIR", os.path.join(os.path.dirname(users_path), "ticket-cache"))),
        engines, transport, lambda: app.config["TOKEN_SECRET"])
    app.extensions["cs"]["ticket_cache"] = tcache
    ticket_cache.register(app, {"api_user": api_user, "json_error": json_error, "engines": engines, "cache": tcache})

    assistant.register(app, {
        "ticket_cache": tcache,
        "api_user": api_user, "json_error": json_error, "engines": engines, "transport": transport, "store": store,
        "llm_call": llm_call,
        "cache_dir": o.get("TRANSLATE_CACHE_DIR", os.environ.get("TRANSLATE_CACHE_DIR", os.path.join(os.path.dirname(users_path), "translate-cache"))),
        "assist_limiter": o.get("ASSIST_LIMITER"), "translate_limiter": o.get("TRANSLATE_LIMITER"),
        "knowledge_cache": o.get("KNOWLEDGE_CACHE"),
    })

    @app.errorhandler(404)
    def nf(_e):
        if request.path.startswith("/api/"):
            return json_error("forbidden_fn", 404)
        return "Not found", 404

    @app.errorhandler(413)
    def too_big(_e):
        return json_error("bad_request", 413)

    return app
