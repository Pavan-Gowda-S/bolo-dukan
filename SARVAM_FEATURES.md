# Sarvam features: switches and how to demo them

Every feature below is behind a switch in `.env`. All switches are **off** unless set to `true`, and with all of them off the site behaves exactly like the `working-v1` tag.
Restart the server after changing a switch.

**AI provider.** If `SARVAM_API_KEY` is set, Sarvam is used. Gemini (`GEMINI_API_KEY`) is the backup if a Sarvam call fails.
Run `.venv\Scripts\python.exe scripts\check_sarvam.py` (optionally with a menu photo or PDF path) to test the key.

**Ground rules (enforced in code):**
- The AI never decides money: prices, totals, availability and payment status always come from the database.
- Nothing is ordered or saved until a person taps a confirm button.
- Every AI failure shows a friendly message, and taps and forms keep working.
- `SARVAM_API_KEY` stays on the server and is never sent to the browser.

| Switch | What it does | Fallback |
|---|---|---|
| `FEATURE_KANNADA_ALERTS` | Dashboard says "ಟೇಬಲ್ 5, ಹೊಸ ಆರ್ಡರ್…" for start, order, waiter, bill, paid (after Cashfree confirms) and quiz wins. Text comes from fixed templates. Only one open dashboard speaks each alert. | The Kannada text still shows on the table card |
| `FEATURE_VOICE_ORDER` | 🎙️ on the table page: hold to talk in any Indian language → proposed cart with menu prices → **Add to order** | Type in the box, or tap the menu |
| `FEATURE_BUDGET_ORDER` | "₹ Order by budget" (budget, people, meal) or saying "₹800 dinner for 4" → a basket built by code, never over budget, plus one optional suggestion | Order normally |
| `FEATURE_VOICE_ACTIONS` | Saying "waiter ko bulao" or "bill kodi" does exactly what the buttons do | The 🔔 and Bill buttons |
| `FEATURE_MENU_PHOTO` | Owner uploads a JPG, PNG or PDF of the paper menu → Sarvam Doc AI → editable draft. Dishes with no price are highlighted and block saving. | CSV upload or typing dishes |
| `FEATURE_TABLE_QUIZ` | 🎮 → **Table Quiz (LIVE)**: tables race through 8 questions; the winning table gets a free tea added at ₹0 (needs 2+ tables) | Other games |

## Demo in 3 steps each

**Kannada alerts**
1. Open the dashboard and tap **🔔 Turn on sound**.
2. On a phone, scan a table QR → Start ordering → (approve) → order a dosa.
3. Within about 3 seconds the dashboard says the order in Kannada, once, even if two dashboards are open.

**Voice ordering**
1. Open the table page over the **HTTPS** link (ngrok), since phones only allow the mic over HTTPS.
2. Hold 🎙️ and say "eradu masala dose, ondu filter coffee".
3. Check the proposed cart and total, then tap **Add to order**. The cashier sees a normal order.

**Budget order**
1. On the table page tap **₹ Order by budget**.
2. Enter 800, 4 people, Dinner → **Build my order**.
3. The cart total is at most ₹800. Tap **Add suggestion** if one is offered, then **Add to order**.

**Voice "waiter" / "bill"**
1. Hold 🎙️ and say "waiter ko bulao". The dashboard shows the 🔔 and says "ಟೇಬಲ್ N, ವೇಟರ್ ಬೇಕು".
2. Once the cashier has accepted the orders, say "bill kodi".
3. The bill opens with the total from accepted items, and you can Pay.

**Menu photo / PDF**
1. Owner → **Menu** → pick the menu language → **📷 Upload menu photo or PDF**.
2. Check the draft table: fix names, pick categories, and fill in any red (missing) prices.
3. **Save menu**. **Cancel** changes nothing.

**Table Quiz**
1. Two tables each open 🎮 → **Table Quiz** → **Join the quiz** (it starts 30 seconds after the first join).
2. Answer 8 questions; faster correct answers score more, with one answer per table.
3. The dashboard shows "🎁 Table N won" → **Give free tea** adds the drink to their bill at ₹0.

## Tests

- `.venv\Scripts\python.exe -m unittest discover -s tests`: budget basket (fits exactly, leftover suggestion, too-low budget, unavailable items skipped, never over budget across 2,000 random menus).
- `scripts\check_sarvam.py`: real Sarvam chat, Kannada TTS, STT and (with a file) document reading.

## Not verified yet

- Voice on a real phone over HTTPS. It was tested with Sarvam-generated Kannada speech and typed text, not a phone mic.
- Menu reading on a phone camera photo or a PDF. It was tested with Sarvam Doc AI on a generated menu image with Kannada names, a two-size line and a dish with no price: 13 of 13 dishes were read correctly in about 7 seconds.
- Paying online needs Cashfree keys. The payment flow itself is unchanged.
