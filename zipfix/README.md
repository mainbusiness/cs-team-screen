# zipfix — מילוי מיקודים בסקרין של צוות השירות

Owner, 2026-10-10: "כפתור במסך שירות הלקוחות — קליק אחד עושה הכול ומחזיר את המיקודים לשלוח לספקית".
זה ה-backend. ה-UI (interface-builder) והבוט בוואטסאפ (VPS) צורכים את ה-API למטה.
**מקור הלוגיקה:** `Systems/Zip_Fixer/zipfix.py` — הועתק ללא שינוי בהתנהגות הפתרון
(`parse_street`, `classify`, `resolve`, `fix_bad`, `verify_customer_zip`, `needs_review`).
ההבדלים מהסקריפט שעל המק: הרשאות מ-env, מטמון דיסק חסום, מצב ריצה פר-thread, `run_brand()` שמחזיר מבנה
במקום קבצים, בידוד שגיאה פר-הזמנה, תפוגת טוקן Shopify, רשימת מארחים מותרים ליציאה.

## API (קבוע — שני הצרכנים בנויים עליו)

| route | auth | מה |
|---|---|---|
| `POST /api/<brand>/zipfix` | סשן + CSRF + גישה למותג, תפקיד admin/agent | `{"orders":"1646, 1647"}` או `{"orders":null}` (= כל הפתוחות הלא-ממומשות). → `{"ok":true,"job":id,"reused":bool}` |
| `GET /api/<brand>/zipfix/<job>` | כנ"ל, והג'וב חייב להיות של אותו מותג | `{"ok":true,"state":"running\|done\|error","progress":{"done","total"},"result":{...}}` |
| `POST /bot/zipfix` | header `X-Zipbot-Token` (= `ZIPBOT_SECRET`), בלי סשן/CSRF | `{"brand","orders"}` — אותו מודל |
| `GET /bot/zipfix/<job>[?brand=x]` | אותו header | אותו מבנה; `?brand=` אופציונלי ננעל למותג |

`result` = `supplier_text` (**הטקסט היחיד לשליחה לספקית**: שורות `1646 - 1794000` ממוינות לפי מספר הזמנה, ואחריהן בלוקי
`Order #N address:`), `review[]` `{order,zip,reason,city,address,note}` (נשלח, כדאי להעיף עין — **לא** לספקית),
`ask_customer[]` `{order,city,address}`, `counts{orders,zips,review,ask}` (orders = הזמנות שנבדקו, zips = שורות בטקסט הספקית),
`not_found[]` (מספרים שביקשו ולא נמצאו בחנות), `brand`, `ran_at`.
הזמנה שהעיבוד שלה קרס נכנסת ל-`review` עם `zip:null` והסיבה "שגיאה בעיבוד ההזמנה" — לעולם לא נעלמת בשקט.

שגיאות: `{"ok":false,"error":code,"msg":עברית}` — `bad_orders`/`orders_required` 400 · `busy` 429 (שתי ריצות כבר רצות) ·
`rate_limited` 429 · `forbidden_brand`/`forbidden_role` 403 · `job_not_found` 404 · `brand_unsupported` 404 · `not_configured` 503 ·
`bot_unauthorized` 401 · `bot_disabled` 503. מפתח `orders` חייב להופיע: חסר ⇒ 400 (לא "כל ההזמנות").

## איך זה רץ
- ג'וב = thread אחד, לכל היותר 2 במקביל. אותו מותג + אותה קבוצת הזמנות בזמן שהוא רץ ⇒ מחזירים את אותו ג'וב.
- תוצאה: קובץ JSON ב-`/var/data/zipfix-jobs/` (0600, כתיבה אטומית), נשמר 24 שעות. **כולל כתובות** — לכן רק על הדיסק.
- ריסטארט באמצע ריצה ⇒ בעלייה הבאה הרשומה נסגרת כ-`interrupted`.
- מטמון דפי המקורות: `/var/data/zipfix-cache/cache.zfc`, דחוס, חסום ל-64MB (`ZIPFIX_CACHE_MAX_MB`, 8–512), מפנה ישן-ראשון,
  נכתב לכל היותר פעם בדקה ובסוף ריצה. ריצה קרה על כל הפתוחות ≈ 9 דק'; חמה ≈ דקה.
- אודיט: כל ריצה נרשמת ב-`users-audit.jsonl` (`zipfix_run` / `zipfix_done`) עם משתמש, מותג, מספר הזמנות, ספירות. **אף פעם לא כתובת.**
- יציאה רק למארחים: liors.co.il, zips.co.il, data.gov.il, postalcode.48shops.com, html.duckduckgo.com, *.myshopify.com (https בלבד, גם בהפניות).
- Shopify: **קריאה בלבד** (`read_orders`+`read_customers`), client-credentials, API 2026-10. אין שום mutation בקוד.

## הגדרה (Render env — מ-Keychain `cs-engine` דרך `deploy/render_deploy.py` / `deploy/zipfix_deploy.py env`)
`SHOPIFY_CLIENT_ID_<BRAND>` + `SHOPIFY_CLIENT_SECRET_<BRAND>` ל-VELORA, ROZELA, CELESTA, APEXMEN, SELERA ·
`ZIPBOT_SECRET` (40 תווים; Keychain `cs-engine` חשבון `all/ZIPBOT_SECRET`) · `ZIPFIX_CACHE_DIR` · אופציונלי `ZIPFIX_JOBS_DIR`.
בלי `ZIPBOT_SECRET` (או קצר מ-32) מסלול הבוט עונה 503. מותג בלי פרטי חיבור ⇒ 503 `not_configured`, לא ריצה ריקה.
⛔ התיקייה `lookups/` לא נקראת `data/`: ה-push של `render_deploy.py` מתעלם מכל תיקייה בשם `data`.

## בדיקות
- `pytest tests/test_zipfix.py` — offline (ללא רשת/Shopify): API, הרשאות, בוט, 2-בו-זמנית, dedupe, אודיט בלי כתובות, פורמט הפלט, מטמון.
- `python3 -m zipfix.selftest` (מתוך `team_screen/`, **צריך רשת**) — אותה בדיקת רגרסיה של `Zip_Fixer/selftest.py` (55 מקרים) על הקוד שנשלח.
  מריצים אחרי כל שינוי ב-`core.py`. כל מקרה מוכח מול מיקוד שלקוח הזין / הרשימה של גיא.
- השוואה מול המק: `python3 -m zipfix.core run --brand velora` מול `Systems/Zip_Fixer/zipfix.py run --brand velora` — פלט זהה.
