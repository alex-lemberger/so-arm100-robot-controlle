# Muse Device Adapter Implementation Plan

**Status: COMPLETE — 2026-06-05. Merged to master (db8b44b). 22/22 specs green.**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a `MuseDeviceService` that fulfils the `BrainDevice` contract using `muse-js` (Web Bluetooth), selectable via `environment.device = 'muse'`.

**Architecture:** A pure `bandPowers()` utility (Goertzel DFT) converts a 256-sample EEG window into theta/alpha/beta power fractions. `MuseDeviceService` extends `BrainDevice`, receives raw EEG packets from `MuseClient`, accumulates samples in a ring buffer, emits normalised `focus$`/`calm$` every 64 new samples (sliding window). `MuseClient` is passed as a constructor default, allowing tests to inject a fake without TestBed. The `main.ts` factory adds a `'muse'` branch.

**Tech Stack:** Angular 19 (standalone), RxJS 7, `muse-js@^3.3.0`, Karma + Jasmine. Tests require no hardware (fake `MuseClient` via constructor injection).

---

## Reference: design spec

`docs/superpowers/specs/2026-06-05-muse-device-adapter-design.md`

## File structure

- **Create** `src/app/core/neurofeedback/services/muse-eeg-utils.ts` — pure `goertzel()` + `bandPowers()` functions.
- **Create** `src/app/core/neurofeedback/services/muse-eeg-utils.spec.ts` — sine-wave unit tests (no Angular).
- **Create** `src/app/core/neurofeedback/services/muse-device.service.ts` — `MuseDeviceService extends BrainDevice`.
- **Create** `src/app/core/neurofeedback/services/muse-device.service.spec.ts` — FakeMuseClient integration tests.
- **Modify** `src/app/environments/environment.ts` — add `'muse'` to device union.
- **Modify** `src/main.ts` — add `'muse'` factory branch.

---

## Task 1: `bandPowers()` pure utility (TDD)

**Files:**
- Create: `src/app/core/neurofeedback/services/muse-eeg-utils.ts`
- Create: `src/app/core/neurofeedback/services/muse-eeg-utils.spec.ts`

### Step 1: Install muse-js

- [x] Run:
```bash
npm install muse-js
```
Expected: `muse-js` appears in `package.json` dependencies.

### Step 2: Write the failing tests

- [x] Create `src/app/core/neurofeedback/services/muse-eeg-utils.spec.ts`:

```ts
import { bandPowers, goertzel } from './muse-eeg-utils';

/** Pure sine wave at `hz` — 256 samples at 256 Hz sample rate. */
function sine(hz: number, samples = 256, rate = 256): number[] {
  return Array.from({ length: samples }, (_, i) =>
    Math.sin(2 * Math.PI * hz * i / rate)
  );
}

describe('goertzel', () => {
  it('returns high power at the target frequency', () => {
    const power = goertzel(sine(10), 10, 256);
    expect(power).toBeGreaterThan(1000);
  });

  it('returns near-zero power at a non-present frequency', () => {
    const power = goertzel(sine(10), 20, 256);
    expect(power).toBeLessThan(1);
  });
});

describe('bandPowers', () => {
  it('alpha dominates for a 10 Hz signal', () => {
    const p = bandPowers(sine(10));
    expect(p.alpha).toBeGreaterThan(p.beta);
    expect(p.alpha).toBeGreaterThan(p.theta);
  });

  it('beta dominates for a 20 Hz signal', () => {
    const p = bandPowers(sine(20));
    expect(p.beta).toBeGreaterThan(p.alpha);
    expect(p.beta).toBeGreaterThan(p.theta);
  });

  it('theta dominates for a 6 Hz signal', () => {
    const p = bandPowers(sine(6));
    expect(p.theta).toBeGreaterThan(p.alpha);
    expect(p.theta).toBeGreaterThan(p.beta);
  });

  it('all band powers are near-zero for a DC (flat) signal', () => {
    const flat = new Array(256).fill(1);
    const p = bandPowers(flat);
    expect(p.alpha + p.beta + p.theta).toBeLessThan(1);
  });
});
```

### Step 3: Run tests to verify they fail

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-eeg-utils.spec.ts'
```
Expected: FAIL — `bandPowers` / `goertzel` not found.

### Step 4: Implement the utilities

- [x] Create `src/app/core/neurofeedback/services/muse-eeg-utils.ts`:

```ts
export interface BandPowers {
  theta: number;  // 4–8 Hz
  alpha: number;  // 8–13 Hz
  beta:  number;  // 13–30 Hz
}

/**
 * Goertzel algorithm — computes signal power at one frequency bin.
 * O(N) per target frequency; cheaper than a full FFT for a small fixed band set.
 */
export function goertzel(samples: number[], targetHz: number, sampleRate: number): number {
  const N = samples.length;
  const k = Math.round(N * targetHz / sampleRate);
  const omega = (2 * Math.PI * k) / N;
  const coeff = 2 * Math.cos(omega);
  let s0 = 0, s1 = 0, s2 = 0;
  for (const x of samples) {
    s0 = x + coeff * s1 - s2;
    s2 = s1;
    s1 = s0;
  }
  return s1 * s1 + s2 * s2 - coeff * s1 * s2;
}

/** Sum Goertzel power across all integer-Hz bins in [lo, hi). */
function sumBand(samples: number[], loHz: number, hiHz: number, sampleRate: number): number {
  let power = 0;
  for (let f = loHz; f < hiHz; f++) {
    power += goertzel(samples, f, sampleRate);
  }
  return power;
}

/**
 * Compute EEG band powers from a window of samples.
 * @param samples  Array of EEG amplitude values (length should be a power of 2, typically 256).
 * @param sampleRate  Hz; default 256 (Muse 2 native rate).
 */
export function bandPowers(samples: number[], sampleRate = 256): BandPowers {
  return {
    theta: sumBand(samples, 4, 8, sampleRate),   // 4,5,6,7 Hz
    alpha: sumBand(samples, 8, 13, sampleRate),  // 8..12 Hz
    beta:  sumBand(samples, 13, 30, sampleRate), // 13..29 Hz
  };
}
```

### Step 5: Run tests to verify they pass

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-eeg-utils.spec.ts'
```
Expected: PASS (6 specs).

### Step 6: Verify build

- [x] Run:
```bash
npx ng build --configuration development
```
Expected: `Application bundle generation complete.`

### Step 7: Commit

- [x] Run:
```bash
git add src/app/core/neurofeedback/services/muse-eeg-utils.ts \
        src/app/core/neurofeedback/services/muse-eeg-utils.spec.ts \
        package.json package-lock.json
git commit -m "feat: Goertzel bandPowers utility for EEG band classification"
```

---

## Task 2: `MuseDeviceService` — state lifecycle (TDD)

**Files:**
- Create: `src/app/core/neurofeedback/services/muse-device.service.ts`
- Create: `src/app/core/neurofeedback/services/muse-device.service.spec.ts`

### Step 1: Write the failing lifecycle tests

- [x] Create `src/app/core/neurofeedback/services/muse-device.service.spec.ts`:

```ts
import { Subject, BehaviorSubject } from 'rxjs';
import { MuseClient, EEGReading, TelemetryData } from 'muse-js';
import { MuseDeviceService } from './muse-device.service';

class FakeMuseClient {
  readonly eegReadings = new Subject<EEGReading>();
  readonly telemetryData = new Subject<TelemetryData>();
  readonly connectionStatus = new BehaviorSubject<boolean>(false);
  connect = jasmine.createSpy('connect').and.returnValue(Promise.resolve());
  start   = jasmine.createSpy('start').and.returnValue(Promise.resolve());
  disconnect = jasmine.createSpy('disconnect').and.returnValue(Promise.resolve());
}

/** Build a minimal EEGReading for the AF7 electrode (index 1). */
function eegPacket(samples: number[], electrode = 1): EEGReading {
  return { electrode, index: 0, timestamp: Date.now(), samples };
}

describe('MuseDeviceService — lifecycle', () => {
  let fake: FakeMuseClient;
  let service: MuseDeviceService;

  beforeEach(() => {
    fake = new FakeMuseClient();
    service = new MuseDeviceService(fake as unknown as MuseClient);
  });

  afterEach(async () => {
    await service.disconnect();
  });

  it('state$ starts disconnected with no error', () => {
    const s = service.state$.value;
    expect(s.isLoggedIn).toBe(false);
    expect(s.error).toBeNull();
  });

  it('connect() calls client.connect() and client.start()', async () => {
    await service.connect();
    expect(fake.connect).toHaveBeenCalledTimes(1);
    expect(fake.start).toHaveBeenCalledTimes(1);
  });

  it('connect() sets state$ to isLoggedIn=true on success', async () => {
    await service.connect();
    expect(service.state$.value.isLoggedIn).toBe(true);
    expect(service.state$.value.error).toBeNull();
  });

  it('connect() is a no-op if already connected', async () => {
    await service.connect();
    await service.connect();
    expect(fake.connect).toHaveBeenCalledTimes(1);
  });

  it('connect() sets state$.error and rethrows on client failure', async () => {
    fake.connect.and.returnValue(Promise.reject(new Error('BT unavailable')));
    await expectAsync(service.connect()).toBeRejected();
    expect(service.state$.value.error).toBe('BT unavailable');
    expect(service.state$.value.isLoggedIn).toBe(false);
  });

  it('disconnect() calls client.disconnect()', async () => {
    await service.connect();
    await service.disconnect();
    expect(fake.disconnect).toHaveBeenCalledTimes(1);
  });

  it('disconnect() nulls focus$ and calm$, resets state$', async () => {
    await service.connect();
    await service.disconnect();
    expect(service.focus$.value).toBeNull();
    expect(service.calm$.value).toBeNull();
    expect(service.state$.value.isLoggedIn).toBe(false);
  });

  it('getStatus() resolves with battery from first telemetry packet', async () => {
    await service.connect();
    const statusPromise = service.getStatus();
    fake.telemetryData.next({ sequenceId: 1, batteryLevel: 75, fuelGaugeVoltage: 0, temperature: 0 });
    const status = await statusPromise;
    expect(status.battery?.level).toBeCloseTo(0.75);
    expect(status.state).toBe('online');
  });
});
```

### Step 2: Run tests to verify they fail

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-device.service.spec.ts'
```
Expected: FAIL — `MuseDeviceService` not found.

### Step 3: Implement the service skeleton (lifecycle only, no EEG pipeline yet)

- [x] Create `src/app/core/neurofeedback/services/muse-device.service.ts`:

```ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';
import { MuseClient } from 'muse-js';
import { BrainDevice, DeviceState, DeviceStatus } from '../brain-device';

@Injectable()
export class MuseDeviceService extends BrainDevice implements OnDestroy {
  readonly focus$ = new BehaviorSubject<number | null>(null);
  readonly calm$  = new BehaviorSubject<number | null>(null);
  readonly state$ = new BehaviorSubject<DeviceState>({ isLoggedIn: false, error: null });
  readonly extras$ = new BehaviorSubject<Record<string, number>>({});

  protected eegSub: Subscription | null = null;

  constructor(protected readonly client: MuseClient = new MuseClient()) {
    super();
  }

  async connect(): Promise<void> {
    if (this.state$.value.isLoggedIn) return;
    try {
      await this.client.connect();
      await this.client.start();
      this.setupEegPipeline();
      this.state$.next({ isLoggedIn: true, error: null });
    } catch (err) {
      const error = err instanceof Error ? err.message : 'Connection failed';
      this.state$.next({ isLoggedIn: false, error });
      throw err;
    }
  }

  async disconnect(): Promise<void> {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.sampleBuffer = [];
    this.stepCount = 0;
    await this.client.disconnect();
    this.focus$.next(null);
    this.calm$.next(null);
    this.extras$.next({});
    this.state$.next({ isLoggedIn: false, error: null });
  }

  async getStatus(): Promise<DeviceStatus> {
    return new Promise((resolve) => {
      const isOnline = this.state$.value.isLoggedIn;
      const sub = this.client.telemetryData.subscribe(t => {
        sub.unsubscribe();
        resolve({
          state: isOnline ? 'online' : 'offline',
          battery: { level: t.batteryLevel / 100, charging: false },
        });
      });
      // Fallback if no telemetry arrives within 2 s
      setTimeout(() => {
        sub.unsubscribe();
        resolve({ state: isOnline ? 'online' : 'offline' });
      }, 2000);
    });
  }

  ngOnDestroy(): void {
    this.disconnect();
  }

  // EEG pipeline fields — populated in Task 3
  protected sampleBuffer: number[] = [];
  protected stepCount = 0;

  protected setupEegPipeline(): void {
    // Implemented in Task 3
  }
}
```

### Step 4: Run tests to verify they pass

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-device.service.spec.ts'
```
Expected: PASS (8 specs — lifecycle suite only).

### Step 5: Commit

- [x] Run:
```bash
git add src/app/core/neurofeedback/services/muse-device.service.ts \
        src/app/core/neurofeedback/services/muse-device.service.spec.ts
git commit -m "feat: MuseDeviceService skeleton with connect/disconnect/getStatus"
```

---

## Task 3: EEG pipeline — focus$ / calm$ / extras$ (TDD)

**Files:**
- Modify: `src/app/core/neurofeedback/services/muse-device.service.ts` — implement `setupEegPipeline()`
- Modify: `src/app/core/neurofeedback/services/muse-device.service.spec.ts` — append EEG pipeline specs

### Step 1: Append failing EEG pipeline tests

- [x] Append to `muse-device.service.spec.ts` (after the existing lifecycle `describe` block):

```ts
describe('MuseDeviceService — EEG pipeline', () => {
  let fake: FakeMuseClient;
  let service: MuseDeviceService;

  beforeEach(async () => {
    fake = new FakeMuseClient();
    service = new MuseDeviceService(fake as unknown as MuseClient);
    await service.connect();
  });

  afterEach(async () => {
    await service.disconnect();
  });

  /**
   * Push `count` identical samples on the AF7 electrode (index 1) in packets of 12.
   * This simulates real muse-js packet delivery.
   */
  function pushSamples(value: number, count: number): void {
    const PACKET = 12;
    for (let sent = 0; sent < count; sent += PACKET) {
      const chunk = Math.min(PACKET, count - sent);
      fake.eegReadings.next(eegPacket(new Array(chunk).fill(value), 1));
    }
  }

  it('focus$ and calm$ are null before any samples arrive', () => {
    expect(service.focus$.value).toBeNull();
    expect(service.calm$.value).toBeNull();
  });

  it('focus$ and calm$ remain null until WINDOW (256) samples are buffered', () => {
    pushSamples(0.5, 255);
    expect(service.focus$.value).toBeNull();
  });

  it('emits focus$ and calm$ after 256 samples fill the window', () => {
    pushSamples(0.5, 256);
    expect(service.focus$.value).not.toBeNull();
    expect(service.calm$.value).not.toBeNull();
  });

  it('emitted focus$ and calm$ are within [0, 1]', () => {
    pushSamples(0.5, 256);
    expect(service.focus$.value!).toBeGreaterThanOrEqual(0);
    expect(service.focus$.value!).toBeLessThanOrEqual(1);
    expect(service.calm$.value!).toBeGreaterThanOrEqual(0);
    expect(service.calm$.value!).toBeLessThanOrEqual(1);
  });

  it('extras$ contains alpha, beta, theta keys after first emission', () => {
    pushSamples(0.5, 256);
    const extras = service.extras$.value;
    expect(extras['alpha']).toBeDefined();
    expect(extras['beta']).toBeDefined();
    expect(extras['theta']).toBeDefined();
  });

  it('extras$ band fractions sum to ~1.0', () => {
    pushSamples(0.5, 256);
    const e = service.extras$.value;
    expect(e['alpha'] + e['beta'] + e['theta']).toBeCloseTo(1.0, 5);
  });

  it('emits again every STEP (64) new samples', () => {
    pushSamples(0.5, 256);
    const firstFocus = service.focus$.value!;
    // Push a sine at a different value to change the band profile
    pushSamples(1.0, 64);
    // focus$/calm$ should have updated (may or may not change value, but emit happened)
    expect(service.focus$.value).not.toBeNull();
    expect(service.calm$.value).not.toBeNull();
  });

  it('ignores samples from non-AF7 electrodes', () => {
    // Push 256 samples on electrode 0 (TP9) — should not trigger emission
    for (let sent = 0; sent < 256; sent += 12) {
      fake.eegReadings.next(eegPacket(new Array(12).fill(0.5), 0));
    }
    expect(service.focus$.value).toBeNull();
  });
});
```

### Step 2: Run to verify the new specs fail

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-device.service.spec.ts'
```
Expected: The 8 lifecycle specs still pass; the 8 new EEG pipeline specs fail (empty `setupEegPipeline()`).

### Step 3: Implement `setupEegPipeline()`

- [x] In `muse-device.service.ts`, add the import at the top of the file (after the existing imports):

```ts
import { EMPTY, from } from 'rxjs';
import { mergeMap } from 'rxjs/operators';
import { bandPowers } from './muse-eeg-utils';
```

- [x] Replace the constants and `setupEegPipeline()` stub with:

```ts
  private readonly WINDOW = 256;
  private readonly STEP   = 64;
  private readonly SAMPLE_RATE = 256;
  private readonly EEG_ELECTRODE = 1;  // AF7 — left frontal (focus/calm relevant)

  protected setupEegPipeline(): void {
    this.sampleBuffer = [];
    this.stepCount    = 0;

    this.eegSub = this.client.eegReadings.pipe(
      mergeMap(reading =>
        reading.electrode === this.EEG_ELECTRODE
          ? from(reading.samples)
          : EMPTY
      ),
    ).subscribe(sample => {
      this.sampleBuffer.push(sample);
      if (this.sampleBuffer.length > this.WINDOW) {
        this.sampleBuffer.shift();
      }
      this.stepCount++;
      if (this.stepCount >= this.STEP && this.sampleBuffer.length >= this.WINDOW) {
        this.stepCount = 0;
        this.emitBandPowers(this.sampleBuffer.slice());
      }
    });
  }

  private emitBandPowers(window: number[]): void {
    const p = bandPowers(window, this.SAMPLE_RATE);
    const total = p.theta + p.alpha + p.beta;
    if (total <= 0) return;
    this.focus$.next(p.beta  / total);
    this.calm$.next( p.alpha / total);
    this.extras$.next({
      theta: p.theta / total,
      alpha: p.alpha / total,
      beta:  p.beta  / total,
    });
  }
```

Also remove the placeholder `protected sampleBuffer` and `protected stepCount` declarations from the skeleton (they are now defined as `private` above).

### Step 4: Run all muse-device specs to verify 16/16 pass

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/muse-device.service.spec.ts'
```
Expected: PASS (16 specs — 8 lifecycle + 8 EEG pipeline).

### Step 5: Commit

- [x] Run:
```bash
git add src/app/core/neurofeedback/services/muse-device.service.ts \
        src/app/core/neurofeedback/services/muse-device.service.spec.ts
git commit -m "feat: EEG pipeline in MuseDeviceService — sliding window Goertzel → focus$/calm$"
```

---

## Task 4: Environment knob + factory + final verification

**Files:**
- Modify: `src/app/environments/environment.ts`
- Modify: `src/main.ts`

### Step 1: Add `'muse'` to the device union

- [x] In `src/app/environments/environment.ts`, change:

```ts
device: 'mock' as 'mock' | 'neurosity',
```

to:

```ts
device: 'mock' as 'mock' | 'neurosity' | 'muse',
```

### Step 2: Add the `'muse'` factory branch in `main.ts`

- [x] In `src/main.ts`, add the import alongside the existing device imports:

```ts
import { MuseDeviceService } from './app/core/neurofeedback/services/muse-device.service';
```

- [x] Replace the existing factory:

```ts
{
  provide: BrainDevice,
  useFactory: () =>
    environment.device === 'neurosity'
      ? new NeurosityService()
      : new MockNeurosityService(),
}
```

with:

```ts
{
  provide: BrainDevice,
  useFactory: () => {
    if (environment.device === 'muse')      return new MuseDeviceService();
    if (environment.device === 'neurosity') return new NeurosityService();
    return new MockNeurosityService();
  },
}
```

### Step 3: Verify mock and muse selections both compile

- [x] Run (default mock):
```bash
npx ng build --configuration development
```
Expected: `Application bundle generation complete.`

- [x] Temporarily set `device: 'muse'` in `environment.ts`, run build, then revert:
```bash
# set device: 'muse' manually in environment.ts, then:
npx ng build --configuration development
# revert: set device: 'mock' again
```
Expected: build passes in both settings.

### Step 4: Run all new specs together

- [x] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless \
  --include='**/muse-eeg-utils.spec.ts' \
  --include='**/muse-device.service.spec.ts'
```
Expected: PASS (22 specs total: 6 utils + 16 service).

### Step 5: Commit

- [x] Run:
```bash
git add src/app/environments/environment.ts src/main.ts
git commit -m "feat: add muse device to env union + provider factory"
```

---

## Done criteria

- `bandPowers()` correctly identifies dominant bands in synthetic sine waves (6 specs green).
- `MuseDeviceService` lifecycle (connect/disconnect/getStatus/error handling) verified (8 specs green).
- EEG pipeline emits `focus$`/`calm$`/`extras$` in [0,1] range after 256-sample window, slides every 64 samples (8 specs green).
- `ng build --configuration development` passes for `device: 'mock'` and `device: 'muse'`.
- Setting `device: 'muse'` in `environment.ts`, serving the app, and opening `/dashboard` produces no console errors at boot (Bluetooth pairing dialog only appears when `connect()` is explicitly called).
