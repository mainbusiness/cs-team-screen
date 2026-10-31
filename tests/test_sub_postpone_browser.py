"""Owner, 2026-11-01: postpone the next delivery to a date the agent picks. Own module = its own fresh mock (the pause test changes rozela's cycles)."""
from test_sub_pause_postpone_browser import server, _login, _ticket, _tk, _day, _he, pw  # noqa: F401


def test_postpone_past_a_later_delivery_moves_the_last_one_and_skips_the_earlier(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = _login(p, base, pwd)
        _ticket(pg, base, "rozela")              # the only mock brand whose Kaching writes are on
        last4 = _tk("rozela")[1]
        pg.locator("[data-test=sub-postpone]").first.click()
        dlg = pg.locator("[data-test=pp-dlg]")
        dlg.wait_for()
        assert _he(28) in dlg.locator("[data-test=pp-next-cur]").inner_text()
        for k in ("w1", "w2", "w3", "pm1", "pm2"):
            assert dlg.locator("[data-test=pp-preset-%s]" % k).is_visible()
        dlg.locator("[data-test=pp-preset-w2]").click()                       # +14 days from the next delivery: one move, inside the gap
        what = dlg.locator("[data-test=pp-what]").inner_text()
        assert "המשלוח הבא יעבור מ-" in what and _he(42) in what and _he(58) in what, what
        assert dlg.locator("[data-test=pp-close]").count() == 0               # 16 days to the next one
        dlg.locator("[data-test=pp-preset-w3]").click()                       # +21: only 9 days before the following delivery — a soft warning
        assert dlg.locator("[data-test=pp-close]").is_visible()
        dlg.locator("[data-test=pp-date]").fill(_day(70))                     # past the +58 delivery
        what = dlg.locator("[data-test=pp-what]").inner_text()
        assert "ידולגו המשלוחים של" in what and "אין שום חיוב או משלוח לפני" in what, what
        steps = dlg.locator("[data-test=pp-what] .pp-steps li").all_inner_texts()
        assert len(steps) == 2 and steps[0].startswith("העברת המשלוח של") and _he(58) in steps[0] and steps[1].startswith("דילוג על המשלוח של") and _he(28) in steps[1], steps
        assert all(b.get_attribute("aria-pressed") == "false" for b in dlg.locator(".pp-preset").all())
        dlg.locator("[data-test=pp-next]").click()
        pg.fill("#sub-dlg input.code", last4)
        pg.click("[data-test=mg-go]")
        res = dlg.locator("[data-test=pp-result]")
        try:
            res.wait_for(timeout=8000)
        except Exception:
            raise AssertionError(dlg.inner_text())
        assert "בוצע ואומת" in res.inner_text() and _he(70) in res.inner_text(), res.inner_text()
        dlg.locator("[data-test=pp-full]").click()
        pg.wait_for_selector("[data-test=mg-cycle]")
        rows = pg.locator("[data-test=mg-cycle]").all_inner_texts()
        assert "מדולג" in rows[0] and _he(70) in rows[1] and "מדולג" not in rows[1], rows
        browser.close()
