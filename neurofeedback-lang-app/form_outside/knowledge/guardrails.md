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
