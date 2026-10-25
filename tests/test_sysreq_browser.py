"""Owner, 2026-10-25 — the CS manager proposes changes to the SYSTEM itself, the owner approves in HQ. Real browser, mock engines:
 - the card is on the managers' board right under the AI-notes card, admins only; an agent never sees it and the API answers 403;
 - send is disabled until 10 characters; a send says "נשלח לגיא לאישור", empties the box and lists the request as waiting;
 - an unsent draft survives a reload; the owner's decision (machine API) comes back as a status chip + his reply;
 - a request done / rejected more than 14 days ago is in the collapsed archive line, not in the list;
 - English desk strings; no horizontal overflow at 390 / 768 / 1280; no console errors.
"""
import json
import os
import tempfile
import time
import urllib.request

import pytest

import browser_server
import sysreq
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
SECRET = "k" * 48                       # browser_server's TOKEN_SECRET
SHOTS = os.environ.get("SYSREQ_SHOTS_DIR")


@pytest.fixture(scope="module")
def server():
    d = tempfile.mkdtemp(prefix="cs-sysreq-")
    path = os.path.join(d, "system-requests.json")
    base, pwd, proc = browser_server.start(extra_env={"SYSREQ_PATH": path},
                                           users=(("admin1", ["admin", "user-manager"], ALL, "he"), ("admin2", ["admin"], ALL, "en"),
                                                  ("agent1", ["agent"], ["rozela"], "he"), ("um1", ["user-manager"], ALL, "he")))
    yield base, pwd, path
    proc.terminate()
    proc.wait(timeout=10)


def until(cond, ms=8000):
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def login(p, base, pwd, user, width=1280, en=False):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(base + ("/cs/en/login" if en else "/cs/login"))
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return browser, pg, errors


def open_board(pg, base, en=False):
    pg.goto(base + ("/cs/en#/dash" if en else "/cs#/dash"))
    pg.wait_for_selector("[data-test=sysreq]")
    pg.wait_for_selector("[data-test=sysreq-list] :is([data-test=sysreq-none],[data-test=sysreq-item],[data-test=sysreq-archive])")


def hq_decide(base, rid_id, status, reply):
    req = urllib.request.Request(base + "/hq/sysreq/%d" % rid_id, method="POST", data=json.dumps({"status": status, "reply": reply}).encode(),
                                 headers={"Content-Type": "application/json", "X-HQ-Token": sysreq.mint_token(SECRET)})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_manager_sends_a_request_and_sees_guys_answer(server):
    base, pwd, path = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "admin1")
        open_board(pg, base)
        card = pg.locator("[data-test=sysreq]")
        assert "🛠️ הצעות לשיפור המערכת" in card.locator("h3").inner_text()
        help_ = card.locator("[data-test=sysreq-help]").inner_text()
        assert "לאישור" in help_ and "ההערות ל-AI" in help_
        # right under the AI-notes card, in the managers' area
        order = pg.evaluate("() => { const a = document.getElementById('ai-notes'), s = document.getElementById('sysreq');"
                            " return !!(a && s && (a.compareDocumentPosition(s) & Node.DOCUMENT_POSITION_FOLLOWING)); }")
        assert order, "the card follows the AI-notes card"
        assert pg.locator("[data-test=sysreq-jump]").is_visible()
        assert card.locator("[data-test=sysreq-none]").inner_text() == "עוד לא נשלחו בקשות."
        send = card.locator("[data-test=sysreq-send]")
        assert send.is_disabled()
        card.locator("[data-test=sysreq-text-input]").fill("קצר")
        assert send.is_disabled() and "עוד 7 תווים" in card.locator("[data-test=sysreq-count]").inner_text()
        text = "אחרי סגירת פנייה בוואטסאפ המסך חוזר לראש הרשימה — שיעבור לפנייה שמעל"
        card.locator("[data-test=sysreq-text-input]").fill(text)
        card.locator("[data-test=sysreq-brand]").select_option("rozela")
        card.locator("[data-test=sysreq-ticket]").fill("1646")
        assert send.is_enabled()
        send.click()
        assert until(lambda: card.locator("[data-test=sysreq-status]").inner_text() == "נשלח לגיא לאישור ✓")
        assert card.locator("[data-test=sysreq-text-input]").input_value() == ""
        item = card.locator("[data-test=sysreq-item]")
        assert until(lambda: item.count() == 1)
        assert item.locator("[data-test=sysreq-chip]").inner_text() == "⏳ ממתין לגיא"
        assert item.locator("[data-test=sysreq-text]").inner_text() == text
        meta = item.locator("[data-test=sysreq-meta]").inner_text()
        assert "Rozela" in meta and "פנייה 1646" in meta and "admin1" in meta
        rid_id = int(item.get_attribute("data-id"))
        stored = json.load(open(path))["items"][str(rid_id)]
        assert stored["status"] == "pending" and stored["user"] == "admin1" and stored["brand"] == "rozela"
        # an unsent draft survives a reload
        card.locator("[data-test=sysreq-text-input]").fill("טיוטה שלא נשלחה ושורדת רענון של הדף")
        pg.reload()
        open_board(pg, base)
        assert pg.locator("[data-test=sysreq-text-input]").input_value() == "טיוטה שלא נשלחה ושורדת רענון של הדף"
        assert "שוחזרה טיוטה" in pg.locator("[data-test=sysreq-status]").inner_text()
        # the owner decides in HQ -> the board shows it
        assert hq_decide(base, rid_id, "approved", "מאשר, נבנה מחר")["ok"]
        pg.reload()
        open_board(pg, base)
        item = pg.locator("[data-test=sysreq-item][data-id='%d']" % rid_id)
        assert item.locator("[data-test=sysreq-chip]").inner_text() == "✅ אושר"
        assert item.locator("[data-test=sysreq-reply]").inner_text() == "תשובת גיא: מאשר, נבנה מחר"
        for w in (390, 768, 1280):
            pg.set_viewport_size({"width": w, "height": 900})
            pg.wait_for_timeout(250)
            assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth"), "overflow at %d" % w
            if SHOTS:
                pg.locator("[data-test=sysreq]").screenshot(path=os.path.join(SHOTS, "sysreq_%d.png" % w))
        assert not [e for e in errors if "favicon" not in e], errors
        browser.close()


def test_old_decided_requests_go_to_the_collapsed_archive(server):
    base, pwd, path = server
    st = sysreq.SysReqStore(path)
    rec, _ = st.create("admin1", "all", "", "בקשה ישנה שכבר בוצעה מזמן ולא צריכה להיות ברשימה", "9" * 32)
    st.decide(rec["id"], "done", "בוצע")
    d = json.load(open(path))
    d["items"][str(rec["id"])]["updated_at"] = time.time() - 20 * 86400
    json.dump(d, open(path, "w"))
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "admin1")
        open_board(pg, base)
        assert pg.locator("[data-test=sysreq-item][data-id='%d']" % rec["id"]).count() == 0
        arch = pg.locator("[data-test=sysreq-archive]")
        assert arch.get_attribute("open") is None
        assert "(1)" in arch.locator("summary").inner_text()
        arch.locator("summary").click()
        assert "🔧 בוצע · #%d" % rec["id"] in arch.locator("[data-test=sysreq-arch-row]").inner_text()
        browser.close()


@pytest.mark.parametrize("user", ["agent1", "um1"])
def test_agent_and_user_manager_never_see_it(server, user):
    base, pwd, _ = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, user)
        pg.goto(base + "/cs#/dash")
        pg.wait_for_timeout(1500)
        assert pg.locator("[data-test=sysreq]").count() == 0
        assert pg.locator("[data-test=sysreq-jump]").count() == 0
        assert pg.request.get(base + "/api/sysreq").status == 403
        browser.close()


def test_english_desk(server):
    base, pwd, _ = server
    with pw.sync_playwright() as p:
        browser, pg, errors = login(p, base, pwd, "admin2", width=390, en=True)
        open_board(pg, base, en=True)
        card = pg.locator("[data-test=sysreq]")
        assert "System change requests" in card.locator("h3").inner_text()
        assert "approval" in card.locator("[data-test=sysreq-help]").inner_text()
        assert card.locator("[data-test=sysreq-send]").inner_text() == "Send to Guy"
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
