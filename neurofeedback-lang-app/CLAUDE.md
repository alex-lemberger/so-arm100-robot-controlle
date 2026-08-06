# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Angular 19 SPA pairing language-learning exercises with live EEG neurofeedback. A Neurosity headset streams focus/calm probabilities while the user does exercises; a dashboard correlates brain metrics against learning progress. Backend is Supabase (PostgreSQL + Supabase Auth + Supabase Storage); an optional WordPress REST source supplies exercise content.

**Companion repo (robot-learning pipeline).** This app is also the control-center frontend for `htdp`, the robot-arm learning pipeline at `~/human-task-dataset-pipeline` (separate repo: Python/uv, MuJoCo + LeRobot + ACT). The `/lab` section drives it via `htdp serve` (localhost FastAPI). **Read `docs/INTEGRATION.md`** for the contract, run flow (`npm run dev` → `/lab` → "Start server"), and task routing. Contract source of truth is the pipeline's `src/htdp/serve/models.py`, mirrored by `src/app/core/pipeline/pipeline.models.ts` — change both together. Keep the repos separate (the pipeline is a standalone product; don't monorepo).

## Commands

- `npm start` / `ng serve` — dev server on http://localhost:4200 (development config, source maps, no optimization).
- `ng build` — production build by default → `dist/neurofeedback-lang-app`. `npm run watch` for incremental dev builds.
- `ng test` — unit tests via Karma + Jasmine. ⚠️ **Currently broken out-of-box**: all specs fail because `@neurosity/sdk`'s browser bundle throws `parcelRequire is not defined` under the Karma/webpack build, which cascades into an AppComponent injector error. Fix the SDK import/test setup before trusting test results. Headless run: `ng test --watch=false --browsers=ChromeHeadless`.
- Single test: temporarily use `fdescribe`/`fit` in the `.spec.ts`, or `ng test --include='**/neurosity.service.spec.ts'`.
- No linter or e2e runner is configured.
- **Verify compilation** with `ng build --configuration development` (fast; the broken `ng test` can't be trusted for typechecks).

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

**Capture module (`modules/capture/`).** Skill-data capture platform (Phase 1 complete). `/capture` route sits outside the dashboard shell. Workers wear EEG + BLE IMU gloves + record video; raw data uploads to Supabase Storage (`captures/{sessionId}/video.mp4`, `imu_left.bin`, `imu_right.bin`) with EEG ticks to Supabase table `eeg_ticks` (FK → `captures`, ON DELETE CASCADE). `CaptureSessionService` orchestrates all streams; `ImuService` uses Web Bluetooth API (Chrome/Android only). **Wizard is state-machine based** (`CaptureState.status` → `@switch` in `CaptureShellComponent`) — not route-based; steps are hardware-gated and sequential. **`CaptureModeService.isMock`** is a `signal<boolean>` initialized from `environment.device === 'mock'` (separate from `useMockData`); toggle at runtime via `captureModeService.toggle()`. **`CaptureHistoryService`** (`providedIn: 'root'`) is the single source of truth for session history: real mode queries Supabase on dashboard init; mock mode `load()` is a no-op and `CaptureSessionService.stopSession()` calls `addMockSession()` instead. Sessions table rendered below `.dash__grid` on `/dashboard`. **`LiveCaptureComponent`** shows a MM:SS elapsed timer (signal + `setInterval`, cleared in `ngOnDestroy`) in the REC status row.

**Sim bridge (`core/sim-bridge/`).** `SimBridgeService` connects to the MuJoCo WebSocket server at `ws://localhost:8765`. All state (status/tick/totalTicks/joints/currentEegTick) is held in a single `_snap` signal updated atomically on each WS message — prevents partial-render races. Reconnects automatically (3s delay, max 3 retries). `transferSession()` sends `{cmd:'replay', eegTicks, durationMs, ...}`; in mock mode `CaptureSessionsTableComponent` synthesises sinusoidal EEG ticks client-side (no Supabase rows needed). `SimControlComponent` widget (`shared/.../widgets/`) shows status dot, progress bar, EEG overlay, and Pause/Resume/Stop controls; lives inside the `.captures-section` card on `/dashboard`. `eeg_ticks` table has **no `t` or `created_at` column** — never add `.order()` to `fetchEegTicks`. **Robot sim (v2.5):** `~/handwerk-robot-sim` (separate git repo) runs H1 humanoid with mink differential IK — right arm traces a boustrophedon wall-plane grid (20 waypoints), speed EEG-modulated. Run: `mjpython sim/ws_server.py --model h1`. Spec + plan in `docs/superpowers/`.

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
