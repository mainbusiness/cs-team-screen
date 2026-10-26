"""Must-read notices (Owner, 2026-10-26: the Kaching subscriptions procedure for the CS manager Manager, team_screen/notice.py).
Shown until each user acknowledges; the ack is per user, persistent across a restart, audited once, CSRF-protected; agents of
other brands never get it. The same tests run on Postgres with CS_TEST_PG=<url>."""
import json
import os
import re

import pytest

import notice
from conftest import audit_text, client_for, logged_in, login  # noqa: F401

NID = notice.KACHING_SUBS["id"]
ALL = ["rozela", "celesta", "apexmen", "velora"]
SOP_DIR = "/Users/Shared/course_mrr/cs_sop_manager"


def notices(c):
    r = c.get("/api/notice")
    assert r.status_code == 200, r.data
    return {n["id"]: n for n in r.get_json()["notices"]}


def ack(c, tok, nid=NID, origin=None):
    h = {"X-CSRF-Token": tok} if tok else {}
    if origin:
        h["Origin"] = origin
    return c.post("/api/notice/ack", json={"id": nid}, headers=h)


def test_manager_sees_it_until_he_acks_and_it_survives_a_restart(make_app, pw_hash):
    a1 = make_app()
    c, tok = logged_in(a1, pw_hash, "manager", ["admin", "user-manager"], ALL)
    n = notices(c)[NID]
    assert n["acked"] is False and n["acked_at"] is None
    assert n["title"] == "🧾 נוהל חדש: מנויים ב-Kaching — חשוב מאוד"
    assert [b["brand"] for b in n["brand_notes"]] == ["rozela", "celesta", "apexmen"]
    assert notices(c)[NID]["acked"] is False, "still unacked on the next open"
    r = ack(c, tok)
    assert r.status_code == 200 and r.get_json()["already"] is False
    first = r.get_json()["acked_at"]
    assert notices(c)[NID]["acked"] is True
    a2 = make_app()                                         # restart: the ack is on the store, not in the process
    c2 = client_for(a2)
    assert login(c2, "manager").status_code == 302
    assert notices(c2)[NID]["acked"] is True and notices(c2)[NID]["acked_at"] == first
    r = ack(c, tok)                                         # a second click keeps the first time and writes no second audit line
    assert r.get_json()["already"] is True and r.get_json()["acked_at"] == first
    assert audit_text(a1).count('"notice_acked"') == 1


def test_ack_is_per_user(app, pw_hash):
    c1, t1 = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ALL)
    c2, _ = logged_in(app, pw_hash, "agent-two", ["agent"], ["celesta", "apexmen"])
    assert ack(c1, t1).status_code == 200
    n = notices(c2)[NID]
    assert n["acked"] is False
    assert [b["brand"] for b in n["brand_notes"]] == ["celesta", "apexmen"], "an agent sees only her brands' options"


def test_agent_of_other_brands_does_not_get_it(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "vel1", ["agent"], ["velora"])
    assert notices(c) == {}
    assert ack(c, tok).status_code == 400


def test_csrf_and_login_are_required(app, pw_hash):
    assert client_for(app).get("/api/notice").status_code == 401
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ALL)
    assert ack(c, None).status_code == 403
    assert ack(c, "nope").status_code == 403
    assert ack(c, tok, origin="https://evil.example").status_code == 403
    assert ack(c, tok, nid="no-such-notice").status_code == 400
    assert c.post("/api/notice/ack", data="x", headers={"X-CSRF-Token": tok}).status_code == 400
    assert notices(c)[NID]["acked"] is False


def test_file_store_refuses_a_broken_file(make_app, pw_hash):
    if os.environ.get("CS_TEST_PG"):
        pytest.skip("file layout only")
    a = make_app()
    st = a.extensions["cs"]["notice_acks"]
    st.ack("manager", NID)
    assert oct(os.stat(st.path).st_mode & 0o777) == "0o600"
    open(st.path, "w").write("[]")
    with pytest.raises(RuntimeError):
        st.acks_of("manager")


@pytest.mark.skipif(not os.path.isdir(SOP_DIR), reason="the procedure files live on the Mac only")
def test_text_is_the_procedure_files_word_for_word():
    """Every line of each brand's procedure file is in the notice for that brand (the shared steps + its own options line)."""
    n = notice.KACHING_SUBS
    for b in n["brands"]:
        shown = "\n".join([n["intro"]] + [s["head"] + "\n" + "\n".join(s["lines"]) for s in n["sections"]] + [n["brand_notes"][b]]).replace("\u2066", "").replace("\u2069", "")
        src = open(os.path.join(SOP_DIR, b + ".md"), encoding="utf-8").read().split("\n", 2)[2]   # skip the file's own title
        for line in src.splitlines():
            line = line.strip().lstrip("- ").strip()
            if not line:
                continue
            m = re.match(r"^\*\*3\. ביטול:\*\* מציעים פעם אחת את אפשרויות השימור: (.*)$", line)
            if m:
                assert m.group(1) == n["brand_notes"][b], b
                continue
            for part in [p for p in re.split(r"\*\*(\d\. [^*]+:)\*\*\s*", line) if p.strip()]:
                assert part.strip() in shown.replace("**", "").replace("\n", " ") or part.strip() in shown, (b, part)
