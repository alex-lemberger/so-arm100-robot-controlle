# Signal-Only Migration Analysis

## Current Architecture Overview

Analysis of feasibility for migrating from NGXS + Observables to a signal-only approach.

### Current State Management

Three NGXS stores:

- **ExerciseState** (`modules/language-learning/state/exercise.state.ts`) — language learning exercises, action handlers return RxJS streams with `tap`/`catchError`
- **CaptureState** (`modules/capture/state/capture.state.ts`) — skill capture sessions; `status` field drives a hardware-gated sequential wizard (state machine)
- **DashboardState** — dashboard data aggregation; provided at feature level, not globally

### Data Flow Architecture

1. Components inject `Store` and consume state via `toSignal(this.store.select(...))`
2. Data sources:
   - Exercise sources (WordPress REST, mock) via `ExerciseSource` strategy interface
   - Brain devices (Neurosity, Muse) via `BrainDevice` abstract class → `focus$`/`calm$` Observables
   - Interaction cadence proxy via `EngagementSource` (standard tier, no headset required)
3. `LearningSessionService` subscribes to brain streams and persists EEG ticks to Supabase
4. `DashboardService` aggregates data for visualisation components
5. `SimBridgeService` holds all WebSocket + replay state in a single `_snap` signal (already fully signal-based)

### Key Services and Dependencies

- **`BrainDevice`** abstract class — exposes `focus$`/`calm$` as `BehaviorSubject` (hardware/WebSocket streams; Observable boundary stays)
- **`EngagementSource`** interface — wraps brain device or generates proxy metrics
- **Exercise source strategy**: `WpExerciseSourceService`, `MockExerciseService`, base `ExerciseService`
- **`CaptureSessionService`** — orchestrates EEG + IMU + video streams during capture
- **`CaptureHistoryService`** — single source of truth for session history (Supabase in real mode, addMockSession in mock mode)
- `FirestoreService` is deleted — all persistence goes through `SupabaseClientService`

---

## Migration Considerations

### What Would Change

**Replacing NGXS stores with service-level signals:**

1. **Remove NGXS decorators**: `@State`, `@Action`, `@Selector` all gone; replace with `signal()` + `computed()` inside plain services
2. **Component consumption**: Replace `toSignal(this.store.select(...))` with direct signal access from injected services; remove `inject(Store)` from components
3. **Side-effect orchestration**: NGXS action handlers are RxJS streams (`tap` to commit, `catchError` → `handleError`). In a signal-only approach these become `effect()` calls or explicit Promise chains — no equivalent of action piping built-in
4. **Derived state**: Replace `@Selector` with `computed()` signals inside services

### What Would Stay the Same

1. **`BrainDevice` / `EngagementSource` abstractions** — unchanged; `focus$`/`calm$` remain Observables (streaming hardware data); `toSignal()` stays at that boundary
2. **Data formats** — same ranges (0–1), same nullability, same Supabase schema
3. **Standalone component architecture** — components continue to be signal-first consumers
4. **Mock/real switch** — `environment.ts` `useMockData` + `CaptureModeService.isMock` patterns unchanged
5. **Strategy pattern for exercise sources** — interface implementations unaffected
6. **`SimBridgeService`** — already fully signal-based (`_snap` signal); no migration needed

### Hard Migration Targets

**`CaptureState` is a state machine.** The `status` field cycles through hardware-gated wizard steps (`@switch` in `CaptureShellComponent`). NGXS actions are a natural fit for state-machine transitions with guarded side effects (hardware checks, upload flows). Replicating this with `signal()` + `computed()` requires manually implementing transition guards and async side-effect sequencing — no built-in equivalent.

**Upload and replay side-effect flows.** `CaptureSessionService.stopSession()` triggers a multi-step async chain (EEG flush → video upload → Supabase insert → history update). NGXS action pipelines handle cancellation, error routing, and chaining cleanly. Replacing with `effect()` or Promise chains loses that structure.

**`BrainDevice` streams don't migrate.** `focus$`/`calm$` are perpetual WebSocket/BLE streams. They become signals via `toSignal()` at the component or service boundary — they cannot become native signals at source. Any "signal-only" approach still has this Observable seam.

---

## Recommendation: Keep the Hybrid — No Full Migration

The app is already in an optimal hybrid state:

- **NGXS** for the two stateful, side-effect-heavy stores (`ExerciseState`, `CaptureState`)
- **`toSignal()`** at consumption edges so components get signal semantics without touching NGXS internals
- **Pure signals** where state is simple and local (`SimBridgeService._snap`, dashboard widget inputs, `CaptureModeService.isMock`)
- **`DashboardState`** is a candidate for extraction to a plain signal service if it grows complex, but no urgency

A full NGXS → signal migration would:
- Cost several weeks of refactoring with no user-visible gain
- Require manually reimplementing state-machine semantics for `CaptureState`
- Gain nothing on performance (NGXS with `toSignal()` at edges already avoids unnecessary re-renders)

**Preferred path:** Continue the hybrid. New features write signal-first services and use `toSignal()` only at Observable boundaries. Migrate a store opportunistically only if fundamentally reworking it anyway.
