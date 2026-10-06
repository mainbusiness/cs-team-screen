#!/usr/bin/env python3
"""External driver: calls every brand engine's `runAgent` admin job, once per run (cron / launchd, every minute).

Why: Apps Script time triggers are capped (consumer accounts: 90 min of trigger runtime a day). A web-app call is not. The engines keep
their 5-minute trigger as a fallback and leave at once while this driver is alive (heartbeat), so the quota is almost untouched.

  TOKEN_SECRET   the engines' Script Property (env, or the Keychain item cs-engine / all/TOKEN_SECRET on the Mac)
  ENGINES_JSON   {"rozela": "https://script.google.com/macros/s/<id>/exec", ...} (env, or --engines FILE, or deploy/deployments.json)
  DRIVER_BRANDS  comma list, default rozela,celesta,apexmen,selera,velora (a brand not yet live must not be driven)

Brands run in parallel. Logs one status line per brand, never customer data. Exit 0 = every brand answered and is healthy,
1 = a brand failed, 2 = a brand answers but has not completed a run for 15 minutes. Two drivers at once are harmless: the engine's run guard.
"""
import argparse, tempfile, uuid, base64, concurrent.futures, hashlib, hmac, json, os, re, subprocess, sys, time, urllib.error, urllib.request

DEFAULT_BRANDS = "rozela,celesta,apexmen,selera,velora"
def _core_url_re():
    """The core server (Node + Postgres) may replace a brand's Apps Script URL. Only the ONE host named in CORE_ENGINE_HOST is accepted."""
    host = os.environ.get("CORE_ENGINE_HOST", "").strip().lower()
    if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", host):
        return None
    return re.compile(r"^https://" + re.escape(host) + r"/exec/[a-z][a-z0-9]{1,30}$")


class _EngineUrl:
    """Apps Script web-app URLs, plus the core server's per-brand URL when CORE_ENGINE_HOST is set."""
    def __init__(self, gas):
        self.gas = gas

    def match(self, url):
        core = _core_url_re()
        return self.gas.match(url) or (core.match(url) if core else None)


URL_RE = _EngineUrl(re.compile(r"^https://script\.google\.com/(?:a/macros/[A-Za-z0-9.-]+|macros)/s/[A-Za-z0-9_-]{20,200}/exec$"))
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


def call_engine(url, secret, brand, transport, fn, args, timeout, now=None):
    """One engine call; returns the parsed reply or raises ValueError('reply_is_not_ours' | ...)."""
    rid = uuid.uuid4().hex
    body = json.dumps({"fn": fn, "rid": rid, "args": args, "token": mint_token(secret, brand, now)}).encode()
    status, text = transport(url, body, timeout)
    out = json.loads(text)
    # the reply must be the answer to THIS request (a bare {"ok":true} is what a POST turned into a GET looks like)
    if not isinstance(out, dict) or out.get("fn") != fn or out.get("rid") != rid:
        raise ValueError("reply_is_not_ours")
    if status != 200 or not out.get("ok"):
        raise ValueError("http=%s error=%s" % (status, str(out.get("error", "?"))[:40]))
    return out


def progress_confirmed(brand, url, secret, transport, now_s=None):
    """The reply of a long call is advisory (Apps Script may answer a slow POST with HTML): the engine's own status says whether a run went on."""
    try:
        r = call_engine(url, secret, brand, transport, "apiStatus", {}, 30)
        att = r.get("lastAttempt")
        if not att:
            return False
        import datetime
        t = datetime.datetime.fromisoformat(att.replace("Z", "+00:00")).timestamp()
        return (now_s if now_s is not None else time.time()) - t < 150
    except Exception:
        return False


def run_brand(brand, url, secret, transport, budget, now=None, idle=0):
    """One brand. Returns (code, line): code 0 ok, 1 failed, 2 stale."""
    t0 = time.time()
    args = {"job": "runAgent", "budget": budget}
    if idle:
        args["idle"] = idle   # a second driver: the engine answers "other_driver_fresh" at once when an external run completed within `idle` seconds
    try:
        out = call_engine(url, secret, brand, transport, "apiAdminRun", args, budget + 40, now)
    except Exception as e:   # network, HTML, a reply that is not ours: our own error text only, never a body
        why = str(e) if isinstance(e, ValueError) else type(e).__name__
        if why != "reply_is_not_ours" and not why.startswith("JSON") and "http=" in why and "unauthorized" in why:
            return 1, "%s FAIL %s" % (brand, why)
        if progress_confirmed(brand, url, secret, transport):
            return 0, "%s ok reply_lost(%s) but the engine's own status shows a run just happened (%ds)" % (brand, why, int(time.time() - t0))
        return 1, "%s FAIL %s (and no run seen in the engine's status)" % (brand, why)
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


# ---------------- a brand whose Gmail quota is spent: pause it for 30 minutes (the engine says `stopped=gmail_quota`) ----------------

GMAIL_BACKOFF_S = 30 * 60


def backoff_path(environ):
    return environ.get("DRIVER_STATE_FILE") or os.path.join(tempfile.gettempdir(), "cs_driver_backoff.json")


def backoff_load(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def backoff_until(path, brand):
    try:
        return float(backoff_load(path).get(brand) or 0)
    except Exception:
        return 0.0


def backoff_set(path, brand, until):
    d = backoff_load(path)
    d[brand] = until
    try:
        with open(path, "w") as f:
            json.dump({k: v for k, v in d.items() if isinstance(v, (int, float)) and v > time.time() - 3600}, f)
    except Exception:
        pass   # a read-only place (a cron host without a disk): the engine answers a paused brand in one property read anyway


def wants_backoff(line):
    """The engine paused its Gmail work (quota) and had no WhatsApp work this run: nothing to gain from calling it every minute."""
    return "stopped=gmail_quota" in line and (" wa=0 " in line or " wa=0)" in line or "wa=0" in line)


def run_brand_chain(brand, url, secret, transport, budget, idle, window_s):
    """Short web runs back to back inside the driver's minute: another call while the last one found work (processed or redrafted something)."""
    t0 = time.time()
    code, line = run_brand(brand, url, secret, transport, budget, None, idle)
    lines = [line]
    while code == 0 and "processed=0 wa=0 redraft=0/" not in line and "skipped=" not in line and "other_driver_fresh" not in line and "reply_lost" not in line \
            and len(lines) < 3 and time.time() - t0 + budget + 10 < window_s:
        code, line = run_brand(brand, url, secret, transport, budget, None, idle)
        lines.append(line)
    return code, lines[-1] if len(lines) == 1 else "%s [%d calls] last: %s" % (brand, len(lines), line)


# ---------------- the weekly owner summary: Thursday 18:00 Israel time, ONE mail, counts only ----------------

WEEKLY_SENDERS = ("celesta", "apexmen")      # the engines that mail it (rozela's engine cannot be deployed right now); the first that works sends
BRAND_TITLES = {"rozela": "Rozela", "celesta": "Celesta", "apexmen": "ApexMen", "velora": "Velora", "selera": "Selera"}


def israel_local(now_utc):
    """Local time in Israel (DST handled). zoneinfo when the system has tzdata, else the statutory rule: DST from the Friday before the last Sunday of March
    02:00 to the last Sunday of October 02:00 (local)."""
    import datetime as dt
    try:
        from zoneinfo import ZoneInfo
        return now_utc.astimezone(ZoneInfo("Asia/Jerusalem"))
    except Exception:
        def last_sunday(y, m):
            d = dt.date(y, m, 31 if m in (3, 10) else 30)
            while d.weekday() != 6:
                d -= dt.timedelta(days=1)
            return d
        y = now_utc.year
        start = dt.datetime.combine(last_sunday(y, 3) - dt.timedelta(days=2), dt.time(0, 0), tzinfo=dt.timezone.utc) + dt.timedelta(hours=2 - 2)
        end = dt.datetime.combine(last_sunday(y, 10), dt.time(0, 0), tzinfo=dt.timezone.utc) + dt.timedelta(hours=-1)
        off = 3 if start <= now_utc < end else 2
        return now_utc.astimezone(dt.timezone(dt.timedelta(hours=off)))


def weekly_window(local):
    """Thursday 18:00 to 18:04 local."""
    return local.weekday() == 3 and local.hour == 18 and local.minute < 5


def iso_week_label(local):
    y, w, _ = local.isocalendar()
    return "%d-W%02d" % (y, w)


def fmt_minutes(m):
    if m is None:
        return "אין נתונים"
    if m < 120:
        return "%d דק׳" % m
    return ("%.1f" % (m / 60.0)).rstrip("0").rstrip(".") + " שעות"


def _top(d, n=4):
    items = sorted((d or {}).items(), key=lambda kv: -kv[1])[:n]
    return ", ".join("%s %d" % (k, v) for k, v in items)


def compose_weekly(stats, local, days=7):
    """stats = {brand: weeklyStats dict | None}. Plain Hebrew text: totals first, then a short section per brand."""
    import datetime as dt
    start = (local - dt.timedelta(days=days)).strftime("%d.%m")
    end = local.strftime("%d.%m.%Y")
    ok = {b: s for b, s in stats.items() if s}
    tot = {"received": 0, "sent": 0, "open": 0, "rescued": 0, "cancels": 0}
    for s in ok.values():
        tot["received"] += (s.get("received") or {}).get("email", 0) + (s.get("received") or {}).get("whatsapp", 0)
        sent = s.get("sent") or {}
        tot["sent"] += sent.get("human", 0) + sent.get("auto_reply", 0) + sent.get("auto_cancel", 0)
        tot["open"] += (s.get("open") or {}).get("now", 0)
        tot["rescued"] += s.get("spamRescued", 0)
        tot["cancels"] += s.get("kachingCancels", 0)
    lines = ["סיכום שבועי — %s עד %s" % (start, end), "",
             "בסך הכל: התקבלו %d פניות · נשלחו %d תשובות · פתוחות עכשיו %d · הצלות מספאם %d · ביטולי מנוי %d" % (tot["received"], tot["sent"], tot["open"], tot["rescued"], tot["cancels"])]
    for b in stats:
        s = stats[b]
        lines += ["", "— %s —" % BRAND_TITLES.get(b, b)]
        if not s:
            lines.append("לא זמין (המנוע לא ענה או עדיין לא עודכן)")
            continue
        rc, sent, fr, op = s.get("received") or {}, s.get("sent") or {}, s.get("firstResponse") or {}, s.get("open") or {}
        lines.append("התקבלו: %d מיילים · %d וואטסאפ" % (rc.get("email", 0), rc.get("whatsapp", 0)))
        by = _top(sent.get("byAgent"), 6)
        lines.append("נשלחו: %d ידנית%s · %d תשובות אוטומטיות · %d ביטולים אוטומטיים" % (sent.get("human", 0), " (%s)" % by if by else "", sent.get("auto_reply", 0), sent.get("auto_cancel", 0)))
        if fr.get("n"):
            lines.append("זמן מענה ראשון: חציון %s · 90%% עד %s (על %d פניות)" % (fmt_minutes(fr.get("medianMin")), fmt_minutes(fr.get("p90Min")), fr["n"]))
        else:
            lines.append("זמן מענה ראשון: אין נתונים")
        lines.append("פתוחות עכשיו: %d%s" % (op.get("now", 0), " (הישנה ביותר: %s)" % fmt_minutes(int(op["oldestHours"] * 60)) if op.get("oldestHours") is not None else ""))
        lines.append("הצלות מספאם: %d · ביטולי מנוי ב-Kaching: %d%s" % (s.get("spamRescued", 0), s.get("kachingCancels", 0), " (נכשלו או נדחו: %d)" % s["kachingFailed"] if s.get("kachingFailed") else ""))
        if s.get("sendRefusals"):
            lines.append("דחיות שליחה: " + _top(s["sendRefusals"]))
        if s.get("sendWarnings"):
            lines.append("נשלחו עם אזהרה: " + _top(s["sendWarnings"]))
        if s.get("engineErrors"):
            lines.append("שגיאות מנוע: " + _top(s["engineErrors"]))
        sup = s.get("alertsSuppressed") or {}
        if sup:
            lines.append("התראות שהושתקו: %d (%s)" % (sum(sup.values()), _top(sup, 3)))
        wa = s.get("whatsapp") or {}
        lines.append("וואטסאפ: %s%s" % ("לא נראה כעת" if wa.get("stale") else "תקין", " · התראות ניתוק: %d" % wa.get("staleAlerts", 0) if wa.get("staleAlerts") else ""))
        if s.get("auditTruncated"):
            lines.append("שימו לב: היומן קוצר, חלק מהספירות חלקיות")
    return "סיכום שבועי " + end, "\n".join(lines)


def maybe_weekly(engines, secret, transport, brands, now_utc=None, out=print):
    """Called every minute by the driver. In the Thursday 18:00-18:04 window, and only if this ISO week's report has not been sent (the engine that sends it keeps the stamp):
    collect weeklyStats from every brand, compose ONE summary, send it through sendOwnerReport on the first sender engine that works. Never raises."""
    import datetime as dt
    try:
        now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
        local = israel_local(now_utc)
        if not weekly_window(local):
            return None
        week = iso_week_label(local)
        senders = [b for b in WEEKLY_SENDERS if b in engines] + [b for b in brands if b in engines and b not in WEEKLY_SENDERS]   # last resort: any engine that has the job
        for b in senders:   # already sent? one cheap call
            try:
                r = call_engine(engines[b], secret, b, transport, "apiAdminRun", {"job": "sendOwnerReport", "subject": "x", "body": "x", "week": week, "peek": 1}, 30)
                if (r.get("result") or {}).get("sent"):
                    return "weekly: already sent (%s)" % week
                break
            except Exception:
                continue
        stats = {}
        for b in brands:
            if b not in engines:
                continue
            try:
                stats[b] = (call_engine(engines[b], secret, b, transport, "apiAdminRun", {"job": "weeklyStats", "days": 7}, 60).get("result") or None)
                if stats[b] is not None and "received" not in stats[b]:
                    stats[b] = None
            except Exception:
                stats[b] = None
        subject, body = compose_weekly(stats, local)
        for b in senders:
            try:
                r = call_engine(engines[b], secret, b, transport, "apiAdminRun", {"job": "sendOwnerReport", "subject": subject, "body": body, "week": week}, 60)
                res = r.get("result") or {}
                if res.get("sent") or res.get("skipped") == "already_sent":
                    return "weekly: %s via %s (%s)" % ("sent" if res.get("sent") else "already sent", b, week)
            except Exception:
                continue
        return "weekly: FAILED to send (%s)" % week
    except Exception as e:
        return "weekly: error %s" % type(e).__name__


def main(argv=None, environ=None, transport=None, out=print, now_utc=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--brands", help="comma list (default env DRIVER_BRANDS or %s)" % DEFAULT_BRANDS)
    ap.add_argument("--engines", help="file with the ENGINES_JSON object")
    ap.add_argument("--budget", type=int, default=22, help="seconds a web run may spend (10..25: longer web replies are lost)")
    ap.add_argument("--window", type=int, default=55, help="seconds the driver keeps chaining short runs per invocation")
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
    state = backoff_path(environ)
    for b in list(todo):
        until = backoff_until(state, b)
        if until > time.time():   # Gmail quota spent: not hammered every minute
            out(time.strftime("%H:%M:%S ") + "%s ok backoff gmail_quota until %s (%d min left)" % (b, time.strftime("%H:%M", time.localtime(until)), int((until - time.time()) / 60) + 1))
            todo.remove(b)
            codes.append(0)
    paused_any = len(todo) != len([b for b in want if b in engines])
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(todo)) as ex:
            futs = {b: ex.submit(run_brand_chain, b, engines[b], secret, transport, max(10, min(25, a.budget)), max(0, min(600, a.only_if_stale)), a.window) for b in todo}
            for b in todo:
                code, line = futs[b].result()
                out(time.strftime("%H:%M:%S ") + line)
                codes.append(code)
                if wants_backoff(line):
                    backoff_set(state, b, time.time() + GMAIL_BACKOFF_S)
                    out(time.strftime("%H:%M:%S ") + "%s backoff 30 min (Gmail daily quota)" % b)
    if todo or paused_any:
        line = maybe_weekly(engines, secret, transport, want, now_utc, out)
        if line:
            out(time.strftime("%H:%M:%S ") + line)
    return max(codes) if codes else 1


if __name__ == "__main__":
    sys.exit(main())
