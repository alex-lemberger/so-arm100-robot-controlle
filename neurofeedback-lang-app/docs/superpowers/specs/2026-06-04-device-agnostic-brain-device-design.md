# Device-Agnostic Brain Device Abstraction — Design

**Date:** 2026-06-04
**Status:** Approved (design), pending implementation plan

## Goal

Decouple the app from the Neurosity Crown so any neurofeedback device (or
mock) can supply focus/calm metrics behind a single vendor-neutral boundary.
Today the headset SDK is already sealed in one file; this work formalizes the
contract so adding a device is one new file, not a refactor.

## Scope

**In scope:** Extract a `BrainDevice` abstraction (abstract class doubling as
the Angular DI token), make `NeurosityService` and `MockNeurosityService`
conform, drive device selection from `environment.ts` via a provider factory in
`main.ts`, migrate the three consumer injection sites, and remove a dead
Firestore method that leaks into the device service.

**Out of scope:** No new real device adapter (e.g. Muse/OpenBCI) — that becomes
one new file later. No runtime device picker (selection is build/env config).
No fix for the pre-existing `@neurosity/sdk`-under-Karma test breakage.

## Decisions

- **Metric model:** focus/calm core (unchanged, app keeps working) plus an
  optional `extras$` bag for device-specific metrics (alpha/beta/theta, signal
  quality). Nothing consumes `extras$` yet; it is room to grow.
- **Device selection:** env/build config (`environment.device`), matching the
  existing `useMockData` pattern. Switching devices = rebuild.
- **Abstraction shape:** abstract class as the DI token (Angular-idiomatic — one
  symbol is both compile-time type and runtime injection token).

## Current coupling (verified)

- `@neurosity/sdk` (`Notion`) is imported in exactly one file:
  `neurosity.service.ts` (+ its spec). Nothing else touches the SDK.
- Actual consumed surface across the app today is only `focus$` + `calm$`:
  - `LearningSessionService` subscribes to `focus$`/`calm$`.
  - `dashboard.component` does `combineLatest([focus$, calm$])`.
- `LoginComponent` authenticates via **Firebase Auth**, not the device — the
  device's `login(email, password)` is never called by any component.
- `NeurosityService.getFirestoreData()` reads the Firestore `neuro` collection,
  has **zero callers**, and is unrelated to a brain device → dead code + layering
  leak, to be deleted.

## 1. The `BrainDevice` contract

New file: `src/app/core/neurofeedback/brain-device.ts`

```ts
import { Observable } from 'rxjs';

export interface DeviceState {
  isLoggedIn: boolean;   // connected/authenticated
  error: string | null;
}

export interface DeviceStatus {
  state: string;         // 'online' | 'offline' | ...
  battery?: { level: number; charging: boolean };
  sampling?: { rate: number };
}

export abstract class BrainDevice {
  // Primary metrics the app consumes (0–1, null = no data yet)
  abstract readonly focus$: Observable<number | null>;
  abstract readonly calm$: Observable<number | null>;

  // Connection/auth state
  abstract readonly state$: Observable<DeviceState>;

  // Optional device-specific extras (alpha/beta/theta, signal quality, …)
  abstract readonly extras$?: Observable<Record<string, number>>;

  // Lifecycle — credentials optional (USB/BT devices need none)
  abstract connect(credentials?: { email: string; password: string }): Promise<void>;
  abstract disconnect(): Promise<void>;
  abstract getStatus(): Promise<DeviceStatus>;
}
```

- `focus$`/`calm$`/`state$` typed as `Observable` (consumers only read); impls
  back them with `BehaviorSubject` internally.
- `connect()`/`disconnect()` are vendor-neutral renames of `login()`/`logout()`.
  Credentials optional so non-account devices fit.
- `extras$` optional; mock and Neurosity leave it undefined for now.
- `getFirestoreData()` is intentionally absent (see §2).

## 2. Implementations + cleanup

**`NeurosityService extends BrainDevice`:**
- Rename `login()`→`connect()`, `logout()`→`disconnect()`. Internal
  `notion.login/logout` calls unchanged.
- `focus$`/`calm$`/`state$` already match the abstract members.
- Delete `getFirestoreData()` (dead, mislocated). If the `Firestore` constructor
  dependency becomes unused after removal, drop it from the constructor (and from
  the factory `deps` in §3). Verify during implementation.
- `@neurosity/sdk` import stays sealed in this one file.

**`MockNeurosityService extends BrainDevice`:**
- Rename `login()`→`connect()`, `logout()`→`disconnect()`. Keep the hardcoded-
  credential gate (mock stream starts on connect with
  `test@example.com` / `password123`).
- Already exposes `focus$`/`calm$`/`state$`/`getStatus` — conforms after rename.

**Naming:** concrete class names stay (`NeurosityService`,
`MockNeurosityService`) — accurate descriptions of what each is. Only the shared
token/type is vendor-neutral (`BrainDevice`). A future device =
`MuseDeviceService extends BrainDevice`, new file.

## 3. Env config + provider factory

**`environment.ts`** — add an explicit device knob:

```ts
device: 'mock' as 'mock' | 'neurosity',   // active brain device
```

Keep `neurosityDeviceId`. `useMockData` is untouched — it still governs
exercise/dashboard data sources. Device selection becomes its own knob,
independent of `useMockData`.

**`main.ts`** — replace the hardcoded override:

```ts
// before
{ provide: NeurosityService, useClass: MockNeurosityService }

// after
{
  provide: BrainDevice,
  useFactory: (firestore: Firestore) =>
    environment.device === 'neurosity'
      ? new NeurosityService(firestore)
      : new MockNeurosityService(),
  deps: [Firestore],
}
```

Factory picks the impl by env at bootstrap. Adding a device = one branch + one
import. If `NeurosityService` no longer needs `Firestore` after §2, drop it from
the factory and `deps`.

## 4. Consumer migration

Three injection sites swap the concrete class for the `BrainDevice` token;
behavior identical (they already use only the shared surface).

- `LearningSessionService` — inject `private device: BrainDevice`;
  `this.neurosityService.focus$/calm$` → `this.device.focus$/calm$`.
- `dashboard.component.ts` — inject `private device: BrainDevice`;
  `combineLatest([this.device.focus$, this.device.calm$])`.
- `main.ts` — provider handled in §3; the concrete classes stay imported because
  the factory references them.

No template changes. No other files touch the device.

## 5. Error handling + testing

**Error handling:** unchanged contract → unchanged behavior. Errors flow through
`state$.error` (both impls already set it). `focus$`/`calm$` emit `null` with no
data; consumers already null-check. The factory is a pure sync pick and cannot
fail.

**Testing:**
- `neurosity.service.spec.ts` — update for the `connect()`/`disconnect()` renames
  and removed `getFirestoreData()`. NOTE: this spec is part of the suite that is
  currently red because `@neurosity/sdk`'s browser bundle throws
  `parcelRequire is not defined` under Karma/webpack. That breakage is
  pre-existing and out of scope; the renames will not make it green.
- Add a mock-backed test (`brain-device.spec.ts` or extend the mock spec):
  assert `MockNeurosityService` satisfies `BrainDevice`, `connect()` starts the
  stream, `disconnect()` nulls `focus$`/`calm$`. Mock has no SDK → runs clean.
- The abstraction is verifiable green via the mock, independent of the
  Neurosity/Karma issue.

**Verification before done:** `ng build` passes; mock-backed app serves and
streams focus/calm after connect (`test@example.com` / `password123`).

## Future work (not now)

- Real second adapter (Muse `muse-js`, OpenBCI, or a generic WebSocket/LSL
  source) implementing `BrainDevice` with a bands→focus/calm adapter.
- Surface `extras$` in the dashboard once a device provides extra channels.
- Optional runtime device picker (registry + UI) if hot-swap is ever needed.
- Fix `@neurosity/sdk`-under-Karma so the real-device spec can run green.
