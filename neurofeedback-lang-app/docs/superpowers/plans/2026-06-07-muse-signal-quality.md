# Muse 2 Signal Quality Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Block the hardware-setup wizard's EEG step until ≥3/4 Muse 2 electrodes hold good contact for 3 continuous seconds, preventing bad-data capture sessions.

**Architecture:** New `EegSignalQualityService` in the capture module derives per-electrode quality from raw EEG variance (muse-js has no native quality API). `MockNeurosityService` gains a simulated `rawEeg$` that animates through poor→good so the wizard UI can be fully tested without hardware. `HardwareSetupComponent` wires the service via an Angular `effect()` and gates "Weiter" on `gateOpen$`.

**Tech Stack:** Angular 19 standalone, RxJS, Signals (`effect`, `toSignal`, `computed`), Jasmine/Karma, muse-js `EegReading`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/app/modules/capture/services/eeg-signal-quality.service.ts` | Per-electrode variance classification + 3 s gate |
| Create | `src/app/modules/capture/services/eeg-signal-quality.service.spec.ts` | 9 unit tests |
| Modify | `src/app/core/neurofeedback/services/mock-neurosity.service.ts` | Replace `rawEeg$ = undefined` with simulated cold Observable |
| Modify | `src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts` | Inject service, show electrode dots, gate canContinue |

---

## Task 1: EegSignalQualityService — failing tests

**Files:**
- Create: `src/app/modules/capture/services/eeg-signal-quality.service.spec.ts`

- [x] **Step 1: Create the spec file**

```typescript
// src/app/modules/capture/services/eeg-signal-quality.service.spec.ts
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { EegSignalQualityService, ElectrodeQuality } from './eeg-signal-quality.service';
import { EegReading } from '../../../core/neurofeedback/brain-device';

function makeReading(electrode: number, samples: number[]): EegReading {
  return { electrode, samples, timestamp: Date.now() };
}

// Variance ≈ 200 µV² — within [5, 2000] → 'good'
function goodSamples(n = 256): number[] {
  return Array.from({ length: n }, (_, i) => 20 * Math.sin(i * 0.1));
}

// Variance = 0 — below MIN_VARIANCE (5) → 'poor'
function flatSamples(n = 256): number[] {
  return Array(n).fill(0);
}

// Variance = 25,000,000 — above MAX_VARIANCE (2000) → 'poor'
function noisySamples(n = 256): number[] {
  return Array.from({ length: n }, (_, i) => i % 2 === 0 ? 5000 : -5000);
}

describe('EegSignalQualityService', () => {
  let service: EegSignalQualityService;
  let source$: Subject<EegReading>;
  let latestQuality: ElectrodeQuality[];
  let gateValues: boolean[];

  beforeEach(() => {
    jasmine.clock().install();
    TestBed.configureTestingModule({});
    service = TestBed.inject(EegSignalQualityService);
    source$ = new Subject<EegReading>();
    latestQuality = [];
    gateValues = [];
    service.quality$.subscribe(q => { latestQuality = q; });
    service.gateOpen$.subscribe(v => { gateValues.push(v); });
  });

  afterEach(() => {
    service.stopMonitoring();
    jasmine.clock().uninstall();
  });

  it('emits unknown for all electrodes before 128 samples', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, goodSamples(64)));
    expect(latestQuality[0].state).toBe('unknown');
    expect(latestQuality[1].state).toBe('unknown');
    expect(latestQuality[2].state).toBe('unknown');
    expect(latestQuality[3].state).toBe('unknown');
  });

  it('emits good for variance in range', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, goodSamples(256)));
    expect(latestQuality[0].state).toBe('good');
  });

  it('emits poor for flat signal', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, flatSamples(256)));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('emits poor for noisy signal', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, noisySamples(256)));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('emits poor when window contains NaN', () => {
    service.startMonitoring(source$.asObservable());
    const samples = goodSamples(256);
    samples[10] = NaN;
    source$.next(makeReading(0, samples));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('opens gate after 3 s of ≥3/4 good', () => {
    service.startMonitoring(source$.asObservable());
    for (let e = 0; e < 4; e++) {
      source$.next(makeReading(e, goodSamples(256)));
    }
    expect(gateValues[gateValues.length - 1]).toBeFalse();

    jasmine.clock().tick(3001);
    source$.next(makeReading(0, goodSamples(12)));   // trigger evaluate at t+3001ms

    expect(gateValues[gateValues.length - 1]).toBeTrue();
  });

  it('resets gate timer when quality drops', () => {
    service.startMonitoring(source$.asObservable());
    for (let e = 0; e < 4; e++) {
      source$.next(makeReading(e, goodSamples(256)));
    }
    jasmine.clock().tick(1000);
    source$.next(makeReading(0, goodSamples(12)));   // still good at t+1s

    // drop 3 electrodes to poor
    for (let e = 0; e < 3; e++) {
      source$.next(makeReading(e, flatSamples(256)));
    }
    jasmine.clock().tick(3001);
    source$.next(makeReading(0, flatSamples(12)));   // trigger evaluate at t+4s

    expect(gateValues[gateValues.length - 1]).toBeFalse();
  });

  it('opens gate immediately when rawEeg$ is undefined', () => {
    service.startMonitoring(undefined);
    expect(gateValues[gateValues.length - 1]).toBeTrue();
  });

  it('ignores emissions after stopMonitoring', () => {
    service.startMonitoring(source$.asObservable());
    service.stopMonitoring();
    const qualityBeforeStop = [...latestQuality];
    source$.next(makeReading(0, goodSamples(256)));
    expect(latestQuality).toEqual(qualityBeforeStop);
  });
});
```

- [x] **Step 2: Run tests — verify they fail**

```bash
ng test --include='**/eeg-signal-quality.service.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: FAIL — `EegSignalQualityService` not found / cannot read properties of undefined.

---

## Task 2: EegSignalQualityService — implementation

**Files:**
- Create: `src/app/modules/capture/services/eeg-signal-quality.service.ts`

- [x] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/eeg-signal-quality.service.ts
import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject, Subscription } from 'rxjs';
import { EegReading } from '../../../core/neurofeedback/brain-device';

export type ContactState = 'unknown' | 'poor' | 'good';

export interface ElectrodeQuality {
  electrode: number;
  name: string;
  state: ContactState;
}

const ELECTRODE_NAMES = ['TP9', 'AF7', 'AF8', 'TP10'];
const BUFFER_SIZE = 256;
const MIN_SAMPLES = 128;
const MIN_VARIANCE = 5;       // µV² — below = flat / no contact
const MAX_VARIANCE = 2000;    // µV² — above = excessive artifact noise
const GOOD_COUNT_THRESHOLD = 3;
const GATE_DURATION_MS = 3000;

@Injectable({ providedIn: 'root' })
export class EegSignalQualityService {
  private buffers: number[][] = [[], [], [], []];
  private sub: Subscription | null = null;
  private goodSince: number | null = null;

  private readonly _quality$ = new BehaviorSubject<ElectrodeQuality[]>(
    ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
  );
  private readonly _gateOpen$ = new BehaviorSubject<boolean>(false);

  readonly quality$ = this._quality$.asObservable();
  readonly gateOpen$ = this._gateOpen$.asObservable();

  startMonitoring(rawEeg$: Observable<EegReading> | undefined): void {
    this.stopMonitoring();
    if (!rawEeg$) {
      this._gateOpen$.next(true);
      return;
    }
    this.buffers = [[], [], [], []];
    this.goodSince = null;
    this._gateOpen$.next(false);
    this._quality$.next(
      ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
    );
    this.sub = rawEeg$.subscribe(reading => {
      if (reading.electrode < 0 || reading.electrode >= 4) return;
      const buf = this.buffers[reading.electrode];
      buf.push(...reading.samples);
      if (buf.length > BUFFER_SIZE) {
        this.buffers[reading.electrode] = buf.slice(-BUFFER_SIZE);
      }
      this.evaluate();
    });
  }

  stopMonitoring(): void {
    this.sub?.unsubscribe();
    this.sub = null;
    this.goodSince = null;
    this.buffers = [[], [], [], []];
    this._gateOpen$.next(false);
    this._quality$.next(
      ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
    );
  }

  private evaluate(): void {
    const qualities = this.buffers.map((buf, electrode) => ({
      electrode,
      name: ELECTRODE_NAMES[electrode],
      state: this.classify(buf),
    }));
    this._quality$.next(qualities);

    const goodCount = qualities.filter(q => q.state === 'good').length;
    const now = Date.now();

    if (goodCount >= GOOD_COUNT_THRESHOLD) {
      if (this.goodSince === null) {
        this.goodSince = now;
      } else if (now - this.goodSince >= GATE_DURATION_MS) {
        this._gateOpen$.next(true);
      }
    } else {
      this.goodSince = null;
      this._gateOpen$.next(false);
    }
  }

  private classify(buf: number[]): ContactState {
    if (buf.length < MIN_SAMPLES) return 'unknown';
    if (buf.some(s => isNaN(s))) return 'poor';
    const mean = buf.reduce((s, x) => s + x, 0) / buf.length;
    const variance = buf.reduce((s, x) => s + (x - mean) ** 2, 0) / buf.length;
    return variance < MIN_VARIANCE || variance > MAX_VARIANCE ? 'poor' : 'good';
  }
}
```

- [x] **Step 2: Run tests — verify they pass**

```bash
ng test --include='**/eeg-signal-quality.service.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: 9 specs, 0 failures.

- [x] **Step 3: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.` No errors.

- [x] **Step 4: Commit**

```bash
git add src/app/modules/capture/services/eeg-signal-quality.service.ts \
        src/app/modules/capture/services/eeg-signal-quality.service.spec.ts
git commit -m "feat(capture): add EegSignalQualityService with variance-based electrode classification"
```

---

## Task 3: Mock dry-run — simulated rawEeg$ in MockNeurosityService

**Files:**
- Modify: `src/app/core/neurofeedback/services/mock-neurosity.service.ts`

The mock simulates the full quality onboarding animation without hardware:
- **Phase 1 (0–1 500 ms after subscription):** flat samples (variance = 0 → `'poor'`)
- **Phase 2 (1 500 ms +):** sinusoidal samples (variance ≈ 200 µV² → `'good'`)
- **Gate opens** after 3 s of phase 2 (≈ 4.5 s total from monitoring start)

- [x] **Step 1: Replace `rawEeg$ = undefined` with a simulated cold Observable**

In `src/app/core/neurofeedback/services/mock-neurosity.service.ts`, replace line 23:

```typescript
public readonly rawEeg$ = undefined;
```

with:

```typescript
public readonly rawEeg$: Observable<EegReading>;
```

Add this to the `constructor()` body after `super()`:

```typescript
this.rawEeg$ = new Observable<EegReading>(subscriber => {
  const start = Date.now();
  const id = setInterval(() => {
    const elapsed = Date.now() - start;
    const phase2 = elapsed >= 1500;
    const tick = Math.floor(elapsed / 50);
    for (let electrode = 0; electrode < 4; electrode++) {
      const samples: number[] = phase2
        ? Array.from({ length: 12 }, (_, i) => 20 * Math.sin((tick * 12 + i) * 0.1))
        : Array(12).fill(0);
      subscriber.next({ electrode, samples, timestamp: Date.now() });
    }
  }, 50);
  return () => clearInterval(id);
});
```

Also add `Observable` to the existing rxjs import at the top if not already present — the file already imports `{ BehaviorSubject, Subject, Subscription, interval }`, so add `Observable`:

```typescript
import { BehaviorSubject, Observable, Subject, Subscription, interval } from 'rxjs';
```

- [x] **Step 2: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.` No errors.

- [x] **Step 3: Commit**

```bash
git add src/app/core/neurofeedback/services/mock-neurosity.service.ts
git commit -m "feat(mock): add simulated rawEeg$ stream for signal quality dry-run"
```

---

## Task 4: Wire HardwareSetupComponent

**Files:**
- Modify: `src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts`

- [x] **Step 1: Add imports and inject the service**

At the top of the file, add to the imports section:

```typescript
import { OnDestroy } from '@angular/core';
import { EegSignalQualityService } from '../../services/eeg-signal-quality.service';
```

Change the class declaration from:

```typescript
export class HardwareSetupComponent {
```

to:

```typescript
export class HardwareSetupComponent implements OnDestroy {
```

Inside the class, after `private brainDevice = inject(BrainDevice);`, add:

```typescript
private eegQualityService = inject(EegSignalQualityService);
```

- [x] **Step 2: Add signals for quality state**

After the `eegEmail` and `eegPassword` lines, add:

```typescript
protected readonly hasRawEeg = !!this.brainDevice.rawEeg$;
protected eegGateOpen = toSignal(this.eegQualityService.gateOpen$, { initialValue: false });
protected eegQuality = toSignal(this.eegQualityService.quality$, { initialValue: [] });
protected eegQualityLabel = computed(() => {
  if (this.eegGateOpen()) return 'Signal bereit ✓';
  const goodCount = this.eegQuality().filter(q => q.state === 'good').length;
  return goodCount >= 3 ? 'Stabilisierung…' : 'Elektroden prüfen';
});
```

- [x] **Step 3: Start/stop monitoring via effect**

Add a constructor to the component (it currently has none):

```typescript
constructor() {
  effect(() => {
    if (this.eegOk()) {
      this.eegQualityService.startMonitoring(this.brainDevice.rawEeg$);
    } else {
      this.eegQualityService.stopMonitoring();
    }
  });
}
```

Add `ngOnDestroy`:

```typescript
ngOnDestroy(): void {
  this.eegQualityService.stopMonitoring();
}
```

- [x] **Step 4: Gate canContinue on eegGateOpen**

In `canContinue()`, change the `'eeg'` case from:

```typescript
case 'eeg':
  return this.eegOk();
```

to:

```typescript
case 'eeg':
  return this.eegOk() && this.eegGateOpen();
```

- [x] **Step 5: Add electrode quality UI to the EEG step template**

Inside the `@case ('eeg')` block in the template, after the existing `<button>` for connecting, add:

```html
@if (eegOk() && hasRawEeg) {
  <div class="electrode-row">
    @for (eq of eegQuality(); track eq.electrode) {
      <div class="electrode-item">
        <span class="electrode-dot"
              [class.electrode-dot--unknown]="eq.state === 'unknown'"
              [class.electrode-dot--poor]="eq.state === 'poor'"
              [class.electrode-dot--good]="eq.state === 'good'">
        </span>
        <span class="electrode-label">{{ eq.name }}</span>
      </div>
    }
  </div>
  <p class="quality-label"
     [class.quality-label--good]="eegGateOpen()"
     [class.quality-label--warn]="!eegGateOpen() && eegQuality().filter(q => q.state === 'good').length >= 3">
    {{ eegQualityLabel() }}
  </p>
}
```

Add these styles to the component's `styles` array (inside the existing backtick block, after `.setup-error` rule):

```css
.electrode-row {
  display: flex;
  gap: 20px;
  justify-content: center;
  margin-top: 8px;
}
.electrode-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.electrode-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #2a3545;
  transition: background 0.3s;
}
.electrode-dot--unknown { background: #4a5568; }
.electrode-dot--poor    { background: #e53e3e; }
.electrode-dot--good    { background: #48bb78; }
.electrode-label {
  font-size: 10px;
  color: #9aa8c4;
  font-family: 'DM Mono', monospace;
}
.quality-label {
  text-align: center;
  font-size: 13px;
  color: #9aa8c4;
  margin: 4px 0 0;
}
.quality-label--warn { color: #f6ad55; }
.quality-label--good { color: #48bb78; }
```

- [x] **Step 6: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.` No errors.

- [x] **Step 7: Commit**

```bash
git add src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts
git commit -m "feat(capture): wire EegSignalQualityService into hardware-setup wizard"
```

---

## Task 5: Manual dry-run verification

**Files:** none (browser test)

- [x] **Step 1: Ensure environment uses mock device**

`src/app/environments/environment.ts` must have `device: 'mock'`. Confirm:

```bash
grep "device:" src/app/environments/environment.ts
```

Expected: `device: 'mock' as 'mock' | 'neurosity' | 'muse',`

If it says `'muse'`, temporarily change to `'mock'` for this test.

- [x] **Step 2: Start dev server**

```bash
npm start
```

Open http://localhost:4200/capture in Chrome.

- [x] **Step 3: Walk through the wizard to the EEG step**

1. Click through prep → left glove (mock: connect instantly) → right glove → camera → EEG step
2. On the EEG step, enter credentials `test@example.com` / `password123` and click "EEG Headset verbinden"
3. Wait 1 s for mock connect delay

- [x] **Step 4: Observe signal quality animation**

Expected sequence:
- Headset connects → 4 electrode dots appear (red — `'poor'`, flat phase)
- Label shows: `"Elektroden prüfen"`
- After ≈1.5 s → dots turn green (`'good'`, sinusoidal phase)
- Label shows: `"Stabilisierung…"` (amber)
- "Weiter" button remains disabled
- After ≈3 s of green → label switches to `"Signal bereit ✓"` (green)
- "Weiter" button enables

- [x] **Step 5: Restore environment if changed**

If you temporarily set `device: 'mock'`, restore to original value and save.

---

## Self-Review

### Spec coverage

| Spec requirement | Task |
|-----------------|------|
| `EegSignalQualityService.startMonitoring / stopMonitoring` | Task 2 |
| `quality$` per-electrode variance classification | Task 2 |
| `'unknown'` before 128 samples | Task 1 + 2 |
| NaN → `'poor'` | Task 1 + 2 |
| `MIN_VARIANCE` / `MAX_VARIANCE` named constants | Task 2 |
| `gateOpen$` — ≥3/4 good for 3 s | Task 1 + 2 |
| Gate resets on quality drop | Task 1 + 2 |
| `rawEeg$ = undefined` → gate passes immediately | Task 1 + 2 |
| `stopMonitoring` unsubscribes | Task 1 + 2 |
| Mock dry-run simulated stream | Task 3 |
| Electrode dot UI in wizard | Task 4 |
| `canContinue` gated on `eegGateOpen` | Task 4 |
| `effect()` starts/stops monitoring | Task 4 |
| `ngOnDestroy` cleanup | Task 4 |

### Type consistency

- `EegReading` from `brain-device.ts` — used in service, spec, mock ✓
- `ElectrodeQuality` / `ContactState` defined in service, imported in component via `eegQuality` signal ✓
- `gateOpen$: Observable<boolean>` — `toSignal` in component → `eegGateOpen: Signal<boolean>` ✓
- `quality$: Observable<ElectrodeQuality[]>` — `toSignal` → `eegQuality: Signal<ElectrodeQuality[]>` ✓
- `canContinue()` case `'eeg'` uses `this.eegGateOpen()` — Signal, not Observable ✓

### Placeholder scan

None found.
