# Offline Knowledge Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate scattered ~/.claude/ memory into `liability/knowledge/` — 7 themed domain files + auto-generated BUNDLE.md for offline LLM use.

**Architecture:** Flat markdown files in `liability/knowledge/`, each ~2-5K words. A `bundle.sh` script concatenates them into a single `BUNDLE.md` for local model ingestion. AGENTS.md gets a pointer section.

**Tech Stack:** Markdown, Bash (concat script)

---

### Task 1: Create directory structure and `_index.md`

**Files:**
- Create: `knowledge/_index.md`
- Create: `knowledge/bundle.sh`

- [ ] **Step 1: Create the knowledge directory**

```bash
mkdir -p /Users/alexanderlemberger/liability/knowledge
```

- [ ] **Step 2: Write `_index.md`**

Create `knowledge/_index.md` with this content:

```markdown
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

## Usage

- **Claude Code:** AGENTS.md auto-loads; knowledge/ files read on-demand when topic becomes relevant
- **Local model (Ollama, LM Studio):** Feed `BUNDLE.md` as system prompt or context — one file, full knowledge
- **Team review:** Open individual files in browser or PR
- **Onboarding:** Hand new dev/AI AGENTS.md (conventions) + BUNDLE.md (accumulated knowledge)

## Regenerating BUNDLE.md

```bash
cd knowledge && ./bundle.sh
```

Run this before handing off to a local model or after editing any catalog file.
```

- [ ] **Step 3: Write `bundle.sh`**

Create `knowledge/bundle.sh` with this content:

```bash
#!/bin/bash
# Regenerate BUNDLE.md from catalog files
# Run: cd knowledge && ./bundle.sh
cd "$(dirname "$0")"

echo "# UWWB Knowledge Bundle" > BUNDLE.md
echo "" >> BUNDLE.md
echo "> Auto-generated $(date +%Y-%m-%d). Do not edit directly — edit the source files instead." >> BUNDLE.md
echo "> Covers: architecture, active features, parked features, patterns, tooling, marine/CaTa, collaboration." >> BUNDLE.md
echo "" >> BUNDLE.md

for f in _index.md architecture.md features-active.md features-parked.md \
         patterns-and-gotchas.md tooling.md marine-cata.md collaboration.md; do
  echo "---" >> BUNDLE.md
  echo "" >> BUNDLE.md
  cat "$f" >> BUNDLE.md
  echo "" >> BUNDLE.md
done

echo "✓ Bundle generated: knowledge/BUNDLE.md ($(wc -c < BUNDLE.md | tr -d ' ') bytes)"
```

- [ ] **Step 4: Make bundle.sh executable**

```bash
chmod +x knowledge/bundle.sh
```

- [ ] **Step 5: Commit scaffold**

```bash
git add knowledge/_index.md knowledge/bundle.sh
git commit -m "feat(knowledge): scaffold offline knowledge catalog structure

Creates knowledge/ directory with _index.md (catalog TOC) and bundle.sh
(concat script for generating BUNDLE.md for local LLM ingestion).

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 2: Write `architecture.md`

**Files:**
- Create: `knowledge/architecture.md`

**Sources to consolidate:**
- MEMORY.md "Architecture Decisions" + "Key File Locations" sections
- `~/.claude/markdowns/DATA_FLOW.md` (if relevant)
- `~/.claude/markdowns/FE_STRUCTURE.md` (if relevant)
- `inplace_editing_architecture.md` architectural notes (the decision to park it)

- [ ] **Step 1: Write architecture.md**

Create `knowledge/architecture.md` consolidating the above sources. Structure:

```markdown
# Architecture

## Key Decisions

- **Editing pattern:** slide-panel + uwwb-form + AsyncState<T> (not inplace editing — that's a parked POC, maintenance only)
- **Feature scaffolding:** mandatory 3-layer pattern (openapi / domain / view)
- **State management:** NGXS with AsyncState<T>, queryAsyncState, mutateAsyncState, createAsyncSelectors
- **Shared libs policy:** Do not edit uwwb-components or libs/styles without cross-team approval; prefer feature-local workarounds

## Data Flow

Frontend (Angular) → liability-application (Spring Boot BFF) → liability-ios (FaktorZehn IOS engine)
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
- Submit banner: SummaryState manages `submitBannerType`, wires to `SelectOfferActions.UpdateStatus` lifecycle via NGXS Actions stream

## Read-Only Mode Guard

Any view with edit actions must guard with `AppSelectors.readOnlyMode` from `@liability/domain`:
- Action buttons: `[readOnly]` on uwwb-actionelement
- Controls: checkboxes/toggles → `[disabled]`
- Cards: `[readonly]` on cardClick
- Tables: conditionally omit edit column or guard callback
- Add buttons: `[disabled]`
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/architecture.md
git commit -m "feat(knowledge): add architecture.md — decisions, data flow, key locations

Consolidates Architecture Decisions, Key File Locations, state patterns,
notification components, and read-only mode guard from session memory.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 3: Write `features-active.md`

**Files:**
- Create: `knowledge/features-active.md`

**Sources:**
- `offer-table-enrichment.md`
- `coverage-detail-redesign.md`
- `broker_data_card_feature.md`
- `dms_integration.md`
- `coverage-table-optimization-plan.md`

- [ ] **Step 1: Write features-active.md**

Create `knowledge/features-active.md`. Include each feature's status, key decisions, branch, and critical implementation notes. Structure by feature with `##` headers:

```markdown
# Active Features

Features currently in progress or recently completed. Check branch status before resuming work.

## Offer Table Enrichment

**Stories:** 710110, 710118, 710122 | **Branch:** `feature/710110-710118-710122-offer-table-filters` | **PR:** #287863
**Status:** Frontend workaround merged. Team decided (2026-06-11) to pursue backend approach — backend stories handed to BA.

**Problem:** `GET /offer/v2` doesn't return partnerName, policyNumber, typeOfBusiness.

**Solution (temporary):** Fan-out N×2 calls via `GetOfferEnrichments` action. Results in `offerEnrichments: Record<string, OfferEnrichment>` map in AppState. Client-side `contains` filter in `enrichedOffers` selector.

**Critical:** `loading: false` must be set in `GetOfferEnrichments` (after forkJoin), NOT in `getPaginatedOffers`. `cancelUncompleted: true` prevents race on rapid pagination. Column names must be flat (`partnerName`), not dotted paths.

**Migration path:** When backend ships, remove OfferEnrichment/OfferTextFilters, remove GetOfferEnrichments, restore loading to getPaginatedOffers, wire server params. Backend contract: `docs/superpowers/specs/2026-06-10-offer-list-backend-contract.md`.

## Coverage Detail UX Redesign

**Branch:** `feature/coverage-detail-list-redesign`
**Status:** Spec + plan + 2 prototypes done. Awaiting user feedback before implementation.

**Change:** List-detail layout replacing TabView for coverage details.

## Broker Data Card

**Branch:** frontend+backend `feature/668936-broker-agreement`, uwwb-api `feature/668936-broker-agreement-rules`
**Status:** Wired to real API across 3 repos.

**Deploy order:** uwwb-api → npm publish → frontend. Field change guide + local testing workflow in memory file.

## DMS Integration (Doxis WebCube)

**PR:** #280722
**Status:** Awaiting merge. BA questions on popup vs iframe resolved. Pipeline needs re-run after merge.

## Coverage Table Optimization

**Status:** 2 high-priority items fixed, 7 lower-priority remain.

**Done:**
- #1: Collapse/expand moved to view layer (no longer triggers expensive selector recompute)
- #6: `cancelUncompleted` race condition on `ToggleCoverageSelected` fixed — concurrent toggles now parallel, `applyResponse` reads current state

**Remaining (lower priority):** Redundant enrichCoverageTree (6 calls), passthrough computed signal, method calls in template per row, missing trackBy, hardcoded validation field paths, dead code callbackValidationMessages, GetCyberContract snapshot mismatch.
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/features-active.md
git commit -m "feat(knowledge): add features-active.md — offer enrichment, coverage, broker, DMS

Consolidates 5 active feature memory files into single reviewable document.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 4: Write `features-parked.md`

**Files:**
- Create: `knowledge/features-parked.md`

**Sources:**
- `project_inplace_editing_status.md`
- `inplace_editing_architecture.md`
- `inplace_card_label_convention.md`
- `inplace_label_field_alignment.md`
- `odin_migration_option_c.md`
- `exclusions-and-definitions-rework.md`
- `coverage-table-review-pending.md`

- [ ] **Step 1: Write features-parked.md**

Create `knowledge/features-parked.md`:

```markdown
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

**Impression:** Odin team delivers "website" components, not "enterprise app" components. May need architecture-level escalation.

## Exclusions & Definitions Review Rework

**Status:** Full DOR available, not yet started.

**Scope:** Frontend-only. Replaces dropdown (SELECT) with checkbox for exclusion status. Adds colored status badges (INCLUDED=green, EXCLUDED=red, NA=gray).

**Key decisions:**
- Badge component moves from property domain to uwwb-components (Nx boundary fix)
- Overview stays in CardModel pattern with `type: 'template'` + templateRef
- Edit panel: FormControlType.CHECKBOX. NA rows → disabled. Transform boolean↔IdAndLabel at view boundary.

## Coverage Table Data Flow Review

**Status:** 10 findings documented. Two HIGH items first.

**Priority list:**
1. (HIGH) No ngxsOnInit — option change does not re-load coverage data
2. (HIGH) GetCyberContract should read offerNumber/optionIndex from state, not action payload
3-10. (MEDIUM/LOW) See `docs/reviews/coverage-table-data-flow-review.md`
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/features-parked.md
git commit -m "feat(knowledge): add features-parked.md — inplace editing, odin, exclusions

Consolidates parked/on-hold features with full architectural context for
maintenance reference.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 5: Write `patterns-and-gotchas.md`

**Files:**
- Create: `knowledge/patterns-and-gotchas.md`

**Sources:**
- `primeng_21_migration.md`
- `primeng_dropdown_panel_width_fix.md`
- `primeng_dropdown_ngmodel_preselection.md`
- `primeng_costdata_select_broken.md`
- `viewport_fix_nested_slide_panel.md`
- `coverage-table-readonly-fix.md`
- `grep_coverage_gitignore_blindspot.md`

- [ ] **Step 1: Write patterns-and-gotchas.md**

Create `knowledge/patterns-and-gotchas.md`:

```markdown
# Patterns & Gotchas

Hard-won lessons, framework quirks, and workarounds. Check here before debugging PrimeNG or NGXS issues.

## PrimeNG 17→21 Migration

**Branch:** `liability-frotnend_primeng-update` (merged)

**TypeScript strictness:**
- `ControlValueAccessor.registerOnChange(fn)` — propagateChange must accept parameter: `(_: unknown) => void`, not `() => void`
- Affects all form components inheriting `AbstractControlValueAccessor` in `libs/uwwb-components/src/lib/form/`

**TranslateService mock:** `instant()` signature requires `(key: string | string[], interpolateParams?)`. Add `Array.isArray(key)` guard when using key as string.

**Running single tests:** `npx jest --config libs/<lib>/jest.config.ts --testPathPatterns="<pattern>" --no-coverage`

**Known pre-existing:** uwwb-components tests have PrimeNG module resolution failures (shared lib, not liability-specific).

## PrimeNG Dropdown — Panel Width Fix (v17)

**Problem:** `p-dropdown` with `appendTo="body"` renders panel wider than trigger.

**Root cause:** `white-space: nowrap` + no `max-width` on overlay. CSS-only fails because PrimeNG injects styles via CSS-in-JS, and appendTo teleports panel outside component DOM.

**Fix** (in `uwwb-inplace-card.component.ts`, `onDropdownShow()`):
1. `querySelectorAll('.uwwb-inplace-panel')[last]` — always take LAST (PrimeNG keeps closing panels in DOM)
2. Traverse to overlay: `panel.parentElement?.parentElement`
3. Set `panel.style.maxWidth = overlayEl.style.minWidth`
4. Find trigger, correct left position
5. MutationObserver re-applies `white-space: normal` on PrimeNG re-renders

**Key insight:** `white-space: normal` alone never prevents shrink-to-fit — must also constrain max-width.

## PrimeNG Dropdown — ngModel Pre-selection

**Problem:** Dropdown shows empty in edit mode even when field has value.

**Root cause:** PrimeNG uses deep object equality by default. If `value.label` differs from options label, match fails silently.

**Fix:** Add `dataKey: 'id'` to any dropdown using `IdAndLabel*` option types. Always.

## PrimeNG Cost Data Select (v21)

**Problem:** "Type of Participation" select not populating — same symptom as turnover-split combobox fix.

**Status:** Investigation needed — combobox fix (optionLabel, dataKey, placeholder) should cover it but doesn't. Check if availableValues shape differs or form model passes values differently.

## ViewportFixDirective + Nested Slide Panels

**Problem:** Route-level `uwwbViewportFix` steals CTA buttons from child slide panels.

**Root cause:** `ViewportFixDirective.queryCtas()` uses unscoped `querySelectorAll('[data-viewport-cta]')`. Form actionbar inside any descendant slide panel gets pinned to page bottom-left.

**Fix:** On child slide panels that render uwwb-form with actions: `[appendTo]="'body'" [mediaOriented]="false"`.

**Side effect of appendTo:** Panel escapes `.media` wrapper → width rule doesn't match → panel narrower. `mediaOriented="false"` switches to `.defined` wrapper (80% width, looks correct).

**When to check:** Introducing uwwbViewportFix on a route component → audit ALL child components in wrapped subtree for uwwb-slide-panel usage.

**Reference:** risk-profile-general-information-overview (directive) + turnover-split-overview (appendTo fix).

## Grep Blindspot: coverage/ Directories

**Problem:** Ripgrep honors `.gitignore` bare `coverage` entry → silently skips ALL `coverage/` directories including git-tracked source like `libs/feature/program-coverage/.../coverage/`.

**Fix:** For repo-wide audits touching coverage-related features, use `grep -rn` via Bash. Don't trust empty Grep results.

## NGXS Race Condition: cancelUncompleted on Multi-Item Toggles

**Problem:** `cancelUncompleted: true` on `ToggleCoverageSelected` cancelled ALL in-flight toggles, not just same-item.

**Fix:** Remove cancelUncompleted, read current state in applyResponse (not stale `prev` captured at invocation). Concurrent toggles for different items now run in parallel safely.

**Root cause:** `mutateAsyncState` captures `prevData` at invocation. With concurrent calls on same slice, later response's merge into stale prev overwrites earlier response's result.
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/patterns-and-gotchas.md
git commit -m "feat(knowledge): add patterns-and-gotchas.md — PrimeNG, NGXS, viewport

Consolidates 7 memory files of hard-won debugging lessons and workarounds.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 6: Write `tooling.md`

**Files:**
- Create: `knowledge/tooling.md`

**Sources:**
- `generic_app_dev_setup.md`
- `dev_mock_patterns.md`
- `azure_devops_api.md`

- [ ] **Step 1: Write tooling.md**

Create `knowledge/tooling.md`:

```markdown
# Tooling & Dev Environment

## Local Dev Startup

**Quickstart:** `~/liability/start-local.sh` — opens Terminal windows for all 3 services.

### Manual startup order

| # | Service | Port | Command | Profiles |
|---|---------|------|---------|----------|
| 1 | liability-ios | 8082 | `cd liability-ios && mvn spring-boot:run -Dspring-boot.run.profiles=dev,local` | dev=no OAuth2 outbound, local=URLs |
| 2 | liability-application | 8081 | `cd liability-application && mvn -pl apps/liability spring-boot:run -Dspring-boot.run.profiles=dev,no-auth,local` | no-auth=no inbound auth, dev=no outbound OAuth2 |
| 3 | liability-frontend | 4200 | `cd liability-frontend && npm start` | — |

### Required Mocks (Mockoon)

| Mock | Port | File | Key Route |
|------|------|------|-----------|
| Central Identifier | 18080 | `liability-ios/mockoon/CentralIdentifier.json` | `POST /Offer/ids` → random ID |
| Partner | 8091 | `liability-application/mockoon/Partner.json` | various |

**Without Central Identifier mock:** offer creation fails with "Central Identifier Service returned no ID".

### Profile Notes

- `liability-ios` needs `dev` profile for OAuth2 bypass (configured in `application-dev.yaml`)
- `liability-ios` does NOT have `no-auth` (unlike liability-application)
- PostgreSQL on 5430 optional — H2 in-memory used by default locally

## Dev Mock Patterns (Temporary Testing)

⚠️ Always remove before merging — mark with `// TODO: remove mock before merging`

### Mock calculate success
```typescript
// In premium-result.state.ts calculatePremium:
return of({ status: 200 } as CalculationResultResource);
```

### Mock all nav items green
```typescript
// In app.state.ts getStatus:
const allValid = Object.fromEntries(
    Object.entries(defaultStatusList).map(([k, v]) => [k, { ...v, valid: true }])
) as unknown as ProgressResource;
return of(allValid).pipe(tap(statusList => ctx.patchState({ statusLoading: false, statusList })));
```

### Mock submit with delay
```typescript
// Add @Action on SummaryState (NOT SelectOfferState — it's lazy, would fire success instead of error)
@Action(SelectOfferActions.UpdateStatus)
mockSubmit(): Observable<never> {
    return timer(3000).pipe(switchMap(() => throwError(() => new Error('Simulated submit error'))));
}
```

## Azure DevOps REST API

PAT in `~/.zshrc` as `$AZURE_DEVOPS_PAT`. Run `source ~/.zshrc` first.

Base: `https://dev.azure.com/HDI-GLOBAL/UWWB-ICP/_apis/git/repositories/liability-frontend`

```bash
# Find PR by branch
curl -s -u ":$AZURE_DEVOPS_PAT" "{BASE}/pullrequests?searchCriteria.sourceRefName=refs/heads/{BRANCH}&api-version=7.1"

# Read comments
curl -s -u ":$AZURE_DEVOPS_PAT" "{BASE}/pullrequests/{PR_ID}/threads?api-version=7.1"

# Post comment
curl -s -X POST -u ":$AZURE_DEVOPS_PAT" -H "Content-Type: application/json" \
  "{BASE}/pullrequests/{PR_ID}/threads?api-version=7.1" \
  -d '{"comments": [{"parentCommentId": 0, "content": "...", "commentType": 1}], "status": 1}'
```
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/tooling.md
git commit -m "feat(knowledge): add tooling.md — local dev, mocking, Azure DevOps API

Consolidates dev setup, mock patterns, and CI/CD tooling from 3 memory files.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 7: Write `marine-cata.md`

**Files:**
- Create: `knowledge/marine-cata.md`

**Sources:**
- MEMORY.md "Marine Workflow", "CaTa Prototype — UI Conventions", "Marine — Strategic Direction" sections
- CLAUDE.md CaTa conventions (already in global context)
- `marine_workflow_figma_first.md` (key patterns, not full 739 lines)

- [ ] **Step 1: Write marine-cata.md**

Create `knowledge/marine-cata.md`. This is the largest file — include all CaTa UI conventions, strategic direction, and the Figma-first workflow. Pull from MEMORY.md lines 44-87 and the CLAUDE.md CaTa section. Structure:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/marine-cata.md
git commit -m "feat(knowledge): add marine-cata.md — prototype, UI conventions, strategy

Consolidates CaTa/Marine strategic direction, UI conventions, Figma workflow,
and prototype technical details.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 8: Write `collaboration.md`

**Files:**
- Create: `knowledge/collaboration.md`

**Sources:**
- `feedback_shared_components.md`
- `feedback_self_improvement_loop.md`

- [ ] **Step 1: Write collaboration.md**

Create `knowledge/collaboration.md`:

```markdown
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

## Code Review Standards

(Detailed standards live in AGENTS.md — this section captures accumulated learnings)

- Guard all edit actions with `AppSelectors.readOnlyMode` in every new view
- Never skip the failing-test step in TDD — even for "obvious" implementations
- Prefer `selectSignal` over `select` + async pipe in new components
- Always check if feature state is lazy-loaded — selectors need `?.` optional chaining
```

- [ ] **Step 2: Commit**

```bash
git add knowledge/collaboration.md
git commit -m "feat(knowledge): add collaboration.md — shared component policy, feedback loop

Consolidates team collaboration rules and self-improvement principles.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 9: Add Knowledge Catalog section to AGENTS.md

**Files:**
- Modify: `AGENTS.md` (add section after Repository Overview)

- [ ] **Step 1: Add Knowledge Catalog section**

In `AGENTS.md`, after the "Repository Overview" section (after the data flow line ending with "External integrations: Pricing service, Partner service (both via Feign)."), insert:

```markdown

## Knowledge Catalog

Accumulated project knowledge lives in `knowledge/`. For full offline context, use `knowledge/BUNDLE.md`.

→ See [`knowledge/_index.md`](knowledge/_index.md) for the catalog index.
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): add Knowledge Catalog pointer section

Links AGENTS.md to knowledge/_index.md and BUNDLE.md for offline LLM use.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 10: Generate BUNDLE.md and verify

**Files:**
- Create (generated): `knowledge/BUNDLE.md`

- [ ] **Step 1: Run bundle.sh**

```bash
cd /Users/alexanderlemberger/liability/knowledge && ./bundle.sh
```

Expected output: `✓ Bundle generated: knowledge/BUNDLE.md (XXXXX bytes)`

- [ ] **Step 2: Verify bundle size**

```bash
wc -c knowledge/BUNDLE.md
wc -l knowledge/BUNDLE.md
```

Expected: Under 200K characters (~50K-80K is likely). Under 2000 lines.

- [ ] **Step 3: Spot-check bundle content**

```bash
head -20 knowledge/BUNDLE.md
grep "^---$" knowledge/BUNDLE.md | wc -l
grep "^# " knowledge/BUNDLE.md
```

Expected: Header with timestamp, 8 separator lines (one per file boundary), 8 top-level headings.

- [ ] **Step 4: Commit the bundle**

```bash
git add knowledge/BUNDLE.md
git commit -m "feat(knowledge): generate initial BUNDLE.md for offline LLM use

Single monolith file concatenating all 7 domain files + index.
Hand this to any local model for full project context.

Co-Authored-By: Claude Opus 4 <noreply@anthropic.com>"
```

---

### Task 11: Final verification

- [ ] **Step 1: Verify complete file list**

```bash
ls -la /Users/alexanderlemberger/liability/knowledge/
```

Expected 10 files:
- `_index.md`
- `architecture.md`
- `features-active.md`
- `features-parked.md`
- `patterns-and-gotchas.md`
- `tooling.md`
- `marine-cata.md`
- `collaboration.md`
- `BUNDLE.md`
- `bundle.sh`

- [ ] **Step 2: Verify AGENTS.md has the pointer**

```bash
grep -A3 "Knowledge Catalog" /Users/alexanderlemberger/liability/AGENTS.md
```

Expected: The "## Knowledge Catalog" section with link to `knowledge/_index.md`.

- [ ] **Step 3: Verify git log**

```bash
git log --oneline -10
```

Expected: 9 commits (scaffold, 7 domain files, AGENTS.md pointer, bundle generation).
