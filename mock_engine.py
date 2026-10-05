"""
mock_engine.py — a fake brand engine for local preview and screenshots (MOCK_ENGINE=1).

It is NOT a second engine: it exists so the SPA can be clicked and screenshot without a live call.
It still exercises the real path: the proxy mints a token per call and this module verifies it with a
Python port of Api.gs verifyToken_ (signature, exp/iat, 12h lifetime, role, brand), applies the Api.gs
role table and the args.brand check, and answers in Api.gs shapes. Kaching refusals use the gate's exact
English sentences (Kaching.gs) so the Hebrew translation is exercised too.

All names, emails, phones and orders below are invented.
"""

import base64
import copy
import hashlib
import hmac
import json
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone

MOCK_BRANDS = ("rozela", "celesta", "apexmen", "selera")      # velora on purpose has NO engine: it previews "not connected"
CS_ROLES = ("agent", "admin", "user-manager")
OPEN = ("ready", "action", "health", "delay")
SUMMARY_COLS = ['id', 'status', 'category', 'name', 'email', 'subject', 'summary', 'action', 'waiting_since',
                'created_at', 'handled_by', 'handled_at', 'language', 'order_no', 'channel', 'emails_count',
                'cancelled', 'watch', 'ship_state', 'recommendation', 'siblings']
TICKET_COLS = ['id', 'status', 'category', 'name', 'email', 'phone', 'channel', 'subject', 'summary', 'action',
               'draft_text', 'draft_id', 'thread_id', 'message_id', 'waiting_since', 'created_at', 'handled_by',
               'handled_at', 'language', 'order_no', 'order_date', 'tracking', 'carrier', 'ship_state', 'wa_sig',
               'wa_out', 'wa_send', 'notes', 'watch', 'emails_count', 'cancelled', 'recommendation', 'siblings']
WORK = ("agent", "admin")
TABLE = {"apiBoot": CS_ROLES, "apiStatus": CS_ROLES, "apiTicket": WORK, "apiTicketExtras": WORK, "apiTickets": WORK,
         "apiSearch": WORK, "apiSaveDraft": WORK, "apiSend": WORK, "apiMarkHandled": WORK, "apiClose": WORK,
         "apiNote": WORK, "apiKachingCancel": WORK, "apiAutoCancelList": WORK, "apiAutoCancelApprove": WORK,
         "apiAutoCancelReject": WORK, "apiSettings": ("admin",), "apiKnowledge": WORK, "apiCustomerLookup": WORK,
         "apiTicketFull": WORK, "apiChanges": WORK, "apiAutoReplyList": WORK, "apiAutoReplyReview": WORK, "apiWaTakeOver": WORK}
CONTRACT_RE_PREFIX = "gid://shopify/SubscriptionContract/"


def _iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def verify_token(token, secret, brand, now_s=None):
    """Port of Api.gs verifyToken_. Returns (ok, claims_or_reason)."""
    if len(secret) < 32:
        return False, "TOKEN_SECRET missing or too short"
    if not isinstance(token, str) or len(token) < 10 or len(token) > 4096:
        return False, "malformed"
    parts = token.split(".")
    import re
    if len(parts) != 2 or not re.match(r"^[A-Za-z0-9_-]+$", parts[0]) or not re.match(r"^[A-Za-z0-9_-]+$", parts[1]):
        return False, "malformed"
    want = _b64e(hmac.new(secret.encode(), parts[0].encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(want, parts[1]):
        return False, "bad signature"
    try:
        c = json.loads(_b64d(parts[0]).decode("utf-8"))
    except Exception:
        return False, "unreadable payload"
    now_s = int(now_s if now_s is not None else time.time())
    if not isinstance(c.get("exp"), int) or not isinstance(c.get("iat"), int):
        return False, "no exp/iat"
    if c["exp"] <= now_s:
        return False, "expired"
    if c["iat"] > now_s + 60:
        return False, "issued in the future"
    if c["exp"] - c["iat"] > 12 * 3600 + 60:
        return False, "lifetime too long"
    if not isinstance(c.get("user"), str) or not c["user"] or len(c["user"]) > 64:
        return False, "no user"
    if c.get("role") not in CS_ROLES:
        return False, "unknown role"
    if not isinstance(c.get("brands"), list) or brand.lower() not in [str(b).lower() for b in c["brands"]]:
        return False, "wrong brand"
    return True, {"user": c["user"], "role": c["role"], "brands": c["brands"], "lang": str(c.get("lang") or "he")[:5]}


# ---------- fixtures ----------

def _conv(now, *msgs):
    out = []
    for i, (who, hours_ago, text) in enumerate(msgs):
        out.append({"id": "m%d" % i, "who": who, "at": _iso(now - timedelta(hours=hours_ago)), "text": text})
    return out


def _order(now, name, days_ago, items, ful="FULFILLED", pay="PAID", shipped_days_ago=None, track_no=None):
    o = {"id": "gid://shopify/Order/%d" % (5000000 + int(name[1:])), "name": name,
         "createdAt": _iso(now - timedelta(days=days_ago)), "financialStatus": pay, "fulfillmentStatus": ful,
         "items": [{"title": t, "quantity": q} for t, q in items], "fulfillments": []}
    if shipped_days_ago is not None:
        o["fulfillments"].append({"createdAt": _iso(now - timedelta(days=shipped_days_ago)), "tracking": [
            {"company": "JYTD", "number": track_no or "JY%d" % random.randint(10 ** 9, 10 ** 10),
             "url": "https://t.17track.net/en#nums=" + (track_no or "JY0000000000")}]})
    return o


def _sub(cid, status, every, items, created_days, now, last_pay="SUCCEEDED", next_days=None):
    s = {"id": CONTRACT_RE_PREFIX + cid, "status": status, "every": every, "createdAt": _iso(now - timedelta(days=created_days)),
         "lastPaymentStatus": last_pay, "lines": [{"title": t, "quantity": q} for t, q in items]}
    if next_days is not None:
        s["nextBillingDate"] = _iso(now + timedelta(days=next_days))
    return s


def _ship(o, now, normal=14, late=21):
    if not o:
        return {"state": "unknown", "reason": "no order data", "normalDays": normal, "lateDays": late}
    days = (now - datetime.fromisoformat(o["createdAt"].replace("Z", "+00:00"))).days
    st = "very_late" if days > late else ("late" if days > normal else "not_late")
    tr = (o["fulfillments"][0]["tracking"][0] if o["fulfillments"] else None)
    return {"state": st, "orderName": o["name"], "daysSinceOrder": days, "shipped": bool(o["fulfillments"]),
            "normalDays": normal, "lateDays": late, "trackingUrl": tr["url"] if tr else "",
            "trackingNumber": tr["number"] if tr else "", "carrier": tr["company"] if tr else ""}


def build_brand(brand, now):
    P = {"rozela": ("Rozela", "רוזלה סלק — 60 כמוסות"), "celesta": ("Celesta", "סלסטה קולגן"),
         "velora": ("Velora", "ולורה — כדורי דלעת לשיער"), "apexmen": ("ApexMen", "אייפקס מן — 60 כמוסות"),
         "selera": ("Selera", "סלרה — תה צמחים")}[brand]
    name, product = P
    tickets, snaps, archive = [], {}, []

    def add(t, conv, orders=(), subs=(), arch=False):
        row = {c: "" for c in TICKET_COLS}
        row.update(t)
        row.setdefault("thread_id", t["id"][1:])
        row["emails_count"] = row.get("emails_count") or sum(1 for m in conv if m["who"] == "customer")
        orders = list(orders)
        sh = _ship(orders[0] if orders else None, now)
        if orders and not row.get("order_no"):
            row["order_no"] = orders[0]["name"]
            row["order_date"] = orders[0]["createdAt"]
            row["tracking"] = sh.get("trackingUrl", "")
            row["carrier"] = sh.get("carrier", "")
        row["ship_state"] = sh["state"]
        row["recommendation"] = row.get("recommendation") or RECO.get(row.get("category"), RECO["other"])
        (archive if arch else tickets).append(row)
        snaps[row["id"]] = {"orders": orders, "subscriptions": list(subs), "shipping": sh, "conversation": conv,
                            "lookup": "ok" if orders else "none"}

    sig = "\n\nיהודה\nצוות " + name
    h = lambda x: _iso(now - timedelta(hours=x))

    if brand == "rozela":
        o9 = _order(now, "#4516", 5, [(product, 1)], shipped_days_ago=3, track_no="JY4516000777")
        add({"id": "t18f2c01", "status": "sent", "category": "shipping", "name": "טל ברק", "email": "tal.b@example.com", "channel": "email",
             "subject": "מתי מגיע?", "summary": "שאלה פשוטה על זמן משלוח — נענתה אוטומטית עם קישור מעקב.", "created_at": h(3),
             "handled_by": "auto-reply", "handled_at": h(2.5), "language": "he",
             "recommendation": "לוודא שקישור המעקב נכון ושהטון חם. אם תקין — לסמן נבדק.",
             "draft_text": "היי טל, ההזמנה יצאה לפני 3 ימים ונמצאת בדרך: https://t.17track.net/en#nums=JY4516000777\nבדרך כלל זה מגיע תוך שבוע-שבועיים." + sig},
            _conv(now, ("customer", 3, "היי, מתי ההזמנה שלי אמורה להגיע?"),
                  ("us", 2.5, "היי טל, ההזמנה יצאה לפני 3 ימים ונמצאת בדרך: https://t.17track.net/en#nums=JY4516000777\nבדרך כלל זה מגיע תוך שבוע-שבועיים." + sig)),
            [o9])
        add({"id": "t18f2c02", "status": "ready", "category": "product", "name": "אילנה ג.", "email": "ilana.g@example.com", "channel": "email",
             "subject": "אפשר עם קפה?", "summary": "שואלת אם אפשר לקחת את הכמוסות עם קפה.", "waiting_since": h(1.2), "created_at": h(1.2),
             "language": "he", "recommendation": "תשובה פשוטה מהמדיניות — אפשר לשלוח כמו שהיא.",
             "draft_text": "היי אילנה, כן, אפשר לקחת גם עם קפה. הכי נוח עם ארוחה." + sig},
            _conv(now, ("customer", 1.2, "שלום, אפשר לקחת את הכמוסות יחד עם קפה בבוקר?")))
        add({"id": "t18f2c03", "status": "sent", "category": "shipping", "name": "רועי", "email": "roi@example.com", "channel": "email",
             "subject": "מספר מעקב", "summary": "ביקש מספר מעקב — נשלח אוטומטית.", "created_at": h(28), "handled_by": "auto-reply",
             "handled_at": h(27), "language": "he", "recommendation": "נבדק — אין מה לעשות."},
            _conv(now, ("customer", 28, "אפשר מספר מעקב?"), ("us", 27, "היי רועי, הנה הקישור למעקב." + sig)))
        o1 = _order(now, "#4512", 6, [(product, 2)], shipped_days_ago=4, track_no="JY4512778810")
        add({"id": "t18f2a01", "status": "ready", "category": "shipping", "name": "מיכל לוי", "email": "michal.levi@example.com",
             "phone": "+972521234567", "channel": "email", "subject": "איפה ההזמנה שלי?",
             "summary": "שואלת איפה ההזמנה #4512 — נשלחה לפני 4 ימים, עדיין בזמן.", "waiting_since": h(2.2), "created_at": h(2.2),
             "language": "he",
             "draft_text": "היי מיכל, ההזמנה שלך יצאה אלינו לפני 4 ימים ונמצאת בדרך\nאפשר לעקוב כאן: https://t.17track.net/en#nums=JY4512778810\nבדרך כלל זה מגיע תוך שבוע-שבועיים מההזמנה, אז את עדיין בטווח." + sig},
            _conv(now, ("customer", 2.2, "היי, הזמנתי לפני כמעט שבוע ועוד לא קיבלתי כלום. אפשר לדעת איפה זה עומד?\nתודה, מיכל")),
            [o1])
        add({"id": "t18f2a02", "status": "ready", "category": "product", "name": "רונית אברהם", "email": "ronit.a@example.com",
             "channel": "email", "subject": "שאלה על המינון", "summary": "שואלת כמה כמוסות לוקחים ביום ואם אפשר עם ארוחה.",
             "waiting_since": h(5), "created_at": h(5), "language": "he",
             "draft_text": "היי רונית, לוקחים 2 כמוסות ביום, הכי נוח עם ארוחה ועם כוס מים.\nאם את לוקחת תרופות קבועות, שווה לשאול את הרופא לפני." + sig},
            _conv(now, ("customer", 5, "שלום, קיבלתי את החבילה. כמה כמוסות צריך לקחת ביום? ואפשר עם אוכל?")),
            [_order(now, "#4498", 9, [(product, 1)], shipped_days_ago=7, track_no="JY4498120033")])
        sub_cid = "9876543210123"
        add({"id": "t18f2a03", "status": "action", "category": "cancel_subscription", "name": "יוסי מזרחי", "siblings": 1,
             "email": "yossi.m@example.com", "phone": "+972544445566", "channel": "email", "subject": "Re: ההזמנה שלך נשלחה",
             "summary": "כועס: לא ביקש מנוי, חויב שוב. רוצה לבטל מיד ומאיים בביטול עסקה.",
             "action": "cancel: " + CONTRACT_RE_PREFIX + sub_cid, "waiting_since": h(26), "created_at": h(30), "language": "he",
             "draft_text": "היי יוסי, ביטלתי את המנוי כך שלא יהיו חיובים נוספים. ההזמנה האחרונה כבר בדרך אליך." + sig},
            _conv(now,
                  ("customer", 30, "למה חייבתם אותי שוב?? לא ביקשתי שום מנוי."),
                  ("us", 29, "היי יוסי, מבינים את התסכול. המנוי נבחר בעמוד התשלום, אבל אפשר לבטל אותו מתי שרוצים. רוצה שנבטל?\n\nיהודה\nצוות Rozela"),
                  ("customer", 26, "כן ברור שאני רוצה לבטל!!\nאם זה לא מבוטל היום אני פונה לחברת האשראי.\n\nOn Mon, Oct 3, 2026 at 10:12 Rozela <support@tryrozela.com> wrote:\n> היי יוסי, מבינים את התסכול. המנוי נבחר בעמוד התשלום,\n> אבל אפשר לבטל אותו מתי שרוצים. רוצה שנבטל?")),
            [_order(now, "#4530", 2, [(product, 1)], ful="UNFULFILLED"), _order(now, "#4310", 32, [(product, 1)], shipped_days_ago=30, track_no="JY4310009911")],
            [_sub(sub_cid, "ACTIVE", "1 month", [(product, 1)], 32, now, next_days=28),
             _sub("1112223334441", "CANCELLED", "2 month", [(product, 2)], 200, now)])
        add({"id": "t18f2a04", "status": "action", "category": "return_refund", "name": "דנה כהן", "email": "dana.cohen@example.com",
             "channel": "email", "subject": "החזר כספי", "summary": "מבקשת החזר מלא לפי האחריות של 90 יום — פתחה בקבוק אחד.",
             "action": "refund request: a human decides (refunds are done by hand)", "waiting_since": h(8), "created_at": h(8), "language": "he",
             "draft_text": "היי דנה, אין בעיה, ההחזר לפי האחריות של 90 יום הוא מלא גם על בקבוק פתוח. אני מעבירה את זה לטיפול ותקבלי עדכון כשההחזר יוצא." + sig},
            _conv(now, ("customer", 8, "היי, ניסיתי חודש ולא הרגשתי הבדל. אני רוצה להחזיר ולקבל את הכסף, ראיתי שיש אחריות 90 יום.")),
            [_order(now, "#4402", 33, [(product, 2)], shipped_days_ago=31, track_no="JY4402556677")])
        add({"id": "t18f2a05", "status": "health", "category": "health", "name": "שירה בן דוד", "email": "shira.bd@example.com",
             "channel": "email", "subject": "תופעת לוואי", "summary": "מדווחת על פריחה בידיים מאז שהתחילה לקחת. צריך מענה אנושי.",
             "action": "health: possible adverse effect — a human answers, owner alerted", "waiting_since": h(1), "created_at": h(1), "language": "he",
             "draft_text": "היי שירה, תודה שעדכנת. ממליצים להפסיק לקחת עד שתתייעצי עם רופא. נשמח לעזור עם החזר אם צריך." + sig},
            _conv(now, ("customer", 1, "מאז שהתחלתי לקחת את הכמוסות יש לי פריחה בידיים. זה קשור?")),
            [_order(now, "#4505", 12, [(product, 1)], shipped_days_ago=10, track_no="JY4505001122")])
        add({"id": "t18f2a06", "status": "delay", "category": "shipping", "name": "אבי פרץ", "email": "avi.peretz@example.com",
             "channel": "email", "subject": "עדיין לא הגיע", "summary": "הזמנה #4377 לפני 24 יום, עוד לא הגיעה — עיכוב אמיתי.",
             "action": "delay: order is past the late threshold", "waiting_since": h(20), "created_at": h(20), "language": "he",
             "draft_text": "היי אבי, אתה צודק, זה לוקח יותר מהרגיל ואני מצטער על זה. בדקתי, החבילה בדרך: https://t.17track.net/en#nums=JY4377445566\nאם עד סוף השבוע זה לא אצלך, תכתוב לי ונשלח חדשה." + sig},
            _conv(now, ("customer", 20, "הזמנתי לפני יותר משלושה שבועות. מה קורה?")),
            [_order(now, "#4377", 24, [(product, 1)], shipped_days_ago=21, track_no="JY4377445566")])
        add({"id": "t18f2a07", "status": "delay", "category": "shipping", "name": "Olga Petrova", "email": "olga.p@example.com",
             "channel": "email", "subject": "Где мой заказ?", "summary": "לקוחה דוברת רוסית: הזמנה לפני 16 יום, עוד לא הגיעה.",
             "action": "delay: late", "waiting_since": h(14), "created_at": h(14), "language": "ru",
             "draft_text": "Здравствуйте, Ольга! Заказ уже в пути, вот ссылка для отслеживания: https://t.17track.net/en#nums=JY4421337799\nОбычно доставка занимает до трёх недель.\n\nYehuda\nRozela Team"},
            _conv(now, ("customer", 14, "Здравствуйте, я заказала 16 дней назад и ещё ничего не получила.")),
            [_order(now, "#4421", 16, [(product, 1)], shipped_days_ago=13, track_no="JY4421337799")])
        add({"id": "t18f2a08", "status": "sent", "category": "product", "name": "נועה שמש", "email": "noa.s@example.com",
             "channel": "email", "subject": "אפשר לקחת בהריון?", "summary": "שאלה על הריון — נענתה: להתייעץ עם רופא.",
             "waiting_since": "", "created_at": h(10), "handled_by": "manager", "handled_at": h(3), "language": "he",
             "draft_text": "היי נועה, בהריון הכי נכון להתייעץ קודם עם הרופא/ה. אם יאשרו, המינון הוא 2 כמוסות ביום." + sig},
            _conv(now, ("customer", 10, "היי, אני בהריון, אפשר לקחת?"),
                  ("us", 3, "היי נועה, בהריון הכי נכון להתייעץ קודם עם הרופא/ה. אם יאשרו, המינון הוא 2 כמוסות ביום.\n\nיהודה\nצוות Rozela")))
        add({"id": "t18f2a09", "status": "done", "category": "order_change", "name": "משה גולן", "email": "moshe.g@example.com",
             "channel": "email", "subject": "שינוי כתובת", "summary": "ביקש לשנות כתובת למשלוח — עודכן בשופיפיי ידנית.",
             "created_at": h(6), "handled_by": "agent-one", "handled_at": h(1.5), "language": "he"},
            _conv(now, ("customer", 6, "עברתי דירה, אפשר לשנות את הכתובת להזמנה?")),
            [_order(now, "#4529", 1, [(product, 1)], ful="UNFULFILLED")])
        add({"id": "t18f2a10", "status": "done", "category": "other", "name": "ליאת", "email": "liat@example.com",
             "channel": "email", "subject": "תודה!", "summary": "הודתה על השירות.", "created_at": h(40),
             "handled_by": "manager", "handled_at": h(30), "language": "he"},
            _conv(now, ("customer", 40, "רק רציתי להגיד תודה, הגיע מהר!")))
        add({"id": "w8ab77c1", "status": "action", "category": "other", "name": "עומר", "phone": "+972537778899",
             "channel": "whatsapp", "subject": "WhatsApp", "summary": "הודעת וואטסאפ חדשה",
             "action": "whatsapp: no automatic draft in this phase", "waiting_since": h(0.6), "created_at": h(0.6), "language": "he"},
            _conv(now, ("customer", 0.6, "היי יש לכם משלוח לאילת?")))
        for n, days in (("00", 82), ("01", 84)):
            add({"id": "w8ab77" + n, "status": "ready", "category": "other", "name": "לקוחה %s" % n, "phone": "+97250000%s11" % n,
                 "channel": "whatsapp", "subject": "WhatsApp", "summary": "תגובה להודעת עגלה נטושה מיולי.",
                 "waiting_since": _iso(now - timedelta(days=days)), "created_at": _iso(now - timedelta(days=days)), "language": "he",
                 "draft_text": "היי, תודה שחזרת אלינו!" + sig}, _conv(now, ("customer", days * 24, "כן מה המחיר?")))
        add({"id": "t18f2a11", "status": "action", "category": "shipping", "name": "אגי ל.", "email": "agi.l@example.com", "channel": "email",
             "subject": "עיכוב", "summary": "שואלת על הזמנה #4400 — 19 ימים מההזמנה.", "waiting_since": h(4), "created_at": h(4), "language": "he",
             "order_no": "#4400", "draft_text": "היי אגי, ההזמנה בדרך." + sig}, _conv(now, ("customer", 4, "איפה הזמנה 4400?")))
        snaps["t18f2a11"]["shipping"] = {"state": "late", "orderName": "#4400", "daysSinceOrder": 19,      # new engine: no thresholds
                                         "shipped": True, "trackingUrl": "", "trackingNumber": "", "carrier": ""}
        snaps["t18f2a11"]["notes"] = {"orders": "chip_only", "subscriptions": "error", "orderNo": "#4400"}
        add({"id": "t18f2a12", "status": "merged", "category": "shipping", "name": "מיכל לוי", "email": "michal.levi@example.com",
             "channel": "email", "subject": "עוד שאלה", "summary": "אוחד לפנייה של מיכל לוי.", "created_at": h(30),
             "handled_by": "engine", "handled_at": h(29), "language": "he"}, _conv(now, ("customer", 30, "ושוב שאלה")))
        bot_conv = _conv(now, ("customer", 0.9, "היי, הגיע לי בקבוק שבור, מצרפת תמונות"), ("us", 0.85, "היי! מצטערים לשמוע, אפשר לשלוח תמונה של הבקבוק?"),
                         ("customer", 0.8, "הנה"))
        bot_conv[0]["photos"] = [{"ref": "m1-0", "file": None, "unavailable": True}]
        bot_conv[2]["photos"] = [{"ref": "m3-0", "file": {"id": "f1", "url": "https://drive.google.com/file/d/f1/view", "w": 800, "h": 600}},
                                 {"ref": "m3-1", "file": None}]
        bot_conv[1]["author"] = "ai"
        add({"id": "w8ab77c2", "status": "bot", "category": "complaint", "name": "שני", "phone": "+972548889911", "channel": "whatsapp",
             "subject": "WhatsApp", "summary": "בקבוק הגיע שבור — הבוט של דונדי מבקש תמונות.", "action": "whatsapp: Dondy bot is handling this chat",
             "waiting_since": h(0.8), "created_at": h(0.9), "language": "he",
             "recommendation": "הבוט מטפל. לקחת את השיחה רק אם הלקוחה מבקשת אדם או שהבוט נתקע."}, bot_conv)
        add({"id": "t17aa001", "status": "done", "category": "shipping", "name": "מיכל לוי", "email": "michal.levi@example.com",
             "channel": "email", "subject": "מתי זה מגיע?", "summary": "שאלה על זמני משלוח, נענתה.", "created_at": _iso(now - timedelta(days=60)),
             "handled_by": "manager", "handled_at": _iso(now - timedelta(days=60)), "language": "he"},
            _conv(now, ("customer", 1440, "מתי זה מגיע?")), arch=True)
        add({"id": "t17aa002", "status": "done", "category": "billing", "name": "יוסי מזרחי", "email": "yossi.m@example.com",
             "channel": "email", "subject": "חיוב כפול?", "summary": "שאל על חיוב — הוסבר שזה מנוי.", "created_at": _iso(now - timedelta(days=35)),
             "handled_by": "manager", "handled_at": _iso(now - timedelta(days=35)), "language": "he"},
            _conv(now, ("customer", 840, "רואה שני חיובים")), arch=True)
    else:
        add({"id": "t%s01" % brand[:4], "status": "ready", "category": "shipping", "name": "אורית ש.", "email": "orit.%s@example.com" % brand,
             "channel": "email", "subject": "מתי זה מגיע?", "summary": "שואלת מתי ההזמנה תגיע — עדיין בזמן.", "waiting_since": h(3),
             "created_at": h(3), "language": "he", "draft_text": "היי אורית, ההזמנה בדרך ונמצאת עדיין בזמן המשלוח הרגיל." + sig},
            _conv(now, ("customer", 3, "היי, מתי ההזמנה מגיעה?")),
            [_order(now, "#2210", 5, [(product, 1)], shipped_days_ago=3, track_no="JY2210000001")])
        if brand == "selera":
            return {"name": name, "tickets": tickets, "archive": archive, "snaps": snaps}
        add({"id": "t%s02" % brand[:4], "status": "action", "category": "cancel_subscription", "name": "רמי ק.", "email": "rami.%s@example.com" % brand,
             "channel": "email", "subject": "לא ביקשתי מנוי", "summary": "טוען שלא ביקש מנוי; חויב שוב.",
             "action": "cancel: " + CONTRACT_RE_PREFIX + "5550001112223", "waiting_since": h(9), "created_at": h(9), "language": "he",
             "draft_text": "היי רמי, ההזמנה כבר בהכנה. אפשר להשהות את המנוי לחודש או לבטל — מה מעדיף?" + sig},
            _conv(now, ("customer", 9, "לא ביקשתי שום מנוי ולקחו לי כסף שוב.")),
            [_order(now, "#2215", 1, [(product, 1)], ful="UNFULFILLED")],
            [_sub("5550001112223", "ACTIVE", "1 month", [(product, 1)], 31, now)])
    for wid in ("w8ab77c1", "w8ab77c2"):                       # new-engine notes on the WhatsApp chats (no email)
        if wid in snaps:
            snaps[wid]["notes"] = {"orders": "not_checked", "subscriptions": "not_checked_no_email"}
    return {"name": name, "tickets": tickets, "archive": archive, "snaps": snaps}


RECO = {
    "shipping": "לשלוח את הטיוטה — ההזמנה בזמן; לוודא שקישור המעקב נכון.",
    "product": "לשלוח את הטיוטה אחרי בדיקה מהירה של המינון.",
    "cancel_subscription": "לבטל את המנוי בכפתור בפאנל המנויים, ואז לשלוח את הטיוטה.",
    "return_refund": "לבצע החזר בשופיפיי לפי האחריות של 90 יום, ואז לשלוח את הטיוטה.",
    "health": "לא לשלוח טיוטה בלי בדיקה — להמליץ להפסיק ולהתייעץ עם רופא.",
    "order_change": "לעדכן את הכתובת בשופיפיי ולסגור.",
    "billing": "לבדוק את החיוב בשופיפיי ולענות.",
    "other": "לקרוא ולענות.",
}


def build_auto_reply(brand, now):
    """apiAutoReplyList items in the coordinator's shape (2026-10-05). Item id = ticket id."""
    if brand != "rozela":
        return []
    return [
        {"id": "t18f2c01", "email": "ta***@example.com", "subject": "מתי מגיע?", "summary": "שאלה פשוטה על זמן משלוח.",
         "replyText": "היי טל, ההזמנה יצאה לפני 3 ימים ונמצאת בדרך: https://t.17track.net/en#nums=JY4516000777\nבדרך כלל זה מגיע תוך שבוע-שבועיים.\n\nיהודה\nצוות Rozela",
         "sentAt": _iso(now - timedelta(hours=2.5)), "state": "sent", "review": "pending", "reviewedBy": ""},
        {"id": "t18f2c02", "email": "il***@example.com", "subject": "אפשר עם קפה?", "summary": "שואלת אם אפשר עם קפה.",
         "replyText": "היי אילנה, כן, אפשר לקחת גם עם קפה. הכי נוח עם ארוחה.\n\nיהודה\nצוות Rozela",
         "dueAt": None, "state": "shadow_would_send", "review": "pending", "reviewedBy": ""},
        {"id": "t18f2c03", "email": "ro***@example.com", "subject": "מספר מעקב", "summary": "ביקש מספר מעקב.",
         "replyText": "היי רועי, הנה הקישור למעקב.\n\nיהודה\nצוות Rozela", "sentAt": _iso(now - timedelta(hours=27)),
         "state": "sent", "review": "ok", "reviewedBy": "manager"},
    ]


def build_auto(brand, now):
    """Auto-cancel records in the FINAL engine shape (coordinator, 2026-10-05). Item id = ticket id."""
    if brand != "rozela":
        return []
    base = lambda **kw: dict({"approvedBy": "", "error": "", "dueAt": None}, **kw)
    return [
        base(id="t18f2a03", email="yo***@example.com", contractId=CONTRACT_RE_PREFIX + "9876543210123",
             nextBilling=_iso(now + timedelta(days=28)), state="shadow_would_cancel", subject="Re: ההזמנה שלך נשלחה",
             summary="כועס: לא ביקש מנוי, חויב שוב. רוצה לבטל מיד.", ticketStatus="action",
             replyText="היי יוסי, ביטלתי את המנוי. לא יהיו חיובים נוספים, וההזמנה האחרונה כבר בדרך אליך.\n\nיהודה\nצוות Rozela",
             evidence={"dkim": "pass", "spf": "pass", "contractCount": 1, "modelReason": "single request: cancel the subscription"}),
        base(id="t18f2b11", email="ha***@example.com", contractId=CONTRACT_RE_PREFIX + "4445556667778",
             nextBilling=_iso(now + timedelta(days=3)), state="queued", dueAt=_iso(now + timedelta(minutes=6)), approvedBy="manager",
             subject="ביטול מנוי", summary="מבקשת לבטל את המנוי, בלי סיבה נוספת.", ticketStatus="action",
             replyText="היי חנה, ביטלתי את המנוי, לא יהיו חיובים נוספים.\n\nיהודה\nצוות Rozela",
             evidence={"dkim": "pass", "spf": "pass", "contractCount": 1, "modelReason": "single request: cancel"}),
        base(id="t18f2b12", email="ga***@example.com", contractId=CONTRACT_RE_PREFIX + "1212121212129",
             nextBilling=_iso(now + timedelta(days=12)), state="cancelled_reply_failed", approvedBy="agent-two",
             subject="תבטלו", summary="ביקש ביטול; המנוי בוטל אבל התשובה לא נשלחה.", ticketStatus="action",
             replyText="היי, ביטלתי את המנוי.\n\nיהודה\nצוות Rozela", error="gmail send failed: quota",
             evidence={"dkim": "pass", "spf": "pass", "contractCount": 1, "modelReason": "single request: cancel"}),
        base(id="t18f2b13", email="ro***@example.com", contractId=CONTRACT_RE_PREFIX + "7778889990001",
             nextBilling=_iso(now + timedelta(days=9)), state="aborted_human", subject="מנוי",
             summary="ביקשה לבטל; נציג ענה ידנית ב-Gmail לפני שהתור רץ.", ticketStatus="sent",
             replyText="היי רונית, ביטלתי את המנוי.\n\nיהודה\nצוות Rozela", error="a human replied in Gmail first; nothing was cancelled",
             evidence={"dkim": "pass", "spf": "fail", "contractCount": 2, "modelReason": "cancel + refund request"}),
    ]


class MockEngines:
    def __init__(self, secret, latency_ms=None):
        self.secret = secret
        self.latency = (int(os.environ.get("MOCK_LATENCY_MS", "250")) if latency_ms is None else latency_ms) / 1000.0
        self.lock = threading.Lock()
        now = datetime.now(timezone.utc)
        self.brands = {b: build_brand(b, now) for b in MOCK_BRANDS}
        # rozela: live-like switches (send on, cancels on); celesta: like today's real state (dry run, cancels off)
        self.switches = {"rozela": {"dry": False, "writes": True, "frozen": "", "auto": "shadow", "reply": "on"},
                         "celesta": {"dry": True, "writes": False, "frozen": "", "auto": "off"},
                         "selera": {"dry": True, "writes": False, "frozen": "", "auto": "off"},
                         "apexmen": {"dry": True, "writes": True, "frozen": "2026-10-05T09:00:00Z — daily limit of 100 cancellations reached", "auto": "off"}}
        self.auto = {b: build_auto(b, now) for b in MOCK_BRANDS}
        self.autoreply = {b: build_auto_reply(b, now) for b in MOCK_BRANDS}
        self.version = {b: 1 for b in MOCK_BRANDS}
        self.touched = {b: {} for b in MOCK_BRANDS}     # ticket id -> version of its last change

    def transport(self, url, body):
        brand = url.split("mock://", 1)[1]
        if self.latency:
            time.sleep(self.latency)
        with self.lock:
            out = self.dispatch(brand, body)
            if out.get("ok") and body.get("fn") in ("apiSaveDraft", "apiSend", "apiMarkHandled", "apiClose", "apiNote", "apiKachingCancel"):
                self.version[brand] += 1
                self.touched[brand][(body.get("args") or {}).get("id")] = self.version[brand]
            return out

    def dispatch(self, brand, req):
        fail = lambda e, **kw: dict({"ok": False, "error": e}, **kw)
        fn = req.get("fn")
        ok, claims = verify_token(req.get("token"), self.secret, brand)
        if not ok:
            return fail("unauthorized")
        if fn not in TABLE or claims["role"] not in TABLE[fn]:
            return fail("unauthorized")
        args = req.get("args") or {}
        if "brand" in args and str(args["brand"]).lower() != brand:
            return fail("unauthorized")
        return getattr(self, fn)(brand, args, claims)

    # ---------- helpers ----------
    def _b(self, brand):
        return self.brands[brand]

    def _find(self, brand, tid, archive=False):
        for t in self._b(brand)["tickets"] + (self._b(brand)["archive"] if archive else []):
            if t["id"] == tid:
                return t
        return None

    @staticmethod
    def _now():
        return _iso(datetime.now(timezone.utc))

    @staticmethod
    def _problem(text):
        low = text.lower()
        if not text.strip():
            return "empty draft"
        if "[name]" in low or "{{" in text:
            return "leftover placeholder"
        if "100%" in text or "מובטח" in text or "guaranteed" in low:
            return "promise or cure claim"
        return None

    # ---------- API ----------
    def apiBoot(self, brand, a, c):
        b = self._b(brand)
        counts = {}
        for t in b["tickets"]:
            counts[t["status"]] = counts.get(t["status"], 0) + 1
        sw = self.switches[brand]
        return {"ok": True, "brand": brand, "brandName": b["name"], "user": c["user"], "role": c["role"], "lang": c["lang"],
                "counts": counts, "tickets": [{k: t[k] for k in SUMMARY_COLS} for t in b["tickets"]], "serverTime": self._now(),
                "dryRun": sw["dry"], "cancelEnabled": sw["writes"], "cancelFrozen": bool(sw["frozen"]),
                "subscriptions": "none" if brand == "selera" else "kaching", "version": self.version[brand]}

    def apiStatus(self, brand, a, c):
        sw = self.switches[brand]
        return {"ok": True, "brand": brand, "lastRun": self._now(), "stale": False, "lastError": None,
                "dryRun": sw["dry"], "cancelWrites": sw["writes"], "cancelFrozen": sw["frozen"] or None}

    def apiTicket(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        return {"ok": True, "ticket": copy.deepcopy(t)} if t else {"ok": False, "error": "not_found"}

    def apiTicketExtras(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "id": t["id"], "extras": copy.deepcopy(self._b(brand)["snaps"].get(t["id"], {}))}

    def apiTickets(self, brand, a, c):
        return {"ok": True, "tickets": [copy.deepcopy(t) for t in (self._find(brand, i) for i in a.get("ids", [])) if t]}

    def apiSearch(self, brand, a, c):
        q = str(a.get("q", "")).strip().lower()
        if len(q) < 2 or len(q) > 100:
            return {"ok": False, "error": "bad_query"}
        hits = []
        b = self._b(brand)
        for tab, rows in (("tickets", b["tickets"]), ("archive", b["archive"])):
            for t in rows:
                hay = "\n".join(str(t.get(k, "")) for k in ("id", "email", "name", "phone", "order_no", "subject", "summary")).lower()
                if q in hay and len(hits) < 50:
                    r = {k: t[k] for k in SUMMARY_COLS}
                    r["archived"] = tab == "archive"
                    hits.append(r)
        return {"ok": True, "tickets": hits}

    def apiSaveDraft(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        text = a.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return {"ok": False, "error": "bad_text"}
        if not t:
            return {"ok": False, "error": "not_found"}
        if t["status"] not in OPEN:
            return {"ok": False, "error": "not_open"}
        if "REFUSE-SAVE" in text:                  # preview-only trigger: lets the screenshot run prove the rollback path
            return {"ok": False, "error": "busy"}
        t["draft_text"] = text
        return {"ok": True, "problem": self._problem(text)}

    def apiSend(self, brand, a, c):
        text = a.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return {"ok": False, "error": "bad_text"}
        if self.switches[brand]["dry"]:
            return {"ok": False, "error": "dry_run"}
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        if t["status"] in ("sent", "done"):
            return {"ok": False, "error": "already_sent" if t["channel"] == "whatsapp" else "already_handled"}
        p = self._problem(text)
        if p and a.get("override") is not True:
            return {"ok": False, "error": "draft_problem", "problem": p}
        if t["channel"] == "whatsapp":                     # live engine (2026-10-05 08:14): wa_queued + double-send guard
            if t["status"] == "wa_queued" or t.get("wa_send") == "pending":
                return {"ok": True, "queued": True, "already": True}
            t.update({"wa_out": text, "wa_send": "pending", "status": "wa_queued", "handled_by": c["user"], "handled_at": self._now()})
            return {"ok": True, "queued": True}
        t.update({"status": "sent", "draft_text": text, "handled_by": c["user"], "handled_at": self._now(), "draft_id": ""})
        snap = self._b(brand)["snaps"].get(t["id"])
        if snap:
            snap["conversation"].append({"id": "m-sent", "who": "us", "at": self._now(), "text": text})
        return {"ok": True, "sent": True, "warnings": []}

    def _close(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        if t["status"] == "done":
            return {"ok": True, "noop": True}
        t.update({"status": "done", "handled_by": c["user"], "handled_at": self._now(), "draft_id": ""})
        return {"ok": True}

    apiMarkHandled = _close
    apiClose = _close

    def apiNote(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        text = a.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            return {"ok": False, "error": "bad_text"}
        if not t:
            return {"ok": False, "error": "not_found"}
        line = "[%s %s] %s" % (self._now()[:16], c["user"], text.strip())
        t["notes"] = (t["notes"] + "\n" if t.get("notes") else "") + line
        return {"ok": True}

    def apiKachingCancel(self, brand, a, c):
        """Mirrors Kaching.gs kachingCancelContract's checks, order and sentences."""
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        sw = self.switches[brand]
        res = lambda ok, msg, status=None: {"ok": ok, "status": status, "message": msg}
        if not sw["writes"]:
            return res(False, "cancellations are switched off")
        if sw["frozen"]:
            return res(False, "cancellations are frozen: " + sw["frozen"])
        if c["role"] not in ("admin", "agent"):
            return res(False, 'role "%s" may not cancel subscriptions' % c["role"])
        cid = a.get("contractId")
        if not isinstance(cid, str) or not cid.startswith(CONTRACT_RE_PREFIX) or not cid[len(CONTRACT_RE_PREFIX):].isdigit():
            return res(False, "exactly one valid contract id is required")
        if str(a.get("confirm", "")) != cid[-4:]:
            return res(False, "confirmation code does not match the contract")
        if not t.get("email"):
            return res(False, "ticket has no customer email")
        wants = str(t.get("action", "")).startswith("cancel:")
        reason = str(a.get("reason", "")).strip()
        if not wants and (len(reason) < 10 or len([w for w in reason.split() if len(w) >= 2]) < 2):
            return res(False, "no cancel request from the customer and no written reason")
        subs = self._b(brand)["snaps"].get(t["id"], {}).get("subscriptions", [])
        match = next((s for s in subs if s["id"] == cid), None)
        if not match:
            return res(False, "this contract does not belong to the ticket's customer")
        if match["status"] == "CANCELLED":
            return res(True, "already cancelled", "CANCELLED")
        if match["status"] not in ("ACTIVE", "PAUSED", "FAILED"):
            return res(False, "status %s cannot be cancelled" % match["status"])
        match["status"] = "CANCELLED"
        match.pop("nextBillingDate", None)
        done = [x for x in str(t.get("cancelled", "")).split(",") if x]
        if cid not in done:
            done.append(cid)
        t["cancelled"] = ",".join(done)
        return res(True, "cancelled", "CANCELLED")

    # ---------- auto-cancel + settings (FINAL engine shapes, coordinator 2026-10-05) ----------
    APPROVABLE = ("shadow_would_cancel", "aborted_newer", "refused")
    IN_FLIGHT = ("queued", "cancelling", "cancelled", "replying")

    def _mode(self, brand):
        sw = self.switches[brand]
        live = (not sw["dry"]) and sw["writes"] and sw["auto"] == "on"
        return "live" if live else ("shadow" if sw["auto"] != "off" else "off")

    def apiAutoCancelList(self, brand, a, c):
        return {"ok": True, "switch": self.switches[brand]["auto"], "mode": self._mode(brand), "items": copy.deepcopy(self.auto[brand])}

    def _auto_get(self, brand, iid):
        if not isinstance(iid, str) or not iid:
            return "bad_id", None
        it = next((x for x in self.auto[brand] if x["id"] == iid), None)
        if it:
            return None, it
        return ("no_auto_record" if self._find(brand, iid) else "not_found"), None

    def apiAutoCancelApprove(self, brand, a, c):
        err, it = self._auto_get(brand, a.get("id"))
        if err:
            return {"ok": False, "error": err}
        if it["state"] not in self.APPROVABLE:
            return {"ok": False, "error": "not_approvable", "state": it["state"]}
        text = a.get("replyText", it["replyText"])
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return {"ok": False, "error": "bad_text"}
        p = self._problem(text)
        if p:
            return {"ok": False, "error": "draft_problem", "problem": p}
        sw = self.switches[brand]
        if sw["dry"] or not sw["writes"]:
            return {"ok": False, "error": "live_switches_off", "reason": "DRY_RUN=on" if sw["dry"] else "KACHING_WRITES=off"}
        due = _iso(datetime.now(timezone.utc) + timedelta(minutes=5))
        it.update({"state": "queued", "dueAt": due, "approvedBy": c["user"], "replyText": text})
        return {"ok": True, "id": it["id"], "state": "queued", "dueAt": due, "approvedBy": c["user"]}

    def apiAutoCancelReject(self, brand, a, c):
        note = str(a.get("note", "")).strip()
        if not (2 <= len(note) <= 300):
            return {"ok": False, "error": "bad_note"}
        err, it = self._auto_get(brand, a.get("id"))
        if err:
            return {"ok": False, "error": err}
        if it["state"] in self.IN_FLIGHT:
            return {"ok": False, "error": "not_rejectable"}
        self.auto[brand].remove(it)
        return {"ok": True, "id": it["id"]}

    def apiSettings(self, brand, a, c):
        sw = self.switches[brand]
        cur = {"DRY_RUN": "on" if sw["dry"] else "off", "KACHING_WRITES": "on" if sw["writes"] else "off", "AUTO_CANCEL": sw["auto"],
               "AUTO_REPLY": sw.get("reply", "off")}
        action = a.get("action")
        if action == "get":
            return {"ok": True, "settings": cur}
        if action != "set":
            return {"ok": False, "error": "bad_action"}
        allowed = {"DRY_RUN": ["on", "off"], "KACHING_WRITES": ["on", "off"], "AUTO_CANCEL": ["off", "shadow", "on"],
                   "AUTO_REPLY": ["off", "shadow", "on"]}
        key, val = a.get("key"), a.get("value")
        if key not in allowed:
            return {"ok": False, "error": "bad_key"}
        if val not in allowed[key]:
            return {"ok": False, "error": "bad_value", "allowed": allowed[key]}
        if key == "AUTO_CANCEL" and val == "on" and (cur["DRY_RUN"] == "on" or cur["KACHING_WRITES"] != "on"):
            return {"ok": False, "error": "needs_live_switches", "reason": "AUTO_CANCEL=on needs DRY_RUN=off and KACHING_WRITES=on"}
        frm = cur[key]
        if frm == val:
            return {"ok": True, "key": key, "from": frm, "to": val, "noop": True}
        if key == "AUTO_REPLY" and val == "on" and cur["DRY_RUN"] == "on":
            return {"ok": False, "error": "needs_live_switches", "reason": "AUTO_REPLY=on needs DRY_RUN=off"}
        if key == "AUTO_REPLY":
            sw["reply"] = val
        elif key == "DRY_RUN":
            sw["dry"] = val == "on"
        elif key == "KACHING_WRITES":
            sw["writes"] = val == "on"
        else:
            sw["auto"] = val
        return {"ok": True, "key": key, "from": frm, "to": val}

    # ---------- phase 5: knowledge + customer lookup (FINAL engine shapes, coordinator 2026-10-05) ----------
    KNOWLEDGE = {
        "rozela": ("## Rozela — כמוסות סלק\n- 60 כמוסות בבקבוק, 2 ביום עם ארוחה.\n- תוסף תזונה, לא תחליף לתרופה; במקרים מיוחדים להתייעץ עם רופא.\n"
                   "- משלוח: נקודת איסוף חינם; עד הבית לפי ההזמנה.",
                   ["1. החזר כספי: אחריות 90 יום לפי עמוד המוצר — החזר מלא, גם על בקבוקים פתוחים, בלי עמלות.",
                    "2. ביטול מנוי: מיד לפי בקשה, בלי מחזור נוסף.",
                    "3. ביטול הזמנה: עד 24 שעות אם עוד לא נשלחה.",
                    "4. מחירי משלוח: לא מצטטים מהאתר — רק מה שמופיע בהזמנה של הלקוח."]),
        "selera": ("## Selera — תה צמחים\n- שקיק אחד ביום.", ["1. החזר כספי: 30 יום.", "2. אין מנויים במותג הזה."]),
    }

    def apiKnowledge(self, brand, a, c):
        k, pol = self.KNOWLEDGE.get(brand, ("## %s\n- (mock)" % self._b(brand)["name"], ["1. החזר כספי: לפי עמוד המוצר."]))
        return {"ok": True, "brand": brand, "brandName": self._b(brand)["name"], "knowledge": k, "policy": pol,
                "shippingDays": {"normal": 14, "late": 21}, "subscriptions": "none" if brand == "selera" else "kaching",
                "updatedAt": "2026-10-05T08:00:00Z"}

    def apiCustomerLookup(self, brand, a, c):
        q = str(a.get("q", "")).strip().lower()
        if not (2 <= len(q) <= 100):
            return {"ok": False, "error": "bad_query"}
        qtype = "email" if "@" in q else ("order" if q.lstrip("#").isdigit() and len(q.lstrip("#")) <= 7 else ("phone" if q.replace("+", "").isdigit() else "name"))
        b = self._b(brand)
        rows = [t for t in b["tickets"] + b["archive"]
                if q in "\n".join(str(t.get(k, "")) for k in ("email", "name", "phone", "order_no")).lower()]
        orders, subs, seen = [], [], set()
        now = datetime.now(timezone.utc)
        for t in rows:
            snap = b["snaps"].get(t["id"], {})
            for o in snap.get("orders", []):
                if o["name"] in seen:
                    continue
                seen.add(o["name"])
                created = datetime.fromisoformat(o["createdAt"].replace("Z", "+00:00"))
                orders.append({"name": o["name"], "ordered": o["createdAt"][:10], "daysSinceOrder": (now - created).days,
                               "payment": o["financialStatus"], "fulfillment": o["fulfillmentStatus"], "customer": t.get("name", ""),
                               "email": (t.get("email", "")[:2] + "***@" + t.get("email", "").split("@")[-1]) if t.get("email") else "",
                               "items": o["items"], "tracking": [tr for f in o["fulfillments"] for tr in f["tracking"]]})
            for s_ in snap.get("subscriptions", []):
                subs.append({"id": s_["id"], "status": s_["status"], "every": s_["every"], "items": [l["title"] for l in s_["lines"]]})
        return {"ok": True, "queryType": qtype, "orderLookup": "ok" if orders else "none", "orders": orders[:5],
                "subscriptions": "none" if brand == "selera" else subs,
                "tickets": [{"id": t["id"], "status": t["status"], "summary": t["summary"], "created_at": t["created_at"]} for t in rows][:10]}

    # ---------- performance (2026-10-05): one-call ticket + incremental changes ----------
    def apiTicketFull(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "ticket": copy.deepcopy(t), "extras": copy.deepcopy(self._b(brand)["snaps"].get(t["id"], {})),
                "snapshotAt": self._now()}

    def apiChanges(self, brand, a, c):
        try:
            since = int(str(a.get("since") or 0))
        except ValueError:
            since = 0
        ids = [i for i, v in self.touched[brand].items() if v > since]
        rows = [{k: t[k] for k in SUMMARY_COLS} for t in self._b(brand)["tickets"] if t["id"] in ids]
        return {"ok": True, "version": self.version[brand], "tickets": rows, "removed": [], "serverMs": 40, "serverTime": self._now()}

    # ---------- auto-reply review (coordinator shapes, 2026-10-05) ----------
    def apiAutoReplyList(self, brand, a, c):
        r = self.switches[brand].get("reply", "off")
        live = r == "on" and not self.switches[brand]["dry"]
        return {"ok": True, "switch": r, "mode": "live" if live else ("shadow" if r != "off" else "off"),
                "items": copy.deepcopy(self.autoreply[brand])}

    def apiAutoReplyReview(self, brand, a, c):
        it = next((x for x in self.autoreply[brand] if x["id"] == a.get("id")), None)
        if not it:
            return {"ok": False, "error": "not_found"}
        if a.get("verdict") not in ("ok", "problem"):
            return {"ok": False, "error": "bad_verdict"}
        if it["review"] != "pending":
            return {"ok": False, "error": "already_reviewed"}
        it.update({"review": a["verdict"], "reviewedBy": c["user"]})
        if a["verdict"] == "problem":
            t = self._find(brand, it["id"])
            if t:
                t.update({"status": "action", "action": "auto-reply flagged by %s: %s" % (c["user"], str(a.get("note", ""))[:200]),
                          "recommendation": "תשובה אוטומטית סומנה כבעייתית — לקרוא את ההערה ולתקן מול הלקוח."})
                self.version[brand] += 1
                self.touched[brand][t["id"]] = self.version[brand]
        return {"ok": True}

    # ---------- WhatsApp: a person takes the chat back from the Dondy bot (engine @18) ----------
    def apiWaTakeOver(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t or t.get("channel") != "whatsapp":
            return {"ok": False, "error": "not_found"}
        if t["status"] != "bot":
            return {"ok": False, "error": "not_bot"}
        t.update({"status": "action", "action": "whatsapp: taken over from the Dondy bot, waiting for a draft"})
        self.version[brand] += 1
        self.touched[brand][t["id"]] = self.version[brand]
        return {"ok": True, "id": t["id"], "status": "action"}
