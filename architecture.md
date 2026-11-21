# Bolo Dukaan — Architecture

How the system fits together. For requirements see `prds.md`; for conventions see `rules.md`; for the look see `design.md`.

## Shape of the system

A single Python process serving a vanilla-JS frontend, with SQLite as the only datastore and three outside services: **Sarvam AI** for voice and language (Gemini only as backup), **Cashfree** for UPI payments, and **Google** for sign-in.

```
 Guest phone      Waiter phone      Kitchen TV        Owner / cashier browser
      │                │                │                     │
      └────────────────┴──── HTTPS (ngrok) ───────────────────┘
                                 ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ run.py → app/web.py        standard-library HTTP server          │
 │ app/main.py                tables, orders, bills (core routes)    │──► SQLite  data/bolo_dukaan.db
 │ app/features.py            voice ordering, alerts, budget, quiz   │──► Sarvam AI (Saaras, Bulbul, sarvam-105b, Doc AI)
 │ app/upgrades.py            sales summary, split bill, owner voice │      └─ Gemini only as backup
 │ app/restaurant.py          kitchen TV, staff, merge, report,      │──► Cashfree Payment Links
 │                            game rooms, floor plan                 │
 │ app/store.py · planner.py  supermarket and meal planner           │──► Google (Sign in with Google)
 └──────────────────────────────────────────────────────────────────┘
 static/  HTML + CSS + vanilla JS, Three.js (3D background, 3D floor), canvas games
```

**Design constraints that shape everything:**

1. **Windows Smart App Control friendly**: pure Python, one dependency (`qrcode`), standard-library HTTP server. No compiled wheels, no framework.
2. **One process, one file DB**: `data/bolo_dukaan.db`, no database server to install or secure. Uploads (menu photos, blueprints) live under `data/uploads/`.
3. **No build step**: the frontend is static files served as they are.
4. **Feature-switched**: every optional part is behind a `FEATURE_*` flag in `.env` (`app/config.py`). `FEATURE_MENU_PREVIEW` and `FEATURE_SEATS` default on; everything else defaults off.

## Backend layers

| Layer | Module(s) | Responsibility |
|---|---|---|
| Entry | `run.py` | Arguments (port/host), `init_db()`, status banner, opens the browser |
| HTTP framework | `app/web.py` | `App`, `Request`, `Response`, `HTTPError`, routing, cookies, multipart uploads, static files, threading server |
| Core routes | `app/main.py` | Owner, guest and cashier endpoints, validation helpers (`_str`, `_int`, `_menu_details_in`), session and order state changes, table merge resolution |
| Feature modules | `app/features.py`, `upgrades.py`, `store.py`, `restaurant.py` | Imported at the bottom of `main.py` and registered on the same `app`. `features`: voice, alerts, budget, quiz, menu photo. `upgrades`: sales summary, split bill, owner voice. `store`: supermarket, shop, planner. `restaurant`: kitchen TV, staff + waiter portal, merge tables, daily report, game rooms, floor plan |
| Pure logic | `app/budget.py`, `summary.py`, `split.py`, `planner.py` | Money and maths as testable pure functions (no HTTP, no AI) |
| Data | `app/db.py` | `SCHEMA`, additive migrations in `init_db()`, status constants, `row`/`rows` helpers |
| Auth | `app/auth.py` | PBKDF2 hashing, signed HttpOnly owner cookie (`bd_owner`) and a separately signed staff cookie (`bd_staff`) |
| AI | `app/ai.py`, `sarvam.py`, `gemini.py` | Sarvam first (Saaras STT, Bulbul TTS, sarvam-105b chat, Document Intelligence), Gemini backup |
| Payments | `app/cashfree.py` | Payment links, HMAC webhook check, status re-check |
| Config | `app/config.py` | `.env` loading, `FEATURE_*` flags, `features()` payload for the pages, `*_ready()` checks |
| HTTP client | `app/net.py` | Standard-library `urllib` wrapper used for every outgoing call |

### Who may call what

| Caller | Proof | Allowed |
|---|---|---|
| Owner | `bd_owner` cookie | Everything for their restaurant |
| Waiter | `bd_staff` cookie (`require_staff`) | Approve/reject tables, order status, clear waiter calls, merge tables, waiter board, blueprint image: only for **assigned tables** of **their** restaurant (`restaurant.actor` + `session_for`, else 403) |
| Guest | `X-Guest-Token` header (per phone, per session) | Their table session only |
| Kitchen TV | 32-character secret in the URL | Read-only ticket board and its own announcement claims |
| Game room player | Room token in the URL + per-player key | That room's game only |
| Cashfree | HMAC signature | Triggers a payment re-check |

### Database

- `sqlite3` with `check_same_thread=False`, `timeout=15`, connections through the `db()` context manager.
- `SCHEMA` is `CREATE TABLE IF NOT EXISTS`; `init_db()` adds new columns with guarded `ALTER TABLE`, so migrations are additive and safe to re-run.
- 26 tables:
  - **Restaurant:** `restaurants` (+ `kitchen_token`, `floor_image`, `business_type`), `owners`, `menu_items` (+ dish details: `description`, `is_veg`, `spice`, `allergens`, `kcal`, `protein_g`, `carbs_g`, `fat_g`, `fibre_g`), `tables` (+ `seats`, `pos_x`, `pos_y`, `merged_into`)
  - **Staff:** `staff`, `staff_tables`
  - **Guest session:** `table_sessions` (+ `approved_by`), `session_guests`, `orders` (+ `accepted_at`, `accepted_by`, `guest_id`), `order_items`, `waiter_calls`, `join_attempts` (also used for PIN throttling)
  - **Money:** `payments`, `bill_shares`
  - **Engagement:** `game_scores`, `quiz_rounds`, `quiz_players`, `quiz_answers`, `game_rooms`, `game_room_players`, `game_room_answers`, `announcements` (+ `kitchen_claimed`), `translations`
  - **Supermarket:** `products`, `store_orders`, `store_order_items`

### State machines (authoritative in `app/db.py`)

```
Session: WAITING_APPROVAL ──approve (owner or waiter)──► OPEN ──request bill──► BILL_REQUESTED
             │ reject                                      │                        │
             ▼                                             │            Cashfree confirms PAID
           REJECTED                                        │                        ▼
                                                           │              PAID ──free──► CLOSED
                                                           │              PAID_CASH (cash) ──► CLOSED

Order:  PENDING ──► ACCEPTED ──► PREPARING ──► SERVED          (ACCEPTED → kitchen TV + kitchen voice)
            └── REJECTED (with reason)

ACTIVE_SESSION_STATUSES   = (WAITING_APPROVAL, OPEN, BILL_REQUESTED, PAID)
BILLABLE_ORDER_STATUSES   = (ACCEPTED, PREPARING, SERVED)
```

Orders, voice, budget and assistant calls return `409 Waiting for the waiter to confirm your table` until the session is OPEN. After `BILL_REQUESTED` no new orders are accepted. The bill is summed on the server over `BILLABLE_ORDER_STATUSES`.

**Merged tables.** `tables.merged_into` points a table at a host table. `_table_by_token` resolves the merged table's QR to the host, so start/join/menu all act on the host's session. If both tables were ordering, `session_guests`, `orders` and `waiter_calls` move to the host session and the old session closes; `GET /api/session/{id}` follows a phone whose token moved. Freeing the host (or paying cash) clears the merge.

### Request flow (guest order → kitchen → payment)

1. Guest opens `/t/{token}` → `GET /api/t/{token}` returns table (seats, merged tables), restaurant and menu (with nutrition and photos when on). The guest can preview the menu at once.
2. `POST /api/t/{token}/start` → `WAITING_APPROVAL`; a waiter (portal) or the owner (dashboard) approves; `approved_by` is recorded.
3. Order round: `POST /api/session/{id}/orders` (taps) or `/voice` / `/assistant` (speech → Sarvam → menu-matched cart at menu prices → guest confirms).
4. The waiter reads the order back and ticks each item, then `POST /api/orders/{id}/status` ACCEPTED (`accepted_by`, `accepted_at`). `restaurant.on_order_status` adds a `kitchen_order` announcement; the kitchen TV shows the ticket and speaks it once.
5. PREPARING / SERVED from the portal or dashboard; served tickets leave the kitchen board.
6. `POST /api/session/{id}/request-bill` → server sums billable orders → `BILL_REQUESTED`; the guest sees a receipt and can share it on WhatsApp.
7. `POST /api/session/{id}/pay` → Cashfree Payment Link; the webhook (HMAC-checked) triggers a status re-check; `PAID` only on full-amount confirmation.
8. Free table → `CLOSED`; join code, merges and game rooms end.

### Voice and AI path

```
mic audio ─► Sarvam Saaras (STT) ─┐
text      ────────────────────────┼─► Sarvam sarvam-105b (intent JSON; Gemini as backup)
                                  │      └─► match_items() → cart at menu prices → guest taps to confirm
voice     ◄─ Sarvam Bulbul (TTS) ◄┘
alerts: fixed Kannada/Hindi/English phrases (no AI) → Bulbul → one dashboard / one kitchen TV claims each
```

`features.announce()` writes an announcement row from fixed templates (start, order, waiter with reason, bill, paid, quiz, kitchen_order, store_order). The dashboard claims with `claimed`, the kitchen TV with `kitchen_claimed`, so each screen speaks each event once. Recipe steps are translated in one sarvam-105b call per recipe and cached in `translations`.

## Frontend

| Piece | Files | Notes |
|---|---|---|
| Shared helpers | `static/js/common.js` | API wrapper, toasts, formatting, 3D tilt, recorder, sounds, build-change reload |
| 3D | `bg3d.js`, `floor3d.js` | Background, and the restaurant floor: status rings, chairs per table, blueprint texture and real table positions when a floor plan exists |
| Owner / cashier | `dashboard.js`, `dashboard_plus.js` | Grid, Plan view, 3D floor, drawer actions, merge, sales strip, owner voice, Kitchen display / Staff / Daily report buttons |
| Guest | `table.js`, `games.js` | Menu preview, dish sheet, cart, voice, call waiter, receipt + WhatsApp, split, games and "Play with my table" |
| Waiter | `waiter.js` (+ `waiter.html`) | Assigned tables, order read-back, floor view, buzz + voice |
| Kitchen | `kitchen.js` (+ `kitchen.html`) | Ticket board, timers, reconnecting, voice claims |
| Owner tools | `setup.html`, `staff.html`, `report.html`, `floor.html` | Tables + chairs, waiters, daily report, blueprint editor with 3D preview |
| Game room | `game.html` | Game-only page for `/g/{room}` |
| Supermarket | `store.js`, `shop.js`, `planner.js` | Store admin, customer shop, meal planner |
| Styles | `style.css` + `dashboard`, `table`, `shop`, `auth` | Tokens in `:root` (see `design.md`) |

Pages are plain HTML with real page loads (no SPA router). Live screens poll: dashboard 2 s, waiter 3 s, kitchen 2 s, guest 2.5 s, game room 0.7–2 s. Polling screens redraw only what changed so nothing flickers.

## Configuration and runtime

- `.env` (never committed) holds `SARVAM_API_KEY`, optional `GEMINI_API_KEY`, `GOOGLE_CLIENT_ID`, `CASHFREE_APP_ID/SECRET_KEY/ENV`, `PUBLIC_URL` and the `FEATURE_*` switches.
- `config.features()` is the effective payload: the flag **and** the needed capability (for example `split_bill = FEATURE_SPLIT_BILL and cashfree_ready()`).
- Public URL: fixed `PUBLIC_URL` or ngrok auto-detected; QR links refresh from **QR codes → Refresh links**.
- Startup prints which AI and payment providers are live and which features are on.

## Testing

- `python -m pytest -q`: pure-logic tests (`test_budget.py`, `test_planner.py`, `test_split_summary.py`) plus `test_restaurant_upgrades.py`, which runs the real routes on a temporary database for menu preview, seats, dish details, kitchen TV, staff permissions, merge tables, daily report, waiter calls, game rooms and the floor plan.
- `scripts/check_sarvam.py`: live Sarvam check (chat, Kannada voice, speech-to-text, document reading). `check.bat`: Gemini backup and a ₹1 Cashfree sandbox link.
- `scripts/seed_source.py`: rebuilds and validates `app/data/*.json`.

## Repository layout

```
app/            backend (see the layer table)
  data/         ingredients.json, recipes.json, products_demo.json, photos.json
static/
  pages/        index, signup, login, setup, menu, qr, dashboard, table, paid, kitchen, waiter, staff,
                staff_login, report, floor, game, store, shop, credits
  js/           common, bg3d, floor3d, dashboard(+plus), table, games, kitchen, waiter, store, shop, planner
  css/          style.css (design system), dashboard, table, shop, auth
  img/photos/   locally stored, credited food and grocery photos
scripts/        check_sarvam.py, seed_source.py, fetch_photos.py, localize_photos.py
tests/          pytest suite
run.py          entry point · start.bat / start.ps1, check.bat, ngrok.bat (Windows one-click)
```
