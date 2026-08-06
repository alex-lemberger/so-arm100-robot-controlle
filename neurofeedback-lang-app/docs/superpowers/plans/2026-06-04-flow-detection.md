# Flow Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect "flow state" live from the EEG focus/calm streams and show an *In Flow* badge plus a running *% of session in flow* in the dashboard live band.

**Architecture:** A standalone `FlowDetectorService` consumes `BrainDevice.focus$/calm$`, runs a pure reducer (`stepFlow`) that EMA-smooths each signal then classifies flow with a dual-threshold + dwell + hysteresis rule, and exposes `inFlow$`. The dashboard consumes it via `toSignal` and accumulates the running percentage against its existing session timer. A pre-existing scale bug in the mock device (emits 0–100 instead of 0–1) is fixed.

**Tech Stack:** Angular 19 (standalone, Signals), RxJS 7, NGXS (unchanged), Karma + Jasmine. The detector imports **no** `@neurosity/sdk`, so its specs run cleanly under the otherwise-broken Karma setup.

**Spec:** `docs/superpowers/specs/2026-06-04-flow-detection-design.md`

---

## File Structure

- **Create** `src/app/core/neurofeedback/models/flow-config.ts` — `FlowConfig` interface, `DEFAULT_FLOW_CONFIG`, `FLOW_CONFIG` DI token. Pure constants/types.
- **Create** `src/app/core/neurofeedback/services/flow-detector.service.ts` — pure reducer (`FlowState`, `initialFlowState`, `stepFlow`) + `FlowDetectorService` that wires the streams.
- **Create** `src/app/core/neurofeedback/services/flow-detector.service.spec.ts` — unit tests for `stepFlow` (pure) and the service (fake `BrainDevice`).
- **Modify** `src/app/core/neurofeedback/services/mock-neurosity.service.ts` — emit 0–1 to honor the `BrainDevice` contract.
- **Modify** `src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts` — assert emitted values are within [0,1].
- **Modify** `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` / `.html` / `.scss` — badge + running %.

**Test command (single spec):** `ng test --include='**/flow-detector.service.spec.ts' --watch=false --browsers=ChromeHeadless`

---

## Task 1: Flow config model

**Files:**
- Create: `src/app/core/neurofeedback/models/flow-config.ts`

This file is pure types + constants (no branching logic), so it has no standalone test; it is exercised by Task 2's `stepFlow` tests.

- [ ] **Step 1: Create the config file**

```ts
import { InjectionToken } from '@angular/core';

/** Tunable thresholds for flow-state classification. All metric bounds are 0–1. */
export interface FlowConfig {
  /** EMA smoothing factor (0–1); higher = more responsive, noisier. */
  alpha: number;
  /** Min smoothed focus to enter flow. */
  enterFocus: number;
  /** Smoothed focus below this exits flow (hysteresis; < enterFocus). */
  exitFocus: number;
  /** Calm sweet-spot bounds to enter flow. */
  enterCalmLo: number;
  enterCalmHi: number;
  /** Calm exit bounds (wider than enter bounds; hysteresis). */
  exitCalmLo: number;
  exitCalmHi: number;
  /** Seconds the enter condition must hold before flow is declared. */
  dwellSeconds: number;
}

export const DEFAULT_FLOW_CONFIG: FlowConfig = {
  alpha: 0.3,
  enterFocus: 0.70,
  exitFocus: 0.62,
  enterCalmLo: 0.45,
  enterCalmHi: 0.85,
  exitCalmLo: 0.40,
  exitCalmHi: 0.90,
  dwellSeconds: 5,
};

/** Overridable in tests / future per-user tuning. */
export const FLOW_CONFIG = new InjectionToken<FlowConfig>('FLOW_CONFIG', {
  providedIn: 'root',
  factory: () => DEFAULT_FLOW_CONFIG,
});
```

- [ ] **Step 2: Verify it compiles**

Run: `npx ng build --configuration development`
Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add src/app/core/neurofeedback/models/flow-config.ts
git commit -m "feat: flow-state config tokens"
```

---

## Task 2: `stepFlow` pure reducer (TDD)

**Files:**
- Create: `src/app/core/neurofeedback/services/flow-detector.service.ts`
- Test: `src/app/core/neurofeedback/services/flow-detector.service.spec.ts`

- [ ] **Step 1: Write the failing tests**

Create `flow-detector.service.spec.ts`:

```ts
import { initialFlowState, stepFlow, FlowState } from './flow-detector.service';
import { DEFAULT_FLOW_CONFIG, FlowConfig } from '../models/flow-config';

const CFG: FlowConfig = DEFAULT_FLOW_CONFIG;

/** Feed a constant focus/calm for `n` steps of `dt` seconds each. */
function run(focus: number | null, calm: number | null, n: number, dt = 1, cfg = CFG): FlowState {
  let s = initialFlowState();
  for (let i = 0; i < n; i++) { s = stepFlow(s, focus, calm, dt, cfg); }
  return s;
}

describe('stepFlow', () => {
  it('does not enter flow before the dwell time elapses', () => {
    // Good sample, but only 4s < dwellSeconds (5).
    const s = run(0.85, 0.6, 4, 1);
    expect(s.inFlow).toBe(false);
  });

  it('enters flow once the enter condition holds for dwellSeconds', () => {
    const s = run(0.85, 0.6, 6, 1);
    expect(s.inFlow).toBe(true);
  });

  it('stays in flow on a brief dip that remains above exitFocus (hysteresis)', () => {
    let s = run(0.85, 0.6, 6, 1);          // in flow
    expect(s.inFlow).toBe(true);
    s = stepFlow(s, 0.66, 0.6, 1, CFG);     // smoothed focus stays >= exitFocus (0.62)
    expect(s.inFlow).toBe(true);
  });

  it('exits flow when smoothed focus drops below exitFocus', () => {
    let s = run(0.85, 0.6, 8, 1);          // firmly in flow, smoothed ~0.85
    expect(s.inFlow).toBe(true);
    for (let i = 0; i < 6; i++) { s = stepFlow(s, 0.10, 0.6, 1, CFG); } // drag smoothed down
    expect(s.inFlow).toBe(false);
  });

  it('exits flow when calm leaves the exit band', () => {
    let s = run(0.85, 0.6, 8, 1);
    expect(s.inFlow).toBe(true);
    for (let i = 0; i < 8; i++) { s = stepFlow(s, 0.85, 0.97, 1, CFG); } // calm too high
    expect(s.inFlow).toBe(false);
  });

  it('treats a null sample as not-in-flow and resets dwell', () => {
    let s = run(0.85, 0.6, 4, 1);          // partway through dwell
    s = stepFlow(s, null, 0.6, 1, CFG);
    expect(s.inFlow).toBe(false);
    expect(s.dwell).toBe(0);
  });

  it('respects a config override (dwellSeconds 0 enters immediately)', () => {
    const cfg: FlowConfig = { ...CFG, dwellSeconds: 0 };
    const s = run(0.85, 0.6, 1, 1, cfg);
    expect(s.inFlow).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `ng test --include='**/flow-detector.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: FAIL — `flow-detector.service` has no exports `initialFlowState`/`stepFlow`.

- [ ] **Step 3: Write the reducer**

Create `flow-detector.service.ts` (service added in Task 3; reducer first):

```ts
import { FlowConfig } from '../models/flow-config';

export interface FlowState {
  /** Smoothed focus, null until first non-null sample. */
  fSm: number | null;
  /** Smoothed calm, null until first non-null sample. */
  cSm: number | null;
  /** Accumulated seconds the enter condition has held (while not yet in flow). */
  dwell: number;
  inFlow: boolean;
}

export function initialFlowState(): FlowState {
  return { fSm: null, cSm: null, dwell: 0, inFlow: false };
}

/**
 * Advance the flow classifier by one sample.
 * Pure: no clock, no streams. `dt` is seconds since the previous sample.
 */
export function stepFlow(
  s: FlowState,
  focus: number | null,
  calm: number | null,
  dt: number,
  cfg: FlowConfig,
): FlowState {
  if (focus == null || calm == null) {
    return { fSm: s.fSm, cSm: s.cSm, dwell: 0, inFlow: false };
  }

  const fSm = s.fSm == null ? focus : cfg.alpha * focus + (1 - cfg.alpha) * s.fSm;
  const cSm = s.cSm == null ? calm : cfg.alpha * calm + (1 - cfg.alpha) * s.cSm;

  if (s.inFlow) {
    const exit = fSm < cfg.exitFocus || cSm < cfg.exitCalmLo || cSm > cfg.exitCalmHi;
    return { fSm, cSm, dwell: 0, inFlow: !exit };
  }

  const enter = fSm >= cfg.enterFocus && cSm >= cfg.enterCalmLo && cSm <= cfg.enterCalmHi;
  const dwell = enter ? s.dwell + dt : 0;
  return { fSm, cSm, dwell, inFlow: dwell >= cfg.dwellSeconds };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `ng test --include='**/flow-detector.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: PASS (7 specs).

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/services/flow-detector.service.ts src/app/core/neurofeedback/services/flow-detector.service.spec.ts
git commit -m "feat: stepFlow reducer for flow-state classification"
```

---

## Task 3: `FlowDetectorService` stream wiring (TDD)

**Files:**
- Modify: `src/app/core/neurofeedback/services/flow-detector.service.ts`
- Test: `src/app/core/neurofeedback/services/flow-detector.service.spec.ts`

- [ ] **Step 1: Add the failing service test**

Append to `flow-detector.service.spec.ts`:

```ts
import { TestBed } from '@angular/core/testing';
import { BehaviorSubject, Observable } from 'rxjs';
import { FlowDetectorService } from './flow-detector.service';
import { FLOW_CONFIG, DEFAULT_FLOW_CONFIG } from '../models/flow-config';
import { BrainDevice, DeviceState, DeviceStatus } from '../brain-device';

class FakeDevice implements BrainDevice {
  focus$ = new BehaviorSubject<number | null>(null);
  calm$ = new BehaviorSubject<number | null>(null);
  state$ = new BehaviorSubject<DeviceState>({ isLoggedIn: true, error: null });
  extras$: Observable<Record<string, number>> = new BehaviorSubject({});
  connect() { return Promise.resolve(); }
  disconnect() { return Promise.resolve(); }
  getStatus(): Promise<DeviceStatus> { return Promise.resolve({ state: 'online' }); }
}

describe('FlowDetectorService', () => {
  let device: FakeDevice;
  let service: FlowDetectorService;

  beforeEach(() => {
    device = new FakeDevice();
    TestBed.configureTestingModule({
      providers: [
        FlowDetectorService,
        { provide: BrainDevice, useValue: device },
        // dwellSeconds 0 → enter as soon as a qualifying sample arrives (no timing)
        { provide: FLOW_CONFIG, useValue: { ...DEFAULT_FLOW_CONFIG, dwellSeconds: 0 } },
      ],
    });
    service = TestBed.inject(FlowDetectorService);
  });

  it('emits true once focus and calm enter the flow zone', () => {
    const seen: boolean[] = [];
    service.inFlow$.subscribe((v) => seen.push(v));
    device.focus$.next(0.85);
    device.calm$.next(0.60);
    expect(seen[seen.length - 1]).toBe(true);
  });

  it('emits false when focus leaves the flow zone', () => {
    const seen: boolean[] = [];
    service.inFlow$.subscribe((v) => seen.push(v));
    device.focus$.next(0.85);
    device.calm$.next(0.60);   // true (smoothed focus seeds at 0.85)
    device.focus$.next(0.10);  // smoothed → 0.625, still ≥ exitFocus (holds)
    device.focus$.next(0.10);  // smoothed → ~0.47, exits
    expect(seen[seen.length - 1]).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `ng test --include='**/flow-detector.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: FAIL — `FlowDetectorService` is not exported / has no `inFlow$`.

- [ ] **Step 3: Add the service to `flow-detector.service.ts`**

Add these imports at the top of the file:

```ts
import { Injectable, inject } from '@angular/core';
import { Observable, combineLatest } from 'rxjs';
import { distinctUntilChanged, map, scan, shareReplay } from 'rxjs/operators';
import { BrainDevice } from '../brain-device';
import { FLOW_CONFIG } from '../models/flow-config';
```

Append below the reducer:

```ts
interface ScanAcc { state: FlowState; last: number | null; }

/**
 * Classifies live flow state from the device focus/calm streams.
 * Single public output: `inFlow$`. Pure logic lives in `stepFlow`.
 */
@Injectable({ providedIn: 'root' })
export class FlowDetectorService {
  private readonly cfg = inject(FLOW_CONFIG);
  private readonly device = inject(BrainDevice);
  /** Injectable clock seam for deterministic tests. */
  protected now: () => number = () => Date.now();

  readonly inFlow$: Observable<boolean> = combineLatest([
    this.device.focus$,
    this.device.calm$,
  ]).pipe(
    scan<[number | null, number | null], ScanAcc>((acc, [focus, calm]) => {
      const t = this.now();
      const dt = acc.last == null ? 0 : Math.max(0, (t - acc.last) / 1000);
      return { state: stepFlow(acc.state, focus, calm, dt, this.cfg), last: t };
    }, { state: initialFlowState(), last: null }),
    map((acc) => acc.state.inFlow),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}
```

- [ ] **Step 4: Run to verify all specs pass**

Run: `ng test --include='**/flow-detector.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: PASS (9 specs total).

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/services/flow-detector.service.ts src/app/core/neurofeedback/services/flow-detector.service.spec.ts
git commit -m "feat: FlowDetectorService wiring inFlow$ from device streams"
```

---

## Task 4: Fix mock device scale to 0–1 (TDD)

**Files:**
- Modify: `src/app/core/neurofeedback/services/mock-neurosity.service.ts` (emit sites near line 70–73)
- Test: `src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts`

> Note: `mock-neurosity.service.spec.ts` is one of the specs that historically fails because of the `@neurosity/sdk` import cascade. Run it filtered; if the suite errors on unrelated SDK setup rather than this assertion, record that and verify the fix by reading the emitted values in the dashboard instead (Task 5 manual check). The source change itself is unambiguous.

- [ ] **Step 1: Add a failing assertion**

Add this spec to `mock-neurosity.service.spec.ts` (inside the top-level `describe`):

```ts
import { fakeAsync, tick } from '@angular/core/testing';

it('emits focus and calm within the 0–1 BrainDevice contract', fakeAsync(() => {
  // `service` is the MockNeurosityService instance from the existing setup.
  service.connect({ email: 'a@b.c', password: 'x' });
  tick(1100); // allow login (~1000ms) + one stream tick (1000ms interval)
  const focus = service.focus$.value;
  const calm = service.calm$.value;
  expect(focus).not.toBeNull();
  expect(focus!).toBeGreaterThanOrEqual(0);
  expect(focus!).toBeLessThanOrEqual(1);
  expect(calm!).toBeGreaterThanOrEqual(0);
  expect(calm!).toBeLessThanOrEqual(1);
  service.disconnect();
}));
```

- [ ] **Step 2: Run to verify it fails**

Run: `ng test --include='**/mock-neurosity.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: FAIL — emitted value ~0–100 exceeds 1 (or, if the SDK import cascade errors the suite, note it and proceed; the assertion still encodes the intent).

- [ ] **Step 3: Divide the emitted values by 100**

In `mock-neurosity.service.ts`, find the stream tick (around line 70):

```ts
        const focusValue = this.generateRealisticValue(this.baselineFocus);
        const calmValue = this.generateRealisticValue(this.baselineCalm);
        this.focus$.next(focusValue);
        this.calm$.next(calmValue);
```

Replace the two `next` lines so the public streams emit 0–1 (the internal
generator stays on its 0–100 model):

```ts
        const focusValue = this.generateRealisticValue(this.baselineFocus);
        const calmValue = this.generateRealisticValue(this.baselineCalm);
        this.focus$.next(focusValue / 100);
        this.calm$.next(calmValue / 100);
```

- [ ] **Step 4: Run to verify it passes**

Run: `ng test --include='**/mock-neurosity.service.spec.ts' --watch=false --browsers=ChromeHeadless`
Expected: PASS (or the documented SDK-cascade caveat from Step 2).

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/services/mock-neurosity.service.ts src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts
git commit -m "fix: mock device emits 0-1 to honor BrainDevice contract"
```

---

## Task 5: Dashboard badge + running flow %

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.html`
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.scss`

> The component injects Firebase `Auth`, so an isolated TestBed spec needs the
> full Firebase provider graph (brittle here). Verify this task by compilation
> (`ng build`) plus the manual check in Step 6 — consistent with how the rest of
> this component is validated.

- [ ] **Step 1: Wire the detector into the component**

In `dashboard.component.ts`, add the import:

```ts
import { FlowDetectorService } from '../../../../core/neurofeedback/services/flow-detector.service';
```

Add the injection alongside the other `inject(...)` fields:

```ts
  private readonly flowDetector = inject(FlowDetectorService);
```

Add the flow signals (near the `focus`/`calm` signals):

```ts
  readonly inFlow = toSignal(this.flowDetector.inFlow$, { initialValue: false });
  readonly flowSeconds = signal(0);
  readonly flowPercent = computed(() => {
    const e = this.elapsed();
    return e > 0 ? Math.round((this.flowSeconds() / e) * 100) : 0;
  });
```

- [ ] **Step 2: Accumulate flow seconds in the existing timer**

In `dashboard.component.ts`, change `startTimer()` so each tick also counts
flow seconds while in flow:

```ts
  private startTimer(): void {
    this.stopTimer();
    this.timerId = setInterval(() => {
      this.elapsed.update((s) => s + 1);
      if (this.inFlow()) { this.flowSeconds.update((s) => s + 1); }
    }, 1000);
  }
```

In `startSession()`, reset the flow counter where `elapsed` is reset:

```ts
      this.elapsed.set(0);
      this.flowSeconds.set(0);
      this.sessionActive.set(true);
      this.startTimer();
```

- [ ] **Step 3: Add the badge to the live band**

In `dashboard.component.html`, inside `.band__session`, replace the `.band__sub`
line:

```html
        <div class="band__sub">Session 2 of 3 · Today</div>
```

with the session sub-line plus a flow badge that only shows during a session:

```html
        <div class="band__sub">Session 2 of 3 · Today</div>
        @if (sessionActive()) {
          <div class="flowbadge" [class.flowbadge--on]="inFlow()" aria-live="polite">
            <span class="flowbadge__dot" aria-hidden="true"></span>
            <span class="flowbadge__text">{{ inFlow() ? 'In Flow' : 'Building…' }}</span>
            <span class="flowbadge__pct">{{ flowPercent() }}%</span>
          </div>
        }
```

- [ ] **Step 4: Style the badge**

Append to `dashboard.component.scss`:

```scss
/* ── Flow badge ───────────────────────────────────────────────── */
.flowbadge {
  display: inline-flex; align-items: center; gap: 6px; margin-top: 8px;
  padding: 3px 9px; border-radius: 999px;
  background: var(--c-border-soft); color: var(--c-text-3);
  font-size: 11px; font-weight: 600; letter-spacing: .02em;
  transition: background .2s, color .2s;
}
.flowbadge__dot {
  width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0;
}
.flowbadge__pct { font-family: var(--c-mono); font-weight: 500; }
.flowbadge--on {
  background: var(--c-teal); color: #fff;
  .flowbadge__dot { animation: flow-pulse 1.8s ease-in-out infinite; }
}
@keyframes flow-pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }
@media (prefers-reduced-motion: reduce) { .flowbadge--on .flowbadge__dot { animation: none; } }
```

- [ ] **Step 5: Verify compilation**

Run: `npx ng build --configuration development`
Expected: `Application bundle generation complete.`

- [ ] **Step 6: Manual verification**

Run: `npm start`, open `http://localhost:4200/dashboard`. Confirm:
- Focus/calm rings now read values in `0.00–1.00` (mock fix from Task 4).
- Click **Start Session**: badge appears showing `Building…` then flips to
  `In Flow` (teal, pulsing) once smoothed focus/calm sit in the zone for ~5 s;
  the `%` climbs while in flow.
- Click **End Session**: timer stops; badge hides.

- [ ] **Step 7: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/dashboard.component.ts src/app/shared/components/layout/dashboard-layout/dashboard.component.html src/app/shared/components/layout/dashboard-layout/dashboard.component.scss
git commit -m "feat: live In-Flow badge and session flow percentage"
```

---

## Done criteria

- `FlowDetectorService.inFlow$` classifies flow with smoothing + dwell + hysteresis; covered by 9 passing specs that import no `@neurosity/sdk`.
- Mock device emits 0–1; dashboard rings render correctly.
- Live band shows an accessible `In Flow` / `Building…` badge and a running flow `%` during a session.
- `ng build --configuration development` succeeds.
