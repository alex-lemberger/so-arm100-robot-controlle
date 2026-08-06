# Device-Agnostic BrainDevice Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Neurosity-specific device coupling with a vendor-neutral `BrainDevice` abstraction so any device (or the mock) plugs in behind one DI token, selected by env config.

**Architecture:** An abstract class `BrainDevice` doubles as the Angular DI token and compile-time type. `NeurosityService` and `MockNeurosityService` extend it (renaming `login/logout` → `connect/disconnect`). A factory in `main.ts` picks the impl from `environment.device`. Consumers inject `BrainDevice` instead of the concrete class. A dead Firestore method is removed from the device service.

**Tech Stack:** Angular 19 (standalone), RxJS 7, NGXS, Karma + Jasmine, `@neurosity/sdk`.

---

## Reference: design spec

`docs/superpowers/specs/2026-06-04-device-agnostic-brain-device-design.md`

## Pre-existing condition (do not try to "fix" here)

The Karma suite is **already red** before any change: `@neurosity/sdk`'s browser bundle throws `parcelRequire is not defined` under Karma/webpack, which cascades into an AppComponent injector error. This is out of scope. Consequence: tests that import (directly or transitively) `NeurosityService` cannot run green. Therefore:

- New behavior is verified with **mock-only** tests (no SDK import) — these run green.
- Changes to `NeurosityService` and its spec are verified by **`ng build`** (TypeScript compile), not by running Karma.

## File structure

- Create: `src/app/core/neurofeedback/brain-device.ts` — the abstract contract + `DeviceState`/`DeviceStatus` interfaces.
- Create: `src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts` — mock conformance + lifecycle tests (green).
- Modify: `src/app/core/neurofeedback/services/mock-neurosity.service.ts` — extend `BrainDevice`, rename methods.
- Modify: `src/app/core/neurofeedback/services/neurosity.service.ts` — extend `BrainDevice`, rename methods, delete `getFirestoreData()` + `Firestore` dep.
- Modify: `src/app/core/neurofeedback/services/neurosity.service.spec.ts` — rename method calls (compile-only).
- Modify: `src/app/environments/environment.ts` — add `device` knob.
- Modify: `src/main.ts` — `BrainDevice` provider factory.
- Modify: `src/app/core/neurofeedback/services/learning-session.service.ts` — inject `BrainDevice`.
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` — inject `BrainDevice`.

---

### Task 1: Create the `BrainDevice` contract

**Files:**
- Create: `src/app/core/neurofeedback/brain-device.ts`

- [ ] **Step 1: Write the file**

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

/**
 * Vendor-neutral neurofeedback device contract.
 * Doubles as the Angular DI token (abstract class = runtime token + type).
 * Implementations: NeurosityService (real), MockNeurosityService (synthetic).
 */
export abstract class BrainDevice {
  /** Focus probability stream, 0–1, null until data arrives. */
  abstract readonly focus$: Observable<number | null>;
  /** Calm probability stream, 0–1, null until data arrives. */
  abstract readonly calm$: Observable<number | null>;
  /** Connection/auth state. */
  abstract readonly state$: Observable<DeviceState>;
  /** Optional device-specific extra metrics (alpha/beta/theta, signal quality, …). */
  abstract readonly extras$?: Observable<Record<string, number>>;

  /** Connect/authenticate. Credentials optional (USB/BT devices need none). */
  abstract connect(credentials?: { email: string; password: string }): Promise<void>;
  /** Disconnect and stop streams. */
  abstract disconnect(): Promise<void>;
  /** One-shot device status snapshot. */
  abstract getStatus(): Promise<DeviceStatus>;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `npx ng build`
Expected: build succeeds (no consumers yet; file is standalone). The existing `@neurosity/sdk` non-ESM warning is unrelated and OK.

- [ ] **Step 3: Commit**

```bash
git add src/app/core/neurofeedback/brain-device.ts
git commit -m "feat: add vendor-neutral BrainDevice contract"
```

---

### Task 2: Conform `MockNeurosityService` to `BrainDevice` (TDD)

**Files:**
- Test: `src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts` (create)
- Modify: `src/app/core/neurofeedback/services/mock-neurosity.service.ts`

- [ ] **Step 1: Write the failing test**

Create `src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts`:

```ts
import { fakeAsync, tick } from '@angular/core/testing';
import { BrainDevice } from '../brain-device';
import { MockNeurosityService } from './mock-neurosity.service';

const VALID = { email: 'test@example.com', password: 'password123' };

describe('MockNeurosityService', () => {
  it('satisfies the BrainDevice contract', () => {
    const device: BrainDevice = new MockNeurosityService();
    expect(device).toBeTruthy();
    expect(typeof device.connect).toBe('function');
    expect(typeof device.disconnect).toBe('function');
  });

  it('connect() with valid credentials starts focus/calm stream', fakeAsync(() => {
    const device = new MockNeurosityService();
    device.connect(VALID);
    tick(1000); // resolve the simulated login delay
    tick(1000); // first metrics interval tick
    expect(device.focus$.value).not.toBeNull();
    expect(device.calm$.value).not.toBeNull();
    device.disconnect();
    tick(500);
  }));

  it('connect() rejects invalid credentials', fakeAsync(() => {
    const device = new MockNeurosityService();
    let rejected = false;
    device.connect({ email: 'x', password: 'y' }).catch(() => (rejected = true));
    tick(1000);
    expect(rejected).toBeTrue();
  }));

  it('disconnect() nulls focus/calm', fakeAsync(() => {
    const device = new MockNeurosityService();
    device.connect(VALID);
    tick(2000);
    device.disconnect();
    tick(500);
    expect(device.focus$.value).toBeNull();
    expect(device.calm$.value).toBeNull();
  }));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx ng test --watch=false --browsers=ChromeHeadless --include='**/mock-neurosity.service.spec.ts'`
Expected: FAIL — `device.connect is not a function` (mock still has `login`/`logout`).

- [ ] **Step 3: Implement — extend `BrainDevice`, rename methods**

In `mock-neurosity.service.ts`:

Add import at top (after existing imports):
```ts
import { BrainDevice, DeviceStatus } from '../brain-device';
```

Change the class declaration:
```ts
export class MockNeurosityService extends BrainDevice implements OnDestroy {
```

Add `super()` as the first line of the constructor (line 43-46 becomes):
```ts
  constructor() {
    super();
    this.focus$.next(null);
    this.calm$.next(null);
  }
```

Rename `login` → `connect` and change its signature to take a credentials object (replace the existing `async login(email: string, password: string)` method):
```ts
  async connect(credentials?: { email: string; password: string }): Promise<void> {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (
          credentials?.email === this.mockCredentials.email &&
          credentials?.password === this.mockCredentials.password
        ) {
          this._state.next({ isLoggedIn: true, error: null });
          this.startMockDataStream();
          resolve();
        } else {
          this._state.next({ isLoggedIn: false, error: 'Invalid credentials' });
          reject(new Error('Invalid credentials'));
        }
      }, 1000);
    });
  }
```

Rename `logout` → `disconnect` (change only the method name; body unchanged):
```ts
  async disconnect(): Promise<void> {
```

`getStatus()` already returns the `DeviceStatus` shape — leave it.

- [ ] **Step 4: Run test to verify it passes**

Run: `npx ng test --watch=false --browsers=ChromeHeadless --include='**/mock-neurosity.service.spec.ts'`
Expected: PASS (4 specs).

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/services/mock-neurosity.service.ts src/app/core/neurofeedback/services/mock-neurosity.service.spec.ts
git commit -m "feat: conform MockNeurosityService to BrainDevice contract"
```

---

### Task 3: Conform `NeurosityService`, delete dead Firestore method

**Files:**
- Modify: `src/app/core/neurofeedback/services/neurosity.service.ts`

Verified by `ng build` (this file transitively imports `@neurosity/sdk`, so its Karma spec cannot run green — pre-existing condition).

- [ ] **Step 1: Extend `BrainDevice` and add `super()`**

In `neurosity.service.ts`:

Add import (after existing imports):
```ts
import { BrainDevice, DeviceStatus } from '../brain-device';
```

Change the class declaration:
```ts
export class NeurosityService extends BrainDevice implements OnDestroy {
```

- [ ] **Step 2: Remove the dead Firestore dependency and method**

Delete the `getFirestoreData()` method (currently the last method, lines ~155-157):
```ts
  public getFirestoreData(): Observable<any[]> {
    return collectionData(collection(this.firestore, 'neuro'), { idField: 'id' });
  }
```

Remove now-unused Firestore imports (the line):
```ts
import { collectionData, collection, Firestore } from '@angular/fire/firestore';
```

Change the constructor to zero-arg with `super()` (replace the existing `constructor(private firestore: Firestore) { ... }`):
```ts
  constructor() {
    super();
    this.notion = new Notion({
      deviceId: environment.neurosityDeviceId
    });
    this.checkAuthState();
  }
```

- [ ] **Step 3: Rename `login` → `connect`, `logout` → `disconnect`**

Replace the `async login(email: string, password: string)` method signature and body header so it reads credentials from the object:
```ts
  async connect(credentials?: { email: string; password: string }): Promise<void> {
    if (!credentials) {
      throw new Error('Neurosity device requires email/password credentials');
    }
    try {
      await from(Promise.resolve(this.notion.login({
        email: credentials.email,
        password: credentials.password,
      }))).toPromise();
      this._state.next({ isLoggedIn: true, error: null });
      await this.setupSubscriptions();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Login failed';
      this._state.next({ isLoggedIn: false, error: errorMessage });
      throw new Error(errorMessage);
    }
  }
```

Rename `async logout()` → `async disconnect()` (change only the method name; body unchanged):
```ts
  async disconnect(): Promise<void> {
```

Annotate `getStatus()` return to satisfy the contract — change its signature:
```ts
  async getStatus(): Promise<DeviceStatus> {
```

- [ ] **Step 4: Verify the whole app type-checks**

Run: `npx ng build`
Expected: build succeeds. (If the compiler reports `extras$` missing — it should not, since `extras$?` is optional. If it reports an unused `Observable` import, remove it.)

- [ ] **Step 5: Update the Neurosity spec method names (compile-only)**

In `neurosity.service.spec.ts`, rename any `service.login(...)` call to `service.connect({ email, password })` and `service.logout()` to `service.disconnect()`. If the spec references `getFirestoreData`, delete that test block. Do NOT attempt to run this spec under Karma (pre-existing `parcelRequire` failure). The goal here is only that `ng build` / `tsc` over the spec compiles.

Run: `npx ng build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add src/app/core/neurofeedback/services/neurosity.service.ts src/app/core/neurofeedback/services/neurosity.service.spec.ts
git commit -m "feat: conform NeurosityService to BrainDevice, drop dead getFirestoreData"
```

---

### Task 4: Env knob + `main.ts` provider factory

**Files:**
- Modify: `src/app/environments/environment.ts`
- Modify: `src/main.ts`

- [ ] **Step 1: Add the `device` knob to environment**

In `environment.ts`, add after the `useMockData` line:
```ts
  device: 'mock' as 'mock' | 'neurosity',  // active brain device implementation
```

- [ ] **Step 2: Replace the hardcoded device override in `main.ts`**

Add an import (with the other app imports near the top):
```ts
import { BrainDevice } from './app/core/neurofeedback/brain-device';
```

Replace the provider line:
```ts
    { provide: NeurosityService, useClass: MockNeurosityService }
```
with:
```ts
    {
      provide: BrainDevice,
      useFactory: () =>
        environment.device === 'neurosity'
          ? new NeurosityService()
          : new MockNeurosityService(),
    }
```

The existing `NeurosityService` and `MockNeurosityService` imports stay (referenced by the factory).

- [ ] **Step 3: Verify build**

Run: `npx ng build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/app/environments/environment.ts src/main.ts
git commit -m "feat: select brain device via env config + provider factory"
```

---

### Task 5: Migrate consumers to inject `BrainDevice`

**Files:**
- Modify: `src/app/core/neurofeedback/services/learning-session.service.ts`
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`

- [ ] **Step 1: Migrate `LearningSessionService`**

In `learning-session.service.ts`:

Replace the import:
```ts
import { NeurosityService } from './neurosity.service';
```
with:
```ts
import { BrainDevice } from '../brain-device';
```

Change the constructor parameter (line ~38-41):
```ts
  constructor(
    private firestoreService: FirestoreService,
    private device: BrainDevice
  ) {}
```

Update the two stream references inside `startMetricsCollection` (`this.neurosityService.focus$` → `this.device.focus$`, `this.neurosityService.calm$` → `this.device.calm$`):
```ts
    this.metricsSubscription = this.device.focus$.subscribe(focus => {
```
```ts
    this.device.calm$.subscribe(calm => {
```

- [ ] **Step 2: Migrate `dashboard.component.ts`**

In `dashboard.component.ts`:

Replace the import:
```ts
import { NeurosityService } from '../../../../core/neurofeedback/services/neurosity.service';
```
with:
```ts
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
```

Change the constructor parameter (line 65):
```ts
    private device: BrainDevice,
```

Update the `combineLatest` block (lines 74-77):
```ts
    combineLatest([
      this.device.focus$,
      this.device.calm$
    ]).pipe(
```

- [ ] **Step 3: Verify build**

Run: `npx ng build`
Expected: build succeeds. No remaining references to `NeurosityService` outside `neurosity.service.ts`, `mock-neurosity.service.ts` (no), `main.ts` factory, and specs.

- [ ] **Step 4: Run the green mock test to confirm no regression**

Run: `npx ng test --watch=false --browsers=ChromeHeadless --include='**/mock-neurosity.service.spec.ts'`
Expected: PASS (4 specs).

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/services/learning-session.service.ts src/app/shared/components/layout/dashboard-layout/dashboard.component.ts
git commit -m "refactor: inject BrainDevice token in session + dashboard consumers"
```

---

### Task 6: End-to-end verification (mock path)

**Files:** none (verification only)

- [ ] **Step 1: Production build passes**

Run: `npx ng build`
Expected: "Application bundle generation complete." Only the known `@neurosity/sdk` non-ESM warning.

- [ ] **Step 2: App serves and streams mock metrics**

Run: `npx ng serve --port 4321`
Then in a browser open `http://localhost:4321/`, log in (Firebase) and trigger the device connect path with the mock credentials `test@example.com` / `password123`. Confirm the dashboard scatter plot begins receiving focus/calm points (stream emits ~1/sec).
Expected: focus/calm values populate; no console errors about the device.
Stop the server when done.

- [ ] **Step 3: Confirm Neurosity selection compiles**

Temporarily set `device: 'neurosity'` in `environment.ts`, run `npx ng build`, confirm it builds, then revert to `'mock'`.
Expected: builds in both settings.

- [ ] **Step 4: Final commit (if env was touched/reverted, ensure clean tree)**

```bash
git status   # expect clean, on feat/device-agnostic-brain-device
```

---

## Self-review notes

- **Spec coverage:** §1 contract → Task 1. §2 impls + `getFirestoreData` removal → Tasks 2-3. §3 env + factory → Task 4. §4 consumers → Task 5. §5 testing/error handling → mock specs (Task 2), build checks (Tasks 3-5), e2e (Task 6). Pre-existing Karma breakage explicitly carved out.
- **Method-name consistency:** `connect`/`disconnect` used identically in contract (Task 1), mock (Task 2), real (Task 3), and the credential object shape `{ email, password }` matches across all three. `extras$?` optional → not implemented anywhere (intended).
- **Factory deps:** none, because removing `getFirestoreData()` makes `NeurosityService`'s constructor zero-arg (Task 3 Step 2) — consistent with the no-`deps` factory in Task 4.
