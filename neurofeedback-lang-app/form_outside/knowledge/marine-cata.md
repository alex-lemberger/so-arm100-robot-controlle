# Marine / CaTa Prototype

## Strategic Direction (2026-05-27)

- **CaTa prototype is a hybrid** — converges legacy marine UW app + CaTa Excel tool into one unified flow
- **All 13 legacy marine screens covered** in React prototype
- **Claim Analysis is the deepest merge point** — legacy provided shell; CaTa provided actuarial calculations
- **Prototype is the product definition artifact** — BA uses it with product model team; decisions flow: Prototype → Spring Boot entity → Angular
- `calc.jsx` is the authoritative spec for the backend calculation service
- **Pitch framing:** "We prototyped a unified flow — does this make sense, or are there historical constraints we should know about?" (discovery, not commitment)
- **Open question:** Why did the two tools historically exist separately? Must answer before committing to hybrid in Angular.

## Figma-First Workflow

Design defined as Figma prototype BEFORE code implementation: Figma → Review → Angular.

**Cyber Figma reference:** https://www.figma.com/design/jhJTdEHTYI1DQFz6gLBV8X/Cyber_UWWB?node-id=66-1650
**Marine page:** node-id=2016-35510

### Cognitive Mapping (Legacy → New UX)

| Legacy | New |
|---|---|
| Editable inline table | Read-only table + edit/delete per row (side panel) |
| Section with inline form | Card with edit icon (side panel) |
| Inline dropdowns/inputs | Read-only label/value display |
| Add button in table | "+ Add New" link below (green) |
| Calculation metadata | InputEl fields + Calculate button |
| Wide table (14+ cols) | Reduce to 8 most important — readability over completeness |

## CaTa Prototype — Tech Stack & Conventions

**Stack:** React 18 UMD + Babel standalone, no build step
**Serve:** `python3 -m http.server 8765` from `~/.claude/screensMarine/HDI-Marine Form/`
**Files:** `src/steps.jsx` (screens), `src/app.jsx` (shell/nav), `src/styles.css`, `src/components.jsx`, `src/calc.jsx`

### Core Pattern

`DisplayCardGrid` > `DisplayCard` (read-only) + `Drawer` (all edits)
- Draft-state: copy on open, merge on save, null on close

### Settings

- `SETTINGS_DEFAULTS` + `useState` in App
- Synced to `window.appSettings` synchronously on every render (not useEffect — avoids frame lag)
- Persisted to localStorage key `cata_settings_v1`
- Settings screen at `activeId === "settings"` (outside step array)
- Language options: en/de/fr/es/it/nl (BCP-47 code in `settings.language`)

### Locale-Aware Formatting

- `fmtDE(n)` in steps.jsx reads `window.appSettings.locale`
- `FilledNumber`/`NumberInput` in components.jsx: locale-aware text inputs (format on blur, parse on change)
- `CALC.run(state, settings)` uses settings.locale/currency
- `CALC` exports: `formatNumber`, `formatNumberPlain`, `formatDate`

### Icons

Font Awesome 6 via CDN. `Icon` component maps name → FA class in components.jsx. Unmapped names return null — always add entries to map before use.

Nav mapping: General Data=fa-id-card, Tools=fa-toolbox, Tech Adj=fa-pen-ruler, Tech Premium=fa-file-shield, Loadings=fa-tag, Analysis=fa-sliders, Summary=fa-file-contract, Final Decision=fa-file-lines, Settings=fa-gear, Exchange Rates=fa-coins

### Navigation

- Phase blocks: QUOTATION and POST-BINDING
- Legend style: label on border with `position: absolute; top: -9px` + background cut-through
- Sidebar width: 284px
- `savedSteps` Set persisted to `cata_saved_steps_v1`
- Hash-based deep linking: every step has URL (e.g. `#bcResult`, `#analysis`, `#settings`)

### Display Conventions

- **Cards:** bold label (`dfield__label`), muted value (`dfield__value`); no check in header; booleans = "Yes"/"No"
- **Tables:** `grid-tbl` class, border-collapse: separate, row shadow on td, all left-aligned, `+ Add New` at bottom
- **Green:** `#65A518` everywhere (--accent, --accent-soft, --accent-tint, --accent-ink)
- **Cancel button:** `btn--outline` with 1.5px solid border, hover #f0f0f0
- **DisplayCard grid gotcha:** uses grid by default — pass `grid={false}` and wrap in div to stack vertically
- **Nav dots:** plain `<span className="nav-dot" />` only — no done/active classes; icons 14px/#575757

### System Screens Pattern

Settings, exchange-rates must be added in 3 places in app.jsx:
1. Initial activeId resolver
2. hashchange handler
3. PartnerBanner/footer guards

### Cross-Screen Auto-Open Drawer

Flag in App state (e.g. `openRatesDrawer`) passed as prop; target screen consumes in useEffect.

### Exchange Rates

Editable EUR-base rates in Settings (separate drawer per card). Dedicated read-only `#exchange-rates` screen under System nav. "Update rates →" auto-opens rates drawer on Settings.

### Deployment

- Netlify: drop folder on netlify.com/drop (account recreated 2026-05-29, old links dead)
- Password gate: client-side in index.html before root div, sessionStorage-based

## Completed Figma Screens

All 13 steps converted to DisplayCard + Drawer pattern. Key frames:
- General Data: `2815:1138`
- Technical Adjustment: `3091:3152` (edit panel: `3129:3392`)
- Technical Premium: `3134:3392`
- Claim Analysis (3 sub-screens): Method & Limits `2925:1911`, Claim Data `2926:2203`, BC Result `2927:2449`
- Tools: `3189:4009` (Download Ready: `3200:4328`)

## Product Pipeline

Prototype → Spring Boot entity design → Angular implementation
- `calc.jsx` = backend calculation service spec
- Settings split: policy currency = DB field; locale/format = frontend only
- Pre-backend checklist in `~/.claude/docs/2026-05-29-cata-prototype-mapping-review.md`
