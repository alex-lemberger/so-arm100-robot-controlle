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