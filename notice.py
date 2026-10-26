"""notice.py — must-read notices for the team, shown until each user acknowledges (Owner, 2026-10-26: "the CS procedure — very
important to pass it to the CS manager Manager, and put an alert for him when he enters his CS system so he won't forget").

  GET  /api/notice              -> {ok, notices: [{id, title, intro, sections, brand_notes, acked, acked_at}]}
  POST /api/notice/ack {id}     -> {ok, id, acked_at, already}

Who sees a notice: every logged-in user who holds one of its brands, and every admin (Manager = admin + all brands).
The screen opens it as a modal on every app open until that user clicks "✅ קראתי והבנתי"; after that it stays reachable from
the ☰ menu ("🧾 נוהל מנויים"). The ack is stored per user (Postgres `screen_notice_acks` in production, a JSON file for tests:
flock + temp + fsync + rename) and audited once as `notice_acked`.

The text is the CS procedure file (/Users/Shared/course_mrr/cs_sop_manager/<brand>.md, 2026-10-26) word for word. The three files
differ ONLY in the retention options of step 3, so the shared steps are written once and each brand gets its own options line.
`**x**` marks bold (the screen renders it with textContent, never as HTML).
"""
import fcntl
import json
import os
import re
import tempfile
import threading
import time

from flask import jsonify, request

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

KACHING_SUBS = {
    "id": "kaching-subs-2026-10-26",
    "brands": ["rozela", "celesta", "apexmen"],
    "menu": "🧾 נוהל מנויים",
    "title": "🧾 נוהל חדש: מנויים ב-Kaching — חשוב מאוד",
    "intro": "**למה:** אין לנו אזור ניהול מנוי באתר. כל קישור \"ניהול המנוי\" ו\"עדכון אמצעי תשלום\" במיילים של המנוי פותח וואטסאפ "
             "לשירות, ולכן כל הבקשות האלה מגיעות אלינו. ⛔ לא שולחים ללקוח קישור לאזור ניהול מנויים באתר, כי הוא לא קיים.",
    "sections": [
        {"head": "1. \"עדכון אמצעי תשלום\" / \"התשלום לא עבר\":",
         "lines": ["Kaching ← Subscriptions ← המנוי של הלקוח ← Payment method ← ⋮ ← **\"Send link to update card\"**. אחר כך עונים:",
                   "\"שלחנו לך מייל עם קישור מאובטח לעדכון הכרטיס\"",
                   "באותו יום, לא מחכים."]},
        {"head": "2. שינוי / דילוג / דחייה (תאריך, תדירות, כמות, מוצר):",
         "lines": ["מבצעים ב-Kaching על המנוי של הלקוח, ומאשרים לו מה השתנה ומתי המשלוח הבא."]},
        {"head": "3. ביטול:",
         "lines": ["מציעים פעם אחת את אפשרויות השימור (לפי המותג — למטה).",
                   "אם הלקוח עדיין רוצה לבטל: **מבטלים מיד, באותו יום, לפני החיוב הבא**, ומאשרים לו שבוטל ושלא יהיו חיובים נוספים.",
                   "ביטול איטי מייצר צ'ארג'בקים (\u2066Brandon 13.10 [13:37]\u2069).",   # LRI/PDI: an LTR island, so the brackets don't mirror
                   "תופעת לוואי או סיבה רפואית: בלי הצעה, מבטלים מיד."]},
    ],
    "brand_head": "אפשרויות השימור בביטול — לפי מותג:",
    "brand_notes": {
        "rozela": "דחייה של המשלוח הבא בשבועיים או בחודש · החלפה למורינגה במשלוח הבא · 50% הנחה על המשלוח הבא (פעם אחת ללקוח).",
        "celesta": "דחייה של המשלוח הבא בשבועיים או בחודש · שינוי כמות או תדירות · 50% הנחה על המשלוח הבא (פעם אחת ללקוח).",
        "apexmen": "דחייה של המשלוח הבא בשבועיים או בחודש · 50% הנחה על המשלוח הבא (פעם אחת ללקוח).",
    },
    "brand_names": {"rozela": "Rozela", "celesta": "Celesta", "apexmen": "Apexmen"},
    "ack": "✅ קראתי והבנתי",
}
NOTICES = [KACHING_SUBS]
BY_ID = {n["id"]: n for n in NOTICES}


def applies(notice, user):
    if "admin" in (user.get("roles") or []):
        return True
    return any(b in (user.get("brands") or []) for b in notice["brands"])


def view(notice, user, acked_at):
    """What one user's screen gets: the brand notes of HIS brands (an admin with none of them sees all three)."""
    mine = [b for b in notice["brands"] if b in (user.get("brands") or [])] or list(notice["brands"])
    return {"id": notice["id"], "menu": notice["menu"], "title": notice["title"], "intro": notice["intro"],
            "sections": notice["sections"], "brand_head": notice["brand_head"],
            "brand_notes": [{"brand": b, "name": notice["brand_names"][b], "text": notice["brand_notes"][b]} for b in mine],
            "ack": notice["ack"], "acked": acked_at is not None, "acked_at": acked_at}


class AckStore:
    """{"acks": {"<user>": {"<notice id>": ts}}} in one JSON file. Read-modify-write under a thread lock + flock, temp + fsync + replace."""

    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            return {"acks": {}}
        if not isinstance(d, dict) or not isinstance(d.get("acks"), dict):
            raise RuntimeError("notice acks file is not an acks file")          # never start over an unreadable file
        return d

    def acks_of(self, user):
        with self._lock:
            fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH)
                return dict(self._read()["acks"].get(user) or {})
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def ack(self, user, notice_id):
        """-> (acked_at, created). A second ack keeps the FIRST timestamp."""
        with self._lock:
            fd = os.open(self.path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                d = self._read()
                mine = d["acks"].setdefault(user, {})
                if notice_id in mine:
                    return mine[notice_id], False
                mine[notice_id] = round(self.clock(), 3)
                tmp = tempfile.NamedTemporaryFile("w", dir=os.path.dirname(os.path.abspath(self.path)), delete=False, encoding="utf-8")
                try:
                    with tmp:
                        json.dump(d, tmp, ensure_ascii=False)
                        tmp.flush()
                        os.fsync(tmp.fileno())
                    os.chmod(tmp.name, 0o600)
                    os.replace(tmp.name, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp.name)
                    except OSError:
                        pass
                    raise
                return mine[notice_id], True
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)


class PgAckStore:
    """Same contract on the core Postgres (pgstore.SCHEMA: screen_notice_acks). One INSERT ... ON CONFLICT DO NOTHING: two
    instances side by side during a deploy can never write two acks or move the first timestamp."""

    def __init__(self, db, clock=time.time):
        self.db, self.clock = db, clock

    def acks_of(self, user):
        return {r[0]: r[1] for r in self.db.q("select notice_id, acked_at from screen_notice_acks where username=%s", (user,))}

    def ack(self, user, notice_id):
        def go(c):
            got = c.execute("insert into screen_notice_acks(username, notice_id, acked_at) values (%s,%s,%s) "
                            "on conflict (username, notice_id) do nothing returning acked_at",
                            (user, notice_id, round(self.clock(), 3))).fetchone()
            if got:
                return got[0], True
            return c.execute("select acked_at from screen_notice_acks where username=%s and notice_id=%s",
                             (user, notice_id)).fetchone()[0], False
        return self.db.run(go, tx=True)


def register(app, d):
    """d: api_user, json_error, ui_lang, store (users: audit), acks (AckStore | PgAckStore)."""
    acks, users = d["acks"], d["store"]

    @app.get("/api/notice")
    def notice_list():
        u, err = d["api_user"]()
        if err:
            return err
        mine = acks.acks_of(u["username"])
        resp = jsonify({"ok": True, "notices": [view(n, u, mine.get(n["id"])) for n in NOTICES if applies(n, u)]})
        resp.headers["Cache-Control"] = "no-store, private"
        return resp

    @app.post("/api/notice/ack")
    def notice_ack():
        u, err = d["api_user"]()
        if err:
            return err
        lang = d["ui_lang"](u)
        b = request.get_json(silent=True)
        nid = b.get("id") if isinstance(b, dict) else None
        if not isinstance(nid, str) or not ID_RE.match(nid) or nid not in BY_ID or not applies(BY_ID[nid], u):
            return d["json_error"]("bad_request", 400, lang)
        at, created = acks.ack(u["username"], nid)
        if created:
            users.audit(u["username"], "notice_acked", nid, {"acked_at": at})
        return jsonify({"ok": True, "id": nid, "acked_at": at, "already": not created})
