"""Regression: five slow reads must not refuse a human send while slot six is idle."""
import engine_proxy
from conftest import ENGINES, valid_reply


def test_send_uses_reserved_capacity_under_read_pressure_once(monkeypatch):
    monkeypatch.setattr(engine_proxy, "GATE_WAIT_S", 0.05)
    g = engine_proxy.gate("rozela")
    shared = engine_proxy.GATE_CAP - engine_proxy.GATE_RESERVED
    for _ in range(shared):
        assert g.acquire(False)
    calls = []

    def transport(url, body):
        calls.append(body)
        assert g.inflight <= engine_proxy.GATE_CAP
        return dict(valid_reply(url, body), rid=body["rid"], fn=body["fn"])

    user = {"username": "noa", "roles": ["agent"], "brands": ["rozela"]}
    try:
        status, reply = engine_proxy.call(ENGINES, transport, "t" * 40, user,
            "rozela", "apiSend", {"id": "t1", "text": "approved reply"}, "he")
        assert status == 200 and reply["ok"], reply
        assert len(calls) == 1 and calls[0]["fn"] == "apiSend"
        assert g.inflight == shared
    finally:
        for _ in range(shared):
            g.release(False, 0, None)


def test_send_priority_never_exceeds_global_cap_or_retries(monkeypatch):
    monkeypatch.setattr(engine_proxy, "GATE_WAIT_S", 0.05)
    g = engine_proxy.gate("rozela")
    for _ in range(engine_proxy.GATE_CAP):
        assert g.acquire(False, top=True)
    calls = []
    user = {"username": "noa", "roles": ["agent"], "brands": ["rozela"]}
    try:
        status, reply = engine_proxy.call(ENGINES, lambda *a: calls.append(a), "t" * 40,
            user, "rozela", "apiSend", {"id": "t1", "text": "approved reply"}, "he")
        assert status == 503 and reply["error"] == "busy"
        assert not calls and g.peak == engine_proxy.GATE_CAP
    finally:
        for _ in range(engine_proxy.GATE_CAP):
            g.release(False, 0, None)
