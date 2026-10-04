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
      app: 'שירות לקוחות', tab_ready: 'חדש', tab_action: 'צריך החלטה', tab_health: 'בריאות', tab_delay: 'עיכוב',
      tab_sent: 'ממתין ללקוח', tab_today: 'טופל היום', tab_search: 'חיפוש',
      st_ready: 'חדש', st_action: 'צריך החלטה', st_health: 'בריאות', st_delay: 'עיכוב', st_sent: 'ממתין ללקוח', st_done: 'טופל', st_noreply: 'ללא מענה',
      cat_shipping: 'משלוח', cat_product: 'מוצר', cat_order_change: 'שינוי הזמנה', cat_return_refund: 'החזרה / החזר', cat_cancel_subscription: 'ביטול מנוי',
      cat_billing: 'חיוב', cat_health: 'בריאות', cat_complaint: 'תלונה', cat_legal: 'משפטי', cat_discount: 'הנחה', cat_voc: 'מחקר לקוחות', cat_other: 'אחר',
      ch_email: 'מייל', ch_whatsapp: 'וואטסאפ',
      dry_run: 'מצב ניסיון — שליחה כבויה. אפשר לקרוא, לערוך ולשמור טיוטות; השליחה ללקוח חסומה.',
      frozen: 'ביטולי מנויים מוקפאים במותג הזה — רק אדמין יכול לשחרר.',
      mock: 'תצוגה מקומית — נתונים מדומים, שום דבר לא נשלח.',
      bootstrap_env: 'ADMIN_BOOTSTRAP עדיין מוגדר בשרת. הסירו אותו מ-Render.',
      no_brands: 'לא הוגדרו לך מותגים. פנו למנהל.', not_connected: 'המותג {b} עוד לא מחובר למערכת.',
      loading: 'טוען…', empty_ready: 'אין פניות חדשות', empty_action: 'אין פניות שמחכות להחלטה', empty_health: 'אין פניות בריאות',
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
      ship_not_late: 'בזמן', ship_late: 'באיחור', ship_very_late: 'באיחור חמור', ship_unknown: 'לא ידוע', ship_not_applicable: 'לא רלוונטי',
      ship_line: '{state} · {d} ימים מההזמנה (רגיל עד {n}, איחור אחרי {l})',
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
      // users
      u_title: 'ניהול משתמשים', u_new: 'משתמש חדש', u_username: 'שם משתמש (לועזית)', u_display: 'שם תצוגה', u_roles: 'תפקיד', u_brands: 'מותגים',
      u_lang: 'שפה', u_disabled: 'מושבת', u_active: 'פעיל', u_create: 'יצירה', u_save: 'שמירה', u_edit: 'עריכה', u_cancel: 'ביטול',
      u_reset: 'איפוס סיסמה', u_reset_arm: 'לחצו שוב לאיפוס', u_temp: 'סיסמה זמנית:', u_temp_note: 'מוצגת פעם אחת בלבד. שלחו אותה למשתמש בערוץ פרטי — בכניסה הראשונה יבחר סיסמה משלו.',
      u_saved: 'נשמר', u_created: 'המשתמש נוצר', u_last: 'כניסה אחרונה', u_never: 'עוד לא נכנס', u_audit: 'יומן שינויים (100 אחרונים)',
      u_must_change: 'סיסמה זמנית', role_agent: 'נציג/ה', role_admin: 'אדמין', 'role_user-manager': 'מנהל/ת משתמשים',
      lang_he: 'עברית', lang_en: 'אנגלית', u_admin_only: 'רק אדמין', u_me: 'אני'
    },
    en: {
      app: 'Customer service', tab_ready: 'New', tab_action: 'Needs decision', tab_health: 'Health', tab_delay: 'Delay',
      tab_sent: 'Waiting for customer', tab_today: 'Handled today', tab_search: 'Search',
      st_ready: 'New', st_action: 'Needs decision', st_health: 'Health', st_delay: 'Delay', st_sent: 'Waiting for customer', st_done: 'Handled', st_noreply: 'No reply',
      cat_shipping: 'Shipping', cat_product: 'Product', cat_order_change: 'Order change', cat_return_refund: 'Return / refund', cat_cancel_subscription: 'Cancel subscription',
      cat_billing: 'Billing', cat_health: 'Health', cat_complaint: 'Complaint', cat_legal: 'Legal', cat_discount: 'Discount', cat_voc: 'Customer research', cat_other: 'Other',
      ch_email: 'Email', ch_whatsapp: 'WhatsApp',
      dry_run: 'Test mode — sending is off. You can read, edit and save drafts; nothing reaches the customer.',
      frozen: 'Subscription cancellations are frozen for this brand — only an admin can lift it.',
      mock: 'Local preview — fake data, nothing is sent.', bootstrap_env: 'ADMIN_BOOTSTRAP is still set on the server. Remove it in Render.',
      no_brands: 'You have no brands. Ask Manager.', not_connected: 'Brand {b} is not connected yet.',
      loading: 'Loading…', empty_ready: 'No new tickets', empty_action: 'Nothing waits for a decision', empty_health: 'No health tickets',
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
      ship_line: '{state} · {d} days since the order (normal up to {n}, late after {l})',
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
  async function api(path, body, method) {
    const opt = { method: method || 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': CSRF, Accept: 'application/json' } };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    PENDING++;
    let r;
    try { r = await fetch(path, opt); } catch (e) { return { ok: false, error: 'network', msg: t('err_network') }; } finally { PENDING--; }
    if (r.status === 401) { setTimeout(function () { location.href = BASE + '/login'; }, 600); return { ok: false, error: 'not_logged_in', msg: t('err_login') }; }
    try { return await r.json(); } catch (e) { return { ok: false, error: 'bad_response', msg: t('err_bad_response') }; }
  }
  function engine(fn, args, brand) {
    return api('/api/' + encodeURIComponent(brand || S.brand) + '/' + fn, { args: args || {} });
  }

  // ---------------------------------------------------------------- state
  const S = {
    me: null, brand: null, view: 'list', tab: 'ready', ticketId: null,
    boots: {}, bootErr: {}, auto: {}, autoEdits: {}, autoMsg: {}, settings: {}, listSig: '', tk: null, search: { q: '', res: null, err: null, seq: 0 }, menuOpen: false
  };
  const OPEN = ['ready', 'action', 'health', 'delay'];
  const TABS = ['ready', 'action', 'auto', 'health', 'delay', 'sent', 'today', 'search'];
  const brandName = function (b) { const bt = S.boots[b]; return (bt && bt.brandName) || (b.charAt(0).toUpperCase() + b.slice(1)); };
  const boot = function () { return S.boots[S.brand] || null; };

  // ---------------------------------------------------------------- routing
  function parseHash() {
    const p = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
    if (p[0] === 'users') return { view: 'users' };
    if (p[0] === 'settings') return { view: 'settings', brand: p[1] };
    if (p[0] === 'b' && p[1]) {
      if (p[2] === 't' && p[3]) return { view: 'ticket', brand: p[1], id: p[3] };
      return { view: 'list', brand: p[1], tab: TABS.indexOf(p[2]) >= 0 ? p[2] : 'ready' };
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
    if (r.view === 'users') {
      if (!S.me.can_manage_users) return go('#/', true);
      S.view = 'users';
      $('settings-pane').hidden = true;
      document.body.className = 'view-users';
      renderTop(); renderBanners(); Users.show();
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
      renderTop(); renderBanners(); Settings.show();
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
      if (window.matchMedia('(max-width: 999px)').matches) { S.ticketId = null; S.tk = null; }
    }
    document.body.className = S.view === 'ticket' ? 'view-ticket' : 'view-list';
    renderTop(); renderBanners(); renderTabs(); renderList(true);
    if (S.view !== 'ticket' && !S.ticketId) renderTicketPlaceholder();
    if (brandChanged || !S.boots[brand]) loadBoot(brand);
  }

  // ---------------------------------------------------------------- top / banners / tabs
  function renderTop() {
    const top = $('top');
    clear(top);
    top.append(h('span', { class: 'title', text: t('app') }));
    const brands = S.me.brands;
    if (brands.length > 1 && S.view !== 'users') {
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
    } else if (brands.length === 1 && S.view !== 'users') {
      top.append(h('span', { class: 'who', text: brandName(brands[0].id) }));
    }
    top.append(h('span', { class: 'spacer' }));
    top.append(h('span', { class: 'who', text: S.me.user.display_name || S.me.user.username }));
    const mb = h('button', { class: 'menu-btn', type: 'button', text: '☰', 'aria-label': t('menu'), 'aria-expanded': S.menuOpen ? 'true' : 'false' });
    mb.addEventListener('click', function (e) { e.stopPropagation(); S.menuOpen = !S.menuOpen; renderTop(); });
    top.append(mb);
    if (S.menuOpen) {
      const m = h('div', { class: 'menu', role: 'menu' });
      if (S.view === 'users' && canWork()) m.append(h('a', { href: '#/', text: t('to_tickets') }));
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
  document.addEventListener('click', function () { if (S.menuOpen) { S.menuOpen = false; renderTop(); } });

  function renderBanners() {
    const el = $('banners');
    clear(el);
    if (S.me.mock) el.append(h('p', { class: 'banner info', text: t('mock') }));
    (S.me.warnings || []).forEach(function (w) { el.append(h('p', { class: 'banner danger', text: t(w) })); });
    if (S.view === 'users') return;
    const b = boot();
    if (b) el.append(modeBanner(b));
    if (b && b.cancelFrozen) el.append(h('p', { class: 'banner danger', text: t('frozen') }));
  }

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
    p.append(h('span', { class: 'chip ' + (b.cancelEnabled ? 'bad' : ''), text: t('mode_kaching', { v: b.cancelEnabled ? t('val_on') : t('val_off') }) }));
    if (auto) p.append(h('span', { class: 'chip ' + (auto === 'on' ? 'bad' : auto === 'shadow' ? 'st-sent' : ''), text: t('mode_auto', { v: t('val_' + auto) }) }));
    return p;
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
    if (id === 'auto') { const a = S.auto[S.brand]; return a && a.items ? a.items.filter(function (x) { return !AutoCancel.inFlight(x.state); }).length : ''; }
    if (id === 'search') return '';
    return (b.counts && b.counts[id]) || 0;
  }
  function renderTabs() {
    const el = $('tabs');
    clear(el);
    const b = boot();
    TABS.forEach(function (id) {
      const n = tabCount(id, b);
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
    if (conn && !conn.connected) { S.bootErr[brand] = t('not_connected', { b: brandName(brand) }); renderList(true); return; }
    const r = await engine('apiBoot', {}, brand);
    if (canWork()) loadAuto(brand);
    if (r.ok) { S.boots[brand] = r; delete S.bootErr[brand]; } else { S.bootErr[brand] = r.msg || r.error; }
    if (brand !== S.brand) return;
    renderTop(); renderBanners(); renderTabs(); renderList(false); checkStale(); Draft.refreshSend();
  }

  setInterval(function () {
    if (document.hidden || !S.brand || S.view === 'users' || S.view === 'settings') return;
    loadBoot(S.brand);
  }, 60000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && S.brand && S.view !== 'users') {
      const b = boot();
      if (!b || Date.now() - ms(b.serverTime) > 30000) loadBoot(S.brand);
    }
  });

  // ---------------------------------------------------------------- list
  function sortRows(rows, tab) {
    const key = function (x) {
      if (OPEN.indexOf(tab) >= 0) return ms(x.waiting_since) || ms(x.created_at) || 0;
      return -(ms(x.handled_at) || ms(x.created_at) || 0);
    };
    return rows.slice().sort(function (a, b) { return key(a) - key(b); });
  }
  function rowsFor(tab) {
    const b = boot();
    if (!b) return null;
    if (tab === 'today') return sortRows(todayList(b), 'today');
    if (tab === 'search') return S.search.res;
    if (tab === 'auto') { const a = S.auto[S.brand]; return a ? (a.items || []) : null; }
    return sortRows((b.tickets || []).filter(function (x) { return x.status === tab; }), tab);
  }

  function rowEl(x, opts) {
    opts = opts || {};
    const open = OPEN.indexOf(x.status) >= 0;
    let age = '';
    let old = false;
    if (open) {
      const w = ms(x.waiting_since) || ms(x.created_at);
      if (w) { age = t('waiting', { d: dur(Date.now() - w) }); old = Date.now() - w > 24 * 3600000; }
    } else if (x.handled_at) {
      age = t('handled_by', { who: x.handled_by || '—', when: ago(x.handled_at) });
    }
    const chips = [];
    if (opts.showStatus || !open || S.tab === 'search' || S.tab === 'today') chips.push(h('span', { class: 'chip st-' + x.status, text: t('st_' + x.status) }));
    if (x.category) chips.push(h('span', { class: 'chip', text: t('cat_' + x.category) }));
    if (x.channel === 'whatsapp') chips.push(h('span', { class: 'chip outline', text: t('ch_whatsapp') }));
    if (Number(x.emails_count) > 1) chips.push(h('span', { class: 'chip outline', text: t('msgs', { n: x.emails_count }) }));
    if (x.language && x.language !== 'he' && x.language !== 'iw') chips.push(h('span', { class: 'chip outline', text: String(x.language).toUpperCase() }));
    if (x.order_no) chips.push(h('span', { class: 'chip outline ltr', text: x.order_no }));
    if (x.cancelled) chips.push(h('span', { class: 'chip ok', text: t('cancelled_here') }));
    if (x.archived) chips.push(h('span', { class: 'chip', text: t('archived') }));
    const inner = [
      h('div', { class: 'l1' }, h('span', { class: 'name', dir: 'auto', text: x.name || x.email || x.phone || t('no_name') }),
        h('span', { class: 'age' + (old ? ' old' : ''), text: age })),
      h('div', { class: 'sum', dir: 'auto', text: x.summary || x.subject || '' }),
      h('div', { class: 'chips' }, chips)
    ];
    if (x.archived || opts.static) return h('div', { class: 'row', 'data-id': x.id }, inner);
    return h('a', { class: 'row' + (x.id === S.ticketId ? ' selected' : ''), href: ticketHash(x.id), 'data-id': x.id }, inner);
  }

  function renderList(force) {
    const lp = $('list-pane');
    if (!S.brand) return;
    const err = S.bootErr[S.brand];
    const rows = rowsFor(S.tab);
    const sig = JSON.stringify([S.brand, S.tab, S.ticketId, err || '', S.tab === 'search' ? [S.search.q, S.search.err, S.search.res] : rows,
      S.tab === 'auto' ? [S.auto[S.brand], S.autoMsg] : null]);
    if (!force && sig === S.listSig) return;           // nothing changed: zero DOM work
    if (lp.contains(document.activeElement) && S.tab !== 'search' && !force) return;
    if (S.tab === 'auto' && !force && AutoCancel.busy()) return;     // never rebuild under an edited reply
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
      return;
    }
    if (S.tab === 'auto') { AutoCancel.render(lp, force); return; }
    clear(lp);
    if (err) { lp.append(h('div', { class: 'err-box', text: err })); return; }
    if (rows === null) { for (let i = 0; i < 5; i++) lp.append(h('div', { class: 'skeleton' })); return; }
    const b = boot();
    lp.append(h('div', { class: 'list-meta' }, h('span', { text: brandName(S.brand) + ' · ' + t('tab_' + S.tab) }),
      h('span', { text: t('updated', { when: ago(b.serverTime) }) })));
    if (!rows.length) {
      lp.append(h('div', { class: 'empty' }, h('b', { text: t('empty_' + S.tab) }), h('span', { text: t('empty_hint') })));
      return;
    }
    rows.forEach(function (x) { lp.append(rowEl(x)); });
  }

  async function runSearch(q) {
    q = String(q || '').trim();
    S.search.q = q;
    const seq = ++S.search.seq;
    if (q.length < 2) { S.search.res = null; S.search.err = null; renderList(true); return; }
    S.search.res = null; S.search.err = null; renderList(true);
    const r = await engine('apiSearch', { q: q });
    if (seq !== S.search.seq) return;            // an older answer must not overwrite a newer query
    if (r.ok) S.search.res = r.tickets || []; else S.search.err = r.msg || r.error;
    renderList(true);
  }

  // ---------------------------------------------------------------- ticket
  function renderTicketPlaceholder() {
    const tp = $('ticket-pane');
    clear(tp);
    tp.append(h('div', { class: 'placeholder', text: t('pick_ticket') }));
  }

  async function openTicket(id) {
    S.ticketId = id;
    S.tk = { id: id, brand: S.brand, loading: true };
    Draft.detach();
    const tp = $('ticket-pane');
    clear(tp);
    tp.append(h('div', { class: 'tk-body' }, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })));
    const brand = S.brand;
    const res = await Promise.all([engine('apiTicket', { id: id }), engine('apiTicketExtras', { id: id })]);
    if (S.ticketId !== id || S.brand !== brand) return;
    const a = res[0];
    const b = res[1];
    if (!a.ok) { clear(tp); tp.append(h('div', { class: 'tk-body' }, backBtn(), h('div', { class: 'err-box', text: a.msg || a.error }))); return; }
    S.tk = { id: id, brand: brand, ticket: a.ticket, extras: b.ok ? (b.extras || {}) : null, extrasErr: b.ok ? null : (b.msg || b.error), related: null };
    renderTicket();
    loadRelated();
    renderList(true);
  }

  function backBtn() {
    return h('button', { class: 'back-btn', type: 'button', text: (LANG === 'en' ? '← ' : '→ ') + t('back'), onclick: function () { go(listHash()); } });
  }

  function statusChip(st) { return h('span', { class: 'chip st-' + st, text: t('st_' + st) }); }

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
    [/draft blocked|draft problem|safety/i, 'בדיקת הבטיחות עצרה את הטיוטה.']
  ];
  function actionLines(action) {
    return String(action || '').split(' | ').filter(Boolean).map(function (part) {
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
    contact.append(h('span', { class: 'item' }, h('span', { class: 'chip outline', text: t('ch_' + (x.channel || 'email')) })));
    const head = h('div', { class: 'tk-head' },
      h('div', { class: 'l1' }, backBtn(), h('h2', { dir: 'auto', text: x.name || x.email || x.phone || t('no_name') }), statusChip(x.status)),
      contact,
      x.summary ? h('p', { class: 'summary-line', dir: 'auto', text: x.summary }) : null);
    tp.append(head);

    const body = h('div', { class: 'tk-body' });
    tp.append(body);
    body.append(h('div', { id: 'tk-stale' }));
    if (isOpen && x.action) {
      const lines = actionLines(x.action);
      body.append(h('div', { class: 'why' + (x.status === 'health' ? ' health' : ''), role: 'note' }, h('b', { text: t('why_human') }),
        lines.map(function (l) { return h('div', null, h('span', { text: l.text }), l.text !== l.raw ? h('div', null, h('span', { class: 'raw', text: l.raw })) : null); })));
    }
    body.append(convCard(ex.conversation || []));
    body.append(Draft.card(x));
    body.append(ordersCard(ex));
    body.append(h('div', { id: 'subs-card' }, subsCard(ex, x)));
    body.append(h('div', { id: 'notes-card' }, notesCard(x)));
    body.append(h('div', { id: 'related-card' }, relatedCard()));
    body.append(detailsCard(x));
    if (k.extrasErr) body.insertBefore(h('div', { class: 'err-box', text: k.extrasErr }), body.children[1]);
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
        h('button', { class: 'btn small', type: 'button', text: t('refresh'), onclick: function () { Draft.flush(); openTicket(S.tk.id); } })));
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
  function convCard(conv) {
    const card = h('div', { class: 'card' }, h('h3', { text: t('conversation') }));
    const list = h('div', { class: 'conv' });
    const msgs = conv.slice().sort(function (a, b) { return (ms(a.at) || 0) - (ms(b.at) || 0); });
    msgs.forEach(function (m, i) {
      const who = m.who === 'us' ? 'us' : (m.who === 'automatic' ? 'automatic' : 'customer');
      const long = String(m.text || '').length > 600 && i < msgs.length - 1;
      const el = h('div', { class: 'msg ' + who + (long ? ' collapsed' : '') },
        h('div', { class: 'meta' }, h('b', { text: t(who) }), h('span', { text: fmtDate(m.at, true) })),
        messageBody(m.text));
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
    let st = null;   // { id, brand, key, ta, base, dirty, saving, timer, stateEl, problemEl }
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
          if (k && k.indexOf('cs.draft.') === 0) { const v = readLocal(k); if (!v || Date.now() - v.at > 7 * 86400000) localStorage.removeItem(k); }
        }
      } catch (e) { /* ignore */ }
    }
    function setState(kind, msg) {
      if (!st || !st.stateEl) return;
      st.stateEl.className = 'save-state' + (kind === 'fail' ? ' bad' : '');
      st.stateEl.textContent = kind === 'local' ? t('save_local') : kind === 'saving' ? t('saving') : kind === 'saved' ? t('saved') :
        kind === 'fail' ? t('save_failed', { m: msg || '' }) : (msg || '');
    }
    function showProblem(p) {
      if (!st || !st.problemEl) return;
      clear(st.problemEl);
      st.problemEl.hidden = !p;
      if (p) st.problemEl.append(t('safety', { p: p }));
    }
    async function save() {
      if (!st || !st.dirty) return;
      if (st.saving) { st.again = true; return; }
      const mine = st;
      const text = mine.ta.value;
      if (!text.trim()) return;
      mine.saving = true;
      setState('saving');
      const r = await engine('apiSaveDraft', { id: mine.id, text: text }, mine.brand);
      mine.saving = false;
      if (st !== mine) return;
      if (r.ok) {
        mine.base = text;
        if (S.tk && S.tk.id === mine.id && S.tk.ticket) S.tk.ticket.draft_text = text;
        if (mine.ta.value === text) { mine.dirty = false; dropLocal(); setState('saved'); } else writeLocal();
        showProblem(r.problem ? (r.problem_msg || r.problem) : null);
      } else {
        setState('fail', r.msg || r.error);
      }
      if (mine.again) { mine.again = false; save(); }
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
      const problemEl = h('div', { class: 'problem', hidden: true });
      const note = h('div');
      st.stateEl = stateEl; st.problemEl = problemEl;
      const errEl = h('div', { hidden: true });
      const c = h('div', { class: 'card draft' }, h('h3', { text: t('draft') }), note, ta, stateEl, problemEl, errEl);
      if (!isOpen) {
        ta.readOnly = true;
        if (local) dropLocal();
        c.append(h('div', { class: 'muted small', text: t('draft_readonly') }));
        return c;
      }
      if (local && local.text !== server && local.text.trim()) {
        ta.value = local.text;
        st.dirty = true;
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
        st.dirty = true;
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
      function sendDisabled() { return isDry() || !ta.value.trim(); }
      const actions = h('div', { class: 'actions' });
      const all = [];
      function lock(on) { all.forEach(function (b) { b.disabled = on || (b === sendBtn && sendDisabled()); }); }
      function showErr(r) {
        clear(errEl);
        errEl.hidden = false;
        const box = h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error }));
        if (r.error === 'draft_problem') {
          const ob = armed(t('send_anyway'), t('send_arm'), 'danger-outline small', function () { doSend(true); });
          box.append(h('div', { class: 'actions' }, ob));
        }
        errEl.append(box);
      }
      async function doSend(override) {
        const text = ta.value;
        lock(true);
        clear(errEl); errEl.hidden = true;
        clearTimeout(st.timer);
        const args = { id: x.id, text: text };
        if (override) args.override = true;
        const r = await engine('apiSend', args, st.brand);
        if (r.ok) {
          st.dirty = false; dropLocal();
          toast(r.queued ? t('queued_ok') : t('sent_ok'));
          await afterAction();
          return;
        }
        lock(false);
        showErr(r);
      }
      async function doClose(fn, okMsg) {
        lock(true);
        clear(errEl); errEl.hidden = true;
        const r = await engine(fn, { id: x.id }, st.brand);
        if (r.ok) { st.dirty = false; dropLocal(); toast(okMsg); await afterAction(); return; }
        lock(false);
        showErr(r);
      }
      const sendBtn = armed(t('send'), t('send_arm'), 'primary', function () { if (!sendDisabled()) doSend(false); });
      st.refreshSend = function () {
        if (sendBtn.classList.contains('arm')) return;
        sendBtn.disabled = sendDisabled();
        sendBtn.textContent = isDry() && S.boots[st.brand] ? t('send_dry') : t('send');
        sendBtn.title = isDry() ? t('dry_run') : '';
      };
      st.refreshSend();
      const handledBtn = armed(t('handled'), t('handled_arm'), '', function () { doClose('apiMarkHandled', t('handled_ok')); });
      const closeBtn = armed(t('close'), t('close_arm'), 'ghost', function () { doClose('apiClose', t('closed_ok')); });
      all.push(sendBtn, handledBtn, closeBtn);
      actions.append(sendBtn, handledBtn, closeBtn);
      c.append(actions);
      return c;
    }
    return { card: card, flush: flush, detach: detach, isDirty: function () { return !!(st && (st.dirty || st.saving)); },
      refreshSend: function () { if (st && st.refreshSend) st.refreshSend(); } };
  })();

  async function afterAction() {
    const id = S.tk && S.tk.id;
    await loadBoot(S.brand);
    if (id && S.tk && S.tk.id === id) openTicket(id);
  }

  // ---- orders
  function ordersCard(ex) {
    const c = h('div', { class: 'card' }, h('h3', { text: t('orders') }));
    const orders = ex.orders || [];
    const sh = ex.shipping || null;
    if (sh && sh.state && sh.state !== 'unknown' && sh.orderName) {
      c.append(h('p', { class: 'small ship-line' }, h('span', { class: 'chip ' + (sh.state === 'not_late' ? 'ok' : sh.state === 'not_applicable' ? '' : 'bad'), text: sh.orderName }), ' ',
        t('ship_line', { state: t('ship_' + sh.state), d: sh.daysSinceOrder, n: sh.normalDays, l: sh.lateDays })));
    }
    if (!orders.length) {
      c.append(h('div', { class: 'muted', text: ex.lookup === 'error' ? t('lookup_error') : t('no_orders') }));
      return c;
    }
    const list = h('div', { class: 'sub-list' });
    orders.forEach(function (o) {
      const tracks = [];
      (o.fulfillments || []).forEach(function (f) {
        (f.tracking || []).forEach(function (tr) {
          const u = safeUrl(tr.url);
          const label = [tr.company, tr.number].filter(Boolean).join(' · ') || t('track');
          tracks.push(u ? h('a', { href: u, target: '_blank', rel: 'noopener noreferrer', class: 'ltr', text: label }) : h('span', { class: 'ltr', text: label }));
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
    const subs = ex.subscriptions || [];
    if (!subs.length) { c.append(h('div', { class: 'muted', text: t('no_subs') })); return c; }
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
          h('dt', { text: t('sub_id') }), h('dd', null, h('span', { class: 'ltr', text: contractNum(s.id) }))));
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
            const res = await Promise.all([engine('apiTicket', { id: x.id }), engine('apiTicketExtras', { id: x.id })]);
            if (S.tk && S.tk.id === x.id && res[0].ok) {
              S.tk.ticket.cancelled = res[0].ticket.cancelled;
              if (res[1].ok) S.tk.extras = res[1].extras || {};
              const slot = document.getElementById('subs-card');
              if (slot) { clear(slot); slot.append(subsCard(S.tk.extras || {}, S.tk.ticket)); }
            }
          }
          return;
        }
        go.disabled = code.value.length !== 4;
        result.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error }),
          r.message ? h('span', { class: 'raw', text: r.message }) : null));
      });
      const warn = [];
      if (b.cancelFrozen) warn.push(h('div', { class: 'problem', text: t('dlg_frozen') }));
      else if (b.cancelEnabled === false) warn.push(h('div', { class: 'problem', text: t('dlg_off') }));
      dlg.append(h('div', { class: 'in' },
        h('h3', { text: t('dlg_title') }),
        h('div', null, h('b', { dir: 'auto', text: items || '—' }), ' ', h('span', { class: 'chip', text: t('ss_' + s.status) })),
        h('div', { class: 'small muted' }, t('sub_id') + ': ', h('span', { class: 'ltr', text: num }), ' · ', x.email ? h('span', { class: 'ltr', text: x.email }) : null),
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
      const fresh = await engine('apiTicket', { id: x.id });
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
    const r = await engine('apiSearch', { q: q }, k.brand);
    if (S.tk !== k) return;
    k.related = r.ok ? (r.tickets || []).filter(function (x) { return x.id !== k.id; }) : [];
    k.relatedErr = r.ok ? null : (r.msg || r.error);
    paintRelated();
  }
  function relatedCard() {
    const c = h('div', { class: 'card related' }, h('h3', { text: t('related') }));
    const k = S.tk;
    if (!k || k.related === null || k.related === undefined) c.append(h('div', { class: 'muted small', text: t('loading') }));
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
      dlg.append(h('div', { class: 'in' }, h('h3', { text: opts.title }), opts.body ? h('p', { class: 'm0', text: opts.body }) : null,
        opts.extra || null, h('div', { class: 'row-btns' }, no, ok)));
      dlg.showModal();
      setTimeout(function () { no.focus(); }, 0);
    });
  }

  // ---------------------------------------------------------------- automatic cancellations queue
  async function loadAuto(brand) {
    const r = await engine('apiAutoCancelList', {}, brand);
    // An engine without these functions answers "unauthorized" (Api.gs gives no function-name oracle).
    if (r.ok) S.auto[brand] = { items: Array.isArray(r.items) ? r.items : [], switch: r.switch || null, mode: r.mode || null };
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
      const r = await engine('apiTicketExtras', { id: tid });
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
        parts.push(ok ? t('ac_ev_auth_ok') : t('ac_ev_auth_bad') + ' ' + t('ac_ev_auth_detail', { d: String(ev.dkim), s: String(ev.spf) }));
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
      const chipCls = kd === 'approvable' ? 'st-action' : kd === 'flight' ? 'st-sent' : 'bad';
      card.append(h('div', { class: 'hd' },
        kd === 'flight' ? h('span', { class: 'spinner', 'aria-hidden': 'true' }) : null,
        h('span', { class: 'chip ' + chipCls, text: stateText(it) }),
        it.approvedBy ? h('span', { class: 'chip outline', text: t('ac_approved_by', { u: it.approvedBy }) }) : null,
        it.ticketStatus ? h('span', { class: 'chip outline', text: t('ac_ticket_status', { s: t('st_' + it.ticketStatus) }) }) : null,
        it.email ? h('span', { class: 'ltr muted small', text: it.email }) : null));
      if (it.subject || it.summary) card.append(h('div', null, it.subject ? h('b', { dir: 'auto', text: it.subject }) : null, it.summary ? h('div', { class: 'small', dir: 'auto', text: it.summary }) : null));
      if (kd === 'reply_failed') card.append(h('div', { class: 'err-box', role: 'alert' }, h('b', { text: t('ac_state_cancelled_reply_failed') }), it.error ? h('span', { class: 'raw', text: String(it.error) }) : null));
      else if (kd === 'stopped' && it.error) card.append(h('div', { class: 'err-box' }, h('span', { class: 'raw', text: String(it.error) })));
      const msgSlot = h('div', { class: 'msg customer ac-msg' }, h('span', { class: 'muted small', text: t('loading') }));
      card.append(h('div', { class: 'small muted', text: t('ac_last_msg') }), msgSlot);
      fetchMessage(it, msgSlot);
      card.append(h('dl', { class: 'kv' },
        h('dt', { text: t('ac_contract') }), h('dd', null, h('span', { class: 'ltr', text: contractNum(it.contractId) || '—' })),
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
          h('span', { class: 'raw', text: [r.error, r.state, r.reason, r.problem].filter(Boolean).join(' · ') })));
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

  // ---------------------------------------------------------------- system mode (admin)
  const Settings = (function () {
    const KEYS = [['DRY_RUN', ['on', 'off']], ['KACHING_WRITES', ['on', 'off']], ['AUTO_CANCEL', ['off', 'shadow', 'on']]];
    function norm(key, v) {
      if (v === undefined || v === null) return null;
      if (key === 'AUTO_CANCEL') { const s = String(v).toLowerCase(); return s === 'true' ? 'on' : s === 'false' ? 'off' : s; }
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
      p.append(h('h2', { text: t('set_title', { b: brandName(brand) }) }));
      const st = S.settings[brand];
      if (st && st.refusal) p.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: t('set_refused') + ' ' + st.refusal.msg }),
        h('span', { class: 'raw', 'data-test': 'refusal-raw', text: st.refusal.raw })));
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
            const yes = await confirmDlg({ title: t('set_confirm_q', { k: t('set_' + k), v: t('val_' + v), b: brandName(brand) }), body: t('set_' + k + '_help'), ok: t('ok'), danger: v === 'on' || (k === 'DRY_RUN' && v === 'off') });
            if (!yes) return;
            seg.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
            const r = await engine('apiSettings', { action: 'set', key: k, value: v }, brand);
            S.settings[brand].refusal = r.ok ? null : {
              msg: r.msg || '',
              raw: [r.error, r.reason, Array.isArray(r.allowed) ? 'allowed: ' + r.allowed.join('|') : null].filter(Boolean).join(' · ')
            };
            if (r.ok) toast(r.noop ? t('set_noop') : t('set_ok') + ' (' + k + ': ' + r.from + ' → ' + r.to + ')');
            if (r.ok && k === 'AUTO_CANCEL') loadAuto(brand);
            await load(brand);
            await loadBoot(brand);
          });
          seg.append(b);
        });
        p.append(h('div', { class: 'card set-row' }, h('div', { class: 'set-hd' }, h('b', { text: t('set_' + k) }), h('span', { class: 'ltr muted small', text: k })),
          h('div', { class: 'muted small', text: t('set_' + k + '_help') }), seg));
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
          al.append(h('div', null, h('span', { class: 'muted', text: fmtDate(l.time, true) + ' · ' }), h('b', { text: l.actor }), ' ', h('span', { class: 'ltr', text: l.action }),
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
      c.append(h('div', { class: 'small muted' }, (u.brands.length ? u.brands.map(brandName).join(' · ') : '—') + ' · ' + t('lang_' + u.lang) + ' · ' +
        t('u_last') + ': ' + (u.last_login ? fmtDate(u.last_login, true) : t('u_never'))));
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
    window.addEventListener('hashchange', route);
    route();
  }
  start();
})();
