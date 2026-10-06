import json, os, sys, time
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import driver, security

SECRET = "S" * 40
URL = lambda c: "https://script.google.com/macros/s/%s/exec" % (c * 30)
ENV = {"TOKEN_SECRET": SECRET, "ENGINES_JSON": json.dumps({"rozela": URL("a"), "celesta": URL("b"), "apexmen": URL("c"), "velora": URL("d"), "selera": URL("e")})}


@pytest.fixture(autouse=True)
def isolated_driver_state(tmp_path, monkeypatch):
    # Every fake-transport test must own its persisted state. The production driver
    # also runs on this host: its active cooldown must neither skip our fake calls
    # nor be overwritten by the test suite.
    monkeypatch.setitem(ENV, "DRIVER_STATE_FILE", str(tmp_path / "driver-backoff.json"))


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


def test_default_brands_include_velora_and_each_brand_gets_its_own_token_and_url():
    seen = {}
    def tr(url, body, timeout):
        req = json.loads(body)
        seen[url] = req
        return 200, json.dumps(reply(body, ok=True, result={"processed": 1, "health": {"lastRunAgeMs": 1000}}))
    lines = []
    code = driver.main(["--window", "1"], dict(ENV), tr, lines.append)   # window 1: one call per brand (no chaining)
    assert code == 0
    assert sorted(seen) == sorted([URL("a"), URL("b"), URL("c"), URL("d"), URL("e")])
    for url, req in seen.items():
        assert req["fn"] == "apiAdminRun" and req["args"] == {"job": "runAgent", "budget": 22}
        payload = json.loads(__import__("base64").urlsafe_b64decode(req["token"].split(".")[0] + "=="))
        assert payload["role"] == "admin" and len(payload["brands"]) == 1
    assert len(lines) == 5


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
    assert len(lines) == 5 and sum("FAIL" in l for l in lines) == 1


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


# ---------------- the weekly owner summary ----------------
import datetime as _dt

STATS = {"days": 7, "received": {"email": 12, "whatsapp": 30}, "sent": {"human": 25, "byAgent": {"noa": 10, "agent-two": 15}, "auto_reply": 3, "auto_cancel": 2},
         "firstResponse": {"n": 25, "medianMin": 42, "p90Min": 210}, "open": {"now": 7, "oldestHours": 5.5}, "spamRescued": 2, "kachingCancels": 4, "kachingFailed": 1,
         "sendRefusals": {"cancel_claim": 2}, "engineErrors": {"run: ai_unavailable": 3}, "alertsSuppressed": {"WhatsApp ingest failing for N minutes": 2},
         "whatsapp": {"staleAlerts": 1, "stale": False}, "auditTruncated": False}


def utc(y, m, d, h, mi):
    return _dt.datetime(y, m, d, h, mi, tzinfo=_dt.timezone.utc)


def test_the_window_is_thursday_1800_to_1804_israel_time_in_summer_and_winter():
    assert driver.weekly_window(driver.israel_local(utc(2026, 10, 8, 15, 2)))      # Thursday, UTC+3 (DST until 25 Oct)
    assert driver.weekly_window(driver.israel_local(utc(2026, 12, 3, 16, 2)))      # Thursday, UTC+2
    for bad in [utc(2026, 10, 8, 14, 59), utc(2026, 10, 8, 15, 5), utc(2026, 10, 7, 15, 2), utc(2026, 12, 3, 15, 2), utc(2026, 10, 9, 15, 2)]:
        assert not driver.weekly_window(driver.israel_local(bad)), bad
    assert driver.iso_week_label(driver.israel_local(utc(2026, 10, 8, 15, 2))) == "2026-W41"


def test_fallback_timezone_rule_agrees_with_zoneinfo_around_the_dst_change(monkeypatch):
    import builtins
    real = builtins.__import__
    def no_zoneinfo(name, *a, **k):
        if name == "zoneinfo":
            raise ImportError
        return real(name, *a, **k)
    for when in [utc(2026, 10, 8, 15, 2), utc(2026, 12, 3, 16, 2), utc(2026, 3, 26, 15, 2), utc(2026, 3, 29, 23, 30)]:
        want = driver.israel_local(when)
        monkeypatch.setattr(builtins, "__import__", no_zoneinfo)
        got = driver.israel_local(when)
        monkeypatch.setattr(builtins, "__import__", real)
        assert got.utcoffset() == want.utcoffset(), when


def weekly_transport(sent_before=False, fail=()):
    calls = []
    def tr(url, body, timeout):
        req = json.loads(body)
        brand = {URL("a"): "rozela", URL("b"): "celesta", URL("c"): "apexmen", URL("e"): "selera"}.get(url, "?")
        calls.append((brand, req["args"].get("job"), req["args"]))
        job = req["args"].get("job")
        if brand in fail and job in ("weeklyStats", "sendOwnerReport"):
            return 200, json.dumps(reply(req and body, ok=False, error="bad_args"))
        if job == "sendOwnerReport":
            if req["args"].get("peek"):
                return 200, json.dumps(reply(body, ok=True, result={"sent": sent_before}))
            return 200, json.dumps(reply(body, ok=True, result={"sent": True}))
        if job == "weeklyStats":
            if brand == "rozela":
                return 200, json.dumps(reply(body, ok=False, error="bad_job"))   # an engine that is not deployed yet
            return 200, json.dumps(reply(body, ok=True, result=STATS))
        return 200, json.dumps(reply(body, ok=True, result={"processed": 0, "health": {}}))
    return tr, calls


def test_weekly_is_sent_once_in_the_window_through_celesta_with_all_brands_in_one_text():
    tr, calls = weekly_transport()
    lines = []
    code = driver.main(["--window", "1"], dict(ENV), tr, lines.append, now_utc=utc(2026, 10, 8, 15, 2))
    assert code == 0
    sends = [c for c in calls if c[1] == "sendOwnerReport" and not c[2].get("peek")]
    assert len(sends) == 1 and sends[0][0] == "celesta"
    a = sends[0][2]
    assert a["week"] == "2026-W41"
    assert "בסך הכל" in a["body"] and "— Celesta —" in a["body"] and "— Rozela —" in a["body"] and "לא זמין" in a["body"]
    assert "התקבלו: 12 מיילים · 30 וואטסאפ" in a["body"] and "חציון 42 דק׳" in a["body"] and "3.5 שעות" in a["body"]
    assert any("weekly: sent via celesta" in l for l in lines)
    assert [c[0] for c in calls if c[1] == "weeklyStats"].count("selera") == 1


def test_weekly_not_outside_the_window_not_twice_and_falls_back_to_apexmen():
    tr, calls = weekly_transport()
    driver.main(["--window", "1"], dict(ENV), tr, lambda s: None, now_utc=utc(2026, 10, 8, 14, 59))
    assert not any(c[1] in ("sendOwnerReport", "weeklyStats") for c in calls)
    tr, calls = weekly_transport(sent_before=True)
    lines = []
    driver.main(["--window", "1"], dict(ENV), tr, lines.append, now_utc=utc(2026, 10, 8, 15, 3))
    assert not any(c[1] == "weeklyStats" for c in calls), "already sent: no stats are even collected"
    assert any("already sent" in l for l in lines)
    tr, calls = weekly_transport(fail=("celesta",))
    lines = []
    driver.main(["--window", "1"], dict(ENV), tr, lines.append, now_utc=utc(2026, 10, 8, 15, 3))
    sends = [c for c in calls if c[1] == "sendOwnerReport" and not c[2].get("peek")]
    assert [c[0] for c in sends] == ["celesta", "apexmen"], "celesta failed, apexmen sends"
    assert any("via apexmen" in l for l in lines)


def test_compose_is_plain_tidy_and_survives_a_missing_section():
    local = driver.israel_local(utc(2026, 10, 8, 15, 2))
    subject, body = driver.compose_weekly({"celesta": STATS, "rozela": None}, local)
    assert subject.startswith("סיכום שבועי")
    assert "<" not in body and "{" not in body
    assert "נשלחו: 25 ידנית (agent-two 15, noa 10) · 3 תשובות אוטומטיות · 2 ביטולים אוטומטיים" in body
    assert "דחיות שליחה: cancel_claim 2" in body and "שגיאות מנוע:" in body and "התראות שהושתקו: 2" in body
    assert "וואטסאפ: תקין · התראות ניתוק: 1" in body
    assert len(body) < 3000


# ---------------- Gmail quota: the brand is paused for 30 minutes ----------------

def test_a_brand_with_a_spent_gmail_quota_is_paused_for_30_minutes_and_resumes(tmp_path, monkeypatch):
    calls = []
    def tr(url, body, timeout):
        calls.append(url)
        return 200, json.dumps(reply(body, ok=True, result={"processed": 0, "waDrafted": 0, "stopped": "gmail_quota", "health": {}}))
    env = dict(ENV, DRIVER_STATE_FILE=str(tmp_path / "backoff.json"))
    t = [1_000_000.0]
    monkeypatch.setattr(driver.time, "time", lambda: t[0])
    lines = []
    assert driver.main(["--brands", "selera"], env, tr, lines.append) == 0
    first = len(calls)
    assert first >= 1 and any("backoff 30 min" in l for l in lines)
    t[0] += 60
    lines.clear()
    assert driver.main(["--brands", "selera"], env, tr, lines.append) == 0
    assert len(calls) == first, "not one engine call while paused"
    assert "backoff gmail_quota" in lines[0]
    t[0] += 31 * 60
    driver.main(["--brands", "selera"], env, tr, lambda s: None)
    assert len(calls) > first, "resumes after 30 minutes"


def test_the_pause_is_per_brand_and_never_when_the_brand_has_whatsapp_work(tmp_path, monkeypatch):
    def tr(url, body, timeout):
        sel = url == URL("e")
        return 200, json.dumps(reply(body, ok=True, result={"processed": 0, "waDrafted": 0 if sel else 3, "stopped": "gmail_quota", "health": {}}))
    env = dict(ENV, DRIVER_STATE_FILE=str(tmp_path / "b.json"))
    monkeypatch.setattr(driver.time, "time", lambda: 5_000_000.0)
    driver.main(["--brands", "selera,celesta"], env, tr, lambda s: None)
    st = json.load(open(env["DRIVER_STATE_FILE"]))
    assert "selera" in st and "celesta" not in st, st
