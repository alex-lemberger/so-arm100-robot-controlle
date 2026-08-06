# Review: `IEngagementSource` Spec & Plan

Review of [`specs/engagement_source_spec.md`](engagement_source_spec.md) and [`plans/engagement_source_plan.md`](../plans/engagement_source_plan.md).

**Date:** 2026-06-09
**Verdict:** Direction correct (decouple engagement from hardware). Not yet buildable as written. Three blockers + one conceptual flag + convention nits. Fix blockers #1 and #2 before coding — they change the interface shape.

---

## Critical issues

### 1. Circular dependency — input feed is missing (BLOCKER)
`InteractionEngagementSource` needs `latencyMs` / `errorRate` as **input** to compute focus. But the interface only exposes `getInteractionMetrics()` as **output**. No ingest path is defined for raw interaction events.

- Data actually flows **Exercise → Source** (ExerciseState owns prompt time, answers, errors).
- Spec wires **Source → Exercise** only.
- **Fix:** add an input channel — e.g. `recordInteraction(event)` on the source, or a separate `InteractionTracker` that the source consumes. Decide before coding; it changes the interface.

### 2. Tautology risk — corrupts the dashboard's purpose (BLOCKER)
The dashboard correlates focus vs learning progress (error rate). The Standard tier *derives* focus *from* error rate. Correlating error-rate-derived-focus against error-rate is guaranteed and meaningless.

- EEG focus = independent signal. Proxy focus = not independent.
- If both feed the same widget identically, Standard-tier correlation charts become circular.
- **Fix:** tag engagement provenance (EEG vs proxy). Exclude proxy from the learning-correlation viz, or label it clearly as a heuristic distinct from biometric focus.

### 3. `useMockData` overload (BLOCKER — plan Phase 4)
Plan suggests toggling tier via `useMockData` "or custom flag." Do not touch `useMockData`.

- Per CLAUDE.md it's the central switch read in 3 places (mock-vs-real *data*).
- Tier (Standard vs Premium) is orthogonal to mock-vs-real.
- Precedent: `CaptureModeService.isMock` is kept separate from `useMockData`. Mirror it.
- **Fix:** add a dedicated `engagementTier` flag. Overloading the central switch adds a hidden 4th meaning = future bug.

---

## Conceptual flag

### Calm proxy is dubious
Focus-from-latency/error is defensible. Calm-from-interaction is not — no credible software signal maps to relaxation.

- **Fix:** Standard tier exposes focus (+ maybe generic "engagement") and returns calm as `null`/unavailable, not a fabricated number. Honest gap beats pseudoscience.

---

## Spec nits

- **Method vs property mismatch.** Spec: `getFocusScore(): Observable<number>`. Existing `BrainDevice` exposes `focus$` / `calm$` as observable *properties*; consumers do `toSignal(BrainDevice.focus$)`. Match that (`focus$: Observable<number>`) or you refactor every call site for nothing.
- **Range — verified OK.** Spec says 0.0–1.0. Confirmed against code: `BrainDevice.focus$`/`calm$` are typed `Observable<number | null>` and emit 0–1 (the mock's internal 0–100 is divided by 100 before emit). Spec matches the existing contract; no adapter needed. Keep the `| null` (streams are null until data arrives).
- **Proxy formula undefined.** "high latency + high error = low focus" is hand-wave. Define normalization: what `latencyMs` = 0.0 focus vs 1.0? What's the `errorRate` domain? Otherwise two devs build two different scores.
- **Typos:** `caputreState` → `CaptureState`; "at a runtime" → "at runtime".
- **`I` prefix.** `IEngagementSource` — Hungarian prefix not idiomatic Angular/TS; repo uses `BrainDevice` (no prefix). Drop to `EngagementSource`.
- **Placement.** Spec puts the interface in `core/neurofeedback/`. Standard tier is software-only — nesting it under `neurofeedback/` re-couples to the thing being decoupled. Use `core/engagement/`.

## Plan nits

- **Interface ≠ DI token.** Plan says "abstract class or interface." TS interfaces don't exist at runtime → can't inject. Must be an abstract class or `InjectionToken`. Decide; follow whatever `BrainDevice` does.
- **File naming is snake_case.** `engagement_source.interface.ts`, `engagement_metrics.model.ts` — repo is kebab-case (`capture.state.ts`, `neurosity.service.ts`). → `engagement-source.ts`, `engagement-metrics.model.ts`.
- **Missing consumer: `LearningSessionService`.** It subscribes to `focus$` / `calm$` and persists per-tick metrics to Supabase — a direct consumer of the streams being abstracted. Add it to refactor scope.
- **Persistence unaddressed.** Where do `UserActivityMetrics` go? `eeg_ticks` serves Premium. Standard tier needs its own table/column or an explicit "not persisted." State it.
- **Tests too weak.** Phase 5 "(if possible) add unit tests." The proxy formula is a *pure function* — no `@neurosity/sdk` import, so the broken Karma `parcelRequire` issue doesn't block it. Extract proxy math to a pure fn + spec it. That's exactly the part that needs tests; don't hedge it.
- **DashboardService item vague.** "remains compatible or is updated" — pick one. Does the dashboard read engagement via the new interface or stay direct?
- **No inter-phase checkpoints.** Only a final `ng build`. Add a verify step after Phase 3 (the highest-risk refactor phase).

---

## Bottom line
1. Resolve input feed (#1) and tautology (#2) first — they reshape the interface.
2. Decide tier flag (#3) and calm-proxy handling — quick calls.
3. Rest is cleanup (naming, DI token, tests, persistence, missing consumer).
