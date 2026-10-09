"""
messages.py — every message the team reads, in Hebrew (and English for /cs/en).

One place, server side, so the proxy, the user manager and the tests all speak the same words.
Engine answers keep their raw text (`message`, `problem`) next to the translation (`msg`), so a
support person can quote the exact gate wording to Guy.

The Kaching gate (engine/Kaching.gs) and draftProblem (engine/Safety.gs) return English sentences.
They are matched here by pattern, not by exact string, and anything unknown falls back to a generic
line plus the raw text — a new engine message is never swallowed.
"""

import re

PROXY = {
    "not_logged_in": ("צריך להתחבר מחדש.", "Please sign in again."),
    "csrf": ("הדף התיישן. רעננו את הדף ונסו שוב.", "This page is out of date. Refresh and try again."),
    "forbidden_brand": ("אין לך הרשאה למותג הזה.", "You do not have access to this brand."),
    "forbidden_fn": ("הפעולה הזאת לא זמינה מהמסך.", "This action is not available from the screen."),
    "forbidden_role": ("לתפקיד שלך אין הרשאה לפעולה הזאת.", "Your role cannot do this."),
    "brand_not_connected": ("המותג הזה עוד לא מחובר למערכת.", "This brand is not connected yet."),
    "bad_request": ("הבקשה לא תקינה.", "Bad request."),
    "bad_note": ("הערה של 2 עד 300 תווים.", "A note of 2 to 300 characters."),
    # phase 5: assistant + English mode
    "assistant_off": ("העוזר כבוי (חסר מפתח Anthropic בשרת). לדווח לבעלים.", "The assistant is off (no Anthropic key on the server). Tell the owner."),
    "assistant_misconfigured": ("מפתח ה-Anthropic בשרת לא תקין. לדווח לבעלים.", "The server's Anthropic key is invalid. Tell the owner."),
    "assistant_busy": ("שירות ה-AI עמוס כרגע. נסו שוב בעוד דקה.", "The AI service is busy. Try again in a minute."),
    "assistant_timeout": ("העוזר לא ענה בזמן. נסו שאלה קצרה יותר או שוב בעוד רגע.", "The assistant did not answer in time. Try a shorter question."),
    "assistant_unreachable": ("אין חיבור לשירות ה-AI. נסו שוב בעוד רגע.", "Cannot reach the AI service. Try again shortly."),
    "assistant_error": ("תשובה לא תקינה משירות ה-AI. נסו שוב.", "Invalid answer from the AI service. Try again."),
    "knowledge_unavailable": ("מאגר הידע של המותג עוד לא זמין במנוע — העוזר לא עונה בלעדיו (כדי לא להמציא מדיניות).",
                              "The brand's knowledge is not available from the engine yet — the assistant will not answer without it."),
    "translate_failed": ("התרגום נכשל. נסו שוב.", "The translation failed. Try again."),
    "not_found": ("לא נמצא.", "Not found."),
    "engine_timeout": ("המנוע לא ענה בזמן. נסו שוב בעוד רגע — הפעולה אולי בוצעה, רעננו לפני שחוזרים ענציגה ב.",
                       "The engine did not answer in time. The action may have happened; refresh before repeating it."),
    "engine_unreachable": ("אין חיבור למנוע של המותג. נסו שוב בעוד רגע.", "Cannot reach the brand engine. Try again shortly."),
    "write_unknown": ("לא הצלחנו לאשר אם הפעולה בוצעה — רעננו את הפנייה ובדקו.",
                      "We could not confirm whether the action went through — refresh the ticket and check."),
    "engine_bad_response_write": ("המנוע החזיר שגיאה זמנית — ייתכן שהפעולה בוצעה. רעננו את הפנייה ובדקו לפני שמנסים שוב.",
                                  "The engine returned a temporary error — the action may have happened. Refresh the ticket and check before trying again."),
    "engine_bad_response": ("המנוע החזיר תשובה לא תקינה. אם זה חוזר — לדווח למנהל.",
                            "The engine sent an invalid answer. If it repeats, tell Manager."),
    "server_error": ("תקלה זמנית בשרת. נסו שוב בעוד רגע.", "A temporary server error. Try again in a moment."),
    "server_misconfigured": ("המערכת לא מוגדרת עד הסוף (חסר מפתח). לדווח לבעלים.",
                             "The system is not fully configured (missing key). Tell the owner."),
    "rate_limited": ("יותר מדי ניסיונות. נסו שוב בעוד {wait} דקות.", "Too many attempts. Try again in {wait} minutes."),
    "bad_login": ("שם משתמש או סיסמה שגויים.", "Wrong username or password."),
    "password_too_short": ("סיסמה של 10 תווים לפחות.", "At least 10 characters."),
    "password_too_long": ("הסיסמה ארוכה מדי.", "Password is too long."),
    "password_contains_username": ("הסיסמה לא יכולה להכיל את שם המשתמש.", "The password cannot contain the username."),
    "password_too_simple": ("הסיסמה פשוטה מדי.", "Password is too simple."),
    "password_mismatch": ("שתי הסיסמאות לא זהות.", "The two passwords differ."),
    "password_same": ("הסיסמה החדשה זהה לישנה.", "The new password equals the old one."),
    "wrong_current_password": ("הסיסמה הנוכחית שגויה.", "Current password is wrong."),
    # user manager
    "bad_username": ("שם משתמש: אותיות לועזיות קטנות, ספרות, נקודה, מקף. 2-32 תווים.",
                     "Username: lowercase letters, digits, dot, dash. 2-32 characters."),
    "user_exists": ("שם המשתמש הזה כבר קיים.", "That username exists."),
    "not_found": ("המשתמש לא נמצא.", "User not found."),
    "bad_roles": ("צריך לבחור לפחות תפקיד אחד.", "Pick at least one role."),
    "bad_brands": ("רשימת מותגים לא תקינה.", "Invalid brand list."),
    "unknown_brand": ("מותג לא מוכר.", "Unknown brand."),
    "bad_lang": ("שפה לא תקינה.", "Invalid language."),
    "bad_display_name": ("שם תצוגה ארוך מדי.", "Display name too long."),
    "bad_disabled": ("ערך לא תקין.", "Invalid value."),
    "only_admin_grants_admin": ("רק אדמין יכול לתת או להסיר הרשאת אדמין, או לערוך משתמש אדמין.",
                                "Only an admin can grant or remove admin, or edit an admin user."),
    "self_lockout": ("אי אפשר לנעול או להוריד הרשאות לעצמך.", "You cannot disable yourself or remove your own access."),
    "last_admin": ("חייב להישאר לפחות אדמין פעיל אחד.", "At least one active admin must remain."),
    "users_file_corrupt": ("קובץ המשתמשים פגום. לדווח לבעלים.", "The users file is damaged. Tell the owner."),
}

# Api.gs error codes ({ok:false, error:<code>})
ENGINE = {
    "unauthorized": ("המנוע סירב להרשאה (פג תוקף, תפקיד או מותג לא תואם). רעננו את הדף.",
                     "The engine refused the credentials (expired, role or brand mismatch). Refresh."),
    "busy": ("המערכת באמצע פעולה אחרת. נסו שוב בעוד כמה שניות.", "The engine is busy. Try again in a few seconds."),
    "server_error": ("תקלה במנוע. נרשמה ביומן; נסו שוב או דווחו.", "Engine error. It was logged; try again or report it."),
    "bad_request": ("הבקשה לא תקינה.", "Bad request."),
    "bad_id": ("מזהה פנייה לא תקין.", "Invalid ticket id."),
    "bad_ids": ("רשימת מזהים לא תקינה.", "Invalid id list."),
    "not_found": ("הפנייה לא נמצאה (אולי הועברה לארכיון).", "Ticket not found (maybe archived)."),
    "bad_query": ("חיפוש: 2 עד 100 תווים.", "Search: 2 to 100 characters."),
    "bad_text": ("הטקסט ריק או ארוך מדי.", "The text is empty or too long."),
    "not_open": ("הפנייה כבר לא פתוחה — אי אפשר לשמור בה טיוטה.", "The ticket is no longer open."),
    "dry_run": ("מצב ניסיון — שליחה כבויה.", "Test mode — sending is off."),
    "already_handled": ("מישהו כבר טיפל בפנייה הזאת.", "Someone already handled this ticket."),
    "draft_problem": ("בדיקת הבטיחות עצרה את השליחה: {problem}", "The safety check stopped the send: {problem}"),
    "bad_channel": ("ערוץ לא נתמך לשליחה.", "Unsupported channel."),
    "thread_missing": ("השרשור לא נמצא ב-Gmail.", "The Gmail thread is missing."),
    "replied_elsewhere": ("הלקוח כבר קיבל תשובה ישירות מ-Gmail, ולכן לא נשלחה תשובה נוספת. הפנייה נסגרה כ״נענתה״. הטקסט שכתבת נשמר.",
                          "The customer was already answered straight from Gmail, so no second reply was sent. The ticket was closed as answered. Your text is kept."),
    "newer_message": ("הלקוח כתב הודעה חדשה מאז שהטיוטה נכתבה. רעננו וקראו אותה לפני שליחה.",
                      "The customer wrote again since the draft was made. Refresh and read it first."),
    "bad_job": ("משימה לא מוכרת.", "Unknown job."),
    "cancel_not_done": ("הטיוטה אומרת שהמנוי בוטל, אבל הוא עדיין פעיל. קודם לבטל בכפתור בפאנל המנויים, ואז לשלוח.",
                        "The draft says the subscription was cancelled, but it is still active. Cancel it with the button first, then send."),
    "cancel_claim": ("הטיוטה אומרת שהמנוי בוטל, אבל הוא עדיין פעיל. קודם לבטל בכפתור בפאנל המנויים, ואז לשלוח.",
                     "The draft says the subscription was cancelled, but it is still active. Cancel it with the button first, then send."),
    "wa_send_in_flight": ("תשובה אחרת כבר ממתינה לשליחה בוואטסאפ. הטיוטה שלך נשמרה; רעננו ובדקו לפני שליחה נוספת.",
                          "Another WhatsApp reply is already pending. Your draft is preserved; refresh and check before sending again."),
    "already_sent": ("התשובה כבר נשלחה בפנייה הזאת — אין צורך לשלוח שוב.", "This reply was already sent — no need to send again."),
    "bad_template": ("התבנית לא נמצאה ברשימה של דונדי. רעננו ונסו שוב.", "That template is not in Dondy's list. Refresh and try again."),
    "no_phone": ("אין מספר טלפון בפנייה, אי אפשר לשלוח תבנית.", "This ticket has no phone number, so a template cannot be sent."),
    "wa_window_closed": ("עברו יותר מ-24 שעות מאז ההודעה האחרונה של הלקוח. וואטסאפ מאפשר עכשיו רק תבנית מאושרת.",
                         "More than 24 hours have passed since the customer's last message. WhatsApp now allows only an approved template."),
    "already": ("הפעולה כבר בוצעה — אין צורך לחזור ענציגה ב.", "This was already done — no need to repeat it."),
    "engine_slow": ("המנוע איטי כרגע, מנסה שוב…", "The engine is slow right now, trying again…"),
    "not_bot": ("השיחה כבר לא אצל הבוט — רעננו את הפנייה.", "The bot is no longer handling this chat — refresh the ticket."),
    "rate_limited": ("המנוע מגביל קריאות כרגע. נסו שוב בעוד כמה דקות.", "The engine is rate-limiting. Try again in a few minutes."),
    "bad_since": ("גרסת רשימה לא תקינה.", "Invalid list version."),
}

# Safety.gs draftProblem() sentences
DRAFT_PROBLEMS = [
    (r"^empty draft$", "הטיוטה ריקה", "the draft is empty"),
    (r"^too long \((\d+) chars\)$", "הטיוטה ארוכה מדי ({0} תווים)", "too long ({0} characters)"),
    (r"^leftover placeholder$", "נשאר שדה למילוי (כמו [NAME])", "a placeholder was left (like [NAME])"),
    (r"^promise or cure claim$", "הבטחה או טענת ריפוי", "a promise or cure claim"),
    (r"^mentions AI$", "הטקסט מזכיר בינה מלאכותית", "the text mentions AI"),
    (r"^link not on the allowlist: (.*)$", "קישור שלא ברשימה המותרת: {0}", "a link not on the allowlist: {0}"),
    (r"^tracking link not from store data$", "קישור מעקב שלא מגיע מנתוני החנות", "a tracking link not from store data"),
    (r"^order number not from store data: (.*)$", "מספר הזמנה שלא מופיע בנתוני החנות: {0}", "an order number not in store data: {0}"),
    (r"^price not in policy: (.*)$", "מחיר שלא מופיע במדיניות: {0}", "a price not in the policy: {0}"),
    (r"^percentage not in policy: (.*)$", "אחוז שלא מופיע במדיניות: {0}", "a percentage not in the policy: {0}"),
    (r"^discount wording not in policy: (.*)$", "ניסוח הנחה שלא במדיניות: {0}", "discount wording not in the policy: {0}"),
    (r"^apologises for a delay that is not a delay$", "התנצלות על עיכוב שאינו עיכוב", "an apology for a delay that is not one"),
    # engine (in progress, 2026-10-05): the draft says "cancelled" but Kaching still shows the contract active
    (r"(?i)^.*cancel.*(still active|not cancelled|is active|active contract).*$",
     "הטיוטה אומרת שהמנוי בוטל, אבל המנוי עדיין פעיל — קודם לבטל בכפתור בפאנל המנויים, ואז לשלוח",
     "the draft says the subscription was cancelled, but it is still active — cancel it with the button first, then send"),
]

# Kaching.gs kachingCancelContract() messages
KACHING = [
    (r"^cancellations are switched off$",
     "ביטולי מנויים כבויים כרגע במערכת. רק גיא מדליק אותם.", "Subscription cancellations are switched off."),
    (r"^cancellations are frozen: (.*)$",
     "ביטולי מנויים מוקפאים ({0}). רק אדמין יכול לשחרר את ההקפאה.", "Cancellations are frozen ({0}). Only an admin can lift it."),
    (r"^role \"(.*)\" may not cancel subscriptions$",
     "לתפקיד \"{0}\" אין הרשאה לבטל מנויים.", "Role \"{0}\" may not cancel subscriptions."),
    (r"^exactly one valid contract id is required$", "מזהה מנוי לא תקין.", "A single valid contract id is required."),
    (r"^confirmation code does not match the contract$",
     "4 הספרות שהוקלדו לא תואמות לסוף מספר המנוי.", "The 4 digits do not match the end of the contract id."),
    (r"^ticket has no customer email$", "לפנייה אין מייל לקוח — אי אפשר לאמת שהמנוי שלו.", "The ticket has no customer email."),
    (r"^no cancel request from the customer and no written reason$",
     "הלקוח לא ביקש ביטול בפנייה — חובה לכתוב סיבה (10 תווים לפחות, שתי מילים).",
     "The customer did not ask to cancel — write a reason (10+ characters, two words)."),
    (r"^another cancellation is running, try again$", "ביטול אחר רץ ברגע זה. נסו שוב בעוד כמה שניות.",
     "Another cancellation is running. Try again."),
    (r"^limit: (\S+) cancellations per hour per user$",
     "הגעת למגבלה: {0} ביטולים בשעה למשתמש. גיא קיבל התראה.", "Limit reached: {0} cancellations per hour per user."),
    (r"^this contract does not belong to the ticket's customer$",
     "המנוי הזה לא שייך ללקוח של הפנייה.", "This contract does not belong to the ticket's customer."),
    (r"^status (\S+) cannot be cancelled$", "מנוי בסטטוס {0} לא ניתן לביטול.", "A contract in status {0} cannot be cancelled."),
    (r"^Kaching returned (\d+)\. Not retried.*$",
     "קצ'ינג החזיר שגיאה {0}. לא נוסה שוב — בדקו בקצ'ינג לפני ניסיון נוסף.",
     "Kaching returned {0}. Not retried — check in Kaching first."),
    (r"^request accepted but status is (.*) — check in Kaching$",
     "הבקשה התקבלה אבל הסטטוס עכשיו {0}. בדקו בקצ'ינג.", "Accepted, but the status is {0}. Check in Kaching."),
    (r"^request sent but the outcome is unknown.*$",
     "הבקשה נשלחה אבל התוצאה לא ידועה. בדקו בקצ'ינג ואל תנסו שוב.", "Sent, but the outcome is unknown. Check Kaching; do not retry."),
    (r"^error: (.*)$", "שגיאה בבדיקת המנוי: {0}", "Error while checking the contract: {0}"),
    (r"^cancelled$", "המנוי בוטל.", "The subscription was cancelled."),
    (r"^already cancelled$", "המנוי כבר היה מבוטל.", "The subscription was already cancelled."),
]


# Auto-cancel queue + system switches (engine shapes final, coordinator 2026-10-05)
AUTO = {
    "bad_id": ("מזהה לא תקין.", "Invalid id."),
    "bad_text": ("נוסח התשובה ריק או ארוך מדי.", "The reply text is empty or too long."),
    "not_found": ("הפנייה לא נמצאה.", "Ticket not found."),
    "no_auto_record": ("אין לפנייה הזאת רשומת ביטול אוטומטי (אולי כבר טופלה).", "This ticket has no auto-cancel record (maybe already handled)."),
    "not_approvable": ("אי אפשר לאשר במצב הנוכחי ({state}). רעננו את הרשימה.", "Cannot approve in the current state ({state}). Refresh the list."),
    "not_rejectable": ("אי אפשר להעביר לטיפול ידני במצב הנוכחי. רעננו את הרשימה.", "Cannot move to manual handling in this state. Refresh."),
    "newer_message": ("הלקוח כתב הודעה חדשה מאז — פתחו את הפנייה וקראו אותה לפני אישור.",
                      "The customer wrote again — open the ticket and read it before approving."),
    "draft_problem": ("בדיקת הבטיחות עצרה את נוסח התשובה: {problem}", "The safety check stopped the reply: {problem}"),
    # the engine's reason is shown verbatim next to this line by the screen, so it is not repeated inside the Hebrew
    "live_switches_off": ("הביטול האוטומטי לא יכול לרוץ: המערכת לא במצב חי.", "Auto-cancel cannot run: the system is not live."),
    "bad_note": ("הערה של 2 עד 300 תווים.", "A note of 2 to 300 characters."),
}
SETTINGS = {
    "bad_action": ("פעולה לא מוכרת.", "Unknown action."),
    "bad_key": ("מתג לא מוכר.", "Unknown switch."),
    "bad_value": ("ערך לא מותר. מותר: {allowed}", "Value not allowed. Allowed: {allowed}"),
    "needs_live_switches": ("אי אפשר — צריך קודם לשנות מתגים אחרים.", "Not possible — other switches must change first."),
}
AUTO.update({
    "bad_verdict": ("ערך בדיקה לא תקין.", "Invalid review value."),
    "not_reviewable": ("אי אפשר לסמן בדיקה במצב הנוכחי. רעננו את הרשימה.", "Cannot review in the current state. Refresh the list."),
    "already_reviewed": ("מישהו כבר בדק את התשובה הזאת.", "Someone already reviewed this reply."),
    "no_auto_reply": ("אין לפנייה הזאת תשובה אוטומטית.", "This ticket has no automatic reply."),
})
AUTO_FNS = ("apiAutoCancelList", "apiAutoCancelApprove", "apiAutoCancelReject", "apiAutoReplyList", "apiAutoReplyReview")


def iso(v):
    """Wrap an inserted value in FSI..PDI so an English/LTR token inside a Hebrew sentence cannot reorder it."""
    v = str(v)
    return "\u2068" + v + "\u2069" if re.search(r"[A-Za-z0-9]", v) else v


def _idx(lang):
    return 1 if lang == "en" else 0


def proxy_msg(code, lang="he", **kw):
    pair = PROXY.get(code) or ENGINE.get(code) or ("שגיאה לא צפויה ({0}).".format(code), "Unexpected error ({0}).".format(code))
    text = pair[_idx(lang)]
    return text.format(**kw) if kw else text


def _match(table, raw, lang):
    raw = str(raw or "").strip()
    for pat, he, en in table:
        m = re.match(pat, raw, re.S)
        if m:
            return (en if lang == "en" else he).format(*[iso(g) for g in m.groups()])
    return None


def draft_problem_msg(problem, lang="he"):
    return _match(DRAFT_PROBLEMS, problem, lang) or str(problem or "")


def kaching_msg(message, lang="he"):
    t = _match(KACHING, message, lang)
    if t:
        return t
    return ("תשובה מהמנוי: {0}" if lang != "en" else "Gate answer: {0}").format(message or "—")


def engine_error_msg(resp, fn, lang="he"):
    """Localized line for an engine {ok:false} answer."""
    if fn == "apiKachingCancel" and resp.get("message"):
        return kaching_msg(resp.get("message"), lang)
    code = str(resp.get("error") or "")
    table = AUTO if fn in AUTO_FNS else SETTINGS if fn == "apiSettings" else None
    if table and code in table:
        allowed = resp.get("allowed")
        kw = {"state": iso(resp.get("state") or "?"), "reason": iso(resp.get("reason") or "?"),
              "problem": draft_problem_msg(resp.get("problem"), lang) if resp.get("problem") else "?",
              "allowed": iso(", ".join(map(str, allowed)) if isinstance(allowed, list) else str(allowed or "?"))}
        return table[code][_idx(lang)].format(**kw)
    if code == "draft_problem":
        tmpl = ENGINE["draft_problem"][_idx(lang)]
        return tmpl.format(problem=draft_problem_msg(resp.get("problem"), lang))
    pair = ENGINE.get(code)
    if pair:
        return pair[_idx(lang)]
    if code in PROXY:
        return PROXY[code][_idx(lang)]
    # never a raw code in front of an agent (QA round 4: "המנוע סירב: get_not_supported"); the code stays in `error`
    return ("הפעולה לא הושלמה. רעננו את הפנייה ונסו שוב." if lang != "en" else "The action did not complete. Refresh the ticket and try again.")
