# Guardrails — Local Model Executor

Project root: `/Users/alexanderlemberger/neurofeedback-lang-app`
Read `CLAUDE.md` only when you need architecture context. The task prompt is the authority for what to change.

## Hard Stops — STOP immediately if any is true

1. Editing `main.ts` or `app.routes.ts` unless plan explicitly lists it
2. Adding an import whose file path you have not verified exists on disk
3. Adding a new npm package
4. Touching any file under `src/app/core/` not listed in the plan's File Map
5. Guessing an Angular Material selector, NGXS action type, or selector name — verify in source first
6. Editing any file outside the plan's File Map
7. Writing `any`, `as unknown as`, or `@ts-ignore`
8. Deleting existing code not listed as "remove" in the plan
9. Adding refactoring or cleanup unrelated to the task
10. Creating a commit unless the plan step explicitly says "Commit"

## Patterns

- New components: `standalone: true`, signals (`signal()` / `computed()` / `effect()`), implement `OnDestroy`
- New services: `providedIn: 'root'`, use `signal()` not `BehaviorSubject`
- NGXS handlers: return `Observable`, `tap` to commit, `catchError` → `handleError`
- Three.js: init in `afterNextRender()`, cancel RAF + disconnect ResizeObserver in `ngOnDestroy()`
- No `any`, no magic number repetition, `readonly` on all non-reassigned fields

## Verification (run in order before done)

1. `npx tsc --noEmit` — zero errors
2. `ng build --configuration development` — build succeeds (`ng test` broken project-wide, skip)
3. Scope audit: every file you touched must be in the plan's File Map
4. No `// TODO`, no half-implemented stubs, every plan checkbox ticked
