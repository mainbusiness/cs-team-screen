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
