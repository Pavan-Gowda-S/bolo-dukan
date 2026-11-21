# Bolo Dukaan — PRDs

Product requirements for Bolo Dukaan. One section per product area. Each PRD states the problem, the requirements, what is explicitly out of scope, and how the area is verified. Requirements marked **[SWITCH]** are gated by a `FEATURE_*` flag in `.env` and must degrade to the documented fallback when off.

---

## PRD-1: Restaurant onboarding & menu (Owner)

**Problem.** A small restaurant has a paper menu, a fixed number of tables, and no way to get online without a developer.

**Requirements**
- Owner signs up with email + password (PBKDF2-hashed) or Google ID token (verified audience/issuer/expiry/email).
- Setup flow: restaurant name, language (kn-IN / hi-IN / en-IN), Wi-Fi details, table count (max 60).
- Menu can be created three ways: typed entry, CSV upload (Excel "Save as CSV"), or photo/PDF OCR **[SWITCH: FEATURE_MENU_PHOTO]** — OCR always produces a *draft* the owner reviews and edits before saving.
- Menu items support local-script name, category, price in **integer paise**, availability toggle, soft delete.
- Owner can generate printable QR cards per table with the table token, Wi-Fi details, and Kannada/Hindi captions. QR links refresh when the public URL changes.

**Out of scope:** multi-location restaurants, menu versioning, printed bill templates.

**Verified by:** owner flow in README demo script; `tests/` cover price validation and state helpers.

---

## PRD-2: Table session lifecycle (Guest + Cashier)

**Problem.** Orders get lost on paper; the cashier cannot see which table needs attention.

**Requirements**
- Guest scans the table QR → sees menu → taps "Start ordering" → session enters `WAITING_APPROVAL`.
- Cashier must approve before ordering begins (defends against shared/photographed QR links).
- Session state machine (authoritative, defined in `app/db.py`):
  `WAITING_APPROVAL → OPEN → BILL_REQUESTED → PAID | PAID_CASH → CLOSED`, plus `REJECTED` from approval, and per-order `PENDING → ACCEPTED → PREPARING → SERVED` (or `REJECTED`).
- After `BILL_REQUESTED`, no new orders can be placed on that session.
- Freeing a table closes the session and invalidates its join code and QR token for that session.
- Dashboard colour contract (see `design.md`): grey empty, yellow flashing waiting, blue ordering, orange flashing new order, purple bill, green paid, red waiter bell. Grid view and 3D floor view show identical state.

**Out of scope:** reservations, table merging across sessions, tipping.

**Verified by:** state constants and `ACTIVE_SESSION_STATUSES` / `BILLABLE_ORDER_STATUSES` tuples in `app/db.py`; dashboard tests manual via demo script.

---

## PRD-3: Ordering — tap, voice, and budget

**Problem.** Guests in a noisy restaurant type slowly on phones; language barriers stall orders.

**Requirements**
- **Tap ordering** always works: browse menu, quantity stepper, cart, submit an order round.
- **Voice ordering** **[SWITCH: FEATURE_VOICE_ORDER]**: hold mic, speak in Kannada/Hindi/English (or a mix), receive a *proposed cart at menu prices* plus a reply in the guest's language. The guest must confirm by tap — voice never places a paid order by itself.
- **Budget ordering** **[SWITCH: FEATURE_BUDGET_ORDER]**: "₹800, dinner for 4" builds a cart in **pure code** (`app/budget.py`, no AI) that never exceeds the budget.
- **Voice actions** **[SWITCH: FEATURE_VOICE_ACTIONS]**: "bill kodi" / "waiter ko bulao" perform exactly what the buttons do — no extra capability.
- **Shared table:** friends join with a 4-digit join code; 3 wrong attempts block that phone for 10 minutes (10 per network).
- AI is preferred with Sarvam (`SARVAM_API_KEY`), falls back to Gemini (`GEMINI_API_KEY`), then to taps and forms. Every AI failure path must return a usable screen, never a dead end.

**Out of scope:** AI deciding prices, quantities or totals; offline ordering; scheduled orders.

**Verified by:** `tests/test_budget.py`; `check.bat` / `scripts/check_sarvam.py` for live AI keys.

---

## PRD-4: Billing & payments (Cashfree)

**Problem.** Bill disputes and fake "I already paid" claims.

**Requirements**
- The bill amount is **summed by the server** from billable orders (`ACCEPTED`, `PREPARING`, `SERVED`). The phone never sends an amount.
- One payment link per bill; expired links are replaced on re-tap of Pay.
- Table becomes `PAID` **only** when Cashfree's API confirms `PAID` with the full amount. A signed webhook only *triggers* that re-check; duplicate webhooks are no-ops.
- "Paid in cash" is refused if the bill was just paid online.
- **Split bill** **[SWITCH: FEATURE_SPLIT_BILL]**: split equally or by items; each share gets its own Cashfree UPI link; table is `PAID` only when every share is paid or the cashier takes the rest in cash.
- All money is integer **paise** end to end; rupees only at display time.

**Out of scope:** refunds, partial captures, cards, wallet payments beyond UPI links.

**Verified by:** `tests/test_split_summary.py`; ₹1 sandbox link via `check.bat`.

---

## PRD-5: Cashier dashboard

**Problem.** The cashier needs one screen that answers "what needs me now?" during a rush.

**Requirements**
- Single view of every table: colour-coded grid **and** interactive 3D floor (Three.js) with status rings/beams; both driven by the same `/api/dashboard` payload.
- Actions: approve/reject table, order status (accept / reject-with-reason / preparing / served), paid in cash, free table, clear waiter call.
- Today's revenue and open-bill count visible at a glance.
- **Spoken alerts** **[SWITCH: FEATURE_KANNADA_ALERTS]**: one dashboard instance speaks each event in the restaurant's language (Kannada/Hindi/English) via server TTS; fallback is text on the table card + chime. **[SWITCH: FEATURE_GEMINI_TTS]** gates the Gemini voice fallback specifically.
- **Sales summary (A1)** **[SWITCH: FEATURE_SALES_SUMMARY]**: collected total, bill count, average, online vs cash donut, top items, bill list — only verified payments count.
- **Owner voice assistant (A3)** **[SWITCH: FEATURE_OWNER_VOICE]**: read-only answers from the database; anything that mutates data requires a confirming tap.

**Out of scope:** staff accounts/roles, shift management, inventory.

**Verified by:** demo script steps 1:40–2:40; `app/summary.py` pure functions under test.

---

## PRD-6: Games & engagement (Guest wait time)

**Problem.** Guests wait 10–20 minutes for food with nothing to do.

**Requirements**
- **Table Quiz** **[SWITCH: FEATURE_TABLE_QUIZ]**: tables race through 8 questions; winning table gets a free tea added at ₹0 (server-side, no AI).
- Four waiting games: Rickshaw Rush, Dosa Flip, Chai Catch, Spice Match — canvas/3D, no network dependency beyond score posting.
- Per-restaurant "today's top players" board.
- Anti-cheat: per-game score caps, guest-session token required, per-table rate limit.

**Out of scope:** multiplayer real-time games beyond the quiz, prizes other than the scripted free item.

---

## PRD-7: Supermarket mode

**[SWITCH: FEATURE_SUPERMARKET]** — requires selecting "Supermarket" business type at signup.

**Problem.** The same order/pay/alert machinery should work for a counter-service grocery store.

**Requirements**
- `/store` management surface: products (add, CSV import, price-list photo OCR with owner review, ~160-SKU demo seed), shop QR for the counter, order queue.
- Customer shop at `/s/<slug>`: search, categories, cart, direct checkout.
- Order flow: paid orders appear with chime + Kannada alert → tick items while picking → `Mark packed` → `Handed over`.
- Store sales view: today's verified total, orders, average, top sellers.
- Voice add-to-cart in the shop ("eradu kilo atta, ondu litre haalu") under the same AI rules as PRD-3.

**Out of scope:** inventory counts, expiry dates, delivery.

---

## PRD-8: AI meal planner

**[SWITCH: FEATURE_MEAL_PLANNER]** — requires `FEATURE_SUPERMARKET`.

**Problem.** Households plan meals across budget, diet, appliances and leftovers by hand.

**Requirements**
- 8-step wizard (or one-shot voice): people, budget, days, meals/day, appliances, diet, goal, staples at home.
- Recipe filtering/ranking runs in code (`app/planner.py`): kitchen + diet filter, goal ranking, up to 100 of 142 recipes with kcal/protein/carbs, time, badges, estimated cost.
- Sticky budget bar: amber over 90%, red over budget.
- Recipe detail: ingredients scaled to party size, steps in en/kn/hi, read-aloud TTS **[SWITCH: related TTS]**, hands-free voice commands ("next"/"repeat"/"previous"), nutrition with sources, YouTube link when `youtube_id` exists.
- Cart: cheapest pack combination covering every ingredient with leftovers shown; user can swap packs; **Fill to budget** lands ₹20–30 under budget, never over.
- Pay via Cashfree; order confirmed only after full-amount confirmation.

**AI boundary:** AI may understand speech, read price lists, and translate. Every price, quantity, total and budget decision is computed in code with money in integer paise. Nothing is bought without a tap.

**Data:** `app/data/ingredients.json` (97 rows, nutrition per 100 g + source), `recipes.json` (142), `products_demo.json` (163 SKUs). Rebuild/validate with `python scripts/seed_source.py`.

**Verified by:** `tests/test_planner.py`.

---

## PRD-9: Nutrition & photos

- **[SWITCH: FEATURE_NUTRITION]** — approximate kcal/protein/carbs/fat per dish from standard recipes and IFCT 2017 / NIN data; must be labelled approximate and carry sources at `/credits`.
- **[SWITCH: FEATURE_PHOTOS]** — real food/grocery photos from Wikimedia Commons under free licences, credited at `/credits`; emoji fallback when off.

---

## Cross-cutting requirements

| Area | Requirement |
|---|---|
| Language | Every guest-facing string supports kn-IN, hi-IN, en-IN. Restaurant language set at setup. |
| AI policy | Every AI feature has an on/off switch, never decides money, always falls back to taps/forms. |
| Windows | One double-click start (`start.bat`); only pure-Python dependency (`qrcode`); std-lib server so Smart App Control never blocks it. |
| Security | See `rules.md` §Security — approved tables, join-code throttling, HMAC webhooks, signed HttpOnly cookies, HTTPS via ngrok. |
| Feature switches | All `FEATURE_*` default **off**; with all off the site matches the `working-v1` baseline. |
