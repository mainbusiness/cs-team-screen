"""Owner, 2026-10-26: at 390 px an admin's top bar made the page 521 px wide (the whole screen sat shifted sideways on a phone).
Zero horizontal overflow at 360 / 390 / 414 for an admin (all brands), a pure user-manager and agents (1 and 2 brands), on the list,
an open ticket and the managers' board, in both desks; the collapsed links stay reachable (title + aria-label, never hidden)."""
import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
USERS = (("admin1", ["admin", "user-manager"], ALL, "he"), ("um1", ["user-manager"], ALL, "he"),
         ("agent2", ["agent"], ["celesta", "apexmen"], "he"), ("agent1", ["agent"], ["rozela"], "he"))
OV = "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start(users=USERS)
    yield base, pwd
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.parametrize("user", [u[0] for u in USERS])
def test_no_horizontal_overflow_on_phones(server, user):
    base, pwd = server
    roles = dict((u[0], u[1]) for u in USERS)[user]
    bad = []
    with pw.sync_playwright() as p:
        browser = launch(p)
        for desk in ("/cs", "/cs/en"):
            pg = browser.new_context(viewport={"width": 390, "height": 800}).new_page()
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.goto(base + "/cs/login")
            pg.fill("input[name=username]", user)
            pg.fill("input[name=password]", pwd)
            pg.click("button[type=submit]")
            pg.wait_for_load_state("networkidle")
            views = ["#/"]
            if "user-manager" in roles or "admin" in roles:
                views.append("#/dash")
            for v in views:
                pg.goto(base + desk + v)
                pg.wait_for_load_state("networkidle")
                pg.wait_for_timeout(700)
                for w in (360, 390, 414):
                    pg.set_viewport_size({"width": w, "height": 800})
                    pg.wait_for_timeout(200)
                    sw, cw = pg.evaluate(OV)
                    if sw > cw:
                        bad.append((desk, v, w, sw, cw))
                if v == "#/" and pg.locator("#list-pane a.row").count():
                    pg.locator("#list-pane a.row").first.click()
                    pg.wait_for_timeout(900)
                    for w in (360, 390, 414):
                        pg.set_viewport_size({"width": w, "height": 800})
                        pg.wait_for_timeout(200)
                        sw, cw = pg.evaluate(OV)
                        if sw > cw:
                            bad.append((desk, "ticket", w, sw, cw))
            if pg.locator("[data-test=dash-link]").count():
                assert pg.get_attribute("[data-test=dash-link]", "aria-label"), "the collapsed board link keeps its name"
            assert pg.locator("[data-test=english-workspace]").is_visible()
            assert not errors, errors
            pg.context.close()
        browser.close()
    assert not bad, bad
