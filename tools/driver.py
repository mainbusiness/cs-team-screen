#!/usr/bin/env python3
"""External driver: calls every brand engine's `runAgent` admin job, once per run (cron / launchd, every minute).

Why: Apps Script time triggers are capped (consumer accounts: 90 min of trigger runtime a day). A web-app call is not. The engines keep
their 5-minute trigger as a fallback and leave at once while this driver is alive (heartbeat), so the quota is almost untouched.

  TOKEN_SECRET   the engines' Script Property (env, or the Keychain item cs-engine / all/TOKEN_SECRET on the Mac)
  ENGINES_JSON   {"rozela": "https://script.google.com/macros/s/<id>/exec", ...} (env, or --engines FILE, or deploy/deployments.json)
  DRIVER_BRANDS  comma list, default rozela,celesta,apexmen (a brand not yet live must not be driven)

Brands run in parallel. Logs one status line per brand, never customer data. Exit 0 = every brand answered and is healthy,
1 = a brand failed, 2 = a brand answers but has not completed a run for 15 minutes. Two drivers at once are harmless: the engine's run guard.
"""
import argparse, uuid, base64, concurrent.futures, hashlib, hmac, json, os, re, subprocess, sys, time, urllib.error, urllib.request

DEFAULT_BRANDS = "rozela,celesta,apexmen"
URL_RE = re.compile(r"^https://script\.google\.com/(?:a/macros/[A-Za-z0-9.-]+|macros)/s/[A-Za-z0-9_-]{20,200}/exec$")
STALE_MS = 15 * 60 * 1000
TOKEN_TTL_S = 600


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def mint_token(secret: str, brand: str, now=None) -> str:
    """Same format as team_screen/security.py mint_engine_token: base64url(payload) + '.' + base64url(HMAC-SHA256(secret, that string))."""
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("TOKEN_SECRET missing or shorter than 32 characters")
    iat = int(now if now is not None else time.time())
    payload = {"user": "driver", "role": "admin", "brands": [brand], "lang": "he", "iat": iat, "exp": iat + TOKEN_TTL_S}
    p64 = b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode())
    return p64 + "." + b64url(hmac.new(secret.encode(), p64.encode("ascii"), hashlib.sha256).digest())


def keychain(account: str) -> str:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", "cs-engine", "-a", account, "-w"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def load_engines(environ, engines_file=None):
    raw = environ.get("ENGINES_JSON", "")
    if not raw and engines_file:
        with open(engines_file) as f:
            raw = f.read()
    if not raw:
        dep = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "deploy", "deployments.json")
        if os.path.exists(dep):
            with open(dep) as f:
                ids = json.load(f)
            raw = json.dumps({b: "https://script.google.com/macros/s/%s/exec" % i for b, i in ids.items()})
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}
    return {str(b).lower(): u for b, u in data.items() if isinstance(u, str) and URL_RE.match(u)}


def http_transport(url: str, body: bytes, timeout: float):
    """POST; Apps Script answers 302 to googleusercontent, urllib follows it with a GET (the run already happened on the POST)."""
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def age_min(ms):
    return "-" if ms is None else "%dm" % round(ms / 60000)


def run_brand(brand, url, secret, transport, budget, now=None, idle=0):
    """One brand. Returns (code, line): code 0 ok, 1 failed, 2 stale."""
    t0 = time.time()
    try:
        rid = uuid.uuid4().hex
        args = {"job": "runAgent", "budget": budget}
        if idle:
            args["idle"] = idle   # a second driver: the engine answers "other_driver_fresh" at once when an external run completed within `idle` seconds
        body = json.dumps({"fn": "apiAdminRun", "rid": rid, "args": args, "token": mint_token(secret, brand, now)}).encode()
        status, text = transport(url, body, budget + 120)
        out = json.loads(text)
        # the reply must be the answer to THIS request (a bare {"ok":true} is what a POST turned into a GET looks like)
        if not isinstance(out, dict) or out.get("fn") != "apiAdminRun" or out.get("rid") != rid:
            return 1, "%s FAIL reply_is_not_ours (fn/rid missing or different)" % brand
    except Exception as e:   # network, JSON, anything: the text of OUR error only, never a response body
        return 1, "%s FAIL %s" % (brand, type(e).__name__)
    if status != 200 or not isinstance(out, dict) or not out.get("ok"):
        return 1, "%s FAIL http=%s error=%s" % (brand, status, str(out.get("error", "?") if isinstance(out, dict) else "?")[:40])
    r = out.get("result") or {}
    secs = int(time.time() - t0)
    if r.get("error"):
        return 1, "%s FAIL run_error=%s" % (brand, str(r["error"])[:60])
    if r.get("skipped") == "other_driver_fresh":
        return 0, "%s ok other_driver_fresh (%ds)" % (brand, secs)
    if isinstance(r.get("skipped"), str):   # "running" / "external_driver" / "lock_busy" (a number is the count of threads skipped)
        return 0, "%s ok skipped=%s (%ds)" % (brand, r["skipped"], secs)
    h = r.get("health") or {}
    rd = r.get("redraft") or {}
    line = "%s ok processed=%s wa=%s redraft=%s/rem%s stopped=%s lastRunAge=%s waErr=%s (%ds)" % (
        brand, r.get("processed", 0), r.get("waDrafted", 0), rd.get("redrafted", 0), rd.get("remaining", "-"), r.get("stopped") or "-",
        age_min(h.get("lastRunAgeMs")), age_min(h.get("waErrorMs") or None), secs)
    if (h.get("lastRunAgeMs") or 0) > STALE_MS:
        return 2, line + " STALE"
    return 0, line


def main(argv=None, environ=None, transport=None, out=print):
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", help="comma list (default env DRIVER_BRANDS or %s)" % DEFAULT_BRANDS)
    ap.add_argument("--engines", help="file with the ENGINES_JSON object")
    ap.add_argument("--budget", type=int, default=150, help="seconds the engine may spend picking up work (30..270)")
    ap.add_argument("--only-if-stale", type=int, default=0, metavar="SECONDS", help="second driver: run only when no external run completed within this many seconds")
    a = ap.parse_args(argv)
    environ = os.environ if environ is None else environ
    transport = transport or http_transport
    secret = environ.get("TOKEN_SECRET") or keychain("all/TOKEN_SECRET")
    engines = load_engines(environ, a.engines)
    want = [b.strip().lower() for b in (a.brands or environ.get("DRIVER_BRANDS") or DEFAULT_BRANDS).split(",") if b.strip()]
    if len(secret) < 32:
        out("driver: TOKEN_SECRET missing")
        return 1
    missing = [b for b in want if b not in engines]
    for b in missing:
        out("%s FAIL no engine url" % b)
    todo = [b for b in want if b in engines]
    codes = [1] * len(missing)
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(todo)) as ex:
            futs = {b: ex.submit(run_brand, b, engines[b], secret, transport, max(30, min(270, a.budget)), None, max(0, min(600, a.only_if_stale))) for b in todo}
            for b in todo:
                code, line = futs[b].result()
                out(time.strftime("%H:%M:%S ") + line)
                codes.append(code)
    return max(codes) if codes else 1


if __name__ == "__main__":
    sys.exit(main())
