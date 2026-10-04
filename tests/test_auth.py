"""Auth: hashing, login rate limits, CSRF, session cookie and session lifetime, bootstrap, users file."""
import json
import os
import stat
import time

import pytest

import security
from conftest import PASSWORD, add_user, call, client_for, csrf_from, logged_in, login, spa_csrf, store_of


# ---------- hashing ----------

def test_hash_format_iterations_and_salt():
    h1 = security.hash_password("hunter2-hunter2")
    h2 = security.hash_password("hunter2-hunter2")
    algo, it, salt, digest = h1.split("$")
    assert algo == "pbkdf2_sha256"
    assert int(it) >= 310_000 and security.PBKDF2_ITERATIONS >= 310_000
    assert len(__import__("base64").b64decode(salt)) == 16
    assert h1 != h2                                    # per-user salt
    assert security.verify_password("hunter2-hunter2", h1)
    assert not security.verify_password("hunter2-hunter3", h1)


def test_hash_refuses_weak_iteration_counts():
    with pytest.raises(ValueError):
        security.hash_password("x" * 12, iterations=1000)
    import base64
    import hashlib
    salt = b"0123456789abcdef"
    weak = "pbkdf2_sha256$1000$%s$%s" % (base64.b64encode(salt).decode(), base64.b64encode(hashlib.pbkdf2_hmac("sha256", b"pw-pw-pw-pw", salt, 1000)).decode())
    assert not security.verify_password("pw-pw-pw-pw", weak)      # a downgraded record never verifies
    assert not security.verify_password("x", "garbage")


def test_password_policy():
    assert security.password_problem("short") == "password_too_short"
    assert security.password_problem("manager-1234567", "manager") == "password_contains_username"
    assert security.password_problem("aaaaaaaaaaaa") == "password_too_simple"
    assert security.password_problem("Correct-Horse-91") is None
    assert security.password_problem(security.temp_password()) is None


# ---------- login + cookie ----------

def test_login_sets_hardened_session_cookie(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c = client_for(app)
    r = login(c, "noa")
    assert r.status_code == 302 and r.headers["Location"].endswith("/cs")
    cookie = [v for k, v in r.headers.items() if k == "Set-Cookie" and v.startswith("__Host-cs=")][0]
    low = cookie.lower()
    assert "httponly" in low and "secure" in low and "samesite=strict" in low and "path=/" in low and "domain" not in low


def test_wrong_password_and_unknown_user_look_the_same(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    a = login(client_for(app), "noa", "wrong-password-1")
    b = login(client_for(app, "10.0.0.2"), "nobody", "wrong-password-1")
    assert a.status_code == b.status_code == 401
    assert "שם משתמש או סיסמה שגויים" in a.get_data(as_text=True)
    assert "שם משתמש או סיסמה שגויים" in b.get_data(as_text=True)


def test_disabled_user_cannot_log_in(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    store_of(app).update("t", "noa", lambda r, a: r.__setitem__("disabled", True), None)
    assert login(client_for(app), "noa").status_code == 401


def test_rate_limit_per_username(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    for i in range(5):
        assert login(client_for(app, "10.1.0.%d" % i), "noa", "bad-password-x").status_code == 401
    # sixth try, from yet another IP and with the RIGHT password: still blocked
    r = login(client_for(app, "10.9.9.9"), "noa", PASSWORD)
    assert r.status_code == 429
    assert "יותר מדי ניסיונות" in r.get_data(as_text=True)


def test_rate_limit_per_ip(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c = client_for(app, "10.2.2.2")
    for i in range(20):
        login(c, "spray%d" % i, "bad-password-x")
    assert login(c, "noa", PASSWORD).status_code == 429            # same IP, valid account: blocked
    assert login(client_for(app, "10.3.3.3"), "noa", PASSWORD).status_code == 302   # other IP fine


def test_limiter_spray_cannot_evict_an_active_ip():
    now = [0.0]
    lim = security.LoginLimiter(per_ip=3, per_user=100, window_s=60, clock=lambda: now[0], max_keys=50)
    for i in range(3):
        lim.fail("6.6.6.6", "victim")
    assert lim.blocked("6.6.6.6", "x") > 0
    for i in range(500):                                   # spray unique usernames from other IPs
        lim.fail("10.0.%d.%d" % (i // 250, i % 250), "spray%d" % i)
    assert lim.blocked("6.6.6.6", "anyone") > 0             # the attacking IP is still blocked
    assert len(lim._hits) <= 50 + 600


def test_bad_proxy_hops_refused(make_app):
    for v in ("abc", -1, 9):
        with pytest.raises(RuntimeError):
            make_app(TRUSTED_PROXY_HOPS=v)


def test_limiter_window_expires_and_success_clears_user():
    now = [1000.0]
    lim = security.LoginLimiter(per_ip=100, per_user=3, window_s=60, clock=lambda: now[0])
    for _ in range(3):
        lim.fail("1.1.1.1", "a")
    assert lim.blocked("1.1.1.1", "a") > 0
    now[0] += 61
    assert lim.blocked("1.1.1.1", "a") == 0
    lim.fail("1.1.1.1", "b")
    lim.success("b")
    assert lim.blocked("2.2.2.2", "b") == 0


# ---------- CSRF ----------

def test_csrf_required_on_state_changing_calls(app, pw_hash, transport):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert call(c, None, "rozela", "apiBoot").status_code == 403
    r = call(c, "not-the-token", "rozela", "apiBoot")
    assert r.status_code == 403 and r.get_json()["error"] == "csrf"
    assert call(c, tok, "rozela", "apiBoot", origin="https://evil.example").status_code == 403
    assert transport.calls == []
    own = c.get("/healthz").request.host_url.rstrip("/")          # this site's own origin, as the browser would send it
    assert call(c, tok, "rozela", "apiBoot", origin=own).status_code == 200
    assert len(transport.calls) == 1


def test_csrf_required_on_login_form(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c = client_for(app)
    c.get("/cs/login")
    assert c.post("/cs/login", data={"username": "noa", "password": PASSWORD}).status_code == 403


def test_login_with_browser_origin_header(app, pw_hash):
    """A real browser sends Origin on the login form post; the test client does not. Both must work."""
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c = client_for(app)
    page = c.get("/cs/login")
    own = page.request.host_url.rstrip("/")
    tok = csrf_from(page.get_data(as_text=True))
    assert c.post("/cs/login", data={"username": "noa", "password": PASSWORD, "csrf": tok}, headers={"Origin": "null"}).status_code == 403
    assert c.post("/cs/login", data={"username": "noa", "password": PASSWORD, "csrf": tok}, headers={"Origin": own}).status_code == 302


def test_logout_requires_csrf(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert c.post("/cs/logout").status_code == 403
    assert c.post("/cs/logout", data={"csrf": tok}).status_code == 302
    assert c.get("/api/me").status_code == 401


# ---------- session lifetime ----------

def test_session_ends_when_user_disabled_or_password_reset(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert c.get("/api/me").status_code == 200
    store_of(app).update("t", "noa", lambda r, a: r.__setitem__("pw", r["pw"]), None, bump_sv=True)   # e.g. a reset
    store_of(app).update("t", "noa", lambda r, a: r.__setitem__("display_name", "x"), None, bump_sv=True)
    assert c.get("/api/me").status_code == 401


def test_session_expires_after_12h(app, pw_hash, monkeypatch):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 12 * 3600 + 5)
    assert c.get("/api/me").status_code == 401


def test_must_change_password_flow(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"], must_change=True)
    c = client_for(app)
    r = login(c, "noa")
    assert r.headers["Location"].endswith("/cs/password")
    assert c.get("/api/me").status_code == 401                  # nothing else until the password is changed
    assert c.get("/cs").headers["Location"].endswith("/cs/password")
    page = c.get("/cs/password").get_data(as_text=True)
    tok = csrf_from(page)
    bad = c.post("/cs/password", data={"csrf": tok, "current": PASSWORD, "new": "short", "repeat": "short"})
    assert bad.status_code == 400
    ok = c.post("/cs/password", data={"csrf": tok, "current": PASSWORD, "new": "Brand-New-Pass-77", "repeat": "Brand-New-Pass-77"})
    assert ok.status_code == 302
    assert c.get("/api/me").status_code == 200                  # session re-issued with the new version
    assert login(client_for(app, "10.4.4.4"), "noa", "Brand-New-Pass-77").status_code == 302


# ---------- bootstrap ----------

def test_bootstrap_creates_first_admin_once(make_app, tmp_path):
    app = make_app(ADMIN_BOOTSTRAP="owner:Very-Strong-Boot-1")
    u = store_of(app).get("owner")
    assert u and "admin" in u["roles"] and u["must_change"]
    assert set(u["brands"]) >= {"rozela", "celesta", "velora", "apexmen"}
    # second start with a different value: ignored because users exist
    app2 = make_app(ADMIN_BOOTSTRAP="intruder:Another-Strong-1")
    assert store_of(app2).get("intruder") is None
    c = client_for(app2)
    assert login(c, "owner", "Very-Strong-Boot-1").status_code == 302


def test_bootstrap_rejects_weak_password(make_app):
    app = make_app(ADMIN_BOOTSTRAP="owner:short")
    assert store_of(app).count() == 0


def test_admin_sees_bootstrap_warning(make_app):
    app = make_app(ADMIN_BOOTSTRAP="owner:Very-Strong-Boot-1")
    c = client_for(app)
    login(c, "owner", "Very-Strong-Boot-1")
    tok = csrf_from(c.get("/cs/password").get_data(as_text=True))
    c.post("/cs/password", data={"csrf": tok, "current": "Very-Strong-Boot-1", "new": "Admin-Pass-2026x", "repeat": "Admin-Pass-2026x"})
    assert "bootstrap_env" in c.get("/api/me").get_json()["warnings"]


# ---------- storage + config ----------

def test_users_file_is_atomic_private_and_clean(app, pw_hash, tmp_path):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    add_user(app, pw_hash, "ron", ["agent"], ["celesta"])
    p = tmp_path / "users.json"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]
    data = json.loads(p.read_text())
    assert set(data["users"]) == {"noa", "ron"}
    audit = (tmp_path / "audit.jsonl").read_text()
    assert "pbkdf2" not in audit and PASSWORD not in audit


def test_startup_refusals(make_app):
    with pytest.raises(RuntimeError):
        make_app(SECRET_KEY="short")
    with pytest.raises(RuntimeError):
        make_app(MOCK_ENGINE=True)                      # mock + ENGINES_JSON together
    with pytest.raises(RuntimeError):
        make_app(COOKIE_SECURE=False)                   # insecure cookies outside mock preview


def test_security_headers(app, pw_hash):
    c, _ = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = c.get("/cs")
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["Referrer-Policy"] == "same-origin"     # no-referrer makes browsers send Origin: null -> login locked out
    assert client_for(app).get("/healthz").status_code == 200
