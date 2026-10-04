import os
import re
import sys

import pytest

os.environ.setdefault("MOCK_LATENCY_MS", "0")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import engine_proxy  # noqa: E402
import security  # noqa: E402
from app import create_app  # noqa: E402

TOKEN_SECRET = "t" * 40 + "-test-secret-not-real"
PASSWORD = "Correct-Horse-91"
ENGINES = {b: "https://script.google.com/macros/s/AKfycb%s0000000000000000000000/exec" % b for b in ("rozela", "celesta", "velora", "apexmen")}


@pytest.fixture(scope="session")
def pw_hash():
    # one real 600k-round hash for the whole run (hashing per user would make the suite slow)
    return security.hash_password(PASSWORD)


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.reply = {"ok": True}
        self.raise_ = None

    def __call__(self, url, body):
        self.calls.append((url, body))
        if self.raise_:
            raise self.raise_
        return self.reply(url, body) if callable(self.reply) else dict(self.reply)


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def make_app(tmp_path, transport):
    import json

    def _make(**over):
        cfg = {
            "SECRET_KEY": "s" * 48, "TOKEN_SECRET": TOKEN_SECRET, "ENGINES_JSON": json.dumps(ENGINES),
            "USERS_PATH": str(tmp_path / "users.json"), "AUDIT_PATH": str(tmp_path / "audit.jsonl"),
            "TRANSPORT": transport, "TRUSTED_PROXY_HOPS": 0, "ADMIN_BOOTSTRAP": "",
        }
        cfg.update(over)
        app = create_app(cfg)
        app.testing = True
        return app
    return _make


@pytest.fixture
def app(make_app):
    return make_app()


def store_of(app):
    return app.extensions["cs"]["store"]


def add_user(app, pw_hash, username, roles, brands, lang="he", must_change=False):
    vb = app.extensions["cs"]["valid_brands"]
    return store_of(app).create("test", username, pw_hash, {"display_name": username, "roles": roles, "brands": brands, "lang": lang},
                                vb, must_change=must_change)


def client_for(app, ip="10.0.0.1"):
    c = app.test_client()
    c.environ_base.update({"wsgi.url_scheme": "https", "HTTP_HOST": "cs.test", "REMOTE_ADDR": ip})
    return c


def csrf_from(html):
    m = re.search(r'name="csrf" value="([^"]+)"', html) or re.search(r'name="csrf" content="([^"]+)"', html)
    return m.group(1) if m else None


def login(c, username, password=PASSWORD, path="/cs/login"):
    page = c.get(path)
    tok = csrf_from(page.get_data(as_text=True))
    return c.post(path, data={"username": username, "password": password, "csrf": tok})


def spa_csrf(c):
    r = c.get("/cs")
    assert r.status_code == 200, r.status_code
    return csrf_from(r.get_data(as_text=True))


def logged_in(app, pw_hash, username, roles, brands, **kw):
    add_user(app, pw_hash, username, roles, brands, **kw)
    c = client_for(app)
    r = login(c, username)
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    tok = spa_csrf(c)
    return c, tok


def call(c, tok, brand, fn, args=None, origin=None):
    headers = {"X-CSRF-Token": tok} if tok else {}
    if origin:
        headers["Origin"] = origin
    return c.post("/api/%s/%s" % (brand, fn), json={"args": args or {}}, headers=headers)
