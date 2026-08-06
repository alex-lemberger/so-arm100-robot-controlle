# AGENTS.md

This file provides guidance to OpenCode when working with code in this repository.

## Operating Principles

Apply these to **every** task, before producing code, specs, or analysis. Most errors here trace to one root cause: confident output that was never checked against ground truth. These principles exist to break that habit.

1. **Ground truth over priors — verify before you assert.** Never state a file path, API shape, type, or convention from memory. Read it or grep it first; training priors do not reflect *this* codebase. If you cannot verify a claim, label it explicitly as an assumption.
2. **Project docs are binding.** Read this file and `CLAUDE.md` before acting. Their conventions override defaults and "common practice." (Example failure: proposing to overload `useMockData` despite a section that explicitly documents that switch.)
3. **Plausible ≠ correct.** Surface-coherent text is the default failure mode of a language model. After drafting, attack your own output: where is the circular logic, the unverified claim, the missing case? If you did not try to break it, it is not done.
4. **Trace dependencies end-to-end.** For any interface or change, enumerate every producer and every consumer of each field/stream. An output with no defined input feed, or a refactor that does not list the consumers it touches, is incomplete by definition.
5. **Detect logical traps.** Watch for circularity, tautology, and metric leakage. Never derive a value from input X and then evaluate or correlate it against X.
6. **Make contracts explicit.** State units, ranges, and null/empty/error cases. Ambiguity (e.g. 0–1 vs 0–100) is a latent bug — pin it.
7. **Never fabricate.** If a value or signal is unknown or unavailable, say so or return `null`. An invented plausible number is worse than an admitted gap because it hides.
8. **Reuse before invent.** Match the shape of neighboring code (observable properties, naming, DI pattern). A new abstraction needs justification, not just novelty.
9. **Do not trade rigor for convenience.** No "tests if possible," no skipped verification. If something is testable, test it; typecheck/build before claiming it compiles.
10. **Verify before claiming "done."** Run the command and quote the output. "Should work" is not "works" — evidence before assertion, every time.
11. **Surface scope and unknowns.** State what you did not check, what is out of scope, and any open questions. Honest gaps let the human catch what you missed; papered-over gaps do not.
12. **Citations must be real and checkable — never fabricate authority.** Cite by `file:line` or by the exact heading/rule text; never invent rule numbers, page numbers, or section refs (markdown has no pages). The word "verified" or "grep confirms" is only allowed when you actually ran the command — paste or name it. A confident, well-formatted citation that points to nothing is worse than no citation: it borrows trust it did not earn and is the hardest error to catch. Before writing "Rule #N says…", confirm Rule #N exists and says that. *(This rule exists because a review once cited "Rule #27/#43/#115" and "AGENTS.md p.142" — none of which exist — to make a wrong verdict look rigorous. A later review, with this rule in front of it, still cited a non-existent "Rule #30" and misquoted this very rule. Stating the rule reduces but does not eliminate the behaviour: a weak model cannot reliably check its own citation. Treat any citation that does not resolve to a real `file:line` or quoted text as **invalid on sight** — this needs an external gate, e.g. a reviewer or CI step rejecting unresolvable refs, not just good intentions.)*

13. **Verification levels are not interchangeable; never imply an unrun check passed.** Compiling, unit-testing, and running at runtime are three separate claims — state which you actually performed. `ng build` passing does **not** mean tests pass or the app runs. If a check cannot be run (e.g. Karma is broken repo-wide, see Commands), say so plainly and substitute one you *can* run: typecheck the spec (`npx tsc -p tsconfig.spec.json --noEmit`) and/or prove the logic with an isolated `node` script. Never present authored-but-unrun tests as if they pass, and never let a green build stand in for a green test or a working runtime. *(This rule exists because an executor shipped 5 unit tests that would have failed on a `BehaviorSubject` replay; with Karma broken it never ran them and treated the task as done — the build was green, the tests were write-only.)*

> **Authority boundary.** These principles are executor-side guards. Authoring specs/plans, judging/reviewing work, and final sign-off stay with a human or a strong reviewer — a weak model cannot self-certify past them (see the citation gate and the broken-Karma case). When in doubt, hand the decision up, do not assert it.

For spec/plan documents specifically, also apply the checklist in **"Spec & Plan Authoring — required rigor"** below.

## Architectural Rules

Binding patterns for this codebase, each verified against the source (2026-06-09). Follow them; deviating needs a stated reason.

### A. Abstraction & DI
1. **Never inject a bare TypeScript interface** (they don't exist at runtime). A DI-injected contract is an `abstract class` that doubles as the token (`core/neurofeedback/brain-device.ts`). A strategy contract selected manually may be a plain `.interface.ts` (`modules/language-learning/services/exercise-source.interface.ts`).
2. **Use one of the two sanctioned implementation-selection mechanisms — do not invent a third:** (a) DI provider override in `main.ts` (`BrainDevice` → `MockNeurosityService`); (b) constructor branch on an environment flag (`ExerciseState`: `useMockData ? mock : wp`).

### B. Feature switches
3. **One flag, one meaning.** `useMockData` = data source; `device` (`mock|neurosity|muse`) = which headset. An orthogonal concern gets its **own** flag (e.g. `CaptureModeService.isMock`). Never overload an existing switch — adding a hidden second meaning is a bug.

### C. State (NGXS) — three stores: `exercise`, `capture`, `dashboard`
4. **Actions are namespaced in the state file. Error handling is intentionally not uniform:** async handlers return RxJS streams with `catchError` that writes `error` to state (`exercise.state.ts`, `dashboard.state.ts`); purely synchronous handlers call `patchState` directly (`capture.state.ts`). Match the neighboring handler's style — do not force a stream onto a synchronous action, and `handleError` is `exercise.state`'s helper, not a mandated convention.
5. **Components read state via Signals (`toSignal`).** There are zero `async` pipes in the templates — keep it that way.

### D. Data access
6. **All Supabase access goes through `SupabaseClientService`.** Raw `createClient` belongs in exactly one file (`core/supabase/supabase-client.service.ts`). Persistence and streams live in services, never in components.

### E. Stream contracts
7. **Expose observable *properties* (`focus$`), not getter methods (`getFocusScore()`).** Probability/score streams are normalized **0–1** and **nullable until data arrives** (`Observable<number | null>`). New engagement or metric streams must follow this shape.

### F. Conventions
8. kebab-case filenames; no `I`-prefix on interfaces; `app` selector prefix; SCSS component styles; DM Sans (UI) / DM Mono (numeric) fonts.

### G. Module boundaries
9. `core/` = cross-cutting · `modules/` = features · `shared/` = layout. **Adding a backend means implementing the existing contract, not editing state** (proven by the three `ExerciseSource` implementations behind one interface).

## Project

Angular 19 SPA pairing language-learning exercises with live EEG neurofeedback. A Neurosity headset streams focus/calm probabilities while the user does exercises; a dashboard correlates brain metrics against learning progress. Backend is Supabase (PostgreSQL + Supabase Auth + Supabase Storage); an optional WordPress REST source supplies exercise content.

## Commands

- `npm start` / `ng serve` — dev server on http://localhost:4200 (development config, source maps, no optimization).
- `ng build` — production build by default → `dist/neurofeedback-lang-app`. `npm run watch` for incremental dev builds.
- `ng test` — unit tests via Karma + Jasmine. ⚠️ **Currently broken out-of-box**: all specs fail because `@neurosity/sdk`'s browser bundle throws `parcelRequire is not defined` under the Karma/webpack build, which cascades into an AppComponent injector error. Fix the SDK import/test setup before trusting test results. Headless run: `ng test --watch=false --browsers=ChromeHeadless`.
- Single test: temporarily use `fdescribe`/`fit` in the `.spec.ts`, or `ng test --include='**/neurosity.service.spec.ts'`.
- No linter or e2e runner is configured.
- **Verify compilation** with `ng build --configuration development` (fast; the broken `ng test` can't be trusted for typechecks).
- ⚠️ **`ng build` does NOT type-check — esbuild transpiles only.** A variable used before its `const` declaration will silently pass `ng build` and crash at runtime with `ReferenceError`. After every task that adds or refactors TypeScript, run `npx tsc --noEmit` (uses `tsconfig.json`; exits 0 if clean). This is the only gate that catches real type errors. Proven failure 2026-06-12: `lShP` used before declaration passed `ng build` but crashed `buildSkeleton()` at runtime.

## Mock vs. real data — the central switch

`src/app/environments/environment.ts` `useMockData` (currently `true`) toggles data sources app-wide. It is read in three independent places, so flipping it changes behavior everywhere:

- `ExerciseState` constructor picks `MockExerciseService` vs `WpExerciseSourceService`.
- `DashboardService` branches internally between `getMock*()` generators and Supabase queries.
- `NeurosityService` itself is **always** replaced by `MockNeurosityService` via a DI override in `main.ts` (`{ provide: NeurosityService, useClass: MockNeurosityService }`) — independent of `useMockData`. To talk to a real headset, change that provider and set a real `neurosityDeviceId`.

`environment.ts` holds the Supabase project URL + anon key. Project is live at `https://hmiwxefpxbvjstsdywxb.supabase.co` (Frankfurt, eu-central-1). Schema deployed. Auth user created and verified.

## Architecture

Standalone-component app — no `AppModule`. `main.ts` is the composition root: it wires Angular Material modules, NGXS (`provideStore`), and the mock overrides. No Firebase providers.

**State (NGXS).** Three stores. `ExerciseState` (`modules/language-learning/state/exercise.state.ts`) and `CaptureState` (`modules/capture/state/capture.state.ts`) are registered in `main.ts`; `DashboardState` is provided at the dashboard feature level. Actions live in the same file under a namespace (e.g. `ExerciseActions`, `CaptureActions`). Action handlers return RxJS streams (`tap` to commit, `catchError` → `handleError`). Newer components consume state via `toSignal()` rather than the `async` pipe — prefer Signals for new component state.

**Exercise sources — strategy pattern.** `ExerciseSource` interface (`getExercises`/`getExercisesByType`/`getExercise`) has three implementations: `ExerciseService` (Firestore), `WpExerciseSourceService` (WordPress REST), `MockExerciseService`. `ExerciseState` holds one as `exerciseSource`. When adding a backend, implement this interface rather than touching the state.

**Neurofeedback (`core/neurofeedback`).** `NeurosityService` wraps the `@neurosity/sdk` `Notion` client and exposes `focus$`/`calm$` BehaviorSubjects. `LearningSessionService` subscribes to those streams during an active session, accumulates a running average, and persists per-tick metrics via `SupabaseClientService`. `FirestoreService` is deleted — services inject `SupabaseClientService` directly.

**Visualisations (`core/visualisations`).** D3-based chart components (focus/bar/pie/scatter) plus a `drone-sim` component on its own top-level `/droneSim` route.

**Capture module (`modules/capture/`).** Skill-data capture platform (Phase 1 complete). `/capture` route sits outside the dashboard shell. Workers wear EEG + BLE IMU gloves + record video; raw data uploads to Supabase Storage (`captures/{sessionId}/video.mp4`, `imu_left.bin`, `imu_right.bin`) with EEG ticks to Supabase table `eeg_ticks` (FK → `captures`, ON DELETE CASCADE). `CaptureSessionService` orchestrates all streams; `ImuService` uses Web Bluetooth API (Chrome/Android only). **Wizard is state-machine based** (`CaptureState.status` → `@switch` in `CaptureShellComponent`) — not route-based; steps are hardware-gated and sequential. **`CaptureModeService.isMock`** is a `signal<boolean>` initialized from `environment.device === 'mock'` (separate from `useMockData`); toggle at runtime via `captureModeService.toggle()`. **`CaptureHistoryService`** (`providedIn: 'root'`) is the single source of truth for session history: real mode queries Supabase on dashboard init; mock mode `load()` is a no-op and `CaptureSessionService.stopSession()` calls `addMockSession()` instead. Sessions table rendered below `.dash__grid` on `/dashboard`.

**Routing.** `DashboardLayoutComponent` is the shell; children are `/dashboard` and `/exercises` (with nested `/exercises/speaking/:id`). `/droneSim` and `/capture` sit outside the shell. The shell uses a **custom fixed hover-expand sidebar** (`NavigationComponent`, 64→244px, pure CSS) — not `mat-sidenav`. The `/dashboard` landing view is `shared/components/layout/dashboard-layout/dashboard.component.ts` (Signals; `toSignal` of `BrainDevice.focus$/calm$`). Its bespoke viz — arc rings, EEG waveform, weekly bars — are plain-SVG standalone widgets under `dashboard-layout/widgets/` using `input()` signals, **not** d3.

## Layout

- `core/` — cross-cutting: `neurofeedback/` (services, models), `auth/`, `visualisations/`, `state/`, `supabase/` (`SupabaseClientService`, `SupabaseAuthService`).
- `modules/language-learning/` — the main feature: components, services (exercise sources, audio recording), and `ExerciseState`.
- `modules/capture/` — skill-data capture platform (Phase 1 complete): `CaptureState`, `CaptureSessionService`, `CaptureHistoryService`, `ImuService`, `VideoRecorderService`, `CaptureUploadService`, components under `components/`.
- `shared/` — models, pipes, and layout components (dashboard shell, nav, header).
- `dashboard/` — dashboard data service (note: feature is split between here and `shared/.../dashboard-layout/`).
- `public/` and `src/assets/audio/` — exercise audio (German, Spanish).

## Conventions

- SCSS component styles; Angular Material `azure-blue` prebuilt theme + Tailwind utilities.
- Fonts (in `index.html`): **DM Sans** for UI, **DM Mono** for biometric/numeric values; Material Icons for `mat-icon`.
- Component selector prefix `app`.
- `GEMINI.md` is a historical refactoring log, not active rules. `README.md`'s "Database Recommendations" section is also stale — the app runs on Supabase today.

## Three.js / Canvas Components

Established pattern (see `robot-viewer.component.ts`, 2026-06-12). Follow exactly when adding any WebGL/canvas component:

- **Init in `afterNextRender()`** — not `ngAfterViewInit`; Angular 17+ SSR-safe.
- **WebGL guard first:** `if (!canvas.getContext('webgl2') && !canvas.getContext('webgl')) return;` — prevents crash in jsdom test env and non-WebGL browsers.
- **RAF loop cleanup:** store `rafId = requestAnimationFrame(loop)`; cancel in `ngOnDestroy` via `cancelAnimationFrame(this.rafId)`.
- **Dispose everything in `ngOnDestroy`:** `renderer.dispose()`, all `MeshPhongMaterial.dispose()`, `ResizeObserver.disconnect()`. Three.js leaks GPU memory otherwise.
- **ResizeObserver on the canvas element** — updates `renderer.setSize()` + `camera.aspect` + `camera.updateProjectionMatrix()`.
- **Signal `effect()` for data binding** — watch input signals, call update function; do not rebuild scene on each frame.
- **Tree-shake Three.js:** import only named symbols (`WebGLRenderer`, `Scene`, …); never `import * as THREE from 'three'`.
- **OrbitControls** from `three/addons/controls/OrbitControls.js` (works with `moduleResolution: "bundler"` in `tsconfig.json`).
- **Spec testing:** add `NO_ERRORS_SCHEMA` to `TestBed` config when the component hosts a Three.js child — canvas has no WebGL in jsdom and the child will early-return from init without crashing.

## Spec & Plan Authoring — required rigor

When writing or revising any spec/plan/architecture doc in this repo (`specs/`, `plans/`), apply the checks below **before** declaring the doc ready. These were distilled from a real failed review (`specs/engagement_source_review.md`, the `IEngagementSource` spec/plan) where a surface-plausible document hid three blockers. Do not repeat those mistakes.

### 1. Trace data flow in both directions
For every interface/service, verify the **producer and consumer of each field actually exist**.
- A method that *returns* a metric implies something *computes* it from inputs — confirm those inputs have a defined ingest path. Exposing an output stream without wiring its input is a **circular/unbuildable design**, not a detail to resolve later.
- List every existing consumer of any stream you abstract before proposing the refactor. **Verified (2026-06-09):** the only direct consumers of `BrainDevice.focus$`/`calm$` are `LearningSessionService`, `dashboard.component.ts` (via `toSignal`), `live-capture.component.ts`, and `capture-session.service.ts`. `ExerciseState` and `CaptureState` do **not** consume these streams — `ExerciseState` injects only `Router` + the three exercise sources and receives focus metrics pre-computed via the `UpdateFocusMetrics` action. Confirm with `grep -rln 'focus\$' src/app`, do not infer consumers from prose.

### 2. Check for metric leakage / tautology
Never derive a signal from input X and then correlate or evaluate it against X. The dashboard's core purpose is correlating engagement against learning progress (error rate). A "focus" score *computed from* error rate, charted against error rate, is a guaranteed, meaningless correlation. Tag signal provenance and keep derived/heuristic signals out of correlations that would close the loop.

### 3. Respect the central switch — don't overload `useMockData`
`useMockData` means mock-vs-real **data**, read in three independent places (see "Mock vs. real data"). Any new, orthogonal toggle (tier, mode, device) gets its **own** flag. Precedent: `CaptureModeService.isMock` and `environment.device` are deliberately kept separate from `useMockData`. Adding a hidden fourth meaning to the central switch is a bug, not a shortcut.

### 4. Honor existing conventions (verify, don't guess)
Grep the codebase before asserting a shape. Known constraints:
- **Observable shape:** existing services expose observable *properties* (`focus$`, `calm$`) consumed via `toSignal(...)`. Prefer that over getter methods (`getFocusScore()`) unless there's a reason — otherwise every call site needs a needless refactor.
- **DI tokens:** TypeScript `interface`s don't exist at runtime and **cannot be injected**. Use an `abstract class` or `InjectionToken` (follow `BrainDevice`).
- **Naming:** files are kebab-case (`capture.state.ts`), not snake_case. No `I`-prefix on interfaces (`BrainDevice`, not `IBrainDevice`).
- **Value ranges:** pin numeric contracts explicitly. `focus`/`calm` have a documented history of 0–1 vs 0–100 confusion (the "mock 0-100 bug," fixed twice). State the range and add an adapter if a source differs.
- **Placement:** don't nest a software-only abstraction under `core/neurofeedback/` — that re-couples to the thing being decoupled.

### 5. No hand-waved formulas, no fabricated signals
- Any derived metric needs a **concrete normalization** (what input value maps to 0.0 vs 1.0). "high latency = low focus" is not a spec.
- If no credible signal exists for a field, return `null`/unavailable — do **not** fabricate a number (e.g. a software-derived "calm" score). Honest gap beats pseudoscience.

### 6. State persistence and tests explicitly
- Say where any new data lives (table/column) or that it is **not persisted**. `eeg_ticks` is EEG-only; new telemetry needs its own home.
- Pure functions (e.g. a score formula) are unit-testable **despite** the broken Karma/`parcelRequire` setup, because they avoid the `@neurosity/sdk` import. Extract such logic and spec it — never downgrade tests to "if possible."

### 7. Add inter-phase verification
A single final `ng build` is not enough. Put a verification checkpoint after the highest-risk phase (typically the state-refactor phase), not only at the end.

### 8. A spec describes future work — don't fault it for not existing yet
When **reviewing** a spec/plan, a proposed artifact that the codebase does not contain yet (a new `InjectionToken`, a new `isProxy` flag, new classes) is the **deliverable**, not a defect. "No such token exists in the codebase" / "no established implementation" is not a valid criticism of a proposal — of course it doesn't exist; the spec is asking for it to be built. Valid criticisms are: the proposal conflicts with an existing pattern, is internally inconsistent, is unbuildable as specified, or misstates the *current* code it builds on. Verify the proposal against existing **patterns and constraints**, not against the absence of the thing being proposed. *(This exists because a review graded a spec **F** for proposing an `InjectionToken` and an `isProxy` flag that "don't exist" — both were the spec's own deliverables.)*

### 9. Plans must be fine-grained and build-gated
A plan is for a weak executor that drifts and invents APIs. Write it so it cannot. Every plan in this repo must:
- **One atomic task per step** — one file, one concrete change. Never bundle "update X, Y and Z" into a single checkbox.
- **A verification gate after every task** — state the exact command (`ng build --configuration development`) and that it must pass before the next task starts. Do not defer all verification to the end.
- **Explicit signatures and verified paths** — give the actual file path, type/method signature, and real handler/symbol names in each task, confirmed by grep first. The executor should copy, not guess. ("Inject `EngagementSource` into `ExerciseState` and call `recordInteraction()` in the `NavigateToNext`/`UpdateProgress` handlers" — not "wire up the state.")
- **Dependency order** — models → pure functions → providers → DI → integration → final verify. Highest-risk steps (state/integration) come last and get their own task each.
- **An explicit out-of-scope list** — fence the phase so the executor does not wander into deferred work.
- **Verify the data/wiring actually exists before depending on it.** Before a step says "feed X from Y", confirm Y produces X. *(This rule earned its keep: a plan was about to detail `focus = 1 - errorRate`, but a grep showed the app has no answer-correctness anywhere — `errorRate` had no source. Caught before granularizing, the signal was switched to interaction cadence, which the app does produce. See `plans/engagement_source_plan.md` for the resulting shape.)*

### Correction note — the grader also failed (verified 2026-06-09)
The first-pass review of the `IEngagementSource` spec/plan was itself sourced from `CLAUDE.md`/memory rather than from the code, and inherited the document's own false premise. Recorded here so future sessions do not repeat it:

- **False premise (student's spec §5 / plan Phase 3):** "refactor `ExerciseState` and `CaptureState` to inject `IEngagementSource` *instead of specific neuro-services*." Ground truth: **neither state injects any neuro-service.** `ExerciseState` injects only `Router` + three exercise sources; `CaptureState` has zero `focus`/`calm`/`BrainDevice` references. The engagement-stream seam is the four consumers named in rule #4 (chiefly `LearningSessionService`) — that is where an abstraction must be inserted, not in the NGXS states.
- **The review repeated it.** It listed `ExerciseState`/`CaptureState`/`DashboardService` as direct `focus$`/`calm$` consumers without grepping. A critique is not exempt from Principle #1 — verify the document under review *and* your own corrections against the code.
- **Two facts the review got needlessly wrong by trusting memory:**
  - Range: `BrainDevice.focus$`/`calm$` emit **0–1** (`number | null`); the mock's 0–100 is internal and divided by 100 before emit. The spec's "0.0–1.0" was already correct — the suggested "add an adapter" was speculative. Don't manufacture risks from half-remembered history.
  - `null`-for-unavailable is already the established contract (`Observable<number | null>`), so the recommendation that a Standard tier emit `null` for `calm` is not a new pattern — it matches `BrainDevice` exactly. Verifying would have stated it with confidence instead of as a proposal.

**Standing lesson:** before reviewing or correcting *anything*, grep the symbols involved. Trust neither the document under review nor the project's own prose for facts that a one-line search can confirm.
