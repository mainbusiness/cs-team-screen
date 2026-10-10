"""Zip fill backend: offline tests (no network, no Shopify). The network regression is `python -m zipfix.selftest`."""
import json
import os
import stat
import threading
import time

import pytest

from conftest import client_for, logged_in, spa_csrf
from zipfix import core, jobs, routes

BOT = "b" * 40


def fake_result(brand, nums, progress, addr="הכלנית 16"):
    progress(0, 2)
    progress(2, 2)
    return {"brand": brand, "supplier_text": "1646 - 1794000\n1647 - 4061053", "review": [
        {"order": "1647", "zip": "4061053", "reason": "r", "city": "תל מונד", "address": addr, "note": ""}],
        "ask_customer": [], "counts": {"orders": 2, "zips": 2, "review": 1, "ask": 0}, "not_found": [],
        "ran_at": "2026-10-10T00:00:00Z", "_legacy_text": "x"}


@pytest.fixture
def zapp(make_app, tmp_path):
    state = {"calls": []}

    def runner(brand, nums, progress):
        state["calls"].append((brand, nums))
        return fake_result(brand, nums, progress)

    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "jobs"), ZIPFIX_RUNNER=runner, ZIPBOT_SECRET=BOT,
                   ZIPFIX_CONFIGURED=lambda b: True, ZIPFIX_CACHE_DIR=str(tmp_path / "zc"))
    app.state = state
    return app


def poll(c, url, hdr=None, tries=100):
    for _ in range(tries):
        r = c.get(url, headers=hdr or {})
        d = r.get_json()
        if d.get("state") != "running":
            return r, d
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@pytest.fixture
def ui(zapp, pw_hash):
    return logged_in(zapp, pw_hash, "agent1", ["agent"], ["velora", "rozela"])


# ---------- order list parsing ----------

@pytest.mark.parametrize("raw,exp", [
    ("1646, 1647  #1648", ["1646", "1647", "1648"]), (["1646", 1647], ["1646", "1647"]), ("1646,1646", ["1646"]),
    (1646, ["1646"]), (None, None)])
def test_parse_orders_ok(raw, exp):
    assert routes.parse_orders({"orders": raw}) == (exp, None)


@pytest.mark.parametrize("body", [{}, {"orders": ""}, {"orders": "  ,, "}, {"orders": []}, {"orders": "12a"}, {"orders": "1;DROP"},
                                  {"orders": {"a": 1}}, {"orders": [True]}, {"orders": ["1", None]}, {"orders": " ".join(map(str, range(1, 302)))},
                                  {"orders": "1234567890"}])
def test_parse_orders_bad(body):
    nums, e = routes.parse_orders(body)
    assert e in ("bad_orders", "orders_required") and nums is None


# ---------- browser routes ----------

def test_ui_flow_and_result_shape(zapp, ui):
    c, tok = ui
    r = c.post("/api/velora/zipfix", json={"orders": "1646, 1647"}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    jid = r.get_json()["job"]
    r, d = poll(c, "/api/velora/zipfix/" + jid)
    assert d["state"] == "done" and d["progress"] == {"done": 2, "total": 2}
    res = d["result"]
    assert set(res) >= {"supplier_text", "review", "ask_customer", "counts", "ran_at"} and "_legacy_text" not in res
    assert res["counts"]["zips"] == 2
    assert zapp.state["calls"] == [("velora", ["1646", "1647"])]          # the real zipfix route, not the generic engine proxy


def test_orders_null_means_all_open(zapp, ui):
    c, tok = ui
    jid = c.post("/api/velora/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok}).get_json()["job"]
    poll(c, "/api/velora/zipfix/" + jid)
    assert zapp.state["calls"][-1] == ("velora", None)


def test_missing_orders_key_is_refused_not_all(zapp, ui):
    c, tok = ui
    r = c.post("/api/velora/zipfix", json={}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 400 and r.get_json()["error"] == "orders_required" and not zapp.state["calls"]


def test_auth_gates(zapp, pw_hash, ui):
    c, tok = ui
    anon = client_for(zapp, "10.0.0.9")
    assert anon.post("/api/velora/zipfix", json={"orders": None}).status_code in (401, 403)
    assert anon.get("/api/velora/zipfix/" + "a" * 24).status_code == 401
    assert c.post("/api/velora/zipfix", json={"orders": None}).status_code == 403                       # no CSRF
    r = c.post("/api/celesta/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 403 and r.get_json()["error"] == "forbidden_brand"                          # no access to that brand
    assert not zapp.state["calls"]


def test_pure_user_manager_refused(zapp, pw_hash):
    c, tok = logged_in(zapp, pw_hash, "um", ["user-manager"], ["velora"])
    r = c.post("/api/velora/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 403 and r.get_json()["error"] == "forbidden_role"


def test_job_is_brand_scoped(zapp, ui):
    c, tok = ui
    jid = c.post("/api/velora/zipfix", json={"orders": "1"}, headers={"X-CSRF-Token": tok}).get_json()["job"]
    poll(c, "/api/velora/zipfix/" + jid)
    assert c.get("/api/rozela/zipfix/" + jid).status_code == 404
    assert c.get("/api/velora/zipfix/..%2f..%2fusers").status_code == 404
    assert c.get("/api/velora/zipfix/short").status_code == 404


def test_unsupported_brand(make_app, pw_hash, tmp_path, monkeypatch):
    monkeypatch.setenv("EXTRA_BRANDS", "elevanu")
    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=fake_result, ZIPFIX_CONFIGURED=lambda b: True)
    c, tok = logged_in(app, pw_hash, "agent9", ["agent"], ["elevanu"])
    r = c.post("/api/elevanu/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 404 and r.get_json()["error"] == "brand_unsupported"


def test_not_configured(make_app, pw_hash, tmp_path):
    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=fake_result, ZIPFIX_CONFIGURED=lambda b: False)
    c, tok = logged_in(app, pw_hash, "agent9", ["agent"], ["velora"])
    r = c.post("/api/velora/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok})
    assert r.status_code == 503 and r.get_json()["error"] == "not_configured"


def test_two_at_a_time_and_dedupe(make_app, pw_hash, tmp_path):
    gate, started = threading.Event(), threading.Semaphore(0)

    def slow(brand, nums, progress):
        started.release(); gate.wait(10)
        return fake_result(brand, nums, progress)

    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=slow, ZIPFIX_CONFIGURED=lambda b: True)
    c, tok = logged_in(app, pw_hash, "agent9", ["agent"], ["velora", "rozela", "celesta"])
    h = {"X-CSRF-Token": tok}
    a = c.post("/api/velora/zipfix", json={"orders": "1,2"}, headers=h).get_json()
    again = c.post("/api/velora/zipfix", json={"orders": "2 1"}, headers=h).get_json()
    assert again["job"] == a["job"] and again["reused"] is True and a["reused"] is False             # same set = same job
    b = c.post("/api/rozela/zipfix", json={"orders": "1,2"}, headers=h).get_json()                      # other brand = other job
    assert b["job"] != a["job"]
    third = c.post("/api/celesta/zipfix", json={"orders": None}, headers=h)
    assert third.status_code == 429 and third.get_json()["error"] == "busy"
    gate.set()
    poll(c, "/api/velora/zipfix/" + a["job"]); poll(c, "/api/rozela/zipfix/" + b["job"])
    assert c.post("/api/celesta/zipfix", json={"orders": None}, headers=h).status_code == 200


def test_runner_crash_becomes_error_without_details(make_app, pw_hash, tmp_path):
    def boom(brand, nums, progress):
        raise RuntimeError("velora: [{'message': 'secret street 5 Haifa'}]")

    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=boom, ZIPFIX_CONFIGURED=lambda b: True)
    c, tok = logged_in(app, pw_hash, "agent9", ["agent"], ["velora"])
    jid = c.post("/api/velora/zipfix", json={"orders": None}, headers={"X-CSRF-Token": tok}).get_json()["job"]
    r, d = poll(c, "/api/velora/zipfix/" + jid)
    assert d["state"] == "error" and d["error"] == "shopify_failed" and "secret" not in json.dumps(d)


def test_rate_limit_per_user(make_app, pw_hash, tmp_path):
    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=fake_result, ZIPFIX_CONFIGURED=lambda b: True)
    c, tok = logged_in(app, pw_hash, "agent9", ["agent"], ["velora"])
    h = {"X-CSRF-Token": tok}
    codes = []
    for i in range(14):
        r = c.post("/api/velora/zipfix", json={"orders": str(100 + i)}, headers=h)
        codes.append(r.status_code)
        if r.status_code == 200:
            poll(c, "/api/velora/zipfix/" + r.get_json()["job"])
    assert codes[:12] == [200] * 12 and codes[12:] == [429, 429]


def test_audit_has_user_brand_count_but_no_address(zapp, ui):
    c, tok = ui
    jid = c.post("/api/velora/zipfix", json={"orders": "1646, 1647"}, headers={"X-CSRF-Token": tok}).get_json()["job"]
    poll(c, "/api/velora/zipfix/" + jid)
    time.sleep(0.2)
    lines = [l for l in zapp.extensions["cs"]["store"].audit_tail(50) if l["action"].startswith("zipfix")]
    start = next(l for l in lines if l["action"] == "zipfix_run")
    assert start["actor"] == "agent1" and start["target"] == "velora" and start["detail"]["orders"] == 2
    assert "הכלנית" not in json.dumps(lines, ensure_ascii=False) and "תל מונד" not in json.dumps(lines, ensure_ascii=False)
    assert any(l["action"] == "zipfix_done" and l["detail"]["zips"] == 2 for l in lines)


def test_job_file_private_and_swept(zapp, ui, tmp_path):
    c, tok = ui
    jid = c.post("/api/velora/zipfix", json={"orders": "7"}, headers={"X-CSRF-Token": tok}).get_json()["job"]
    poll(c, "/api/velora/zipfix/" + jid)
    p = tmp_path / "jobs" / (jid + ".json")
    assert stat.S_IMODE(p.stat().st_mode) == 0o600 and stat.S_IMODE((tmp_path / "jobs").stat().st_mode) == 0o700
    mgr = zapp.extensions["zipfix"]["jobs"]
    for _ in range(100):
        if mgr.running() == 0:
            break
        time.sleep(0.02)
    mgr.now = lambda: time.time() + 25 * 3600
    mgr._sweep()
    assert not p.exists()


def test_restart_closes_running_records(tmp_path):
    d = tmp_path / "j"; d.mkdir()
    rec = {"job": "o" * 24, "brand": "velora", "state": "running", "progress": {"done": 1, "total": 5}, "created": time.time()}
    (d / ("o" * 24 + ".json")).write_text(json.dumps(rec))
    m = jobs.JobManager(str(d), fake_result)
    got = m.get("o" * 24)
    assert got["state"] == "error" and got["error"] == "interrupted"


# ---------- bot route ----------

def bot_client(zapp, ip="10.9.9.9"):
    return client_for(zapp, ip)


def test_bot_requires_token(zapp):
    c = bot_client(zapp)
    assert c.post("/bot/zipfix", json={"brand": "velora", "orders": None}).status_code == 401
    assert c.post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-Zipbot-Token": "x" * 40}).status_code == 401
    assert c.get("/bot/zipfix/" + "a" * 24).status_code == 401
    assert not zapp.state["calls"]


def test_bot_flow_no_session_no_csrf(zapp):
    c = bot_client(zapp)
    h = {"X-Zipbot-Token": BOT}
    r = c.post("/bot/zipfix", json={"brand": "velora", "orders": "1646"}, headers=h)
    assert r.status_code == 200
    r, d = poll(c, "/bot/zipfix/" + r.get_json()["job"], h)
    assert d["state"] == "done" and d["result"]["counts"]["zips"] == 2
    assert zapp.state["calls"] == [("velora", ["1646"])]
    lines = zapp.extensions["cs"]["store"].audit_tail(20)
    assert any(l["action"] == "zipfix_run" and l["actor"] == "zipbot" for l in lines)


def test_bot_poll_can_pin_brand(zapp):
    c, h = bot_client(zapp), {"X-Zipbot-Token": BOT}
    jid = c.post("/bot/zipfix", json={"brand": "velora", "orders": "5"}, headers=h).get_json()["job"]
    poll(c, "/bot/zipfix/" + jid, h)
    assert c.get("/bot/zipfix/%s?brand=velora" % jid, headers=h).status_code == 200
    assert c.get("/bot/zipfix/%s?brand=rozela" % jid, headers=h).status_code == 404


def test_outbound_allowlist():
    ok = ["https://liors.co.il/x", "https://zips.co.il/search?q=1", "https://x0mb1s-jv.myshopify.com/admin/api/1/graphql.json",
          "https://data.gov.il/api", "https://postalcode.48shops.com/Default.aspx", "https://html.duckduckgo.com/html/?q=1"]
    bad = ["http://zips.co.il/", "https://evil.com/", "https://zips.co.il.evil.com/", "https://169.254.169.254/", "https://zips.co.il:8443/",
           "file:///etc/passwd", "https://a.b.myshopify.com/"]
    assert all(core.host_allowed(u) for u in ok) and not any(core.host_allowed(u) for u in bad)
    assert core.http("http://169.254.169.254/latest/meta-data/") == (0, "")


def test_bot_bad_inputs(zapp):
    c, h = bot_client(zapp), {"X-Zipbot-Token": BOT}
    assert c.post("/bot/zipfix", json={"brand": "nope", "orders": None}, headers=h).status_code == 404
    assert c.post("/bot/zipfix", json={"orders": None}, headers=h).status_code == 404                   # brand always required
    assert c.post("/bot/zipfix", json={"brand": "velora", "orders": "x"}, headers=h).status_code == 400
    assert c.post("/bot/zipfix", data="not json", headers=h).status_code == 400
    assert c.get("/bot/zipfix/nope", headers=h).status_code == 404


def test_bot_failed_attempts_are_rate_limited(zapp):
    c = bot_client(zapp, "10.7.7.7")
    codes = [c.post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-Zipbot-Token": "w" * 40}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert c.post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-Zipbot-Token": BOT}).status_code == 429   # blocked even with the right key
    assert bot_client(zapp, "10.8.8.8").post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-Zipbot-Token": BOT}).status_code == 200


def test_bot_disabled_without_secret(make_app, tmp_path):
    app = make_app(ZIPFIX_JOBS_DIR=str(tmp_path / "j"), ZIPFIX_RUNNER=fake_result, ZIPBOT_SECRET="short")
    r = client_for(app).post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-Zipbot-Token": "short"})
    assert r.status_code == 503


def test_session_cookie_does_not_open_bot_route(zapp, ui):
    c, tok = ui
    assert c.post("/bot/zipfix", json={"brand": "velora", "orders": None}, headers={"X-CSRF-Token": tok}).status_code == 401


# ---------- core: run_brand output format (fake sources) ----------

def order(n, city="תל מונד", a1="הכלנית 16", a2="", zip_=None, country="IL"):
    return {"brand": "velora", "order": "#" + str(n), "created": "2026-10-10", "city": city, "address1": a1, "address2": a2,
            "zip": zip_, "country": country}


def test_run_brand_format(monkeypatch):
    os_ = [order(1700), order(1646), order(1650, city="עכו", a1="2", a2="17, שרה לוי תנאי"), order(1651, city="d", a1="d"),
           order(1652, city="חריש", a1="שוהם 22"), order(1653, zip_="1234567", city="חיפה", a1="הרצל 4")]
    monkeypatch.setattr(core, "fetch_many", lambda b, n=None, chunk=40: os_)
    res = {"הכלנית 16": {"zip": "4061053", "level": "EXACT_2SRC", "city": "תל מונד", "street": "הכלנית", "house": "16", "note": ""},
           "שוהם 22": {"zip": "2515500", "level": "EXACT", "city": "חורפיש", "street": "שוהם", "house": "22", "note": ""}}
    monkeypatch.setattr(core, "resolve", lambda c, a1, a2="": res[a1])
    monkeypatch.setattr(core, "fix_bad", lambda o: {"action": "ASK_CUSTOMER", "address": None, "zip": None, "level": "NONE", "city": None}
                        if o["city"] == "d" else {"action": "FROM_CONTEXT", "address": "שרה לוי תנאי 17", "zip": "2400000", "level": "EXACT", "city": "עכו"})
    monkeypatch.setattr(core, "needs_review", lambda o, r: "ניחוש" if o["city"] == "חריש" else None)
    seen = []
    out = core.run_brand("velora", None, lambda d, t: seen.append((d, t)))
    assert out["supplier_text"] == ("1646 - 4061053\n1652 - 2515500\n1650 - 2400000\n1700 - 4061053".replace("1652 - 2515500\n1650 - 2400000", "1650 - 2400000\n1652 - 2515500")
                                    + "\n\nOrder #1650 address:\nCity: עכו\nZip code: 2400000\nStreet and number: שרה לוי תנאי 17\n")
    assert [r["order"] for r in out["review"]] == ["1652"] and out["review"][0]["reason"] == "ניחוש"
    assert out["ask_customer"] == [{"order": "1651", "city": "d", "address": "d"}]
    assert out["counts"] == {"orders": 6, "zips": 4, "review": 1, "ask": 1}
    assert "לא לשלוח לספקית" in out["_legacy_text"] and "לא לשלוח לספקית" not in out["supplier_text"]
    assert seen[0] == (0, 6) and seen[-1] == (6, 6)


def test_run_brand_one_bad_order_does_not_sink_batch(monkeypatch):
    monkeypatch.setattr(core, "fetch_many", lambda b, n=None, chunk=40: [order(1), order(2, a1="BOOM 1")])

    def resolve(c, a1, a2=""):
        if a1.startswith("BOOM"):
            raise KeyError("x")
        return {"zip": "4061053", "level": "EXACT", "city": c, "street": "s", "house": "1", "note": ""}
    monkeypatch.setattr(core, "resolve", resolve)
    out = core.run_brand("velora", ["1", "2", "3"])
    assert out["supplier_text"] == "1 - 4061053"
    assert out["review"][0]["order"] == "2" and "שגיאה" in out["review"][0]["reason"] and out["review"][0]["zip"] is None
    assert out["not_found"] == ["3"]


def test_run_brand_nothing_to_do(monkeypatch):
    monkeypatch.setattr(core, "fetch_many", lambda b, n=None, chunk=40: [order(5, zip_="4061053")])
    out = core.run_brand("velora", None)
    assert out["supplier_text"] == "" and out["counts"] == {"orders": 1, "zips": 0, "review": 0, "ask": 0}


def test_fuzzy_ledger_is_per_thread():
    core.FUZZY.clear(); core.FUZZY.add(("city", "a", "b"))
    seen = []
    t = threading.Thread(target=lambda: seen.append(len(core.FUZZY)))
    t.start(); t.join()
    assert seen == [0] and len(core.FUZZY) == 1
    core.FUZZY.clear()


# ---------- core: offline parsing (the PARSE cases of the original selftest) ----------

def test_parse_street_cases():
    from zipfix.selftest import PARSE
    for c, t, st, n in PARSE:
        assert core.parse_street(t, c) == (st, n), (c, t)


# ---------- bounded cache ----------

def test_cache_round_trip_eviction_and_corruption(tmp_path):
    p = str(tmp_path / "c" / "cache.zfc")
    c = core.BoundedCache(p, 4000)
    for i in range(200):
        c["k%d" % i] = [200, "x" * 50 + str(i) * 20]
    assert c.stats()["bytes"] <= 4000 and "k199" in c and "k0" not in c               # oldest evicted first
    c.save(force=True)
    assert [n for n in os.listdir(tmp_path / "c")] == ["cache.zfc"]                    # temp file removed
    c2 = core.BoundedCache(p, 4000)
    assert c2["k199"] == c["k199"] and "k0" not in c2
    raw = open(p, "rb").read()
    open(p, "wb").write(raw[: len(raw) // 2])                                          # truncated file: read up to the damage
    c3 = core.BoundedCache(p, 4000)
    assert "k199" not in c3 or c3["k199"] == c["k199"]
    open(p, "wb").write(b"garbage")
    assert "k1" not in core.BoundedCache(p, 4000)


def test_cache_save_throttle(tmp_path, monkeypatch):
    p = str(tmp_path / "cache.zfc")
    c = core.BoundedCache(p, 10 ** 6)
    c["a"] = [200, "x"]
    c.save()                                                                           # first minute: no write
    assert not os.path.exists(p)
    c._last_save = time.time() - 61
    c.save()
    assert os.path.exists(p)
    m = os.path.getmtime(p); c["b"] = [200, "y"]; c.save()
    assert os.path.getmtime(p) == m                                                    # second write inside the minute is skipped
    c.save(force=True)
    assert core.BoundedCache(p, 10 ** 6)["b"] == [200, "y"]
