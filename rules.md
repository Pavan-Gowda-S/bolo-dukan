# Bolo Dukaan — Rules

Non-negotiable rules for anyone (human or AI) changing this codebase. If a change violates a rule here, it is not ready.

## 1. Money

- All money is **integer paise** in code, database and API payloads. Rupees appear only in display strings.
- The server computes every bill, total, split and budget. **A client-supplied amount is never trusted** — the phone never sends what it owes.
- AI never decides a price, quantity, total or payment outcome. AI proposes; code computes; a human tap confirms.
- Payment status becomes `PAID` only after Cashfree's API confirms `PAID` with the **full amount**. A webhook signature only triggers that re-check; duplicate webhooks must be idempotent no-ops.
- Free items (quiz prize) are added server-side at ₹0, never by the guest's client.
- Never invent numbers shown as facts: nutrition is owner-entered or computed from IFCT/NIN data and labelled "approx."; otherwise say it isn't available.

## 2. AI policy (Sarvam → Gemini → fallback)

- Sarvam AI is the voice and language engine (Saaras speech-to-text, Bulbul voice, sarvam-105b chat, Document Intelligence). Gemini is only a backup.
- Every AI feature sits behind its own `FEATURE_*` switch in `.env`, **default off**. With all switches off the site must behave like the `working-v1` baseline.
- Every Sarvam call has a 15-second timeout and the screen offers taps instead.
- Spoken alerts use fixed phrase templates (`features.announce`), never AI-written text.
- Every AI call path needs a working non-AI fallback: taps, forms, or plain code (e.g. budget ordering lives in `app/budget.py`, not a model).
- Sarvam (`SARVAM_API_KEY`) is the preferred AI; Gemini (`GEMINI_API_KEY`) is backup. Feature flags in `config.py` must reflect what is actually available (`sarvam_ready()` / `gemini_ready()`).
- If an AI feature misbehaves, the fix is to make the fallback good — never to make the UI depend on the model.

## 3. Feature switches

- New features ship behind a `FEATURE_*` flag declared in `app/config.py`, defaulting to `False`. The only exceptions are small, safe ones agreed in the PRD (`FEATURE_MENU_PREVIEW`, `FEATURE_SEATS` default on). With new flags off, the existing demo must work exactly as before.
- The flag gates both the backend route behaviour and the frontend UI (via the features payload) — no orphaned buttons when the flag is off.
- Document the flag, its fallback and its demo step in `README.md` and `prds.md`.

## 4. Security

- **All permission checks happen on the server.** Hiding a button in the browser is not security.
- Table access is by unguessable token; ordering still requires approval by a waiter or the owner (the server answers 409 until then).
- Roles: the owner can do everything for their restaurant. A waiter (`bd_staff`, separately signed) may only approve/reject tables, change order status, clear waiter calls and merge tables, and only for their assigned tables of their own restaurant (403 otherwise). Use `restaurant.actor()` + `session_for()` for routes that waiters may call; everything else uses `require_owner`.
- Staff PINs are hashed like passwords; wrong PINs are throttled (5 per username, 20 per network, 10 minutes).
- Secret links (kitchen TV, game rooms) are random, read-only or game-only, and can be regenerated or expire. They must never expose prices, phone numbers, totals or session APIs.
- Uploads are checked by file signature and size, stored under `data/uploads/`, and served only to the people who need them.
- Join codes: 3 wrong tries block that phone for 10 minutes (10 per network); codes die when the table is freed.
- Owner auth: PBKDF2-salted passwords, or Google ID tokens verified for audience, issuer, expiry and email. Session cookie is signed and `HttpOnly`.
- Cashfree webhooks must verify the HMAC signature before acting.
- Game scores require the guest-session token and respect per-game caps and per-table limits.
- Secrets live in `.env` only — never commit it, never hard-code keys, never log them.
- HTTPS via ngrok for anything phone-facing; card/UPI details go only to Cashfree, never through this server.

## 5. State machines

- Session statuses and order statuses are defined **once**, in `app/db.py` (`WAITING_APPROVAL`, `OPEN`, `BILL_REQUESTED`, `PAID`, `PAID_CASH`, `CLOSED`, `REJECTED`; `PENDING`, `ACCEPTED`, `PREPARING`, `SERVED`, `REJECTED`). Import the constants; never string-literal a status in new code.
- Transitions follow the diagram in `README.md` (and PRD-2). Do not add implicit transitions — after `BILL_REQUESTED`, no new orders.
- `ACTIVE_SESSION_STATUSES` and `BILLABLE_ORDER_STATUSES` are the canonical sets for queries; extend them there if you add a status.
- Any new status gets: a `--st-*` token in `design.md`/`style.css`, a dashboard colour, and grid + 3D-floor + card rendering that agree.

## 6. Language & content

- Guest-facing text supports **kn-IN, hi-IN, en-IN**. The restaurant's language is set at setup; the Noto Kannada/Devanagari font stack must stay in the font stack.
- Server-generated alerts go through the announce path (`features.announce`) so one dashboard instance speaks each event — do not play TTS from multiple browsers. The kitchen TV claims its own copy (`kitchen_claimed`) and speaks only `kitchen_order` events.
- No exclamation marks in interface text; labels stay short; numbers use tabular figures (`.mono`).

## 7. Code & architecture

- **Standard library first.** The only required package is `qrcode` (pure Python) — this keeps Windows Smart App Control from blocking the build. Adding any dependency requires checking `requirements.txt` and justifying why std-lib cannot do it.
- Keep the shape: `app/web.py` (tiny framework), `app/main.py` + feature modules (routes via `@route`), `app/db.py` (schema/migrations), `static/` (vanilla HTML/CSS/JS, no build step).
- Frontend has no framework and no bundler. New JS goes in a focused module under `static/js/`; shared helpers go in `common.js`.
- Pure logic (billing summary, splitting, planner maths, budget) stays in pure functions with unit tests. Route behaviour and permissions are tested against a temporary database (`tests/test_restaurant_upgrades.py`). Run everything with `python -m pytest -q`.
- Only ADD when extending: reuse existing functions (session state machine, `ORDER_FLOW`, `announce`, the QR generator, quiz questions) instead of copying or renaming them.
- Validation helpers (`_str`, `_int`, …) in `main.py` are the pattern for parsing request bodies; raise `HTTPError` with a human message.
- Windows-first: keep `start.bat`/`start.ps1` working, keep paths short-path friendly, keep UTF-8 console handling in `run.py`.

## 8. Testing & verification

- Every change ships with tests in `tests/` (`test_split_summary.py`, `test_planner.py`, `test_budget.py` for pure logic; `test_restaurant_upgrades.py` for routes and permissions). Run `python -m pytest -q`, then the full demo once (scan → approve → order → accept → bill → pay → free) before committing.
- `scripts/check_sarvam.py` validates the Sarvam key (chat, Kannada voice, speech-to-text, document reading); `check.bat` checks the Gemini backup and makes a ₹1 Cashfree sandbox link. Run them before claiming payments or AI work.
- `python scripts/seed_source.py` rebuilds and validates `app/data/*.json` — never hand-edit those files.
- Never claim a test that was not run.

## 9. UI (see also `design.md`)

- Add tokens to `:root`; no hard-coded hex in component CSS.
- Reuse `.btn`, `.card`, `.toast`, `.status-tag`, `.chip` before inventing components.
- One accent per surface; status colours are reserved for live state, nothing else.
- Feature-gated UI hides itself when its flag is off.
- Motion explains something or it gets removed: named transitions only, no animating layout properties, one easing curve (`--ease`).
- Screens that refresh on a timer must not replay entrance animations; update only what changed.

## 10. Documentation

- User-facing behaviour changes update `README.md` (features, switches, API reference, troubleshooting).
- Requirement changes update `prds.md`; look/token changes update `design.md`; structural changes update `architecture.md`.
- Keep the switch table in `README.md` and `prds.md` in sync with `app/config.py`.
