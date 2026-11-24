"""Owner accounts (2026-11-25, owners.py) in a real browser against the mock engine, signed in as a MANAGER (admin + user-manager):
the owner is on a ticket and typing, an agent with a similar name ("agent-one") is on the same ticket and sends. The manager sees the
agent's presence chip and dashboard row, and NO chip, NO row, NO last sign-in and NO edit / reset control for the owner; the server
refuses a reset / disable of the owner with 403 even when the page is bypassed."""
import json

import pytest

from browser_server import start
from pw_launch import launch, pw

OWNER, TWIN, MGR = "guy", "agent-one", "mgr-cs"
USERS = ((OWNER, ["admin", "user-manager"], ["rozela", "celesta", "apexmen", "velora"], "he"),
         (TWIN, ["agent"], ["rozela"], "he"),
         (MGR, ["admin", "user-manager"], ["rozela", "celesta", "apexmen", "velora"], "he"))
TID = "t18f2a11"
_NO_QREMIND = ("(() => { const g = Storage.prototype.getItem; Storage.prototype.getItem = function (k) { return String(k).indexOf('cs-quality-later-') === 0 "
               "? String(Date.now() + 864e5) : g.call(this, k); }; })();")


@pytest.fixture(scope="module")
def srv():
    base, pwd, proc = start(extra_env={}, users=USERS)
    yield base, pwd
    proc.terminate()


def page_for(b, base, pwd, user, width=1280):
    ctx = b.new_context(viewport={"width": width, "height": 950})
    ctx.add_init_script(_NO_QREMIND)
    pg = ctx.new_page()
    pg.errors, pg.watch = [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))

    def on_resp(r):
        if r.url.endswith("/watch") or r.url.endswith("/ticket"):
            try:
                pg.watch.append(r.json())
            except Exception:  # noqa: BLE001
                pass
    pg.on("response", on_resp)
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def presence_users(pg):
    return {o.get("user") for r in pg.watch for o in (r.get("others") or []) if isinstance(o, dict)}


def test_manager_sees_the_agent_twin_and_no_trace_of_the_owner(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        b = launch(p)
        own = page_for(b, base, pwd, OWNER)                 # the owner is on the ticket and typing
        own.goto(base + "/cs#/b/rozela/t/" + TID)
        own.wait_for_selector(".draft textarea", timeout=30000)
        own.fill(".draft textarea", "בודק משהו")
        twin = page_for(b, base, pwd, TWIN)                 # the agent is on the same ticket and sends
        twin.goto(base + "/cs#/b/rozela/t/" + TID)
        twin.wait_for_selector(".draft textarea", timeout=30000)
        twin.fill(".draft textarea", "היי, ההזמנה בדרך ותגיע עד יום חמישי.")
        twin.click("[data-test=send-btn]"); twin.wait_for_timeout(600); twin.click("[data-test=send-btn]")
        twin.wait_for_timeout(2500)
        twin.goto(base + "/cs#/b/rozela/t/" + TID)          # back on the ticket: the manager will see him there
        twin.wait_for_selector("#ticket-pane .tk-body", timeout=30000)

        mgr = page_for(b, base, pwd, MGR)
        mgr.goto(base + "/cs#/b/rozela/t/" + TID)
        mgr.wait_for_selector("[data-test=tk-presence]:not([hidden])", timeout=15000)
        mgr.wait_for_timeout(6000)                          # at least one more /watch tick while the owner keeps the ticket open
        chip = mgr.inner_text("[data-test=tk-presence]")
        assert TWIN in chip and OWNER not in chip.replace(TWIN, ""), chip
        seen = presence_users(mgr)
        assert TWIN in seen and OWNER not in seen, seen
        assert {MGR, TWIN} <= presence_users(own), presence_users(own)      # the owner still sees who is here

        # the managers' board: a row for the agent, none for the owner
        mgr.goto(base + "/cs#/dash")
        mgr.wait_for_selector("[data-test=dash-agent][data-user='%s']" % TWIN, state="attached", timeout=30000)   # in a folded section
        assert mgr.locator("[data-test=dash-agent][data-user='%s']" % OWNER).count() == 0
        dash = mgr.evaluate("async () => (await fetch('/api/dash')).json()")
        assert OWNER not in [a["user"] for a in dash["agents"]] and OWNER not in (dash.get("senders") or {})

        # the user manager: the owner's card has no sign-in time and no control; the agent's card has both
        mgr.goto(base + "/cs#/users")
        mgr.wait_for_selector(".u-card .hd b.ltr", timeout=20000)
        cards = mgr.evaluate("""() => Array.from(document.querySelectorAll('#users-pane .u-card')).map(c => {
            const n = c.querySelector('.hd b.ltr'); return n ? { u: n.textContent, text: c.innerText, buttons: c.querySelectorAll('button').length } : null; })
            .filter(Boolean)""")
        by = {c["u"]: c for c in cards}
        assert OWNER in by and TWIN in by, list(by)
        assert "כניסה אחרונה: —" in by[OWNER]["text"] and by[OWNER]["buttons"] == 0, by[OWNER]
        assert "כניסה אחרונה: עוד לא נכנס" not in by[TWIN]["text"] and "כניסה אחרונה: —" not in by[TWIN]["text"] and by[TWIN]["buttons"] >= 2, by[TWIN]
        users = mgr.evaluate("async () => (await fetch('/api/manage/users')).json()")["users"]
        o = [u for u in users if u["username"] == OWNER][0]
        assert "last_login" not in o and "updated_at" not in o and o["locked"] is True
        assert [u for u in users if u["username"] == TWIN][0]["last_login"]
        audit = mgr.evaluate("async () => (await fetch('/api/manage/audit')).json()")["lines"]
        assert audit and not [x for x in audit if OWNER in (x.get("actor"), x.get("target"))]

        # the page is bypassed: the server refuses
        res = mgr.evaluate("""async (o) => {
            const csrf = (document.querySelector('meta[name=csrf]') || {}).content;
            const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(b) })
                .then(async r => ({ s: r.status, j: await r.json() }));
            return [await post('/api/manage/users/' + o + '/reset', {}), await post('/api/manage/users/' + o, { disabled: true })]; }""", OWNER)
        for r in res:
            assert r["s"] == 403 and r["j"]["error"] == "owner_protected" and "temp_password" not in r["j"], json.dumps(r, ensure_ascii=False)
        assert not mgr.errors and not own.errors and not twin.errors, (mgr.errors, own.errors, twin.errors)
        b.close()
