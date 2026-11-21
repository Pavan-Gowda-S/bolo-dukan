<div align="center">

<img src="static/img/logo.svg" width="88" alt="Bolo Dukaan logo">

# Bolo Dukaan for Restaurants

**Every table, talking to you.**

Set up a restaurant in minutes and get a live dashboard plus a QR code for every table.<br>
Guests order and pay from their phones by tapping **or just talking** in Kannada, Hindi or English.<br>
The cashier runs everything from one screen.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini-8E75B2?logo=googlegemini&logoColor=white)
![Cashfree](https://img.shields.io/badge/Payments-Cashfree%20UPI-6A1B9A)
![Three.js](https://img.shields.io/badge/3D-Three.js-000000?logo=threedotjs&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-one--click%20start-0078D6?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-blue)

</div>

---

## Contents

- [What it does](#what-it-does)
- [Features](#features)
- [Supermarket mode & AI Meal Planner](#supermarket-mode--ai-meal-planner)
- [Quick start (Windows)](#quick-start-windows)
- [Configuration](#configuration)
- [How a table works](#how-a-table-works)
- [Payments with Cashfree](#payments-with-cashfree)
- [Security](#security)
- [Architecture](#architecture)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Demo script (3 minutes)](#demo-script-3-minutes)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What it does

| | |
|---|---|
| 📸 **Owner** | Signs up (email or Google), snaps a photo of the paper menu, picks the number of tables and gets printable QR codes. |
| 📱 **Guest** | Scans the table QR, asks to start, orders by tapping or speaking, tracks the food live, plays a game while waiting, requests the bill and pays by UPI. |
| 🖥️ **Cashier** | Sees every table colour-coded in a grid or a 3D floor, approves tables, accepts orders, hears spoken alerts in the kitchen's language and closes bills. |

## Features

**For the owner**
- Sign up / log in with **email + password** or **Sign in with Google**
- **Menu from a photo (OCR)**: Gemini reads every dish, local-script name and price from a photo of the paper menu; the owner reviews and edits before saving
- Menu by **CSV upload** (Excel "Save as CSV" works) or typed one by one; mark dishes unavailable for the day
- **Printable QR cards** for every table with Wi-Fi details, captions in Kannada and Hindi

**For guests**
- **Voice ordering with Sarvam AI**: hold the mic and say "eradu masala dose, ondu coffee", "ಎರಡು ಇಡ್ಲಿ ವಡೆ" or "do chai aur ek samosa". You get a proposed cart at menu prices, and a reply in your language.
- **Order by budget**: "₹800, dinner for 4" builds a cart in code (no AI) that never goes over budget
- Voice "bill kodi" / "waiter ko bulao" does exactly what the buttons do
- **Shared table**: friends join with a 4-digit code, so all phones share one bill
- Live order tracker (Sent → Accepted → Cooking → Served), call-waiter button, UPI payment
- **Table Quiz (live)**: tables race through 8 questions, and the winning table gets a **free tea** added at ₹0
- **Games** while waiting: **Rickshaw Rush** (3-lane runner), **Dosa Flip** (timing), **Chai Catch** (arcade), **Spice Match** (3D memory), with a **today's top players** board per restaurant

> Every AI feature has an on/off switch, never decides money, and falls back to taps and forms. See [SARVAM_FEATURES.md](SARVAM_FEATURES.md).

**For the cashier**
- Live **grid** and an interactive **3D restaurant floor** (Three.js) with glowing status rings and beams
- Approve / reject tables, accept / reject (with a reason) / preparing / served, paid in cash, free table
- **Spoken alerts** in Kannada, Hindi or English ("ಟೇಬಲ್ 5, ಹೊಸ ಆರ್ಡರ್") via Gemini TTS, with browser voice and text fallbacks
- Today's revenue and open bills at a glance

**Upgrades (each behind its own switch)**
- **Sales summary** (A1): today's collected total, bill count, average, online vs cash donut, top items and a bill list. Only verified payments count.
- **Split the bill** (A2): equally or by items. Each person gets their own Cashfree UPI link; the table is PAID only when every share is paid (or the cashier takes the rest in cash). A Kannada alert for each share.
- **Owner voice assistant** (A3): "aaj ka collection?", "how many tables are free?", "free table 4". Answers come from the database; anything that changes data asks for a tap first.
- **Nutrition on the menu**: approx. kcal, protein, carbs and fat per dish, computed from standard recipes and IFCT 2017 / NIN data.
- **Real food photos** from Wikimedia Commons (free licences, credited at `/credits`).

**Built for Windows**
- Double-click `start.bat`. It needs only Python and **one pure-Python package** (`qrcode`).
  The web server, database and HTTPS calls use Python's standard library, so Windows **Smart App Control** never blocks a compiled file.

## Quick start (Windows)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"**.
2. Put this folder at a **short path**, e.g. `C:\Users\you\bolo-dukaan` (Windows has a 260-character path limit).
3. Double-click **`start.bat`**. The first run creates a private `.venv`, installs `qrcode` and creates `.env`.
4. Open `.env` in Notepad, add your keys (see [Configuration](#configuration)), then close the window and run `start.bat` again.
5. Double-click **`check.bat`** to test the keys: a Kannada order through Gemini, a Kannada voice alert, and a ₹1 Cashfree sandbox link.
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

## Configuration

Everything lives in `.env` (never commit it; it's in `.gitignore`). Restart after changes.

| Variable | Purpose |
|---|---|
| `SARVAM_API_KEY` | **Preferred AI**: speech-to-text (saaras), Kannada voice (bulbul), order understanding (sarvam-105b), menu photo/PDF reading (Doc AI). Get one at [dashboard.sarvam.ai](https://dashboard.sarvam.ai). Test with `scripts\check_sarvam.py` |
| `GEMINI_API_KEY` | Backup AI if Sarvam is missing or fails. Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | Default `gemini-2.5-flash` |
| `GEMINI_TTS_MODEL` / `GEMINI_TTS_VOICE` | Default `gemini-2.5-flash-preview-tts` / `Kore` |
| `GOOGLE_CLIENT_ID` | Sign in with Google. Create an OAuth **Web application** client in [Google Cloud Console](https://console.cloud.google.com/apis/credentials); add `http://localhost:8001` and your ngrok URL as **Authorized JavaScript origins** |
| `CASHFREE_APP_ID` / `CASHFREE_SECRET_KEY` / `CASHFREE_ENV` | Payment links. Use **sandbox** keys from the Cashfree merchant dashboard |
| `PUBLIC_URL` | Optional fixed public URL; leave empty to auto-detect ngrok |
| `FEATURE_*` | On/off switches for each AI feature (below) |

**Feature switches.** All are **off** unless set to `true`. With all of them off the site behaves like the `working-v1` tag. If one misbehaves during a demo, set it to `false` and restart.

| Switch | Feature | Fallback |
|---|---|---|
| `FEATURE_KANNADA_ALERTS` | Spoken Kannada dashboard alerts (one dashboard speaks each) | Text on the table card + chime |
| `FEATURE_GEMINI_TTS` | Allow Gemini's voice if Sarvam is missing | Text only |
| `FEATURE_VOICE_ORDER` | Mic ordering at the table | Type it, or tap to order |
| `FEATURE_MENU_PHOTO` | Menu photo / PDF → draft menu | CSV / typed menu |
| `FEATURE_BUDGET_ORDER` | "₹800 for 4" basket (pure code) | Order normally |
| `FEATURE_VOICE_ACTIONS` | Voice "bill" / "waiter" | Buttons |
| `FEATURE_TABLE_QUIZ` | Live quiz between tables, free tea prize | Other games |
| `FEATURE_SALES_SUMMARY` | Today's sales strip + bill list (A1) | Dashboard totals |
| `FEATURE_SPLIT_BILL` | Split equally / by items, one UPI link per person (A2) | One bill for the table |
| `FEATURE_OWNER_VOICE` | Owner voice assistant on the dashboard (A3) | Dashboard buttons |
| `FEATURE_SUPERMARKET` | "Supermarket" business type, products, store QR, direct order, pick & pack | Restaurant only |
| `FEATURE_MEAL_PLANNER` | AI meal planner in the shop (needs `FEATURE_SUPERMARKET`) | Direct shopping |
| `FEATURE_NUTRITION` | Approx. kcal / protein / carbs / fat on menus and recipes | Prices only |
| `FEATURE_PHOTOS` | Real food & grocery photos (Wikimedia Commons) | Emoji |

## Supermarket mode & AI Meal Planner

Choose **Supermarket** when you sign up (needs `FEATURE_SUPERMARKET=true`). You land on **/store**:

- **Products**: load a demo catalogue of ~160 groceries, add one by one, import a CSV, or snap a **photo of a price list** (AI reads it, you check every price before saving).
- **Shop link + QR** for the counter. Customers open `/s/<your-store>`.
- **Orders**: paid orders appear with a chime and a Kannada alert. Tick each item as you pick it, then **Mark packed** → **Handed over**.
- **Sales**: today's verified total, orders, average and top sellers.

Customers can **shop directly** (search, categories, cart, or say "eradu kilo atta, ondu litre haalu") or **plan meals**:

1. **Wizard** (8 steps, or say it all at once): people, budget, days, meals per day, appliances (3D flip cards), diet, goal (high protein, high calorie, low calorie, balanced, low carb), staples at home.
2. **Recipes**: up to 100 of 142 recipes that fit the kitchen and diet, ranked by the goal, with kcal / protein / carbs, badges, time and estimated cost. A sticky budget bar turns amber over 90 % and red over budget.
3. **Recipe detail**: ingredients scaled to your people, steps in English, ಕನ್ನಡ or हिन्दी, **read aloud**, **hands-free mode** (say "next", "repeat", "previous", "ಮುಂದೆ", "आगे"), nutrition with sources, and a **YouTube** link (or an embedded video when a recipe has a `youtube_id`).
4. **Cart**: the cheapest packs that cover every ingredient, with leftovers shown. Swap a pack, remove an item, then **Fill to budget**, which adds fruit, snacks or staples so you land **₹20–30 under** your budget and never over.
5. **Pay** with a Cashfree UPI link. The order is confirmed only after Cashfree confirms the full amount.

Example: 4 people, ₹1,500, 2 days, veg, high protein, stove + pressure cooker → 56 recipes; 4 recipes cost ₹1,157 and **Fill to budget** brings it to ₹1,476 (₹24 under).

Rules: the AI only understands speech, reads price lists and translates. Every price, quantity, total and budget decision is computed in code (`app/planner.py`, money in integer paise) and nothing is bought without a tap. Data: `app/data/ingredients.json` (97 ingredients, nutrition per 100 g with a source on every row), `recipes.json` (142), `products_demo.json` (163 SKUs, demo prices). Rebuild and validate them with `python scripts/seed_source.py`.

## How a table works

```
Guest scans QR ──► "Start ordering" ──► WAITING_APPROVAL ──(cashier approves)──► OPEN
                                              │                                    │
                                     (cashier rejects)                 orders: PENDING → ACCEPTED
                                              ▼                                → PREPARING → SERVED
                                          REJECTED                                 │
                                                                            "Request bill"
                                                                                   ▼
                     CLOSED ◄──(free table)── PAID ◄──(Cashfree confirms)── BILL_REQUESTED
                                                                                   │
                                                                     (paid in cash) ▼
                                                                              PAID_CASH
```

Dashboard colours: grey empty · **yellow flashing** wants to start · blue ordering · **orange flashing** new order · purple bill requested · green paid · red bell waiter called.

## Payments with Cashfree

- The bill is **summed by the server** from accepted orders. The phone never sends an amount.
- After the bill is requested, no new orders can be placed.
- One payment link per bill (`bd{session}c{counter}…`). An expired link is replaced when the guest taps Pay again.
- A table is marked **PAID only after Cashfree's API confirms `PAID` with the full amount.** A signed webhook only *triggers* that check. Duplicate webhooks do nothing.
- "Paid in cash" is refused if the bill was just paid online.

## Security

| Attack | Defence |
|---|---|
| QR link shared, ordering from home | The cashier approves every table first |
| Guessing the join code | 3 wrong tries block that phone for 10 minutes (10 per network) |
| Old photo of the QR | The join code dies when the table is freed |
| Faked payment | HMAC webhook signature + status check with Cashfree |
| Dashboard access | Owner login: PBKDF2-salted passwords or Google ID token verified with Google (audience, issuer, expiry, verified email); signed HttpOnly cookie |
| Public Wi-Fi | HTTPS through ngrok; card/UPI details go only to Cashfree |
| Fake high scores | Per-game score caps, guest-session token required, per-table limit |

## Architecture

```
 Phone (guest)            Browser (cashier/owner)
      │  HTTPS (ngrok)           │
      ▼                          ▼
 ┌──────────────────────────────────────────┐
 │  run.py → app/web.py  (std-lib HTTP)     │
 │  app/main.py          (all API routes)   │──► SQLite  data/bolo_dukaan.db
 │  app/gemini.py   ─────────────────────── │──► Gemini (orders, OCR, TTS)
 │  app/cashfree.py ─────────────────────── │──► Cashfree Payment Links
 │  Google tokeninfo ────────────────────── │──► Sign in with Google
 └──────────────────────────────────────────┘
 static/  HTML + CSS + vanilla JS, Three.js (3D background, 3D floor), canvas games
```

## API reference

<details>
<summary>Show all endpoints</summary>

| Group | Method | Endpoint | Does |
|---|---|---|---|
| Owner | POST | `/api/owner/signup` | Create owner + restaurant |
| Owner | POST | `/api/owner/login` | Log in (email + password) |
| Owner | POST | `/api/owner/google` | Sign up / log in with a Google ID token |
| Owner | GET | `/api/auth/config` | Public sign-in settings (Google client ID) |
| Owner | POST | `/api/owner/setup` | Tables, language, Wi-Fi |
| Owner | GET / POST / PUT / DELETE | `/api/owner/menu[/{id}]` | Menu CRUD |
| Owner | POST | `/api/owner/menu/csv` · `/photo` · `/bulk` | CSV import, photo OCR, save reviewed items |
| Owner | GET | `/api/owner/qr` · `/api/owner/qr/{id}.svg` | QR list and SVG codes |
| Guest | GET | `/api/t/{token}` | Table, restaurant, menu |
| Guest | POST | `/api/t/{token}/start` · `/join` | Ask to start · join with code |
| Guest | GET | `/api/session/{id}` | Orders, bill, status |
| Guest | POST | `/api/session/{id}/orders` | Place an order round |
| Guest | POST | `/api/session/{id}/assistant` | Voice / text ordering (Gemini) |
| Guest | POST | `/api/session/{id}/call-waiter` · `/request-bill` · `/pay` | Waiter, bill, Cashfree link |
| Guest | GET | `/api/session/{id}/payment-status` | Re-check payment with Cashfree |
| Guest | POST | `/api/session/{id}/score` | Post a game score |
| Guest | GET | `/api/t/{token}/leaderboard?game=` | Today's top players |
| Cashier | GET | `/api/dashboard` | All tables with status |
| Cashier | POST | `/api/session/{id}/approve` · `/reject` · `/cash` · `/free` | Table actions |
| Cashier | POST | `/api/orders/{id}/status` | ACCEPTED, REJECTED, PREPARING, SERVED |
| Cashier | POST | `/api/waiter-calls/{id}/done` | Clear a waiter call |
| Cashier | GET | `/api/announce?text=` | Gemini TTS audio |
| Cashier | GET | `/api/dashboard/summary?date=` | Today's sales summary (A1) |
| Guest | GET / POST | `/api/session/{id}/split` · `/split/cancel` · `/shares/{share}/pay` | Split the bill (A2) |
| Cashier | POST | `/api/shares/{id}/cash` | Take one share in cash |
| Owner | POST | `/api/owner/voice` · `/api/owner/voice/confirm` | Owner voice assistant (A3) |
| Store | GET / POST / PUT / DELETE | `/api/store/products[/{id}]` · `/csv` · `/photo` · `/bulk` · `/api/store/seed-demo` | Products |
| Store | GET | `/api/store/info` · `/api/store/qr.svg` · `/api/store/orders` | Store, QR, orders |
| Store | POST | `/api/store/orders/{id}/status` | PAID → PACKED → DONE |
| Shop | GET | `/api/s/{slug}` | Store and products |
| Shop | POST | `/api/s/{slug}/voice` · `/checkout` | Voice add, checkout (Cashfree link) |
| Shop | GET / POST | `/api/s/{slug}/orders/{id}?t=` · `/repay` | Order status, pay again |
| Planner | GET / POST | `/api/s/{slug}/planner/options` · `/recipes` · `/recipe/{id}` · `/cart` · `/voice` · `/command` | Meal planner |
| Planner | POST | `/api/s/{slug}/tts` | Read a step aloud |
| Public | GET | `/api/credits` | Photo credits and nutrition sources |
| Cashfree | POST | `/api/webhooks/cashfree` | Payment notification |

</details>

## Project structure

```
app/
  main.py        API routes and business rules
  web.py         tiny standard-library web framework
  db.py          SQLite schema and migrations
  auth.py        password hashing and signed cookies
  gemini.py      voice/text ordering, menu OCR, TTS
  cashfree.py    payment links and webhook signatures
  net.py         HTTPS client (urllib)
  config.py      .env loading and feature switches
  summary.py · split.py   sales summary and bill splitting (pure functions)
  upgrades.py    A1-A3 routes
  planner.py     meal planner maths (filter, nutrition, ranking, cart, fill to budget)
  store.py       supermarket, shop and planner routes
  data/          ingredients, recipes, demo products, photo credits
scripts/         seed_source.py (data + validation), fetch_photos.py, localize_photos.py
tests/           unit tests (python -m unittest discover -s tests)
static/
  pages/         landing, signup, login, setup, menu, qr, dashboard, table, paid, store, shop, credits
  js/            common, bg3d (3D background), floor3d (3D floor), dashboard, dashboard_plus, table, games, store, shop, planner
  css/           design system and page styles
run.py · start.bat · start.ps1 · check.bat · check.py · ngrok.bat · .env.example
```

## Demo script (3 minutes)

| Time | What happens |
|---|---|
| 0:00 | "A waiter can't be at every table. Paper menus, missed orders, long waits for the bill." |
| 0:20 | Photo of a paper menu → digital menu → "8 tables" → 8 QR codes appear |
| 0:50 | A judge scans table 5 → cashier approves → judge says "2 masala dosa, 1 filter coffee" → cart → order |
| 1:40 | Dashboard speaks "ಟೇಬಲ್ 5, ಹೊಸ ಆರ್ಡರ್" → Accept → Served (show the 3D floor) |
| 2:00 | Request bill → Pay → Cashfree UPI → verified → table turns green |
| 2:40 | Free table → the join code dies. *"From a paper menu to a voice-ordering restaurant in 2 minutes."* |

## Troubleshooting

| Problem | Fix |
|---|---|
| "Port 8000 is already in use" | `start.bat -Port 8001` (and `ngrok.bat 8001`) |
| Install fails on first run | Move the folder to a short path, e.g. `C:\Users\you\bolo-dukaan` |
| Phones can't open the QR | Run `ngrok.bat`, then **QR codes → Refresh links** |
| Mic button missing | Needs `GEMINI_API_KEY` and the HTTPS (ngrok) link |
| Google button greyed out | Add `GOOGLE_CLIENT_ID` and the page's origin in Google Cloud Console |
| Gemini voice silent | The preview TTS model sometimes returns nothing; the app retries and falls back to the browser voice |
| Start over | Stop the server and delete the `data` folder |

## License

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE).
