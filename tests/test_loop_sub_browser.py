"""Owner, 2026-11-20 (rozela moved its subscriptions to Loop): the agents can CANCEL again (always behind the "בטוח/ה?" dialog with the save-advice
card) and PAUSE (2 / 4 / 6 / 8 weeks) / resume a Loop subscription from the send area. Mock engine + real browser, both desks, 1280 + 390.
Kaching writes are OFF in every test here (the app that is being replaced); Loop has its own switch."""
import json
import re

import pytest

from browser_server import start
from pw_launch import launch, pw
from test_sub_cancel_button_browser import _login, _no_sideways, _with_advice, TRY_SAVE, YOSSI, RONIT

LOOP_ON = {"writes": False, "loop": True}


def _srv(switches):
    return start(extra_env={"MOCK_SWITCHES": json.dumps({"rozela": switches})}, users=(("agent1", ["agent"], ["rozela"], "he"), ("agent-en", ["agent"], ["rozela"], "en")))


@pytest.fixture()
def srv():
    base, pwd, proc = _srv(LOOP_ON)
    yield base, pwd
    proc.terminate()


def _spy(pg, fn):
    """Records every request of one engine fn (and lets it through to the mock engine)."""
    sent = []

    def catch(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.continue_()
    pg.route("**/api/rozela/" + fn, catch)
    return sent


def _abort(pg, fn):
    sent = []

    def catch(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.abort()
    pg.route("**/api/rozela/" + fn, catch)
    return sent


def _loop_option(pg):
    return pg.locator("[data-test=subx-opt]", has_text="Loop") if False else pg.locator("[data-test=subx-opt]").filter(has=pg.locator("bdi", has_text=re.compile(r"^\d{8}$")))


@pytest.mark.parametrize("width", [1280, 390])
def test_cancel_dialog_lists_the_loop_subscription_with_the_warning_card_first_and_cancels_it_only_on_the_click(srv, width):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=width)
        pg.route("**/api/rozela/apiSubCancelPreview", _with_advice(TRY_SAVE))
        sent = _spy(pg, "apiSubCancel")
        pg.goto(base + YOSSI)
        btn = pg.locator("[data-test=draft-card] [data-test=subx-btn]")
        btn.wait_for()
        assert btn.is_enabled(), "Loop cancels are on: the button is on although Kaching is off"
        assert pg.locator("[data-test=subx-why]").count() == 0
        btn.click()
        pg.locator("[data-test=subx-opt]").nth(1).wait_for()
        dlg = pg.locator("#subx-dlg")
        card = dlg.locator("[data-test=subx-adv]")
        assert card.count() == 1 and card.get_attribute("data-verdict") == "try_save", "the warning card is in the dialog before any Loop cancel"
        assert "לפני שמבטלים" in card.inner_text()
        k = pg.locator("[data-test=subx-opt]", has_text="0123")
        assert k.get_attribute("data-off") == "1" and k.locator("input").is_disabled(), "the Kaching one stays off"
        lp = pg.locator("[data-test=subx-opt]", has_text="פורמולת הסלק של רוזלה")
        assert lp.get_attribute("data-off") is None and lp.locator("input").is_enabled()
        assert re.search(r"\d{8}", lp.inner_text()) and "loop-" not in lp.inner_text(), lp.inner_text()
        assert "כל 3 חודשים" in lp.inner_text(), lp.inner_text()
        assert "null" not in dlg.inner_text() and "undefined" not in dlg.inner_text() and "object" not in dlg.inner_text().lower()
        go = pg.locator("[data-test=subx-go]")
        assert go.is_disabled() and go.inner_text() == "לבטל בכל זאת" and card.bounding_box()["y"] < go.bounding_box()["y"]
        assert _no_sideways(pg) == {"page": True, "dlg": True}
        lp.click()
        pg.wait_for_timeout(200)
        assert sent == [], "opening and picking cancels nothing"
        go.click()
        ok = pg.locator("[data-test=subx-ok]")
        ok.wait_for()
        assert re.search(r"המנוי בוטל — אומת \d{1,2}:\d{2}", ok.inner_text())
        assert len(sent) == 1 and re.match(r"^loop-\d{8}$", sent[0]["args"]["contractId"]), sent
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()


def test_loop_switch_off_keeps_the_loop_subscription_listed_but_not_pickable(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)

        def off(route):
            r = route.fetch()
            j = r.json()
            j["loopWrites"] = False
            route.fulfill(response=r, body=json.dumps(j))
        pg.route("**/api/rozela/apiSubCancelPreview", off)
        sent = _abort(pg, "apiSubCancel")
        pg.goto(base + YOSSI)
        pg.click("[data-test=subx-btn]")
        pg.locator("[data-test=subx-opt]").nth(1).wait_for()
        lp = pg.locator("[data-test=subx-opt]", has_text="פורמולת הסלק של רוזלה")
        assert lp.get_attribute("data-off") == "1" and "Loop כבויים" in lp.inner_text()
        assert pg.is_disabled("[data-test=subx-go]")
        assert sent == []
        browser.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_pause_a_loop_subscription_dated_verified_and_stays_on_the_ticket(srv, width):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=width)
        sent = _spy(pg, "apiSubPause")
        pg.goto(base + RONIT)                                                  # NOT a cancel request: the pause is a save tool, always there
        assert pg.locator("[data-test=draft-card] [data-test=subx-btn]").count() == 0
        btn = pg.locator("[data-test=draft-card] [data-test=subp-btn]")
        btn.wait_for()
        assert btn.inner_text() == "להשהות את המנוי" and btn.is_enabled()
        btn.click()
        pg.locator("[data-test=subp-q]").wait_for()
        dlg = pg.locator("#subx-dlg")
        assert "רונית אברהם" in pg.inner_text("[data-test=subp-q]") and "פורמולת הסלק של רוזלה" in dlg.inner_text()
        assert pg.locator("[data-test=subp-w]").count() == 4
        assert [pg.locator("[data-test=subp-w]").nth(i).inner_text() for i in range(4)] == ["שבועיים", "4 שבועות", "6 שבועות", "8 שבועות"]
        assert not any(pg.locator("[data-test=subp-w] input").nth(i).is_checked() for i in range(4)), "no preselected duration: never a default pause"
        go = pg.locator("[data-test=subp-go]")
        assert go.is_disabled(), "no duration, no pause"
        assert pg.locator("[data-test=subp-paused]").is_hidden()
        assert _no_sideways(pg) == {"page": True, "dlg": True}
        pg.locator("[data-test=subp-w]").nth(1).click()
        assert go.is_enabled()
        go.click()
        ok = pg.locator("[data-test=subp-ok]")
        ok.wait_for()
        assert re.search(r"המנוי הושהה ל-4 שבועות — אומת \d{1,2}:\d{2}", ok.inner_text()), ok.inner_text()
        assert len(sent) == 1 and sent[0]["args"]["weeks"] == "4" and re.match(r"^loop-\d{8}$", sent[0]["args"]["contractId"]), sent
        pg.wait_for_load_state("networkidle")                                   # the screen's own fresh re-read of the ticket (refresh) has landed
        pg.reload()                                                            # the verdict is on the ticket, not in the tab
        pg.locator("[data-test=subp-ok]").wait_for()
        # a paused subscription offers resume, never a second pause
        pg.click("[data-test=subp-btn]")
        pg.locator("[data-test=subp-paused]").wait_for()
        assert pg.locator("[data-test=subp-weeks]").is_hidden()
        rgo = pg.locator("[data-test=subp-go]")
        assert rgo.inner_text() == "להחזיר את המנוי לפעילות" and rgo.is_enabled()
        rgo.click()
        pg.locator("[data-test=subp-ok]", has_text="הוחזר לפעילות").wait_for()
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()


def test_pause_failure_is_red_with_the_manual_line_and_cannot_be_clicked_again(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.route("**/api/rozela/apiSubPause", lambda route: route.fulfill(content_type="application/json", body=json.dumps(
            {"ok": False, "verified": False, "error": "not_paused", "msg": "הודעת-בדיקה-ייחודית", "contractId": json.loads(route.request.post_data)["args"]["contractId"],
             "record": {"op": "pause", "state": "failed", "reason": "Loop answered 400: Subscription is not eligible", "provider": "loop"}})))
        pg.goto(base + RONIT)
        pg.click("[data-test=subp-btn]")
        pg.locator("[data-test=subp-w]").nth(0).click()
        pg.click("[data-test=subp-go]")
        fail = pg.locator("#subx-dlg [data-test=subp-fail]")
        fail.wait_for()
        assert "הודעת-בדיקה-ייחודית" in fail.inner_text() and "המנוי לא הושהה" in fail.inner_text() and "להשהות ידנית ב-Loop" in fail.inner_text() and "not eligible" in fail.inner_text()
        assert pg.locator("[data-test=subp-go]").is_hidden()
        browser.close()


def test_loop_off_in_the_preview_disables_the_pause_with_the_reason(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)

        def off(route):
            r = route.fetch()
            j = r.json()
            j["loopWrites"] = False
            route.fulfill(response=r, body=json.dumps(j))
        pg.route("**/api/rozela/apiSubPausePreview", off)
        sent = _abort(pg, "apiSubPause")
        pg.goto(base + RONIT)
        pg.click("[data-test=subp-btn]")
        pg.locator("[data-test=subp-off]").wait_for()
        pg.locator("[data-test=subp-w] input").first.click(force=True)
        assert pg.is_disabled("[data-test=subp-go]") and sent == []
        browser.close()


def test_kaching_brand_pause_button_opens_kachings_pause_for_a_period_form():
    """Owner, 2026-11-20: the same button in every brand. No Loop here (default rozela mock = Kaching writes on): the button opens Kaching's own pause form."""
    base, pwd, proc = start(users=(("agent1", ["agent"], ["rozela"], "he"),))
    try:
        with pw.sync_playwright() as p:
            browser, pg, errors = _login(p, base, pwd)
            sent = _abort(pg, "apiKachingAction")
            pg.goto(base + YOSSI)
            pg.locator("[data-test=draft-card] [data-test=subx-btn]").wait_for()
            btn = pg.locator("[data-test=draft-card] [data-test=subp-btn]")
            btn.wait_for()
            assert btn.inner_text() == "להשהות את המנוי"
            btn.click()
            pg.locator("[data-test=pp-preset-m1]").wait_for()                # Kaching's pause-for-a-period form (month / 2 months / 3 months / a date)
            assert pg.locator("[data-test=pp-preset-m2]").count() == 1 and pg.locator("[data-test=pp-date]").count() == 1
            assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert sent == [], "opening the form pauses nothing"
            assert not errors, errors
            browser.close()
    finally:
        proc.terminate()


def test_kaching_brand_several_subscriptions_ask_which_and_kaching_off_or_frozen_has_no_button():
    base, pwd, proc = start(users=(("agent1", ["agent"], ["rozela"], "he"),))
    try:
        with pw.sync_playwright() as p:
            browser, pg, errors = _login(p, base, pwd)

            def two(route):
                r = route.fetch()
                j = r.json()
                subs = (j.get("extras") or {}).get("subscriptions") or []
                act = [x for x in subs if x.get("status") == "ACTIVE"]
                if act:
                    j["extras"]["subscriptions"] = subs + [dict(act[0])]      # a second ACTIVE line (the mock engine knows only the real contract)
                route.fulfill(response=r, body=json.dumps(j))
            pg.route("**/api/rozela/ticket", two)
            pg.goto(base + YOSSI)
            pg.locator("[data-test=draft-card] [data-test=subp-btn]").wait_for()
            pg.click("[data-test=draft-card] [data-test=subp-btn]")
            pg.locator("[data-test=subp-opt]").nth(1).wait_for()
            assert pg.is_disabled("[data-test=subp-go]")
            pg.locator("[data-test=subp-opt]").nth(1).click()
            pg.click("[data-test=subp-go]")
            pg.locator("[data-test=pp-preset-m1]").wait_for()
            browser.close()
    finally:
        proc.terminate()
    for sw in ({"writes": False}, {"frozen": "2026-11-20T00:00:00Z - daily limit"}):
        b2, w2, pr2 = _srv(sw)
        try:
            with pw.sync_playwright() as p:
                browser, pg, errors = _login(p, b2, w2)
                pg.goto(b2 + YOSSI)
                pg.locator("[data-test=draft-card] [data-test=subx-btn]").wait_for()
                pg.wait_for_timeout(400)
                assert pg.locator("[data-test=subp-btn]").count() == 0, sw
                browser.close()
        finally:
            pr2.terminate()


def test_english_desk_pause_and_cancel_dialogs(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, user="agent-en", width=390)
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a02")
        btn = pg.locator("[data-test=subp-btn]")
        btn.wait_for()
        assert btn.inner_text() == "Pause the subscription"
        btn.click()
        pg.locator("[data-test=subp-q]").wait_for()
        assert [pg.locator("[data-test=subp-w]").nth(i).inner_text() for i in range(4)] == ["2 weeks", "4 weeks", "6 weeks", "8 weeks"]
        pg.locator("[data-test=subp-w]").nth(3).click()
        assert pg.inner_text("[data-test=subp-go]") == "Yes, pause the subscription"
        assert _no_sideways(pg) == {"page": True, "dlg": True}
        pg.click("[data-test=subp-go]")
        ok = pg.locator("[data-test=subp-ok]")
        ok.wait_for()
        assert re.search(r"Subscription paused for 8 weeks — verified", ok.inner_text()), ok.inner_text()
        pg.route("**/api/rozela/apiSubCancelPreview", _with_advice(dict(TRY_SAVE, why="no_reason", step="ask_why", percent=0, reason=None)))
        pg.goto(base + "/cs/en#/b/rozela/t/t18f2a03")
        pg.click("[data-test=subx-btn]")
        pg.locator("[data-test=subx-adv]").wait_for()
        assert "Before you cancel" in pg.inner_text("[data-test=subx-adv]")
        assert pg.inner_text("[data-test=subx-go]") == "Cancel anyway"
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_postpone_the_next_delivery_by_loops_own_options_verified_and_kept_on_the_ticket(srv, width):
    """Owner, 2026-11-23 (rozela on Loop): "אי אפשר לדחות מנוי ... בכפתור במערכת". The "⏭ לדחות משלוח" button next to pause: 7 / 15 / 30 / 45 / 60 days
    (Loop's own delay options), no default, the current and the new date shown, the verdict read back and kept on the ticket."""
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=width)
        sent = _spy(pg, "apiSubPostpone")
        pg.goto(base + RONIT)
        btn = pg.locator("[data-test=draft-card] [data-test=subd-btn]")
        btn.wait_for()
        assert btn.inner_text() == "⏭ לדחות משלוח" and btn.is_enabled()
        btn.click()
        pg.locator("[data-test=subp-q]").wait_for()
        assert "לדחות את המשלוח הבא של רונית אברהם?" in pg.inner_text("[data-test=subp-q]")
        opts = pg.locator("[data-test=subd-d]")
        assert [opts.nth(i).inner_text() for i in range(opts.count())] == ["7 ימים", "15 ימים", "30 ימים", "45 ימים", "60 ימים"]
        assert not any(pg.locator("[data-test=subd-d] input").nth(i).is_checked() for i in range(5)), "no preselected length"
        go = pg.locator("[data-test=subp-go]")
        assert go.is_disabled() and go.inner_text() == "כן, לדחות את המשלוח"
        assert "החיוב והמשלוח הבא כרגע: 10.2.27" in pg.inner_text("[data-test=subd-dates]")
        opts.nth(2).click()
        assert "אחרי הדחייה: 12.3.27" in pg.inner_text("[data-test=subd-dates]")
        assert _no_sideways(pg) == {"page": True, "dlg": True}
        go.click()
        ok = pg.locator("[data-test=subd-ok]")
        ok.wait_for()
        assert re.search(r"המשלוח הבא נדחה ב-30 ימים, ל-12\.3\.27 — אומת \d{1,2}:\d{2}", ok.inner_text()), ok.inner_text()
        assert len(sent) == 1 and sent[0]["args"]["days"] == "30" and re.match(r"^loop-\d{8}$", sent[0]["args"]["contractId"]), sent
        pg.wait_for_load_state("networkidle")
        pg.reload()
        pg.locator("[data-test=subd-ok]").wait_for()
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()


def test_postpone_failure_is_red_with_the_manual_line_and_a_paused_subscription_has_nothing_to_postpone(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd)
        pg.route("**/api/rozela/apiSubPostpone", lambda route: route.fulfill(content_type="application/json", body=json.dumps(
            {"ok": False, "verified": False, "error": "not_postponed", "msg": "הודעת-בדיקה-ייחודית", "contractId": json.loads(route.request.post_data)["args"]["contractId"],
             "record": {"op": "postpone", "state": "failed", "reason": "Loop answered 400: newBillingDateEpoch is required", "provider": "loop"}})))
        pg.goto(base + RONIT)
        pg.click("[data-test=subd-btn]")
        pg.locator("[data-test=subd-d]").nth(0).click()
        pg.click("[data-test=subp-go]")
        fail = pg.locator("#subx-dlg [data-test=subd-fail]")
        fail.wait_for()
        assert "המשלוח לא נדחה" in fail.inner_text() and "לדחות ידנית ב-Loop" in fail.inner_text() and "הודעת-בדיקה-ייחודית" in fail.inner_text()
        assert pg.locator("[data-test=subp-go]").is_hidden()
        pg.keyboard.press("Escape")
        # pause it, then the postpone dialog says there is nothing to postpone and offers no button
        pg.click("[data-test=subp-btn]")
        pg.locator("[data-test=subp-w]").nth(0).click()
        pg.click("[data-test=subp-go]")
        pg.locator("[data-test=subp-ok]").first.wait_for()
        pg.click("[data-test=subd-btn]")
        pg.locator("[data-test=subd-paused]").wait_for()
        assert pg.locator("[data-test=subd-days]").is_hidden() and pg.locator("[data-test=subp-go]").is_hidden()
        assert not errors, errors
        browser.close()


def test_kaching_brand_has_no_loop_postpone_button():
    base, pwd, proc = start(users=(("agent1", ["agent"], ["rozela"], "he"),))
    try:
        with pw.sync_playwright() as p:
            browser, pg, errors = _login(p, base, pwd)
            pg.goto(base + RONIT)
            pg.locator("[data-test=draft-card]").wait_for()
            pg.wait_for_load_state("networkidle")
            assert pg.locator("[data-test=subd-btn]").count() == 0
            browser.close()
    finally:
        proc.terminate()


def _patch_ticket(pg, tid, category=None, subs=None):
    """The ticket answer as served, with a category / a subscriptions list put in (what a real rozela ticket looked like on 2026-11-24)."""
    def handler(route):
        r = route.fetch()
        j = r.json()
        if j.get("ticket", {}).get("id") == tid:
            if category is not None:
                j["ticket"]["category"] = category
                j["ticket"]["action"] = ""
            if subs is not None:
                j.setdefault("extras", {})["subscriptions"] = subs
        route.fulfill(response=r, body=json.dumps(j))
    pg.route("**/api/rozela/ticket", handler)


@pytest.mark.parametrize("width", [1280, 390])
def test_billing_ticket_i_did_not_order_gets_the_cancel_button_and_the_dialog_opens(srv, width):
    """the owner 2026-11-24: "the button does not appear in some tickets" - live: "I did not order, stop charging me" filed as billing / refund had no button."""
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=width)
        pg.goto(base + "/cs#/b/rozela/t/t18f2a04")          # a return_refund ticket in the mock (its action is not "cancel:")
        btn = pg.locator("[data-test=draft-card] [data-test=subx-btn]")
        btn.wait_for(timeout=15000)
        assert btn.is_enabled()
        btn.click()
        pg.wait_for_selector("#subx-dlg [data-test=subx-q], #subx-dlg [data-test=subx-none], #subx-dlg [data-test=subx-noemail], #subx-dlg [data-test=subx-ended], #subx-dlg [data-test=subx-dlg-err]", timeout=15000)
        assert not pg.locator("#subx-dlg [data-test=subx-dlg-err]").count(), pg.inner_text("#subx-dlg")
        assert pg.locator("#subx-dlg [data-test=subx-q], #subx-dlg [data-test=subx-ended], #subx-dlg [data-test=subx-none]").count(), pg.inner_text("#subx-dlg")
        _no_sideways(pg)
        assert not errors, errors
        browser.close()


def test_shipping_ticket_still_has_no_cancel_button(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=1280)
        _patch_ticket(pg, "t18f2a02", category="shipping")
        pg.goto(base + RONIT)
        pg.wait_for_selector("[data-test=draft-card]", timeout=15000)
        pg.wait_for_timeout(800)
        assert pg.locator("[data-test=draft-card] [data-test=subx-btn]").count() == 0
        browser.close()


def test_loop_subscription_in_the_panel_is_shown_live_without_the_kaching_action_buttons(srv):
    """A Loop row in the subscriptions panel: status + note, never Kaching's manage / pause / cancel (they would call Kaching with a Loop id)."""
    base, pwd = srv
    loop = {"id": "loop-48597382", "provider": "loop", "status": "ACTIVE", "every": {"interval": "MONTH", "count": 1}, "createdAt": "2026-11-01T10:00:00Z",
            "nextBillingDate": "2026-12-01T10:00:00Z", "lines": [{"title": "פורמולת הסלק של רוזלה", "quantity": 2}]}
    with pw.sync_playwright() as p:
        browser, pg, errors = _login(p, base, pwd, width=1280)
        _patch_ticket(pg, "t18f2a02", subs=[loop])
        pg.goto(base + RONIT)
        note = pg.locator("[data-test=sub-loop-note]")
        note.wait_for(timeout=15000)
        card = pg.locator("#subs-card")
        assert "פורמולת הסלק" in card.inner_text() and "48597382" in card.inner_text()
        assert card.locator("[data-test=manage-sub]").count() == 0 and card.locator("[data-test=sub-pause]").count() == 0
        assert "null" not in card.inner_text() and "[object Object]" not in card.inner_text()
        assert not errors, errors
        browser.close()
