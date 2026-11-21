# Bolo Dukaan — Design System

The single source of truth for how Bolo Dukaan looks and behaves. All UI CSS lives in `static/css/`; tokens are defined once in `:root` in `style.css` and reused everywhere.

## Product character

A restaurant operating surface for Indian restaurants: warm, festive, a little loud — saffron and marigold against a deep night-purple — but the working screens (dashboard, table view) stay calm enough to stare at during a full shift.

## Color tokens (`static/css/style.css` → `:root`)

### Surfaces

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0613` | Page background |
| `--bg-2` | `#130b22` | Raised background |
| `--bg-3` | `#1b1030` | Higher surface |
| `--glass` / `--glass-2` | `rgba(255,255,255,.055 / .09)` | Translucent fills |
| `--glass-strong` | `rgba(24,15,42,.78)` | Toasts, strong overlays |
| `--line` / `--line-2` | `rgba(255,255,255,.11 / .2)` | Hairline borders |

### Text

| Token | Value | Role |
|---|---|---|
| `--text` | `#f7f2ff` | Primary |
| `--muted` | `#b6abcc` | Secondary |
| `--faint` | `#7d7296` | Tertiary / placeholder |

### Accents

| Token | Value | Use |
|---|---|---|
| `--saffron` | `#ff9f1c` | Primary accent, nav underline, focus ring |
| `--marigold` | `#ffc145` | Links, eyebrow text, toast icon |
| `--chili` | `#ff4d6d` | Danger / heat |
| `--rose` | `#ff3d9a` | Secondary hot accent |
| `--mint` | `#2ee6a6` | Success, switch "on" |
| `--sky` | `#4cc9f0` | Info, ACCEPTED state |
| `--violet` | `#9b5cff` | Cool accent |

### Gradients (decorative, use sparingly)

- `--grad-hot`: saffron → orange → pink — primary buttons, brand mark, active pill
- `--grad-cool`: sky → violet — `.btn.cool`
- `--grad-mint`: mint → cyan — `.btn.mint`

### Table status colors (dashboard contract)

These map 1:1 to the session state machine and must stay consistent across grid, 3D floor and table cards:

| Token | Value | Meaning |
|---|---|---|
| `--st-empty` | `#6b6584` | Empty / freed table (grey) |
| `--st-waiting` | `#facc15` | WAITING_APPROVAL — yellow, flashing |
| `--st-open` | `#3b82f6` | OPEN — ordering (blue) |
| `--st-order` | `#fb923c` | New order pending — orange, flashing |
| `--st-bill` | `#a855f7` | BILL_REQUESTED (purple) |
| `--st-paid` | `#22c55e` | PAID / PAID_CASH (green) |
| `--st-alert` | `#ef4444` | Waiter called (red bell) |

Order status tags use `.s-PENDING`, `.s-ACCEPTED`, `.s-PREPARING`, `.s-SERVED`, `.s-REJECTED` classes with `color-mix()` tinted backgrounds.

## Typography

- **Display**: `"Fraunces", Georgia, serif` — headings, brand (`--font-display`)
- **UI**: `"Plus Jakarta Sans", "Noto Sans Kannada", "Noto Sans Devanagari", system-ui` — everything else (`--font`)
- The Noto stacks are not optional: Kannada and Hindi text renders through them on every screen.
- Scale: `h1 clamp(2.2rem, 6vw, 4.6rem)`, `h2 clamp(1.6rem, 3.4vw, 2.4rem)`, `h3 1.25rem`, body `16px`
- `.eyebrow`: uppercase, `.18em` tracking, `.72rem`, marigold — section labels only
- `.mono`: `font-variant-numeric: tabular-nums` — all money and counts

## Spacing & layout

- Container: `min(1180px, 100% - 32px)`; narrow forms: `min(560px, 100% - 32px)`
- Utilities: `.row`, `.row.wrap`, `.spread`, `.stack` (gap 14px), `.grow`, `.center`
- Card padding: `.card` 24px, `.card-lg` clamp(22px, 4vw, 40px)
- Radii: `--r-sm 10px`, `--r 16px`, `--r-lg 24px`, `--r-xl 32px`
- Topbar: sticky, 66px min-height, blurred

## Components

- **`.btn`** — gradient fill, 3D solid bottom shadow, press = translateY(4px). Variants: default (hot), `.cool`, `.mint`, `.danger`, `.violet`; sizes `.sm`, `.lg`, `.block`. Ghost counterpart: `.btn-ghost` with `.active` state.
- **`.input` / `.field`** — dark fill, marigold focus border + 4px glow ring. Focus-visible outline on all interactive elements uses `--marigold`.
- **`.chip`**, **`.pill`** (scroll-snap scroller, gradient active state), **`.status-tag`** (uppercase state label)
- **`.switch`** — mint when checked; `.stepper` for quantities
- **`.toast`** — bottom-center stack in `#toasts`, spring in / ease out, kinds `ok`, `bad`, `say`
- **`.overlay` + `.sheet` / `.modal` / `.drawer`** — three dismissible layers, all `z-index` 60/61
- **`.tilt`** — pointer-tracked 3D tilt surface driven by CSS vars (`--rx/--ry/--mx/--my`)
- **`.reveal`** — scroll-entrance fade + rise, delay via `--d`

## Motion

- One easing for UI: `--ease: cubic-bezier(.2,.8,.2,1)`; spring only for playful pops: `--spring: cubic-bezier(.34,1.56,.64,1)`
- Named transitions only (`transform`, `box-shadow`, `background`, `border-color`, `opacity`)
- Ambient motion is decorative and layered behind content: `#bg3d` (Three.js background, fixed, pointer-events none, fades in via `.ready`), `.grain` overlay at 6% opacity, `.loader-orb`
- Status flashing (yellow/orange) means "needs attention now" — never flash a color that isn't a live state

## Page inventory (`static/pages/`)

| Page | Audience | Notes |
|---|---|---|
| `index.html` | Landing | Marketing hero |
| `signup.html`, `login.html` | Owner | Email/password + Google sign-in |
| `setup.html` | Owner | Tables, language, Wi-Fi |
| `menu.html` | Owner | Menu CRUD, CSV/photo import |
| `qr.html` | Owner | Printable table QR cards |
| `dashboard.html` | Cashier/Owner | Grid + 3D floor, actions, spoken alerts |
| `table.html` | Guest | Ordering, voice, games, bill, pay |
| `paid.html` | Guest | Payment confirmation |
| `store.html` | Store owner | Supermarket management |
| `shop.html` | Shop customer | Catalog, cart, meal planner |
| `credits.html` | Public | Photo credits, nutrition sources |

## Frontend JS modules (`static/js/`)

`common.js` (shared fetch/toast/helpers), `bg3d.js` + `floor3d.js` (Three.js), `dashboard.js` / `dashboard_plus.js`, `table.js`, `games.js`, `store.js`, `shop.js`, `planner.js`. Vanilla JS, no framework, no build step.

## Rules for new UI

1. Add tokens to `:root`, never hard-code hex values in component CSS.
2. Reuse existing components (`.btn`, `.card`, `.toast`, `.status-tag`) before inventing new ones.
3. Any new table/order state gets a `--st-*` token and a dashboard color — grid, floor and card must agree.
4. Money renders with `.mono` (tabular figures) in paise→rupee formatting, consistent everywhere.
5. Interface text supports kn-IN / hi-IN / en-IN; use the Noto font stack and never assume Latin-only strings.
6. Feature-gated UI must hide itself when the matching `FEATURE_*` flag is off (see `rules.md`).
