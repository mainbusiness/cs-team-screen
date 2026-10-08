/*
 * CS team screen SPA. Vanilla JS, no build step, no inline script (strict CSP).
 *
 * Rules this file keeps (each one was bought by a failure on an earlier screen):
 *  - Nothing customer-typed is ever set as HTML: every node is built with textContent (h()).
 *  - A polling refresh never rebuilds the ticket pane: if the server changed under the agent, a banner
 *    offers "refresh" instead. The list re-renders only when its signature changed.
 *  - The agent's draft is mirrored to localStorage on every keystroke and saved to the engine on blur and
 *    after 2.5s idle. If the server draft changed meanwhile, the agent's text wins and a banner offers the
 *    server version. A failed save is a sticky state, not a toast.
 *  - Irreversible actions (send, close, cancel) need a second deliberate click / typed confirmation, and are
 *    never retried automatically.
 *  - Copy has two paths (Clipboard API, then execCommand) and only says "copied" when it really copied.
 */
'use strict';
(function () {
  const LANG = (document.querySelector('meta[name=lang]') || {}).content || 'he';
  const CSRF = (document.querySelector('meta[name=csrf]') || {}).content || '';
  const BASE = LANG === 'en' ? '/cs/en' : '/cs';

  // ---------------------------------------------------------------- strings
  const STR = {
    he: {
      app: 'שירות לקוחות', tab_ready: 'פתוחות', tab_action: 'צריך החלטה', tab_health: 'בריאות', tab_delay: 'עיכוב',
      tab_sent: 'ממתין ללקוח', tab_today: 'טופל היום', tab_search: 'חיפוש',
      st_ready: 'חדש', st_action: 'צריך החלטה', st_health: 'בריאות', st_delay: 'עיכוב', st_sent: 'ממתין ללקוח', st_done: 'טופל', st_noreply: 'ללא מענה',
      cat_shipping: 'משלוח', cat_product: 'מוצר', cat_order_change: 'שינוי הזמנה', cat_return_refund: 'החזרה / החזר', cat_cancel_subscription: 'ביטול מנוי',
      cat_billing: 'חיוב', cat_health: 'בריאות', cat_complaint: 'תלונה', cat_legal: 'משפטי', cat_discount: 'הנחה', cat_voc: 'מחקר לקוחות', cat_other: 'אחר',
      ch_email: 'מייל', ch_whatsapp: 'וואטסאפ',
      dry_run: 'מצב ניסיון — שליחה כבויה. אפשר לקרוא, לערוך ולשמור טיוטות; השליחה ללקוח חסומה.',
      frozen: 'ביטולי מנויים מוקפאים במותג הזה — רק אדמין יכול לשחרר.',
      mock: 'תצוגה מקומית — נתונים מדומים, שום דבר לא נשלח.',
      bootstrap_env: 'ADMIN_BOOTSTRAP עדיין מוגדר בשרת. הסירו אותו מ-Render.',
      no_brands: 'לא הוגדרו לך מותגים. פנו למנהל.', not_connected: 'המותג {b} עוד לא מחובר',
      loading: 'טוען…', empty_ready: 'אין פניות פתוחות', empty_action: 'אין פניות שמחכות להחלטה', empty_health: 'אין פניות בריאות',
      empty_delay: 'אין עיכובים', empty_sent: 'אין פניות שממתינות ללקוח', empty_today: 'עוד לא טופלו פניות היום',
      empty_hint: 'הרשימה מתרעננת לבד כל דקה.', search_ph: 'שם, מייל, טלפון או מספר הזמנה', search_min: 'לפחות 2 תווים',
      search_none: 'לא נמצא כלום', archived: 'בארכיון', waiting: 'ממתין {d}', handled_by: '{who} · {when}', updated: 'עודכן {when}',
      no_name: 'ללא שם', msgs: '{n} הודעות', back: 'חזרה', copy: 'העתק', copied: 'הועתק', copy_fail: 'ההעתקה נכשלה — סמנו והעתיקו ידנית',
      why_human: 'למה צריך אדם', summary: 'בקצרה', conversation: 'השיחה', customer: 'לקוח/ה', us: 'אנחנו', automatic: 'הודעה אוטומטית',
      show_more: 'הצג הכול', show_less: 'הצג פחות', quote: 'ציטוט',
      draft: 'טיוטת תשובה', draft_readonly: 'הפנייה כבר טופלה — הטיוטה לקריאה בלבד.', save_local: 'נשמר במכשיר…', saving: 'שומר…',
      saved: 'נשמר ✓', save_failed: 'לא נשמר בשרת: {m} — הטקסט שמור במכשיר הזה.', restored: 'שוחזרה טיוטה שלא נשמרה מהמכשיר הזה.',
      conflict: 'הטיוטה בשרת השתנתה מאז שערכת (אולי הלקוח כתב שוב והמערכת כתבה טיוטה חדשה). מוצגת הגרסה שלך.',
      use_server: 'החלף בגרסת השרת', keep_mine: 'השאר את שלי',
      send: 'שליחה', send_arm: 'לחצו שוב לשליחה', send_dry: 'השליחה כבויה (מצב ניסיון)', sent_ok: 'נשלח ללקוח', queued_ok: 'נכנס לתור הוואטסאפ',
      send_anyway: 'לשלוח בכל זאת (יירשם ביומן)', handled: 'טופל בלי שליחה', handled_arm: 'לחצו שוב — טופל בלי שליחה',
      close: 'סגירה', close_arm: 'לחצו שוב לסגירה', closed_ok: 'הפנייה נסגרה', handled_ok: 'סומן כטופל',
      safety: 'בדיקת בטיחות: {p}',
      orders: 'הזמנות', no_orders: 'לא נמצאה הזמנה (הזמנות מעל 60 יום לא נראות).', lookup_error: 'בדיקת ההזמנות נכשלה ברגע הכתיבה.',
      track: 'מעקב', items: 'פריטים', ordered: 'הוזמן', shipped_on: 'נשלח',
      ship_not_late: 'בזמן', ship_late: 'מאחר', ship_very_late: 'מאחר מאוד', ship_unknown: 'לא ידוע', ship_not_applicable: 'לא רלוונטי',
      ship_line: '{state} · {d} ימים מההזמנה',
      fin_PAID: 'שולם', fin_PENDING: 'ממתין לתשלום', fin_REFUNDED: 'הוחזר', fin_PARTIALLY_REFUNDED: 'הוחזר חלקית', fin_VOIDED: 'בוטל',
      fin_AUTHORIZED: 'מאושר', fin_PARTIALLY_PAID: 'שולם חלקית',
      ful_FULFILLED: 'נשלח', ful_UNFULFILLED: 'עוד לא נשלח', ful_PARTIALLY_FULFILLED: 'נשלח חלקית', ful_IN_PROGRESS: 'בהכנה',
      ful_ON_HOLD: 'בהמתנה', ful_SCHEDULED: 'מתוזמן', ful_RESTOCKED: 'הוחזר למלאי',
      subs: 'מנויים', no_subs: 'אין מנויים ללקוח הזה (לפי המייל).', sub_status: 'סטטוס', sub_every: 'תדירות', sub_next: 'חיוב הבא',
      sub_next_na: 'לא מגיע מהמנוע', sub_since: 'מאז', sub_lastpay: 'תשלום אחרון', sub_id: 'מספר מנוי',
      pay_SUCCEEDED: 'עבר בהצלחה', pay_FAILED: 'נכשל', pay_PENDING: 'בתהליך', pay_REFUNDED: 'הוחזר',
      ss_ACTIVE: 'פעיל', ss_PAUSED: 'מושהה', ss_CANCELLED: 'מבוטל', ss_FAILED: 'תשלום נכשל', ss_EXPIRED: 'פג תוקף',
      every_day: 'כל יום', every_week: 'כל שבוע', every_month: 'כל חודש', every_year: 'כל שנה', every_n: 'כל {n} {u}',
      unit_day: 'ימים', unit_week: 'שבועות', unit_month: 'חודשים', unit_year: 'שנים',
      cancel_sub: 'ביטול מנוי', cancelled_here: 'בוטל דרך המערכת',
      afs_title: 'ההודעה ל{name} נשלחה. נשאר לטפל:', afs_open: 'פתח את הפנייה', afs_done: 'טיפלתי', afs_chip: 'נשאר לטפל', afs_cancelled: 'המנוי של {name} בוטל אוטומטית',
      afs_sub_no_email: 'המנוי לא בוטל: אין בפנייה כתובת מייל של הלקוח, אז אי אפשר למצוא את המנוי. לבטל ידנית.',
      afs_sub_unreachable: 'המנוי לא בוטל: לא הצלחנו להתחבר למערכת המנויים. לבטל ידנית.',
      afs_sub_several: 'המנוי לא בוטל: ללקוח יש כמה מנויים פעילים. לבחור איזה לבטל בפאנל המנויים.',
      afs_sub_refused: 'המנוי לא בוטל: מערכת המנויים דחתה את הביטול. לבטל ידנית.',
      afs_order_cancel: 'לפי שופיפיי ההזמנה עדיין לא בוטלה. לבטל אותה בשופיפיי.',
      afs_order_refund: 'לפי שופיפיי עדיין לא בוצע החזר. לבצע את ההחזר בשופיפיי.',
      afs_order_unknown: 'ההודעה מדברת על ביטול הזמנה או החזר, ולא הצלחנו לבדוק את זה בשופיפיי. לבדוק ידנית.',
      dlg_title: 'ביטול מנוי', dlg_type: 'כדי לאשר, הקלידו את 4 הספרות האחרונות של מספר המנוי',
      dlg_reason: 'סיבה', dlg_reason_opt: '(אופציונלי — הלקוח ביקש ביטול)', dlg_reason_req: '(חובה — הלקוח לא ביקש ביטול בפנייה: 10 תווים, שתי מילים)',
      dlg_off: 'לפי המנוע, ביטולים כבויים כרגע — סביר שהבקשה תסורב.', dlg_frozen: 'ביטולים מוקפאים כרגע — סביר שהבקשה תסורב.',
      dlg_go: 'לבטל את המנוי', dlg_back: 'חזרה', dlg_working: 'מבטל…', dlg_irrev: 'הפעולה לא הפיכה. היא לא תנוסה שוב אוטומטית.',
      notes: 'הערות פנימיות', note_ph: 'הערה לצוות (לא נשלחת ללקוח)', note_add: 'הוספה', note_ok: 'ההערה נשמרה', no_notes: 'אין הערות.',
      details: 'פרטים', created: 'נפתח', handled_at: 'טופל', by: 'ע״י', ticket_id: 'מזהה', language: 'שפה', order: 'הזמנה',
      audit_na: 'יומן הפעולות המלא נשמר במנוע (גיליון audit) ולא נחשף למסך.',
      related: 'פניות קודמות של הלקוח', no_related: 'אין פניות נוספות.',
      stale: 'הפנייה התעדכנה בשרת ({what}).', stale_new: 'הלקוח כתב שוב', stale_status: 'הסטטוס השתנה', refresh: 'רענון',
      pick_ticket: 'בחרו פנייה מהרשימה',
      menu: 'תפריט', users: 'ניהול משתמשים', change_pw: 'החלפת סיסמה', logout: 'יציאה', to_en: 'English UI', to_he: 'ממשק בעברית', to_tickets: 'חזרה לפניות',
      err_network: 'אין חיבור לאינטרנט או לשרת. שום דבר לא נשלח — נסו שוב.', err_bad_response: 'תשובה לא תקינה מהשרת.', err_login: 'צריך להתחבר מחדש.',
      orders_chip_only: 'פרטי ההזמנה לא נשמרו', check_error: 'לא ניתן לבדוק כרגע', orders_not_checked: 'הזמנות: לא נבדק', subs_not_checked: 'מנויים: לא נבדק',
      st_merged: 'אוחד',
      related_later: 'הפניות הקודמות ייטענו כשהמערכת תתפנה.',
      old_section: 'ישנים (30+ יום)', subs_no_email: 'מנויים: לא נבדק (אין מייל)', subs_unavailable: 'בדיקת המנויים לא זמינה כרגע.',
      siblings: 'ללקוח יש עוד {n} פניות פתוחות', siblings_one: 'ללקוח יש עוד פנייה פתוחה אחת', siblings_short: '+{n} פתוחות',
      tab_bot: '🤖 הבוט של דונדי מטפל', empty_bot: 'אין כרגע שיחות שהבוט של דונדי מטפל בהן', st_bot: '🤖 בוט',
      tab_failed: '⚠️ נכשלו', empty_failed: 'אין שליחות וואטסאפ שנכשלו', wa_fail: '⚠️ השליחה נכשלה',
      tab_wa24: '🕓 מעל 24 שעות', empty_wa24: 'אין צ׳אטים שעברו 24 שעות', wa_win_closed: '🕓 מעל 24 שעות — רק תבנית', wa_win_soon: '⏳ נסגר בעוד {d}',
      wa_win_note: 'הלקוח לא כתב יותר מ-24 שעות. וואטסאפ מאפשר עכשיו רק תבנית מאושרת, לכן אי אפשר לשלוח טקסט חופשי.',
      tpl_title: 'שליחת תבנית מאושרת (מעירה את השיחה)', tpl_send: 'שלח תבנית', tpl_send_arm: 'ללחוץ שוב לאישור', tpl_loading: 'טוען תבניות…',
      tpl_none: 'לא נמצאו תבניות מאושרות ב-Dondy למותג הזה.', tpl_sent_ok: 'התבנית נכנסה לתור לשליחה', tpl_then: 'לשלוח את התשובה שכתבתי כשהלקוח עונה',
      tpl_then_hint: 'אם הלקוח עונה תשובה קצרה, התשובה שכתבת נשלחת לבד בשמך. אם הוא שואל משהו חדש, היא מחכה לאישור שלך.',
      wa_fail_tpl: '⚠️ עברו 24 שעות — צריך תבנית בדונדי', wa_fail_unknown_note: 'לא ידוע אם ההודעה יצאה — בדקו בדונדי לפני שליחה חוזרת.',
      wa_fail_tpl_note: 'הלקוח לא כתב 24 שעות: וואטסאפ מאפשר רק תבנית מאושרת. שלחו תבנית מדונדי.',
      wa_fail_note: 'ההודעה לא יצאה. אפשר לשלוח שוב את אותו הטקסט.', wa_resend: 'שלח שוב', wa_resend_arm: 'לחצו שוב לשליחה חוזרת',
      bot_banner: 'הבוט של דונדי מטפל בשיחה הזאת. אין טיוטה — המנוע בודק אותה בכל ריצה.', takeover: 'לקחת את השיחה', takeover_arm: 'לחצו שוב כדי לקחת את השיחה',
      takeover_ok: 'השיחה אצלך — טיוטה תיכתב בריצה הבאה של המנוע', photo_dondy: '📷 תמונה — לצפייה בדונדי', photo_open: '📷 תמונה — פתיחה',
      photo_wait: '📷 תמונה — עוד לא הגיעה',
      err_bad_engine: 'המנוע החזיר תשובה לא תקינה. נסו שוב בעוד רגע.',
      ob_flight_send: '⏳ נשלח ברקע…', ob_flight_close: '⏳ נסגר ברקע…', ob_ok_email: '✅ נשלח', ob_ok_wa: '✅ נשלח לוואטסאפ', ob_ok_queued: '📤 נכנס לתור',
      ob_ok_close: '✅ טופל', ob_refused: '⚠️ לא נשלח — צריך תיקון', ob_refused_close: '⚠️ לא נסגר — צריך תיקון', ob_unknown: '❓ לא אושר — לבדוק',
      ob_checking: '⏳ בודק מה קרה לשליחה…', ob_retry: '⏳ מנסה לשלוח שוב…', ob_retry_close: '⏳ מנסה לסגור שוב…', ob_retry_n: 'ניסיון {n} מתוך {max}. המערכת מנסה שוב לבד, אין צורך לשלוח שוב.', ob_unsent: '⚠️ השליחה לא בוצעה — אפשר לשלוח שוב', ob_header: 'בתהליך שליחה ({n})', ob_none: 'אין שליחות בתהליך',
      ob_toast_ok: '{name}: נשלח', ob_toast_queued: '{name}: נכנס לתור לוואטסאפ', ob_toast_refused: '{name}: לא נשלח — צריך תיקון', ob_toast_unknown: '{name}: לא אושר — לבדוק',
      ob_toast_closed: '{name}: טופל', ob_why: 'הסיבה:', ob_inflight_lock: 'השליחה הקודמת עדיין בדרך — אין לשלוח שוב.',
      st_wa_queued: '📤 בתור לוואטסאפ', st_unknown: 'סטטוס אחר', cat_unknown: 'אחר',
      wa_queued_chip: '📤 נכנס לתור לוואטסאפ — אל תשלחו שוב', wa_already: 'ההודעה כבר בתור לוואטסאפ — לא נשלחה פעם שנייה',
      wa_locked: 'לא אושר אם ההודעה נכנסה לתור — השליחה נעולה עד שהמנוע יאשר את המצב', wa_check: 'לבדוק שוב',
      list_stale: 'הרשימה לא עודכנה {m} דקות — מנסה לרענן', list_refresh: 'רענון עכשיו',
      tk_partial: 'טוען את הפנייה המלאה…', tk_slow: 'המנוע איטי כרגע, מנסה שוב…', tk_failed: 'הפנייה המלאה לא נטענה כרגע.', tk_retry: 'לנסות שוב',
      search_local: 'תוצאות מהרשימה — מחפש גם בארכיון…', search_engine_failed: 'החיפוש בארכיון לא הצליח כרגע — מוצגות תוצאות מהרשימה בלבד.',
      reconnecting: 'מתעדכן…', send_wa: 'שליחה בוואטסאפ', send_email: 'שליחה במייל', chan_all: 'הכול', wa_banner: 'פנייה בוואטסאפ',
      email_banner: 'פנייה במייל', err_restarting: 'השרת בעדכון — נסו שוב בעוד דקה.',
      err_restart_write: 'השרת התעדכן בדיוק ברגע הזה. רעננו את הפנייה ובדקו אם הפעולה בוצעה לפני שמנסים שוב.',
      tab_auto: 'ביטולי מנוי אוטומטיים', empty_auto: 'אין ביטולים אוטומטיים שממתינים', auto_na: 'הביטול האוטומטי עוד לא זמין במנוע של המותג הזה.',
      ac_state_queued: 'אושר — יבוטל {when}', ac_state_queued_nodue: 'אושר — בתור לביטול', ac_state_shadow_would_cancel: 'הצעה: המערכת הייתה מבטלת',
      ac_state_aborted_newer: 'נעצר: הלקוח כתב שוב', ac_state_refused: 'נעצר: המנוע סירב', ac_state_cancelling: 'מבטל בקאצ׳ינג…', ac_state_cancelled: 'בוטל — שולח תשובה…',
      ac_state_replying: 'שולח תשובה…', ac_state_cancelled_reply_failed: "בוטל בקאצ'ינג אבל התשובה לא נשלחה — שלחו ידנית",
      ac_state_aborted_human: 'בוטל התהליך: נציג טיפל ידנית', ac_state_aborted_stale: 'בוטל התהליך: הרשומה התיישנה', ac_state_aborted_from: 'בוטל התהליך: כתובת השולח לא תקינה',
      ac_state_failed: 'נכשל', ac_state_recovered: 'שוחזר אחרי תקלה', ac_approved_by: 'אושר ע״י {u}', ac_ticket_status: 'הפנייה: {s}',
      ac_model: 'נימוק המודל', ac_ev_auth_detail: '(DKIM: {d} · SPF: {s})',
      ac_last_msg: 'ההודעה האחרונה של הלקוח', ac_contract: 'המנוי שזוהה', ac_next: 'חיוב הבא', ac_reply: 'התשובה ללקוח (אפשר לערוך)',
      ac_ev_auth_ok: 'המייל מאומת ✓', ac_ev_auth_bad: 'המייל לא מאומת ✗', ac_ev_one: 'מנוי אחד פעיל ✓', ac_ev_many: '{n} מנויים פעילים ✗', ac_ev_none: 'אין מנוי פעיל ✗',
      ac_ev_reason_ok: 'בקשה יחידה: ביטול ✓',
      ac_approve: 'אשר וביטול', ac_approve_q: 'לאשר את הביטול?', ac_approve_body: 'המנוי יבוטל ותשלח תשובה ללקוח בעוד כמה דקות.',
      ac_manual: 'העבר לטיפול ידני', ac_note_ph: 'למה לטיפול ידני? (חובה)', ac_manual_go: 'העבר', ac_note_req: 'צריך לכתוב הערה.',
      ac_ok: 'אושר — המנוי יבוטל והתשובה תישלח בעוד כמה דקות', ac_moved: 'הועבר לטיפול ידני', ac_refused: 'המנוע סירב:', ac_mode: 'מצב: {m}',
      mode_off: 'כבוי', mode_live: 'חי', mode_shadow: 'צל',
      ok: 'אישור', cancel_btn: 'ביטול',
      settings: 'מצב מערכת', set_title: 'מצב מערכת — {b}', set_admin_only: 'רק אדמין.',
      set_DRY_RUN: 'מצב ניסיון', set_DRY_RUN_help: 'מצב ניסיון: טיוטות לשיט בלבד, שום דבר לא נשלח',
      set_KACHING_WRITES: 'ביטולי מנוי', set_KACHING_WRITES_help: "ביטולי מנוי בקאצ'ינג מופעלים",
      set_AUTO_CANCEL: 'ביטול אוטומטי', set_AUTO_CANCEL_help: 'כבוי / צל: רק מציע / פעיל: מבטל ועונה לבד אחרי כמה דקות',
      val_on: 'פועל', val_off: 'כבוי', val_shadow: 'צל', set_confirm_q: 'לשנות "{k}" ל"{v}" במותג {b}?', set_ok: 'עודכן', set_noop: 'לא השתנה — כבר היה במצב הזה', set_refused: 'המנוע סירב לשינוי:',
      mode_test: 'מצב ניסיון — שליחה כבויה', mode_is_live: 'מצב חי — תשובות נשלחות ללקוחות', mode_kaching: "ביטולי קאצ'ינג: {v}", mode_auto: 'ביטול אוטומטי: {v}',
      as_title: 'עוזר ידע', as_open: 'עוזר', as_ph: 'שאלו על המדיניות, המוצר או הלקוח…', as_send: 'שאל', as_clear: 'שיחה חדשה',
      as_ctx: 'כולל את הפנייה הפתוחה', as_thinking: 'חושב…', as_hello: 'אפשר לשאול כאן על המדיניות והמוצרים של {b}, או "מה לענות כאן?" כשפנייה פתוחה. העוזר רק קורא — הוא לא שולח ולא משנה כלום.',
      as_me: 'אני', as_bot: 'עוזר', tool_search_customer: 'חיפש לקוח', tool_get_ticket: 'קרא פנייה', as_close: 'סגירה', as_na: 'העוזר לא זמין בשרת הזה.',
      not_connected_hint: 'כשהמנוע של המותג יחובר, הפניות יופיעו כאן אוטומטית.',
      tab_autoreply: 'נענה אוטומטית — לבדיקה', empty_autoreply: 'אין תשובות אוטומטיות שממתינות לבדיקה',
      ar_label: '🤖 נענה אוטומטית', ar_label_shadow: '🤖 היה נשלח אוטומטית', ar_label_queued: '🤖 יישלח אוטומטית {when}', ar_failed: 'השליחה האוטומטית נכשלה',
      ar_sent_at: 'נשלח {when}', ar_question: 'שאלת הלקוח', ar_reply: 'התשובה שנשלחה', ar_reply_shadow: 'התשובה שהייתה נשלחת',
      ar_ok: '✓ נבדק — תקין', ar_problem: '⚠ בעיה', ar_note_ph: 'מה לא תקין? (חובה — הפנייה תיפתח מחדש)', ar_problem_go: 'סמן בעיה ופתח מחדש',
      ar_reviewed_ok: '✓ נבדק ע״י {u}', ar_reviewed_problem: '⚠ סומן כבעיה ע״י {u}', ar_pending: 'ממתין לבדיקה', ar_open: 'פתיחת הפנייה',
      ar_done_ok: 'סומן כתקין', ar_done_problem: 'סומן כבעיה — הפנייה נפתחה מחדש', ar_na: 'התשובות האוטומטיות עוד לא זמינות במנוע של המותג הזה.',
      ar_mode: 'מענה אוטומטי: {m}', mode_auto_reply: 'מענה אוטומטי: {v}', what_to_do: 'מה לעשות',
      set_AUTO_REPLY: 'מענה אוטומטי', set_AUTO_REPLY_help: 'כבוי / צל: מסמן מה היה נשלח / פעיל: עונה לבד על מיילים פשוטים ומסמן לבדיקה',
      set_AUTO_REPLY_note: 'מצב "פעיל" דורש שמצב ניסיון יהיה כבוי.',
      syncing: 'טוען גרסה עדכנית…', checking: 'מתעדכן…', sync_failed: 'לא עודכן ({m}) — מוצג עותק מ{when}', tk_updated: 'יש גרסה חדשה של הפנייה', apply_update: 'הצג',
      live_new_msg: 'התקבלה הודעה חדשה', live_new_msgs: 'התקבלו {n} הודעות חדשות', live_ok: 'הבנתי',
      draft_new_avail: 'המנוע כתב טיוטה חדשה — הטיוטה שלך לא נגעה.', use_new_draft: 'החלף לטיוטה החדשה', draft_updated: 'הטיוטה עודכנה לפי ההודעה החדשה.',
      orders_err: 'בדיקת ההזמנות נכשלה: {m}', subs_err: 'בדיקת המנויים נכשלה: {m}',
      // users
      u_title: 'ניהול משתמשים', u_new: 'משתמש חדש', u_username: 'שם משתמש (לועזית)', u_display: 'שם תצוגה', u_roles: 'תפקיד', u_brands: 'מותגים',
      u_lang: 'שפה', u_disabled: 'מושבת', u_active: 'פעיל', u_create: 'יצירה', u_save: 'שמירה', u_edit: 'עריכה', u_cancel: 'ביטול',
      u_reset: 'איפוס סיסמה', u_reset_arm: 'לחצו שוב לאיפוס', u_temp: 'סיסמה זמנית:', u_temp_note: 'מוצגת פעם אחת בלבד. שלחו אותה למשתמש בערוץ פרטי — בכניסה הראשונה יבחר סיסמה משלו.',
      u_saved: 'נשמר', u_created: 'המשתמש נוצר', u_last: 'כניסה אחרונה', u_never: 'עוד לא נכנס', u_audit: 'יומן שינויים (100 אחרונים)',
      u_must_change: 'סיסמה זמנית', role_agent: 'נציג/ה', role_admin: 'אדמין', 'role_user-manager': 'מנהל/ת משתמשים',
      lang_he: 'עברית', lang_en: 'אנגלית', u_admin_only: 'רק אדמין', u_me: 'אני'
    },
    en: {
      app: 'Customer service', tab_ready: 'Open', tab_action: 'Needs decision', tab_health: 'Health', tab_delay: 'Delay',
      tab_sent: 'Waiting for customer', tab_today: 'Handled today', tab_search: 'Search',
      st_ready: 'New', st_action: 'Needs decision', st_health: 'Health', st_delay: 'Delay', st_sent: 'Waiting for customer', st_done: 'Handled', st_noreply: 'No reply',
      cat_shipping: 'Shipping', cat_product: 'Product', cat_order_change: 'Order change', cat_return_refund: 'Return / refund', cat_cancel_subscription: 'Cancel subscription',
      cat_billing: 'Billing', cat_health: 'Health', cat_complaint: 'Complaint', cat_legal: 'Legal', cat_discount: 'Discount', cat_voc: 'Customer research', cat_other: 'Other',
      ch_email: 'Email', ch_whatsapp: 'WhatsApp',
      dry_run: 'Test mode — sending is off. You can read, edit and save drafts; nothing reaches the customer.',
      frozen: 'Subscription cancellations are frozen for this brand — only an admin can lift it.',
      mock: 'Local preview — fake data, nothing is sent.', bootstrap_env: 'ADMIN_BOOTSTRAP is still set on the server. Remove it in Render.',
      no_brands: 'You have no brands. Ask Manager.', not_connected: 'Brand {b} is not connected yet.',
      loading: 'Loading…', empty_ready: 'No open tickets', empty_action: 'Nothing waits for a decision', empty_health: 'No health tickets',
      empty_delay: 'No delays', empty_sent: 'Nothing waits for the customer', empty_today: 'Nothing handled yet today',
      empty_hint: 'The list refreshes every minute.', search_ph: 'Name, email, phone or order number', search_min: 'At least 2 characters',
      search_none: 'Nothing found', archived: 'Archived', waiting: 'waiting {d}', handled_by: '{who} · {when}', updated: 'updated {when}',
      no_name: 'No name', msgs: '{n} messages', back: 'Back', copy: 'Copy', copied: 'Copied', copy_fail: 'Copy failed — select and copy by hand',
      why_human: 'Why a human', summary: 'Summary', conversation: 'Conversation', customer: 'Customer', us: 'Us', automatic: 'Automatic message',
      show_more: 'Show all', show_less: 'Show less', quote: 'Quote',
      draft: 'Reply draft', draft_readonly: 'Already handled — the draft is read-only.', save_local: 'Saved on this device…', saving: 'Saving…',
      saved: 'Saved ✓', save_failed: 'Not saved on the server: {m} — the text is kept on this device.', restored: 'Restored an unsaved draft from this device.',
      conflict: 'The server draft changed since you edited (maybe the customer wrote again). Your version is shown.',
      use_server: 'Use the server version', keep_mine: 'Keep mine',
      send: 'Send', send_arm: 'Click again to send', send_dry: 'Sending is off (test mode)', sent_ok: 'Sent to the customer', queued_ok: 'Queued for WhatsApp',
      send_anyway: 'Send anyway (logged)', handled: 'Handled without sending', handled_arm: 'Click again — handled without sending',
      close: 'Close', close_arm: 'Click again to close', closed_ok: 'Ticket closed', handled_ok: 'Marked handled', safety: 'Safety check: {p}',
      orders: 'Orders', no_orders: 'No order found (orders older than 60 days are invisible).', lookup_error: 'The order lookup failed when the draft was written.',
      track: 'Tracking', items: 'Items', ordered: 'Ordered', shipped_on: 'Shipped',
      ship_not_late: 'On time', ship_late: 'Late', ship_very_late: 'Very late', ship_unknown: 'Unknown', ship_not_applicable: 'Not applicable',
      ship_line: '{state} · {d} days since the order',
      fin_PAID: 'Paid', fin_PENDING: 'Payment pending', fin_REFUNDED: 'Refunded', fin_PARTIALLY_REFUNDED: 'Partially refunded', fin_VOIDED: 'Voided',
      fin_AUTHORIZED: 'Authorized', fin_PARTIALLY_PAID: 'Partially paid',
      ful_FULFILLED: 'Shipped', ful_UNFULFILLED: 'Not shipped yet', ful_PARTIALLY_FULFILLED: 'Partially shipped', ful_IN_PROGRESS: 'In progress',
      ful_ON_HOLD: 'On hold', ful_SCHEDULED: 'Scheduled', ful_RESTOCKED: 'Restocked',
      subs: 'Subscriptions', no_subs: 'No subscriptions for this customer (by email).', sub_status: 'Status', sub_every: 'Frequency', sub_next: 'Next billing',
      sub_next_na: 'not provided by the engine', sub_since: 'Since', sub_lastpay: 'Last payment', sub_id: 'Contract',
      pay_SUCCEEDED: 'Succeeded', pay_FAILED: 'Failed', pay_PENDING: 'Pending', pay_REFUNDED: 'Refunded',
      ss_ACTIVE: 'Active', ss_PAUSED: 'Paused', ss_CANCELLED: 'Cancelled', ss_FAILED: 'Payment failed', ss_EXPIRED: 'Expired',
      every_day: 'Every day', every_week: 'Every week', every_month: 'Every month', every_year: 'Every year', every_n: 'Every {n} {u}',
      unit_day: 'days', unit_week: 'weeks', unit_month: 'months', unit_year: 'years',
      cancel_sub: 'Cancel subscription', cancelled_here: 'Cancelled from this screen',
      afs_title: 'Your message to {name} was sent. Still to do:', afs_open: 'Open the ticket', afs_done: 'Done', afs_chip: 'Still to do', afs_cancelled: "{name}'s subscription was cancelled automatically",
      afs_sub_no_email: 'The subscription was NOT cancelled: the ticket has no customer email, so the subscription cannot be found. Cancel it manually.',
      afs_sub_unreachable: 'The subscription was NOT cancelled: the subscriptions system could not be reached. Cancel it manually.',
      afs_sub_several: 'The subscription was NOT cancelled: the customer has several active subscriptions. Choose which one to cancel in the subscriptions panel.',
      afs_sub_refused: 'The subscription was NOT cancelled: the subscriptions system refused. Cancel it manually.',
      afs_order_cancel: 'Shopify still shows the order as not cancelled. Cancel it in Shopify.',
      afs_order_refund: 'Shopify shows no refund yet. Make the refund in Shopify.',
      afs_order_unknown: 'The message mentions an order cancellation or a refund and it could not be checked in Shopify. Check manually.',
      dlg_title: 'Cancel subscription', dlg_type: 'To confirm, type the last 4 digits of the contract number',
      dlg_reason: 'Reason', dlg_reason_opt: '(optional — the customer asked to cancel)', dlg_reason_req: '(required — the customer did not ask: 10+ characters, two words)',
      dlg_off: 'The engine says cancellations are off — this will likely be refused.', dlg_frozen: 'Cancellations are frozen — this will likely be refused.',
      dlg_go: 'Cancel the subscription', dlg_back: 'Back', dlg_working: 'Cancelling…', dlg_irrev: 'This cannot be undone and is never retried automatically.',
      notes: 'Internal notes', note_ph: 'Note for the team (never sent to the customer)', note_add: 'Add', note_ok: 'Note saved', no_notes: 'No notes.',
      details: 'Details', created: 'Opened', handled_at: 'Handled', by: 'by', ticket_id: 'Id', language: 'Language', order: 'Order',
      audit_na: 'The full action log lives in the engine (audit sheet) and is not exposed here.',
      related: "Customer's other tickets", no_related: 'No other tickets.',
      stale: 'This ticket changed on the server ({what}).', stale_new: 'the customer wrote again', stale_status: 'the status changed', refresh: 'Refresh',
      pick_ticket: 'Pick a ticket from the list',
      menu: 'Menu', users: 'Users', change_pw: 'Change password', logout: 'Sign out', to_en: 'English UI', to_he: 'Hebrew UI', to_tickets: 'Back to tickets',
      err_network: 'No connection. Nothing was sent — try again.', err_bad_response: 'Invalid server answer.', err_login: 'Please sign in again.',
      orders_chip_only: 'Order details were not saved', check_error: 'Cannot check right now', orders_not_checked: 'Orders: not checked', subs_not_checked: 'Subscriptions: not checked',
      st_merged: 'Merged',
      related_later: 'Previous tickets will load when the system is free.',
      old_section: 'Older than 30 days', subs_no_email: 'Subscriptions: not checked (no email)', subs_unavailable: 'Subscription lookup unavailable right now.',
      siblings: 'This customer has {n} more open tickets', siblings_one: 'This customer has 1 more open ticket', siblings_short: '+{n} open',
      tab_bot: '🤖 Dondy bot is handling', empty_bot: 'The Dondy bot is not handling any chat right now', st_bot: '🤖 Bot',
      tab_failed: '⚠️ Failed', empty_failed: 'No failed WhatsApp sends', wa_fail: '⚠️ The send failed',
      tab_wa24: '🕓 Over 24 hours', empty_wa24: 'No chats past 24 hours', wa_win_closed: '🕓 Over 24 hours — template only', wa_win_soon: '⏳ Closes in {d}',
      wa_win_note: 'The customer has not written for more than 24 hours. WhatsApp now allows only an approved template, so free text cannot be sent.',
      tpl_title: 'Send an approved template (wakes the chat)', tpl_send: 'Send template', tpl_send_arm: 'Click again to confirm', tpl_loading: 'Loading templates…',
      tpl_none: 'No approved templates were found in Dondy for this brand.', tpl_sent_ok: 'The template is queued for sending', tpl_then: 'Send the reply I wrote when the customer answers',
      tpl_then_hint: 'If the customer answers briefly, your reply goes out by itself in your name. If they ask something new, it waits for your approval.',
      wa_fail_tpl: '⚠️ 24 hours passed — needs a template in Dondy', wa_fail_unknown_note: 'Unknown whether it went out — check in Dondy before sending again.',
      wa_fail_tpl_note: 'The customer has not written for 24 hours: WhatsApp allows only an approved template. Send one from Dondy.',
      wa_fail_note: 'The message did not go out. You can send the same text again.', wa_resend: 'Send again', wa_resend_arm: 'Click again to resend',
      bot_banner: 'The Dondy bot is handling this chat. No draft — the engine re-checks it every run.', takeover: 'Take over', takeover_arm: 'Click again to take over',
      takeover_ok: 'The chat is yours — a draft will be written on the next engine run', photo_dondy: '📷 Photo — view in Dondy', photo_open: '📷 Photo — open',
      photo_wait: '📷 Photo — not arrived yet',
      err_bad_engine: 'The engine returned an invalid answer. Try again in a moment.',
      ob_flight_send: '⏳ Sending in the background…', ob_flight_close: '⏳ Closing in the background…', ob_ok_email: '✅ Sent', ob_ok_wa: '✅ Sent to WhatsApp', ob_ok_queued: '📤 Queued',
      ob_ok_close: '✅ Handled', ob_refused: '⚠️ Not sent — needs a fix', ob_refused_close: '⚠️ Not closed — needs a fix', ob_unknown: '❓ Not confirmed — check',
      ob_checking: '⏳ Checking what happened to the send…', ob_retry: '⏳ Trying to send again…', ob_retry_close: '⏳ Trying to close again…', ob_retry_n: 'Try {n} of {max}. The system retries by itself; do not send again.', ob_unsent: '⚠️ The send did not happen — you can send again', ob_header: 'Sending ({n})', ob_none: 'Nothing in progress',
      ob_toast_ok: '{name}: sent', ob_toast_queued: '{name}: queued for WhatsApp', ob_toast_refused: '{name}: not sent — needs a fix', ob_toast_unknown: '{name}: not confirmed — check',
      ob_toast_closed: '{name}: handled', ob_why: 'Reason:', ob_inflight_lock: 'The previous send is still on its way — do not send again.',
      st_wa_queued: '📤 Queued for WhatsApp', st_unknown: 'Other status', cat_unknown: 'Other',
      wa_queued_chip: '📤 Queued for WhatsApp — do not send again', wa_already: 'Already queued for WhatsApp — not sent a second time',
      wa_locked: 'Not confirmed whether the message was queued — sending is locked until the engine confirms', wa_check: 'Check again',
      list_stale: 'The list has not updated for {m} minutes — trying to refresh', list_refresh: 'Refresh now',
      tk_partial: 'Loading the full ticket…', tk_slow: 'The engine is slow right now, trying again…', tk_failed: 'The full ticket could not load right now.', tk_retry: 'Try again',
      search_local: 'Results from the list — searching the archive too…', search_engine_failed: 'The archive search failed right now — showing results from the list only.',
      reconnecting: 'Reconnecting…', send_wa: 'Send on WhatsApp', send_email: 'Send by email', chan_all: 'All', wa_banner: 'WhatsApp conversation',
      email_banner: 'Email conversation', en_confirm_wa: 'Confirm translation and send on WhatsApp', en_confirm_email: 'Confirm translation and send by email', err_restarting: 'The server is updating — try again in a minute.',
      err_restart_write: 'The server restarted at exactly this moment. Refresh the ticket and check whether the action happened before trying again.',
      tab_auto: 'Automatic cancellations', empty_auto: 'No automatic cancellations waiting', auto_na: 'Automatic cancellation is not available in this brand engine yet.',
      ac_state_queued: 'Approved — cancels {when}', ac_state_queued_nodue: 'Approved — queued', ac_state_shadow_would_cancel: 'Proposal: the system would cancel',
      ac_state_aborted_newer: 'Stopped: the customer wrote again', ac_state_refused: 'Stopped: the engine refused', ac_state_cancelling: 'Cancelling in Kaching…', ac_state_cancelled: 'Cancelled — sending the reply…',
      ac_state_replying: 'Sending the reply…', ac_state_cancelled_reply_failed: 'Cancelled in Kaching but the reply was NOT sent — send it by hand',
      ac_state_aborted_human: 'Aborted: an agent handled it', ac_state_aborted_stale: 'Aborted: the record went stale', ac_state_aborted_from: 'Aborted: bad sender address',
      ac_state_failed: 'Failed', ac_state_recovered: 'Recovered after a fault', ac_approved_by: 'approved by {u}', ac_ticket_status: 'ticket: {s}',
      ac_model: 'Model reasoning', ac_ev_auth_detail: '(DKIM: {d} · SPF: {s})',
      ac_last_msg: "Customer's last message", ac_contract: 'Matched contract', ac_next: 'Next billing', ac_reply: 'Reply to the customer (editable)',
      ac_ev_auth_ok: 'Email verified ✓', ac_ev_auth_bad: 'Email not verified ✗', ac_ev_one: 'One active contract ✓', ac_ev_many: '{n} active contracts ✗', ac_ev_none: 'No active contract ✗',
      ac_ev_reason_ok: 'Single request: cancel ✓',
      ac_approve: 'Approve and cancel', ac_approve_q: 'Approve this cancellation?', ac_approve_body: 'The subscription will be cancelled and the reply sent to the customer in a few minutes.',
      ac_manual: 'Move to manual handling', ac_note_ph: 'Why manual? (required)', ac_manual_go: 'Move', ac_note_req: 'A note is required.',
      ac_ok: 'Approved — cancels and replies in a few minutes', ac_moved: 'Moved to manual handling', ac_refused: 'The engine refused:', ac_mode: 'Mode: {m}',
      mode_off: 'off', mode_live: 'live', mode_shadow: 'shadow',
      ok: 'OK', cancel_btn: 'Cancel',
      settings: 'System mode', set_title: 'System mode — {b}', set_admin_only: 'Admin only.',
      set_DRY_RUN: 'Test mode', set_DRY_RUN_help: 'Test mode: drafts to the sheet only, nothing is sent',
      set_KACHING_WRITES: 'Subscription cancels', set_KACHING_WRITES_help: 'Kaching subscription cancellations are enabled',
      set_AUTO_CANCEL: 'Automatic cancel', set_AUTO_CANCEL_help: 'Off / shadow: only proposes / on: cancels and replies by itself after a few minutes',
      val_on: 'On', val_off: 'Off', val_shadow: 'Shadow', set_confirm_q: 'Change "{k}" to "{v}" for {b}?', set_ok: 'Updated', set_noop: 'No change — it was already so', set_refused: 'The engine refused the change:',
      mode_test: 'Test mode — sending is off', mode_is_live: 'Live — replies reach customers', mode_kaching: 'Kaching cancels: {v}', mode_auto: 'Auto-cancel: {v}',
      as_title: 'Knowledge assistant', as_open: 'Assistant', as_ph: 'Ask about the policy, the product or the customer…', as_send: 'Ask', as_clear: 'New chat',
      as_ctx: 'Include the open ticket', as_thinking: 'Thinking…', as_hello: 'Ask about {b} policy and products here, or "what should I answer?" while a ticket is open. The assistant only reads — it never sends or changes anything.',
      as_me: 'Me', as_bot: 'Assistant', tool_search_customer: 'searched customer', tool_get_ticket: 'read ticket', as_close: 'Close', as_na: 'The assistant is not available on this server.',
      not_connected_hint: 'Tickets will appear here once the brand engine is connected.',
      tab_autoreply: 'Auto-answered — to review', empty_autoreply: 'No automatic replies waiting for review',
      ar_label: '🤖 Answered automatically', ar_label_shadow: '🤖 Would have been sent automatically', ar_label_queued: '🤖 Will be sent automatically {when}', ar_failed: 'The automatic send failed',
      ar_sent_at: 'sent {when}', ar_question: "Customer's question", ar_reply: 'The reply that was sent', ar_reply_shadow: 'The reply that would have been sent',
      ar_ok: '✓ Reviewed — OK', ar_problem: '⚠ Problem', ar_note_ph: 'What is wrong? (required — the ticket reopens)', ar_problem_go: 'Flag and reopen',
      ar_reviewed_ok: '✓ Reviewed by {u}', ar_reviewed_problem: '⚠ Flagged by {u}', ar_pending: 'Waiting for review', ar_open: 'Open the ticket',
      ar_done_ok: 'Marked OK', ar_done_problem: 'Flagged — the ticket was reopened', ar_na: 'Automatic replies are not available in this brand engine yet.',
      ar_mode: 'Auto-reply: {m}', mode_auto_reply: 'Auto-reply: {v}', what_to_do: 'What to do',
      set_AUTO_REPLY: 'Auto-reply', set_AUTO_REPLY_help: 'Off / shadow: marks what would be sent / on: answers simple emails by itself and flags them for review',
      set_AUTO_REPLY_note: '"On" requires test mode to be off.',
      syncing: 'Loading the latest version…', checking: 'Updating…', sync_failed: 'Not updated ({m}) — showing a copy from {when}', tk_updated: 'A newer version of this ticket is ready', apply_update: 'Show',
      live_new_msg: 'A new message arrived', live_new_msgs: '{n} new messages arrived', live_ok: 'Got it',
      draft_new_avail: 'The engine wrote a new draft — yours is untouched.', use_new_draft: 'Use the new draft', draft_updated: 'The draft was updated for the new message.',
      orders_err: 'Order lookup failed: {m}', subs_err: 'Subscription lookup failed: {m}',
      tr_loading: 'Translating…', tr_failed: 'Translation failed: {m}', show_orig: 'Show original', show_en: 'Show English', tr_from: 'translated from {l}',
      en_draft: 'Your reply (write in English)', en_draft_loading: 'Translating the AI draft into English…', en_draft_ai: 'Prefilled with the AI draft, translated to English. Edit freely.',
      en_safety: 'Write in English. Customers receive only the approved Hebrew translation. If translation fails, nothing is sent.', en_invalid: 'A valid Hebrew translation is required. Nothing was sent. Please translate again.', en_review: 'Translate to Hebrew', en_reviewing: 'Translating…', en_side_en: 'Your English', en_side_out: 'What the customer gets ({l})',
      en_confirm: 'Confirm translation and send', en_edit: 'Back to edit', en_same: 'Customers receive the Hebrew translation only.',
      en_stale: 'You changed the English text — translate again before sending.', tr_retry: 'Retry translation', tr_incomplete: '{n} not translated (original shown)',
      lang_name_he: 'Hebrew', lang_name_ru: 'Russian', lang_name_en: 'English', lang_name_ar: 'Arabic', lang_name_fr: 'French',
      u_title: 'Users', u_new: 'New user', u_username: 'Username', u_display: 'Display name', u_roles: 'Role', u_brands: 'Brands',
      u_lang: 'Language', u_disabled: 'Disabled', u_active: 'Active', u_create: 'Create', u_save: 'Save', u_edit: 'Edit', u_cancel: 'Cancel',
      u_reset: 'Reset password', u_reset_arm: 'Click again to reset', u_temp: 'Temporary password:', u_temp_note: 'Shown once. Send it privately; the user picks their own at first sign-in.',
      u_saved: 'Saved', u_created: 'User created', u_last: 'Last sign-in', u_never: 'never', u_audit: 'Change log (last 100)',
      u_must_change: 'temporary password', role_agent: 'Agent', role_admin: 'Admin', 'role_user-manager': 'User manager',
      lang_he: 'Hebrew', lang_en: 'English', u_admin_only: 'admin only', u_me: 'me'
    }
  };
  function t(k, vars) {
    let s = (STR[LANG] && STR[LANG][k] !== undefined) ? STR[LANG][k] : (STR.he[k] !== undefined ? STR.he[k] : k);
    if (vars) Object.keys(vars).forEach(function (a) { s = s.split('{' + a + '}').join(String(vars[a])); });
    return s;
  }

  /** Like t(), but returns nodes: every inserted value sits in its own <bdi>, so an English name or an id inside a
   *  Hebrew sentence cannot reorder the sentence around it (measured: "$30→$25" read as a price rise). */
  function tx(k, vars) {
    const tmpl = t(k);
    const frag = document.createDocumentFragment();
    const re = /\{([a-z_]+)\}/g;
    let last = 0;
    let m;
    while ((m = re.exec(tmpl)) !== null) {
      frag.append(tmpl.slice(last, m.index));
      const v = vars && vars[m[1]] !== undefined ? vars[m[1]] : m[0];
      const b = document.createElement('bdi');
      if (v && v.nodeType) b.append(v); else b.textContent = String(v);
      frag.append(b);
      last = re.lastIndex;
    }
    frag.append(tmpl.slice(last));
    return frag;
  }

  // ---------------------------------------------------------------- DOM helpers
  function h(tag, props) {
    const el = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        const v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'style') throw new Error('h(): inline style is blocked by the CSP (style-src self) — use a class');
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k.slice(0, 2) === 'on' && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (k === 'value') el.value = v;
        else if (k === 'checked' || k === 'disabled' || k === 'readOnly' || k === 'hidden' || k === 'open') el[k] = !!v;
        else el.setAttribute(k, v === true ? '' : String(v));
      });
    }
    for (let i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c === null || c === undefined || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  const $ = function (id) { return document.getElementById(id); };
  const ICONS = {
    wa: 'M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.1 14.9l-.3-.2-3 .8.8-2.9-.2-.3A8 8 0 0 1 12 4zm-3.2 4c-.2 0-.5 0-.7.3-.2.3-.9.9-.9 2.2s.9 2.5 1 2.7c.1.2 1.8 2.8 4.4 3.9 2.2.9 2.6.7 3.1.6.5 0 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2l-.4-.3-1.6-.8c-.2-.1-.4-.1-.6.1l-.7.9c-.1.2-.3.2-.5.1a6.6 6.6 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.7-1.8c-.2-.5-.4-.4-.5-.4h-.5z',
    mail: 'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm1 2v.4l8 5.1 8-5.1V7H4zm16 2.8-7.5 4.8a1 1 0 0 1-1 0L4 9.8V17h16V9.8z'
  };
  function icon(name) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'ic');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', ICONS[name]);
    path.setAttribute('fill', 'currentColor');
    svg.append(path);
    return svg;
  }
  function isWA(x) { return String((x && x.channel) || '').toLowerCase() === 'whatsapp'; }
  /** QA round 5 (double WhatsApp send): queued = status wa_queued, or (older engine) wa_send pending on an open ticket. */
  /** A failed WhatsApp send: wa_send failed | template_required | unknown (claim expired), the ticket back in "action".
   *  Engine @47/48: every WhatsApp list row carries wa_send (state) — it decides; the action line only when it is missing.
   *  -> 'failed' | 'template_required' | 'unknown' | null */
  const WA_FAIL_STATES = ['failed', 'template_required', 'unknown'];
  function waFail(x) {
    if (!x || !isWA(x) || OPEN.indexOf(x.status) < 0) return null;
    const st = String(x.wa_send || '').split(':')[0];
    if (WA_FAIL_STATES.indexOf(st) >= 0) return st;
    if (st) return null;                                             // pending / claimed / sent: not a failure
    const a = String(x.action || '').trim();
    // the engine's WA_FAIL_MARK (with or without U+FE0F), or its own failure lines — older ones carry no mark
    if (a.charAt(0) !== '\u26A0' && !/בדקו בדונדי לפני שליחה חוזרת|חלון 24 השעות נסגר/.test(a)) return null;
    return /24|תבנית|template/i.test(a) ? 'template_required' : 'failed';
  }
  /** WhatsApp's 24-hour window, counted from the customer's last message (engine column wa_last_in). Meta refuses free text after it.
   *  -> { state: 'closed' | 'soon' | 'open', left } or null when the time is unknown / not an open WhatsApp ticket. */
  const WA_WINDOW_MS = 24 * 3600000, WA_WINDOW_MARGIN_MS = 2 * 60000, WA_SOON_MS = 4 * 3600000;
  function waWin(x) {
    if (!x || !isWA(x) || OPEN.indexOf(x.status) < 0) return null;
    const at = ms(x.wa_last_in);
    if (!at) return null;
    const left = at + WA_WINDOW_MS - WA_WINDOW_MARGIN_MS - Date.now();
    return { state: left <= 0 ? 'closed' : left < WA_SOON_MS ? 'soon' : 'open', left: left };
  }
  function waWinClosed(x) { const w = waWin(x); return !!w && w.state === 'closed'; }
  function waWinChip(x) {
    const w = waWin(x);
    if (!w || w.state === 'open') return null;
    return h('span', { class: 'chip wa-win ' + w.state, 'data-test': 'wa-win-chip', 'data-state': w.state, text: w.state === 'closed' ? t('wa_win_closed') : t('wa_win_soon', { d: dur(w.left) }) });
  }
  /** WhatsApp past 24 hours: the brand's approved templates exactly as Dondy lists them; sending one wakes the chat. The written answer can be
   *  kept to go out by itself once the customer replies (the engine decides: only after a short answer that is not a question). */
  const TPL = {};
  async function loadTemplates(brand) {
    const c = TPL[brand];
    if (c && Date.now() - c.at < 300000) return c.list;
    const r = await api('/api/' + encodeURIComponent(brand) + '/apiTemplates', { args: {} }, 'POST', { quiet: true });
    if (!r || !r.ok || !Array.isArray(r.templates)) return null;
    TPL[brand] = { list: r.templates, at: Date.now() };
    return r.templates;
  }
  // The draft card is redrawn whenever a draft save lands, so what the agent chose here (template, the waiting-reply tick, the armed
  // first click) lives outside the card, per ticket.
  const TPL_UI = {};
  function templateBox(brand, x, getDraft) {
    const mem = TPL_UI[brand + '|' + x.id] || (TPL_UI[brand + '|' + x.id] = { name: '', then: null, armedAt: 0 });
    const ARM_MS = 6000;
    const sel = h('select', { class: 'tpl-select', 'data-test': 'tpl-select', 'aria-label': t('tpl_title') });
    const prev = h('div', { class: 'tpl-preview', dir: 'auto', 'data-test': 'tpl-preview' });
    const thenCb = h('input', { type: 'checkbox', 'data-test': 'tpl-then' });
    const thenRow = h('label', { class: 'tpl-then', hidden: true }, thenCb, ' ', h('span', { text: t('tpl_then') }), h('div', { class: 'muted small', text: t('tpl_then_hint') }));
    const err = h('div', { class: 'error', hidden: true, role: 'alert', 'data-test': 'tpl-error' });
    const status = h('div', { class: 'muted small', text: t('tpl_loading'), 'data-test': 'tpl-status' });
    const btn = h('button', { class: 'btn primary wa', type: 'button', text: t('tpl_send'), 'data-test': 'tpl-send' });
    let list = [];
    let busy = false;
    const paintBtn = function () {
      const armedNow = Date.now() - mem.armedAt < ARM_MS;
      btn.classList.toggle('arm', armedNow);
      btn.textContent = armedNow ? t('tpl_send_arm') : t('tpl_send');
      btn.disabled = busy || !list.length;
    };
    // The chosen template is remembered by NAME (mem.name), never read back from the <select>: a redraw can leave the element unselected.
    const chosen = function () { return list.filter(function (tp) { return tp.name === mem.name; })[0] || list[0] || null; };
    const paint = function () {
      const tpl = chosen();
      if (tpl && sel.value !== tpl.name) sel.value = tpl.name;
      prev.textContent = tpl ? tpl.text : '';
      const has = !!String(getDraft() || '').trim();
      thenRow.hidden = !has;
      thenCb.checked = has && (mem.then === null ? true : mem.then);
      paintBtn();
    };
    async function fire() {
      const tpl = chosen();
      if (!tpl || busy) return;
      busy = true; paintBtn();
      err.hidden = true;
      const args = { id: x.id, template: tpl.name };
      const draft = String(getDraft() || '').trim();
      if (thenCb.checked && draft) args.then = draft;
      const r = await api('/api/' + encodeURIComponent(brand) + '/apiSendTemplate', { args: args, lang: LANG });
      busy = false;
      if (r && r.ok) { delete TPL_UI[brand + '|' + x.id]; toast(t('tpl_sent_ok')); pollChanges(brand); goNext(brand, x.id); return; }
      err.textContent = (r && (r.msg || r.message)) || t('err_bad_engine');
      err.hidden = false;
      paintBtn();
    }
    btn.addEventListener('click', function () {
      if (btn.disabled) return;
      if (Date.now() - mem.armedAt < ARM_MS) { mem.armedAt = 0; fire(); return; }      // the second click sends
      mem.armedAt = Date.now();
      paintBtn();
      setTimeout(paintBtn, ARM_MS + 100);
    });
    sel.addEventListener('change', function () { if (sel.value) { mem.name = sel.value; mem.armedAt = 0; } paint(); });
    thenCb.addEventListener('change', function () { mem.then = thenCb.checked; });
    const box = h('div', { class: 'tpl-box', 'data-test': 'tpl-box' }, h('b', { text: t('tpl_title') }), status, sel, prev, thenRow, h('div', { class: 'actions' }, btn), err);
    box.refresh = paint;
    paintBtn();
    loadTemplates(brand).then(function (l) {
      list = l || [];
      if (!list.length) { status.textContent = t('tpl_none'); sel.hidden = true; paintBtn(); return; }
      status.hidden = true;
      list.forEach(function (tp) { const o = document.createElement('option'); o.textContent = tp.name; o.value = tp.name; sel.append(o); });
      mem.name = chosen().name;
      paint();
    });
    return box;
  }
  /** The "failed" tab is for sends a person can still do something about here; a chat past 24 hours lives in its own tab. */
  function waFailActionable(x) { const k = waFail(x); return !!k && k !== 'template_required' && !waWinClosed(x); }
  function waFailChip(x) {
    const k = waFail(x);
    if (!k) return null;
    if (k === 'template_required' || waWinClosed(x)) return null;   // said by the 24-hour chip
    return h('span', { class: 'chip wa-fail', 'data-test': 'wa-fail-chip', 'data-kind': k, text: t('wa_fail') });
  }
  function waQueued(x) { return !!x && (x.status === 'wa_queued' || (isWA(x) && x.wa_send === 'pending')); }
  const WA_LOCK = {};
  function waLock(brand, id) { WA_LOCK[brand + '|' + id] = true; }
  function waLocked(brand, id) { return !!WA_LOCK[brand + '|' + id]; }
  /** The one channel pill used everywhere: WhatsApp green with a chat icon, email blue with an envelope. */
  function chanPill(x, big) {
    const wa = isWA(x);
    return h('span', { class: 'chip ch ' + (wa ? 'ch-wa' : 'ch-email') + (big ? ' big' : ''), 'data-test': wa ? 'ch-wa' : 'ch-email' },
      icon(wa ? 'wa' : 'mail'), t(wa ? 'ch_whatsapp' : 'ch_email'));
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function safeUrl(u) { return /^https:\/\/[^\s"<>]+$/i.test(String(u || '')) ? String(u) : null; }

  let toastTimer = null;
  function toast(msg) {
    const el = $('toast');
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('on'); }, 2600);
  }

  async function copyText(text, btn) {
    let ok = false;
    try {
      if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch (e) { ok = false; }
    if (!ok) {
      const ta = h('textarea', { class: 'offscreen', readonly: true, 'aria-hidden': 'true' });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      ta.remove();
    }
    if (btn) {
      btn.textContent = ok ? t('copied') : t('copy');
      btn.classList.toggle('done', ok);
      setTimeout(function () { btn.textContent = t('copy'); btn.classList.remove('done'); }, 1600);
    }
    if (!ok) toast(t('copy_fail'));
    return ok;
  }
  function copyBtn(text) {
    const b = h('button', { class: 'copy', type: 'button', text: t('copy'), 'aria-label': t('copy') });
    b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); copyText(text, b); });
    return b;
  }

  /** A button that needs two clicks within 4s. */
  function armed(label, armLabel, cls, onFire) {
    const b = h('button', { class: 'btn ' + (cls || ''), type: 'button', text: label });
    let armedAt = 0;
    let timer = null;
    b.addEventListener('click', function () {
      if (b.disabled) return;
      if (Date.now() - armedAt < 4000) {
        armedAt = 0; clearTimeout(timer); b.classList.remove('arm'); b.textContent = label;
        onFire(b);
        return;
      }
      armedAt = Date.now();
      b.classList.add('arm');
      b.textContent = armLabel;
      timer = setTimeout(function () { armedAt = 0; b.classList.remove('arm'); b.textContent = label; }, 4000);
    });
    return b;
  }

  // ---------------------------------------------------------------- time
  const TZ = 'Asia/Jerusalem';
  function ms(iso) { const v = Date.parse(iso || ''); return isNaN(v) ? null : v; }
  function ilDay(v) { return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(v)); }
  function fmtDate(iso, withTime) {
    const v = ms(iso);
    if (v === null) return '—';
    const o = { timeZone: TZ, day: 'numeric', month: 'numeric', year: '2-digit' };
    if (withTime) { o.hour = '2-digit'; o.minute = '2-digit'; }
    return new Intl.DateTimeFormat(LANG === 'en' ? 'en-GB' : 'he-IL', o).format(new Date(v));
  }
  function dur(msec) {
    const m = Math.max(0, Math.round(msec / 60000));
    if (LANG === 'en') {
      if (m < 60) return m + ' min';
      if (m < 48 * 60) return Math.round(m / 60) + ' h';
      return Math.round(m / 1440) + ' days';
    }
    if (m < 60) return m + ' דק׳';
    if (m < 48 * 60) return Math.round(m / 60) + ' ש׳';
    return Math.round(m / 1440) + ' ימים';
  }
  function ago(iso) {
    const v = ms(iso);
    if (v === null) return '';
    const rtf = new Intl.RelativeTimeFormat(LANG === 'en' ? 'en' : 'he', { numeric: 'auto', style: 'short' });
    const s = (v - Date.now()) / 1000;
    const a = Math.abs(s);
    if (a < 60) return rtf.format(0, 'minute');
    if (a < 3600) return rtf.format(Math.round(s / 60), 'minute');
    if (a < 172800) return rtf.format(Math.round(s / 3600), 'hour');
    return rtf.format(Math.round(s / 86400), 'day');
  }

  // ---------------------------------------------------------------- api
  let PENDING = 0;
  /*
   * Deploy resilience (2026-10-05, measured in Render's logs): the service has a persistent disk, so a deploy is
   * a short outage. Render answers it with its own 502/503 HTML page, or the connection drops. That is "the server
   * is restarting", not "the server answered badly".
   *  - READS retry with backoff (1, 2, 4, 8, 15, 15 s ≈ 45 s) behind a small "Reconnecting…" pill, and only then say so.
   *  - WRITES are never retried: the request may have landed just before the restart. The agent is told to refresh
   *    and check, never "invalid answer".
   *  - Our OWN JSON answers (also 502/504, e.g. engine_timeout) are real answers and pass straight through.
   */
  const READ_FNS = ['list', 'changes', 'watch', 'ticket', 'prefetch', 'result', 'related', 'queue', 'translate', 'translate-rows', 'translate-autoreply', 'translate-out',
    'assistant', 'apiBoot', 'apiStatus', 'apiTicket', 'apiTicketExtras', 'apiTickets', 'apiSearch', 'apiAutoReplyList', 'apiAutoCancelList', 'apiTemplates'];
  const RETRY_MS = [1000, 2000, 4000, 8000, 15000, 15000];
  function isRead(path, method, body) {
    if ((method || 'POST') === 'GET') return true;
    const m = /^\/api\/[^/]+\/([A-Za-z-]+)$/.exec(path);
    if (!m) return false;
    if (m[1] === 'apiSettings') return !!(body && body.args && body.args.action === 'get');
    return READ_FNS.indexOf(m[1]) >= 0;
  }
  let RECONNECTING = 0;
  function paintReconnect() {
    let el = document.getElementById('reconnect');
    if (!el) {
      el = h('div', { id: 'reconnect', class: 'reconnect', role: 'status', 'aria-live': 'polite', 'data-test': 'reconnecting', hidden: true },
        h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', t('reconnecting'));
      document.body.append(el);
    }
    el.hidden = RECONNECTING <= 0;
  }
  function sleep(ms) { return new Promise(function (res) { setTimeout(res, ms); }); }
  /** One HTTP round trip: {kind: 'json'|'transient'|'auth', data}. */
  async function once(path, opt) {
    let r;
    try { r = await fetch(path, opt); } catch (e) { return { kind: 'transient' }; }          // connection dropped mid-restart
    if (r.status === 401) return { kind: 'auth' };
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!data || typeof data !== 'object' || !('ok' in data)) return { kind: 'transient', status: r.status };   // Render's HTML page
    return { kind: 'json', data: data };
  }
  async function api(path, body, method, opts) {
    opts = opts || {};
    const opt = { method: method || 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': CSRF, Accept: 'application/json', 'X-UI-Lang': LANG } };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    const read = isRead(path, method, body);
    const retries = read && opts.retry !== false ? RETRY_MS : [];
    PENDING++;
    let shown = false;
    try {
      for (let i = 0; ; i++) {
        const res = await once(path, opt);
        if (res.kind === 'auth') { setTimeout(function () { location.href = BASE + '/login'; }, 600); return { ok: false, error: 'not_logged_in', msg: t('err_login') }; }
        if (res.kind === 'json') return res.data;
        if (!read) return { ok: false, error: 'server_restarted', msg: t('err_restart_write') };   // never re-send a write
        if (i >= retries.length) return { ok: false, error: 'server_restarting', msg: t('err_restarting'), quiet: !!opts.quiet };
        if (!opts.quiet && !shown) { shown = true; RECONNECTING++; paintReconnect(); }
        await sleep(retries[i]);
      }
    } finally {
      PENDING--;
      if (shown) { RECONNECTING--; paintReconnect(); }
    }
  }
  async function engine(fn, args, brand) {
    const b = brand || S.brand;
    const r = await api('/api/' + encodeURIComponent(b) + '/' + fn, { args: args || {}, lang: LANG });
    if (r && r.refresh) afterUnknownWrite(b, args && args.id, r.msg);       // QA round 4: the write may have run
    return r;
  }
  /** A write whose reply was lost: re-read the ticket from the engine and say so at the top of it. */
  function afterUnknownWrite(brand, id, msg) {
    setTimeout(async function () {
      if (brand !== S.brand) return;
      pollChanges(brand);
      if (id && S.tk && S.tk.id === id) {
        await openTicket(id, { fresh: true, showMemo: true });   // the copy stays on screen (with its lock) meanwhile
        const slot = document.getElementById('tk-stale');
        if (slot && S.tk && S.tk.id === id) {
          clear(slot);
          slot.append(h('div', { class: 'stale', role: 'status', 'data-test': 'write-unknown' }, h('span', { text: msg || t('err_bad_engine') })));
        }
      }
    }, 800);
  }

  // ---------------------------------------------------------------- state
  const S = {
    me: null, brand: null, view: 'list', tab: 'ready', ticketId: null,
    boots: {}, bootErr: {}, ar: {}, rowTr: {}, tkMemo: {}, prefetchedAt: {}, assist: {}, auto: {}, autoEdits: {}, autoMsg: {}, settings: {}, listSig: '', tk: null, search: { q: '', res: null, err: null, seq: 0 }, menuOpen: false
  };
  const OPEN = ['ready', 'action', 'health', 'delay'];
  const TABS = ['ready', 'action', 'failed', 'wa24', 'autoreply', 'auto', 'health', 'delay', 'bot', 'sent', 'today', 'search'];
  // Owner, 2026-10-07: new / needs decision / health / delay are ONE list ("ready" = every open ticket); what a ticket is shows as a label on its
  // row, never as a filter that hides tickets. Their old links still open the one list.
  const MERGED = ['action', 'health', 'delay'];
  const brandName = function (b) { const bt = S.boots[b]; return (bt && bt.brandName) || (b.charAt(0).toUpperCase() + b.slice(1)); };
  const boot = function () { return S.boots[S.brand] || null; };
  /** apiBoot.subscriptions === 'none' (e.g. selera): no subscriptions panel, no auto-cancel queue. */
  function noSubs(brand) { const b = S.boots[brand || S.brand]; return !!(b && String(b.subscriptions || '').toLowerCase() === 'none'); }
  function connected(brand) { const c = S.me.brands.filter(function (x) { return x.id === (brand || S.brand); })[0]; return !!(c && c.connected); }

  // ---------------------------------------------------------------- routing
  function parseHash() {
    const p = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
    if (p[0] === 'users') return { view: 'users' };
    if (p[0] === 'dash') return { view: 'dash' };
    if (p[0] === 'settings') return { view: 'settings', brand: p[1] };
    if (p[0] === 'b' && p[1]) {
      if (p[2] === 't' && p[3]) return { view: 'ticket', brand: p[1], id: p[3] };
      return { view: 'list', brand: p[1], tab: TABS.indexOf(p[2]) >= 0 && MERGED.indexOf(p[2]) < 0 ? p[2] : 'ready' };
    }
    return { view: 'list' };
  }
  function go(hash, replace) {
    if (replace) history.replaceState(null, '', hash); else location.hash = hash;
    if (replace) route();
  }
  function listHash(tab) { return '#/b/' + encodeURIComponent(S.brand) + '/' + (tab || S.tab); }
  function ticketHash(id) { return '#/b/' + encodeURIComponent(S.brand) + '/t/' + encodeURIComponent(id); }

  function canWork() { return S.me && (S.me.engine_role === 'agent' || S.me.engine_role === 'admin'); }

  function route() {
    const r = parseHash();
    const myBrands = S.me.brands.map(function (b) { return b.id; });
    $('dash-pane').hidden = true;
    if (r.view === 'dash') {
      if (!S.me.can_manage_users) return go('#/', true);           // admin + user-manager only (the server says 403 too)
      S.view = 'dash';
      $('users-pane').hidden = true;
      $('settings-pane').hidden = true;
      document.body.className = 'view-dash';
      renderTop(); renderBanners(); Dash.show(); Assist.sync();
      return;
    }
    if (r.view === 'users') {
      if (!S.me.can_manage_users) return go('#/', true);
      S.view = 'users';
      $('settings-pane').hidden = true;
      document.body.className = 'view-users';
      renderTop(); renderBanners(); Users.show(); Assist.sync();
      return;
    }
    $('users-pane').hidden = true;
    $('settings-pane').hidden = true;
    if (r.view === 'settings') {
      if (!S.me.is_admin) return go('#/', true);
      const sb = r.brand && myBrands.indexOf(r.brand) >= 0 ? r.brand : (S.brand || myBrands[0]);
      if (!sb) return go('#/', true);
      S.brand = sb; S.view = 'settings';
      document.body.className = 'view-settings';
      renderTop(); renderBanners(); Settings.show(); Assist.sync();
      return;
    }
    if (!canWork()) {                       // a pure user-manager has no ticket access
      if (S.me.can_manage_users) return go('#/users', true);
    }
    let brand = r.brand && myBrands.indexOf(r.brand) >= 0 ? r.brand : null;
    if (!brand) brand = (localStorage.getItem('cs.brand') && myBrands.indexOf(localStorage.getItem('cs.brand')) >= 0) ? localStorage.getItem('cs.brand') : myBrands[0];
    if (!brand) { S.brand = null; renderTop(); renderNoBrand(); return; }
    if (brand !== r.brand) return go('#/b/' + encodeURIComponent(brand) + '/' + (r.tab || 'ready'), true);
    const brandChanged = brand !== S.brand;
    S.brand = brand;
    localStorage.setItem('cs.brand', brand);
    if (r.view === 'ticket') {
      S.view = 'ticket';
      if (S.ticketId !== r.id || brandChanged) openTicket(r.id);
      S.ticketId = r.id;
    } else {
      S.view = 'list';
      S.tab = r.tab || 'ready';
      setTimeout(function () { prefetchTab(S.brand); }, 0);
      if (window.matchMedia('(max-width: 999px)').matches) { S.ticketId = null; S.tk = null; }
    }
    document.body.className = S.view === 'ticket' ? 'view-ticket' : 'view-list';
    renderTop(); renderBanners(); renderTabs(); renderList(true);
    if (S.view !== 'ticket' && !S.ticketId) renderTicketPlaceholder();
    if (brandChanged || !S.boots[brand]) loadBoot(brand);
    Assist.sync();
  }

  // ---------------------------------------------------------------- top / banners / tabs
  function renderTop() {
    const top = $('top');
    clear(top);
    top.append(h('span', { class: 'title', text: t('app') }));
    const brands = S.me.brands;
    if (S.me.can_manage_users && S.view !== 'dash') top.append(h('a', { class: 'dash-link', href: '#/dash', 'data-test': 'dash-link', text: '📊 ' + (LANG === 'en' ? 'Managers' : 'לוח מנהלים') }));
    if (brands.length > 1 && S.view !== 'users' && S.view !== 'dash') {
      const sel = h('select', { class: 'brand', 'aria-label': 'brand' });
      brands.forEach(function (b) {
        sel.append(h('option', { value: b.id, text: brandName(b.id) + (b.connected ? '' : ' ·'), selected: b.id === S.brand ? 'selected' : null }));
      });
      sel.value = S.brand || '';
      sel.addEventListener('change', function () {
        S.ticketId = null; S.tk = null;
        go(S.view === 'settings' ? '#/settings/' + encodeURIComponent(sel.value) : '#/b/' + encodeURIComponent(sel.value) + '/ready');
      });
      top.append(sel);
    } else if (brands.length === 1 && S.view !== 'users' && S.view !== 'dash') {
      top.append(h('span', { class: 'who', text: brandName(brands[0].id) }));
    }
    top.append(h('a', { class: 'dash-link', href: '/cs/en' + location.hash, 'data-test': 'english-workspace', text: 'English desk', 'aria-current': LANG === 'en' ? 'page' : null }));
    top.append(h('span', { class: 'spacer' }));
    const pend = Outbox.pending();
    if (pend.length) {
      const ob = h('button', { class: 'ob-btn' + (pend.some(function (i) { return i.state !== 'flight' && i.state !== 'checking' && i.state !== 'retry'; }) ? ' warn' : ''), type: 'button', 'data-test': 'outbox-indicator' },
        tx('ob_header', { n: pend.length }));
      ob.addEventListener('click', function (e) { e.stopPropagation(); S.obOpen = !S.obOpen; renderTop(); });
      top.append(ob);
      if (S.obOpen) {
        const m = h('div', { class: 'menu ob-menu', 'data-test': 'outbox-menu' });
        pend.forEach(function (it) {
          m.append(h('a', { href: '#/b/' + encodeURIComponent(it.brand) + '/t/' + encodeURIComponent(it.id) },
            h('span', { class: 'chip ' + Outbox.cls(it), text: Outbox.label(it) }), ' ', h('bdi', { text: it.name })));
        });
        top.append(m);
      }
    }
    top.append(h('span', { class: 'who', text: S.me.user.display_name || S.me.user.username }));
    const mb = h('button', { class: 'menu-btn', type: 'button', text: '☰', 'aria-label': t('menu'), 'aria-expanded': S.menuOpen ? 'true' : 'false' });
    mb.addEventListener('click', function (e) { e.stopPropagation(); S.menuOpen = !S.menuOpen; renderTop(); });
    top.append(mb);
    if (S.menuOpen) {
      const m = h('div', { class: 'menu', role: 'menu' });
      if ((S.view === 'users' || S.view === 'dash') && canWork()) m.append(h('a', { href: '#/', text: t('to_tickets') }));
      if (S.me.can_manage_users && S.view !== 'users') m.append(h('a', { href: '#/users', text: t('users') }));
      if (S.me.is_admin && S.view !== 'settings' && S.brand) m.append(h('a', { href: '#/settings/' + encodeURIComponent(S.brand), text: t('settings') }));
      if (S.view === 'settings' && canWork()) m.append(h('a', { href: '#/', text: t('to_tickets') }));
      m.append(h('a', { href: '/cs/password', text: t('change_pw') }));
      m.append(h('a', { href: (LANG === 'en' ? '/cs' : '/cs/en') + location.hash, text: LANG === 'en' ? t('to_he') : t('to_en') }));
      const f = h('form', { method: 'post', action: '/cs/logout' }, h('input', { type: 'hidden', name: 'csrf', value: CSRF }),
        h('button', { type: 'submit', text: t('logout') }));
      m.append(f);
      top.append(m);
    }
  }
  document.addEventListener('click', function () { if (S.menuOpen || S.obOpen) { S.menuOpen = false; S.obOpen = false; renderTop(); } });

  function renderBanners() {
    const el = $('banners');
    clear(el);
    if (S.me.mock) el.append(h('p', { class: 'banner info', text: t('mock') }));
    (S.me.warnings || []).forEach(function (w) { el.append(h('p', { class: 'banner danger', text: t(w) })); });
    if (S.view === 'users') return;
    const b = boot();
    if (b) el.append(modeBanner(b));
    const age = listAge(S.brand);
    if (b && age !== null && age > 120) {
      el.append(h('div', { class: 'banner warn stale-list', role: 'status', 'data-test': 'list-stale' },
        h('span', null, tx('list_stale', { m: Math.floor(age / 60) })), ' ',
        h('button', { class: 'btn small', type: 'button', text: t('list_refresh'), onclick: function (e) { e.target.disabled = true; forceList(S.brand); } })));
    }
    if (b && b.cancelFrozen) el.append(h('p', { class: 'banner danger', text: t('frozen') }));
    AfterSend.list().forEach(function (n) {
      el.append(h('div', { class: 'banner warn after-send', role: 'alert', 'data-test': 'after-send', 'data-id': n.id },
        h('b', { text: t('afs_title', { name: n.name || '' }) + ' ' }),
        h('span', { text: (n.codes || []).map(function (c) { return t('afs_' + c); }).join(' ') }), ' ',
        h('a', { class: 'btn small', href: '#/b/' + encodeURIComponent(n.brand) + '/t/' + encodeURIComponent(n.id), text: t('afs_open') }), ' ',
        h('button', { class: 'btn small', type: 'button', 'data-test': 'after-send-done', text: t('afs_done'), onclick: function () { AfterSend.drop(n.brand, n.id); renderBanners(); } })));
    });
  }

  /** Owner, 2026-10-09: an agent's message is always sent; what it promised and the system could not do stays on screen as a reminder until
   *  the agent says it is handled. Kept on this device (it survives a reload); the ticket row carries the same reminder for everyone. */
  const AfterSend = (function () {
    const KEY = 'cs.after';
    function read() { try { const v = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
    function write(v) { try { localStorage.setItem(KEY, JSON.stringify(v.slice(-30))); } catch (e) { /* private mode: the row chip still shows it */ } }
    return {
      list: function () { return read(); },
      add: function (n) { const v = read().filter(function (x) { return !(x.brand === n.brand && x.id === n.id); }); v.push(n); write(v); },
      drop: function (brand, id) { write(read().filter(function (x) { return !(x.brand === brand && x.id === id); })); }
    };
  })();

  /** One colored strip everyone sees: test vs live, Kaching cancels, auto-cancel. Values read tolerantly. */
  function onOff(v) { return v === true || /^(on|true|1|yes)$/i.test(String(v)); }
  function autoMode() {
    // The AUTO_CANCEL switch comes with apiAutoCancelList (agents + admins); admins also have it from apiSettings.
    const a = S.auto[S.brand];
    const set = S.settings[S.brand] && S.settings[S.brand].values;
    let v = a && a.switch ? a.switch : (set ? set.AUTO_CANCEL : undefined);
    if (v === undefined || v === null || v === '') return null;
    v = String(v).toLowerCase();
    return v === 'true' ? 'on' : v === 'false' ? 'off' : v;
  }
  function modeBanner(b) {
    const live = !b.dryRun;
    const auto = autoMode();
    const p = h('div', { class: 'banner mode ' + (live ? 'live' : 'warn') + (auto === 'on' ? ' auto-on' : ''), 'data-test': live ? 'mode-live' : 'dry-run' },
      h('span', { class: 'mode-main', text: live ? t('mode_is_live') : t('dry_run') }));
    if (!noSubs()) p.append(h('span', { class: 'chip ' + (b.cancelEnabled ? 'bad' : ''), text: t('mode_kaching', { v: b.cancelEnabled ? t('val_on') : t('val_off') }) }));
    if (auto) p.append(h('span', { class: 'chip ' + (auto === 'on' ? 'bad' : auto === 'shadow' ? 'st-sent' : ''), text: t('mode_auto', { v: t('val_' + auto) }) }));
    const ar = S.ar[S.brand];
    const arv = ar && ar.switch ? String(ar.switch).toLowerCase() : (S.settings[S.brand] && S.settings[S.brand].values ? S.settings[S.brand].values.AUTO_REPLY : null);
    if (arv && ['on', 'off', 'shadow'].indexOf(arv) >= 0) p.append(h('span', { class: 'chip ' + (arv === 'on' ? 'bad' : arv === 'shadow' ? 'st-sent' : ''), text: t('mode_auto_reply', { v: t('val_' + arv) }) }));
    return p;
  }

  /** Seconds since the server last synced this brand's list with the engine (QA round 5: a 27-minute stale list). */
  const SYNC = {};
  function noteSync(brand, age) { if (typeof age === 'number') SYNC[brand] = { age: age, at: Date.now() }; }
  function listAge(brand) { const x = SYNC[brand]; return x ? x.age + (Date.now() - x.at) / 1000 : null; }
  async function forceList(brand) {
    const r = await api('/api/' + encodeURIComponent(brand) + '/list', { maxAge: 0 });
    if (r.ok && Array.isArray(r.tickets) && r.counts) { const cur = S.boots[brand]; S.boots[brand] = r; noteSync(brand, r.syncedAge || 0); if (cur) r._prev = null; }
    if (brand === S.brand) { renderBanners(); renderTabs(); renderList(true); }
  }

  function todayList(b) {
    const today = ilDay(Date.now());
    return (b.tickets || []).filter(function (x) {
      return (x.status === 'done' || x.status === 'sent') && ms(x.handled_at) !== null && ilDay(ms(x.handled_at)) === today;
    });
  }
  function tabCount(id, b) {
    if (!b) return '';
    if (id === 'today') return todayList(b).length;
    if (id === 'autoreply') { const a = S.ar[S.brand]; return a && a.items ? a.items.filter(function (x) { return x.review === 'pending'; }).length : ''; }
    if (id === 'auto') { const a = S.auto[S.brand]; return a && a.items ? a.items.filter(function (x) { return !AutoCancel.inFlight(x.state); }).length : ''; }
    if (id === 'search') return '';
    if (id === 'failed') return (b.tickets || []).filter(waFailActionable).length;
    if (id === 'wa24') return (b.tickets || []).filter(waWinClosed).length;
    if (id === 'ready') return (b.tickets || []).filter(function (x) { return OPEN.indexOf(x.status) >= 0; }).length;
    const rows = (b.tickets || []).filter(function (x) { return x.status === id; }).length;
    if (OPEN.indexOf(id) >= 0) return rows;               // apiBoot carries EVERY open ticket: the rows are the truth
    if (id === 'sent') {
      const sr = (b.tickets || []).filter(function (x) { return x.status === 'sent' || x.status === 'wa_queued'; }).length;
      return Math.max(sr, (Number((b.counts || {}).sent) || 0) + (Number((b.counts || {}).wa_queued) || 0));
    }
    return Math.max(rows, Number((b.counts || {})[id]) || 0);
  }
  function renderTabs() {
    const el = $('tabs');
    clear(el);
    const b = boot();
    if (!connected()) return;                       // nothing to list yet: no tabs, no counts
    TABS.forEach(function (id) {
      if (MERGED.indexOf(id) >= 0) return;               // part of the one open list
      if (id === 'auto' && (!b || noSubs())) return;     // unknown until apiBoot answers: hidden, not guessed
      if (id === 'autoreply' && (!S.ar[S.brand] || S.ar[S.brand].unavailable)) return;
      const n = tabCount(id, b);
      if (id === 'failed' && !n && S.tab !== 'failed') return;      // shown only while something failed
      if (id === 'wa24' && !n && S.tab !== 'wa24') return;          // shown only while a chat is past its 24 hours
      const a = h('a', { class: 'tab ' + id, href: listHash(id), role: 'tab', 'aria-selected': (S.view !== 'ticket' || window.innerWidth >= 1000) && S.tab === id ? 'true' : 'false' },
        t('tab_' + id), n !== '' ? h('span', { class: 'n', text: String(n) }) : null);
      el.append(a);
    });
  }

  function renderNoBrand() {
    document.body.className = 'view-list';
    clear($('tabs'));
    const lp = $('list-pane');
    clear(lp);
    lp.append(h('div', { class: 'empty' }, h('b', { text: t('no_brands') })));
  }

  // ---------------------------------------------------------------- boot + polling
  async function loadBoot(brand) {
    const conn = S.me.brands.filter(function (b) { return b.id === brand; })[0];
    if (conn && !conn.connected) { renderTabs(); renderList(true); return; }
    let r = await api('/api/' + encodeURIComponent(brand) + '/list', {});     // Render cache: instant when warm
    if (r.ok && (!Array.isArray(r.tickets) || !r.counts || typeof r.counts !== 'object')) {
      r = { ok: false, error: 'engine_bad_response', msg: t('err_bad_engine') };      // never render a list without its data
    }
    if (r.ok && canWork() && String(r.subscriptions || '').toLowerCase() !== 'none') loadAuto(brand);
    if (r.ok && canWork()) AutoReply.load(brand);
    if (r.ok) { S.boots[brand] = r; delete S.bootErr[brand]; noteSync(brand, r.syncedAge); }
    // QA 2026-10-06: after a quiet hour the cached list is old; the server refreshes it now — fetch that, don't wait 10 s
    if (r.ok && typeof r.syncedAge === 'number' && r.syncedAge > 30) setTimeout(function () { if (S.boots[brand] === r) pollChanges(brand); }, 1500);
    else if (!S.boots[brand]) { S.bootErr[brand] = r.msg || r.error; }               // keep the last good list on a bad reply
    if (brand !== S.brand) return;
    renderTop(); renderBanners(); renderTabs(); renderList(false); checkStale(); Draft.refreshSend(); EnDraft.refresh(); Assist.sync(); paintSubs(brand);
    prefetchTab(brand);
  }

  /** Warm the first 15 tickets of the visible tab on the server (it caps engine concurrency at 3). */
  function prefetchTab(brand) {
    if (!canWork() || brand !== S.brand || S.tab === 'search' || S.tab === 'auto' || S.tab === 'autoreply') return;
    const rows = (rowsFor(S.tab) || []).filter(function (x) { return !isOld(x); });
    const key = brand + '|' + S.tab;
    if (!rows.length || Date.now() - (S.prefetchedAt[key] || 0) < 60000) return;
    S.prefetchedAt[key] = Date.now();
    api('/api/' + encodeURIComponent(brand) + '/prefetch', { ids: rows.slice(0, 15).map(function (x) { return x.id; }) }, 'POST', { quiet: true });
  }

  /** DRY_RUN & co. change outside this tab (System Mode, or the engine directly): adopt them without a reload. */
  function mergeSwitches(brand, sw) {
    const b = S.boots[brand];
    if (!b || !sw || typeof sw !== 'object') return;
    let changed = false;
    ['dryRun', 'cancelEnabled', 'cancelFrozen', 'subscriptions'].forEach(function (k) {
      if (k in sw && sw[k] !== b[k]) { b[k] = sw[k]; changed = true; }
    });
    if (!changed || brand !== S.brand) return;
    renderBanners(); renderTabs(); Draft.refreshSend(); EnDraft.refresh(); paintSubs(brand);
  }
  async function refreshSwitches(brand) {
    const r = await api('/api/' + encodeURIComponent(brand) + '/list', { maxAge: 15 }, 'POST', { quiet: true });
    if (r.ok) mergeSwitches(brand, r);
  }

  /** Every 15 s: only what changed since our version, merged into the list in place (no full reload). */
  let polling = false;
  async function pollChanges(brand) {
    const b = S.boots[brand];
    if (!b) return loadBoot(brand);
    if (polling || !connected(brand)) return;
    polling = true;
    let r;
    // background: one quiet attempt per tick; on a restart keep the last good state and try again next tick
    try { r = await api('/api/' + encodeURIComponent(brand) + '/changes', { since: b.version }, 'POST', { retry: false, quiet: true }); } finally { polling = false; }
    if (r && typeof r.syncedAge === 'number') noteSync(brand, r.syncedAge);
    if (brand === S.brand) renderBanners();                               // the stale banner follows the real age
    if (!r.ok || S.boots[brand] !== b || !Array.isArray(b.tickets)) return;
    if (!Array.isArray(r.changed || [])) return;
    let touched = false;
    if (r.reset) {                                                   // the server's log does not reach back to our version
      const old = {};
      b.tickets.forEach(function (x) { old[x.id] = JSON.stringify(x); });
      r.changed.forEach(function (row) { if (row && row.id && old[row.id] !== JSON.stringify(row)) delete S.tkMemo[brand + '|' + row.id]; });
      b.tickets = r.changed.filter(function (row) { return row && row.id; }).map(function (row) { return Object.assign({}, row); });
      touched = true;
      r = Object.assign({}, r, { changed: [], removed: [] });
    }
    const byId = {};
    b.tickets.forEach(function (x, i) { byId[x.id] = i; });
    (r.changed || []).forEach(function (row) {
      if (!row || !row.id) return;
      touched = true;
      if (byId[row.id] !== undefined) b.tickets[byId[row.id]] = Object.assign({}, b.tickets[byId[row.id]], row);
      else { b.tickets.push(row); byId[row.id] = b.tickets.length - 1; }
      delete S.tkMemo[brand + '|' + row.id];                       // its full copy is now old
      if (S.tk && S.tk.brand === brand && S.tk.id === row.id) Watch.kick();   // the open chat: fetch it now, not in 5 s
    });
    if ((r.removed || []).length) { touched = true; b.tickets = b.tickets.filter(function (x) { return r.removed.indexOf(x.id) < 0; }); }
    if (r.counts && typeof r.counts === 'object') b.counts = r.counts;
    mergeSwitches(brand, r.switches);
    if (r.version !== undefined) b.version = r.version;
    if (r.serverTime) b.serverTime = r.serverTime;
    if (brand !== S.brand) return;
    renderTabs();
    renderList(false);                                              // signature-compared: zero DOM work when nothing changed
    if (touched) { checkStale(); prefetchTab(brand); }
  }

  // P0 speed (Owner, 2026-10-05): every 10 s. Cheap — the server shares one engine read per brand among all agents.
  setInterval(function () {
    if (document.hidden || !S.brand || S.view === 'users' || S.view === 'settings') return;
    pollChanges(S.brand);
  }, 10000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && S.brand && S.view !== 'users') {
      const b = boot();
      if (!b) loadBoot(S.brand); else pollChanges(S.brand);
    }
  });

  // ---------------------------------------------------------------- list
  const OLD_MS = 30 * 86400000;
  function waitedSince(x) { return ms(x.waiting_since) || ms(x.created_at) || 0; }
  function isOld(x) { const w = waitedSince(x); return !!w && Date.now() - w > OLD_MS; }
  function sortRows(rows, tab) {
    // newest first everywhere (live QA 2026-10-05: 80-day-old abandoned-cart chats sat at the top of "new")
    const key = function (x) {
      if (OPEN.indexOf(tab) >= 0 || tab === 'bot') return -waitedSince(x);
      return -(ms(x.handled_at) || ms(x.created_at) || 0);
    };
    // Owner, 2026-10-07: a WhatsApp chat whose 24 hours are about to end goes to the top (the one closing soonest first):
    // answered now it is a normal reply, an hour later it needs a template.
    const soon = function (x) { const w = OPEN.indexOf(tab) >= 0 ? waWin(x) : null; return w && w.state === 'soon' ? w.left : Infinity; };
    return rows.slice().sort(function (a, b) { const sa = soon(a), sb = soon(b); if (sa !== sb) return sa < sb ? -1 : 1; return key(a) - key(b); });
  }
  function byChannel(rows) {
    if (!rows || !S.chan || S.chan === 'all') return rows;
    return rows.filter(function (x) { return S.chan === 'whatsapp' ? isWA(x) : !isWA(x); });
  }
  function rowsFor(tab) {
    const b = boot();
    if (!b) return null;
    if (['ready', 'action', 'failed', 'wa24', 'health', 'delay', 'bot', 'sent', 'today'].indexOf(tab) >= 0) return byChannel(rowsForRaw(tab));
    return rowsForRaw(tab);
  }
  function rowsForRaw(tab) {
    const b = boot();
    if (!b) return null;
    if (tab === 'today') return sortRows(todayList(b), 'today');
    if (tab === 'failed') return sortRows((b.tickets || []).filter(waFailActionable), 'action');
    if (tab === 'wa24') return sortRows((b.tickets || []).filter(waWinClosed), 'action');
    if (tab === 'search') return S.search.res;
    if (tab === 'sent') return sortRows((b.tickets || []).filter(function (x) { return x.status === 'sent' || x.status === 'wa_queued'; }), 'sent');
    if (tab === 'autoreply') { const a = S.ar[S.brand]; return a ? (a.items || []) : null; }
    if (tab === 'auto') { const a = S.auto[S.brand]; return a ? (a.items || []) : null; }
    if (tab === 'ready') return sortRows((b.tickets || []).filter(function (x) { return OPEN.indexOf(x.status) >= 0; }), 'ready');
    return sortRows((b.tickets || []).filter(function (x) { return x.status === tab; }), tab);
  }

  function rowEl(x, opts) {
    opts = opts || {};
    const open = OPEN.indexOf(x.status) >= 0;
    let age = '';
    let old = false;
    if (open || x.status === 'bot') {
      const w = ms(x.waiting_since) || ms(x.created_at);
      if (w) { age = t('waiting', { d: dur(Date.now() - w) }); old = Date.now() - w > 24 * 3600000; }
    } else if (x.handled_at) {
      age = tx('handled_by', { who: x.handled_by || '—', when: ago(x.handled_at) });
    }
    const chips = [];
    chips.push(h('span', { class: 'chip st-' + x.status, 'data-test': 'row-status', 'data-status': x.status, text: label('st_', x.status, 'st_unknown') }));   // always: the one open list tells them apart by this label
    if (x.category) chips.push(h('span', { class: 'chip', text: label('cat_', x.category, 'cat_unknown') }));
    chips.unshift(chanPill(x));
    const winChip = waWinChip(x);
    if (winChip) chips.push(winChip);
    if (Number(x.emails_count) > 1) chips.push(h('span', { class: 'chip outline', text: t('msgs', { n: x.emails_count }) }));
    if (x.language && x.language !== 'he' && x.language !== 'iw') chips.push(h('span', { class: 'chip outline', text: String(x.language).toUpperCase() }));
    if (x.order_no) chips.push(h('span', { class: 'chip outline ltr', text: x.order_no }));
    if (x.cancelled) chips.push(h('span', { class: 'chip ok', text: t('cancelled_here') }));
    if (!open && /^\u26A0\uFE0F? ?ההודעה נשלחה/.test(String(x.action || ''))) chips.unshift(h('span', { class: 'chip bad', 'data-test': 'after-send-chip', text: t('afs_chip') }));
    if (Number(x.siblings) > 0) chips.push(h('span', { class: 'chip sib', text: t('siblings_short', { n: Number(x.siblings) }) }));
    if (isAutoReplied(x)) chips.unshift(h('span', { class: 'chip bot', text: t('ar_label'), 'data-test': 'bot-chip' }));
    if (waFail(x)) chips.unshift(waFailChip(x));
    const ob = Outbox.forTicket(S.brand, x.id);
    if (ob && (ob.state !== 'ok' || Date.now() - ob.at < 15 * 60000)) chips.unshift(h('span', { class: 'chip ' + Outbox.cls(ob), text: Outbox.label(ob), 'data-test': 'row-outbox', 'data-state': ob.state }));
    if (x.archived) chips.push(h('span', { class: 'chip', text: t('archived') }));
    const inner = [
      h('div', { class: 'l1' }, h('span', { class: 'name', dir: 'auto', text: x.name || x.email || x.phone || t('no_name') }),
        h('span', { class: 'age' + (old ? ' old' : '') }, age)),
      h('div', { class: 'sum', dir: 'auto', text: rowText(x, 'summary') || x.subject || '' }),
      x.recommendation ? h('div', { class: 'rec', dir: 'auto', 'data-test': 'row-rec' }, h('span', { class: 'rec-k', text: t('what_to_do') + ': ' }), rowText(x, 'recommendation')) : null,
      h('div', { class: 'chips' }, chips)
    ];
    const ch = isWA(x) ? ' wa' : ' email';
    if (x.archived || opts.static) return h('div', { class: 'row' + ch, 'data-id': x.id }, inner);
    return h('a', { class: 'row' + ch + (x.id === S.ticketId ? ' selected' : ''), href: ticketHash(x.id), 'data-id': x.id, 'data-w': String(waitedSince(x)) }, inner);
  }

  /** Handled by the engine's auto-reply. Tolerant: the engine's exact marker is not final (handled_by / a flag). */
  function isAutoReplied(x) {
    if (!x) return false;
    if (x.auto_reply === true || x.autoReplied === true || x.auto_replied === true) return true;
    if (/^(auto|auto[-_ ]?reply|autoreply|engine|bot)$/i.test(String(x.handled_by || ''))) return true;
    const a = S.ar[S.brand];
    return !!(a && a.items && a.items.some(function (it) { return it.id === x.id && it.state === 'sent'; }));
  }
  function rowText(x, f) {
    const tr = LANG === 'en' ? S.rowTr[S.brand + '|' + x.id] : null;
    return (tr && tr[f]) || x[f] || '';
  }
  /** English mode: summary + recommendation of the visible rows, translated server-side from the cached list. */
  let rowTrBusy = false;
  async function translateRows(rows) {
    if (LANG !== 'en' || rowTrBusy || !rows || !rows.length) return;
    const brand = S.brand;
    const ids = rows.filter(function (x) { return !S.rowTr[brand + '|' + x.id] && (x.summary || x.recommendation); }).slice(0, 40).map(function (x) { return x.id; });
    if (!ids.length) return;
    rowTrBusy = true;
    const r = await api('/api/' + encodeURIComponent(brand) + '/translate-rows', { ids: ids }, 'POST', { quiet: true });
    rowTrBusy = false;
    if (!r.ok) return;
    ids.forEach(function (i) { S.rowTr[brand + '|' + i] = (r.rows || {})[i] || { none: true }; });
    if (brand === S.brand) renderList(false);
  }

  function renderList(force) {
    const lp = $('list-pane');
    if (!S.brand) return;
    if (!connected()) {
      S.listSig = 'nc:' + S.brand;
      clear(lp);
      lp.append(h('div', { class: 'empty', 'data-test': 'not-connected' }, h('b', null, tx('not_connected', { b: brandName(S.brand) })), h('span', { text: t('not_connected_hint') })));
      return;
    }
    if (S.tab === 'auto' && noSubs()) { go(listHash('ready'), true); return; }
    const err = S.bootErr[S.brand];
    let rows = rowsFor(S.tab);
    const sig = JSON.stringify([S.brand, S.tab, S.ticketId, S.chan || 'all', S.search.note || '', err || '', S.tab === 'search' ? [S.search.q, S.search.err, S.search.res] : rows,
      S.tab === 'auto' ? [S.auto[S.brand], S.autoMsg] : null, Outbox.ver(), S.tab === 'autoreply' ? [S.ar[S.brand], S.autoMsg] : null, LANG === 'en' ? S.rowTr : null]);
    if (!force && sig === S.listSig) return;           // nothing changed: zero DOM work
    if (lp.contains(document.activeElement) && S.tab !== 'search' && !force) return;
    if (S.tab === 'auto' && !force && AutoCancel.busy()) return;     // never rebuild under an edited reply
    if (S.tab === 'autoreply' && !force && AutoReply.busy()) return;
    S.listSig = sig;

    let searchBox = lp.querySelector('.search-box');
    if (S.tab === 'search') {
      if (!searchBox) {
        clear(lp);
        const inp = h('input', { type: 'search', placeholder: t('search_ph'), 'aria-label': t('tab_search'), dir: 'auto', autocomplete: 'off', value: S.search.q });
        let deb = null;
        inp.addEventListener('input', function () { clearTimeout(deb); deb = setTimeout(function () { runSearch(inp.value); }, 400); });
        inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { clearTimeout(deb); runSearch(inp.value); } });
        searchBox = h('div', { class: 'search-box' }, inp);
        lp.append(searchBox, h('div', { class: 'results' }));
        setTimeout(function () { if (window.innerWidth >= 1000 || !S.search.q) inp.focus(); }, 0);
      }
      const res = lp.querySelector('.results');
      clear(res);
      if (err) res.append(h('div', { class: 'err-box', text: err }));
      else if (S.search.err) res.append(h('div', { class: 'err-box', text: S.search.err }));
      else if (S.search.res === null) res.append(h('div', { class: 'empty', text: S.search.q ? t('loading') : t('search_min') }));
      else if (!S.search.res.length) res.append(h('div', { class: 'empty' }, h('b', { text: t('search_none') })));
      else S.search.res.forEach(function (x) { res.append(rowEl(x, { showStatus: true })); });
      // after the chain, never inside it (QA round 5: a note placed in the if/else hid every result row)
      if (S.search.note && S.search.res && !S.search.err) res.prepend(h('div', { class: 'muted small search-note', 'data-test': 'search-note', text: S.search.note }));
      return;
    }
    if (S.tab === 'auto') { AutoCancel.render(lp, force); return; }
    if (S.tab === 'autoreply') { AutoReply.render(lp); return; }
    clear(lp);
    if (err) { lp.append(h('div', { class: 'err-box', text: err })); return; }
    if (rows === null) { for (let i = 0; i < 5; i++) lp.append(h('div', { class: 'skeleton' })); return; }
    const b = boot();
    lp.append(h('div', { class: 'list-meta' }, h('span', { text: brandName(S.brand) + ' · ' + t('tab_' + S.tab) }),
      h('span', { text: t('updated', { when: ago(b.serverTime) }) })));
    if ((b.tickets || []).some(isWA)) {
      const seg = h('div', { class: 'chan-filter', role: 'group', 'data-test': 'chan-filter' });
      [['all', t('chan_all'), null], ['email', t('ch_email'), 'mail'], ['whatsapp', t('ch_whatsapp'), 'wa']].forEach(function (c) {
        const on = (S.chan || 'all') === c[0];
        const b2 = h('button', { type: 'button', class: 'chan-btn ' + c[0] + (on ? ' on' : ''), 'aria-pressed': on ? 'true' : 'false' }, c[2] ? icon(c[2]) : null, c[1]);
        b2.addEventListener('click', function () { S.chan = c[0]; renderList(true); });
        seg.append(b2);
      });
      lp.append(seg);
    }
    if (!rows.length) {
      lp.append(h('div', { class: 'empty' }, h('b', { text: t('empty_' + S.tab) }), h('span', { text: t('empty_hint') })));
      return;
    }
    const work = OPEN.indexOf(S.tab) >= 0 || S.tab === 'bot';
    if (work) rows = rows.filter(function (x) { return !Outbox.hidesRow(S.brand, x.id); });              // closed in the background
    rows = rows.filter(function (x) { return Outbox.flagged(S.brand, x.id); }).concat(rows.filter(function (x) { return !Outbox.flagged(S.brand, x.id); }));   // needs a fix -> top
    const fresh = work ? rows.filter(function (x) { return !isOld(x); }) : rows;
    const old = work ? rows.filter(isOld) : [];
    fresh.forEach(function (x) { lp.append(rowEl(x)); });
    if (old.length) {
      S.oldOpen = S.oldOpen || {};
      const det = h('details', { class: 'old-section', open: !!S.oldOpen[S.brand + '|' + S.tab], 'data-test': 'old-section' },
        h('summary', null, t('old_section'), h('span', { class: 'n', text: String(old.length) })));
      det.addEventListener('toggle', function () { S.oldOpen[S.brand + '|' + S.tab] = det.open; });
      old.forEach(function (x) { det.append(rowEl(x)); });
      lp.append(det);
    }
    translateRows(rows);
  }

  async function runSearch(q) {
    q = String(q || '').trim();
    S.search.q = q;
    const seq = ++S.search.seq;
    if (q.length < 2) { S.search.res = null; S.search.err = null; renderList(true); return; }
    // QA round 5: the engine search took 35-62 s. Rows already on the screen answer at once; the engine adds the archive.
    const ql = q.toLowerCase();
    const local = ((boot() || {}).tickets || []).filter(function (x) {
      return [x.id, x.name, x.email, x.phone, x.order_no, x.subject, x.summary].some(function (v) { return v && String(v).toLowerCase().indexOf(ql) >= 0; });
    }).slice(0, 50);
    S.search.res = local; S.search.err = null; S.search.note = t('search_local'); renderList(true);
    const r = await engine('apiSearch', { q: q });
    if (seq !== S.search.seq) return;            // an older answer must not overwrite a newer query
    if (r.ok && Array.isArray(r.tickets)) {
      const seen = {};
      S.search.res = r.tickets.concat(local).filter(function (x) { if (!x || seen[x.id]) return false; seen[x.id] = 1; return true; });
      S.search.note = null;
    } else S.search.note = t('search_engine_failed');
    renderList(true);
  }

  // ---------------------------------------------------------------- ticket
  function renderTicketPlaceholder() {
    const tp = $('ticket-pane');
    clear(tp);
    tp.append(h('div', { class: 'placeholder', text: t('pick_ticket') }));
  }

  function markSelected(id) {
    const lp = $('list-pane');
    lp.querySelectorAll('a.row.selected').forEach(function (a) { a.classList.remove('selected'); });
    const el = lp.querySelector('a.row[data-id="' + CSS.escape(String(id)) + '"]');
    if (el) el.classList.add('selected');
  }
  function tkSig(tk, ex) { return JSON.stringify([tk || null, ex || null]); }
  function userBusyInTicket() {
    const a = document.activeElement;
    const typing = a && $('ticket-pane').contains(a) && /^(TEXTAREA|INPUT|SELECT)$/.test(a.tagName);
    return typing || Draft.isDirty() || EnDraft.busy() || $('cancel-dlg').open || $('confirm-dlg').open;
  }
  function paintSync() {
    const el = document.getElementById('tk-sync');
    const k = S.tk;
    if (!el || !k) return;
    clear(el);
    el.hidden = !(k.syncing || k.syncErr || k.pending);
    el.className = 'chip sync ' + (k.syncErr ? 'bad' : k.pending ? 'st-sent' : 'outline');
    if (k.syncing) el.append(h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', t('syncing'));
    else if (k.pending) {
      el.append(t('tk_updated') + ' · ');
      el.append(h('button', { class: 'more-btn', type: 'button', text: t('apply_update'), onclick: function () { applyTicket(S.tk, S.tk.pending, true); } }));
    } else if (k.syncErr) el.append(tx('sync_failed', { m: k.syncErr, when: ago(k.cachedAt) }));
  }
  /** Put a ticket copy on screen. Never under the agent's fingers: if they are typing, offer it instead. */
  function applyTicket(k, r, force) {
    if (S.tk !== k) return;
    const sig = tkSig(r.ticket, r.extras);
    k.pending = null;
    if (k.ticket && sig === k.sig) { paintSync(); return; }
    if (k.ticket && !force && userBusyInTicket()) { k.pending = r; paintSync(); return; }
    const pane = $('ticket-pane');
    const sy = window.scrollY;
    const ps = pane.scrollTop;
    const first = !k.ticket;
    k.tr = null; k.trRequest = (k.trRequest || 0) + 1;
    k.ticket = r.ticket; k.extras = r.extras || {}; k.extrasErr = r.extrasErr || null; k.sig = sig;
    k.cachedAt = r.cache && r.cache.hit ? new Date(Date.now() - (r.cache.age_s || 0) * 1000).toISOString() : new Date().toISOString();
    S.tkMemo[k.brand + '|' + k.id] = { ticket: k.ticket, extras: k.extras, extrasErr: k.extrasErr, sig: sig, cachedAt: k.cachedAt };
    if (!first) Draft.detach();
    renderTicket();
    if (!first) { window.scrollTo(0, sy); pane.scrollTop = ps; }
    if (first || k.related === null) loadRelated();
  }
  async function openTicket(id, opts) {
    opts = opts || {};
    S.ticketId = id;
    const brand = S.brand;
    Draft.detach();
    const k = { id: id, brand: brand, related: null, syncing: true };
    S.tk = k;
    const tp = $('ticket-pane');
    const memo = S.tkMemo[brand + '|' + id];
    if (memo && (!opts.fresh || opts.showMemo)) applyTicket(k, { ticket: memo.ticket, extras: memo.extras, extrasErr: memo.extrasErr, cache: { hit: true, age_s: (Date.now() - ms(memo.cachedAt)) / 1000 } });
    else renderPartial(brand, id, t('tk_partial'));
    markSelected(id);                                    // move the highlight only — no list rebuild on every open
    const t0 = performance.now();
    refreshSwitches(brand);                            // test mode / cancels no older than 15 s on every open
    let r = await api('/api/' + encodeURIComponent(brand) + '/ticket', opts.fresh ? { id: id, fresh: true, open: true } : { id: id, open: true });
    // QA round 5: the engine was slow (33-43 s) or answered badly ~1 in 3 at peak. Never an error first: the list row
    // is on screen at once, the server keeps fetching (capped 15 s wait) and a quick retry usually hits its cache.
    for (let tries = 0; !k.ticket && S.tk === k && !r.ok && (r.error === 'engine_slow' || r.error === 'engine_bad_response' || r.error === 'engine_timeout' || r.error === 'busy') && tries < (r.error === 'engine_slow' ? 3 : 1); tries++) {
      renderPartial(brand, id, t('tk_slow'));
      await new Promise(function (res) { setTimeout(res, 2500); });
      if (S.tk !== k) return;
      r = await api('/api/' + encodeURIComponent(brand) + '/ticket', { id: id, open: true });
    }
    if (S.tk !== k) return;
    k.firstPaintMs = Math.round(performance.now() - t0);
    if (!r.ok) {
      k.syncing = false;
      if (!k.ticket) { renderPartial(brand, id, null, t('tk_failed')); return; }
      k.syncErr = r.msg || r.error; paintSync(); return;
    }
    if (!r.ticket || typeof r.ticket !== 'object') {
      k.syncing = false;
      if (!k.ticket) { clear(tp); tp.append(h('div', { class: 'tk-body' }, backBtn(), h('div', { class: 'err-box', text: t('err_bad_engine') }))); return; }
      k.syncErr = t('err_bad_engine'); paintSync(); return;
    }
    const hit = !!(r.cache && r.cache.hit);
    // a copy the engine vouched for within seconds (read itself, or untouched by the shared change feed) needs no
    // second round-trip: it IS the fresh copy (P0 speed, the owner 2026-10-05)
    const confirmed = !!(r.cache && r.cache.confirmed && !r.cache.stale);
    // the send guards (WhatsApp lock, outbox decisions) trust only an engine read or a vouch <= 12 s old; an older
    // confirmed copy is shown at once and the immediate check below settles them
    if (!hit || guardFresh(r)) { delete WA_LOCK[brand + '|' + id]; Outbox.reconcile(brand, id, r.ticket); }
    k.syncing = hit && !confirmed;                     // an unconfirmed cache hit is shown now and revalidated right after
    k.srvAt = r.cache && typeof r.cache.at === 'number' ? r.cache.at : 0;
    applyTicket(k, r, !memo || !!opts.showMemo);
    Draft.refreshSend();
    paintSync();
    prefetchNext(brand, id);
    if (!k.syncing) { if (hit && !guardFresh(r)) Watch.kick(true); return; }   // checked at once, in the background
    const f = await api('/api/' + encodeURIComponent(brand) + '/ticket', { id: id, revalidate: true, open: true }, 'POST', { quiet: true });
    if (S.tk !== k) return;
    k.syncing = false;
    if (!f.ok) { k.syncErr = f.msg || f.error; paintSync(); return; }
    if (!f.ticket || typeof f.ticket !== 'object') { k.syncErr = t('err_bad_engine'); paintSync(); return; }
    k.syncErr = null;
    delete WA_LOCK[brand + '|' + id];                  // the engine just told us the real state
    Outbox.reconcile(brand, id, f.ticket);
    if (f.cache && typeof f.cache.at === 'number') k.srvAt = f.cache.at;
    liveUpdate(k, f);
    Draft.refreshSend();
    paintSync();
  }
  /** "send → next" lands on a warm ticket: the next 5 of this tab are read on the server at background priority, and the
   *  next 3 copied into this page's memory a moment later (cache only — never an engine call from here). */
  function prefetchNext(brand, id) {
    if (!canWork() || brand !== S.brand) return;
    const tab = ['ready', 'action', 'failed', 'wa24', 'health', 'delay', 'bot'].indexOf(S.tab) >= 0 ? S.tab : null;
    if (!tab) return;
    const rows = (rowsFor(tab) || []).filter(function (x) { return !isOld(x) && !Outbox.hidesRow(brand, x.id); });
    const pos = rows.map(function (x) { return x.id; }).indexOf(id);
    const ids = rows.slice(pos + 1, pos + 6).map(function (x) { return x.id; }).filter(function (x) { return x !== id; });
    if (!ids.length) return;
    api('/api/' + encodeURIComponent(brand) + '/prefetch', { ids: ids }, 'POST', { quiet: true });
    setTimeout(function () {
      ids.slice(0, 3).forEach(async function (nid) {
        if (S.tkMemo[brand + '|' + nid]) return;
        const r = await api('/api/' + encodeURIComponent(brand) + '/ticket', { id: nid, peek: true }, 'POST', { retry: false, quiet: true });
        if (!r || !r.ok || !r.ticket || typeof r.ticket !== 'object' || S.tkMemo[brand + '|' + nid]) return;
        S.tkMemo[brand + '|' + nid] = { ticket: r.ticket, extras: r.extras || {}, extrasErr: r.extrasErr || null, sig: tkSig(r.ticket, r.extras),
          cachedAt: new Date(Date.now() - ((r.cache && r.cache.age_s) || 0) * 1000).toISOString() };
      });
    }, 2500);
  }

  function guardFresh(r) { return !!(r && r.cache && typeof r.cache.vouched_s === 'number' && r.cache.vouched_s <= 12); }
  function msgKey(m) { return [m && m.who, m && m.at, String((m && m.text) || '').slice(0, 120)].join('|'); }
  /** A newer copy of the OPEN ticket (watch / revalidate). Never under the agent's fingers:
   *  - idle  -> the whole ticket is redrawn in place (scroll kept);
   *  - typing in, or an edited draft -> only the conversation is replaced; the draft is never touched — a new engine
   *    draft is OFFERED next to it;
   *  - a dialog / the English editor busy -> the old "newer version · show" chip.
   *  Customer messages that were not on screen are announced: "התקבלה הודעה חדשה". */
  function liveUpdate(k, r) {
    if (S.tk !== k || !r || !r.ticket || typeof r.ticket !== 'object') return;
    if (r.cache && typeof r.cache.at === 'number') k.srvAt = Math.max(k.srvAt || 0, r.cache.at);
    const had = {};
    ((k.extras && k.extras.conversation) || []).forEach(function (m) { had[msgKey(m)] = 1; });
    const fresh = k.ticket ? ((r.extras && r.extras.conversation) || []).filter(function (m) { return m && m.who !== 'us' && !had[msgKey(m)]; }) : [];
    if (k.ticket && tkSig(r.ticket, r.extras) === k.sig) { k.pending = null; paintSync(); return; }
    const a = document.activeElement;
    const typing = a && $('ticket-pane').contains(a) && /^(TEXTAREA|INPUT|SELECT)$/.test(a.tagName);
    const touched = typing || Draft.isDirty() || Draft.edited() || EnDraft.busy();
    const hard = $('cancel-dlg').open || $('confirm-dlg').open;
    if (fresh.length) k.live = (k.live || []).concat(fresh);
    if (!k.ticket || hard) { applyTicket(k, r, !k.ticket); paintLive(k); return; }
    if (!touched) { applyTicket(k, r, true); paintLive(k); return; }
    // the agent is working in this ticket: swap the conversation only, keep the draft and the caret where they are
    const pane = $('ticket-pane');
    const old = document.getElementById('tk-conv');
    const anchor = typing ? a : old;
    const y0 = anchor ? anchor.getBoundingClientRect().top : 0;
    const prevDraft = String((k.ticket && k.ticket.draft_text) || '');
    k.ticket = r.ticket; k.extras = r.extras || {}; k.extrasErr = r.extrasErr || null; k.sig = tkSig(r.ticket, r.extras); k.pending = null;
    k.tr = null; k.trRequest = (k.trRequest || 0) + 1;
    k.cachedAt = new Date().toISOString();
    S.tkMemo[k.brand + '|' + k.id] = { ticket: k.ticket, extras: k.extras, extrasErr: k.extrasErr, sig: k.sig, cachedAt: k.cachedAt };
    if (old) {
      const cc = convCard(k.extras.conversation || []);
      cc.id = 'tk-conv';
      if (isWA(k.ticket)) cc.classList.add('wa');
      old.replaceWith(cc);
    }
    const nd = String(r.ticket.draft_text || '');
    if (nd !== prevDraft && !enMode(k.ticket)) Draft.offer(nd);
    Draft.refreshSend();
    if (enMode(k.ticket)) Translate.load(k);
    if (anchor && anchor.isConnected) {
      const d = anchor.getBoundingClientRect().top - y0;
      if (d) { if (pane.scrollHeight > pane.clientHeight) pane.scrollTop += d; else window.scrollBy(0, d); }
    }
    paintLive(k);
    paintSync();
  }
  function paintLive(k) {
    const el = document.getElementById('tk-live');
    if (!el || S.tk !== k) return;
    clear(el);
    const ms_ = k.live || [];
    el.hidden = !ms_.length;
    if (!ms_.length) return;
    const last = ms_[ms_.length - 1];
    el.append(h('div', { class: 'live-head' }, h('b', { text: ms_.length > 1 ? t('live_new_msgs', { n: ms_.length }) : t('live_new_msg') }),
      h('button', { class: 'btn small ghost', type: 'button', text: t('live_ok'), onclick: function () { k.live = []; paintLive(k); } })));
    let preview = String(last.text || '').slice(0, 400);
    if (enMode(k.ticket)) {
      const index = ((k.extras && k.extras.conversation) || []).findIndex(function (m) { return msgKey(m) === msgKey(last); });
      const translated = ((k.tr && k.tr.conversation) || []).find(function (m) { return Number(m.i) === index; });
      preview = translated ? String(translated.text || '').slice(0, 400) : t('tr_loading');
      if (k.tr && k.tr.err) preview = t('tr_failed', { m: k.tr.err });
    }
    el.append(h('div', { class: 'live-text', dir: 'auto', text: preview }));
  }

  /** The open ticket, every 5 s: cheap on the server (it rides the brand's shared change feed). */
  const Watch = (function () {
    let busy = false;
    /** "מתעדכן…" — small, never blocking (send stays as it is), only while a check of the open chat runs. Periodic
     *  ticks show it only if they take longer than 0.8 s, so a quick check never flickers. */
    function mark(k, on) {
      const el = document.getElementById('tk-check');
      if (el && S.tk === k) el.hidden = !on;
    }
    async function tick(now) {
      const k = S.tk;
      if (busy || !k || !k.ticket || k.syncing || document.hidden || S.view !== 'ticket' || !canWork()) return;
      busy = true;
      const shown = setTimeout(function () { mark(k, true); }, now ? 0 : 800);
      let r;
      try { r = await api('/api/' + encodeURIComponent(k.brand) + '/watch', { id: k.id, at: k.srvAt || 0 }, 'POST', { retry: false, quiet: true }); }
      finally { busy = false; clearTimeout(shown); mark(k, false); }
      if (S.tk !== k || !r || !r.ok) return;
      if (typeof r.syncedAge === 'number') noteSync(k.brand, r.syncedAge);
      if (r.changed && r.ticket) liveUpdate(k, r);
      if (S.tk === k && guardFresh(r)) {             // the engine just vouched for what is on screen: settle the guards
        delete WA_LOCK[k.brand + '|' + k.id];
        Outbox.reconcile(k.brand, k.id, k.ticket);
        Draft.refreshSend();
      }
    }
    setInterval(tick, 5000);
    return { kick: function (now) { setTimeout(function () { tick(now); }, 0); }, tick: tick };
  })();

  /** No full ticket yet: what the list already knows about it (read-only), and a note. Never an empty error box. */
  function renderPartial(brand, id, note, failed) {
    const tp = $('ticket-pane');
    const b = S.boots[brand];
    const row = b && (b.tickets || []).filter(function (x) { return x.id === id; })[0];
    clear(tp);
    const body = h('div', { class: 'tk-body', 'data-test': 'tk-partial' });
    if (row) {
      tp.append(h('div', { class: 'tk-head' }, h('div', { class: 'l1' }, backBtn(), h('h2', { dir: 'auto', text: row.name || row.email || t('no_name') }), statusChip(row.status)),
        h('div', { class: 'contact' }, chanPill(row), row.email ? h('span', { class: 'val', text: row.email }) : null),
        row.summary ? h('p', { class: 'summary-line', dir: 'auto', text: row.summary }) : null));
      if (row.recommendation) body.append(h('div', { class: 'todo' }, h('b', { text: t('what_to_do') }), h('div', { dir: 'auto', text: row.recommendation })));
    } else body.append(backBtn());
    if (note) body.append(h('div', { class: 'stale', role: 'status' }, h('span', { class: 'spinner' }), ' ', note));
    if (failed) body.append(h('div', { class: 'stale', role: 'status' }, h('span', { text: failed }), ' ',
      h('button', { class: 'btn small', type: 'button', text: t('tk_retry'), onclick: function () { openTicket(id); } })));
    if (!row) for (let i = 0; i < 2; i++) body.append(h('div', { class: 'skeleton' }));
    tp.append(body);
  }

  /** One ticket's panels after a write: from the server cache (already patched or revalidated), never a full pane rebuild. */
  async function fetchTicket(brand, id, revalidate) {
    return api('/api/' + encodeURIComponent(brand) + '/ticket', revalidate ? { id: id, revalidate: true } : { id: id });
  }

  function backBtn() {
    return h('button', { class: 'back-btn', type: 'button', text: (LANG === 'en' ? '← ' : '→ ') + t('back'), onclick: function () { go(listHash()); } });
  }

  /** engine field `siblings` = other OPEN tickets of the same customer. Absent -> nothing. Click -> search. */
  function siblingsChip(x) {
    const n = Number(x && x.siblings);
    if (!(n > 0)) return null;
    const q = String(x.email || x.phone || '').trim();
    const b = h('button', { class: 'chip sib big', type: 'button', 'data-test': 'siblings' }, n === 1 ? t('siblings_one') : t('siblings', { n: n }));
    b.addEventListener('click', function () {
      if (q.length < 2) return;
      S.search.q = q; S.search.res = null; S.listSig = '';
      go('#/b/' + encodeURIComponent(S.brand) + '/search');
      setTimeout(function () { const inp = $('list-pane').querySelector('.search-box input'); if (inp) inp.value = q; runSearch(q); }, 0);
    });
    return h('div', { class: 'sib-row' }, b);
  }
  function label(prefix, v, fallback) { const k = prefix + v; const x = t(k); return x === k ? t(fallback) : x; }
  function statusChip(st) { return h('span', { class: 'chip st-' + String(st || '').replace(/[^a-z_]/g, ''), text: label('st_', st, 'st_unknown') }); }

  const ACTION_HE = [
    [/^cancel: contract lookup failed/i, 'הלקוח מבקש לבטל מנוי, אבל בדיקת המנויים נכשלה — לבדוק בקצ׳ינג ידנית.'],
    [/^cancel: no active contract found/i, 'הלקוח מבקש לבטל מנוי, אבל לא נמצא מנוי פעיל במייל הזה — אולי מייל אחר.'],
    [/^cancel: /i, 'הלקוח מבקש לבטל מנוי — הביטול נעשה בכפתור בפאנל המנויים.'],
    [/^health/i, 'נושא בריאותי — תשובה של אדם בלבד.'],
    [/^delay/i, 'עיכוב אמיתי במשלוח.'],
    [/^whatsapp/i, 'הודעת וואטסאפ — בשלב הזה אין טיוטה אוטומטית.'],
    [/^engine error/i, 'שגיאת מערכת בעיבוד הפנייה — לטפל ידנית.'],
    [/^voc/i, 'תשובה לא ברורה לשאלת המחקר — אדם מחליט.'],
    [/^customer has \d+ open tickets/i, 'ללקוח יש כמה פניות פתוחות — לבדוק.'],
    [/^refund/i, 'בקשת החזר כספי — החזרים מתבצעים ידנית.'],
    [/draft blocked|draft problem|safety/i, null]       // the owner 2026-10-06: a content check never blocks a send — not shown at all
  ];
  function actionLines(action, hasDraft) {
    return String(action || '').split(' | ').filter(Boolean).filter(function (part) {
      return !/draft blocked|draft problem|safety/i.test(part);
    }).map(function (part) {
      // QA 2026-10-06: every open ticket has a draft now; "no automatic draft" next to one is wrong
      if (hasDraft && /^whatsapp/i.test(part) && LANG !== 'en') return { text: 'הודעת וואטסאפ — יש טיוטה למטה: לבדוק ולשלוח.', raw: part };
      let he = null;
      if (LANG !== 'en') for (let i = 0; i < ACTION_HE.length; i++) if (ACTION_HE[i][0].test(part)) { he = ACTION_HE[i][1]; break; }
      return { text: he || part, raw: part };
    });
  }

  function renderTicket() {
    const tp = $('ticket-pane');
    const k = S.tk;
    const x = k.ticket;
    const ex = k.extras || {};
    clear(tp);
    const isOpen = OPEN.indexOf(x.status) >= 0;

    const contact = h('div', { class: 'contact' });
    if (x.email) contact.append(h('span', { class: 'item' }, h('span', { class: 'val', text: x.email }), copyBtn(x.email)));
    if (x.phone) contact.append(h('span', { class: 'item' }, h('a', { class: 'val', href: 'tel:' + String(x.phone).replace(/[^\d+]/g, ''), text: x.phone }), copyBtn(x.phone)));
    contact.append(h('span', { class: 'item' }, chanPill(x)));
    const head = h('div', { class: 'tk-head' },
      h('div', { class: 'l1' }, backBtn(), h('h2', { dir: 'auto', text: x.name || x.email || x.phone || t('no_name') }),
        isAutoReplied(x) ? h('span', { class: 'chip bot', text: t('ar_label'), 'data-test': 'bot-chip' }) : null, statusChip(x.status), waFailChip(x), waWinChip(x)),
      h('div', { class: 'sync-row' }, h('span', { id: 'tk-sync', class: 'chip sync outline', hidden: true, 'aria-live': 'polite', 'data-test': 'tk-sync' }),
        h('span', { id: 'tk-check', class: 'tk-check', hidden: true, 'data-test': 'tk-check' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', t('checking'))),
      h('div', { class: 'ch-banner ' + (isWA(x) ? 'wa' : 'email'), 'data-test': isWA(x) ? 'wa-banner' : 'email-banner' },
        icon(isWA(x) ? 'wa' : 'mail'), t(isWA(x) ? 'wa_banner' : 'email_banner')),
      contact,
      siblingsChip(x),
      !isWA(x) && x.subject ? h('div', { class: 'summary-line', 'data-test': 'email-subject' },
        h('b', { text: enMode(x) ? 'Subject: ' : 'נושא: ' }),
        h('span', { id: 'tk-subject', dir: 'auto', text: x.subject }),
        h('span', { id: 'tk-subject-warning', class: 'chip bad', hidden: !enMode(x), role: 'status', text: 'Subject not translated yet — original shown' })) : null,
      x.summary ? h('p', { class: 'summary-line', id: 'tk-summary', dir: 'auto', text: x.summary }) : null);
    tp.append(head);

    const body = h('div', { class: 'tk-body' });
    tp.append(body);
    body.append(h('div', { id: 'tk-stale' }));
    body.append(h('div', { id: 'tk-outbox' }));
    body.append(h('div', { id: 'tk-live', class: 'live-note', role: 'status', 'aria-live': 'polite', 'data-test': 'tk-live', hidden: true }));
    const wf = waFail(x);
    if (wf) body.append(waFailBox(k, x, wf));
    if (x.status === 'wa_queued') body.append(h('div', { class: 'wa-note', role: 'status', 'data-test': 'wa-queued' },
      h('span', { class: 'chip ch-wa big', text: t('wa_queued_chip') })));
    if (x.recommendation) body.append(h('div', { class: 'todo', role: 'note', 'data-test': 'what-to-do' },
      h('b', { text: t('what_to_do') }), h('div', { id: 'tk-reco', dir: 'auto', text: x.recommendation })));
    const whyLines = isOpen && x.action ? actionLines(x.action, !!String(x.draft_text || '').trim()) : [];
    if (whyLines.length) {
      const lines = whyLines;
      body.append(h('div', { class: 'why' + (x.status === 'health' ? ' health' : ''), role: 'note', 'data-test': 'why-human' }, h('b', { text: t('why_human') }),
        lines.map(function (l) { return h('div', null, h('span', { text: l.text }), l.text !== l.raw ? h('div', null, h('bdi', { class: 'raw', text: l.raw })) : null); })));
    }
    const cc = convCard(ex.conversation || []);
    cc.id = 'tk-conv';
    if (isWA(x)) cc.classList.add('wa');
    body.append(cc);
    if (x.status === 'bot') {
      const tb = armed(t('takeover'), t('takeover_arm'), 'primary wa', async function (btn) {
        btn.disabled = true;
        const r = await engine('apiWaTakeOver', { id: x.id }, k.brand);
        if (!r.ok) { btn.disabled = false; body.insertBefore(h('div', { class: 'err-box', role: 'alert', text: r.msg || r.error }), body.children[1]); return; }
        toast(t('takeover_ok'));
        await afterAction();
      });
      tb.setAttribute('data-test', 'takeover');
      body.insertBefore(h('div', { class: 'bot-banner', role: 'note', 'data-test': 'bot-banner' }, h('div', null, t('bot_banner')), h('div', { class: 'actions' }, tb)),
        body.children[1] || null);
    }
    const dcard = x.status === 'bot' ? null : (enMode(x) && isOpen ? EnDraft.card(x) : Draft.card(x));
    if (dcard && x.recommendation && isOpen) {
      const h3 = dcard.querySelector('h3');
      h3.after(h('div', { class: 'todo-chip', 'data-test': 'what-to-do-chip' }, h('b', { text: t('what_to_do') + ': ' }), h('span', { class: 'tk-reco2', dir: 'auto', text: x.recommendation })));
    }
    if (dcard) body.append(dcard);
    body.append(ordersCard(ex, x));
    // Rendered only once apiBoot says the brand HAS subscriptions; a deep link can arrive first (paintSubs fills it later).
    const subsHidden = !!(ex.notes && ex.notes.subscriptions === 'brand_none');
    body.append(h('div', { id: 'subs-card' }, S.boots[k.brand] && !noSubs(k.brand) && !subsHidden ? subsCard(ex, x) : null));
    body.append(h('div', { id: 'notes-card' }, notesCard(x)));
    body.append(h('div', { id: 'related-card' }, relatedCard()));
    body.append(detailsCard(x));
    if (k.extrasErr) body.insertBefore(h('div', { class: 'err-box', text: k.extrasErr }), body.children[1]);
    Outbox.paintBanner();
    paintLive(k);
    if (enMode(x)) {
      if (k.tr && k.tr.ok) { Translate.paint(k); EnDraft.prefill(x.id, k.tr.draft); } else Translate.load(k);
    }
    paintSync();
  }

  /** The failed-send box at the top of the ticket. "שלח שוב" only for a plain failure (failed: open / chat / compose) —
   *  never for unknown (it may have gone out) or template_required (needs a template). Same text (wa_out), the normal
   *  outbox, a new rid; every guard of a first send applies (DRY_RUN, one open action, the WhatsApp lock). */
  function waFailBox(k, x, kind) {
    const box = h('div', { class: 'wa-fail-box', role: 'alert', 'data-test': 'wa-fail' },
      h('div', { text: kind === 'template_required' ? t('wa_fail_tpl_note') : kind === 'unknown' ? t('wa_fail_unknown_note') : t('wa_fail_note') }));
    const text = String(x.wa_out || '');
    if (kind !== 'failed' || String(x.wa_send || '').split(':')[0] !== 'failed' || !text.trim()) return box;
    const b0 = S.boots[k.brand];
    const btn = armed(t('wa_resend'), t('wa_resend_arm'), 'primary wa', function () {
      if (btn.disabled) return;
      if (Outbox.start('apiSend', k.brand, x, { id: x.id, text: text, channel: 'whatsapp' }, 'resend')) goNext(k.brand, x.id);
    });
    btn.setAttribute('data-test', 'wa-resend');
    btn.disabled = !b0 || !!b0.dryRun || Outbox.blocks(k.brand, x.id) || waLocked(k.brand, x.id) || waQueued(x);
    box.append(h('div', { class: 'actions' }, btn));
    return box;
  }

  function checkStale() {
    if (!S.tk || !S.tk.ticket || S.view === 'users') return;
    const b = boot();
    if (!b) return;
    const row = (b.tickets || []).filter(function (r) { return r.id === S.tk.id; })[0];
    const x = S.tk.ticket;
    const what = [];
    if (row) {
      if (String(row.emails_count) !== String(x.emails_count) || String(row.waiting_since) !== String(x.waiting_since)) what.push(t('stale_new'));
      if (row.status !== x.status) what.push(t('stale_status'));
    }
    const slot = document.getElementById('tk-stale');
    if (!slot) return;
    clear(slot);
    if (what.length) {
      slot.append(h('div', { class: 'stale', role: 'status' }, h('span', { text: t('stale', { what: what.join(', ') }) }),
        h('button', { class: 'btn small', type: 'button', text: t('refresh'), onclick: function () { Draft.flush(); openTicket(S.tk.id, { fresh: true }); } })));
    }
  }

  // ---- conversation
  const QUOTE_HEAD = /^(On .{4,200}wrote:|ב[-־]?.{4,200}כתב(?:\/ה|ה)?:|.{2,200}<[^>\s]+@[^>\s]+>\s*(?:wrote|כתב\S*):)\s*$/;
  function messageBody(text) {
    const lines = String(text || '').replace(/\r/g, '').split('\n');
    const out = [];
    let buf = [];
    let quote = null;
    function flushText() { if (buf.length) { out.push(h('div', { class: 'txt', dir: 'auto', text: buf.join('\n').replace(/^\n+|\n+$/g, '') })); buf = []; } }
    function flushQuote() { if (quote) { out.push(h('blockquote', { dir: 'auto' }, quote.cap ? h('span', { class: 'cap', text: quote.cap }) : null, quote.lines.join('\n'))); quote = null; } }
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      if (/^\s*>/.test(ln)) {
        if (!quote) { flushText(); quote = { cap: null, lines: [] }; }
        quote.lines.push(ln.replace(/^\s*>\s?/, ''));
        continue;
      }
      if (QUOTE_HEAD.test(ln.trim()) && i + 1 < lines.length && (/^\s*>/.test(lines[i + 1]) || lines[i + 1].trim() === '')) {
        flushText(); flushQuote();
        quote = { cap: ln.trim(), lines: [] };
        continue;
      }
      if (quote) flushQuote();
      buf.push(ln);
    }
    flushText(); flushQuote();
    return out;
  }
  /** WhatsApp photo slots {ref, file:{url}|null, unavailable?}. Never an <img> (Drive files are private; the CSP allows
   *  images only from this site): a stored file is a link, an unavailable one says where to look. */
  function photoChips(photos) {
    if (!Array.isArray(photos) || !photos.length) return null;
    const row = h('div', { class: 'photos' });
    photos.forEach(function (p) {
      if (!p || typeof p !== 'object') return;
      const url = p.file && safeUrl(p.file.url);
      if (url && /^https:\/\/(drive|docs)\.google\.com\//.test(url)) {
        row.append(h('a', { class: 'chip photo', href: url, target: '_blank', rel: 'noopener noreferrer', text: t('photo_open'), 'data-test': 'photo-file' }));
      } else if (p.unavailable || p.file) {
        row.append(h('span', { class: 'chip photo dondy', text: t('photo_dondy'), 'data-test': 'photo-dondy' }));
      } else {
        row.append(h('span', { class: 'chip photo wait', text: t('photo_wait'), 'data-test': 'photo-wait' }));
      }
    });
    return row;
  }
  const ORIG = new WeakMap();
  function convCard(conv) {
    const card = h('div', { class: 'card' }, h('h3', null, t('conversation'), h('span', { id: 'tr-state', class: 'chip outline', hidden: true })));
    const list = h('div', { class: 'conv' });
    const msgs = conv.map(function (m, i) { return Object.assign({ _i: i }, m); }).sort(function (a, b) { return (ms(a.at) || 0) - (ms(b.at) || 0); });
    msgs.forEach(function (m, i) {
      const who = m.who === 'us' ? 'us' : (m.who === 'automatic' ? 'automatic' : 'customer');
      const long = String(m.text || '').length > 600 && i < msgs.length - 1;
      const el = h('div', { class: 'msg ' + who + (long ? ' collapsed' : ''), 'data-i': String(m._i) },
        h('div', { class: 'meta' }, h('b', { text: t(who) }), h('span', { text: fmtDate(m.at, true) })),
        h('div', { class: 'mbody' }, messageBody(m.text)), photoChips(m.photos));
      ORIG.set(el, String(m.text || ''));
      if (long) {
        const mb = h('button', { class: 'more-btn', type: 'button', text: t('show_more') });
        mb.addEventListener('click', function () { const c = el.classList.toggle('collapsed'); mb.textContent = c ? t('show_more') : t('show_less'); });
        el.append(mb);
      }
      list.append(el);
    });
    if (!msgs.length) list.append(h('div', { class: 'muted', text: '—' }));
    card.append(list);
    return card;
  }

  // ---- draft (editor + send / handled / close)
  const Draft = (function () {
    let st = null;   // { id, brand, key, ta, base, dirty, saving, timer, stateEl }
    function key(brand, id) { return 'cs.draft.' + brand + '.' + id; }
    function readLocal(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
    function writeLocal() {
      try { localStorage.setItem(st.key, JSON.stringify({ text: st.ta.value, base: st.base, at: Date.now() })); } catch (e) { /* quota: server save still runs */ }
    }
    function dropLocal() { try { localStorage.removeItem(st.key); } catch (e) { /* ignore */ } }
    function pruneOld() {
      try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
          const k = localStorage.key(i);
          if (k && k.indexOf('cs.draft.') === 0 && k.indexOf('cs.draft.en.') !== 0) { const v = readLocal(k); if (!v || Date.now() - v.at > 7 * 86400000) localStorage.removeItem(k); }
        }
      } catch (e) { /* ignore */ }
    }
    function setState(kind, msg) {
      if (!st || !st.stateEl) return;
      st.stateEl.className = 'save-state' + (kind === 'fail' ? ' bad' : kind === 'saved_opt' ? ' opt' : '');
      st.stateEl.textContent = kind === 'local' ? t('save_local') : kind === 'saving' ? t('saving') : (kind === 'saved' || kind === 'saved_opt') ? t('saved') :
        kind === 'fail' ? t('save_failed', { m: msg || '' }) : (msg || '');
    }
    async function save() {
      if (!st || !st.dirty) return;
      if (st.saving) { st.again = true; return; }
      const mine = st;
      const text = mine.ta.value;
      if (!text.trim()) return;
      // Optimistic: "saved" shows at once. The device copy is kept until the engine confirms, and a refusal rolls the
      // screen's idea of the server draft back — the agent's text itself is never touched.
      const tk = S.tk && S.tk.id === mine.id ? S.tk.ticket : null;
      const prevBase = mine.base;
      const prevDraft = tk ? tk.draft_text : null;
      mine.saving = true;
      mine.base = text;
      if (tk) tk.draft_text = text;
      if (mine.ta.value === text) mine.dirty = false;
      setState('saved_opt');
      const r = await engine('apiSaveDraft', { id: mine.id, text: text }, mine.brand);
      mine.saving = false;
      if (r.ok) {
        if (st === mine) {
          if (mine.ta.value === text && !mine.dirty) { dropLocal(); setState('saved'); } else writeLocal();
          // Owner, 2026-10-06: a person's send is never blocked by a content check — the engine's check is an audit only,
          // so nothing about it is shown here (agents read any note as "must edit")
        }
      } else {
        mine.base = prevBase;
        if (tk && tk.draft_text === text) tk.draft_text = prevDraft;
        mine.dirty = true;
        if (st === mine) { writeLocal(); setState('fail', r.msg || r.error); } else toast(t('save_failed', { m: r.msg || r.error }));
      }
      if (mine.again && st === mine) { mine.again = false; save(); }
    }
    function flush() { if (st) { clearTimeout(st.timer); if (st.dirty) save(); } }
    function detach() { flush(); st = null; }
    window.addEventListener('beforeunload', function (e) { if (st && (st.dirty || st.saving)) { writeLocal(); e.preventDefault(); e.returnValue = ''; } });
    window.addEventListener('pagehide', function () { if (st && st.dirty) writeLocal(); });

    function card(x) {
      pruneOld();
      const isOpen = OPEN.indexOf(x.status) >= 0;
      const k = key(S.brand, x.id);
      const server = String(x.draft_text || '');
      const local = readLocal(k);
      const ta = h('textarea', { dir: 'auto', 'aria-label': t('draft'), spellcheck: 'true', rows: '9' });
      ta.value = server;
      st = { id: x.id, brand: S.brand, key: k, ta: ta, base: server, dirty: false, saving: false, timer: null };
      const stateEl = h('div', { class: 'save-state', 'aria-live': 'polite' });
      const note = h('div');
      const offerEl = h('div', { class: 'stale', hidden: true, 'data-test': 'draft-offer' });
      st.stateEl = stateEl; st.offerEl = offerEl;
      const errEl = h('div', { hidden: true });
      const c = h('div', { class: 'card draft' }, h('h3', { text: t('draft') }), note, offerEl, ta, stateEl, errEl);
      if (!isOpen) {
        ta.readOnly = true;
        if (local) dropLocal();
        c.append(h('div', { class: 'muted small', text: t('draft_readonly') }));
        return c;
      }
      if (local && local.text !== server && local.text.trim()) {
        ta.value = local.text;
        st.dirty = true;
        st.edited = true;
        if (local.base === server) {
          note.append(h('div', { class: 'muted small', text: t('restored') }));
          st.timer = setTimeout(save, 800);
        } else {
          const banner = h('div', { class: 'stale' }, h('span', { text: t('conflict') }));
          banner.append(h('button', { class: 'btn small', type: 'button', text: t('use_server'), onclick: function () {
            ta.value = server; st.base = server; st.dirty = false; dropLocal(); clear(note); setState('', '');
          } }));
          banner.append(h('button', { class: 'btn small ghost', type: 'button', text: t('keep_mine'), onclick: function () { st.base = server; clear(note); save(); } }));
          note.append(banner);
        }
      } else if (local) dropLocal();

      ta.addEventListener('input', function () {
        pingEdit(st.brand, st.id);
        st.dirty = true;
        st.edited = true;                                    // for good: a saved edit is still the agent's text
        writeLocal();
        setState('local');
        clearTimeout(st.timer);
        st.timer = setTimeout(save, 2500);
        sendBtn.disabled = sendDisabled();
      });
      ta.addEventListener('blur', function () { clearTimeout(st.timer); if (st.dirty) save(); });

      // Live, never captured at render time: a deep link can render this card before apiBoot answers.
      // Unknown mode = disabled (fail closed); loadBoot() calls refreshSend() when the answer lands.
      function isDry() { const b = S.boots[st.brand]; return !b || !!b.dryRun; }
      function winClosed() { return waWinClosed(S.tk && S.tk.id === x.id ? S.tk.ticket : x); }
      function sendDisabled() { return isDry() || winClosed() || !ta.value.trim() || waQueued(S.tk && S.tk.id === x.id ? S.tk.ticket : x) || waLocked(st.brand, x.id) || Outbox.blocks(st.brand, x.id); }
      const actions = h('div', { class: 'actions' });
      const all = [];
      async function doSend() {
        const text = ta.value;
        clear(errEl); errEl.hidden = true;
        clearTimeout(st.timer);
        writeLocal();                                        // the text is safe on this device whatever happens
        const args = { id: x.id, text: text };
        if (isWA(x)) args.channel = 'whatsapp';
        // Owner, 2026-10-05: the agent never waits for the engine — hand it to the outbox and go to the next ticket
        if (Outbox.start('apiSend', st.brand, x, args)) { st.dirty = false; goNext(st.brand, x.id); }
        return;
      }
      async function doClose(fn, okMsg) {
        clear(errEl); errEl.hidden = true;
        if (Outbox.start(fn, st.brand, x, { id: x.id })) goNext(st.brand, x.id);   // optimistic: off the list, next ticket
        return;
      }
      const sendLabel = isWA(x) ? t('send_wa') : t('send_email');
      const waNote = h('div', { class: 'wa-note', 'data-test': 'wa-queued' });
      c.append(waNote);
      function paintWa() {
        clear(waNote);
        const tk = S.tk && S.tk.id === x.id ? S.tk.ticket : x;
        if (waQueued(tk) && tk.status !== 'wa_queued') waNote.append(h('span', { class: 'chip ch-wa big', text: t('wa_queued_chip') }));
        else if (waLocked(st.brand, x.id)) waNote.append(h('span', { class: 'chip bad big', text: t('wa_locked') }), ' ',
          h('button', { class: 'btn small', type: 'button', text: t('wa_check'), onclick: function () { openTicket(x.id, { fresh: true }); } }));
        waNote.hidden = !waNote.firstChild;
      }
      const sendBtn = armed(sendLabel, t('send_arm'), 'primary' + (isWA(x) ? ' wa' : ''), function () { if (!sendDisabled()) doSend(); });
      sendBtn.setAttribute('data-test', 'send-btn');
      st.refreshSend = function () {
        paintWa();
        if (sendBtn.classList.contains('arm')) return;
        sendBtn.disabled = sendDisabled();
        sendBtn.textContent = isDry() && S.boots[st.brand] ? t('send_dry') : sendLabel;
        sendBtn.title = isDry() ? t('dry_run') : '';
      };
      st.refreshSend();
      const handledBtn = armed(t('handled'), t('handled_arm'), '', function () { doClose('apiMarkHandled', t('handled_ok')); });
      const closeBtn = armed(t('close'), t('close_arm'), 'ghost', function () { doClose('apiClose', t('closed_ok')); });
      all.push(sendBtn, handledBtn, closeBtn);
      actions.append(sendBtn, handledBtn, closeBtn);
      if (winClosed()) {
        c.append(h('div', { class: 'wa-win-note', role: 'status', 'data-test': 'wa-win-note', text: t('wa_win_note') }));
        const tb = templateBox(st.brand, x, function () { return ta.value; });
        ta.addEventListener('input', function () { tb.refresh(); });
        c.append(tb);
      }
      c.append(actions);
      return c;
    }
    /** The engine wrote a new draft while this one is on screen. Untouched text is replaced (and said so); an edited
     *  one is never overwritten — the new draft is offered next to it. */
    function offer(text) {
      if (!st || !st.ta || !st.offerEl || st.ta.readOnly) return;
      const mine = st;
      if (text === mine.ta.value || text === mine.base) return;
      clear(mine.offerEl);
      if (!mine.edited && !mine.dirty && !mine.saving && mine.ta.value === mine.base) {
        const pos = mine.ta.selectionStart;
        mine.ta.value = text; mine.base = text;
        if (document.activeElement === mine.ta) { try { mine.ta.setSelectionRange(Math.min(pos, text.length), Math.min(pos, text.length)); } catch (e) { /* ignore */ } }
        mine.offerEl.append(h('span', { class: 'small', text: t('draft_updated') }));
        mine.offerEl.hidden = false;
        if (mine.refreshSend) mine.refreshSend();
        return;
      }
      mine.offerEl.append(h('span', { text: t('draft_new_avail') }), ' ',
        h('button', { class: 'btn small', type: 'button', text: t('use_new_draft'), 'data-test': 'use-new-draft', onclick: function () {
          if (st !== mine) return;
          clearTimeout(mine.timer);
          const inFlight = mine.saving;                    // an autosave of the old text is on its way: save this after it
          mine.ta.value = text; mine.edited = false;
          if (inFlight) { mine.dirty = true; mine.again = true; writeLocal(); }
          else { mine.base = text; mine.dirty = false; dropLocal(); setState('', ''); }
          clear(mine.offerEl); mine.offerEl.hidden = true;
          if (mine.refreshSend) mine.refreshSend();
        } }));
      mine.offerEl.hidden = false;
    }
    return { card: card, flush: flush, detach: detach, offer: offer, isDirty: function () { return !!(st && (st.dirty || st.saving)); },
      edited: function () { return !!(st && st.edited); },
      refreshSend: function () { if (st && st.refreshSend) st.refreshSend(); } };
  })();

  // ---------------------------------------------------------------- English mode (phase 5, /cs/en only)
  function normLang(c) { c = String(c || '').toLowerCase().split('-')[0]; return c === 'iw' || !c ? 'he' : c; }
  function langName(c) { const k = 'lang_name_' + normLang(c); const v = t(k); return v === k ? normLang(c).toUpperCase() : v; }
  function enMode(x) { return LANG === 'en' && !!x; }

  /** One "show original" toggle per translated block. The original text is never discarded. */
  function bilingual(container, original, english, toggleHost) {
    let showing = 'en';
    const btn = h('button', { class: 'more-btn tr-toggle', type: 'button', 'data-test': 'show-original' });
    function paint() {
      clear(container);
      const plain = container.classList.contains('summary-line') || container.id === 'tk-reco';
      add(container, plain ? (showing === 'en' ? english : original) : messageBody(showing === 'en' ? english : original));
      btn.textContent = showing === 'en' ? t('show_orig') : t('show_en');
    }
    btn.addEventListener('click', function () { showing = showing === 'en' ? 'orig' : 'en'; paint(); });
    toggleHost.append(btn);
    paint();
  }

  const Translate = {
    async load(k) {
      const x = k.ticket;
      const requestId = k.trRequest = (k.trRequest || 0) + 1;
      k.tr = { loading: true };
      this.paint(k);
      const r = await api('/api/' + encodeURIComponent(k.brand) + '/translate', { ticketId: k.id });
      if (S.tk !== k || k.trRequest !== requestId) return;
      k.tr = r.ok ? r : { err: r.msg || r.error };
      this.paint(k);
      paintLive(k);
      if (r.ok) EnDraft.prefill(x.id, r.draft);
      else EnDraft.prefill(x.id, null);
    },
    paint(k) {
      const chip = document.getElementById('tr-state');
      const tr = k.tr || {};
      if (chip) {
        chip.hidden = false;
        clear(chip);
        if (tr.loading) chip.append(t('tr_loading'));
        else if (tr.err) { chip.className = 'chip bad'; chip.append(tx('tr_failed', { m: tr.err })); }
        else {
          chip.append(tx('tr_from', { l: langName(tr.source || k.ticket.language) }));
          if (tr.incomplete) { chip.className = 'chip bad'; chip.append(' · ', tx('tr_incomplete', { n: tr.incomplete })); }
        }
      }
      if (!tr.loading && (tr.err || tr.incomplete)) chip.append(' ', h('button', { type: 'button', class: 'more-btn', text: t('tr_retry'), onclick: function () { Translate.load(k); } }));
      if (!tr.ok) return;
      const pane = $('ticket-pane');
      (tr.conversation || []).forEach(function (c) {
        if (!c || typeof c.text !== 'string') return;
        const el = pane.querySelector('.msg[data-i="' + Number(c.i) + '"]');
        if (!el || el.dataset.tr) return;
        el.dataset.tr = '1';
        el.querySelector('.mbody').setAttribute('lang', 'en');
        bilingual(el.querySelector('.mbody'), ORIG.get(el) || '', c.text, el.querySelector('.meta'));
      });
      if (tr.recommendation) {
        const r1 = document.getElementById('tk-reco');
        if (r1 && !r1.dataset.tr) { r1.dataset.tr = '1'; const host = h('span', { class: 'sum-toggle' }); r1.after(host); bilingual(r1, k.ticket.recommendation || '', tr.recommendation, host); }
        document.querySelectorAll('.tk-reco2').forEach(function (el) { el.textContent = tr.recommendation; });
      }
      const subject = document.getElementById('tk-subject');
      if (subject && tr.subject && !subject.dataset.tr) {
        subject.dataset.tr = '1';
        const host = h('span', { class: 'sum-toggle' });
        subject.after(host);
        bilingual(subject, k.ticket.subject || '', tr.subject, host);
        const warning = document.getElementById('tk-subject-warning');
        if (warning) warning.hidden = true;
      }
      const sum = document.getElementById('tk-summary');
      if (sum && tr.summary && !sum.dataset.tr) {
        sum.dataset.tr = '1';
        const host = h('span', { class: 'sum-toggle' });
        sum.after(host);
        bilingual(sum, k.ticket.summary || '', tr.summary, host);
      }
    }
  };

  const EnDraft = (function () {
    let cur = null;
    function card(x) {
      const brand = S.brand;
      const key = 'cs.draft.en.' + brand + '.' + x.id;
      let local = null;
      try { local = localStorage.getItem(key); } catch (e) { local = null; }
      const ta = h('textarea', { dir: 'ltr', lang: 'en', rows: '8', 'aria-label': t('en_draft') });
      const note = h('div', { class: 'muted small' });
      const review = h('div', { class: 'en-review', hidden: true, 'data-test': 'en-review' });
      const errEl = h('div');
      const me = { id: x.id, brand: brand, ta: ta, note: note, prefilled: false, translated: null, busy: false };
      cur = me;
      if (local !== null && local.trim()) { ta.value = local; note.textContent = t('restored'); me.prefilled = true; } else note.textContent = t('en_draft_loading');
      function isDry() { const b = S.boots[brand]; return !b || !!b.dryRun; }
      function showErr(r) {
        clear(errEl);
        errEl.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error })));
      }
      const reviewBtn = h('button', { class: 'btn primary', type: 'button', text: t('en_review'), 'data-test': 'en-review-btn' });
      const confirmBtn = h('button', { class: 'btn primary' + (isWA(x) ? ' wa' : ''), type: 'button', text: t('en_confirm'), 'data-test': 'en-confirm' });
      const editBtn = h('button', { class: 'btn ghost', type: 'button', text: t('en_edit') });
      function refresh() {
        reviewBtn.disabled = me.busy || !ta.value.trim();
        confirmBtn.disabled = me.busy || !me.translated || isDry() || waQueued(S.tk && S.tk.id === x.id ? S.tk.ticket : x) || waLocked(brand, x.id) || Outbox.blocks(brand, x.id);
        confirmBtn.textContent = isDry() && S.boots[brand] ? t('send_dry') : t(isWA(x) ? 'en_confirm_wa' : 'en_confirm_email');
        confirmBtn.title = isDry() ? t('dry_run') : '';
      }
      me.refresh = refresh;
      function paintReview() {
        clear(review);
        const tr = me.translated;
        review.hidden = !tr;
        if (!tr) return;
        add(review, [h('div', { class: 'en-cols' },
          h('div', { class: 'en-col' }, h('b', { text: t('en_side_en') }), h('div', { class: 'txt', dir: 'ltr', lang: 'en', text: tr.en })),
          h('div', { class: 'en-col out' }, h('b', null, tx('en_side_out', { l: langName(tr.target) })), h('div', { class: 'txt', dir: 'auto', text: tr.out }))),
          tr.same ? h('div', { class: 'muted small', text: t('en_same') }) : null,
          h('div', { class: 'actions' }, confirmBtn, editBtn)]);
        refresh();
      }
      ta.addEventListener('input', function () {
        if (S.tk) pingEdit(S.tk.brand, S.tk.id);
        me.typed = true;
        try { localStorage.setItem(key, ta.value); } catch (e) { /* the server never holds this English text */ }
        if (me.translated) { me.translated = null; paintReview(); showErr({ msg: t('en_stale') }); }
        refresh();
      });
      reviewBtn.addEventListener('click', async function () {
        if (!ta.value.trim()) return;
        me.busy = true; reviewBtn.textContent = t('en_reviewing'); clear(errEl); refresh();
        const sourceText = ta.value;
        const r = await api('/api/' + encodeURIComponent(brand) + '/translate-out', { ticketId: x.id, text: sourceText, lang: LANG });
        me.busy = false; reviewBtn.textContent = t('en_review');
        if (!r.ok) { refresh(); showErr(r); return; }
        if (ta.value !== sourceText) { refresh(); showErr({ msg: t('en_stale') }); return; }
        if (normLang(r.target) !== 'he' || !/[\u0590-\u05ff]/.test(r.text || '') || r.same) { refresh(); showErr({ msg: t('en_invalid') }); return; }
        me.translated = { en: sourceText, out: r.text, target: r.target, same: false };
        paintReview();
      });
      editBtn.addEventListener('click', function () { me.translated = null; paintReview(); ta.focus(); });
      async function send() {
        if (!me.translated || isDry() || me.busy) return;
        if (ta.value !== me.translated.en || normLang(me.translated.target) !== 'he') { me.translated = null; paintReview(); showErr({ msg: t('en_stale') }); return; }
        me.busy = true; refresh(); clear(errEl);
        const args = { id: x.id, text: me.translated.out };
        if (isWA(x)) args.channel = 'whatsapp';
        try {
          if (Outbox.start('apiSend', brand, x, args)) goNext(brand, x.id);
        } finally {
          // Outbox owns the in-flight lock after handoff; a rejected handoff must not freeze this editor.
          me.busy = false; refresh();
        }
      }
      confirmBtn.addEventListener('click', function () { send(); });
      async function doClose(fn, okMsg) {
        if (Outbox.start(fn, brand, x, { id: x.id })) goNext(brand, x.id);
      }
      const handledBtn = armed(t('handled'), t('handled_arm'), '', function () { doClose('apiMarkHandled', t('handled_ok')); });
      const closeBtn = armed(t('close'), t('close_arm'), 'ghost', function () { doClose('apiClose', t('closed_ok')); });
      refresh();
      const enCard = h('div', { class: 'card draft en-draft', 'data-test': 'en-draft' }, h('h3', { text: t('en_draft') }), h('div', { class: 'muted small', text: t('en_safety'), 'data-test': 'hebrew-only-notice' }), note, ta);
      if (waWinClosed(x)) {     // past 24 hours: no free text; a template instead (the reply that waits is translated to Hebrew by the server)
        reviewBtn.hidden = true;
        const tbe = templateBox(brand, x, function () { return ta.value; });
        ta.addEventListener('input', function () { tbe.refresh(); });
        enCard.append(h('div', { class: 'wa-win-note', role: 'status', 'data-test': 'wa-win-note', text: t('wa_win_note') }), tbe);
      }
      enCard.append(h('div', { class: 'actions' }, reviewBtn, handledBtn, closeBtn), review, errEl);
      return enCard;
    }
    function prefill(id, text) {
      if (!cur || cur.id !== id || cur.prefilled) return;
      if (text && !cur.ta.value.trim()) { cur.ta.value = text; cur.note.textContent = t('en_draft_ai'); cur.prefilled = true; }
      else cur.note.textContent = '';
      cur.refresh();
    }
    return { card: card, prefill: prefill, refresh: function () { if (cur && cur.refresh) cur.refresh(); },
      busy: function () { return !!(cur && S.tk && cur.id === S.tk.id && (cur.typed || cur.translated || cur.busy)); } };
  })();

  // ---------------------------------------------------------------- knowledge assistant (phase 5)
  const Assist = (function () {
    const fab = $('assist-fab');
    const pane = $('assist');
    let ui = null;
    function st() { if (!S.assist[S.brand]) S.assist[S.brand] = { msgs: [], busy: false, err: null, withTicket: true }; return S.assist[S.brand]; }
    function available() { return !!(S.me && S.me.assistant && canWork() && S.brand && connected() && (S.view === 'list' || S.view === 'ticket')); }
    function build() {
      if (ui) return;
      const title = h('b', { class: 'as-title' });
      const log = h('div', { class: 'as-log', 'aria-live': 'polite' });
      const ta = h('textarea', { rows: '2', dir: 'auto', placeholder: t('as_ph'), 'aria-label': t('as_ph'), maxlength: '4000' });
      const sendBtn = h('button', { class: 'btn primary', type: 'button', text: t('as_send') });
      const ctxCb = h('input', { type: 'checkbox', checked: true });
      const ctxRow = h('label', { class: 'as-ctx cb' }, ctxCb, t('as_ctx'));
      const err = h('div');
      const clearBtn = h('button', { class: 'btn small ghost', type: 'button', text: t('as_clear') });
      const closeBtn = h('button', { class: 'btn small', type: 'button', text: t('as_close'), 'aria-label': t('as_close') });
      pane.append(h('div', { class: 'as-head' }, title, h('span', { class: 'spacer' }), clearBtn, closeBtn), log, err, ctxRow,
        h('div', { class: 'as-compose' }, ta, sendBtn));
      ui = { title: title, log: log, ta: ta, sendBtn: sendBtn, ctxCb: ctxCb, ctxRow: ctxRow, err: err };
      sendBtn.addEventListener('click', send);
      ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
      ctxCb.addEventListener('change', function () { st().withTicket = ctxCb.checked; });
      clearBtn.addEventListener('click', function () { const s = st(); if (s.busy) return; s.msgs = []; s.err = null; render(); });
      closeBtn.addEventListener('click', function () { pane.hidden = true; sync(); });
    }
    function render() {
      if (!ui) return;
      const s = st();
      clear(ui.title);
      ui.title.append(t('as_title') + ' · ', h('bdi', { text: brandName(S.brand) }));
      ui.ctxRow.hidden = !(S.view === 'ticket' && S.ticketId);
      ui.ctxCb.checked = s.withTicket;
      clear(ui.log);
      ui.log.append(h('div', { class: 'as-hello muted small' }, tx('as_hello', { b: brandName(S.brand) })));
      s.msgs.forEach(function (m) {
        ui.log.append(h('div', { class: 'as-msg ' + (m.role === 'user' ? 'me' : 'bot') },
          h('div', { class: 'meta' }, h('b', { text: m.role === 'user' ? t('as_me') : t('as_bot') }),
            (m.tools || []).map(function (tl) { return h('span', { class: 'chip ' + (tl.ok ? 'outline' : 'bad'), text: t('tool_' + tl.name) }); })),
          h('div', { class: 'txt', dir: 'auto', text: m.content })));
      });
      if (s.busy) ui.log.append(h('div', { class: 'as-msg bot' }, h('span', { class: 'spinner' }), ' ', t('as_thinking')));
      clear(ui.err);
      if (s.err) ui.err.append(h('div', { class: 'err-box', role: 'alert', text: s.err }));
      ui.sendBtn.disabled = s.busy;
      ui.log.scrollTop = ui.log.scrollHeight;
    }
    async function send() {
      const s = st();
      const text = ui.ta.value.trim();
      if (!text || s.busy) return;
      const brand = S.brand;
      s.msgs.push({ role: 'user', content: text });
      ui.ta.value = '';
      s.busy = true; s.err = null;
      render();
      const body = { lang: LANG, messages: s.msgs.map(function (m) { return { role: m.role, content: m.content }; }) };
      if (s.withTicket && S.view === 'ticket' && S.ticketId) body.ticketId = S.ticketId;
      let r = await api('/api/' + encodeURIComponent(brand) + '/assistant', body);
      s.busy = false;
      if (r.ok && !(typeof r.reply === 'string' && r.reply.trim())) r = { ok: false, msg: t('err_bad_engine') };   // no answer = an error
      if (r.ok) s.msgs.push({ role: 'assistant', content: r.reply, tools: Array.isArray(r.tools) ? r.tools : [] });
      else {
        const lost = s.msgs.pop();                    // the question is never lost: back into the box
        s.err = r.msg || r.error;
        if (S.brand === brand && !ui.ta.value.trim()) ui.ta.value = lost.content;
      }
      if (S.brand === brand) render();
    }
    function sync() {
      const ok = available();
      if (!ok) pane.hidden = true;
      fab.hidden = !ok || !pane.hidden;
      if (!pane.hidden) render();
    }
    fab.addEventListener('click', function () { build(); pane.hidden = false; sync(); ui.ta.focus(); });
    return { sync: sync };
  })();

  function paintSubs(brand) {
    const slot = document.getElementById('subs-card');
    if (!slot || !S.tk || !S.tk.ticket || S.tk.brand !== brand || !S.boots[brand]) return;
    if (noSubs(brand) || (S.tk.extras && S.tk.extras.notes && S.tk.extras.notes.subscriptions === 'brand_none')) { clear(slot); return; }
    if (!slot.firstChild) slot.append(subsCard(S.tk.extras || {}, S.tk.ticket));
  }

  async function afterAction() {
    const id = S.tk && S.tk.id;
    if (id) delete S.tkMemo[S.brand + '|' + id];          // the server cache was patched by the write; the memo was not
    await loadBoot(S.brand);
    if (id && S.tk && S.tk.id === id) openTicket(id);
  }

  // ---- orders
  function ordersCard(ex, x) {
    const c = h('div', { class: 'card' }, h('h3', { text: t('orders') }));
    const orders = ex.orders || [];
    const sh = ex.shipping || null;
    if (sh && sh.state && sh.state !== 'unknown' && sh.orderName) {
      c.append(h('p', { class: 'small ship-line' }, h('bdi', { class: 'chip ' + (sh.state === 'not_late' ? 'ok' : sh.state === 'not_applicable' ? '' : 'bad'), text: sh.orderName }), ' ',
        t('ship_line', { state: t('ship_' + sh.state), d: sh.daysSinceOrder })));             // never the internal thresholds
    }
    if (ex.ordersError) c.append(h('div', { class: 'problem' }, tx('orders_err', { m: String(ex.ordersError) })));
    if (!orders.length) {
      const note = (ex.notes && typeof ex.notes === 'object') ? ex.notes.orders : undefined;
      const chipNo = (sh && sh.state && sh.state !== 'unknown' && sh.orderName) || (ex.notes && ex.notes.orderNo) || (x && x.order_no);
      if (chipNo && !(sh && sh.orderName)) c.append(h('p', { class: 'small ship-line' }, h('bdi', { class: 'chip outline', text: chipNo })));
      let line = null;
      if (note === 'chip_only' || (note === undefined && chipNo)) line = note === 'chip_only' ? t('orders_chip_only') : null;
      else if (note === 'error' || (note === undefined && ex.lookup === 'error')) line = t('check_error');
      else if (note === 'not_checked') line = t('orders_not_checked');
      else if (note === 'none' || note === undefined) line = chipNo ? null : t('no_orders');
      if (line) c.append(h('div', { class: 'muted', 'data-test': 'orders-note', text: line }));
      return c;                                           // an order chip is never next to "no order found"
    }
    const list = h('div', { class: 'sub-list' });
    orders.forEach(function (o) {
      const tracks = [];
      (o.fulfillments || []).forEach(function (f) {
        (f.tracking || []).forEach(function (tr) {
          const u = safeUrl(tr.url);
          const label = [tr.company, tr.number].filter(Boolean).join(' · ') || t('track');
          tracks.push(u ? h('a', { href: u, target: '_blank', rel: 'noopener noreferrer', class: 'ltr', text: label }) : h('bdi', { class: 'ltr', text: label }));
          if (tr.number) tracks.push(copyBtn(tr.number));
        });
      });
      const shipped = (o.fulfillments || []).map(function (f) { return f.createdAt; }).filter(Boolean)[0];
      list.append(h('div', { class: 'item-card' },
        h('div', { class: 'hd' }, h('b', { class: 'ltr', text: o.name || '—' }),
          o.financialStatus ? h('span', { class: 'chip ' + (/PAID/.test(o.financialStatus) && !/REFUND/.test(o.financialStatus) ? 'ok' : ''), text: t('fin_' + o.financialStatus) }) : null,
          o.fulfillmentStatus ? h('span', { class: 'chip ' + (o.fulfillmentStatus === 'FULFILLED' ? 'st-sent' : 'outline'), text: t('ful_' + o.fulfillmentStatus) }) : null),
        h('dl', { class: 'kv' },
          h('dt', { text: t('ordered') }), h('dd', { text: fmtDate(o.createdAt) + ' (' + ago(o.createdAt) + ')' }),
          shipped ? h('dt', { text: t('shipped_on') }) : null, shipped ? h('dd', { text: fmtDate(shipped) }) : null,
          tracks.length ? h('dt', { text: t('track') }) : null, tracks.length ? h('dd', null, tracks) : null),
        h('ul', null, (o.items || []).map(function (it) { return h('li', { dir: 'auto', text: (it.quantity > 1 ? it.quantity + ' × ' : '') + it.title }); }))));
    });
    c.append(list);
    return c;
  }

  // ---- subscriptions + cancel
  function everyText(e) {
    const m = /^(\d+)\s+(day|week|month|year)s?$/i.exec(String(e || '').trim());
    if (!m) return e || '—';
    const n = Number(m[1]);
    const u = m[2].toLowerCase();
    return n === 1 ? t('every_' + u) : t('every_n', { n: n, u: t('unit_' + u) });
  }
  function payText(v) { const k = 'pay_' + String(v || '').toUpperCase(); const x = t(k); return x === k ? String(v) : x; }
  function contractNum(id) { return String(id || '').split('/').pop(); }
  function subsCard(ex, x) {
    const c = h('div', { class: 'card' }, h('h3', { text: t('subs') }));
    const subs = Array.isArray(ex.subscriptions) ? ex.subscriptions : [];
    if (ex.subscriptionsError) c.append(h('div', { class: 'problem' }, tx('subs_err', { m: String(ex.subscriptionsError) })));
    if (!subs.length) {
      const note = (ex.notes && typeof ex.notes === 'object') ? ex.notes.subscriptions : undefined;
      const why = note === 'not_checked_no_email' ? t('subs_no_email') : note === 'error' ? t('check_error')
        : note === 'not_checked' ? t('subs_not_checked') : note === 'none' ? t('no_subs')
        : !String(x.email || '').trim() ? t('subs_no_email')
        : (typeof ex.subscriptions === 'string' && /unavailable|error/i.test(ex.subscriptions)) ? t('subs_unavailable') : t('no_subs');
      c.append(h('div', { class: 'muted', 'data-test': 'subs-empty', text: why }));
      return c;
    }
    const done = String(x.cancelled || '').split(',').filter(Boolean);
    const isOpen = OPEN.indexOf(x.status) >= 0;
    const list = h('div', { class: 'sub-list' });
    subs.forEach(function (s) {
      const cancellable = ['ACTIVE', 'PAUSED', 'FAILED'].indexOf(s.status) >= 0;
      const items = (s.lines || []).map(function (l) { return (l.quantity > 1 ? l.quantity + ' × ' : '') + l.title; }).join(', ');
      const card = h('div', { class: 'item-card' },
        h('div', { class: 'hd' }, h('b', { dir: 'auto', text: items || '—' }),
          h('span', { class: 'chip ' + (s.status === 'ACTIVE' ? 'ok' : s.status === 'CANCELLED' ? '' : 'bad'), text: t('ss_' + s.status) }),
          done.indexOf(s.id) >= 0 ? h('span', { class: 'chip ok', text: t('cancelled_here') }) : null),
        h('dl', { class: 'kv' },
          h('dt', { text: t('sub_every') }), h('dd', { text: everyText(s.every) }),
          h('dt', { text: t('sub_next') }), h('dd', { text: s.nextBillingDate ? fmtDate(s.nextBillingDate) : (s.status === 'CANCELLED' ? '—' : t('sub_next_na')) }),
          h('dt', { text: t('sub_since') }), h('dd', { text: fmtDate(s.createdAt) }),
          s.lastPaymentStatus ? h('dt', { text: t('sub_lastpay') }) : null, s.lastPaymentStatus ? h('dd', { text: payText(s.lastPaymentStatus) }) : null,
          h('dt', { text: t('sub_id') }), h('dd', null, h('bdi', { class: 'ltr', text: contractNum(s.id) }))));
      if (cancellable && canWork()) {
        card.append(h('div', { class: 'actions' }, h('button', { class: 'btn danger-outline small', type: 'button', text: t('cancel_sub'),
          disabled: !isOpen && false, onclick: function () { Cancel.open(x, s); } })));
      }
      list.append(card);
    });
    c.append(list);
    return c;
  }

  const Cancel = (function () {
    const dlg = $('cancel-dlg');
    let busy = false;
    function open(x, s) {
      if (busy) return;
      clear(dlg);
      const wants = /^cancel:/i.test(String(x.action || ''));
      const b = boot() || {};
      const num = contractNum(s.id);
      const items = (s.lines || []).map(function (l) { return (l.quantity > 1 ? l.quantity + ' × ' : '') + l.title; }).join(', ');
      const code = h('input', { class: 'code', inputmode: 'numeric', maxlength: '4', autocomplete: 'off', pattern: '[0-9]{4}', 'aria-label': t('dlg_type') });
      const reason = h('textarea', { rows: '3', dir: 'auto', maxlength: '500' });
      const result = h('div', { 'aria-live': 'assertive' });
      const go = h('button', { class: 'btn danger', type: 'button', text: t('dlg_go'), disabled: true });
      const back = h('button', { class: 'btn ghost', type: 'button', text: t('dlg_back') });
      code.addEventListener('input', function () { code.value = code.value.replace(/\D/g, '').slice(0, 4); go.disabled = busy || code.value.length !== 4; });
      back.addEventListener('click', function () { if (!busy) dlg.close(); });
      dlg.addEventListener('cancel', function (e) { if (busy) e.preventDefault(); });
      go.addEventListener('click', async function () {
        if (busy || code.value.length !== 4) return;
        busy = true; go.disabled = true; back.disabled = true; go.textContent = t('dlg_working');
        clear(result);
        const r = await engine('apiKachingCancel', { id: x.id, contractId: s.id, confirm: code.value, reason: reason.value.trim() }, S.brand);
        busy = false; back.disabled = false; go.textContent = t('dlg_go');
        if (r.ok) {
          dlg.close();
          toast(r.msg || t('ss_CANCELLED'));
          if (S.tk && S.tk.id === x.id) {               // refresh only the panels the cancel changed; the draft is untouched
            const fr = await fetchTicket(S.brand, x.id, true);
            if (S.tk && S.tk.id === x.id && fr.ok) {
              S.tk.ticket.cancelled = fr.ticket.cancelled;
              S.tk.extras = fr.extras || {};
              const slot = document.getElementById('subs-card');
              if (slot) { clear(slot); slot.append(subsCard(S.tk.extras || {}, S.tk.ticket)); }
            }
          }
          return;
        }
        go.disabled = code.value.length !== 4;
        result.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error }),
          r.message ? h('bdi', { class: 'raw', text: r.message }) : null));
      });
      const warn = [];
      if (b.cancelFrozen) warn.push(h('div', { class: 'problem', text: t('dlg_frozen') }));
      else if (b.cancelEnabled === false) warn.push(h('div', { class: 'problem', text: t('dlg_off') }));
      dlg.append(h('div', { class: 'in' },
        h('h3', { text: t('dlg_title') }),
        h('div', null, h('b', { dir: 'auto', text: items || '—' }), ' ', h('span', { class: 'chip', text: t('ss_' + s.status) })),
        h('div', { class: 'small muted' }, t('sub_id') + ': ', h('bdi', { class: 'ltr', text: num }), ' · ', x.email ? h('bdi', { class: 'ltr', text: x.email }) : null),
        warn,
        h('label', null, t('dlg_type'), code),
        h('label', null, h('span', null, t('dlg_reason') + ' ', h('span', { class: 'muted small', text: wants ? t('dlg_reason_opt') : t('dlg_reason_req') })), reason),
        h('div', { class: 'small muted', text: t('dlg_irrev') }),
        result,
        h('div', { class: 'row-btns' }, back, go)));
      dlg.showModal();
      setTimeout(function () { code.focus(); }, 0);
    }
    return { open: open };
  })();

  // ---- notes
  function notesCard(x) {
    const c = h('div', { class: 'card' }, h('h3', { text: t('notes') }));
    const notes = String(x.notes || '').trim();
    c.append(notes ? h('div', { class: 'notes-list', dir: 'auto', text: notes }) : h('div', { class: 'muted small mb8', text: t('no_notes') }));
    const inp = h('input', { type: 'text', placeholder: t('note_ph'), maxlength: '1000', dir: 'auto', 'aria-label': t('note_ph') });
    const btn = h('button', { class: 'btn small', type: 'button', text: t('note_add') });
    const err = h('div');
    async function addNote() {
      const text = inp.value.trim();
      if (!text) return;
      btn.disabled = true;
      clear(err);
      const r = await engine('apiNote', { id: x.id, text: text });
      btn.disabled = false;
      if (!r.ok) { err.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
      toast(t('note_ok'));
      const fresh = await fetchTicket(S.brand, x.id, true);
      if (S.tk && S.tk.id === x.id) {
        if (fresh.ok) S.tk.ticket.notes = fresh.ticket.notes;
        const slot = document.getElementById('notes-card');
        if (slot) { clear(slot); slot.append(notesCard(S.tk.ticket)); }
      }
    }
    btn.addEventListener('click', addNote);
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') addNote(); });
    c.append(h('div', { class: 'note-add' }, inp, btn), err);
    return c;
  }

  // ---- related
  async function loadRelated() {
    const k = S.tk;
    if (!k || !k.ticket) return;
    const q = String(k.ticket.email || k.ticket.phone || '').trim();
    if (q.length < 2) { k.related = []; paintRelated(); return; }
    // server-cached and background-priority: never takes an engine slot an agent needs
    const r = await api('/api/' + encodeURIComponent(k.brand) + '/related', { q: q }, 'POST', { quiet: true });
    if (S.tk !== k) return;
    if (r.ok && r.deferred) {
      k.related = undefined; k.relatedDeferred = true; paintRelated();
      if (!k.relatedRetried) { k.relatedRetried = true; setTimeout(function () { if (S.tk === k) loadRelated(); }, 20000); }
      return;
    }
    k.relatedDeferred = false;
    k.related = r.ok ? (r.tickets || []).filter(function (x) { return x.id !== k.id; }) : [];
    k.relatedErr = r.ok ? null : (r.msg || r.error);
    paintRelated();
  }
  function relatedCard() {
    const c = h('div', { class: 'card related' }, h('h3', { text: t('related') }));
    const k = S.tk;
    if (k && k.relatedDeferred && !k.related) c.append(h('div', { class: 'muted small', 'data-test': 'related-deferred', text: t('related_later') }));
    else if (!k || k.related === null || k.related === undefined) c.append(h('div', { class: 'muted small', text: t('loading') }));
    else if (k.relatedErr) c.append(h('div', { class: 'err-box', text: k.relatedErr }));
    else if (!k.related.length) c.append(h('div', { class: 'muted small', text: t('no_related') }));
    else k.related.forEach(function (x) { c.append(rowEl(x, { showStatus: true })); });
    return c;
  }
  function paintRelated() {
    const slot = document.getElementById('related-card');
    if (slot) { clear(slot); slot.append(relatedCard()); }
  }

  function detailsCard(x) {
    return h('div', { class: 'card' }, h('h3', { text: t('details') }),
      h('dl', { class: 'kv' },
        h('dt', { text: t('created') }), h('dd', { text: fmtDate(x.created_at, true) }),
        x.handled_at ? h('dt', { text: t('handled_at') }) : null, x.handled_at ? h('dd', { text: fmtDate(x.handled_at, true) + ' ' + t('by') + ' ' + (x.handled_by || '—') }) : null,
        x.order_no ? h('dt', { text: t('order') }) : null, x.order_no ? h('dd', { class: 'ltr', text: x.order_no }) : null,
        x.language ? h('dt', { text: t('language') }) : null, x.language ? h('dd', { text: x.language }) : null,
        h('dt', { text: t('ticket_id') }), h('dd', { class: 'ltr', text: x.id })),
      h('p', { class: 'muted small mt8', text: t('audit_na') }));
  }

  // ---------------------------------------------------------------- confirm dialog
  function confirmDlg(opts) {
    return new Promise(function (resolve) {
      const dlg = $('confirm-dlg');
      clear(dlg);
      const ok = h('button', { class: 'btn ' + (opts.danger ? 'danger' : 'primary'), type: 'button', text: opts.ok || t('ok') });
      const no = h('button', { class: 'btn ghost', type: 'button', text: t('cancel_btn') });
      let done = false;
      function finish(v) { if (done) return; done = true; dlg.close(); resolve(v); }
      ok.addEventListener('click', function () { finish(true); });
      no.addEventListener('click', function () { finish(false); });
      dlg.addEventListener('close', function () { finish(false); }, { once: true });
      dlg.append(h('div', { class: 'in' }, h('h3', null, opts.title), opts.body ? h('p', { class: 'm0', text: opts.body }) : null,
        opts.extra || null, h('div', { class: 'row-btns' }, no, ok)));
      dlg.showModal();
      setTimeout(function () { no.focus(); }, 0);
    });
  }

  // ---------------------------------------------------------------- background sends (Owner, 2026-10-05)
  /*
   * An agent never waits for the engine: send / handled / close are handed to this outbox and the agent moves on.
   * Each item: {rid, brand, id, fn, args, channel, name, state, at, msg, reply}
   *   state: flight -> ok | refused | unknown | retry;  checking (after a reload) -> ok | unknown;  unknown -> ok | retry | unsent
   *   retry (Owner, 2026-10-09: "a reply an agent sent is ALWAYS sent; if it fails, try again 5 s later"): the answer said nothing went
   *   out and the cause passes (the engine's lock, a full gate, a server error, a login that ran out) -> the SAME call with the SAME rid
   *   after 5 s, then slower, ~17 min in all. Safe: the engine keeps the reply of a rid that succeeded and never runs it twice.
   *   A refusal about the ticket itself (closed WhatsApp window, already sent, someone else's send in flight) is never retried.
   * The rid is made HERE, so after a reload the page can still ask the server (/result -> apiResult) what happened;
   * the server finishes the request even if the browser left. One open item per ticket; a ticket with an item in
   * flight / checking / unknown never offers another send.
   */
  const Outbox = (function () {
    const KEY = 'cs.outbox';
    let items = {};
    let ver = 0;
    const RETRY_CODES = ['busy', 'server_error', 'rate_limited', 'not_logged_in', 'dropped', 'assistant_timeout', 'assistant_unreachable', 'assistant_busy', 'assistant_error'];
    const RETRY_AFTER_MS = [5000, 10000, 20000, 30000, 60000, 60000, 120000, 120000, 300000, 300000];
    // The engine remembers a rid that succeeded for 30 min (RES_TTL_S in engine/Api.gs). After that a same-rid call would RUN again, so a
    // lost "sent" could become a second message. No automatic send later than 20 min after the agent's click: then a person decides.
    const RETRY_WINDOW_MS = 20 * 60000;
    const timers = {};
    function arm(it, ms) {
      clearTimeout(timers[it.rid]);
      timers[it.rid] = setTimeout(function () {
        const waiting = function () { return items[it.rid] === it && it.state === 'retry'; };   // not dismissed, not decided meanwhile
        if (waiting() && Date.now() - it.at > RETRY_WINDOW_MS) {           // the page was closed for too long: never a surprise send
          it.state = 'refused'; toast(tx('ob_toast_refused', { name: it.name }).textContent); changed(it); return;
        }
        const go = function () { it.state = 'flight'; it.tried_at = Date.now(); changed(it); return run(it); };
        if (!waiting()) return;
        if (!(navigator.locks && navigator.locks.request)) { go(); return; }
        // two tabs hold the same outbox: one sends, the other asks again in a moment (and then gets the engine's stored reply)
        navigator.locks.request('cs.outbox.' + it.rid, { ifAvailable: true }, function (lock) {
          if (!lock) { if (waiting()) arm(it, 4000); return null; }
          return waiting() ? go() : null;
        });
      }, ms);
    }
    /** Nothing went out and the cause passes: the same rid again, later. false = out of tries (the agent decides). */
    function again(it, r) {
      const n = it.tries || 0;
      if (n >= RETRY_AFTER_MS.length || Date.now() - it.at > RETRY_WINDOW_MS) return false;
      let ms = RETRY_AFTER_MS[n];
      if (r && Number.isFinite(r.retryAfterSeconds) && r.retryAfterSeconds > 0) ms = Math.max(ms, Math.min(r.retryAfterSeconds, 600) * 1000);
      it.tries = n + 1; it.state = 'retry'; it.msg = (r && r.msg) || null; it.code = (r && r.error) || null; it.next = Date.now() + ms;
      arm(it, ms);
      return true;
    }
    function newRid() {
      if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '');
      const a = new Uint8Array(16); crypto.getRandomValues(a);
      return Array.prototype.map.call(a, function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
    }
    function save() {
      try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) { /* memory still has it */ }
    }
    function load() {
      try { items = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { items = {}; }
      const now = Date.now();
      Object.keys(items).forEach(function (r) { if (now - (items[r].at || 0) > 24 * 3600000) delete items[r]; });
    }
    function changed(it) {
      ver++;
      save();
      renderTop();
      if (it && it.brand === S.brand) {
        renderList(false);
        if (S.tk && S.tk.id === it.id) { paintBanner(); Draft.refreshSend(); EnDraft.refresh(); }
      }
    }
    function forTicket(brand, id) {
      let best = null;
      Object.keys(items).forEach(function (r) { const it = items[r]; if (!it.superseded_by && it.brand === brand && it.id === id && (!best || it.at > best.at)) best = it; });
      return best;
    }
    function blocks(brand, id) {
      const it = forTicket(brand, id);
      return !!it && (it.state === 'flight' || it.state === 'checking' || it.state === 'retry' || it.state === 'unknown' || it.state === 'delivery_issue');
    }
    function hidesRow(brand, id) {                      // a close / handled in flight or done takes the row off the list
      const it = forTicket(brand, id);
      return !!it && it.fn !== 'apiSend' && (it.state === 'flight' || it.state === 'checking' || it.state === 'retry' || it.state === 'ok');
    }
    function flagged(brand, id) {
      const it = forTicket(brand, id);
      return !!it && (it.state === 'refused' || it.state === 'unknown' || it.state === 'unsent' || it.state === 'delivery_issue');
    }
    function label(it) {
      if (!it) return '';
      const close = it.fn !== 'apiSend';
      if (it.state === 'flight') return close ? t('ob_flight_close') : t('ob_flight_send');
      if (it.state === 'checking') return t('ob_checking');
      if (it.state === 'retry') return close ? t('ob_retry_close') : t('ob_retry');
      if (it.state === 'delivery_issue') return t(it.delivery_state === 'unknown' ? 'wa_fail_unknown_note' : it.delivery_state === 'template_required' ? 'wa_fail_tpl' : 'wa_fail');
      if (it.state === 'ok') return close ? t('ob_ok_close') : it.reply && it.reply.queued ? t('ob_ok_queued') : it.channel === 'whatsapp' ? t('ob_ok_wa') : t('ob_ok_email');
      if (it.state === 'refused') return close ? t('ob_refused_close') : t('ob_refused');
      if (it.state === 'unsent') return t('ob_unsent');
      return t('ob_unknown');
    }
    function cls(it) {
      return it.state === 'ok' ? 'ok' : (it.state === 'flight' || it.state === 'checking' || it.state === 'retry') ? 'st-sent' : 'bad';
    }
    function patchRow(it) {                              // what the engine now says, before the next poll brings it
      const b = S.boots[it.brand];
      const row = b && (b.tickets || []).filter(function (x) { return x.id === it.id; })[0];
      if (!row) return;
      if (it.fn === 'apiSend') { row.status = it.reply && it.reply.queued ? 'wa_queued' : 'sent'; }
      else row.status = 'done';
      row.handled_by = S.me.user.username;
      row.handled_at = new Date().toISOString();
      delete S.tkMemo[it.brand + '|' + it.id];
    }
    function settle(it, r) {
      if (r && r.ok) {
        it.state = 'ok'; it.reply = { queued: !!r.queued, already: !!r.already }; it.msg = null; delete it.delivery_state;
        patchRow(it);
        if (it.fn === 'apiSend') { try { localStorage.removeItem('cs.draft.' + it.brand + '.' + it.id); localStorage.removeItem('cs.draft.en.' + it.brand + '.' + it.id); } catch (e) { /* ignore */ } }
        toast(tx(it.fn !== 'apiSend' ? 'ob_toast_closed' : r.queued ? 'ob_toast_queued' : 'ob_toast_ok', { name: it.name }).textContent);
        if (it.fn === 'apiSend' && r.after && typeof r.after === 'object') {
          const codes = Array.isArray(r.after.reminders) ? r.after.reminders.filter(function (c) { return typeof c === 'string' && /^[a-z_]{3,30}$/.test(c); }) : [];
          if (codes.length) { AfterSend.add({ brand: it.brand, id: it.id, name: it.name || '', codes: codes, at: Date.now() }); renderBanners(); }
          else if (r.after.cancelled) toast(t('afs_cancelled', { name: it.name || '' }));
        }
      } else if (r && (r.error === 'network' || r.error === 'server_restarted' || r.error === 'bad_response')) {
        // the connection dropped (a reload, a restart): the server is most likely still finishing it — ask it soon
        it.state = 'checking'; it.msg = null;
        later(it, 4000);
      } else if (r && (r.refresh || r.error === 'write_unknown')) {
        it.state = 'unknown'; it.msg = r.msg || null;
        toast(tx('ob_toast_unknown', { name: it.name }).textContent);
        later(it, 20000);                                // ask the server again in a moment
      } else if (r && RETRY_CODES.indexOf(r.error) >= 0 && again(it, r)) {
        // scheduled, quietly: the agent has nothing to do
      } else {
        it.state = 'refused'; it.msg = (r && (r.msg || r.error)) || null; it.err = r ? { error: r.error, problem: r.problem, problem_msg: r.problem_msg } : null;
        toast(tx('ob_toast_refused', { name: it.name }).textContent);
      }
      changed(it);
    }
    async function run(it) {
      const body = { args: it.args, rid: it.rid, lang: LANG };
      if (it.via) body.via = it.via;                       // the dashboard counts a re-send apart
      if (it.tries) body.attempt = it.tries + 1;           // the server log tells an automatic retry from a first send
      const r = await api('/api/' + encodeURIComponent(it.brand) + '/' + it.fn, body);
      if (!items[it.rid]) return;
      settle(it, r);
    }
    /** After a reload, or when the reply was lost: ask the server for the stored reply of this rid. Never resends. */
    async function check(it) {
      const r = await api('/api/' + encodeURIComponent(it.brand) + '/result', { rid: it.rid }, 'POST', { quiet: true });
      if (!items[it.rid] || (it.state !== 'checking' && it.state !== 'unknown')) return;
      if (r.ok && r.found && r.reply && typeof r.reply.ok === 'boolean') { settle(it, r.reply); return; }
      const age = Date.now() - (it.tried_at || it.at);
      if (it.state === 'checking' && age < 150000) { later(it, 6000); return; }         // the server may still be working on it
      if (it.state === 'checking') { it.state = 'unknown'; changed(it); }
      if (age < 600000) later(it, 30000);
    }
    function later(it, ms) { setTimeout(function () { if (items[it.rid]) check(it); }, ms); }
    /** A fresh ENGINE read of the ticket: decides an unknown item (never while its own request may still be running). */
    function reconcile(brand, id, tk) {
      const it = forTicket(brand, id);
      const acceptedQueue = it && (it.state === 'ok' || it.state === 'delivery_issue') && it.reply && it.reply.queued === true;
      if (!it || (!acceptedQueue && ['unknown', 'checking', 'refused', 'unsent'].indexOf(it.state) < 0) || !tk) return;
      const mine = tk.handled_by === S.me.user.username;
      const wa = (tk.channel || it.channel) === 'whatsapp';
      const waState = String(tk.wa_send || '').split(':')[0];
      const queued = wa && (waState === 'pending' || waState === 'claimed');
      const delivered = wa ? waState === 'sent' : tk.status === 'sent';
      if (acceptedQueue && !delivered) {
        const submitted = it.args && it.args.text;
        const handledAt = Date.parse(tk.handled_at || '');
        const sameAttempt = wa && mine && Number.isFinite(handledAt) && handledAt >= it.at &&
          typeof submitted === 'string' && !!submitted.trim() && submitted === tk.wa_out;
        if (sameAttempt && (queued || WA_FAIL_STATES.indexOf(waState) >= 0)) {
          const state = queued ? 'ok' : 'delivery_issue';
          const issue = queued ? null : waState;
          if (it.state !== state || (it.delivery_state || null) !== issue) {
            it.state = state; it.delivery_state = issue; changed(it);
          }
        }
        return; // Time alone cannot authorize another send after queue acceptance.
      }
      const done = it.fn === 'apiSend' ? (queued || delivered) : tk.status === 'done';
      // A previous successful send must never erase a newer failed attempt. Engine time must follow the attempt.
      const handledAt = Date.parse(tk.handled_at || '');
      if (done && mine && Number.isFinite(handledAt) && handledAt >= it.at) {
        if (it.state === 'refused' || it.state === 'unsent') {
          // This refusal did not succeed; later work resolved the ticket. Preserve the attempt and drafts.
          Object.keys(items).forEach(function (rid) {
            const old = items[rid];
            if (old.brand === brand && old.id === id && old.fn === it.fn && old.at <= handledAt &&
                (old.state === 'refused' || old.state === 'unsent')) old.superseded_by = 'engine:' + tk.handled_at;
          });
          changed(it);
        } else {
          // A newer reply by this same agent can belong to another attempt. A lost receipt is
          // recovered only from this attempt's exact text and its actual channel state.
          const isSend = it.fn === 'apiSend';
          const submitted = it.args && it.args.text;
          const sameText = typeof submitted === 'string' && !!submitted.trim() && submitted === tk[wa ? 'wa_out' : 'draft_text'];
          if (!isSend || (sameText && (queued || delivered))) settle(it, { ok: true, queued: queued });
        }
        return;
      }
      if (acceptedQueue || it.state === 'refused' || it.state === 'unsent') return;
      if (Date.now() - (it.tried_at || it.at) > 90000 && OPEN.indexOf(tk.status) >= 0) {
        // the engine says nothing went out: send it again by ourselves, and only after the last try hand it to the agent
        if (!again(it, { error: 'unsent' })) { it.state = 'unsent'; it.msg = null; }
        changed(it);
      }
    }
    function start(fn, brand, x, args, via) {
      const prev = forTicket(brand, x.id);
      if (prev && (prev.state === 'flight' || prev.state === 'checking' || prev.state === 'retry' || prev.state === 'unknown' || prev.state === 'delivery_issue')) { toast(t('ob_inflight_lock')); return null; }
      const it = { rid: newRid(), brand: brand, id: x.id, fn: fn, args: args, channel: isWA(x) ? 'whatsapp' : 'email',
        name: x.name || x.email || x.phone || x.id, state: 'flight', at: Date.now(), via: via || null };
      items[it.rid] = it;
      changed(it);
      run(it);
      return it;
    }
    function list() {
      return Object.keys(items).map(function (r) { return items[r]; })
        .filter(function (it) {
          if (it.superseded_by) return false;
          if (it.state === 'refused' || it.state === 'unsent') {
            const resolved = Object.keys(items).some(function (rid) {
              const newer = items[rid];
              return newer.brand === it.brand && newer.id === it.id && newer.fn === it.fn && newer.state === 'ok' && newer.at > it.at;
            });
            if (resolved) return false;
          }
          return it.state !== 'ok' || Date.now() - it.at < 60000;
        })
        .sort(function (a, b) { return b.at - a.at; });
    }
    function pending() { return list().filter(function (it) { return it.state !== 'ok'; }); }
    function dismiss(it) { clearTimeout(timers[it.rid]); delete timers[it.rid]; delete items[it.rid]; changed(it); }
    function paintBanner() {
      const slot = document.getElementById('tk-outbox');
      if (!slot || !S.tk) return;
      clear(slot);
      const it = forTicket(S.tk.brand, S.tk.id);
      if (!it || (it.state === 'ok' && Date.now() - it.at > 15 * 60000)) return;
      const box = h('div', { class: 'outbox-banner ' + cls(it), role: 'status', 'data-test': 'outbox-banner', 'data-state': it.state }, h('b', { text: label(it) }));
      if (it.msg && it.state !== 'ok') box.append(h('div', { class: 'small' }, t('ob_why') + ' ', h('span', { dir: 'auto', text: it.msg })));
      if (it.state === 'retry') box.append(h('div', { class: 'small', 'data-test': 'outbox-retry-n', text: t('ob_retry_n', { n: it.tries, max: RETRY_AFTER_MS.length }) }));
      if (it.state === 'refused' || it.state === 'unsent' || it.state === 'retry') box.append(h('button', { class: 'btn small ghost', type: 'button', text: '✕', 'aria-label': 'dismiss', onclick: function () { dismiss(it); } }));
      slot.append(box);
    }
    async function recoverFailures() {
      // One read at a time, once per ticket on boot. Old tickets can be absent from the latest list page.
      const candidates = pending().filter(function (it) {
        return forTicket(it.brand, it.id) === it && ['refused', 'unsent', 'unknown', 'checking', 'delivery_issue'].indexOf(it.state) >= 0;
      });
      for (const it of candidates) {
        if (forTicket(it.brand, it.id) !== it) continue;
        const r = await api('/api/' + encodeURIComponent(it.brand) + '/ticket', { id: it.id, revalidate: true }, 'POST', { quiet: true });
        if (r.ok && r.ticket && (!(r.cache && r.cache.hit) || guardFresh(r))) reconcile(it.brand, it.id, r.ticket);
      }
    }
    function boot() {
      load();
      Object.keys(items).forEach(function (r) {
        const it = items[r];
        if (it.state === 'flight') { it.state = 'checking'; later(it, 1500); }     // the page died mid-send: ask, never resend
        else if (it.state === 'checking' || it.state === 'unknown') later(it, 1500);
        else if (it.state === 'retry') arm(it, Math.max(1500, (it.next || 0) - Date.now()));   // the page closed between tries: go on
      });
      save();
      setTimeout(recoverFailures, 2000);
    }
    return { start: start, forTicket: forTicket, blocks: blocks, hidesRow: hidesRow, flagged: flagged, label: label, cls: cls,
      list: list, pending: pending, reconcile: reconcile, paintBanner: paintBanner, boot: boot, ver: function () { return ver; } };
  })();

  /** After a hand-off: the next ticket of the current tab (or the list), within a frame. */
  function goNext(brand, fromId) {
    if (brand !== S.brand) return;
    const tab = ['ready', 'action', 'failed', 'wa24', 'health', 'delay', 'bot'].indexOf(S.tab) >= 0 ? S.tab : null;
    const rows = tab ? (rowsFor(tab) || []).filter(function (x) { return !isOld(x) && !Outbox.blocks(brand, x.id) && !Outbox.hidesRow(brand, x.id); }) : [];
    const all = tab ? (rowsFor(tab) || []).filter(function (x) { return !isOld(x); }) : [];
    const pos = all.map(function (x) { return x.id; }).indexOf(fromId);
    const after = rows.filter(function (x) { return all.map(function (y) { return y.id; }).indexOf(x.id) > pos && x.id !== fromId; });
    const next = after[0] || rows.filter(function (x) { return x.id !== fromId; })[0];
    if (next) go(ticketHash(next.id)); else go(listHash(tab || 'ready'));
  }

  // ---------------------------------------------------------------- automatic cancellations queue
  async function loadAuto(brand) {
    // shared per brand on the server (cached 45 s, background priority): never takes an agent's engine slot
    const r = await api('/api/' + encodeURIComponent(brand) + '/queue', { fn: 'apiAutoCancelList' }, 'POST', { quiet: true });
    if (r.ok && r.deferred) { if (!S.auto[brand]) setTimeout(function () { loadAuto(brand); }, 20000); return; }
    // An engine without these functions answers "unauthorized" (Api.gs gives no function-name oracle).
    if (r.ok && !Array.isArray(r.items)) return;
    if (r.ok) S.auto[brand] = { items: r.items, switch: r.switch || null, mode: r.mode || null };
    else if (r.error === 'unauthorized' || r.error === 'forbidden_fn') S.auto[brand] = { items: null, unavailable: true };
    else S.auto[brand] = { items: (S.auto[brand] && S.auto[brand].items) || null, err: r.msg || r.error };
    if (brand === S.brand) { renderBanners(); renderTabs(); if (S.tab === 'auto') renderList(false); }
  }

  const AutoCancel = (function () {
    // State classes — engine contract (coordinator, 2026-10-05).
    const APPROVABLE = ['shadow_would_cancel', 'aborted_newer', 'refused'];
    const IN_FLIGHT = ['queued', 'cancelling', 'cancelled', 'replying'];
    const editing = {};     // key -> true while the agent has unsaved reply edits / an open manual note
    function inFlight(st) { return IN_FLIGHT.indexOf(String(st || '')) >= 0; }
    function kind(st) {
      st = String(st || '');
      if (APPROVABLE.indexOf(st) >= 0) return 'approvable';
      if (IN_FLIGHT.indexOf(st) >= 0) return 'flight';
      if (st === 'cancelled_reply_failed') return 'reply_failed';
      return 'stopped';          // aborted_*, failed_*, recovered_*, anything new: show the error, never approve
    }
    function key(id) { return S.brand + '|' + id; }
    function busy() { return Object.keys(editing).some(function (k) { return editing[k] && k.indexOf(S.brand + '|') === 0; }); }
    function ticketIdOf(it) {
      const v = it.ticketId || it.id;
      return v && /^[A-Za-z0-9_-]{1,80}$/.test(String(v)) ? String(v) : null;
    }
    function paint(slot, text) { if (slot && slot.isConnected) { clear(slot); add(slot, text ? messageBody(text) : h('span', { class: 'muted small', text: '—' })); } }
    async function fetchMessage(it, slot) {
      const tid = ticketIdOf(it);
      if (!tid) { paint(slot, ''); return; }
      const mk = S.brand + '|' + tid;
      if (typeof S.autoMsg[mk] === 'string') { paint(slot, S.autoMsg[mk]); return; }
      if (S.autoMsg[mk] === null) return;               // a fetch is already running; it paints the live node
      S.autoMsg[mk] = null;
      const r = await fetchTicket(S.brand, tid, false);
      const conv = (r.ok && r.extras && r.extras.conversation) || [];
      const last = conv.filter(function (m) { return m.who === 'customer'; }).pop();
      S.autoMsg[mk] = last ? String(last.text || '') : '';
      const live = document.querySelector('.ac-item[data-id="' + CSS.escape(String(it.id)) + '"] .ac-msg');
      paint(live || slot, S.autoMsg[mk]);
    }
    function passed(v) { return v === true || /^(pass|ok|true|yes|verified)$/i.test(String(v)); }
    function evidenceText(ev) {
      ev = ev || {};
      const parts = [];
      if (ev.dkim !== undefined || ev.spf !== undefined) {
        const ok = passed(ev.dkim) && passed(ev.spf);
        parts.push(ok ? t('ac_ev_auth_ok') : t('ac_ev_auth_bad') + ' ' + t('ac_ev_auth_detail', { d: '\u2068' + String(ev.dkim) + '\u2069', s: '\u2068' + String(ev.spf) + '\u2069' }));
      }
      if (ev.contractCount !== undefined) {
        const n = Number(ev.contractCount);
        if (!isNaN(n)) parts.push(n === 1 ? t('ac_ev_one') : n === 0 ? t('ac_ev_none') : t('ac_ev_many', { n: n }));
      }
      if (ev.modelReason) parts.push(t('ac_ev_reason_ok'));     // a record exists only after the model classed the request as a lone cancel
      return parts.join(' · ');
    }
    function stateText(it) {
      const st = String(it.state || '');
      if (st === 'queued') return it.dueAt ? t('ac_state_queued', { when: ago(it.dueAt) }) : t('ac_state_queued_nodue');
      let k = 'ac_state_' + st;
      if (/^failed_/.test(st)) k = 'ac_state_failed';
      if (/^recovered_/.test(st)) k = 'ac_state_recovered';
      const v = t(k);
      if (v === k) return st;
      return k === 'ac_state_' + st ? v : v + ' (' + st + ')';
    }
    function itemEl(it) {
      const k = key(it.id);
      const kd = kind(it.state);
      const card = h('div', { class: 'card ac-item ac-' + kd, 'data-id': it.id, 'data-state': it.state });
      if (LANG === 'en') {
        const tid = ticketIdOf(it);
        card.append(h('div', { class: 'hd' }, h('span', { class: 'chip outline', text: stateText(it) }), h('bdi', { text: it.email || tid || '—' })),
          h('p', { text: 'Open the translated conversation to review this cancellation and reply in English. Customer replies are sent in Hebrew.' }));
        if (tid) card.append(h('a', { class: 'btn primary', href: '#/b/' + encodeURIComponent(S.brand) + '/t/' + encodeURIComponent(tid), text: 'Open English conversation' }));
        return card;
      }
      const chipCls = kd === 'approvable' ? 'st-action' : kd === 'flight' ? 'st-sent' : 'bad';
      card.append(h('div', { class: 'hd' },
        kd === 'flight' ? h('span', { class: 'spinner', 'aria-hidden': 'true' }) : null,
        h('span', { class: 'chip ' + chipCls, text: stateText(it) }),
        it.approvedBy ? h('span', { class: 'chip outline' }, tx('ac_approved_by', { u: it.approvedBy })) : null,
        it.ticketStatus ? h('span', { class: 'chip outline', text: t('ac_ticket_status', { s: t('st_' + it.ticketStatus) }) }) : null,
        it.email ? h('bdi', { class: 'ltr muted small', text: it.email }) : null));
      if (it.subject || it.summary) card.append(h('div', null, it.subject ? h('b', { dir: 'auto', text: it.subject }) : null, it.summary ? h('div', { class: 'small', dir: 'auto', text: it.summary }) : null));
      if (kd === 'reply_failed') card.append(h('div', { class: 'err-box', role: 'alert' }, h('b', { text: t('ac_state_cancelled_reply_failed') }), it.error ? h('bdi', { class: 'raw', text: String(it.error) }) : null));
      else if (kd === 'stopped' && it.error) card.append(h('div', { class: 'err-box' }, h('bdi', { class: 'raw', text: String(it.error) })));
      const msgSlot = h('div', { class: 'msg customer ac-msg' }, h('span', { class: 'muted small', text: t('loading') }));
      card.append(h('div', { class: 'small muted', text: t('ac_last_msg') }), msgSlot);
      fetchMessage(it, msgSlot);
      card.append(h('dl', { class: 'kv' },
        h('dt', { text: t('ac_contract') }), h('dd', null, h('bdi', { class: 'ltr', text: contractNum(it.contractId) || '—' })),
        h('dt', { text: t('ac_next') }), h('dd', { text: it.nextBilling ? fmtDate(it.nextBilling) : '—' })));
      const ev = evidenceText(it.evidence);
      if (ev) card.append(h('div', { class: 'evidence', text: ev }));
      if (it.evidence && it.evidence.modelReason) card.append(h('div', { class: 'small muted' }, t('ac_model') + ': ', h('span', { dir: 'auto', text: String(it.evidence.modelReason) })));
      const orig = String(it.replyText || '');
      const ta = h('textarea', { dir: 'auto', rows: '4', 'aria-label': t('ac_reply'), readOnly: kd !== 'approvable' });
      ta.value = S.autoEdits[k] !== undefined && kd === 'approvable' ? S.autoEdits[k] : orig;
      ta.addEventListener('input', function () { S.autoEdits[k] = ta.value; editing[k] = ta.value !== orig; });
      add(card, [h('label', { class: 'small muted', text: t('ac_reply') }), h('div', { class: 'draft' }, ta),
        kd === 'reply_failed' && orig ? h('div', { class: 'actions' }, copyBtn(orig)) : null]);
      if (kd === 'flight' || kd === 'reply_failed') return card;      // in flight / already cancelled: no buttons
      const res = h('div');
      const approve = kd === 'approvable' ? h('button', { class: 'btn primary', type: 'button', text: t('ac_approve') }) : null;
      const manual = h('button', { class: 'btn', type: 'button', text: t('ac_manual') });
      const noteRow = h('div', { class: 'note-add', hidden: true });
      const note = h('input', { type: 'text', placeholder: t('ac_note_ph'), maxlength: '300', dir: 'auto' });
      const noteGo = h('button', { class: 'btn small', type: 'button', text: t('ac_manual_go') });
      noteRow.append(note, noteGo);
      function lockAll(on) { [approve, manual, noteGo, note].forEach(function (b) { if (b) b.disabled = on; }); if (approve) ta.readOnly = on; }
      function refused(r) {
        clear(res);
        res.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || t('ac_refused') }),
          h('bdi', { class: 'raw', text: [r.error, r.state, r.reason, r.problem].filter(Boolean).join(' · ') })));
      }
      if (approve) approve.addEventListener('click', async function () {
        const yes = await confirmDlg({ title: t('ac_approve_q'), body: t('ac_approve_body'), ok: t('ac_approve'), danger: true });
        if (!yes) return;
        lockAll(true);
        const args = { id: it.id };
        if (ta.value !== orig) args.replyText = ta.value;
        const r = await engine('apiAutoCancelApprove', args);
        lockAll(false);
        if (!r.ok) { refused(r); return; }
        delete editing[k]; delete S.autoEdits[k];
        toast(t('ac_ok'));
        loadAuto(S.brand);
      });
      manual.addEventListener('click', function () { noteRow.hidden = false; editing[k + '#note'] = true; note.focus(); });
      noteGo.addEventListener('click', async function () {
        const n = note.value.trim();
        if (n.length < 2 || n.length > 300) { clear(res); res.append(h('div', { class: 'err-box', text: t('ac_note_req') })); return; }
        lockAll(true);
        const r = await engine('apiAutoCancelReject', { id: it.id, note: n });
        lockAll(false);
        if (!r.ok) { refused(r); return; }
        delete editing[k]; delete editing[k + '#note']; delete S.autoEdits[k];
        toast(t('ac_moved'));
        loadAuto(S.brand);
      });
      card.append(h('div', { class: 'actions' }, approve, manual), noteRow, res);
      return card;
    }
    function render(lp) {
      clear(lp);
      const a = S.auto[S.brand];
      if (!a) { for (let i = 0; i < 3; i++) lp.append(h('div', { class: 'skeleton' })); return; }
      if (a.unavailable) { lp.append(h('div', { class: 'empty' }, h('b', { text: t('auto_na') }))); return; }
      if (a.err) lp.append(h('div', { class: 'err-box', text: a.err }));
      if (!a.items) return;
      lp.append(h('div', { class: 'list-meta' }, h('span', { text: brandName(S.brand) + ' · ' + t('tab_auto') }),
        a.mode ? h('span', { text: t('ac_mode', { m: t('mode_' + a.mode) }) }) : null));
      if (!a.items.length) { lp.append(h('div', { class: 'empty' }, h('b', { text: t('empty_auto') }), h('span', { text: t('empty_hint') }))); return; }
      const order = { approvable: 0, reply_failed: 1, stopped: 2, flight: 3 };
      a.items.slice().sort(function (x, y) { return order[kind(x.state)] - order[kind(y.state)]; }).forEach(function (it) { lp.append(itemEl(it)); });
    }
    return { render: render, busy: busy, inFlight: inFlight };
  })();

  // ---------------------------------------------------------------- automatic replies — human review (Owner, 2026-10-05)
  const AutoReply = (function () {
    const editing = {};
    const trCache = {};
    function busy() { return Object.keys(editing).some(function (k) { return editing[k] && k.indexOf(S.brand + '|') === 0; }); }
    async function load(brand) {
      const r = await api('/api/' + encodeURIComponent(brand) + '/queue', { fn: 'apiAutoReplyList' }, 'POST', { quiet: true });
      if (r.ok && r.deferred) { if (!S.ar[brand]) setTimeout(function () { load(brand); }, 20000); return; }
      if (r.ok && !Array.isArray(r.items)) return;              // a reply without items is not "empty": keep what we have
      if (r.ok) {
        S.ar[brand] = { items: r.items, switch: r.switch || null, mode: r.mode || null };
        const ids = S.ar[brand].items.filter(function (x) { return x.review === 'pending'; }).map(function (x) { return x.ticketId || x.id; });
        if (ids.length) api('/api/' + encodeURIComponent(brand) + '/prefetch', { ids: ids.slice(0, 15) }, 'POST', { quiet: true });   // questions load warm
      }
      else if (r.error === 'unauthorized' || r.error === 'forbidden_fn') S.ar[brand] = { items: null, unavailable: true };
      else S.ar[brand] = { items: (S.ar[brand] && S.ar[brand].items) || null, err: r.msg || r.error };
      if (brand === S.brand) { renderBanners(); renderTabs(); renderList(false); }
    }
    function stateChip(it) {
      const st = String(it.state || '');
      if (st === 'sent') return h('span', { class: 'chip bot', text: t('ar_label') });
      if (/^shadow/.test(st)) return h('span', { class: 'chip st-sent', text: t('ar_label_shadow') });
      if (st === 'queued') return h('span', { class: 'chip st-action' }, tx('ar_label_queued', { when: it.dueAt ? ago(it.dueAt) : '' }));
      if (/fail/.test(st)) return h('span', { class: 'chip bad', text: t('ar_failed') });
      return h('bdi', { class: 'chip outline', text: st || '—' });
    }
    function reviewChip(it) {
      if (it.review === 'ok') return h('span', { class: 'chip ok' }, tx('ar_reviewed_ok', { u: it.reviewedBy || '—' }));
      if (it.review === 'problem') return h('span', { class: 'chip bad' }, tx('ar_reviewed_problem', { u: it.reviewedBy || '—' }));
      return h('span', { class: 'chip st-action', text: t('ar_pending') });
    }
    async function question(it, slot) {
      if (it.question || it.lastMessage) { clear(slot); add(slot, messageBody(it.question || it.lastMessage)); return; }
      const mk = S.brand + '|' + (it.ticketId || it.id);
      if (typeof S.autoMsg[mk] === 'string') { clear(slot); add(slot, S.autoMsg[mk] ? messageBody(S.autoMsg[mk]) : '—'); return; }
      const r = await fetchTicket(S.brand, it.ticketId || it.id, false);
      const conv = (r.ok && r.extras && r.extras.conversation) || [];
      const last = conv.filter(function (m) { return m.who === 'customer'; }).pop();
      S.autoMsg[mk] = last ? String(last.text || '') : '';
      const live = document.querySelector('.ar-item[data-id="' + CSS.escape(String(it.id)) + '"] .ar-q');
      const el = live || slot;
      if (el && el.isConnected) { clear(el); add(el, S.autoMsg[mk] ? messageBody(S.autoMsg[mk]) : '—'); }
    }
    async function translate(it, card) {
      if (LANG !== 'en') return;
      const key = S.brand + '|' + it.id;
      let tr = trCache[key];
      if (!tr) {
        const r = await api('/api/' + encodeURIComponent(S.brand) + '/translate-autoreply', { id: it.id });
        if (!r.ok) return;
        tr = trCache[key] = r;
      }
      if (!card.isConnected) return;
      [['.ar-q', 'question'], ['.ar-reply', 'reply'], ['.ar-sum', 'summary']].forEach(function (p) {
        const el = card.querySelector(p[0]);
        if (!el || !tr[p[1]] || el.dataset.tr) return;
        el.dataset.tr = '1';
        const host = card.querySelector(p[0] + '-tg');
        if (p[0] === '.ar-sum') { const orig = el.textContent; clear(el); el.classList.add('summary-line'); bilingual(el, orig, tr[p[1]], host); }
        else bilingual(el, el.dataset.orig || el.textContent, tr[p[1]], host);
      });
    }
    function itemEl(it) {
      const k = S.brand + '|' + it.id;
      const tid = it.ticketId || it.id;
      const shadow = /^shadow/.test(String(it.state || ''));
      const card = h('div', { class: 'card ar-item', 'data-id': it.id, 'data-test': 'ar-item' });
      const when = it.sentAt || it.dueAt;
      card.append(h('div', { class: 'hd' }, stateChip(it), reviewChip(it),
        when && it.sentAt ? h('span', { class: 'muted small' }, tx('ar_sent_at', { when: fmtDate(when, true) })) : null,
        it.email ? h('bdi', { class: 'ltr muted small', text: it.email }) : null));
      card.append(h('div', null, it.subject ? h('b', { dir: 'auto', text: it.subject }) : null,
        it.summary ? h('div', { class: 'small ar-sum', dir: 'auto', text: it.summary }) : null, h('span', { class: 'ar-sum-tg' })));
      const q = h('div', { class: 'msg customer ar-q' }, h('span', { class: 'muted small', text: t('loading') }));
      card.append(h('div', { class: 'small muted ar-lbl' }, t('ar_question'), h('span', { class: 'ar-q-tg' })), q);
      question(it, q);
      const reply = h('div', { class: 'msg us ar-reply', 'data-orig': String(it.replyText || '') });
      add(reply, messageBody(String(it.replyText || '—')));
      card.append(h('div', { class: 'small muted ar-lbl' }, shadow ? t('ar_reply_shadow') : t('ar_reply'), h('span', { class: 'ar-reply-tg' })), reply);
      if (it.error) card.append(h('div', { class: 'err-box' }, h('bdi', { class: 'raw', text: String(it.error) })));
      const res = h('div');
      const actions = h('div', { class: 'actions' });
      const open = h('a', { class: 'btn ghost small', href: ticketHash(tid), text: t('ar_open'), 'data-test': 'ar-open' });
      if (it.review === 'pending' && !/fail/.test(String(it.state || ''))) {
        const okBtn = h('button', { class: 'btn primary', type: 'button', text: t('ar_ok'), 'data-test': 'ar-ok' });
        const probBtn = h('button', { class: 'btn danger-outline', type: 'button', text: t('ar_problem'), 'data-test': 'ar-problem' });
        const noteRow = h('div', { class: 'note-add', hidden: true });
        const note = h('input', { type: 'text', placeholder: t('ar_note_ph'), maxlength: '300', dir: 'auto' });
        const go = h('button', { class: 'btn small danger', type: 'button', text: t('ar_problem_go') });
        noteRow.append(note, go);
        function lockAll(on) { [okBtn, probBtn, go, note].forEach(function (b) { b.disabled = on; }); }
        async function review(verdict, n) {
          lockAll(true);
          clear(res);
          const args = { id: it.id, verdict: verdict };
          if (n) args.note = n;
          const r = await engine('apiAutoReplyReview', args);
          lockAll(false);
          if (!r.ok) { res.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error }), h('bdi', { class: 'raw', text: String(r.error || '') }))); return; }
          delete editing[k];
          it.review = verdict; it.reviewedBy = S.me.user.username;        // optimistic; the reload below confirms
          toast(verdict === 'ok' ? t('ar_done_ok') : t('ar_done_problem'));
          if (verdict === 'problem') { delete S.tkMemo[S.brand + '|' + tid]; pollChanges(S.brand); }
          load(S.brand);
        }
        okBtn.addEventListener('click', function () { review('ok'); });
        probBtn.addEventListener('click', function () { noteRow.hidden = false; editing[k] = true; note.focus(); });
        go.addEventListener('click', function () {
          const n = note.value.trim();
          if (n.length < 2) { clear(res); res.append(h('div', { class: 'err-box', text: t('ac_note_req') })); return; }
          review('problem', n);
        });
        actions.append(okBtn, probBtn, open);
        card.append(actions, noteRow, res);
      } else {
        actions.append(open);
        card.append(actions);
      }
      translate(it, card);
      return card;
    }
    function render(lp) {
      clear(lp);
      const a = S.ar[S.brand];
      if (!a) { for (let i = 0; i < 3; i++) lp.append(h('div', { class: 'skeleton' })); return; }
      if (a.unavailable) { lp.append(h('div', { class: 'empty' }, h('b', { text: t('ar_na') }))); return; }
      if (a.err) lp.append(h('div', { class: 'err-box', text: a.err }));
      if (!a.items) return;
      lp.append(h('div', { class: 'list-meta' }, h('span', { text: brandName(S.brand) + ' · ' + t('tab_autoreply') }),
        a.mode ? h('span', { text: t('ar_mode', { m: t('mode_' + a.mode) }) }) : null));
      if (!a.items.length) { lp.append(h('div', { class: 'empty' }, h('b', { text: t('empty_autoreply') }), h('span', { text: t('empty_hint') }))); return; }
      const rank = function (x) { return x.review === 'pending' ? 0 : x.review === 'problem' ? 1 : 2; };
      a.items.slice().sort(function (x, y) {
        return rank(x) - rank(y) || (ms(y.sentAt || y.dueAt) || 0) - (ms(x.sentAt || x.dueAt) || 0);
      }).forEach(function (it) { lp.append(itemEl(it)); });
    }
    return { load: load, render: render, busy: busy };
  })();

  // ---------------------------------------------------------------- system mode (admin)
  // ---------------------------------------------------------------- managers' dashboard (Owner, 2026-10-06)
  /** Admin + user-manager only (the server answers 403 to anyone else). Real work time from the activity log: actions
   *  at most 5 min apart are one session; being logged in is not work. Charts are plain SVG (strict CSP, no libraries). */
  const Dash = (function () {
    const HE = {
      title: 'לוח מנהלים', day: 'יום', d7: '7 ימים', d30: '30 ימים', updated: 'עודכן', loading: 'טוען…',
      method: 'זמן עבודה = פעולות ברצף (פתיחה, עריכה, שליחה, סגירה). הפסקה של יותר מ-{m} דק׳ מסיימת רצף. זמן מחובר למסך לא נספר כעבודה.',
      since: 'יומן הפעילות נאסף מ-{d}', received: 'נכנסו היום', answered: 'נענו', closed: 'נסגרו', of: 'מהנכנסות',
      open_now: 'פתוחות עכשיו', awaiting: 'ממתינות למענה', frt: 'זמן למענה ראשון (חציון)', frt_human: 'מענה ראשון של אדם (חציון)',
      incl_bot: 'כולל בוט: {v}', human_pending: 'ממתין לנתון מהמנוע', gmail_blocked: 'מייל: גוגל חסם זמנית — יתעדכן',
      gmail_error: 'מייל: שגיאה בקריאה מג׳ימייל — יתעדכן', wa_only: 'וואטסאפ בלבד', frt_human_all: 'מענה ראשון של אדם', auto_pct: 'מענה אוטומטי',
      wa_failed: 'כשלי שליחה בוואטסאפ', aging: 'גיל הממתינות', partial: 'חלקי: הרשימה מחזיקה רק 100 סגורות אחרונות',
      src_snapshot: 'תמונת חצות', src_rebuilt: 'שוחזר מהרשימה הנוכחית', kpis: 'מדדים מול השוק (2026)',
      frt_email: 'מענה ראשון — מייל', frt_wa: 'מענה ראשון — וואטסאפ', aht: 'זמן טיפול לתשובה (AHT)', fcr: 'פתרון במענה אחד (קירוב)',
      reopen: 'נפתחו מחדש', occ: 'ניצולת (פעיל ÷ מחובר)', backlog: 'בקלוג', sla_wa: 'וואטסאפ נענה תוך שעה', sla_email: 'מייל נענה תוך 24 ש׳',
      csat: 'שביעות רצון (CSAT)', csat_missing: 'חסר — אין סקר שביעות רצון', bench: 'יעד', n_a: 'אין עדיין נתונים',
      fcr_note: 'חלון 72 השעות עוד פתוח', agents: 'נציגים', agent: 'נציג', active: 'זמן עבודה', replies: 'תשובות', closes: 'סגירות',
      per_hour: 'תשובות לשעת עבודה', engine: 'במנוע', none: 'אין פעילות בטווח', by_brand: 'לפי מותג', by_channel: 'לפי ערוץ',
      heat: 'מתי עובדים בפועל', heat_all: 'כל הנציגים', heat_total: 'סה״כ לפי שעה', pies: 'חלוקה', pie_brand: 'זמן עבודה לפי מותג',
      pie_chan: 'לפי ערוץ', pie_cat: 'לפי נושא', pie_who: 'מי ענה', agents_w: 'נציגים', auto_w: 'מענה אוטומטי', email: 'מייל', whatsapp: 'וואטסאפ',
      h: 'ש׳', m: 'דק׳', s: 'שנ׳', resends: 'מתוכן שליחה חוזרת', per_day: 'לפי יום', present: 'מחובר',
      fixing: 'הנתונים בתיקון — לא סופיים', fixing_sub: 'נציגים עונים גם ישירות בדונדי ובג׳ימייל; המספרים יעברו לחישוב מהשיחות עצמן במנוע.',
      onscreen: 'פעילות במסך', log_word: 'ביומן', ds_age: 'לפני {m} דק׳', ds_updating: 'מתעדכן…', missing: 'עוד לא מהשיחות — לא סופי: {b}', from_conv: 'מהשיחות', computing: 'מחשב מהשיחות…',
      src_answered: 'נענו — לפי מקור', src_closed: 'נסגרו — לפי מקור', src_fromSystem: 'מהמערכת', src_fromDondy: 'מדונדי', src_fromEmail: 'מהמייל',
      sub_agent: 'נציג', sub_auto: 'אוטומטי', sub_human: 'אדם', sub_bot: 'בוט', sub_template: 'תבנית', sub_close: 'סגירה', sub_direct: 'ישיר', total: 'סה״כ',
      conv_answered: 'ענו (מהשיחות)', direct_note: 'בלי שם נציג: ישירות בדונדי {d} · ישירות במייל {g} · אוטומטי {a} · בוט ותבניות {b}', others: 'אחרים', all_brands: 'כל המותגים', brand_col: 'מותג', idle_agents: '{n} משתמשים בלי פעילות בטווח', log_new: 'יומן הפעילות עוד ריק — זמן העבודה נספר מהפעולה הבאה של כל נציג; תשובות וסגירות כבר נספרות מהמנוע.'
    };
    const EN = {
      title: 'Managers', day: 'Day', d7: '7 days', d30: '30 days', updated: 'Updated', loading: 'Loading…',
      method: 'Work time = consecutive actions (open, edit, send, close). A gap over {m} min ends a session. Being logged in is not work.',
      since: 'Activity log collected since {d}', received: 'Received today', answered: 'Answered', closed: 'Closed', of: 'of received',
      open_now: 'Open now', awaiting: 'Awaiting a reply', frt: 'First reply (median)', frt_human: 'First reply by a person (median)',
      incl_bot: 'incl. bot: {v}', human_pending: 'waiting for the engine field', gmail_blocked: 'Email: temporarily blocked by Google — will update',
      gmail_error: 'Email: Gmail read failed — will update', wa_only: 'WhatsApp only', frt_human_all: 'First reply by a person', auto_pct: 'Auto-replies',
      wa_failed: 'WhatsApp send failures', aging: 'Backlog age', partial: 'Partial: the list holds only the last 100 closed',
      src_snapshot: 'Midnight snapshot', src_rebuilt: 'Rebuilt from the current list', kpis: 'KPIs vs 2026 benchmarks',
      frt_email: 'First reply — email', frt_wa: 'First reply — WhatsApp', aht: 'Handle time per reply (AHT)', fcr: 'First-contact resolution (proxy)',
      reopen: 'Reopened', occ: 'Occupancy (active ÷ logged in)', backlog: 'Backlog', sla_wa: 'WhatsApp answered within 1h', sla_email: 'Email answered within 24h',
      csat: 'CSAT', csat_missing: 'Missing — no satisfaction survey', bench: 'Target', n_a: 'No data yet',
      fcr_note: 'the 72h window is still open', agents: 'Agents', agent: 'Agent', active: 'Work time', replies: 'Replies', closes: 'Closed',
      per_hour: 'Replies per work hour', engine: 'engine', none: 'No activity in range', by_brand: 'By brand', by_channel: 'By channel',
      heat: 'When they actually work', heat_all: 'All agents', heat_total: 'Total per hour', pies: 'Split', pie_brand: 'Work time by brand',
      pie_chan: 'By channel', pie_cat: 'By topic', pie_who: 'Who answered', agents_w: 'Agents', auto_w: 'Auto-reply', email: 'Email', whatsapp: 'WhatsApp',
      h: 'h', m: 'min', s: 's', resends: 'of them re-sends', per_day: 'Per day', present: 'Logged in',
      fixing: 'The numbers are being fixed — not final', fixing_sub: 'Agents also answer directly in Dondy and Gmail; the numbers will move to the engine\'s count from the conversations.',
      onscreen: 'On-screen activity', log_word: 'log', ds_age: '{m} min ago', ds_updating: 'updating…', missing: 'Not from the conversations yet — not final: {b}', from_conv: 'from conversations', computing: 'Counting from conversations…',
      src_answered: 'Answered — by source', src_closed: 'Closed — by source', src_fromSystem: 'From the system', src_fromDondy: 'From Dondy', src_fromEmail: 'From email',
      sub_agent: 'agent', sub_auto: 'auto', sub_human: 'person', sub_bot: 'bot', sub_template: 'template', sub_close: 'close', sub_direct: 'direct', total: 'Total',
      conv_answered: 'Answered (conversations)', direct_note: 'No agent name: directly in Dondy {d} · directly in email {g} · auto {a} · bot and templates {b}', others: 'Others', all_brands: 'All brands', brand_col: 'Brand', idle_agents: '{n} users with no activity in range', log_new: 'The activity log is still empty — work time counts from each agent\'s next action; replies and closes are already counted from the engine.'
    };
    const L = LANG === 'en' ? EN : HE;
    // Owner, 2026-10-07: did every ticket written to before the desk closed get an answer + labels that say what each number counts
    Object.assign(L, LANG === 'en' ? {
      sv_title: 'Written to before {h}:00 — answered?', sv_def: 'Tickets with a customer message on {d} before the desk closed ({h}:00), by what followed the customer\'s LAST message of the service hours. A reply after it covers the earlier messages too.',
      sv_received: 'Received by {h}:00', sv_person: 'A person answered', sv_auto: 'Only a bot / auto-reply', sv_closed: 'Closed / no answer needed', sv_unanswered: 'No answer',
      sv_all_ok: 'Every ticket got an answer', sv_list: '{b}: {n} with no answer', sv_more: 'and {n} more (the list holds the first {m})', sv_wait: 'Not counted yet (updating): {b}',
      sv_mail_off: 'Email not counted (Gmail blocked): {b}', sv_since: 'waiting since {t}', awaiting_today: 'Awaiting (of today\'s)', aging_all: 'Age of all open tickets ({n})',
      last_day_only: 'The brand cards and the sources below show {d} only; agents, KPIs and charts cover the whole range.'
    } : {
      sv_title: 'פניות שנכנסו עד {h}:00 — קיבלו מענה?', sv_def: 'פניות שלקוח כתב בהן ב-{d} לפני סגירת השירות ({h}:00), לפי מה שקרה אחרי ההודעה האחרונה שלו בשעות השירות. תשובה אחריה מכסה גם את ההודעות שלפניה.',
      sv_received: 'נכנסו עד {h}:00', sv_person: 'ענה אדם', sv_auto: 'רק בוט / מענה אוטומטי', sv_closed: 'נסגרו / לא דורשות תשובה', sv_unanswered: 'בלי מענה',
      sv_all_ok: 'כל הפניות קיבלו מענה', sv_list: '{b}: {n} בלי מענה', sv_more: 'ועוד {n} (ברשימה {m} הראשונות)', sv_wait: 'עוד לא נספר (מתעדכן): {b}',
      sv_mail_off: 'מייל לא נספר (ג׳ימייל חסום): {b}', sv_since: 'ממתינה מ-{t}', awaiting_today: 'ממתינות למענה (מהיום)', aging_all: 'גיל כל הפתוחות ({n})',
      last_day_only: 'כרטיסי המותגים והמקורות מציגים את {d} בלבד; נציגים, מדדים וגרפים מכסים את כל הטווח.'
    });
    function d(k, v) { let s = L[k] || k; Object.keys(v || {}).forEach(function (x) { s = s.replace('{' + x + '}', v[x]); }); return s; }
    const st = { range: '1', date: '', data: null, err: null, busy: false, who: 'all' };
    let timer = null;
    function fmtS(sec) {
      if (sec === null || sec === undefined) return '—';
      sec = Math.round(sec);
      if (sec < 60) return sec + ' ' + L.s;
      if (sec < 3600) return Math.round(sec / 60) + ' ' + L.m;
      const hh = Math.floor(sec / 3600), mm = Math.round((sec % 3600) / 60);
      return hh + ':' + (mm < 10 ? '0' : '') + mm + ' ' + L.h;
    }
    function pctS(p) { return p === null || p === undefined ? '—' : p + '%'; }
    const NS = 'http://www.w3.org/2000/svg';
    function sv(tag, attrs, kids) {
      const el = document.createElementNS(NS, tag);
      Object.keys(attrs || {}).forEach(function (k) { if (attrs[k] !== null && attrs[k] !== undefined) el.setAttribute(k, String(attrs[k])); });
      (kids || []).forEach(function (c) { if (c) el.append(c); });
      return el;
    }
    function catName(c) { const v = t('cat_' + c); return v === 'cat_' + c ? c : v; }
    function nameOf(kind, k) { return kind === 'brand' ? brandName(k) : kind === 'channel' ? L[k] || k : kind === 'category' ? catName(k) : kind === 'src' ? L['src_' + k] || k : L[k + '_w'] || k; }
    /** Donut + legend. data {key: value}; nothing -> a quiet "no data". */
    function pie(title, kind, data, unit) {
      const keys = Object.keys(data || {}).filter(function (k) { return data[k] > 0; }).sort(function (a, b) { return data[b] - data[a]; });
      const total = keys.reduce(function (a, k) { return a + data[k]; }, 0);
      const box = h('div', { class: 'dash-card pie', 'data-test': 'pie-' + kind }, h('h4', { text: title }));
      if (!total) { box.append(h('div', { class: 'muted small', text: L.n_a })); return box; }
      const g = sv('svg', { viewBox: '-1.1 -1.1 2.2 2.2', class: 'donut', role: 'img', 'aria-label': title });
      let a0 = -Math.PI / 2;
      keys.forEach(function (k, i) {
        const frac = data[k] / total;
        const cls = 'sl' + (i % 8);
        if (frac >= 0.9999) { g.append(sv('circle', { cx: 0, cy: 0, r: 1, class: cls })); return; }
        const a1 = a0 + frac * 2 * Math.PI;
        const large = frac > 0.5 ? 1 : 0;
        g.append(sv('path', { class: cls, d: 'M0 0 L' + Math.cos(a0).toFixed(4) + ' ' + Math.sin(a0).toFixed(4) +
          ' A1 1 0 ' + large + ' 1 ' + Math.cos(a1).toFixed(4) + ' ' + Math.sin(a1).toFixed(4) + ' Z' }));
        a0 = a1;
      });
      g.append(sv('circle', { cx: 0, cy: 0, r: 0.55, class: 'hole' }));
      const leg = h('ul', { class: 'legend' });
      keys.forEach(function (k, i) {
        leg.append(h('li', null, h('span', { class: 'sw sl' + (i % 8) }), h('bdi', { text: nameOf(kind, k) }),
          h('b', { text: Math.round(100 * data[k] / total) + '%' }), h('span', { class: 'muted small', text: unit === 's' ? fmtS(data[k]) : String(data[k]) })));
      });
      box.append(h('div', { class: 'pie-row' }, g, leg));
      return box;
    }
    /** Horizontal bars (backlog age, total per hour): SVG rects, widths as attributes (no inline styles). */
    function bars(items, cls) {
      const max = Math.max.apply(null, items.map(function (x) { return x[1]; }).concat([1]));
      const g = sv('svg', { viewBox: '0 0 100 ' + (items.length * 22), class: 'bars ' + (cls || ''), preserveAspectRatio: 'none',
        width: '100%', height: items.length * 22 });                // one 22px row per label
      items.forEach(function (x, i) { g.append(sv('rect', { x: 0, y: i * 22 + 5, height: 12, width: Math.max(0.5, 100 * x[1] / max).toFixed(2), class: 'bar' })); });
      const lab = h('div', { class: 'bar-labels' }, items.map(function (x) { return h('div', null, h('span', { text: x[0] }), h('b', { text: String(x[2] !== undefined ? x[2] : x[1]) })); }));
      return h('div', { class: 'bars-wrap' }, lab, g);
    }
    function big(label, value, sub, test) {
      return h('div', { class: 'big', 'data-test': test }, h('div', { class: 'v', text: String(value) }), h('div', { class: 'l', text: label }),
        sub ? h('div', { class: 'muted small', text: sub }) : null);
    }
    function brandCard(b, o) {
      const pre = o.truncated ? '≥' : '';
      const c = h('div', { class: 'dash-card brand', 'data-test': 'dash-brand', 'data-brand': b },
        h('h3', null, brandName(b),
          o.stats === 'dayStats' ? h('span', { class: 'chip ok', 'data-test': 'ov-from-conv', text: L.from_conv +
            (o.ds_at && st.data ? ' · ' + d('ds_age', { m: Math.max(0, Math.round((st.data.generated_at - o.ds_at) / 60)) }) : '') +
            (o.ds_busy ? ' · ' + L.ds_updating : '') }) :
            (o.ds_busy ? h('span', { class: 'chip outline', text: L.computing }) : (o.source !== 'live' ? h('span', { class: 'chip outline', text: o.source === 'snapshot' ? L.src_snapshot : L.src_rebuilt }) : null))));
      const mailOff = o.email_status && o.email_status !== 'ok';
      if (mailOff) c.append(h('div', { class: 'chip warn-chip', 'data-test': 'ov-mail-blocked', text: o.email_status === 'gmail_blocked' ? L.gmail_blocked : L.gmail_error }));
      c.append(h('div', { class: 'big-row' },
        big(L.received, pre + o.received, mailOff ? L.wa_only : null, 'ov-received'),
        big(L.answered, pre + o.answered, o.answered_pct !== null ? pctS(o.answered_pct) + ' ' + L.of : null, 'ov-answered'),
        big(L.closed, pre + o.closed, o.closed_pct !== null ? pctS(o.closed_pct) + ' ' + L.of : null, 'ov-closed')));
      if (o.truncated) c.append(h('div', { class: 'muted small', text: L.partial }));
      const grid = h('div', { class: 'stat-grid' });
      const fromConv = o.stats === 'dayStats';
      [[L.open_now, o.open_now, 'ov-open'], [fromConv ? L.awaiting_today : L.awaiting, o.awaiting, 'ov-awaiting'],
        fromConv ? [L.frt_human, o.frt_human_known ? fmtS(o.frt_human_s) : '—', 'ov-frt', d('incl_bot', { v: fmtS(o.frt_median_s) }) + (o.frt_human_known ? '' : ' · ' + L.human_pending)]
          : [L.frt, fmtS(o.frt_median_s), 'ov-frt'],
        [L.auto_pct, pctS(o.auto_pct), 'ov-auto'], [L.wa_failed, o.wa_failed, 'ov-wafail']].forEach(function (x) {
        grid.append(h('div', { class: 'stat' + (x[2] === 'ov-wafail' && o.wa_failed ? ' bad' : ''), 'data-test': x[2] }, h('b', { text: String(x[1]) }), h('span', { text: x[0] }),
          x[3] ? h('small', { class: 'muted', 'data-test': x[2] + '-bot', text: x[3] }) : null));
      });
      c.append(grid);
      const ag = o.aging || {};
      const agN = (ag['0-4h'] || 0) + (ag['4-24h'] || 0) + (ag['1-3d'] || 0) + (ag['3d+'] || 0);
      c.append(h('h4', { 'data-test': 'ov-aging-title', text: fromConv ? d('aging_all', { n: agN }) : L.aging }), bars([['0–4 ' + L.h, ag['0-4h'] || 0], ['4–24 ' + L.h, ag['4-24h'] || 0], ['1–3 ' + (LANG === 'en' ? 'd' : 'ימים'), ag['1-3d'] || 0], ['3+ ' + (LANG === 'en' ? 'd' : 'ימים'), ag['3d+'] || 0]], 'aging'));
      return c;
    }
    /** Service hours: every ticket written to before the desk closed, by what followed. The unanswered ones are links. */
    function serviceBlock(x) {
      const sv = x.service;
      if (!sv || (!sv.brands.length && !sv.missing.length)) return null;
      const hh = sv.close_hour || 17, T = sv.total || {};
      const box = h('div', { class: 'dash-card service', 'data-test': 'service' }, h('h3', { text: d('sv_title', { h: hh }) }),
        h('div', { class: 'muted small', 'data-test': 'service-def', text: d('sv_def', { h: hh, d: sv.day }) }));
      if (sv.missing.length) box.append(h('div', { class: 'chip outline', 'data-test': 'service-wait', text: d('sv_wait', { b: sv.missing.map(brandName).join(', ') }) }));
      if (sv.email_unknown.length) box.append(h('div', { class: 'chip warn-chip', 'data-test': 'service-mail-off', text: d('sv_mail_off', { b: sv.email_unknown.map(brandName).join(', ') }) }));
      if (!sv.brands.length) return box;
      const KEYS = ['received', 'person', 'auto', 'closed', 'unanswered'];
      const TKEYS = ['received', 'unanswered', 'person', 'auto', 'closed'];      // the table: what needs action sits next to the brand (a phone shows 2-3 columns)
      const row = h('div', { class: 'sv-cards' });
      KEYS.forEach(function (k) {
        const bad = k === 'unanswered' && T[k] > 0, ok = k === 'unanswered' && !T[k];
        row.append(h('div', { class: 'sv-card' + (k === 'received' ? ' total' : '') + (bad ? ' bad' : '') + (ok ? ' good' : ''), 'data-test': 'service-' + k },
          h('div', { class: 'v', text: String(T[k] || 0) }), h('div', { class: 'l', text: d('sv_' + k, { h: hh }) }),
          k !== 'received' && T.received ? h('div', { class: 'muted small', text: Math.round(100 * (T[k] || 0) / T.received) + '%' }) : null));
      });
      box.append(row);
      if (!T.unanswered && !sv.missing.length) box.append(h('div', { class: 'verified', 'data-test': 'service-all-ok', text: '✓ ' + L.sv_all_ok }));
      const tb = h('table', { class: 'dash-table', 'data-test': 'service-table' }, h('thead', null, h('tr', null, [L.brand_col].concat(TKEYS.map(function (k) { return d('sv_' + k, { h: hh }); })).map(function (c) { return h('th', { text: c }); }))));
      const body = h('tbody');
      sv.brands.forEach(function (b) {
        const o = x.brands[b].service;
        body.append(h('tr', { 'data-brand': b }, h('td', null, h('bdi', { text: brandName(b) })), TKEYS.map(function (k) {
          return h('td', { class: k === 'unanswered' && o[k].total ? 'sv-bad' : null }, h('b', { text: String(o[k].total) }),
            o.email_known ? h('span', { class: 'muted small', text: ' (' + L.whatsapp + ' ' + o[k].whatsapp + ' · ' + L.email + ' ' + o[k].email + ')' }) : h('span', { class: 'muted small', text: ' (' + L.wa_only + ')' }));
        })));
      });
      tb.append(body);
      box.append(h('div', { class: 'table-wrap' }, tb));
      const tm = function (iso) { const dt = new Date(iso); return isNaN(dt) ? '' : dt.toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'he-IL', { timeZone: 'Asia/Jerusalem', hour: '2-digit', minute: '2-digit' }); };
      sv.brands.forEach(function (b) {
        const o = x.brands[b].service;
        if (!o.unanswered.total) return;
        const det = h('details', { class: 'sv-list', 'data-test': 'service-list', 'data-brand': b }, h('summary', { text: d('sv_list', { b: brandName(b), n: o.unanswered.total }) }));
        const ul = h('ul', { class: 'mini' });
        o.tickets.forEach(function (tk) {
          ul.append(h('li', null, h('a', { href: '#/b/' + encodeURIComponent(b) + '/t/' + encodeURIComponent(tk.id), 'data-test': 'service-ticket' },
            (tk.ch === 'whatsapp' ? L.whatsapp : L.email) + ' · ' + d('sv_since', { t: tm(tk.at) }) + (tk.category ? ' · ' + catName(tk.category) : '') + ' · …' + String(tk.id).slice(-5))));
        });
        det.append(ul);
        if (o.unanswered.total > o.tickets.length) det.append(h('div', { class: 'muted small', text: d('sv_more', { n: o.unanswered.total - o.tickets.length, m: o.tickets.length }) }));
        box.append(det);
      });
      return box;
    }
    function kpi(label, value, bench, good, test, note) {
      const cls = good === null || good === undefined ? '' : good ? ' good' : ' bad';
      return h('div', { class: 'kpi' + cls, 'data-test': test }, h('div', { class: 'l', text: label }), h('div', { class: 'v', text: value }),
        bench ? h('div', { class: 'b', text: L.bench + ': ' + bench }) : null, note ? h('div', { class: 'muted small', text: note }) : null);
    }
    function kpis(k, bench) {
      const box = h('div', { class: 'kpi-grid' });
      const lt = function (v, lim) { return v === null || v === undefined ? null : v <= lim; };
      box.append(
        k.frt_human_known ? kpi(L.frt_human_all, fmtS(k.frt_human_s), null, null, 'kpi-frt-human') : null,
        k.frt_human_known && k.frt_human_email_s !== null ? kpi(L.frt_email + ' · ' + L.sub_human, fmtS(k.frt_human_email_s), '< 24 ' + L.h, lt(k.frt_human_email_s, bench.frt_email_s), 'kpi-frt-email', d('incl_bot', { v: fmtS(k.frt_email_s) }))
          : kpi(L.frt_email, fmtS(k.frt_email_s), '< 24 ' + L.h, lt(k.frt_email_s, bench.frt_email_s), 'kpi-frt-email'),
        k.frt_human_known && k.frt_human_wa_s !== null ? kpi(L.frt_wa + ' · ' + L.sub_human, fmtS(k.frt_human_wa_s), '< 90 ' + L.s, lt(k.frt_human_wa_s, bench.frt_wa_s), 'kpi-frt-wa', d('incl_bot', { v: fmtS(k.frt_wa_s) }))
          : kpi(L.frt_wa, fmtS(k.frt_wa_s), '< 90 ' + L.s, null, 'kpi-frt-wa', k.frt_source === 'dayStats' ? d('incl_bot', { v: '' }).replace(/:\s*$/, '') : null),
        kpi(L.aht, fmtS(k.aht_s), '4–6 ' + L.m, k.aht_s === null ? null : k.aht_s <= bench.aht_s[1], 'kpi-aht'),
        kpi(L.fcr, pctS(k.fcr_pct), null, null, 'kpi-fcr', k.fcr_window_open && k.fcr_pct !== null ? L.fcr_note : null),
        kpi(L.reopen, pctS(k.reopen_pct), null, null, 'kpi-reopen'),
        kpi(L.occ, k.occupancy === null ? '—' : Math.round(k.occupancy * 100) + '%', '75–85%',
          k.occupancy === null ? null : k.occupancy >= bench.occupancy[0] && k.occupancy <= bench.occupancy[1], 'kpi-occ'),
        kpi(L.backlog, String(k.backlog), null, null, 'kpi-backlog'),
        kpi(L.sla_wa, pctS(k.sla_wa_pct), '≥ 90%', k.sla_wa_pct === null ? null : k.sla_wa_pct >= 90, 'kpi-sla-wa', k.sla_wa_n ? 'n=' + k.sla_wa_n : null),
        kpi(L.sla_email, pctS(k.sla_email_pct), '≥ 90%', k.sla_email_pct === null ? null : k.sla_email_pct >= 90, 'kpi-sla-email', k.sla_email_n ? 'n=' + k.sla_email_n : null),
        kpi(L.csat, '—', null, null, 'kpi-csat', L.csat_missing));
      return box;
    }
    function agentsTable(all) {
      // the engine is the truth for replies/closes (the log only exists since it was deployed): the larger number leads
      const list = all.filter(function (a) { return a.active_s || a.sends || a.closes || a.engine_sends || a.engine_closes || a.ds_answered; });
      const idle = all.length - list.length;
      const wrap = h('div', { class: 'table-wrap' });
      if (idle) wrap.append(h('div', { class: 'muted small idle-note', text: d('idle_agents', { n: idle }) }));
      if (!list.length) { wrap.append(h('div', { class: 'muted', text: L.none })); return wrap; }
      const tb = h('table', { class: 'dash-table', 'data-test': 'dash-agents' });
      tb.append(h('thead', null, h('tr', null, [L.agent, L.conv_answered, L.active, L.replies, L.closes, L.per_hour, 'AHT', L.occ].map(function (x) { return h('th', { text: x }); }))));
      const body = h('tbody');
      list.forEach(function (a) {
        const tr = h('tr', { 'data-test': 'dash-agent', 'data-user': a.user },
          h('td', null, h('bdi', { text: a.name })),
          h('td', { 'data-test': 'ag-conv' }, h('b', { text: a.ds_answered === null || a.ds_answered === undefined ? '—' : String(a.ds_answered) })),
          h('td', { 'data-test': 'ag-active', text: fmtS(a.active_s) }),
          h('td', { 'data-test': 'ag-replies' }, h('b', { text: String(Math.max(a.sends, a.engine_sends)) }),
            h('span', { class: 'muted small', text: ' (' + L.engine + ' ' + a.engine_sends + ' · ' + L.log_word + ' ' + a.sends + ')' })),
          h('td', null, h('b', { text: String(Math.max(a.closes, a.engine_closes)) }),
            h('span', { class: 'muted small', text: ' (' + L.engine + ' ' + a.engine_closes + ' · ' + L.log_word + ' ' + a.closes + ')' })),
          h('td', { text: a.per_hour === null ? '—' : String(a.per_hour) }),
          h('td', { text: fmtS(a.aht_s) }),
          h('td', { text: a.occupancy === null ? '—' : Math.round(a.occupancy * 100) + '%' }));
        body.append(tr);
        const det = h('details', { class: 'ag-det' }, h('summary', { text: L.by_brand + ' · ' + L.by_channel + ' · ' + L.per_day }));
        const part = function (obj, kind) {
          return h('ul', { class: 'mini' }, Object.keys(obj || {}).map(function (k) {
            return h('li', null, h('bdi', { text: nameOf(kind, k) }), ': ' + fmtS(obj[k].active_s) + ' · ' + obj[k].sends + ' ' + L.replies + ' · ' + obj[k].closes + ' ' + L.closes);
          }));
        };
        det.append(part(a.by_brand, 'brand'), part(a.by_channel, 'channel'));
        if (a.days.length > 1) det.append(h('ul', { class: 'mini' }, a.days.map(function (x) { return h('li', null, x.day + ': ' + fmtS(x.active_s) + ' · ' + x.sends + ' ' + L.replies); })));
        if (a.resends) det.append(h('div', { class: 'muted small', text: a.resends + ' ' + L.resends }));
        det.append(h('div', { class: 'muted small', text: L.present + ': ' + fmtS(a.present_s) }));
        body.append(h('tr', { class: 'det-row' }, h('td', { colspan: '8' }, det)));
      });
      tb.append(body);
      wrap.append(tb);
      return wrap;
    }
    function heatmap(data) {
      const box = h('div', { class: 'dash-card heat-card' }, h('h3', { text: L.heat }));
      const agents = data.agents.filter(function (a) { return a.active_s > 0; });
      let rows;
      if (data.days.length === 1) {
        rows = agents.map(function (a) { return [a.name, data.heat[a.user][data.days[0]]]; });
      } else {
        const sel = h('select', { 'aria-label': L.agent, 'data-test': 'heat-who' }, h('option', { value: 'all', text: L.heat_all }),
          agents.map(function (a) { return h('option', { value: a.user, text: a.name, selected: st.who === a.user ? 'selected' : null }); }));
        sel.addEventListener('change', function () { st.who = sel.value; render(); });
        box.append(sel);
        rows = data.days.map(function (dd) {
          const v = new Array(24).fill(0);
          agents.forEach(function (a) { if (st.who === 'all' || st.who === a.user) (data.heat[a.user][dd] || []).forEach(function (x, i) { v[i] += x; }); });
          return [dd.slice(5), v];
        });
      }
      if (!rows.length) { box.append(h('div', { class: 'muted small', text: L.none })); return box; }
      const max = Math.max.apply(null, rows.map(function (r) { return Math.max.apply(null, r[1]); }).concat([1]));
      const grid = h('div', { class: 'heat', 'data-test': 'heatmap' });
      grid.append(h('div', { class: 'hl' }));
      for (let i = 0; i < 24; i++) grid.append(h('div', { class: 'hh', text: i % 3 === 0 ? String(i) : '' }));
      rows.forEach(function (r) {
        grid.append(h('div', { class: 'hl' }, h('bdi', { text: r[0] })));
        r[1].forEach(function (x, i) {
          const lvl = x <= 0 ? 0 : Math.min(5, 1 + Math.floor(4.999 * x / max));
          grid.append(h('div', { class: 'hc lvl' + lvl, title: r[0] + ' ' + i + ':00 · ' + fmtS(x) }));
        });
      });
      box.append(h('div', { class: 'heat-scroll' }, grid));
      const tot = data.hour_total.map(function (x, i) { return [String(i) + ':00', x, fmtS(x)]; }).filter(function (x) { return x[1] > 0; });
      if (tot.length) box.append(h('h4', { text: L.heat_total }), bars(tot, 'hours'));
      return box;
    }
    /** "Answered" / "closed" split by where it happened: the system (agent / auto), Dondy (person / bot / template / close),
     *  the mailbox directly. A row of cards (total, then each source with its parts), a pie, and the per-brand table. */
    const SRC = [['fromSystem', ['agent', 'auto']], ['fromDondy', ['human', 'bot', 'template', 'close']], ['fromEmail', ['direct']]];
    function sourcesBlock(srcs, metric) {
      const tot = srcs.total[metric];
      const box = h('div', { class: 'src-block', 'data-test': 'src-' + metric }, h('h3', { text: L['src_' + metric] }));
      const all = SRC.reduce(function (a, s) { return a + (tot[s[0]].total || 0); }, 0);
      const row = h('div', { class: 'src-cards' }, h('div', { class: 'src-card total', 'data-test': 'src-' + metric + '-total' },
        h('div', { class: 'v', text: String(all) }), h('div', { class: 'l', text: L.total })));
      SRC.forEach(function (s) {
        const parts = s[1].filter(function (k) { return tot[s[0]][k]; }).map(function (k) { return L['sub_' + k] + ' ' + tot[s[0]][k]; });
        row.append(h('div', { class: 'src-card', 'data-test': 'src-' + metric + '-' + s[0] }, h('div', { class: 'v', text: String(tot[s[0]].total || 0) }),
          h('div', { class: 'l', text: L['src_' + s[0]] }), h('div', { class: 'muted small', text: parts.join(' · ') || '—' })));
      });
      box.append(row);
      const data = {};
      SRC.forEach(function (s) { data[s[0]] = tot[s[0]].total || 0; });
      const pieBox = pie(L['src_' + metric], 'src', data, 'n');
      const tb = h('table', { class: 'dash-table' }, h('thead', null, h('tr', null, [L.brand_col, L.total].concat(SRC.map(function (s) { return L['src_' + s[0]]; })).map(function (c) { return h('th', { text: c }); }))));
      const body = h('tbody');
      const line = function (name, m, mailOff) {
        const n = SRC.reduce(function (a, s) { return a + (m[s[0]].total || 0); }, 0);
        body.append(h('tr', null, h('td', null, h('bdi', { text: name })), h('td', null, h('b', { text: String(n) })),
          SRC.map(function (s) {
            if (s[0] === 'fromEmail' && mailOff) return h('td', { 'data-test': 'src-mail-off', title: L.gmail_blocked, text: '—' });
            const parts = s[1].filter(function (k) { return m[s[0]][k]; }).map(function (k) { return L['sub_' + k] + ' ' + m[s[0]][k]; });
            return h('td', null, h('b', { text: String(m[s[0]].total || 0) }), parts.length ? h('span', { class: 'muted small', text: ' (' + parts.join(' · ') + ')' }) : null);
          })));
      };
      Object.keys(srcs.brands || {}).forEach(function (b) { const ob = (st.data.brands || {})[b] || {}; line(brandName(b), srcs.brands[b][metric], ob.email_status && ob.email_status !== 'ok'); });
      if (Object.keys(srcs.brands || {}).length > 1) line(L.all_brands, tot);
      tb.append(body);
      box.append(h('div', { class: 'src-split' }, pieBox, h('div', { class: 'table-wrap' }, tb)));
      return box;
    }
    function render() {
      const p = $('dash-pane');
      clear(p);
      const head = h('div', { class: 'dash-head' }, h('h2', { text: L.title }));
      const rg = h('div', { class: 'seg', role: 'group' });
      [['1', L.day], ['7', L.d7], ['30', L.d30]].forEach(function (x) {
        const b = h('button', { type: 'button', class: 'btn small' + (st.range === x[0] ? ' on' : ''), 'aria-pressed': st.range === x[0] ? 'true' : 'false', text: x[1], 'data-test': 'range-' + x[0] });
        b.addEventListener('click', function () { st.range = x[0]; st.data = null; render(); load(); });   // never old numbers under a new choice
        rg.append(b);
      });
      const di = h('input', { type: 'date', value: st.date || st.shown || '', max: st.shown || null, 'aria-label': 'date', 'data-test': 'dash-date' });
      di.addEventListener('change', function () { st.date = di.value; st.data = null; render(); load(); });
      head.append(rg, di);
      if (st.data) head.append(h('b', { class: 'shown-day', 'data-test': 'dash-shown', text: st.data.days.length > 1 ? st.data.days[0] + ' – ' + st.data.end_day : st.data.end_day }));
      if (st.data) head.append(h('span', { class: 'muted small', 'data-test': 'dash-updated', text: L.updated + ' ' + new Date(st.data.generated_at * 1000).toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'he-IL') }));
      p.append(head);
      if (st.err) p.append(h('div', { class: 'err-box', text: st.err }));
      const x = st.data;
      if (!x) { p.append(h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })); return; }
      if (x.stats_source === 'mixed') p.append(h('div', { class: 'note-box warn', role: 'status', 'data-test': 'dash-missing',
        text: '⚠️ ' + d('missing', { b: Object.keys(x.missing_ds || {}).map(brandName).join(', ') }) }));
      if (x.stats_source === 'list') p.append(h('div', { class: 'err-box dash-fixing', role: 'alert', 'data-test': 'dash-fixing' },
        h('b', { text: '⚠️ ' + L.fixing }), h('div', { class: 'small', text: L.fixing_sub })));
      if (x.verify_note) p.append(h('div', { class: 'verified', role: 'status', 'data-test': 'dash-verify', text: x.verify_note }));
      p.append(h('div', { class: 'muted small dash-method', text: d('method', { m: Math.round(x.idle_gap_s / 60) }) + (x.log_since ? ' · ' + d('since', { d: x.log_since }) : '') }));
      if (!x.log_since) p.append(h('div', { class: 'note-box', 'data-test': 'dash-log-new', text: L.log_new }));
      p.append(serviceBlock(x) || '');
      if (x.days.length > 1) p.append(h('div', { class: 'note-box', 'data-test': 'dash-last-day', text: d('last_day_only', { d: x.end_day }) }));
      const bw = h('div', { class: 'brand-grid' });
      Object.keys(x.brands).forEach(function (b) { bw.append(brandCard(b, x.brands[b])); });
      p.append(bw);
      if (x.sources && x.sources.total && x.sources.total.answered) p.append(sourcesBlock(x.sources, 'answered'), sourcesBlock(x.sources, 'closed'));
      p.append(h('h3', { text: L.kpis }), kpis(x.kpis, x.bench));
      p.append(h('h3', { text: L.agents + ' — ' + L.onscreen, 'data-test': 'dash-onscreen' }), agentsTable(x.agents));
      const sd = x.senders || {};
      if (Object.keys(sd).length) {
        const known = {}; x.agents.forEach(function (a) { known[a.user] = 1; });
        const fixed = ['dondy_direct', 'gmail_direct', 'auto', 'auto-reply', 'bot', 'template'];
        const other = Object.keys(sd).filter(function (k) { return !known[k] && fixed.indexOf(k) < 0 && sd[k]; }).map(function (k) { return k + ' ' + sd[k]; });
        p.append(h('div', { class: 'muted small', 'data-test': 'dash-direct', text: d('direct_note', { d: sd.dondy_direct || 0, g: sd.gmail_direct || 0,
          a: (sd.auto || 0) + (sd['auto-reply'] || 0), b: (sd.bot || 0) + (sd.template || 0) }) + (other.length ? ' · ' + L.others + ': ' + other.join(', ') : '') }));
      }
      p.append(heatmap(x));
      const pg = h('div', { class: 'pie-grid' });
      pg.append(pie(L.pie_brand, 'brand', x.pies.brand, 's'), pie(L.pie_chan, 'channel', x.pies.channel, 's'),
        pie(L.pie_cat, 'category', x.pies.category, 's'), pie(L.pie_who, 'who', x.pies.who, 'n'));
      p.append(h('h3', { text: L.pies }), pg);
    }
    async function load(fromTimer) {
      if (st.busy && fromTimer) return;
      st.busy = true;
      const q = '?range=' + encodeURIComponent(st.range) + (st.date ? '&date=' + encodeURIComponent(st.date) : '');
      const seq = st.seq = (st.seq || 0) + 1;
      let r;
      try { r = await api('/api/dash' + q, undefined, 'GET', { quiet: true }); } finally { if (seq === st.seq) st.busy = false; }
      if (seq !== st.seq) return;                       // the manager chose another day / range meanwhile (gate run 2026-10-06)
      if (r && r.ok) { st.data = r; st.err = null; if (!st.date) st.shown = r.end_day; } else if (r) st.err = r.msg || r.error;
      if (S.view === 'dash') render();
    }
    function show() {
      $('dash-pane').hidden = false;
      render();
      load();
      if (!timer) timer = setInterval(function () { if (S.view === 'dash' && !document.hidden) load(true); }, 30000);
    }
    return { show: show, load: load };
  })();

  /** Typing in a ticket is work: a quiet heartbeat at most once a minute (autosave alone waits for a pause). */
  const EDIT_PING = {};
  function pingEdit(brand, id) {
    const k = brand + '|' + id;
    if (Date.now() - (EDIT_PING[k] || 0) < 60000) return;
    EDIT_PING[k] = Date.now();
    api('/api/' + encodeURIComponent(brand) + '/activity', { id: id, kind: 'edit' }, 'POST', { quiet: true, retry: false });
  }

  const Settings = (function () {
    const KEYS = [['DRY_RUN', ['on', 'off']], ['KACHING_WRITES', ['on', 'off']], ['AUTO_CANCEL', ['off', 'shadow', 'on']], ['AUTO_REPLY', ['off', 'shadow', 'on']]];
    function norm(key, v) {
      if (v === undefined || v === null) return null;
      if (key === 'AUTO_CANCEL' || key === 'AUTO_REPLY') { const s = String(v).toLowerCase(); return s === 'true' ? 'on' : s === 'false' ? 'off' : s; }
      return onOff(v) ? 'on' : 'off';
    }
    async function load(brand) {
      const r = await engine('apiSettings', { action: 'get' }, brand);
      const cur = S.settings[brand] || {};
      if (r.ok) S.settings[brand] = { values: r.settings || {}, err: null, refusal: cur.refusal };
      else S.settings[brand] = { values: cur.values || null, err: r.msg || r.error, refusal: cur.refusal };
      if (S.view === 'settings' && S.brand === brand) render();
    }
    function show() { $('settings-pane').hidden = false; render(); load(S.brand); if (!S.boots[S.brand]) loadBoot(S.brand); }
    function render() {
      const p = $('settings-pane');
      clear(p);
      const brand = S.brand;
      p.append(h('h2', null, tx('set_title', { b: brandName(brand) })));
      const st = S.settings[brand];
      if (st && st.refusal) p.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: t('set_refused') + ' ' + st.refusal.msg }),
        h('bdi', { class: 'raw', 'data-test': 'refusal-raw', text: st.refusal.raw })));
      if (st && st.err) p.append(h('div', { class: 'err-box', text: st.err }));
      if (!st || !st.values) { p.append(h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })); return; }
      KEYS.forEach(function (kv) {
        const k = kv[0];
        const cur = norm(k, st.values[k]);
        const seg = h('div', { class: 'seg', role: 'group', 'aria-label': t('set_' + k) });
        kv[1].forEach(function (v) {
          // colour follows RISK, not the word "on": DRY_RUN=off is the live (risky) state
          const risk = k === 'DRY_RUN' ? (v === 'off' ? 'on' : 'off') : v;
          const b = h('button', { type: 'button', class: 'seg-btn' + (cur === v ? ' on v-' + risk : ''), 'aria-pressed': cur === v ? 'true' : 'false', text: t('val_' + v) });
          b.addEventListener('click', async function () {
            if (cur === v) return;
            const yes = await confirmDlg({ title: tx('set_confirm_q', { k: t('set_' + k), v: t('val_' + v), b: brandName(brand) }), body: t('set_' + k + '_help'), ok: t('ok'), danger: v === 'on' || (k === 'DRY_RUN' && v === 'off') });
            if (!yes) return;
            seg.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
            const r = await engine('apiSettings', { action: 'set', key: k, value: v }, brand);
            S.settings[brand].refusal = r.ok ? null : {
              msg: r.msg || '',
              raw: [r.error, r.reason, Array.isArray(r.allowed) ? 'allowed: ' + r.allowed.join('|') : null].filter(Boolean).join(' · ')
            };
            if (r.ok) toast(r.noop ? t('set_noop') : t('set_ok') + ' (' + k + ': ' + r.from + ' → ' + r.to + ')');
            if (r.ok) refreshSwitches(brand);
            if (r.ok && k === 'AUTO_CANCEL') loadAuto(brand);
            if (r.ok && k === 'AUTO_REPLY') AutoReply.load(brand);
            await load(brand);
            await loadBoot(brand);
          });
          seg.append(b);
        });
        if (st.values[k] === undefined && k === 'AUTO_REPLY') return;      // engine without the switch yet: not offered
        p.append(h('div', { class: 'card set-row', 'data-key': k }, h('div', { class: 'set-hd' }, h('b', { text: t('set_' + k) }), h('bdi', { class: 'ltr muted small', text: k })),
          h('div', { class: 'muted small', text: t('set_' + k + '_help') }),
          k === 'AUTO_REPLY' ? h('div', { class: 'small set-note' + (norm('DRY_RUN', st.values.DRY_RUN) === 'on' ? ' warn' : ''), text: t('set_AUTO_REPLY_note') }) : null, seg));
      });
    }
    return { show: show };
  })();

  // ---------------------------------------------------------------- users manager
  const Users = (function () {
    let data = null;
    let err = null;
    let openEdit = null;
    let temp = null;     // { username, pw }
    async function load() {
      const r = await api('/api/manage/users', undefined, 'GET');
      if (r.ok) { data = r; err = null; } else { err = r.msg || r.error; }
      render();
    }
    function show() {
      $('users-pane').hidden = false;
      render();
      load();
    }
    function rolesBox(sel, lockAdmin) {
      const g = h('div', { class: 'grp' }, h('span', { text: t('u_roles') }));
      ['agent', 'admin', 'user-manager'].forEach(function (r) {
        const cb = h('input', { type: 'checkbox', name: 'role', value: r, checked: sel.indexOf(r) >= 0, disabled: r === 'admin' && lockAdmin });
        g.append(h('label', { class: 'cb' }, cb, t('role_' + r) + (r === 'admin' && lockAdmin ? ' (' + t('u_admin_only') + ')' : '')));
      });
      return g;
    }
    function brandsBox(sel) {
      const g = h('div', { class: 'grp' }, h('span', { text: t('u_brands') }));
      (data.valid_brands || []).forEach(function (b) {
        g.append(h('label', { class: 'cb' }, h('input', { type: 'checkbox', name: 'brand', value: b, checked: sel.indexOf(b) >= 0 }), brandName(b)));
      });
      return g;
    }
    function langBox(v) {
      const s = h('select', { name: 'lang' }, h('option', { value: 'he', text: t('lang_he') }), h('option', { value: 'en', text: t('lang_en') }));
      s.value = v || 'he';
      return h('div', { class: 'grp' }, h('span', { text: t('u_lang') }), s);
    }
    function collect(form) {
      const vals = function (n) { return Array.prototype.slice.call(form.querySelectorAll('input[name=' + n + ']:checked')).map(function (i) { return i.value; }); };
      const out = { roles: vals('role'), brands: vals('brand'), lang: form.querySelector('select[name=lang]').value };
      const dn = form.querySelector('input[name=display_name]');
      if (dn) out.display_name = dn.value.trim();
      const dis = form.querySelector('input[name=disabled]');
      if (dis) out.disabled = dis.checked;
      return out;
    }
    function tempBox() {
      if (!temp) return null;
      return h('div', { class: 'temp-pw', role: 'status' }, h('b', { text: temp.username }), t('u_temp'), h('code', { text: temp.pw }), copyBtn(temp.pw),
        h('div', { class: 'small full-row', text: t('u_temp_note') }));
    }
    function render() {
      const p = $('users-pane');
      if (S.view !== 'users') return;
      clear(p);
      p.append(h('h2', { text: t('u_title') }));
      if (err) p.append(h('div', { class: 'err-box', text: err }));
      if (!data) { p.append(h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })); return; }
      const lockAdmin = !S.me.is_admin;
      // create
      const msg = h('div');
      const cf = h('form', { class: 'u-form' },
        h('div', { class: 'grp' }, h('span', { text: t('u_username') }), h('input', { type: 'text', name: 'username', dir: 'ltr', autocomplete: 'off', autocapitalize: 'none', spellcheck: 'false', required: true, maxlength: '32' })),
        h('div', { class: 'grp' }, h('span', { text: t('u_display') }), h('input', { type: 'text', name: 'display_name', dir: 'auto', maxlength: '60' })),
        rolesBox(['agent'], lockAdmin), brandsBox([]), langBox('he'), msg,
        h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'submit', text: t('u_create') })));
      cf.addEventListener('submit', async function (e) {
        e.preventDefault();
        const body = collect(cf);
        body.username = cf.querySelector('input[name=username]').value.trim().toLowerCase();
        clear(msg);
        const r = await api('/api/manage/users', body);
        if (!r.ok) { msg.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
        temp = { username: r.user.username, pw: r.temp_password };
        toast(t('u_created'));
        load();
      });
      p.append(h('details', { class: 'u-card', open: !(data.users || []).length }, h('summary', { text: '+ ' + t('u_new') }), cf));
      const tb = tempBox();
      if (tb) p.append(tb);
      (data.users || []).forEach(function (u) { p.append(userCard(u, lockAdmin)); });
      const aud = h('details', { class: 'u-card audit' }, h('summary', { text: t('u_audit') }));
      const al = h('div', { class: 'audit-list' }, t('loading'));
      aud.append(al);
      aud.addEventListener('toggle', async function () {
        if (!aud.open) return;
        const r = await api('/api/manage/audit', undefined, 'GET');
        clear(al);
        if (!r.ok) { al.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
        r.lines.forEach(function (l) {
          al.append(h('div', null, h('span', { class: 'muted', text: fmtDate(l.time, true) + ' · ' }), h('b', { text: l.actor }), ' ', h('bdi', { class: 'ltr', text: l.action }),
            l.target ? ' → ' + l.target : '', l.detail ? h('span', { class: 'muted small ltr', text: ' ' + JSON.stringify(l.detail) }) : null));
        });
      });
      p.append(aud);
    }
    function userCard(u, lockAdmin) {
      const isMe = u.username === S.me.user.username;
      const targetAdmin = u.roles.indexOf('admin') >= 0;
      const blocked = targetAdmin && lockAdmin;
      const c = h('div', { class: 'u-card' + (u.disabled ? ' disabled' : '') });
      c.append(h('div', { class: 'hd' }, h('b', { class: 'ltr', text: u.username }), u.display_name ? h('span', { dir: 'auto', text: u.display_name }) : null,
        isMe ? h('span', { class: 'chip outline', text: t('u_me') }) : null,
        u.roles.map(function (r) { return h('span', { class: 'chip st-sent', text: t('role_' + r) }); }),
        h('span', { class: 'chip ' + (u.disabled ? 'bad' : 'ok'), text: u.disabled ? t('u_disabled') : t('u_active') }),
        u.must_change ? h('span', { class: 'chip', text: t('u_must_change') }) : null));
      c.append(h('div', { class: 'small muted' }, h('bdi', { text: u.brands.length ? u.brands.map(brandName).join(' · ') : '—' }), ' · ' + t('lang_' + u.lang) + ' · ' +
        t('u_last') + ': ', h('bdi', { text: u.last_login ? fmtDate(u.last_login, true) : t('u_never') })));
      if (blocked) return c;
      const msg = h('div');
      if (openEdit === u.username) {
        const f = h('form', { class: 'u-form' },
          h('div', { class: 'grp' }, h('span', { text: t('u_display') }), h('input', { type: 'text', name: 'display_name', value: u.display_name || '', dir: 'auto', maxlength: '60' })),
          rolesBox(u.roles, lockAdmin || isMe), brandsBox(u.brands), langBox(u.lang),
          h('div', { class: 'grp' }, h('label', { class: 'cb' }, h('input', { type: 'checkbox', name: 'disabled', checked: u.disabled, disabled: isMe }), t('u_disabled'))),
          msg,
          h('div', { class: 'actions' }, h('button', { class: 'btn primary', type: 'submit', text: t('u_save') }),
            h('button', { class: 'btn ghost', type: 'button', text: t('u_cancel'), onclick: function () { openEdit = null; render(); } })));
        // disabled role boxes are not sent: keep the stored roles for them
        f.addEventListener('submit', async function (e) {
          e.preventDefault();
          const body = collect(f);
          if (isMe) { delete body.roles; delete body.disabled; } else if (lockAdmin) { body.roles = body.roles.filter(function (r) { return r !== 'admin'; }); }
          clear(msg);
          const r = await api('/api/manage/users/' + encodeURIComponent(u.username), body);
          if (!r.ok) { msg.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
          openEdit = null;
          toast(t('u_saved'));
          load();
        });
        c.append(f);
      } else {
        const reset = armed(t('u_reset'), t('u_reset_arm'), 'small', async function () {
          clear(msg);
          const r = await api('/api/manage/users/' + encodeURIComponent(u.username) + '/reset', {});
          if (!r.ok) { msg.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
          temp = { username: u.username, pw: r.temp_password };
          load();
        });
        c.append(h('div', { class: 'actions' }, h('button', { class: 'btn small', type: 'button', text: t('u_edit'), onclick: function () { openEdit = u.username; render(); } }), reset), msg);
      }
      return c;
    }
    return { show: show };
  })();

  // ---------------------------------------------------------------- start
  async function start() {
    const r = await api('/api/me', undefined, 'GET');
    if (!r.ok) {
      const lp = $('list-pane');
      clear(lp);
      lp.append(h('div', { class: 'err-box', text: r.msg || r.error }));
      return;
    }
    S.me = r;
    Outbox.boot();                                     // sends that were in flight when the page closed: ask, never resend
    window.addEventListener('hashchange', route);
    route();
  }
  start();
})();
