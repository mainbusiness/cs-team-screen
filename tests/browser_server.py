"""Start the real app in mock mode (Flask threaded, or gunicorn like Render) for browser / HTTP tests."""
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANDS = ["rozela", "celesta", "apexmen", "selera", "velora"]


def preack_env(users_path):
    """Must-read notices (2026-10-26) open a modal over the whole screen until acknowledged. Every browser test / preview other
    than tests/test_notice_browser.py starts with them acknowledged for every user in the users file -> {"NOTICE_PATH": path}."""
    import json
    sys.path.insert(0, ROOT)
    import notice
    from users_store import UserStore
    d = os.path.dirname(os.path.abspath(users_path))
    names = [u["username"] for u in UserStore(users_path, os.path.join(d, "a.jsonl")).all()]
    npath = os.path.join(d, "notice-acks.json")
    with open(npath, "w") as f:
        json.dump({"acks": {u: {n["id"]: 1.0 for n in notice.NOTICES} for u in names}}, f)
    return {"NOTICE_PATH": npath}


def start(extra_env=None, gunicorn=False, users=(("agent1", ["agent"], ["rozela"], "he"),)):
    sys.path.insert(0, ROOT)
    import security
    from users_store import UserStore
    tmp = tempfile.mkdtemp(prefix="cs-srv-")
    path = os.path.join(tmp, "users.json")
    pwd = secrets.token_urlsafe(12) + "-Aa1"
    st = UserStore(path, os.path.join(tmp, "a.jsonl"))
    for name, roles, brands, lang in users:
        st.create("t", name, security.hash_password(pwd), {"display_name": name, "roles": roles, "brands": brands, "lang": lang}, BRANDS, must_change=False)
    extra_env = dict(extra_env or {})
    if "NOTICE_PATH" not in extra_env:
        extra_env.update(preack_env(path))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    env = dict(os.environ, MOCK_ENGINE="1", COOKIE_SECURE="0", USERS_PATH=path, TRUSTED_PROXY_HOPS="0", MOCK_LATENCY_MS="0",
               ENGINES_JSON="", PYTHONDONTWRITEBYTECODE="1", SECRET_KEY="s" * 48, TOKEN_SECRET="k" * 48, **(extra_env or {}))
    if gunicorn:
        cmd = [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "8", "--timeout", "120", "--bind", "127.0.0.1:%d" % port, "wsgi:app"]
    else:
        cmd = [sys.executable, "-c", "from app import create_app;create_app().run(host='127.0.0.1',port=%d,threaded=True)" % port]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d" % port
    for _ in range(150):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    return base, pwd, proc
