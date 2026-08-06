# Cognitive-State Capture Labels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label every capture session with per-tick `load`, `fatigue`, and `signal_ok` derived from the Muse EEG band powers, persisted to `eeg_ticks`.

**Architecture:** Pure metric functions (`cognitive-metrics.ts`) + a thin streaming service (`CognitiveStateService`, mirrors `FlowDetectorService`) consuming `BrainDevice.extras$` (already emits normalized theta/alpha/beta at ~4 Hz). `CaptureSessionService` reads the service's outputs into the existing per-tick write; `eeg_ticks` gains three nullable columns.

**Tech Stack:** Angular 19, RxJS, NGXS-adjacent service pattern, Supabase (PostgreSQL).

**Verification reality:** `ng test` (Karma) is broken repo-wide (`@neurosity/sdk` parcelRequire). Pure logic is verified via a `node` replication + `npx tsc -p tsconfig.spec.json --noEmit`; integration via `ng build --configuration development` and a runtime check. Never claim a Karma pass (AGENTS Principle #13).

---

## File structure

- **Create** `src/app/core/neurofeedback/cognitive-metrics.ts` — pure metrics + `stepCognitive` reducer + state type. No Angular/SDK imports.
- **Create** `src/app/core/neurofeedback/cognitive-metrics.spec.ts` — Jasmine specs (deliverable; logic also verified via node).
- **Create** `src/app/core/neurofeedback/services/cognitive-state.service.ts` — streaming glue over `extras$`.
- **Create** `supabase/migrations/20260609_eeg_ticks_cognitive.sql` — additive nullable columns.
- **Modify** `src/app/modules/capture/models/capture-session.model.ts` — extend `EegTick`.
- **Modify** `src/app/modules/capture/services/supabase-capture.service.ts` — extend `writeEegTick`.
- **Modify** `src/app/modules/capture/services/capture-session.service.ts` — inject service, session hooks, extend tick write.

---

## Task 1: Pure cognitive-metrics module

**Files:**
- Create: `src/app/core/neurofeedback/cognitive-metrics.ts`
- Test: `src/app/core/neurofeedback/cognitive-metrics.spec.ts`

- [ ] **Step 1: Write the implementation**

`src/app/core/neurofeedback/cognitive-metrics.ts`:
```ts
/** Cognitive-state metrics from normalized EEG band powers (theta/alpha/beta as fractions). Heuristic, relative. */

export const BASELINE_MS = 30_000;  // fatigue baseline = mean index over first 30s of a session
export const FATIGUE_SPAN = 1.0;    // index doubling vs baseline => fatigue ~1.0

export interface Bands { theta: number; alpha: number; beta: number; }

export interface CognitiveState {
  baselineSum: number;
  baselineCount: number;
  baseline: number | null;   // frozen once the baseline window closes
  load: number | null;
  fatigue: number | null;
  signalOk: boolean;
}

export function initialCognitiveState(): CognitiveState {
  return { baselineSum: 0, baselineCount: 0, baseline: null, load: null, fatigue: null, signalOk: false };
}

/** Load: theta share of slow-band power, 0..1. null if theta+alpha == 0. */
export function loadFromBands(theta: number, alpha: number): number | null {
  const denom = theta + alpha;
  if (!(denom > 0)) return null;
  return theta / denom;
}

/** Fatigue index (theta+alpha)/beta. null if beta == 0. */
export function fatigueIndex(theta: number, alpha: number, beta: number): number | null {
  if (!(beta > 0)) return null;
  return (theta + alpha) / beta;
}

/** Relative fatigue from index vs baseline, clamped 0..1. */
export function fatigueFromIndex(index: number, baseline: number): number {
  if (!(baseline > 0)) return 0;
  const rise = (index / baseline - 1) / FATIGUE_SPAN;
  return Math.min(1, Math.max(0, rise));
}

function finite(n: number | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n);
}

/**
 * Fold one band-power sample into cognitive state.
 * @param elapsedMs ms since session start; drives the baseline window.
 */
export function stepCognitive(state: CognitiveState, bands: Partial<Bands>, elapsedMs: number): CognitiveState {
  const { theta, alpha, beta } = bands;
  if (!finite(theta) || !finite(alpha) || !finite(beta)) {
    return { ...state, load: null, fatigue: null, signalOk: false };
  }
  const load = loadFromBands(theta, alpha);
  const index = fatigueIndex(theta, alpha, beta);
  if (index === null) {
    return { ...state, load, fatigue: null, signalOk: true };
  }
  if (elapsedMs < BASELINE_MS) {
    return {
      ...state,
      baselineSum: state.baselineSum + index,
      baselineCount: state.baselineCount + 1,
      baseline: null,
      load, fatigue: null, signalOk: true,
    };
  }
  const baseline = state.baseline
    ?? (state.baselineCount > 0 ? state.baselineSum / state.baselineCount : index);
  return { ...state, baseline, load, fatigue: fatigueFromIndex(index, baseline), signalOk: true };
}
```

- [ ] **Step 2: Write the spec**

`src/app/core/neurofeedback/cognitive-metrics.spec.ts`:
```ts
import {
  loadFromBands, fatigueIndex, fatigueFromIndex,
  stepCognitive, initialCognitiveState, BASELINE_MS,
} from './cognitive-metrics';

describe('cognitive-metrics', () => {
  it('loadFromBands returns theta share', () => expect(loadFromBands(0.6, 0.2)).toBeCloseTo(0.75, 5));
  it('loadFromBands null when theta+alpha is 0', () => expect(loadFromBands(0, 0)).toBeNull());

  it('fatigueIndex computes (theta+alpha)/beta', () => expect(fatigueIndex(0.3, 0.3, 0.4)).toBeCloseTo(1.5, 5));
  it('fatigueIndex null when beta is 0', () => expect(fatigueIndex(0.5, 0.5, 0)).toBeNull());

  it('fatigueFromIndex is 0 at baseline', () => expect(fatigueFromIndex(1.5, 1.5)).toBe(0));
  it('fatigueFromIndex ~1 when index doubles', () => expect(fatigueFromIndex(3.0, 1.5)).toBe(1));
  it('fatigueFromIndex clamps below 0', () => expect(fatigueFromIndex(0.5, 1.5)).toBe(0));

  it('stepCognitive: null fatigue during baseline window', () => {
    const s = stepCognitive(initialCognitiveState(), { theta: 0.3, alpha: 0.3, beta: 0.4 }, 0);
    expect(s.fatigue).toBeNull();
    expect(s.load).toBeCloseTo(0.5, 5);
    expect(s.baselineCount).toBe(1);
  });

  it('stepCognitive: freezes baseline and reports rising fatigue after window', () => {
    let s = initialCognitiveState();
    s = stepCognitive(s, { theta: 0.3, alpha: 0.3, beta: 0.4 }, 0);          // index 1.5 -> baseline
    s = stepCognitive(s, { theta: 0.3, alpha: 0.3, beta: 0.2 }, BASELINE_MS + 1); // index 3.0
    expect(s.baseline).toBeCloseTo(1.5, 5);
    expect(s.fatigue).toBe(1);
  });

  it('stepCognitive: signalOk false on non-finite bands', () => {
    const s = stepCognitive(initialCognitiveState(), { theta: NaN, alpha: 0.3, beta: 0.4 }, 0);
    expect(s.signalOk).toBe(false);
  });
});
```

- [ ] **Step 3: Verify the logic with node (Karma is broken)**

Run:
```bash
node -e '
const BASELINE_MS=30000, SPAN=1.0;
const load=(t,a)=>{const d=t+a; return d>0? t/d : null;};
const idx=(t,a,b)=> b>0? (t+a)/b : null;
const fat=(i,base)=> base>0? Math.min(1,Math.max(0,(i/base-1)/SPAN)) : 0;
const fin=n=>typeof n==="number"&&Number.isFinite(n);
function step(s,{theta,alpha,beta},ms){
  if(!fin(theta)||!fin(alpha)||!fin(beta)) return {...s,load:null,fatigue:null,signalOk:false};
  const l=load(theta,alpha), i=idx(theta,alpha,beta);
  if(i===null) return {...s,load:l,fatigue:null,signalOk:true};
  if(ms<BASELINE_MS) return {...s,baselineSum:s.baselineSum+i,baselineCount:s.baselineCount+1,baseline:null,load:l,fatigue:null,signalOk:true};
  const base=s.baseline ?? (s.baselineCount>0? s.baselineSum/s.baselineCount : i);
  return {...s,baseline:base,load:l,fatigue:fat(i,base),signalOk:true};
}
const init=()=>({baselineSum:0,baselineCount:0,baseline:null,load:null,fatigue:null,signalOk:false});
let p=0,f=0,t=(n,c)=>{(c?p++:f++);console.log((c?"PASS":"FAIL")+" "+n);};
t("load share", load(0.6,0.2)===0.75);
t("load null", load(0,0)===null);
t("idx", idx(0.3,0.3,0.4)===1.5);
t("fat 0", fat(1.5,1.5)===0);
t("fat 1", fat(3.0,1.5)===1);
let s=init(); s=step(s,{theta:0.3,alpha:0.3,beta:0.4},0); t("baseline tick null fatigue", s.fatigue===null&&s.baselineCount===1);
s=step(s,{theta:0.3,alpha:0.3,beta:0.2},BASELINE_MS+1); t("post-window fatigue", Math.abs(s.baseline-1.5)<1e-9&&s.fatigue===1);
t("nonfinite signalOk", step(init(),{theta:NaN,alpha:0.3,beta:0.4},0).signalOk===false);
console.log(`\n${p} passed, ${f} failed`); process.exit(f?1:0);
'
```
Expected: `8 passed, 0 failed`, exit 0.

- [ ] **Step 4: Typecheck the spec + compile**

Run:
```bash
npx tsc -p tsconfig.spec.json --noEmit && npx ng build --configuration development
```
Expected: tsc prints nothing (clean); build ends `Application bundle generation complete.`

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/cognitive-metrics.ts src/app/core/neurofeedback/cognitive-metrics.spec.ts
git commit -m "feat(neuro): pure cognitive-state metrics (load, fatigue, baseline reducer)"
```

---

## Task 2: CognitiveStateService

**Files:**
- Create: `src/app/core/neurofeedback/services/cognitive-state.service.ts`

- [ ] **Step 1: Write the service**

`src/app/core/neurofeedback/services/cognitive-state.service.ts`:
```ts
import { Injectable, inject } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';
import { BrainDevice } from '../brain-device';
import { CognitiveState, initialCognitiveState, stepCognitive } from '../cognitive-metrics';

/**
 * Derives cognitive-state labels (load, fatigue, signalOk) from the device's
 * EEG band-power stream (`BrainDevice.extras$`). Mirrors FlowDetectorService:
 * pure logic in cognitive-metrics, thin streaming glue here.
 */
@Injectable({ providedIn: 'root' })
export class CognitiveStateService {
  private readonly device = inject(BrainDevice);

  private state: CognitiveState = initialCognitiveState();
  private startMs = 0;
  private sub: Subscription | null = null;

  private readonly _load = new BehaviorSubject<number | null>(null);
  private readonly _fatigue = new BehaviorSubject<number | null>(null);
  private readonly _signalOk = new BehaviorSubject<boolean>(false);

  readonly load$ = this._load.asObservable();
  readonly fatigue$ = this._fatigue.asObservable();
  readonly signalOk$ = this._signalOk.asObservable();

  /** Reset the baseline and begin consuming the band-power stream. */
  startSession(now: number = Date.now()): void {
    this.state = initialCognitiveState();
    this.startMs = now;
    this._load.next(null);
    this._fatigue.next(null);
    this._signalOk.next(false);
    this.sub?.unsubscribe();
    this.sub = this.device.extras$?.subscribe(bands => this.ingest(bands)) ?? null;
  }

  /** Stop consuming the stream. */
  endSession(): void {
    this.sub?.unsubscribe();
    this.sub = null;
  }

  private ingest(bands: Record<string, number>): void {
    this.state = stepCognitive(this.state, bands, Date.now() - this.startMs);
    this._load.next(this.state.load);
    this._fatigue.next(this.state.fatigue);
    this._signalOk.next(this.state.signalOk);
  }
}
```

> No service spec: the logic is fully covered by `cognitive-metrics.spec.ts`; this is thin glue using `Date.now()` + DI, which only Karma could exercise (broken). Verified by build + the Task 6 runtime check.

- [ ] **Step 2: Compile**

Run: `npx ng build --configuration development`
Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add src/app/core/neurofeedback/services/cognitive-state.service.ts
git commit -m "feat(neuro): CognitiveStateService deriving load/fatigue from extras\$"
```

---

## Task 3: Extend EegTick model + writeEegTick

**Files:**
- Modify: `src/app/modules/capture/models/capture-session.model.ts` (the `EegTick` interface)
- Modify: `src/app/modules/capture/services/supabase-capture.service.ts` (`writeEegTick`)

- [ ] **Step 1: Extend the model**

In `capture-session.model.ts`, replace the `EegTick` interface with:
```ts
export interface EegTick {
  t: string;
  focus: number;
  calm: number;
  inFlow: boolean;
  load: number | null;
  fatigue: number | null;
  signalOk: boolean | null;
}
```

- [ ] **Step 2: Extend writeEegTick**

In `supabase-capture.service.ts`, replace the `writeEegTick` method with:
```ts
  writeEegTick(
    sessionId: string,
    focus: number,
    calm: number,
    inFlow: boolean,
    load: number | null,
    fatigue: number | null,
    signalOk: boolean | null,
  ): void {
    this.supabase.client
      .from('eeg_ticks')
      .insert({ session_id: sessionId, focus, calm, in_flow: inFlow, load, fatigue, signal_ok: signalOk })
      .then(({ error }) => {
        if (error) console.error('EEG tick write failed:', error.message);
      });
  }
```

- [ ] **Step 3: Compile**

Run: `npx ng build --configuration development`
Expected: build fails — `capture-session.service.ts` still calls the old 4-arg `writeEegTick`. That is expected; Task 5 fixes the caller. To keep this task self-contained, instead verify only the two edited files typecheck:

Run: `npx tsc --noEmit -p tsconfig.app.json 2>&1 | grep -E "capture-session.model|supabase-capture" || echo "no errors in edited files"`
Expected: `no errors in edited files`

> Note: the full build goes green at Task 5. Commit now; the repo is briefly mid-refactor (acceptable — single short-lived gap, fixed in the next two tasks).

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/models/capture-session.model.ts src/app/modules/capture/services/supabase-capture.service.ts
git commit -m "feat(capture): extend EegTick + writeEegTick with load/fatigue/signal_ok"
```

---

## Task 4: Database migration

**Files:**
- Create: `supabase/migrations/20260609_eeg_ticks_cognitive.sql`

- [ ] **Step 1: Write the migration**

`supabase/migrations/20260609_eeg_ticks_cognitive.sql`:
```sql
-- Cognitive-state labels for capture ticks. Nullable + idempotent: existing rows stay valid.
alter table public.eeg_ticks
  add column if not exists load      real,
  add column if not exists fatigue   real,
  add column if not exists signal_ok boolean;
```

- [ ] **Step 2: Apply to Supabase**

This repo has no migration pipeline (apply SQL manually). Run the SQL above in the Supabase SQL editor for project `hmiwxefpxbvjstsdywxb` (Frankfurt). Verify:
```sql
select column_name from information_schema.columns
where table_name = 'eeg_ticks' and column_name in ('load','fatigue','signal_ok');
```
Expected: three rows.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260609_eeg_ticks_cognitive.sql
git commit -m "feat(db): add load/fatigue/signal_ok columns to eeg_ticks"
```

---

## Task 5: Wire CognitiveStateService into the capture session

**Files:**
- Modify: `src/app/modules/capture/services/capture-session.service.ts`

- [ ] **Step 1: Import + inject**

Add the import near the other `core/neurofeedback` imports:
```ts
import { CognitiveStateService } from '../../../core/neurofeedback/services/cognitive-state.service';
```
Add to the constructor parameter list (alongside `flowDetector`):
```ts
    private cognitiveState: CognitiveStateService,
```

- [ ] **Step 2: Session hooks**

In `startSession(...)`, immediately after `this.eegTickCount = 0;`, add:
```ts
    this.cognitiveState.startSession();
```
In `stopSession()`, immediately after `this.eegSub?.unsubscribe();`, add:
```ts
    this.cognitiveState.endSession();
```

- [ ] **Step 3: Extend the tick subscription + write**

Replace `startEegSubscription` and `writeEegTick` with:
```ts
  protected startEegSubscription(sessionId: string): Subscription {
    return combineLatest([this.brainDevice.focus$, this.brainDevice.calm$])
      .pipe(
        filter(([f, c]) => f !== null && c !== null),
        withLatestFrom(
          this.flowDetector.inFlow$,
          this.cognitiveState.load$,
          this.cognitiveState.fatigue$,
          this.cognitiveState.signalOk$,
        ),
      )
      .subscribe(([[focus, calm], inFlow, load, fatigue, signalOk]) => {
        this.writeEegTick(sessionId, focus!, calm!, inFlow, load, fatigue, signalOk);
      });
  }

  private writeEegTick(
    sessionId: string,
    focus: number,
    calm: number,
    inFlow: boolean,
    load: number | null,
    fatigue: number | null,
    signalOk: boolean | null,
  ): void {
    this.eegTickCount++;
    if (!this.mode.isMock()) {
      this.supabaseCapture.writeEegTick(sessionId, focus, calm, inFlow, load, fatigue, signalOk);
    }
  }
```

- [ ] **Step 4: Compile (now green end-to-end)**

Run: `npx ng build --configuration development`
Expected: `Application bundle generation complete.`

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/services/capture-session.service.ts
git commit -m "feat(capture): write load/fatigue/signal_ok per EEG tick"
```

---

## Task 6: Final verification

- [ ] **Step 1: Full build + metric tests + typecheck**

Run:
```bash
npx ng build --configuration development
npx tsc -p tsconfig.spec.json --noEmit
```
Expected: build complete; tsc clean. (Re-run the Task 1 node check if desired: `8 passed`.)

- [ ] **Step 2: Runtime sanity (mock + real notes)**

- Mock mode (`environment.device === 'mock'`): start a capture; `writeEegTick` runs but does not persist in mock (by design) and `MockNeurosityService` has no `extras$`, so `load/fatigue` stay null — confirm no console errors and the session completes.
- Real Muse (when hardware arrives): connect, start a capture, and confirm `eeg_ticks` rows carry non-null `load`/`fatigue` after ~30 s (baseline), and that `load` rises during mental effort (e.g., arithmetic) — the spec's eyes-closed / mental-math probe.

- [ ] **Step 3: No commit** (verification only).

---

## Notes / out of scope (per spec)
- Live UI gauges, stored segment flags, multi-electrode quality, validated metrics — all deferred.
- Mock-mode `load/fatigue` are null (mock device has no `extras$`); not worth synthesizing for Phase 1.
