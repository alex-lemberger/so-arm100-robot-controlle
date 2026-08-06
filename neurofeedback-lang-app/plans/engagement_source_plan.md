# Implementation Plan: `EngagementSource` Abstraction (granular)

Companion spec: [`../specs/engagement_source_spec.md`](../specs/engagement_source_spec.md).
Standard-tier focus signal is **interaction cadence** (timing), not errorRate — the app has no correctness scoring today.

## How to execute — read first
- Do **one** numbered task at a time, in order. Do not batch tasks.
- After **every** task, run `ng build --configuration development`. It must pass before you start the next task. If it fails, fix it before moving on.
- `ng test` is broken repo-wide (`parcelRequire`, see AGENTS.md). Author `.spec.ts` files as deliverables, but verify by build + reading — do **not** rely on a Karma run.
- Before using any `BrainDevice` member, confirm its shape in `src/app/core/neurofeedback/brain-device.ts`. Do not invent APIs.
- New engagement code lives in `src/app/core/engagement/`.

---

## Phase 1 — Models & contract

- [ ] **1.1** Create `src/app/core/engagement/engagement-metrics.model.ts`.
  - Do: `export interface UserActivityMetrics { latencyMs: number; errorRate: number; sessionCadence: number; isProxy: boolean; }` and `export interface UserInteractionEvent { type: 'response' | 'error'; timestamp: number; payload?: Record<string, unknown>; }`.
  - Done when: `ng build` passes.

- [ ] **1.2** Create `src/app/core/engagement/engagement-source.ts`.
  - Do: `export abstract class EngagementSource` with `abstract readonly focus$: Observable<number | null>;`, `abstract readonly calm$: Observable<number | null>;`, `abstract getInteractionMetrics(): Observable<UserActivityMetrics>;`, `abstract recordInteraction(event: UserInteractionEvent): void;`. Import `Observable` from `rxjs` and the models from 1.1.
  - Done when: `ng build` passes.

## Phase 2 — Cadence focus function (pure, test-first)

- [ ] **2.1** Create `src/app/core/engagement/focus-from-cadence.ts`.
  - Do: `export const IDEAL_MS = 8000;` `export const MAX_MS = 60000;` `export function focusFromCadence(gapMs: number): number { if (gapMs <= IDEAL_MS) return 1; if (gapMs >= MAX_MS) return 0; return 1 - (gapMs - IDEAL_MS) / (MAX_MS - IDEAL_MS); }`
  - Done when: `ng build` passes.

- [ ] **2.2** Create `src/app/core/engagement/focus-from-cadence.spec.ts`.
  - Do: cases — `gap=0 → 1`, `gap=IDEAL_MS → 1`, `gap=MAX_MS → 0`, `gap>MAX_MS → 0`, `gap=34000 (midpoint) → ~0.5`.
  - Done when: `ng build` passes; 5 cases present. (Do not run Karma.)

## Phase 3 — Standard provider

- [ ] **3.1** Create `src/app/core/engagement/interaction-engagement-source.ts`.
  - Do: `@Injectable()` `export class InteractionEngagementSource extends EngagementSource`. Hold `private lastTs: number | null = null;` and `private readonly _focus$ = new BehaviorSubject<number | null>(null);`. `focus$ = this._focus$.asObservable();`. `calm$ = of(null);`. `recordInteraction(e)`: if `lastTs !== null`, compute `gap = e.timestamp - lastTs` and `this._focus$.next(focusFromCadence(gap))`; then `this.lastTs = e.timestamp;`. `getInteractionMetrics()`: return a `BehaviorSubject<UserActivityMetrics>` (or `of(...)`) with `isProxy: true` and the latest `sessionCadence`.
  - Done when: `ng build` passes.

- [ ] **3.2** Create `src/app/core/engagement/interaction-engagement-source.spec.ts`.
  - Do: two `recordInteraction` calls ~2s apart → `focus$` emits `1` (prompt); calls ~50s apart → `focus$` emits a low value; `calm$` emits `null`.
  - Done when: `ng build` passes; cases present.

## Phase 4 — Premium provider

- [ ] **4.1** Create `src/app/core/engagement/eeg-engagement-source.ts`.
  - Do: `@Injectable()` `export class EEGEngagementSource extends EngagementSource`. `constructor(private device: BrainDevice) { super(); }`. `focus$ = this.device.focus$;` `calm$ = this.device.calm$;` `recordInteraction(): void {}` (no-op). `getInteractionMetrics()`: return `EMPTY` (from `rxjs`).
  - Done when: `ng build` passes.

## Phase 5 — DI wiring

- [ ] **5.1** Edit `src/app/environments/environment.ts`: add `engagementTier: 'standard' as 'standard' | 'premium',`.
  - Done when: `ng build` passes.

- [ ] **5.2** Edit `src/main.ts`: provide `EngagementSource` via a factory that returns `InteractionEngagementSource` when `environment.engagementTier === 'standard'`, else `EEGEngagementSource`. Use `{ provide: EngagementSource, useClass: ... }` selected by the flag (or a `useFactory`). Keep the existing `BrainDevice`/`NeurosityService` mock override.
  - Done when: `ng build` passes **and** `npm start` boots with no console DI error.

## Phase 6 — Integration (one file per task; highest risk)

- [ ] **6.1** Edit `src/app/core/neurofeedback/services/learning-session.service.ts`: change the injected type from `BrainDevice` to `EngagementSource` (constructor param + import). It only uses `focus$`/`calm$`, which `EngagementSource` provides — no other change.
  - Done when: `ng build` passes.

- [ ] **6.2** Edit `src/app/modules/language-learning/state/exercise.state.ts`: inject `EngagementSource`. In the `NavigateToNext`, `NavigateToPrevious`, and `UpdateProgress` handlers, call `this.engagement.recordInteraction({ type: 'response', timestamp: Date.now() })`. Do **not** read `focus$` here.
  - Done when: `ng build` passes.

- [ ] **6.3** Edit `src/app/dashboard/services/dashboard.service.ts` (and/or the dashboard widget): surface the `isProxy` flag so proxy engagement is visually distinguished from biometric. Display only — no metric recalculation.
  - Done when: `ng build` passes.

## Phase 7 — Final verification

- [ ] **7.1** `ng build --configuration development` → green.
- [ ] **7.2** `npm start` → app boots, no DI/console errors. Open an exercise, click Next a few times, confirm no crash.

## Out of scope (Phase 1)
- Persisting `UserActivityMetrics` (in-memory only; `interaction_metrics` table deferred).
- `errorRate` / `latencyMs` in the focus formula (cadence only until a scored exercise exists).
