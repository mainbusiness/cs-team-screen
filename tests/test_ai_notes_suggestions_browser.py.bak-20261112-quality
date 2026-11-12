"""Owner, 2026-10-22 — "the notes the manager gives do not improve the AI's answers; understand why and make a real fix that works for good".
Measured: one note in 12 days, ~1,500 hand edits of AI drafts that never reached the AI. The engine (AiLearn.gs) now distils the team's
edits into suggested rules, and a note rewrites the open AI drafts. Checked in a real browser against the mock engine, inside the SAME
AI-notes card:
 - the suggestions render per brand (text, "found in N corrections", 2 examples collapsed), an empty brand says how many corrections it has;
 - approve as is, and edit + approve: the item leaves, the note appears in the notes list and goes through the reading + check flow;
   an editor the manager is typing in survives the repaint caused by another decision;
 - reject (two clicks) is stored: after a reload the suggestion is still gone;
 - a change that touched the prompt says how many open drafts are rewritten (add, delete, a document attached), and nothing for 0 / null;
 - a check where a fixed system rule stopped the answer is shown as a warning, never as checked;
 - English desk strings, and no horizontal overflow at 390 and 1280 px.
"""
import json
import os

import pytest

import browser_server
from pw_launch import launch, pw  # noqa: F401

ALL = ["rozela", "celesta", "apexmen", "selera", "velora"]
PDF = {"name": "iso-certificate.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n" + b"A" * 3000}
SHOTS = os.environ.get("AIN_SHOTS_DIR")       # set to keep screenshots for reading (Gate 0)


@pytest.fixture(scope="module")
def server():
    base, pwd, proc = browser_server.start(users=(("admin1", ["admin"], ALL, "he"), ("admin2", ["admin"], ALL, "en")))
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


def open_card(p, base, pwd, user="admin1", width=1280, routes=None):
    browser = launch(p)
    pg = browser.new_context(viewport={"width": width, "height": 900}).new_page()
    for pattern, handler in (routes or []):
        pg.route(pattern, handler)
    pg.goto(base + ("/cs/en/login" if user == "admin2" else "/cs/login"))
    pg.fill("input[name=username]", user)
    pg.fill("input[name=password]", pwd)
    pg.click("button[type=submit]")
    pg.wait_for_load_state("networkidle")
    pg.goto(base + ("/cs/en#/dash" if user == "admin2" else "/cs#/dash"))
    pg.wait_for_selector("[data-test=ai-notes]")
    pg.wait_for_selector("[data-test=ai-sugg-section] [data-test=ai-sugg-empty]")     # the suggestions arrived
    return browser, pg


def sugg(pg, sid):
    return pg.locator("[data-test=ai-sugg][data-id=%s]" % sid)


def note_in(pg, brand, text):
    return pg.locator("[data-test=ai-group-brand][data-brand=%s] [data-test=ai-note]" % brand).filter(has_text=text)


def test_suggestions_render_per_brand_with_counts_and_collapsed_examples(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        sec = pg.locator("[data-test=ai-notes] [data-test=ai-sugg-section]")
        assert "💡 הצעות מהתיקונים של הצוות" in sec.locator("h4").inner_text()
        assert sec.locator("[data-test=ai-sugg-total]").inner_text() == "3"
        ro = sec.locator("[data-test=ai-sugg-brand][data-brand=rozela] [data-test=ai-sugg]")
        assert ro.count() == 2
        assert ro.nth(0).get_attribute("data-id") == "s1b2c3d4e5f6a7b8c", "newest first"
        first = sugg(pg, "s0a1b2c3d4e5f6a7b")
        assert "לא להציע החזר כספי" in first.locator("[data-test=ai-sugg-text]").inner_text()
        assert first.locator("[data-test=ai-sugg-count]").inner_text() == "נמצא ב-6 תיקונים"
        det = first.locator("[data-test=ai-sugg-examples]")
        assert det.get_attribute("open") is None, "the examples are born collapsed"
        assert not first.locator("[data-test=ai-sugg-example]").first.is_visible()
        det.locator("summary").click()
        assert first.locator("[data-test=ai-sugg-example]").count() == 2
        ex = first.locator("[data-test=ai-sugg-example]").first.inner_text()
        assert "הלקוח:" in ex and "ה-AI כתב:" in ex and "הצוות שלח:" in ex and "60 יום החזר" in ex and "שבוע נוסף" in ex
        for b in ("approve", "edit", "reject"):
            assert first.locator("[data-test=ai-sugg-%s]" % b).is_visible(), b
        # brands with none say so, with their corrections count; Velora is not connected, so it is not listed
        emp = {e.get_attribute("data-brand"): e.inner_text() for e in sec.locator("[data-test=ai-sugg-empty]").all()}
        assert set(emp) == {"apexmen", "selera"}, emp
        assert "עדיין אין הצעות" in emp["apexmen"] and "4 תיקונים נאספו" in emp["apexmen"]
        assert "המערכת מציעה כאן כלל" in sec.inner_text()
        help_ = pg.locator("[data-test=ai-notes-help]").inner_text()
        assert "הטיוטות הפתוחות בתור נכתבות מחדש" in help_ and "תיקונים שהצוות עושה" in help_
        for w in (1280, 390):
            pg.set_viewport_size({"width": w, "height": 900})
            over = pg.evaluate("""() => { const c = document.querySelector('[data-test=ai-notes]'); const out = [];
                for (const e of [c, ...c.querySelectorAll('*')]) { const cs = getComputedStyle(e);
                  if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
                  if (e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0) out.push(e.className || e.tagName); }
                return { doc: document.documentElement.scrollWidth > innerWidth, els: out }; }""")
            assert not over["doc"] and not over["els"], (w, over)
            if SHOTS:
                sec.screenshot(path=os.path.join(SHOTS, "sugg_he_%d.png" % w))
        browser.close()


def test_approve_and_edit_then_approve_become_checked_notes_and_an_open_editor_survives(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        sent = []
        pg.on("request", lambda r: sent.append(json.loads(r.post_data)) if r.url.endswith("/apiAiNoteSuggestDecide") else None)
        # open the editor on one suggestion and type in it
        b = sugg(pg, "s1b2c3d4e5f6a7b8c")
        b.locator("[data-test=ai-sugg-edit]").click()
        ta = b.locator("[data-test=ai-sugg-edit-text]")
        assert ta.input_value() == "לפתוח בשם הלקוח ולא ב'שלום רב'."
        assert pg.evaluate("document.activeElement.getAttribute('data-test')") == "ai-sugg-edit-text"
        ta.fill("לפתוח ב'היי' ובשם הפרטי של הלקוח.")
        # approve the OTHER suggestion as it is: the section repaints, the half-written edit must still be there
        sugg(pg, "s0a1b2c3d4e5f6a7b").locator("[data-test=ai-sugg-approve]").click()
        assert until(lambda: sugg(pg, "s0a1b2c3d4e5f6a7b").count() == 0)
        st = pg.locator("[data-test=ai-sugg-status]")
        assert "ההצעה נוספה כהערה ל-Rozela" in st.inner_text()
        assert sugg(pg, "s1b2c3d4e5f6a7b8c").locator("[data-test=ai-sugg-edit-text]").input_value() == "לפתוח ב'היי' ובשם הפרטי של הלקוח."
        n1 = note_in(pg, "rozela", "לא להציע החזר כספי")
        assert until(lambda: n1.count() == 1)
        assert n1.get_attribute("data-id") == "0a1b2c3d4e5f6a7b", "the note keeps the suggestion's id (without the s)"
        r1 = n1.locator("[data-test=ai-note-reply]")
        assert until(lambda: r1.get_attribute("data-state") == "checked", 12000), r1.get_attribute("data-state")
        assert r1.locator("[data-test=ai-note-understood]").count() == 1
        assert sent[-1]["args"] == {"id": "s0a1b2c3d4e5f6a7b", "decision": "approve"}, "as is: no text"
        # now save the edit
        sugg(pg, "s1b2c3d4e5f6a7b8c").locator("[data-test=ai-sugg-edit-save]").click()
        assert until(lambda: sugg(pg, "s1b2c3d4e5f6a7b8c").count() == 0)
        assert sent[-1]["args"] == {"id": "s1b2c3d4e5f6a7b8c", "decision": "approve", "text": "לפתוח ב'היי' ובשם הפרטי של הלקוח."}
        n2 = note_in(pg, "rozela", "לפתוח ב'היי'")
        assert until(lambda: n2.count() == 1)
        assert until(lambda: n2.locator("[data-test=ai-note-reply]").get_attribute("data-state") == "checked", 12000)
        assert pg.locator("[data-test=ai-sugg-brand][data-brand=rozela]").count() == 0
        assert until(lambda: "37 תיקונים נאספו" in pg.locator("[data-test=ai-sugg-empty][data-brand=rozela]").inner_text())
        browser.close()


def test_reject_takes_two_clicks_and_is_stored(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        c = sugg(pg, "s2c3d4e5f6a7b8c9d")
        rej = c.locator("[data-test=ai-sugg-reject]")
        rej.click()
        assert "לחצו שוב" in rej.inner_text() and c.count() == 1, "one click only arms it"
        pg.wait_for_timeout(600)
        rej.click()
        assert until(lambda: sugg(pg, "s2c3d4e5f6a7b8c9d").count() == 0)
        assert "סומנה כלא רלוונטית" in pg.locator("[data-test=ai-sugg-status]").inner_text()
        assert note_in(pg, "celesta", "delivery date").count() == 0, "a rejection makes no note"
        pg.reload()
        pg.wait_for_selector("[data-test=ai-sugg-section] [data-test=ai-sugg-empty]")
        assert sugg(pg, "s2c3d4e5f6a7b8c9d").count() == 0
        assert "12 תיקונים נאספו" in pg.locator("[data-test=ai-sugg-empty][data-brand=celesta]").inner_text()
        browser.close()


def test_a_change_to_the_prompt_says_how_many_open_drafts_are_rewritten(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        status = pg.locator("[data-test=ai-note-status]")
        pg.fill("[data-test=ai-note-text]", "לא לכתוב 'מצטערים על אי הנוחות'")
        pg.select_option("[data-test=ai-note-scope]", "apexmen")
        pg.click("[data-test=ai-note-add]")
        line = status.locator("[data-test=ai-note-redraft][data-brand=apexmen]")
        assert until(lambda: line.count() == 1)
        n = int(line.get_attribute("data-n"))
        assert n > 0 and line.inner_text() == "✍️ %d טיוטות פתוחות ב-ApexMen נכתבות מחדש לפי ההערה (תוך כמה דקות)" % n, line.inner_text()
        assert "נשמר ל-ApexMen" in status.inner_text() and "[object" not in status.inner_text()
        # delete it: rewritten back, without the note
        item = note_in(pg, "apexmen", "מצטערים על אי הנוחות")
        assert until(lambda: item.count() == 1)
        d = item.locator("[data-test=ai-note-del]")
        d.click()
        pg.wait_for_timeout(600)
        d.click()
        assert until(lambda: "נכתבות מחדש בלי ההערה" in status.inner_text())
        # a claim waiting for its document is not in the prompt: no line; the document brings it in: the line
        pg.fill("[data-test=ai-note-text]", "יש לנו תקן ISO 22000")
        pg.select_option("[data-test=ai-note-scope]", "selera")
        pg.click("[data-test=ai-note-add]")
        claim = note_in(pg, "selera", "ISO 22000")
        assert until(lambda: claim.count() == 1 and claim.locator("[data-test=ai-note-reply]").get_attribute("data-state") == "needs_file")
        assert status.locator("[data-test=ai-note-redraft]").count() == 0, status.inner_text()
        claim.locator("[data-test=ai-note-reply] [data-test=ai-note-file-input]").set_input_files(PDF)
        assert until(lambda: status.locator("[data-test=ai-note-redraft][data-brand=selera]").count() == 1, 12000), status.inner_text()
        assert "טיוטה פתוחה אחת ב-Selera נכתבת מחדש לפי ההערה" in status.inner_text(), "one draft: the singular line"
        browser.close()


@pytest.mark.parametrize("value", [0, None])
def test_zero_or_null_redraft_says_nothing_extra(server, value):
    base, pwd = server

    def zero(route):
        r = route.fetch()
        j = r.json()
        if j.get("ok"):
            j["redraft"] = value
        route.fulfill(response=r, body=json.dumps(j))
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd, routes=[("**/apiAiNoteAdd", zero)])
        pg.fill("[data-test=ai-note-text]", "בלי סימני קריאה %s" % value)
        pg.select_option("[data-test=ai-note-scope]", "celesta")
        pg.click("[data-test=ai-note-add]")
        status = pg.locator("[data-test=ai-note-status]")
        assert until(lambda: "נשמר ל-Celesta" in status.inner_text())
        assert status.locator("[data-test=ai-note-redraft]").count() == 0 and "✍️" not in status.inner_text()
        browser.close()


def test_a_note_a_fixed_rule_stops_is_a_warning_never_checked(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd)
        pg.fill("[data-test=ai-note-text]", "MOCK-GATE לתת ללקוח קישור להזמנה")
        pg.select_option("[data-test=ai-note-scope]", "celesta")
        pg.click("[data-test=ai-note-add]")
        r = note_in(pg, "celesta", "MOCK-GATE").locator("[data-test=ai-note-reply]")
        assert until(lambda: r.count() == 1 and r.get_attribute("data-state") == "not_following", 12000), r.get_attribute("data-state")
        g = r.locator("[data-test=ai-note-gate]")
        assert g.count() == 1 and g.inner_text().startswith("⚠")
        assert "כלל קבוע במערכת עצר או החליף את התשובה" in g.inner_text() and "קישור לאתר שאינו של המותג" in g.inner_text()
        assert "✅" not in r.inner_text() and "נכנס למערכת ונבדק" not in r.inner_text()
        assert r.locator("[data-test=ai-note-recheck]").count() == 1
        if SHOTS:
            note_in(pg, "celesta", "MOCK-GATE").screenshot(path=os.path.join(SHOTS, "gate_he_1280.png"))
        browser.close()


def test_english_desk_strings(server):
    base, pwd = server
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd, user="admin2", width=390)
        sec = pg.locator("[data-test=ai-sugg-section]")
        assert "Suggestions from the team's corrections" in sec.locator("h4").inner_text()
        assert "corrections collected" in sec.inner_text()
        assert "open drafts in the queue are rewritten" in pg.locator("[data-test=ai-notes-help]").inner_text()
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if SHOTS:
            pg.locator("[data-test=ai-notes]").screenshot(path=os.path.join(SHOTS, "card_en_390.png"))
        browser.close()


def test_a_named_gate_wins_over_a_judge_that_said_yes(server):
    """Off-contract on purpose: if a reply ever carried gate AND follows:true, the gate decides — never "checked"."""
    base, pwd = server

    def yes_but_gated(route):
        r = route.fetch()
        j = r.json()
        if j.get("ok") and isinstance(j.get("note"), dict) and isinstance(j["note"].get("check"), dict) and "MOCK-GATE" in j["note"].get("text", ""):
            j["note"]["check"]["follows"] = True
        route.fulfill(response=r, body=json.dumps(j))
    with pw.sync_playwright() as p:
        browser, pg = open_card(p, base, pwd, routes=[("**/apiAiNoteCheck", yes_but_gated)])
        pg.fill("[data-test=ai-note-text]", "MOCK-GATE קישור למעקב")
        pg.select_option("[data-test=ai-note-scope]", "apexmen")
        pg.click("[data-test=ai-note-add]")
        r = note_in(pg, "apexmen", "MOCK-GATE קישור").locator("[data-test=ai-note-reply]")
        assert until(lambda: r.count() == 1 and r.get_attribute("data-state") in ("not_following", "checked"), 12000)
        assert r.get_attribute("data-state") == "not_following" and r.locator("[data-test=ai-note-gate]").count() == 1
        assert "✅" not in r.inner_text()
        browser.close()
