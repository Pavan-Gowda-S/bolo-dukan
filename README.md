<div align="center">

<img src="static/img/logo.svg" width="88" alt="Bolo Dukaan logo">

# Bolo Dukaan for Restaurants

**Every table, talking to you.**

Set up a restaurant in minutes and get a live dashboard plus a QR code for every table.<br>
Guests browse, order and pay from their phones by tapping **or just talking** in Kannada, Hindi or English.<br>
Waiters work from their own phones, the kitchen gets a big-screen display, and the owner sees everything from one screen.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Sarvam AI](https://img.shields.io/badge/Voice%20%26%20AI-Sarvam%20AI-FF6B00)
![Cashfree](https://img.shields.io/badge/Payments-Cashfree%20UPI-6A1B9A)
![Three.js](https://img.shields.io/badge/3D-Three.js-000000?logo=threedotjs&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-one--click%20start-0078D6?logo=windows&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-blue)

</div>

---

## Contents

- [What it does](#what-it-does)
- [Voice and AI: Sarvam](#voice-and-ai-sarvam)
- [Features](#features)
- [Pages and who uses them](#pages-and-who-uses-them)
- [Quick start (Windows)](#quick-start-windows)
- [Configuration and switches](#configuration-and-switches)
- [Restaurant upgrades in detail](#restaurant-upgrades-in-detail)
- [Supermarket mode and AI Meal Planner](#supermarket-mode-and-ai-meal-planner)
- [How a table works](#how-a-table-works)
- [Payments with Cashfree](#payments-with-cashfree)
- [Security](#security)
- [Architecture](#architecture)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Tests](#tests)
- [Demo script (4 minutes)](#demo-script-4-minutes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What it does

| | |
|---|---|
| 📸 **Owner** | Signs up (email or Google), snaps a photo of the paper menu, sets tables and chairs, optionally uploads a floor plan, prints QR codes, adds waiters, and downloads a daily report. |
| 📱 **Guest** | Scans the table QR, browses the menu at once, taps a dish for photos and nutrition, orders by tapping or speaking once the waiter confirms the table, calls a waiter for exactly what they need, plays games, and pays by UPI or shares the bill on WhatsApp. |
| 🧑‍🍳 **Waiter** | Logs in on their own phone with a PIN, sees only their tables, approves seated guests, reads each order back before sending it to the kitchen, marks food served and merges tables for big groups. |
| 📺 **Kitchen** | A no-touch TV showing accepted orders as big tickets with timers, and reads each new order aloud in Kannada. |
| 🖥️ **Cashier** | Sees every table colour-coded in a grid, a blueprint plan or a 3D floor, hears spoken alerts in the kitchen's language and closes bills. |

## Voice and AI: Sarvam

All voice and language features run on **[Sarvam AI](https://www.sarvam.ai)**, built for Indian languages. Gemini is only a backup that is used if a Sarvam call fails or no Sarvam key is set.

| Job | Sarvam model |
|---|---|
| Speech to text (guest orders, owner questions, shopper requests, hands-free cooking) | **Saaras** (`saaras:v4`) |
| Kannada / Hindi / English voice (kitchen and dashboard alerts, replies, recipe read-aloud) | **Bulbul** (`bulbul:v3`) |
| Understanding orders, budgets, owner questions and price lists; translating recipe steps | **Sarvam chat model** (`sarvam-105b`) |
| Reading a photo or PDF of a menu or price list | **Sarvam Document Intelligence** |

**Ground rules, enforced in code:** the AI never decides money (prices, totals, availability and payment status come from the database), nothing is ordered or saved until a person taps confirm, every AI call has a 15-second timeout with a tap fallback, and spoken alerts use **fixed phrases** so the words are always right. See [SARVAM_FEATURES.md](SARVAM_FEATURES.md).

## Features

**For the owner**
- Sign up / log in with **email + password** or **Sign in with Google**; choose **Restaurant** or **Supermarket**
- **Menu from a photo or PDF**: Sarvam reads every dish, local-script name and price; the owner reviews before saving
- Menu by **CSV** (Excel "Save as CSV" works) or typed one by one, with optional description, veg/non-veg, spice level, allergens and nutrition
- **Tables and chairs**: type or tap the number of tables, set chairs per table or "__ chairs for all tables"
- **Optional floor plan**: upload a blueprint and drag tables onto it; the 3D floor follows it
- **Printable QR cards** with seats, Wi-Fi details and captions in Kannada and Hindi
- **Staff**: add waiters with a username and PIN, assign tables, reset PINs, deactivate
- **Daily report**: download a CSV or save a clean printable page as PDF
- **Kitchen display link** for any TV or tablet, with a "Regenerate" button

**For guests**
- **Menu preview** right after scanning; ordering opens once the waiter confirms the table
- **Dish details**: photo, description, spice, allergens and a nutrition ring (kcal) with protein/carbs/fat bars, always labelled approx. and never guessed
- **Voice ordering**: say "eradu masala dose, ondu coffee", "ಎರಡು ಇಡ್ಲಿ ವಡೆ" or "do chai aur ek samosa" and get a proposed cart at menu prices
- **Order by budget**: "₹800, dinner for 4" builds a cart in code (no AI) that never goes over budget
- **Call a waiter for something specific** (water, cutlery, clean the table, help to order, extra chutney, or type it), see it's on the way, cancel it, and get a tick when it's done
- **Shared table**: friends join with a 4-digit code and all phones share one bill
- **Receipt-style bill** with **Share on WhatsApp**, UPI payment, and **split the bill** equally or by items
- **Games**: "Play with all tables" (live Table Quiz with a free-tea prize and today's leaderboard) or **"Play with my table"** (a private trivia room with its own QR), plus Rickshaw Rush, Dosa Flip, Chai Catch and Spice Match

**For the cashier**
- Live **grid**, a **blueprint plan view** and an interactive **3D restaurant floor** (Three.js) with glowing status rings, real table positions and the right number of chairs
- Approve / reject tables, accept / reject / preparing / served, paid in cash, free table, **merge tables**
- **Spoken alerts** in Kannada, Hindi or English via Sarvam Bulbul, with browser-voice and text fallbacks
- **Sales summary**: collected today, bills, average, UPI vs cash, top items; shows who approved a table and who accepted an order
- **Owner voice assistant**: "aaj ka collection?", "how many tables are free?", "free table 4" (actions ask for a tap first)

**Built for Windows**
- Double-click `start.bat`. It needs only Python and **one pure-Python package** (`qrcode`). The web server, database and HTTPS calls use Python's standard library, so Windows **Smart App Control** never blocks a compiled file.

## Pages and who uses them

| URL | Who | What |
|---|---|---|
| `/owner/signup` · `/owner/login` | Owner | Account (email or Google) |
| `/owner/setup` | Owner | Name, tables, chairs per table, kitchen language, Wi-Fi |
| `/owner/menu` | Owner | Menu: photo / CSV / typed, dish details |
| `/owner/qr` | Owner | Printable table QR cards |
| `/owner/floor` | Owner | Optional blueprint + drag tables, with a 3D preview |
| `/owner/staff` | Owner | Waiter accounts and their tables |
| `/owner/report` | Owner | Daily report, CSV download, Save as PDF |
| `/dashboard` | Owner / cashier | Live tables: grid, plan, 3D floor |
| `/t/<table>` | Guest | Menu, order, games, bill, pay |
| `/g/<room>` | Guests at one table | Private trivia room (game only) |
| `/staff/login` · `/waiter` | Waiter | PIN login and the waiter portal |
| `/kitchen/<secret>` | Kitchen TV | Accepted orders, no touching needed |
| `/store` · `/s/<store>` | Supermarket | Store dashboard and the customer shop |

## Quick start (Windows)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. Put this folder at a **short path**, e.g. `C:\Users\you\bolo-dukaan` (Windows has a 260-character path limit).
3. Double-click **`start.bat`**. The first run creates a private `.venv`, installs `qrcode` and creates `.env`.
4. Open `.env` in Notepad, add your keys (see [Configuration](#configuration-and-switches)), then run `start.bat` again.
5. Test the keys: `.venv\Scripts\python.exe scripts\check_sarvam.py` checks Sarvam (speech, voice, chat, document reading); `check.bat` checks the Gemini backup and makes a ₹1 Cashfree sandbox link.
6. For phones, run **`ngrok.bat`** in a second window. The app detects the HTTPS link by itself. Open **QR codes → Refresh links**.

```powershell
.\start.bat                 # http://localhost:8000
.\start.bat -Port 8001      # if port 8000 is busy
.\ngrok.bat 8001            # public HTTPS link for that port
```

<details>
<summary>macOS / Linux</summary>

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your keys
python run.py --port 8000
```
</details>

## Configuration and switches

Everything lives in `.env` (never commit it; it's in `.gitignore`). Restart after changes.

| Variable | Purpose |
|---|---|
| `SARVAM_API_KEY` | **Main voice and AI**: Saaras speech-to-text, Bulbul voice, sarvam-105b chat, Document Intelligence. Get one at [dashboard.sarvam.ai](https://dashboard.sarvam.ai) |
| `SARVAM_TTS_SPEAKER` · `SARVAM_TIMEOUT` | Voice (default `kavya`) and call timeout (default 15 s) |
| `GEMINI_API_KEY` | Optional backup if a Sarvam call fails. [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `GOOGLE_CLIENT_ID` | Sign in with Google. Create an OAuth **Web application** client in [Google Cloud Console](https://console.cloud.google.com/apis/credentials) and add your origins |
| `CASHFREE_APP_ID` / `CASHFREE_SECRET_KEY` / `CASHFREE_ENV` | Payment links. Use **sandbox** keys from the Cashfree merchant dashboard |
| `PUBLIC_URL` | Optional fixed public URL; leave empty to auto-detect ngrok |

**Feature switches.** Each feature can be turned off with `false` and a restart. `FEATURE_MENU_PREVIEW` and `FEATURE_SEATS` are **on** by default; all others are **off** unless set to `true`. With the new switches off, the demo works exactly as before.

| Switch | Feature | When off |
|---|---|---|
| `FEATURE_KANNADA_ALERTS` | Spoken Kannada alerts (dashboard, kitchen, waiter) | Text + chime |
| `FEATURE_VOICE_ORDER` | Mic ordering at the table and in the shop | Tap to order |
| `FEATURE_VOICE_ACTIONS` | Voice "bill" / "waiter" | Buttons |
| `FEATURE_MENU_PHOTO` | Menu / price-list photo → draft | CSV / typed |
| `FEATURE_BUDGET_ORDER` | "₹800 for 4" basket (pure code) | Order normally |
| `FEATURE_TABLE_QUIZ` | Live quiz between tables, free tea prize | Other games |
| `FEATURE_SALES_SUMMARY` | Today's sales strip + bill list | Dashboard totals |
| `FEATURE_SPLIT_BILL` | Split equally / by items, one UPI link per person | One bill |
| `FEATURE_OWNER_VOICE` | Owner voice assistant | Dashboard buttons |
| `FEATURE_NUTRITION` | Approx. kcal / protein / carbs / fat from IFCT/NIN data | Prices only |
| `FEATURE_PHOTOS` | Real food & grocery photos (Wikimedia Commons) | Emoji |
| `FEATURE_MENU_PREVIEW` | Browse the menu before approval (default **on**) | Waiting screen |
| `FEATURE_SEATS` | Chairs per table everywhere (default **on**) | Tables only |
| `FEATURE_DISH_DETAILS` | Dish details sheet + owner dish fields | Menu cards only |
| `FEATURE_KITCHEN_TV` | Kitchen display + kitchen voice | Dashboard only |
| `FEATURE_STAFF` | Waiter accounts and portal | Owner does everything |
| `FEATURE_MERGE_TABLES` | Merge two tables for a big group | Separate bills |
| `FEATURE_GAME_ROOMS` | "Play with my table" private trivia | Restaurant-wide games |
| `FEATURE_FLOOR_PLAN` | Blueprint + table positions, plan view, 3D layout | Auto layout |
| `FEATURE_DAILY_REPORT` | CSV + printable daily report | Sales strip |
| `FEATURE_SUPERMARKET` · `FEATURE_MEAL_PLANNER` | Supermarket mode and the meal planner | Restaurant only |
| `FEATURE_GEMINI_TTS` | Allow Gemini's voice as a backup (default on) | Browser voice |

## Restaurant upgrades in detail

**Menu preview before approval.** After scanning, guests can browse the whole menu and open dish details, but there are no add buttons, no cart, no mic and no budget button. A banner says *"Ordering opens once the waiter confirms you're at the table."* The server refuses orders, voice, budget and assistant calls with `409 Waiting for the waiter to confirm your table` until the table is OPEN. When it opens, the same screen switches to ordering without a reload.

**Chairs per table.** Setup has a typeable table count with +/−, a "__ chairs for all tables" box (+/− or type) and a +/− box for each table (1–20). Seats show on QR cards, dashboard cards ("3 phones · 6 seats", with a warning if more phones than chairs), the waiter portal, the kitchen TV, the plan view and the 3D floor (with that many chairs).

**Dish details.** Tap a dish to see its photo (or a coloured initial), local name, price, veg dot, description, spice level, allergens and a nutrition panel: a kcal ring split by macros and bars for protein, carbs, fat and fibre with grams and % of calories. Values come from the owner first, then from computed IFCT/NIN data, otherwise *"Nutrition info not available for this dish."* Nothing is guessed.

**Kitchen TV.** The owner opens **📺 Kitchen display** on the dashboard and puts the secret link on any TV. One tap on ▶ Start turns on sound and full screen. Tickets show the table, seats, order number, big quantities and an mm:ss timer that turns **amber at 10 minutes** and **red at 20**. Only ACCEPTED / PREPARING orders appear; served orders disappear. It refreshes every 2 seconds and shows "Reconnecting…" instead of going blank. Each new accepted order is spoken once in Kannada (*"ಟೇಬಲ್ 4. 2 ಮಸಾಲೆ ದೋಸೆ, 1 ಫಿಲ್ಟರ್ ಕಾಫಿ."*). No prices, phones or totals are sent to it.

**Waiter portal and staff.** The owner adds waiters (name, username, 4–6 digit PIN) and assigns tables (none = all). Waiters log in at `/staff/login` with the restaurant code. The portal shows only their tables: approve or reject a table ("Are guests seated at Table 4?"), **read each item back and tick it** before Accept sends it to the kitchen, mark preparing / served, clear waiter calls, merge tables, and a floor view. Phones buzz on new events, with optional Kannada voice. Waiters can't see sales, bills, the menu editor, payments, QR codes, staff or settings; the server returns 403. The dashboard shows *who* approved a table and accepted an order.

**Merge tables.** For a big group, the owner (dashboard drawer) or a waiter (portal) merges one table into another. The merged table's QR opens the main table's order, seats add up, and there is one bill. If both tables were already ordering, guests and orders move to the main table and those phones follow automatically. Freeing the main table unmerges.

**Daily report.** `/owner/report` shows the day's verified bills, UPI vs cash, and every item sold, with a date picker. **Download CSV** opens in Excel; **Save as PDF** prints a clean report page.

**Trivia: two modes.** Tapping Play asks *Play with all tables* (the restaurant quiz and leaderboard) or *Play with my table*: a private room with its own QR and WhatsApp link (`/g/<room>`) that opens **only the game**. Players pick a nickname, the host starts, everyone gets the same question with a 15-second countdown, faster right answers score more, and there's a live leaderboard and a podium. The room closes when the table is freed or after 3 hours.

**Floor plan from a blueprint (optional).** Upload a PNG or JPG (up to 5 MB) at `/owner/floor` and drag each table (mouse or touch, snap to grid, reset to auto layout) while a live 3D preview updates. The dashboard's 3D floor lays the blueprint on the floor and puts tables where they really are; a **Plan** view shows the blueprint with live coloured markers. Owners who skip it keep the automatic layout.

## Supermarket mode and AI Meal Planner

Choose **Supermarket** when you sign up (needs `FEATURE_SUPERMARKET=true`). You land on **/store**: products (demo catalogue of ~160 groceries, CSV, or a price-list photo you check before saving), a shop link + QR, paid orders with a pick-and-pack checklist and Kannada alerts, and today's sales.

Customers can **shop directly** (search, categories, cart, or say "eradu kilo atta, ondu litre haalu") or **plan meals**: an 8-step wizard (people, budget, days, meals, appliances, diet, goal, staples), up to 100 matching recipes ranked by goal with nutrition and estimated cost, recipe detail with steps in English, ಕನ್ನಡ or हिन्दी, **read-aloud** and **hands-free mode** ("next", "ಮುಂದೆ", "आगे"), a YouTube link, then a cart of the cheapest packs with **Fill to budget** (lands ₹20–30 under, never over) and UPI payment.

Example: 4 people, ₹1,500, 2 days, veg, high protein, stove + pressure cooker → 56 recipes; 4 recipes cost ₹1,157 and **Fill to budget** brings it to ₹1,476 (₹24 under).

## How a table works

```
Guest scans QR ──► browse menu ──► "Start ordering" ──► WAITING_APPROVAL ──(waiter/owner approves)──► OPEN
                                                              │                                       │
                                                     (rejects) ▼                         orders: PENDING → ACCEPTED ──► kitchen TV
                                                          REJECTED                            → PREPARING → SERVED
                                                                                                      │
                                                                                               "Request bill"
                                                                                                      ▼
                            CLOSED ◄──(free table)── PAID ◄──(Cashfree confirms)──────────── BILL_REQUESTED
                                                                                                      │
                                                                                        (paid in cash) ▼
                                                                                                 PAID_CASH
```

Dashboard colours: grey empty · **yellow flashing** wants to start · blue ordering · **orange flashing** new order · purple bill requested · green paid · red bell waiter called.

## Payments with Cashfree

- The bill is **summed by the server** from accepted orders. The phone never sends an amount.
- After the bill is requested, no new orders can be placed.
- One payment link per bill (or per share when split). An expired link is replaced when the guest taps Pay again.
- A table is marked **PAID only after Cashfree's API confirms `PAID` with the full amount.** A signed webhook only *triggers* that check, and duplicate webhooks do nothing.
- "Paid in cash" is refused if the bill was just paid online.

## Security

| Risk | Defence |
|---|---|
| QR link shared, ordering from home | A waiter or the owner approves every table; the server refuses orders until then |
| Guessing the join code | 3 wrong tries block that phone for 10 minutes (10 per network) |
| Guessing a waiter PIN | 5 wrong PINs lock that username for 10 minutes (20 per network); PINs are salted PBKDF2 hashes |
| Waiter reaching owner screens | Every route checks on the server: waiters may only approve/reject, change order status, clear waiter calls and merge **their** tables (403 otherwise) |
| Staff cookie forged from an owner cookie | Separately signed `bd_staff` cookie |
| Kitchen link leaked | Random 32-character link, read-only, no prices or phones; **Regenerate** kills the old one |
| Game room link shared | It opens only the game; it closes with the table or after 3 hours |
| Blueprint upload | PNG/JPG only (checked by file signature), 5 MB limit, served only to the owner and staff |
| Faked payment | HMAC webhook signature + status check with Cashfree |
| Dashboard access | PBKDF2-salted passwords or Google ID token verified with Google; signed HttpOnly cookie |
| Secrets | Keys stay in `.env`; a leak check scans every page and API response |

## Architecture

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

## API reference

<details>
<summary>Show all endpoints</summary>

| Group | Method | Endpoint | Does |
|---|---|---|---|
| Owner | POST | `/api/owner/signup` · `/login` · `/google` · `/logout` | Accounts |
| Owner | GET | `/api/owner/me` · `/api/auth/config` | Owner info (incl. seats) · public sign-in settings |
| Owner | POST | `/api/owner/setup` | Tables, `seats[]`, language, Wi-Fi |
| Owner | GET / POST / PUT / DELETE | `/api/owner/menu[/{id}]` | Menu CRUD with optional dish details |
| Owner | POST | `/api/owner/menu/csv` · `/photo` · `/bulk` | CSV import, photo reading (Sarvam), save reviewed items |
| Owner | GET | `/api/owner/qr` · `/api/owner/qr/{id}.svg` | QR list and SVG codes |
| Owner | GET / POST / PUT | `/api/owner/staff[/{id}]` | Waiter accounts |
| Owner | GET · POST | `/api/owner/kitchen-link` · `/regenerate` | Kitchen TV link |
| Owner | GET | `/api/owner/report?date=` · `/api/owner/report.csv?date=` | Daily report |
| Owner | GET / PUT · POST / DELETE | `/api/owner/floor` · `/api/owner/floor/image` | Floor positions · blueprint |
| Owner | POST | `/api/owner/voice` · `/api/owner/voice/confirm` | Owner voice assistant |
| Guest | GET | `/api/t/{token}` | Table (seats, merged), restaurant, menu |
| Guest | POST | `/api/t/{token}/start` · `/join` | Ask to start · join with code |
| Guest | GET | `/api/session/{id}` | Orders, bill, status, waiter call |
| Guest | POST | `/api/session/{id}/orders` | Place an order round (409 until approved) |
| Guest | POST | `/api/session/{id}/voice` · `/budget` · `/assistant` | Voice ordering (Sarvam), budget basket |
| Guest | POST | `/api/session/{id}/call-waiter` · `/call-waiter/cancel` | Call a waiter with a reason · cancel |
| Guest | POST | `/api/session/{id}/request-bill` · `/pay` | Bill and Cashfree link |
| Guest | GET / POST | `/api/session/{id}/split` · `/split/cancel` · `/shares/{share}/pay` | Split the bill |
| Guest | GET | `/api/session/{id}/payment-status` | Re-check payment with Cashfree |
| Guest | POST · GET | `/api/session/{id}/score` · `/api/t/{token}/leaderboard?game=` | Game scores |
| Guest | GET · POST | `/api/t/{token}/quiz` · `/api/session/{id}/quiz/join` · `/quiz/answer` | Table Quiz |
| Game room | POST | `/api/session/{id}/game-room` | Create the table's private room |
| Game room | GET · POST | `/api/g/{room}/state` · `/join` · `/start` · `/answer` · `/qr.svg` | Play in the room |
| Owner or waiter | POST | `/api/session/{id}/approve` · `/reject` | Approve / reject a table |
| Owner or waiter | POST | `/api/orders/{id}/status` | ACCEPTED, REJECTED, PREPARING, SERVED |
| Owner or waiter | POST | `/api/waiter-calls/{id}/done` | Clear a waiter call |
| Owner or waiter | POST | `/api/tables/merge` · `/api/tables/{id}/unmerge` | Merge tables |
| Owner or staff | GET | `/api/floor/image` | The blueprint image |
| Waiter | POST · GET | `/api/staff/login` · `/logout` · `/api/waiter/board` | Waiter login and board |
| Kitchen | GET · POST | `/api/kitchen/{secret}/board` · `/announcements/{id}/claim` | Kitchen tickets and voice |
| Cashier | GET | `/api/dashboard` · `/api/dashboard/summary?date=` | Tables · sales summary |
| Cashier | POST | `/api/session/{id}/cash` · `/free` · `/api/shares/{id}/cash` | Close bills |
| Store / Shop / Planner | | `/api/store/…` · `/api/s/{slug}/…` | Supermarket mode and meal planner |
| Cashfree | POST | `/api/webhooks/cashfree` | Payment notification |

</details>

## Project structure

```
app/
  main.py        core routes: owner, tables, orders, bills, dashboard
  restaurant.py  kitchen TV, staff + waiter portal, merge tables, daily report, game rooms, floor plan
  features.py    voice ordering, Kannada alerts, budget basket, table quiz, menu photo
  upgrades.py    sales summary, split bill, owner voice assistant
  ai.py          Sarvam first, Gemini backup
  sarvam.py      Saaras STT, Bulbul TTS, sarvam-105b chat, Document Intelligence
  gemini.py      backup AI
  cashfree.py    payment links and webhook signatures
  store.py · planner.py   supermarket and meal planner
  summary.py · split.py · budget.py   pure functions (tested)
  web.py · db.py · auth.py · net.py · config.py
  data/          ingredients, recipes, demo products, photo credits
static/
  pages/   landing, signup, login, setup, menu, qr, dashboard, table, paid, kitchen, waiter, staff,
           staff_login, report, floor, game, store, shop, credits
  js/      common, bg3d, floor3d, dashboard, dashboard_plus, table, games, kitchen, waiter, store, shop, planner
  css/     design system and page styles
scripts/   check_sarvam.py, seed_source.py, fetch_photos.py, localize_photos.py
tests/     pytest suite (pure functions + real routes on a temporary database)
run.py · start.bat · start.ps1 · check.bat · check.py · ngrok.bat · .env.example
```

## Tests

```powershell
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest -q
```

The suite covers the money maths (bill splitting, budget baskets, meal-planner cart and fill-to-budget) and the restaurant upgrades end to end on a temporary database. That includes:
- the 409 before approval, seat validation, and owner-entered nutrition winning (never guessed)
- kitchen tickets with no prices, spoken once
- waiter permissions (403 on owner routes and on other restaurants' or unassigned tables), PIN rate-limiting
- merging tables, the CSV report, the waiter call with a reason, game rooms, and blueprint upload checks

## Demo script (4 minutes)

| Time | What happens |
|---|---|
| 0:00 | "A waiter can't be at every table. Paper menus, missed orders, long waits for the bill." |
| 0:20 | Photo of a paper menu → digital menu (Sarvam) → 8 tables with chairs → QR codes; open the floor plan and show the 3D floor matching it |
| 0:50 | A judge scans table 5 → browses the menu, taps Masala Dosa for the nutrition ring → "Start ordering" |
| 1:10 | The waiter's phone buzzes → Approve → judge says "2 masala dosa, 1 filter coffee" → cart → order |
| 1:40 | The waiter reads the order back, ticks each item, Accept → the **kitchen TV** shows the ticket and says "ಟೇಬಲ್ 5. 2 ಮಸಾಲೆ ದೋಸೆ, 1 ಫಿಲ್ಟರ್ ಕಾಫಿ" |
| 2:20 | Guest calls a waiter for water, plays "Play with my table" trivia with a friend |
| 2:50 | Request bill → receipt → Share on WhatsApp → Pay → Cashfree UPI → verified → table turns green |
| 3:30 | Owner downloads today's report (CSV / PDF). *"From a paper menu to a talking restaurant in minutes."* |

## Troubleshooting

| Problem | Fix |
|---|---|
| "Port 8000 is already in use" | `start.bat -Port 8001` (and `ngrok.bat 8001`) |
| Install fails on first run | Move the folder to a short path, e.g. `C:\Users\you\bolo-dukaan` |
| Phones can't open the QR | Run `ngrok.bat`, then **QR codes → Refresh links** |
| Mic button missing | Needs `SARVAM_API_KEY`, `FEATURE_VOICE_ORDER=true` and the HTTPS (ngrok) link |
| No spoken alerts | Set `FEATURE_KANNADA_ALERTS=true`, tap **Turn on sound** (or ▶ Start on the kitchen TV) |
| Waiter can't log in | Check `FEATURE_STAFF=true`, the restaurant code on **Staff**, and wait 10 minutes after 5 wrong PINs |
| Kitchen TV says the link changed | The owner regenerated it; open the new link from **📺 Kitchen display** |
| Google button greyed out | Add `GOOGLE_CLIENT_ID` and the page's origin in Google Cloud Console |
| Start over | Stop the server and delete the `data` folder |

## License

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE).
