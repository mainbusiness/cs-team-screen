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
    # "לענות מאוחר יותר" (snooze.py, 2026-10-14)
    "snooze_too_late": ("כבר כמעט 17:00 — בחרו זמן אחר.", "It is almost 17:00: pick another time."),
    "snooze_not_open": ("אפשר לדחות רק פנייה פתוחה. רעננו את הרשימה.", "Only an open ticket can be snoozed. Refresh the list."),
    "snooze_everyone": ("אי אפשר לדחות: אף נציג אחר לא יראה את הפנייה. היא חייבת להישאר אצל מישהו.",
                        "Cannot snooze: no other agent would see this ticket. It must stay with someone."),
    "forbidden_fn": ("הפעולה הזאת לא זמינה מהמסך.", "This action is not available from the screen."),
    "forbidden_role": ("לתפקיד שלך אין הרשאה לפעולה הזאת.", "Your role cannot do this."),
    "brand_not_connected": ("המותג הזה עוד לא מחובר למערכת.", "This brand is not connected yet."),
    "bad_request": ("הבקשה לא תקינה.", "Bad request."),
    "bad_note": ("הערה של 2 עד 300 תווים.", "A note of 2 to 300 characters."),
    "bad_ai_note": ("הערה ל-AI: בין 1 ל-600 תווים.", "A note to the AI: 1 to 600 characters."),
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
    "engine_timeout": ("המנוע לא ענה בזמן. נסו שוב בעוד רגע — הפעולה אולי בוצעה, רעננו לפני שחוזרים עליה.",
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

# apiLinkCustomer ("קישור לקוח", 2026-10-20): its own wording for the codes it shares with search
LINK = {
    "bad_query": ("לכתוב מספר הזמנה (למשל #12057), מייל או טלפון.", "Enter an order number (e.g. #12057), an email or a phone."),
    "no_order": ("לא נמצאו הזמנה או מנוי לפרט הזה (הזמנות מלפני יותר מ-60 יום לא מופיעות). לבקש מהלקוח פרט אחר.",
                 "No order or subscription for this detail (orders older than 60 days are not visible). Ask the customer for another detail."),
    "several_emails": ("לפרט הזה יש הזמנות עם כמה כתובות מייל ({orders}). לבקש מהלקוח את מספר ההזמנה המדויק.",
                       "This detail has orders with several emails ({orders}). Ask the customer for the exact order number."),
    "store_unavailable": ("אין חיבור לחנות כרגע. נסו שוב בעוד רגע.", "Cannot reach the store right now. Try again shortly."),
}

# Api.gs error codes ({ok:false, error:<code>})
ENGINE = {
    # files an agent attaches (attach.py + engine/Attach.gs, 2026-10-11)
    "attach_none": ("לא נבחר קובץ.", "No file was chosen."),
    "attach_empty": ("הקובץ ריק.", "The file is empty."),
    "attach_type": ("סוג הקובץ לא נתמך, או שהתוכן לא תואם לסיומת. מותר: PDF, JPG, PNG, WEBP, GIF, DOC/DOCX, XLS/XLSX, TXT.",
                    "This file type is not allowed, or its content does not match its extension. Allowed: PDF, JPG, PNG, WEBP, GIF, DOC/DOCX, XLS/XLSX, TXT."),
    "attach_too_big": ("הקובץ גדול מדי: עד 10MB לקובץ ועד 18MB לכל הקבצים במייל; בוואטסאפ עד 5MB.",
                       "The file is too large: up to 10 MB a file and 18 MB for all files of an email; 5 MB on WhatsApp."),
    "attach_budget": ("הועלו יותר מדי קבצים בזמן קצר. נסו שוב בעוד כמה דקות.", "Too many files in a short time. Try again in a few minutes."),
    "attach_unavailable": ("צירוף קבצים לא זמין למותג הזה.", "Attaching files is not available for this brand."),
    "attach_missing": ("קובץ מצורף כבר לא נמצא בשרת (נמחק אחרי 30 יום או שההעלאה לא הסתיימה). להסיר אותו ולצרף שוב.",
                       "An attached file is no longer on the server (removed after 30 days, or its upload did not finish). Remove it and attach it again."),
    "attach_wa_off": ("צירוף קבצים בוואטסאפ עוד לא פעיל במותג הזה.", "Files on WhatsApp are not switched on for this brand yet."),
    "attach_wa_one": ("בוואטסאפ אפשר לצרף קובץ אחד להודעה.", "WhatsApp takes one file per message."),
    "attach_wa_type": ("בוואטסאפ אפשר לצרף רק PDF, JPG, PNG, DOC/DOCX או XLS/XLSX.", "On WhatsApp only PDF, JPG, PNG, DOC/DOCX or XLS/XLSX can be attached."),
    "attach_corrupt": ("הקובץ הגיע פגום לשרת. לצרף אותו שוב.", "The file arrived damaged. Attach it again."),
    "attach_id_reuse": ("תקלה בהעלאת הקובץ. לצרף אותו שוב.", "The upload failed. Attach the file again."),
    "attach_failed": ("תקלה בהעלאת הקובץ. לצרף אותו שוב.", "The upload failed. Attach the file again."),
    "bad_attach": ("תקלה בהעלאת הקובץ. לצרף אותו שוב.", "The upload failed. Attach the file again."),
    # Kaching contract panel (2026-10-14)
    "no_subscriptions": ("למותג הזה אין מערכת מנויים מחוברת.", "This brand has no subscription system connected."),
    "no_email": ("לא מזוהה מייל של הזמנה ללקוח, אז אי אפשר למצוא את המנוי. לבקש מהלקוח מספר הזמנה או מייל ולקשר אותם לפנייה (בפאנל ההזמנות).",
                 "The customer has no known order email, so the subscription cannot be found. Ask the customer for the order number or email and link it to the ticket (orders panel)."),
    "not_customers_contract": ("המנוי הזה לא שייך ללקוח של הפנייה.", "This subscription does not belong to the ticket's customer."),
    # order edits in Shopify (engine/OrderEdit.gs, 2026-10-16)
    "no_customer": ("לפנייה אין מייל או טלפון של לקוח — אי אפשר לאמת שההזמנה שלו.", "The ticket has no customer email or phone, so the order cannot be matched to the customer."),
    "not_customers_order": ("ההזמנה הזאת לא שייכת ללקוח של הפנייה.", "This order does not belong to the ticket's customer."),
    # "לבטל את המנוי" (2026-10-16)
    "no_kaching": ("למותג הזה אין חיבור לקאצ'ינג (אין טוקן), אז אי אפשר לבטל מכאן. לבטל ידנית ב-Kaching.",
                   "This brand has no Kaching connection (no token), so it cannot be cancelled here. Cancel it manually in Kaching."),
    "not_cancel_request": ("הפנייה הזאת לא מבקשת ביטול מנוי. ביטול בלי בקשה — דרך \"ביטול מנוי\" בפאנל המנויים, עם סיבה.",
                           "This ticket does not ask to cancel a subscription. To cancel anyway, use \"Cancel subscription\" in the subscriptions panel, with a reason."),
    "bad_contract": ("צריך לבחור מנוי אחד לביטול.", "Choose one subscription to cancel."),
    "not_cancelled": ("המנוי לא בוטל. לבטל ידנית ב-Kaching.", "The subscription was NOT cancelled. Cancel it manually in Kaching."),
    "kaching_unavailable": ("אין חיבור למערכת המנויים (קצ'ינג) כרגע. נסו שוב בעוד רגע.", "Cannot reach the subscription system (Kaching). Try again shortly."),
    "shopify_unavailable": ("אין חיבור לחנות כרגע (רשימת המוצרים). נסו שוב בעוד רגע.", "Cannot reach the store right now (product list). Try again shortly."),
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
    # Owner, 2026-10-11: two agents on one ticket. The screen names who and when itself (by / at) and offers "send anyway"; this is the fallback line.
    "changed_meanwhile": ("מישהו אחר כבר ענה או סגר את הפנייה אחרי שפתחת אותה. ההודעה שלך לא נשלחה והטקסט נשמר — קראו את התשובה שלו ואז החליטו.",
                          "Someone else answered or closed this ticket after you opened it. Your message was not sent and your text is kept — read their answer, then decide."),
    "bad_template": ("התבנית לא נמצאה ברשימה של דונדי. רעננו ונסו שוב.", "That template is not in Dondy's list. Refresh and try again."),
    "no_phone": ("אין מספר טלפון בפנייה, אי אפשר לשלוח תבנית.", "This ticket has no phone number, so a template cannot be sent."),
    "wa_window_closed": ("עברו יותר מ-24 שעות מאז ההודעה האחרונה של הלקוח. וואטסאפ מאפשר עכשיו רק תבנית מאושרת.",
                         "More than 24 hours have passed since the customer's last message. WhatsApp now allows only an approved template."),
    "already": ("הפעולה כבר בוצעה — אין צורך לחזור עליה.", "This was already done — no need to repeat it."),
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
    # Kaching.gs kachingContractAction() — pause / resume / skip / discount / products (2026-10-14)
    (r"^unknown action$", "פעולה לא מוכרת על המנוי.", "Unknown subscription action."),
    (r"^subscription changes are switched off$", "שינויים במנויים כבויים כרגע במערכת. רק גיא מדליק אותם.", "Subscription changes are switched off."),
    (r"^subscription changes are frozen: (.*)$", "שינויים במנויים מוקפאים ({0}). רק אדמין יכול לשחרר את ההקפאה.",
     "Subscription changes are frozen ({0}). Only an admin can lift it."),
    (r"^role \"(.*)\" may not change subscriptions$", "לתפקיד \"{0}\" אין הרשאה לשנות מנויים.", "Role \"{0}\" may not change subscriptions."),
    (r"^another subscription change is running, try again$", "שינוי אחר במנוי רץ ברגע זה. נסו שוב בעוד כמה שניות.",
     "Another subscription change is running. Try again."),
    (r"^limit: (\S+) subscription changes per hour per user$", "הגעת למגבלה: {0} שינויים במנויים בשעה למשתמש. גיא קיבל התראה.",
     "Limit reached: {0} subscription changes per hour per user."),
    (r"^status (\S+) does not allow (\S+)$", "במנוי בסטטוס {0} אי אפשר לבצע את הפעולה הזאת ({1}).", "A contract in status {0} does not allow {1}."),
    (r"^Kaching refused \((\d+)\)(.*?)\. Not retried.*$", "קצ'ינג סירב (שגיאה {0}{1}). לא נוסה שוב — בדקו בקצ'ינג לפני ניסיון נוסף.",
     "Kaching refused ({0}{1}). Not retried — check in Kaching first."),
    (r"^request accepted but the change is not visible yet.*$", "קצ'ינג קיבל את הבקשה, אבל השינוי עוד לא מופיע. בדקו בקצ'ינג — לא לחזור על הפעולה.",
     "Kaching accepted it but the change is not visible yet. Check in Kaching — do not repeat it."),
    (r"^done$", "בוצע.", "Done."),
    (r"^a billing cycle is required$", "צריך לבחור משלוח (מחזור חיוב).", "Choose a billing cycle."),
    (r"^billing cycle (\d+) is not an upcoming cycle of this contract$", "משלוח {0} הוא לא משלוח עתידי של המנוי הזה. רעננו.",
     "Cycle {0} is not an upcoming cycle of this contract. Refresh."),
    (r"^billing cycle (\d+) is already skipped$", "משלוח {0} כבר מדולג.", "Cycle {0} is already skipped."),
    (r"^billing cycle (\d+) is not skipped$", "משלוח {0} לא מדולג.", "Cycle {0} is not skipped."),
    (r"^a new date is required \(YYYY-MM-DD\)$", "צריך לבחור תאריך חדש.", "Choose a new date."),
    (r"^the new date must be in the future$", "התאריך החדש חייב להיות בעתיד.", "The new date must be in the future."),
    (r"^the new date is more than 400 days away$", "התאריך החדש רחוק מדי (יותר מ-400 יום).", "The new date is more than 400 days away."),
    (r"^discount type must be PERCENTAGE or FIXED_AMOUNT$", "סוג הנחה: אחוזים או סכום קבוע.", "Discount type: percentage or fixed amount."),
    (r"^a percentage between 1 and 100 is required$", "אחוז הנחה בין 1 ל-100.", "A percentage between 1 and 100."),
    (r"^an amount between 0\.01 and (\S+) is required$", "סכום הנחה בין 0.01 ל-{0}.", "An amount between 0.01 and {0}."),
    (r"^a discount title of 2 to 60 characters is required$", "שם להנחה: 2 עד 60 תווים.", "A discount title of 2 to 60 characters."),
    (r"^the number of billing cycles must be between 1 and 60$", "מספר המשלוחים להנחה: 1 עד 60 (או ריק = לתמיד).",
     "Number of cycles: 1 to 60 (or empty = forever)."),
    (r"^a product line is required$", "צריך לבחור מוצר במנוי.", "Choose a product of the subscription."),
    (r"^this product line is not in the contract$", "המוצר הזה כבר לא במנוי. רעננו.", "This product is no longer in the subscription. Refresh."),
    (r"^the last product cannot be removed.*$", "אי אפשר להסיר את המוצר האחרון במנוי — אם צריך, מבטלים את המנוי.",
     "The last product cannot be removed — cancel the subscription instead."),
    (r"^a valid product variant is required$", "צריך לבחור מוצר מהחנות.", "Choose a product from the store."),
    (r"^a quantity between 1 and 20 is required$", "כמות בין 1 ל-20.", "A quantity between 1 and 20."),
    (r"^a price between 0 and 20000 is required$", "מחיר בין 0 ל-20000.", "A price between 0 and 20000."),
    (r"^nothing to change.*$", "לא נבחר שום שינוי (מוצר, כמות או מחיר).", "Nothing to change (product, quantity or price)."),
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
# Managers' notes to the AI (engine AiNotes.gs, 2026-10-11). An explicit set: a future fn with a similar name must not borrow these texts.
AI_NOTE_FNS = frozenset(("apiAiNotes", "apiAiNoteAdd", "apiAiNoteDelete", "apiAiNoteAttach", "apiAiNoteCheck"))
AI_NOTES = {
    "bad_id": ("מזהה ההערה לא תקין. רעננו את הדף ונסו שוב.", "Invalid note id. Refresh and try again."),
    "bad_scope": ("לא נבחר למי ההערה (כל המותגים או מותג אחד).", "Choose who the note is for (all brands or one brand)."),
    "bad_text": ("הערה ל-AI: בין 1 ל-600 תווים.", "A note to the AI: 1 to 600 characters."),
    "too_many": ("הגעתם ל-60 הערות — מחקו הערה ישנה כדי להוסיף", "You have reached 60 notes — delete an old note to add a new one"),
    "bad_file": ("הקובץ לא הועלה כמו שצריך. בחרו אותו שוב.", "The file was not uploaded properly. Choose it again."),
    "not_found": ("ההערה כבר לא קיימת (אולי נמחקה). רעננו את הרשימה.", "The note no longer exists (maybe deleted). Refresh the list."),
    "needs_file": ("קודם צריך לצרף את הקובץ של האישור.", "Attach the approval document first."),
    "attach_missing": ("הקובץ לא נמצא בשרת (ההעלאה לא הסתיימה). צרפו אותו שוב.", "The file is not on the server (the upload did not finish). Attach it again."),
    "attach_type": ("לאישור אפשר לצרף PDF, תמונה (JPG/PNG/WEBP) או Word.", "An approval can be a PDF, an image (JPG/PNG/WEBP) or a Word file."),
    "attach_unavailable": ("צירוף קבצים לא זמין למותג הזה.", "Attaching files is not available for this brand."),
    "unauthorized": ("המנוע של המותג סירב (אולי עוד לא עודכן להערות ל-AI, או שההרשאה פגה). רעננו את הדף.",
                     "The brand engine refused (maybe not updated for AI notes yet, or the session expired). Refresh."),
}

# Sales log for bonuses (engine Sales.gs, the owner 2026-10-14). An explicit set of fns, like the AI notes above.
SALE_FNS = frozenset(("apiSaleCandidates", "apiSaleLog", "apiSaleMine", "apiSaleProof", "apiSaleList", "apiSaleDecide", "apiSaleSuggestions",
                      "apiSaleSuggestCredit", "apiSaleSuggestDismiss", "apiSaleScan"))
SALES = {
    "bad_id": ("מזהה לא תקין. רעננו את הדף ונסו שוב.", "Invalid id. Refresh and try again."),
    "bad_order": ("מספר הזמנה לא תקין (3 עד 9 ספרות, למשל 1234).", "Invalid order number (3 to 9 digits, e.g. 1234)."),
    "bad_text": ("ההערה ארוכה מדי (עד 300 תווים).", "The note is too long (up to 300 characters)."),
    "bad_decision": ("החלטה לא מוכרת.", "Unknown decision."),
    "not_found": ("לא נמצא. רעננו את הרשימה.", "Not found. Refresh the list."),
    "order_not_found": ("ההזמנה לא נמצאה בשופיפיי של המותג הזה. בדקו את המספר.", "That order was not found in this brand's Shopify. Check the number."),
    "shopify_unavailable": ("אין חיבור לשופיפיי כרגע. נסו שוב בעוד רגע.", "Cannot reach Shopify right now. Try again in a moment."),
    "order_already_credited": ("ההזמנה הזאת כבר רשומה על {by}. הזמנה נזקפת פעם אחת בלבד.", "This order is already credited to {by}. An order is credited once."),
    "no_agent": ("אין נציג מזוהה. בחרו נציג כדי לזקוף.", "No agent identified. Choose an agent to credit."),
    "rate_limited": ("יותר מדי חיפושים בשופיפיי. נסו שוב בעוד {wait} שניות.", "Too many Shopify lookups. Try again in {wait} seconds."),
    "unauthorized": ("אין הרשאה לפעולה הזאת (או שהמנוע של המותג עוד לא עודכן ליומן המכירות).", "Not allowed (or the brand engine does not have the sales log yet)."),
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


# OrderEdit.gs orderEditGate() refusals and plan errors (Owner, 2026-10-16). Same mechanism as KACHING: the engine's exact English sentence -> a Hebrew / English line.
ORDER_EDIT = [
    (r"^unknown (mode|edit)$", "בקשת עריכה לא מוכרת.", "Unknown edit request."),
    (r"^order edits are switched off$", "עריכת הזמנות כבויה כרגע במערכת. רק גיא מדליק אותה.", "Order edits are switched off."),
    (r"^order edits have no write credential$", "עריכת הזמנות עוד לא מחוברת לשופיפיי (חסר מפתח כתיבה). גיא צריך לאשר אותו.", "Order edits are not connected to Shopify yet (no write credential)."),
    (r"^order edits are frozen: (.*)$", "עריכת הזמנות מוקפאת ({0}). רק אדמין יכול לשחרר את ההקפאה.", "Order edits are frozen ({0}). Only an admin can lift it."),
    (r"^role \"(.*)\" may not edit orders$", "לתפקיד \"{0}\" אין הרשאה לערוך הזמנות.", "Role \"{0}\" may not edit orders."),
    (r"^exactly one valid order id is required$", "צריך לבחור הזמנה אחת.", "Choose exactly one order."),
    (r"^ticket has no customer email or phone$", "לפנייה אין מייל או טלפון של לקוח — אי אפשר לאמת שההזמנה שלו.", "The ticket has no customer email or phone."),
    (r"^another order edit is running, try again$", "עריכה אחרת של הזמנה רצה ברגע זה. נסו שוב בעוד כמה שניות.", "Another order edit is running. Try again in a few seconds."),
    (r"^limit: (\S+) order edits per hour per user$", "הגעת למגבלה: {0} עריכות הזמנה בשעה למשתמש. גיא קיבל התראה.", "Limit reached: {0} order edits per hour per user."),
    (r"^the order was not found.*$", "ההזמנה לא נמצאה (הזמנות מעל 60 יום לא נראות). לערוך בשופיפיי.", "The order was not found (orders older than 60 days are not visible). Edit it in Shopify."),
    (r"^this order does not belong to the ticket's customer$", "ההזמנה הזאת לא שייכת ללקוח של הפנייה.", "This order does not belong to the ticket's customer."),
    (r"^the order is cancelled$", "ההזמנה בוטלה — אי אפשר לערוך אותה.", "The order is cancelled and cannot be edited."),
    (r"^the order is not unfulfilled \((.*)\)$", "ההזמנה כבר טופלה במשלוח ({0}) — אי אפשר לערוך אותה כאן.", "The order is already being fulfilled ({0}) and cannot be edited here."),
    (r"^the order has no shipping address$", "להזמנה אין כתובת משלוח.", "The order has no shipping address."),
    (r"^Shopify does not allow editing this order(.*)$", "שופיפיי לא מאפשר לערוך את ההזמנה הזאת{0}.", "Shopify does not allow editing this order{0}."),
    (r"^payment status (\S+) does not allow item changes$", "סטטוס התשלום ({0}) לא מאפשר לשנות פריטים. לערוך בשופיפיי.", "Payment status {0} does not allow item changes. Edit it in Shopify."),
    (r"^the order is closed$", "ההזמנה סגורה — אי אפשר לערוך אותה.", "The order is closed."),
    (r"^confirmation code does not match the order$", "מספר ההזמנה שהוקלד לא תואם.", "The typed order number does not match."),
    (r"^the new address is missing$", "חסרה הכתובת החדשה.", "The new address is missing."),
    (r"^field not allowed: (.*)$", "אי אפשר לשנות את השדה הזה ({0}).", "This field cannot be changed ({0})."),
    (r"^bad value for (\S+)$", "ערך לא תקין בשדה {0}.", "Invalid value in {0}."),
    (r"^the zip code is not valid$", "המיקוד לא תקין.", "The zip code is not valid."),
    (r"^the phone number is not valid$", "מספר הטלפון לא תקין.", "The phone number is not valid."),
    (r"^nothing to change$", "לא שונה כלום.", "Nothing was changed."),
    (r"^the address would be incomplete$", "הכתובת תהיה חסרה (רחוב / עיר).", "The address would be incomplete."),
    (r"^no item change was given$", "לא נבחר שינוי בפריטים.", "No item change was chosen."),
    (r"^too many changes at once$", "יותר מדי שינויים בבת אחת.", "Too many changes at once."),
    (r"^bad change$", "שינוי לא תקין.", "Invalid change."),
    (r"^unknown change$", "שינוי לא מוכר.", "Unknown change."),
    (r"^quantity must be a whole number up to (\S+)$", "כמות: מספר שלם עד {0}.", "Quantity: a whole number up to {0}."),
    (r"^quantity must be at least 1$", "הכמות חייבת להיות 1 לפחות.", "Quantity must be at least 1."),
    (r"^this item is not on the order$", "הפריט הזה כבר לא בהזמנה. רעננו.", "This item is no longer on the order. Refresh."),
    (r"^the same item twice$", "אותו פריט פעמיים.", "The same item twice."),
    (r"^the same product twice$", "אותו מוצר פעמיים.", "The same product twice."),
    (r"^the quantity is already (\S+)$", "הכמות כבר {0}.", "The quantity is already {0}."),
    (r"^a valid product is required$", "צריך לבחור מוצר.", "Choose a product."),
    (r"^this product is already on the order.*$", "המוצר הזה כבר בהזמנה — משנים את הכמות שלו.", "This product is already on the order — change its quantity instead."),
    (r"^an order cannot be left without items.*$", "אי אפשר להשאיר הזמנה בלי פריטים. אם צריך, מבטלים אותה בשופיפיי.", "An order cannot be left without items — cancel it in Shopify."),
    (r"^this item cannot be matched safely.*$", "אי אפשר לשנות את הפריט הזה בבטחה מכאן. לשנות בשופיפיי.", "This item cannot be changed safely from here. Change it in Shopify."),
    (r"^Shopify refused the change: (.*?)\.? Not retried\.$", "שופיפיי סירב לשינוי: {0}. לא נוסה שוב.", "Shopify refused the change: {0}. Not retried."),
    (r"^Shopify refused the change: (.*)$", "שופיפיי סירב לשינוי: {0}", "Shopify refused the change: {0}"),
    (r"^the price change is larger than (\S+) .*$", "שינוי המחיר גדול מ-{0}. לבצע בשופיפיי.", "The price change is larger than {0}. Do it in Shopify."),
    (r"^an increase of (\S+) needs an admin$", "העלאת מחיר ההזמנה ב-{0} דורשת אדמין. אפשר להוריד מחיר או להוסיף פריט חינם.", "An increase of {0} needs an admin. A reduction or a free item is fine."),
    (r"^the price shown to the agent is missing$", "המחיר לא נשלח. חזרו לשלב הקודם.", "The price was not sent. Go back a step."),
    (r"^the price changed since the preview.*$", "המחיר השתנה מאז התצוגה המקדימה. בדקו את המחיר החדש ואשרו שוב.", "The price changed since the preview. Review the new price and confirm again."),
    (r"^request accepted but the change is not visible yet.*$", "שופיפיי קיבל את הבקשה, אבל השינוי עוד לא מופיע. בדקו בשופיפיי — לא לחזור על הפעולה.", "Shopify accepted it but the change is not visible yet. Check in Shopify — do not repeat it."),
    (r"^request sent but the outcome is unknown.*$", "הבקשה נשלחה אבל התוצאה לא ידועה. בדקו בשופיפיי ואל תנסו שוב.", "Sent, but the outcome is unknown. Check Shopify; do not retry."),
    (r"^error: (.*)$", "שגיאה בעריכת ההזמנה: {0}", "Error while editing the order: {0}"),
    (r"^done$", "בוצע.", "Done."),
]


def order_edit_msg(message, lang="he"):
    t = _match(ORDER_EDIT, message, lang)
    if t:
        return t
    return ("עריכת ההזמנה לא הושלמה: {0}" if lang != "en" else "The order edit did not complete: {0}").format(iso(message or "—"))


# "תשובה אחרת" (engine/AgentRedraft.gs, 2026-10-14)
REDRAFT = {
    "rate_limited": ("כבר ביקשתם {n} תשובות אחרות לפנייה הזאת בשעה האחרונה. אפשר שוב בעוד {wait} דקות.",
                     "You already asked for {n} other answers on this ticket in the last hour. Try again in {wait} minutes."),
    "rate_limited_user": ("הגעתם למגבלת התשובות האחרות לשעה. אפשר שוב בעוד {wait} דקות.", "You reached the hourly limit of other answers. Try again in {wait} minutes."),
    "changed_meanwhile": ("הפנייה השתנתה בינתיים (הלקוח כתב, או שמישהו אחר ענה או ערך). הטיוטה לא הוחלפה — קראו שוב ונסו מחדש.",
                          "The ticket changed meanwhile (the customer wrote, or someone else answered or edited). The draft was not replaced. Read it again and retry."),
    "no_new_draft": ("לא נוצרה תשובה אחרת שעוברת את הבדיקות. הטיוטה הקיימת נשארה.", "No other answer passed the checks. The current draft stays."),
    "same_draft": ("יצאה אותה תשובה. נסו עם בקשה קצרה (למשל \"יותר קצר\").", "The same answer came out. Try with a short wish (e.g. \"shorter\")."),
    "ai_failed": ("הכתיבה האוטומטית לא הצליחה הפעם. הטיוטה הקיימת נשארה.", "The AI could not write an answer this time. The current draft stays."),
    "ai_unavailable": ("שירות הכתיבה האוטומטית לא זמין כרגע. נסו שוב בעוד דקה.", "The AI service is not available right now. Try again in a minute."),
    "cannot_redraft": ("אי אפשר לכתוב תשובה אחרת לפנייה הזאת (אין שיחה שמורה).", "No other answer can be written for this ticket (no stored conversation)."),
    "nothing_to_undo": ("אין טיוטה קודמת לחזור אליה.", "There is no previous draft to go back to."),
    "not_open": ("הפנייה כבר לא פתוחה.", "The ticket is no longer open."),
    "wa_send_in_flight": ("הודעה בדרך ללקוח — אי אפשר להחליף טיוטה עכשיו.", "A message is on its way to the customer: the draft cannot be replaced now."),
    "auto_pending": ("פעולה אוטומטית ממתינה על הפנייה. נסו שוב אחריה.", "An automatic action is pending on this ticket. Try again after it."),
    "bad_hint": ("הבקשה ארוכה מדי (עד 200 תווים).", "The wish is too long (up to 200 characters)."),
}


def engine_error_msg(resp, fn, lang="he"):
    """Localized line for an engine {ok:false} answer."""
    if fn == "apiRedraftOne":
        code = str(resp.get("error") or "")
        if code == "rate_limited" and resp.get("scope") == "user":
            code = "rate_limited_user"
        if code in REDRAFT:
            wait = max(1, (int(resp.get("retryAfterSeconds") or 60) + 59) // 60)
            return REDRAFT[code][_idx(lang)].format(n=5, wait=wait)
    if fn in ("apiKachingCancel", "apiKachingAction", "apiSubCancel") and resp.get("message"):
        return kaching_msg(resp.get("message"), lang)
    if fn == "apiOrderEdit" and resp.get("message"):
        return order_edit_msg(resp.get("message"), lang)
    code = str(resp.get("error") or "")
    if fn == "apiLinkCustomer" and code in LINK:
        orders = resp.get("orders")
        return LINK[code][_idx(lang)].format(orders=iso(", ".join(map(str, orders)) if isinstance(orders, list) else "?"))
    table = AUTO if fn in AUTO_FNS else SETTINGS if fn == "apiSettings" else AI_NOTES if fn in AI_NOTE_FNS else SALES if fn in SALE_FNS else None
    if table and code in table:
        allowed = resp.get("allowed")
        kw = {"state": iso(resp.get("state") or "?"), "reason": iso(resp.get("reason") or "?"), "by": iso(resp.get("by") or "?"),
              "wait": str(resp.get("retryAfterSeconds") or 60),
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
