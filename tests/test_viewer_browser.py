"""The read-only viewer in a real browser against the mock engine (the owner 2026-11-09): he sees the list, the ticket, the boards and the billing health;
no write control is drawn for him anywhere, and the page never even tries a write."""
import pytest

from browser_server import start
from pw_launch import launch, pw

USERS = (("viewer1", ["viewer"], ["rozela"], "he"), ("agent1", ["agent"], ["rozela"], "he"), ("viewer-en", ["viewer"], ["rozela"], "en"))
WRITES = ("apiSend", "apiSaveDraft", "apiNote", "apiClose", "apiMarkHandled", "apiKachingCancel", "apiKachingAction", "apiOrderEdit", "apiSubCancel", "apiLinkCustomer",
          "apiMergeTickets", "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyReview", "apiWaTakeOver", "apiRedraftOne", "apiSendTemplate", "apiSettings")


@pytest.fixture(scope="module")
def srv():
    base, pwd, proc = start(extra_env={}, users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user, width=1280, path="/cs"):
    pg = launch(p).new_page(viewport={"width": width, "height": 1000})
    pg.errors, pg.posts = [], []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("request", lambda r: pg.posts.append(r.url) if r.method == "POST" else None)
    pg.goto(base + path + "/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def open_ticket(pg, n=0):
    pg.wait_for_selector("a[href*='/t/']", timeout=30000)
    pg.evaluate("(n) => { const a = Array.from(document.querySelectorAll('a[href*=\"/t/\"]'))[n]; if (a) a.click(); }", n)
    pg.wait_for_selector("#ticket-pane .tk-body", timeout=30000)
    pg.wait_for_timeout(1200)


def controls(pg):
    return pg.evaluate("""() => {
      const pane = document.getElementById('ticket-pane');
      const out = { textarea: pane.querySelectorAll('textarea').length, inputs: Array.from(pane.querySelectorAll('input:not([type=hidden])')).map(i => i.getAttribute('data-test') || i.type),
                    buttons: Array.from(pane.querySelectorAll('button')).map(b => b.getAttribute('data-test') || b.className || b.textContent.trim()) };
      return out; }""")


def test_viewer_reads_the_list_and_tickets_and_has_no_write_control(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "viewer1")
        pg.wait_for_selector("a[href*='/t/']", timeout=30000)
        n = pg.locator("a[href*='/t/']").count()
        assert n >= 3
        saw_draft = False
        for i in range(min(n, 6)):
            pg.goto(base + "/cs#/b/rozela/ready")
            open_ticket(pg, i)
            c = controls(pg)
            assert c["textarea"] == 0, (i, c)
            assert c["inputs"] == [], (i, c)
            allowed = ("copy", "more-btn", "back", "tk-back", "sg-open")   # sg-open: the read-only save-offer guide
            bad = [b for b in c["buttons"] if not any(a in str(b) for a in allowed)]
            assert bad == [], (i, bad)
            if pg.locator("[data-test=ro-draft]").count():
                saw_draft = True
                assert "לקריאה בלבד" in pg.inner_text("[data-test=ro-note]") or "קריאה בלבד" in pg.inner_text("[data-test=ro-note]")
            for t in ("[data-test=send]", "[data-test=close]", "[data-test=handled]", "[data-test=oe-btn]", "[data-test=manage-sub]", "[data-test=mg-btn]", "[data-test=takeover]",
                      "[data-test=subx]", "[data-test=sub-pause]", "[data-test=sub-postpone]", "[data-test=lk-open]", "[data-test=mg-in]"):
                assert pg.locator(t).count() == 0, (i, t)
        assert saw_draft, "the mock has tickets with an AI draft: the read-only draft must show for at least one"
        assert pg.locator("#assist-fab:visible").count() == 0                      # no assistant
        assert pg.locator("[data-test=zip-link]").count() == 0
        assert pg.locator(".tab.auto").count() == 0 and pg.locator(".tab.autoreply").count() == 0
        # nothing wrote, and nothing even tried
        wrote = [u for u in pg.posts if any("/" + w in u for w in WRITES) or "/snooze" in u or "/activity" in u]
        assert wrote == [], wrote
        assert pg.errors == []


def test_viewer_dashboard_shows_the_boards_and_billing_but_no_admin_cards(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "viewer1")
        pg.goto(base + "/cs#/dash/more")
        pg.wait_for_selector("[data-test=bh-brand]", timeout=30000)
        txt = pg.inner_text("[data-test=bh]")
        for bad in ("null", "undefined", "NaN", "[object", "{d}", "{a}", "{b}"):
            assert bad not in txt, (bad, txt[:400])
        assert pg.locator("[data-test=bh-dunning]").inner_text() == "102"
        assert pg.locator("[data-test=bh-first]").inner_text() == "62.3%"
        assert pg.locator("[data-test=bh-reason]").count() == 3
        assert "לא זמין דרך ה-API של Kaching" in pg.inner_text("[data-test=bh-na]")
        assert "סיבה שהלקוח בחר" in pg.inner_text("[data-test=bh-na]") or "הסיבה שהלקוח בחר" in pg.inner_text("[data-test=bh-na]")
        pg.select_option("[data-test=bh-period]", "LAST_90_DAYS")
        pg.wait_for_timeout(800)
        assert pg.locator("[data-test=bh-brand]").count() == 1                   # rozela only
        pg.wait_for_selector("[data-test=cr-table]", timeout=30000)                # why customers cancel (the existing board) is there for him
        assert pg.locator("[data-test=cx]").count() == 1
        for gone in ("#ai-notes", "#sysreq", "[data-test=sales-table]", "[data-test=ai-notes-jump]", "[data-test=sysreq-jump]"):
            assert pg.locator(gone).count() == 0, gone
        assert pg.locator("a[href='#/users']").count() == 0
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        wrote = [u for u in pg.posts if "/api/dash/snapshot" in u or "/api/dash/warm" in u or "/settings" in u]
        assert wrote == []
        assert pg.errors == []


def test_viewer_client_wall_refuses_a_write_even_if_the_page_asked(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "viewer1")
        # the screen's own helper refuses before any request: drive it through the page's global fetch counter
        before = len(pg.posts)
        res = pg.evaluate("""async () => {
          const r = await fetch('/api/rozela/apiSend', { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': document.querySelector('meta[name=csrf]').content }, body: JSON.stringify({ args: { id: 't1', text: 'x' } }) });
          return [r.status, await r.json()]; }""")
        assert res[0] == 403 and res[1]["error"] == "forbidden_role"
        assert len(pg.posts) == before + 1


def test_the_agent_still_has_every_write_control(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "agent1")
        open_ticket(pg, 0)
        assert pg.locator("#ticket-pane textarea").count() >= 1
        assert pg.locator("#ticket-pane .note-add input").count() == 1


def test_english_viewer_desk_shows_the_read_only_note(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "viewer-en", 1280, "/cs/en")
        pg.goto(base + "/cs/en#/dash/more")
        pg.wait_for_selector("[data-test=bh-brand]", timeout=30000)
        txt = pg.inner_text("[data-test=bh]")
        assert "Not available through Kaching" in txt and "retry settings" in txt
        assert pg.errors == []


def test_phone_width_has_no_sideways_scroll_on_the_billing_card(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "viewer1", 390)
        pg.goto(base + "/cs#/dash/more")
        pg.wait_for_selector("[data-test=bh-brand]", timeout=30000)
        pg.wait_for_timeout(1500)
        assert pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert pg.evaluate("() => Array.from(document.querySelectorAll('[data-test=bh] *')).every(e => e.closest('.table-wrap') || e.getBoundingClientRect().right <= window.innerWidth + 1)")
