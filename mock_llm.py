"""
mock_llm.py — a deterministic stand-in for the Anthropic Messages API (local preview + screenshots only).

It does NOT judge anything: the real refusal of other-brand questions comes from the system prompt
rule in assistant.py. This mock imitates the expected behaviour so the screen can be clicked offline.
"""
import json
import re

BRAND_WORDS = {"rozela": ("rozela", "רוזלה"), "celesta": ("celesta", "סלסטה"), "apexmen": ("apexmen", "אייפקס"),
               "velora": ("velora", "ולורה"), "selera": ("selera", "סלרה"), "elevanu": ("elevanu", "אלבנו")}

EN = {
    "למה חייבתם אותי שוב?? לא ביקשתי שום מנוי.": "Why did you charge me again?? I never asked for any subscription.",
    "היי יוסי, מבינים את התסכול. המנוי נבחר בעמוד התשלום, אבל אפשר לבטל אותו מתי שרוצים. רוצה שנבטל?\n\nיהודה\nצוות Rozela":
        "Hi Yossi, we understand the frustration. The subscription was selected on the checkout page, but you can cancel it any time. "
        "Want us to cancel it?\n\nYehuda\nRozela Team",
    "כועס: לא ביקש מנוי, חויב שוב. רוצה לבטל מיד ומאיים בביטול עסקה.":
        "Angry: did not ask for a subscription, was charged again. Wants to cancel now and threatens a chargeback.",
    "היי יוסי, ביטלתי את המנוי כך שלא יהיו חיובים נוספים. ההזמנה האחרונה כבר בדרך אליך.\n\nיהודה\nצוות Rozela":
        "Hi Yossi, I cancelled the subscription so there will be no more charges. Your last order is already on its way.\n\nYehuda\nRozela Team",
}
EN.update({
    "היי, מתי ההזמנה שלי אמורה להגיע?": "Hi, when is my order supposed to arrive?",
    "שאלה פשוטה על זמן משלוח.": "A simple question about delivery time.",
    "היי טל, ההזמנה יצאה לפני 3 ימים ונמצאת בדרך: https://t.17track.net/en#nums=JY4516000777\nבדרך כלל זה מגיע תוך שבוע-שבועיים.\n\nיהודה\nצוות Rozela":
        "Hi Tal, your order left 3 days ago and is on its way: https://t.17track.net/en#nums=JY4516000777\nIt usually arrives within one to two weeks.\n\nYehuda\nRozela Team",
    "לוודא שקישור המעקב נכון ושהטון חם. אם תקין — לסמן נבדק.": "Check the tracking link is right and the tone is warm. If fine, mark it reviewed.",
    "לבטל את המנוי בכפתור בפאנל המנויים, ואז לשלוח את הטיוטה.": "Cancel the subscription with the button in the subscriptions panel, then send the draft.",
    "לשלוח את הטיוטה אחרי בדיקה מהירה של המינון.": "Send the draft after a quick check of the dosage.",
    "שואלת כמה כמוסות לוקחים ביום ואם אפשר עם ארוחה.": "Asks how many capsules to take a day and whether with a meal.",
    "שואלת איפה ההזמנה #4512 — נשלחה לפני 4 ימים, עדיין בזמן.": "Asks where order #4512 is — shipped 4 days ago, still on time.",
    "לשלוח את הטיוטה — ההזמנה בזמן; לוודא שקישור המעקב נכון.": "Send the draft — the order is on time; check the tracking link.",
    "שואלת אם אפשר עם קפה.": "Asks whether it can be taken with coffee.",
    "שלום, אפשר לקחת את הכמוסות יחד עם קפה בבוקר?": "Hello, can I take the capsules together with my morning coffee?",
    "היי אילנה, כן, אפשר לקחת גם עם קפה. הכי נוח עם ארוחה.\n\nיהודה\nצוות Rozela": "Hi Ilana, yes, you can take them with coffee too. Easiest with a meal.\n\nYehuda\nRozela Team",
    "ביקש מספר מעקב.": "Asked for a tracking number.",
    "אפשר מספר מעקב?": "Can I have a tracking number?",
    "היי רועי, הנה הקישור למעקב.\n\nיהודה\nצוות Rozela": "Hi Roi, here is the tracking link.\n\nYehuda\nRozela Team",
})

HE = {
    "Hi Yossi, I cancelled the subscription right away, so there will be no more charges. Your last order is already on its way to you.\n\nYehuda\nRozela Team":
        "היי יוסי, ביטלתי את המנוי מיד, כך שלא יהיו עוד חיובים. ההזמנה האחרונה כבר בדרך אליך.\n\nיהודה\nצוות Rozela",
}


def _sys(payload):
    s = payload.get("system")
    return "\n".join(b.get("text", "") for b in s) if isinstance(s, list) else str(s or "")


def _resp(text=None, tool=None):
    if tool:
        return {"content": [{"type": "text", "text": ""}, {"type": "tool_use", "id": "toolu_mock1", "name": tool[0], "input": tool[1]}],
                "stop_reason": "tool_use"}
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


class MockClaude:
    def __init__(self):
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        sys_text = _sys(payload)
        if "Task: translate-" in sys_text:
            items = json.loads(payload["messages"][-1]["content"])["items"]
            table = HE if "Task: translate-out" in sys_text else EN
            pref = "(HE) " if table is HE else "(EN) "
            out = [{"i": it["i"], "text": table.get(it["text"], "שלום, תודה על הפנייה. אנחנו בודקים ונעדכן בהקדם." if table is HE else pref + it["text"])} for it in items]
            return _resp(json.dumps({"translations": out}, ensure_ascii=False))
        he = "Answer in Hebrew" in sys_text
        brand = (re.search(r"Brand: .*?\(([a-z0-9-]+)\)", sys_text) or [None, ""])[1]
        last = payload["messages"][-1]["content"]
        if isinstance(last, list):                 # tool results came back
            res = json.loads(last[0]["content"])
            n_o = len(res.get("orders") or [])
            subs = res.get("subscriptions")
            n_s = len(subs) if isinstance(subs, list) else 0
            last_o = (res.get("orders") or [{}])[0]
            if he:
                txt = ("מצאתי %d הזמנות ו-%d מנויים. האחרונה: %s מ-%s, סטטוס משלוח: %s.\nאם הלקוח מבקש ביטול מנוי — הכפתור \"ביטול מנוי\" בפאנל המנויים של הפנייה."
                       % (n_o, n_s, last_o.get("name", "—"), last_o.get("ordered", "—"), last_o.get("fulfillment", "—")))
            else:
                txt = "Found %d orders and %d subscriptions. Latest: %s from %s." % (n_o, n_s, last_o.get("name", "—"), last_o.get("ordered", "—"))
            return _resp(txt)
        q = last.lower()
        for b, words in BRAND_WORDS.items():
            if b != brand and any(w in q for w in words):
                name = words[0].capitalize()
                cur = (brand or "").capitalize()
                return _resp("זה לא זמין כאן — אני עונה רק על %s. כדי לשאול על %s, החליפו מותג בראש המסך." % (cur, name) if he else
                             "That is not available here — I only answer about %s. Switch brand at the top of the screen to ask about %s." % (cur, name))
        m = re.search(r"[\w.+-]+@[\w.-]+|#?\d{4,}", last)
        if m:
            return _resp(tool=("search_customer", {"q": m.group(0)}))
        rules = [l for l in sys_text.splitlines() if re.match(r"^\d+\. ", l)]
        hit = next((r for r in rules if any(w in r for w in re.findall(r"[֐-׿]{3,}", last))), rules[0] if rules else "")
        if he:
            return _resp("לפי המדיניות: %s\nאפשר לענות ללקוח:\n\"היי, אין בעיה — ההחזר מלא לפי האחריות של 90 יום, גם על בקבוק פתוח. אני מעבירה את זה לטיפול ותקבל/י עדכון כשההחזר יוצא.\"" % hit.split(". ", 1)[-1])
        return _resp("Per the policy: %s" % hit.split(". ", 1)[-1])
