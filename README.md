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
| `tests/` | pytest (100 tests) |
| `tools/screens.py` | mock preview + Playwright screenshots + on-screen checks → `screens/` |

## Environment (Render)

| var | required | what |
|---|---|---|
| `TOKEN_SECRET` | yes | 32+ chars. **Same value** as the `TOKEN_SECRET` Script Property of every brand engine. |
| `ENGINES_JSON` | yes | `{"rozela":"https://script.google.com/macros/s/<id>/exec", "celesta": "...", "apexmen": "..."}`. Only Apps Script `/exec` URLs are accepted (Workspace `/a/macros/<domain>/s/...` too); anything else is dropped and the brand shows "not connected". |
| `SECRET_KEY` | yes | 32+ random chars, Flask session signing. Render-only; never shared with the engines. The app refuses to start without it. |
| `ADMIN_BOOTSTRAP` | first boot only | `username:password` (password 10+ chars). Creates the first admin (admin + user-manager, all brands, must change password) **only if the users file is empty**. **Remove it from the Render environment right after the first boot.** The app ignores it once users exist, logs a warning, and shows admins a red banner while it is still set. |
| `USERS_PATH` | no | default `/var/data/users.json` (the persistent disk). The audit log goes next to it (`users-audit.jsonl`), or to `AUDIT_PATH`. |
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
