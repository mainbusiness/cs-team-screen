"""The server finishes a send even when the browser leaves mid-request — under gunicorn, like Render."""
import re
import time

import pytest
import requests

import browser_server

pytest.importorskip("gunicorn")


def test_gunicorn_finishes_a_send_after_the_client_gives_up():
    base, pwd, proc = browser_server.start({"MOCK_SLOW_FNS": "apiSend:3000"}, gunicorn=True)
    try:
        s = requests.Session()
        tok = re.search(r'name="csrf" value="([^"]+)"', s.get(base + "/cs/login").text).group(1)
        s.post(base + "/cs/login", data={"username": "agent1", "password": pwd, "csrf": tok})
        tok = re.search(r'name="csrf" content="([^"]+)"', s.get(base + "/cs").text).group(1)
        H = {"X-CSRF-Token": tok}
        rid = "a" * 8 + "b" * 24
        with pytest.raises(requests.exceptions.ReadTimeout):
            s.post(base + "/api/rozela/apiSend", json={"args": {"id": "t18f2a01", "text": "היי מיכל"}, "rid": rid}, headers=H, timeout=0.5)
        found = None
        for _ in range(20):
            time.sleep(0.5)
            j = s.post(base + "/api/rozela/result", json={"rid": rid}, headers=H).json()
            if j.get("found"):
                found = j
                break
        assert found and found["forFn"] == "apiSend" and found["reply"]["sent"] is True
        t = s.post(base + "/api/rozela/ticket", json={"id": "t18f2a01", "revalidate": True}, headers=H).json()["ticket"]
        assert t["status"] == "sent" and t["handled_by"] == "agent1"
        # the same rid again is the SAME send (idempotent), never a second one
        again = s.post(base + "/api/rozela/apiSend", json={"args": {"id": "t18f2a01", "text": "היי מיכל"}, "rid": rid}, headers=H, timeout=10).json()
        assert again["ok"] and again.get("replayed") is True
    finally:
        proc.terminate()
