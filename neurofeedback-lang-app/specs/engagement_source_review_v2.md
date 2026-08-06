# Review: `EngagementSource` Spec — Revision 2

Clean re-review of [`engagement_source_spec.md`](engagement_source_spec.md) as it stands now (V2), verified line-by-line against the source. Supersedes the V1 critique in [`engagement_source_review.md`](engagement_source_review.md), which reviewed an earlier draft.

**Date:** 2026-06-09
**Verdict:** Buildable. V2 resolved all three V1 blockers and every convention nit. Remaining items are refinements, not blockers. Grade: **B+ / A−**.

---

## Resolved since V1 (credit)
| V1 blocker / nit | V2 fix | Evidence |
|---|---|---|
| Missing input feed (circular dep) | `recordInteraction(event)` + `UserInteractionEvent` model | spec §2 l.16, §3 l.26 |
| Tautology in dashboard correlation | `isProxy` flag; dashboard must distinguish | §3 l.24, §5 l.42 |
| `useMockData` overload | dedicated `engagementTier` flag via `InjectionToken` | §5 l.41 |
| `getFocusScore()` method | `focus$` observable property | §2 l.10 |
| Fabricated calm proxy | `calm: null` for Standard tier | §2 l.13, §4 l.37 |
| `I`-prefix / placement / snake_case | `EngagementSource`, `core/engagement/`, kebab-case | §1, §2 l.6 |
| Hand-waved formula | concrete pure function | §4 l.36 |

---

## Remaining issues (refinements)

### 1. `focus$` drops nullability — mismatches `BrainDevice` (concrete)
Spec §2 l.10 types `focus$: Observable<number>`, but `calm$` (l.13) is `Observable<number | null>`. Verified against `core/neurofeedback/brain-device.ts`: **both** `focus$` and `calm$` are `Observable<number | null>` and emit `null` until data arrives. `EEGEngagementSource` wraps `BrainDevice`, so its `focus$` *will* emit `null` at startup. **Fix:** make `focus$: Observable<number | null>` for consistency and to preserve the null-until-data contract.

### 2. Formula ignores fields the model defines
§4 l.36 computes focus from `errorRate` only: `Focus = 1.0 - clamp(errorRate, 0, 1)`. But `UserActivityMetrics` defines `latencyMs` and `sessionCadence` (§3 l.21, 23) that go unused. Either fold them into the formula or drop them from the model — don't define inputs you ignore.

### 3. `CaptureState` as an injection target is still questionable
§5 l.40 refactors `ExerciseState`, `CaptureState`, and `LearningSessionService` to inject `EngagementSource`.
- `LearningSessionService` — correct; it's the real `focus$`/`calm$` consumer.
- `ExerciseState` — now defensible: the exercise layer produces interaction events and would call `recordInteraction()`. Clarify it injects to **feed** events, not to read `focus$`.
- `CaptureState` — weak. The capture module records skill data (EEG + IMU + video), not Q&A exercises, so it has no `latency`/`error` interaction stream to feed. Justify or drop it.

### 4. Premium-tier behaviour for the interaction methods is undefined
The interface forces `EEGEngagementSource` (Premium) to implement `recordInteraction()` and `getInteractionMetrics()`. Define their Premium behaviour: no-op ingest? `getInteractionMetrics` emitting `isProxy: false` records, or nothing? Unspecified contract = inconsistent implementations.

### 5. Persistence still deferred
§5 l.43 says "define a persistence strategy for `UserActivityMetrics`." Acknowledged but unspecified. Name the table/column (Standard tier has no home — `eeg_ticks` is EEG-only) before implementation, or state explicitly "not persisted in Phase 1."

### 6. Adapter caveat is unnecessary for the current source (minor)
§2 l.11/13 tells implementers to adapt "if the upstream source uses 0–100." Verified: `BrainDevice` already emits 0–1, so for the only real source today this is a no-op caveat. Harmless but slightly misleading — keep it as defensive guidance for future sources, not a current requirement.

---

## Bottom line
V2 is a strong, implementable spec. No blockers. Address #1 (nullability) and #2 (formula) before coding — they are cheap and concrete; #3–#5 are decisions to record; #6 is cosmetic.
