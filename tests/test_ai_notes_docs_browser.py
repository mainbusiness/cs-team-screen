"""Owner, 2026-10-18 — "don't reject what my manager sends; let him upload the file; a note without the file gets a reply to upload it;
answer him and update when it is in the system". Checked in a real browser against the mock engine:
 - a claim note without its document -> the reply under the note asks for the file (status needs_file), with an upload button;
 - uploading there -> the note is in, checked, and the reply shows the question and the bot's answer;
 - a note added WITH a file goes straight in and is checked; the hint asks for the file while typing a claim;
 - a check where the bot does not follow the note says so (never "checked") and offers to check again.
"""
import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
PDF = {"name": "fda-certificate.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n" + b"A" * 3000}


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start(users=(("admin1", ["admin"], ALL, "he"),))
    yield base, pwd
    proc.terminate()
    proc.wait(timeout=10)


def until(cond, ms=8000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def open_card(p, base, pwd):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    pg.goto(base + "/cs/login")
    pg.fill("input[name=username]", "admin1")
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.goto(base + "/cs#/dash")
    pg.wait_for_selector("[data-test=ai-notes]")
    return browser, pg


def note(pg, brand, text):
    return pg.locator("[data-test=ai-group-brand][data-brand=%s] [data-test=ai-note]" % brand).filter(has_text=text)


def test_claim_note_without_file_asks_for_it_then_upload_puts_it_in_and_checks(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        text = "יש מצב לתקן את הבוט שיגיד שכן יש אישור משרד הבריאות קובץ FDA"
        pg.fill("[data-test=ai-note-text]", text)
        assert pg.locator("[data-test=ai-note-doc-hint]").is_visible(), "the hint asks for the file while typing a claim"
        pg.select_option("[data-test=ai-note-scope]", "celesta")
        pg.click("[data-test=ai-note-add]")
        n = note(pg, "celesta", text)
        assert until(lambda: n.count() == 1)
        r = n.locator("[data-test=ai-note-reply]")
        assert until(lambda: r.get_attribute("data-state") == "needs_file")
        assert "צריך גם את הקובץ של האישור" in r.inner_text()
        # the system's reading comes back right away, before the file, so the manager sees he was understood
        assert until(lambda: r.locator("[data-test=ai-note-understood]").count() == 1)
        assert "איך הבנתי:" in r.inner_text() and "הבנתי: הבוט יגיד ללקוחות" in r.inner_text()
        assert r.locator("[data-test=ai-note-wrong]").count() == 1
        # upload right there, under the note
        r.locator("[data-test=ai-note-file-input]").set_input_files(PDF)
        assert until(lambda: r.get_attribute("data-state") == "checked", 12000), r.get_attribute("data-state")
        assert "נכנס למערכת ונבדק" in r.inner_text()
        assert "שאלתי את הבוט:" in r.inner_text() and "הבוט ענה:" in r.inner_text()
        assert "fda-certificate.pdf" in n.locator("[data-test=ai-note-file]").inner_text()
        browser.close()


def test_note_with_file_goes_straight_in_and_a_plain_note_is_checked_too(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        text = "יש לנו אישור FDA למוצר"
        pg.fill("[data-test=ai-note-text]", text)
        pg.select_option("[data-test=ai-note-scope]", "rozela")
        pg.locator("[data-test=ai-notes] .ain-row [data-test=ai-note-file-input]").set_input_files(PDF)
        assert until(lambda: "fda-certificate.pdf" in pg.locator("[data-test=ai-note-file-chosen]").inner_text())
        assert not pg.locator("[data-test=ai-note-doc-hint]").is_visible(), "a chosen file answers the hint"
        pg.click("[data-test=ai-note-add]")
        r = note(pg, "rozela", text).locator("[data-test=ai-note-reply]")
        assert until(lambda: r.count() == 1 and r.get_attribute("data-state") == "checked", 12000)
        assert pg.locator("[data-test=ai-note-file-chosen]").is_hidden(), "the composer is empty again"
        # a plain note needs no file: in, and checked
        pg.fill("[data-test=ai-note-text]", "תמיד לפתוח בשם הלקוח")
        pg.select_option("[data-test=ai-note-scope]", "apexmen")
        pg.click("[data-test=ai-note-add]")
        r2 = note(pg, "apexmen", "תמיד לפתוח בשם הלקוח").locator("[data-test=ai-note-reply]")
        assert until(lambda: r2.count() == 1 and r2.get_attribute("data-state") == "checked", 12000)
        browser.close()


def test_a_check_the_bot_fails_is_reported_never_checked(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        text = "MOCK-NOFOLLOW לפתוח בהיי"
        pg.fill("[data-test=ai-note-text]", text)
        pg.select_option("[data-test=ai-note-scope]", "selera")
        pg.click("[data-test=ai-note-add]")
        r = note(pg, "selera", text).locator("[data-test=ai-note-reply]")
        assert until(lambda: r.count() == 1 and r.get_attribute("data-state") == "not_following", 12000)
        assert "הבוט עוד לא ענה לפי ההערה" in r.inner_text()
        assert r.locator("[data-test=ai-note-recheck]").count() == 1
        browser.close()


def test_not_what_i_meant_puts_the_text_back_and_the_new_note_replaces_the_old(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        old = "יש לנו אישור משרד הבריאות ואישור FDA"
        pg.fill("[data-test=ai-note-text]", old)
        pg.select_option("[data-test=ai-note-scope]", "apexmen")
        pg.click("[data-test=ai-note-add]")
        n = note(pg, "apexmen", old)
        assert until(lambda: n.count() == 1 and n.locator("[data-test=ai-note-wrong]").count() == 1)
        oid = n.get_attribute("data-id")
        n.locator("[data-test=ai-note-wrong]").click()
        assert pg.input_value("[data-test=ai-note-text]") == old
        assert pg.input_value("[data-test=ai-note-scope]") == "apexmen"
        assert "ההערה הקודמת תימחק" in pg.locator("[data-test=ai-note-status]").inner_text()
        pg.fill("[data-test=ai-note-text]", "יש לנו אישור FDA. אין אישור משרד הבריאות.")
        pg.click("[data-test=ai-note-add]")
        assert until(lambda: pg.locator("[data-test=ai-note][data-id=\"%s\"]" % oid).count() == 0), "the old note is gone"
        assert until(lambda: note(pg, "apexmen", "אין אישור משרד הבריאות").count() == 1)
        browser.close()
