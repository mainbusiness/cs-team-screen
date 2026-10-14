"""Sales log for bonuses (Owner, 2026-10-14), real browser against the mock engine: the "מכירה" button on both desks, the one-order-once refusal,
the agent's own list, and the managers' table (filters, proof, approve / reject, per-agent summary, sales nobody logged)."""
import pytest

from browser_server import start
from pw_launch import launch, pw

TICKET = "t18f2s01"      # rozela, closed pre-sale chat: customer asked, agent-two answered; orders #4601 (after), #4599 (before), #4602 (cancelled)


@pytest.fixture
def srv():
    base, pwd, proc = start(users=(("agent-two", ["agent"], ["rozela", "celesta"], "he"), ("amit", ["agent"], ["rozela"], "en"),
                                   ("guy", ["admin"], ["rozela", "celesta"], "he")))
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user, width=1280):
    pg = launch(p).new_page(viewport={"width": width, "height": 1000})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.errors = errors
    return pg


@pytest.mark.parametrize("user,path,width", [("agent-two", "/cs", 1280), ("amit", "/cs/en", 1280), ("agent-two", "/cs", 390), ("guy", "/cs", 1280)])
def test_no_sales_anywhere_outside_the_managers_board(srv, user, path, width):
    """Owner, 2026-10-14: "שלא יהיה את החלק של המכירות בממשק ... רק אני אוכל לראות את המכירות בטבלת מנהלים". No sale button, no sale chips, no
    "my sales" in the top bar or the menu — for agents on both desks, and for the admin too outside #/dash."""
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user, width)
        pg.goto(base + path + "#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=draft-card], [data-test=en-draft]")
        pg.wait_for_timeout(800)
        for sel in ("[data-test=sale-btn]", "[data-test=sale-bar]", "[data-test=sale-chip]", "[data-test=sales-mine-link]", "[data-test=sales-mine-menu]", "#sale-dlg[open]"):
            assert pg.locator(sel).count() == 0, (user, sel)
        if pg.locator(".menu-btn").count():
            pg.click(".menu-btn")
            pg.wait_for_timeout(200)
            assert pg.locator("[data-test=sales-mine-menu]").count() == 0
        assert not pg.errors, pg.errors


@pytest.mark.parametrize("user,path", [("agent-two", "/cs"), ("amit", "/cs/en")])
def test_an_agent_calling_the_sales_api_directly_is_refused(srv, user, path):
    """Enforced on the server too, not only hidden: every sales call from an agent's session is refused before the engine (and the engine refuses it)."""
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user)
        pg.goto(base + path + "#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=draft-card], [data-test=en-draft]")
        csrf = pg.evaluate("() => (document.querySelector('meta[name=csrf]') || {}).content || ''")
        for fn, args in (("apiSaleLog", {"id": TICKET, "orderNo": "#4601"}), ("apiSaleMine", {}), ("apiSaleCandidates", {"id": TICKET}),
                         ("apiSaleProof", {"id": "o4601"}), ("apiSaleList", {})):
            r = pg.request.post(base + "/api/rozela/" + fn, data={"args": args}, headers={"X-CSRF-Token": csrf, "Origin": base})
            assert r.status == 403 and r.json()["error"] == "forbidden_role", (fn, r.status, r.text()[:200])


def test_managers_table_filters_proof_decisions_summary_and_unlogged_sales(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy")
        pg.goto(base + "/cs#/dash")
        pg.wait_for_selector("[data-test=sales-title]")
        pg.wait_for_selector("[data-test=sale-row]")
        assert pg.locator("[data-test=sale-row]").count() == 3                          # 2 rozela + 1 celesta, this month
        assert "72 שעות" in pg.inner_text("[data-test=sales-defaults]")
        # filters
        pg.select_option("[data-test=f-status]", "review")
        assert pg.locator("[data-test=sale-row]").count() == 1
        assert "נציג אחר (agent-two) ענה אחרון" in pg.inner_text("[data-test=sale-row]")
        pg.select_option("[data-test=f-status]", "all")
        pg.select_option("[data-test=f-brand]", "celesta")
        assert pg.locator("[data-test=sale-row]").count() == 1
        pg.select_option("[data-test=f-brand]", "all")
        pg.select_option("[data-test=f-agent]", "agent-two")
        assert pg.locator("[data-test=sale-row]").count() == 2
        pg.select_option("[data-test=f-agent]", "all")
        # the proof: the frozen conversation, expandable
        row = pg.locator("[data-test=sale-row][data-status=review]")
        row.locator("[data-test=sale-conv]").click()
        pg.wait_for_selector("[data-test=sale-proof] .pm")
        assert "חבילת 3 חודשים" in pg.inner_text("[data-test=sale-proof]")
        assert "העתק קפוא" in pg.inner_text("[data-test=sale-proof]")
        assert row.locator("a[data-test=sale-ticket]").get_attribute("href").endswith("/t/t18f2c01")
        assert "#4591" in row.inner_text()
        # approve the review sale: it becomes approved and counts in amit's month
        row.locator("[data-test=sale-approve]").click()
        pg.wait_for_selector("[data-test=sale-row][data-id=o4591][data-status=approved]")
        pg.wait_for_function("document.querySelector('[data-test=sum-row][data-agent=amit]') && document.querySelector('[data-test=sum-row][data-agent=amit]').innerText.includes('299')")
        # reject one with a reason
        r2 = pg.locator("[data-test=sale-row][data-id=o4590]")
        r2.locator("[data-test=sale-reject]").click()
        pg.fill("[data-test=sale-reject-note]", "לא קשור לשיחה")
        pg.click("[data-test=sale-reject-go]")
        pg.wait_for_selector("[data-test=sale-row][data-id=o4590][data-status=rejected]")
        assert "לא קשור לשיחה" in pg.inner_text("[data-test=sale-row][data-id=o4590]")
        # per-agent summary: agent-two's rejected sale is out of the count
        agent-two = pg.locator("[data-test=sum-row][data-agent=agent-two]").first
        assert "1" in agent-two.inner_text()
        # sales nobody logged: credit one with a click; the one without an agent needs the manager to pick
        assert pg.locator("[data-test=sug-row]").count() == 2
        pg.locator("[data-test=sug-row][data-id=o4610] [data-test=sug-credit]").click()
        pg.wait_for_selector("[data-test=sale-row][data-id=o4610][data-status=approved]")
        assert "זוהתה" in pg.inner_text("[data-test=sale-row][data-id=o4610]")
        pg.locator("[data-test=sug-row][data-id=o4611] [data-test=sug-credit]").click()
        pg.wait_for_function("document.body.innerText.includes('לא זוהה נציג')")
        pg.select_option("[data-test=sug-row][data-id=o4611] [data-test=sug-agent]", "amit")
        pg.locator("[data-test=sug-row][data-id=o4611] [data-test=sug-credit]").click()
        pg.wait_for_selector("[data-test=sale-row][data-id=o4611]")
        assert pg.locator("[data-test=sug-row]").count() == 0
        assert "אין כרגע מכירות שלא נרשמו" in pg.inner_text("[data-test=sug-empty]")
        assert not pg.errors, pg.errors


def test_an_agent_never_gets_the_managers_table(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent-two")
        for fn in ("apiSaleList", "apiSaleDecide", "apiSaleSuggestions", "apiSaleSuggestCredit", "apiSaleScan"):
            st = pg.evaluate("""async (fn) => {
              const csrf = document.querySelector('meta[name=csrf]').content;
              const r = await fetch('/api/rozela/' + fn, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({args: {id: 'o4591', decision: 'approved'}})});
              return r.status; }""", fn)
            assert st == 403, fn
