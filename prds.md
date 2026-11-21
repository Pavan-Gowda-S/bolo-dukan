# Bolo Dukaan — PRDs

Product requirements for Bolo Dukaan. Voice and language run on **Sarvam AI** (Gemini only as backup). One section per product area. Each PRD states the problem, the requirements, what is explicitly out of scope, and how the area is verified. Requirements marked **[SWITCH]** are gated by a `FEATURE_*` flag in `.env` and must degrade to the documented fallback when off.

---

## PRD-1: Restaurant onboarding & menu (Owner)

**Problem.** A small restaurant has a paper menu, a fixed number of tables, and no way to get online without a developer.

**Requirements**
- Owner signs up with email + password (PBKDF2-hashed) or Google ID token (verified audience/issuer/expiry/email).
- Setup flow: restaurant name, language (kn-IN / hi-IN / en-IN), Wi-Fi details, table count (max 60; type it or tap +/−).
- **Chairs per table** **[SWITCH: FEATURE_SEATS, default on]**: one number per table (1–20), typed or tapped, plus "__ chairs for all tables". `/api/owner/setup` accepts `seats[]` and rejects a list whose length isn't the table count. Seats appear on QR cards, dashboard cards, the waiter portal, the kitchen TV, the Plan view and the 3D floor. When more phones join than there are chairs, show a warning (never block).
- Menu can be created three ways: typed entry, CSV upload (Excel "Save as CSV"), or photo/PDF OCR **[SWITCH: FEATURE_MENU_PHOTO]** — OCR always produces a *draft* the owner reviews and edits before saving.
- Menu items support local-script name, category, price in **integer paise**, availability toggle, soft delete, and optional details **[SWITCH: FEATURE_DISH_DETAILS]**: description, veg/non-veg, spice 0–3, allergens and owner-entered nutrition (kcal, protein, carbs, fat, fibre). Empty means unknown, never guessed. Same fields as optional CSV columns.
- Owner can generate printable QR cards per table with the table token, Wi-Fi details, and Kannada/Hindi captions. QR links refresh when the public URL changes.

**Out of scope:** multi-location restaurants, menu versioning, printed bill templates.

**Verified by:** owner flow in README demo script; `tests/` cover price validation and state helpers.

---

## PRD-2: Table session lifecycle (Guest + Cashier)

**Problem.** Orders get lost on paper; the cashier cannot see which table needs attention.

**Requirements**
- Guest scans the table QR → **previews the menu** **[SWITCH: FEATURE_MENU_PREVIEW, default on]** (read-only: no add buttons, cart, mic or budget; banner "Ordering opens once the waiter confirms you're at the table") → taps "Start ordering" → session enters `WAITING_APPROVAL`.
- A waiter or the owner must approve before ordering begins (defends against shared/photographed QR links). Until then the server answers `409 Waiting for the waiter to confirm your table` to orders, voice, budget and assistant calls. When approved, the same screen switches to ordering without a reload.
- Session state machine (authoritative, defined in `app/db.py`):
  `WAITING_APPROVAL → OPEN → BILL_REQUESTED → PAID | PAID_CASH → CLOSED`, plus `REJECTED` from approval, and per-order `PENDING → ACCEPTED → PREPARING → SERVED` (or `REJECTED`).
- After `BILL_REQUESTED`, no new orders can be placed on that session.
- Freeing a table closes the session and invalidates its join code and QR token for that session.
- Dashboard colour contract (see `design.md`): grey empty, yellow flashing waiting, blue ordering, orange flashing new order, purple bill, green paid, red waiter bell. Grid view and 3D floor view show identical state.

**Out of scope:** reservations, tipping.

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

**Out of scope:** shift management, inventory, payroll.

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

## PRD-10: Waiter portal and staff accounts

**[SWITCH: FEATURE_STAFF]**

**Problem.** One cashier can't walk to every table; waiters need their own tool, but must not see the money.

**Requirements**
- Owner page `/owner/staff`: add a waiter (name, username, 4–6 digit PIN), assign tables (none = all), reset PIN, deactivate, copy the login link.
- `/staff/login`: restaurant code + username + PIN. 5 wrong PINs lock that username for 10 minutes (20 per network). Separately signed `bd_staff` cookie.
- `/waiter` (mobile-first): only assigned tables, coloured like the dashboard. Approve/reject ("Are guests seated at Table 4?"), read the order back and tick each item before **Accept** sends it to the kitchen, reject with a reason, preparing/served, clear waiter calls, merge tables, floor view. New events buzz, with optional Kannada voice.
- Server permissions: approve/reject, order status, waiter-call done and merge accept the owner **or** a waiter of the same restaurant and an assigned table; everything else stays owner-only (403 for waiters). `approved_by` and `accepted_by` record "owner" or "waiter:Name" and show on the dashboard.

**Verified by:** `tests/test_restaurant_upgrades.py::StaffTests` (403 on owner routes, other restaurants and unassigned tables; PIN throttling; owner cookie can't pass as staff).

---

## PRD-11: Kitchen TV display

**[SWITCH: FEATURE_KITCHEN_TV]**

**Problem.** Kitchens lose paper tickets and can't see how long a table has waited.

**Requirements**
- Owner gets a secret link (32 characters) from **📺 Kitchen display**; **Regenerate** invalidates the old one.
- `/kitchen/{secret}`: one ▶ Start tap (sound + full screen + screen wake lock), then no touching. Tickets for ACCEPTED / PREPARING orders: table, seats, order number, big quantities, local names, mm:ss timer, amber after 10 min, red after 20 min, a "Cooking" badge when preparing. Served orders disappear. Refresh every 2 s; show "Reconnecting…" instead of going blank.
- `GET /api/kitchen/{secret}/board` is read-only and carries no prices, phone numbers or totals.
- When an order is accepted, a `kitchen_order` announcement is written from a fixed template ("ಟೇಬಲ್ 4. 2 ಮಸಾಲೆ ದೋಸೆ, …") and spoken once by the kitchen TV (`kitchen_claimed`), never by the cashier dashboard.

**Verified by:** `KitchenTests` (no prices or phones, spoken once, served disappears, regenerate kills the old link).

---

## PRD-12: Guest experience upgrades

- **Dish details** **[SWITCH: FEATURE_DISH_DETAILS]**: tapping a dish opens a sheet with photo or coloured initial, name, local name, price, veg dot, description, spice, allergens and nutrition (kcal ring; protein/carbs/fat/fibre bars with grams and % of calories). Owner values first, then computed IFCT/NIN values, else "Nutrition info not available for this dish." Always labelled approx. with its source. Add-to-cart hidden in preview.
- **Call a waiter** for a reason (water, cutlery, clean the table, help to order, extra chutney, or typed). The guest sees "on the way" with the time, can cancel, and gets a tick when it's cleared. The kitchen alert speaks the reason from fixed Kannada phrases.
- **Bill as a receipt** (restaurant, tables, bill number, date, item lines with unit prices, item count, total) with **Share on WhatsApp** and the phone's share sheet.

**Verified by:** `DishDetailsTests`, `WaiterCallTests`; browser check of the sheets.

---

## PRD-13: Merge tables

**[SWITCH: FEATURE_MERGE_TABLES]**

- The owner (dashboard drawer) or a waiter (portal, own tables only) merges table B into table A for a big group. B's QR opens A's order; seats add up; one bill.
- If both were ordering, B's guests, orders and waiter calls move to A, and B's phones follow automatically. A table whose bill is requested or paid, or with a payment in progress, can't be merged.
- Unmerge any time; freeing A or paying cash unmerges.

**Verified by:** `MergeTests`.

---

## PRD-14: Daily report

**[SWITCH: FEATURE_DAILY_REPORT]**

- `/owner/report?date=` shows the day's verified bills (time, table, method, Cashfree link, amount), UPI vs cash, and every item sold with quantity and amount.
- **Download CSV** (UTF-8 with BOM so Excel shows ₹ and Kannada) and **Save as PDF** (print style). Owner-only.

**Verified by:** `ReportTests`.

---

## PRD-15: Trivia with my table

**[SWITCH: FEATURE_GAME_ROOMS]**

- Tapping Play asks **Play with all tables** (existing quiz + leaderboard) or **Play with my table**.
- A private room per table session: random 16+ character token, its own QR and WhatsApp link to `/g/{room}`, which opens only the game (no menu, cart, bill or session APIs).
- Nickname join (up to 30 players, unique nicknames); the first player is host and starts; same questions, 15-second timer and speed scoring as the table quiz; live leaderboard and podium; play again.
- The room closes when the table is freed or after 3 hours.

**Verified by:** `GameRoomTests` (answer never sent during the question, no double scoring, room token can't read the session, closes with the table).

---

## PRD-16: Floor plan from a blueprint (optional)

**[SWITCH: FEATURE_FLOOR_PLAN]**

- Owner uploads a PNG/JPG up to 5 MB (checked by file signature), stored under `data/uploads/r<id>/`, served only to the owner and staff.
- Placement editor: the image fills the editor; each table is a marker sized by seats ("T4 · 6"); drag with mouse or touch, snap to a light grid, "Reset to auto layout", live 3D preview. Positions saved as % (`tables.pos_x`, `pos_y`, 0–100).
- Dashboard **Plan** view and the waiter floor view show the blueprint with live coloured markers; tap to open the table.
- `floor3d.js` lays the blueprint on the 3D floor and places tables at their positions with as many chairs as seats; without positions it keeps the automatic layout.
- **Reading the blueprint** **[SWITCH: FEATURE_FLOOR_AI]**: walls and door gaps are traced from the image pixels in the browser (no AI); Gemini vision proposes tables (label, chairs, shape), counters and rooms; every proposal is checked against the drawn lines and shown to the owner, who taps **Apply**. The 3D floor then raises the walls, builds counters and room labels, and places tables. If Gemini is unavailable or out of quota, walls are still traced and tables can be dragged by hand.

---

## PRD-17: Tips

**[SWITCH: FEATURE_TIPS]** — once the bill is requested the guest can add 0 / 5 / 10 / 15 % or a rupee amount (max half the bill). The server works out the paise and adds it to the Cashfree link; the table is PAID only when Cashfree confirms the full amount including the tip. The receipt and WhatsApp share show the tip.

**Verified by:** `TipTests`.

---

## PRD-18: Relay AI agent

**[SWITCH: FEATURE_RELAY + RELAY_WEBHOOK_URL]** — `bill_paid`, `waiter_call` and on-demand `daily_report` events are POSTed (HTTPS, background thread) to the owner's Relay.app workflow, where AI steps summarise, alert or log them. No phone numbers or secrets in the payload; nothing is sent when off.

**Verified by:** `RelayTests`.

**Verified by:** `FloorPlanTests` (bad file type and size rejected, positions validated, image not public).

---

## Cross-cutting requirements

| Area | Requirement |
|---|---|
| Language | Every guest-facing string supports kn-IN, hi-IN, en-IN. Restaurant language set at setup. |
| AI policy | Every AI feature has an on/off switch, never decides money, always falls back to taps/forms. |
| Windows | One double-click start (`start.bat`); only pure-Python dependency (`qrcode`); std-lib server so Smart App Control never blocks it. |
| Security | See `rules.md` §Security — approved tables, join-code throttling, HMAC webhooks, signed HttpOnly cookies, HTTPS via ngrok. |
| Feature switches | `FEATURE_MENU_PREVIEW` and `FEATURE_SEATS` default **on**; every other `FEATURE_*` defaults **off**. With the new switches off the demo works exactly as before. |
| Permissions | Checked on the server for every route; hiding a button is never the security. |
| Timeouts | Every Sarvam call has a 15-second timeout and a tap fallback. |

---

## PRD-19: Games that matter to the bill

- **Bill Roulette** **[SWITCH: FEATURE_ROULETTE]**: 2–12 named players; the server loads one chamber (`secrets`) before the first pull; players pull in order; whoever hits it "pays the bill", shown on the receipt and announced. No money moves by itself.
- **Housie** **[SWITCH: FEATURE_HOUSIE]**: real tambola tickets (3 × 9, 15 numbers); one number every 7 s after a 40 s lobby; claims checked against the numbers really called; first line → free juice, full house → free starter (first valid claim wins).
- **Lucky Spin** **[SWITCH: FEATURE_LUCKY_SPIN, LUCKY_SPIN_MIN_RUPEES]**: unlocked by the accepted bill; one spin per visit; weighted result drawn on the server; the menu nudges "Order ₹X more to unlock".
- **Prizes** are added to the winning table's bill at **₹0** when staff serve them and tap Give (owner or waiter).

**Verified by:** `tests/test_table_games.py` (valid tickets, no early reveal of the loser, bogus claims refused, one spin, prize at ₹0 doesn't change the bill).

---

## PRD-20: Supermarket 3D aisle finder

**[SWITCH: FEATURE_AISLE_FINDER]** — the shopper types a product ("chips"), picks the exact type, and a 3D store shows aisles with signs, shelves, the entrance and billing counters, a glowing path from the entrance and a pin on the exact spot, plus "Aisle 7 · left side · bay 2 · top shelf". The layout is built from the store's categories (two per aisle, A–Z) so every shopper sees the same map.
