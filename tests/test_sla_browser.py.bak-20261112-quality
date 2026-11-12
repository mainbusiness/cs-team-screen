"""SLA in a real browser against the mock engine (Owner, 2026-10-24): the manager's banner (business hours only), the board section, the
agents' in-ticket guidance. SLA_CONFIG makes every hour a business hour so the test does not depend on the clock it runs at."""
import json

import pytest

from browser_server import start
from pw_launch import launch, pw

USERS = (("guy", ["admin"], ["rozela", "celesta", "apexmen"], "he"), ("agent-two", ["agent"], ["rozela", "celesta"], "he"),
         ("amit", ["agent"], ["rozela"], "en"), ("dan", ["user-manager"], ["rozela", "celesta"], "he"))
ALWAYS = json.dumps({"hours": {str(i): [0, 24] for i in range(7)}})
NEVER = json.dumps({"hours": {}})


def boot(cfg):
    return start(extra_env={"SLA_CONFIG": cfg}, users=USERS)


@pytest.fixture
def srv():
    base, pwd, proc = boot(ALWAYS)
    yield base, pwd
    proc.terminate()


@pytest.fixture
def srv_closed():
    base, pwd, proc = boot(NEVER)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user, width=1280, path="/cs"):
    pg = launch(p).new_page(viewport={"width": width, "height": 1000})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.goto(base + path + "/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.goto(base + path)                      # a Hebrew-profile user is sent to /cs after login; the English desk is asked for explicitly
    pg.wait_for_load_state("networkidle")
    return pg


def no_junk(txt):
    for bad in ("null", "undefined", "NaN", "[object", "{b}", "{k}", "{f}", "{o}", "{n}"):
        assert bad not in txt, (bad, txt[:300])


@pytest.mark.parametrize("width,path", [(1280, "/cs"), (390, "/cs"), (1280, "/cs/en"), (390, "/cs/en")])
def test_manager_gets_banner_then_board_section(srv, width, path):
    base, pwd = srv
    user = "guy"
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user, width, path)
        pg.wait_for_selector("[data-test=sla-banner]", timeout=20000)
        b = pg.locator("[data-test=sla-banner]")
        no_junk(b.inner_text())
        box = b.bounding_box()
        assert box and box["width"] > 0 and box["height"] > 0
        assert b.get_attribute("data-level") in ("breach", "risk")
        # the banner button is a real link to the board and really sits on top (nothing covers it)
        btn = pg.locator("[data-test=sla-banner-go]")
        assert pg.evaluate("(el) => { const r = el.getBoundingClientRect(); const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return el.contains(t) || t === el; }", btn.element_handle())
        btn.click()
        pg.wait_for_selector("[data-test=sla]", timeout=20000)
        pg.wait_for_selector("[data-test=sla-brand][data-brand=rozela]", timeout=20000)
        assert pg.locator("[data-test=sla-banner]").count() == 0                       # the board shows the section instead
        sec = pg.locator("[data-test=sla]")
        txt = sec.inner_text()
        no_junk(txt)
        assert pg.locator("[data-test=sla-brand]").count() >= 2 and pg.locator("[data-test=sla-total]").count() == 1
        assert pg.locator("[data-test=sla-dayline]").inner_text().strip()
        order = pg.evaluate("() => { const a = document.querySelector('[data-test=dash-live]'), b = document.querySelector('[data-test=sla]');"
                            " return !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING); }")
        assert order
        if path == "/cs":
            assert "זמני מענה" in txt and "שעות עבודה" in txt
        else:
            assert "response times" in txt and "business" in txt
        # the section is built once: a second board refresh must not replace the node
        pg.evaluate("() => { window.__sla = document.querySelector('[data-test=sla]'); }")
        pg.wait_for_timeout(1500)
        assert pg.evaluate("() => window.__sla === document.querySelector('[data-test=sla]') && document.body.contains(window.__sla)")
        # a link in the alert table opens its ticket
        if pg.locator("[data-test=sla-alert]").count():
            href = pg.locator("[data-test=sla-alert] a").first.get_attribute("href")
            assert href.startswith("#/b/") and "/t/" in href
        assert pg.errors == []


def test_banner_stays_silent_outside_business_hours(srv_closed):
    base, pwd = srv_closed
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy")
        pg.wait_for_timeout(2500)
        assert pg.locator("[data-test=sla-banner]").count() == 0
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=sla-brand]", timeout=20000)
        assert pg.locator("[data-test=sla-off]").count() == 1                         # the board still says why there is no alarm
        assert pg.errors == []


def test_agent_has_no_banner_no_endpoint_but_gets_the_playbooks(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent-two")
        pg.wait_for_selector("#list-pane .row", timeout=20000)
        pg.wait_for_timeout(1500)
        assert pg.locator("[data-test=sla-banner]").count() == 0
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")                                    # a plain shipping ticket
        pg.wait_for_selector("[data-test=playbooks]", timeout=20000)
        pb = pg.locator("[data-test=playbooks]")
        assert pb.get_attribute("open") is None and pb.get_attribute("data-cancel") is None
        pb.locator("summary").click()
        txt = pb.inner_text()
        no_junk(txt)
        for need in ("לא קיבלתי", "לא זיהיתי את החיוב", "ניסיתי לבטל", "המוצר לא עבד", "https://tryrozela.com/pages/track", "מנהל השירות"):
            assert need in txt, need
        assert pb.locator("[data-test=pb-retention]").count() == 1 and "מה גרם לך לרצות לבטל" in txt
        assert "המנהל" not in txt and "גיא" not in txt                               # escalation names the manager's role, never Guy
        assert pg.errors == []
        assert pg.evaluate("async () => (await fetch('/api/dash/sla')).status") == 403           # last: this deliberate 403 is a console line


def test_cancel_ticket_opens_the_retention_card_first(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent-two")
        pg.wait_for_selector("#list-pane .row", timeout=20000)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a03")                                    # category cancel_subscription
        pg.wait_for_selector("[data-test=playbooks][data-cancel='1']", timeout=20000)
        pb = pg.locator("[data-test=playbooks]")
        assert pb.get_attribute("open") is not None
        assert pb.locator("[data-test=pb-retention]").is_visible()
        first = pb.locator(".pb-item").first.get_attribute("data-test")
        assert first == "pb-retention"
        assert pg.locator("[data-test=subx]").count() == 1                            # the cancel button slot is still there
        assert pg.errors == []


def test_english_desk_gets_english_playbooks(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "amit", 1280, "/cs/en")
        pg.wait_for_selector("#list-pane .row", timeout=20000)
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a01")
        pg.wait_for_selector("[data-test=playbooks]", timeout=20000)
        pg.locator("[data-test=playbooks] summary").click()
        txt = pg.locator("[data-test=playbooks]").inner_text()
        assert "Quick handling guide" in txt and "I do not recognize the charge" in txt and "the CS manager" in txt
        no_junk(txt)


def test_true_first_reply_from_conversations_is_shown_beside_the_row_based_numbers(srv):
    """The board's dayStats number (the real first reply by a person) is drawn inside the brand card, today only, and a day without it draws nothing."""
    base, pwd = srv

    def patch(route):
        r = route.fetch()
        j = r.json()
        for b, (s, n) in {"rozela": (780.0, 12), "celesta": (5400.0, 3)}.items():
            if b in j.get("brands", {}):
                j["brands"][b].update(frt_human_known=True, frt_human_s=s, frt_human_n={"all": n, "email": n, "whatsapp": 0}, frt_human_wa_s=None, frt_human_email_s=s)
        route.fulfill(response=r, json=j)
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy")
        pg.route("**/api/dash?*", patch)
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=sla-brand][data-brand=rozela] [data-test=sla-conv]", timeout=30000)
        txt = pg.locator("[data-test=sla-brand][data-brand=rozela] [data-test=sla-conv]").inner_text()
        assert "13 דק׳" in txt and "מדגם 12" in txt and "מייל 13 דק׳" in txt
        assert "1.5 ש׳" in pg.locator("[data-test=sla-brand][data-brand=celesta] [data-test=sla-conv]").inner_text()
        assert pg.locator("[data-test=sla-brand][data-brand=apexmen] [data-test=sla-conv]").count() == 0
        no_junk(pg.inner_text("[data-test=sla]"))
        assert pg.errors == []
