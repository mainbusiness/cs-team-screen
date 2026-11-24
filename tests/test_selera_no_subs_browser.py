"""Selera has NO subscriptions (a pillow brand; the owner 2026-11-24: "there should be no option to cancel a subscription there — only this brand").
On a brand whose boot says subscriptions:'none' the screen offers no subscription-cancel anywhere: no Kaching / auto-cancel switches in the
admin settings, no retention playbook card in a ticket. A brand WITH subscriptions (rozela) keeps all of them."""
import pytest

from browser_server import start
from pw_launch import launch, pw

USERS = (("guy", ["admin"], ["rozela", "selera"], "he"),)


@pytest.fixture
def srv():
    base, pwd, proc = start(users=USERS)
    yield base, pwd
    proc.terminate()


def login(p, base, pwd, user):
    pg = launch(p).new_page(viewport={"width": 1280, "height": 1000})
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    return pg


def test_selera_offers_no_subscription_cancel_rozela_still_does(srv):
    base, pwd = srv
    with pw.sync_playwright() as p:
        pg = login(p, base, pwd, "guy")
        # settings, opened directly (the boot may arrive after the first paint: the re-render must drop the rows)
        pg.goto(base + "/cs#/settings/selera")
        pg.wait_for_selector(".set-row[data-key=DRY_RUN]", timeout=20000)
        pg.wait_for_timeout(1500)
        assert pg.locator(".set-row[data-key=KACHING_WRITES]").count() == 0
        assert pg.locator(".set-row[data-key=AUTO_CANCEL]").count() == 0
        pg.goto(base + "/cs#/settings/rozela")
        pg.wait_for_selector(".set-row[data-key=KACHING_WRITES]", timeout=20000)
        assert pg.locator(".set-row[data-key=AUTO_CANCEL]").count() == 1
        # a selera ticket: playbooks without the subscription-retention card, never opened as a cancel
        pg.goto(base + "/cs#/b/selera/t/tsele01")
        pg.wait_for_selector("[data-test=playbooks]", timeout=20000)
        pb = pg.locator("[data-test=playbooks]")
        assert pb.get_attribute("data-cancel") is None
        assert pb.locator("[data-test=pb-retention]").count() == 0
        assert pg.locator("[data-test=subx] button").count() == 0
        # rozela keeps the card
        pg.goto(base + "/cs#/b/rozela/t/t18f2a01")
        pg.wait_for_selector("[data-test=playbooks] [data-test=pb-retention]", state="attached", timeout=20000)
        assert pg.errors == []
