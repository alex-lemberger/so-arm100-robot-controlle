# Specification: `EngagementSource` Abstraction

## 1. Purpose
To decouple the application's core engagement logic from specific hardware drivers (like Neurosity). This enables a "Standard Tier" (software-only interaction metrics) and a "Premium Tier" (EEG/biometric signals) using a unified interface, enabling sensor-agnostic architecture.

## 2. Interface Definition (`core/engagement/engagement-source.ts`)
The abstract class provides observable streams of engagement data and an input channel to ingest interaction events.

### Core Properties/Methods:
*   **`focus$: Observable<number | null>`**
    *   Normalized 0.0–1.0, or `null` until the first reading arrives. Mirrors `BrainDevice`, whose streams are `number | null`. `BrainDevice` already emits 0–1; an adapter is only needed for a future source on a different scale.
*   **`calm$: Observable<number | null>`**
    *   Normalized 0.0–1.0, or `null` when the tier has no biometric calm signal (e.g., Standard) or until data arrives.
*   **`getInteractionMetrics(): Observable<UserActivityMetrics>`**
    *   Returns an observable containing time-series interaction data.
*   **`recordInteraction(event: UserInteractionEvent): void`**
    *   Ingests raw interaction events (e.g., response latency, correctness) to update internal proxy metrics.

## 3. Data Models
### `UserActivityMetrics` (in `core/engagement/engagement-metrics.model.ts`)
*   **`latencyMs: number`**: Time elapsed between prompt and response.
*   **`errorRate: number`**: Frequency of incorrect answers in the current window.
*   **`sessionCadence: number`**: Average time between consecutive interactions.
*   **`isProxy: boolean`**: `true` if metrics are derived from software interaction, `false` for biometric data.

### `UserInteractionEvent`
*   **`type: 'response' | 'error'`**
*   **`timestamp: number`**
*   **`payload?: Record<string, any>`**

## 4. Implementation Strategy
1.  **`EEGEngagementSource` (Premium):**
    *   Wraps `BrainDevice` streams; maps `focus$` and `calm$` directly, preserving `number | null`.
    *   `recordInteraction()` is a no-op (focus/calm come from biometrics). `getInteractionMetrics()` emits an empty stream — interaction proxying is a Standard-tier concern.
2.  **`InteractionEngagementSource` (Standard):**
    *   `recordInteraction(event)` records the event timestamp and computes `gapMs` = time since the previous interaction.
    *   Focus via a pure function of interaction cadence — `focusFromCadence(gapMs)`: `1.0` when interactions are prompt/steady (`gapMs ≤ IDEAL_MS`), `0.0` when stalled (`gapMs ≥ MAX_MS`), linear between. Phase 1 constants: `IDEAL_MS = 8000`, `MAX_MS = 60000` (tunable).
    *   `errorRate` is captured in `UserActivityMetrics` for a future scored-exercise tier but is **not** an input in Phase 1 — no exercise type produces correctness today (only `speaking-exercise`, which is ungraded).
    *   Emits `calm$: null` (no biometric signal).

## 5. Integration Requirements
*   **State Consumption:**
    *   `LearningSessionService` consumes `focus$`/`calm$` for persistence — it is the existing stream consumer.
    *   `ExerciseState` injects `EngagementSource` only to **feed** `recordInteraction()` on user-interaction actions that already flow through it (`NavigateToNext`, `NavigateToPrevious`, `UpdateProgress`), supplying the cadence signal; it does not read `focus$`.
    *   `CaptureState` is out of scope — the capture module produces no Q&A interaction stream.
*   **Dependency Injection:** Use a dedicated `engagementTier` flag ('premium' | 'standard') via an `InjectionToken` in `main.ts`.
*   **Data Provenance:** Dashboard widgets must use the `isProxy` flag to distinguish between biometric and heuristic signals, preventing tautological correlation.
*   **Persistence:** Phase 1 keeps `UserActivityMetrics` in-memory only (not persisted) — `eeg_ticks` is EEG-only. A dedicated `interaction_metrics` table is deferred to a later phase.
