# Flow Detection — Design Spec

_Date: 2026-06-04 · Status: approved (design), pending implementation plan_

## Goal

Detect "flow state" live during a learning session from the EEG focus/calm
streams and surface it in the dashboard live band: an **In Flow** badge plus a
running **% of session spent in flow**. Real-time only — no history or
persistence in this iteration.

## Background & constraints

- `BrainDevice` contract (`core/neurofeedback/brain-device.ts`): `focus$` and
  `calm$` are `Observable<number | null>`, **0–1**, null until data arrives.
- Real `NeurosityService` emits `focus.probability` / `calm.probability` (0–1) ✓.
- Streams tick at **1 Hz** under the mock (`mockUpdateInterval = 1000`).
- The mock is the DI default (`main.ts` overrides `BrainDevice`/`NeurosityService`
  with `MockNeurosityService`), independent of `useMockData`.

### Pre-existing bug to fix (in scope)

`MockNeurosityService.generateRealisticValue` clamps to `0..100` and emits
~0–100 (`mock-neurosity.service.ts:60-62`), **violating the 0–1 `BrainDevice`
contract**. Consequences:
- The dashboard live-band rings (shipped earlier) render e.g. `70.00` / `7000%`.
- Flow thresholds are meaningless until the scale is consistent.

**Fix:** emit 0–1 from the mock (divide the generated value by 100, keep one
internal 0–100 model or rescale baselines). This also corrects the rings. Verify
the rings read `0.00–1.00` afterward.

## Architecture

Standalone, single-purpose **`FlowDetectorService`** (chosen over inlining in
`DashboardComponent` or extending `LearningSessionService` — keeps detection
reusable, isolated, and unit-testable without importing `@neurosity/sdk`, which
sidesteps the broken Karma/SDK spec setup).

```
BrainDevice.focus$ ┐
                   ├─► FlowDetectorService ──► inFlow$ (boolean)
BrainDevice.calm$  ┘        (smooth → classify)        │
                                                       │
DashboardComponent (live band) ◄────── toSignal ───────┘
   owns session timer → accumulates flowSeconds → Flow NN%
```

- **`FlowDetectorService`** — `@Injectable()`, injects `BrainDevice`. Pure
  stream transform; no UI, no Firestore, no session lifecycle. Exposes:
  - `inFlow$: Observable<boolean>` — current flow classification (the only
    public output for v1).
- **`FlowConfig`** — interface + `DEFAULT_FLOW_CONFIG` constant holding all
  tunable numbers, provided via DI token so tests/consumers can override.
- **`DashboardComponent`** — consumes `inFlow$` via `toSignal`; accumulates the
  running fraction against its existing per-second timer.

## Detector algorithm

Per emission of `combineLatest([focus$, calm$])`:

1. **Null gate.** If either value is `null`, output `inFlow = false` and reset
   the dwell counter. (No data ⇒ not in flow.)
2. **Smooth.** EMA per signal: `s = α·x + (1−α)·sPrev`, `α = 0.3`
   (≈ 3 s settling @ 1 Hz). Seed `sPrev` with the first non-null value.
3. **Classify with hysteresis + dwell.** Let `f = focusSm`, `c = calmSm`.
   - **Enter condition:** `f ≥ enterFocus` AND `enterCalmLo ≤ c ≤ enterCalmHi`.
     When the enter condition has held continuously for `dwellSeconds`, set
     `inFlow = true` (rising-edge debounce). Track dwell as accumulated time
     between emissions, not tick count, so it's robust to rate changes.
   - **Exit condition (only when `inFlow`):** `f < exitFocus` OR
     `c < exitCalmLo` OR `c > exitCalmHi`. On exit, set `inFlow = false`
     immediately and reset dwell. Exit thresholds are looser than enter
     thresholds (hysteresis band) to prevent flicker on brief dips.

Emit `inFlow$` only on change (`distinctUntilChanged`).

### Default config (`DEFAULT_FLOW_CONFIG`)

| Param          | Value      | Meaning                                  |
|----------------|------------|------------------------------------------|
| `alpha`        | `0.3`      | EMA smoothing factor                     |
| `enterFocus`   | `0.70`     | min smoothed focus to enter              |
| `exitFocus`    | `0.62`     | drop below ⇒ exit (hysteresis)           |
| `enterCalmLo`  | `0.45`     | calm sweet-spot lower bound (enter)      |
| `enterCalmHi`  | `0.85`     | calm sweet-spot upper bound (enter)      |
| `exitCalmLo`   | `0.40`     | calm lower exit bound (hysteresis)       |
| `exitCalmHi`   | `0.90`     | calm upper exit bound (hysteresis)       |
| `dwellSeconds` | `5`        | enter condition hold time before flow    |

Rationale: flow = sustained high focus within an arousal sweet spot (not too
calm/drowsy, not too agitated). Hysteresis + dwell trade a few seconds of
latency for a stable, non-flickering signal.

## Dashboard UI (live band)

- `inFlow = toSignal(flowDetector.inFlow$, { initialValue: false })`.
- **Badge** in the band: `In Flow` (teal `--c-teal`, soft pulse animation) when
  `inFlow()`; `Building…` (muted) when session active but not in flow; hidden
  when no session. `aria-live="polite"` on the badge so transitions announce;
  always carry a text label (never colour-only). Respect
  `prefers-reduced-motion` for the pulse.
- **Running %**: `flowSeconds` signal incremented each second when
  `sessionActive() && inFlow()`, alongside the existing `elapsed` timer.
  `flowPercent = elapsed ? round(100 · flowSeconds / elapsed) : 0`. Reset
  `flowSeconds` to 0 in `startSession()`. Display as `Flow NN%`.

## Testing

- **`FlowDetectorService` unit tests** with synthetic streams
  (`BehaviorSubject` or marbles) — no `@neurosity/sdk` import, so they run under
  the current Karma setup. Cases:
  - Enters flow only after `dwellSeconds` of sustained enter condition.
  - Does **not** flicker on a brief sub-`enterFocus` dip that stays above
    `exitFocus` (hysteresis holds).
  - Exits on a true drop below `exitFocus` or calm leaving the exit band.
  - `null` emission forces `inFlow = false` and resets dwell.
  - Override `FlowConfig` (e.g. `dwellSeconds = 0`) changes behavior.
- Manual: run with mock device, confirm badge + % behave and rings read 0–1.

## Out of scope (future)

- Signal-quality gating (mock exposes none; real device `extras$` may).
- Persisting per-session flow summary + Sessions/history view.
- Baseline-relative (z-score) normalization for per-person variance.

## Files (anticipated)

- **New:** `core/neurofeedback/services/flow-detector.service.ts`,
  `flow-detector.service.spec.ts`, `core/neurofeedback/models/flow-config.ts`.
- **Modified:** `mock-neurosity.service.ts` (0–1 fix),
  `shared/components/layout/dashboard-layout/dashboard.component.{ts,html,scss}`
  (badge + %).
