"""Owner, 2026-10-14: pause and every other Kaching action from the subscription panel (mock engine, real browser)."""
import pytest

from test_resilience_browser import page, server  # noqa: F401

pw = pytest.importorskip("playwright.sync_api")


def _open_manage(pg, base):
    pg.goto(base + "/cs#/b/rozela/t/t18f2a03")
    pg.wait_for_selector("[data-test=manage-sub]")
    pg.locator("[data-test=manage-sub]").first.click()
    pg.wait_for_selector("[data-test=mg-cycle]")


def _confirm(pg, last4):
    pg.wait_for_selector("[data-test=mg-go]")
    assert pg.is_disabled("[data-test=mg-go]")
    pg.fill("#sub-dlg input.code", "0000")
    assert pg.is_disabled("[data-test=mg-go]")                 # the button lights only on the right 4 digits
    pg.fill("#sub-dlg input.code", last4)
    pg.click("[data-test=mg-go]")


def test_pause_then_resume_from_the_panel(page):
    pg, base = page
    _open_manage(pg, base)
    dlg = pg.locator("#sub-dlg")
    assert "פעיל" in dlg.inner_text()
    dlg.get_by_role("button", name="השהיית מנוי").click()
    assert "לא יהיו חיובים" in dlg.inner_text()
    _confirm(pg, "0123")
    dlg.locator(".chip", has_text="מושהה").first.wait_for()
    dlg.get_by_role("button", name="חידוש מנוי").click()
    _confirm(pg, "0123")
    dlg.get_by_role("button", name="השהיית מנוי").wait_for()


def test_skip_a_delivery_and_add_a_discount(page):
    pg, base = page
    _open_manage(pg, base)
    dlg = pg.locator("#sub-dlg")
    pg.locator("[data-test=mg-cycle]").first.get_by_role("button", name="דילוג").click()
    _confirm(pg, "0123")
    pg.locator("[data-test=mg-cycle]").first.locator(".chip", has_text="מדולג").wait_for()
    dlg.get_by_role("button", name="הוספת הנחה").click()
    dlg.locator("input[inputmode=decimal]").fill("15")
    dlg.locator("input[maxlength='60']").fill("הנחת שימור")
    dlg.get_by_role("button", name="המשך לאישור").click()
    assert "הנחת שימור" in dlg.inner_text() and "15%" in dlg.inner_text()
    _confirm(pg, "0123")
    pg.locator("[data-test=mg-go]").wait_for(state="detached")
    assert "הנחת שימור" in dlg.inner_text()


def test_save_discount_defaults_presets_hint_and_guide(page):
    """Owner, 2026-10-27: the add-discount form starts as the save discount (percentage, ONE delivery, the engine's title), has 30/40/50 buttons, a hint from the
    renewals paid, a soft warning outside that shape, and the team's guide. The gates (4 digits, limits) are unchanged."""
    pg, base = page
    _open_manage(pg, base)
    dlg = pg.locator("#sub-dlg")
    guide = dlg.locator("[data-test=save-guide]")
    guide.wait_for()
    assert guide.get_attribute("open") is None                      # collapsed on the contract view
    guide.locator("summary").click()
    text = guide.inner_text()
    for needle in ("50%", "40%", "30%", "הצעה אחת בלבד", "בודקים על לקוח אמיתי אחד", "ממשק הניהול של קצ׳ינג"):
        assert needle in text, needle
    dlg.get_by_role("button", name="הוספת הנחה").click()
    assert dlg.locator("select").first.input_value() == "PERCENTAGE"
    assert dlg.locator("[data-test=mg-dcycles]").input_value() == "1"
    assert dlg.locator("[data-test=mg-dtitle]").input_value() == "הנחת שימור"
    assert dlg.locator("[data-test=mg-dvalue]").input_value() == ""
    assert "חידושים ששולמו במנוי הזה: 1" in dlg.locator("[data-test=mg-dhint]").inner_text()   # the mock contract has 2 orders
    assert dlg.locator("[data-test=save-guide]").last.get_attribute("open") is not None         # open inside the form
    warn = dlg.locator("[data-test=mg-dwarn]")
    assert warn.is_hidden()
    for n in ("30", "40", "50"):
        dlg.locator("[data-test=mg-preset-%s]" % n).click()
        assert dlg.locator("[data-test=mg-dvalue]").input_value() == n
        assert warn.is_hidden()
    dlg.locator("[data-test=mg-dcycles]").fill("3")
    assert warn.is_visible()                                        # not the save shape: a soft warning, never a block
    dlg.locator("[data-test=mg-dcycles]").fill("1")
    assert warn.is_hidden()
    dlg.locator("[data-test=mg-dvalue]").fill("35")
    assert warn.is_visible()
    dlg.locator("[data-test=mg-preset-40]").click()
    dlg.get_by_role("button", name="המשך לאישור").click()
    summary = dlg.inner_text()
    assert "הנחת שימור" in summary and "40%" in summary and "ל-1 משלוחים" in summary
    _confirm(pg, "0123")                                            # the 4-digit gate is still the only way through
    pg.locator("[data-test=mg-go]").wait_for(state="detached")
    assert "הנחת שימור" in dlg.inner_text()


def test_save_discount_gates_are_unchanged(page):
    pg, base = page
    _open_manage(pg, base)
    dlg = pg.locator("#sub-dlg")
    dlg.get_by_role("button", name="הוספת הנחה").click()
    dlg.get_by_role("button", name="המשך לאישור").click()           # no value: refused, no confirm step
    assert dlg.locator("[data-test=mg-dvalue][aria-invalid=true]").count() == 1
    dlg.locator("[data-test=mg-preset-30]").click()
    dlg.locator("[data-test=mg-dtitle]").fill("x")                  # a title under 2 characters: refused
    dlg.get_by_role("button", name="המשך לאישור").click()
    assert dlg.locator("[data-test=mg-dtitle][aria-invalid=true]").count() == 1
    assert pg.locator("[data-test=mg-go]").count() == 0


def test_the_cancel_recommendation_links_to_the_guide(page):
    pg, base = page

    def rewrite(route, request):
        resp = route.fetch()
        body = resp.json()
        tk = body.get("ticket") or (body.get("data") or {}).get("ticket")
        if tk is not None:
            tk["recommendation"] = "סולם הצלה: סיבה: יקר לו · הוצע: הנחה 40% על ההזמנה הבאה במנוי בלבד. אם מסכים: להוסיף הנחה 40% ב'ניהול מנוי' → הנחה → אחוזים · מחזור אחד · כותרת 'הנחת שימור', ורק אחרי שהלקוח הסכים. אם מתעקש: לבטל בכפתור באותו יום ולשלוח אישור"
        route.fulfill(response=resp, json=body)

    pg.route("**/api/rozela/ticket*", rewrite)
    pg.goto(base + "/cs#/b/rozela/t/t18f2a03")
    pg.wait_for_selector("[data-test=sg-open]")
    pg.click("[data-test=sg-open]")
    dlg = pg.locator("[data-test=save-guide-dlg]")
    dlg.wait_for()
    assert "50%" in dlg.inner_text() and "הצעה אחת בלבד" in dlg.inner_text()
    dlg.get_by_role("button", name="סגירה").click()
    assert not dlg.is_visible()
