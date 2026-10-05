import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import driver, security

SECRET = "S" * 40
URL = lambda c: "https://script.google.com/macros/s/%s/exec" % (c * 30)
ENV = {"TOKEN_SECRET": SECRET, "ENGINES_JSON": json.dumps({"rozela": URL("a"), "celesta": URL("b"), "apexmen": URL("c"), "velora": URL("d")})}


def reply(body, **kw):
    req = json.loads(body)
    return dict({"fn": req["fn"], "rid": req["rid"]}, **kw)


def ok(result):
    return lambda url, body, timeout: (200, json.dumps(reply(body, ok=True, job="runAgent", result=result)))


def test_token_is_the_format_the_engines_verify():
    t = driver.mint_token(SECRET, "rozela", now=1000)
    assert t == security.mint_engine_token(SECRET, "driver", "admin", ["rozela"], "he", ttl_s=600, now=1000)


def test_short_secret_refused():
    try:
        driver.mint_token("short", "rozela")
        assert False
    except ValueError:
        pass


def test_default_brands_exclude_velora_and_each_brand_gets_its_own_token_and_url():
    seen = {}
    def tr(url, body, timeout):
        req = json.loads(body)
        seen[url] = req
        return 200, json.dumps(reply(body, ok=True, result={"processed": 1, "health": {"lastRunAgeMs": 1000}}))
    lines = []
    code = driver.main(["--window", "1"], dict(ENV), tr, lines.append)   # window 1: one call per brand (no chaining)
    assert code == 0
    assert sorted(seen) == sorted([URL("a"), URL("b"), URL("c")])
    for url, req in seen.items():
        assert req["fn"] == "apiAdminRun" and req["args"] == {"job": "runAgent", "budget": 22}
        payload = json.loads(__import__("base64").urlsafe_b64decode(req["token"].split(".")[0] + "=="))
        assert payload["role"] == "admin" and len(payload["brands"]) == 1
    assert len(lines) == 3


def test_failures_are_nonzero_and_leak_nothing():
    def tr(url, body, timeout):
        return 200, json.dumps(reply(body, ok=False, error="unauthorized", secret="customer dana@example.com"))
    lines = []
    assert driver.main(["--brands", "rozela"], dict(ENV), tr, lines.append) == 1
    assert "dana" not in " ".join(lines) and "rozela FAIL" in lines[0]
    def boom(url, body, timeout):
        raise OSError("connection reset by dana@example.com")
    lines = []
    assert driver.main(["--brands", "rozela"], dict(ENV), boom, lines.append) == 1
    assert "dana" not in " ".join(lines) and "OSError" in lines[0]


def test_one_brand_failing_does_not_hide_the_others_and_exit_is_the_worst():
    def tr(url, body, timeout):
        if url == URL("b"):
            return 500, "x"
        return 200, json.dumps(reply(body, ok=True, result={"processed": 0, "health": {}}))
    lines = []
    assert driver.main([], dict(ENV), tr, lines.append) == 1
    assert len(lines) == 3 and sum("FAIL" in l for l in lines) == 1


def test_running_elsewhere_is_fine_and_a_stale_brand_is_flagged():
    lines = []
    assert driver.main(["--brands", "rozela"], dict(ENV), ok({"skipped": "running"}), lines.append) == 0
    lines = []
    assert driver.main(["--brands", "rozela"], dict(ENV), ok({"processed": 0, "health": {"lastRunAgeMs": 20 * 60000}}), lines.append) == 2
    assert "STALE" in lines[0]


def test_unknown_brand_and_missing_secret_fail_closed():
    lines = []
    assert driver.main(["--brands", "nobrand"], dict(ENV), ok({}), lines.append) == 1
    bad = dict(ENV, ENGINES_JSON=json.dumps({"rozela": "https://evil.example/exec"}))
    lines = []
    assert driver.main(["--brands", "rozela"], bad, ok({}), lines.append) == 1


def test_brands_run_in_parallel():
    def slow(url, body, timeout):
        time.sleep(0.3)
        return 200, json.dumps(reply(body, ok=True, result={"processed": 0, "health": {}}))
    t0 = time.time()
    assert driver.main([], dict(ENV), slow, lambda s: None) == 0
    assert time.time() - t0 < 0.8


def test_a_skipped_COUNT_is_not_a_skipped_run():
    lines = []
    driver.main(["--brands", "rozela"], dict(ENV), ok({"processed": 2, "skipped": 3, "health": {"lastRunAgeMs": 0}}), lines.append)
    assert "processed=2" in lines[0] and "skipped=" not in lines[0]


def test_render_cron_body_matches_the_driver_contract():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "deploy"))
    import render_deploy as rd
    env = rd.cron_env("S" * 40, ENV["ENGINES_JSON"])
    body = rd.cron_body(env)
    assert body["type"] == "cron_job" and body["serviceDetails"]["schedule"] == "* * * * *"
    assert body["serviceDetails"]["envSpecificDetails"]["startCommand"] == "python tools/driver.py"
    assert {e["key"] for e in env} >= {"TOKEN_SECRET", "ENGINES_JSON", "DRIVER_BRANDS"}
    assert os.path.exists(os.path.join(os.path.dirname(__file__), "..", "tools", "driver.py"))
    json.loads(env[1]["value"])


def test_a_reply_that_is_not_ours_is_a_failure():
    for text in ['{"ok": true}', json.dumps({"ok": True, "fn": "apiBoot", "rid": "x", "result": {}}), json.dumps({"ok": True, "fn": "apiAdminRun", "rid": "someone-else", "result": {}})]:
        lines = []
        assert driver.main(["--brands", "rozela"], dict(ENV), lambda u, b, t, text=text: (200, text), lines.append) == 1
        assert "reply_is_not_ours" in lines[0]


def test_second_driver_sends_idle_and_other_driver_fresh_is_fine():
    seen = []
    def tr(url, body, timeout):
        seen.append(json.loads(body))
        return 200, json.dumps(reply(body, ok=True, result={"skipped": "other_driver_fresh", "health": {}}))
    lines = []
    assert driver.main(["--brands", "rozela", "--only-if-stale", "180"], dict(ENV), tr, lines.append) == 0
    assert seen[0]["args"]["idle"] == 180 and "other_driver_fresh" in lines[0]
    seen.clear()
    driver.main(["--brands", "rozela"], dict(ENV), tr, lambda s: None)
    assert "idle" not in seen[0]["args"], "the primary driver never asks"


def test_a_lost_reply_is_advisory_the_engine_status_decides():
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    def lost_but_ran(url, body, timeout):
        req = json.loads(body)
        if req["fn"] == "apiAdminRun":
            return 200, "<html>Google error page</html>"
        return 200, json.dumps({"ok": True, "fn": req["fn"], "rid": req["rid"], "lastAttempt": now.isoformat()})
    lines = []
    assert driver.main(["--brands", "rozela", "--window", "1"], dict(ENV), lost_but_ran, lines.append) == 0
    assert "reply_lost" in lines[0] and "FAIL" not in lines[0]
    def lost_and_idle(url, body, timeout):
        req = json.loads(body)
        if req["fn"] == "apiAdminRun":
            return 200, '{"ok": true}'
        return 200, json.dumps({"ok": True, "fn": req["fn"], "rid": req["rid"], "lastAttempt": (now - datetime.timedelta(minutes=10)).isoformat()})
    lines = []
    assert driver.main(["--brands", "rozela", "--window", "1"], dict(ENV), lost_and_idle, lines.append) == 1
    assert "FAIL" in lines[0] and "no run seen" in lines[0]
    def refused(url, body, timeout):
        req = json.loads(body)
        return 200, json.dumps({"ok": False, "error": "unauthorized", "fn": req["fn"], "rid": req["rid"]})
    lines = []
    assert driver.main(["--brands", "rozela", "--window", "1"], dict(ENV), refused, lines.append) == 1, "a real refusal is never advisory"


def test_short_runs_are_chained_while_they_find_work_and_stop_when_idle():
    calls = []
    def tr(url, body, timeout):
        req = json.loads(body)
        calls.append(req["args"].get("budget"))
        busy = len(calls) < 3
        return 200, json.dumps(reply(body, ok=True, result={"processed": 5 if busy else 0, "waDrafted": 0, "health": {}}))
    lines = []
    assert driver.main(["--brands", "rozela"], dict(ENV), tr, lines.append) == 0
    assert len(calls) == 3 and all(b == 22 for b in calls), calls
    assert "[3 calls]" in lines[0]
    calls.clear()
    driver.main(["--brands", "rozela", "--budget", "120"], dict(ENV), tr, lambda s: None)
    assert calls[0] == 25, "a web run is capped at 25 s by the driver too"
