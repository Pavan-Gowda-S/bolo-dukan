# Bolo Dukaan — Architecture

How the system fits together. For requirements see `prds.md`; for conventions see `rules.md`.

## Shape of the system

A single Python process serving a vanilla-JS frontend, with SQLite as the only datastore and three external services (Sarvam/Gemini for AI, Cashfree for payments, Google for sign-in).

```
 Phone (guest)            Browser (cashier/owner)
      │  HTTPS (ngrok)           │
      ▼                          ▼
 ┌──────────────────────────────────────────┐
 │  run.py → app/web.py   (std-lib HTTP)    │
 │  app/main.py           (all API routes)  │──► SQLite  data/bolo_dukaan.db
 │  app/sarvam.py, gemini.py (AI)           │──► Sarvam AI / Gemini
 │  app/cashfree.py       (payments)        │──► Cashfree Payment Links
 │  Google tokeninfo      (sign-in)         │──► Google OAuth
 └──────────────────────────────────────────┘
 static/  HTML + CSS + vanilla JS, Three.js (bg3d, floor3d), canvas games
```

**Design constraints that shape everything:**

1. **Windows Smart App Control friendly** — pure Python, one dependency (`qrcode`), std-lib HTTP server. No compiled wheels, no framework.
2. **One process, one file DB** — `data/bolo_dukaan.db`, no DB server to install or secure.
3. **No build step** — frontend is static files served as-is.
4. **Feature-switched** — every optional capability is gated by `FEATURE_*` in `.env` (`app/config.py`), default off.

## Backend layers

| Layer | Module(s) | Responsibility |
|---|---|---|
| Entry | `run.py` | Arg parsing (port/host), `init_db()`, status banner, opens browser |
| HTTP framework | `app/web.py` | `App`, `Request`, `Response`, `HTTPError`, `@route`-style routing, cookies, uploads, static files, `ThreadingHTTPServer` |
| Routes & business rules | `app/main.py` | Owner/guest/cashier endpoints, validation helpers (`_str`, `_int`), session & order state transitions |
| Feature modules | `app/features.py`, `upgrades.py`, `store.py` | Registered by late import at the bottom of `main.py` (line ~1176): voice/OCR/quiz/announce (features), A1–A3 upgrades (summary, split, owner voice), supermarket + shop + planner routes (store) |
| Pure logic | `app/budget.py`, `summary.py`, `split.py`, `planner.py` | Money and maths as testable pure functions — no HTTP, no AI |
| Domain data | `app/db.py` | `SCHEMA` DDL, `init_db()` migrations, connection pool, status constants, `row`/`rows` helpers |
| Auth | `app/auth.py` | PBKDF2 hashing, signed HttpOnly owner cookie, `require_owner` decorator helper |
| AI | `app/ai.py`, `sarvam.py`, `gemini.py` | Provider abstraction: Sarvam preferred (STT saaras, TTS bulbul, intent sarvam-105b, Doc AI), Gemini backup (chat, OCR, TTS) |
| Payments | `app/cashfree.py` | Payment links, HMAC webhook signature verification, status re-check |
| Config | `app/config.py` | `.env` loading, `FEATURE_*` flags, `features()` payload sent to the frontend, `*_ready()` capability probes |
| HTTP client | `app/net.py` | Std-lib `urllib` wrapper (`request`, `NetError`) used for all outbound API calls |
| Static assets | `static/` | Pages, CSS, JS (see below) |

### Routing

`app/main.py` creates `app = App(config.STATIC_DIR)`; `route = app.route` is the decorator used by every endpoint (`@route("POST", "/api/owner/signup")`). Page routes are registered in a loop from a page map (line ~246: `route("GET", _path)(_page_handler(_file))`), mapping `/`-paths to `static/pages/*.html`. Feature modules import the shared `app` object late to avoid circular imports.

### Database

- `sqlite3` with `check_same_thread=False`, `timeout=15`, connections via `db()` context manager — safe under the threading HTTP server.
- Schema is `CREATE TABLE IF NOT EXISTS` DDL in `app/db.py::SCHEMA`; `init_db()` runs it idempotently at startup, so migrations are additive.
- 22 tables, grouped:
  - **Restaurant:** `restaurants`, `owners`, `menu_items`, `tables`
  - **Guest session:** `table_sessions`, `session_guests`, `orders`, `order_items`, `waiter_calls`, `join_attempts`
  - **Money:** `payments`, `bill_shares`
  - **Engagement:** `game_scores`, `quiz_rounds`, `quiz_players`, `quiz_answers`, `announcements`, `translations`
  - **Supermarket:** `products`, `store_orders`, `store_order_items`

### State machines (authoritative in `app/db.py`)

```
Session: WAITING_APPROVAL ──approve──► OPEN ──request bill──► BILL_REQUESTED
             │ reject                      │                        │
             ▼                             │            Cashfree confirms PAID
           REJECTED                        │                        ▼
                                           │              PAID ──free──► CLOSED
                                           │              PAID_CASH (cash) ──► CLOSED

Order:  PENDING ──► ACCEPTED ──► PREPARING ──► SERVED
            └── REJECTED (with reason)

ACTIVE_SESSION_STATUSES   = (WAITING_APPROVAL, OPEN, BILL_REQUESTED, PAID)
BILLABLE_ORDER_STATUSES   = (ACCEPTED, PREPARING, SERVED)
```

New orders are refused once the session is `BILL_REQUESTED` or beyond. The bill is summed server-side over `BILLABLE_ORDER_STATUSES`.

### Request flow (guest order → payment)

1. Guest opens `/t/{token}` → `GET /api/t/{token}` returns table, restaurant, menu.
2. `POST /api/t/{token}/start` → `WAITING_APPROVAL`; cashier approves via `POST /api/session/{id}/approve`.
3. Order round: `POST /api/session/{id}/orders` (taps) or `/assistant` (voice → AI intent → matched to menu at menu prices → proposed cart → guest confirms).
4. Cashier moves orders through `POST /api/orders/{id}/status`.
5. `POST /api/session/{id}/request-bill` → server sums billable orders → `BILL_REQUESTED`.
6. `POST /api/session/{id}/pay` → Cashfree Payment Link created (one per bill, `bd{session}c{counter}…`).
7. Guest pays on Cashfree; webhook `POST /api/webhooks/cashfree` (HMAC-verified) *triggers* a server-side status re-check via `GET /api/session/{id}/payment-status`; `PAID` only on full-amount confirmation.
8. Cashier frees the table → `CLOSED`, join code and session tokens die.

### AI path

```
mic audio ─► Sarvam STT (saaras) ─┐
text      ────────────────────────┼─► intent extraction (sarvam-105b, fallback Gemini)
                                  │      └─► match_items() → menu-matched cart at menu prices
TTS reply ◄─ Sarvam bulbul ◄──────┘         └─► guest confirms by tap
              (fallback: Gemini TTS if FEATURE_GEMINI_TTS, then browser voice, then text)
```

`features.voice()`, `features.budget()` (pure code), `features.menu_photo()` (Doc AI/Gemini OCR → draft JSON → owner reviews) are the main entry points. `features.announce()` writes an announcement row so exactly one dashboard instance plays the spoken alert.

### Payments path

`app/cashfree.py` wraps Payment Links creation and webhook signature verification. `app/net.py` is the only outbound HTTP client. Sandbox keys by default (`CASHFREE_ENV`), verified by the ₹1 link in `check.bat`.

## Frontend

| Piece | Files | Notes |
|---|---|---|
| Shared helpers | `static/js/common.js` | fetch wrapper, toasts, formatting, feature-flag reads |
| 3D ambience | `bg3d.js` | Fixed full-viewport Three.js background, fades in (`.ready`), `data-bg="calm"` dims it |
| 3D floor | `floor3d.js` | Restaurant floor with status rings/beams; consumes the same `/api/dashboard` payload as the grid |
| Cashier | `dashboard.js`, `dashboard_plus.js` | Grid, actions, sales summary, owner voice (A1/A3) |
| Guest | `table.js` | Menu, cart, voice, tracker, bill, pay, join |
| Games | `games.js` | Quiz + 4 canvas/3D games, score posting |
| Supermarket | `store.js`, `shop.js`, `planner.js` | Store admin, customer shop, 8-step meal planner |
| Styles | `style.css` (design system) + `dashboard/table/shop/auth` page styles | Tokens in `:root` — see `design.md` |

Pages (`static/pages/`) are plain HTML loading these modules; no SPA router — navigation is real HTTP page loads, with `common.js` handling API calls and live updates (polling `/api/dashboard`, `/api/session/{id}`).

## Configuration & runtime

- `.env` (never committed) holds keys: `SARVAM_API_KEY`, `GEMINI_API_KEY` (+model/voice), `GOOGLE_CLIENT_ID`, `CASHFREE_APP_ID/SECRET_KEY/ENV`, `PUBLIC_URL`, all `FEATURE_*`.
- `config.features()` computes the effective feature payload — flag **and** required capability both true (e.g. `split_bill = FEATURE_SPLIT_BILL and cashfree_ready()`).
- Public URL: fixed `PUBLIC_URL` or auto-detected ngrok; QR links refresh via **QR codes → Refresh links**.
- Startup prints which AI/payment providers are live and which features are on.

## Testing

- `python -m unittest discover -s tests` — pure-logic tests only: `test_budget.py`, `test_planner.py`, `test_split_summary.py`.
- `check.bat`/`check.py` — live integration smoke: Kannada Gemini order, Kannada voice alert, ₹1 Cashfree sandbox link.
- `scripts/seed_source.py` — rebuilds/validates `app/data/*.json` (ingredients, recipes, demo products).
- No frontend test harness; dashboard/table flows are verified via the README demo script.

## Repository layout

```
app/            backend (see layer table above)
  data/         ingredients.json, recipes.json, products_demo.json, photos.json
static/
  pages/        landing, signup, login, setup, menu, qr, dashboard, table, paid, store, shop, credits
  js/           common, bg3d, floor3d, dashboard(+plus), table, games, store, shop, planner
  css/          style.css (design system), dashboard, table, shop, auth
scripts/        seed_source.py, fetch_photos.py, localize_photos.py, check_sarvam.py
tests/          unittest suite (pure logic)
run.py          entry point · start.bat/ps1, check.bat, ngrok.bat  (Windows one-click)
```
