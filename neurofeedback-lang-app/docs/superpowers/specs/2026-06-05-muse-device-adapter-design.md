# Muse 2 Device Adapter — Design

**Date:** 2026-06-05
**Status:** Approved (design), pending implementation plan

## Goal

Add a `MuseDeviceService` that implements the `BrainDevice` contract using the
`muse-js` library (Web Bluetooth). Selecting `device: 'muse'` in `environment.ts`
routes the provider factory to this adapter. No other files change behaviour.

## Scope

**In scope:**
- Install `muse-js` npm package.
- `MuseDeviceService extends BrainDevice` in one new file.
- Raw EEG → sliding-window FFT → band powers → normalised `focus$` / `calm$`.
- `extras$` carrying raw relative band powers `{ alpha, beta, theta }`.
- `'muse'` added to `environment.device` union + factory branch in `main.ts`.
- Unit tests with a mocked `MuseClient` (no hardware).

**Out of scope:**
- Runtime device picker UI.
- Electrode signal-quality checks.
- Blink/jaw-clench artefact rejection.
- Any change to `FlowDetectorService`, dashboard, or other consumers.

## Dependencies

| Package | Version | Role |
|---------|---------|------|
| `muse-js` | `^3.3.0` | Web Bluetooth MuseClient + EEG stream |

No FFT library needed — a minimal Goertzel / DFT helper is implemented inline
(avoids a large dependency for a small fixed set of frequency bands).

## Architecture

### EEG pipeline

```
MuseClient.eegReadings          Observable<EEGReading>
  └─ filter electrode TP9/AF7/AF8/TP10
  └─ map samples[]
  └─ bufferCount(256, 64)        sliding window: 256 samples, step 64 (~250 ms @ 256 Hz)
  └─ map → bandPowers(window)    inline DFT → { theta, alpha, beta } absolute powers
  └─ map → normalisedMetrics     relative powers (each / sum), mapped to 0–1
  └─ shareReplay(1)
```

Four electrodes are averaged before windowing to reduce noise.

### Band definitions

| Band | Range | Maps to |
|------|-------|---------|
| Theta | 4–8 Hz | component of `calm$` |
| Alpha | 8–13 Hz | primary driver of `calm$` |
| Beta | 13–30 Hz | primary driver of `focus$` |

### Metric formulas

```
total  = theta + alpha + beta

focus$ = beta  / total          (0–1, higher = more focused)
calm$  = alpha / total          (0–1, higher = more calm/relaxed)
extras$ = { theta: theta/total, alpha: alpha/total, beta: beta/total }
```

Relative power fractions are naturally bounded 0–1 and comparable across
sessions without session-level normalisation.

## 1. `MuseDeviceService` contract

```ts
@Injectable()                         // NOT providedIn:'root' — factory-provided
export class MuseDeviceService extends BrainDevice implements OnDestroy {
  readonly focus$:  BehaviorSubject<number | null>
  readonly calm$:   BehaviorSubject<number | null>
  readonly state$:  BehaviorSubject<DeviceState>
  readonly extras$: BehaviorSubject<Record<string, number>>

  async connect(): Promise<void>      // Web Bluetooth pairing → start streaming
  async disconnect(): Promise<void>   // stop streaming + disconnect client
  async getStatus(): Promise<DeviceStatus>  // battery from telemetryData
  ngOnDestroy(): void                 // cleanup subscriptions
}
```

`connect()` takes no credentials (Muse uses Web Bluetooth pairing, not
account login). Calling `connect()` while already connected is a no-op.

## 2. Inline DFT helper

A small pure function `bandPowers(samples: number[], sampleRate: number): BandPowers`
using the Goertzel algorithm for the fixed set of frequencies. Exported
separately so it can be unit-tested in isolation without a MuseClient.

```ts
interface BandPowers { theta: number; alpha: number; beta: number; }

function bandPowers(samples: number[], sampleRate = 256): BandPowers
```

Goertzel evaluates power at discrete frequency bins cheaply — no full FFT
needed for 3 bands.

## 3. Environment + factory

**`environment.ts`** — extend the device union:

```ts
device: 'mock' as 'mock' | 'neurosity' | 'muse',
```

**`main.ts`** — add a branch:

```ts
environment.device === 'muse'      ? new MuseDeviceService()
environment.device === 'neurosity' ? new NeurosityService()
                                   : new MockNeurosityService()
```

## 4. Testing strategy

All tests run without hardware via a `FakeMuseClient` stub:

- `bandPowers()` unit tests: feed synthetic sine waves at known frequencies
  (e.g. 10 Hz pure sine → alpha power dominates → calm$ near 1.0).
- `MuseDeviceService` integration tests: `FakeMuseClient` exposes a
  `Subject<EEGReading>` so tests push synthetic readings and assert
  `focus$` / `calm$` values.
- `connect()` / `disconnect()` lifecycle: assert state$ transitions.
- `getStatus()` returns correct battery level from fake telemetry.

No `@angular/core/testing` TestBed needed for `bandPowers` (pure function).
Service tests use TestBed with `{ provide: MuseClient, useValue: fakeClient }`.

## 5. Error handling

- Web Bluetooth unavailable (non-Chrome): `connect()` rejects, `state$.error`
  set to `'Web Bluetooth not supported'`.
- User cancels pairing dialog: `connect()` rejects with BT error message.
- Connection drop mid-session: `connectionStatus` false → `state$` set to
  `{ isLoggedIn: false, error: 'Connection lost' }`, `focus$`/`calm$` emit
  `null`.

## 6. Verification

- `ng build --configuration development` passes.
- `ng test --include='**/muse-device.service.spec.ts'` — all specs green
  (no hardware, no Web Bluetooth required).
- Manual: set `device: 'muse'`, serve app, confirm no console errors at boot
  (Bluetooth dialog only appears on `connect()` call, not at startup).

## Future work (not now)

- Signal quality / headband-fit indicator via `client.telemetryData`.
- Artefact rejection (jaw clench detection via `client.accelerometerData`).
- Per-electrode band powers exposed through `extras$` for richer dashboard.
- Runtime device picker if hot-swap ever needed.
