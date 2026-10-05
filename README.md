# CS team screen (phase 3)

The one web screen the owner's support team uses to read tickets, edit the AI draft, send it, cancel
subscriptions through the Kaching gate, run the automatic-cancellation queue, and (admins) flip the
system switches. Flask on Render. Hebrew at `/cs`, the same SPA with English UI strings at `/cs/en`.

**It runs on Render, not on the Mac and not on the tailnet.** The team works from outside the owner's
network, and Render cannot reach the Mac. So the HQ rules about `Systems/Inbox/capture.py`,
`HQ_Dashboard/registry.json` and tailnet URLs **do not apply to this app**. Its URL is the
`*.onrender.com` (or custom) domain, and every click it cares about is in its own audit log on the
Render disk and in each engine's `audit` sheet.

## Layout

| file | what |
|---|---|
| `app.py` | Flask factory: login, sessions, CSRF, pages, `/api/<brand>/<fn>` proxy, user manager API |
| `engine_proxy.py` | fn allowlist + roles (mirror of `engine/Api.gs apiTable_`), argument allowlist, token mint, HTTP forward |
| `security.py` | PBKDF2 hashing, login rate limiter, engine token minting |
| `users_store.py` | users JSON on the disk (flock + temp + fsync + rename, 0600) and the JSON-lines audit log |
| `messages.py` | every Hebrew/English message, incl. Kaching gate + `draftProblem` + auto-cancel/settings error codes |
| `mock_engine.py` | fake engines for local preview (verifies the real token with a port of `verifyToken_`) |
| `manage.py` | CLI: `add-user`, `reset-password`, `disable`, `enable`, `list`, `seed-team` |
| `templates/`, `static/` | the SPA (vanilla JS, no build step, strict CSP — no inline script or style) |
| `wsgi.py`, `render.yaml`, `requirements*.txt` | deploy |
| `assistant.py` | phase 5: knowledge assistant (`/api/<brand>/assistant`) + English mode (`/translate`, `/translate-out`) |
| `llm.py` | the only Anthropic Messages API client (timeouts, error codes, never logs the key) |
| `mock_llm.py` | deterministic fake Claude for local preview only |
| `ticket_cache.py` | Render-side cache: stale-while-revalidate list + full tickets, prefetch (cap 3), change polling, write-through |
| `tests/` | pytest (220 tests, incl. real-browser tests with Playwright) |
| `tools/screens.py` | mock preview + Playwright screenshots + on-screen checks → `screens/` |

## Environment (Render)

| var | required | what |
|---|---|---|
| `TOKEN_SECRET` | yes | 32+ chars. **Same value** as the `TOKEN_SECRET` Script Property of every brand engine. |
| `ENGINES_JSON` | yes | `{"rozela":"https://script.google.com/macros/s/<id>/exec", "celesta": "...", "apexmen": "..."}`. Only Apps Script `/exec` URLs are accepted (Workspace `/a/macros/<domain>/s/...` too); anything else is dropped and the brand shows "not connected". |
| `SECRET_KEY` | yes | 32+ random chars, Flask session signing. Render-only; never shared with the engines. The app refuses to start without it. |
| `ADMIN_BOOTSTRAP` | first boot only | `username:password` (password 10+ chars). Creates the first admin (admin + user-manager, all brands, must change password) **only if the users file is empty**. **Remove it from the Render environment right after the first boot.** The app ignores it once users exist, logs a warning, and shows admins a red banner while it is still set. |
| `USERS_PATH` | no | default `/var/data/users.json` (the persistent disk). The audit log goes next to it (`users-audit.jsonl`), or to `AUDIT_PATH`. |
| `ANTHROPIC_API_KEY` | phase 5 | Knowledge assistant (`claude-opus-5-5`) and English-mode translation (`claude-sonnet-5-5`). Without it the assistant answers "off" and English mode cannot translate. Render-only. |
| `TICKET_CACHE_DIR` | no | default `/var/data/ticket-cache` (0700, files 0600). In-memory first; the disk copy only makes restarts warm. |
| `TRANSLATE_CACHE_DIR` | no | default `/var/data/translate-cache` (next to the users file). Translations cached by content hash, 30 days. |
| `ASSISTANT_MODEL`, `TRANSLATE_MODEL` | no | override the two model ids. |
| `TRUSTED_PROXY_HOPS` | no | default `1` (Render's proxy). Used for the client IP in the login rate limit. |
| `EXTRA_BRANDS` | no | comma list of extra brand ids the user manager may assign before they have an engine (for example a future brand). |
| `MOCK_ENGINE`, `COOKIE_SECURE`, `MOCK_LATENCY_MS` | local only | preview mode. `MOCK_ENGINE=1` refuses to start if `ENGINES_JSON` is set; `COOKIE_SECURE=0` is refused outside mock mode. |

`render.yaml` declares the four secrets with `sync: false` (no values in the repo), a 1 GB disk at
`/var/data`, health check `/healthz`, and **one** gunicorn worker with 16 threads. One worker is
deliberate: the login rate limiter lives in process memory, and a disk-backed service runs one
instance anyway.

## First deploy

1. Create the service from `render.yaml` and set `TOKEN_SECRET`, `ENGINES_JSON`, `SECRET_KEY`, `ADMIN_BOOTSTRAP`.
2. Open `https://<service>/cs/login`, sign in as the bootstrap admin, and choose a new password.
3. **Delete `ADMIN_BOOTSTRAP`** from the environment (redeploy).
4. Create the team, either in the screen (menu → ניהול משתמשים) or in the Render Shell:
   ```
   python manage.py seed-team
   ```
   This creates four accounts and prints a one-time temporary password for each. Existing ones are skipped:

   | user | roles | brands |
   |---|---|---|
   | `guy` | admin | all |
   | `manager` | admin, user-manager | all |
   | `agent-one` | agent | rozela, velora |
   | `agent-two` | agent | celesta, apexmen |

   Or one at a time: `python manage.py add-user manager --roles admin,user-manager --brands all --name "Manager"`.
   Each user must replace the temporary password at first sign-in. No password is in code or in the repo.

## Security model (short)

- **Auth:** PBKDF2-HMAC-SHA256, 600,000 rounds (the floor is 310k), 16-byte salt per user. Failed logins
  are limited to 5 per username and 20 per IP per 15 minutes. An unknown user, a wrong password and a
  disabled account get the same answer and take the same time.
- **Session:** cookie `__Host-cs`: HttpOnly, Secure, SameSite=Strict, Path=/, no Domain, 12 h absolute.
  The user record is re-read on every request. Disabling a user, a password reset, or a change of
  roles or brands bumps the session version, which ends that user's open sessions.
- **CSRF:** the per-session token must be in `X-CSRF-Token` (API) or the `csrf` form field, and the
  `Origin` header, when sent, must be this site. Referrer-Policy is `same-origin`. **Not**
  `no-referrer`: with that, Chromium sends `Origin: null` on our own form posts and nobody can log in
  (measured in a real browser).
- **Proxy:** the browser never sees an engine URL or a token. Per call it checks: the user holds the
  brand, the fn is on the allowlist, and the user's engine role may call it (the engine re-checks).
  Arguments are rebuilt from a per-fn key list and `args.brand` is forced. The token names **only the
  called brand**, so a mis-wired `ENGINES_JSON` is refused by the engine ("wrong brand"). `apiSettings`
  is admin-only in Flask as well as in the engine, and its `action`/`key`/`value` must come from a fixed
  table. `apiAdminRun` and `apiWa*` are not reachable at all.
- **Roles:** a user may hold several local roles. The token carries the strongest engine role
  (admin > agent > user-manager). A pure user-manager sees only the user manager. Only an admin may
  grant or remove admin, or edit or reset an admin. Nobody may disable themselves or change their own
  roles. At least one active admin must remain.
- **Browser:** strict CSP (`script-src 'self'; style-src 'self'`, no inline). All customer text is set
  via `textContent`. Ticket ids live only in the URL fragment. HTML and API responses are `no-store`.

## Local preview + tests

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/playwright install chromium
.venv/bin/python -m pytest -q tests
.venv/bin/python tools/screens.py        # mock engines, 14 screenshots → screens/, fails on console errors,
                                          # 390px overflow, "[object …]"/"null" on screen, Send enabled in DRY_RUN
```

## API shapes this screen relies on (from `engine/Api.gs` and the coordinator's final shapes, 2026-10-05)

- `apiBoot` → `counts`, `tickets` (summary columns), `dryRun`, `cancelEnabled`, `cancelFrozen`, `brandName`, `serverTime`.
  The top banner uses only these three switches. The AUTO_CANCEL chip comes from `apiAutoCancelList.switch`.
- `apiTicket` → `ticket` (all 31 columns). `apiTicketExtras` → `extras` = the snapshot:
  `{orders, subscriptions, shipping, conversation, lookup, ...}`.
- Related tickets = `apiSearch(email || phone)` minus the current one. Archived hits are display-only,
  because `apiTicket` reads only the live tab.
- `apiKachingCancel` → `{ok, status, message}`, where `message` is the gate's exact English sentence.
  The screen shows the Hebrew translation **and** the raw sentence.
- Auto-cancel: approvable = `shadow_would_cancel | aborted_newer | refused`. In flight (spinner, no
  buttons) = `queued | cancelling | cancelled | replying`. `cancelled_reply_failed` gets a red "send it
  by hand" box. Every other state (`aborted_*`, `failed_*`, `recovered_*`, unknown) shows its error
  and offers only "move to manual handling". The badge counts items that are not in flight.
- `apiSettings` uses `action` (not `op`). A refusal shows the Hebrew line plus the engine's `error`,
  `reason` and `allowed`, verbatim.

## Phase 5 — knowledge assistant + English mode

- **Assistant** (`POST /api/<brand>/assistant {messages, ticketId?}`): same session, CSRF, brand and role gate as the
  proxy, agent and admin roles only. The system prompt is the brand's `apiKnowledge`, cached 10 minutes per brand and
  sent with `cache_control: ephemeral`, plus the rule "answer only about this brand". The two read-only tools are
  `search_customer` (→ `apiCustomerLookup`) and `get_ticket` (→ `apiTicket` + `apiTicketExtras`). Neither has a brand
  argument: both call the brand in the URL, with a token that names only that brand, so another brand's data has no
  path in. `apiKnowledge` and `apiCustomerLookup` are **server-internal**, and the browser route answers 404 for them.
  An open ticket goes in as a second, uncached system block inside `<customer_data>`. Every tool call is audited to
  the disk log with tool, brand, ok, ticket id or query length (never the query text). Limits: 20 messages per user
  per 10 min, 4 tool rounds, ~110 s per turn. If `apiKnowledge` is unavailable, the assistant refuses instead of
  answering from nothing.
- **English mode** (`/cs/en`, users with `lang: en`): the conversation, summary and AI draft are translated to English
  in one Sonnet call with the whole conversation as context, cached on disk per message hash. Each block has a
  "Show original" toggle. The agent writes in English. "Translate for the customer" shows the English and the
  customer-language text side by side, and only "Confirm translation and send" calls `apiSend`, with the
  **translated** text (the engine's `draftProblem` still checks it). Editing the English after translating
  invalidates the review. If the model skips items, the response says `incomplete: n` and the screen shows it.
  The Hebrew UI at `/cs` is unchanged.
- **Brands without subscriptions** (`apiBoot.subscriptions == 'none'`, e.g. selera): no subscriptions panel, no
  auto-cancel tab, no Kaching chip. Both stay hidden until `apiBoot` answers, so they are never shown first.
- **Brands with no engine** (in `EXTRA_BRANDS` but not in `ENGINES_JSON`): a neutral "המותג עוד לא מחובר" state, no
  tabs, no assistant.
- `render.yaml` gunicorn timeout is 150 s, because an assistant turn with tools can take ~1-2 minutes.

## Performance layer (2026-10-05)

Measured live before it: Render answered in 0.2-0.8 s, apiBoot took 2-3 s, and opening a ticket took **17-18 s**.

- `POST /api/<brand>/list` serves the cached list at once and refreshes it in the background if it is older than
  10 s. `POST /api/<brand>/ticket {id}` serves the cached `{ticket, extras}` at once. `{revalidate:true}` goes to the
  engine. `{fresh:true}` (only from the explicit Refresh click) asks the engine to re-read the store and Kaching,
  which is rate-limited there to 30 per 10 min.
- Engine calls: `apiTicketFull` when the engine has it, otherwise `apiTicket` and `apiTicketExtras` **in parallel**.
  "The engine lacks it" is only recorded after the fallback works, so an auth failure never switches it off.
- `POST /api/<brand>/prefetch {ids}`: the first 15 ids of the visible tab. **At most 3 background engine calls run at
  once in the whole process**, enforced by a semaphore that also covers both halves of a fallback pair. A user's own
  click never queues behind prefetch.
- `POST /api/<brand>/changes {since}`: every 20 s from the browser. It uses `apiChanges` (agent/admin, int `since`,
  `removed`, `reset`). If the engine lacks it, on `reset`/`bad_since`, or for user-managers, it does one `apiBoot`
  and diffs here. Only changed rows go back, and the browser merges them in place.
- Writes through the screen patch the cached ticket and list row at once (draft, status, handled_by, counts), mark
  the ticket stale, and revalidate it in the background. A refused write invalidates the ticket.
- Browser: a ticket opened this session paints from memory immediately. Otherwise it comes from the Render cache
  (~200 ms measured with a 1.5 s engine), with a "מתעדכן…" chip until the revalidation lands. If the agent is
  typing, the newer copy is offered ("show") instead of replacing the pane. Draft saves are optimistic: "saved"
  shows in ~5 ms. A refusal rolls the screen's server copy back and shows a sticky error. The agent's text stays
  in the box and in localStorage until the engine confirms.
- Isolation: every cache key starts with the brand, brand and id are regex-checked before any path, the routes use
  the same brand/role gate as the proxy, and per-user fields (user, role, lang) are stripped before a list is cached.
- `Server-Timing` on every `/api/` response: `cache;desc=hit|miss`, `engine;dur` per engine fn, `gas;dur` (the
  engine's `serverMs`), and `app;dur`. Durations and hit/miss only, never data.

## Auto-reply review (Owner, 2026-10-05)

The engine answers easy emails by itself (`AUTO_REPLY`) and marks them handled. A human then checks each one.

- Tab **"נענה אוטומטית — לבדיקה"** (`apiAutoReplyList`). The badge counts `review: pending`. Each card shows the
  customer's question, our reply, and when it was sent, with "🤖 נענה אוטומטית". "✓ נבדק — תקין" takes one click.
  "⚠ בעיה" needs a note of 2-300 chars, checked in Flask before the engine; it reopens the ticket, and the cache
  patches the ticket to `action` at once. Shadow items show "🤖 היה נשלח אוטומטית" with the text and a link to the
  ticket. Items that cannot be sent or reviewed show their error and no buttons. If the engine lacks
  `apiAutoReplyList`, the tab is hidden.
- The 🤖 label appears on list rows and on the ticket header. Matching is tolerant: `handled_by` = auto / auto-reply /
  engine / bot, an `auto_reply` flag, or a sent item in the review list.
- `recommendation` appears as a green "מה לעשות" box at the top of every ticket, as a chip above the draft, and as
  one muted line in list rows.
- System Mode has an **AUTO_REPLY** switch (off / shadow / on, admin only in Flask too), with the note that "on"
  needs test mode off. The top banner shows an auto-reply chip.
- English mode: `/translate` now includes the recommendation. `/translate-rows {ids}` translates the summary and
  recommendation of rows the **server** holds in the brand's cached list. `/translate-autoreply {id}` translates the
  card from the engine's own item (list memoised 30 s). The browser never supplies text to translate; ids are
  deduped, with a 30k-character budget. Both endpoints use the disk cache.

## Deploy resilience (lesson, 2026-10-05)

**The client must survive a server restart. Reads retry; writes never do.**

What happened: the service has a persistent disk, so Render cannot deploy without downtime. During the two
switchovers on 2026-10-04 (22:18 and 22:47-22:48 UTC), Render answered 23 requests with its own 223 KB HTML 502 page
(`/changes`, `/ticket`, `/prefetch`, `/cs/login`). `api()` failed on `r.json()`, and agents saw "תשובה לא תקינה מהשרת".
The app itself logged no 500s and no tracebacks.

The rule, enforced in `api()` in `static/app.js`:
- A **restart** is any answer that is not our JSON: Render's HTML page, an empty body, or a dropped connection.
  Our own JSON 502/504 answers (`engine_timeout`, `engine_bad_response`) are real answers and are shown at once.
- **Reads** (`list`, `changes`, `ticket`, `prefetch`, `apiTicket*`, `apiSearch`, `apiBoot`, the auto-reply/auto-cancel
  lists, `translate*`, the assistant, `/api/me`, `apiSettings` get) retry after 1, 2, 4, 8, 15 and 15 s (~45 s) behind a
  small non-blocking "מתעדכן… / Reconnecting…" pill. Only after that do they say "השרת בעדכון — נסו שוב בעוד דקה".
- **Writes** (send, save draft, handled, close, note, Kaching cancel, auto-cancel/auto-reply review, settings set) are
  **never** re-sent: the request may have landed just before the restart. The agent sees "השרת התעדכן בדיוק ברגע הזה.
  רעננו את הפנייה ובדקו אם הפעולה בוצעה לפני שמנסים שוב."
- The 20 s **poller** makes one quiet attempt per tick. On a restart it keeps the last good list and tries again next
  tick, with no pill and no message. Prefetch, background revalidation and list translation are quiet too.
- Proof: `tests/test_resilience_browser.py` runs real Chromium, with Playwright injecting Render's HTML 502:
  - a read that fails twice then loads, showing no error;
  - a send that fails, with exactly one request and the "check first" message;
  - a silent poller;
  - our own JSON 504, shown once and not retried.

  Each of these fails if its rule is removed (checked by mutation).

## WhatsApp vs email (Owner, 2026-10-05)

- **List rows:** WhatsApp rows have a 4 px WhatsApp-green (#25D366) stripe on the inline-start edge (right in RTL) and
  a green "וואטסאפ" pill with a chat icon (#075E54 on #D9FDD3, 6.9:1). Email rows have a pale blue stripe and a blue
  "מייל" pill with an envelope.
- **Channel filter:** הכול / מייל / וואטסאפ, shown only when the brand has WhatsApp tickets.
- **Ticket page:** a channel banner, and a green tint on customer bubbles in WhatsApp tickets.
- **Send button:** "שליחה בוואטסאפ" in WhatsApp green (#008069 with white, 4.9:1) or "שליחה במייל".
- **English UI:** "WhatsApp" / "Email", and the English-mode confirm button names the channel.

## Dondy bot, WhatsApp photos, live switches (engine @18, 2026-10-05)

- **Status `bot`:** a WhatsApp chat that Dondy's AI bot is handling. It gets a tab "🤖 הבוט של דונדי מטפל" with the
  `counts.bot` badge. The ticket shows a purple banner and no draft. "לקחת את השיחה" (two clicks) calls
  `apiWaTakeOver {id}` (agent/admin). The cache moves the row to `action` at once, and the next engine run writes a
  draft. `not_bot` is translated into Hebrew. Note: apiBoot lists all open tickets but only the 100 newest closed
  ones, so the bot tab lists the bot chats that apiBoot returns, while the badge shows the engine's full count.
- **Photos:** each slot is `{ref, file:{url}|null, unavailable?}`.
  - A stored file is a "📷 תמונה — פתיחה" link (Drive URLs only).
  - `unavailable` is a green "📷 תמונה — לצפייה בדונדי" chip.
  - A slot still uploading is "📷 תמונה — עוד לא הגיעה".
  - Never an `<img>`: Drive files are private, and the CSP allows images only from this site.
- **Switches never go stale on a client** (live E2E: DRY_RUN was flipped in the engine, and Send stayed disabled
  until a reload).
  - A System Mode change patches the cached list at once, and `/changes` returns `switches` to every open tab
    (polled every 15 s).
  - Opening a ticket re-reads them with `/list {maxAge: 15}`.
  - A change made directly in the engine is picked up in the background once the cached switches are older than 15 s.

## Live QA fixes (2026-10-05)

- **Sorting:** work tabs are newest-first by `waiting_since`. Tickets waiting more than 30 days go into a collapsed
  "ישנים (30+ יום)" / "Older than 30 days" section with a count. Prefetch skips them.
- **Fact panel:**
  - Never shows the internal shipping thresholds, only בזמן / מאחר / מאחר מאוד plus days since the order.
  - Never shows "לא נמצאה הזמנה" next to an order chip.
  - With no email it shows "מנויים: לא נבדק (אין מייל)".
- **`siblings`** (engine field, optional): a yellow "ללקוח יש עוד N פניות פתוחות" chip that opens a search for the
  customer's email (or phone). Absent or 0 means no chip.
- **Favicon:** `/favicon.ico` (cached 7 days).
- **Desktop tabs** wrap and are compressed, so every tab is visible at 1280 px. The desktop layout follows the real
  height of the header, banners and tabs (flex column) instead of a fixed `calc(100vh - 104px)`.
- **The assistant answers in the page's UI language** (`/cs` vs `/cs/en`), sent as `lang` with every question.
- **Cancel-claim refusal:** `draft_problem` with a cancel-claim reason, or a dedicated `cancel_not_done` /
  `cancel_claim` code, shows "הטיוטה אומרת שהמנוי בוטל, אבל הוא עדיין פעיל — קודם לבטל בכפתור…". The override stays
  as it was: offered only for `draft_problem`, two clicks, audited by the engine. Unknown codes are shown, never swallowed.
