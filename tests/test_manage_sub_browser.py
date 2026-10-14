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
