# UWWB Knowledge Bundle

> Auto-generated 2026-06-12. Do not edit directly — edit the source files instead.
> Covers: architecture, active features, parked features, patterns, tooling, marine/CaTa, collaboration.

---

# Knowledge Catalog

> Offline-first knowledge base for the HDI UWWB workspace.
> Hand `BUNDLE.md` to any LLM for full context in one prompt.

Last bundled: 2026-06-12

## Contents

| File | Domain | Summary |
|------|--------|---------|
| architecture.md | System design | Data flow, 3-layer pattern, key file locations, state management decisions |
| features-active.md | Current work | Offer list enrichment, coverage detail redesign, broker card, DMS integration |
| features-parked.md | On hold | Inplace editing (parked POC), Odin migration, exclusions rework, coverage table review |
| patterns-and-gotchas.md | Lessons learned | PrimeNG fixes, readonly guards, NGXS race conditions, viewport directive |
| tooling.md | Dev environment | Local startup, mocking, Azure DevOps API, grep blindspot |
| marine-cata.md | Marine product | CaTa prototype, UI conventions, calc spec, strategic direction |
| collaboration.md | Team rules | Shared component policy, self-improvement loop, PR standards |
| guardrails.md | Decision framework | Hard stops, binary decision trees, pattern templates, verification gates |

## Usage

### Claude Code (daily driver)

You change nothing. It already works:

1. Start in `~/liability/`
2. AGENTS.md auto-loads → includes the Knowledge Catalog pointer
3. Knowledge files are read on-demand when a topic becomes relevant
4. After a significant session → relevant knowledge file gets updated, then `./bundle.sh`

### Local Model (OpenCode, Aider, LM Studio, Ollama)

**Setup (OpenCode):** Already configured via `opencode.json` — loads `guardrails-slim.md` automatically. Knowledge files available on-demand via `@knowledge/filename.md`.

**Setup (Aider):**
```bash
cd ~/liability
aider --read knowledge/guardrails-slim.md
```

**Setup (LM Studio / Ollama chat):**
```bash
cat knowledge/guardrails-slim.md | pbcopy
# Paste into system prompt field
```

### How to Prompt the Local Model (Critical)

Local models (20B-32B) follow guardrails for pattern conformance but **cannot refuse explicit file-path instructions**. They lack the reasoning to override a direct task with a system rule. Adapt your prompts accordingly:

**DO — scoped, feature-local, explicit boundaries:**
```
Add a GetRiskScores action and state handler in the cyber risk-profile domain.
Follow the existing queryAsyncState pattern.
```
```
The dropdown renders too wide in turnover-split-overview.
Fix with a feature-local workaround in risk-profile-view. Do NOT edit shared libs.
```

**DON'T — naming shared-lib files as targets (model will comply blindly):**
```
Fix libs/uwwb-components/src/lib/form/form.component.ts
```

**Rule of thumb:** Never mention a file path you don't want the model to touch. Describe the problem + scope instead.

### What Local Models Are Good At

- ✅ Scaffolding (new components, actions, selectors, state, postactions)
- ✅ Pattern replication (given a template, produce conformant code)
- ✅ Mechanical edits (rename, add fields, extend existing patterns)
- ✅ Following explicit instructions within a named feature

### What Local Models Cannot Do (Use Claude Code Instead)

- ❌ Judgment calls ("where should this fix go?")
- ❌ Self-restraint (refusing to edit a file you mentioned)
- ❌ Architecture decisions (new patterns, cross-feature changes)
- ❌ Debugging complex issues (race conditions, state lifecycle)

### Team Review

Open individual domain files in browser or PR. Each file is self-contained and reviewable independently.

### Onboarding (new dev or AI)

Hand them: AGENTS.md (conventions) + BUNDLE.md (accumulated knowledge) + guardrails.md (decision rules).

## Keeping It Fresh

| When | Do |
|------|-----|
| After a significant Claude Code session | Update the relevant knowledge file |
| Before handing off to local model | Run `cd knowledge && ./bundle.sh` |
| After a PR with new learnings | Add to patterns-and-gotchas.md or features-active.md |
| Feature moves active → parked | Move entry between files |
| Feature completed & shipped | Remove from features-active.md |

## Regenerating BUNDLE.md

```bash
cd knowledge && ./bundle.sh
```

Run this before handing off to a local model or after editing any catalog file.

## Expanding for New Backends

The catalog covers the shared Angular frontend + cross-cutting knowledge. When backend-specific knowledge grows:

1. Create `backend-{product}.md` (e.g. `backend-marine.md`)
2. Add it to `bundle.sh`'s for-loop
3. Add a row to the Contents table above
4. Run `./bundle.sh`

Current products: liability, property, cyber, marine (upcoming).
OpenCode always starts from `~/liability/` (workspace root) — `opencode.json` catches everything.

## Quick Reference

```
~/liability/
  AGENTS.md                    ← Claude Code + OpenCode read this automatically
  opencode.json                ← loads guardrails-slim.md into OpenCode context
  knowledge/
    guardrails-slim.md         ← always loaded (2KB, fits in attention)
    guardrails.md              ← full version (for Claude Code / frontier models)
    BUNDLE.md                  ← full knowledge bundle (for frontier models or manual lookup)
    bundle.sh                  ← run after edits: ./bundle.sh
    [domain files]             ← edit these, not BUNDLE.md; local model reads via @file
```

---

# Architecture

## Key Decisions

- **Editing pattern:** slide-panel + uwwb-form + AsyncState<T> (not inplace editing — that's a parked POC, maintenance only)
- **Feature scaffolding:** mandatory 3-layer pattern (openapi / domain / view)
- **State management:** NGXS with AsyncState<T>, queryAsyncState, mutateAsyncState, createAsyncSelectors
- **Shared libs policy:** Do not edit uwwb-components or libs/styles without cross-team approval; prefer feature-local workarounds

## Data Flow

Frontend (Angular 21) → liability-application (Spring Boot BFF) → liability-ios (FaktorZehn IOS engine)
External: Pricing service, Partner service (both via Feign)

## Key File Locations

- Global style overrides: `libs/styles/overrides/` (imported via `libs/styles/styles.scss`)
- Risk profile views: `libs/feature/cyber/risk-profile/risk-profile-view/src/lib/`
- App-level state: `libs/global-domain/` (`@liability/domain`)
- Global OpenAPI client: `libs/openapi-liability/` (`@liability/openapi`)
- Utilities: `libs/utils/` (`@liability/utils`)
- Shell/routes: `@shell`
- Default status list: `libs/global-domain/src/assets/default-status-list.json`

## State Pattern (per feature)

4 files per domain: actions, state, selectors, postactions.
- Actions: top-level imports, minimal payloads
- State: AsyncState<T>, queryAsyncState/mutateAsyncState
- Selectors: createAsyncSelectors(State, 'key') → { loading, error, data, asyncState, mutationStatus, mutationError }
- Postactions: @Injectable() service handling UI side effects (notifications, panels, blockUI, navigation)

## Feature Status / Nav Progress

- `AppSelectors.featureStatus(name)` reads `state.statusList[name].valid`
- Populated by `AppStateActions.GetStatus` → `progressController.getStatus(offerNumber, optionIndex)`
- `RefreshWorkspace` dispatches `GetStatus` + `GetHeaderInformation`

## Shared Notification Components

- `UwwbCalculationNotificationBannerComponent` (`libs/uwwb-components/src/lib/calculation-notification-banner/`) — inputs: type, title, message, showCancelButton, cancelButtonLabel
- `UwwbCalculationErrorToastComponent` (`libs/uwwb-components/src/lib/calculation-error-toast/`) — inputs: mailtoHref, title, subtitle, reportButtonLabel; fixed bottom-right overlay
- Submit banner: SummaryState manages submitBannerType, wires to SelectOfferActions.UpdateStatus lifecycle via NGXS Actions stream

## Read-Only Mode Guard

Any view with edit actions must guard with `AppSelectors.readOnlyMode` from `@liability/domain`:
- Action buttons: `[readOnly]` on uwwb-actionelement
- Controls: checkboxes/toggles → `[disabled]`
- Cards: `[readonly]` on cardClick
- Tables: conditionally omit edit column or guard callback
- Add buttons: `[disabled]`
---

# Active Features

Features currently in progress or recently completed. Check branch status before resuming work.

## Offer Table Enrichment

**Stories:** 710110, 710118, 710122 | **Branch:** `feature/710110-710118-710122-offer-table-filters` | **PR:** #287863
**Status:** Frontend workaround merged. Team decided (2026-06-11) to pursue backend approach — backend stories handed to BA.

**Problem:** `GET /offer/v2` doesn't return partnerName, policyNumber, typeOfBusiness.

**Solution (temporary):** Fan-out N×2 calls via `GetOfferEnrichments` action. Results in `offerEnrichments: Record<string, OfferEnrichment>` map in AppState. Client-side `contains` filter in `enrichedOffers` selector.

**Critical details:**
- `loading: false` must be set in `GetOfferEnrichments` (after forkJoin), NOT in `getPaginatedOffers`
- `cancelUncompleted: true` prevents race on rapid pagination
- Column names must be flat (`partnerName`), not dotted paths (`offer.partnerName`)
- i18n: use `NEW_BUSINESS`/`RENEWAL`/`ENDORSEMENT` (NOT `NEWLY_CREATED`/`COPIED_AS_RENEWAL`)

**Migration path:** When backend ships, remove OfferEnrichment/OfferTextFilters, remove GetOfferEnrichments, restore loading to getPaginatedOffers, wire server params. Backend contract: `docs/superpowers/specs/2026-06-10-offer-list-backend-contract.md`.

## Coverage Detail UX Redesign

**Branch:** `feature/coverage-detail-list-redesign`
**Status:** Spec + plan + 2 prototypes done. Awaiting user feedback before implementation.

**Change:** List-detail layout replacing TabView for coverage details.

## Broker Data Card

**Branch:** frontend+backend `feature/668936-broker-agreement`, uwwb-api `feature/668936-broker-agreement-rules`
**Status:** Wired to real API across 3 repos.

**Deploy order:** uwwb-api → npm publish → frontend. Field change guide + local testing workflow documented.

## DMS Integration (Doxis WebCube)

**PR:** #280722
**Status:** Awaiting merge. BA questions on popup vs iframe resolved. Pipeline needs re-run after merge.

## Coverage Table Optimization

**Status:** 2 high-priority items fixed, 7 lower-priority remain.

**Done:**
- #1: Collapse/expand moved to view layer (no longer triggers expensive selector recompute)
- #6: `cancelUncompleted` race condition on `ToggleCoverageSelected` fixed — concurrent toggles now parallel, `applyResponse` reads current state

**Remaining (lower priority):** Redundant enrichCoverageTree (6 calls), passthrough computed signal, method calls in template per row, missing trackBy, hardcoded validation field paths, dead code callbackValidationMessages, GetCyberContract snapshot mismatch.
---

# Parked & On-Hold Features

Features that are paused, awaiting external input, or maintenance-only. Preserved here for context when touching related code.

## Inplace Editing (Parked POC — maintenance only)

**Status:** Not for new features. Existing risk-profile code (GeneralInformation, RiskAssessment, StandardsCertifications, ExclusionsAndDefinitions) maintained as-is.

**Why parked:** Confirmed by user — won't be adopted. New features use slide-panel + uwwb-form + AsyncState<T>.

### Architecture (reference only)

**Dual state pattern:**
```typescript
interface XxxStateModel {
    saved?: Resource | null;   // last persisted server response
    edited?: Resource | null;  // validate-only response (carries messages)
}
```
- GET: sets both saved + edited
- UPDATE with onlyValidate=true: sets only edited
- UPDATE with onlyValidate=false: sets both
- RESET: `ctx.patchState({ edited: state.saved })`

**validateAndSave pattern:** Component dispatches validate (true) → checks messages → dispatches save (false). `hasErrorMessage` util in `risk-profile-view/src/lib/inplace-validation.util.ts`.

**Postactions:** Every inplace state needs `XxxPostactions` (@Injectable), registered in routes.ts providers alongside state.

**Label convention:** `uwwb-label-field` and `uwwb-inplace-field` append `.LABEL` internally. Model labels must NOT include `.LABEL`. Exception: `CollapsibleGroupModel` uses `| translate` directly.

**Alignment fix:** Read-only fields need 8px padding-left via `::ng-deep uwwb-inplace-card div.p-2 > uwwb-label-field > div { padding-left: 8px; }` in feature SCSS.

### Known issues
- Risk-profile states pass offerNumber in action payload (should read from AppSelectors)
- hasErrorMessage util duplicated in cyber-program-coverage-view
- Risk-profile states don't use AsyncState<T>

## Odin Migration — Option C

**Status:** Awaiting feedback from system architect + Odin team.

**Plan:** Incremental CDK-based migration: Slide Panel → Form → Toast → Card → Table. Preferred location: inside Odin repo (contributing directly to hdi-components).

**8 P0 blockers remain:** Table, Form, Slide Panel, Toast, Editor, Card, Skeleton, Tree Table.

**Key decisions:**
- Use Angular CDK (already v21.2.8 in deps) + Odin design tokens as foundation
- Keep same public API as uwwb-components (drop-in replacement per feature)
- Coexistence: both libraries side-by-side during transition

**Impression:** Odin team delivers "website" components, not "enterprise app" components. May need architecture-level escalation.

## Exclusions & Definitions Review Rework

**Status:** Full DOR available, not yet started.

**Scope:** Frontend-only. Replaces dropdown (SELECT) with checkbox for exclusion status. Adds colored status badges (INCLUDED=green, EXCLUDED=red, NA=gray).

**Key decisions:**
- Badge component moves from property domain to uwwb-components (Nx boundary fix)
- Overview stays in CardModel pattern with `type: 'template'` + templateRef
- Edit panel: FormControlType.CHECKBOX. NA rows → disabled. Transform boolean↔IdAndLabel at view boundary.
- Data model: `IdAndLabelResourceEventExclusion.IdEnum` = `'INCLUDED' | 'EXCLUDED' | 'NA'`

## Coverage Table Data Flow Review

**Status:** 10 findings documented. Two HIGH items first.

**Priority list:**
1. (HIGH) No ngxsOnInit — option change does not re-load coverage data
2. (HIGH) GetCyberContract should read offerNumber/optionIndex from state, not action payload
3. (MEDIUM) `depth` field on CyberCoverageResource belongs on CoverageNodeModel, not domain type
4. (MEDIUM) Missing debounce on coverage search input
5. (MEDIUM) `editingContractHasValidationErrors` hardcodes field paths — brittle on API change
6. (MEDIUM) `filterSelectedCoverageNodes`/`filterCoverageNodesByName` in wrong file (selectors, not utilities)
7. (MEDIUM) `as unknown as` type assertion at component/table boundary
8. (LOW) `callbackValidationMessages` dead code
9. (LOW) Duplicate dispatch pattern in postactions success handlers
10. (LOW) Sync-only actions misleadingly included in error handler

See `docs/reviews/coverage-table-data-flow-review.md` for full details.

---

# Patterns & Gotchas

## PrimeNG Fixes / Workarounds

### Drawer Mask Bug (v21)
- `p-drawer` leave animation `animationend` may not fire, leaving orphaned `.p-drawer-mask` in DOM
- **Fix:** `ViewChild` + `destroyModal()` per instance, with `effect(onCleanup)` to cancel stale timeouts
- **Reference:** `~/.claude/docs/2026-04-23-primeng-drawer-mask-bug.md`

### Table Component Filters
- In lazy mode, `loadServerData` fires on every filter change.
- Only `dateEquals` and `inArray` match modes are re-applied client-side (`isClientSideFilter`).
- `contains` fires the server call but no client-side re-application — for enriched/computed fields not in API.
  - Store filter values in state and apply in the selector instead.
  - **Critical:** When a selector-level filter is active, `loading: false` must be deferred until enrichment data is available.
    Setting it too early causes table to render empty result while enrichments are in-flight.

### TreeTable Column Alignment
- PrimeNG's `p-treeTable` auto-aligns columns with `p-column` headers.
- For proper alignment, ensure all columns use `<p-column>` or remove them from `<p-treeTable>` entirely.

## Read-Only Mode

**Pattern:** Check `AppSelectors.readOnlyMode` from `@liability/domain` in components and templates.
- Buttons: `[readOnly]` on uwwb-actionelement
- Controls: checkboxes/toggles → `[disabled]`
- Cards: `[readonly]` on cardClick
- Tables: conditionally omit edit column or guard callback

**Gotcha:** Read-only guards must be applied consistently — any action that can change data state should be guarded.

## AsyncState Flow Pattern

### Pattern
- State keys = names of AsyncState<T> fields in state class (e.g., resource, editingResource)
- Query actions → `queryAsyncState({ ctx, key: 'resource', request: api.load() })`
- Mutate actions → `mutateAsyncState({ ctx, key: 'editingResource', ... })`

### Key Rules
- **All async data** uses `AsyncState<T>` with helpers from `@liability/utils`:
  - Queries (GET): `queryAsyncState(...)` stores identifiers, then queries
  - Mutations (POST/PUT/DELETE): `mutateAsyncState(...)` optimistic updates, rollback on failure
- **State reads its own data:** `ctx.getState()` (not action payload)
- **Action payloads minimal**: Load* stores identifiers; Reload*, Edit*, Save* read from `ctx.getState()`
- `cancelUncompleted: true` on validators and reloads (NGXS cancellation)
- **Validation = mutateAsyncState** on `editingResource`, not `queryAsyncState`
- All features must implement offer context lifecycle (reset state on `OfferContextReady`/`Cleared`)
  - `onOfferContextReady(actions$, ctx, INITIAL_STATE)`
  - Listen to changes in other features with EventBus pattern
- **Selectors:** `createAsyncSelectors(RiskProfileState, 'resource')` → `{ loading, error, data, asyncState, mutationStatus, mutationError }`
  - Derived selectors compose from async selectors

## NGXS State Pattern

### Action Handlers
- Actions must return observable that NGXS can handle (for lifecycle tracking)
- Use `return` when calling `queryAsyncState`/`mutateAsyncState`

## Angular Reactivity Gotchas

### Signals & Templates
- Always invoke signals in templates (`mySignal()` not `mySignal`)
- Track functions (e.g., `trackById`) must be invoked (`track trackById` not `track trackById()`)

### Immutable Updates
- Never mutate signal values directly:
  ```ts
  // ❌ BAD: mutation
  this.items()[0].quantity = 5;
  
  // ✅ GOOD: immutable update with update()
  this.items.update(items => items.map(i =>
    i.id === id ? {...i, quantity: newQty} : i
  ));
  ```

### Effects & AfterRenderEffect
- `effect()` only for side effects (logging, localStorage) — never for mutations
- `afterRenderEffect()` for DOM reads/writes after render

## Component Lifecycle Gotchas

**ngAfterViewInit:** Never mutate signal values here → ExpressionChangedAfterItHasBeenCheckedError
- Use `PendingTasks` service for async stability in zoneless apps
---

# Tooling

## Local Development Setup

### Angular (frontend)

```bash
cd liability-frontend
npm install --include=optional      # Initial setup
npm ci                              # Clean install when node_modules is stale/corrupted after merge
npm start                           # Serve liability-app (local)
npm run start:property              # Serve property-app
npm run start:cyber                 # Serve cyber-app
npm run start:generic:no-auth       # Serve generic-app (no auth)
npx nx test <project>               # Unit tests (Jest)
npx nx lint <project>               # ESLint
npm run generate:<domain>           # Regenerate OpenAPI client (e.g. generate:openapi-cost-data)
```

### Spring Boot (backend)

```bash
cd liability-application
./mvnw clean install            # Full build
./mvnw spotless:apply           # Format code
# Local: use Spring profile "local", "noauth" to disable OAuth2, "partnermock" for mock partners
```

## Frontend Mocking Setup

- Local mocking via Mockoon (see `liability-application/mockoon/`)
- `--no-auth` profile disables OAuth2 auth in Angular and in backend services
- `npm run start:no-auth` is equivalent to `npm run start` with `NO_AUTH=true` env var

## E2E Tests

```bash
STAGE=local IS_HEADLESS=false npx playwright test
```

Tests use:
- Page Object Model pattern with reusable logic in `teststeps/`
- Test data in `testdata/`
- Custom helpers instead of Playwright's `input.fill()` for Angular compatibility

### Tags & Organization
- Tests tagged with `@property`, `@liability`, or `@shared` as appropriate.
- Organized into: `tests/e2e/` (happy paths), `tests/regression/`, `tests/sanity/`, `tests/smoke/`, `tests/icp/`

## Azure DevOps API Access

The UWWB project uses Azure DevOps for CI/CD with several important considerations:
1. The pipeline configuration files are located in `liability-application/pipelines/`
2. For accessing Azure DevOps APIs directly, we use the `az` CLI tool.
3. Authentication is done via service principal, which requires a token for API access.

### Common Commands
```bash
# List projects
az devops project list

# Get build definition details (for pipeline setup)
az pipelines show --id <pipeline-id>

# Get build logs
az pipelines build log show --build-id <build-id>
```

## grep Limitation

**The project's grep configuration contains a blindspot for finding Angular component selectors.**

For example, running:
```bash
grep -r "selector.*my-component" .
```
will not find the selector that lives in a component like:
```ts
@Component({
  selector: 'app-my-component',
  ...
})
export class MyComponent {}
```

This is due to the current grep setup. When searching for component selectors or Angular directives, we should use a more targeted approach.
---

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

---

# Collaboration Rules

## Shared Components Policy

**Rule:** Do NOT edit shared libraries (`libs/uwwb-components`, `libs/styles/overrides/*`) unless explicitly asked. Default to feature-local workaround even when slightly less elegant.

**Why:** These libs are consumed by multiple teams. Any change requires cross-team defense in review (2+ teams), which significantly slows work.

**How to apply:**
- Fix could go in shared primitive OR feature → always pick feature
- Acceptable local patterns: helper component with ViewEncapsulation.None + local SCSS, `:has()` selectors, Renderer2 style injection
- Before editing anything under `libs/uwwb-components/` or `libs/styles/` → stop, propose local alternative first
- If shared edit is genuinely the only option → flag explicitly and ask before touching

**Example:** Turnover-split slide-panel width fix — solved with local `risk-profile-turnover-split-panel-style` helper component using `:has()` selector, instead of rewriting `_sidebar.scss`.

## Self-Improvement Loop

**Principle:** The self-improvement loop (capture → apply → prune) is the most important meta-aspect of this project's development process.

**Why:** Every PR, architectural decision, and recurring mistake is a learning signal. Without systematic capture, guidelines go stale and sessions repeat mistakes.

**How to apply:** At the end of any significant session, PR, or after receiving code review feedback — proactively update knowledge catalog or CLAUDE.md. Don't wait to be asked.

### Triggers (capture immediately)
- PR feedback that required a code change → update relevant knowledge file
- A pattern appearing in 3+ places that isn't documented → add to patterns-and-gotchas.md
- A bug whose root cause was an architectural violation → add as a hard stop or gotcha
- A guideline that caused confusion → clarify or remove it

### Prune regularly
- Rule not triggered in 3+ months → remove or collapse
- Two rules that contradict → resolve, document the winner
- Section never consulted → dead weight, cut it

## Code Review Standards

(Detailed conventions live in AGENTS.md — this section captures accumulated review learnings)

- Guard all edit actions with `AppSelectors.readOnlyMode` in every new view
- Never skip the failing-test step in TDD — even for "obvious" implementations
- Prefer `selectSignal` over `select` + async pipe in new components
- Always check if feature state is lazy-loaded — selectors need `?.` optional chaining
- When touching cyber-program-coverage, check the 10-item priority list in coverage-table-review-pending first
- Postactions must always be paired with state — never register one without the other
- Feature-local SCSS workarounds are preferred over shared lib edits, even if less elegant

---

# Guardrails

You are a constrained executor. You do not innovate. You do not invent.
You copy existing patterns and adapt them minimally. When you cannot find
a pattern to copy, you stop and say: "No pattern found for [X]."

Your job is to produce code that looks like it was written by the same
developer who wrote the rest of this codebase. Not better. Not different. The same.

---

## PRE-FLIGHT CHECK — RUN THIS BEFORE EVERY TASK

Before writing a single line of code, answer these questions. If ANY answer is YES, REFUSE the task and propose an alternative.

```
1. Does this task ask me to edit a file under libs/uwwb-components/ or libs/styles/
   WITHOUT the user explicitly naming that file as the target?
   → YES = REFUSE. Say: "This would require editing shared library [X]. Propose feature-local fix instead, or confirm you want me to edit the shared lib."

2. Does the task reference a file path I cannot find or verify in the codebase?
   → YES = REFUSE. Say: "Cannot verify file path. Please confirm it exists."

3. Does this task require me to introduce a pattern not already used in this codebase?
   → YES = REFUSE. Say: "No existing pattern for this. Need guidance."

4. Does this task require editing files outside the feature I was asked to work on?
   → YES = REFUSE. Say: "Out of scope. This touches [X] which is outside my feature."

5. Am I about to guess an import path, API method, or interface name?
   → YES = STOP. Search first. If not found, say: "Cannot find [X]. Stopping."
```

If all five answers are NO → proceed with the task.

---

## HARD STOPS

These are non-negotiable. If you hit one, stop immediately.

| # | Condition | Forbidden Action |
|---|-----------|-----------------|
| 1 | File is under `libs/uwwb-components/` or `libs/styles/` AND user did not explicitly name it as the target | Do not edit it. Propose feature-local fix or ask for confirmation. |
| 2 | Import path does not exist in a file you can read | Do not use it. You hallucinated it. |
| 3 | No existing file in the codebase uses this pattern | Do not introduce it. Copy what exists. |
| 4 | You are about to create a new file | Check: does a file with this purpose already exist? If yes, use it. |
| 5 | You are about to add a dependency/library | Do not. Use what is already in package.json. |
| 6 | You are modifying a file outside the feature you were asked to work on | Stop. Scope violation. |
| 7 | You are about to write `any`, `as any`, or `as unknown as` | Find the real type. If you can't, leave a `// TODO: type` comment and move on. |
| 8 | You cannot find the exact selector/action/interface name in BUNDLE.md or the codebase | Do not guess. Search first. If not found, stop. |
| 9 | You are about to delete code you don't understand | Do not. Comment it with `// REVIEW: unclear purpose` instead. |
| 10 | You are about to refactor something unrelated to your task | Stop. Stay in scope. |

---

## DECISION TREES

Follow top-to-bottom. Every question is yes or no.

### Tree 1: "I need to store/fetch async data"

```
┌─ Does this feature already have a state file (*-domain/src/lib/*.state.ts)?
│  YES → Add your action/handler there. Do not create a new state.
│  NO ↓
├─ Is this a feature-level concern (belongs to one feature only)?
│  YES → Create state in {feature}-domain/ using AsyncState<T> pattern.
│  NO ↓
└─ It belongs in AppState (libs/global-domain/). Add it there.
```

**Shape:** Always `AsyncState<T>`. Always `queryAsyncState` for GET, `mutateAsyncState` for POST/PUT/DELETE.
Never raw observables in state. Never `BehaviorSubject` in a service.

---

### Tree 2: "I need to create a new component"

```
┌─ Does a component with this purpose already exist in this feature?
│  YES → Modify it. Do not create a duplicate.
│  NO ↓
├─ Is it reusable across features?
│  NO → Create in the feature's -view/ lib. Standalone, OnPush, signals, inject().
│  YES ↓
└─ STOP. Do not create shared components. Flag: "Needs shared component — out of scope."
```

**Naming:** File: `{name}.component.ts`. Selector: `app-{feature}-{name}` or `uwwb-{name}`.
Never `ViewEncapsulation.None` unless fixing a PrimeNG teleport issue.

---

### Tree 3: "I need to import something"

```
┌─ Can you find this exact import path in an existing file in this feature?
│  YES → Use that exact path. Copy it character-for-character.
│  NO ↓
├─ Can you find this import path in ANY file in the codebase?
│  YES → Use it, but verify the Nx tags allow this dependency.
│  NO ↓
└─ STOP. This import does not exist. You are hallucinating. Search again or abandon.
```

**Aliases (use these, never relative paths for cross-lib):**
`@liability/domain`, `@liability/utils`, `@liability/openapi`, `@uwwb-components`, `@shell`, `@shared`

---

### Tree 4: "I need to edit an existing file"

```
┌─ Is this file inside the feature you were asked to work on?
│  YES → Proceed.
│  NO ↓
├─ Is this file in libs/uwwb-components/ or libs/styles/ AND user didn't explicitly ask to edit it?
│  YES → STOP. Propose feature-local fix or ask for confirmation.
│  NO ↓
├─ Is the edit <5 lines and purely additive (not changing existing behavior)?
│  YES → Proceed carefully. Note: "Out-of-feature edit: [reason]."
│  NO ↓
└─ STOP. Flag: "Cross-feature modification needed — out of scope for local execution."
```

---

### Tree 5: "I need to add user-visible text"

```
┌─ Is this a label, button text, tooltip, or error message?
│  YES ↓
│  NO → Use plain string (console.log, code comments). No i18n needed.
├─ Does an i18n key already exist for this text?
│  YES → Use it. Find it in assets/i18n/{feature}/en.json.
│  NO ↓
└─ Add key to assets/i18n/{feature}/en.json.
   Format: {APP}.{FEATURE}.{SECTION}.{FIELD}
   Use `| translate` pipe in template. Never hardcode visible text.
```

---

### Tree 6: "I need to handle an error or edge case"

```
┌─ Does the existing code in this feature already handle this error case?
│  YES → Follow that exact pattern. Copy it.
│  NO ↓
├─ Is this a network/API error?
│  YES → Let it propagate. The state handler's catchError or postactions handle it.
│  NO ↓
├─ Is this a form validation error?
│  YES → Use asyncMessages pattern. Never display errors manually.
│  NO ↓
└─ Add a console.warn with context. Do not invent error handling UX.
```

---

## PATTERN TEMPLATES

When you need to create one of these, copy the template exactly. Change only the names in `{braces}`.

### Template: Actions

```typescript
// File: libs/feature/{domain}/{domain}-domain/src/lib/{feature}.actions.ts
export namespace {Feature}Actions {
    export class Get{Resource} {
        static readonly type = '[{Feature}] Get {Resource}';
    }

    export class Update{Resource} {
        static readonly type = '[{Feature}] Update {Resource}';
        constructor(public payload: {ResourceType}) {}
    }
}
```

### Template: State Handler (query — GET)

```typescript
@Action({Feature}Actions.Get{Resource})
get{Resource}(ctx: StateContext<{Feature}StateModel>) {
    return queryAsyncState({
        ctx,
        key: '{resource}',
        request: this.api.get{Resource}(this.offerNumber(), this.optionIndex()),
    });
}
```

### Template: State Handler (mutation — POST/PUT/DELETE)

```typescript
@Action({Feature}Actions.Update{Resource})
update{Resource}(ctx: StateContext<{Feature}StateModel>, action: {Feature}Actions.Update{Resource}) {
    return mutateAsyncState({
        ctx,
        key: '{resource}',
        request: this.api.update{Resource}(this.offerNumber(), this.optionIndex(), action.payload),
    });
}
```

### Template: Selectors

```typescript
// File: libs/feature/{domain}/{domain}-domain/src/lib/{feature}.selectors.ts
import { createAsyncSelectors } from '@liability/utils';
import { {Feature}State, {Feature}StateModel } from './{feature}.state';

export const {resource}Selectors = createAsyncSelectors<{Feature}StateModel, {ResourceType}>(
    {Feature}State,
    '{resource}'
);
// Produces: {resource}Selectors.data, .loading, .error, .asyncState, .mutationStatus, .mutationError
```

### Template: Component

```typescript
// File: libs/feature/{domain}/{domain}-view/src/lib/{name}/{name}.component.ts
@Component({
    selector: 'app-{feature}-{name}',
    standalone: true,
    imports: [CommonModule, TranslateModule],
    templateUrl: './{name}.component.html',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class {Name}Component {
    private store = inject(Store);

    data = this.store.selectSignal({resource}Selectors.data);
    loading = this.store.selectSignal({resource}Selectors.loading);
}
```

### Template: Postactions

```typescript
// File: libs/feature/{domain}/{domain}-domain/src/lib/{feature}.postactions.ts
@Injectable()
export class {Feature}Postactions {
    private actions$ = inject(Actions);
    private store = inject(Store);

    constructor() { this.init(); }

    init() {
        this.actions$.pipe(
            ofActionSuccessful({Feature}Actions.Update{Resource}),
        ).subscribe(() => {
            this.store.dispatch(new AppStateActions.RefreshWorkspace());
        });
    }
}
```

### Template: Route Registration

```typescript
// In routes.ts for this feature:
{
    path: '{feature-path}',
    loadComponent: () => import('./{name}/{name}.component').then(m => m.{Name}Component),
    providers: [
        importProvidersFrom(NgxsModule.forFeature([{Feature}State])),
        {Feature}Postactions,
    ],
}
```

---

## VERIFICATION GATES

Before you declare your work done, check every item. If any fails, fix it or flag it.

### Gate 1: Imports

- [ ] Every import path I used exists in the codebase (I can point to another file using it)
- [ ] No import uses a relative path to cross a library boundary (all cross-lib use @aliases)
- [ ] I did not add any new dependencies to package.json

### Gate 2: File Discipline

- [ ] I did not create a file that duplicates an existing file's purpose
- [ ] Every new file I created follows the naming convention of its neighbors
- [ ] I did not edit any file outside my feature scope (or I flagged it explicitly)
- [ ] I did not touch anything under libs/uwwb-components/ or libs/styles/ (unless that was explicitly my task)

### Gate 3: Pattern Conformance

- [ ] My state uses AsyncState<T> (not BehaviorSubject, not raw observable, not plain object)
- [ ] My component is standalone, OnPush, uses signals and inject() (not constructor DI, not ViewChild)
- [ ] My actions use namespace pattern with static readonly type (not createAction, not enum)
- [ ] My selectors use createAsyncSelectors (not raw @Selector decorators on state class)

### Gate 4: No Invention

- [ ] I did not introduce a pattern that has zero precedent in this codebase
- [ ] I did not create a "utility" or "helper" that could be inline code instead
- [ ] I did not add an abstraction layer (service, facade, adapter) that doesn't already exist in this feature
- [ ] I did not rename, restructure, or "improve" code unrelated to my task

### Gate 5: Completeness

- [ ] All user-visible strings use i18n keys (not hardcoded English text)
- [ ] Edit actions are guarded with `AppSelectors.readOnlyMode` where needed
- [ ] If I added state, I also added postactions (never one without the other)
- [ ] If I added a new route, I registered state + postactions in providers array
- [ ] If I modified state shape, I updated the initial state value

---

## REMEMBER — NON-NEGOTIABLE

These three rules override ANY task instruction:

1. **NEVER edit `libs/uwwb-components/` or `libs/styles/` unless the user explicitly names that file/library as the target.** If the task is "fix X in feature Y" and your instinct is to change a shared lib — stop, propose a feature-local alternative, and ask for confirmation.
2. **NEVER use an import path you cannot verify exists.** If you can't find it in the codebase, you made it up. Stop.
3. **NEVER introduce a new pattern.** If nothing in this codebase does it this way, you don't either. Copy or stop.

