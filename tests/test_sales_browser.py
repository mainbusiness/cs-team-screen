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


def test_hebrew_desk_agent_logs_a_sale_and_sees_it_in_his_list(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent-two")
        pg.goto(base + "/cs#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=sale-btn]")
        assert "מכירה" in pg.inner_text("[data-test=sale-btn]")
        pg.click("[data-test=sale-btn]")
        pg.wait_for_selector("[data-test=sale-order]")
        rows = pg.locator("[data-test=sale-order]")
        assert rows.count() == 3
        assert "אחרי השיחה" in pg.inner_text("[data-test=sale-order][data-order='#4601']")
        assert "לפני השיחה" in pg.inner_text("[data-test=sale-order][data-order='#4599']")
        assert "בוטלה" in pg.inner_text("[data-test=sale-order][data-order='#4602']")
        assert "72 שעות" in pg.inner_text("[data-test=sale-rules]")                     # the default is stated in the screen
        # 2026-10-14 ("ממלא לך אוטומטית"): the one order after the chat, not cancelled, not credited, is already chosen: one click to confirm
        assert pg.locator("[data-test=sale-order][data-order='#4601'] input").is_checked()
        assert not pg.locator("[data-test=sale-order][data-order='#4602'] input").is_checked()
        assert pg.is_enabled("[data-test=sale-go]")
        pg.fill("[data-test=sale-note]", "ענתה לשאלה על חבילת 3 חודשים")
        pg.click("[data-test=sale-go]")
        pg.wait_for_selector("[data-test=sale-done]")
        assert pg.get_attribute("[data-test=sale-done] [data-test=sale-status]", "data-status") == "verified"
        assert "299.8" in pg.inner_text("[data-test=sale-done]")
        pg.click("[data-test=sale-close]")
        # the ticket now carries a chip for the sale; the list opens from it and from the top bar
        pg.wait_for_selector("[data-test=sale-chip]")
        assert "#4601" in pg.inner_text("[data-test=sale-chip]")
        pg.click("[data-test=sales-mine-link]")
        pg.wait_for_selector("[data-test=sale-mine-row]")
        texts = [pg.locator("[data-test=sale-mine-row]").nth(i).inner_text() for i in range(pg.locator("[data-test=sale-mine-row]").count())]
        assert any("#4601" in t and "מאומת" in t for t in texts)
        assert "מכירות" in pg.inner_text("[data-test=sale-mine-sum]") or "2" in pg.inner_text("[data-test=sale-mine-sum]")
        # a reload still shows the chip (the list is the server's, not the page's)
        pg.keyboard.press("Escape")
        pg.reload()
        pg.wait_for_selector("[data-test=sale-chip]")
        assert not pg.errors, pg.errors


def test_english_desk_second_claim_is_refused_and_a_review_sale_says_why(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        # agent-two logs #4601 first (through the page), then amit on the English desk tries the same order
        a = login(p, base, pwd, "agent-two")
        a.goto(base + "/cs#/b/rozela/t/" + TICKET)
        a.wait_for_selector("[data-test=sale-btn]")
        a.click("[data-test=sale-btn]")
        a.wait_for_selector("[data-test=sale-order]")
        a.locator("[data-test=sale-order][data-order='#4601'] input").check()
        a.click("[data-test=sale-go]")
        a.wait_for_selector("[data-test=sale-done]")
        b = login(p, base, pwd, "amit")
        b.goto(base + "/cs/en#/b/rozela/t/" + TICKET)
        b.wait_for_selector("[data-test=sale-btn]")
        assert "Sale" in b.inner_text("[data-test=sale-btn]")
        b.click("[data-test=sale-btn]")
        b.wait_for_selector("[data-test=sale-order]")
        assert "already credited to agent-two" in b.inner_text("[data-test=sale-order][data-order='#4601']")
        assert b.locator("[data-test=sale-order][data-order='#4601'] input").is_disabled()
        # nothing left to fill in by itself (the only order after the chat is credited, one is cancelled, one is before): typing is ready
        assert b.locator("input[name=sale-order]:checked").count() == 0 and b.is_disabled("[data-test=sale-go]")
        assert b.evaluate("document.activeElement && document.activeElement.getAttribute('data-test')") == "sale-typed"
        b.fill("[data-test=sale-typed]", "4601")                                        # typed by hand: the engine refuses, naming who holds it
        b.click("[data-test=sale-go]")
        b.wait_for_selector("[data-test=sale-err]")
        assert "already credited to agent-two" in b.inner_text("[data-test=sale-err]").replace("\u2068", "").replace("\u2069", "")
        b.fill("[data-test=sale-typed]", "4599")                                        # created BEFORE the answer: logged, but for review, with the reason
        b.click("[data-test=sale-go]")
        b.wait_for_selector("[data-test=sale-done]")
        assert b.get_attribute("[data-test=sale-done] [data-test=sale-status]", "data-status") == "review"
        assert "before the first agent reply" in b.inner_text("[data-test=sale-reasons]")
        assert "Guy" in b.inner_text("[data-test=sale-done]")
        assert not b.errors, b.errors


def test_phone_width_dialog_fits(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent-two", width=390)
        pg.goto(base + "/cs#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=sale-btn]")
        pg.click("[data-test=sale-btn]")
        pg.wait_for_selector("[data-test=sale-order]")
        box = pg.locator("#sale-dlg").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 391
        assert pg.evaluate("document.documentElement.scrollWidth") <= 391


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


@pytest.mark.parametrize("user,path", [("agent-two", "/cs"), ("amit", "/cs/en")])
def test_several_orders_after_the_chat_the_newest_eligible_one_is_chosen_on_both_desks(srv, user, path):
    """2026-10-14: with several orders after the chat, the NEWEST that is not cancelled and not credited to anyone is chosen; never one before the chat."""
    import json
    from datetime import datetime, timedelta, timezone
    base, pwd = srv
    iso = lambda h: (datetime.now(timezone.utc) - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")
    o = lambda name, h, **kw: dict({"id": "gid://shopify/Order/9" + name[1:], "name": name, "createdAt": iso(h), "amount": 100.0, "currency": "ILS",
                                    "cancelled": False, "items": "Rozela", "financial": "PAID", "after_reply": True, "credited": None}, **kw)
    orders = [o("#5001", 40), o("#5002", 5), o("#5003", 1, cancelled=True), o("#5004", 2, credited={"agent": "dana", "effective": "verified"}),
              o("#5005", 0.5, after_reply=False)]

    def fake(route):
        r = route.fetch()
        body = r.json()
        body["orders"] = orders
        body["lookup"] = "ok"
        route.fulfill(response=r, body=json.dumps(body), headers=dict(r.headers, **{"content-type": "application/json"}))
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, user)
        pg.route("**/api/rozela/apiSaleCandidates", fake)
        pg.goto(base + path + "#/b/rozela/t/" + TICKET)
        pg.wait_for_selector("[data-test=sale-btn]")
        pg.click("[data-test=sale-btn]")
        pg.wait_for_selector("[data-test=sale-order][data-order='#5002']")
        checked = [pg.locator("input[name=sale-order]:checked").nth(i).get_attribute("value") for i in range(pg.locator("input[name=sale-order]:checked").count())]
        assert checked == ["#5002"], checked
        assert pg.is_enabled("[data-test=sale-go]")
        assert not pg.errors, pg.errors
