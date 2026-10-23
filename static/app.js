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
      local_older: 'הלקוח כתב שוב אחרי שערכת את הטיוטה הזאת במכשיר. מוצגת הטיוטה החדשה.', use_mine_old: 'להחזיר את הגרסה שלי',
      search_archive_wait: 'מחפש בארכיון…', tpl_load_failed: 'לא הצלחנו לטעון את התבניות כרגע.', tpl_retry: 'לנסות שוב',
      send: 'שליחה', send_arm: 'לחצו שוב לשליחה', send_dry: 'השליחה כבויה (מצב ניסיון)', sent_ok: 'נשלח ללקוח', queued_ok: 'נכנס לתור הוואטסאפ',
      send_anyway: 'לשלוח בכל זאת (יירשם ביומן)', handled: 'טופל בלי שליחה', handled_arm: 'לחצו שוב — טופל בלי שליחה',
      close: 'סגירה', close_arm: 'לחצו שוב לסגירה', closed_ok: 'הפנייה נסגרה', handled_ok: 'סומן כטופל',
      close_ns: 'סגירה בלי שליחה', close_ns_arm: 'ללחוץ שוב לסגירה', close_ns_title: 'הפנייה נסגרת בלי לשלוח ללקוח. בוואטסאפ היא נסגרת גם בדונדי.',
      // Owner, 2026-10-11: sending never closes the ticket; another message on any answered / closed ticket; two agents on one ticket
      close_tk: 'סגירת הפנייה', close_tk_arm: 'ללחוץ שוב לסגירה', close_tk_title: 'סוגרים את הפנייה ועוברים לפנייה הבאה. בוואטסאפ היא נסגרת גם בדונדי.',
      // Owner, 2026-10-14 (from the CS team): send + close in one action, a different AI answer, answer later
      send_close: 'שליחה וסגירה', send_close_arm: 'ללחוץ שוב — שליחה וסגירה', send_close_title: 'שולחים ללקוח, סוגרים ועוברים לפנייה הבאה מיד. אם השליחה לא תצליח, הפנייה לא תיסגר ותחזור לראש הרשימה.',
      en_confirm_close: 'אישור, שליחה וסגירה',
      ob_queued_close: '⏳ תיסגר מיד אחרי השליחה', ob_close_dropped: '{name}: השליחה לא הצליחה, ולכן הפנייה לא נסגרה. היא בראש הרשימה.',
      rd_btn: 'תשובה אחרת', rd_ph: 'מה לשנות? (לא חובה) למשל: יותר קצר, בלי הצעת הנחה', rd_busy: 'כותב תשובה אחרת…', rd_done: 'נכתבה תשובה אחרת.',
      rd_undo: 'חזרה לטיוטה הקודמת', rd_undone: 'הטיוטה הקודמת חזרה.', rd_title: 'ה-AI כותב תשובה אחרת לפי השיחה. אפשר לכתוב בקצרה מה לשנות. כל הבדיקות הרגילות חלות גם עליה.',
      rd_tr_failed: 'התשובה החדשה נכתבה, אבל התרגום נכשל: {m}', rd_left: 'אפשר עוד {n} בשעה הזאת',
      snz_btn: 'לענות מאוחר יותר', snz_30m: 'עוד 30 דקות', snz_1h: 'עוד שעה', snz_2h: 'עוד שעתיים', snz_eod: 'סוף היום (17:00)',
      snz_until: 'נדחה עד {t}', snz_cancel: 'להחזיר עכשיו', snz_ok: 'נדחה עד {t}. הפנייה תחזור לראש הרשימה שלך.', snz_back: '⏰ חזרה מדחייה',
      snz_section: 'נדחו', snz_title: 'הפנייה נעלמת רק מהרשימה שלך וחוזרת לראשה בזמן שבחרת, או מיד אם הלקוח כותב שוב. שאר הנציגים ממשיכים לראות אותה.',
      snz_failed: 'הדחייה לא נשמרה: {m}',
      fu_title: 'הודעה נוספת ללקוח', fu_ph: 'אפשר לכתוב כאן הודעה נוספת ללקוח…', fu_sent: 'נענתה · {who} · {when}', fu_done: 'נסגרה · {who} · {when}',
      fu_queued: 'הודעה בדרך לוואטסאפ · {who} · {when}', fu_hint: 'ההודעה נשלחת ללקוח באותה שיחה. הפנייה לא נפתחת מחדש.',
      fu_wait: 'ההודעה הקודמת עדיין בדרך ללקוח. אפשר כבר לכתוב את הבאה — השליחה תיפתח כשהקודמת תצא.',
      fu_restored: 'ההודעה לא נשלחה — הטקסט שלך הוחזר לתיבה.', msg_pending: '⏳ בדרך ללקוח', msg_queued: '📤 בתור לוואטסאפ',
      cm_answered: '{who} כבר ענה/תה בפנייה הזאת ב-{when}, אחרי שפתחת אותה.', cm_closed: '{who} כבר סגר/ה את הפנייה הזאת ב-{when}, אחרי שפתחת אותה.',
      cm_kept: 'ההודעה שלך לא נשלחה, והטקסט שלך נשמר בתיבה. קראו את מה שנשלח בשיחה, ואם עדיין צריך — שלחו אותה כהודעה נוספת.',
      cm_send_anyway: 'לשלוח בכל זאת כהודעה נוספת', cm_tpl_anyway: 'לשלוח את התבנית בכל זאת',
      who_dondy: 'מישהו בדונדי', who_gmail: 'מישהו מ-Gmail', who_bot: 'המענה האוטומטי', who_merge: 'מיזוג פניות', who_someone: 'מישהו', who_me: 'את/ה',
      pres_view: 'גם {who} בפנייה הזאת עכשיו', pres_edit: '✍️ {who} כותב/ת תשובה בפנייה הזאת עכשיו — כדאי לתאם לפני ששולחים',
      safety: 'בדיקת בטיחות: {p}',
      orders: 'הזמנות', no_orders: 'לא נמצאה הזמנה (הזמנות מעל 60 יום לא נראות).', lookup_error: 'בדיקת ההזמנות נכשלה ברגע הכתיבה.',
      track: 'מעקב', items: 'פריטים', ordered: 'הוזמן', shipped_on: 'נשלח',
      ship_not_late: 'בזמן', ship_late: 'מאחר', ship_very_late: 'מאחר מאוד', ship_unknown: 'לא ידוע', ship_not_applicable: 'לא רלוונטי',
      ship_line: '{state} · {d} ימים מההזמנה',
      fin_PAID: 'שולם', fin_PENDING: 'ממתין לתשלום', fin_REFUNDED: 'הוחזר', fin_PARTIALLY_REFUNDED: 'הוחזר חלקית', fin_VOIDED: 'בוטל',
      fin_AUTHORIZED: 'מאושר', fin_PARTIALLY_PAID: 'שולם חלקית',
      dlv_steps: 'הוזמן|נשלח|בדרך|אמור להגיע', dlv_cancelled: 'ההזמנה בוטלה', dlv_prep: 'בהכנה במחסן (יום {d} מההזמנה)', dlv_prep_late: 'מתעכב: {d} ימים מההזמנה ועוד לא נשלח', dlv_shipped: 'נשלח מהמחסן, צפי הגעה {a}–{b}', dlv_transit: 'בדרך ללקוח, צפי הגעה {a}–{b}', dlv_arriving: 'אמור להגיע בימים אלה ({a}–{b})', dlv_due: 'היה אמור להגיע עד {b}. כדאי לוודא עם הלקוח', dlv_late: 'באיחור: {d} ימים מההזמנה', dlv_note: 'הערכה לפי תאריכי ההזמנה והשליחה (אין מעקב חי מחברת השילוח)',
      ful_FULFILLED: 'נשלח', ful_UNFULFILLED: 'עוד לא נשלח', ful_PARTIALLY_FULFILLED: 'נשלח חלקית', ful_IN_PROGRESS: 'בהכנה',
      ful_ON_HOLD: 'בהמתנה', ful_SCHEDULED: 'מתוזמן', ful_RESTOCKED: 'הוחזר למלאי',
      subs: 'מנויים', no_subs: 'אין מנויים ללקוח הזה (לפי המייל).', sub_status: 'סטטוס', sub_every: 'תדירות', sub_next: 'חיוב הבא',
      sub_next_na: 'לא מגיע מהמנוע', sub_since: 'מאז', sub_lastpay: 'תשלום אחרון', sub_id: 'מספר מנוי',
      pay_SUCCEEDED: 'עבר בהצלחה', pay_FAILED: 'נכשל', pay_PENDING: 'בתהליך', pay_REFUNDED: 'הוחזר',
      ss_ACTIVE: 'פעיל', ss_PAUSED: 'מושהה', ss_CANCELLED: 'מבוטל', ss_FAILED: 'תשלום נכשל', ss_EXPIRED: 'פג תוקף',
      every_day: 'כל יום', every_week: 'כל שבוע', every_month: 'כל חודש', every_year: 'כל שנה', every_n: 'כל {n} {u}',
      unit_day: 'ימים', unit_week: 'שבועות', unit_month: 'חודשים', unit_year: 'שנים',
      cancel_sub: 'ביטול מנוי', cancelled_here: 'בוטל דרך המערכת',
      oe_btn: 'עריכת הזמנה', oe_title: 'עריכת הזמנה בשופיפיי', oe_loading: 'טוען את ההזמנה משופיפיי…', oe_err_load: 'לא הצלחנו לטעון את ההזמנה.',
      oe_off: 'עריכת הזמנות כבויה כרגע — גיא צריך להדליק אותה.', oe_off_cred: 'עריכת הזמנות עוד לא מחוברת לשופיפיי — מחכה לאישור של גיא.', oe_off_frozen: 'עריכת הזמנות מוקפאת כרגע.',
      oe_tab_items: 'פריטים', oe_tab_address: 'כתובת ופרטי משלוח', oe_total: 'סכום ההזמנה', oe_qty: 'כמות', oe_zero: '0 = להסיר את הפריט מההזמנה.', oe_add: 'הוספת מוצר', oe_pick: 'בחרו מוצר…',
      oe_variants_loading: 'טוען מוצרים…', oe_next_items: 'בדיקת מחיר', oe_next_address: 'המשך לאישור', oe_back: 'חזרה', oe_nochange: 'לא שונה כלום.', oe_bad_qty: 'כמות: מספר שלם בין 0 ל-20 (להוספה: 1 עד 20).',
      oe_f_firstName: 'שם פרטי', oe_f_lastName: 'שם משפחה', oe_f_address1: 'רחוב ומספר', oe_f_address2: 'דירה / קומה / הערה', oe_f_city: 'עיר', oe_f_zip: 'מיקוד', oe_f_phone: 'טלפון',
      oe_confirm: 'מה יקרה:', oe_delta_up: 'סכום ההזמנה יעלה ב-{d}', oe_delta_down: 'סכום ההזמנה ירד ב-{d}', oe_delta_zero: 'סכום ההזמנה לא ישתנה', oe_total_line: 'מ-{a} ל-{b}',
      oe_settle_up: 'הלקוח לא יחויב אוטומטית. את ההפרש גובים בשופיפיי.', oe_settle_down: 'הלקוח לא יזוכה אוטומטית. את ההחזר מסדרים בשופיפיי.',
      oe_money_note: 'המערכת לא גובה, לא מחזירה כסף ולא שולחת הודעה ללקוח. הפרש מחיר — גבייה או החזר — מסדרים בשופיפיי.',
      oe_ln_change: '{p}: מ-{a} ל-{b}', oe_ln_add: '{p}: נוסף × {q}', oe_ln_remove: '{p}: יוסר מההזמנה', oe_addr_change: '{f}: מ-{a} ל-{b}',
      oe_needs_admin: 'העלאת סכום ההזמנה דורשת אדמין. אפשר להוריד כמות, להסיר פריט או להוסיף מוצר בחינם.',
      oe_type: 'הקלידו את מספר ההזמנה ({n}) כדי לאשר', oe_reason: 'סיבה (לא חובה)', oe_go: 'בצעו את השינוי בשופיפיי', oe_working: 'מבצע…', oe_done: 'ההזמנה עודכנה בשופיפיי ✓',
      oe_unverified: 'שופיפיי קיבל את הבקשה, אבל השינוי עוד לא מופיע. לבדוק בשופיפיי — לא לחזור על הפעולה.', oe_close: 'סגירה', oe_cannot: 'אי אפשר לערוך את ההזמנה כאן: {why}',
      manage_sub: 'ניהול מנוי', mg_title: 'ניהול מנוי', mg_loading: 'טוען את המנוי מקצ׳ינג…', mg_err_load: 'לא הצלחנו לטעון את המנוי.',
      mg_pause: 'השהיית מנוי', mg_resume: 'חידוש מנוי', mg_reactivate: 'הפעלה מחדש', mg_cancel: 'ביטול מנוי',
      mg_cycles: 'משלוחים וחיובים הבאים', mg_no_cycles: 'אין משלוחים עתידיים.', mg_cycle_n: 'משלוח {n}', mg_skipped: 'מדולג',
      mg_skip: 'דילוג', mg_unskip: 'ביטול הדילוג', mg_resched: 'שינוי תאריך', mg_new_date: 'תאריך חדש',
      mg_lines: 'מוצרים במנוי', mg_qty: 'כמות', mg_price: 'מחיר ליחידה', mg_change: 'שינוי', mg_remove: 'הסרה', mg_add_line: 'הוספת מוצר',
      mg_swap: 'החלפה למוצר', mg_keep: 'בלי החלפה', mg_pick: 'בחרו מוצר…', mg_variant: 'מוצר מהחנות', mg_variants_loading: 'טוען מוצרים מהחנות…',
      mg_price_opt: 'מחיר ליחידה (ריק = בלי שינוי)', mg_price_new_opt: 'מחיר ליחידה (ריק = מחיר המנוי של החנות)',
      mg_discounts: 'הנחות', mg_no_discounts: 'אין הנחות במנוי.', mg_add_discount: 'הוספת הנחה', mg_dtype: 'סוג', mg_dtype_pct: 'אחוזים (%)',
      mg_dtype_fixed: 'סכום קבוע', mg_dvalue: 'ערך', mg_dtitle: 'שם ההנחה (הלקוח רואה אותו)', mg_dcycles: 'לכמה משלוחים (ריק = לתמיד)',
      mg_dc_forever: 'לתמיד', mg_dc_n: 'ל-{n} משלוחים',
      mg_next: 'המשך לאישור', mg_type: 'כדי לאשר, הקלידו את 4 הספרות האחרונות של מספר המנוי', mg_reason: 'הערה ליומן (אופציונלי)',
      mg_go: 'לבצע', mg_working: 'מבצע…', mg_back: 'חזרה', mg_close: 'סגירה', mg_confirm: 'מה יקרה:',
      mg_off: 'לפי המנוע, שינויים במנויים כבויים כרגע — סביר שהבקשה תסורב.', mg_frozen: 'שינויים במנויים מוקפאים כרגע — סביר שהבקשה תסורב.',
      mg_done: 'בוצע ✓', mg_unverified: 'קצ׳ינג קיבל את הבקשה, אבל השינוי עוד לא מופיע. לבדוק בקצ׳ינג — לא לחזור על הפעולה.',
      mg_do_pause: 'להשהות את המנוי. לא יהיו חיובים ומשלוחים עד שמחדשים אותו.', mg_do_resume: 'לחדש את המנוי. החיובים והמשלוחים חוזרים לפי הלוח.',
      mg_do_reactivate: 'להפעיל מחדש מנוי מבוטל. הלקוח יחויב שוב לפי הלוח.', mg_do_skip: 'לדלג על משלוח {n} ({d}): לא יהיה חיוב ולא משלוח בתאריך הזה.',
      mg_do_unskip: 'להחזיר את משלוח {n} ({d}).', mg_do_reschedule: 'להזיז את משלוח {n} מ-{d} ל-{nd}.',
      mg_do_add_discount: 'להוסיף הנחה «{title}»: {v}, {c}.', mg_do_add_line: 'להוסיף למנוי: {q} × {p}{pr}.',
      mg_do_update_line: 'לשנות את «{p}»: {what}.', mg_do_remove_line: 'להסיר מהמנוי את «{p}».',
      mg_w_qty: 'כמות {q}', mg_w_swap: 'החלפה ל{p}', mg_w_price: 'מחיר {pr} ליחידה',
      afs_title: 'ההודעה ל{name} נשלחה. נשאר לטפל:', afs_open: 'פתח את הפנייה', afs_done: 'טיפלתי', afs_chip: 'נשאר לטפל', afs_cancelled: 'המנוי של {name} בוטל אוטומטית',
      afs_sub_no_email: 'המנוי לא בוטל: לא מזוהה מייל של הזמנה ללקוח, אז אי אפשר למצוא את המנוי. לבקש מהלקוח מספר הזמנה או מייל, לקשר בפאנל ההזמנות ולבטל.',
      afs_sub_unreachable: 'המנוי לא בוטל: לא הצלחנו להתחבר למערכת המנויים. לבטל ידנית.',
      afs_sub_several: 'המנוי לא בוטל: ללקוח יש כמה מנויים פעילים. לבחור איזה לבטל בפאנל המנויים.',
      afs_sub_refused: 'המנוי לא בוטל: מערכת המנויים דחתה את הביטול. לבטל ידנית.',
      afs_order_cancel: 'לפי שופיפיי ההזמנה עדיין לא בוטלה. לבטל אותה בשופיפיי.', afs_newer_message: 'הלקוח כתב הודעה נוספת לפני שהתשובה נשלחה. לקרוא אותה ולוודא שהתשובה עונה גם עליה.',
      afs_order_refund: 'לפי שופיפיי עדיין לא בוצע החזר. לבצע את ההחזר בשופיפיי.',
      // "לבטל את המנוי" in the send area (the owner's CS team, 2026-10-16)
      sx_btn: 'לבטל את המנוי', sx_off_token: 'אין חיבור לקאצ\'ינג במותג הזה — לבטל ידנית ב-Kaching.',
      sx_off_frozen: 'ביטולים מוקפאים כרגע במערכת — לבטל ידנית ב-Kaching.', sx_off_writes: 'ביטולים כבויים במערכת — לבטל ידנית ב-Kaching.',
      sx_checking: 'בודק בקאצ\'ינג את המנויים של {name}…', sx_q_one: 'לבטל את המנוי של {name}?', sx_q_many: 'ל{name} יש {n} מנויים פעילים. איזה לבטל?',
      sx_none: 'לא נמצא בקאצ\'ינג מנוי למייל {email}. אם הלקוח הזמין עם מייל או טלפון אחר, לבקש ממנו את מספר ההזמנה או את המייל של ההזמנה ולקשר כאן:',
      sx_ended: '✅ המנוי של {name} כבר מבוטל בקאצ\'ינג (נבדק עכשיו, {t}). אין מה לבטל שוב.',
      sx_noemail: 'לא מזוהה מייל של הזמנה ללקוח הזה (למשל: בפנייה יש רק טלפון שלא תואם להזמנה), אז אי אפשר למצוא את המנוי. לבקש מהלקוח את מספר ההזמנה או את המייל שאיתו הזמין, ולקשר כאן:',
      lk_ph: 'מספר הזמנה (#12057) או מייל שהלקוח מסר', lk_go: 'מצא וקשר', lk_working: 'מחפש בחנות…', lk_ok: '🔗 מקושר ללקוח {email}',
      lk_orders: 'הזמנות: {o}', lk_by: 'קישר: {by}, {t}', lk_unlink: 'ביטול הקישור', lk_other: '🔗 לא הלקוח הנכון? קישור לפי מספר הזמנה או מייל',
      lk_hint: 'הפרטים בפנייה לא מובילים להזמנה? לבקש מהלקוח את מספר ההזמנה או את המייל של ההזמנה, ולקשר כאן:', lk_done: 'הלקוח קושר לפנייה',
      sx_go: 'כן, לבטל את המנוי', sx_back: 'חזרה', sx_working: 'מבטל ובודק בקאצ\'ינג…',
      sx_note: 'אחרי הביטול המערכת קוראת את המנוי שוב מקאצ\'ינג ומאשרת שהוא באמת מבוטל.',
      sx_ok: '✅ המנוי בוטל — אומת בקאצ\'ינג {t}', sx_ok_old: '✅ המנוי בוטל דרך המערכת', sx_fail: '❌ המנוי לא בוטל',
      sx_manual: 'לבטל ידנית ב-Kaching.', sx_unknown: 'לא ידוע אם המנוי בוטל. לבדוק ב-Kaching לפני ניסיון נוסף.',
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
      photo_wait: '📷 תמונה — עוד לא הגיעה', photo_gone: '📷 תמונה — נמחקה אחרי 7 ימים, לצפייה בדונדי', voice_wait: '🎤 הודעה קולית — עוד לא הגיעה', voice_dondy: '🎤 הודעה קולית — לשמיעה בדונדי', voice_gone: '🎤 הודעה קולית — נמחקה אחרי 30 יום', media_video: '🎬 וידאו — לצפייה בדונדי', media_file: '📎 קובץ — לצפייה בדונדי',
      att_btn: '📎 צירוף קובץ', att_uploading: 'מעלה…', att_failed: 'לא הועלה', att_remove: 'הסרת הקובץ', att_hint: 'PDF, תמונה, Word, Excel או TXT · עד {mb}MB לקובץ',
      att_hint_wa: 'קובץ אחד: PDF, JPG, PNG, Word או Excel · עד {mb}MB', att_type: 'סוג קובץ לא נתמך: {name}', att_size: 'הקובץ גדול מדי: {name} (עד {mb}MB)',
      att_total: 'כל הקבצים יחד גדולים מדי (עד {mb}MB למייל)', att_count: 'אפשר לצרף עד {n} קבצים', att_wa_one: 'בוואטסאפ אפשר לצרף קובץ אחד להודעה',
      att_wait: 'ממתינים לסיום ההעלאה או להסרת קובץ שנכשל', att_sent_chip: '📎 {name}',
      err_bad_engine: 'המנוע החזיר תשובה לא תקינה. נסו שוב בעוד רגע.',
      ob_flight_send: '⏳ נשלח ברקע…', ob_flight_close: '⏳ נסגר ברקע…', ob_ok_email: '✅ נשלח', ob_ok_wa: '✅ נשלח לוואטסאפ', ob_ok_queued: '📤 נכנס לתור',
      ob_ok_close: '✅ טופל', ob_refused: '⚠️ לא נשלח — צריך תיקון', ob_refused_close: '⚠️ לא נסגר — צריך תיקון', ob_unknown: '❓ לא אושר — לבדוק',
      ob_checking: '⏳ בודק מה קרה לשליחה…', ob_elsewhere: 'ℹ️ כבר נענה מ-Gmail — לא נשלח שוב', ob_toast_elsewhere: '{name}: הלקוח כבר נענה מ-Gmail. לא נשלחה תשובה נוספת, והפנייה נסגרה.', ob_retry: '⏳ מנסה לשלוח שוב…', ob_retry_close: '⏳ מנסה לסגור שוב…', ob_retry_n: 'ניסיון {n} מתוך {max}. המערכת מנסה שוב לבד, אין צורך לשלוח שוב.', ob_unsent: '⚠️ השליחה לא בוצעה — אפשר לשלוח שוב', ob_header: 'בתהליך שליחה ({n})', ob_none: 'אין שליחות בתהליך',
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
      ac_approve: 'לאשר ולבטל', ac_approve_q: 'לאשר את הביטול?', ac_approve_body: 'המנוי יבוטל ותשלח תשובה ללקוח בעוד כמה דקות.',
      ac_manual: 'העבר לטיפול ידני', ac_note_ph: 'למה לטיפול ידני? (חובה)', ac_manual_go: 'העבר', ac_note_req: 'צריך לכתוב הערה.',
      ac_ok: 'אושר — המנוי יבוטל והתשובה תישלח בעוד כמה דקות', ac_moved: 'הועבר לטיפול ידני', ac_refused: 'המנוע סירב:', ac_mode: 'מצב: {m}',
      mode_off: 'כבוי', mode_live: 'חי', mode_shadow: 'צל',
      ok: 'אישור', cancel_btn: 'חזרה',
      settings: 'מצב מערכת', set_title: 'מצב מערכת — {b}', set_admin_only: 'רק אדמין.',
      set_DRY_RUN: 'מצב ניסיון', set_DRY_RUN_help: 'מצב ניסיון: טיוטות לגיליון בלבד, שום דבר לא נשלח',
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
      ar_reviewed_ok: '✓ נבדק ע״י {u}', ar_reviewed_problem: '⚠ סומן כבעיה ע״י {u}', ar_pending: 'ממתין לבדיקה', ar_banner: '🤖 הבוט ענה לבד ל-{n} לקוחות. צריך לעבור על כל תשובה ולוודא שהבוט לא כתב שטויות.', ar_banner_one: '🤖 הבוט ענה לבד ללקוח אחד. צריך לעבור על התשובה ולוודא שהבוט לא כתב שטויות.', ar_banner_go: 'לבדיקת התשובות', ar_open: 'פתיחת הפנייה',
      ar_done_ok: 'סומן כתקין', ar_done_problem: 'סומן כבעיה — הפנייה נפתחה מחדש', ar_na: 'התשובות האוטומטיות עוד לא זמינות במנוע של המותג הזה.',
      ar_mode: 'מענה אוטומטי: {m}', mode_auto_reply: 'מענה אוטומטי: {v}', what_to_do: 'מה לעשות',
      set_AUTO_REPLY: 'מענה אוטומטי', set_AUTO_REPLY_help: 'כבוי / צל: מסמן מה היה נשלח / פעיל: עונה לבד על מיילים פשוטים ומסמן לבדיקה',
      set_AUTO_REPLY_note: 'מצב "פעיל" דורש שמצב ניסיון יהיה כבוי.',
      syncing: 'טוען גרסה עדכנית…', checking: 'מתעדכן…', sync_failed: 'לא עודכן ({m}) — מוצג עותק מ{when}', tk_updated: 'יש גרסה חדשה של הפנייה', apply_update: 'הצג',
      live_new_msg: 'התקבלה הודעה חדשה', live_new_msgs: 'התקבלו {n} הודעות חדשות', live_ok: 'הבנתי',
      draft_new_avail: 'המנוע כתב טיוטה חדשה — הטיוטה שלך לא נגעה.', use_new_draft: 'החלף לטיוטה החדשה', draft_updated: 'הטיוטה עודכנה לפי ההודעה החדשה.',
      orders_err: 'בדיקת ההזמנות נכשלה: {m}', subs_err: 'בדיקת המנויים נכשלה: {m}',
      mailbox_at: 'התקבל בתיבה:', order_open: 'פתיחת ההזמנה בשופיפיי (בלשונית חדשה)',
      ain_title: 'שיפור ה-AI — הערות למנהלים', ain_help: 'ההערות של המנהלים מחייבות את ה-AI: הן נכנסות לכל טיוטה מהטיוטה הבאה, וגם הטיוטות הפתוחות בתור נכתבות מחדש לפיהן (טיוטה שנציג ערך ושמר לא נדרסת). על כל הערה המערכת עונה כאן ומעדכנת כשהיא נכנסה ונבדקה. תיקונים שהצוות עושה בטיוטות של ה-AI הופכים כאן להצעות להערות.',
      ain_r_gate: '⚠ נכנס למערכת, אבל בבדיקה ב-{b} כלל קבוע במערכת עצר או החליף את התשובה, ולכן ההערה לא מגיעה ללקוח: {gate}',
      ain_redraft: '✍️ {n} טיוטות פתוחות ב-{b} נכתבות מחדש לפי ההערה (תוך כמה דקות)', ain_redraft_1: '✍️ טיוטה פתוחה אחת ב-{b} נכתבת מחדש לפי ההערה (תוך כמה דקות)',
      ain_redraft_del: '✍️ {n} טיוטות פתוחות ב-{b} נכתבות מחדש בלי ההערה (תוך כמה דקות)', ain_redraft_del_1: '✍️ טיוטה פתוחה אחת ב-{b} נכתבת מחדש בלי ההערה (תוך כמה דקות)',
      ain_s_title: '💡 הצעות מהתיקונים של הצוות', ain_s_help: 'כשהצוות מתקן את אותו דבר בטיוטות של ה-AI שוב ושוב, המערכת מציעה כאן כלל. מה שמאשרים נכנס כהערה של המותג ועובר בדיקה כמו כל הערה.',
      ain_s_count: 'נמצא ב-{n} תיקונים', ain_s_examples: 'דוגמאות ({n})', ain_s_ex_c: 'הלקוח:', ain_s_ex_ai: 'ה-AI כתב:', ain_s_ex_sent: 'הצוות שלח:',
      ain_s_approve: '✅ להוסיף כהערה', ain_s_edit: '✏️ לערוך ולהוסיף', ain_s_reject: '✕ לא רלוונטי', ain_s_reject_arm: 'לא רלוונטי? לחצו שוב', ain_s_cancel: 'ביטול',
      ain_s_saving: 'שומר…', ain_s_added: 'ההצעה נוספה כהערה ל-{b}. היא מופיעה ברשימת ההערות למטה ועוברת בדיקה.', ain_s_rejected: 'ההצעה סומנה כלא רלוונטית ({b})',
      ain_s_noop: 'ההצעה הזאת כבר טופלה קודם ({b})', ain_s_fail: 'לא נשמר — {m}',
      ain_s_empty: 'עדיין אין הצעות ב-{b} · {n} תיקונים נאספו', ain_s_load_err: 'ההצעות לא נטענו מ-{b}: {m}', ain_s_loading: 'טוען הצעות…',
      ain_file_btn: '📎 צירוף קובץ (אישור / תעודה)', ain_file_clear: 'הסרת הקובץ', ain_file_big: 'הקובץ גדול מדי (עד 10MB).',
      ain_doc_hint: 'ההערה מדברת על אישור או תעודה: צרפו גם את הקובץ, וההערה תיכנס למערכת מיד.',
      ain_r_needs: '📎 קיבלתי. כדי שהבוט יגיד את זה ללקוחות צריך גם את הקובץ של האישור. העלו אותו כאן, וברגע שהוא עולה ההערה נכנסת למערכת ואעדכן כאן.',
      ain_r_attach: '📎 העלאת הקובץ', ain_r_uploading: 'מעלה את הקובץ…', ain_r_up_fail: 'הקובץ לא עלה ל-{b}: {m}',
      ain_r_checking: '⏳ נכנס למערכת. בודק עכשיו שהבוט באמת עונה לפי ההערה (עד דקה)…',
      ain_r_ok: '✅ נכנס למערכת ונבדק ({d}).', ain_r_ok_n: '✅ נכנס למערכת ונבדק ב-{n} מותגים ({d}).', ain_r_q: 'שאלתי את הבוט:', ain_r_a: 'הבוט ענה:',
      ain_r_no: '⚠ נכנס למערכת, אבל בבדיקה ב-{b} הבוט עוד לא ענה לפי ההערה: {why}', ain_r_err: 'נכנס למערכת. הבדיקה האוטומטית לא הצליחה לרוץ עכשיו ({b}).',
      ain_r_recheck: 'לבדוק שוב', ain_r_reply: 'תשובת המערכת', ain_r_file: '📄 {n}',
      ain_r_understood: '🧠 איך הבנתי:', ain_r_reading: '⏳ כותב איך הבנתי את ההערה…', ain_r_wrong: '✏️ לא הבנת נכון — לערוך',
      ain_edit_hint: 'ערכו את ההערה ולחצו "הוספת הערה". ההערה הקודמת תימחק ותוחלף בחדשה.', ain_replaced: 'ההערה הקודמת הוחלפה',
      ain_jump: '🧠 שיפור ה-AI', ain_ph: 'מה ה-AI צריך לעשות אחרת? למשל: "לא לכתוב \'מצטערים על אי הנוחות\' — לפתוח ישר בתשובה."',
      ain_scope: 'למי ההערה', ain_all: 'כל המותגים', ain_add: 'הוספת הערה', ain_adding: 'שומר…', ain_count: '{n}/600',
      ain_general: 'כללי — כל המותגים', ain_brand: 'רק {b}', ain_empty: 'אין עדיין הערות. הערה שתוסיפו תיכנס לטיוטות הבאות של ה-AI.',
      ain_by: '{u} · {d}', ain_del: '✕', ain_del_arm: 'למחוק? לחצו שוב', ain_del_title: 'מחיקת ההערה',
      ain_saved_all: 'נשמר בכל {n} המותגים', ain_saved_one: 'נשמר ל-{b}', ain_saved_part: 'נשמר ב-{ok} מתוך {n} מותגים — נכשל: {bad}',
      ain_save_fail: 'לא נשמר — {m}', ain_deleted: 'נמחק', ain_del_part: 'נמחק ב-{ok} מתוך {n} מותגים — נכשל: {bad}', ain_del_fail: 'לא נמחק — {m}',
      ain_missing: 'חסר ב: {b}', ain_fill: 'להשלים', ain_load_err: 'לא נטען מ-{b}: {m}', ain_retry: 'לטעון שוב', ain_loading: 'טוען הערות…',
      ain_not_conn: 'מותגים שלא מחוברים למערכת לא מקבלים הערות: {b}', ain_too_long: 'עד 600 תווים',
      // users
      u_title: 'ניהול משתמשים', u_new: 'משתמש חדש', u_username: 'שם משתמש (לועזית)', u_display: 'שם תצוגה', u_roles: 'תפקיד', u_brands: 'מותגים',
      u_lang: 'שפה', u_disabled: 'מושבת', u_active: 'פעיל', u_create: 'יצירה', u_save: 'שמירה', u_edit: 'עריכה', u_cancel: 'ביטול',
      u_reset: 'איפוס סיסמה', u_reset_arm: 'לחצו שוב לאיפוס', u_temp: 'סיסמה זמנית:', u_temp_note: 'מוצגת פעם אחת בלבד. שלחו אותה למשתמש בערוץ פרטי — בכניסה הראשונה יבחר סיסמה משלו.',
      u_saved: 'נשמר', u_created: 'המשתמש נוצר', u_last: 'כניסה אחרונה', u_never: 'עוד לא נכנס', u_audit: 'יומן שינויים (100 אחרונים)',
      u_must_change: 'סיסמה זמנית', role_agent: 'נציג/ה', role_admin: 'אדמין', 'role_user-manager': 'מנהל/ת משתמשים',
      lang_he: 'עברית', lang_en: 'אנגלית', u_admin_only: 'רק אדמין', u_me: 'אני',
      tr_loading: 'מתרגם לעברית…', tr_failed: 'התרגום נכשל: {m}', show_orig: 'הצג מקור', show_he: 'הצג תרגום', tr_from: 'תורגם אוטומטית מ{l}',
      tr_retry: 'לנסות שוב', tr_incomplete: '{n} לא תורגמו (מוצג המקור)', tr_reply_he: 'עונים ללקוח בעברית בלבד',
      lang_name_he: 'עברית', lang_name_ru: 'רוסית', lang_name_en: 'אנגלית', lang_name_ar: 'ערבית', lang_name_fr: 'צרפתית',
      lang_name_es: 'ספרדית', lang_name_de: 'גרמנית', lang_name_uk: 'אוקראינית', lang_name_am: 'אמהרית', lang_name_it: 'איטלקית', lang_name_pt: 'פורטוגזית'
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
      local_older: 'The customer wrote again after you edited this draft on this device. The new draft is shown.', use_mine_old: 'Bring back my version',
      search_archive_wait: 'Searching the archive…', tpl_load_failed: 'The templates could not be loaded right now.', tpl_retry: 'Try again',
      send: 'Send', send_arm: 'Click again to send', send_dry: 'Sending is off (test mode)', sent_ok: 'Sent to the customer', queued_ok: 'Queued for WhatsApp',
      send_anyway: 'Send anyway (logged)', handled: 'Handled without sending', handled_arm: 'Click again — handled without sending',
      close: 'Close', close_arm: 'Click again to close', closed_ok: 'Ticket closed', handled_ok: 'Marked handled', safety: 'Safety check: {p}',
      close_ns: 'Close without sending', close_ns_arm: 'Click again to close', close_ns_title: 'The ticket closes without sending anything to the customer. On WhatsApp it is closed in Dondy too.',
      close_tk: 'Close ticket', close_tk_arm: 'Click again to close', close_tk_title: 'Closes the ticket and moves to the next one. On WhatsApp it is closed in Dondy too.',
      send_close: 'Send & close', send_close_arm: 'Click again: send & close', send_close_title: 'Sends to the customer, closes and moves to the next ticket at once. If the send fails, the ticket is not closed and comes back to the top.',
      en_confirm_close: 'Confirm, send & close',
      ob_queued_close: '⏳ Closes right after the send', ob_close_dropped: '{name}: the send did not go through, so the ticket was not closed. It is at the top of the list.',
      rd_btn: 'Different answer', rd_ph: 'What to change? (optional) e.g. shorter, no discount offer', rd_busy: 'Writing a different answer…', rd_done: 'A different answer was written.',
      rd_undo: 'Back to the previous draft', rd_undone: 'The previous draft is back.', rd_title: 'The AI writes a different answer from the conversation. You can say briefly what to change. All the usual checks apply.',
      rd_tr_failed: 'The new answer was written, but its translation failed: {m}', rd_left: '{n} more this hour',
      snz_btn: 'Answer later', snz_30m: 'In 30 minutes', snz_1h: 'In 1 hour', snz_2h: 'In 2 hours', snz_eod: 'End of day (17:00)',
      snz_until: 'Snoozed until {t}', snz_cancel: 'Bring back now', snz_ok: 'Snoozed until {t}. It comes back to the top of your list.', snz_back: '⏰ Back from snooze',
      snz_section: 'Snoozed', snz_title: 'The ticket leaves only your list and comes back to its top at the time you chose, or at once if the customer writes again. The other agents still see it.',
      snz_failed: 'The snooze was not saved: {m}',
      fu_title: 'Another message to the customer', fu_ph: 'You can write another message to the customer here…', fu_sent: 'Answered · {who} · {when}', fu_done: 'Closed · {who} · {when}',
      fu_queued: 'A message is on its way to WhatsApp · {who} · {when}', fu_hint: 'The message goes to the customer in the same conversation. The ticket is not reopened.',
      fu_wait: 'The previous message is still on its way. You can write the next one now — Send opens once the previous one is out.',
      fu_restored: 'The message was not sent — your text is back in the box.', msg_pending: '⏳ On its way', msg_queued: '📤 Queued for WhatsApp',
      cm_answered: '{who} already answered this ticket at {when}, after you opened it.', cm_closed: '{who} already closed this ticket at {when}, after you opened it.',
      cm_kept: 'Your message was not sent and your text is kept in the box. Read what was sent in the conversation; if it is still needed, send yours as another message.',
      cm_send_anyway: 'Send anyway as another message', cm_tpl_anyway: 'Send the template anyway',
      who_dondy: 'Someone in Dondy', who_gmail: 'Someone in Gmail', who_bot: 'The automatic reply', who_merge: 'A ticket merge', who_someone: 'Someone', who_me: 'You',
      pres_view: '{who} also has this ticket open', pres_edit: '✍️ {who} is writing a reply in this ticket right now — coordinate before sending',
      orders: 'Orders', no_orders: 'No order found (orders older than 60 days are invisible).', lookup_error: 'The order lookup failed when the draft was written.',
      track: 'Tracking', items: 'Items', ordered: 'Ordered', shipped_on: 'Shipped',
      ship_not_late: 'On time', ship_late: 'Late', ship_very_late: 'Very late', ship_unknown: 'Unknown', ship_not_applicable: 'Not applicable',
      ship_line: '{state} · {d} days since the order',
      fin_PAID: 'Paid', fin_PENDING: 'Payment pending', fin_REFUNDED: 'Refunded', fin_PARTIALLY_REFUNDED: 'Partially refunded', fin_VOIDED: 'Voided',
      fin_AUTHORIZED: 'Authorized', fin_PARTIALLY_PAID: 'Partially paid',
      dlv_steps: 'Ordered|Shipped|On the way|Due', dlv_cancelled: 'Order cancelled', dlv_prep: 'Being prepared (day {d} since the order)', dlv_prep_late: 'Delayed: {d} days since the order and not shipped yet', dlv_shipped: 'Left the warehouse, expected {a}–{b}', dlv_transit: 'On the way, expected {a}–{b}', dlv_arriving: 'Should arrive these days ({a}–{b})', dlv_due: 'Should have arrived by {b}. Worth checking with the customer', dlv_late: 'Late: {d} days since the order', dlv_note: 'Estimate from the order and shipping dates (no live carrier tracking)',
      ful_FULFILLED: 'Shipped', ful_UNFULFILLED: 'Not shipped yet', ful_PARTIALLY_FULFILLED: 'Partially shipped', ful_IN_PROGRESS: 'In progress',
      ful_ON_HOLD: 'On hold', ful_SCHEDULED: 'Scheduled', ful_RESTOCKED: 'Restocked',
      subs: 'Subscriptions', no_subs: 'No subscriptions for this customer (by email).', sub_status: 'Status', sub_every: 'Frequency', sub_next: 'Next billing',
      sub_next_na: 'not provided by the engine', sub_since: 'Since', sub_lastpay: 'Last payment', sub_id: 'Contract',
      pay_SUCCEEDED: 'Succeeded', pay_FAILED: 'Failed', pay_PENDING: 'Pending', pay_REFUNDED: 'Refunded',
      ss_ACTIVE: 'Active', ss_PAUSED: 'Paused', ss_CANCELLED: 'Cancelled', ss_FAILED: 'Payment failed', ss_EXPIRED: 'Expired',
      every_day: 'Every day', every_week: 'Every week', every_month: 'Every month', every_year: 'Every year', every_n: 'Every {n} {u}',
      unit_day: 'days', unit_week: 'weeks', unit_month: 'months', unit_year: 'years',
      cancel_sub: 'Cancel subscription', cancelled_here: 'Cancelled from this screen',
      oe_btn: 'Edit order', oe_title: 'Edit the order in Shopify', oe_loading: 'Loading the order from Shopify…', oe_err_load: 'Could not load the order.',
      oe_off: 'Order editing is switched off — the owner has to turn it on.', oe_off_cred: 'Order editing is not connected to Shopify yet — waiting for Guy\'s approval.', oe_off_frozen: 'Order editing is frozen right now.',
      oe_tab_items: 'Items', oe_tab_address: 'Address and shipping details', oe_total: 'Order total', oe_qty: 'Quantity', oe_zero: '0 = remove the item from the order.', oe_add: 'Add a product', oe_pick: 'Choose a product…',
      oe_variants_loading: 'Loading products…', oe_next_items: 'Check the price', oe_next_address: 'Continue', oe_back: 'Back', oe_nochange: 'Nothing was changed.', oe_bad_qty: 'Quantity: a whole number from 0 to 20 (to add: 1 to 20).',
      oe_f_firstName: 'First name', oe_f_lastName: 'Last name', oe_f_address1: 'Street and number', oe_f_address2: 'Apartment / floor / note', oe_f_city: 'City', oe_f_zip: 'Zip code', oe_f_phone: 'Phone',
      oe_confirm: 'What will happen:', oe_delta_up: 'The order total goes up by {d}', oe_delta_down: 'The order total goes down by {d}', oe_delta_zero: 'The order total does not change', oe_total_line: 'from {a} to {b}',
      oe_settle_up: 'The customer is not charged automatically. Collect the difference in Shopify.', oe_settle_down: 'The customer is not refunded automatically. Do the refund in Shopify.',
      oe_money_note: 'This screen does not charge, refund or message the customer. A price difference — a charge or a refund — is settled in Shopify.',
      oe_ln_change: '{p}: from {a} to {b}', oe_ln_add: '{p}: added × {q}', oe_ln_remove: '{p}: removed from the order', oe_addr_change: '{f}: from {a} to {b}',
      oe_needs_admin: 'Raising the order total needs an admin. You can lower a quantity, remove an item or add a free product.',
      oe_type: 'Type the order number ({n}) to confirm', oe_reason: 'Reason (optional)', oe_go: 'Make the change in Shopify', oe_working: 'Working…', oe_done: 'The order was updated in Shopify ✓',
      oe_unverified: 'Shopify accepted it but the change is not visible yet. Check in Shopify — do not repeat it.', oe_close: 'Close', oe_cannot: 'This order cannot be edited here: {why}',
      manage_sub: 'Manage subscription', mg_title: 'Manage subscription', mg_loading: 'Loading the subscription from Kaching…', mg_err_load: 'Could not load the subscription.',
      mg_pause: 'Pause', mg_resume: 'Resume', mg_reactivate: 'Reactivate', mg_cancel: 'Cancel subscription',
      mg_cycles: 'Upcoming deliveries and charges', mg_no_cycles: 'No upcoming deliveries.', mg_cycle_n: 'Delivery {n}', mg_skipped: 'Skipped',
      mg_skip: 'Skip', mg_unskip: 'Unskip', mg_resched: 'Change date', mg_new_date: 'New date',
      mg_lines: 'Products', mg_qty: 'Quantity', mg_price: 'Unit price', mg_change: 'Change', mg_remove: 'Remove', mg_add_line: 'Add product',
      mg_swap: 'Swap to', mg_keep: 'No swap', mg_pick: 'Choose a product…', mg_variant: 'Store product', mg_variants_loading: 'Loading the store products…',
      mg_price_opt: 'Unit price (empty = no change)', mg_price_new_opt: 'Unit price (empty = the store subscription price)',
      mg_discounts: 'Discounts', mg_no_discounts: 'No discounts on this subscription.', mg_add_discount: 'Add discount', mg_dtype: 'Type', mg_dtype_pct: 'Percentage (%)',
      mg_dtype_fixed: 'Fixed amount', mg_dvalue: 'Value', mg_dtitle: 'Discount name (the customer sees it)', mg_dcycles: 'For how many deliveries (empty = forever)',
      mg_dc_forever: 'forever', mg_dc_n: 'for {n} deliveries',
      mg_next: 'Continue to confirm', mg_type: 'To confirm, type the last 4 digits of the contract number', mg_reason: 'Note for the log (optional)',
      mg_go: 'Do it', mg_working: 'Working…', mg_back: 'Back', mg_close: 'Close', mg_confirm: 'What will happen:',
      mg_off: 'The engine says subscription changes are off — this will likely be refused.', mg_frozen: 'Subscription changes are frozen — this will likely be refused.',
      mg_done: 'Done ✓', mg_unverified: 'Kaching accepted it but the change is not visible yet. Check in Kaching — do not repeat it.',
      mg_do_pause: 'Pause the subscription. No charges or deliveries until it is resumed.', mg_do_resume: 'Resume the subscription. Charges and deliveries continue on schedule.',
      mg_do_reactivate: 'Reactivate a cancelled subscription. The customer will be charged again on schedule.', mg_do_skip: 'Skip delivery {n} ({d}): no charge and no delivery on that date.',
      mg_do_unskip: 'Restore delivery {n} ({d}).', mg_do_reschedule: 'Move delivery {n} from {d} to {nd}.',
      mg_do_add_discount: 'Add the discount “{title}”: {v}, {c}.', mg_do_add_line: 'Add to the subscription: {q} × {p}{pr}.',
      mg_do_update_line: 'Change “{p}”: {what}.', mg_do_remove_line: 'Remove “{p}” from the subscription.',
      mg_w_qty: 'quantity {q}', mg_w_swap: 'swap to {p}', mg_w_price: 'price {pr} each',
      afs_title: 'Your message to {name} was sent. Still to do:', afs_open: 'Open the ticket', afs_done: 'Done', afs_chip: 'Still to do', afs_cancelled: "{name}'s subscription was cancelled automatically",
      afs_sub_no_email: 'The subscription was NOT cancelled: the customer has no known order email, so the subscription cannot be found. Ask for the order number or email, link it in the orders panel, then cancel.',
      afs_sub_unreachable: 'The subscription was NOT cancelled: the subscriptions system could not be reached. Cancel it manually.',
      afs_sub_several: 'The subscription was NOT cancelled: the customer has several active subscriptions. Choose which one to cancel in the subscriptions panel.',
      afs_sub_refused: 'The subscription was NOT cancelled: the subscriptions system refused. Cancel it manually.',
      afs_newer_message: 'The customer wrote again before your reply went out. Read it and make sure the reply covers it too.', afs_order_cancel: 'Shopify still shows the order as not cancelled. Cancel it in Shopify.',
      afs_order_refund: 'Shopify shows no refund yet. Make the refund in Shopify.',
      sx_btn: 'Cancel the subscription', sx_off_token: 'This brand has no Kaching connection — cancel it manually in Kaching.',
      sx_off_frozen: 'Cancellations are frozen right now — cancel it manually in Kaching.', sx_off_writes: 'Cancellations are switched off — cancel it manually in Kaching.',
      sx_checking: "Checking {name}'s subscriptions in Kaching…", sx_q_one: "Cancel {name}'s subscription?", sx_q_many: '{name} has {n} active subscriptions. Which one to cancel?',
      sx_none: 'No subscription in Kaching for {email}. If the customer ordered with another email or phone, ask them for the order number or the email of the order, and link it here:',
      sx_ended: "✅ {name}'s subscription is already cancelled in Kaching (checked just now, {t}). Nothing to cancel again.",
      sx_noemail: "This customer has no known order email (e.g. the ticket only has a phone that does not match an order), so the subscription cannot be found. Ask the customer for the order number or the email they ordered with, and link it here:",
      lk_ph: 'Order number (#12057) or email the customer gave', lk_go: 'Find and link', lk_working: 'Searching the store…', lk_ok: '🔗 Linked to customer {email}',
      lk_orders: 'Orders: {o}', lk_by: 'Linked by {by}, {t}', lk_unlink: 'Remove the link', lk_other: '🔗 Wrong customer? Link by order number or email',
      lk_hint: "The ticket's details lead to no order? Ask the customer for the order number or the email of the order, and link it here:", lk_done: 'Customer linked to the ticket',
      sx_go: 'Yes, cancel the subscription', sx_back: 'Back', sx_working: 'Cancelling and checking in Kaching…',
      sx_note: 'After the cancel the system reads the subscription again from Kaching and confirms it really is cancelled.',
      sx_ok: '✅ Subscription cancelled — verified in Kaching {t}', sx_ok_old: '✅ Subscription cancelled from this screen', sx_fail: '❌ The subscription was NOT cancelled',
      sx_manual: 'Cancel it manually in Kaching.', sx_unknown: 'Unknown whether it was cancelled. Check in Kaching before trying again.',
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
      photo_wait: '📷 Photo — not arrived yet', photo_gone: '📷 Photo — removed after 7 days, view in Dondy', voice_wait: '🎤 Voice message — not arrived yet', voice_dondy: '🎤 Voice message — listen in Dondy', voice_gone: '🎤 Voice message — removed after 30 days', media_video: '🎬 Video — view in Dondy', media_file: '📎 File — view in Dondy',
      att_btn: '📎 Attach file', att_uploading: 'Uploading…', att_failed: 'Not uploaded', att_remove: 'Remove the file', att_hint: 'PDF, image, Word, Excel or TXT · up to {mb} MB a file',
      att_hint_wa: 'One file: PDF, JPG, PNG, Word or Excel · up to {mb} MB', att_type: 'File type not allowed: {name}', att_size: 'File too large: {name} (up to {mb} MB)',
      att_total: 'All files together are too large (up to {mb} MB an email)', att_count: 'Up to {n} files', att_wa_one: 'WhatsApp takes one file per message',
      att_wait: 'Waiting for an upload to finish, or for a failed file to be removed', att_sent_chip: '📎 {name}',
      err_bad_engine: 'The engine returned an invalid answer. Try again in a moment.',
      ob_flight_send: '⏳ Sending in the background…', ob_flight_close: '⏳ Closing in the background…', ob_ok_email: '✅ Sent', ob_ok_wa: '✅ Sent to WhatsApp', ob_ok_queued: '📤 Queued',
      ob_ok_close: '✅ Handled', ob_refused: '⚠️ Not sent — needs a fix', ob_refused_close: '⚠️ Not closed — needs a fix', ob_unknown: '❓ Not confirmed — check',
      ob_checking: '⏳ Checking what happened to the send…', ob_elsewhere: 'ℹ️ Already answered from Gmail — not sent again', ob_toast_elsewhere: '{name}: already answered from Gmail. No second reply was sent, and the ticket was closed.', ob_retry: '⏳ Trying to send again…', ob_retry_close: '⏳ Trying to close again…', ob_retry_n: 'Try {n} of {max}. The system retries by itself; do not send again.', ob_unsent: '⚠️ The send did not happen — you can send again', ob_header: 'Sending ({n})', ob_none: 'Nothing in progress',
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
      ok: 'OK', cancel_btn: 'Back',
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
      ar_reviewed_ok: '✓ Reviewed by {u}', ar_reviewed_problem: '⚠ Flagged by {u}', ar_pending: 'Waiting for review', ar_banner: '🤖 The bot answered {n} customers by itself. Read every reply and make sure the bot did not write nonsense.', ar_banner_one: '🤖 The bot answered one customer by itself. Read the reply and make sure the bot did not write nonsense.', ar_banner_go: 'Review the replies', ar_open: 'Open the ticket',
      ar_done_ok: 'Marked OK', ar_done_problem: 'Flagged — the ticket was reopened', ar_na: 'Automatic replies are not available in this brand engine yet.',
      ar_mode: 'Auto-reply: {m}', mode_auto_reply: 'Auto-reply: {v}', what_to_do: 'What to do',
      set_AUTO_REPLY: 'Auto-reply', set_AUTO_REPLY_help: 'Off / shadow: marks what would be sent / on: answers simple emails by itself and flags them for review',
      set_AUTO_REPLY_note: '"On" requires test mode to be off.',
      syncing: 'Loading the latest version…', checking: 'Updating…', sync_failed: 'Not updated ({m}) — showing a copy from {when}', tk_updated: 'A newer version of this ticket is ready', apply_update: 'Show',
      live_new_msg: 'A new message arrived', live_new_msgs: '{n} new messages arrived', live_ok: 'Got it',
      draft_new_avail: 'The engine wrote a new draft — yours is untouched.', use_new_draft: 'Use the new draft', draft_updated: 'The draft was updated for the new message.',
      orders_err: 'Order lookup failed: {m}', subs_err: 'Subscription lookup failed: {m}',
      mailbox_at: 'Received at:', order_open: 'Open the order in Shopify (new tab)',
      ain_title: 'Improve the AI — managers\' notes', ain_help: 'Managers\' notes bind the AI: they go into every draft from the next one on, and the open drafts in the queue are rewritten under them (a draft an agent edited and saved is never replaced). The system answers every note here and updates when it is in and checked. The corrections the team makes to the AI\'s drafts become suggested notes here.',
      ain_r_gate: '⚠ In the system, but in the check on {b} a fixed system rule stopped or replaced the answer, so the note does not reach the customer: {gate}',
      ain_redraft: '✍️ {n} open drafts in {b} are being rewritten under the note (within a few minutes)', ain_redraft_1: '✍️ 1 open draft in {b} is being rewritten under the note (within a few minutes)',
      ain_redraft_del: '✍️ {n} open drafts in {b} are being rewritten without the note (within a few minutes)', ain_redraft_del_1: '✍️ 1 open draft in {b} is being rewritten without the note (within a few minutes)',
      ain_s_title: '💡 Suggestions from the team\'s corrections', ain_s_help: 'When the team corrects the same thing in the AI\'s drafts again and again, the system suggests a rule here. What you approve goes in as a note of that brand and is checked like any note.',
      ain_s_count: 'Found in {n} corrections', ain_s_examples: 'Examples ({n})', ain_s_ex_c: 'Customer:', ain_s_ex_ai: 'The AI wrote:', ain_s_ex_sent: 'The team sent:',
      ain_s_approve: '✅ Add as a note', ain_s_edit: '✏️ Edit and add', ain_s_reject: '✕ Not relevant', ain_s_reject_arm: 'Not relevant? Click again', ain_s_cancel: 'Cancel',
      ain_s_saving: 'Saving…', ain_s_added: 'The suggestion was added as a note for {b}. It is in the notes list below and is being checked.', ain_s_rejected: 'Marked not relevant ({b})',
      ain_s_noop: 'This suggestion was already decided ({b})', ain_s_fail: 'Not saved — {m}',
      ain_s_empty: '{b}: no suggestions yet · {n} corrections collected', ain_s_load_err: 'Suggestions not loaded from {b}: {m}', ain_s_loading: 'Loading suggestions…',
      ain_file_btn: '📎 Attach a file (approval / certificate)', ain_file_clear: 'Remove the file', ain_file_big: 'The file is too big (up to 10MB).',
      ain_doc_hint: 'This note is about an approval or a certificate: attach the file too, and the note goes in at once.',
      ain_r_needs: '📎 Got it. For the bot to tell customers this, the approval document is needed too. Upload it here: as soon as it is up the note goes in and I will update here.',
      ain_r_attach: '📎 Upload the file', ain_r_uploading: 'Uploading the file…', ain_r_up_fail: 'The file was not uploaded to {b}: {m}',
      ain_r_checking: '⏳ In the system. Checking now that the bot really answers by the note (up to a minute)…',
      ain_r_ok: '✅ In the system and checked ({d}).', ain_r_ok_n: '✅ In the system and checked in {n} brands ({d}).', ain_r_q: 'I asked the bot:', ain_r_a: 'The bot answered:',
      ain_r_no: '⚠ In the system, but in the check on {b} the bot did not answer by the note yet: {why}', ain_r_err: 'In the system. The automatic check could not run now ({b}).',
      ain_r_recheck: 'Check again', ain_r_reply: 'System reply', ain_r_file: '📄 {n}',
      ain_r_understood: '🧠 How I understood it:', ain_r_reading: '⏳ Writing how I understood the note…', ain_r_wrong: '✏️ Not what I meant — edit',
      ain_edit_hint: 'Edit the note and click "Add note". The old note is deleted and replaced by the new one.', ain_replaced: 'The old note was replaced',
      ain_jump: '🧠 Improve the AI', ain_ph: 'What should the AI do differently? E.g. "Don\'t write \'sorry for the inconvenience\' — open with the answer."',
      ain_scope: 'Who is it for', ain_all: 'All brands', ain_add: 'Add note', ain_adding: 'Saving…', ain_count: '{n}/600',
      ain_general: 'General — all brands', ain_brand: '{b} only', ain_empty: 'No notes yet. A note you add goes into the AI\'s next drafts.',
      ain_by: '{u} · {d}', ain_del: '✕', ain_del_arm: 'Delete? Click again', ain_del_title: 'Delete the note',
      ain_saved_all: 'Saved in all {n} brands', ain_saved_one: 'Saved for {b}', ain_saved_part: 'Saved in {ok} of {n} brands — failed: {bad}',
      ain_save_fail: 'Not saved — {m}', ain_deleted: 'Deleted', ain_del_part: 'Deleted in {ok} of {n} brands — failed: {bad}', ain_del_fail: 'Not deleted — {m}',
      ain_missing: 'Missing in: {b}', ain_fill: 'Complete', ain_load_err: 'Not loaded from {b}: {m}', ain_retry: 'Load again', ain_loading: 'Loading notes…',
      ain_not_conn: 'Brands not connected to the system get no notes: {b}', ain_too_long: 'Up to 600 characters',
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
  function waWin(x, any) {          // any: also an answered / closed chat (another message or a template, 2026-10-11)
    if (!x || !isWA(x) || (!any && OPEN.indexOf(x.status) < 0)) return null;
    const at = ms(x.wa_last_in);
    if (!at) return null;
    const left = at + WA_WINDOW_MS - WA_WINDOW_MARGIN_MS - Date.now();
    return { state: left <= 0 ? 'closed' : left < WA_SOON_MS ? 'soon' : 'open', left: left };
  }
  function waWinClosed(x, any) { const w = waWin(x, any); return !!w && w.state === 'closed'; }
  /** Owner, 2026-10-11: "after it's closed there is no option to reply anymore". An answered, closed or queued ticket takes another message. */
  const FOLLOWUP_ST = ['sent', 'done', 'wa_queued'];
  function canFollowUp(x) { return !!x && FOLLOWUP_ST.indexOf(x.status) >= 0; }
  /** Who handled a ticket, in words: a person's name, or what Dondy / Gmail / the bot did. */
  function whoName(by) {
    const b = String(by || '').trim();
    if (!b) return t('who_someone');
    if (S.me && S.me.user && b === S.me.user.username) return t('who_me');
    const m = { dondy: 'who_dondy', gmail: 'who_gmail', 'auto-reply': 'who_bot', auto: 'who_bot', engine: 'who_bot', bot: 'who_bot', merge: 'who_merge' }[b.toLowerCase()];
    return m ? t(m) : b;
  }
  /** HH:MM today, else the date with the time. */
  function whenShort(iso) {
    const v = ms(iso);
    if (v === null) return '—';
    if (ilDay(v) === ilDay(Date.now())) return new Intl.DateTimeFormat(LANG === 'en' ? 'en-GB' : 'he-IL', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(new Date(v));
    return fmtDate(iso, true);
  }
  /** Messages this page sent and the conversation does not show yet (WhatsApp waits for the bridge's echo): shown as ours with a
   *  "on its way" mark, so the agent sees what went out and can write the next one. Dropped once the conversation has them. */
  const OUTGOING = {};
  const TYPED = {};          // brand|id -> last keystroke in this ticket (presence: "is writing")
  function outgoingFor(brand, id, conv) {
    const list = OUTGOING[brand + '|' + id] || [];
    const have = (conv || []).filter(function (m) { return m && m.who === 'us'; }).map(function (m) { return String(m.text || '').trim().slice(0, 200); });
    const left = list.filter(function (o) { return have.indexOf(String(o.text).trim().slice(0, 200)) < 0 && Date.now() - o.at < 30 * 60000; });
    if (left.length) OUTGOING[brand + '|' + id] = left; else delete OUTGOING[brand + '|' + id];
    return left;
  }
  /** Who else has this ticket on screen (from /watch and the open): a quiet chip; a stronger one when they are writing. */
  function paintPresence(k, others) {
    const el = document.getElementById('tk-presence');
    if (!el || S.tk !== k) return;
    const list = Array.isArray(others) ? others.filter(function (o) { return o && typeof o.user === 'string'; }) : [];
    clear(el);
    el.hidden = !list.length;
    if (!list.length) return;
    const editing = list.filter(function (o) { return o.editing; });
    const names = (editing.length ? editing : list).map(function (o) { return String(o.name || o.user); }).join(', ');
    el.className = 'chip presence' + (editing.length ? ' bad' : ' outline');
    el.setAttribute('data-state', editing.length ? 'editing' : 'viewing');
    el.append(tx(editing.length ? 'pres_edit' : 'pres_view', { who: names }));
  }
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
    async function fire(seenOverride) {
      const tpl = chosen();
      if (!tpl || busy) return;
      busy = true; paintBtn();
      err.hidden = true;
      const tk = S.tk && S.tk.id === x.id ? S.tk.ticket : x;
      // seen: someone else's answer after this screen loaded stops it (2026-10-11, rozela: the same template re-sent 3 minutes later)
      const args = { id: x.id, template: tpl.name, seen: typeof seenOverride === 'string' ? seenOverride : String(tk.handled_at || '') };
      const draft = String(getDraft() || '').trim();
      if (thenCb.checked && draft) args.then = draft;
      const r = await api('/api/' + encodeURIComponent(brand) + '/apiSendTemplate', { args: args, lang: LANG });
      busy = false;
      if (r && r.ok) {
        // Owner, 2026-10-11: a send never moves on. The template shows as on its way; the ticket stays on screen.
        delete TPL_UI[brand + '|' + x.id]; toast(t('tpl_sent_ok')); pollChanges(brand);
        (OUTGOING[brand + '|' + x.id] || (OUTGOING[brand + '|' + x.id] = [])).push({ text: tpl.text, at: Date.now(), rid: 'tpl', queued: true });
        if (S.tk && S.tk.id === x.id) {
          if (typeof r.handled_at === 'string' && S.tk.ticket) { S.tk.ticket.handled_at = r.handled_at; S.tk.ticket.handled_by = S.me.user.username; S.tk.ticket.wa_send = 'pending'; }
          repaintConv(S.tk); Draft.refreshSend(); EnDraft.refresh(); Watch.kick(true);
        }
        clear(status); status.hidden = false; status.textContent = t('tpl_sent_ok');
        paintBtn();
        return;
      }
      clear(err);
      if (r && r.error === 'changed_meanwhile') {
        err.append(h('div', { text: t(r.status === 'done' ? 'cm_closed' : 'cm_answered', { who: whoName(r.by), when: whenShort(r.at) }) }));
        const again = armed(t('cm_tpl_anyway'), t('tpl_send_arm'), 'btn small', function () { fire(typeof r.at === 'string' ? r.at : ''); });
        again.setAttribute('data-test', 'tpl-anyway');
        err.append(h('div', { class: 'actions' }, again));
        if (S.tk && S.tk.id === x.id) refreshOpen(brand, x.id);
      } else err.textContent = (r && (r.msg || r.message)) || t('err_bad_engine');
      err.hidden = false;
      paintBtn();
    }
    btn.addEventListener('keydown', function (e) { if (e.repeat && (e.key === 'Enter' || e.key === ' ')) e.preventDefault(); });   // a held key is not a second click
    btn.addEventListener('click', function () {
      if (btn.disabled) return;
      if (mem.armedAt && Date.now() - mem.armedAt < ARM_MIN_MS) return;                 // a double-click is not a confirmation (review 2026-10-11 #2)
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
    function fill(l) {
      if (l === null) {                                  // the server failed: say so and offer a retry (review 2026-10-11 #8)
        clear(status); status.hidden = false; sel.hidden = true; list = []; paintBtn();
        status.append(t('tpl_load_failed') + ' ', h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'tpl-retry', text: t('tpl_retry'), onclick: function () {
          clear(status); status.textContent = t('tpl_loading'); loadTemplates(brand).then(fill);
        } }));
        return;
      }
      list = l;
      if (!list.length) { status.textContent = t('tpl_none'); sel.hidden = true; paintBtn(); return; }
      status.hidden = true; sel.hidden = false; clear(sel);
      list.forEach(function (tp) { const o = document.createElement('option'); o.textContent = tp.name; o.value = tp.name; sel.append(o); });
      mem.name = chosen().name;
      paint();
    }
    loadTemplates(brand).then(fill);
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
  /** Clicking an order number opens it in Shopify (Owner, 2026-10-11). The store handle comes from the engine (apiBoot.myshopify);
   *  the order's own page when its gid is known, else the store's order search by the number shown. No handle -> null (plain text). */
  function shopHandle(brand) {
    const b = S.boots[brand];
    const m = /^([a-z0-9][a-z0-9-]{0,62})\.myshopify\.com$/i.exec(String((b && b.myshopify) || '').trim());
    return m ? m[1].toLowerCase() : null;
  }
  function orderUrl(brand, name, gid) {
    const hd = shopHandle(brand);
    if (!hd) return null;
    const m = /^gid:\/\/shopify\/Order\/(\d{1,20})$/.exec(String(gid || '').trim());
    if (m) return 'https://admin.shopify.com/store/' + hd + '/orders/' + m[1];
    const n = String(name || '').trim();
    return n ? 'https://admin.shopify.com/store/' + hd + '/orders?query=' + encodeURIComponent(n) : null;
  }
  /** The brand's list (with its myshopify) came after the ticket was drawn: plain order numbers become links, nothing is rebuilt. */
  function upgradeOrderLinks(brand) {
    if (!shopHandle(brand)) return;
    Array.prototype.forEach.call(document.querySelectorAll('bdi[data-order-brand]'), function (el) {
      if (el.getAttribute('data-order-brand') !== brand) return;
      const a = orderLink(brand, el.getAttribute('data-order'), el.getAttribute('data-gid'), el.className || null);
      if (a.tagName === 'A') el.replaceWith(a);
    });
  }
  /** The gid of an order shown by name, when the ticket's order lookup has it. */
  function orderGid(ex, name) {
    const n = String(name || '').trim();
    const o = n && ((ex && ex.orders) || []).filter(function (x) { return x && String(x.name || '').trim() === n; })[0];
    return (o && o.id) || null;
  }
  /** An order number: a new-tab link to Shopify, or the same text when there is no link. The click never reaches a row under it. */
  function orderLink(brand, name, gid, cls) {
    const text = String(name || '').trim();
    const u = safeUrl(orderUrl(brand, text, gid));
    // no link yet: remembers what it needs, so the brand's list arriving later (a deep link) turns it into a link in place
    if (!u) return h('bdi', { class: cls || null, text: text, 'data-order': text || null, 'data-order-brand': text ? brand : null, 'data-gid': gid || null });
    return h('a', { class: 'order-link' + (cls ? ' ' + cls : ''), href: u, target: '_blank', rel: 'noopener noreferrer', dir: 'ltr', title: t('order_open'),
      'data-test': 'order-link', text: text, onclick: function (e) { e.stopPropagation(); } });
  }

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

  /** A button that needs two clicks within 4s — two separate clicks: a double-click or a held Enter never confirms
   *  (review 2026-10-11 #2: a double-click sent to the customer / closed the ticket with no confirm step). */
  const ARM_MIN_MS = 500;
  function armed(label, armLabel, cls, onFire) {
    const b = h('button', { class: 'btn ' + (cls || ''), type: 'button', text: label });
    let armedAt = 0;
    let timer = null;
    b.addEventListener('keydown', function (e) { if (e.repeat && (e.key === 'Enter' || e.key === ' ')) e.preventDefault(); });
    b.addEventListener('click', function () {
      if (b.disabled) return;
      if (armedAt && Date.now() - armedAt < ARM_MIN_MS) return;
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

  /** Owner, 2026-10-11: "handled without sending" and "close" did the same thing in the engine (closeTicket_), so an agent gets ONE
   *  button. apiMarkHandled stays in the proxy for outbox items queued before this change. */
  /** After an answer (Owner, 2026-10-11): sending no longer closes; this button does, and moves to the next ticket. */
  function closeTicketBtn(onFire) {
    const b = armed(t('close_tk'), t('close_tk_arm'), '', onFire);
    b.setAttribute('data-test', 'close-btn');
    b.setAttribute('data-kind', 'close');
    b.setAttribute('title', t('close_tk_title'));
    return b;
  }
  function closeNoSendBtn(onFire) {
    const b = armed(t('close_ns'), t('close_ns_arm'), '', onFire);
    b.setAttribute('data-test', 'close-btn');
    b.setAttribute('data-kind', 'nosend');
    b.setAttribute('title', t('close_ns_title'));
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
  const READ_FNS = ['list', 'changes', 'watch', 'ticket', 'prefetch', 'result', 'related', 'queue', 'translate', 'translate-he', 'translate-rows', 'translate-autoreply', 'translate-out',
    'assistant', 'apiBoot', 'apiStatus', 'apiTicket', 'apiTicketExtras', 'apiTickets', 'apiSearch', 'apiAutoReplyList', 'apiAutoCancelList', 'apiTemplates', 'apiAiNotes', 'apiAiNoteSuggestions'];
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
    if (p[0] === 'zip') return { view: 'zip', brand: p[1] };
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
    if (r.view !== 'zip') Zip.leave();
    if (r.view === 'zip') {                            // מילוי מיקודים: anyone who works tickets, on their own brands only
      if (!canWork()) return go('#/', true);
      const zb = r.brand && myBrands.indexOf(r.brand) >= 0 ? r.brand : (S.brand && myBrands.indexOf(S.brand) >= 0 ? S.brand : myBrands[0]);
      if (!zb) return go('#/', true);
      if (zb !== r.brand) return go('#/zip/' + encodeURIComponent(zb), true);
      S.view = 'zip'; S.brand = zb;
      $('users-pane').hidden = true;
      $('settings-pane').hidden = true;
      document.body.className = 'view-zip';
      renderTop(); renderBanners(); Zip.show(zb); Assist.sync();
      return;
    }
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
      if (window.matchMedia('(max-width: 999px)').matches) {
        if (S.ticketId) { S.lastOpenId = S.ticketId; S.restoreScroll = true; }   // back on the list: where he was (2026-10-15)
        S.ticketId = null; S.tk = null;
      }
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
    if (canWork() && brands.length && S.view !== 'zip') {          // phone (<=640px): hidden by CSS, the ☰ menu carries it — the bar has no room
      const zl = LANG === 'en' ? 'Zip-code fill' : 'מילוי מיקודים';
      top.append(h('a', { class: 'dash-link zip-link', href: '#/zip/' + encodeURIComponent(S.brand || brands[0].id), 'data-test': 'zip-link', title: zl, 'aria-label': zl },
        '📮', h('span', { class: 'zip-link-txt', text: ' ' + zl })));
    }
    // Owner, 2026-10-14: "only I see the sales, in the managers' table" — no sales entry for anyone outside #/dash (the engine and proxy refuse agents too)
    if (brands.length > 1 && S.view !== 'users' && S.view !== 'dash' && S.view !== 'zip') {
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
    } else if (brands.length === 1 && S.view !== 'users' && S.view !== 'dash' && S.view !== 'zip') {
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
      if ((S.view === 'users' || S.view === 'dash' || S.view === 'zip') && canWork()) m.append(h('a', { href: '#/', text: t('to_tickets') }));
      if (canWork() && brands.length && S.view !== 'zip') m.append(h('a', { href: '#/zip/' + encodeURIComponent(S.brand || brands[0].id), 'data-test': 'zip-menu', text: LANG === 'en' ? 'Zip-code fill' : 'מילוי מיקודים' }));
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
    if (S.view === 'users' || S.view === 'zip') return;
    const b = boot();
    if (b) el.append(modeBanner(b));
    const age = listAge(S.brand);
    if (b && age !== null && age > 120) {
      el.append(h('div', { class: 'banner warn stale-list', role: 'status', 'data-test': 'list-stale' },
        h('span', null, tx('list_stale', { m: Math.floor(age / 60) })), ' ',
        h('button', { class: 'btn small', type: 'button', text: t('list_refresh'), onclick: function (e) { e.target.disabled = true; forceList(S.brand); } })));
    }
    if (b && b.cancelFrozen) el.append(h('p', { class: 'banner danger', text: t('frozen') }));
    // Owner, 2026-10-09: a mail the bot answered is "read" in Gmail now, so the inbox no longer reminds anyone to check it. The reminder lives
    // here, on every screen of the brand, until each automatic reply was reviewed (the tab's own count is easy to miss).
    const ar = S.ar[S.brand], arN = canWork() && ar && ar.items ? ar.items.filter(function (x) { return x.review === 'pending' && String(x.state) === 'sent'; }).length : 0;   // really sent, not a shadow "would send"
    if (arN && !(S.tab === 'autoreply' && S.view !== 'ticket')) {
      el.append(h('div', { class: 'banner warn ar-review', role: 'status', 'data-test': 'ar-review-banner', 'data-n': String(arN) },
        h('span', { text: arN === 1 ? t('ar_banner_one') : t('ar_banner', { n: arN }) }), ' ',
        h('a', { class: 'btn small', href: listHash('autoreply'), 'data-test': 'ar-review-go', text: t('ar_banner_go') })));
    }
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
    if (r.ok && Array.isArray(r.tickets) && r.counts) { const cur = S.boots[brand]; S.boots[brand] = r; noteSync(brand, r.syncedAge || 0); if (cur) r._prev = null; upgradeOrderLinks(brand); }
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
    // 2026-10-14: his "פתוחות" counts only what HE sees (his snoozed tickets are not in his list); everyone else's count is unchanged
    const seen = function (x) { return !Snooze.hides(S.brand, x); };
    if (id === 'failed') return (b.tickets || []).filter(function (x) { return waFailActionable(x) && seen(x); }).length;
    if (id === 'wa24') return (b.tickets || []).filter(function (x) { return waWinClosed(x) && seen(x); }).length;
    if (id === 'ready') return (b.tickets || []).filter(function (x) { return OPEN.indexOf(x.status) >= 0 && seen(x); }).length;
    const rows = (b.tickets || []).filter(function (x) { return x.status === id && (OPEN.indexOf(id) < 0 || seen(x)); }).length;
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
    if (r.ok) { S.boots[brand] = r; delete S.bootErr[brand]; noteSync(brand, r.syncedAge); upgradeOrderLinks(brand); }
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
    ['dryRun', 'cancelEnabled', 'cancelFrozen', 'subscriptions', 'orderEdits'].forEach(function (k) {
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
    if (Snooze.WORK_TABS.indexOf(tab) >= 0) { const r = byChannel(rowsForRaw(tab)); return r ? r.filter(function (x) { return !Snooze.hides(S.brand, x); }) : r; }   // 2026-10-14: his snoozed ones
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
    if (x.order_no) chips.push(h('span', { class: 'chip outline ltr', 'data-test': 'row-order' }, orderLink(S.brand, x.order_no, null)));
    if (x.cancelled) chips.push(h('span', { class: 'chip ok', text: t('cancelled_here') }));
    if (!open && /^\u26A0\uFE0F? ?ההודעה נשלחה/.test(String(x.action || ''))) chips.unshift(h('span', { class: 'chip bad', 'data-test': 'after-send-chip', text: t('afs_chip') }));
    if (Number(x.siblings) > 0) chips.push(h('span', { class: 'chip sib', text: t('siblings_short', { n: Number(x.siblings) }) }));
    if (isAutoReplied(x)) chips.unshift(h('span', { class: 'chip bot', text: t('ar_label'), 'data-test': 'bot-chip' }));
    if (waFail(x)) chips.unshift(waFailChip(x));
    if (open && Snooze.back(S.brand, x)) chips.unshift(h('span', { class: 'chip snz-back', 'data-test': 'snooze-back', text: t('snz_back') }));
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
      S.tab === 'auto' ? [S.auto[S.brand], S.autoMsg] : null, Outbox.ver(), Snooze.ver(), S.tab === 'autoreply' ? [S.ar[S.brand], S.autoMsg] : null, LANG === 'en' ? S.rowTr : null]);
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
      const searching = S.search.note === t('search_local');
      if (err) res.append(h('div', { class: 'err-box', text: err }));
      else if (S.search.err) res.append(h('div', { class: 'err-box', text: S.search.err }));
      else if (S.search.res === null) res.append(h('div', { class: 'empty', text: S.search.q ? t('loading') : t('search_min') }));
      else if (!S.search.res.length) res.append(h('div', { class: 'empty' }, h('b', { text: searching ? t('search_archive_wait') : t('search_none') })));   // review 2026-10-11 #7
      else S.search.res.forEach(function (x) { res.append(rowEl(x, { showStatus: true })); });
      // after the chain, never inside it (QA round 5: a note placed in the if/else hid every result row)
      if (S.search.note && S.search.res && !S.search.err && !(searching && !S.search.res.length)) res.prepend(h('div', { class: 'muted small search-note', 'data-test': 'search-note', text: S.search.note }));
      return;
    }
    if (S.tab === 'auto') { AutoCancel.render(lp, force); return; }
    if (S.tab === 'autoreply') { AutoReply.render(lp); return; }
    const keepTop = lp.scrollTop;                      // Owner, 2026-10-15: a re-render never throws the list back to the top
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
    rows = shownRows(S.tab) || [];                     // the one order of the list (goNext reads the same one)
    const shown = { brand: S.brand, tab: S.tab, chan: S.chan || 'all', ids: rows.map(function (x) { return x.id; }) };
    if (S.listShown && S.listShown.brand === shown.brand && S.listShown.tab === shown.tab) S.listShownPrev = S.listShown;
    S.listShown = shown;
    // Owner, 2026-10-18: a template / a send that stays on the ticket takes it out of the tab while he is still on it, and the next
    // re-renders no longer hold it. The last list that DID hold the open ticket is kept for goNext, however many re-renders follow.
    if (S.ticketId && shown.ids.indexOf(S.ticketId) >= 0) S.listOfOpen = { id: S.ticketId, brand: shown.brand, tab: shown.tab, ids: shown.ids };
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
    const snz = Snooze.WORK_TABS.indexOf(S.tab) >= 0 ? byChannel(Snooze.hidden(S.brand)) : [];
    if (snz.length) {          // small, closed by default: his snoozed tickets, each with its time and "bring back now"
      S.snzOpen = S.snzOpen || {};
      const det2 = h('details', { class: 'old-section snz-section', open: !!S.snzOpen[S.brand], 'data-test': 'snooze-section' },
        h('summary', null, t('snz_section'), h('span', { class: 'n', text: String(snz.length) })));
      det2.addEventListener('toggle', function () { S.snzOpen[S.brand] = det2.open; });
      snz.forEach(function (x) {
        det2.append(h('div', { class: 'snz-row', 'data-test': 'snoozed-row', 'data-id': x.id }, rowEl(x),
          h('div', { class: 'snz-act' }, h('span', { class: 'chip outline', text: t('snz_until', { t: Snooze.until(S.brand, x.id) }) }), ' ',
            h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'snooze-row-cancel', text: t('snz_cancel'), onclick: function () { Snooze.cancel(S.brand, x.id); } }))));
      });
      lp.append(det2);
    }
    lp.scrollTop = keepTop;
    keepRowInView(lp, S.ticketId);
    if (S.restoreScroll && S.view === 'list') {       // phone: back from a ticket -> the list where he was, on the ticket he was on
      S.restoreScroll = false;
      const el = S.lastOpenId && lp.querySelector('a.row[data-id="' + CSS.escape(String(S.lastOpenId)) + '"]');
      if (el) el.scrollIntoView({ block: 'center' });
    }
    translateRows(rows);
  }
  /** Wide screen: the open ticket's row stays visible in the list pane (only the pane scrolls, never the page). */
  function keepRowInView(lp, id) {
    if (!id || window.matchMedia('(max-width: 999px)').matches) return;
    const el = lp.querySelector('a.row[data-id="' + CSS.escape(String(id)) + '"]');
    if (!el) return;
    const a = el.getBoundingClientRect(), q = lp.getBoundingClientRect();
    if (a.top < q.top) lp.scrollTop -= q.top - a.top + 8;
    else if (a.bottom > q.bottom) lp.scrollTop += a.bottom - q.bottom + 8;
  }
  /** The rows of a tab in the order the list SHOWS them: the ones that need a fix, back from snooze, the rest, then the 30+ day section.
   *  keepId: that ticket stays in although the outbox / a snooze already hides it — goNext needs its place at the moment of the click. */
  function shownRows(tab, keepId) {
    const work = OPEN.indexOf(tab) >= 0 || tab === 'bot';
    let rows = Snooze.WORK_TABS.indexOf(tab) >= 0
      ? (function () { const r = byChannel(rowsForRaw(tab)); return r ? r.filter(function (x) { return x.id === keepId || !Snooze.hides(S.brand, x); }) : r; })()
      : rowsFor(tab);
    if (!rows) return null;
    if (work) rows = rows.filter(function (x) { return x.id === keepId || !Outbox.hidesRow(S.brand, x.id, x); });   // closed in the background (on its way)
    rows = rows.filter(function (x) { return Outbox.flagged(S.brand, x.id); }).concat(rows.filter(function (x) { return !Outbox.flagged(S.brand, x.id); }));   // needs a fix -> top
    if (!work) return rows;
    // back from snooze (time is up, or the customer wrote again) -> top, right after the ones that need a fix (2026-10-14)
    const isBack = function (x) { return !Outbox.flagged(S.brand, x.id) && Snooze.back(S.brand, x); };
    const fl = rows.filter(function (x) { return Outbox.flagged(S.brand, x.id); });
    rows = fl.concat(rows.filter(isBack), rows.filter(function (x) { return !Outbox.flagged(S.brand, x.id) && !isBack(x); }));
    return rows.filter(function (x) { return !isOld(x); }).concat(rows.filter(isOld));
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
  /** The brand a ticket belongs to — never the brand on screen now (review 2026-10-11 #4: a brand switch while a ticket
   *  was loading built its draft, cancel and notes against the other brand's engine). */
  function tkBrand(x) { return S.tk && x && S.tk.id === x.id && S.tk.brand ? S.tk.brand : S.brand; }
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
    keepRowInView(lp, id);
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
    // review 2026-10-11 #1: an edited draft stays the agent's text after its autosave landed. A whole redraw would rebuild it
    // from this copy's draft_text, which can be OLDER than the save. Swap the conversation only and offer a new draft.
    if (k.ticket && Draft.edited()) {
      if (r.cache && typeof r.cache.at === 'number' && k.srvAt && r.cache.at < k.srvAt) { paintSync(); return; }   // an older copy than one already taken in
      if ($('cancel-dlg').open || $('confirm-dlg').open) { k.pending = r; paintSync(); return; }
      liveUpdate(k, r);
      return;
    }
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
    if (r && Array.isArray(r.others)) { k.others = r.others; paintPresence(k, r.others); }
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
    const rows = (rowsFor(tab) || []).filter(function (x) { return !isOld(x) && !Outbox.hidesRow(brand, x.id, x); });
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
      const cc = convCard(k.extras.conversation || [], outgoingFor(k.brand, k.id, k.extras.conversation || []));
      cc.id = 'tk-conv';
      if (isWA(k.ticket)) cc.classList.add('wa');
      old.replaceWith(cc);
    }
    const nd = String(r.ticket.draft_text || '');
    if (nd !== prevDraft && !enMode(k.ticket)) Draft.offer(nd);
    Draft.refreshSend();
    if (enMode(k.ticket)) Translate.load(k);
    else if (HeTranslate.needed(k)) HeTranslate.load(k);
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
    } else if (foreignText(last.text)) {     // Hebrew desk: a new message in another language shows its Hebrew translation
      const index = ((k.extras && k.extras.conversation) || []).findIndex(function (m) { return msgKey(m) === msgKey(last); });
      const translated = ((k.trHe && k.trHe.conversation) || []).find(function (m) { return Number(m.i) === index; });
      preview = translated ? String(translated.text || '').slice(0, 400) : t('tr_loading');
      if (k.trHe && k.trHe.err) preview = String(last.text || '').slice(0, 400);
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
      const ed = Date.now() - (TYPED[k.brand + '|' + k.id] || 0) < 30000;      // "is writing" for the others' presence chip
      try { r = await api('/api/' + encodeURIComponent(k.brand) + '/watch', { id: k.id, at: k.srvAt || 0, ed: ed }, 'POST', { retry: false, quiet: true }); }
      finally { busy = false; clearTimeout(shown); mark(k, false); }
      if (S.tk === k && r && Array.isArray(r.others)) { k.others = r.others; paintPresence(k, r.others); }
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
  /** The open ticket changed under the agent (someone else answered): bring the engine's copy in now, never under their fingers. */
  async function refreshOpen(brand, id) {
    const k = S.tk;
    if (!k || k.brand !== brand || k.id !== id) return;
    const r = await fetchTicket(brand, id, true);
    if (S.tk !== k || !r || !r.ok || !r.ticket || typeof r.ticket !== 'object') return;
    if (r.cache && typeof r.cache.at === 'number') k.srvAt = Math.max(k.srvAt || 0, r.cache.at);
    liveUpdate(k, r);
    Draft.refreshSend();
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
        h('span', { id: 'tk-check', class: 'tk-check', hidden: true, 'data-test': 'tk-check' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', t('checking')),
        h('span', { id: 'tk-presence', class: 'chip presence outline', hidden: true, role: 'status', 'aria-live': 'polite', 'data-test': 'tk-presence' }),
        h('span', { id: 'tk-snooze', class: 'tk-snooze', hidden: true, 'data-test': 'tk-snooze' })),
      h('div', { class: 'ch-banner ' + (isWA(x) ? 'wa' : 'email'), 'data-test': isWA(x) ? 'wa-banner' : 'email-banner' },
        icon(isWA(x) ? 'wa' : 'mail'), t(isWA(x) ? 'wa_banner' : 'email_banner')),
      contact,
      null,                 // the sale button + chips were here; sales live only in the managers' table (Owner, 2026-10-14)
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
    const cc = convCard(ex.conversation || [], outgoingFor(k.brand, k.id, ex.conversation || []));
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
    const dcard = x.status === 'bot' ? null : (enMode(x) && (isOpen || canFollowUp(x)) ? EnDraft.card(x) : Draft.card(x));
    if (dcard && x.recommendation && isOpen) {
      const h3 = dcard.querySelector('h3');
      h3.after(h('div', { class: 'todo-chip', 'data-test': 'what-to-do-chip' }, h('b', { text: t('what_to_do') + ': ' }), h('span', { class: 'tk-reco2', dir: 'auto', text: x.recommendation })));
    }
    const subx = SubCancel.slot();                 // "לבטל את המנוי" (2026-10-16): bottom of the send area, both desks
    if (dcard) { dcard.append(subx); dcard.addEventListener('input', function () { SubCancel.paint(); }); body.append(dcard); } else body.append(subx);
    body.append(h('div', { id: 'orders-card' }, ordersCard(ex, x)));
    // Rendered only once apiBoot says the brand HAS subscriptions; a deep link can arrive first (paintSubs fills it later).
    const subsHidden = !!(ex.notes && ex.notes.subscriptions === 'brand_none');
    body.append(h('div', { id: 'subs-card' }, S.boots[k.brand] && !noSubs(k.brand) && !subsHidden ? subsCard(ex, x) : null));
    body.append(h('div', { id: 'notes-card' }, notesCard(x)));
    body.append(h('div', { id: 'related-card' }, relatedCard()));
    body.append(detailsCard(x));
    // Owner, 2026-10-11: which of the brand's mailboxes the customer wrote to — small, at the very bottom. Email only; nothing when unknown.
    const mbox = !isWA(x) && typeof ex.mailbox === 'string' ? ex.mailbox.trim() : '';
    if (mbox) body.append(h('p', { class: 'muted small tk-mailbox', 'data-test': 'tk-mailbox' }, t('mailbox_at') + ' ', h('bdi', { dir: 'ltr', text: mbox })));
    if (k.extrasErr) body.insertBefore(h('div', { class: 'err-box', text: k.extrasErr }), body.children[1]);
    Outbox.paintBanner();
    paintLive(k);
    paintPresence(k, k.others);
    Snooze.paintTicket(k);
    if (enMode(x)) {
      if (k.tr && k.tr.ok) { Translate.paint(k); EnDraft.prefill(x.id, k.tr.draft); } else Translate.load(k);
    } else if (HeTranslate.needed(k)) {
      if (k.trHe && k.trHe.ok && k.trHe.sig === k.sig) HeTranslate.paint(k); else HeTranslate.load(k);
    }
    paintSync();
    SubCancel.paint();
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
      if (Outbox.start('apiSend', k.brand, x, { id: x.id, text: text, channel: 'whatsapp' }, 'resend')) {     // stays on the ticket (2026-10-11)
        (OUTGOING[k.brand + '|' + x.id] || (OUTGOING[k.brand + '|' + x.id] = [])).push({ text: text, at: Date.now(), rid: 'resend', queued: true });
        repaintConv(S.tk);
      }
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
  const MEDIA_MARKER_RE = /^\[(audio|video|file|image|sticker|document|location|contacts?)\]$/i;
  /** What the message body shows: a media-only message gets a Hebrew label instead of "[audio]" (and nothing when the player is there). */
  function bodyText(m) {
    const mk = MEDIA_MARKER_RE.exec(String(m.text || '').trim());
    if (!mk) return m.text;
    const kind = mk[1].toLowerCase();
    if (kind === 'audio') return (m.photos || []).some(isVoiceSlot) ? '' : t('voice_dondy');
    return t('media_' + (kind === 'video' ? 'video' : 'file'));
  }
  function isVoiceSlot(p) { return !!p && (/^a\d/.test(String(p.ref || '')) || (!!p.file && (p.file.kind === 'audio' || /^audio\//.test(String(p.file.mime || ''))))); }
  function photoChips(photos) {
    if (!Array.isArray(photos) || !photos.length) return null;
    const row = h('div', { class: 'photos' });
    photos.forEach(function (p) {
      if (!p || typeof p !== 'object') return;
      const cm = p.file && /^core-media:(m[0-9a-f]{24})$/.exec(String(p.file.url || ''));
      if (isVoiceSlot(p)) {     // a voice message (2026-10-11): played right here
        if (cm && S.brand) {
          const au = h('audio', { class: 'voice-player', controls: '', preload: 'none', src: '/api/' + encodeURIComponent(S.brand) + '/photo/' + cm[1], 'data-test': 'voice-player' });
          au.addEventListener('error', function () { au.replaceWith(h('span', { class: 'chip photo dondy', text: t('voice_gone'), 'data-test': 'voice-gone' })); });
          row.append(au);
        } else row.append(h('span', { class: 'chip photo ' + (p.unavailable ? 'dondy' : 'wait'), text: t(p.unavailable ? 'voice_dondy' : 'voice_wait'), 'data-test': 'voice-wait' }));
        return;
      }
      if (cm && S.brand) {      // stored on our server (2026-10-11): shown right here, a click opens it full size
        const src = '/api/' + encodeURIComponent(S.brand) + '/photo/' + cm[1];
        const img = h('img', { class: 'photo-thumb', src: src, alt: t('photo_open'), loading: 'lazy' });
        const a = h('a', { class: 'photo-link', href: src, target: '_blank', rel: 'noopener noreferrer', 'data-test': 'photo-img' }, img);
        img.addEventListener('error', function () { a.replaceWith(h('span', { class: 'chip photo dondy', text: t('photo_gone'), 'data-test': 'photo-gone' })); });
        row.append(a);
        return;
      }
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
  // ---- files the agent sends with the reply (Owner, 2026-10-11). Server: attach.py (checks + upload) -> engine/Attach.gs (stored on the core).
  // A file is uploaded the moment it is picked; the send carries only its id, so the Outbox's retries never upload or send it twice.
  // Shown only where the engine says it can go (apiBoot.attach): email; WhatsApp only while the brand's switch is on and the 24 hours are open.
  const Attach = (function () {
    const EXT = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'txt'];
    const WA_EXT = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx'];
    const state = {};                 // 'brand|ticket' -> [{key, name, size, id, status: 'up'|'ok'|'err', msg}]
    const painters = {};              // 'brand|ticket' -> the open composer's repaint
    let seq = 0;
    function k(brand, id) { return brand + '|' + id; }
    function info(brand) { const b = S.boots[brand]; return b && b.attach && typeof b.attach === 'object' ? b.attach : null; }
    function allowed(brand, x) {
      const i = info(brand);
      if (!i || !canWork()) return false;
      return isWA(x) ? !!i.whatsapp && !waWinClosed(x) : !!i.email;
    }
    function items(brand, id) { return state[k(brand, id)] || (state[k(brand, id)] = []); }
    function ext(name) { const m = /\.([A-Za-z0-9]{1,5})$/.exec(String(name || '')); return m ? m[1].toLowerCase() : ''; }
    function mb(n) { return Math.round(n / 1048576); }
    function size(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }
    function ids(brand, id) { return (state[k(brand, id)] || []).filter(function (a) { return a.status === 'ok'; }).map(function (a) { return a.id; }); }
    function blocks(brand, id) { return (state[k(brand, id)] || []).some(function (a) { return a.status === 'up' || a.status === 'err'; }); }
    function sent(brand, id) { delete state[k(brand, id)]; const p = painters[k(brand, id)]; if (p) p(); }   // handed to the Outbox: the row empties
    async function upload(brand, x, it, file, repaint) {
      const fd = new FormData();
      fd.append('file', file, file.name);
      fd.append('channel', isWA(x) ? 'whatsapp' : 'email');
      let r = null;
      try {
        const res = await fetch('/api/' + encodeURIComponent(brand) + '/attach', { method: 'POST', credentials: 'same-origin', body: fd,
          headers: { 'X-CSRF-Token': CSRF, Accept: 'application/json', 'X-UI-Lang': LANG } });
        r = await res.json().catch(function () { return { ok: false, msg: t('att_failed') }; });
      } catch (e) { r = { ok: false, msg: t('err_network') }; }
      if (items(brand, x.id).indexOf(it) < 0) return;          // removed meanwhile
      if (r && r.ok === true && /^a[0-9a-f]{24}$/.test(String(r.id || ''))) { it.status = 'ok'; it.id = r.id; it.name = r.name || it.name; it.size = r.size || it.size; }
      else { it.status = 'err'; it.msg = (r && (r.msg || r.error)) || t('att_failed'); }
      repaint();
    }
    /** The 📎 row of a composer, or null where files cannot go. onChange: the composer re-checks its send button.
     *  A deep link can draw the composer before the brand's list (apiBoot) is in: then a hidden slot waits for it (measured: the row was missing). */
    function box(brand, x, onChange) {
      if (info(brand)) return build(brand, x, onChange);
      const slot = h('div', { class: 'attach-slot', hidden: true });
      let n = 0;
      const tick = function () {
        if (info(brand)) { const real = build(brand, x, onChange); if (real) slot.replaceWith(real); else slot.remove(); return; }
        if (++n < 100 && (slot.isConnected || n < 5)) setTimeout(tick, 300);
      };
      setTimeout(tick, 300);
      return slot;
    }
    function build(brand, x, onChange) {
      if (!allowed(brand, x)) return null;
      const i = info(brand);
      const wa = isWA(x);
      const input = h('input', { type: 'file', hidden: true, 'data-test': 'attach-input', accept: (wa ? WA_EXT : EXT).map(function (e) { return '.' + e; }).join(',') });
      if (!wa) input.multiple = true;
      const btn = h('button', { class: 'btn small ghost', type: 'button', text: t('att_btn'), 'data-test': 'attach-btn', onclick: function () { input.click(); } });
      const hint = h('span', { class: 'muted small', text: t(wa ? 'att_hint_wa' : 'att_hint', { mb: mb(wa ? i.waFileMax : i.fileMax) }) });
      const chips = h('div', { class: 'att-chips', 'data-test': 'attach-chips' });
      const err = h('div', { class: 'att-err small', 'aria-live': 'polite', hidden: true, 'data-test': 'attach-err' });   // not role=alert: the composer's own error box is the alert
      const wait = h('div', { class: 'muted small', hidden: true, 'data-test': 'attach-wait', text: t('att_wait') });
      const el = h('div', { class: 'attach', 'data-test': 'attach' }, h('div', { class: 'att-row' }, btn, hint), chips, err, wait, input);
      function paint() {
        clear(chips);
        const list = items(brand, x.id);
        list.forEach(function (a) {
          const rm = h('button', { class: 'att-x', type: 'button', 'aria-label': t('att_remove'), title: t('att_remove'), text: '✕', 'data-test': 'attach-remove',
            onclick: function () { const l = items(brand, x.id); const n = l.indexOf(a); if (n >= 0) l.splice(n, 1); paint(); } });
          chips.append(h('span', { class: 'chip file ' + a.status, 'data-test': 'attach-chip', 'data-status': a.status, title: a.status === 'err' ? a.msg : '' },
            h('span', { class: 'att-name', dir: 'auto', text: a.name }), h('span', { class: 'att-size', text: size(a.size) }),
            a.status === 'up' ? h('span', { class: 'att-st', text: t('att_uploading') }) : a.status === 'err' ? h('span', { class: 'att-st', text: a.msg }) : null, rm));
        });
        btn.disabled = wa && list.length >= 1;
        wait.hidden = !blocks(brand, x.id);
        if (onChange) onChange();
      }
      function say(msg) { err.textContent = msg; err.hidden = !msg; }
      input.addEventListener('change', function () {
        const files = Array.prototype.slice.call(input.files || []);
        input.value = '';
        say('');
        const list = items(brand, x.id);
        const room = wa ? 1 - list.length : (i.emailFilesMax || 10) - list.length;
        if (files.length > room) { say(wa ? t('att_wa_one') : t('att_count', { n: i.emailFilesMax || 10 })); return; }
        let total = list.reduce(function (s, a) { return s + (a.size || 0); }, 0);
        for (let n = 0; n < files.length; n++) {
          const f = files[n];
          if ((wa ? WA_EXT : EXT).indexOf(ext(f.name)) < 0) { say(t('att_type', { name: f.name })); return; }
          const cap = wa ? i.waFileMax : i.fileMax;
          if (f.size > cap || f.size < 1) { say(t('att_size', { name: f.name, mb: mb(cap) })); return; }
          total += f.size;
        }
        if (!wa && total > i.emailTotalMax) { say(t('att_total', { mb: Math.floor(i.emailTotalMax / 1000000) })); return; }
        files.forEach(function (f) {
          const it = { key: ++seq, name: f.name, size: f.size, id: null, status: 'up', msg: '' };
          list.push(it);
          upload(brand, x, it, f, function () { const p = painters[k(brand, x.id)]; if (p) p(); });   // the row on screen NOW (the ticket may have re-rendered)
        });
        paint();
      });
      painters[k(brand, x.id)] = paint;
      paint();
      return el;
    }
    /** Names of the files that went with a message (conversation). Names only: the customer's copy is in their inbox. */
    function fileChips(files) {
      if (!Array.isArray(files) || !files.length) return null;
      return h('div', { class: 'att-chips sent', 'data-test': 'msg-files' }, files.slice(0, 10).map(function (n) {
        return h('span', { class: 'chip file ok', dir: 'auto', text: t('att_sent_chip', { name: String(n) }) });
      }));
    }
    return { box: box, ids: ids, blocks: blocks, sent: sent, fileChips: fileChips, allowed: allowed };
  })();
  const ORIG = new WeakMap();
  function convCard(conv, outgoing) {
    const card = h('div', { class: 'card' }, h('h3', null, t('conversation'), h('span', { id: 'tr-state', class: 'chip outline', hidden: true })));
    const list = h('div', { class: 'conv' });
    const msgs = conv.map(function (m, i) { return Object.assign({ _i: i }, m); }).sort(function (a, b) { return (ms(a.at) || 0) - (ms(b.at) || 0); });
    msgs.forEach(function (m, i) {
      const who = m.who === 'us' ? 'us' : (m.who === 'automatic' ? 'automatic' : 'customer');
      const long = String(m.text || '').length > 600 && i < msgs.length - 1;
      const el = h('div', { class: 'msg ' + who + (long ? ' collapsed' : ''), 'data-i': String(m._i) },
        h('div', { class: 'meta' }, h('b', { text: t(who) }), h('span', { text: fmtDate(m.at, true) })),
        h('div', { class: 'mbody' }, messageBody(bodyText(m))), photoChips(m.photos), Attach.fileChips(m.files));
      ORIG.set(el, String(m.text || ''));
      if (long) {
        const mb = h('button', { class: 'more-btn', type: 'button', text: t('show_more') });
        mb.addEventListener('click', function () { const c = el.classList.toggle('collapsed'); mb.textContent = c ? t('show_more') : t('show_less'); });
        el.append(mb);
      }
      list.append(el);
    });
    (outgoing || []).forEach(function (o) {          // sent from this page, not in the conversation yet (2026-10-11)
      list.append(h('div', { class: 'msg us pending', 'data-test': 'msg-outgoing' },
        h('div', { class: 'meta' }, h('b', { text: t('us') }), h('span', { text: fmtDate(new Date(o.at).toISOString(), true) }), ' ',
          h('span', { class: 'chip st-sent', text: o.queued ? t('msg_queued') : t('msg_pending') })),
        h('div', { class: 'mbody', dir: 'auto' }, messageBody(o.text))));
    });
    if (!msgs.length && !(outgoing || []).length) list.append(h('div', { class: 'muted', text: '—' }));
    card.append(list);
    return card;
  }
  /** Redraw only the conversation of the open ticket (an outgoing message was added, or one came back refused). */
  function repaintConv(k) {
    const old = document.getElementById('tk-conv');
    if (!old || !k || S.tk !== k) return;
    const cc = convCard((k.extras && k.extras.conversation) || [], outgoingFor(k.brand, k.id, (k.extras && k.extras.conversation) || []));
    cc.id = 'tk-conv';
    if (isWA(k.ticket)) cc.classList.add('wa');
    old.replaceWith(cc);
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
      if (st.fu) { writeLocal(); return; }               // another message on an answered ticket: the engine keeps no draft for it
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
          writeLocal();                                // kept until a server copy shows this text (review 2026-10-11 #1)
          if (mine.ta.value === text && !mine.dirty) setState('saved');
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
    window.addEventListener('beforeunload', function (e) { if (st && (st.dirty || st.saving)) { writeLocal(); if (st.fu) return; e.preventDefault(); e.returnValue = ''; } });
    window.addEventListener('pagehide', function () { if (st && st.dirty) writeLocal(); });

    function card(x) {
      pruneOld();
      const isOpen = OPEN.indexOf(x.status) >= 0;
      const brand = tkBrand(x);
      const k = key(brand, x.id);
      // Owner, 2026-10-11: an answered / closed ticket takes another message. It starts EMPTY: never the answer already sent.
      const fu0 = !isOpen && canFollowUp(x);
      const server = fu0 ? '' : String(x.draft_text || '');
      const local = readLocal(k);
      const ta = h('textarea', { dir: 'auto', 'aria-label': t('draft'), spellcheck: 'true', rows: fu0 ? '5' : '9' });
      ta.value = server;
      st = { id: x.id, brand: brand, key: k, ta: ta, base: server, dirty: false, saving: false, timer: null, fu: fu0 };
      const me = st;
      const title = h('h3', { text: fu0 ? t('fu_title') : t('draft') });
      const stateEl = h('div', { class: 'save-state', 'aria-live': 'polite' });
      const note = h('div');
      const fuEl = h('div', { class: 'fu-note muted small', 'data-test': 'fu-note', hidden: true });
      const offerEl = h('div', { class: 'stale', hidden: true, 'data-test': 'draft-offer' });
      st.stateEl = stateEl; st.offerEl = offerEl;
      const errEl = h('div', { hidden: true });
      const c = h('div', { class: 'card draft' + (fu0 ? ' followup' : ''), 'data-test': 'draft-card' }, title, fuEl, note, offerEl, ta, stateEl, errEl);
      if (!isOpen && !fu0) {
        ta.readOnly = true;
        if (local) dropLocal();
        c.append(h('div', { class: 'muted small', text: t('draft_readonly') }));
        return c;
      }
      function cur() { return S.tk && S.tk.id === x.id ? S.tk.ticket : x; }
      function paintFu() {
        if (!me.fu) { fuEl.hidden = true; return; }
        const tk = cur();
        title.textContent = t('fu_title');
        c.classList.add('followup');
        ta.placeholder = t('fu_ph');
        clear(fuEl);
        const line = tk.status === 'done' ? 'fu_done' : waQueued(tk) ? 'fu_queued' : 'fu_sent';
        if (tk.handled_at || tk.handled_by) fuEl.append(h('div', { 'data-test': 'fu-who' }, tx(line, { who: whoName(tk.handled_by), when: whenShort(tk.handled_at) })));
        fuEl.append(h('div', { text: t('fu_hint') }));
        fuEl.hidden = false;
      }
      paintFu();
      const wroteAt = ms(x.waiting_since);
      if (me.fu) {
        // another message lives on this device only (the engine keeps no draft for an answered ticket); a refused one comes back here
        if (local && String(local.text || '').trim()) {
          ta.value = local.text; me.dirty = true; me.edited = true;
          note.append(h('div', { class: 'muted small', 'data-test': local.back ? 'fu-restored' : 'restored', text: local.back ? t('fu_restored') : t('restored') }));
        } else if (local) dropLocal();
      } else if (local && local.text !== server && local.text.trim() && wroteAt && local.at && local.at < wroteAt) {
        // review 2026-10-11 #5: the customer wrote after this device copy — the new server draft leads, the old text is offered
        const older = h('div', { class: 'stale', 'data-test': 'draft-older-local' }, h('span', { text: t('local_older') }));
        older.append(' ', h('button', { class: 'btn small ghost', type: 'button', text: t('use_mine_old'), onclick: function () {
          if (!st || st.ta !== ta) return;
          ta.value = local.text; st.dirty = true; st.edited = true; clear(note); writeLocal(); save();
          if (st.refreshSend) st.refreshSend();
        } }));
        note.append(older);
      } else if (local && local.text !== server && local.text.trim()) {
        ta.value = local.text;
        st.dirty = true;
        st.edited = true;
        if (local.base === server) {
          note.append(h('div', { class: 'muted small', 'data-test': local.back ? 'fu-restored' : 'restored', text: local.back ? t('fu_restored') : t('restored') }));
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
        pingEdit(me.brand, me.id);
        TYPED[me.brand + '|' + me.id] = Date.now();
        me.dirty = true;
        me.edited = true;                                    // for good: a saved edit is still the agent's text
        writeLocal();
        setState('local');
        clearTimeout(me.timer);
        me.timer = setTimeout(save, 2500);
        sendBtn.disabled = sendDisabled();
      });
      ta.addEventListener('blur', function () { clearTimeout(me.timer); if (me.dirty && st === me) save(); });

      // Live, never captured at render time: a deep link can render this card before apiBoot answers.
      // Unknown mode = disabled (fail closed); loadBoot() calls refreshSend() when the answer lands.
      function isDry() { const b = S.boots[me.brand]; return !b || !!b.dryRun; }
      function winClosed() { return waWinClosed(cur(), me.fu); }
      function sendDisabled() { return isDry() || winClosed() || !ta.value.trim() || waQueued(cur()) || waLocked(me.brand, x.id) || Outbox.blocks(me.brand, x.id) || Attach.blocks(me.brand, x.id); }
      const actions = h('div', { class: 'actions' });
      async function doSend() {
        const text = ta.value;
        clear(errEl); errEl.hidden = true;
        clearTimeout(me.timer);
        writeLocal();                                        // the text is safe on this device whatever happens
        const tk = cur();
        // seen: the ticket as THIS screen shows it — someone else's answer after it is refused by the engine (changed_meanwhile)
        const args = { id: x.id, text: text, seen: String(tk.handled_at || '') };
        const files = Attach.ids(me.brand, x.id);            // ids of files already uploaded (attach.py): the send carries only these
        if (files.length) args.attachments = files;
        if (me.fu || OPEN.indexOf(tk.status) < 0) args.followup = true;      // answered / closed, OR this page already sent on it (its copy may lag)
        if (isWA(x)) args.channel = 'whatsapp';
        // Owner, 2026-10-05: the agent never waits for the engine — the outbox sends it in the background.
        // Owner, 2026-10-11: and the send never closes or moves on. The message shows in the conversation, the box empties for the next one.
        const it = Outbox.start('apiSend', me.brand, x, args);
        if (!it) return null;
        delete TYPED[me.brand + '|' + x.id];                // sent: no longer "writing" for the others' presence chip
        Attach.sent(me.brand, x.id);
        const ok = OUTGOING[me.brand + '|' + x.id] || (OUTGOING[me.brand + '|' + x.id] = []);
        ok.push({ text: text, at: Date.now(), rid: it.rid, queued: isWA(x) });
        ta.value = ''; me.base = ''; me.dirty = false; me.edited = false; me.saving = false;
        dropLocal(); setState('', ''); clear(note); clear(offerEl); offerEl.hidden = true;
        me.fu = true; paintFu();
        repaintConv(S.tk);
        me.refreshSend();
        return it;
      }
      async function doClose(fn) {
        clear(errEl); errEl.hidden = true;
        if (Outbox.start(fn, me.brand, x, { id: x.id })) goNext(me.brand, x.id);   // closing DOES move on: off the list, next ticket
      }
      const sendLabel = isWA(x) ? t('send_wa') : t('send_email');
      const waNote = h('div', { class: 'wa-note', 'data-test': 'wa-queued' });
      const waitEl = h('div', { class: 'fu-wait muted small', role: 'status', 'data-test': 'fu-wait', hidden: true, text: t('fu_wait') });
      c.append(waNote, waitEl);
      function paintWa() {
        clear(waNote);
        const tk = cur();
        if (!me.fu && waQueued(tk) && tk.status !== 'wa_queued') waNote.append(h('span', { class: 'chip ch-wa big', text: t('wa_queued_chip') }));
        else if (waLocked(me.brand, x.id)) waNote.append(h('span', { class: 'chip bad big', text: t('wa_locked') }), ' ',
          h('button', { class: 'btn small', type: 'button', text: t('wa_check'), onclick: function () { openTicket(x.id, { fresh: true }); } }));
        waNote.hidden = !waNote.firstChild;
        waitEl.hidden = !(me.fu && (waQueued(tk) || Outbox.blocks(me.brand, x.id)));
      }
      const sendBtn = armed(sendLabel, t('send_arm'), 'primary' + (isWA(x) ? ' wa' : ''), function () { if (!sendDisabled()) doSend(); });
      sendBtn.setAttribute('data-test', 'send-btn');
      // Owner, 2026-10-14: 60% of sends were followed by a close by the same agent (median 2.6 s later). One armed action sends, closes and moves
      // on at once; the close waits in the outbox behind THIS send and runs only once the engine accepted it.
      function sendCloseOff() { return sendDisabled() || !!Outbox.lastChange(me.brand, x.id); }     // "someone answered meanwhile": read first
      const sendCloseBtn = armed(t('send_close'), t('send_close_arm'), 'primary send-close' + (isWA(x) ? ' wa' : ''), function () {
        if (sendCloseOff()) return;
        doSend().then(function (it) { if (it && Outbox.start('apiClose', me.brand, x, { id: x.id })) goNext(me.brand, x.id); });
      });
      sendCloseBtn.setAttribute('data-test', 'send-close-btn');
      sendCloseBtn.setAttribute('title', t('send_close_title'));
      // "תשובה אחרת" (Owner, 2026-10-14): a different AI answer for this open ticket, on the agent's click; the previous one is a click away
      const rd = Regen.row({
        brand: me.brand, x: x, k: function () { return S.tk && S.tk.id === x.id ? S.tk : null; }, ticket: cur,
        alive: function () { return st === me && ta.isConnected; },
        visible: function () { return !me.fu && OPEN.indexOf(cur().status) >= 0; },
        canUse: function () { return !me.fu && OPEN.indexOf(cur().status) >= 0 && !waQueued(cur()) && !Outbox.blocks(me.brand, x.id); },
        snapshot: async function () {
          clearTimeout(me.timer);
          for (let i = 0; i < 100 && me.saving; i++) await sleep(100);        // an autosave on its way lands first: the engine then has what we show
          return { base: me.base, box: ta.value, dirty: me.dirty || me.edited };
        },
        apply: function (text) {
          ta.value = text; me.base = text; me.dirty = false; me.edited = false;
          dropLocal(); setState('', ''); clear(offerEl); offerEl.hidden = true;
          if (me.refreshSend) me.refreshSend();
          return null;
        },
        restore: function (snap, server) {
          if (typeof server === 'string') me.base = server;
          ta.value = snap.box;
          if (snap.box !== me.base) { me.dirty = true; me.edited = true; writeLocal(); save(); } else { me.dirty = false; me.edited = false; dropLocal(); setState('', ''); }
          if (me.refreshSend) me.refreshSend();
        }
      });
      stateEl.after(rd.el);
      // The close button says what it does: "close without sending" before any answer, "close the ticket" after one. Rebuilt only when that changes.
      const closeSlot = h('span', { class: 'close-slot' });
      let closeKind = null;
      function paintClose() {
        const tk = cur();
        const mineOut = !!OUTGOING[me.brand + '|' + x.id];
        const kind = tk.status === 'done' && !mineOut ? 'none' : (me.fu || tk.status === 'sent' || mineOut) ? 'close' : 'nosend';
        if (kind !== closeKind) {
          closeKind = kind;
          clear(closeSlot);
          if (kind !== 'none') closeSlot.append(kind === 'close' ? closeTicketBtn(function () { doClose('apiClose'); }) : closeNoSendBtn(function () { doClose('apiClose'); }));
        }
        const b = closeSlot.firstChild;
        if (b && !b.classList.contains('arm')) b.disabled = Outbox.closeLocked(me.brand, x.id);     // 2026-10-14: queued behind a send, never waits for it
      }
      st.refreshSend = function () {
        paintWa();
        paintClose();
        rd.paint();
        if (me.fu) paintFu();
        if (!sendCloseBtn.classList.contains('arm')) sendCloseBtn.disabled = sendCloseOff();
        if (sendBtn.classList.contains('arm')) return;
        sendBtn.disabled = sendDisabled();
        const cm = Outbox.lastChange(me.brand, x.id);
        sendBtn.textContent = isDry() && S.boots[me.brand] ? t('send_dry') : cm && ta.value.trim() ? t('cm_send_anyway') : sendLabel;
        sendBtn.title = isDry() ? t('dry_run') : '';
      };
      st.refreshSend();
      actions.append(sendBtn, sendCloseBtn, closeSlot);
      if (winClosed()) {
        c.append(h('div', { class: 'wa-win-note', role: 'status', 'data-test': 'wa-win-note', text: t('wa_win_note') }));
        const tb = templateBox(me.brand, x, function () { return ta.value; });
        ta.addEventListener('input', function () { tb.refresh(); });
        c.append(tb);
      }
      const attEl = Attach.box(me.brand, x, function () { if (me.refreshSend) me.refreshSend(); });   // 📎 (null where files cannot go)
      if (attEl) c.append(attEl);
      c.append(actions);
      return c;
    }
    /** A send that did not go out (refused, or "unsent" after the last try): the text comes back to the box on THIS ticket, or to the
     *  device copy that the next open restores. The box is never overwritten when the agent already typed something new. */
    function giveBack(brand, id, text) {
      if (typeof text !== 'string' || !text.trim()) return;
      const k = key(brand, id);
      if (st && st.key === k && st.ta && !st.ta.readOnly) {
        if (st.ta.value.trim()) return;
        st.ta.value = text; st.dirty = true; st.edited = true;
        writeLocal();
        try { const v = readLocal(k); if (v) { v.back = true; localStorage.setItem(k, JSON.stringify(v)); } } catch (e) { /* ignore */ }
        setState('local');
        if (st.refreshSend) st.refreshSend();
        return;
      }
      const prev = readLocal(k);
      if (prev && String(prev.text || '').trim()) return;
      const memo = S.tkMemo[brand + '|' + id];
      const base = memo && memo.ticket && OPEN.indexOf(memo.ticket.status) >= 0 ? String(memo.ticket.draft_text || '') : '';
      try { localStorage.setItem(k, JSON.stringify({ text: text, base: base, at: Date.now(), back: true })); } catch (e) { /* the outbox banner still names it */ }
    }
    /** The engine wrote a new draft while this one is on screen. Untouched text is replaced (and said so); an edited
     *  one is never overwritten — the new draft is offered next to it. */
    function offer(text) {
      if (!st || !st.ta || !st.offerEl || st.ta.readOnly || st.fu) return;     // another message is never replaced by an engine draft
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
    return { card: card, flush: flush, detach: detach, offer: offer, giveBack: giveBack, isDirty: function () { return !!(st && (st.dirty || st.saving)); },
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
      btn.textContent = showing === 'en' ? t('show_orig') : t(LANG === 'en' ? 'show_en' : 'show_he');
    }
    btn.addEventListener('click', function () { showing = showing === 'en' ? 'orig' : 'en'; paint(); });
    toggleHost.append(btn);
    paint();
  }

  /** True when a Hebrew-desk agent cannot read the text as is (Russian, Arabic, English...). Links, emails and tokens with a
   *  digit (order / tracking numbers) do not count. Mirror of assistant.py script_lang. */
  function foreignText(text) {
    if (MEDIA_MARKER_RE.test(String(text || '').trim())) return false;     // "[audio]" is not text (2026-10-12)
    const s = String(text || '').replace(/https?:\/\/\S+|www\.\S+|\S+@\S+|\S*\d\S*/g, ' ');
    const he = (s.match(/[\u0590-\u05FF]/g) || []).length, ru = (s.match(/[\u0400-\u04FF]/g) || []).length;
    const ar = (s.match(/[\u0600-\u06FF]/g) || []).length, la = (s.match(/[A-Za-z]/g) || []).length;
    if (!he && !ru && !ar && !la) return false;
    return !(he && he >= ru && he >= ar && la <= 2 * he);
  }

  /** Hebrew desk (Owner, 2026-10-10): the customer's messages in another language are translated into Hebrew automatically,
   *  with "הצג מקור" to see the original. We reply only in Hebrew; the draft is Hebrew already. */
  const HeTranslate = {
    needed(k) {
      if (LANG === 'en' || !k || !k.ticket) return false;
      const conv = (k.extras && k.extras.conversation) || [];
      return foreignText(k.ticket.subject) || conv.some(function (m) { return m && m.who !== 'us' && m.who !== 'automatic' && foreignText(m.text); });
    },
    async load(k) {
      const requestId = k.trHeRequest = (k.trHeRequest || 0) + 1;
      const sig = k.sig;
      k.trHe = { loading: true };
      this.paint(k);
      const r = await api('/api/' + encodeURIComponent(k.brand) + '/translate-he', { ticketId: k.id }, 'POST', { quiet: true });
      if (S.tk !== k || k.trHeRequest !== requestId) return;
      k.trHe = r.ok ? Object.assign({}, r, { sig: sig }) : { err: r.msg || r.error };
      this.paint(k);
      paintLive(k);
    },
    paint(k) {
      const chip = document.getElementById('tr-state');
      const tr = k.trHe || {};
      if (chip) {
        chip.hidden = false;
        chip.className = 'chip outline';
        chip.setAttribute('data-test', 'he-translate');
        clear(chip);
        if (tr.loading) chip.append(t('tr_loading'));
        else if (tr.err) { chip.className = 'chip bad'; chip.append(tx('tr_failed', { m: tr.err })); }
        else {
          const src = ((tr.conversation || [])[0] || {}).source || k.ticket.language;
          chip.append(t('tr_from', { l: langName(src) }) + ' · ' + t('tr_reply_he'));   // one plain string: "מ" + "רוסית" never split
          if (tr.incomplete) { chip.className = 'chip bad'; chip.append(' · ', tx('tr_incomplete', { n: tr.incomplete })); }
        }
        if (!tr.loading && (tr.err || tr.incomplete)) chip.append(' ', h('button', { type: 'button', class: 'more-btn', text: t('tr_retry'), onclick: function () { HeTranslate.load(k); } }));
      }
      if (!tr.ok) return;
      const pane = $('ticket-pane');
      (tr.conversation || []).forEach(function (c) {
        if (!c || typeof c.text !== 'string') return;
        const el = pane.querySelector('.msg[data-i="' + Number(c.i) + '"]');
        if (!el || el.dataset.tr) return;
        if (typeof c.o === 'string' && (ORIG.get(el) || '').slice(0, 120) !== c.o) return;   // the conversation changed meanwhile: never on the wrong message
        el.dataset.tr = '1';
        el.querySelector('.mbody').setAttribute('lang', 'he');
        bilingual(el.querySelector('.mbody'), ORIG.get(el) || '', c.text, el.querySelector('.meta'));
      });
      const subject = document.getElementById('tk-subject');
      if (subject && tr.subject && !subject.dataset.tr) {
        subject.dataset.tr = '1';
        const host = h('span', { class: 'sum-toggle' });
        subject.after(host);
        bilingual(subject, k.ticket.subject || '', tr.subject, host);
      }
    }
  };

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
      const brand = tkBrand(x);
      const key = 'cs.draft.en.' + brand + '.' + x.id;
      let local = null;
      try { local = localStorage.getItem(key); } catch (e) { local = null; }
      // Owner, 2026-10-11: an answered / closed ticket takes another message — written in English, delivered in Hebrew, starting EMPTY
      const fu0 = OPEN.indexOf(x.status) < 0 && canFollowUp(x);
      const ta = h('textarea', { dir: 'ltr', lang: 'en', rows: fu0 ? '5' : '8', 'aria-label': t('en_draft') });
      const note = h('div', { class: 'muted small' });
      const review = h('div', { class: 'en-review', hidden: true, 'data-test': 'en-review' });
      const errEl = h('div');
      const me = { id: x.id, brand: brand, ta: ta, note: note, prefilled: fu0, translated: null, busy: false, fu: fu0, key: key };
      cur = me;
      function tkNow() { return S.tk && S.tk.id === x.id ? S.tk.ticket : x; }
      const title = h('h3', { text: fu0 ? t('fu_title') : t('en_draft') });
      const fuEl = h('div', { class: 'fu-note muted small', 'data-test': 'fu-note', hidden: true });
      function paintFu() {
        if (!me.fu) return;
        const tk = tkNow();
        title.textContent = t('fu_title');
        ta.placeholder = t('fu_ph');
        clear(fuEl);
        const line = tk.status === 'done' ? 'fu_done' : waQueued(tk) ? 'fu_queued' : 'fu_sent';
        if (tk.handled_at || tk.handled_by) fuEl.append(h('div', { 'data-test': 'fu-who' }, tx(line, { who: whoName(tk.handled_by), when: whenShort(tk.handled_at) })));
        fuEl.append(h('div', { text: t('fu_hint') }));
        fuEl.hidden = false;
      }
      paintFu();
      if (local !== null && local.trim()) { ta.value = local; note.textContent = t('restored'); me.prefilled = true; } else note.textContent = fu0 ? '' : t('en_draft_loading');
      function isDry() { const b = S.boots[brand]; return !b || !!b.dryRun; }
      function showErr(r) {
        clear(errEl);
        errEl.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error })));
      }
      const reviewBtn = h('button', { class: 'btn primary', type: 'button', text: t('en_review'), 'data-test': 'en-review-btn' });
      const confirmBtn = h('button', { class: 'btn primary' + (isWA(x) ? ' wa' : ''), type: 'button', text: t('en_confirm'), 'data-test': 'en-confirm' });
      const editBtn = h('button', { class: 'btn ghost', type: 'button', text: t('en_edit') });
      // Owner, 2026-10-14: confirm, send and close in one click (the review step is the confirmation here, as for the plain confirm)
      const confirmCloseBtn = h('button', { class: 'btn primary send-close' + (isWA(x) ? ' wa' : ''), type: 'button', text: t('en_confirm_close'), 'data-test': 'en-confirm-close', title: t('send_close_title') });
      let rd = null;
      function refresh() {
        reviewBtn.disabled = me.busy || !ta.value.trim();
        confirmBtn.disabled = me.busy || !me.translated || isDry() || waQueued(S.tk && S.tk.id === x.id ? S.tk.ticket : x) || waLocked(brand, x.id) || Outbox.blocks(brand, x.id) || Attach.blocks(brand, x.id);
        if (me.fu) paintFu();
        paintClose();
        confirmBtn.textContent = isDry() && S.boots[brand] ? t('send_dry') : t(isWA(x) ? 'en_confirm_wa' : 'en_confirm_email');
        confirmBtn.title = isDry() ? t('dry_run') : '';
        confirmCloseBtn.disabled = confirmBtn.disabled;
        if (rd) rd.paint();
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
          h('div', { class: 'actions' }, confirmBtn, confirmCloseBtn, editBtn)]);
        refresh();
      }
      ta.addEventListener('input', function () {
        if (S.tk) pingEdit(S.tk.brand, S.tk.id);
        TYPED[brand + '|' + x.id] = Date.now();
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
        const tk = tkNow();
        const args = { id: x.id, text: me.translated.out, seen: String(tk.handled_at || '') };
        const files = Attach.ids(brand, x.id);              // the files go with the approved Hebrew text
        if (files.length) args.attachments = files;
        if (me.fu || OPEN.indexOf(tk.status) < 0) args.followup = true;      // as in Draft: the page's own send counts before its copy says so
        if (isWA(x)) args.channel = 'whatsapp';
        let started = null;
        try {
          // Owner, 2026-10-11: the send never closes or moves on; the message shows in the conversation and the box empties for the next one
          const it = Outbox.start('apiSend', brand, x, args, undefined, me.translated.en);
          started = it;
          if (it) {
            Attach.sent(brand, x.id);
            (OUTGOING[brand + '|' + x.id] || (OUTGOING[brand + '|' + x.id] = [])).push({ text: me.translated.out, at: Date.now(), rid: it.rid, queued: isWA(x) });
            ta.value = ''; me.translated = null; me.typed = false;
            try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
            note.textContent = '';
            me.fu = true; paintFu();
            paintReview();
            repaintConv(S.tk);
          }
        } finally {
          // Outbox owns the in-flight lock after handoff; a rejected handoff must not freeze this editor.
          me.busy = false; refresh();
        }
        return started;
      }
      confirmBtn.addEventListener('click', function () { send(); });
      confirmCloseBtn.addEventListener('click', function () {
        if (confirmCloseBtn.disabled) return;
        send().then(function (it) { if (it && Outbox.start('apiClose', brand, x, { id: x.id })) goNext(brand, x.id); });
      });
      // "תשובה אחרת" (2026-10-14): the engine writes a new HEBREW draft; this desk shows it in English, like the first one
      rd = Regen.row({
        brand: brand, x: x, k: function () { return S.tk && S.tk.id === x.id ? S.tk : null; }, ticket: tkNow,
        alive: function () { return cur === me && ta.isConnected; },
        visible: function () { return !me.fu && OPEN.indexOf(tkNow().status) >= 0 && !waWinClosed(x, me.fu); },
        canUse: function () { return !me.fu && !me.busy && OPEN.indexOf(tkNow().status) >= 0 && !waQueued(tkNow()) && !Outbox.blocks(brand, x.id); },
        snapshot: async function () { return { base: String(tkNow().draft_text || ''), box: ta.value, typed: !!me.typed }; },
        apply: async function () {
          const r = await api('/api/' + encodeURIComponent(brand) + '/translate', { ticketId: x.id });
          if (cur !== me) return null;
          if (!r.ok || typeof r.draft !== 'string' || !r.draft.trim()) return r.msg || r.error || 'translate_failed';
          ta.value = r.draft; me.translated = null; me.typed = false; me.prefilled = true;
          try { localStorage.removeItem(key); } catch (e) { /* the English text is never kept on the server */ }
          note.textContent = t('en_draft_ai'); clear(errEl); paintReview(); refresh();
          return null;
        },
        restore: function (snap) {
          ta.value = snap.box; me.translated = null; me.typed = snap.typed;
          try { if (snap.typed) localStorage.setItem(key, snap.box); else localStorage.removeItem(key); } catch (e) { /* ignore */ }
          paintReview(); refresh();
        }
      });
      async function doClose(fn) {
        if (Outbox.start(fn, brand, x, { id: x.id })) goNext(brand, x.id);       // closing DOES move on
      }
      const closeSlot = h('span', { class: 'close-slot' });
      let closeKind = null;
      function paintClose() {
        const tk = tkNow();
        const mineOut = !!OUTGOING[brand + '|' + x.id];
        const kind = tk.status === 'done' && !mineOut ? 'none' : (me.fu || tk.status === 'sent' || mineOut) ? 'close' : 'nosend';
        if (kind !== closeKind) {
          closeKind = kind;
          clear(closeSlot);
          if (kind !== 'none') closeSlot.append(kind === 'close' ? closeTicketBtn(function () { doClose('apiClose'); }) : closeNoSendBtn(function () { doClose('apiClose'); }));
        }
        const b = closeSlot.firstChild;
        if (b && !b.classList.contains('arm')) b.disabled = Outbox.closeLocked(brand, x.id);        // 2026-10-14: queued behind a send, never waits for it
      }
      refresh();
      const enCard = h('div', { class: 'card draft en-draft' + (fu0 ? ' followup' : ''), 'data-test': 'en-draft' }, title, fuEl, h('div', { class: 'muted small', text: t('en_safety'), 'data-test': 'hebrew-only-notice' }), note, ta);
      if (waWinClosed(x, me.fu)) {     // past 24 hours: no free text; a template instead (the reply that waits is translated to Hebrew by the server)
        reviewBtn.hidden = true;
        const tbe = templateBox(brand, x, function () { return ta.value; });
        ta.addEventListener('input', function () { tbe.refresh(); });
        enCard.append(h('div', { class: 'wa-win-note', role: 'status', 'data-test': 'wa-win-note', text: t('wa_win_note') }), tbe);
      }
      const attE = Attach.box(brand, x, function () { refresh(); });   // 📎 (null where files cannot go)
      if (attE) enCard.append(attE);
      enCard.append(rd.el, h('div', { class: 'actions' }, reviewBtn, closeSlot), review, errEl);
      rd.paint();
      return enCard;
    }
    /** A send that did not go out: the agent's ENGLISH text comes back to the box (or to the device copy the next open restores). */
    function giveBack(brand, id, src) {
      if (typeof src !== 'string' || !src.trim()) return;
      const k = 'cs.draft.en.' + brand + '.' + id;
      if (cur && cur.id === id && cur.brand === brand && cur.ta && cur.ta.isConnected) {
        if (cur.ta.value.trim()) return;
        cur.ta.value = src; cur.typed = true; cur.prefilled = true;
        try { localStorage.setItem(k, src); } catch (e) { /* ignore */ }
        cur.note.textContent = t('fu_restored');
        if (cur.refresh) cur.refresh();
        return;
      }
      try { if (!String(localStorage.getItem(k) || '').trim()) localStorage.setItem(k, src); } catch (e) { /* the outbox banner still names it */ }
    }
    function prefill(id, text) {
      if (!cur || cur.id !== id || cur.prefilled) return;
      if (text && !cur.ta.value.trim()) { cur.ta.value = text; cur.note.textContent = t('en_draft_ai'); cur.prefilled = true; }
      else cur.note.textContent = '';
      cur.refresh();
    }
    return { card: card, prefill: prefill, giveBack: giveBack, refresh: function () { if (cur && cur.refresh) cur.refresh(); },
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
    SubCancel.paint();                               // the brand's Kaching state arrived with apiBoot
  }

  async function afterAction() {
    const id = S.tk && S.tk.id;
    if (id) delete S.tkMemo[S.brand + '|' + id];          // the server cache was patched by the write; the memo was not
    await loadBoot(S.brand);
    if (id && S.tk && S.tk.id === id) openTicket(id);
  }

  // ---- orders
  // Owner, 2026-10-12: every order shows where its delivery stands. Shopify never records delivery (one carrier, no delivery events), so the
  // stage is computed from the real order / shipping dates and the brand rules: 7-12 Israeli business days on the way (Sun-Thu), late =
  // not shipped by day 4 or not arrived by day 17 (engine Config.gs LATE_UNSHIPPED_DAYS / LATE_SHIPPED_DAYS). Shown as an estimate.
  const SHIP_MIN_BD = 7, SHIP_MAX_BD = 12, SHIP_LATE_UNSHIPPED = 4, SHIP_LATE_SHIPPED = 17;
  function addBusinessDays(t0, n) { const d = new Date(t0); let k = 0; while (k < n) { d.setDate(d.getDate() + 1); if (d.getDay() !== 5 && d.getDay() !== 6) k++; } return d.getTime(); }
  function shipStage(o, nowMs) {
    const now = nowMs || Date.now(), DAY = 86400000;
    const ordered = ms(o.createdAt);
    const shipped = ms((o.fulfillments || []).map(function (f) { return f.createdAt; }).filter(Boolean)[0]);
    const days = ordered ? Math.max(0, Math.floor((now - ordered) / DAY)) : 0;
    if (o.cancelledAt) return { key: 'cancelled', step: -1, tone: 'bad' };
    if (!shipped) return days >= SHIP_LATE_UNSHIPPED ? { key: 'prep_late', step: 0, tone: 'bad', d: days } : { key: 'prep', step: 0, tone: '', d: days + 1 };
    const a = addBusinessDays(shipped, SHIP_MIN_BD), b = addBusinessDays(shipped, SHIP_MAX_BD);
    const base = { a: a, b: b, d: days };
    if (days >= SHIP_LATE_SHIPPED) return Object.assign({ key: 'late', step: 3, tone: 'bad' }, base);
    if (now > b) return Object.assign({ key: 'due', step: 3, tone: 'warn' }, base);
    if (now >= a) return Object.assign({ key: 'arriving', step: 3, tone: 'ok' }, base);
    if (now - shipped < 2 * DAY) return Object.assign({ key: 'shipped', step: 1, tone: '' }, base);
    return Object.assign({ key: 'transit', step: 2, tone: '' }, base);
  }
  function shipStageEl(o) {
    const st = shipStage(o);
    const dm = function (x) { const d = new Date(x); return d.getDate() + '/' + (d.getMonth() + 1); };
    const text = t('dlv_' + st.key, { d: st.d, a: st.a ? dm(st.a) : '', b: st.b ? dm(st.b) : '' });
    const steps = t('dlv_steps').split('|');
    return h('div', { class: 'ship-stage ' + (st.tone || ''), 'data-test': 'ship-stage', 'data-stage': st.key },
      st.step >= 0 ? h('ol', { class: 'ship-steps' }, steps.map(function (s, i) { return h('li', { class: i < st.step ? 'done' : (i === st.step ? 'now' : ''), text: s }); })) : null,
      h('div', { class: 'ship-text', text: text }),
      h('div', { class: 'ship-note muted small', text: t('dlv_note') }));
  }
  function ordersCard(ex, x) {
    const c = ordersCardBody(ex, x);
    const lk = Link.row(ex, x);
    if (lk) c.append(lk);
    return c;
  }
  function ordersCardBody(ex, x) {
    const c = h('div', { class: 'card' }, h('h3', { text: t('orders') }));
    const orders = ex.orders || [];
    const sh = ex.shipping || null;
    if (sh && sh.state && sh.state !== 'unknown' && sh.orderName) {
      c.append(h('p', { class: 'small ship-line' }, h('bdi', { class: 'chip ' + (sh.state === 'not_late' ? 'ok' : sh.state === 'not_applicable' ? '' : 'bad') },
        orderLink(S.tk ? S.tk.brand : S.brand, sh.orderName, orderGid(ex, sh.orderName))), ' ',
        t('ship_line', { state: t('ship_' + sh.state), d: sh.daysSinceOrder })));             // never the internal thresholds
      if (!orders.length && typeof sh.daysSinceOrder === 'number') {   // no order list on this ticket: the stage from the engine's summary (2026-10-12)
        const DAYMS = 86400000, now = Date.now();
        c.append(shipStageEl({ createdAt: new Date(now - sh.daysSinceOrder * DAYMS).toISOString(),
          fulfillments: sh.shipped && typeof sh.daysSinceShipped === 'number' ? [{ createdAt: new Date(now - sh.daysSinceShipped * DAYMS).toISOString() }] : [] }));
      }
    }
    if (ex.ordersError) c.append(h('div', { class: 'problem' }, tx('orders_err', { m: String(ex.ordersError) })));
    if (!orders.length) {
      const note = (ex.notes && typeof ex.notes === 'object') ? ex.notes.orders : undefined;
      const chipNo = (sh && sh.state && sh.state !== 'unknown' && sh.orderName) || (ex.notes && ex.notes.orderNo) || (x && x.order_no);
      if (chipNo && !(sh && sh.orderName)) c.append(h('p', { class: 'small ship-line' }, h('bdi', { class: 'chip outline' }, orderLink(S.tk ? S.tk.brand : S.brand, chipNo, null))));
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
        h('div', { class: 'hd' }, o.name ? h('b', { class: 'ltr' }, orderLink(S.tk ? S.tk.brand : S.brand, o.name, o.id)) : h('b', { class: 'ltr', text: '—' }),
          o.financialStatus ? h('span', { class: 'chip ' + (/PAID/.test(o.financialStatus) && !/REFUND/.test(o.financialStatus) ? 'ok' : ''), text: t('fin_' + o.financialStatus) }) : null,
          o.fulfillmentStatus ? h('span', { class: 'chip ' + (o.fulfillmentStatus === 'FULFILLED' ? 'st-sent' : 'outline'), text: t('ful_' + o.fulfillmentStatus) }) : null),
        shipStageEl(o),
        h('dl', { class: 'kv' },
          h('dt', { text: t('ordered') }), h('dd', { text: fmtDate(o.createdAt) + ' (' + ago(o.createdAt) + ')' }),
          shipped ? h('dt', { text: t('shipped_on') }) : null, shipped ? h('dd', { text: fmtDate(shipped) }) : null,
          tracks.length ? h('dt', { text: t('track') }) : null, tracks.length ? h('dd', null, tracks) : null),
        h('ul', null, (o.items || []).map(function (it) { return h('li', { dir: 'auto', text: (it.quantity > 1 ? it.quantity + ' × ' : '') + it.title }); })),
        OrderEdit.row(x, o, S.tk ? S.tk.brand : S.brand)));
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
      if (canWork()) {
        // Owner, 2026-10-14: every Kaching action (pause, resume, skip, date, products, discount, reactivate) from here
        card.append(h('div', { class: 'actions' },
          h('button', { class: 'btn small', type: 'button', text: t('manage_sub'), 'data-test': 'manage-sub', onclick: function () { Manage.open(x, s); } }),
          cancellable ? h('button', { class: 'btn danger-outline small', type: 'button', text: t('cancel_sub'),
            disabled: !isOpen && false, onclick: function () { Cancel.open(x, s); } }) : null));
      }
      list.append(card);
    });
    c.append(list);
    return c;
  }

  // ---- "קישור לקוח" (the owner's CS team, 2026-10-20): the details on the ticket (often only a WhatsApp phone) are not always the order's. The
  // customer is asked for the order number or the email of the order; the agent enters it here and the engine links ONE order email to the
  // ticket (apiLinkCustomer). The orders / subscriptions panels and the cancel button then use it. None / several = refused, never a guess.
  const Link = (function () {
    function repaint(brand) {
      if (!S.tk || !S.tk.ticket) return;
      const ex = S.tk.extras || {}, x = S.tk.ticket;
      const oc = $('orders-card');
      if (oc) { clear(oc); oc.append(ordersCard(ex, x)); }
      const sc = document.getElementById('subs-card');
      if (sc && S.boots[brand] && !noSubs(brand)) { clear(sc); sc.append(subsCard(ex, x)); }
      SubCancel.paint();
    }
    function apply(id, brand, r) {
      if (!S.tk || S.tk.id !== id) return;
      S.tk.extras = Object.assign({}, S.tk.extras || {}, r.extras || {});
      if (!r.linked) delete S.tk.extras.linked;
      const ord = (r.linked && r.linked.orders || [])[0];
      if (ord && !S.tk.ticket.order_no) S.tk.ticket.order_no = ord;
      repaint(brand);
    }
    /** The input + button. done(r) runs after a successful link (the cancel dialog reopens its check). */
    function form(x, brand, done) {
      const inp = h('input', { type: 'text', dir: 'ltr', class: 'lk-in', maxlength: '100', autocomplete: 'off', placeholder: t('lk_ph'), 'aria-label': t('lk_ph'), 'data-test': 'lk-in' });
      const go = h('button', { class: 'btn small', type: 'button', text: t('lk_go'), 'data-test': 'lk-go' });
      const out = h('div', { 'aria-live': 'polite' });
      let busy = false;
      async function run() {
        const q = inp.value.trim();
        if (busy || q.length < 3) { inp.focus(); return; }
        busy = true; go.disabled = true; go.textContent = t('lk_working');
        clear(out);
        const r = await engine('apiLinkCustomer', { id: x.id, q: q }, brand);
        busy = false; go.disabled = false; go.textContent = t('lk_go');
        if (!r.ok) { out.append(h('div', { class: 'err-box', role: 'alert', 'data-test': 'lk-err', text: r.msg || r.error })); return; }
        toast(t('lk_done'));
        apply(x.id, brand, r);
        if (done) done(r);
      }
      go.addEventListener('click', run);
      inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); run(); } });
      return h('div', { class: 'lk-form', 'data-test': 'lk-form' }, h('div', { class: 'lk-row' }, inp, go), out);
    }
    /** The line at the bottom of the orders panel: the link that is set, or the way to set one. */
    function row(ex, x) {
      const brand = (S.tk && S.tk.brand) || S.brand;
      const l = ex && ex.linked && typeof ex.linked === 'object' && ex.linked.email ? ex.linked : null;
      if (l) {
        const un = canWork() ? h('button', { class: 'btn ghost small', type: 'button', text: t('lk_unlink'), 'data-test': 'lk-unlink', onclick: async function () {
          un.disabled = true;
          const r = await engine('apiLinkCustomer', { id: x.id, unlink: true }, brand);
          if (!r.ok) { un.disabled = false; toast(r.msg || r.error); return; }
          apply(x.id, brand, r);
        } }) : null;
        return h('div', { class: 'lk-box', 'data-test': 'lk-box' }, h('b', null, t('lk_ok', { email: '' }), h('bdi', { class: 'ltr', text: l.email })),
          l.orders && l.orders.length ? h('div', { class: 'small', text: t('lk_orders', { o: l.orders.join(', ') }) }) : null,
          h('div', { class: 'small muted', text: t('lk_by', { by: l.by || '', t: whenShort(l.at) }) }), un);
      }
      if (!canWork()) return null;
      const notes = (ex && ex.notes) || {};
      const lost = !(ex && ex.orders && ex.orders.length) || notes.subscriptions === 'not_checked_no_email';
      if (lost) return h('div', { class: 'lk-open', 'data-test': 'lk-open' }, h('div', { class: 'small muted', text: t('lk_hint') }), form(x, brand, null));
      return h('details', { class: 'lk-more', 'data-test': 'lk-more' }, h('summary', { class: 'small', text: t('lk_other') }), form(x, brand, null));
    }
    return { form: form, row: row };
  })();

  // ---- "לבטל את המנוי" in the send area (the owner's CS team, 2026-10-16: "כפתור במערכת שמאשר שבאמת יבוטל המנוי").
  // One click + ONE confirm step that names the customer and the product; several subscriptions = the agent picks (never a guess). No typed
  // digits: the engine runs the full cancel gate and then reads the contract back from Kaching. The verdict is kept on the ticket
  // (`cancelled` + extras.subCancel), so every agent and device sees "✅ ... אומת בקאצ'ינג HH:MM" or the red failure.
  const SubCancel = (function () {
    // A light mirror of Safety.gs draftClaimsCancel_: it only decides whether the button SHOWS. The engine decides whether it may run.
    const CLAIM_RE = /(?<!לא\s)(?:ביטל|הפסק)(?:תי|נו)\s+(?:לך\s+|עבורך\s+)?(?:כבר\s+)?(?:את\s+)?(?:ה)?מי?נוי|(?:ה)?מי?נוי\s+(?:שלך\s+)?(?:כבר\s+)?(?:בוטל|מבוטל|הופסק)|\b(?:I|we)(?:'ve|\s+have)?\s+(?:already\s+|successfully\s+)?cancel(?:l)?ed\b[^.!?\n]{0,50}\b(?:subscription|membership)|\bsubscription\s+(?:has\s+been|was|is\s+now|is)\s+(?:already\s+)?cancel(?:l)?ed/i;
    let busy = false;
    function slot() { return h('div', { id: 'tk-subcancel', class: 'subx', 'data-test': 'subx' }); }
    function liveDraft() {
      const s = document.getElementById('tk-subcancel');
      const card = s && s.closest('.card');
      const ta = card && card.querySelector('textarea');
      return ta ? ta.value : '';
    }
    function asked(x, draft) {
      return /^cancel:/i.test(String(x.action || '')) || String(x.category || '') === 'cancel_subscription'
        || CLAIM_RE.test(String(x.draft_text || '')) || CLAIM_RE.test(String(draft || ''));
    }
    function itemsText(items) { return (items || []).map(function (l) { return (l.quantity > 1 ? l.quantity + ' × ' : '') + l.title; }).join(', '); }
    function failBox(msg, raw) {
      return h('div', { class: 'err-box', role: 'alert', 'data-test': 'subx-fail' }, h('b', { text: t('sx_fail') }),
        msg ? h('div', { text: msg }) : null, raw && raw !== msg ? h('bdi', { class: 'raw', text: raw }) : null, h('div', { text: t('sx_manual') }));
    }
    function paint() {
      const el = document.getElementById('tk-subcancel');
      if (!el || !S.tk || !S.tk.ticket) return;
      const x = S.tk.ticket, ex = S.tk.extras || {}, brand = S.tk.brand || S.brand;
      const b = S.boots[brand];
      clear(el);
      if (!b || noSubs(brand)) return;                          // not known yet, or a brand without subscriptions (selera): nothing at all
      const done = String(x.cancelled || '').split(',').filter(Boolean);
      const rec = ex.subCancel && typeof ex.subCancel === 'object' ? ex.subCancel : null;
      if (rec && rec.state === 'cancelled' && done.indexOf(rec.contractId) >= 0) {
        el.append(h('div', { class: 'ok-box', role: 'status', 'data-test': 'subx-ok' }, h('b', { text: t('sx_ok', { t: whenShort(rec.at) }) }),
          rec.items && rec.items.length ? h('div', { class: 'small', dir: 'auto', text: itemsText(rec.items) }) : null));
        return;
      }
      if (done.length) { el.append(h('div', { class: 'ok-box', role: 'status', 'data-test': 'subx-ok' }, h('b', { text: t('sx_ok_old') }))); return; }
      if (rec && rec.state === 'failed') el.append(failBox(rec.reasonMsg || '', rec.reason));
      if (!canWork() || !asked(x, liveDraft())) return;
      const why = b.kachingReady === false ? t('sx_off_token') : b.cancelFrozen ? t('sx_off_frozen') : b.cancelEnabled === false ? t('sx_off_writes') : '';
      el.append(h('div', { class: 'actions subx-row' },
        h('button', { class: 'btn danger-outline', type: 'button', 'data-test': 'subx-btn', text: t('sx_btn'), disabled: !!why || busy, onclick: open }),
        why ? h('span', { class: 'muted small', 'data-test': 'subx-why', text: why }) : null));
    }
    function dlgEl() {
      let d = document.getElementById('subx-dlg');
      if (!d) {
        d = h('dialog', { id: 'subx-dlg', class: 'dlg', 'data-test': 'subx-dlg' });
        d.addEventListener('cancel', function (e) { if (busy) e.preventDefault(); });
        document.body.append(d);
      }
      return d;
    }
    function contractLine(c, email) {
      return h('div', { class: 'subx-c' }, h('b', { dir: 'auto', text: itemsText(c.items) || '—' }), ' ', h('span', { class: 'chip', text: t('ss_' + c.status) }),
        h('div', { class: 'small muted' }, t('sub_id') + ': ', h('bdi', { class: 'ltr', text: contractNum(c.id) }), c.every ? ' · ' + everyText(c.every) : '',
          email ? ' · ' : '', email ? h('bdi', { class: 'ltr', text: email }) : null));
    }
    /** Keeps the verdict on this page's copy of the ticket (the engine kept it on the ticket itself). */
    function keep(id, rec, cid) {
      if (!S.tk || S.tk.id !== id) return;
      if (rec) S.tk.extras = Object.assign({}, S.tk.extras || {}, { subCancel: rec });
      if (cid) {
        const done = String(S.tk.ticket.cancelled || '').split(',').filter(Boolean);
        if (done.indexOf(cid) < 0) done.push(cid);
        S.tk.ticket.cancelled = done.join(',');
      }
      paint();
    }
    async function refresh(brand, id) {                         // the subscriptions panel shows the new status too; the draft is untouched
      const fr = await fetchTicket(brand, id, true);
      if (!S.tk || S.tk.id !== id || !fr.ok) return;
      const mine = (S.tk.extras || {}).subCancel;
      S.tk.ticket.cancelled = fr.ticket.cancelled;
      S.tk.extras = Object.assign({}, fr.extras || {});
      if (!S.tk.extras.subCancel && mine) S.tk.extras.subCancel = mine;
      const sc = document.getElementById('subs-card');
      if (sc) { clear(sc); sc.append(subsCard(S.tk.extras, S.tk.ticket)); }
      paint();
    }
    async function open() {
      if (busy || !S.tk || !S.tk.ticket) return;
      const x = S.tk.ticket, brand = S.tk.brand || S.brand, id = x.id;
      const name = x.name || x.email || x.phone || t('no_name');
      const draft = liveDraft();
      const dlg = dlgEl();
      clear(dlg);
      const box = h('div', { class: 'in' });
      const back = h('button', { class: 'btn ghost', type: 'button', text: t('sx_back'), onclick: function () { if (!busy) dlg.close(); } });
      box.append(h('h3', { text: t('sx_btn') }),
        h('div', { class: 'muted', 'data-test': 'subx-loading' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' ', t('sx_checking', { name: name })),
        h('div', { class: 'row-btns' }, back));
      dlg.append(box);
      if (!dlg.open) dlg.showModal();                           // open again after a link: the dialog is already showing
      const pv = await engine('apiSubCancelPreview', { id: id, draft: draft }, brand);
      if (!dlg.open || !S.tk || S.tk.id !== id) return;
      clear(box);
      box.append(h('h3', { text: t('sx_btn') }));
      // 2026-10-20 (order #12057): the customer is not identified -> ask for the order number / email and link it right here
      if (!pv.ok && pv.error === 'no_email') {
        box.append(h('div', { class: 'warn-box', role: 'note', 'data-test': 'subx-noemail', text: t('sx_noemail') }), Link.form(x, brand, open), h('div', { class: 'row-btns' }, back));
        return;
      }
      if (!pv.ok) { box.append(h('div', { class: 'err-box', role: 'alert', 'data-test': 'subx-dlg-err', text: pv.msg || pv.error }), h('div', { class: 'row-btns' }, back)); return; }
      const list = Array.isArray(pv.contracts) ? pv.contracts : [];
      const ended = Array.isArray(pv.ended) ? pv.ended : [];
      // Already cancelled (in Kaching itself, or earlier): say so, verified live now. Never "nothing to cancel", which reads as "not done".
      if (!list.length && ended.length) {
        box.append(h('div', { class: 'ok-box', role: 'status', 'data-test': 'subx-ended' }, h('b', { text: t('sx_ended', { name: name, t: whenShort(pv.checkedAt) }) })),
          h('div', { class: 'subx-ended-list' }, ended.map(function (c) { return contractLine(c, pv.email); })), h('div', { class: 'row-btns' }, back));
        return;
      }
      if (!list.length) {
        box.append(h('div', { 'data-test': 'subx-none', text: t('sx_none', { name: name, email: pv.email || '' }) }), Link.form(x, brand, open), h('div', { class: 'row-btns' }, back));
        return;
      }
      let pick = list.length === 1 ? list[0].id : null;          // one = that one; several = the agent picks
      const go = h('button', { class: 'btn danger', type: 'button', 'data-test': 'subx-go', text: t('sx_go'), disabled: !pick });
      const result = h('div', { 'aria-live': 'assertive' });
      box.append(h('div', { 'data-test': 'subx-q' }, h('b', { text: list.length === 1 ? t('sx_q_one', { name: name }) : t('sx_q_many', { name: name, n: list.length }) })));
      if (list.length === 1) box.append(contractLine(list[0], pv.email));
      else {
        const opts = h('div', { class: 'subx-opts', role: 'radiogroup' });
        list.forEach(function (c) {
          const r = h('input', { type: 'radio', name: 'subx-pick', value: c.id });
          r.addEventListener('change', function () { if (r.checked) { pick = c.id; go.disabled = busy; } });
          opts.append(h('label', { class: 'subx-opt', 'data-test': 'subx-opt' }, r, contractLine(c, '')));
        });
        box.append(opts, pv.email ? h('div', { class: 'small muted' }, h('bdi', { class: 'ltr', text: pv.email })) : null);
      }
      box.append(h('div', { class: 'small muted', text: t('sx_note') }), result, h('div', { class: 'row-btns' }, back, go));
      go.addEventListener('click', async function () {
        if (busy || !pick) return;
        busy = true; go.disabled = true; back.disabled = true; go.textContent = t('sx_working');
        clear(result); paint();
        const r = await engine('apiSubCancel', { id: id, contractId: pick, draft: draft }, brand);
        busy = false; back.disabled = false; go.textContent = t('sx_go');
        const rec = r && r.record && typeof r.record === 'object' ? Object.assign({}, r.record) : null;
        if (rec && !r.verified) rec.reasonMsg = r.msg || '';
        keep(id, rec, r && r.verified === true ? pick : null);
        if (r && r.verified === true) {
          dlg.close();
          toast(t('sx_ok', { t: whenShort(r.at) }));
          refresh(brand, id);
          return;
        }
        go.hidden = true;                                       // a failure is read, not clicked again on reflex
        result.append(failBox(r && r.error === 'write_unknown' ? t('sx_unknown') : (r && (r.msg || r.error)) || '', r && r.message));
      });
    }
    return { slot: slot, paint: paint };
  })();

  const Cancel = (function () {
    const dlg = $('cancel-dlg');
    let busy = false;
    function open(x, s) {
      if (busy) return;
      clear(dlg);
      const wants = /^cancel:/i.test(String(x.action || ''));
      const b = boot() || {};
      const num = contractNum(s.id);
      const brand = tkBrand(x);
      const last4 = String(s.id).slice(-4);              // the gate's own rule (Kaching.gs): the contract id's last 4 digits
      const items = (s.lines || []).map(function (l) { return (l.quantity > 1 ? l.quantity + ' × ' : '') + l.title; }).join(', ');
      const code = h('input', { class: 'code', inputmode: 'numeric', maxlength: '4', autocomplete: 'off', pattern: '[0-9]{4}', 'aria-label': t('dlg_type') });
      const reason = h('textarea', { rows: '3', dir: 'auto', maxlength: '500' });
      const result = h('div', { 'aria-live': 'assertive' });
      const go = h('button', { class: 'btn danger', type: 'button', text: t('dlg_go'), disabled: true });
      const back = h('button', { class: 'btn ghost', type: 'button', text: t('dlg_back') });
      // review 2026-10-11 #9: the button lights only when the gate would accept — the right 4 digits, and a written reason
      // (10+ characters, 2 words) when the customer did not ask to cancel
      function reasonOk() { const v = reason.value.trim(); return v.length >= 10 && v.split(/\s+/).filter(function (w) { return /[\p{L}\p{N}]{2,}/u.test(w); }).length >= 2; }
      function ready() { return code.value === last4 && (wants || reasonOk()); }
      code.addEventListener('input', function () {
        code.value = code.value.replace(/\D/g, '').slice(0, 4);
        code.setAttribute('aria-invalid', code.value.length === 4 && code.value !== last4 ? 'true' : 'false');
        go.disabled = busy || !ready();
      });
      reason.addEventListener('input', function () { go.disabled = busy || !ready(); });
      back.addEventListener('click', function () { if (!busy) dlg.close(); });
      dlg.addEventListener('cancel', function (e) { if (busy) e.preventDefault(); });
      go.addEventListener('click', async function () {
        if (busy || !ready()) return;
        busy = true; go.disabled = true; back.disabled = true; go.textContent = t('dlg_working');
        clear(result);
        const r = await engine('apiKachingCancel', { id: x.id, contractId: s.id, confirm: code.value, reason: reason.value.trim() }, brand);
        busy = false; back.disabled = false; go.textContent = t('dlg_go');
        if (r.ok) {
          dlg.close();
          toast(r.msg || t('ss_CANCELLED'));
          if (S.tk && S.tk.id === x.id) {               // refresh only the panels the cancel changed; the draft is untouched
            const fr = await fetchTicket(brand, x.id, true);
            if (S.tk && S.tk.id === x.id && fr.ok) {
              S.tk.ticket.cancelled = fr.ticket.cancelled;
              S.tk.extras = fr.extras || {};
              const slot = document.getElementById('subs-card');
              if (slot) { clear(slot); slot.append(subsCard(S.tk.extras || {}, S.tk.ticket)); }
            }
          }
          return;
        }
        go.disabled = !ready();
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


  // ---- order edit in Shopify (Owner, 2026-10-16: "שיהיה אפשר לערוך את ההזמנה דרך המערכת"). The engine gate (OrderEdit.gs) re-checks everything; this is the form.
  // Two edits only: the shipping address / name / phone, or the items (quantity, remove, add). Never a payment, a refund or a message to the customer.
  const OrderEdit = (function () {
    const dlg = $('order-dlg');
    const ADDR = ['firstName', 'lastName', 'address1', 'address2', 'city', 'zip', 'phone'];
    let st = null;
    function money(v, cur) {
      if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '—';
      return Number(v).toFixed(2).replace(/\.00$/, '') + ' ' + (cur === 'ILS' || !cur ? '₪' : cur);
    }
    function varName(v) { return (v.product || '—') + (v.title ? ' · ' + v.title : '') + (v.price ? ' (' + money(v.price) + ')' : ''); }
    function lineName(l) { return (l.title || '—') + (l.variantTitle ? ' · ' + l.variantTitle : ''); }
    /** One line saying why the button is off ('' = on). Comes from apiBoot.orderEdits, kept fresh by the feed. */
    function why(brand) {
      const b = S.boots[brand];
      const s = b && b.orderEdits;
      return s === 'on' ? '' : s === 'no_credential' ? t('oe_off_cred') : s === 'frozen' ? t('oe_off_frozen') : t('oe_off');
    }
    /** The button (+ the reason when off) at the bottom of an order that can still change. */
    function row(x, o, brand) {
      if (!canWork() || !o || !o.id || o.cancelledAt || o.fulfillmentStatus !== 'UNFULFILLED') return null;
      const w = why(brand);
      return h('div', { class: 'actions oe-row', 'data-test': 'oe-row' },
        h('button', { class: 'btn small', type: 'button', text: t('oe_btn'), disabled: !!w, 'data-test': 'oe-btn', onclick: function () { open(x, o); } }),
        w ? h('span', { class: 'muted small', 'data-test': 'oe-why', text: w }) : null);
    }
    function refreshOrdersCard(x, order) {
      (async function () {
        if (!(S.tk && S.tk.id === x.id)) return;
        const ex = S.tk.extras || (S.tk.extras = {});
        const mine = (ex.orders || []).filter(function (o) { return o && o.id === order.id; })[0];
        if (mine) mine.items = (order.lines || []).map(function (l) { return { title: l.title, quantity: l.quantity }; });
        const slot = $('orders-card');
        if (slot) { clear(slot); slot.append(ordersCard(ex, S.tk.ticket)); }
        const fr = await fetchTicket(st ? st.brand : S.brand, x.id, true);
        if (S.tk && S.tk.id === x.id && fr.ok) {
          S.tk.extras = fr.extras || S.tk.extras;
          const s2 = $('orders-card');
          if (s2) { clear(s2); s2.append(ordersCard(S.tk.extras || {}, S.tk.ticket)); }
        }
      })();
    }
    function errBox(r) {
      return h('div', { class: 'err-box', role: 'alert', 'data-test': 'oe-err' }, h('div', { text: r.msg || r.error || t('err_bad_engine') }), r.message ? h('bdi', { class: 'raw', text: r.message }) : null);
    }
    async function open(x, o) {
      if (st && st.busy) return;
      st = { x: x, o: o, brand: tkBrand(x), s: null, tab: 'items', step: 'edit', busy: false, variants: null, qty: {}, addId: '', addQty: '1', form: {}, preview: null, pending: null, note: null, err: null };
      clear(dlg);
      dlg.append(h('div', { class: 'in' }, h('h3', { text: t('oe_title') }), h('div', { class: 'muted', text: t('oe_loading') })));
      if (!dlg.open) dlg.showModal();
      const mine = st;
      const r = await engine('apiOrderEditState', { id: x.id, orderId: o.id }, st.brand);
      if (st !== mine) return;
      if (!r.ok) {
        clear(dlg);
        dlg.append(h('div', { class: 'in' }, h('h3', { text: t('oe_title') }), errBox(r.msg ? r : { msg: t('oe_err_load'), error: r.error }),
          h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: t('oe_close'), onclick: function () { dlg.close(); } }))));
        return;
      }
      st.s = r;
      st.tab = !st.s.order.can.items ? 'items' : 'address';
      resetForm();
      render();
    }
    function resetForm() {
      const a = st.s.order.address || {};
      st.form = {};
      ADDR.forEach(function (k) { st.form[k] = a[k] || ''; });
      st.qty = {};
      (st.s.order.lines || []).forEach(function (l) { st.qty[l.id] = String(l.quantity); });
      st.addId = ''; st.addQty = '1';
    }
    async function loadVariants() {
      if (st.variants) return;
      const mine = st;
      const r = await engine('apiKachingVariants', {}, st.brand);
      if (st !== mine) return;
      st.variants = r.ok && Array.isArray(r.variants) ? r.variants : [];
      if (!st.busy && st.step === 'edit' && st.tab === 'items') render();
    }
    function snapshotInputs() {      // what the agent typed survives a repaint (build-rules §1ב)
      if (!st || st.step !== 'edit') return;
      dlg.querySelectorAll('[data-oe-line]').forEach(function (i) { st.qty[i.getAttribute('data-oe-line')] = i.value; });
      dlg.querySelectorAll('[data-oe-field]').forEach(function (i) { st.form[i.getAttribute('data-oe-field')] = i.value; });
      const sel = dlg.querySelector('[data-test=oe-add-sel]'), aq = dlg.querySelector('[data-test=oe-add-qty]');
      if (sel) st.addId = sel.value;
      if (aq) st.addQty = aq.value;
    }
    function btn(text, onclick, cls, test) { return h('button', { class: 'btn small ' + (cls || ''), type: 'button', text: text, disabled: st.busy, 'data-test': test || null, onclick: onclick }); }

    async function preview(kind, payload) {
      st.busy = true; st.err = null; render();
      const args = { id: st.x.id, orderId: st.o.id, kind: kind, mode: 'preview' };
      args[kind === 'items' ? 'ops' : 'address'] = JSON.stringify(payload);
      const mine = st;
      const r = await engine('apiOrderEdit', args, st.brand);
      if (st !== mine) return;
      st.busy = false;
      if (r.ok && r.mode === 'preview') { st.preview = r; st.pending = { kind: kind, payload: payload }; st.step = 'confirm'; } else st.err = r;
      render();
    }
    function nextItems() {
      snapshotInputs();
      const ops = [];
      for (const l of st.s.order.lines) {
        const v = String(st.qty[l.id] === undefined ? l.quantity : st.qty[l.id]).trim();
        if (!/^\d{1,2}$/.test(v) || Number(v) > 20) { st.err = { msg: t('oe_bad_qty') }; render(); return; }
        if (Number(v) !== l.quantity) ops.push({ type: 'qty', lineId: l.id, quantity: Number(v) });
      }
      if (st.addId) {
        if (!/^\d{1,2}$/.test(String(st.addQty).trim()) || Number(st.addQty) < 1 || Number(st.addQty) > 20) { st.err = { msg: t('oe_bad_qty') }; render(); return; }
        ops.push({ type: 'add', variantId: st.addId, quantity: Number(st.addQty) });
      }
      if (!ops.length) { st.err = { msg: t('oe_nochange') }; render(); return; }
      preview('items', ops);
    }
    function nextAddress() {
      snapshotInputs();
      const cur = st.s.order.address || {};
      const diff = {};
      ADDR.forEach(function (k) { const v = String(st.form[k] || '').trim(); if (v !== String(cur[k] || '').trim()) diff[k] = v; });
      if (!Object.keys(diff).length) { st.err = { msg: t('oe_nochange') }; render(); return; }
      preview('address', diff);
    }
    function itemsDiff(p) {
      const key = function (l) { return l.title + '|' + (l.variantTitle || ''); };
      const before = {}, after = {};
      (p.before.lines || []).forEach(function (l) { before[key(l)] = l; });
      (p.after.lines || []).forEach(function (l) { after[key(l)] = l; });
      const out = [];
      Object.keys(before).forEach(function (k) {
        const b = before[k], a = after[k];
        if (!a) out.push(tx('oe_ln_remove', { p: lineName(b) }));
        else if (a.quantity !== b.quantity) out.push(tx('oe_ln_change', { p: lineName(b), a: b.quantity, b: a.quantity }));
      });
      Object.keys(after).forEach(function (k) { if (!before[k]) out.push(tx('oe_ln_add', { p: lineName(after[k]), q: after[k].quantity })); });
      return out;
    }
    function confirmView() {
      const p = st.preview, o = st.s.order, wrap = h('div', { class: 'mg-work', 'data-test': 'oe-confirm' });
      const digits = String(o.name).replace(/\D/g, '');
      const list = h('ul', { class: 'oe-diff', 'data-test': 'oe-summary' });
      let delta = null;
      if (st.pending.kind === 'items') {
        itemsDiff(p).forEach(function (n) { list.append(h('li', { dir: 'auto' }, n)); });
        const d = Number(p.delta);
        delta = h('div', { class: 'oe-delta ' + (d > 0 ? 'up' : d < 0 ? 'down' : ''), 'data-test': 'oe-delta' },
          h('b', null, d > 0 ? tx('oe_delta_up', { d: money(Math.abs(d), p.currency) }) : d < 0 ? tx('oe_delta_down', { d: money(Math.abs(d), p.currency) }) : t('oe_delta_zero')),
          ' · ', tx('oe_total_line', { a: money(p.before.total, p.currency), b: money(p.after.total, p.currency) }),
          d !== 0 ? h('div', { class: 'small muted', text: d > 0 ? t('oe_settle_up') : t('oe_settle_down') }) : null);
      } else {
        (p.changed || []).forEach(function (k) {
          list.append(h('li', { dir: 'auto' }, tx('oe_addr_change', { f: t('oe_f_' + k), a: (p.before && p.before[k]) || '—', b: (p.after && p.after[k]) || '—' })));
        });
      }
      const code = h('input', { class: 'code', inputmode: 'numeric', maxlength: '9', autocomplete: 'off', 'aria-label': t('oe_type', { n: digits }), 'data-test': 'oe-code' });
      const reason = h('textarea', { rows: '2', dir: 'auto', maxlength: '500', 'data-test': 'oe-reason' });
      const result = h('div', { 'aria-live': 'assertive' });
      const blocked = p.needsAdmin === true;
      const go = h('button', { class: 'btn primary', type: 'button', text: t('oe_go'), disabled: true, 'data-test': 'oe-go' });
      const back = btn(t('oe_back'), function () { st.step = 'edit'; st.preview = null; st.err = null; render(); }, 'ghost', 'oe-back');
      code.addEventListener('input', function () {
        code.value = code.value.replace(/\D/g, '').slice(0, 9);
        go.disabled = st.busy || blocked || code.value !== digits;
      });
      go.addEventListener('click', async function () {
        if (st.busy || blocked || code.value !== digits) return;
        st.busy = true; go.disabled = true; back.disabled = true; go.textContent = t('oe_working'); clear(result);
        const args = { id: st.x.id, orderId: st.o.id, kind: st.pending.kind, mode: 'apply', confirm: code.value, reason: reason.value.trim() };
        args[st.pending.kind === 'items' ? 'ops' : 'address'] = JSON.stringify(st.pending.payload);
        if (st.pending.kind === 'items') args.expectDelta = p.delta;
        const mine = st;
        const r = await engine('apiOrderEdit', args, st.brand);
        if (st !== mine) return;
        st.busy = false; back.disabled = false; go.textContent = t('oe_go');
        if (r.ok) {
          if (r.order && r.order.id === st.o.id) { st.s.order = r.order; refreshOrdersCard(st.x, r.order); }
          st.note = r.verified ? t('oe_done') : (r.msg || t('oe_unverified'));
          st.verified = !!r.verified;
          toast(r.verified ? t('oe_done') : (r.msg || t('oe_unverified')));
          st.step = 'edit'; st.preview = null; st.pending = null; st.err = null;
          resetForm(); render();
          return;
        }
        go.disabled = code.value !== digits;
        result.append(errBox(r));
      });
      add(wrap, [h('div', { class: 'mg-summary' }, h('b', { text: t('oe_confirm') })), list, delta,
        h('div', { class: 'small muted', 'data-test': 'oe-money-note', text: t('oe_money_note') }),
        blocked ? h('div', { class: 'problem', role: 'alert', 'data-test': 'oe-admin', text: t('oe_needs_admin') }) : null,
        h('label', null, t('oe_type', { n: digits }), code), h('label', null, t('oe_reason'), reason), result, h('div', { class: 'row-btns' }, back, go)]);   // add() skips null; native append would print "null"
      setTimeout(function () { code.focus(); }, 0);
      return wrap;
    }
    function itemsTab() {
      const o = st.s.order;
      const wrap = h('div', { class: 'mg-work', 'data-test': 'oe-items' });
      o.lines.forEach(function (l) {
        const inp = h('input', { type: 'number', min: '0', max: '20', step: '1', inputmode: 'numeric', class: 'oe-qty', value: st.qty[l.id] === undefined ? String(l.quantity) : st.qty[l.id],
          'data-oe-line': l.id, 'data-test': 'oe-line-qty', 'aria-label': t('oe_qty') + ' ' + lineName(l) });
        wrap.append(h('div', { class: 'mg-row', 'data-test': 'oe-line' }, h('span', null, h('b', { dir: 'auto', text: lineName(l) }), ' · ', money(l.unit, o.currency)), h('label', { class: 'oe-qty-l' }, t('oe_qty'), inp)));
      });
      wrap.append(h('div', { class: 'small muted', text: t('oe_zero') }));
      const sel = h('select', { 'aria-label': t('oe_add'), 'data-test': 'oe-add-sel' }, h('option', { value: '', text: st.variants === null ? t('oe_variants_loading') : t('oe_pick') }),
        (st.variants || []).map(function (v) { return h('option', { value: v.id, text: varName(v) }); }));
      sel.value = st.addId;
      const aq = h('input', { type: 'number', min: '1', max: '20', step: '1', inputmode: 'numeric', class: 'oe-qty', value: st.addQty, 'data-test': 'oe-add-qty', 'aria-label': t('oe_qty') });
      wrap.append(h('div', { class: 'mg-sec' }, h('h4', { text: t('oe_add') }), h('div', { class: 'mg-row' }, sel, aq)));
      wrap.append(h('div', { class: 'row-btns' }, btn(t('oe_next_items'), nextItems, 'primary', 'oe-next')));
      return wrap;
    }
    function addressTab() {
      const wrap = h('div', { class: 'mg-work', 'data-test': 'oe-address' });
      ADDR.forEach(function (k) {
        const inp = h('input', { type: 'text', dir: k === 'phone' || k === 'zip' ? 'ltr' : 'auto', maxlength: '100', value: st.form[k] || '', 'data-oe-field': k, 'data-test': 'oe-f-' + k });
        wrap.append(h('label', null, t('oe_f_' + k), inp));
      });
      wrap.append(h('div', { class: 'row-btns' }, btn(t('oe_next_address'), nextAddress, 'primary', 'oe-next')));
      return wrap;
    }
    function render() {
      if (!st || !st.s) return;
      const o = st.s.order, can = o.can || {}, canMsg = o.canMsg || {};
      const tabs = h('div', { class: 'row-btns start oe-tabs' });
      ['items', 'address'].forEach(function (k) {
        const off = !!can[k];
        const b = h('button', { class: 'btn small ' + (st.tab === k ? 'primary' : 'ghost'), type: 'button', text: t('oe_tab_' + k), disabled: st.busy || st.step !== 'edit' || off, 'aria-pressed': st.tab === k ? 'true' : 'false',
          'data-test': 'oe-tab-' + k, onclick: function () { snapshotInputs(); st.tab = k; st.err = null; render(); } });
        tabs.append(b);
      });
      const offMsg = can.items && can.address ? (canMsg.items || can.items) : null;
      if (st.step === 'edit' && st.tab === 'items') loadVariants();
      clear(dlg);
      dlg.append(h('div', { class: 'in' },
        h('h3', { text: t('oe_title') }),
        h('div', null, h('b', { class: 'ltr' }, o.name), ' ', o.financial ? h('span', { class: 'chip ' + (/PAID/.test(o.financial) && !/REFUND/.test(o.financial) ? 'ok' : ''), text: t('fin_' + o.financial) }) : null,
          ' ', o.fulfillment ? h('span', { class: 'chip outline', text: t('ful_' + o.fulfillment) }) : null),
        h('div', { class: 'small muted' }, t('oe_total') + ': ', h('b', { text: money(o.total, o.currency) }), st.s.status !== 'on' ? [' · ', why(st.brand)] : null),
        st.note ? h('div', { class: st.verified ? 'ok-box' : 'problem', role: 'status', 'data-test': 'oe-note', text: st.note }) : null,
        offMsg ? h('div', { class: 'problem', role: 'alert', 'data-test': 'oe-cannot', text: t('oe_cannot', { why: offMsg }) }) : null,
        st.s.status !== 'on' ? h('div', { class: 'problem', role: 'alert', 'data-test': 'oe-switch', text: why(st.brand) }) : null,
        offMsg ? null : tabs,
        st.err ? errBox(st.err) : null,
        offMsg ? null : st.step === 'confirm' ? confirmView() : (st.tab === 'items' ? itemsTab() : addressTab()),
        st.step === 'edit' ? h('div', { class: 'small muted', text: t('oe_money_note') }) : null,
        st.step === 'edit' ? h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: t('oe_close'), disabled: st.busy, 'data-test': 'oe-close', onclick: function () { dlg.close(); } })) : null));
    }
    dlg.addEventListener('cancel', function (e) { if (st && st.busy) e.preventDefault(); });
    dlg.addEventListener('close', function () { if (st && !st.busy) st = null; });
    return { open: open, row: row, why: why };
  })();

  // ---- manage subscription: every Kaching action (Owner, 2026-10-14). The engine gate re-checks everything; this is the form.
  const Manage = (function () {
    const dlg = $('sub-dlg');
    let st = null;
    const LIVE = ['ACTIVE', 'PAUSED', 'FAILED'];
    function money(v, cur) {
      if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '—';
      return Number(v).toFixed(2).replace(/\.00$/, '') + ' ' + (cur === 'ILS' || !cur ? '₪' : cur);
    }
    function lineName(l) { return (l.title || '—') + (l.variantTitle ? ' · ' + l.variantTitle : ''); }
    function varName(v) { return (v.product || '—') + (v.title ? ' · ' + v.title : '') + (v.price ? ' (' + money(v.price) + ')' : ''); }
    function refreshSubsCard(x) {
      (async function () {
        if (!(S.tk && S.tk.id === x.id)) return;
        const fr = await fetchTicket(st ? st.brand : S.brand, x.id, true);
        if (S.tk && S.tk.id === x.id && fr.ok) {
          S.tk.extras = fr.extras || {};
          const slot = document.getElementById('subs-card');
          if (slot) { clear(slot); slot.append(subsCard(S.tk.extras || {}, S.tk.ticket)); }
        }
      })();
    }
    async function open(x, s) {
      if (st && st.busy) return;
      st = { x: x, s: s, brand: tkBrand(x), c: null, edit: null, busy: false, variants: null, note: null };
      clear(dlg);
      dlg.append(h('div', { class: 'in' }, h('h3', { text: t('mg_title') }), h('div', { class: 'muted', text: t('mg_loading') })));
      if (!dlg.open) dlg.showModal();
      const r = await engine('apiKachingContract', { id: x.id, contractId: s.id }, st.brand);
      if (!st || st.s !== s) return;
      if (!r.ok) {
        clear(dlg);
        dlg.append(h('div', { class: 'in' }, h('h3', { text: t('mg_title') }),
          h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || t('mg_err_load') }), r.error ? h('bdi', { class: 'raw', text: r.error }) : null),
          h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: t('mg_close'), onclick: function () { dlg.close(); } }))));
        return;
      }
      st.c = r.contract; st.writes = r.writes; st.frozen = r.frozen;
      render();
    }
    async function loadVariants() {
      if (st.variants) return;
      const r = await engine('apiKachingVariants', {}, st.brand);
      st.variants = r.ok && Array.isArray(r.variants) ? r.variants : [];
      st.variantsErr = r.ok ? null : (r.msg || r.error);
      render();
    }
    function startEdit(edit) {
      if (!st || st.busy) return;
      st.edit = edit; st.note = null;
      if (edit.kind === 'line' || edit.kind === 'add_line') loadVariants();
      render();
      setTimeout(function () { const w = document.getElementById('mg-work'); if (w) w.scrollIntoView({ block: 'nearest' }); }, 0);
    }
    // the summary is held in ONE element (a fragment empties itself when appended, and render() may run again)
    function confirmOf(action, params, summary) { startEdit({ kind: 'confirm', action: action, params: params || {}, summary: h('span', { dir: 'auto' }, summary) }); }
    function btn(text, onclick, cls) { return h('button', { class: 'btn small ' + (cls || ''), type: 'button', text: text, disabled: st.busy, onclick: onclick }); }

    function workArea() {
      const e = st.edit;
      if (!e) return null;
      const c = st.c;
      const wrap = h('div', { class: 'mg-work', id: 'mg-work' });
      const put = function () { for (let k = 0; k < arguments.length; k++) add(wrap, arguments[k]); };   // add() skips null; native append would print "null"
      const back = btn(t('mg_back'), function () { st.edit = null; render(); }, 'ghost');
      if (e.kind === 'confirm') {
        const last4 = String(c.id).slice(-4);
        const code = h('input', { class: 'code', inputmode: 'numeric', maxlength: '4', autocomplete: 'off', pattern: '[0-9]{4}', 'aria-label': t('mg_type') });
        const reason = h('textarea', { rows: '2', dir: 'auto', maxlength: '500' });
        const result = h('div', { 'aria-live': 'assertive' });
        const go = h('button', { class: 'btn ' + (e.action === 'pause' || e.action === 'remove_line' ? 'danger' : 'primary'), type: 'button', text: t('mg_go'), disabled: true, 'data-test': 'mg-go' });
        code.addEventListener('input', function () {
          code.value = code.value.replace(/\D/g, '').slice(0, 4);
          code.setAttribute('aria-invalid', code.value.length === 4 && code.value !== last4 ? 'true' : 'false');
          go.disabled = st.busy || code.value !== last4;
        });
        go.addEventListener('click', async function () {
          if (st.busy || code.value !== last4) return;
          st.busy = true; go.disabled = true; back.disabled = true; go.textContent = t('mg_working'); clear(result);
          const args = Object.assign({ id: st.x.id, contractId: c.id, action: e.action, confirm: code.value, reason: reason.value.trim() }, e.params);
          const mine = st;
          const r = await engine('apiKachingAction', args, st.brand);
          if (st !== mine) return;
          st.busy = false; back.disabled = false; go.textContent = t('mg_go');
          if (r.ok) {
            if (r.contract && r.contract.id === c.id) st.c = r.contract;
            st.edit = null;
            st.note = r.verified ? null : (r.msg || t('mg_unverified'));
            toast(r.verified ? t('mg_done') : (r.msg || t('mg_unverified')));
            render();
            refreshSubsCard(st.x);
            return;
          }
          go.disabled = code.value !== last4;
          result.append(h('div', { class: 'err-box', role: 'alert' }, h('div', { text: r.msg || r.error }), r.message ? h('bdi', { class: 'raw', text: r.message }) : null));
        });
        const warn = st.frozen ? h('div', { class: 'problem', text: t('mg_frozen') }) : (st.writes === false ? h('div', { class: 'problem', text: t('mg_off') }) : null);
        put(h('div', { class: 'mg-summary' }, h('b', { text: t('mg_confirm') + ' ' }), e.summary), warn,
          h('label', null, t('mg_type'), code), h('label', null, t('mg_reason'), reason), result, h('div', { class: 'row-btns' }, back, go));
        setTimeout(function () { code.focus(); }, 0);
        return wrap;
      }
      if (e.kind === 'reschedule') {
        const tomorrow = new Date(Date.now() + 86400e3).toISOString().slice(0, 10);
        const inp = h('input', { type: 'date', min: tomorrow, value: String(e.cycle.date).slice(0, 10) });
        const next = btn(t('mg_next'), function () {
          const v = inp.value;
          if (!/^\d{4}-\d{2}-\d{2}$/.test(v) || v === String(e.cycle.date).slice(0, 10)) return;
          confirmOf('reschedule', { cycleIndex: String(e.cycle.index), billingDate: v },
            tx('mg_do_reschedule', { n: e.cycle.index, d: fmtDate(e.cycle.date), nd: fmtDate(v + 'T12:00:00Z') }));
        }, 'primary');
        put(h('h4', { text: tx('mg_cycle_n', { n: e.cycle.index }) }), h('label', null, t('mg_new_date'), inp), h('div', { class: 'row-btns' }, back, next));
        return wrap;
      }
      if (e.kind === 'line' || e.kind === 'add_line') {
        const l = e.line;
        const sel = h('select', { 'aria-label': e.kind === 'line' ? t('mg_swap') : t('mg_variant') },
          h('option', { value: '', text: e.kind === 'line' ? t('mg_keep') : t('mg_pick') }),
          (st.variants || []).map(function (v) { return h('option', { value: v.id, text: varName(v) }); }));
        const qty = h('input', { type: 'number', min: '1', max: '20', step: '1', inputmode: 'numeric', value: l ? String(l.quantity) : '1' });
        const price = h('input', { type: 'text', inputmode: 'decimal', dir: 'ltr', placeholder: l && l.price !== null ? String(l.price) : '' });
        const next = btn(t('mg_next'), function () {
          const p = {};
          const what = [];
          const pr = price.value.trim();
          if (pr && !/^\d{1,6}(\.\d{1,2})?$/.test(pr)) { price.setAttribute('aria-invalid', 'true'); return; }
          if (e.kind === 'add_line') {
            const v = (st.variants || []).filter(function (x) { return x.id === sel.value; })[0];
            if (!v) { sel.setAttribute('aria-invalid', 'true'); return; }
            p.variantId = v.id; p.quantity = String(qty.value || '1');
            if (pr) p.price = pr;
            confirmOf('add_line', p, tx('mg_do_add_line', { q: p.quantity, p: varName(v), pr: pr ? ' · ' + money(pr, st.c.currency) : '' }));
            return;
          }
          lineId(p, l);
          if (sel.value) { const v = (st.variants || []).filter(function (x) { return x.id === sel.value; })[0]; p.variantId = sel.value; what.push(t('mg_w_swap', { p: v ? varName(v) : sel.value })); }
          if (String(qty.value) !== String(l.quantity)) { p.quantity = String(qty.value); what.push(t('mg_w_qty', { q: qty.value })); }
          if (pr) { p.price = pr; what.push(t('mg_w_price', { pr: money(pr, st.c.currency) })); }
          if (!what.length) return;
          confirmOf('update_line', p, tx('mg_do_update_line', { p: lineName(l), what: what.join(', ') }));
        }, 'primary');
        put(h('h4', { text: e.kind === 'line' ? lineName(l) : t('mg_add_line') }),
          st.variants === null ? h('div', { class: 'muted small', text: t('mg_variants_loading') }) : null,
          st.variantsErr ? h('div', { class: 'problem', text: st.variantsErr }) : null,
          h('label', null, e.kind === 'line' ? t('mg_swap') : t('mg_variant'), sel),
          h('label', null, t('mg_qty'), qty),
          h('label', null, e.kind === 'line' ? t('mg_price_opt') : t('mg_price_new_opt'), price),
          h('div', { class: 'row-btns' }, back, next));
        return wrap;
      }
      if (e.kind === 'discount') {
        const type = h('select', { 'aria-label': t('mg_dtype') }, h('option', { value: 'PERCENTAGE', text: t('mg_dtype_pct') }), h('option', { value: 'FIXED_AMOUNT', text: t('mg_dtype_fixed') }));
        const val = h('input', { type: 'text', inputmode: 'decimal', dir: 'ltr' });
        const title = h('input', { type: 'text', dir: 'auto', maxlength: '60' });
        const cyc = h('input', { type: 'number', min: '1', max: '60', step: '1', inputmode: 'numeric' });
        const next = btn(t('mg_next'), function () {
          const v = val.value.trim();
          if (!/^\d{1,6}(\.\d{1,2})?$/.test(v)) { val.setAttribute('aria-invalid', 'true'); return; }
          if (title.value.trim().length < 2) { title.setAttribute('aria-invalid', 'true'); return; }
          const p = { discountType: type.value, value: v, title: title.value.trim() };
          if (cyc.value) p.recurringCycleLimit = String(cyc.value);
          confirmOf('add_discount', p, tx('mg_do_add_discount', { title: p.title, v: type.value === 'PERCENTAGE' ? v + '%' : money(v, st.c.currency),
            c: p.recurringCycleLimit ? t('mg_dc_n', { n: p.recurringCycleLimit }) : t('mg_dc_forever') }));
        }, 'primary');
        put(h('h4', { text: t('mg_add_discount') }), h('label', null, t('mg_dtype'), type), h('label', null, t('mg_dvalue'), val),
          h('label', null, t('mg_dtitle'), title), h('label', null, t('mg_dcycles'), cyc), h('div', { class: 'row-btns' }, back, next));
        return wrap;
      }
      return null;
    }
    function lineId(p, l) { p.lineId = l.id; }

    function render() {
      if (!st || !st.c) return;
      const c = st.c;
      const live = LIVE.indexOf(c.status) >= 0;
      const editing = !!st.edit;
      const items = (c.lines || []).map(function (l) { return (l.quantity > 1 ? l.quantity + ' × ' : '') + l.title; }).join(', ');
      const top = [];
      if (c.status === 'ACTIVE' || c.status === 'FAILED') top.push(btn(t('mg_pause'), function () { confirmOf('pause', {}, t('mg_do_pause')); }, 'danger-outline'));
      if (c.status === 'PAUSED') top.push(btn(t('mg_resume'), function () { confirmOf('resume', {}, t('mg_do_resume')); }, 'primary'));
      if (['CANCELLED', 'EXPIRED', 'FAILED'].indexOf(c.status) >= 0) top.push(btn(t('mg_reactivate'), function () { confirmOf('reactivate', {}, t('mg_do_reactivate')); }));
      if (live) top.push(btn(t('mg_cancel'), function () { const x = st.x, s = st.s; dlg.close(); st = null; Cancel.open(x, s); }, 'danger-outline'));

      const cycles = h('div', { class: 'mg-sec' }, h('h4', { text: t('mg_cycles') }));
      if (!(c.cycles || []).length) cycles.append(h('div', { class: 'muted small', text: t('mg_no_cycles') }));
      (c.cycles || []).forEach(function (cy) {
        cycles.append(h('div', { class: 'mg-row', 'data-test': 'mg-cycle' },
          h('span', null, tx('mg_cycle_n', { n: cy.index }), ' · ', h('b', { text: fmtDate(cy.date) }), cy.skipped ? h('span', { class: 'chip bad', text: t('mg_skipped') }) : null),
          live && !editing ? h('span', { class: 'mg-btns' },
            cy.skipped ? btn(t('mg_unskip'), function () { confirmOf('unskip', { cycleIndex: String(cy.index) }, tx('mg_do_unskip', { n: cy.index, d: fmtDate(cy.date) })); })
              : btn(t('mg_skip'), function () { confirmOf('skip', { cycleIndex: String(cy.index) }, tx('mg_do_skip', { n: cy.index, d: fmtDate(cy.date) })); }),
            btn(t('mg_resched'), function () { startEdit({ kind: 'reschedule', cycle: cy }); })) : null));
      });

      const lines = h('div', { class: 'mg-sec' }, h('h4', { text: t('mg_lines') }));
      (c.lines || []).forEach(function (l) {
        lines.append(h('div', { class: 'mg-row', 'data-test': 'mg-line' },
          h('span', null, h('b', { dir: 'auto', text: lineName(l) }), ' · ', t('mg_qty') + ' ' + l.quantity, ' · ', money(l.price, c.currency)),
          live && !editing && l.id ? h('span', { class: 'mg-btns' },
            btn(t('mg_change'), function () { startEdit({ kind: 'line', line: l }); }),
            (c.lines || []).length > 1 ? btn(t('mg_remove'), function () { confirmOf('remove_line', { lineId: l.id }, tx('mg_do_remove_line', { p: lineName(l) })); }, 'danger-outline') : null) : null));
      });
      if (live && !editing) lines.append(h('div', { class: 'row-btns start' }, btn(t('mg_add_line'), function () { startEdit({ kind: 'add_line' }); })));

      const disc = h('div', { class: 'mg-sec' }, h('h4', { text: t('mg_discounts') }));
      if (!(c.discounts || []).length) disc.append(h('div', { class: 'muted small', text: t('mg_no_discounts') }));
      (c.discounts || []).forEach(function (d) {
        disc.append(h('div', { class: 'mg-row' }, h('span', null, h('b', { dir: 'auto', text: d.title || '—' }), d.recurringCycleLimit ? ' · ' + t('mg_dc_n', { n: d.recurringCycleLimit }) : '')));
      });
      if (live && !editing) disc.append(h('div', { class: 'row-btns start' }, btn(t('mg_add_discount'), function () { startEdit({ kind: 'discount' }); })));

      clear(dlg);
      dlg.append(h('div', { class: 'in' },
        h('h3', { text: t('mg_title') }),
        h('div', null, h('b', { dir: 'auto', text: items || '—' }), ' ', h('span', { class: 'chip ' + (c.status === 'ACTIVE' ? 'ok' : c.status === 'CANCELLED' ? '' : 'bad'), text: t('ss_' + c.status) })),
        h('div', { class: 'small muted' }, t('sub_id') + ': ', h('bdi', { class: 'ltr', text: contractNum(c.id) }), ' · ', t('sub_every') + ': ' + everyText(c.every),
          st.x.email ? [' · ', h('bdi', { class: 'ltr', text: st.x.email })] : null),
        st.note ? h('div', { class: 'problem', role: 'status', text: st.note }) : null,
        top.length && !editing ? h('div', { class: 'row-btns start' }, top) : null,
        cycles, lines, disc,
        workArea(),
        editing ? null : h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: t('mg_close'), onclick: function () { dlg.close(); } }))));
    }
    dlg.addEventListener('cancel', function (e) { if (st && st.busy) e.preventDefault(); });
    dlg.addEventListener('close', function () { if (st && !st.busy) st = null; });
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
    const brand = tkBrand(x);
    let busy = false;                                    // review 2026-10-11 #6: a double Enter saved the same note twice
    async function addNote() {
      const text = inp.value.trim();
      if (!text || busy) return;
      busy = true; btn.disabled = true;
      clear(err);
      let r;
      try { r = await engine('apiNote', { id: x.id, text: text }, brand); } catch (e) { r = { ok: false, error: String(e && e.message || e) }; }
      finally { busy = false; btn.disabled = false; }
      if (!r.ok) { err.append(h('div', { class: 'err-box', text: r.msg || r.error })); return; }
      if (inp.value.trim() === text) inp.value = '';
      toast(t('note_ok'));
      const fresh = await fetchTicket(brand, x.id, true);
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
        x.order_no ? h('dt', { text: t('order') }) : null,
        x.order_no ? h('dd', { class: 'ltr' }, orderLink(S.tk ? S.tk.brand : S.brand, x.order_no, orderGid(S.tk && S.tk.extras, x.order_no))) : null,
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
  /** FNV-1a (32 bit) of a draft — engine/AgentRedraft.gs redraft1Fp_: the draft the screen shows is the one the engine replaces. */
  function draftFp(s) {
    s = String(s === null || s === undefined ? '' : s);
    let hsh = 2166136261;
    for (let i = 0; i < s.length; i++) { hsh ^= s.charCodeAt(i); hsh = Math.imul(hsh, 16777619) >>> 0; }
    return ('00000000' + hsh.toString(16)).slice(-8);
  }
  function lastCustomerAt(k) {
    const conv = (k && k.extras && k.extras.conversation) || [];
    for (let i = conv.length - 1; i >= 0; i--) if (conv[i] && conv[i].who === 'customer' && typeof conv[i].at === 'string') return conv[i].at.slice(0, 40);
    return '';
  }

  /** "תשובה אחרת" (Owner, 2026-10-14): one row under the draft, on BOTH desks — an optional short wish, the button, and after it "back to the
   *  previous draft". The engine (apiRedraftOne) writes the new draft through every normal check; nothing here is ever sent. */
  const Regen = {
    undo: {},                 // brand|id -> {snap, draft, at, left}: the way back survives a redraw of the card (the 5 s watch redraws an idle ticket)
    row: function (o) {
      const hint = h('input', { type: 'text', class: 'rd-hint', dir: 'auto', maxlength: '200', placeholder: t('rd_ph'), 'aria-label': t('rd_ph'), 'data-test': 'rd-hint' });
      const btn = h('button', { class: 'btn small', type: 'button', text: t('rd_btn'), title: t('rd_title'), 'data-test': 'rd-btn' });
      const msg = h('div', { class: 'rd-msg small', role: 'status', 'aria-live': 'polite', 'data-test': 'rd-msg', hidden: true });
      const wrap = h('div', { class: 'rd', 'data-test': 'rd-row' }, h('div', { class: 'rd-line' }, hint, btn), msg);
      const uk = o.brand + '|' + o.x.id;
      let busy = false, undo = null;
      const kept = Regen.undo[uk];
      if (kept && Date.now() - kept.at < 30 * 60000 && String(o.ticket().draft_text || '') === kept.draft) undo = kept;
      else delete Regen.undo[uk];
      function paint() { wrap.hidden = !o.visible(); btn.disabled = busy || !o.canUse(); hint.disabled = busy; }
      function say(kind, text, withUndo) {
        clear(msg);
        msg.hidden = !text;
        msg.className = 'rd-msg small' + (kind === 'err' ? ' bad' : '');
        msg.setAttribute('data-kind', kind || '');
        if (!text) return;
        msg.append(h('span', { text: text }));
        if (withUndo && undo) msg.append(' ', h('button', { class: 'btn small ghost', type: 'button', text: t('rd_undo'), 'data-test': 'rd-undo', onclick: doUndo }));
      }
      async function go() {
        if (busy || !o.canUse()) return;
        busy = true; btn.textContent = t('rd_busy'); paint(); say('', '');
        const snap = await o.snapshot();
        const tk = o.ticket();
        const r = await engine('apiRedraftOne', { id: o.x.id, hint: hint.value.trim().slice(0, 200), seen: String(tk.handled_at || ''), last: lastCustomerAt(o.k()), base: draftFp(snap.base) }, o.brand);
        busy = false; btn.textContent = t('rd_btn');
        if (!o.alive()) return;
        if (!r.ok) {
          paint(); say('err', r.msg || r.error);
          if (r.error === 'changed_meanwhile') refreshOpen(o.brand, o.x.id);
          return;
        }
        undo = Regen.undo[uk] = { snap: snap, draft: r.draft, at: Date.now(), left: r.left };
        tk.draft_text = r.draft;
        if (typeof r.recommendation === 'string') tk.recommendation = r.recommendation;
        delete S.tkMemo[o.brand + '|' + o.x.id];
        const err = await o.apply(r.draft);
        if (!o.alive()) return;
        hint.value = '';
        paint();
        if (err) say('err', tx('rd_tr_failed', { m: String(err) }).textContent, true);
        else say('ok', t('rd_done') + (typeof r.left === 'number' ? ' · ' + t('rd_left', { n: r.left }) : ''), true);
      }
      async function doUndo() {
        if (!undo || busy) return;
        const u = undo;
        undo = null; delete Regen.undo[uk]; busy = true; paint(); say('', '');
        const tk = o.ticket();
        let r = { ok: false };
        if (String(tk.draft_text || '') === u.draft) {           // the engine still has the new one: swap it back there (for every screen)
          r = await engine('apiRedraftOne', { id: o.x.id, undo: true, seen: String(tk.handled_at || ''), base: draftFp(u.draft) }, o.brand);
        }
        busy = false;
        if (!o.alive()) return;
        if (r.ok) { tk.draft_text = r.draft; delete S.tkMemo[o.brand + '|' + o.x.id]; }
        o.restore(u.snap, r.ok ? r.draft : null);
        paint();
        say('ok', t('rd_undone'));
      }
      btn.addEventListener('click', go);
      hint.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); go(); } });
      paint();
      if (undo) say('ok', t('rd_done') + (typeof undo.left === 'number' ? ' · ' + t('rd_left', { n: undo.left }) : ''), true);
      return { el: wrap, paint: paint };
    }
  };

  // ---------------------------------------------------------------- answer later (snooze)
  /** Owner, 2026-10-14 (from the CS team): "לענות מאוחר יותר" — 30 min / 1 h / 2 h / 17:00. The ticket leaves THIS agent's list only (kept on the
   *  server: snooze.py, so every device of his agrees), comes back to the top when the time is up, or at once when the customer writes again
   *  (more customer messages / a newer WhatsApp message / a new waiting period: the row moved past what it was). Others still see it. */
  const Snooze = (function () {
    let recs = {};                 // brand|id -> {brand, id, until (s), at (s), n, wl, ws}
    let timer = null, skew = 0, v = 0;
    const WORK_TABS = ['ready', 'action', 'health', 'delay', 'failed', 'wa24'];
    function key(b, id) { return b + '|' + id; }
    function nowS() { return Date.now() / 1000 + skew; }
    function voided(r, row) {
      if (!row) return false;
      if ((Number(row.emails_count) || 0) > (Number(r.n) || 0)) return true;
      const wl = ms(row.wa_last_in), wl0 = ms(r.wl);
      if (wl !== null && (wl0 === null || wl > wl0 + 1000)) return true;
      const ws = ms(row.waiting_since);
      return ws !== null && ws > r.at * 1000 + 1000;
    }
    function rec(b, id) { return recs[key(b, id)] || null; }
    function hides(b, row) { const r = row && rec(b, row.id); return !!r && r.until > nowS() && !voided(r, row) && !Outbox.flagged(b, row.id); }
    function back(b, row) { const r = row && rec(b, row.id); return !!r && !r.pending && !hides(b, row); }
    function hhmm(sec) { return new Intl.DateTimeFormat(LANG === 'en' ? 'en-GB' : 'he-IL', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }).format(new Date(sec * 1000)); }
    function eodOk() {                                    // 17:00 Israel at least 15 minutes away (the server decides; this only greys the option)
      const p = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(nowS() * 1000)).split(':');
      return Number(p[0]) * 60 + Number(p[1]) <= 17 * 60 - 15;
    }
    function repaint(force) {                          // force: his own click (the focus may sit in the list, which a plain render respects)
      v++;
      if (!S.brand) return;
      renderTabs(); renderList(!!force);
      if (S.tk && S.tk.ticket) paintTicket(S.tk);
    }
    function schedule() {
      clearTimeout(timer);
      const next = Object.keys(recs).map(function (k) { return recs[k].until; }).filter(function (u) { return u > nowS(); }).sort(function (a, b) { return a - b; })[0];
      if (next) timer = setTimeout(function () { repaint(); schedule(); }, Math.min(2147000000, Math.max(300, (next - nowS()) * 1000 + 300)));
    }
    async function load() {
      if (!canWork()) return;
      const r = await api('/api/snooze', undefined, 'GET', { quiet: true });
      if (!r.ok || !Array.isArray(r.snoozes)) return;
      if (typeof r.now === 'number') skew = r.now - Date.now() / 1000;
      const next = {};
      r.snoozes.forEach(function (x) { if (x && typeof x.brand === 'string' && typeof x.id === 'string' && typeof x.until === 'number') next[key(x.brand, x.id)] = x; });
      Object.keys(recs).forEach(function (k) { if (recs[k].pending) next[k] = recs[k]; });     // a choice on its way to the server stays
      const changedNow = JSON.stringify(next) !== JSON.stringify(recs);
      recs = next;
      schedule();
      if (changedNow) repaint();
    }
    async function set(b, x, kind) {
      const k = key(b, x.id);
      recs[k] = { brand: b, id: x.id, until: nowS() + 1800, at: nowS(), n: Number(x.emails_count) || 0, wl: x.wa_last_in || '', ws: x.waiting_since || '', pending: true };
      repaint();
      goNext(b, x.id);                                   // like a close: off his list, next ticket at once
      const r = await api('/api/' + encodeURIComponent(b) + '/snooze', { id: x.id, kind: kind });
      if (r.ok && r.snooze) { recs[k] = r.snooze; toast(tx('snz_ok', { t: hhmm(r.snooze.until) }).textContent); }
      else { delete recs[k]; toast(tx('snz_failed', { m: r.msg || r.error || '' }).textContent); }
      schedule();
      repaint();
    }
    async function cancel(b, id, quiet) {
      if (!recs[key(b, id)]) return;
      delete recs[key(b, id)];
      if (!quiet) repaint(true); else v++;
      await api('/api/' + encodeURIComponent(b) + '/snooze', { id: id, cancel: true }, 'POST', { quiet: true });
    }
    function rowOf(b, id, fallback) { const bt = S.boots[b]; return ((bt && bt.tickets) || []).filter(function (r) { return r.id === id; })[0] || fallback; }
    /** The ticket head: "answer later" (4 choices) on an open ticket; "snoozed until HH:MM" + "bring back now" on one of his own. */
    function paintTicket(k) {
      const slot = document.getElementById('tk-snooze');
      if (!slot || !k || !k.ticket) return;
      clear(slot);
      const x = k.ticket, b = k.brand;
      if (!canWork() || OPEN.indexOf(x.status) < 0) { slot.hidden = true; return; }
      slot.hidden = false;
      const row = rowOf(b, x.id, x);
      if (back(b, row)) { cancel(b, x.id, true); }         // it came back and he opened it: the snooze is done
      if (hides(b, row)) {
        slot.append(h('span', { class: 'chip outline snz-chip', 'data-test': 'snooze-chip', text: t('snz_until', { t: hhmm(rec(b, x.id).until) }) }), ' ',
          h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'snooze-cancel', text: t('snz_cancel'), onclick: function () { cancel(b, x.id); } }));
        return;
      }
      const menu = h('div', { class: 'snz-menu', role: 'menu', 'data-test': 'snooze-menu', hidden: true });
      [['30m', 'snz_30m'], ['1h', 'snz_1h'], ['2h', 'snz_2h'], ['eod', 'snz_eod']].forEach(function (o) {
        const opt = h('button', { class: 'btn small', type: 'button', role: 'menuitem', 'data-test': 'snooze-opt', 'data-kind': o[0], text: t(o[1]) });
        if (o[0] === 'eod' && !eodOk()) opt.disabled = true;
        opt.addEventListener('click', function () { menu.hidden = true; set(b, row, o[0]); });
        menu.append(opt);
      });
      const btn = h('button', { class: 'btn small ghost snz-btn', type: 'button', 'aria-haspopup': 'menu', 'data-test': 'snooze-btn', title: t('snz_title'), text: '⏰ ' + t('snz_btn') });
      btn.addEventListener('click', function () { menu.hidden = !menu.hidden; });
      slot.append(btn, menu);
    }
    /** His snoozed open tickets of this brand (the small strip under his list). */
    function hidden(b) { const bt = S.boots[b]; return ((bt && bt.tickets) || []).filter(function (x) { return OPEN.indexOf(x.status) >= 0 && hides(b, x); }); }
    function until(b, id) { const r = rec(b, id); return r ? hhmm(r.until) : ''; }
    setInterval(function () { if (!document.hidden && S.me) load(); }, 30000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden && S.me) load(); });
    return { load: load, hides: hides, back: back, set: set, cancel: cancel, paintTicket: paintTicket, hidden: hidden, until: until, WORK_TABS: WORK_TABS,
      ver: function () { return v; } };
  })();

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
          it.state = 'refused'; giveBack(it); toast(tx('ob_toast_refused', { name: it.name }).textContent); changed(it); return;
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
      if (it && it.fn === 'apiSend') release(it);           // a close waiting behind this send: run it, or drop it (2026-10-14)
      save();
      renderTop();
      if (it && it.brand === S.brand) {
        renderList(false);
        if (S.tk && S.tk.id === it.id) { paintBanner(); Draft.refreshSend(); EnDraft.refresh(); }
      }
    }
    // Owner, 2026-10-14 (the close button right after a send / "שליחה וסגירה"): measured live, the close button was usable only 3.7-4.1 s after
    // the send click (the engine's whole answer) while Gmail had the mail after 0.3-0.5 s. A close now waits in the queue behind the send of
    // its ticket and runs the moment the engine accepted that send — never after a refusal, an unsent or an unknown (the ticket then stays,
    // flagged, at the top of the list), never for a reply that was "already answered in Gmail" (nothing of ours went out).
    function release(send) {
      Object.keys(items).forEach(function (r) {
        const c = items[r];
        if (c.state !== 'queued' || c.after !== send.rid) return;
        if (send.state === 'ok' && !(send.reply && send.reply.elsewhere)) {
          c.state = 'flight'; c.tried_at = Date.now();
          setTimeout(function () { if (items[c.rid] === c && c.state === 'flight') { changed(c); run(c); } }, 0);
        } else if (['refused', 'unsent', 'unknown', 'delivery_issue'].indexOf(send.state) >= 0 || send.state === 'ok') {
          c.state = 'dropped'; c.superseded_by = 'send:' + send.state;
          setTimeout(function () { toast(tx('ob_close_dropped', { name: c.name }).textContent); changed(c); }, 0);
        }
      });
    }
    function forTicket(brand, id) {
      let best = null;
      Object.keys(items).forEach(function (r) { const it = items[r]; if (!it.superseded_by && it.brand === brand && it.id === id && (!best || it.at > best.at)) best = it; });
      return best;
    }
    function blocks(brand, id) {
      const it = forTicket(brand, id);
      return !!it && (it.state === 'flight' || it.state === 'checking' || it.state === 'retry' || it.state === 'unknown' || it.state === 'delivery_issue' || it.state === 'queued');
    }
    /** The close button: usable at once after a send (the close queues behind it). Locked only while a close is already on its way, or while
     *  a send's outcome is unknown or its delivery failed (closing then could hide a message that never reached the customer). */
    function closeLocked(brand, id) {
      const it = forTicket(brand, id);
      if (!it) return false;
      if (it.fn === 'apiSend') return it.state === 'unknown' || it.state === 'delivery_issue';
      return it.state === 'queued' || it.state === 'flight' || it.state === 'checking' || it.state === 'retry' || it.state === 'unknown';
    }
    // Owner, 2026-10-14 ("some devices / users don't see all the open chats"): this device's own close used to hide the row for 24 h, so a
    // chat the customer reopened stayed invisible to the agent who closed it (live: 132 of 170 open chats were handled < 24 h earlier).
    // The server's list is the truth: a close hides its row only while it is on its way, plus a short grace for the next poll to catch up.
    const HIDE_OK_MS = 2 * 60000;
    function hidesRow(brand, id, row) {
      const it = forTicket(brand, id);
      if (!it || it.fn === 'apiSend') return false;
      if (row && (ms(row.waiting_since) || 0) > it.at) return false;           // the customer wrote after the click: an open chat again
      if (it.state === 'queued' || it.state === 'flight' || it.state === 'checking') return true;
      return it.state === 'ok' && typeof it.ok_at === 'number' && Date.now() - it.ok_at < HIDE_OK_MS;
    }
    function flagged(brand, id) {
      const it = forTicket(brand, id);
      return !!it && (it.state === 'refused' || it.state === 'unknown' || it.state === 'unsent' || it.state === 'delivery_issue');
    }
    function label(it) {
      if (!it) return '';
      const close = it.fn !== 'apiSend';
      if (it.state === 'queued') return t('ob_queued_close');
      if (it.state === 'flight') return close ? t('ob_flight_close') : t('ob_flight_send');
      if (it.state === 'checking') return t('ob_checking');
      if (it.state === 'retry') return close ? t('ob_retry_close') : t('ob_retry');
      if (it.state === 'delivery_issue') return t(it.delivery_state === 'unknown' ? 'wa_fail_unknown_note' : it.delivery_state === 'template_required' ? 'wa_fail_tpl' : 'wa_fail');
      if (it.state === 'ok' && it.reply && it.reply.elsewhere) return t('ob_elsewhere');
      if (it.state === 'ok') return close ? t('ob_ok_close') : it.reply && it.reply.queued ? t('ob_ok_queued') : it.channel === 'whatsapp' ? t('ob_ok_wa') : t('ob_ok_email');
      if (it.state === 'refused' && it.err && it.err.error === 'changed_meanwhile') return t(it.err.status === 'done' ? 'cm_closed' : 'cm_answered', { who: whoName(it.err.by), when: whenShort(it.err.at) });
      if (it.state === 'refused') return close ? t('ob_refused_close') : t('ob_refused');
      if (it.state === 'unsent') return t('ob_unsent');
      return t('ob_unknown');
    }
    function cls(it) {
      return it.state === 'ok' ? 'ok' : (it.state === 'flight' || it.state === 'checking' || it.state === 'retry' || it.state === 'queued') ? 'st-sent' : 'bad';
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
        it.state = 'ok'; it.ok_at = Date.now(); it.reply = { queued: !!r.queued, already: !!r.already }; it.msg = null; delete it.delivery_state;
        patchRow(it);
        if (it.fn === 'apiSend') {
          // the device copy goes only if it still IS what was sent: the agent may already be writing the next message (2026-10-11)
          try {
            const k1 = 'cs.draft.' + it.brand + '.' + it.id, v1 = JSON.parse(localStorage.getItem(k1) || 'null');
            if (v1 && it.args && v1.text === it.args.text) localStorage.removeItem(k1);
            const k2 = 'cs.draft.en.' + it.brand + '.' + it.id;
            if (it.src !== undefined && localStorage.getItem(k2) === it.src) localStorage.removeItem(k2);
          } catch (e) { /* ignore */ }
        }
        if (typeof r.handled_at === 'string' && S.tk && S.tk.brand === it.brand && S.tk.id === it.id && S.tk.ticket) {
          // the next message from this screen carries exactly the engine's value as `seen`
          S.tk.ticket.handled_at = r.handled_at; S.tk.ticket.handled_by = S.me.user.username;
        }
        if (it.fn === 'apiSend' && r.queued && !r.already && S.tk && S.tk.brand === it.brand && S.tk.id === it.id && S.tk.ticket) {
          // WhatsApp: ONE message on its way per chat. Until the engine's copy arrives, this copy says so too (else Send would light up
          // and the next message be refused as wa_send_in_flight) — the same patch the server's cache makes.
          S.tk.ticket.wa_send = 'pending'; S.tk.ticket.status = 'wa_queued';
        }
        toast(tx(it.fn !== 'apiSend' ? 'ob_toast_closed' : r.queued ? 'ob_toast_queued' : 'ob_toast_ok', { name: it.name }).textContent);
        if (it.fn === 'apiSend' && r.after && typeof r.after === 'object') {
          const codes = Array.isArray(r.after.reminders) ? r.after.reminders.filter(function (c) { return typeof c === 'string' && /^[a-z_]{3,30}$/.test(c); }) : [];
          if (codes.length) { AfterSend.add({ brand: it.brand, id: it.id, name: it.name || '', codes: codes, at: Date.now() }); renderBanners(); }
          else if (r.after.cancelled) toast(t('afs_cancelled', { name: it.name || '' }));
        }
      } else if (r && r.error === 'replied_elsewhere' && r.closed === true && it.fn === 'apiSend') {
        // Owner, 2026-10-09 (option A): the customer already got an answer straight from Gmail. Nothing was sent, the engine closed the ticket as
        // answered: not a failure, nothing to fix. The agent's text goes back to the box (it was not sent).
        it.state = 'ok'; it.reply = { elsewhere: true }; it.msg = r.msg || null; delete it.delivery_state;
        giveBack(it);
        patchRow(it);
        toast(tx('ob_toast_elsewhere', { name: it.name }).textContent);
      } else if (r && (r.error === 'network' || r.error === 'server_restarted' || r.error === 'bad_response')) {
        // the connection dropped (a reload, a restart): the server is most likely still finishing it — ask it soon
        it.state = 'checking'; it.msg = null;
        later(it, 1000);                                 // 2026-10-14: was 4 s — asking early is only a lookup (never a resend)
      } else if (r && (r.refresh || r.error === 'write_unknown')) {
        it.state = 'unknown'; it.msg = r.msg || null;
        toast(tx('ob_toast_unknown', { name: it.name }).textContent);
        later(it, 20000);                                // ask the server again in a moment
      } else if (r && RETRY_CODES.indexOf(r.error) >= 0 && again(it, r)) {
        // scheduled, quietly: the agent has nothing to do
      } else {
        it.state = 'refused'; it.msg = (r && (r.msg || r.error)) || null; it.err = r ? { error: r.error, problem: r.problem, problem_msg: r.problem_msg } : null;
        if (r && r.error === 'changed_meanwhile') {
          // Owner, 2026-10-11 (two agents on one ticket): say who and when, show their answer, keep this agent's text for "send anyway"
          it.err.by = typeof r.by === 'string' ? r.by.slice(0, 60) : ''; it.err.at = typeof r.at === 'string' ? r.at.slice(0, 40) : ''; it.err.status = typeof r.status === 'string' ? r.status : '';
          it.msg = null;
          refreshOpen(it.brand, it.id);
        }
        giveBack(it);
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
      if (it.state === 'checking' && age < 150000) { later(it, age < 20000 ? 2000 : 6000); return; }         // the server may still be working on it
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
      // a follow-up's ticket is never "open": nothing went out when nothing was handled after the `seen` it carried
      const noNews = !!(it.args && it.args.followup && typeof it.args.seen === 'string' && (ms(tk.handled_at) || 0) <= (ms(it.args.seen) || 0));
      if (Date.now() - (it.tried_at || it.at) > 90000 && (OPEN.indexOf(tk.status) >= 0 || noNews)) {
        // the engine says nothing went out: send it again by ourselves, and only after the last try hand it to the agent
        if (!again(it, { error: 'unsent' })) { it.state = 'unsent'; it.msg = null; giveBack(it); }
        changed(it);
      }
    }
    /** A send that did not go out: its text goes back to the box (or the device copy), and its "on its way" bubble leaves the conversation. */
    function giveBack(it) {
      if (!it || it.fn !== 'apiSend' || !it.args) return;
      const k = it.brand + '|' + it.id;
      if (OUTGOING[k]) { OUTGOING[k] = OUTGOING[k].filter(function (o) { return o.rid !== it.rid; }); if (!OUTGOING[k].length) delete OUTGOING[k]; }
      if (it.src !== undefined) EnDraft.giveBack(it.brand, it.id, it.src); else Draft.giveBack(it.brand, it.id, it.args.text);
      if (S.tk && S.tk.brand === it.brand && S.tk.id === it.id) repaintConv(S.tk);
    }
    /** The newest send of this ticket was refused because someone else answered meanwhile (and nothing newer went out). */
    function lastChange(brand, id) {
      const it = forTicket(brand, id);
      return it && it.fn === 'apiSend' && it.state === 'refused' && it.err && it.err.error === 'changed_meanwhile' ? it : null;
    }
    function start(fn, brand, x, args, via, src) {
      const prev = forTicket(brand, x.id);
      if ((fn === 'apiClose' || fn === 'apiMarkHandled') && prev && prev.fn === 'apiSend' && (prev.state === 'flight' || prev.state === 'checking' || prev.state === 'retry')) {
        // behind the send of this ticket: runs once the engine accepted it (release), never on its own
        const q = { rid: newRid(), brand: brand, id: x.id, fn: fn, args: args, channel: isWA(x) ? 'whatsapp' : 'email',
          name: x.name || x.email || x.phone || x.id, state: 'queued', at: Date.now(), via: via || null, after: prev.rid };
        items[q.rid] = q;
        changed(q);
        return q;
      }
      if (prev && (prev.state === 'flight' || prev.state === 'checking' || prev.state === 'retry' || prev.state === 'unknown' || prev.state === 'delivery_issue' || prev.state === 'queued')) { toast(t('ob_inflight_lock')); return null; }
      const it = { rid: newRid(), brand: brand, id: x.id, fn: fn, args: args, channel: isWA(x) ? 'whatsapp' : 'email',
        name: x.name || x.email || x.phone || x.id, state: 'flight', at: Date.now(), via: via || null };
      if (typeof src === 'string') it.src = src;          // the English desk's own text (local only, never sent): given back on a refusal
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
    function dismiss(it) {
      clearTimeout(timers[it.rid]); delete timers[it.rid]; delete items[it.rid];
      // a close waiting behind this send goes with it: the agent stopped the send, so nothing may close the ticket blindly (Codex 2026-10-14)
      Object.keys(items).forEach(function (r) { const q = items[r]; if (q.state === 'queued' && q.after === it.rid) { q.state = 'dropped'; q.superseded_by = 'send:dismissed'; } });
      changed(it);
    }
    function paintBanner() {
      const slot = document.getElementById('tk-outbox');
      if (!slot || !S.tk) return;
      clear(slot);
      const it = forTicket(S.tk.brand, S.tk.id);
      if (!it || (it.state === 'ok' && Date.now() - it.at > 15 * 60000)) return;
      const box = h('div', { class: 'outbox-banner ' + cls(it), role: 'status', 'data-test': 'outbox-banner', 'data-state': it.state }, h('b', { text: label(it) }));
      if (it.msg && it.state !== 'ok') box.append(h('div', { class: 'small' }, t('ob_why') + ' ', h('span', { dir: 'auto', text: it.msg })));
      if (it.state === 'refused' && it.err && it.err.error === 'changed_meanwhile') { box.setAttribute('data-reason', 'changed_meanwhile'); box.append(h('div', { class: 'small', 'data-test': 'cm-kept', text: t('cm_kept') })); }
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
        if (it.state === 'flight') { it.state = 'checking'; later(it, 500); }     // the page died mid-send: ask, never resend
        else if (it.state === 'checking' || it.state === 'unknown') later(it, 500);
        else if (it.state === 'retry') arm(it, Math.max(1500, (it.next || 0) - Date.now()));   // the page closed between tries: go on
      });
      // a close that waited behind a send when the page closed: decided by that send now (its send gone = never closed blindly)
      Object.keys(items).forEach(function (r) { const q = items[r]; if (q.state === 'queued' && !items[q.after]) { q.state = 'dropped'; q.superseded_by = 'send:gone'; } });
      Object.keys(items).forEach(function (r) { if (items[r].fn === 'apiSend') release(items[r]); });
      save();
      setTimeout(recoverFailures, 2000);
    }
    return { start: start, forTicket: forTicket, blocks: blocks, closeLocked: closeLocked, hidesRow: hidesRow, flagged: flagged, label: label, cls: cls, lastChange: lastChange,
      list: list, pending: pending, reconcile: reconcile, paintBanner: paintBanner, boot: boot, ver: function () { return ver; } };
  })();

  /** After a hand-off: the next ticket of the current tab (or the list), within a frame. */
  function goNext(brand, fromId) {
    if (brand !== S.brand) return;
    const tab = ['ready', 'action', 'failed', 'wa24', 'health', 'delay', 'bot'].indexOf(S.tab) >= 0 ? S.tab : null;
    // Owner, 2026-10-15 ("like Dondy"): the ticket directly ABOVE in the list he is looking at (tab, channel filter, order, the 30+ day section too),
    // so the old ones at the bottom are answered one after another. Before: the next one BELOW among the fresh ones only — from the 30+ day
    // section that was "the first of the list", the top. The place is the one at the click: this ticket is kept in the order although it is
    // already hidden; when it left the data meanwhile, the list as he last saw it. A neighbour gone meanwhile -> further up; nothing above -> below.
    let ids = tab ? (shownRows(tab, fromId) || []).map(function (x) { return x.id; }) : [];
    if (ids.indexOf(fromId) < 0) {
      [S.listShown, S.listShownPrev, S.listOfOpen].some(function (o) { if (o && o.brand === brand && o.tab === tab && o.ids.indexOf(fromId) >= 0) { ids = o.ids; return true; } return false; });
    }
    const avail = {};
    (tab ? shownRows(tab) || [] : []).forEach(function (x) { if (x.id !== fromId && !Outbox.blocks(brand, x.id)) avail[x.id] = true; });
    const i = ids.indexOf(fromId);
    let next = null;
    for (let j = i - 1; i >= 0 && j >= 0 && !next; j--) if (avail[ids[j]]) next = ids[j];
    for (let j = i + 1; i >= 0 && j < ids.length && !next; j++) if (avail[ids[j]]) next = ids[j];
    if (!next) next = Object.keys(avail).length ? (shownRows(tab) || []).filter(function (x) { return avail[x.id]; }).map(function (x) { return x.id; })[0] : null;
    if (next) { go(ticketHash(next)); return; }
    // review 2026-10-11 #3: on a wide screen the list keeps the ticket pane, and its send button lit up again once the reply
    // landed. The handed-off ticket leaves the screen with it.
    if (S.ticketId === fromId) { Draft.detach(); S.ticketId = null; S.tk = null; }
    const lh = listHash(tab || 'ready');
    if (location.hash === lh) { if (!S.ticketId) renderTicketPlaceholder(); renderList(true); } else go(lh);
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
        if (Date.now() < (S.arTrPause || 0)) return;      // refused a moment ago: no storm of retries, the cards stay in the original
        const r = await api('/api/' + encodeURIComponent(S.brand) + '/translate-autoreply', { id: it.id }, 'POST', { quiet: true });
        if (!r.ok) { if (r.error === 'rate_limited') S.arTrPause = Date.now() + Math.max(1, Number(r.wait) || 1) * 60000; return; }
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
  // ---------------------------------------------------------------- AI notes (Owner, 2026-10-11)
  /** "A section in the managers' dashboard where a manager can improve the AI and give notes — general or per brand."
   *  Every brand engine keeps its own list (engine AiNotes.gs). A general note is written to EVERY connected brand with ONE id made here,
   *  so a repeat is a no-op and the list de-dupes by id. Every fan-out reports per brand — never "saved" when a brand failed.
   *  The card is built once; only its list and status repaint, so the textarea is never rebuilt under the manager's fingers. */
  const AiNotes = (function () {
    const MAX = 600;
    const st = { lists: {}, errs: {}, loaded: false, seq: 0, busy: false, pending: null, status: null, checking: {}, tried: {}, uploading: {}, upErr: {}, file: null, replace: null };
    // Mirror of the engine's AI_NOTE_DOC_RE (AiNotes.gs): only for the hint under the text box. The engine's answer (note.status) decides.
    const DOC_RE = /(^|[^A-Za-z])(FDA|MHRA|EMA|CE|ISO|GMP|HACCP|USDA|NSF)([^A-Za-z]|$)|משרד ה?בריאות|מכון ה?תקנים|תו[ -]?ה?תקן|כשרות|בהשגחת|תעוד[הת]|מאושר(?:ת|ים|ות)?\s+(?:ע["״]?י|על[ -]ידי|מטעם|ב)|אישור\s+(?:של\s+|מ|מטעם\s+|ה)?(?:רשות|משרד|מכון|ה?-?FDA)|רישיון\s+יצרן|מוכח(?:ת|ים)?\s+קלינית|נבדק(?:ה|ו)?\s+קלינית|מחקר(?:ים)?\s+קליני|certif|approved\s+by|registered\s+with|clinically\s+(?:proven|tested)/i;
    const FILE_MAX = 10 * 1024 * 1024;
    const FILE_ACCEPT = '.pdf,.jpg,.jpeg,.png,.webp,.doc,.docx';
    let el = null;
    function brands() { return S.me.brands.filter(function (b) { return b.connected; }).map(function (b) { return b.id; }); }
    function newId() {
      const a = new Uint8Array(16);
      crypto.getRandomValues(a);
      return Array.prototype.map.call(a, function (x) { return (x < 16 ? '0' : '') + x.toString(16); }).join('');
    }
    function call(brand, fn, args) { return api('/api/' + encodeURIComponent(brand) + '/' + fn, { args: args, lang: LANG }); }
    /** Runs one call per brand in parallel -> {ok: [brands], bad: [[brand, msg]], rep: {brand: reply}}. "Not found" on a delete is a success. */
    async function fan(targets, fn, args) {
      const res = await Promise.all(targets.map(function (b) { return call(b, fn, args).catch(function () { return null; }); }));
      const out = { ok: [], bad: [], rep: {} };
      res.forEach(function (r, i) {
        out.rep[targets[i]] = r;
        if (r && r.ok) out.ok.push(targets[i]);
        else out.bad.push([targets[i], (r && (r.msg || r.error)) || t('err_bad_engine')]);
      });
      return out;
    }
    function badNames(bad) { return bad.map(function (x) { return brandName(x[0]); }).join(', '); }
    /** The engine's answer to a change that touched the prompt (2026-10-22): `redraft` = how many OPEN AI drafts of that brand are written
     *  again under the change, in the background. A number > 0 is said; 0, null (the queue failed) or absent says nothing. -> {brand: n} */
    function redraftOf(r) {
      const o = {};
      (r.ok || []).forEach(function (b) { const x = r.rep && r.rep[b]; if (x && typeof x.redraft === 'number' && x.redraft > 0) o[b] = x.redraft; });
      return o;
    }
    function setStatus(kind, text, redraft, del) {
      st.status = text || (redraft && Object.keys(redraft).length) ? { kind: kind, text: text || '', redraft: redraft || {}, del: !!del } : null;
      paintStatus();
    }
    /** More drafts are rewritten by a later step of the same action (a document attached after the note): merged into the line shown, max per brand. */
    function addRedraft(redraft) {
      if (!Object.keys(redraft).length) return;
      if (!st.status) st.status = { kind: 'ok', text: '', redraft: {}, del: false };
      Object.keys(redraft).forEach(function (b) { st.status.redraft[b] = Math.max(st.status.redraft[b] || 0, redraft[b]); });
      paintStatus();
    }
    function redraftLines(redraft, del) {
      return Object.keys(redraft || {}).map(function (b) {
        const n = redraft[b];
        const k = (del ? 'ain_redraft_del' : 'ain_redraft') + (n === 1 ? '_1' : '');
        return h('div', { class: 'ain-redraft', 'data-test': 'ai-note-redraft', 'data-brand': b, 'data-n': String(n) }, tx(k, { n: n, b: brandName(b) }));
      });
    }
    async function load() {
      const seq = ++st.seq;
      const bs = brands();
      const res = await Promise.all(bs.map(function (b) { return api('/api/' + encodeURIComponent(b) + '/apiAiNotes', { args: {} }, 'POST', { quiet: true }).catch(function () { return null; }); }));
      if (seq !== st.seq) return;                          // a newer load (after an add / delete) owns the screen
      st.lists = {}; st.errs = {};
      res.forEach(function (r, i) {
        if (r && r.ok && Array.isArray(r.notes)) st.lists[bs[i]] = r.notes.filter(function (n) { return n && typeof n.id === 'string' && typeof n.text === 'string'; });
        else st.errs[bs[i]] = (r && (r.msg || r.error)) || t('err_bad_engine');
      });
      st.loaded = true;
      paintList();
      autoCheck();
    }
    function key(b, id) { return b + '|' + id; }
    function noteOf(b, id) { return (st.lists[b] || []).filter(function (n) { return n.id === id; })[0] || null; }
    /** Every active note without a check is checked once per page load (a new note, a new file, an old note from before the checks). */
    function autoCheck() {
      Object.keys(st.lists).forEach(function (b) {
        st.lists[b].forEach(function (n) {
          if (!n.check && !st.tried[key(b, n.id)]) { st.tried[key(b, n.id)] = true; check(b, n.id); }   // a note waiting for its file gets the reading
        });
      });
    }
    /** The live check of one note in one brand (the engine: a question -> the real draft -> a judge). The note in the list is replaced by the answer. */
    async function check(b, id) {
      st.checking[key(b, id)] = true;
      paintList();
      const r = await call(b, 'apiAiNoteCheck', { id: id }).catch(function () { return null; });
      delete st.checking[key(b, id)];
      if (r && r.ok && r.note) {
        const l = st.lists[b] || [];
        for (let i = 0; i < l.length; i++) if (l[i].id === id) l[i] = r.note;
        paintList();
      } else await load();      // an unclear answer: what the engine stored is the truth
    }
    /** Uploads the document to every brand that holds the note, then attaches it there. Per brand: a failure is shown under the note. */
    async function attachFile(targets, id, file) {
      if (file.size > FILE_MAX) { targets.forEach(function (b) { st.upErr[key(b, id)] = t('ain_file_big'); }); paintList(); return; }
      targets.forEach(function (b) { st.uploading[key(b, id)] = true; delete st.upErr[key(b, id)]; });
      paintList();
      const rd = {};
      await Promise.all(targets.map(async function (b) {
        let r = null;
        try {
          const fd = new FormData();
          fd.append('file', file, file.name);
          fd.append('channel', 'email');
          const res = await fetch('/api/' + encodeURIComponent(b) + '/attach', { method: 'POST', credentials: 'same-origin', body: fd,
            headers: { 'X-CSRF-Token': CSRF, Accept: 'application/json', 'X-UI-Lang': LANG } });
          r = await res.json().catch(function () { return { ok: false, msg: t('err_bad_engine') }; });
          if (r && r.ok === true && /^a[0-9a-f]{24}$/.test(String(r.id || ''))) r = await call(b, 'apiAiNoteAttach', { id: id, file: r.id }).catch(function () { return null; });
        } catch (e) { r = { ok: false, msg: t('err_network') }; }
        delete st.uploading[key(b, id)];
        if (!(r && r.ok)) st.upErr[key(b, id)] = (r && (r.msg || r.error)) || t('err_bad_engine');
        else {
          delete st.tried[key(b, id)];        // a new document: checked again
          if (typeof r.redraft === 'number' && r.redraft > 0) rd[b] = r.redraft;   // the document brought the note into the prompt
        }
      }));
      addRedraft(rd);
      await load();
    }
    /** "Not what I meant": the note's text back in the composer, same scope; the next add replaces it (the old note is deleted after the new one is saved). */
    function edit(n, bs) {
      if (!el) return;
      const ta = el.querySelector('[data-test=ai-note-text]');
      const sel = el.querySelector('[data-test=ai-note-scope]');
      ta.value = n.text;
      sel.value = n.scope === 'all' ? 'all' : bs[0];
      st.replace = { id: n.id, brands: bs.slice() };
      ta.dispatchEvent(new Event('input'));
      setStatus('ok', t('ain_edit_hint'));
      ta.scrollIntoView({ behavior: 'smooth', block: 'center' });
      ta.focus();
    }
    function filePicker(onPick, label) {
      const inp = h('input', { type: 'file', accept: FILE_ACCEPT, hidden: true, 'data-test': 'ai-note-file-input' });
      inp.addEventListener('change', function () { const f = inp.files && inp.files[0]; inp.value = ''; if (f) onPick(f); });
      const btn = h('button', { type: 'button', class: 'btn small', 'data-test': 'ai-note-file-btn', text: label, onclick: function () { inp.click(); } });
      return h('span', { class: 'ain-file-pick' }, btn, inp);
    }
    /** The system's answer under a note: what it needs, that it is checking, or what the check found. per = {brand: note}. */
    function reply(per, id) {
      const bs = Object.keys(per);
      const box = h('div', { class: 'ain-reply', role: 'status', 'data-test': 'ai-note-reply' });
      const errs = bs.filter(function (b) { return st.upErr[key(b, id)]; });
      errs.forEach(function (b) { box.append(h('div', { class: 'ain-r-line bad', 'data-test': 'ai-note-upload-err', text: t('ain_r_up_fail', { b: brandName(b), m: st.upErr[key(b, id)] }) })); });
      if (bs.some(function (b) { return st.uploading[key(b, id)]; })) {
        box.setAttribute('data-state', 'uploading');
        box.append(h('div', { class: 'ain-r-line', text: t('ain_r_uploading') }));
        return box;
      }
      // the system's reading of the note, first: the manager checks he was understood (Owner, 2026-10-18)
      const rd = bs.map(function (b) { return per[b].check && per[b].check.understood; }).filter(Boolean)[0];
      const busy = bs.some(function (b) { return st.checking[key(b, id)] || (!per[b].check && !st.tried[key(b, id)]); });
      const wrong = h('button', { type: 'button', class: 'btn small ghost', 'data-test': 'ai-note-wrong', text: t('ain_r_wrong'), onclick: function () { edit(per[bs[0]], bs); } });
      if (rd) box.append(h('div', { class: 'ain-r-understood', 'data-test': 'ai-note-understood' }, h('b', { text: t('ain_r_understood') + ' ' }), h('span', { dir: 'auto', text: rd })), wrong);
      else if (busy) box.append(h('div', { class: 'ain-r-line', 'data-test': 'ai-note-reading', text: t('ain_r_reading') }));
      const needs = bs.filter(function (b) { return per[b].status === 'needs_file'; });
      if (needs.length) {
        box.setAttribute('data-state', 'needs_file');
        box.append(h('div', { class: 'ain-r-line warn', text: t('ain_r_needs') }), filePicker(function (f) { attachFile(needs, id, f); }, t('ain_r_attach')));
        return box;
      }
      // checking = running now, or about to run (autoCheck); a check whose answer was lost shows as "could not run" with "check again"
      if (busy) {
        box.setAttribute('data-state', 'checking');
        box.append(h('div', { class: 'ain-r-line', text: t('ain_r_checking') }));
        return box;
      }
      const recheck = h('button', { type: 'button', class: 'btn small ghost', 'data-test': 'ai-note-recheck', text: t('ain_r_recheck'),
        onclick: function (e) { e.currentTarget.disabled = true; bs.forEach(function (b) { check(b, id); }); } });
      // 2026-10-22: the check judges the text the customer would get. `gate` = a fixed rule stopped or replaced it: never "checked", even if a judge said yes.
      const no = bs.filter(function (b) { return per[b].check && (per[b].check.follows === false || per[b].check.gate); });
      const err = bs.filter(function (b) { return !per[b].check || per[b].check.err || !('follows' in per[b].check); });
      if (no.length) {
        box.setAttribute('data-state', 'not_following');
        no.forEach(function (b) {
          const c = per[b].check;
          const gate = c.gate ? (typeof c.gate === 'string' && c.gate.trim() ? c.gate : (c.why || '—')) : '';
          box.append(gate ? h('div', { class: 'ain-r-line bad', 'data-test': 'ai-note-gate', dir: 'auto' }, tx('ain_r_gate', { b: brandName(b), gate: gate }))
            : h('div', { class: 'ain-r-line bad', text: t('ain_r_no', { b: brandName(b), why: c.why || '—' }) }));
        });
        box.append(recheck);
        return box;
      }
      if (err.length) {
        box.setAttribute('data-state', 'check_error');
        box.append(h('div', { class: 'ain-r-line warn', text: t('ain_r_err', { b: err.map(brandName).join(', ') }) }), recheck);
        return box;
      }
      const c = per[bs[0]].check;
      box.setAttribute('data-state', 'checked');
      box.append(h('div', { class: 'ain-r-line ok', text: bs.length > 1 ? t('ain_r_ok_n', { n: bs.length, d: fmtDate(c.at, true) }) : t('ain_r_ok', { d: fmtDate(c.at, true) }) }));
      if (c.q) box.append(h('div', { class: 'ain-r-qa small' }, h('b', { text: t('ain_r_q') + ' ' }), h('span', { dir: 'auto', text: c.q })));
      if (c.a) box.append(h('div', { class: 'ain-r-qa small', 'data-test': 'ai-note-answer' }, h('b', { text: t('ain_r_a') + ' ' }), h('span', { dir: 'auto', text: c.a })));
      box.append(recheck);
      return box;
    }
    /** {general: [{note, have: [brands]}], brand: {b: [notes]}} — newest first; a general note is listed once, by id. */
    function grouped() {
      const gen = {}, order = [], per = {};
      Object.keys(st.lists).forEach(function (b) {
        st.lists[b].forEach(function (n) {
          if (n.scope === 'all') {
            if (!gen[n.id]) { gen[n.id] = { note: n, have: [], per: {} }; order.push(n.id); }
            gen[n.id].have.push(b);
            gen[n.id].per[b] = n;
          } else (per[b] = per[b] || []).push(n);
        });
      });
      const byAt = function (a, b) { return (ms(b.at) || 0) - (ms(a.at) || 0); };
      Object.keys(per).forEach(function (b) { per[b].sort(byAt); });
      return { general: order.map(function (id) { return gen[id]; }).sort(function (a, b) { return byAt(a.note, b.note); }), brand: per };
    }
    function delBtn(onFire) {
      const b = armed(t('ain_del'), t('ain_del_arm'), 'small ghost ain-del', onFire);
      b.setAttribute('data-test', 'ai-note-del');
      b.setAttribute('title', t('ain_del_title'));
      b.setAttribute('aria-label', t('ain_del_title'));
      return b;
    }
    function item(n, scopeBrands, extra, per) {
      const li = h('li', { class: 'ain-item', 'data-test': 'ai-note', 'data-id': n.id, 'data-scope': n.scope },
        h('div', { class: 'ain-text', dir: 'auto', text: n.text }),
        n.file ? h('div', { class: 'ain-file small', 'data-test': 'ai-note-file', text: t('ain_r_file', { n: n.file.name }) }) : null,
        h('div', { class: 'ain-meta muted small' }, h('span', null, tx('ain_by', { u: n.by || '—', d: fmtDate(n.at, true) })), extra || null,
          delBtn(async function (btn) {
            btn.disabled = true;
            const r = await fan(scopeBrands, 'apiAiNoteDelete', { id: n.id });
            if (!r.bad.length) setStatus('ok', t('ain_deleted'), redraftOf(r), true);
            else if (r.ok.length) setStatus('bad', t('ain_del_part', { ok: r.ok.length, n: scopeBrands.length, bad: badNames(r.bad) }), redraftOf(r), true);
            else setStatus('bad', t('ain_del_fail', { m: r.bad[0][1] }));
            await load();
          })),
        reply(per, n.id));
      return li;
    }
    // ---------- suggestions from the team's corrections (Owner, 2026-10-22: "the notes don't improve the AI") ----------
    /* The team edits AI drafts ~1,500 times in 12 days and wrote one note; the edits never reached the AI. The engine (AiLearn.gs) logs every
     * edited AI draft at the send, distils repeated corrections into proposed rules, and here a manager approves (as is / edited) or rejects
     * one. An approval IS a brand note (the engine adds it through apiAiNoteAdd), so it then shows in the list below with its reading and check.
     * Its own container and its own repaint: a check result repainting the notes never rebuilds an editor a manager is typing in. */
    const sg = { lists: {}, corr: {}, errs: {}, loaded: false, seq: 0, busy: {}, err: {}, edit: {}, open: {}, status: null };
    const SUGG_ID_RE = /^s[0-9a-f]{16}$/;
    async function loadSugg() {
      const seq = ++sg.seq;
      const bs = brands();
      const res = await Promise.all(bs.map(function (b) { return api('/api/' + encodeURIComponent(b) + '/apiAiNoteSuggestions', { args: {} }, 'POST', { quiet: true }).catch(function () { return null; }); }));
      if (seq !== sg.seq) return;
      sg.lists = {}; sg.corr = {}; sg.errs = {};
      res.forEach(function (r, i) {
        const b = bs[i];
        if (r && r.ok && Array.isArray(r.suggestions)) {
          sg.lists[b] = r.suggestions.filter(function (x) { return x && SUGG_ID_RE.test(String(x.id || '')) && typeof x.text === 'string' && x.text.trim() && (!x.state || x.state === 'pending'); });
          sg.corr[b] = typeof r.corrections === 'number' && r.corrections >= 0 ? r.corrections : 0;
        } else sg.errs[b] = (r && (r.msg || r.error)) || t('err_bad_engine');
      });
      sg.loaded = true;
      paintSugg();
    }
    /** approve (text = the manager's edit, sent only when it differs) or reject. The item leaves the list only on the engine's yes. */
    async function decide(b, s, decision, text) {
      const k = key(b, s.id);
      if (sg.busy[k]) return;
      const args = { id: s.id, decision: decision };
      if (decision === 'approve' && typeof text === 'string') {
        const v = text.trim();
        if (!v || v.length > MAX) return;
        if (v !== s.text.trim()) args.text = v;
      }
      sg.busy[k] = true; delete sg.err[k];
      paintSugg();
      const r = await call(b, 'apiAiNoteSuggestDecide', args).catch(function () { return null; });
      delete sg.busy[k];
      if (!(r && r.ok && r.suggestion)) { sg.err[k] = (r && (r.msg || r.error)) || t('err_bad_engine'); paintSugg(); return; }
      sg.lists[b] = (sg.lists[b] || []).filter(function (x) { return x.id !== s.id; });
      delete sg.edit[k]; delete sg.open[k];
      const rd = {};
      if (typeof r.redraft === 'number' && r.redraft > 0) rd[b] = r.redraft;
      if (r.noop) sg.status = { text: t('ain_s_noop', { b: brandName(b) }), redraft: {} };
      else if (r.suggestion.state === 'approved') sg.status = { text: t('ain_s_added', { b: brandName(b) }), redraft: rd };
      else sg.status = { text: t('ain_s_rejected', { b: brandName(b) }), redraft: {} };
      paintSugg();
      if (r.note && typeof r.note.id === 'string') delete st.tried[key(b, r.note.id)];    // the new note gets its reading and check (autoCheck)
      if (r.suggestion.state === 'approved') await load();
    }
    function suggExample(x) {
      const row = function (label, v) { return h('div', { class: 'ain-s-exrow' }, h('b', { text: label + ' ' }), h('span', { dir: 'auto', text: String(v || '—') })); };
      return h('div', { class: 'ain-s-exitem', 'data-test': 'ai-sugg-example' }, row(t('ain_s_ex_c'), x.customer), row(t('ain_s_ex_ai'), x.ai), row(t('ain_s_ex_sent'), x.sent));
    }
    function suggItem(b, s) {
      const k = key(b, s.id);
      const busy = !!sg.busy[k];
      const li = h('li', { class: 'ain-item ain-s-item', 'data-test': 'ai-sugg', 'data-id': s.id, 'data-brand': b });
      li.append(h('div', { class: 'ain-text', dir: 'auto', 'data-test': 'ai-sugg-text', text: s.text }));
      const meta = h('div', { class: 'ain-meta muted small' });
      if (typeof s.count === 'number' && s.count > 0) meta.append(h('span', { class: 'chip', 'data-test': 'ai-sugg-count', text: t('ain_s_count', { n: s.count }) }));
      if (s.at) meta.append(h('span', { text: fmtDate(s.at, true) }));
      li.append(meta);
      const ex = (Array.isArray(s.examples) ? s.examples : []).filter(function (x) { return x && typeof x === 'object'; }).slice(0, 2);
      if (ex.length) {
        const det = h('details', { class: 'ain-s-ex', open: !!sg.open[k], 'data-test': 'ai-sugg-examples' }, h('summary', { class: 'small', text: t('ain_s_examples', { n: ex.length }) }));
        det.addEventListener('toggle', function () { sg.open[k] = det.open; });
        ex.forEach(function (x) { det.append(suggExample(x)); });
        li.append(det);
      }
      const acts = h('div', { class: 'ain-s-actions' });
      if (sg.edit[k] !== undefined) {
        const ta = h('textarea', { class: 'ain-ta ain-s-ta', rows: 3, maxlength: String(MAX), dir: 'auto', 'data-k': k, 'aria-label': t('ain_s_edit'), 'data-test': 'ai-sugg-edit-text', value: sg.edit[k] });
        const cnt = h('span', { class: 'muted small', text: t('ain_count', { n: sg.edit[k].length }) });
        const save = h('button', { type: 'button', class: 'btn small primary', 'data-test': 'ai-sugg-edit-save', text: busy ? t('ain_s_saving') : t('ain_s_approve') });
        const paintSave = function () { const v = ta.value.trim(); save.disabled = busy || !v || v.length > MAX; cnt.textContent = t('ain_count', { n: ta.value.length }); };
        ta.addEventListener('input', function () { sg.edit[k] = ta.value; paintSave(); });
        save.addEventListener('click', function () { decide(b, s, 'approve', ta.value); });
        paintSave();
        li.append(ta);
        acts.append(save, h('button', { type: 'button', class: 'btn small ghost', 'data-test': 'ai-sugg-edit-cancel', text: t('ain_s_cancel'), disabled: busy,
          onclick: function () { delete sg.edit[k]; paintSugg(); } }), cnt);
      } else {
        acts.append(
          h('button', { type: 'button', class: 'btn small primary', 'data-test': 'ai-sugg-approve', text: busy ? t('ain_s_saving') : t('ain_s_approve'), disabled: busy,
            onclick: function () { decide(b, s, 'approve'); } }),
          h('button', { type: 'button', class: 'btn small', 'data-test': 'ai-sugg-edit', text: t('ain_s_edit'), disabled: busy,
            onclick: function () {
              sg.edit[k] = s.text; paintSugg();
              const nt = el.querySelector('[data-test=ai-sugg-edit-text][data-k="' + k + '"]');
              if (nt) { nt.focus(); nt.setSelectionRange(nt.value.length, nt.value.length); }
            } }));
        const rej = armed(t('ain_s_reject'), t('ain_s_reject_arm'), 'small ghost', function () { decide(b, s, 'reject'); });
        rej.setAttribute('data-test', 'ai-sugg-reject');
        rej.disabled = busy;
        acts.append(rej);
      }
      li.append(acts);
      if (sg.err[k]) li.append(h('div', { class: 'ain-r-line bad', role: 'alert', 'data-test': 'ai-sugg-err', text: t('ain_s_fail', { m: sg.err[k] }) }));
      return li;
    }
    function paintSugg() {
      if (!el) return;
      const box = el.querySelector('[data-test=ai-sugg-section]');
      // a repaint keeps the editor the manager is typing in: its text lives in sg.edit, its focus and caret are put back (build-rules §1ב)
      const ae = document.activeElement;
      const keep = ae && box.contains(ae) && ae.getAttribute('data-k') ? { k: ae.getAttribute('data-k'), a: ae.selectionStart, z: ae.selectionEnd } : null;
      clear(box);
      const total = Object.keys(sg.lists).reduce(function (n, b) { return n + sg.lists[b].length; }, 0);
      box.append(h('h4', { class: 'ain-s-title' }, t('ain_s_title'), total ? h('span', { class: 'n', 'data-test': 'ai-sugg-total', text: String(total) }) : null),
        h('p', { class: 'muted small ain-s-help', text: t('ain_s_help') }));
      if (sg.status) box.append(h('div', { class: 'ain-status small ok', role: 'status', 'data-test': 'ai-sugg-status' }, h('div', { text: sg.status.text }), redraftLines(sg.status.redraft, false)));
      if (!sg.loaded) { box.append(h('div', { class: 'muted small', text: t('ain_s_loading') })); return; }
      Object.keys(sg.errs).forEach(function (b) {
        box.append(h('div', { class: 'muted small ain-s-loaderr', 'data-test': 'ai-sugg-load-err', 'data-brand': b }, t('ain_s_load_err', { b: brandName(b), m: sg.errs[b] }), ' ',
          h('button', { type: 'button', class: 'btn small ghost', text: t('ain_retry'), onclick: function () { loadSugg(); } })));
      });
      const empty = [];
      brands().forEach(function (b) {
        if (sg.errs[b] || !sg.lists[b]) return;
        if (!sg.lists[b].length) { empty.push(b); return; }
        const ul = h('ul', { class: 'ain-list' });
        sg.lists[b].forEach(function (s) { ul.append(suggItem(b, s)); });
        box.append(h('div', { class: 'ain-s-brand', 'data-test': 'ai-sugg-brand', 'data-brand': b }, h('h5', { text: brandName(b) }), ul));
      });
      empty.forEach(function (b) {
        box.append(h('div', { class: 'muted small ain-s-empty', 'data-test': 'ai-sugg-empty', 'data-brand': b }, tx('ain_s_empty', { b: brandName(b), n: sg.corr[b] || 0 })));
      });
      if (keep) {
        const nt = box.querySelector('[data-k="' + keep.k + '"]');
        if (nt) { nt.focus(); try { nt.setSelectionRange(keep.a, keep.z); } catch (e) { /* not a text field */ } }
      }
    }
    function paintList() {
      if (!el) return;
      const list = el.querySelector('[data-test=ai-note-list]');
      clear(list);
      if (!st.loaded) { list.append(h('div', { class: 'muted small', text: t('ain_loading') })); return; }
      Object.keys(st.errs).forEach(function (b) {
        list.append(h('div', { class: 'err-box ain-err', role: 'alert', 'data-test': 'ai-note-load-err', 'data-brand': b }, t('ain_load_err', { b: brandName(b), m: st.errs[b] }), ' ',
          h('button', { type: 'button', class: 'btn small', text: t('ain_retry'), onclick: function () { load(); } })));
      });
      const g = grouped();
      const all = brands();
      const loadedBrands = Object.keys(st.lists);
      let any = false;
      if (g.general.length) {
        any = true;
        const ul = h('ul', { class: 'ain-list' });
        g.general.forEach(function (x) {
          // missing = brands that answered and do NOT have it (a brand that failed to load is unknown, not missing)
          const missing = loadedBrands.filter(function (b) { return x.have.indexOf(b) < 0; });
          const extra = missing.length ? h('span', { class: 'ain-missing' }, h('span', { class: 'chip bad', 'data-test': 'ai-note-missing', text: t('ain_missing', { b: missing.map(brandName).join(', ') }) }), ' ',
            h('button', { type: 'button', class: 'btn small', 'data-test': 'ai-note-fill', text: t('ain_fill'), onclick: async function (e) {
              e.currentTarget.disabled = true;
              const r = await fan(missing, 'apiAiNoteAdd', { id: x.note.id, scope: 'all', text: x.note.text });
              report(r, missing.length, null);
              await load();
            } })) : null;
          ul.append(item(x.note, all, extra, x.per));
        });
        list.append(h('section', { class: 'ain-group', 'data-test': 'ai-group-all' }, h('h4', { text: t('ain_general') }), ul));
      }
      all.forEach(function (b) {
        const ns = g.brand[b];
        if (!ns || !ns.length) return;
        any = true;
        const ul = h('ul', { class: 'ain-list' });
        ns.forEach(function (n) { const per = {}; per[b] = n; ul.append(item(n, [b], null, per)); });
        list.append(h('section', { class: 'ain-group', 'data-test': 'ai-group-brand', 'data-brand': b }, h('h4', null, tx('ain_brand', { b: brandName(b) })), ul));
      });
      if (!any && !Object.keys(st.errs).length) list.append(h('div', { class: 'muted small', 'data-test': 'ai-note-empty', text: t('ain_empty') }));
    }
    function paintStatus() {
      if (!el) return;
      const s0 = el.querySelector('[data-test=ai-note-status]');
      clear(s0);
      if (st.status) {
        if (st.status.text) s0.append(h('div', { text: st.status.text }));
        redraftLines(st.status.redraft, st.status.del).forEach(function (x) { s0.append(x); });   // Element.append(array) would print "[object …]"
      }
      s0.className = 'ain-status small' + (st.status ? (st.status.kind === 'ok' ? ' ok' : ' bad') : '');
      s0.hidden = !st.status;
    }
    /** One line for an add: every brand, one brand, part of them, or none — never "saved" over a failure. */
    function report(r, n, oneBrand) {
      if (!r.bad.length) setStatus('ok', oneBrand ? t('ain_saved_one', { b: brandName(oneBrand) }) : t('ain_saved_all', { n: n }), redraftOf(r));
      else if (r.ok.length) setStatus('bad', t('ain_saved_part', { ok: r.ok.length, n: n, bad: badNames(r.bad) }), redraftOf(r));
      else setStatus('bad', t('ain_save_fail', { m: r.bad[0][1] }));
    }
    function build() {
      const ta = h('textarea', { class: 'ain-ta', rows: 3, maxlength: String(MAX), dir: 'auto', placeholder: t('ain_ph'), 'aria-label': t('ain_title'), 'data-test': 'ai-note-text' });
      const count = h('span', { class: 'muted small ain-count', 'data-test': 'ai-note-count', text: t('ain_count', { n: 0 }) });
      const sel = h('select', { class: 'ain-scope', 'aria-label': t('ain_scope'), 'data-test': 'ai-note-scope' });
      sel.append(h('option', { value: 'all', text: t('ain_all') }));
      brands().forEach(function (b) { sel.append(h('option', { value: b, text: brandName(b) })); });
      const btn = h('button', { type: 'button', class: 'btn primary', 'data-test': 'ai-note-add', text: t('ain_add') });
      const fileChip = h('span', { class: 'ain-file-chosen small', 'data-test': 'ai-note-file-chosen', hidden: true });
      const hint = h('div', { class: 'ain-doc-hint small', 'data-test': 'ai-note-doc-hint', hidden: true, text: t('ain_doc_hint') });
      const paintFile = function () {
        clear(fileChip);
        fileChip.hidden = !st.file;
        if (st.file) fileChip.append(h('span', { text: t('ain_r_file', { n: st.file.name }) }), ' ',
          h('button', { type: 'button', class: 'btn small ghost', 'data-test': 'ai-note-file-clear', text: '✕', title: t('ain_file_clear'), 'aria-label': t('ain_file_clear'),
            onclick: function () { st.file = null; paintFile(); paintBtn(); } }));
      };
      const pick = filePicker(function (f) {
        if (f.size > FILE_MAX) { setStatus('bad', t('ain_file_big')); return; }
        st.file = f; paintFile(); paintBtn();
      }, t('ain_file_btn'));
      const paintBtn = function () {
        const n = ta.value.trim().length;
        hint.hidden = !(DOC_RE.test(ta.value) && !st.file);
        count.textContent = t('ain_count', { n: ta.value.length });
        btn.disabled = st.busy || !n || n > MAX || !brands().length;
        btn.textContent = st.busy ? t('ain_adding') : t('ain_add');
      };
      ta.addEventListener('input', paintBtn);
      sel.addEventListener('change', paintBtn);
      btn.addEventListener('click', async function () {
        const text = ta.value.trim();
        if (st.busy || !text || text.length > MAX) return;
        const scope = sel.value;
        const targets = scope === 'all' ? brands() : [scope];
        // The same text to the same place again reuses its id: a retry after an unclear answer is a no-op in the engine, never a twin.
        const p0 = st.pending;
        const id = p0 && p0.text === text && p0.scope === scope ? p0.id : newId();
        st.pending = { id: id, text: text, scope: scope };
        st.busy = true; paintBtn(); setStatus(null, '');
        let r;
        try { r = await fan(targets, 'apiAiNoteAdd', { id: id, scope: scope === 'all' ? 'all' : 'brand', text: text }); }
        finally { st.busy = false; }
        report(r, targets.length, scope === 'all' ? null : scope);
        const file = st.file;
        const rep = st.replace;
        if (r.ok.length && rep && rep.id !== id) {     // "not what I meant": the old note goes once the new one is saved
          st.replace = null;
          const d = await fan(rep.brands, 'apiAiNoteDelete', { id: rep.id });
          if (!d.bad.length) {
            const rd = redraftOf(r);
            const rd2 = redraftOf(d);
            Object.keys(rd2).forEach(function (b) { rd[b] = Math.max(rd[b] || 0, rd2[b]); });    // one rewrite of the open drafts, under the new note
            setStatus('ok', t('ain_replaced'), rd);
          }
        }
        if (r.ok.length) { st.pending = null; ta.value = ''; st.file = null; paintFile(); }     // saved somewhere: it is in the list now (a part-save offers "complete" there)
        paintBtn();
        if (r.ok.length && file) await attachFile(r.ok, id, file);    // the document goes with the note; its state shows under the note
        else await load();
      });
      const nc = S.me.brands.filter(function (b) { return !b.connected; }).map(function (b) { return brandName(b.id); });
      el = h('div', { class: 'dash-card ain-card', id: 'ai-notes', 'data-test': 'ai-notes' },
        h('h3', { text: t('ain_title') }),
        h('p', { class: 'muted small ain-help', 'data-test': 'ai-notes-help', text: t('ain_help') }),
        ta,
        hint,
        h('div', { class: 'ain-row' }, h('label', { class: 'small' }, t('ain_scope') + ' ', sel), pick, fileChip, count, btn),
        nc.length ? h('div', { class: 'muted small', 'data-test': 'ai-note-not-conn', text: t('ain_not_conn', { b: nc.join(', ') }) }) : null,
        h('div', { class: 'ain-status small', role: 'status', 'aria-live': 'polite', 'data-test': 'ai-note-status', hidden: true }),
        h('section', { class: 'ain-sugg', 'data-test': 'ai-sugg-section' }),
        h('div', { class: 'ain-lists', 'data-test': 'ai-note-list' }));
      paintBtn();
      paintStatus();
      paintSugg();
      paintList();
    }
    function mount(slot) {
      if (!el) build();
      if (el.parentNode !== slot) { clear(slot); slot.append(el); }
      load();
      loadSugg();
    }
    return { mount: mount, load: load };
  })();

  // ---------------------------------------------------------------- managers' dashboard (Owner, 2026-10-06)
  /** Admin + user-manager only (the server answers 403 to anyone else). Work time from the activity log: first to last
   *  action minus breaks over 30 min (Owner, 2026-10-13); "on screen" keeps the old 5-min runs. Being logged in is not work.
   *  Charts are plain SVG (strict CSP, no libraries). */
  // ---------------------------------------------------------------- sales log for bonuses (Owner, 2026-10-14)
  /*
   * The agent presses "מכירה" in a ticket, picks the order that followed the conversation (or types its number); the ENGINE re-reads it from
   * Shopify and verifies it (engine/Sales.gs). The agent is always the logged-in user. Proof = the order + the conversation frozen at that moment.
   * Managers: a table with every sale on the managers' board (#/dash, admins) — filters, the proof, approve / reject, a per-agent bonus summary, and the
   * sales the system found that nobody logged. Strings live here (SL), not in STR: this block is self-contained.
   */
  const SL = {
    he: {
      btn: '💰 מכירה', mine_btn: '💰 המכירות שלי', title: 'רישום מכירה', tab_log: 'רישום מכירה', tab_mine: 'המכירות שלי', close: 'סגירה', cancel: 'ביטול',
      rules: 'ההזמנה נבדקת מול שופיפיי. "מאומת" = אותו לקוח (טלפון או מייל), ההזמנה לא בוטלה, נוצרה אחרי התשובה הראשונה של נציג בשיחה ובתוך {h} שעות מהתשובה האחרונה לפניה. המכירה נרשמת על הנציג שרושם. ההוכחה: ההזמנה עצמה + העתק קפוא של השיחה מרגע הרישום.',
      loading: 'טוענים את ההזמנות של הלקוח…', pick: 'ההזמנות של הלקוח בשופיפיי', none: 'לא נמצאו הזמנות של הלקוח (החנות מראה 60 יום אחורה). אפשר להקליד מספר הזמנה.',
      err_lookup: 'לא הצלחנו לקרוא את ההזמנות מהחנות. אפשר להקליד מספר הזמנה.', no_contact: 'בפנייה אין מייל או טלפון, אז אי אפשר לאתר הזמנות. אפשר להקליד מספר הזמנה (תירשם "לבדיקה").',
      or_type: 'או מספר הזמנה אחר', note: 'הערה (לא חובה)', go: 'רשמו מכירה', busy: 'רושם…',
      after: 'אחרי השיחה', before: 'לפני השיחה', cancelled: 'בוטלה', held: 'כבר רשומה על {a}', mine_held: 'כבר רשמת אותה',
      done_verified: 'המכירה נרשמה ומאומתת', done_review: 'המכירה נרשמה וממתינה לבדיקה של גיא', done_why: 'למה לבדיקה', done_noop: 'המכירה הזאת כבר רשומה אצלך.',
      st_verified: 'מאומת', st_review: 'לבדיקה', st_approved: 'אושר', st_rejected: 'נדחה', st_all: 'כל הסטטוסים',
      r_order_cancelled: 'ההזמנה בוטלה', r_order_refunded: 'ההזמנה הוחזרה או שהתשלום בוטל', r_no_contact: 'בפנייה אין מייל או טלפון להשוואה',
      r_contact_mismatch: 'הטלפון או המייל בהזמנה לא תואמים ללקוח בפנייה', r_no_agent_reply: 'לא נמצאה תשובה של נציג בפנייה',
      r_before_reply: 'ההזמנה נוצרה לפני התשובה הראשונה של נציג', r_outside_window: 'ההזמנה נוצרה יותר מ-{h} שעות אחרי התשובה האחרונה',
      r_other_agent: 'נציג אחר ({a}) ענה אחרון לפני ההזמנה', r_logger_not_in_chat: 'הנציג שרשם לא ענה בשיחה הזאת',
      mine_head: 'המכירות שלי', mine_empty: 'עוד לא רשמת מכירות.', mine_month: 'החודש', col_date: 'הזמנה', col_order: 'הזמנה #', col_amount: 'סכום', col_status: 'סטטוס',
      col_month: 'חודש', col_sales: 'מכירות', col_ticket: 'פנייה', col_brand: 'מותג', col_agent: 'נציג', col_customer: 'לקוח', col_items: 'פריטים', col_src: 'מקור', col_act: 'פעולות', open_ticket: 'לפנייה',
      count_rev: '{n} מכירות · {r}',
      b_title: 'מכירות — יומן בונוסים', b_sub: 'כל המכירות שהנציגים רשמו, מכל המותגים. נשמר במסד הנתונים של המערכת ומשוקף לגוגל שיט כל כמה דקות.',
      b_sheet: 'פתח בגוגל שיט', b_refresh: 'רענון', b_defaults: 'ברירות מחדל שגיא טרם החליט (ערכי קונפיג, אפשר לשנות): חלון {h} שעות מהתשובה האחרונה · הזכות לנציג שרושם · נציג אחר שענה אחרון מסומן "לבדיקה".',
      f_brand: 'מותג', f_agent: 'נציג', f_status: 'סטטוס', f_range: 'תקופה', f_all: 'הכל', f_month: 'החודש', f_prev: 'חודש שעבר', f_custom: 'טווח', f_from: 'מתאריך', f_to: 'עד תאריך',
      src_agent: 'נציג', src_detected: 'זוהתה', approve: 'אשר', reject: 'דחה', undo: 'בטל החלטה', reject_note: 'סיבת הדחייה (לא חובה)', reject_go: 'אשרו דחייה',
      conv: 'שיחה', conv_hide: 'הסתר שיחה', conv_loading: 'טוען את השיחה…', conv_frozen: 'העתק קפוא מ-{t}', conv_cut: '{n} הודעות ישנות יותר לא נשמרו (מקום)', who_customer: 'לקוח', who_us: 'נציג', who_automatic: 'אוטומטי',
      decided: '{s} על ידי {u}', history: 'נרשמה קודם על {a} ונדחתה', none_rows: 'אין מכירות בסינון הזה.',
      sum_head: 'בונוסים לפי נציג — מכירות מאומתות ומאושרות', sum_note: 'נספרות: מאומת או אושר. לבדיקה ללא החלטה — לא נספרת. נדחה — לא נספרת.', sum_review: 'לבדיקה', sum_rej: 'נדחו',
      s_head: 'מכירות שלא נרשמו', s_sub: 'שיחות לפני רכישה שנציג ענה עליהן ונגמרו בהזמנה בחלון הזמן, ואף אחד לא רשם. לחיצה אחת זוקפת לנציג (מאושר על ידך).',
      s_empty: 'אין כרגע מכירות שלא נרשמו.', s_scan: 'סרוק עכשיו', s_scan_done: 'הסריקה הסתיימה', s_credit: 'זקוף לנציג', s_dismiss: 'לא שלנו', s_pick: 'בחרו נציג', s_noagent: 'לא זוהה נציג',
      s_scanned: 'נסרק לפני {m} דק׳', s_never: 'עוד לא נסרק', credited: 'נזקף', err_load: 'לא הצלחנו לטעון מכירות של {b}.'
    },
    en: {
      btn: '💰 Sale', mine_btn: '💰 My sales', title: 'Log a sale', tab_log: 'Log a sale', tab_mine: 'My sales', close: 'Close', cancel: 'Cancel',
      rules: 'The order is checked against Shopify. "Verified" = the same customer (phone or email), the order was not cancelled, it was created after the first agent reply in the chat and within {h} hours of the last reply before it. The sale is credited to the agent who logs it. Proof: the order itself + a frozen copy of the conversation from the moment you log it.',
      loading: 'Loading the customer\'s orders…', pick: 'The customer\'s orders in Shopify', none: 'No orders found for this customer (the store shows the last 60 days). You can type an order number.',
      err_lookup: 'Could not read the orders from the store. You can type an order number.', no_contact: 'The ticket has no email or phone, so orders cannot be found. You can type an order number (it will be logged "for review").',
      or_type: 'Or another order number', note: 'Note (optional)', go: 'Log the sale', busy: 'Logging…',
      after: 'after the chat', before: 'before the chat', cancelled: 'cancelled', held: 'already credited to {a}', mine_held: 'you already logged it',
      done_verified: 'Sale logged and verified', done_review: 'Sale logged, waiting for the owner to review', done_why: 'Why it is for review', done_noop: 'You already logged this sale.',
      st_verified: 'Verified', st_review: 'For review', st_approved: 'Approved', st_rejected: 'Rejected', st_all: 'All statuses',
      r_order_cancelled: 'The order was cancelled', r_order_refunded: 'The order was refunded or the payment voided', r_no_contact: 'The ticket has no email or phone to compare',
      r_contact_mismatch: 'The order\'s phone or email does not match the ticket\'s customer', r_no_agent_reply: 'No agent reply was found in the ticket',
      r_before_reply: 'The order was created before the first agent reply', r_outside_window: 'The order was created more than {h} hours after the last reply',
      r_other_agent: 'Another agent ({a}) replied last before the order', r_logger_not_in_chat: 'The agent who logged it did not reply in this chat',
      mine_head: 'My sales', mine_empty: 'You have not logged a sale yet.', mine_month: 'This month', col_date: 'Order', col_order: 'Order #', col_amount: 'Amount', col_status: 'Status',
      col_month: 'Month', col_sales: 'Sales', col_ticket: 'Ticket', col_brand: 'Brand', col_agent: 'Agent', col_customer: 'Customer', col_items: 'Items', col_src: 'Source', col_act: 'Actions', open_ticket: 'Open ticket',
      count_rev: '{n} sales · {r}',
      b_title: 'Sales — bonus log', b_sub: 'Every sale the agents logged, across brands. Stored in the system database and mirrored to a Google Sheet every few minutes.',
      b_sheet: 'Open in Google Sheets', b_refresh: 'Refresh', b_defaults: 'Defaults the owner has not decided yet (config values): window {h} hours from the last reply · credit to the logging agent · another agent who replied last is flagged "for review".',
      f_brand: 'Brand', f_agent: 'Agent', f_status: 'Status', f_range: 'Period', f_all: 'All', f_month: 'This month', f_prev: 'Last month', f_custom: 'Range', f_from: 'From', f_to: 'To',
      src_agent: 'agent', src_detected: 'detected', approve: 'Approve', reject: 'Reject', undo: 'Undo decision', reject_note: 'Reason (optional)', reject_go: 'Confirm rejection',
      conv: 'Conversation', conv_hide: 'Hide conversation', conv_loading: 'Loading the conversation…', conv_frozen: 'Frozen copy from {t}', conv_cut: '{n} older messages were not kept (size)', who_customer: 'Customer', who_us: 'Agent', who_automatic: 'Automatic',
      decided: '{s} by {u}', history: 'Previously credited to {a} and rejected', none_rows: 'No sales match these filters.',
      sum_head: 'Bonuses per agent — verified and approved sales', sum_note: 'Counted: verified or approved. "For review" with no decision is not counted. Rejected is not counted.', sum_review: 'for review', sum_rej: 'rejected',
      s_head: 'Sales nobody logged', s_sub: 'Pre-sale chats an agent answered that ended in an order inside the window, and nobody logged it. One click credits the agent (approved by you).',
      s_empty: 'No unlogged sales right now.', s_scan: 'Scan now', s_scan_done: 'Scan finished', s_credit: 'Credit the agent', s_dismiss: 'Not ours', s_pick: 'Choose an agent', s_noagent: 'No agent identified',
      s_scanned: 'scanned {m} min ago', s_never: 'not scanned yet', credited: 'credited', err_load: 'Could not load the sales of {b}.'
    }
  };
  function sl(k, vars) {
    let s = (SL[LANG] && SL[LANG][k] !== undefined) ? SL[LANG][k] : (SL.he[k] !== undefined ? SL.he[k] : k);
    if (vars) Object.keys(vars).forEach(function (a) { s = s.split('{' + a + '}').join(String(vars[a])); });
    return s;
  }
  function slMoney(v, cur) {
    const n = Number(v);
    if (!isFinite(n)) return '—';
    return n.toLocaleString(LANG === 'en' ? 'en-US' : 'he-IL', { maximumFractionDigits: 2 }) + ' ' + (cur === 'ILS' || !cur ? '₪' : cur);
  }
  function slRevenue(map) {
    const keys = Object.keys(map || {});
    return keys.length ? keys.map(function (c) { return slMoney(map[c], c); }).join(' + ') : slMoney(0, 'ILS');
  }
  /** One reason code ("other_agent:amit") as a sentence. */
  function slReason(code, cfg) {
    const i = String(code).indexOf(':');
    const base = i < 0 ? code : code.slice(0, i);
    const arg = i < 0 ? '' : code.slice(i + 1);
    const k = 'r_' + base;
    const s = sl(k, { h: (cfg && cfg.windowHours) || 72, a: arg });
    return s === k ? code : s;
  }
  function slStatusChip(sale, big) {
    const e = sale.effective || sale.status;
    return h('span', { class: 'chip sale-st st-' + e + (big ? ' big' : ''), 'data-test': 'sale-status', 'data-status': e, text: sl('st_' + e) });
  }
  function slReasonList(sale, cfg) {
    const r = (sale.reasons || []);
    return r.length ? h('ul', { class: 'sale-reasons', 'data-test': 'sale-reasons' }, r.map(function (c) { return h('li', { 'data-code': c, text: slReason(c, cfg) }); })) : null;
  }

  const Sales = (function () {
    const dlg = $('sale-dlg');
    const MINE = {};            // brand -> { sales, summary, config } (this agent's, refreshed after each log)
    let st = null;              // the open dialog: { tab, brand, x, cands, pick, typed, note, busy, result, err, mine }

    async function loadMine(brand, force) {
      if (MINE[brand] && !force && Date.now() - MINE[brand].at < 60000) return MINE[brand];
      const r = await engine('apiSaleMine', {}, brand);
      if (r && r.ok) MINE[brand] = { sales: r.sales || [], summary: r.summary || [], config: r.config || {}, at: Date.now() };
      return MINE[brand] || null;
    }
    function ticketSales(brand, id) { return ((MINE[brand] && MINE[brand].sales) || []).filter(function (s) { return s.ticket === id; }); }

    /** The bar in the ticket head: the button, and a chip for each sale this agent logged in this ticket. */
    function bar(x) {
      const brand = tkBrand(x);
      const box = h('div', { class: 'sale-bar', id: 'sale-bar', 'data-test': 'sale-bar' });
      paintBar(box, x, brand);
      if (!MINE[brand]) loadMine(brand).then(function () { const el = document.getElementById('sale-bar'); if (el && S.tk && S.tk.id === x.id) paintBar(el, x, brand); });
      return box;
    }
    function paintBar(box, x, brand) {
      clear(box);
      box.append(h('button', { class: 'btn small sale-btn', type: 'button', 'data-test': 'sale-btn', text: sl('btn'), onclick: function () { open(x); } }));
      ticketSales(brand, x.id).forEach(function (s) {
        box.append(h('button', { class: 'chip sale-chip st-' + s.effective, type: 'button', 'data-test': 'sale-chip', title: sl('st_' + s.effective),
          onclick: function () { open(x, 'mine'); } }, h('bdi', { text: s.order_name }), ' · ', slMoney(s.amount, s.currency), ' · ', sl('st_' + s.effective)));
      });
    }

    function open(x, tab) {
      const brand = x ? tkBrand(x) : (S.brand || (S.me.brands[0] && S.me.brands[0].id));
      st = { tab: tab || (x ? 'log' : 'mine'), brand: brand, x: x || null, cands: null, pick: '', typed: '', note: '', busy: false, result: null, err: null };
      if (!dlg.open) dlg.showModal();
      render();
      if (x && st.tab === 'log') loadCands();
      if (st.tab === 'mine') loadMineTab();
    }
    async function loadCands() {
      const mine = st;
      const r = await engine('apiSaleCandidates', { id: mine.x.id }, mine.brand);
      if (st !== mine) return;
      mine.cands = r.ok ? r : { ok: false, lookup: 'error', msg: r.msg, orders: [] };
      // Agent's request via Owner, 2026-10-14 ("ממלא לך אוטומטית"): the button fills itself. An order after the chat, not cancelled, not credited to
      // anyone (the same flags the list marks) is chosen for him — the newest when there are several — so "מכירה" is one more click to confirm.
      // Never over his own choice made meanwhile. None: the typed-number field gets the focus.
      const ok = (mine.cands.orders || []).filter(function (o) { return o && o.after_reply && !o.cancelled && !o.credited && typeof o.name === 'string'; })
        .sort(function (a, b) { return (ms(b.createdAt) || 0) - (ms(a.createdAt) || 0); });
      if (ok.length && !mine.pick && !mine.typed) { mine.pick = ok[0].name; mine.auto = true; }
      render();
      if (st === mine && !ok.length && !mine.result) { const ti = dlg.querySelector('[data-test=sale-typed]'); if (ti) ti.focus(); }
    }
    async function loadMineTab() {
      const mine = st;
      await loadMine(mine.brand, true);
      if (st !== mine) return;
      mine.mineLoaded = true;
      render();
    }
    function render() {
      if (!st) return;
      clear(dlg);
      const tabs = h('div', { class: 'seg', role: 'group' });
      if (st.x) tabs.append(h('button', { class: 'btn small' + (st.tab === 'log' ? ' on' : ''), type: 'button', 'data-test': 'sale-tab-log', 'aria-pressed': st.tab === 'log' ? 'true' : 'false', text: sl('tab_log'),
        onclick: function () { if (st.busy) return; st.tab = 'log'; if (!st.cands) loadCands(); render(); } }));
      tabs.append(h('button', { class: 'btn small' + (st.tab === 'mine' ? ' on' : ''), type: 'button', 'data-test': 'sale-tab-mine', 'aria-pressed': st.tab === 'mine' ? 'true' : 'false', text: sl('tab_mine'),
        onclick: function () { if (st.busy) return; st.tab = 'mine'; st.mineLoaded = false; loadMineTab(); render(); } }));
      dlg.append(h('div', { class: 'in sale-dlg-in' }, h('h3', { text: st.tab === 'log' ? sl('title') : sl('mine_head') }), tabs, st.tab === 'log' ? logBody() : mineBody()));
    }
    function cfgHours() { return (st.cands && st.cands.window_hours) || (MINE[st.brand] && MINE[st.brand].config && MINE[st.brand].config.windowHours) || 72; }

    function logBody() {
      const wrap = h('div', { class: 'sale-log' });
      const x = st.x;
      wrap.append(h('div', { class: 'muted small sale-customer' }, h('bdi', { text: x.name || x.email || x.phone || '' })));
      wrap.append(h('p', { class: 'muted small sale-rules', 'data-test': 'sale-rules', text: sl('rules', { h: cfgHours() }) }));
      if (st.result) { wrap.append(doneBody()); return wrap; }
      if (!st.cands) { wrap.append(h('div', { class: 'muted', 'data-test': 'sale-loading', text: sl('loading') })); wrap.append(btns(false)); return wrap; }
      const c = st.cands;
      const me = S.me.user.username;
      if (c.lookup === 'error') wrap.append(h('div', { class: 'note-box warn', role: 'status', text: sl('err_lookup') }));
      else if (c.lookup === 'no_contact') wrap.append(h('div', { class: 'note-box warn', role: 'status', text: sl('no_contact') }));
      else if (!c.orders.length) wrap.append(h('div', { class: 'note-box', role: 'status', 'data-test': 'sale-none', text: sl('none') }));
      if (c.orders.length) {
        wrap.append(h('h4', { text: sl('pick') }));
        const list = h('div', { class: 'sale-orders', role: 'radiogroup' });
        c.orders.forEach(function (o) {
          const held = o.credited ? (o.credited.agent === me ? sl('mine_held') : sl('held', { a: o.credited.agent })) : '';
          const input = h('input', { type: 'radio', name: 'sale-order', value: o.name, disabled: held ? 'disabled' : null, checked: st.pick === o.name && !st.typed ? 'checked' : null });
          input.addEventListener('change', function () { st.pick = o.name; st.typed = ''; const ti = dlg.querySelector('[data-test=sale-typed]'); if (ti) ti.value = ''; syncGo(); });
          list.append(h('label', { class: 'sale-order' + (held ? ' held' : ''), 'data-test': 'sale-order', 'data-order': o.name },
            input, h('span', { class: 'so-main' }, h('bdi', { class: 'so-name', text: o.name }), ' ', h('b', { text: slMoney(o.amount, o.currency) }), ' ',
              h('span', { class: 'muted small', text: ago(o.createdAt) }), h('span', { class: 'muted small so-items', dir: 'auto', text: o.items })),
            h('span', { class: 'so-chips' }, o.after_reply ? h('span', { class: 'chip ok', text: sl('after') }) : h('span', { class: 'chip outline', text: sl('before') }),
              o.cancelled ? h('span', { class: 'chip bad', text: sl('cancelled') }) : null, held ? h('span', { class: 'chip bad', text: held }) : null)));
        });
        wrap.append(list);
      }
      const typed = h('input', { type: 'text', inputmode: 'numeric', maxlength: '12', dir: 'ltr', 'data-test': 'sale-typed', placeholder: '#1234', value: st.typed, 'aria-label': sl('or_type') });
      typed.addEventListener('input', function () {
        st.typed = typed.value; if (st.typed) { st.pick = ''; dlg.querySelectorAll('input[name=sale-order]').forEach(function (r) { r.checked = false; }); }
        syncGo();
      });
      wrap.append(h('label', null, sl('or_type'), typed));
      const note = h('textarea', { rows: '2', maxlength: '300', 'data-test': 'sale-note', 'aria-label': sl('note') });
      note.value = st.note;
      note.addEventListener('input', function () { st.note = note.value; });
      wrap.append(h('label', null, sl('note'), note));
      if (st.err) wrap.append(h('div', { class: 'err-box', role: 'alert', 'data-test': 'sale-err', text: st.err }));
      wrap.append(btns(true));
      return wrap;
    }
    function chosen() { return (st.typed || st.pick || '').trim(); }
    function syncGo() { const b = dlg.querySelector('[data-test=sale-go]'); if (b) b.disabled = st.busy || !/^#?\d{3,9}$/.test(chosen()); }
    function btns(canGo) {
      const row = h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', 'data-test': 'sale-cancel', text: sl('cancel'), onclick: function () { if (!st.busy) dlg.close(); } }));
      if (canGo) row.append(h('button', { class: 'btn primary', type: 'button', 'data-test': 'sale-go', text: st.busy ? sl('busy') : sl('go'), disabled: st.busy || !/^#?\d{3,9}$/.test(chosen()) ? 'disabled' : null, onclick: submit }));
      return row;
    }
    async function submit() {
      if (st.busy || !/^#?\d{3,9}$/.test(chosen())) return;
      const mine = st;
      mine.busy = true; mine.err = null; render();
      const r = await engine('apiSaleLog', { id: mine.x.id, orderNo: chosen(), note: mine.note.trim() || undefined }, mine.brand);
      mine.busy = false;
      if (st !== mine) return;
      if (!r.ok) { mine.err = r.msg || r.error || sl('err_lookup'); render(); return; }
      mine.result = r;
      delete MINE[mine.brand];
      await loadMine(mine.brand, true);
      const el = document.getElementById('sale-bar');
      if (el && S.tk && S.tk.id === mine.x.id) paintBar(el, S.tk.ticket, mine.brand);
      if (st === mine) render();
    }
    function doneBody() {
      const r = st.result;
      const s = r.sale;
      const box = h('div', { class: 'sale-done', 'data-test': 'sale-done' });
      box.append(h('div', { class: 'sale-done-head' }, slStatusChip(s, true), ' ', h('b', { text: r.noop ? sl('done_noop') : sl(s.status === 'verified' ? 'done_verified' : 'done_review') })));
      box.append(h('div', null, h('bdi', { text: s.order_name }), ' · ', h('b', { text: slMoney(s.amount, s.currency) }), s.items ? h('span', { class: 'muted small', dir: 'auto', text: ' · ' + s.items }) : null));
      if (s.reasons && s.reasons.length) box.append(h('h4', { text: sl('done_why') }), slReasonList(s, { windowHours: cfgHours() }));
      box.append(h('div', { class: 'row-btns' }, h('button', { class: 'btn primary', type: 'button', 'data-test': 'sale-close', text: sl('close'), onclick: function () { dlg.close(); } })));
      return box;
    }

    function mineBody() {
      const wrap = h('div', { class: 'sale-mine', 'data-test': 'sale-mine' });
      const m = MINE[st.brand];
      if (!st.mineLoaded || !m) { wrap.append(h('div', { class: 'muted', text: sl('loading') })); return wrap; }
      const month = ilDay(Date.now()).slice(0, 7);
      const cur = m.summary.filter(function (s) { return s.month === month; })[0];
      wrap.append(h('div', { class: 'sale-sum', 'data-test': 'sale-mine-sum' }, h('b', { text: sl('mine_month') + ': ' }), cur ? sl('count_rev', { n: cur.count, r: slRevenue(cur.revenue) }) : sl('count_rev', { n: 0, r: slMoney(0, 'ILS') }),
        cur && cur.review ? h('span', { class: 'muted small', text: ' · ' + cur.review + ' ' + sl('sum_review') }) : null));
      if (!m.sales.length) { wrap.append(h('div', { class: 'muted', 'data-test': 'sale-mine-empty', text: sl('mine_empty') })); wrap.append(h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: sl('close'), onclick: function () { dlg.close(); } }))); return wrap; }
      const tb = h('table', { class: 'dash-table sale-table' }, h('thead', null, h('tr', null, [sl('col_date'), sl('col_order'), sl('col_amount'), sl('col_status'), sl('col_ticket')].map(function (c) { return h('th', { text: c }); }))));
      const body = h('tbody');
      m.sales.forEach(function (s) {
        body.append(h('tr', { 'data-test': 'sale-mine-row', 'data-status': s.effective },
          h('td', { text: fmtDate(s.order_created_at, true) }), h('td', null, orderLink(s.brand || st.brand, s.order_name, s.order_id)), h('td', { text: slMoney(s.amount, s.currency) }),
          h('td', null, slStatusChip(s), slReasonList(s, m.config)), h('td', null, h('a', { href: '#/b/' + encodeURIComponent(s.brand || st.brand) + '/t/' + encodeURIComponent(s.ticket), text: sl('open_ticket'), onclick: function () { dlg.close(); } }))));
      });
      tb.append(body);
      wrap.append(h('div', { class: 'table-wrap' }, tb), h('div', { class: 'row-btns' }, h('button', { class: 'btn ghost', type: 'button', text: sl('close'), onclick: function () { dlg.close(); } })));
      return wrap;
    }
    dlg.addEventListener('close', function () { st = null; });
    return { bar: bar, open: open, openMine: function () { open(null, 'mine'); } };
  })();

  /** The managers' board table (#/dash, admins): every sale, the proof, approve / reject, per-agent bonus summary, and the sales nobody logged. */
  const SalesBoard = (function () {
    const F = { brand: 'all', agent: 'all', status: 'all', range: 'month', from: '', to: '' };
    const D = { sales: [], summary: [], cfg: {}, errs: [], sug: [], agents: [], scan: {}, loaded: false, busy: false, open: {}, proof: {}, rej: '', msg: '' };
    let root = null;

    async function load() {
      if (D.busy) return;
      D.busy = true; D.errs = [];
      const brands = S.me.brands.filter(function (b) { return b.connected; }).map(function (b) { return b.id; });
      const res = await Promise.all(brands.map(function (b) {
        return Promise.all([engine('apiSaleList', {}, b), engine('apiSaleSuggestions', {}, b)]).then(function (p) { return { b: b, list: p[0], sug: p[1] }; });
      }));
      D.sales = []; D.summary = []; D.sug = []; D.agents = []; D.scan = {};
      res.forEach(function (x) {
        if (!x.list.ok) { D.errs.push(x.b); return; }
        D.cfg = x.list.config || D.cfg;
        x.list.sales.forEach(function (s) { s._brand = x.b; D.sales.push(s); });
        (x.list.summary || []).forEach(function (s) { D.summary.push(Object.assign({ _brand: x.b }, s)); });
        if (x.sug.ok) {
          (x.sug.items || []).forEach(function (s) { s._brand = x.b; D.sug.push(s); });
          (x.sug.agents || []).forEach(function (a) { if (D.agents.indexOf(a) < 0) D.agents.push(a); });
          D.scan[x.b] = x.sug.scan || {};
        }
      });
      D.agents.sort();
      D.loaded = true; D.busy = false;
      paint();
    }
    function inRange(s) {
      if (F.range === 'all') return true;
      const month = ilDay(Date.now()).slice(0, 7);
      if (F.range === 'month') return s.month === month;
      if (F.range === 'prev') { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return s.month === ilDay(d.getTime()).slice(0, 7); }
      const day = ilDay(Date.parse(s.order_created_at) || 0);
      return (!F.from || day >= F.from) && (!F.to || day <= F.to);
    }
    function filtered() {
      return D.sales.filter(function (s) {
        return (F.brand === 'all' || s._brand === F.brand) && (F.agent === 'all' || s.agent === F.agent) && (F.status === 'all' || s.effective === F.status) && inRange(s);
      }).sort(function (a, b) { return String(b.order_created_at).localeCompare(String(a.order_created_at)); });
    }
    function sel(label, key, opts, test) {
      const s = h('select', { 'aria-label': label, 'data-test': test }, opts.map(function (o) { return h('option', { value: o[0], text: o[1], selected: F[key] === o[0] ? 'selected' : null }); }));
      s.addEventListener('change', function () { F[key] = s.value; paint(); });
      return h('label', { class: 'sf' }, h('span', { class: 'muted small', text: label }), s);
    }
    function paint() {
      if (!root) return;
      clear(root);
      const sheet = S.me.sales_sheet_url;
      root.append(h('div', { class: 'dash-head sales-head' }, h('h2', { 'data-test': 'sales-title', text: sl('b_title') }),
        h('button', { class: 'btn small', type: 'button', 'data-test': 'sales-refresh', text: sl('b_refresh'), onclick: function () { load(); } }),
        sheet ? h('a', { class: 'btn small ghost', href: sheet, target: '_blank', rel: 'noopener noreferrer', 'data-test': 'sales-sheet', text: '📄 ' + sl('b_sheet') }) : null));
      root.append(h('p', { class: 'muted small', text: sl('b_sub') }), h('p', { class: 'muted small', 'data-test': 'sales-defaults', text: sl('b_defaults', { h: D.cfg.windowHours || 72 }) }));
      if (!D.loaded) { root.append(h('div', { class: 'skeleton' })); return; }
      D.errs.forEach(function (b) { root.append(h('div', { class: 'err-box', text: sl('err_load', { b: brandName(b) }) })); });
      if (D.msg) root.append(h('div', { class: 'note-box', role: 'status', text: D.msg }));
      root.append(suggestions());
      const brands = [['all', sl('f_all')]].concat(S.me.brands.map(function (b) { return [b.id, brandName(b.id)]; }));
      const agents = [['all', sl('f_all')]].concat(Array.from(new Set(D.sales.map(function (s) { return s.agent; }))).sort().map(function (a) { return [a, a]; }));
      const fl = h('div', { class: 'sales-filters', 'data-test': 'sales-filters' },
        sel(sl('f_brand'), 'brand', brands, 'f-brand'), sel(sl('f_agent'), 'agent', agents, 'f-agent'),
        sel(sl('f_status'), 'status', [['all', sl('st_all')], ['verified', sl('st_verified')], ['review', sl('st_review')], ['approved', sl('st_approved')], ['rejected', sl('st_rejected')]], 'f-status'),
        sel(sl('f_range'), 'range', [['month', sl('f_month')], ['prev', sl('f_prev')], ['all', sl('f_all')], ['custom', sl('f_custom')]], 'f-range'));
      if (F.range === 'custom') {
        [['from', 'f_from'], ['to', 'f_to']].forEach(function (p) {
          const i = h('input', { type: 'date', value: F[p[0]], 'aria-label': sl(p[1]), 'data-test': 'f-' + p[0] });
          i.addEventListener('change', function () { F[p[0]] = i.value; paint(); });
          fl.append(h('label', { class: 'sf' }, h('span', { class: 'muted small', text: sl(p[1]) }), i));
        });
      }
      root.append(fl, table(), summary());
    }
    function agentCell(s) { return h('td', null, h('bdi', { text: s.agent }), s.source === 'detected' ? h('div', { class: 'muted small', text: sl('src_detected') }) : null); }
    function table() {
      const rows = filtered();
      const box = h('div', { class: 'table-wrap sales-wrap' });
      if (!rows.length) { box.append(h('div', { class: 'muted', 'data-test': 'sales-empty', text: sl('none_rows') })); return box; }
      const cols = ['col_date', 'col_brand', 'col_agent', 'col_order', 'col_amount', 'col_customer', 'col_status', 'col_ticket', 'col_act'];
      const tb = h('table', { class: 'dash-table sale-table', 'data-test': 'sales-table' }, h('thead', null, h('tr', null, cols.map(function (c) { return h('th', { text: sl(c) }); }))));
      const body = h('tbody');
      rows.forEach(function (s) {
        const decided = s.decision ? h('div', { class: 'muted small' }, sl('decided', { s: sl('st_' + s.decision), u: s.decided_by }), s.decision_note ? ' — ' + s.decision_note : '') : null;
        const tr = h('tr', { 'data-test': 'sale-row', 'data-id': s.id, 'data-brand': s._brand, 'data-status': s.effective },
          h('td', { text: fmtDate(s.order_created_at, true) }), h('td', null, h('bdi', { text: brandName(s._brand) })), agentCell(s),
          h('td', null, orderLink(s._brand, s.order_name, s.order_id), s.items ? h('div', { class: 'muted small', dir: 'auto', text: s.items }) : null),
          h('td', { text: slMoney(s.amount, s.currency) }),
          h('td', null, h('bdi', { text: s.customer_name || '' }), h('div', { class: 'muted small', dir: 'ltr', text: s.customer_phone || s.customer_email || '' })),
          h('td', null, slStatusChip(s), slReasonList(s, D.cfg), decided,
            (s.history || []).length ? h('div', { class: 'muted small', text: sl('history', { a: s.history[s.history.length - 1].agent }) }) : null),
          h('td', null, h('a', { href: '#/b/' + encodeURIComponent(s._brand) + '/t/' + encodeURIComponent(s.ticket), 'data-test': 'sale-ticket', text: sl('open_ticket') })),
          h('td', { class: 'sale-acts' }, actions(s)));
        body.append(tr);
        if (D.open[s.id]) body.append(h('tr', { class: 'sale-proof-row', 'data-test': 'sale-proof-row' }, h('td', { colspan: String(cols.length) }, proofBox(s))));
      });
      tb.append(body);
      box.append(tb);
      return box;
    }
    function actions(s) {
      const a = h('div', { class: 'row-btns start' });
      if (s.decision !== 'approved') a.append(h('button', { class: 'btn small primary', type: 'button', 'data-test': 'sale-approve', text: sl('approve'), onclick: function () { decide(s, 'approved'); } }));
      if (s.decision !== 'rejected') a.append(h('button', { class: 'btn small danger-outline', type: 'button', 'data-test': 'sale-reject', text: sl('reject'), onclick: function () { D.rej = D.rej === s.id ? '' : s.id; paint(); } }));
      if (s.decision) a.append(h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'sale-undo', text: sl('undo'), onclick: function () { decide(s, 'clear'); } }));
      a.append(h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'sale-conv', 'aria-expanded': D.open[s.id] ? 'true' : 'false', text: D.open[s.id] ? sl('conv_hide') : sl('conv'), onclick: function () { toggleProof(s); } }));
      if (D.rej === s.id) {
        const note = h('input', { type: 'text', maxlength: '300', 'data-test': 'sale-reject-note', placeholder: sl('reject_note'), 'aria-label': sl('reject_note') });
        a.append(note, h('button', { class: 'btn small danger', type: 'button', 'data-test': 'sale-reject-go', text: sl('reject_go'), onclick: function () { decide(s, 'rejected', note.value.trim()); } }));
      }
      return a;
    }
    async function decide(s, decision, note) {
      const r = await engine('apiSaleDecide', { id: s.id, decision: decision, note: note || undefined }, s._brand);
      if (!r.ok) { D.msg = r.msg || r.error; paint(); return; }
      D.msg = ''; D.rej = '';
      Object.assign(s, r.sale, { _brand: s._brand });
      paint();
      load();      // the monthly summary is the engine's
    }
    async function toggleProof(s) {
      if (D.open[s.id]) { delete D.open[s.id]; paint(); return; }
      D.open[s.id] = true;
      paint();
      if (!D.proof[s.id]) {
        const r = await engine('apiSaleProof', { id: s.id }, s._brand);
        D.proof[s.id] = r.ok ? (r.proof || { messages: [] }) : { error: r.msg || r.error };
        paint();
      }
    }
    function proofBox(s) {
      const p = D.proof[s.id];
      const box = h('div', { class: 'sale-proof', 'data-test': 'sale-proof' });
      if (!p) { box.append(h('div', { class: 'muted', text: sl('conv_loading') })); return box; }
      if (p.error) { box.append(h('div', { class: 'err-box', text: p.error })); return box; }
      box.append(h('div', { class: 'muted small', text: sl('conv_frozen', { t: fmtDate(p.frozen_at, true) }) + (p.cut ? ' · ' + sl('conv_cut', { n: p.cut }) : '') }));
      (p.messages || []).forEach(function (m) {
        box.append(h('div', { class: 'pm ' + (m.who === 'customer' ? 'cust' : 'us') }, h('div', { class: 'muted small' }, sl('who_' + (m.who === 'customer' ? 'customer' : m.who === 'automatic' ? 'automatic' : 'us')), ' · ', fmtDate(m.at, true)),
          h('div', { class: 'pm-text', dir: 'auto', text: m.text })));
      });
      return box;
    }
    function summary() {
      const box = h('div', { class: 'sales-sum', 'data-test': 'sales-summary' }, h('h3', { text: sl('sum_head') }), h('p', { class: 'muted small', text: sl('sum_note') }));
      const by = {};
      D.summary.forEach(function (s) {
        if ((F.brand !== 'all' && s._brand !== F.brand) || (F.agent !== 'all' && s.agent !== F.agent)) return;
        const k = s.agent + '|' + s.month;
        const o = by[k] = by[k] || { agent: s.agent, month: s.month, count: 0, revenue: {}, review: 0, rejected: 0 };
        o.count += s.count; o.review += s.review; o.rejected += s.rejected;
        Object.keys(s.revenue || {}).forEach(function (c) { o.revenue[c] = Math.round(((o.revenue[c] || 0) + s.revenue[c]) * 100) / 100; });
      });
      const rows = Object.keys(by).map(function (k) { return by[k]; }).sort(function (a, b) { return a.month < b.month ? 1 : a.month > b.month ? -1 : a.agent < b.agent ? -1 : 1; });
      if (!rows.length) { box.append(h('div', { class: 'muted', text: sl('none_rows') })); return box; }
      const tb = h('table', { class: 'dash-table', 'data-test': 'sales-sum-table' }, h('thead', null, h('tr', null,
        [sl('col_agent'), sl('col_month'), sl('col_sales'), sl('col_amount'), sl('sum_review'), sl('sum_rej')].map(function (c) { return h('th', { text: c }); }))));
      const body = h('tbody');
      rows.forEach(function (r) {
        body.append(h('tr', { 'data-test': 'sum-row', 'data-agent': r.agent, 'data-month': r.month }, h('td', null, h('bdi', { text: r.agent })), h('td', { text: r.month }), h('td', null, h('b', { text: String(r.count) })),
          h('td', { text: slRevenue(r.revenue) }), h('td', { text: String(r.review) }), h('td', { text: String(r.rejected) })));
      });
      tb.append(body);
      box.append(h('div', { class: 'table-wrap' }, tb));
      return box;
    }
    function suggestions() {
      const box = h('div', { class: 'sales-sug', 'data-test': 'sales-sug' });
      const oldest = Object.keys(D.scan).map(function (b) { return D.scan[b] && D.scan[b].ageMin; }).filter(function (m) { return typeof m === 'number'; });
      box.append(h('div', { class: 'dash-head' }, h('h3', { text: sl('s_head') + (D.sug.length ? ' (' + D.sug.length + ')' : '') }),
        h('button', { class: 'btn small', type: 'button', 'data-test': 'sug-scan', text: sl('s_scan'), onclick: scanNow }),
        h('span', { class: 'muted small', text: oldest.length ? sl('s_scanned', { m: Math.max.apply(null, oldest) }) : sl('s_never') })), h('p', { class: 'muted small', text: sl('s_sub') }));
      if (!D.sug.length) { box.append(h('div', { class: 'muted', 'data-test': 'sug-empty', text: sl('s_empty') })); return box; }
      const tb = h('table', { class: 'dash-table sale-table', 'data-test': 'sug-table' });
      const body = h('tbody');
      D.sug.forEach(function (s) {
        let pick = null;
        const agentCellEl = s.agent ? h('td', null, h('bdi', { text: s.agent })) : (function () {
          pick = h('select', { 'aria-label': sl('s_pick'), 'data-test': 'sug-agent' }, h('option', { value: '', text: sl('s_pick') }), D.agents.map(function (a) { return h('option', { value: a, text: a }); }));
          return h('td', null, pick);
        })();
        body.append(h('tr', { 'data-test': 'sug-row', 'data-id': s.id, 'data-brand': s._brand },
          h('td', { text: fmtDate(s.order_created_at, true) }), h('td', null, h('bdi', { text: brandName(s._brand) })), agentCellEl,
          h('td', null, orderLink(s._brand, s.order_name, s.order_id), s.items ? h('div', { class: 'muted small', dir: 'auto', text: s.items }) : null), h('td', { text: slMoney(s.amount, s.currency) }),
          h('td', null, h('bdi', { text: s.customer_name || '' })),
          h('td', null, s.reasons && s.reasons.length ? slReasonList(s, D.cfg) : null, h('a', { href: '#/b/' + encodeURIComponent(s._brand) + '/t/' + encodeURIComponent(s.ticket), text: sl('open_ticket') })),
          h('td', { class: 'sale-acts' }, h('div', { class: 'row-btns start' },
            h('button', { class: 'btn small primary', type: 'button', 'data-test': 'sug-credit', text: sl('s_credit'), onclick: function () { credit(s, pick ? pick.value : ''); } }),
            h('button', { class: 'btn small ghost', type: 'button', 'data-test': 'sug-dismiss', text: sl('s_dismiss'), onclick: function () { dismiss(s); } })))));
      });
      tb.append(body);
      box.append(h('div', { class: 'table-wrap' }, tb));
      return box;
    }
    async function credit(s, agent) {
      if (!s.agent && !agent) { D.msg = sl('s_noagent'); paint(); return; }
      const r = await engine('apiSaleSuggestCredit', { id: s.id, agent: s.agent ? undefined : agent }, s._brand);
      D.msg = r.ok ? sl('credited') + ' ' + s.order_name : (r.msg || r.error);
      await load();
    }
    async function dismiss(s) { const r = await engine('apiSaleSuggestDismiss', { id: s.id }, s._brand); D.msg = r.ok ? '' : (r.msg || r.error); await load(); }
    async function scanNow() {
      D.msg = '';
      for (const b of S.me.brands.filter(function (x) { return x.connected; }).map(function (x) { return x.id; })) { await engine('apiSaleScan', {}, b); }
      D.msg = sl('s_scan_done');
      await load();
    }
    function mount(el) { root = el; D.loaded = false; paint(); load(); }
    return { mount: mount };
  })();

  const Dash = (function () {
    const HE = {
      title: 'לוח מנהלים', day: 'יום', d7: '7 ימים', d30: '30 ימים', updated: 'עודכן', loading: 'טוען…',
      method: 'זמן עבודה = מהפעולה הראשונה עד האחרונה, פחות הפסקות (יותר מ-{b} דק׳ בלי אף פעולה במסך); רווח קצר יותר נספר כעבודה בשופיפיי, קצ׳ינג, דונדי וג׳ימייל. "במסך" = החישוב הקודם (רווח עד {m} דק׳).',
      since: 'יומן הפעילות נאסף מ-{d}', received: 'נכנסו היום', answered: 'נענו', closed: 'נסגרו', of: 'מהנכנסות',
      open_now: 'פתוחות עכשיו', awaiting: 'ממתינות למענה', frt: 'זמן למענה ראשון (חציון)', frt_human: 'מענה ראשון של אדם (חציון)',
      incl_bot: 'כולל בוט: {v}', human_pending: 'ממתין לנתון מהמנוע', gmail_blocked: 'מייל: גוגל חסם זמנית — יתעדכן',
      gmail_error: 'מייל: שגיאה בקריאה מג׳ימייל — יתעדכן', wa_only: 'וואטסאפ בלבד', frt_human_all: 'מענה ראשון של אדם', auto_pct: 'מענה אוטומטי',
      wa_failed: 'כשלי שליחה בוואטסאפ', aging: 'גיל הממתינות', partial: 'חלקי: הרשימה מחזיקה רק 100 סגורות אחרונות',
      src_snapshot: 'תמונת חצות', src_rebuilt: 'שוחזר מהרשימה הנוכחית', kpis: 'מדדים מול השוק (2026)',
      frt_email: 'מענה ראשון — מייל', frt_wa: 'מענה ראשון — וואטסאפ', aht: 'זמן טיפול לתשובה (AHT)', fcr: 'פתרון במענה אחד (קירוב)',
      reopen: 'נפתחו מחדש', occ: 'ניצולת (במסך ÷ זמן עבודה)', backlog: 'בקלוג', sla_wa: 'וואטסאפ נענה תוך שעה', sla_email: 'מייל נענה תוך 24 ש׳',
      csat: 'שביעות רצון (CSAT)', csat_missing: 'חסר — אין סקר שביעות רצון', bench: 'יעד', n_a: 'אין עדיין נתונים',
      fcr_note: 'חלון 72 השעות עוד פתוח', agents: 'נציגים', agent: 'נציג', active: 'זמן עבודה', replies: 'תשובות', closes: 'סגירות', snoozed: 'נדחות עכשיו',
      per_hour: 'תשובות לשעת עבודה', engine: 'במנוע', none: 'אין פעילות בטווח', by_brand: 'לפי מותג', by_channel: 'לפי ערוץ',
      heat: 'מתי עובדים בפועל', heat_all: 'כל הנציגים', heat_total: 'סה״כ לפי שעה', pies: 'חלוקה', pie_brand: 'זמן עבודה לפי מותג',
      pie_chan: 'לפי ערוץ', pie_cat: 'לפי נושא', pie_who: 'מי ענה', agents_w: 'נציגים', auto_w: 'מענה אוטומטי', email: 'מייל', whatsapp: 'וואטסאפ',
      h: 'ש׳', m: 'דק׳', s: 'שנ׳', resends: 'מתוכן שליחה חוזרת', per_day: 'לפי יום', present: 'מחובר',
      fixing: 'הנתונים בתיקון — לא סופיים', fixing_sub: 'נציגים עונים גם ישירות בדונדי ובג׳ימייל; המספרים יעברו לחישוב מהשיחות עצמן במנוע.',
      onscreen: 'זמן עבודה ופעילות במסך', log_word: 'ביומן', ds_age: 'לפני {m} דק׳', ds_updating: 'מתעדכן…', missing: 'עוד לא מהשיחות — לא סופי: {b}', from_conv: 'מהשיחות', computing: 'מחשב מהשיחות…',
      src_answered: 'נענו — לפי מקור', src_closed: 'נסגרו — לפי מקור', src_fromSystem: 'מהמערכת', src_fromDondy: 'מדונדי', src_fromEmail: 'מהמייל',
      sub_agent: 'נציג', sub_auto: 'אוטומטי', sub_human: 'אדם', sub_bot: 'בוט', sub_template: 'תבנית', sub_close: 'סגירה', sub_direct: 'ישיר', total: 'סה״כ',
      conv_answered: 'ענו (מהשיחות)', direct_note: 'בלי שם נציג: ישירות בדונדי {d} · ישירות במייל {g} · אוטומטי {a} · בוט ותבניות {b}', others: 'אחרים', all_brands: 'כל המותגים', brand_col: 'מותג', idle_agents: '{n} משתמשים בלי פעילות בטווח', log_new: 'יומן הפעילות עוד ריק — זמן העבודה נספר מהפעולה הבאה של כל נציג; תשובות וסגירות כבר נספרות מהמנוע.'
    };
    const EN = {
      title: 'Managers', day: 'Day', d7: '7 days', d30: '30 days', updated: 'Updated', loading: 'Loading…',
      method: 'Work time = first to last action, minus breaks (over {b} min with no action on the screen); a shorter gap counts as work in Shopify, Kaching, Dondy and Gmail. "On screen" = the previous measure (gaps up to {m} min).',
      since: 'Activity log collected since {d}', received: 'Received today', answered: 'Answered', closed: 'Closed', of: 'of received',
      open_now: 'Open now', awaiting: 'Awaiting a reply', frt: 'First reply (median)', frt_human: 'First reply by a person (median)',
      incl_bot: 'incl. bot: {v}', human_pending: 'waiting for the engine field', gmail_blocked: 'Email: temporarily blocked by Google — will update',
      gmail_error: 'Email: Gmail read failed — will update', wa_only: 'WhatsApp only', frt_human_all: 'First reply by a person', auto_pct: 'Auto-replies',
      wa_failed: 'WhatsApp send failures', aging: 'Backlog age', partial: 'Partial: the list holds only the last 100 closed',
      src_snapshot: 'Midnight snapshot', src_rebuilt: 'Rebuilt from the current list', kpis: 'KPIs vs 2026 benchmarks',
      frt_email: 'First reply — email', frt_wa: 'First reply — WhatsApp', aht: 'Handle time per reply (AHT)', fcr: 'First-contact resolution (proxy)',
      reopen: 'Reopened', occ: 'Occupancy (on screen ÷ work time)', backlog: 'Backlog', sla_wa: 'WhatsApp answered within 1h', sla_email: 'Email answered within 24h',
      csat: 'CSAT', csat_missing: 'Missing — no satisfaction survey', bench: 'Target', n_a: 'No data yet',
      fcr_note: 'the 72h window is still open', agents: 'Agents', agent: 'Agent', active: 'Work time', replies: 'Replies', closes: 'Closed', snoozed: 'Snoozed now',
      per_hour: 'Replies per work hour', engine: 'engine', none: 'No activity in range', by_brand: 'By brand', by_channel: 'By channel',
      heat: 'When they actually work', heat_all: 'All agents', heat_total: 'Total per hour', pies: 'Split', pie_brand: 'Work time by brand',
      pie_chan: 'By channel', pie_cat: 'By topic', pie_who: 'Who answered', agents_w: 'Agents', auto_w: 'Auto-reply', email: 'Email', whatsapp: 'WhatsApp',
      h: 'h', m: 'min', s: 's', resends: 'of them re-sends', per_day: 'Per day', present: 'Logged in',
      fixing: 'The numbers are being fixed — not final', fixing_sub: 'Agents also answer directly in Dondy and Gmail; the numbers will move to the engine\'s count from the conversations.',
      onscreen: 'Work time and on-screen activity', log_word: 'log', ds_age: '{m} min ago', ds_updating: 'updating…', missing: 'Not from the conversations yet — not final: {b}', from_conv: 'from conversations', computing: 'Counting from conversations…',
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
    // Owner, 2026-10-13: open tickets per brand, live — the same count as the agents' "פתוחות" tab
    Object.assign(L, LANG === 'en' ? {
      live_title: 'Open now — live', live_def: 'Same as the agents\' "Open" tab · refreshes every {s} s', live_all: 'All brands',
      live_age: 'updated {s} s ago', live_old: 'last copy {m} min ago', live_unknown: 'no data yet'
    } : {
      live_title: 'פתוחות עכשיו — בלייב', live_def: 'כמו הלשונית "פתוחות" של הנציגים · מתעדכן כל {s} שנ׳', live_all: 'כל המותגים',
      live_age: 'עודכן לפני {s} שנ׳', live_old: 'עותק אחרון לפני {m} דק׳', live_unknown: 'אין עדיין נתון'
    });
    Object.assign(L, LANG === 'en' ? { on_screen: 'On screen', breaks: 'breaks {t}', shift_w: 'shift' } : { on_screen: 'במסך', breaks: 'הפסקות {t}', shift_w: 'משמרת' });
    function d(k, v) { let s = L[k] || k; Object.keys(v || {}).forEach(function (x) { s = s.replace('{' + x + '}', v[x]); }); return s; }
    const st = { range: '1', date: '', data: null, err: null, busy: false, who: 'all' };
    let timer = null;
    /** The live strip: ONE element, built once and repainted in place from /api/dash/open (its own light 30 s timer, so the
     *  heavy /api/dash load never delays it). An unchanged answer repaints nothing (build-rules §1ב). */
    const live = { el: null, data: null, sig: '', timer: null, busy: false, at: 0 };
    function liveStrip() {
      if (!live.el) live.el = h('section', { class: 'dash-live', 'data-test': 'dash-live', 'aria-live': 'polite' });
      paintLive();
      return live.el;
    }
    function liveCard(name, o, test, brand, total) {
      const unknown = !o || !o.known;
      return h('div', { class: 'live-card' + (total ? ' total' : '') + (!unknown && !o.total ? ' zero' : ''), 'data-test': test, 'data-brand': brand || null },
        h('div', { class: 'l' }, h('bdi', { text: name })),
        h('div', { class: 'v', 'data-test': 'live-n', text: unknown ? '—' : String(o.total) }),
        h('div', { class: 'ch small', 'data-test': 'live-ch' }, unknown ? L.live_unknown : L.whatsapp + ' ' + o.whatsapp + ' · ' + L.email + ' ' + o.email),
        !unknown && !total && o.synced_age > 120 ? h('div', { class: 'muted small', 'data-test': 'live-old', text: d('live_old', { m: Math.round(o.synced_age / 60) }) }) : null);
    }
    function paintLive() {
      if (!live.el) return;
      const x = live.data;
      const sig = x ? JSON.stringify([x.brands, x.total]) : '';
      const ageEl = live.el.querySelector('[data-test=live-age]');
      if (sig && sig === live.sig && ageEl) { ageEl.textContent = d('live_age', { s: Math.max(0, Math.round((Date.now() - live.at) / 1000)) }); return; }
      live.sig = sig;
      clear(live.el);
      live.el.append(h('div', { class: 'live-head' }, h('h3', null, h('span', { class: 'live-dot', 'aria-hidden': 'true' }), L.live_title),
        h('span', { class: 'muted small', text: d('live_def', { s: (x && x.refresh_s) || 30 }) }),
        x ? h('span', { class: 'muted small', 'data-test': 'live-age', text: d('live_age', { s: Math.max(0, Math.round((Date.now() - live.at) / 1000)) }) }) : null));
      if (!x) { live.el.append(h('div', { class: 'skeleton' })); return; }
      const row = h('div', { class: 'live-cards' });
      const brands = Object.keys(x.brands || {});
      if (brands.length > 1) row.append(liveCard(L.live_all, Object.assign({ known: true }, x.total), 'live-total', null, true));
      brands.forEach(function (b) { row.append(liveCard(brandName(b), x.brands[b], 'live-brand', b, false)); });
      live.el.append(row);
    }
    async function loadLive() {
      if (live.busy) return;
      live.busy = true;
      let r;
      try { r = await api('/api/dash/open', undefined, 'GET', { quiet: true }); } finally { live.busy = false; }
      if (r && r.ok) { live.data = r; live.at = Date.now(); }
      if (S.view === 'dash') paintLive();
    }
    /** Cancellations (Owner, 2026-10-23: "כמה מנויים הצוות מבטל כל יום וכמה ביטולים בכללי הוא עושה ללקוחות"; the November goal = the monthly Kaching
     *  cancel rate below half of October's). Admins only, like the sales table. ONE element built once and repainted only when the answer changed
     *  (the 30 s board refresh never rebuilds it). /api/dash/cancels never waits for the engine: a brand still counting says so, an engine without
     *  the fn says "not available yet", a field the engine does not know is "—", never 0. */
    Object.assign(L, LANG === 'en' ? {
      cx_title: 'Cancellations — subscriptions and orders', cx_sub: 'managers only', cx_age: 'Kaching read {m} min ago',
      cx_def: 'Monthly cancel rate = subscriptions cancelled in the month ÷ active subscriptions at the start of the month (Kaching). Target = half of last month\'s rate. A month still running is judged by its pace: so far × days in the month ÷ days passed. Healthy below {h}% · excellent below {e}%.',
      cx_loading: 'Counting from Kaching…', cx_unavail: 'Cancellation numbers are not available yet — waiting for the engine update. The rest of the board is not affected.',
      cx_unavail_some: 'Not available yet (engine not updated): {b}', cx_counting: 'Still counting: {b}', cx_err: 'Kaching did not answer: {b}', cx_stale: 'Not refreshed, showing the last numbers: {b}',
      cx_month_h: 'Monthly cancel rate vs the target', cx_upto: '{m} so far', cx_prev: '{m}: {v}', cx_target: 'Target: {v} (half of {m})',
      cx_good: '✓ Below the target', cx_bad: 'Above the target', cx_good_pace: '✓ At this pace: below the target', cx_bad_pace: 'At this pace: above the target',
      cx_pace: 'At this pace: {v} at the end of {m} (day {e} of {n})', cx_lv_excellent: 'Excellent (below {e}%)', cx_lv_healthy: 'Healthy (below {h}%)', cx_lv_high: 'High ({h}% and over)',
      cx_of: '{c} cancelled of {a} active at the start of the month', cx_no_kaching: 'No Kaching connection', cx_no_target: 'No target: last month unknown',
      cx_day_h: 'Cancellations on {d}', cx_today: 'today', cx_without: 'without {b}',
      cx_subs_team: 'Subscriptions the team cancelled', cx_subs_bot: 'Automatic cancellations', cx_orders_cancelled: 'Orders cancelled',
      cx_team_total: 'All cancellations by the team', cx_subs_all_kaching: 'All subscription cancels in Kaching',
      cx_src_team_total: '= subscriptions the team cancelled + orders cancelled',
      cx_s_subs_team: 'Team', cx_s_subs_bot: 'Automatic', cx_s_orders_cancelled: 'Orders', cx_s_team_total: 'Team total', cx_s_subs_all_kaching: 'All Kaching',
      cx_agents_h: 'Per agent on {d}', cx_agent_n: 'Subscriptions cancelled', cx_by_brand: 'By brand', cx_no_agents: 'No agent cancelled a subscription on this day.',
      cx_agents_note: 'Only a cancel made in the system carries an agent\'s name; a cancel made directly in Kaching is counted in "All subscription cancels in Kaching", without a name.',
      cx_days_h: 'Last {n} days', cx_day_col: 'Day', cx_pick_day: 'Show {d}', cx_unnamed: 'Without an agent\'s name: {n}'
    } : {
      cx_title: 'ביטולים — מנויים והזמנות', cx_sub: 'מנהלים בלבד', cx_age: 'נקרא מקאצ׳ינג לפני {m} דק׳',
      cx_def: 'שיעור ביטול חודשי = מנויים שבוטלו בחודש ÷ מנויים פעילים בתחילת החודש (קאצ׳ינג). יעד = חצי מהשיעור של החודש הקודם. חודש שעוד לא נגמר נמדד לפי הקצב: עד היום × ימי החודש ÷ הימים שעברו. בריא מתחת ל-{h}% · מצוין מתחת ל-{e}%.',
      cx_loading: 'סופר מקאצ׳ינג…', cx_unavail: 'נתוני הביטולים עוד לא זמינים — מחכים לעדכון המנוע. שאר הלוח לא מושפע.',
      cx_unavail_some: 'עוד לא זמין (המנוע לא עודכן): {b}', cx_counting: 'עוד סופר: {b}', cx_err: 'קאצ׳ינג לא ענה: {b}', cx_stale: 'לא התעדכן, מוצגים המספרים האחרונים: {b}',
      cx_month_h: 'שיעור ביטול חודשי מול היעד', cx_upto: '{m} עד היום', cx_prev: '{m}: {v}', cx_target: 'יעד: {v} (חצי מ{m})',
      cx_good: '✓ מתחת ליעד', cx_bad: 'מעל היעד', cx_good_pace: '✓ בקצב הזה: מתחת ליעד', cx_bad_pace: 'בקצב הזה: מעל היעד',
      cx_pace: 'בקצב הזה: {v} בסוף {m} (יום {e} מתוך {n})', cx_lv_excellent: 'מצוין (מתחת ל-{e}%)', cx_lv_healthy: 'בריא (מתחת ל-{h}%)', cx_lv_high: 'גבוה ({h}% ומעלה)',
      cx_of: 'בוטלו {c} מתוך {a} פעילים בתחילת החודש', cx_no_kaching: 'אין חיבור לקאצ׳ינג', cx_no_target: 'אין יעד: החודש הקודם לא ידוע',
      cx_day_h: 'ביטולים ב-{d}', cx_today: 'היום', cx_without: 'בלי {b}',
      cx_subs_team: 'מנויים שהצוות ביטל', cx_subs_bot: 'ביטולים אוטומטיים', cx_orders_cancelled: 'הזמנות שבוטלו',
      cx_team_total: 'סה״כ ביטולים שהצוות עשה', cx_subs_all_kaching: 'כל ביטולי המנויים בקאצ׳ינג',
      cx_src_team_total: '= מנויים שהצוות ביטל + הזמנות שבוטלו',
      cx_s_subs_team: 'הצוות', cx_s_subs_bot: 'אוטומטי', cx_s_orders_cancelled: 'הזמנות', cx_s_team_total: 'סה״כ צוות', cx_s_subs_all_kaching: 'כל קאצ׳ינג',
      cx_agents_h: 'לפי נציג ב-{d}', cx_agent_n: 'מנויים שביטל', cx_by_brand: 'לפי מותג', cx_no_agents: 'אף נציג לא ביטל מנוי ביום הזה.',
      cx_agents_note: 'רק ביטול שנעשה במערכת נושא שם נציג; ביטול ישירות בקאצ׳ינג נספר ב"כל ביטולי המנויים בקאצ׳ינג" בלי שם.',
      cx_days_h: '{n} הימים האחרונים', cx_day_col: 'יום', cx_pick_day: 'להציג את {d}', cx_unnamed: 'בלי שם נציג: {n}'
    });
    const CX_FIELDS = ['subs_team', 'subs_bot', 'orders_cancelled', 'team_total', 'subs_all_kaching'];
    const cx = { el: null, data: null, sig: '', pick: '', brand: 'all', busy: false, err: null, again: null };
    function cxStrip() {
      if (!cx.el) cx.el = h('section', { class: 'dash-cx', id: 'dash-cx', 'data-test': 'cx', 'aria-live': 'polite' });
      paintCx();
      return cx.el;
    }
    function cxN(v) { return v === null || v === undefined ? '—' : String(v); }
    function cxPct(v) { return v === null || v === undefined ? '—' : Number(v).toFixed(1) + '%'; }
    function cxMonth(ym) {
      if (!ym || !/^\d{4}-\d{2}$/.test(ym)) return '—';
      return new Intl.DateTimeFormat(LANG === 'en' ? 'en-GB' : 'he-IL', { month: 'long', timeZone: 'UTC' }).format(new Date(Date.UTC(+ym.slice(0, 4), +ym.slice(5, 7) - 1, 1)));
    }
    function cxDay(dd) {
      const p = dd.split('-');
      const wd = new Intl.DateTimeFormat(LANG === 'en' ? 'en-GB' : 'he-IL', { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])));
      return wd + ' ' + (+p[2]) + '.' + (+p[1]);
    }
    function cxMonthCard(b, o, x) {
      const card = h('div', { class: 'cx-mcard', 'data-test': 'cx-month', 'data-brand': b }, h('div', { class: 'l' }, h('bdi', { text: brandName(b) })));
      if (o.state === 'no_kaching') { card.classList.add('na'); card.append(h('div', { class: 'cx-state', 'data-test': 'cx-month-state', text: L.cx_no_kaching })); return card; }
      if (!o.month || (o.month.churn_pct === null && o.state !== 'ok')) {
        card.classList.add('na');
        card.append(h('div', { class: 'cx-state', 'data-test': 'cx-month-state', text: o.state === 'not_deployed' ? d('cx_unavail_some', { b: brandName(b) }) : o.state === 'error' ? d('cx_err', { b: brandName(b) }) : L.cx_loading }));
        return card;
      }
      const m = o.month, pm = o.prev_month || {};
      if (o.verdict) card.classList.add(o.verdict);
      add(card, [h('div', { class: 'v', 'data-test': 'cx-churn', text: cxPct(m.churn_pct) }),
        h('div', { class: 'small', text: m.partial ? d('cx_upto', { m: cxMonth(m.month) }) : cxMonth(m.month) }),
        o.projected !== null && o.projected !== undefined ? h('div', { class: 'small cx-pace', 'data-test': 'cx-pace', text: d('cx_pace', { v: cxPct(o.projected), m: cxMonth(m.month), e: o.days_elapsed, n: o.days_in_month }) }) : null,
        h('div', { class: 'small', 'data-test': 'cx-prev', text: d('cx_prev', { m: cxMonth(pm.month), v: cxPct(pm.churn_pct) }) }),
        h('div', { class: 'small cx-target', 'data-test': 'cx-target', text: o.target === null ? L.cx_no_target : d('cx_target', { v: cxPct(o.target), m: cxMonth(pm.month) }) }),
        o.verdict ? h('div', { class: 'chip ' + (o.verdict === 'good' ? 'ok' : 'bad'), 'data-test': 'cx-verdict', text: L['cx_' + o.verdict + (o.projected !== null && o.projected !== undefined ? '_pace' : '')] }) : null,
        o.level ? h('div', { class: 'muted small', 'data-test': 'cx-level', text: d('cx_lv_' + o.level, { h: x.healthy_pct, e: x.excellent_pct }) }) : null,
        m.cancelled !== null && m.active_start !== null ? h('div', { class: 'muted small', text: d('cx_of', { c: m.cancelled, a: m.active_start }) }) : null]);   // add(), not append(): append(null) prints "null"
      return card;
    }
    function paintCx() {
      if (!cx.el) return;
      const x = cx.data;
      const sig = JSON.stringify([x && Object.assign({}, x, { at: 0 }), cx.brand, cx.err]);
      if (sig === cx.sig && cx.el.firstChild) return;
      cx.sig = sig;
      clear(cx.el);
      const ages = x ? Object.keys(x.brands).map(function (b) { return x.brands[b].at; }).filter(function (v) { return typeof v === 'number'; }) : [];
      cx.el.append(h('div', { class: 'live-head' }, h('h3', { text: '🚫 ' + L.cx_title }), h('span', { class: 'muted small', text: L.cx_sub }),
        ages.length ? h('span', { class: 'muted small', 'data-test': 'cx-age', text: d('cx_age', { m: Math.max(0, Math.round((x.at - Math.min.apply(null, ages)) / 60)) }) }) : null));
      cx.el.append(h('div', { class: 'muted small cx-def', 'data-test': 'cx-def', text: d('cx_def', { h: x ? x.healthy_pct : 12, e: x ? x.excellent_pct : 8 }) }));
      if (cx.err) cx.el.append(h('div', { class: 'err-box', role: 'alert', 'data-test': 'cx-err', text: cx.err }));
      if (!x) { cx.el.append(h('div', { class: 'muted small', text: L.cx_loading }), h('div', { class: 'skeleton' })); return; }
      const all = Object.keys(x.brands);
      if (!all.length && !x.unavailable.length) return;
      if (all.length && all.every(function (b) { return x.brands[b].state === 'not_deployed'; })) {
        cx.el.append(h('div', { class: 'note-box warn', role: 'status', 'data-test': 'cx-unavailable', text: L.cx_unavail }));
        return;
      }
      const names = function (pred) { return all.filter(function (b) { return pred(x.brands[b]); }).map(brandName).join(', '); };
      const notes = [['cx_unavail_some', function (o) { return o.state === 'not_deployed'; }, 'chip outline'],
        ['cx_counting', function (o) { return o.busy && !Object.keys(o.rows || {}).length; }, 'chip outline'],
        ['cx_err', function (o) { return o.state === 'error' && !Object.keys(o.rows || {}).length; }, 'chip warn-chip'],
        ['cx_stale', function (o) { return o.error && Object.keys(o.rows || {}).length; }, 'chip warn-chip']];
      notes.forEach(function (n) { const v = names(n[1]); if (v) cx.el.append(h('div', { class: n[2] + ' cx-note', 'data-test': 'cx-note', text: d(n[0], { b: v }) })); });
      // A. this month vs the target, per brand
      cx.el.append(h('h4', { text: L.cx_month_h }));
      const mrow = h('div', { class: 'cx-months' });
      all.forEach(function (b) { mrow.append(cxMonthCard(b, x.brands[b], x)); });
      cx.el.append(mrow);
      const churnSrc = x.sources.churn_pct || x.sources.churn || x.sources.month;
      if (churnSrc) cx.el.append(h('div', { class: 'muted small cx-src', 'data-test': 'cx-src-churn', dir: 'auto', text: churnSrc }));
      const withRows = all.filter(function (b) { return Object.keys(x.brands[b].rows || {}).length; });
      if (!withRows.length) return;
      // B. the chosen day: totals over the brands, per brand, per agent
      const day = x.day, T = x.total[day] || {};
      const dayName = cxDay(day) + (day === x.dates[0] ? ' (' + L.cx_today + ')' : '');
      cx.el.append(h('h4', { 'data-test': 'cx-day-title', text: d('cx_day_h', { d: dayName }) }));
      const cards = h('div', { class: 'cx-cards' });
      CX_FIELDS.forEach(function (k) {
        const miss = T[k + '_missing'] || [];
        const src = k === 'team_total' ? L.cx_src_team_total : x.sources[k];
        cards.append(h('div', { class: 'cx-card' + (k === 'team_total' ? ' total' : ''), 'data-test': 'cx-' + k },
          h('div', { class: 'v', text: cxN(T[k]) }), h('div', { class: 'l', text: L['cx_' + k] }),
          miss.length ? h('div', { class: 'small cx-miss', 'data-test': 'cx-miss', text: d('cx_without', { b: miss.map(brandName).join(', ') }) }) : null,
          src ? h('div', { class: 'muted small cx-src', 'data-test': 'cx-src', dir: 'auto', text: src }) : null));     // the engine writes these in Hebrew
      });
      cx.el.append(cards);
      if (withRows.length > 1) {
        const tb = h('table', { class: 'dash-table', 'data-test': 'cx-brand-table' }, h('thead', null, h('tr', null,
          [L.brand_col].concat(CX_FIELDS.map(function (k) { return L['cx_s_' + k]; })).map(function (c) { return h('th', { text: c }); }))));
        const body = h('tbody');
        withRows.forEach(function (b) {
          const r = x.brands[b].rows[day] || {};
          body.append(h('tr', { 'data-brand': b }, h('td', null, h('bdi', { text: brandName(b) })),
            CX_FIELDS.map(function (k) { return h('td', { 'data-k': k }, k === 'team_total' ? h('b', { text: cxN(r[k]) }) : cxN(r[k])); })));
        });
        tb.append(body);
        cx.el.append(h('div', { class: 'table-wrap' }, tb));
      }
      cx.el.append(h('h4', { 'data-test': 'cx-agents-title', text: d('cx_agents_h', { d: dayName }) }));
      if (!x.agents.length) cx.el.append(h('div', { class: 'muted', 'data-test': 'cx-no-agents', text: L.cx_no_agents }));
      else {
        const tb = h('table', { class: 'dash-table', 'data-test': 'cx-agents' }, h('thead', null, h('tr', null, [L.agent, L.cx_agent_n, L.cx_by_brand].map(function (c) { return h('th', { text: c }); }))));
        const body = h('tbody');
        x.agents.forEach(function (a) {
          body.append(h('tr', { 'data-test': 'cx-agent', 'data-user': a.user }, h('td', null, h('bdi', { text: a.name })), h('td', null, h('b', { 'data-test': 'cx-agent-n', text: String(a.n) })),
            h('td', { class: 'muted small', text: Object.keys(a.by_brand).map(function (b) { return brandName(b) + ' ' + a.by_brand[b]; }).join(' · ') })));
        });
        tb.append(body);
        cx.el.append(h('div', { class: 'table-wrap' }, tb));
      }
      if (x.unnamed) cx.el.append(h('div', { class: 'small', 'data-test': 'cx-unnamed', text: d('cx_unnamed', { n: x.unnamed }) }));
      cx.el.append(h('div', { class: 'muted small cx-src', text: L.cx_agents_note }));
      // C. the last 14 days (one brand or all); a day is a button that shows that day above
      const sel = h('select', { 'aria-label': L.brand_col, 'data-test': 'cx-brand-sel' }, h('option', { value: 'all', text: L.all_brands }),
        withRows.map(function (b) { return h('option', { value: b, text: brandName(b), selected: cx.brand === b ? 'selected' : null }); }));
      sel.addEventListener('change', function () { cx.brand = sel.value; paintCx(); });
      if (cx.brand !== 'all' && withRows.indexOf(cx.brand) < 0) cx.brand = 'all';
      cx.el.append(h('div', { class: 'cx-days-head' }, h('h4', { text: d('cx_days_h', { n: x.dates.length }) }), sel));
      const tb = h('table', { class: 'dash-table cx-days', 'data-test': 'cx-days' }, h('thead', null, h('tr', null,
        [L.cx_day_col].concat(CX_FIELDS.map(function (k) { return L['cx_s_' + k]; })).map(function (c) { return h('th', { text: c }); }))));
      const body = h('tbody');
      x.dates.forEach(function (dd) {
        const r = cx.brand === 'all' ? (x.total[dd] || {}) : ((x.brands[cx.brand] || {}).rows || {})[dd] || {};
        body.append(h('tr', { class: dd === day ? 'on' : null, 'data-test': 'cx-day', 'data-day': dd },
          h('td', null, h('button', { type: 'button', class: 'linkish', 'data-test': 'cx-day-btn', 'aria-label': d('cx_pick_day', { d: dd }), 'aria-pressed': dd === day ? 'true' : 'false',
            text: cxDay(dd), onclick: function () { cx.pick = dd; loadCx(); } })),
          CX_FIELDS.map(function (k) { return h('td', { 'data-k': k }, k === 'team_total' ? h('b', { text: cxN(r[k]) }) : cxN(r[k])); })));
      });
      tb.append(body);
      cx.el.append(h('div', { class: 'table-wrap' }, tb));
    }
    async function loadCx() {
      if (!S.me.is_admin) return;
      const want = cx.pick || st.date || '';
      cx.want = want;
      let r;
      try { r = await api('/api/dash/cancels' + (want ? '?date=' + encodeURIComponent(want) : ''), undefined, 'GET', { quiet: true }); } catch (e) { r = null; }
      if (cx.want !== want) return;                     // another day was chosen meanwhile
      if (r && r.ok) { cx.data = r; cx.err = null; } else cx.err = (r && (r.msg || r.error)) || L.cx_err.replace('{b}', '');
      if (S.view === 'dash') paintCx();
      clearTimeout(cx.again);
      if (r && r.ok && r.busy) cx.again = setTimeout(function () { if (S.view === 'dash' && !document.hidden) loadCx(); }, 4000);   // a brand is still counting
    }
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
      const list = all.filter(function (a) { return a.active_s || a.sends || a.closes || a.engine_sends || a.engine_closes || a.ds_answered || a.snoozed_now; });
      const idle = all.length - list.length;
      const wrap = h('div', { class: 'table-wrap' });
      if (idle) wrap.append(h('div', { class: 'muted small idle-note', text: d('idle_agents', { n: idle }) }));
      if (!list.length) { wrap.append(h('div', { class: 'muted', text: L.none })); return wrap; }
      const tb = h('table', { class: 'dash-table', 'data-test': 'dash-agents' });
      tb.append(h('thead', null, h('tr', null, [L.agent, L.conv_answered, L.active, L.on_screen, L.replies, L.closes, L.per_hour, 'AHT', L.occ, L.snoozed].map(function (x) { return h('th', { text: x }); }))));
      const hm = function (sec) { return sec ? new Date(sec * 1000).toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'he-IL', { timeZone: 'Asia/Jerusalem', hour: '2-digit', minute: '2-digit' }) : ''; };
      const shiftTxt = function (x) { return x && x.first ? hm(x.first) + '–' + hm(x.last) + (x.breaks_s ? ' · ' + d('breaks', { t: fmtS(x.breaks_s) }) : '') : ''; };
      const body = h('tbody');
      list.forEach(function (a) {
        const tr = h('tr', { 'data-test': 'dash-agent', 'data-user': a.user },
          h('td', null, h('bdi', { text: a.name })),
          h('td', { 'data-test': 'ag-conv' }, h('b', { text: a.ds_answered === null || a.ds_answered === undefined ? '—' : String(a.ds_answered) })),
          h('td', { 'data-test': 'ag-active' }, h('b', { text: fmtS(a.active_s) }),
            a.shift ? h('div', { class: 'muted small', 'data-test': 'ag-shift' }, h('bdi', { text: shiftTxt(a.shift) })) : null),
          h('td', { 'data-test': 'ag-screen', text: fmtS(a.screen_s) }),
          h('td', { 'data-test': 'ag-replies' }, h('b', { text: String(Math.max(a.sends, a.engine_sends)) }),
            h('span', { class: 'muted small', text: ' (' + L.engine + ' ' + a.engine_sends + ' · ' + L.log_word + ' ' + a.sends + ')' })),
          h('td', null, h('b', { text: String(Math.max(a.closes, a.engine_closes)) }),
            h('span', { class: 'muted small', text: ' (' + L.engine + ' ' + a.engine_closes + ' · ' + L.log_word + ' ' + a.closes + ')' })),
          h('td', { text: a.per_hour === null ? '—' : String(a.per_hour) }),
          h('td', { text: fmtS(a.aht_s) }),
          h('td', { text: a.occupancy === null ? '—' : Math.round(a.occupancy * 100) + '%' }),
          h('td', { 'data-test': 'ag-snoozed', text: String(a.snoozed_now || 0) }));      // "לענות מאוחר יותר" (2026-10-14): hidden from HIS list now
        body.append(tr);
        const det = h('details', { class: 'ag-det' }, h('summary', { text: L.by_brand + ' · ' + L.by_channel + ' · ' + L.per_day }));
        const part = function (obj, kind) {
          return h('ul', { class: 'mini' }, Object.keys(obj || {}).map(function (k) {
            return h('li', null, h('bdi', { text: nameOf(kind, k) }), ': ' + fmtS(obj[k].active_s) + ' · ' + obj[k].sends + ' ' + L.replies + ' · ' + obj[k].closes + ' ' + L.closes);
          }));
        };
        det.append(part(a.by_brand, 'brand'), part(a.by_channel, 'channel'));
        if (a.days.length > 1) det.append(h('ul', { class: 'mini' }, a.days.map(function (x) {
          return h('li', null, x.day + ': ' + fmtS(x.active_s) + ' · ' + L.on_screen + ' ' + fmtS(x.screen_s) + ' · ' + x.sends + ' ' + L.replies,
            x.first ? h('span', { class: 'muted small' }, ' · ', h('bdi', { text: shiftTxt(x) })) : null);
        })));
        if (a.resends) det.append(h('div', { class: 'muted small', text: a.resends + ' ' + L.resends }));
        det.append(h('div', { class: 'muted small', text: L.present + ': ' + fmtS(a.present_s) }));
        body.append(h('tr', { class: 'det-row' }, h('td', { colspan: '9' }, det)));
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
    /** The pane holds two parts: the numbers (rebuilt on every 30 s refresh) and the AI notes card (built once — the 30 s refresh must
     *  never rebuild a textarea a manager is typing in; build-rules §1ב). */
    function parts() {
      const root = $('dash-pane');
      let main = document.getElementById('dash-main');
      if (!main) {
        clear(root);
        main = h('div', { id: 'dash-main' });
        root.append(main, h('div', { id: 'dash-sales', class: 'dash-sales' }), h('div', { id: 'dash-ai' }));
      }
      return { main: main, ai: document.getElementById('dash-ai'), sales: document.getElementById('dash-sales') };
    }
    function render() {
      const p = parts().main;
      clear(p);
      const head = h('div', { class: 'dash-head' }, h('h2', { text: L.title }));
      const rg = h('div', { class: 'seg', role: 'group' });
      [['1', L.day], ['7', L.d7], ['30', L.d30]].forEach(function (x) {
        const b = h('button', { type: 'button', class: 'btn small' + (st.range === x[0] ? ' on' : ''), 'aria-pressed': st.range === x[0] ? 'true' : 'false', text: x[1], 'data-test': 'range-' + x[0] });
        b.addEventListener('click', function () { st.range = x[0]; st.data = null; render(); load(); });   // never old numbers under a new choice
        rg.append(b);
      });
      const di = h('input', { type: 'date', value: st.date || st.shown || '', max: st.shown || null, 'aria-label': 'date', 'data-test': 'dash-date' });
      di.addEventListener('change', function () { st.date = di.value; st.data = null; cx.pick = ''; render(); load(); loadCx(); });
      head.append(rg, di);
      if (S.me.is_admin) head.append(h('button', { type: 'button', class: 'btn small ghost', 'data-test': 'ai-notes-jump', text: t('ain_jump'),
        onclick: function () { const c = document.getElementById('ai-notes'); if (c) c.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }));
      if (st.data) head.append(h('b', { class: 'shown-day', 'data-test': 'dash-shown', text: st.data.days.length > 1 ? st.data.days[0] + ' – ' + st.data.end_day : st.data.end_day }));
      if (st.data) head.append(h('span', { class: 'muted small', 'data-test': 'dash-updated', text: L.updated + ' ' + new Date(st.data.generated_at * 1000).toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'he-IL') }));
      p.append(head, liveStrip());
      if (S.me.is_admin) p.append(cxStrip());          // cancellations (2026-10-23): admins only, like the sales table
      if (st.err) p.append(h('div', { class: 'err-box', text: st.err }));
      const x = st.data;
      if (!x) { p.append(h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })); return; }
      if (x.stats_source === 'mixed') p.append(h('div', { class: 'note-box warn', role: 'status', 'data-test': 'dash-missing',
        text: '⚠️ ' + d('missing', { b: Object.keys(x.missing_ds || {}).map(brandName).join(', ') }) }));
      if (x.stats_source === 'list') p.append(h('div', { class: 'err-box dash-fixing', role: 'alert', 'data-test': 'dash-fixing' },
        h('b', { text: '⚠️ ' + L.fixing }), h('div', { class: 'small', text: L.fixing_sub })));
      if (x.verify_note) p.append(h('div', { class: 'verified', role: 'status', 'data-test': 'dash-verify', text: x.verify_note }));
      p.append(h('div', { class: 'muted small dash-method', 'data-test': 'dash-method', text: d('method', { m: Math.round(x.idle_gap_s / 60), b: Math.round((x.break_gap_s || 1800) / 60) }) + (x.log_since ? ' · ' + d('since', { d: x.log_since }) : '') }));
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
      if (S.me.is_admin) SalesBoard.mount(parts().sales);   // sales log for bonuses (admin only; the proxy answers 403 to anyone else)
      if (S.me.is_admin) AiNotes.mount(parts().ai);       // admin only (the proxy answers 403 to anyone else)
      load();
      loadLive();
      loadCx();
      if (!timer) timer = setInterval(function () { if (S.view === 'dash' && !document.hidden) load(true); }, 30000);
      if (!live.timer) live.timer = setInterval(function () { if (S.view === 'dash' && !document.hidden) { loadLive(); loadCx(); } }, 30000);
    }
    return { show: show, load: load, loadLive: loadLive };
  })();

  /** Typing in a ticket is work: a quiet heartbeat at most once a minute (autosave alone waits for a pause). */
  const EDIT_PING = {};
  function pingEdit(brand, id) {
    const k = brand + '|' + id;
    if (Date.now() - (EDIT_PING[k] || 0) < 60000) return;
    EDIT_PING[k] = Date.now();
    api('/api/' + encodeURIComponent(brand) + '/activity', { id: id, kind: 'edit' }, 'POST', { quiet: true, retry: false });
  }

  /**
   * מילוי מיקודים (Owner, 2026-10-10): one button finds the zip code of every order and hands back the text for the supplier.
   * Backend contract (system-builder): POST /api/<brand>/zipfix {orders: "1646, 1647" | null} → {job};
   * GET /api/<brand>/zipfix/<job> → {state: running|done|error, progress: {done, total}, result}.
   *  - The job id (and, when done, the result) is kept in sessionStorage per brand: a refresh resumes the run, never restarts it.
   *  - Polling (every 2 s) repaints only the status slot; the agent's textarea is never rebuilt under their fingers.
   *  - A dropped poll is not an error: it counts, says "reconnecting" after two, and keeps going. A real refusal stops the run.
   *  - A non-empty box with no order number in it never silently becomes "all open orders".
   */
  const Zip = (function () {
    const HE = {
      title: 'מילוי מיקודים', intro: 'לוחצים פעם אחת — המערכת מוצאת מיקוד לכל הזמנה ומכינה את הטקסט לשליחה לספקית.',
      brand: 'מותג', orders: 'מספרי הזמנות מהספקית (לא חובה)', orders_ph: 'אפשר להדביק כמו שזה הגיע: 1646, 1647 #1650 …',
      p_all: 'ריק — יחפש מיקודים לכל ההזמנות הפתוחות של המותג.', p_some: 'זוהו {n} הזמנות: {list}', p_bad: 'לא זוהה אף מספר הזמנה. מחקו את הטקסט כדי להריץ על כל ההזמנות הפתוחות.',
      go: 'הבא מיקודים', starting: 'מתחיל…', running: 'מחפש מיקודים…', progress: '{d} מתוך {t} הזמנות', progress_0: 'אוסף את ההזמנות…',
      elapsed: 'רץ {s} שנ׳ · אפשר לרענן את הדף, הריצה ממשיכה', conn: 'החיבור לשרת נפל לרגע — ממשיך לנסות…',
      failed: 'הריצה נכשלה', lost: 'הריצה כבר לא נמצאת בשרת (אולי השרת התעדכן). הריצו שוב.', again: 'להריץ שוב', start_failed: 'לא הצלחנו להתחיל',
      c_orders: 'הזמנות', c_zips: 'מיקודים', c_review: 'לבדיקה', c_ask: 'לפנות ללקוח', ran_at: '{b} · הורץ {when}',
      supplier: 'הטקסט לספקית', copy: 'העתק לספקית', copied: 'הועתק ✓', copy_fail: 'ההעתקה נכשלה — סמנו את הטקסט והעתיקו ידנית',
      no_zips: 'לא נמצאו מיקודים לשליחה בריצה הזאת.', review: 'לבדיקה לפני שליחה', review_none: 'אין מה לבדוק — כל המיקודים נמצאו בוודאות.',
      review_note: 'המיקודים האלה כבר בטקסט לספקית. כדאי לוודא אותם באתר דואר ישראל לפני ששולחים.',
      ask: 'לפנות ללקוח', ask_none: 'אין הזמנות שצריך לפנות בהן ללקוח.', ask_note: 'לא נמצא מיקוד — ההזמנות האלה לא בטקסט לספקית. צריך לבקש מהלקוח כתובת מלאה.',
      not_found: 'לא נמצאו בחנות: {list}', order: 'הזמנה', zip: 'מיקוד', verify: 'בדיקה בדואר ישראל ↗', copy_addr: 'העתק כתובת', new_run: 'ריצה חדשה'
    };
    const EN = {
      title: 'Zip-code fill', intro: 'One click: the system finds the zip code of every order and prepares the text for the supplier.',
      brand: 'Brand', orders: 'Order numbers from the supplier (optional)', orders_ph: 'Paste them as they came: 1646, 1647 #1650 …',
      p_all: 'Empty — looks up every open order of the brand.', p_some: '{n} orders found: {list}', p_bad: 'No order number found. Clear the box to run on all open orders.',
      go: 'Get zip codes', starting: 'Starting…', running: 'Finding zip codes…', progress: '{d} of {t} orders', progress_0: 'Collecting the orders…',
      elapsed: 'Running {s} s · you can refresh the page, the run continues', conn: 'Lost the server for a moment — still trying…',
      failed: 'The run failed', lost: 'This run is no longer on the server (it may have restarted). Run it again.', again: 'Run again', start_failed: 'Could not start',
      c_orders: 'Orders', c_zips: 'Zip codes', c_review: 'To check', c_ask: 'Ask customer', ran_at: '{b} · ran {when}',
      supplier: 'Text for the supplier', copy: 'Copy for supplier', copied: 'Copied ✓', copy_fail: 'Copy failed — select the text and copy it by hand',
      no_zips: 'No zip codes to send in this run.', review: 'Check before sending', review_none: 'Nothing to check — every zip code was found with certainty.',
      review_note: 'These zip codes are already in the supplier text. Verify them on the Israel Post site before sending.',
      ask: 'Ask the customer', ask_none: 'No orders need the customer.', ask_note: 'No zip code found — these orders are NOT in the supplier text. Ask the customer for a full address.',
      not_found: 'Not found in the store: {list}', order: 'Order', zip: 'Zip', verify: 'Check on Israel Post ↗', copy_addr: 'Copy address', new_run: 'New run'
    };
    const L = LANG === 'en' ? EN : HE;
    function z(k, v) {
      let s = L[k] !== undefined ? L[k] : k;
      if (v) Object.keys(v).forEach(function (a) { s = s.split('{' + a + '}').join(String(v[a])); });
      return s;
    }
    const POST_URL = 'https://doar.israelpost.co.il/locatezip';
    const POLL_MS = 2000;
    const st = { brand: null, run: null, busy: false, err: null, fails: 0, timer: null, tick: null, seq: 0, typed: {} };

    function key(b) { return 'cs.zipfix.' + b; }
    function readRun(b) {
      try { const v = JSON.parse(sessionStorage.getItem(key(b)) || 'null'); return v && typeof v.job === 'string' ? v : null; } catch (e) { return null; }
    }
    function writeRun(b, v) {
      try { if (v) sessionStorage.setItem(key(b), JSON.stringify(v)); else sessionStorage.removeItem(key(b)); } catch (e) { /* private mode: the run still works, a refresh just loses it */ }
    }
    /** Every digit run, in order, without repeats. "#1646\n1647, 1646" → ['1646', '1647']. */
    function parseOrders(s) {
      const m = String(s || '').match(/\d+/g) || [];
      const seen = {};
      return m.filter(function (x) { if (seen[x]) return false; seen[x] = 1; return true; });
    }
    function stopTimers() { clearTimeout(st.timer); st.timer = null; clearInterval(st.tick); st.tick = null; }
    function el(id) { return document.getElementById(id); }

    function render() {
      const p = $('zip-pane');
      clear(p);
      const mine = S.me.brands;
      p.append(h('h2', { text: '📮 ' + z('title') }), h('p', { class: 'zip-intro', text: z('intro') }));
      const form = h('div', { class: 'card zip-form', 'data-test': 'zip-form' });
      const bwrap = h('div');
      bwrap.append(h('label', { for: 'zip-brand', text: z('brand') }));
      if (mine.length > 1) {
        const sel = h('select', { id: 'zip-brand', 'data-test': 'zip-brand' });
        mine.forEach(function (b) { sel.append(h('option', { value: b.id, text: brandName(b.id) + (b.connected ? '' : ' ·'), selected: b.id === st.brand ? 'selected' : null })); });
        sel.value = st.brand;
        sel.addEventListener('change', function () { go('#/zip/' + encodeURIComponent(sel.value)); });
        bwrap.append(sel);
      } else {
        bwrap.append(h('b', { id: 'zip-brand', 'data-test': 'zip-brand-one', text: brandName(st.brand) }));
      }
      const twrap = h('div');
      const ta = h('textarea', { id: 'zip-orders', class: 'zip-orders', 'data-test': 'zip-orders', rows: '3', spellcheck: 'false', autocomplete: 'off',
        placeholder: z('orders_ph'), 'aria-describedby': 'zip-parse' });
      ta.value = st.typed[st.brand] || '';
      const parse = h('div', { id: 'zip-parse', class: 'zip-parse', 'data-test': 'zip-parse', 'aria-live': 'polite' });
      ta.addEventListener('input', function () { st.typed[st.brand] = ta.value; paintParse(); });
      twrap.append(h('label', { for: 'zip-orders', text: z('orders') }), ta, parse);
      const goBtn = h('button', { id: 'zip-go', class: 'btn primary zip-go', type: 'button', 'data-test': 'zip-go', text: z('go') });
      goBtn.addEventListener('click', start);
      form.append(bwrap, twrap, goBtn);
      p.append(form, h('div', { id: 'zip-status', class: 'zip-status', 'data-test': 'zip-status' }), h('div', { id: 'zip-result', class: 'zip-result', 'data-test': 'zip-result' }));
      paintParse();
      paint();
    }

    function paintParse() {
      const box = el('zip-parse'), ta = el('zip-orders');
      if (!box || !ta) return;
      clear(box);
      const raw = ta.value.trim(), list = parseOrders(raw);
      box.className = 'zip-parse';
      if (!raw) box.append(z('p_all'));
      else if (!list.length) { box.className = 'zip-parse bad'; box.append(z('p_bad')); }
      else {
        const shown = list.slice(0, 12).join(', ') + (list.length > 12 ? ' …' : '');
        const tmpl = z('p_some', { n: list.length }).split('{list}');
        box.append(tmpl[0], h('bdi', { text: shown }), tmpl[1] || '');
      }
    }

    function running() { return !!(st.run && !st.run.result && !st.run.error); }

    /** Status slot + result slot + button state, from st.run. Safe to call on every poll: it never touches the textarea. */
    function paint() {
      const btn = el('zip-go');
      if (btn) { btn.disabled = st.busy || running(); btn.textContent = st.busy ? z('starting') : (running() ? z('running') : z('go')); }
      const s = el('zip-status'), r = el('zip-result');
      if (!s || !r) return;
      clear(s);
      if (st.err) {
        s.append(h('div', { class: 'err-box', role: 'alert', 'data-test': 'zip-error' }, h('b', { text: st.err.title + ' ' }), h('span', { text: st.err.msg }),
          st.err.code ? h('span', { class: 'raw', text: st.err.code }) : null,
          st.err.retry ? h('button', { class: 'btn small', type: 'button', 'data-test': 'zip-again', text: z('again'), onclick: function () { st.err = null; start(); } }) : null));
      }
      if (running()) {
        const pr = st.run.progress || {}, d = Number(pr.done) || 0, tt = Number(pr.total) || 0;
        const bar = h('progress', { 'data-test': 'zip-progress', max: String(tt || 1), 'aria-label': z('running') });
        if (tt) bar.value = Math.min(d, tt);                 // no total yet → indeterminate bar, never a frozen 0%
        const box = h('div', { class: 'card zip-run', role: 'status', 'data-test': 'zip-running' },
          h('div', { class: 'line' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), h('span', { text: z('running') }),
            h('span', { 'data-test': 'zip-count', text: tt ? z('progress', { d: d, t: tt }) : z('progress_0') })),
          bar, h('div', { class: 'sub', id: 'zip-elapsed', 'data-test': 'zip-elapsed' }));
        if (st.fails >= 2) box.append(h('div', { class: 'conn', 'data-test': 'zip-reconnecting', text: z('conn') }));
        s.append(box);
        paintElapsed();
      }
      clear(r);
      if (st.run && st.run.result) r.append(result(st.run.result));
    }
    function paintElapsed() {
      const e = el('zip-elapsed');
      if (e && st.run && st.run.started) e.textContent = z('elapsed', { s: Math.max(0, Math.round((Date.now() - st.run.started) / 1000)) });
    }

    function count(k, v, cls) {
      return h('div', { class: 'zip-count' + (cls && v ? ' ' + cls : ''), 'data-test': 'zip-c-' + k }, h('div', { class: 'v', text: String(v || 0) }), h('div', { class: 'l', text: z('c_' + k) }));
    }
    function result(x) {
      const c = x.counts || {}, review = Array.isArray(x.review) ? x.review : [], ask = Array.isArray(x.ask_customer) ? x.ask_customer : [];
      const text = typeof x.supplier_text === 'string' ? x.supplier_text : '';
      const frag = document.createDocumentFragment();
      frag.append(h('div', { class: 'zip-counts', 'data-test': 'zip-counts' },
        count('orders', c.orders), count('zips', c.zips), count('review', c.review !== undefined ? c.review : review.length, 'warn'),
        count('ask', c.ask !== undefined ? c.ask : ask.length, 'bad')));
      if (x.ran_at || x.brand) {                          // each value isolated: a date inside a Hebrew line must not flip ("14:11 ,10.10.26")
        const meta = h('div', { class: 'zip-meta', 'data-test': 'zip-meta' }), re = /\{(b|when)\}/g, tmpl = z('ran_at');
        const vals = { b: brandName(x.brand || st.brand), when: x.ran_at ? fmtDate(x.ran_at, true) : '—' };
        let last = 0, m;
        while ((m = re.exec(tmpl)) !== null) { meta.append(tmpl.slice(last, m.index), h('bdi', { dir: 'ltr', text: vals[m[1]] })); last = re.lastIndex; }
        meta.append(tmpl.slice(last));
        frag.append(meta);
      }

      const sup = h('div', { class: 'card', 'data-test': 'zip-supplier' }, h('h3', { text: z('supplier') }));
      if (text.trim()) {
        const box = h('textarea', { class: 'zip-text', readOnly: true, 'data-test': 'zip-text', dir: 'ltr', rows: String(Math.min(14, text.split('\n').length + 1)), spellcheck: 'false', 'aria-label': z('supplier') });
        box.value = text;
        const cb = h('button', { class: 'btn primary zip-copy', type: 'button', 'data-test': 'zip-copy', text: '📋 ' + z('copy') });
        let reset = null;
        cb.addEventListener('click', async function () {
          const ok = await copyText(text, null);          // exact text, two paths (Clipboard API, then execCommand)
          clearTimeout(reset);
          cb.textContent = ok ? z('copied') : '📋 ' + z('copy');
          cb.classList.toggle('done', ok);
          if (!ok) { toast(z('copy_fail')); box.focus(); box.select(); }
          reset = setTimeout(function () { cb.textContent = '📋 ' + z('copy'); cb.classList.remove('done'); }, 2500);
        });
        sup.append(box, cb);
      } else sup.append(h('p', { class: 'zip-none', 'data-test': 'zip-no-zips', text: z('no_zips') }));
      const nf = Array.isArray(x.not_found) ? x.not_found.map(String) : [];
      if (nf.length) {
        const parts = z('not_found').split('{list}');
        sup.append(h('p', { class: 'zip-meta', 'data-test': 'zip-not-found' }, parts[0], h('bdi', { text: nf.join(', ') }), parts[1] || ''));
      }
      frag.append(sup);

      const rv = h('div', { class: 'card', 'data-test': 'zip-review' }, h('h3', null, '⚠️ ' + z('review'), h('span', { class: 'chip', text: String(review.length) })));
      if (review.length) {
        rv.append(h('p', { class: 'zip-meta', text: z('review_note') }));
        const list = h('div', { class: 'zip-items' });
        review.forEach(function (it) { list.append(item(it, 'review')); });
        rv.append(list);
      } else rv.append(h('p', { class: 'zip-none', text: z('review_none') }));
      frag.append(rv);

      const ak = h('div', { class: 'card', 'data-test': 'zip-ask' }, h('h3', null, '📞 ' + z('ask'), h('span', { class: 'chip', text: String(ask.length) })));
      if (ask.length) {
        ak.append(h('p', { class: 'zip-meta', text: z('ask_note') }));
        const list = h('div', { class: 'zip-items' });
        ask.forEach(function (it) { list.append(item(it, 'ask')); });
        ak.append(list);
      } else ak.append(h('p', { class: 'zip-none', text: z('ask_none') }));
      frag.append(ak);

      const again = h('button', { class: 'btn', type: 'button', 'data-test': 'zip-new', text: z('new_run') });
      again.addEventListener('click', function () { writeRun(st.brand, null); st.run = null; st.err = null; paint(); const ta = el('zip-orders'); if (ta) ta.focus(); });
      frag.append(h('div', null, again));
      return frag;
    }
    function item(it, kind) {
      const s = function (v) { return v === null || v === undefined ? '' : String(v); };
      const addr = [s(it.address), s(it.city)].filter(Boolean).join(', ');
      const top = h('div', { class: 'zi-head' }, h('span', null, z('order') + ' ', h('bdi', { class: 'ltr', 'data-test': 'zip-order' }, orderLink(st.brand, s(it.order), null))));
      if (kind === 'review') top.append(h('span', null, z('zip') + ' ', h('bdi', { class: 'ltr', 'data-test': 'zip-zip', text: s(it.zip) })));
      const row = h('div', { class: 'zip-item ' + kind, 'data-test': 'zip-' + kind + '-item', 'data-order': s(it.order) }, top);
      if (kind === 'review' && s(it.reason)) row.append(h('div', { class: 'reason', 'data-test': 'zip-reason', text: s(it.reason) }));
      row.append(h('div', { class: 'addr', 'data-test': 'zip-addr' }, h('bdi', { text: addr || '—' })));
      const acts = h('div', { class: 'acts' });
      if (kind === 'review') acts.append(h('a', { class: 'btn small', href: POST_URL, target: '_blank', rel: 'noopener noreferrer', 'data-test': 'zip-verify', text: z('verify') }));
      if (addr) {
        const cb = h('button', { class: 'btn small', type: 'button', text: z('copy_addr') });
        cb.addEventListener('click', async function () { const ok = await copyText(addr, null); cb.textContent = ok ? z('copied') : z('copy_addr'); setTimeout(function () { cb.textContent = z('copy_addr'); }, 1600); });
        acts.append(cb);
      }
      row.append(acts);
      return row;
    }

    async function start() {
      if (st.busy || running()) return;
      const ta = el('zip-orders');
      const raw = ta ? ta.value.trim() : '';
      const list = parseOrders(raw);
      if (raw && !list.length) { paintParse(); if (ta) ta.focus(); return; }   // never turn junk into "all open orders"
      const brand = st.brand;
      st.busy = true; st.err = null; st.fails = 0;
      if (st.run && st.run.result) { st.run = null; writeRun(brand, null); }
      paint();
      const r = await api('/api/' + encodeURIComponent(brand) + '/zipfix', { orders: list.length ? list.join(', ') : null });
      st.busy = false;
      if (brand !== st.brand) return;                    // the agent switched brand meanwhile
      if (!r || !r.ok || typeof r.job !== 'string' || !r.job) {
        st.err = { title: z('start_failed') + ':', msg: (r && r.msg) || t('err_bad_engine'), code: r && r.error };
        paint();
        return;
      }
      st.run = { job: r.job, started: Date.now(), orders: list.length ? list.join(', ') : null, progress: { done: 0, total: list.length || 0 } };
      writeRun(brand, st.run);
      paint();
      follow();
    }

    function follow() {
      stopTimers();
      if (!running()) return;
      st.tick = setInterval(paintElapsed, 1000);
      poll();
    }
    async function poll() {
      const brand = st.brand, run = st.run;
      if (!run || !running() || S.view !== 'zip') return;
      const seq = ++st.seq;
      const r = await api('/api/' + encodeURIComponent(brand) + '/zipfix/' + encodeURIComponent(run.job), undefined, 'GET', { quiet: true, retry: false });
      if (seq !== st.seq || st.run !== run || brand !== st.brand || S.view !== 'zip') return;
      if (r && (r.error === 'server_restarting' || r.error === 'server_restarted')) {
        st.fails++;                                      // a deploy blip: keep the run, say so after two misses, try again
      } else if (!r || !r.ok) {
        writeRun(brand, null);
        st.run = null;
        st.err = { retry: true, title: z('failed') + ':', msg: (r && (r.error === 'job_not_found' || r.error === 'not_found')) ? z('lost') : ((r && r.msg) || t('err_bad_engine')), code: r && r.error };
      } else if (r.state === 'done' && r.result && typeof r.result === 'object') {
        st.fails = 0;
        run.progress = r.progress || run.progress;
        run.result = r.result;
        writeRun(brand, run);
      } else if (r.state === 'error') {
        writeRun(brand, null);
        st.run = null;
        const e = r.result && typeof r.result === 'object' ? r.result : {};
        st.err = { retry: true, title: z('failed') + ':', msg: r.msg || e.msg || r.message || e.error || r.error || t('err_bad_engine'), code: r.error && r.msg ? r.error : null };
      } else {
        st.fails = 0;
        if (r.progress && typeof r.progress === 'object') run.progress = r.progress;
        writeRun(brand, run);
      }
      paint();
      if (running()) st.timer = setTimeout(poll, POLL_MS); else stopTimers();
    }
    function show(brand) {
      $('zip-pane').hidden = false;
      if (brand !== st.brand) { stopTimers(); st.err = null; st.busy = false; st.fails = 0; }
      st.brand = brand;
      st.run = readRun(brand);
      render();
      if (running()) follow();
    }
    function leave() { stopTimers(); st.seq++; $('zip-pane').hidden = true; }
    return { show: show, leave: leave, parse: parseOrders };
  })();

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
    Snooze.load();                                     // his snoozed tickets (server-side: the same on every device)
    window.addEventListener('hashchange', route);
    route();
  }
  start();
})();
