import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import driver, security

SECRET = "S" * 40
URL = lambda c: "https://script.google.com/macros/s/%s/exec" % (c * 30)
ENV = {"TOKEN_SECRET": SECRET, "ENGINES_JSON": json.dumps({"rozela": URL("a"), "celesta": URL("b"), "apexmen": URL("c"), "velora": URL("d")})}


def ok(result):
    return lambda url, body, timeout: (200, json.dumps({"ok": True, "job": "runAgent", "result": result}))


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
        return 200, json.dumps({"ok": True, "result": {"processed": 1, "health": {"lastRunAgeMs": 1000}}})
    lines = []
    code = driver.main([], dict(ENV), tr, lines.append)
    assert code == 0
    assert sorted(seen) == sorted([URL("a"), URL("b"), URL("c")])
    for url, req in seen.items():
        assert req["fn"] == "apiAdminRun" and req["args"] == {"job": "runAgent", "budget": 150}
        payload = json.loads(__import__("base64").urlsafe_b64decode(req["token"].split(".")[0] + "=="))
        assert payload["role"] == "admin" and len(payload["brands"]) == 1
    assert len(lines) == 3


def test_failures_are_nonzero_and_leak_nothing():
    def tr(url, body, timeout):
        return 200, json.dumps({"ok": False, "error": "unauthorized", "secret": "customer dana@example.com"})
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
        return 200, json.dumps({"ok": True, "result": {"processed": 0, "health": {}}})
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
        return 200, json.dumps({"ok": True, "result": {"processed": 0, "health": {}}})
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
