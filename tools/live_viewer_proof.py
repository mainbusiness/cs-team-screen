#!/usr/bin/env python3
"""Live proof of the read-only viewer role against the real screen (2026-11-09). Run on the Mac; secrets come from / go to the Keychain only, nothing secret is printed.

  python3 tools/live_viewer_proof.py create <username> <brand> [--display NAME]   # create a viewer through the user-manager API as the automation admin;
                                                                                   # the one-time password goes to Keychain cs-engine/screen/temp/<username>
  python3 tools/live_viewer_proof.py prove <username>                              # sign in as that viewer (first sign-in sets a new password, kept in Keychain
                                                                                   # cs-engine/screen/<username>), read, then try EVERY write fn: all must be 403
  python3 tools/live_viewer_proof.py check-login <username>                        # the temporary password still works and leads to the change-password page (does NOT change it)
  python3 tools/live_viewer_proof.py disable <username>                            # disable an account (a QA account after the proof)
"""
import http.cookiejar
import json
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

READS = ("apiBoot", "apiTicket", "apiSearch", "apiAutoCancelList", "apiStatus", "apiTickets", "apiAutoReplyList", "apiCancelStats", "apiCancelReasons", "apiBillingHealth", "apiDayStats")
WRITES = ("apiSend", "apiSaveDraft", "apiNote", "apiClose", "apiMarkHandled", "apiKachingCancel", "apiKachingAction", "apiKachingContract", "apiKachingVariants",
          "apiOrderEdit", "apiOrderEditState", "apiSubCancel", "apiSubCancelPreview", "apiLinkCustomer", "apiMergeTickets", "apiAutoCancelApprove", "apiAutoCancelReject",
          "apiAutoReplyReview", "apiWaTakeOver", "apiRedraftOne", "apiTemplates", "apiSendTemplate", "apiSettings", "apiAiNotes", "apiAiNoteAdd", "apiAiNoteDelete",
          "apiAiNoteCheck", "apiAiNoteAttach", "apiAiNoteSuggestions", "apiAiNoteSuggestDecide", "apiSaleCandidates", "apiSaleLog", "apiSaleMine", "apiSaleProof",
          "apiSaleList", "apiSaleDecide", "apiSaleSuggestions", "apiSaleSuggestCredit", "apiSaleSuggestDismiss", "apiSaleScan", "apiAttachPut", "apiKnowledge",
          "apiCustomerLookup", "apiResult", "apiAdminRun", "apiWaIngest")
OTHER_POST = ("/api/{b}/activity", "/api/{b}/snooze", "/api/{b}/assistant", "/api/{b}/translate", "/api/{b}/translate-out", "/api/{b}/zipfix", "/api/sysreq",
              "/api/manage/users", "/api/dash/snapshot", "/api/dash/warm")


def kc_get(acct):
    r = subprocess.run(["security", "find-generic-password", "-s", "cs-engine", "-a", acct, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def kc_set(acct, val):
    subprocess.run(["security", "add-generic-password", "-U", "-s", "cs-engine", "-a", acct, "-w", val], check=True, capture_output=True)


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def req(self, method, path, data=None, js=None):
        h = {"Origin": self.base}
        body = None
        if js is not None:
            body = json.dumps(js).encode()
            h["Content-Type"] = "application/json"
            h["X-CSRF-Token"] = self.csrf
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            r = self.op.open(urllib.request.Request(self.base + path, data=body, method=method, headers=h), timeout=90)
            code, t, url = r.status, r.read().decode(), r.geturl()
        except urllib.error.HTTPError as e:
            code, t, url = e.code, e.read().decode(), self.base + path
        m = re.search(r'name="csrf"[^>]*(?:value|content)="([^"]+)"', t) or re.search(r'(?:value|content)="([^"]+)"[^>]*name="csrf"', t)
        if m:
            self.csrf = m.group(1)
        return code, url, t

    def login(self, user, pw):
        self.req("GET", "/cs/login")
        return self.req("POST", "/cs/login", {"username": user, "password": pw, "csrf": self.csrf})

    def api(self, method, path, js=None):
        code, _, t = self.req(method, path, js=js if method == "POST" else None)
        try:
            return code, json.loads(t)
        except ValueError:
            return code, {"raw": t[:80]}


def base():
    return kc_get("screen/URL")


def admin_client():
    c = Client(base())
    code, url, _ = c.login("claude-admin", kc_get("screen/claude-admin"))
    assert url.endswith("/cs") or "/cs" in url, url
    c.req("GET", "/cs")
    return c


def cmd_create(user, brand, display):
    c = admin_client()
    code, r = c.api("POST", "/api/manage/users", {"username": user, "display_name": display or user, "roles": ["viewer"], "brands": [brand], "lang": "he"})
    assert code in (200, 201) and r.get("ok"), (code, {k: v for k, v in r.items() if k != "temp_password"})
    kc_set("screen/temp/" + user, r["temp_password"])
    print("created", user, "roles", r["user"]["roles"], "brands", r["user"]["brands"], "must_change", r["user"]["must_change"], "(one-time password in Keychain cs-engine/screen/temp/%s)" % user)


def cmd_check_login(user):
    c = Client(base())
    code, url, _ = c.login(user, kc_get("screen/temp/" + user))
    ok = url.endswith("/cs/password")
    print("temporary password works and leads to the change-password page:", ok)
    sys.exit(0 if ok else 1)


def cmd_disable(user):
    c = admin_client()
    code, r = c.api("POST", "/api/manage/users/" + user, {"disabled": True})
    print("disable", user, code, r.get("ok"))


def cmd_prove(user):
    b = Client(base())
    pw = kc_get("screen/" + user)
    if not pw:
        temp = kc_get("screen/temp/" + user)
        code, url, _ = b.login(user, temp)
        assert url.endswith("/cs/password"), url
        new = secrets.token_urlsafe(24)
        code, url, _ = b.req("POST", "/cs/password", {"current": temp, "new": new, "repeat": new, "csrf": b.csrf})
        kc_set("screen/" + user, new)
        pw = new
        b = Client(base())
    code, url, _ = b.login(user, pw)
    b.req("GET", "/cs")
    code, me = b.api("GET", "/api/me")
    assert code == 200 and me["engine_role"] == "viewer" and me["read_only"] is True and me["can_manage_users"] is False and me["is_admin"] is False, me
    brands = [x["id"] for x in me["brands"]]
    brand = brands[0]
    print("signed in as", user, "| engine_role", me["engine_role"], "| read_only", me["read_only"], "| brands", brands)
    fails = []
    # ---- reads
    code, boot = b.api("POST", "/api/%s/list" % brand, {})
    print("list: HTTP", code, "ok", boot.get("ok"), "tickets", len(boot.get("tickets") or []))
    if not (code == 200 and boot.get("ok") and boot.get("tickets")):
        fails.append("list")
    tid = (boot.get("tickets") or [{}])[0].get("id")
    code, tk = b.api("POST", "/api/%s/ticket" % brand, {"id": tid, "open": True})
    print("ticket (read):", code, tk.get("ok"), "conversation messages", len(((tk.get("extras") or {}).get("conversation")) or []))
    if not (code == 200 and tk.get("ok")):
        fails.append("ticket")
    code, se = b.api("POST", "/api/%s/apiSearch" % brand, {"args": {"q": "support"}})
    if code != 200 or not se.get("ok"):                       # a search over the whole mailbox takes 4-9 s and the first try can time out: one more
        code, se = b.api("POST", "/api/%s/apiSearch" % brand, {"args": {"q": "support"}})
    print("search (read):", code, se.get("ok"))
    if not (code == 200 and se.get("ok")):
        fails.append("search")
    for path in ("/api/dash", "/api/dash/open", "/api/dash/sla", "/api/dash/cancels", "/api/dash/cancel-reasons", "/api/dash/billing"):
        code, j = b.api("GET", path)
        extra = ""
        if path.endswith("billing") and j.get("ok"):
            x = j["brands"][brand]
            extra = " state=%s inDunning=%s firstTry=%s%%" % (x.get("state"), (x.get("billing") or {}).get("inDunning"), (x.get("billing") or {}).get("firstTrySuccessRate"))
        print("read %-26s HTTP %s ok=%s%s" % (path, code, j.get("ok"), extra))
        if not (code == 200 and j.get("ok")):
            fails.append(path)
    code, cs = b.api("POST", "/api/%s/apiCancelStats" % brand, {"args": {"from": "2026-11-01", "to": "2026-11-08"}})
    print("apiCancelStats (read, through the proxy):", code, cs.get("ok"))
    if not (code == 200 and cs.get("ok")):
        fails.append("apiCancelStats")
    # ---- writes: every one must be refused
    bad = []
    for fn in WRITES:
        code, j = b.api("POST", "/api/%s/%s" % (brand, fn), {"args": {"id": tid or "t1", "text": "x", "contractId": "gid://shopify/SubscriptionContract/1", "action": "pause", "confirm": "0001"}})
        if code not in (403, 404):
            bad.append((fn, code, j.get("error")))
    n_403 = len(WRITES) - len(bad)
    print("write fns refused (403/404): %d of %d" % (n_403, len(WRITES)), "| NOT refused:", bad)
    codes = {}
    for fn in ("apiSend", "apiSaveDraft", "apiNote", "apiClose", "apiMarkHandled", "apiKachingCancel", "apiKachingAction", "apiOrderEdit", "apiSubCancel", "apiAutoCancelApprove",
               "apiMergeTickets", "apiWaTakeOver", "apiSendTemplate", "apiSettings"):
        code, j = b.api("POST", "/api/%s/%s" % (brand, fn), {"args": {"id": tid or "t1"}})
        codes[fn] = (code, j.get("error"))
    print("explicit:", json.dumps(codes, ensure_ascii=False))
    if bad or any(v != (403, "forbidden_role") for v in codes.values()):
        fails.append("writes")
    other = []
    for p in OTHER_POST:
        code, j = b.api("POST", p.format(b=brand), {"id": tid or "t1", "kind": "edit", "text": "x", "messages": [{"role": "user", "content": "hi"}]})
        if code not in (403, 404):
            other.append((p, code))
    print("other POST routes refused: %d of %d" % (len(OTHER_POST) - len(other), len(OTHER_POST)), "| NOT refused:", other)
    if other:
        fails.append("other")
    print("RESULT:", "ALL PASSED" if not fails else "FAILED " + ",".join(fails))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["create"]:
        cmd_create(a[1], a[2], a[a.index("--display") + 1] if "--display" in a else "")
    elif a[:1] == ["prove"]:
        cmd_prove(a[1])
    elif a[:1] == ["check-login"]:
        cmd_check_login(a[1])
    elif a[:1] == ["disable"]:
        cmd_disable(a[1])
    else:
        print(__doc__)
