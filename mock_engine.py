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
import re
import threading
import time
from datetime import datetime, timedelta, timezone

MOCK_BRANDS = ("rozela", "celesta", "apexmen", "selera")      # velora on purpose has NO engine: it previews "not connected"
CS_ROLES = ("agent", "admin", "user-manager")
OPEN = ("ready", "action", "health", "delay")
SUMMARY_COLS = ['id', 'status', 'category', 'name', 'email', 'subject', 'summary', 'action', 'waiting_since',
                'created_at', 'handled_by', 'handled_at', 'language', 'order_no', 'channel', 'emails_count',
                'cancelled', 'watch', 'ship_state', 'recommendation', 'siblings', 'wa_last_in']
TICKET_COLS = ['id', 'status', 'category', 'name', 'email', 'phone', 'channel', 'subject', 'summary', 'action',
               'draft_text', 'draft_id', 'thread_id', 'message_id', 'waiting_since', 'created_at', 'handled_by',
               'handled_at', 'language', 'order_no', 'order_date', 'tracking', 'carrier', 'ship_state', 'wa_sig',
               'wa_out', 'wa_send', 'notes', 'watch', 'emails_count', 'cancelled', 'recommendation', 'siblings', 'wa_last_in']
WORK = ("agent", "admin")
TABLE = {"apiBoot": CS_ROLES, "apiStatus": CS_ROLES, "apiTicket": WORK, "apiTicketExtras": WORK, "apiTickets": WORK,
         "apiSearch": WORK, "apiSaveDraft": WORK, "apiSend": WORK, "apiMarkHandled": WORK, "apiClose": WORK,
         "apiNote": WORK, "apiKachingCancel": WORK, "apiKachingContract": WORK, "apiKachingAction": WORK, "apiKachingVariants": WORK, "apiOrderEditState": WORK, "apiOrderEdit": WORK,
         "apiSubCancelPreview": WORK, "apiSubCancel": WORK, "apiLinkCustomer": WORK,
         "apiAutoCancelList": WORK, "apiAutoCancelApprove": WORK,
         "apiAutoCancelReject": WORK, "apiSettings": ("admin",), "apiKnowledge": WORK, "apiCustomerLookup": WORK,
         "apiTicketFull": WORK, "apiChanges": WORK, "apiAutoReplyList": WORK, "apiAutoReplyReview": WORK, "apiWaTakeOver": WORK, "apiRedraftOne": WORK,
         "apiResult": WORK, "apiTicketLite": WORK, "apiDayStats": ("admin", "user-manager"),
         "apiTemplates": WORK, "apiSendTemplate": WORK,
         "apiAiNotes": ("admin",), "apiAiNoteAdd": ("admin",), "apiAiNoteDelete": ("admin",), "apiAiNoteAttach": ("admin",), "apiAiNoteCheck": ("admin",), "apiAttachPut": WORK,
         "apiAiNoteSuggestions": ("admin",), "apiAiNoteSuggestDecide": ("admin",),
         "apiSaleCandidates": ("admin",), "apiSaleLog": ("admin",), "apiSaleMine": ("admin",), "apiSaleProof": ("admin",), "apiSaleList": ("admin",), "apiSaleDecide": ("admin",),
         "apiSaleSuggestions": ("admin",), "apiSaleSuggestCredit": ("admin",), "apiSaleSuggestDismiss": ("admin",), "apiSaleScan": ("admin",),
         "apiCancelStats": ("admin",)}
# apiCancelStats (2026-10-23). MOCK_CANCEL_STATS=absent -> the fn is unknown (an engine before the deploy); MOCK_CANCEL_STATE="apexmen:no_kaching,
# celesta:error" overrides a brand's Kaching state (velora has no mock engine, so its "no_kaching" is shown through another brand).
if os.environ.get("MOCK_CANCEL_STATS") == "absent":
    TABLE.pop("apiCancelStats")
MOCK_WRITES = ("apiRedraftOne", "apiSend", "apiSaveDraft", "apiMarkHandled", "apiClose", "apiNote", "apiKachingCancel", "apiKachingAction", "apiSubCancel", "apiOrderEdit", "apiWaTakeOver",
               "apiAutoReplyReview", "apiAutoCancelApprove", "apiAutoCancelReject", "apiSendTemplate", "apiAiNoteAdd", "apiAiNoteDelete", "apiAiNoteSuggestDecide",
               "apiSaleLog", "apiSaleDecide", "apiSaleSuggestCredit", "apiSaleSuggestDismiss")
# engine 2026-10-11: apiBoot.myshopify (the store's admin handle) and extras.mailbox (the support address an email ticket came to).
# apexmen has no myshopify on purpose (order numbers stay plain text); t18f2a02 has no mailbox (an older ticket: the line is hidden).
MYSHOPIFY = {"rozela": "achq3j-nj.myshopify.com", "celesta": "celesta-il.myshopify.com", "apexmen": "", "selera": "selera-tea.myshopify.com"}
MAILBOX = {"rozela": "support@tryrozela.com", "celesta": "hello@celesta.co.il", "apexmen": "support@apexmen.co.il", "selera": "support@selera.co.il"}
NO_MAILBOX = ("t18f2a02",)
AI_NOTE_ID_RE = re.compile(r"^[a-z0-9]{8,40}$")
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
        if row.get("channel") == "whatsapp" and not row.get("wa_last_in"):
            row["wa_last_in"] = row.get("waiting_since") or row.get("created_at") or ""   # the engine keeps the customer's last message time
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
        if row.get("channel") != "whatsapp":
            snaps[row["id"]]["mailbox"] = "" if row["id"] in NO_MAILBOX else MAILBOX.get(brand, "")

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
        # Sales log (2026-10-14): a pre-sale chat a person answered, closed 2 days ago (no open / today count moves). Its customer later ordered:
        # MockEngines.SHOP_ORDERS below has #4601 (after the answer) and #4599 (before it).
        add({"id": "t18f2s01", "status": "done", "category": "product", "name": "דנה שחר", "email": "dana.s@example.com", "phone": "+972501230045",
             "channel": "email", "subject": "מה ההבדל בין החבילות?", "summary": "שאלה לפני רכישה: איזו חבילה מתאימה, ובכמה.", "created_at": h(40),
             "handled_by": "agent-two", "handled_at": h(38), "language": "he"},
            _conv(now, ("customer", 40, "שלום, מה ההבדל בין חבילת חודש לחבילת 3 חודשים? ויש הנחה?"),
                  ("us", 38, "היי דנה, בחבילת 3 חודשים כל חודש יוצא זול יותר, ויש משלוח חינם. אם תרצי אשמח לעזור להזמין." + sig)))
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
             "draft_text": "היי אולגה, ההזמנה כבר בדרך אלייך. מספר המעקב: JY4421337799\n\nנועם משירות לקוחות"},
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
        # engine @37/38: a failed WhatsApp send goes back to "action", marked ⚠️ at the start of the action line
        add({"id": "w8ab77f1", "status": "action", "category": "other", "name": "נועה (נכשל)", "phone": "+972521112233",
             "channel": "whatsapp", "subject": "WhatsApp", "summary": "שאלה על משלוח — השליחה בדונדי נכשלה.",
             "action": "⚠️ בדקו בדונדי לפני שליחה חוזרת (chat_not_found)", "wa_send": "failed:dondy-ext",
             "wa_out": "היי נועה, החבילה יצאה אתמול ותגיע עד יום חמישי.", "draft_text": "היי נועה, החבילה יצאה אתמול ותגיע עד יום חמישי.",
             "waiting_since": h(2), "created_at": h(2), "handled_by": "agent1", "handled_at": h(1), "language": "he"},
            _conv(now, ("customer", 2, "מתי זה מגיע?")))
        add({"id": "w8ab77f2", "status": "action", "category": "other", "name": "דוד (24 שעות)", "phone": "+972521114455",
             "channel": "whatsapp", "subject": "WhatsApp", "summary": "ענינו מאוחר — חלון 24 השעות נסגר.",
             "action": "⚠️ חלון 24 השעות נסגר — צריך תבנית", "wa_send": "template_required:dondy-ext",
             "wa_out": "היי דוד, סליחה על העיכוב.", "draft_text": "היי דוד, סליחה על העיכוב.",
             "waiting_since": h(30), "created_at": h(30), "handled_by": "agent1", "handled_at": h(26), "language": "he"},
            _conv(now, ("customer", 30, "יש עדכון?")))
        add({"id": "w8ab77f3", "status": "action", "category": "other", "name": "אורי (לא ידוע)", "phone": "+972521116677",
             "channel": "whatsapp", "subject": "WhatsApp", "summary": "השליחה לא אושרה — לבדוק בדונדי.",
             "action": "whatsapp: waiting for a draft", "wa_send": "unknown:dondy-ext:1", "wa_out": "היי אורי, בדקנו.",
             "draft_text": "היי אורי, בדקנו.", "waiting_since": h(3), "created_at": h(3), "language": "he"},
            _conv(now, ("customer", 3, "יש חדש?")))
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


def build_ai_suggestions(brand, now):
    """Pending suggestions the engine distilled from the team's edits of AI drafts (AiLearn.gs). rozela: two; celesta: one; others: none."""
    def at(h):
        return _iso(now - timedelta(hours=h))
    seed = {
        "rozela": [
            {"id": "s0a1b2c3d4e5f6a7b", "text": "לא להציע החזר כספי אם הלקוח לא ביקש אותו — קודם לעזור עם השימוש במוצר.", "count": 6, "at": at(30),
             "examples": [{"customer": "המוצר לא עוזר לי, מה עושים?", "ai": "היי, יש לך 60 יום החזר כספי מלא.", "sent": "היי, בואי ננסה יחד שבוע נוסף: 2 כמוסות עם ארוחת בוקר."},
                          {"customer": "לא רואה תוצאות אחרי שבוע", "ai": "אפשר לקבל החזר מלא תוך 60 יום.", "sent": "היי, התוצאות מגיעות בדרך כלל אחרי 3-4 שבועות. כדאי להמשיך."}]},
            {"id": "s1b2c3d4e5f6a7b8c", "text": "לפתוח בשם הלקוח ולא ב'שלום רב'.", "count": 3, "at": at(5),
             "examples": [{"customer": "איפה ההזמנה שלי?", "ai": "שלום רב, ההזמנה בדרך.", "sent": "היי מיכל, ההזמנה בדרך."}]}],
        "celesta": [
            {"id": "s2c3d4e5f6a7b8c9d", "text": "Do not promise a delivery date; give the tracking link instead.", "count": 2, "at": at(12),
             "examples": [{"customer": "When will it arrive?", "ai": "It will arrive on Monday.", "sent": "Here is your tracking link: https://t.17track.net/en"}]}],
    }
    out = []
    for x in seed.get(brand, []):
        out.append(dict(x, state="pending"))
    out.sort(key=lambda x: x["at"])                  # stored oldest first, like the engine's tab; the read reverses it
    return out


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
        self.results = {b: {} for b in MOCK_BRANDS}          # rid -> (fn, user, reply): like the live engine (30 min)
        # MOCK_SLOW_FNS="apiSend:12000,apiClose:8000" — a slow engine for one fn, to test background sends
        self.slow = {}
        for part in os.environ.get("MOCK_SLOW_FNS", "").split(","):
            if ":" in part:
                f, ms = part.split(":", 1)
                self.slow[f.strip()] = int(ms) / 1000.0
        self.version = {b: 1 for b in MOCK_BRANDS}
        # MOCK_WA_DELIVER_MS=4000 — a pretend WhatsApp bridge: a queued send is "sent" that long after it was queued (default: never, as before)
        self.wa_deliver_s = int(os.environ.get("MOCK_WA_DELIVER_MS", "0") or 0) / 1000.0
        self.wa_queued_at = {b: {} for b in MOCK_BRANDS}
        self.touched = {b: {} for b in MOCK_BRANDS}     # ticket id -> version of its last change
        self.ai_notes = {b: [] for b in MOCK_BRANDS}    # engine AiNotes.gs: [{id, scope, text, by, at}] in the order added
        self.ai_sugg = {b: build_ai_suggestions(b, now) for b in MOCK_BRANDS}   # engine AiLearn.gs: [{id, text, count, at, state, examples}]
        self.ai_corrections = {"rozela": 37, "celesta": 12, "apexmen": 4, "selera": 0, "velora": 0}
        # engine Attach.gs: files agents send. MOCK_WA_ATTACH="rozela" = WhatsApp files switched on for those brands (default: off, like live)
        self.attach = {b: {} for b in MOCK_BRANDS}
        self.wa_attach = set(x.strip() for x in os.environ.get("MOCK_WA_ATTACH", "").split(",") if x.strip())
        self.sent_files = []                          # (brand, ticket id, [names]) of every send with files, for the tests
        self._init_sales()

    def transport(self, url, body):
        brand = url.split("mock://", 1)[1]
        if self.latency:
            time.sleep(self.latency)
        if body.get("fn") in self.slow:
            time.sleep(self.slow[body["fn"]])
        with self.lock:
            rid, fn = body.get("rid"), body.get("fn")
            if fn in MOCK_WRITES and rid in self.results[brand]:          # same rid again: idempotent, never twice
                sfn, _u, stored = self.results[brand][rid]
                return dict(stored, replayed=True, fn=fn, rid=rid) if sfn == fn else {"ok": False, "error": "rid_reuse", "fn": fn, "rid": rid}
            self._wa_deliver(brand)
            out = self.dispatch(brand, body)
            if fn in ("apiSend", "apiSendTemplate") and out.get("queued") and not out.get("already"):
                self.wa_queued_at[brand][(body.get("args") or {}).get("id")] = time.time()
            if fn in MOCK_WRITES and out.get("ok") and rid:
                self.results[brand][rid] = (fn, "", dict(out))
            if isinstance(out, dict) and rid:
                out = dict(out, fn=fn, rid=rid)                            # the live engine echoes both
            if out.get("ok") is not None and body.get("fn") == "apiSubCancel" and "verified" in out:      # kept on the ticket either way
                self.version[brand] += 1
                self.touched[brand][(body.get("args") or {}).get("id")] = self.version[brand]
            elif out.get("ok") and body.get("fn") in ("apiSaveDraft", "apiSend", "apiMarkHandled", "apiClose", "apiNote", "apiKachingCancel", "apiKachingAction", "apiSendTemplate"):
                self.version[brand] += 1
                self.touched[brand][(body.get("args") or {}).get("id")] = self.version[brand]
            return out

    def _wa_deliver(self, brand):
        """The pretend bridge (MOCK_WA_DELIVER_MS): queued WhatsApp sends become sent, like apiWaSent result=sent. Caller holds the lock."""
        if not self.wa_deliver_s:
            return
        now = time.time()
        for tid, at in list(self.wa_queued_at[brand].items()):
            if now - at < self.wa_deliver_s:
                continue
            self.wa_queued_at[brand].pop(tid, None)
            t = self._find(brand, tid)
            if t and t.get("wa_send") == "pending":
                # engine 2026-10-14: a chat a person closed while its send was queued stays closed when the send is confirmed
                t.update({"wa_send": "sent:mock", "status": "done" if t.get("status") == "done" else "sent"})
                self.version[brand] += 1
                self.touched[brand][tid] = self.version[brand]

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
                "counts": counts, "tickets": [self._row(brand, t) for t in b["tickets"]],
                "serverTime": self._now(),
                "dryRun": sw["dry"], "cancelEnabled": sw["writes"], "cancelFrozen": bool(sw["frozen"]), "orderEdits": sw.get("oe", "on"),
                "subscriptions": "none" if brand == "selera" else "kaching", "version": self.version[brand],
                "myshopify": MYSHOPIFY.get(brand, ""), "attach": self._attach_info(brand),
                "kachingReady": brand != "selera"}

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

    TEMPLATES = [{"name": "Check 2", "text": "היי 🙂 רצינו לבדוק אם זה זמן נוח להמשיך את השיחה ולעזור לך?"},
                 {"name": "Start", "text": "היי מה נשמע?"}]

    def apiTemplates(self, brand, a, c):
        return {"ok": True, "templates": list(self.TEMPLATES), "at": self._now()}

    def apiSendTemplate(self, brand, a, c):
        """Engine WaTemplates.gs: a template is queued like a reply; `then` is kept for when the customer answers."""
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        tpl = next((x for x in self.TEMPLATES if x["name"] == a.get("template")), None)
        if not tpl:
            return {"ok": False, "error": "bad_template"}
        if t["channel"] != "whatsapp":
            return {"ok": False, "error": "bad_channel"}
        if t.get("wa_send") == "pending":
            return {"ok": False, "error": "wa_send_in_flight"}
        moved = self._moved(t, a, c)                       # engine 2026-10-11: any status (answered / closed too), stale screens refused
        if moved:
            return moved
        at = self._now()
        t.update({"wa_out": tpl["text"], "wa_send": "pending", "status": "wa_queued", "handled_by": c["user"], "handled_at": at})
        self.template_sends = getattr(self, "template_sends", []) + [{"id": t["id"], "template": tpl["name"], "then": a.get("then") or ""}]
        return {"ok": True, "queued": True, "template": tpl["name"], "waiting": bool(a.get("then")), "handled_at": at}

    @staticmethod
    def _moved(t, a, c):
        """engine/Api.gs handledMovedSince_: `seen` = handled_at as the screen showed it; someone ELSE handled it later -> changed_meanwhile."""
        seen = a.get("seen")
        if not isinstance(seen, str):
            return None
        now, was = str(t.get("handled_at") or ""), seen
        if not now or now == was or (was and now < was) or t.get("handled_by") == c["user"]:
            return None
        return {"ok": False, "error": "changed_meanwhile", "by": t.get("handled_by") or "", "at": now, "status": t.get("status")}

    def apiSend(self, brand, a, c):
        text = a.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            return {"ok": False, "error": "bad_text"}
        if self.switches[brand]["dry"]:
            return {"ok": False, "error": "dry_run"}
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        followup = a.get("followup") is True              # engine 2026-10-11: another message on an answered / closed ticket
        moved = self._moved(t, a, c)
        if moved:
            return moved
        if t["status"] in ("sent", "done") and not followup:
            return {"ok": False, "error": "already_sent" if t["channel"] == "whatsapp" else "already_handled"}
        if "REFUSE-SEND" in text:                          # preview / test trigger: a refusal about the ticket (never retried)
            return {"ok": False, "error": "thread_missing"}
        if "BUSY-ONCE" in text and text not in getattr(self, "busy_once", set()):   # test trigger: the first try is "busy" (the outbox retries)
            self.busy_once = getattr(self, "busy_once", set()) | {text}
            return {"ok": False, "error": "busy"}
        if not text.strip():                               # engine 2026-10-06: only an EMPTY draft is refused; content
            return {"ok": False, "error": "draft_problem", "problem": "empty draft"}   # checks are an audit, never a block
        files, ferr = self._attach_resolve(brand, a.get("attachments"), t["channel"], c)
        if ferr:
            return ferr
        at = self._now()
        snap = self._b(brand)["snaps"].get(t["id"])
        if t["channel"] == "whatsapp":                     # live engine (2026-10-05 08:14): wa_queued + double-send guard
            if t["status"] == "wa_queued" or t.get("wa_send") == "pending":
                if t.get("wa_out") == text and t.get("handled_by") == c["user"]:
                    return {"ok": True, "queued": True, "already": True}
                return {"ok": False, "error": "wa_send_in_flight"}
            if t.get("wa_out") == text and str(t.get("wa_send") or "").startswith("sent"):
                return {"ok": False, "error": "already_sent"}
            if self._wa_window_closed(t):
                return {"ok": False, "error": "wa_window_closed"}
            t.update({"wa_out": text, "wa_send": "pending", "status": "wa_queued", "handled_by": c["user"], "handled_at": at})
            if snap:                                       # the mock's bridge is instant: shown as ours at once
                snap["conversation"].append(dict({"id": "m-sent-%d" % len(snap["conversation"]), "who": "us", "at": at, "text": text}, **({"files": files} if files else {})))
            if files:
                self.sent_files.append((brand, t["id"], files))
            return {"ok": True, "queued": True, "handled_at": at}
        if followup and t["status"] == "sent" and t.get("draft_text") == text and t.get("handled_by") == c["user"]:
            return {"ok": False, "error": "already_sent"}
        t.update({"status": "sent", "draft_text": text, "handled_by": c["user"], "handled_at": at, "draft_id": ""})
        if snap:
            snap["conversation"].append(dict({"id": "m-sent-%d" % len(snap["conversation"]), "who": "us", "at": at, "text": text}, **({"files": files} if files else {})))
        if files:
            self.sent_files.append((brand, t["id"], files))
        return {"ok": True, "sent": True, "warnings": [], "handled_at": at}

    # ---------- files (engine/Attach.gs) ----------
    ATTACH_PART = 1_500_000
    WA_TYPES = ("application/pdf", "image/jpeg", "image/png", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _attach_info(self, brand):
        return {"email": True, "whatsapp": brand in self.wa_attach, "fileMax": 10 * 1024 * 1024, "emailTotalMax": 18000000, "emailFilesMax": 10,
                "waFileMax": 5242880, "waTypes": list(self.WA_TYPES)}

    def apiAttachPut(self, brand, a, c):
        aid, size, parts, part = a.get("id"), a.get("size"), a.get("parts"), a.get("part")
        if not re.match(r"^a[0-9a-f]{24}$", str(aid)) or not isinstance(size, int) or size < 1 or size > 10 * 1024 * 1024:
            return {"ok": False, "error": "attach_too_big" if isinstance(size, int) and size > 10 * 1024 * 1024 else "bad_attach"}
        if parts != -(-size // self.ATTACH_PART) or not isinstance(part, int) or not 0 <= part < parts:
            return {"ok": False, "error": "bad_attach"}
        rec = self.attach[brand].setdefault(aid, {"id": aid, "name": a.get("name"), "mime": a.get("mime"), "size": size, "sha256": a.get("sha256"),
                                                  "parts": {}, "owner": c["user"], "ready": False})
        if rec["sha256"] != a.get("sha256") or rec["size"] != size:
            return {"ok": False, "error": "attach_id_reuse"}
        if rec["ready"]:
            return {"ok": True, "id": aid, "part": part, "ready": True}
        rec["parts"][part] = base64.b64decode(a.get("data") or "")
        if part != parts - 1:
            return {"ok": True, "id": aid, "part": part, "ready": False}
        whole = b"".join(rec["parts"][i] for i in sorted(rec["parts"]))
        if len(rec["parts"]) != parts or hashlib.sha256(whole).hexdigest() != rec["sha256"]:
            self.attach[brand].pop(aid, None)
            return {"ok": False, "error": "attach_corrupt"}
        rec["ready"] = True
        return {"ok": True, "id": aid, "part": part, "ready": True}

    def _attach_resolve(self, brand, ids, channel, c):
        if not ids:
            return [], None
        recs = [self.attach[brand].get(i) for i in ids]
        if any(r is None or not r["ready"] for r in recs):
            return None, {"ok": False, "error": "attach_missing"}
        if any(r["owner"] != c["user"] and c["role"] != "admin" for r in recs):
            return None, {"ok": False, "error": "unauthorized"}
        if channel == "whatsapp":
            if brand not in self.wa_attach:
                return None, {"ok": False, "error": "attach_wa_off"}
            if len(recs) > 1:
                return None, {"ok": False, "error": "attach_wa_one"}
            if recs[0]["mime"] not in self.WA_TYPES:
                return None, {"ok": False, "error": "attach_wa_type"}
        elif sum(r["size"] for r in recs) > 18000000:
            return None, {"ok": False, "error": "attach_too_big"}
        return [r["name"] for r in recs], None

    @staticmethod
    def _wa_window_closed(t):
        try:
            last = datetime.fromisoformat(str(t.get("wa_last_in") or "").replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(timezone.utc) - last >= timedelta(hours=24) - timedelta(minutes=2)

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

    @staticmethod
    def draft_fp(s):
        """engine/AgentRedraft.gs redraft1Fp_: FNV-1a 32 over UTF-16 code units (the screen's draftFp)."""
        h = 2166136261
        b = str(s or "").encode("utf-16-le")
        for i in range(0, len(b), 2):
            h ^= b[i] | (b[i + 1] << 8)
            h = (h * 16777619) & 0xFFFFFFFF
        return "%08x" % h

    def apiRedraftOne(self, brand, a, c):
        """engine/AgentRedraft.gs: a different AI draft for one open ticket (5 / ticket / hour), undo = the replaced one back.
        MOCK_REDRAFT_FAIL=1 makes every new answer come out blocked (no_new_draft)."""
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        if t["status"] not in OPEN:
            return {"ok": False, "error": "not_open"}
        if str(t.get("wa_send") or "").startswith(("pending", "claimed")):
            return {"ok": False, "error": "wa_send_in_flight"}
        moved = self._moved(t, a, c)
        if moved:
            return moved
        if self.draft_fp(t.get("draft_text")) != a.get("base"):
            return {"ok": False, "error": "changed_meanwhile", "reason": "draft", "by": "", "at": "", "status": t["status"]}
        prev = getattr(self, "redraft_prev", {})
        self.redraft_prev = prev
        key = (brand, t["id"])
        if a.get("undo") is True:
            if key not in prev:
                return {"ok": False, "error": "nothing_to_undo"}
            old = prev[key]
            prev[key] = t.get("draft_text") or ""
            t["draft_text"] = old
            return {"ok": True, "draft": old, "recommendation": t.get("recommendation") or "", "undone": True}
        hint = a.get("hint") or ""
        if not isinstance(hint, str) or len(hint) > 200:
            return {"ok": False, "error": "bad_hint"}
        calls = getattr(self, "redraft_calls", {})
        self.redraft_calls = calls
        now = time.time()
        mine = [x for x in calls.get(key, []) if now - x < 3600]
        if len(mine) >= 5:
            return {"ok": False, "error": "rate_limited", "scope": "ticket", "retryAfterSeconds": int(3600 - (now - min(mine))) + 1}
        calls[key] = mine + [now]
        self.redraft_hints = getattr(self, "redraft_hints", []) + [hint]
        if os.environ.get("MOCK_REDRAFT_FAIL") == "1":
            return {"ok": False, "error": "no_new_draft"}
        name = (t.get("name") or "").split(" ")[0]
        draft = "היי %s, תשובה אחרת מספר %d%s.\n\nצוות %s" % (name, len(calls[key]), " (קצרה)" if "קצר" in hint else "", self._b(brand)["name"])
        prev[key] = t.get("draft_text") or ""
        t["draft_text"] = draft
        return {"ok": True, "draft": draft, "recommendation": t.get("recommendation") or "", "left": 5 - len(calls[key])}

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
        if not self._sub_email(brand, t):               # engine: ticketCustomerEmail_ (the agent's link first)
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

    # ---------- "לבטל את המנוי" in the send area (engine Api.gs apiSubCancelPreview / apiSubCancel, 2026-10-16) ----------
    SUB_CLAIM_RE = re.compile(r"(?<!לא )(?:ביטל|הפסק)(?:תי|נו)\s+(?:לך\s+)?(?:כבר\s+)?(?:את\s+)?(?:ה)?מנוי|(?:ה)?מנוי\s+(?:שלך\s+)?(?:כבר\s+)?(?:בוטל|מבוטל)"
                              r"|\b(?:I|we)(?:'ve|\s+have)?\s+(?:already\s+)?cancel(?:l)?ed\b[^.!?\n]{0,50}\bsubscription", re.I)

    def _sub_pre(self, brand, a):
        if brand == "selera":
            return None, {"ok": False, "error": "no_subscriptions"}
        t = self._find(brand, a.get("id"))
        if not t:
            return None, {"ok": False, "error": "not_found"}
        draft = a.get("draft") if isinstance(a.get("draft"), str) else ""
        asked = (str(t.get("action", "")).startswith("cancel:") or t.get("category") == "cancel_subscription"
                 or bool(self.SUB_CLAIM_RE.search(t.get("draft_text") or "")) or bool(self.SUB_CLAIM_RE.search(draft)))
        if not asked:
            return None, {"ok": False, "error": "not_cancel_request"}
        if not self._sub_email(brand, t):
            return None, {"ok": False, "error": "no_email", "why": "none"}
        return t, None

    def _sub_email(self, brand, t):
        """engine ticketCustomerEmail_: the agent's link first (apiLinkCustomer), then the ticket's own."""
        l = self._b(brand)["snaps"].get(t["id"], {}).get("linked") or {}
        return l.get("email") or t.get("email") or ""

    def apiLinkCustomer(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        snaps = self._b(brand)["snaps"]
        snap = snaps.setdefault(t["id"], {})
        if a.get("unlink") is True:
            le = (snap.get("linked") or {}).get("email", "")
            if le and le != str(t.get("email") or "").lower():          # engine: what the link brought in leaves with it
                names = set((snap.get("linked") or {}).get("orders", []))
                snap["orders"] = [o for o in snap.get("orders", []) if o.get("name") not in names]
                snap.pop("subscriptions", None)
                snap["notes"] = {"orders": "not_checked", "subscriptions": "not_checked_no_email"}
            snap.pop("linked", None)
            return {"ok": True, "id": t["id"], "linked": None, "extras": copy.deepcopy(snap)}
        q = str(a.get("q") or "").strip().lower()
        num = "#" + q.lstrip("#").strip() if re.match(r"^#?\s?\d{3,9}$", q) else ""
        if not (num or re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", q)):
            return {"ok": False, "error": "bad_query"}
        for other in self._b(brand)["tickets"]:      # the store: every order in the mock snapshots, with its ticket's email
            s = snaps.get(other["id"], {})
            hit = [o for o in s.get("orders", []) if (num and o.get("name") == num) or (not num and str(other.get("email", "")).lower() == q)]
            if hit and other.get("email"):
                rec = {"email": other["email"].lower(), "orders": [o["name"] for o in hit][:5], "kind": "order" if num else "email",
                       "by": c["user"], "at": self._now()}
                snap["linked"] = rec
                snap["orders"] = copy.deepcopy(hit) + [o for o in snap.get("orders", []) if o.get("name") not in rec["orders"]]
                snap["subscriptions"] = copy.deepcopy(s.get("subscriptions", []))
                snap["notes"] = {"orders": "found", "subscriptions": "found" if snap["subscriptions"] else "none"}
                if not t.get("order_no"):
                    t["order_no"] = rec["orders"][0]
                self.version[brand] += 1
                self.touched[brand][t["id"]] = self.version[brand]
                return {"ok": True, "id": t["id"], "linked": rec, "extras": copy.deepcopy(snap)}
        return {"ok": False, "error": "no_order"}

    def apiSubCancelPreview(self, brand, a, c):
        t, err = self._sub_pre(brand, a)
        if err:
            return err
        subs = self._b(brand)["snaps"].get(t["id"], {}).get("subscriptions", [])
        def one(s):
            return {"id": s["id"], "status": s["status"], "every": s.get("every", ""),
                    "items": [{"title": l.get("title", ""), "quantity": l.get("quantity", 1)} for l in s.get("lines", [])]}
        live = [one(s) for s in subs if s["status"] in ("ACTIVE", "PAUSED", "FAILED")]
        ended = [one(s) for s in subs if s["status"] not in ("ACTIVE", "PAUSED", "FAILED")]
        sw = self.switches[brand]
        linked = bool(self._b(brand)["snaps"].get(t["id"], {}).get("linked"))
        return {"ok": True, "id": t["id"], "name": t.get("name", ""), "email": self._sub_email(brand, t), "emailFrom": "linked" if linked else "ticket",
                "contracts": live, "ended": ended, "checkedAt": self._now(),
                "cancelledHere": [x for x in str(t.get("cancelled", "")).split(",") if x], "writes": sw["writes"], "frozen": bool(sw["frozen"])}

    def apiSubCancel(self, brand, a, c):
        t, err = self._sub_pre(brand, a)
        if err:
            return err
        cid = a.get("contractId")
        if not isinstance(cid, str) or not cid.startswith(CONTRACT_RE_PREFIX) or not cid[len(CONTRACT_RE_PREFIX):].isdigit():
            return {"ok": False, "error": "bad_contract"}
        r = self.apiKachingCancel(brand, dict(a, confirm=cid[-4:], reason="the agent pressed the cancel button"), c)   # the same gate
        snap = self._b(brand)["snaps"].setdefault(t["id"], {})
        back = next((s for s in snap.get("subscriptions", []) if s["id"] == cid), None)       # read back
        verified = bool(back and back["status"] == "CANCELLED")
        rec = {"state": "cancelled" if verified else "failed", "contractId": cid, "status": back["status"] if back else (r.get("status") or ""),
               "items": [{"title": l.get("title", ""), "quantity": l.get("quantity", 1)} for l in (back or {}).get("lines", [])],
               "at": self._now(), "by": c["user"], "reason": "" if verified else str(r.get("message") or "not cancelled")[:200]}
        snap["subCancel"] = rec
        out = {"ok": verified, "verified": verified, "state": rec["state"], "status": rec["status"], "contractId": cid, "at": rec["at"],
               "message": str(r.get("message") or ""), "record": rec}
        if not verified:
            out["error"] = "not_cancelled"
        return out

    # ---------- Kaching contract actions (engine Kaching.gs kachingContractAction, 2026-10-14) ----------
    MOCK_VARIANTS = [{"id": "gid://shopify/ProductVariant/48134100517122", "product": "פורמולת הסלק", "title": "", "price": "189.00"},
                     {"id": "gid://shopify/ProductVariant/48134100517123", "product": "פורמולת הסלק", "title": "זוג", "price": "329.00"},
                     {"id": "gid://shopify/ProductVariant/48134100517124", "product": "כדורי דלעת", "title": "", "price": "149.90"}]
    ACTION_FROM = {"pause": ("ACTIVE", "FAILED"), "resume": ("PAUSED",), "reactivate": ("CANCELLED", "EXPIRED", "FAILED")}

    def _contract(self, brand, t, cid):
        """The ticket customer's contract with ids, prices and cycles (built once from the snapshot's subscription)."""
        subs = self._b(brand)["snaps"].get(t["id"], {}).get("subscriptions", [])
        s = next((x for x in subs if x["id"] == cid), None)
        if not s:
            return None, None
        if "cycles" not in s:
            base = datetime.now(timezone.utc) + timedelta(days=28)
            s["cycles"] = [{"index": i + 1, "date": _iso(base + timedelta(days=30 * i)), "skipped": False, "status": "UNBILLED"} for i in range(4)]
            for i, l in enumerate(s["lines"]):
                l.setdefault("id", "gid://shopify/SubscriptionLine/mock-%s-%d" % (cid[-4:], i))
                l.setdefault("variantId", self.MOCK_VARIANTS[0]["id"])
                l.setdefault("price", 160.65)
            s.setdefault("discounts", [])
            s.setdefault("currency", "ILS")
        nxt = next((c for c in s["cycles"] if not c["skipped"]), None)
        if s["status"] in ("ACTIVE", "FAILED"):
            s["nextBillingDate"] = nxt["date"] if nxt else None
        return s, subs

    def apiKachingContract(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        if brand == "selera":
            return {"ok": False, "error": "no_subscriptions"}
        if not t.get("email"):
            return {"ok": False, "error": "no_email"}
        s, _ = self._contract(brand, t, a.get("contractId"))
        if not s:
            return {"ok": False, "error": "not_customers_contract"}
        sw = self.switches[brand]
        return {"ok": True, "id": t["id"], "contract": json.loads(json.dumps(s)), "writes": sw["writes"], "frozen": bool(sw["frozen"])}

    def apiKachingVariants(self, brand, a, c):
        return {"ok": True, "variants": list(self.MOCK_VARIANTS)}

    # ---------- order edits in Shopify (engine OrderEdit.gs, 2026-10-16) ----------
    OE_PRICE = 100.0

    def _oe_order(self, brand, t, order_id):
        """The ticket customer's order as the edit gate sees it (lines with ids / variants / prices built once from the snapshot)."""
        o = next((x for x in self._b(brand)["snaps"].get(t["id"], {}).get("orders", []) if x["id"] == order_id), None)
        if not o:
            return None
        if "oe" not in o:
            lines = []
            for i, it in enumerate(o["items"]):
                v = next((m for m in self.MOCK_VARIANTS if m["product"] == it["title"]), self.MOCK_VARIANTS[2])
                lines.append({"id": "gid://shopify/LineItem/%s%d" % (o["id"][-4:], i + 1), "title": it["title"], "variantTitle": "", "quantity": it["quantity"],
                              "variantId": v["id"], "unit": float(v["price"])})
            o["oe"] = {"lines": lines, "address": {"firstName": t.get("name", ""), "lastName": "", "address1": "הרצל 10", "address2": "", "city": "תל אביב", "zip": "6100000",
                                                  "phone": t.get("phone", ""), "provinceCode": "", "countryCode": "IL", "company": ""}}
        return o

    @staticmethod
    def _oe_total(lines):
        return round(sum(l["quantity"] * l["unit"] for l in lines), 2)

    def _oe_public(self, o, status):
        lines = [{"id": l["id"], "title": l["title"], "variantTitle": l["variantTitle"], "quantity": l["quantity"], "unit": "%.2f" % l["unit"]} for l in o["oe"]["lines"]]
        un = o["fulfillmentStatus"] == "UNFULFILLED"
        return {"id": o["id"], "name": o["name"], "currency": "ILS", "financial": o["financialStatus"], "fulfillment": o["fulfillmentStatus"],
                "total": "%.2f" % self._oe_total(o["oe"]["lines"]), "outstanding": "0.00", "address": dict(o["oe"]["address"]), "lines": lines,
                "can": {"address": "" if un else "the order is not unfulfilled (%s)" % o["fulfillmentStatus"],
                        "items": "" if un else "the order is not unfulfilled (%s)" % o["fulfillmentStatus"]}, "status": status}

    def apiOrderEditState(self, brand, a, c):
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        if not t.get("email") and not t.get("phone"):
            return {"ok": False, "error": "no_customer"}
        o = self._oe_order(brand, t, a.get("orderId"))
        if not o:
            return {"ok": False, "error": "not_customers_order"}
        st = self.switches[brand].get("oe", "on")
        return {"ok": True, "id": t["id"], "status": st, "order": self._oe_public(o, st), "admin": c["role"] == "admin"}

    def apiOrderEdit(self, brand, a, c):
        """Mirrors OrderEdit.gs orderEditGate's checks, order and sentences (the common ones)."""
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        kind, mode = a.get("kind"), a.get("mode")
        if kind not in ("address", "items") or mode not in ("preview", "apply"):
            return {"ok": False, "error": "bad_request"}
        res = lambda ok, msg, **kw: dict({"ok": ok, "kind": kind, "message": msg}, **kw)
        st = self.switches[brand].get("oe", "on")
        if st == "off":
            return res(False, "order edits are switched off")
        if st == "no_credential":
            return res(False, "order edits have no write credential")
        if c["role"] not in ("admin", "agent"):
            return res(False, 'role "%s" may not edit orders' % c["role"])
        o = self._oe_order(brand, t, a.get("orderId"))
        if not o:
            return res(False, "this order does not belong to the ticket's customer")
        if o["fulfillmentStatus"] != "UNFULFILLED":
            return res(False, "the order is not unfulfilled (%s)" % o["fulfillmentStatus"])
        digits = "".join(ch for ch in o["name"] if ch.isdigit())
        if mode == "apply" and str(a.get("confirm", "")).strip() != digits:
            return res(False, "confirmation code does not match the order")
        try:
            payload = json.loads(a.get("address") or "null") if kind == "address" else json.loads(a.get("ops") or "null")
        except ValueError:
            return {"ok": False, "error": "bad_request"}
        od = o["oe"]
        if kind == "address":
            if not isinstance(payload, dict) or not payload:
                return res(False, "the new address is missing")
            allowed = ("firstName", "lastName", "address1", "address2", "city", "zip", "phone")
            for k, v in payload.items():
                if k not in allowed:
                    return res(False, "field not allowed: " + k)
                if k in ("city", "address1", "firstName") and not str(v).strip():
                    return res(False, "bad value for " + k)
            changed = [k for k, v in payload.items() if str(od["address"].get(k, "")).strip().lower() != str(v).strip().lower()]
            if not changed:
                return res(False, "nothing to change")
            after = dict(od["address"], **{k: str(payload[k]).strip() for k in changed})
            if mode == "preview":
                return res(True, "", mode="preview", orderId=o["id"], orderName=o["name"], currency="ILS", needsAdmin=False, changed=changed, before=dict(od["address"]), after=after)
            od["address"] = after
            return res(True, "done", verified=True, orderId=o["id"], orderName=o["name"], order=self._oe_public(o, st))
        if not isinstance(payload, list) or not payload:
            return res(False, "no item change was given")
        lines = [dict(l) for l in od["lines"]]
        for op in payload:
            q = str(op.get("quantity", "")).strip()
            if not q.isdigit() or int(q) > 20:
                return res(False, "quantity must be a whole number up to 20")
            q = int(q)
            if op.get("type") == "qty":
                l = next((x for x in lines if x["id"] == op.get("lineId")), None)
                if not l:
                    return res(False, "this item is not on the order")
                if q == l["quantity"]:
                    return res(False, "the quantity is already %d" % q)
                l["quantity"] = q
            elif op.get("type") == "add":
                v = next((m for m in self.MOCK_VARIANTS if m["id"] == op.get("variantId")), None)
                if not v:
                    return res(False, "a valid product is required")
                if q < 1:
                    return res(False, "quantity must be at least 1")
                if any(x["variantId"] == v["id"] for x in lines):
                    return res(False, "this product is already on the order — change its quantity instead")
                lines.append({"id": "gid://shopify/LineItem/9%d" % len(lines), "title": v["product"], "variantTitle": v["title"], "quantity": q, "variantId": v["id"], "unit": float(v["price"])})
            else:
                return res(False, "unknown change")
        live = [l for l in lines if l["quantity"] > 0]
        if not live:
            return res(False, "an order cannot be left without items — cancel it in Shopify")
        before_t, after_t = self._oe_total(od["lines"]), self._oe_total(live)
        delta = round(after_t - before_t, 2)
        needs_admin = delta > 0 and c["role"] != "admin"
        pub = lambda ls: [{"id": l["id"], "title": l["title"], "variantTitle": l["variantTitle"], "quantity": l["quantity"], "unit": "%.2f" % l["unit"]} for l in ls]
        if mode == "preview":
            return res(True, "", mode="preview", orderId=o["id"], orderName=o["name"], currency="ILS", needsAdmin=needs_admin, delta="%.2f" % delta,
                       before={"total": "%.2f" % before_t, "outstanding": "0.00", "lines": pub(od["lines"])},
                       after={"total": "%.2f" % after_t, "outstanding": "%.2f" % max(delta, 0), "lines": pub(live)})
        if needs_admin:
            return res(False, "an increase of %.2f needs an admin" % delta)
        if str(a.get("expectDelta", "")).strip() != "%.2f" % delta:
            return res(False, "the price changed since the preview — review it again", delta="%.2f" % delta)
        od["lines"] = live
        o["items"] = [{"title": l["title"], "quantity": l["quantity"]} for l in live]
        self.order_edits = getattr(self, "order_edits", []) + [{"order": o["id"], "kind": "items", "delta": "%.2f" % delta}]
        return res(True, "done", verified=True, orderId=o["id"], orderName=o["name"], order=self._oe_public(o, st))

    def apiKachingAction(self, brand, a, c):
        """Mirrors Kaching.gs kachingContractAction's checks, order and sentences (the common ones)."""
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        act = a.get("action")
        res = lambda ok, msg, **kw: dict({"ok": ok, "action": act, "message": msg}, **kw)
        if act not in ("pause", "resume", "reactivate", "skip", "unskip", "reschedule", "add_discount", "add_line", "update_line", "remove_line"):
            return res(False, "unknown action")
        sw = self.switches[brand]
        if not sw["writes"]:
            return res(False, "subscription changes are switched off")
        if sw["frozen"]:
            return res(False, "subscription changes are frozen: " + sw["frozen"])
        if c["role"] not in ("admin", "agent"):
            return res(False, 'role "%s" may not change subscriptions' % c["role"])
        cid = a.get("contractId")
        if not isinstance(cid, str) or not cid.startswith(CONTRACT_RE_PREFIX) or not cid[len(CONTRACT_RE_PREFIX):].isdigit():
            return res(False, "exactly one valid contract id is required")
        if str(a.get("confirm", "")) != cid[-4:]:
            return res(False, "confirmation code does not match the contract")
        if not self._sub_email(brand, t):               # engine: ticketCustomerEmail_ (the agent's link first)
            return res(False, "ticket has no customer email")
        s, _ = self._contract(brand, t, cid)
        if not s:
            return res(False, "this contract does not belong to the ticket's customer")
        live = ("ACTIVE", "PAUSED", "FAILED")
        if s["status"] not in self.ACTION_FROM.get(act, live):
            return res(False, "status %s does not allow %s" % (s["status"], act))
        cyc = None
        if act in ("skip", "unskip", "reschedule"):
            idx = str(a.get("cycleIndex", ""))
            cyc = next((x for x in s["cycles"] if idx.isdigit() and x["index"] == int(idx)), None)
            if not idx.isdigit():
                return res(False, "a billing cycle is required")
            if not cyc:
                return res(False, "billing cycle %s is not an upcoming cycle of this contract" % idx)
            if act == "skip" and cyc["skipped"]:
                return res(False, "billing cycle %s is already skipped" % idx)
            if act == "unskip" and not cyc["skipped"]:
                return res(False, "billing cycle %s is not skipped" % idx)
        line = None
        if act in ("update_line", "remove_line"):
            line = next((l for l in s["lines"] if l.get("id") == a.get("lineId")), None)
            if not line:
                return res(False, "this product line is not in the contract")
            if act == "remove_line" and len(s["lines"]) < 2:
                return res(False, "the last product cannot be removed — cancel the subscription instead")
        if act == "pause":
            s["status"] = "PAUSED"; s.pop("nextBillingDate", None)
        elif act in ("resume", "reactivate"):
            s["status"] = "ACTIVE"
        elif act == "skip":
            cyc["skipped"] = True
        elif act == "unskip":
            cyc["skipped"] = False
        elif act == "reschedule":
            d = str(a.get("billingDate", ""))
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                return res(False, "a new date is required (YYYY-MM-DD)")
            if d <= datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                return res(False, "the new date must be in the future")
            cyc["date"] = d + cyc["date"][10:]
        elif act == "add_discount":
            typ, val, title = a.get("discountType"), str(a.get("value", "")), str(a.get("title", "")).strip()
            if typ not in ("PERCENTAGE", "FIXED_AMOUNT"):
                return res(False, "discount type must be PERCENTAGE or FIXED_AMOUNT")
            try:
                v = float(val)
            except ValueError:
                v = -1
            if typ == "PERCENTAGE" and not (1 <= v <= 100):
                return res(False, "a percentage between 1 and 100 is required")
            if typ == "FIXED_AMOUNT" and not (0.01 <= v <= 1000):
                return res(False, "an amount between 0.01 and 1000 is required")
            if not (2 <= len(title) <= 60):
                return res(False, "a discount title of 2 to 60 characters is required")
            s["discounts"].append({"id": "gid://shopify/SubscriptionManualDiscount/mock%d" % len(s["discounts"]), "title": title,
                                   "recurringCycleLimit": int(a["recurringCycleLimit"]) if str(a.get("recurringCycleLimit", "")).isdigit() else None})
        elif act in ("add_line", "update_line"):
            var = next((v for v in self.MOCK_VARIANTS if v["id"] == a.get("variantId")), None)
            q = str(a.get("quantity", ""))
            if act == "add_line" and not var:
                return res(False, "a valid product variant is required")
            if (act == "add_line" or q) and not (q.isdigit() and 1 <= int(q) <= 20):
                return res(False, "a quantity between 1 and 20 is required")
            if act == "add_line":
                s["lines"].append({"id": "gid://shopify/SubscriptionLine/mock-new-%d" % len(s["lines"]), "title": var["product"],
                                   "variantTitle": var["title"], "variantId": var["id"], "quantity": int(q), "price": float(var["price"])})
            else:
                if not (var or q or a.get("price")):
                    return res(False, "nothing to change: a variant, a quantity or a price is required")
                if var:
                    line.update({"variantId": var["id"], "title": var["product"], "variantTitle": var["title"]})
                if q:
                    line["quantity"] = int(q)
                if a.get("price"):
                    line["price"] = float(a["price"])
        elif act == "remove_line":
            s["lines"] = [l for l in s["lines"] if l is not line]
        self._contract(brand, t, cid)
        return res(True, "done", verified=True, status=s["status"], contract=json.loads(json.dumps(s)))

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
        sw = self.switches[brand]                          # (2026-10-06: a content check never blocks a person's send)
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
                "snapshotAt": self._now(), "v": self.touched[brand].get(t["id"], 0)}

    def _row(self, brand, t):
        """A list row like engine @47/48: the summary columns, the ticket's v, and wa_send (state only) on WhatsApp rows."""
        r = dict({k: t[k] for k in SUMMARY_COLS}, v=self.touched[brand].get(t["id"], 0))
        if t.get("channel") == "whatsapp":
            r["wa_send"] = str(t.get("wa_send") or "").split(":")[0]
        return r

    def apiChanges(self, brand, a, c):
        try:
            since = int(str(a.get("since") or 0))
        except ValueError:
            since = 0
        ids = [i for i, v in self.touched[brand].items() if v > since]
        rows = [self._row(brand, t)
                for t in self._b(brand)["tickets"] if t["id"] in ids]
        sw = self.switches[brand]                    # engine @35/36: the switches ride along with every feed reply
        return {"ok": True, "version": self.version[brand], "tickets": rows, "removed": [], "serverMs": 40, "serverTime": self._now(),
                "dryRun": sw["dry"], "cancelEnabled": sw["writes"], "cancelFrozen": bool(sw["frozen"]), "orderEdits": sw.get("oe", "on"),
                "subscriptions": "none" if brand == "selera" else "kaching"}

    def apiDayStats(self, brand, a, c):
        """Engine 2026-10-06 shape (DayStats.gs dsReport_), small fixed numbers; rozela comes in two chunks."""
        if not isinstance(a.get("date"), str) or len(a["date"]) != 10:
            return {"ok": False, "error": "bad_date"}
        cur = a.get("cursor") or 0
        if brand == "rozela" and cur == 0:
            return {"ok": True, "partial": True, "next": 7, "received": {"total": 0}, "answered": {"total": 0}}
        t = self._b(brand)["tickets"]
        rec = {"email": sum(1 for x in t if x.get("channel") != "whatsapp"), "whatsapp": sum(1 for x in t if x.get("channel") == "whatsapp")}
        tot = lambda o: o["email"] + o["whatsapp"]                    # noqa: E731
        ans = {"email": 3, "whatsapp": 2}
        row = lambda ag, au, hu, bo, te, cl, di: {"fromSystem": {"agent": ag, "auto": au, "total": ag + au},  # noqa: E731
                                                  "fromDondy": {"human": hu, "bot": bo, "template": te, "close": cl, "total": hu + bo + te + cl},
                                                  "fromEmail": {"direct": di, "total": di}}
        return {"ok": True, "date": a["date"], "source": "conversation", "brand": brand,
                "received": dict(rec, total=tot(rec)), "answered": dict(ans, total=5, byHuman=4),
                "awaitingNow": {"email": 2, "whatsapp": 1, "total": 3}, "closedToday": {"email": 1, "whatsapp": 1, "total": 2, "by": {"ours": 1, "dondy": 1}},
                "frt": {"all": {"n": 5, "medianMin": 0, "p90Min": 300}, "email": {"n": 3, "medianMin": 95, "p90Min": 300},
                        "whatsapp": {"n": 2, "medianMin": 0, "p90Min": 9}, "human": {"n": 4, "medianMin": 37, "p90Min": 300},
                        "humanByChannel": {"email": {"n": 3, "medianMin": 95}, "whatsapp": {"n": 1, "medianMin": 12}}},
                "attribution": {"bySender": {"agent1": 2, "auto": 1, "dondy_direct": 1, "gmail_direct": 1}},
                "sources": {"answered": row(2, 1, 1, 0, 0, 0, 1), "closed": row(1, 0, 0, 0, 0, 1, 0), "replies": row(3, 1, 2, 1, 0, 0, 1)},
                # engine 2026-10-07: tickets written to before the desk closed (17:00), by what followed their last message
                "serviceHours": {"closeHour": 17, "received": {"total": 5, "email": 3, "whatsapp": 2}, "person": {"total": 2, "email": 2, "whatsapp": 0},
                                 "auto": {"total": 1, "email": 0, "whatsapp": 1}, "closed": {"total": 1, "email": 1, "whatsapp": 0},
                                 "unanswered": {"total": 1, "email": 0, "whatsapp": 1},
                                 "unansweredTickets": [{"id": x["id"], "ch": "whatsapp", "at": a["date"] + "T13:05:00.000Z"}
                                                       for x in t if x.get("channel") == "whatsapp"][:1]},
                "partial": False, "next": None, "serverMs": 900}

    def apiTicketLite(self, brand, a, c):
        """Engine @35/36 shape: {id, since, seen?} -> {ok, v, changed:false} | {ok, v, changed:true, status, draft_text,
        action, handled_by, msgCount, newMessages[]} (after `seen`, or the last 10 without it)."""
        since, seen = a.get("since"), a.get("seen")
        if not isinstance(since, int) or isinstance(since, bool) or since < 0:
            return {"ok": False, "error": "bad_since"}
        t = self._find(brand, a.get("id"))
        if not t:
            return {"ok": False, "error": "not_found"}
        v = self.touched[brand].get(t["id"], 0)
        if v <= since:
            return {"ok": True, "v": v, "changed": False, "serverMs": 12}
        conv = (self._b(brand)["snaps"].get(t["id"], {}) or {}).get("conversation") or []
        new = conv[seen:] if isinstance(seen, int) and 0 <= seen <= len(conv) else conv[-10:]
        return {"ok": True, "v": v, "changed": True, "status": t["status"], "draft_text": t.get("draft_text", ""),
                "action": t.get("action", ""), "handled_by": t.get("handled_by", ""), "msgCount": len(conv),
                "newMessages": copy.deepcopy(new), "serverMs": 15}

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

    # ---------- managers' notes to the AI (engine AiNotes.gs, 2026-10-11) ----------
    # 2026-10-18: a claim note waits for its document (status needs_file), a document is attached, every active note gets a live check.
    DOC_RE = re.compile(r"(^|[^A-Za-z])(FDA|ISO|GMP|CE)([^A-Za-z]|$)|משרד ה?בריאות|תו[ -]?ה?תקן|מאושר|certif|approved by", re.I)

    def _note_out(self, n):
        o = json.loads(json.dumps(n))
        o["status"] = "needs_file" if self.DOC_RE.search(n["text"]) and not n.get("file") else "active"
        return o

    def apiAiNotes(self, brand, a, c):
        return {"ok": True, "notes": [self._note_out(n) for n in reversed(self.ai_notes[brand])]}

    def apiAiNoteAttach(self, brand, a, c):
        if not isinstance(a.get("id"), str) or not AI_NOTE_ID_RE.match(a["id"]):
            return {"ok": False, "error": "bad_id"}
        if not isinstance(a.get("file"), str) or not re.match(r"^a[0-9a-f]{24}$", a["file"]):
            return {"ok": False, "error": "bad_file"}
        for n in self.ai_notes[brand]:
            if n["id"] == a["id"]:
                meta = self.attach[brand].get(a["file"])
                if not meta or not meta.get("ready"):
                    return {"ok": False, "error": "attach_missing"}
                n["file"] = {"id": a["file"], "name": meta["name"], "mime": meta["mime"], "size": meta["size"], "by": str(c.get("user") or ""), "at": self._now()}
                n.pop("check", None)
                return {"ok": True, "note": self._note_out(n), "redraft": self._redraft(brand)}    # the note came into the prompt
        return {"ok": False, "error": "not_found"}

    def apiAiNoteCheck(self, brand, a, c):
        if not isinstance(a.get("id"), str) or not AI_NOTE_ID_RE.match(a["id"]):
            return {"ok": False, "error": "bad_id"}
        for n in self.ai_notes[brand]:
            if n["id"] == a["id"]:
                reading = "הבנתי: הבוט יגיד ללקוחות: " + n["text"][:80]
                if self._note_out(n)["status"] != "active":       # waiting for its file: the reading only
                    n["check"] = {"at": self._now(), "understood": reading}
                    return {"ok": True, "note": self._note_out(n)}
                if "MOCK-GATE" in n["text"]:      # engine 2026-10-22: the judge said yes, but a fixed rule stopped the production text
                    gate = "קישור לאתר שאינו של המותג"
                    n["check"] = {"at": self._now(), "understood": reading, "q": "שאלה לדוגמה של לקוח", "a": "תשובה לדוגמה של הבוט", "follows": False,
                                  "gate": gate, "why": "כלל קבוע במערכת עצר או החליף את התשובה, ולכן ההערה לא מגיעה ללקוח: " + gate}
                    return {"ok": True, "note": self._note_out(n)}
                fail = "MOCK-NOFOLLOW" in n["text"]
                n["check"] = {"at": self._now(), "understood": reading, "q": "שאלה לדוגמה של לקוח", "a": "תשובה לדוגמה של הבוט", "follows": not fail,
                              "why": "הבוט לא יישם את ההערה" if fail else "הבוט ענה לפי ההערה"}
                return {"ok": True, "note": self._note_out(n)}
        return {"ok": False, "error": "not_found"}

    def apiAiNoteAdd(self, brand, a, c):
        if not isinstance(a.get("id"), str) or not AI_NOTE_ID_RE.match(a["id"]):
            return {"ok": False, "error": "bad_id"}
        if a.get("scope") not in ("all", "brand"):
            return {"ok": False, "error": "bad_scope"}
        text = a.get("text").strip() if isinstance(a.get("text"), str) else ""
        if not text or len(text) > 600:
            return {"ok": False, "error": "bad_text"}
        for n in self.ai_notes[brand]:
            if n["id"] == a["id"]:
                return {"ok": True, "note": self._note_out(n), "noop": True}
        if len(self.ai_notes[brand]) >= 60:
            return {"ok": False, "error": "too_many", "max": 60}
        note = {"id": a["id"], "scope": a["scope"], "text": text, "by": str(c.get("user") or "")[:60], "at": self._now()}
        self.ai_notes[brand].append(note)
        out = {"ok": True, "note": self._note_out(note)}
        if out["note"]["status"] == "active":      # engine 2026-10-22: a change that touched the prompt queues the open drafts' rewrite
            out["redraft"] = self._redraft(brand)
        return out

    def apiAiNoteDelete(self, brand, a, c):
        if not isinstance(a.get("id"), str) or not AI_NOTE_ID_RE.match(a["id"]):
            return {"ok": False, "error": "bad_id"}
        gone = [n for n in self.ai_notes[brand] if n["id"] == a["id"]]
        if not gone:
            return {"ok": True, "noop": True}
        self.ai_notes[brand] = [n for n in self.ai_notes[brand] if n["id"] != a["id"]]
        return {"ok": True, "redraft": self._redraft(brand)} if self._note_out(gone[0])["status"] == "active" else {"ok": True}

    def _redraft(self, brand):
        """How many open AI drafts the engine would write again (engine aiNotesRequeue_). MOCK_REDRAFT_NULL=1 = the queue failed (null)."""
        if os.environ.get("MOCK_REDRAFT_NULL") == "1":
            return None
        return sum(1 for t in self.brands[brand]["tickets"] if t.get("status") in ("ready", "action", "delay", "health") and t.get("draft_text"))

    # ---------- suggestions from the team's corrections (engine AiLearn.gs, 2026-10-22) ----------
    def apiAiNoteSuggestions(self, brand, a, c):
        pending = [json.loads(json.dumps(x)) for x in self.ai_sugg[brand] if x["state"] == "pending"]
        return {"ok": True, "suggestions": list(reversed(pending)), "corrections": self.ai_corrections.get(brand, 0)}

    def apiAiNoteSuggestDecide(self, brand, a, c):
        if not isinstance(a.get("id"), str) or not re.match(r"^s[0-9a-f]{16}$", a["id"]):
            return {"ok": False, "error": "bad_id"}
        if a.get("decision") not in ("approve", "reject"):
            return {"ok": False, "error": "bad_decision"}
        hit = next((x for x in self.ai_sugg[brand] if x["id"] == a["id"]), None)
        if not hit:
            return {"ok": False, "error": "not_found"}
        if hit["state"] != "pending":
            return {"ok": True, "suggestion": json.loads(json.dumps(hit)), "noop": True}
        out = {"ok": True}
        if a["decision"] == "approve":
            text = hit["text"] if a.get("text") is None else (a["text"].strip() if isinstance(a["text"], str) else "")
            if not text or len(text) > 600:
                return {"ok": False, "error": "bad_text"}
            added = self.apiAiNoteAdd(brand, {"id": a["id"][1:], "scope": "brand", "text": text}, c)
            if not added.get("ok"):
                return added
            out["note"] = added["note"]
            if os.environ.get("MOCK_DECIDE_REDRAFT") == "1" and "redraft" in added:
                out["redraft"] = added["redraft"]   # today's engine drops it on a decide; the screen shows it if one ever comes
        hit.update({"state": "approved" if a["decision"] == "approve" else "rejected", "by": str(c.get("user") or "")[:60], "decidedAt": self._now()})
        out["suggestion"] = json.loads(json.dumps(hit))
        return out

    # ---------- sales log (engine Sales.gs, 2026-10-14) ----------
    # The same contract and rules as the engine (verification codes, one order once, roles), over canned Shopify orders.
    WINDOW_H = 72
    SHOP_ORDERS = {"rozela": {"dana.s@example.com": [
        {"id": "gid://shopify/Order/5004601", "name": "#4601", "age_h": 30, "total": "299.80", "items": [("Rozela x3 חבילה", 1)]},
        {"id": "gid://shopify/Order/5004599", "name": "#4599", "age_h": 200, "total": "149.90", "items": [("Rozela", 1)]},
        {"id": "gid://shopify/Order/5004602", "name": "#4602", "age_h": 29, "total": "149.90", "items": [("Rozela", 1)], "cancelled": True}],
        "other.person@example.com": [{"id": "gid://shopify/Order/5004700", "name": "#4700", "age_h": 10, "total": "99.00", "items": [("Rozela", 1)]}]}}

    def _init_sales(self):
        now = datetime.now(timezone.utc)
        self.sales = {b: [] for b in MOCK_BRANDS}
        self.sug = {b: [] for b in MOCK_BRANDS}
        h = lambda x: _iso(now - timedelta(hours=x))

        def seed(brand, order, ticket, agent, amount, status, reasons=(), decision="", by="", hours=20, name="לקוחה לדוגמה"):
            self.sales[brand].append({
                "id": "o" + order[1:], "created_at": h(hours), "brand": brand, "ticket": ticket, "channel": "email", "agent": agent, "logged_by": agent, "source": "agent",
                "order_id": "gid://shopify/Order/50" + order[1:], "order_name": order, "amount": amount, "currency": "ILS", "items": "Rozela", "order_created_at": h(hours + 2),
                "customer_name": name, "customer_phone": "", "customer_email": "x@example.com", "status": status, "reasons": list(reasons),
                "first_reply_at": h(hours + 8), "last_reply_at": h(hours + 6), "last_agent": agent, "decision": decision, "decided_by": by, "decided_at": h(1) if by else "",
                "decision_note": "", "note": "", "month": datetime.now().strftime("%Y-%m"), "history": [],
                "effective": decision or ("verified" if status == "verified" else "review"),
                "_proof": {"frozen_at": h(hours), "channel": "email", "subject": "שאלה לפני רכישה", "customer": name, "cut": 0,
                           "messages": [{"who": "customer", "at": h(hours + 9), "text": "שלום, כמה עולה חבילת 3 חודשים?"},
                                        {"who": "us", "at": h(hours + 8), "text": "היי, 299.8 ש\"ח עם משלוח חינם."}]}})
        seed("rozela", "#4590", "t18f2c03", "agent-two", 149.9, "verified")
        seed("rozela", "#4591", "t18f2c01", "amit", 299.8, "review", ["other_agent:agent-two"], hours=30)
        seed("celesta", "#3301", "t18f2c03", "agent-two", 199.0, "review", ["outside_window"], "approved", "guy", hours=50)
        self.sug["rozela"].append({"id": "o4610", "ticket": "t18f2c02", "channel": "email", "agent": "agent-two", "order_id": "gid://shopify/Order/5004610", "order_name": "#4610",
                                   "amount": 149.9, "currency": "ILS", "items": "Rozela", "order_created_at": h(12), "customer_name": "אילנה ג.", "first_reply_at": h(30),
                                   "last_reply_at": h(26), "reasons": [], "found_at": h(2), "state": "open"})
        self.sug["rozela"].append({"id": "o4611", "ticket": "t18f2c01", "channel": "whatsapp", "agent": "", "order_id": "gid://shopify/Order/5004611", "order_name": "#4611",
                                   "amount": 299.8, "currency": "ILS", "items": "Rozela x2", "order_created_at": h(9), "customer_name": "מיכל לוי", "first_reply_at": h(20),
                                   "last_reply_at": h(15), "reasons": [], "found_at": h(2), "state": "open"})
        self.scan_at = {b: None for b in MOCK_BRANDS}

    @staticmethod
    def _sale_pub(r):
        return {k: v for k, v in r.items() if not k.startswith("_")}

    def _sale_summary(self, rows):
        by = {}
        for r in rows:
            s = by.setdefault((r["agent"], r["month"]), {"agent": r["agent"], "month": r["month"], "count": 0, "revenue": {}, "review": 0, "rejected": 0})
            e = r["effective"]
            if e in ("approved", "verified"):
                s["count"] += 1
                s["revenue"][r["currency"]] = round(s["revenue"].get(r["currency"], 0) + r["amount"], 2)
            elif e == "review":
                s["review"] += 1
            else:
                s["rejected"] += 1
        return sorted(by.values(), key=lambda x: (x["month"], x["agent"]), reverse=True)

    def _sale_orders(self, brand, t):
        return self.SHOP_ORDERS.get(brand, {}).get(str(t.get("email") or "").lower(), [])

    def _sale_first_reply(self, brand, tid):
        conv = self._b(brand)["snaps"].get(tid, {}).get("conversation", [])
        us = [m["at"] for m in conv if m["who"] == "us"]
        return min(us) if us else None

    def apiSaleCandidates(self, brand, a, c):
        t = self._find(brand, a.get("id"), archive=True)
        if not t:
            return {"ok": False, "error": "not_found"}
        first = self._sale_first_reply(brand, t["id"])
        if not (t.get("email") or t.get("phone")):
            return {"ok": True, "ticket": t["id"], "window_hours": self.WINDOW_H, "credit": "logger", "first_reply_at": first or "", "orders": [], "lookup": "no_contact"}
        now = datetime.now(timezone.utc)
        held = {r["order_id"]: r for r in self.sales[brand] if r["decision"] != "rejected"}
        out = []
        for o in self._sale_orders(brand, t):
            created = _iso(now - timedelta(hours=o["age_h"]))
            h_ = held.get(o["id"])
            out.append({"id": o["id"], "name": o["name"], "createdAt": created, "amount": float(o["total"]), "currency": "ILS", "cancelled": bool(o.get("cancelled")),
                        "items": "; ".join(t_ for t_, _q in o["items"]), "financial": "PAID", "after_reply": bool(first) and created >= first,
                        "credited": {"agent": h_["agent"], "effective": h_["effective"]} if h_ else None})
        return {"ok": True, "ticket": t["id"], "window_hours": self.WINDOW_H, "credit": "logger", "first_reply_at": first or "", "orders": out,
                "lookup": "ok" if out else "none"}

    def apiSaleLog(self, brand, a, c):
        t = self._find(brand, a.get("id"), archive=True)
        if not isinstance(a.get("orderNo"), str) or not re.match(r"^#?\d{3,9}$", a["orderNo"].strip()):
            return {"ok": False, "error": "bad_order"}
        if not t:
            return {"ok": False, "error": "not_found"}
        name = "#" + a["orderNo"].strip().lstrip("#")
        found = None
        for email, lst in self.SHOP_ORDERS.get(brand, {}).items():
            for o in lst:
                if o["name"] == name:
                    found = (email, o)
        if not found:
            return {"ok": False, "error": "order_not_found"}
        email, o = found
        key = "o" + o["id"].rsplit("/", 1)[1]
        cur = next((r for r in self.sales[brand] if r["id"] == key), None)
        if cur and cur["decision"] != "rejected":
            if cur["agent"] == c["user"] and cur["ticket"] == t["id"]:
                return {"ok": True, "noop": True, "sale": self._sale_pub(cur)}
            return {"ok": False, "error": "order_already_credited", "by": cur["agent"], "at": cur["created_at"], "ticket": cur["ticket"]}
        now = datetime.now(timezone.utc)
        created = _iso(now - timedelta(hours=o["age_h"]))
        first = self._sale_first_reply(brand, t["id"])
        reasons = []
        if o.get("cancelled"):
            reasons.append("order_cancelled")
        if email != str(t.get("email") or "").lower():
            reasons.append("contact_mismatch")
        if not first:
            reasons.append("no_agent_reply")
        elif created < first:
            reasons.append("before_reply")
        snap_us = [m for m in self._b(brand)["snaps"].get(t["id"], {}).get("conversation", []) if m["who"] == "us"]
        if snap_us and t.get("handled_by") and t["handled_by"] != c["user"]:
            reasons.append("other_agent:" + t["handled_by"])
        conv = self._b(brand)["snaps"].get(t["id"], {}).get("conversation", [])
        rec = {"id": key, "created_at": self._now(), "brand": brand, "ticket": t["id"], "channel": t.get("channel") or "email", "agent": c["user"], "logged_by": c["user"], "source": "agent",
               "order_id": o["id"], "order_name": o["name"], "amount": float(o["total"]), "currency": "ILS", "items": "; ".join(x for x, _q in o["items"]), "order_created_at": created,
               "customer_name": t.get("name") or "", "customer_phone": t.get("phone") or "", "customer_email": t.get("email") or "",
               "status": "review" if reasons else "verified", "reasons": reasons, "first_reply_at": first or "", "last_reply_at": first or "", "last_agent": t.get("handled_by") or "",
               "decision": "", "decided_by": "", "decided_at": "", "decision_note": "", "note": str(a.get("note") or ""), "month": datetime.now().strftime("%Y-%m"),
               "history": [], "effective": "review" if reasons else "verified",
               "_proof": {"frozen_at": self._now(), "channel": t.get("channel"), "subject": t.get("subject"), "customer": t.get("name"), "cut": 0,
                          "messages": [{"who": m["who"], "at": m["at"], "text": m["text"]} for m in conv]}}
        if cur:
            rec["history"] = [{"agent": cur["agent"], "at": cur["created_at"], "decision": cur["decision"], "by": cur["decided_by"], "note": ""}]
            self.sales[brand].remove(cur)
        self.sales[brand].append(rec)
        return {"ok": True, "sale": self._sale_pub(rec)}

    def apiSaleMine(self, brand, a, c):
        rows = sorted([r for r in self.sales[brand] if r["agent"] == c["user"]], key=lambda r: r["created_at"], reverse=True)
        return {"ok": True, "user": c["user"], "config": {"windowHours": self.WINDOW_H, "credit": "logger"}, "sales": [self._sale_pub(r) for r in rows],
                "summary": self._sale_summary(rows)}

    def apiSaleProof(self, brand, a, c):
        r = next((x for x in self.sales[brand] if x["id"] == a.get("id")), None)
        if not r:
            return {"ok": False, "error": "not_found"}
        if c["role"] != "admin" and r["agent"] != c["user"]:
            return {"ok": False, "error": "unauthorized"}
        return {"ok": True, "id": r["id"], "proof": r["_proof"]}

    def apiCancelStats(self, brand, a, c):
        """Engine contract (2026-10-23): {brand, tz, kaching, days[{date, subs_team, subs_team_by, subs_bot, subs_all_kaching, orders_cancelled}],
        month, prev_month, sources}. Fixed numbers from a hash of brand + day, so a test can compute the expected totals."""
        frm, to = a.get("from"), a.get("to")
        try:
            d0, d1 = datetime.strptime(frm, "%Y-%m-%d"), datetime.strptime(to, "%Y-%m-%d")
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_date"}
        if d0 > d1 or (d1 - d0).days >= 62:
            return {"ok": False, "error": "bad_range"}
        over = dict(x.split(":", 1) for x in os.environ.get("MOCK_CANCEL_STATE", "").split(",") if ":" in x)
        state = over.get(brand) or ("no_subscriptions" if brand == "selera" else "ok")
        days, d = [], d0
        while d <= d1:
            ds = d.strftime("%Y-%m-%d")
            hv = int(hashlib.sha256((brand + ds).encode()).hexdigest()[:8], 16)
            team_by = {"agent-two": hv % 4, "amit": (hv >> 4) % 3, "qa-check": 1} if state in ("ok", "no_kaching") else {}
            team_by = {k: v for k, v in team_by.items() if v}
            days.append({"date": ds, "subs_team": sum(team_by.values()), "subs_team_by": team_by, "subs_bot": (hv >> 8) % 3,
                         "subs_all_kaching": None if state != "ok" else sum(team_by.values()) + (hv >> 8) % 3 + (hv >> 12) % 4,
                         "orders_cancelled": None if state == "error" else (hv >> 16) % 5})
            d += timedelta(days=1)
        mo = {"rozela": (56, 820, 6.83, 112, 795, 14.09), "celesta": (55, 500, 11.0, 86, 491, 17.52), "apexmen": (40, 380, 10.53, 64, 376, 17.02)}.get(brand)
        month = prev = {"month": None, "active_start": None, "cancelled": None, "churn_pct": None, "partial": False}
        if mo and state == "ok":
            pm = (d1.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            month = {"month": to[:7], "cancelled": mo[0], "active_start": mo[1], "churn_pct": mo[2], "partial": True}
            prev = {"month": pm, "cancelled": mo[3], "active_start": mo[4], "churn_pct": mo[5], "partial": False}
        return {"ok": True, "brand": brand, "tz": "Asia/Jerusalem", "kaching": state, "days": days, "month": month, "prev_month": prev,
                "sources": {"subs_team": "ביטול מנוי מהמסך (כפתור, אחרי שליחה, תור הביטולים) — יומן הביקורת של המנוע",
                            "subs_bot": "ביטול אוטומטי של המנוע (auto-cancel) — יומן הביקורת",
                            "orders_cancelled": "הזמנות שבוטלו בשופיפיי לפי cancelled_at",
                            "subs_all_kaching": "כל החוזים שעברו ל-CANCELLED בקאצ׳ינג, מכל מקור",
                            "churn_pct": "ביטולים בחודש ÷ מנויים פעילים בתחילת החודש (קאצ׳ינג)"}, "serverMs": 2400}

    def apiSaleList(self, brand, a, c):
        rows = sorted(self.sales[brand], key=lambda r: r["created_at"], reverse=True)
        return {"ok": True, "brand": brand, "shop": MYSHOPIFY.get(brand, ""), "config": {"windowHours": self.WINDOW_H, "credit": "logger", "suggestDays": 7},
                "sales": [self._sale_pub(r) for r in rows], "summary": self._sale_summary(rows),
                "suggestions": len([s for s in self.sug[brand] if s["state"] == "open"])}

    def apiSaleDecide(self, brand, a, c):
        r = next((x for x in self.sales[brand] if x["id"] == a.get("id")), None)
        if a.get("decision") not in ("approved", "rejected", "clear"):
            return {"ok": False, "error": "bad_decision"}
        if not r:
            return {"ok": False, "error": "not_found"}
        clear = a["decision"] == "clear"
        r.update({"decision": "" if clear else a["decision"], "decided_by": "" if clear else c["user"], "decided_at": "" if clear else self._now(),
                  "decision_note": "" if clear else str(a.get("note") or "")})
        r["effective"] = r["decision"] or ("verified" if r["status"] == "verified" else "review")
        return {"ok": True, "sale": self._sale_pub(r)}

    def apiSaleSuggestions(self, brand, a, c):
        agents = sorted({r["agent"] for r in self.sales[brand]} | {"agent-two", "amit"})
        return {"ok": True, "agents": agents, "items": [dict(s) for s in self.sug[brand] if s["state"] == "open"],
                "scan": {"at": self.scan_at[brand] or "", "ageMin": None if not self.scan_at[brand] else 0}, "config": {"windowHours": self.WINDOW_H, "suggestDays": 7}}

    def apiSaleSuggestCredit(self, brand, a, c):
        s = next((x for x in self.sug[brand] if x["id"] == a.get("id") and x["state"] == "open"), None)
        if not s:
            return {"ok": False, "error": "not_found"}
        agent = s["agent"] or str(a.get("agent") or "")
        if not agent:
            return {"ok": False, "error": "no_agent"}
        now = self._now()
        rec = {"id": s["id"], "created_at": now, "brand": brand, "ticket": s["ticket"], "channel": s["channel"], "agent": agent, "logged_by": c["user"], "source": "detected",
               "order_id": s["order_id"], "order_name": s["order_name"], "amount": s["amount"], "currency": s["currency"], "items": s["items"], "order_created_at": s["order_created_at"],
               "customer_name": s["customer_name"], "customer_phone": "", "customer_email": "", "status": "verified", "reasons": [], "first_reply_at": s["first_reply_at"],
               "last_reply_at": s["last_reply_at"], "last_agent": agent, "decision": "approved", "decided_by": c["user"], "decided_at": now, "decision_note": "", "note": "",
               "month": datetime.now().strftime("%Y-%m"), "history": [], "effective": "approved",
               "_proof": {"frozen_at": now, "channel": s["channel"], "subject": "", "customer": s["customer_name"], "cut": 0, "messages": []}}
        self.sales[brand].append(rec)
        s["state"] = "credited"
        return {"ok": True, "sale": self._sale_pub(rec)}

    def apiSaleSuggestDismiss(self, brand, a, c):
        s = next((x for x in self.sug[brand] if x["id"] == a.get("id")), None)
        if not s:
            return {"ok": False, "error": "not_found"}
        s["state"] = "dismissed"
        return {"ok": True}

    def apiSaleScan(self, brand, a, c):
        self.scan_at[brand] = self._now()
        return {"ok": True, "result": {"candidates": 3, "checked": 3, "found": 0, "skipped": 0, "partial": False}}

    def apiResult(self, brand, a, c):
        hit = self.results[brand].get(a.get("rid"))
        if not hit:
            return {"ok": True, "found": False}
        fn, _u, reply = hit
        return {"ok": True, "found": True, "forFn": fn, "reply": dict(reply, fn=fn, rid=a.get("rid"))}



# ---------- מילוי מיקודים (zip-code fill) — preview/test runner for zipfix.JobManager (2026-10-10) ----------
# The real routes and jobs are zipfix/routes.py + zipfix/jobs.py. Only the RUNNER (Shopify + the zip sources) is faked,
# so the preview and the browser tests exercise the real job lifecycle, gates and error codes. Pass it as
#   create_app({"ZIPFIX_RUNNER": mock_engine.zipfix_runner, "ZIPFIX_CONFIGURED": lambda b: True})
# Hooks: order 666 fails the run half way ("shopify" error → shopify_failed); MOCK_ZIPFIX_STEP_MS = time per order (400).
_ZIP_CITIES = (("תל אביב-יפו", "דיזנגוף 112"), ("חיפה", "שדרות מוריה 45"), ("ירושלים", "עמק רפאים 30"),
               ("באר שבע", "רגר 18"), ("ראשון לציון", "הרצל 70"), ("פתח תקווה", "ז׳בוטינסקי 3"),
               ("אשדוד", "הנשיאים 9"), ("נתניה", "שדרות בנימין 21"), ("רמת גן", "ביאליק 50"), ("קריית שמונה", "תל חי 4"))
_ZIP_REASONS = ("אין מספר בית בכתובת — המיקוד לפי הרחוב בלבד", "לרחוב יש כמה מיקודים — נבחר לפי מספר הבית, כדאי לוודא",
                "שם הרחוב לא נמצא כמו שהוא — נבחר השם הקרוב")


def zipfix_runner(brand, nums=None, progress=None):
    step = float(os.environ.get("MOCK_ZIPFIX_STEP_MS", "400")) / 1000.0
    prog = progress or (lambda d, t: None)
    if nums is None:
        base = {"rozela": 1640, "celesta": 3210, "apexmen": 870, "selera": 5100, "velora": 2200}.get(brand, 1000)
        nums = [str(base + i) for i in range(12)]
    orders = [o for o in nums if o != "404"]                     # 404 = an order the store does not have
    total = len(orders)
    prog(0, total)
    lines, review, ask = [], [], []
    for i, o in enumerate(orders):
        time.sleep(step)
        if o == "666" and i >= total // 2:
            raise RuntimeError("shopify: mock outage")
        n = int(o)
        city, addr = _ZIP_CITIES[n % len(_ZIP_CITIES)]
        zipc = "%07d" % (1000000 + (n * 7919) % 8999999)
        if n % 10 == 9:
            ask.append({"order": o, "city": city, "address": addr.rsplit(" ", 1)[0]})   # street only: no house number
        else:
            lines.append("%s - %s" % (o, zipc))
            if n % 10 in (3, 7):
                review.append({"order": o, "zip": zipc, "reason": _ZIP_REASONS[n % 3], "city": city, "address": addr})
        prog(i + 1, total)
    return {"supplier_text": "\n".join(lines), "review": review, "ask_customer": ask,
            "counts": {"orders": total, "zips": len(lines), "review": len(review), "ask": len(ask)},
            "brand": brand, "ran_at": _iso(datetime.now(timezone.utc)), "not_found": [o for o in nums if o == "404"]}
