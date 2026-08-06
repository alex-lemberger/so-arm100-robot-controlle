# Review: `EngagementSource` Implementation Plan (V2)

Review of [`engagement_source_plan.md`](engagement_source_plan.md) as it stands now, verified against the code and against the V2 spec ([`../specs/engagement_source_spec.md`](../specs/engagement_source_spec.md)). Companion to [`../specs/engagement_source_review_v2.md`](../specs/engagement_source_review_v2.md), which covers the spec.

**Date:** 2026-06-09
**Verdict:** Sound, sequenced, buildable. The plan was revised alongside the spec and absorbed the major fixes. One real bug (a path inconsistency) and four refinements/gaps remain — none are blockers. Grade: **B+**.

---

## Resolved since V1 (credit)
| V1 issue | V2 fix | Where |
|---|---|---|
| `IEngagementSource`, snake_case paths | `EngagementSource`, `core/engagement/engagement-source.ts` | plan Phase 1 |
| `useMockData` overload | dedicated `engagementTier` flag | plan Phase 4 |
| `LearningSessionService` omitted | added as a stream consumer for persistence | plan Phase 3 |
| Tests hedged "if possible" | pure-fn extraction + unit tests as explicit steps | plan Phase 2, 5 |
| Provenance ignored | `DashboardService` handles proxy vs biometric | plan Phase 3 |

---

## Remaining issues

### 1. Path inconsistency for the metrics model (real bug)
Phase 1 places `UserActivityMetrics` in `src/app/core/models/engagement-metrics.model.ts`, but the next line and spec §3 place all models under `src/app/core/engagement/`. Two directories for one feature. **Fix:** use `core/engagement/engagement-metrics.model.ts` everywhere.

### 2. `CaptureState` injection target is unjustified
Phase 3 lists "Update `CaptureState` to inject `EngagementSource`." The capture module records skill data (EEG + IMU + video), not Q&A exercises, so it produces no `latency`/`error` interaction stream to feed the Standard tier. The real stream consumer is `LearningSessionService` (verified: it subscribes to both streams at [`src/app/core/neurofeedback/services/learning-session.service.ts:62`](../src/app/core/neurofeedback/services/learning-session.service.ts) and `:69`). **Fix:** justify what `CaptureState` would feed/consume, or drop it from scope.

### 3. `ExerciseState` step should state its purpose
Phase 3 says "Update `ExerciseState` to inject `EngagementSource`." Verified: `ExerciseState` injects only `Router` + three exercise sources today (`src/app/modules/language-learning/state/exercise.state.ts:92`), and does **not** read `focus$`/`calm$`. So the injection's purpose is the **input** side — to call `recordInteraction()` with response/error events — not to consume focus. **Fix:** label it as event production, so nobody wires it to the wrong streams.

### 4. Missing step: wire interaction events into `recordInteraction()`
The V2 spec added `recordInteraction(event)` as the Standard tier's input feed, but the plan never has a step connecting the exercise interaction layer (where latency/correctness originate) to that method. Without it the Standard provider has no data. **Fix:** add an explicit Phase 3 step wiring exercise events → `recordInteraction()`.

### 5. Missing phase: define Standard-tier persistence
Spec §5 defers "define a persistence strategy for `UserActivityMetrics`," but the plan has no phase for it. `eeg_ticks` is EEG-only, so Standard-tier metrics have no home. **Fix:** add a phase naming the Supabase table/column, or explicitly state "not persisted in Phase 1."

---

## Cross-check with `brain-device.ts` (contract reminder)
The premium provider wraps `BrainDevice`, whose `focus$`/`calm$` are `Observable<number | null>` and emit `null` until data (`src/app/core/neurofeedback/brain-device.ts:27` and `:29`). Phase 2's mapping must preserve that nullability — see spec review_v2 issue #1, where the spec types `focus$` as non-null.

## Bottom line
Fix #1 (path) and #4 (input wiring) before execution — they are concrete and cheap. #2, #3, #5 are decisions to record in the plan. No blockers; the phase ordering is correct.
