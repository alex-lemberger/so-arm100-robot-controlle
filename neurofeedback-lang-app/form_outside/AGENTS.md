# AGENTS.md — AI Coding Agent Guide

## Repository Overview

Monorepo for **HDI Underwriting Workbench (UWWB)** — an insurance underwriting platform with four sub-projects:

| Project | Stack | Path | Purpose |
|---------|-------|------|---------|
| **liability-frontend** | Angular 21 + Nx 22 + NGXS + PrimeNG | `liability-frontend/` | SPA frontend (liability, property, cyber apps) |
| **liability-application** | Spring Boot + JPA + Feign | `liability-application/` | BFF layer between frontend and IOS |
| **liability-ios** | Spring Boot + FaktorZehn IOS | `liability-ios/` | Insurance Object System (core domain engine) |
| **risk-metadata-service** | Spring Boot | `risk-metadata-service/` | Risk metadata microservice |

**Data flow:** Frontend → liability-application (BFF) → liability-ios → FaktorZehn IOS engine. External integrations: Pricing service, Partner service (both via Feign).

## Knowledge Catalog

Accumulated project knowledge lives in `knowledge/`. For full offline context, use `knowledge/BUNDLE.md`.

→ See [`knowledge/_index.md`](knowledge/_index.md) for the catalog index.

## Frontend (liability-frontend)

### Architecture

Nx monorepo with **modulith** strategy. Four apps (`liability-app`, `property-app`, `cyber-app`, `generic-app`) share libs under `libs/`. A `mock` app provides test fixtures.

**Feature scaffolding follows a mandatory 3-layer pattern (liability-level features):**
```
libs/feature/{domain}/
  {domain}-openapi/    # Generated OpenAPI client (never edit manually)
  {domain}-domain/     # NGXS state, actions, selectors, postactions
  {domain}-view/       # Components, forms, routes
```
Folder naming is intentionally redundant: `cost-data/cost-data-domain/` ✅

Liability-level feature domains: `general-data`, `exposure-information`, `cost-data`, `program-coverage`, `calculation-adjustment`, `premium-rate`, `summary`, `final-decision`, `hxrenew`.

**Cyber sub-features** follow the 3-layer pattern nested under `libs/feature/cyber/`:
```
libs/feature/cyber/{domain}/
  {domain}-openapi/    {domain}-domain/    {domain}-view/
```
Cyber domains: `risk-profile`, `maturity-assessment`, `cyber-program-coverage`, `calculation-adjustment`.

**Property sub-features** use a fine-grained multi-library pattern under `libs/feature/property/`:
```
libs/feature/property/{domain}/
  domain/              # State
  openapi/             # Generated client
  routes/              # Route configuration
  ui/                  # Shared UI components
  util/                # Utilities
  feature-{name}/      # Feature-specific sub-libs (e.g. feature-pml, feature-risk-grading)
```
Property domains: `risk-analysis`, `program-coverage`, `calculation-adjustment`.

**Cross-cutting feature libs:** `uwwb-core` (domain + view, no openapi).

**Nx library tags** — ONE type per library:
- Domain: `["type:domain", "scope:{feature-name}"]`
- View: `["type:feature", "scope:{feature-name}"]`
- OpenAPI: `["type:openapi", "scope:{feature-name}"]`
- No local `@nx/enforce-module-boundaries` overrides — rely on global `.eslintrc.json`

**Scaffolding details:** See `angular-developer/feature/SKILL.md` for full directory structure, `project.json` templates, and tsconfig path setup. For end-to-end feature generation from an OpenAPI spec, use `angular-developer/scaffold-feature/SKILL.md`.

**Key shared libs:**
- `@uwwb-components` — Reusable UI (slide-panel, uwwb-form, notifications)
- `@uwwb-core/domain`, `@uwwb-core/view` — Core feature state and components
- `@liability/domain` (`libs/global-domain/`) — App-level state, selectors (`AppSelectors.offerNumber`), event bus
- `@liability/openapi` (`libs/openapi-liability/`) — Global OpenAPI client
- `@liability/utils` (`libs/utils/`) — `queryAsyncState`, `mutateAsyncState`, `createAsyncSelectors`, `PostactionHelpers`
- `@shell` — Route configuration
- `@shared` — Cross-feature utilities

### State Management (NGXS)

All async data uses `AsyncState<T>` with helpers from `@liability/utils`:
- **Queries (GET):** `queryAsyncState({ ctx, key: 'resource', request: api.load(), silent?, transform? })`
- **Mutations (POST/PUT/DELETE):** `mutateAsyncState({ ctx, key: 'resource', request: api.save(data), optimistic?, applyResponse?, sideEffect? })`
- **Selectors:** `createAsyncSelectors(State, 'key')` → `{ loading, error, data, asyncState, mutationStatus, mutationError }`
- **Initial state:** `initialAsyncState<T>()` → `{ data: null, status: 'idle', mutationStatus: 'idle' }`

**State file pattern** (4 files per feature domain):
```
{domain}-domain/src/lib/state/
  ├── {domain}.state.ts        # State class with @Action handlers
  ├── {domain}.actions.ts      # Action classes with static type
  ├── {domain}.selectors.ts    # Selectors via createAsyncSelectors + @Selector
  └── {domain}.postactions.ts  # UI side effects (notifications, panels, blockUI)
```

**Actions — key rules:**
- **Top-level imports only** — never inline `import()` types in constructor
- **Minimal payloads** — `Load*` stores identifiers; `Reload*`, `Edit*`, `Save*` read from `ctx.getState()`
- Naming: `Load*` (initial), `Reload*` (background), `Edit*` (open panel), `Save*`/`Update*` (persist), `Validate*` (form change), `Delete*`, `Reset*`
- Prefix: `static readonly type = '[StateName] Action Name'`

```typescript
// ✅ Reload reads from state — no payload needed
export class ReloadRiskProfile { static readonly type = '[RiskProfile] Reload'; }

// ✅ Validate sends full data for backend validation
export class ValidateRiskProfile {
  static readonly type = '[RiskProfile] Validate';
  constructor(public data: RiskProfileResource) {}
}
```

**State handler patterns:**
```typescript
// Load — stores identifiers, then queries
@Action(GetRiskProfile)
get(ctx: StateContext<Model>, action: GetRiskProfile) {
    ctx.patchState({ offerNumber: action.offerNumber, optionIndex: action.optionIndex });
    return queryAsyncState({ ctx, key: 'resource', request: this.service.get(action.offerNumber, action.optionIndex) });
}

// Edit — synchronous copy, NO API call → panel opens instantly
@Action(EditRiskProfile)
edit(ctx: StateContext<Model>) {
    const data = ctx.getState().resource.data;
    if (!data) return;
    ctx.patchState({ editingResource: { data, status: 'success', mutationStatus: 'idle', error: undefined } });
}

// Validate — mutateAsyncState on editingResource with cancelUncompleted
@Action(ValidateRiskProfile, { cancelUncompleted: true })
validate(ctx: StateContext<Model>, action: ValidateRiskProfile) {
    const { offerNumber, optionIndex } = ctx.getState();
    return mutateAsyncState({
        ctx, key: 'editingResource',
        optimistic: () => action.data,
        request: this.service.update(offerNumber, optionIndex, action.data, true),
        applyResponse: resp => resp,
    });
}
```

**Selectors — composition pattern:**
```typescript
// createAsyncSelectors for each AsyncState key
export const RiskProfileResource = createAsyncSelectors(RiskProfileState, 'resource');
export const RiskProfileEditing = createAsyncSelectors(RiskProfileState, 'editingResource');

// Derived selectors compose from async selectors
export class RiskProfileSelectors {
  @Selector([RiskProfileResource.data])
  static items(data: Resource | undefined): Item[] { return data?.items ?? []; }

  @Selector([RiskProfileState])
  static isSaving(state: Model): boolean { return state.editingResource.mutationStatus === 'loading'; }
}

// Component: store.selectSignal(RiskProfileResource.loading)
```

**Postactions** handle side effects (panel open/close, notifications, block UI) — see `*.postactions.ts` files:
- `@Injectable()` class with `init()` method, called from state constructor
- `ofActionDispatched(Edit*)` → open panel (instant, data already copied)
- `ofActionSuccessful(Save*)` → close panel + notification + refresh header
- `ofActionErrored(*)` → error notification + unblock UI
- Always `takeUntilDestroyed(this.destroyRef)` on subscriptions
- Use `PostactionHelpers.onActionErroredWithNotification()` for batch error handling
- Organize complex postactions into `setup*()` private methods

**Critical rules:**
- State reads its own data (`ctx.getState()`), components never send state data back in action payloads
- `cancelUncompleted: true` on validate and reload actions
- Validate = `mutateAsyncState` on `editingResource`, NOT `queryAsyncState`
- Always `return` the observable from action handlers (NGXS needs it for lifecycle tracking)

**Offer context lifecycle — every feature state must implement:**
```typescript
@Injectable()
export class MyFeatureState implements NgxsOnInit {
    private readonly actions$ = inject(Actions);
    private readonly eventBusService = inject(EventBusService);

    ngxsOnInit(ctx: StateContext<MyFeatureStateModel>): void {
        // Reset state when user navigates between offers
        onOfferContextReady(this.actions$, ctx, INITIAL_STATE);

        // React to changes in other features (optional)
        this.eventBusService
            .on(FeatureModel.GENERAL_DATA)
            .pipe(takeUntilDestroyed())
            .subscribe(() => ctx.setState(INITIAL_STATE));
    }
}
```
- `onOfferContextReady(actions$, ctx, INITIAL_STATE)` — resets state on `OfferContextReady` and `OfferContextCleared` (import from `@liability/domain`)
- `EventBusService.on(FeatureModel.*)` — subscribe to cross-feature change notifications; emit via `NotifyFeatureChanged` in postactions
- `FeatureModel` enum in `@liability/domain` — extend when adding new features that other features depend on

**Legacy pattern (do NOT extend):** Most existing features use `edited/saved` state shape with `immer`'s `produce()` and `AppSelectors.offerNumber`. New features MUST use `AsyncState<T>` with `queryAsyncState`/`mutateAsyncState`. Refactor legacy only when directly modifying those features.

**Detailed reference:** `angular-developer/state/SKILL.md`, `angular-developer/action/SKILL.md`, `angular-developer/selector/SKILL.md`, `angular-developer/postactions/SKILL.md`

### Forms

`<uwwb-form>` component with external factory functions. Control `name` must be a valid lodash `get()` path. Validation uses `asyncMessages` from API responses.

**Form factory pattern:**
```typescript
// {form-name}.form.ts — external factory, NOT inline in component
export function createCoverageForm(resource: Resource): FormConfig {
  return {
    controls: [
      { name: 'coverage.name.value', type: 'text', label: 'Name',
        validators: { asyncMessages: (val: Resource) => val.coverage?.name?.messages } },
      { name: 'coverage.amount.value', type: 'number', label: 'Amount',
        validators: { required: true, asyncMessages: (val: Resource) => val.coverage?.amount?.messages } },
    ],
    layout: { columns: 2 },
  };
}
```

**Component integration:**
```typescript
readonly formConfig = computed(() => {
  const resource = this.resource();
  return resource ? createCoverageForm(resource) : undefined;
});

onFormChanged(event: FormChangeEvent): void {
  this.store.dispatch(new ValidateCoverage(stripValidationMessages(event.data)));
}
```

**Key rules:**
- Control `name` = fully qualified lodash `get()` path: `'{section}.{field}.value'`
- `asyncMessages` callback receives **live response** `(val: Resource)`, not closure variable (stale)
- Strip validation messages before dispatching to state
- Recreate FormGroups on visibility toggles
- Pass full resource to all forms for validation handlers

**Detailed reference:** `angular-developer/form/SKILL.md`

### Commands

```bash
cd liability-frontend
npm install --include=optional          # Setup
npm ci                                  # Clean install (use when node_modules is stale/corrupted after a merge)
npm start                               # Serve liability-app (local)
npm run start:property                  # Serve property-app
npm run start:cyber                     # Serve cyber-app
npm run start:generic:no-auth           # Serve generic-app (no auth)
npx nx test <project>                   # Unit tests (Jest)
npx nx lint <project>                   # ESLint
npm run generate:<domain>               # Regenerate OpenAPI client (e.g. generate:openapi-cost-data)
STAGE=local IS_HEADLESS=false npx playwright test  # E2E tests
```

### Package Registry Notes (.npmrc)

- `@general-data` was historically on the **snapshots** registry; as of main merge post-PR284798 it uses the **releases** registry (`uwwb-npm-releases`)
- `@property-*/openapi` packages (`@property-calculation-adjustment/openapi`, `@property-program-coverage/openapi`, `@property-risk-analysis/openapi`) are external deps on `uwwb-npm-releases` — they replaced local `libs/feature/property/*/openapi/` source libs (removed in main ~PR698460/698459)
- If `@general-data/openapi` fields used by a feature branch don't exist in the latest release, create a local type extension in `*-domain/src/lib/models/` — see `general-data-resource.extension.ts` as a reference; delete it once the backend publishes the combined release

### Path Aliases (tsconfig.base.json)

Imports use aliases with these conventions:
- **Liability features:** `@{domain}/openapi`, `@{domain}/domain`, `@feature/{domain}` (view) — e.g. `@cost-data/openapi`, `@cost-data/domain`, `@feature/cost-data`
- **Property features:** `@property/{domain}/{layer}` — e.g. `@property/risk-analysis/domain`, `@property/risk-analysis/openapi`, `@property/risk-analysis/feature-pml`
- **Cyber features:** `@feature/cyber/{domain}` (view), `@feature/cyber/{domain}-domain`, `@feature/cyber/{domain}-openapi` — e.g. `@feature/cyber/risk-profile`, `@feature/cyber/risk-profile-domain`
- **Global:** `@liability/utils`, `@liability/domain`, `@liability/openapi`, `@uwwb-components`, `@uwwb-core/domain`, `@uwwb-core/view`, `@shared`, `@shell`

### Angular Conventions

**Angular 21 + NGXS 21 + PrimeNG 21 + PrimeFlex 3.** Standalone components (no `standalone: true` needed in v20+), OnPush change detection always. For deeper Angular reference, consult `angular-developer/references/`.

**Components:** Use `input()`/`output()` functions (not `@Input`/`@Output` decorators), `inject()` (not constructor DI), host bindings via `host` object (not `@HostBinding`/`@HostListener`). Inline templates for small components.

```ts
@Component({
  selector: 'app-example',
  host: { '[class.active]': 'isActive()' },
  template: `@if (data(); as d) { <span>{{ d.name }}</span> }`,
})
export class ExampleComponent {
  readonly data = input.required<MyData>();
  readonly saved = output<void>();
  private store = inject(Store);
  isActive = computed(() => !!this.data());
}
```

**Template control flow:** Use native `@if`/`@for`/`@switch` (not `*ngIf`/`*ngFor`/`ngSwitch`). `@for` requires `track`:

```html
@for (item of items(); track item.id) { <app-row [item]="item" /> }
@empty { <p>No items.</p> }
```

**Signals & Reactivity:**
- `signal()` for writable state, `computed()` for derived state, `linkedSignal()` for writable-derived state
- **Immutable updates only:** `signal.update(items => [...items, newItem])` ✅ — `signal().push(newItem)` ❌
- `effect()` **only** for side effects (logging, localStorage) — **never** for state mutations (use `computed`/`linkedSignal` instead)
- `afterRenderEffect()` for DOM reads/writes after render
- `untracked()` to read signals without creating a dependency
- Read signals **before** `await` boundaries (reactive context is synchronous only)
- Initialize `toSignal()` outside `computed()`, never inside

**Dependency injection:** `inject()` in field initializers (preferred) or constructor. Services use `providedIn: 'root'`.

**Forms:** This project uses `<uwwb-form>` with external factory functions (not Angular Signal Forms or Reactive Forms directly). Control `name` must be a valid lodash `get()` path. Validation via `asyncMessages` from API responses. See `### Forms` section above.

**Styling:** PrimeFlex utility-first (`flex`, `p-3`, `justify-content-start`). Custom SCSS only for theme variables (`var(--hdi-white)`) or non-standard effects. No Tailwind.

**PrimeNG Styling — `[pt]` pass-through over `::ng-deep`:**
- PrimeNG v21 supports `[pt]` (pass-through) for styling internal component sections — prefer this over `::ng-deep`
- Each PrimeNG component exposes named sections (e.g. TreeTable: `wrapper`, `scrollableBody`, `scrollableHeaderTable`, `tbody`, `thead`)
- Usage: `<p-treeTable [pt]="{ scrollableBody: { style: { overflow: 'visible' } } }">`
- For wrapper components: expose a `ptOverrides` input and merge with base `[pt]` config
- `::ng-deep` is still required for structural CSS targeting `aria-level`, pseudo-elements, or non-PrimeNG child components — but minimize its use
- **Never manually provide PrimeNG internal classes** (e.g. `providers: [TreeTable, TreeTableService]`) — in v21, `p-treeTable` self-provides all required DI tokens via its own decorator

**PrimeNG Drawer Mask Bug (v21):**
- `p-drawer` leave animation `animationend` may not fire, leaving orphaned `.p-drawer-mask` in DOM
- Workaround: `ViewChild` + `destroyModal()` per instance, with `effect(onCleanup)` to cancel stale timeouts
- See `~/.claude/docs/2026-04-23-primeng-drawer-mask-bug.md` for full details
- Watch PrimeNG issues [#19460](https://github.com/primefaces/primeng/issues/19460), [#19498](https://github.com/primefaces/primeng/issues/19498)

**Server-paginated table filters (`TableComponent`):** In lazy mode, `loadServerData` fires on every filter change. Only `dateEquals` and `inArray` match modes are re-applied client-side (`isClientSideFilter`). `contains` fires the server call but no client-side re-application — for enriched/computed fields not in the API, store filter values in state and apply in the selector instead. **Critical:** when a selector-level filter is active, `loading: false` must be deferred until the enrichment data is available — setting it too early causes the table to render an empty result while enrichments are still in-flight.

**`ReadValuePipe` column paths:** Resolves `column.name` as a lodash `get()` path. Top-level spread fields on enriched rows must use flat names (e.g. `partnerName`, not `offer.partnerName`).

**Testing:** Jest (not Vitest). `TestBed.configureTestingModule` with standalone component imports. Use `@testing-library/angular` where applicable. ≥80% branch coverage target.

**Detailed reference:** `angular-developer/component/SKILL.md`, `angular-developer/references/`

### Angular Developer Skills (`angular-developer/`)

Complete reference directory with project-specific skills and Angular framework documentation. **Consult these before generating code.**

**Root skill:** `angular-developer/SKILL.md` — Overarching Angular developer guidelines (version detection, project creation, routing to sub-skills)

#### Project-Specific Skills (Codebase Patterns)

| Skill | Path | When to Use |
|-------|------|-------------|
| **Scaffold Feature** | `angular-developer/scaffold-feature/SKILL.md` | **End-to-end feature generation** from an OpenAPI spec — orchestrates all skills below in a 12-step process with two human checkpoints. Includes `feature-blueprint.md` with domain conventions (entity catalog, state shape, operation mapping, action naming, critical patterns) |
| **Feature Scaffolding** | `angular-developer/feature/SKILL.md` | Creating new features (3-layer pattern, `project.json` templates, tsconfig paths, Nx tags) |
| **State** | `angular-developer/state/SKILL.md` | Creating NGXS state (`AsyncState<T>`, `queryAsyncState`, `mutateAsyncState`, state model, CRUD handlers) |
| **Actions** | `angular-developer/action/SKILL.md` | Creating NGXS actions (naming conventions, top-level imports, minimal payloads, action categories) |
| **Selectors** | `angular-developer/selector/SKILL.md` | Creating NGXS selectors (`createAsyncSelectors`, derived selectors, factory selectors, composition pattern) |
| **Postactions** | `angular-developer/postactions/SKILL.md` | Creating postactions (panel open/close, notifications, blockUI, error handling, `PostactionHelpers`) |
| **Component** | `angular-developer/component/SKILL.md` | Creating Angular components (standalone, OnPush, `inject()`, `input()`/`output()`, signals, template patterns) |
| **Form** | `angular-developer/form/SKILL.md` | Creating uwwb-form factories (`asyncMessages`, control paths, validation flow, `stripValidationMessages`) |

#### Angular Framework References (`angular-developer/references/`)

| Reference | Path | Topic |
|-----------|------|-------|
| `signals-overview.md` | Signals core (`signal`, `computed`, reactive contexts, `untracked`) |
| `linked-signal.md` | `linkedSignal()` — writable state linked to source signals |
| `resource.md` | `resource()` — async data fetching into signal state |
| `effects.md` | `effect()`, `afterRenderEffect()` — side effects and when NOT to use |
| `components.md` | Component anatomy, metadata, template control flow (`@if`/`@for`/`@switch`) |
| `inputs.md` | Signal-based inputs, transforms, model inputs |
| `outputs.md` | Signal-based outputs, custom events |
| `host-elements.md` | Host bindings, attribute injection |
| `signal-forms.md` | Angular Signal Forms (v21+) — **not used in this project** (we use `uwwb-form`) |
| `reactive-forms.md` | Reactive Forms reference |
| `template-driven-forms.md` | Template-driven Forms reference |
| `di-fundamentals.md` | Dependency Injection overview, `inject()` function |
| `creating-services.md` | Services, `providedIn: 'root'` |
| `defining-providers.md` | `InjectionToken`, `useClass`, `useValue`, `useFactory` |
| `injection-context.md` | Where `inject()` is allowed, `runInInjectionContext` |
| `hierarchical-injectors.md` | `EnvironmentInjector` vs `ElementInjector`, resolution rules |
| `angular-aria.md` | Accessible components (Accordion, Listbox, Combobox, Menu, Tabs, etc.) |
| `define-routes.md` | URL paths, static/dynamic segments, wildcards, redirects |
| `loading-strategies.md` | Eager vs lazy loading |
| `show-routes-with-outlets.md` | `<router-outlet>`, nested/named outlets |
| `navigate-to-routes.md` | `RouterLink`, programmatic `Router` navigation |
| `route-guards.md` | `CanActivate`, `CanMatch` guards |
| `data-resolvers.md` | `ResolveFn` — pre-fetch data before route activation |
| `router-lifecycle.md` | Navigation events, debugging |
| `rendering-strategies.md` | CSR, SSG, SSR with hydration |
| `route-animations.md` | View Transitions API |
| `angular-animations.md` | CSS animations and legacy DSL |
| `component-styling.md` | Component styles, encapsulation |
| `tailwind-css.md` | Tailwind integration — **not used in this project** (we use PrimeFlex) |
| `testing-fundamentals.md` | Unit testing patterns, `TestBed` |
| `component-harnesses.md` | Component interaction patterns |
| `router-testing.md` | `RouterTestingHarness` |
| `e2e-testing.md` | E2E testing best practices |
| `cli.md` | Angular CLI commands |
| `mcp.md` | Angular MCP Server tools |

## Backend (liability-application)

### Architecture

DDD-layered multi-module Maven project. Each feature module follows:
```
feature/{domain}/src/main/java/.../
  input/controller/    # REST controllers (InputAdapter)
  service/             # ApplicationService — orchestrates domain + output
  domain/              # Business entities + domain services
  validation/          # Bean validation
```

Modules: `generaldata`, `costdata`, `exposureinformation`, `programcoverage`, `calculationadjustment`, `summary`. Shared code in `shared/domain` and `shared/global`.

### Commands

```bash
cd liability-application
./mvnw clean install                    # Full build
./mvnw spotless:apply                   # Format code
# Local: use Spring profile "local", "noauth" to disable OAuth2, "partnermock" for mock partners
```

## Backend (liability-ios)

FaktorZehn IOS integration. Java 21 + Maven. Uses Spotless for formatting. Custom `org.faktorips` classes exist due to FaktorZehn API limitations.

## Backend (risk-metadata-service)

Standalone Spring Boot service on port 8084. Build with `./mvnw clean install`, run with `local` profile.

## Frontend (Development Guidelines)

> **Detailed conventions for liability-frontend development — critical for code reviews, feature implementation, and architectural decisions.**

### Core Principles

1. **Occam's Razor** - Bare minimum, question every addition, "What breaks if removed?"
2. **Cognitive Load** - Domain-specific naming (`isLoadingPolicy` not `isLoading`)
3. **Explicit > Implicit** - `coveragesResource`, `policyResource` not generic `resource`
4. **Locality** - Group by domain (all Policy CRUD together), not technical layer
5. **Fail Fast** - Type safety, required properties, no defensive loading
6. **Fix Cause** - Architectural fixes not symptoms

### Component Layers

| Layer | Responsibility | ❌ Never | ✅ Always |
|-------|---------------|----------|-----------|
| **Component** | Display, dispatch, UI quirks | Logic, debouncing, transformation, RxJS chains | Forward intentions only |
| **State** | Business logic, cancellation, guards | Data transformation in postactions | Optimistic updates, read own data |
| **Selectors** | Computed aggregations, transformation | — | Complex derivations |
| **Service** | HTTP calls | Logic | Thin wrappers |

```typescript
// ✅ State reads own data
save() { this.store.dispatch(new SaveAction()); }
@Action(SaveAction) save(ctx) { return this.service.save(ctx.getState().data); }

// ❌ Component sends state data back
save() { this.store.dispatch(new SaveAction({ data: this.formData() })); }
```

### AsyncState Flow

**Model slices:** `AsyncState<T>` with query `status/error`, mutation `mutationStatus/mutationError`, seed via `initialAsyncState()`

**Helpers:** `queryAsyncState()` (reads, keeps prior data, `silent` loads, optional `transform`) | `mutateAsyncState()` (writes, optimistic + rollback, `applyResponse`, `sideEffect`)

**Selectors:** `createAsyncSelectors` exposes `loading/error/data/asyncState`

```typescript
// Query (GET) - silent=true for background refresh
queryAsyncState({ ctx, key: 'resource', request: api.load(), silent: true })

// Mutation (POST/PUT/DELETE) - optimistic with rollback
mutateAsyncState({
    ctx, key: 'resource', request: api.delete(id),
    optimistic: prev => ({ items: prev.items.filter(i => i.id !== id) }),
    applyResponse: resp => resp,
    sideEffect: () => ctx.dispatch(new Reload())
})
```

**Key improvements:** `mutationStatus: RequestStatus` (not boolean), separate `optimistic`/`applyResponse`, type-safe keys

**Migration:** ✅ New code | 🟡 Refactor opportunistically | Details: `/docs/async-state-helpers.md`

### Organization

- **Constructors** - Extract to `setup*()` methods (3-5 lines max)
- **Components** - Group signals by domain, section comments, consistent signatures (`onPolicyRetry()`)
- **State** - Group CRUD by domain (all Policy actions together)

### Forms (uwwb-form)

**Pattern:** External factory functions, inline control declarations, full resource to all forms, fully qualified control paths

```html
<uwwb-form [data]="formData()" (valueFormChangedEvent)="validate($event)" />
```

```typescript
// Model: Fully qualified paths with asyncMessages
controls: [{ name: 'coverage.coverage.value', validators: { asyncMessages: (val) => val.coverage.coverage.messages } }]

// Component: Forward event.data (strip validation messages before dispatch)
validate(event) { this.store.dispatch(new Validate(stripValidationMessages(event.data))); }

// State: Normalize paths, mark properties changed with markPropertyAsChanged
trimSectionPrefix('coverage.coverage.value', 'coverage') // → 'coverage.value'
```

**Key practices:** Recreate FormGroups on visibility toggles, guard PrimeNG dropdown emissions, consolidate validation handlers, prefix controls by section

**Dynamic Array Controls:** When generating controls from an array (e.g., `resource.events`), use index-based data paths as control names:

```typescript
// ✅ Index-based data path — mergeData/patchValue/get all work
controls: resource.events.map((event, index) => ({
    name: `events.${index}.exclusion.value`,
    validators: {
        asyncMessages: (val: Resource) => val.events?.[index]?.exclusion?.messages,
    },
}))

// ❌ Display label as name — mergeData puts values at wrong level, patchValue can't match
controls: resource.events.map((event) => ({
    name: event.exclusion?.value?.label,
    validators: {
        asyncMessages: (val: Resource) => event.exclusion?.messages, // stale closure
    },
}))
```

**Key rules:**
- Control `name` must be a valid lodash `get()` path into the data structure
- `asyncMessages` must read from the validator's `val` parameter (live response), not the closure variable (stale)

**ALTERNATIVE (Legacy):** Type guards on data structure (not string-based `controlName` routing)

### Signal & Reactivity Rules

**Lifecycle & Effects:** `effect()` only in injection context (constructor/field initializers), never for mutations, use for side effects only

```typescript
// ✅ Effects for side effects (logging, localStorage, analytics)
constructor() {
  effect(() => {
    console.log('Cart updated:', this.totalItems());
    localStorage.setItem('cart', JSON.stringify(this.cartItems()));
  });
}

// ❌ Never use effect() for mutations (infinite loops!)
effect(() => this.counter.set(this.counter() + 1)); // ❌

// ✅ Use computed() for derived state
total = computed(() => this.subtotal() + this.tax());
isEmpty = computed(() => this.items().length === 0);
```

**Immutable Updates:** Always use `.set()` or `.update()` with immutable patterns, never mutate signal values directly

```typescript
// ✅ Immutable updates with update()
this.items.update(items => items.map(i =>
  i.id === id ? {...i, quantity: newQty} : i
));

this.items.update(items => [...items, newItem]);
this.items.update(items => items.filter(i => i.id !== id));

// ❌ Never mutate signal values directly
this.items().push(newItem); // Breaks reactivity!
this.items()[0].quantity = 5; // Breaks reactivity!
```

**toSignal/toObservable Interop:** Initialize `toSignal()` outside `computed()`, avoid side effects in computed expressions

```typescript
// ✅ Initialize toSignal() outside computed()
dataSignal = toSignal(dataObservable$);
result = computed(() => doSomething(dataSignal()));

// ❌ Never call toSignal() inside computed() (side effects!)
result = computed(() => {
  const dataSignal = toSignal(dataObservable$); // ❌
  return doSomething(dataSignal());
});
```

**Template Rules:** Signals MUST be invoked `()`, track functions MUST be invoked

```typescript
// ✅ Signals invoked in templates
template: `{{ mySignal() }}` // ✅
template: `{{ mySignal }}`   // ❌ ESLint NG8109

// ✅ Track functions invoked in @for
@for (item of items(); track item.id) { } // ✅
@for (item of items(); track trackById) { } // ❌ ESLint NG8115
```

**Change Detection:** Set initial values in constructor/ngOnInit, avoid mutations in `ngAfterViewInit`, use `PendingTasks` for async stability (zoneless)

```typescript
// ✅ Set initial values in constructor/ngOnInit
constructor() { this.setupInitialState(); }
ngOnInit() { this.loadData(); }

// ❌ Never mutate in ngAfterViewInit (ExpressionChangedAfterItHasBeenCheckedError)
ngAfterViewInit() { this.value = 'changed'; } // ❌

// ✅ Use PendingTasks for async stability (zoneless apps)
private pendingTasks = inject(PendingTasks);
async loadData() {
  const taskRef = this.pendingTasks.add();
  try { await this.service.fetch(); }
  finally { taskRef.remove(); }
}
```

**Migration Strategy:** Always signals for new code, migrate opportunistically when refactoring, use schematics for bulk conversions

```typescript
// ✅ New features - Always use input()/output()
readonly user = input.required<User>();
readonly showDetails = input(false);
readonly userEdit = output<User>();

// ✅ Components being refactored - Convert opportunistically
// 🟡 Stable components - Only if blocked by new architecture
// ❌ Legacy NgModules with low ROI - "Ostrich" approach

// Bulk conversion schematics:
// ng generate @angular/core:signal-input-migration
// ng generate @angular/core:inject
// ng generate @angular/core:standalone
```

### Directives - Dynamic DOM Patterns

**For async loading/navigation:** Signals + observers (ResizeObserver, MutationObserver)

```typescript
// Signal-triggered debounced checks
checkTrigger = signal(0);
constructor() {
    toObservable(this.checkTrigger).pipe(skip(1), debounceTime(100), takeUntilDestroyed())
        .subscribe(() => animationFrameScheduler.schedule(() => this.check()));
}

// Defensive queries
const els = el.querySelectorAll('[data-target]');
if (els.length === 0) { this.reset(); return; }

// Hysteresis (prevent flickering)
const threshold = currentState ? exitThreshold : enterThreshold;
```

**Cleanup:** `destroyRef.onDestroy(() => observer?.disconnect())`

### Critical Code Review Protocol

**⚠️ Question First, Don't Just Document!**

**Red Flags:**
- Pattern not found elsewhere → Why different?
- Defensive layers (component + state + framework) → Which layer owns this?
- Heavy RxJS in component → Should be in state?
- "Need to explain to team" → Too complex

**Response:** Present options ("State has `cancelUncompleted` - component debounce adds complexity. Simplify?"), not assumptions

### Task Execution Protocol

**ALWAYS start with data flow** (Component → State → Selectors), not component-scoped fixes

**Before ANY code changes:**
1. Read complete flow (state + selectors + related components)
2. Identify true owner per architecture
3. Question complexity placement
4. Propose architectural fix if misplaced

**Component logic that belongs in state:** Debouncing, selector merging, RxJS chains, validation orchestration, transformation

### Styling - PrimeFlex Utility-First

**ALWAYS check PrimeFlex FIRST** (https://primeflex.org) - Custom CSS is the exception

**✅ Use utilities for:** Layout (`flex`, `grid`), position (`fixed`, `top-0`), spacing (`p-3`, `m-2`), flexbox (`justify-content-start`), z-index (`z-2`), shadows (`shadow-3`)

**❌ Custom SCSS ONLY for:** Theme vars (`var(--hdi-white)`), non-standard spacing, custom effects, transitions, pseudo-selectors, calculations

#### Patterns

**1. Templates** - Utilities in HTML (60-80% CSS reduction)
```html
<div class="flex justify-content-start p-3"><button class="mt-3">Save</button></div>
```

**2. Directives (PREFERRED)** - Inline styles via `setProperty()`/`removeProperty()` + PrimeFlex classes
```typescript
el.style.setProperty('box-shadow', '0 -2px 10px rgba(0, 0, 0, 0.1)');
el.classList.toggle('fixed', isActive); el.classList.toggle('bottom-0', isActive);
```
**Benefits:** Self-contained, no SCSS file, no global pollution, clean lifecycle

**2a. Directives (Legacy)** - Dynamic classes + minimal SCSS (only if pseudo-selectors needed)

**3. Components** - Mix utilities + minimal custom for theme/complex styling

#### Code Review
- [ ] Checked PrimeFlex first?
- [ ] Every custom CSS line justified? (theme/non-standard only)
- [ ] Layout/spacing in template utilities?
- [ ] Aim for 60%+ CSS reduction

### Testing & Quality

**Coverage:** ≥80% branch coverage via `npx nx test <project> --codeCoverage`

**Pre-push:** Run relevant lint/test/Playwright suites

**Specs:** Mirror behavior, cover optimistic flows/selectors, delete stale tests

**Type safety:** Remove unused code immediately, no `any`, trust API contracts

### Standalone Migration

**Posture:** "Ostrich" legacy NgModules when risk/ROI is low (Angular still supports them); new work ships standalone-first

**Incremental:** Remove modules gradually (standalone components can import NgModules), expose public APIs via barrels/path mappings, use Nx lint to prevent barrel bypassing/cycles

**Migrate only:** What's touched or blocks new features (avoid churn)

### Refactoring Checklist
- [ ] Constructor 3-5 lines, extract to `setup*()` methods
- [ ] No `effect()` mutations, `setTimeout()`, boolean control flow
- [ ] Signals use immutable updates (`.update()` with spread/map/filter)
- [ ] `toSignal()` initialized outside `computed()`
- [ ] Signals invoked in templates (`mySignal()`), track functions invoked
- [ ] Initial state set in constructor/ngOnInit (not `ngAfterViewInit`)
- [ ] Domain-specific naming (`isLoadingPolicy` not `isLoading`)
- [ ] Signals/CRUD grouped by domain
- [ ] State uses `mutationStatus: RequestStatus`
- [ ] New features use `input()`/`output()` functions (not decorators)
- [ ] Tests updated, ≥80% coverage
- [ ] PrimeFlex utilities checked first
- [ ] Unused code removed

### Resources
**Context7 MCP:** `/angular/angular`, `/ngxs/store` (on-demand for complex patterns, migrations, troubleshooting)
**AsyncState Details:** See "AsyncState Flow" section above

### Cross-Session Memory (claude-mem)

Plugin installed Apr 21, 2026. Every session is observed and summarized automatically.

**Architecture:**
- Worker service: `http://localhost:$((37700 + uid % 100))/` (port 37701 for this machine)
- MCP server connected as `plugin:claude-mem:mcp-search` but tools are NOT in the deferred tool list
- Use the HTTP API directly instead of MCP tools

**Search past sessions:**
```bash
curl -s "http://localhost:37701/api/search?query=<term>&limit=10"
```

**Fetch full observation details:**
```bash
curl -s "http://localhost:37701/api/observations" -d '{"ids":[1,2,3]}' -H 'Content-Type: application/json'
```

**Skills:** `mem-search`, `smart-explore`, `make-plan`, `do`, `timeline-report`, `knowledge-agent`

**3-step workflow (search → filter → fetch):**
1. `search?query=...&limit=20` — get index table with IDs (~50-100 tokens/result)
2. Pick relevant IDs from titles
3. `get_observations` with selected IDs (~500-1000 tokens each)

**Session start hook** injects a token-efficient summary of recent observations automatically at conversation start.

### Code Review Learnings

**From PR Feedback (Risk Profile Feature):**

1. **ESLint Module Boundaries** - Avoid local `@nx/enforce-module-boundaries` overrides in library `.eslintrc.json` files
   - ❌ Don't define boundary rules per-library
   - ✅ Rely on global `.eslintrc.json` configuration
   - **Exception:** Some legacy libs have local rules, but avoid for new features

2. **Import Statements in Actions** - Always use top-level imports, never inline `import()` types
   ```typescript
   // ❌ Inline imports
   constructor(public payload: import('@feature/lib').Type) {}

   // ✅ Top-level imports
   import { Type } from '@feature/lib';
   constructor(public payload: Type) {}
   ```

3. **Unused Subscriptions** - Remove dead code, especially empty subscriptions
   - ❌ Don't subscribe if nothing happens in the handler
   - ✅ Use `@OnPanelClose()` decorator in components for panel close handling
   - Panel close logic belongs in components, not postactions

4. **Nx Library Tags** - Libraries should have ONE type tag only
   - ❌ `["type:feature", "type:domain"]` - conflicting types
   - ✅ Domain libs: `["type:domain", "scope:feature-name"]`
   - ✅ View libs: `["type:feature", "scope:feature-name"]`
   - OpenAPI libs: `["type:openapi", "scope:feature-name"]`

5. **Folder Naming Convention** - Redundant naming is the codebase standard
   - Pattern: `libs/feature/{domain}/{domain}-{layer}/`
   - Example: `libs/feature/cost-data/cost-data-domain/`
   - This is consistent across ALL features - don't deviate

6. **PR Feedback Context** - Check if feedback applies codebase-wide
   - Comments may highlight existing inconsistencies, not just new code issues
   - Balance: Fix clear violations vs. creating new inconsistencies
   - When in doubt, follow the majority pattern in similar features

7. **State Data Consumption** - Action handlers should read from state, not action payloads
   ```typescript
   // ✅ Read offerNumber/optionIndex from state
   @Action(EditAction)
   edit(ctx: StateContext<StateModel>) {
       const { offerNumber, optionIndex } = ctx.getState();
       return queryAsyncState({ ctx, key: 'editing', request: api.get(offerNumber, optionIndex) });
   }

   // ❌ Pass offerNumber/optionIndex in every action payload
   @Action(EditAction)
   edit(ctx: StateContext<StateModel>, action: EditAction) {
       return queryAsyncState({ ctx, key: 'editing', request: api.get(action.offerNumber, action.optionIndex) });
   }
   ```
   - Store `offerNumber/optionIndex` once in initial load action (e.g., `GetRiskProfile`)
   - All subsequent actions read from `ctx.getState()` for consistency
   - Reduces action payload boilerplate

8. **Panel Opening Timing** - Avoid unnecessary API calls when opening edit panels
   - **Problem:** Making API call when opening edit panel causes delay, requires two clicks
   - **Solution:** Copy data from existing state instead of fetching again
   ```typescript
   // ✅ Synchronous data copy (instant panel opening)
   @Action(EditAction)
   edit(ctx: StateContext<StateModel>) {
       const state = ctx.getState();
       const data = state.mainResource.data;
       if (data) {
           ctx.patchState({
               editingResource: {
                   ...state.editingResource,
                   data: data,
                   status: 'success',
                   error: undefined,
               },
           });
       }
   }

   // ❌ Async API call (delays panel, requires two clicks)
   @Action(EditAction)
   edit(ctx: StateContext<StateModel>) {
       return queryAsyncState({ ctx, key: 'editingResource', request: api.get(...) });
   }
   ```
   - Maintains separation: `mainResource` (read-only view) vs `editingResource` (isolated editing with validation)
   - Panel opens immediately in postactions: `ofActionDispatched(EditAction)` → `slidePanelService.show()`
   - No network delay, better UX

9. **Unnecessary Type Assertions (SonarQube S4325)** - Don't cast when the type already matches
   ```typescript
   // ❌ Redundant cast — o is already Record<string, unknown> | undefined
   (o: Record<string, unknown> | undefined, key) => (o as Record<string, unknown>)?.[key]

   // ✅ Optional chaining handles undefined directly
   (o: Record<string, unknown> | undefined, key) => o?.[key]
   ```
   - If optional chaining `?.` is used, the `| undefined` union is already handled — no cast needed

### Self-Improvement Loop

Every PR, architectural decision, and recurring mistake is a learning signal. Capture it immediately — stale context is the enemy of consistent quality.

**Trigger → Capture → Apply → Prune**

#### Triggers (capture these immediately)
- PR feedback that required a code change → add to **Code Review Learnings**
- A pattern appearing in 3+ places that isn't documented → add to the relevant section
- A bug whose root cause was an architectural violation → add as a red flag with ✅/❌ example
- A guideline that caused confusion or was applied wrongly → clarify or remove it
- A session where Claude made the same mistake twice → add a rule to prevent it

#### Where to capture
| Signal | Destination |
|--------|-------------|
| PR feedback / code review pattern | **Code Review Learnings** section above |
| Recurring session behavior or preference | Project memory file (`liability-frontend/.claude/projects/.../memory/`) |
| One-off decision with lasting consequence | Project memory with **Why:** and **How to apply:** |
| New ✅/❌ pattern for an existing section | Inline example in that section |

#### Prune regularly
- Rule not triggered in 3+ months → remove or collapse it
- Two rules that contradict → resolve, document the winner and why
- Section never consulted → dead weight, cut it

#### Verification
After adding a rule: apply it to the next 3 relevant changes. If it doesn't improve the outcome, remove it. A rule that can't be verified is a rule that shouldn't exist.

### Implementation Notes
- Never create files unless necessary
- Always prefer editing existing files
- Never proactively create docs
- Maintain 100% type safety
- Apply Critical Code Review Protocol

## Cross-Cutting Concerns

- **Auth:** OAuth2 via EntraID (Keycloak in dev). Disable with `noauth` profile (backend) or `npm run start:no-auth` (frontend).
- **OpenAPI-first:** Liability feature specs live in `liability-frontend/openapi/` (e.g. `openapi-cost-data-api.json`). Property/Cyber specs are co-located under `libs/feature/{app}/{domain}/{domain}-openapi/spec/` or `libs/feature/{app}/{domain}/openapi/spec/`. Generated clients must not be hand-edited — run `npm run generate:<domain>`.
- **Docker:** `liability-application/docker/` has docker-compose with Keycloak + PostgreSQL. Frontend Dockerfile uses `envsubst` for runtime config.
- **Mocking:** Mockoon configs in `liability-application/mockoon/` for Pricing and Partner services.
- **E2E tests:** Playwright in `liability-frontend/e2e/` with layered Page Object Model. Test attribute: `pw-testid`. Tags: `@property`, `@liability`, `@shared`. Tests organized into `tests/e2e/` (happy paths), `tests/regression/`, `tests/sanity/`, `tests/smoke/`, `tests/icp/`. Reusable logic in `teststeps/` (`.step.ts` files), page objects in `pages/`, test data in `testdata/`. Use custom helpers (`fillTextInputField`, `fillNumberInputField`) instead of Playwright's `input.fill()` for Angular compatibility.
- **CI:** Azure DevOps pipelines in `liability-application/pipelines/` and `liability-frontend/pipeline/`.

