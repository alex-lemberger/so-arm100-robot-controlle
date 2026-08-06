# Handwerk Skill Capture Platform — Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/capture` route to the existing Angular app that records EEG + IMU glove + video during skilled-work sessions and uploads raw data to Firebase Storage/Firestore.

**Architecture:** Standalone Angular module at `src/app/modules/capture/` wired as a top-level route outside the dashboard shell. NGXS `CaptureState` manages session lifecycle. Four services (`ImuService`, `VideoRecorderService`, `CaptureUploadService`, `CaptureSessionService`) handle hardware, recording, and upload. Six screen components guide the worker through consent → hardware setup → task selection → recording → upload progress.

**Tech Stack:** Angular 19 standalone components, NGXS 19, `@angular/fire/storage` v19, Web Bluetooth API, MediaRecorder API, Firebase Firestore.

---

## Prerequisites

> **Read before starting.**

- **`ng test` is broken** — `@neurosity/sdk` throws `parcelRequire is not defined` under Karma, which cascades into all specs failing. **Do not use `ng test` to verify.** Use `ng build --configuration development` instead after each task.
- **IMU hardware UUIDs are placeholders.** `ImuService` contains `TODO: replace with actual device UUIDs` comments. The correct UUIDs depend on the specific BLE glove hardware chosen for pilot. During software development, mock the service. Before field pilot, replace UUIDs with values from the glove manufacturer's GATT profile documentation.
- **`FlowDetectorService` is not yet implemented.** `CaptureSessionService` stubs `inFlow$` as `false` in this plan. When flow detection ships (see `docs/superpowers/specs/2026-06-04-flow-detection-design.md`), update the service to inject and use `FlowDetectorService`.
- **Firebase Storage rules** must be updated in the Firebase console to allow authenticated writes to `captures/`. This is out-of-scope for the software tasks below but required before real sessions.

---

## File Map

### Create

```
src/app/modules/capture/
  capture.routes.ts
  models/
    capture-session.model.ts
  state/
    capture.actions.ts
    capture.model.ts
    capture.state.ts
  services/
    worker-token.service.ts
    imu.service.ts
    video-recorder.service.ts
    capture-upload.service.ts
    capture-session.service.ts
  components/
    capture-shell/
      capture-shell.component.ts
    worker-consent/
      worker-consent.component.ts
    hardware-setup/
      hardware-setup.component.ts
    task-selector/
      task-selector.component.ts
    live-capture/
      live-capture.component.ts
    upload-progress/
      upload-progress.component.ts
```

### Modify

```
src/app/app.routes.ts         — add /capture top-level route
src/main.ts                   — add CaptureState to provideStore, provideStorage
```

---

## Task 1: Models

**Files:**
- Create: `src/app/modules/capture/models/capture-session.model.ts`

- [ ] **Step 1: Create the model file**

```typescript
// src/app/modules/capture/models/capture-session.model.ts
import { Timestamp } from '@angular/fire/firestore';

export type CaptureSessionStatus =
  | 'recording'
  | 'uploading'
  | 'complete'
  | 'failed';

export interface CaptureSession {
  sessionId: string;
  workerId: string;
  taskType: string;
  taskLabel: string;
  startTime: Timestamp;
  endTime?: Timestamp;
  status: CaptureSessionStatus;
  videoPath?: string;
  imuLeftPath?: string;
  imuRightPath?: string;
  eegTickCount: number;
  consentVersion: string;
  shopId: string;
}

export interface EegTick {
  t: Timestamp;
  focus: number;
  calm: number;
  inFlow: boolean;
}

export interface ImuFrame {
  t: number;    // ms since session start
  ax: number; ay: number; az: number;
  gx: number; gy: number; gz: number;
}

export const TASK_TYPES: string[] = [
  'engine_assembly',
  'electrical_repair',
  'plumbing_installation',
  'hvac_service',
  'brake_replacement',
  'welding',
  'carpentry',
  'other',
];

export const CONSENT_VERSION = '1.0';
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds, no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/models/capture-session.model.ts
git commit -m "feat(capture): add capture session models and types"
```

---

## Task 2: NGXS State

**Files:**
- Create: `src/app/modules/capture/state/capture.actions.ts`
- Create: `src/app/modules/capture/state/capture.model.ts`
- Create: `src/app/modules/capture/state/capture.state.ts`

- [ ] **Step 1: Create actions**

```typescript
// src/app/modules/capture/state/capture.actions.ts
export namespace CaptureActions {
  export class StartSetup {
    static readonly type = '[Capture] Start Setup';
  }

  export class SetWorker {
    static readonly type = '[Capture] Set Worker';
    constructor(public workerToken: string) {}
  }

  export class SetTask {
    static readonly type = '[Capture] Set Task';
    constructor(public taskType: string, public taskLabel: string) {}
  }

  export class StartRecording {
    static readonly type = '[Capture] Start Recording';
    constructor(public sessionId: string) {}
  }

  export class StopRecording {
    static readonly type = '[Capture] Stop Recording';
  }

  export class UploadProgress {
    static readonly type = '[Capture] Upload Progress';
    constructor(public progress: number) {}
  }

  export class UploadComplete {
    static readonly type = '[Capture] Upload Complete';
  }

  export class UploadFailed {
    static readonly type = '[Capture] Upload Failed';
    constructor(public error: string) {}
  }

  export class Reset {
    static readonly type = '[Capture] Reset';
  }
}
```

- [ ] **Step 2: Create state model**

```typescript
// src/app/modules/capture/state/capture.model.ts
export type CaptureStatus =
  | 'idle'
  | 'setup'
  | 'recording'
  | 'uploading'
  | 'done'
  | 'error';

export interface CaptureStateModel {
  workerToken: string | null;
  taskType: string | null;
  taskLabel: string | null;
  sessionId: string | null;
  status: CaptureStatus;
  uploadProgress: number;
  error: string | null;
}
```

- [ ] **Step 3: Create state class**

```typescript
// src/app/modules/capture/state/capture.state.ts
import { Injectable } from '@angular/core';
import { State, Action, StateContext, Selector } from '@ngxs/store';
import { CaptureStateModel, CaptureStatus } from './capture.model';
import { CaptureActions } from './capture.actions';

const DEFAULTS: CaptureStateModel = {
  workerToken: null,
  taskType: null,
  taskLabel: null,
  sessionId: null,
  status: 'idle',
  uploadProgress: 0,
  error: null,
};

@State<CaptureStateModel>({
  name: 'capture',
  defaults: DEFAULTS,
})
@Injectable()
export class CaptureState {
  @Selector()
  static status(state: CaptureStateModel): CaptureStatus {
    return state.status;
  }

  @Selector()
  static sessionId(state: CaptureStateModel): string | null {
    return state.sessionId;
  }

  @Selector()
  static workerToken(state: CaptureStateModel): string | null {
    return state.workerToken;
  }

  @Selector()
  static uploadProgress(state: CaptureStateModel): number {
    return state.uploadProgress;
  }

  @Selector()
  static error(state: CaptureStateModel): string | null {
    return state.error;
  }

  @Selector()
  static taskType(state: CaptureStateModel): string | null {
    return state.taskType;
  }

  @Selector()
  static taskLabel(state: CaptureStateModel): string | null {
    return state.taskLabel;
  }

  @Action(CaptureActions.StartSetup)
  startSetup({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'setup', error: null });
  }

  @Action(CaptureActions.SetWorker)
  setWorker({ patchState }: StateContext<CaptureStateModel>, { workerToken }: CaptureActions.SetWorker) {
    patchState({ workerToken });
  }

  @Action(CaptureActions.SetTask)
  setTask({ patchState }: StateContext<CaptureStateModel>, { taskType, taskLabel }: CaptureActions.SetTask) {
    patchState({ taskType, taskLabel });
  }

  @Action(CaptureActions.StartRecording)
  startRecording({ patchState }: StateContext<CaptureStateModel>, { sessionId }: CaptureActions.StartRecording) {
    patchState({ status: 'recording', sessionId, uploadProgress: 0 });
  }

  @Action(CaptureActions.StopRecording)
  stopRecording({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'uploading' });
  }

  @Action(CaptureActions.UploadProgress)
  uploadProgress({ patchState }: StateContext<CaptureStateModel>, { progress }: CaptureActions.UploadProgress) {
    patchState({ uploadProgress: progress });
  }

  @Action(CaptureActions.UploadComplete)
  uploadComplete({ patchState }: StateContext<CaptureStateModel>) {
    patchState({ status: 'done', uploadProgress: 100 });
  }

  @Action(CaptureActions.UploadFailed)
  uploadFailed({ patchState }: StateContext<CaptureStateModel>, { error }: CaptureActions.UploadFailed) {
    patchState({ status: 'error', error });
  }

  @Action(CaptureActions.Reset)
  reset({ setState }: StateContext<CaptureStateModel>) {
    setState(DEFAULTS);
  }
}
```

- [ ] **Step 4: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/state/
git commit -m "feat(capture): add CaptureState with NGXS actions and selectors"
```

---

## Task 3: WorkerTokenService

**Files:**
- Create: `src/app/modules/capture/services/worker-token.service.ts`

Worker tokens are UUID strings generated once and persisted in `localStorage`. No login required — the token is the worker's anonymous identity.

- [ ] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/worker-token.service.ts
import { Injectable } from '@angular/core';

const STORAGE_KEY = 'capture_worker_token';

@Injectable({ providedIn: 'root' })
export class WorkerTokenService {
  getOrCreate(): string {
    const existing = localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const token = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, token);
    return token;
  }

  get(): string | null {
    return localStorage.getItem(STORAGE_KEY);
  }

  clear(): void {
    localStorage.removeItem(STORAGE_KEY);
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/worker-token.service.ts
git commit -m "feat(capture): add WorkerTokenService with localStorage UUID persistence"
```

---

## Task 4: ImuService

**Files:**
- Create: `src/app/modules/capture/services/imu.service.ts`

Connects to two BLE IMU gloves via Web Bluetooth. Buffers `ImuFrame` readings into `Float32Array` per hand. Exposes connection status observables.

> **Note:** `SERVICE_UUID` and `CHARACTERISTIC_UUID` below are placeholders. Replace with the actual GATT service and characteristic UUIDs from your BLE glove's documentation before field use.

- [ ] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/imu.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { ImuFrame } from '../models/capture-session.model';

// TODO: replace with actual device UUIDs from glove manufacturer's GATT profile
const SERVICE_UUID = '0000181a-0000-1000-8000-00805f9b34fb'; // placeholder
const CHARACTERISTIC_UUID = '00002a56-0000-1000-8000-00805f9b34fb'; // placeholder

type Hand = 'left' | 'right';

interface GloveDevice {
  device: BluetoothDevice;
  server: BluetoothRemoteGATTServer;
  characteristic: BluetoothRemoteGATTCharacteristic;
}

@Injectable({ providedIn: 'root' })
export class ImuService {
  private gloves: Partial<Record<Hand, GloveDevice>> = {};

  private leftConnected = new BehaviorSubject<boolean>(false);
  private rightConnected = new BehaviorSubject<boolean>(false);

  readonly leftConnected$ = this.leftConnected.asObservable();
  readonly rightConnected$ = this.rightConnected.asObservable();

  private leftFrames: ImuFrame[] = [];
  private rightFrames: ImuFrame[] = [];
  private sessionStart = 0;
  private recording = false;

  get isSupported(): boolean {
    return 'bluetooth' in navigator;
  }

  async connect(hand: Hand): Promise<void> {
    const device = await navigator.bluetooth.requestDevice({
      filters: [{ services: [SERVICE_UUID] }],
    });
    const server = await device.gatt!.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    const characteristic = await service.getCharacteristic(CHARACTERISTIC_UUID);

    device.addEventListener('gattserverdisconnected', () => {
      this.gloves[hand] = undefined;
      (hand === 'left' ? this.leftConnected : this.rightConnected).next(false);
    });

    await characteristic.startNotifications();
    characteristic.addEventListener('characteristicvaluechanged', (event) => {
      if (!this.recording) return;
      const frame = this.parseFrame(event, hand);
      if (hand === 'left') this.leftFrames.push(frame);
      else this.rightFrames.push(frame);
    });

    this.gloves[hand] = { device, server, characteristic };
    (hand === 'left' ? this.leftConnected : this.rightConnected).next(true);
  }

  startRecording(sessionStartMs: number): void {
    this.sessionStart = sessionStartMs;
    this.leftFrames = [];
    this.rightFrames = [];
    this.recording = true;
  }

  stopRecording(): { left: Float32Array; right: Float32Array } {
    this.recording = false;
    return {
      left: this.framesToBinary(this.leftFrames),
      right: this.framesToBinary(this.rightFrames),
    };
  }

  async disconnect(): Promise<void> {
    for (const hand of ['left', 'right'] as Hand[]) {
      const glove = this.gloves[hand];
      if (glove?.server.connected) glove.server.disconnect();
      this.gloves[hand] = undefined;
    }
    this.leftConnected.next(false);
    this.rightConnected.next(false);
  }

  private parseFrame(event: Event, _hand: Hand): ImuFrame {
    // TODO: parse according to actual glove GATT characteristic format
    // Placeholder: reads 6 x Int16 little-endian values (ax,ay,az,gx,gy,gz) scaled by 100
    const view = (event.target as BluetoothRemoteGATTCharacteristic).value!;
    return {
      t: Date.now() - this.sessionStart,
      ax: view.getInt16(0, true) / 100,
      ay: view.getInt16(2, true) / 100,
      az: view.getInt16(4, true) / 100,
      gx: view.getInt16(6, true) / 100,
      gy: view.getInt16(8, true) / 100,
      gz: view.getInt16(10, true) / 100,
    };
  }

  private framesToBinary(frames: ImuFrame[]): Float32Array {
    // Layout per frame: t, ax, ay, az, gx, gy, gz (7 floats)
    const buf = new Float32Array(frames.length * 7);
    frames.forEach((f, i) => {
      buf[i * 7 + 0] = f.t;
      buf[i * 7 + 1] = f.ax;
      buf[i * 7 + 2] = f.ay;
      buf[i * 7 + 3] = f.az;
      buf[i * 7 + 4] = f.gx;
      buf[i * 7 + 5] = f.gy;
      buf[i * 7 + 6] = f.gz;
    });
    return buf;
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds. TypeScript may warn about `BluetoothDevice` — ensure `tsconfig.json` has `"lib": ["ES2022", "dom"]` (already present in Angular 19 default config).

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/imu.service.ts
git commit -m "feat(capture): add ImuService with Web Bluetooth BLE glove integration"
```

---

## Task 5: VideoRecorderService

**Files:**
- Create: `src/app/modules/capture/services/video-recorder.service.ts`

Uses `getUserMedia` + `MediaRecorder` to capture camera video. Collects `Blob` chunks during recording. On stop, resolves with a single concatenated `Blob`.

- [ ] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/video-recorder.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class VideoRecorderService {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private stopResolve: ((blob: Blob) => void) | null = null;

  private cameraReady = new BehaviorSubject<boolean>(false);
  readonly cameraReady$ = this.cameraReady.asObservable();

  get previewStream(): MediaStream | null {
    return this.stream;
  }

  async requestCamera(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    });
    this.cameraReady.next(true);
  }

  startRecording(): void {
    if (!this.stream) throw new Error('Camera not ready — call requestCamera() first');
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, { mimeType: 'video/mp4; codecs=avc1' });
    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.recorder.start(1000); // collect a chunk every 1 s
  }

  stopRecording(): Promise<Blob> {
    return new Promise((resolve) => {
      this.stopResolve = resolve;
      this.recorder!.onstop = () => {
        const blob = new Blob(this.chunks, { type: 'video/mp4' });
        this.stopResolve?.(blob);
      };
      this.recorder!.stop();
    });
  }

  releaseCamera(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.cameraReady.next(false);
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/video-recorder.service.ts
git commit -m "feat(capture): add VideoRecorderService with MediaRecorder + getUserMedia"
```

---

## Task 6: CaptureUploadService

**Files:**
- Create: `src/app/modules/capture/services/capture-upload.service.ts`
- Modify: `src/main.ts` — add `provideStorage`

Uploads video blob and two IMU `Float32Array` buffers to Firebase Storage using resumable uploads. Tracks combined progress.

- [ ] **Step 1: Add Firebase Storage provider to `main.ts`**

In `src/main.ts`, add these imports at the top:

```typescript
import { provideStorage, getStorage } from '@angular/fire/storage';
```

Then inside the `providers` array, after `provideFirestore(...)`:

```typescript
provideStorage(() => getStorage()),
```

The full providers array should now read:

```typescript
providers: [
  provideRouter(routes),
  provideFirebaseApp(() => initializeApp(environment.firebase)),
  provideAuth(() => getAuth()),
  provideFirestore(() => getFirestore()),
  provideStorage(() => getStorage()),   // ← add this line
  provideAnimations(),
  provideHttpClient(),
  importProvidersFrom(
    MatSnackBarModule,
    MatDialogModule,
    MatIconModule,
    MatTableModule
  ),
  provideStore([ExerciseState, CaptureState], withNgxsReduxDevtoolsPlugin(), withNgxsLoggerPlugin()),
  {
    provide: BrainDevice,
    useFactory: () =>
      environment.device === 'neurosity'
        ? new NeurosityService()
        : new MockNeurosityService(),
  }
],
```

Also add these imports at the top of `main.ts`:

```typescript
import { CaptureState } from './app/modules/capture/state/capture.state';
```

- [ ] **Step 2: Create CaptureUploadService**

```typescript
// src/app/modules/capture/services/capture-upload.service.ts
import { Injectable } from '@angular/core';
import { Storage, ref, uploadBytesResumable } from '@angular/fire/storage';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class CaptureUploadService {
  private progressSubject = new BehaviorSubject<number>(0);
  readonly progress$ = this.progressSubject.asObservable();

  constructor(private storage: Storage) {}

  async uploadSession(
    sessionId: string,
    video: Blob,
    imuLeft: Float32Array,
    imuRight: Float32Array,
  ): Promise<{ videoPath: string; imuLeftPath: string; imuRightPath: string }> {
    this.progressSubject.next(0);

    const videoPath = `captures/${sessionId}/video.mp4`;
    const imuLeftPath = `captures/${sessionId}/imu_left.bin`;
    const imuRightPath = `captures/${sessionId}/imu_right.bin`;

    let videoBytes = 0, imuLeftBytes = 0, imuRightBytes = 0;
    const totalBytes = video.size + imuLeft.byteLength + imuRight.byteLength;

    const updateProgress = () => {
      const done = videoBytes + imuLeftBytes + imuRightBytes;
      this.progressSubject.next(Math.round((done / totalBytes) * 100));
    };

    await Promise.all([
      this.uploadWithProgress(videoPath, video, (n) => { videoBytes = n; updateProgress(); }),
      this.uploadWithProgress(imuLeftPath, new Blob([imuLeft]), (n) => { imuLeftBytes = n; updateProgress(); }),
      this.uploadWithProgress(imuRightPath, new Blob([imuRight]), (n) => { imuRightBytes = n; updateProgress(); }),
    ]);

    this.progressSubject.next(100);
    return { videoPath, imuLeftPath, imuRightPath };
  }

  private uploadWithProgress(
    path: string,
    data: Blob,
    onProgress: (bytesTransferred: number) => void,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const storageRef = ref(this.storage, path);
      const task = uploadBytesResumable(storageRef, data);
      task.on(
        'state_changed',
        (snap) => onProgress(snap.bytesTransferred),
        reject,
        () => resolve(),
      );
    });
  }
}
```

- [ ] **Step 3: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/services/capture-upload.service.ts src/main.ts
git commit -m "feat(capture): add CaptureUploadService with Firebase Storage resumable uploads"
```

---

## Task 7: CaptureSessionService

**Files:**
- Create: `src/app/modules/capture/services/capture-session.service.ts`

Orchestrates all three streams. Writes EEG ticks to Firestore subcollection. Manages session document lifecycle. Stubs `inFlow` as `false` until `FlowDetectorService` ships.

- [ ] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/capture-session.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { Store } from '@ngxs/store';
import { Firestore, collection, doc, setDoc, updateDoc, Timestamp } from '@angular/fire/firestore';
import { Subscription, combineLatest } from 'rxjs';
import { filter } from 'rxjs/operators';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { CaptureActions } from '../state/capture.actions';
import { CaptureSession, CONSENT_VERSION } from '../models/capture-session.model';

@Injectable({ providedIn: 'root' })
export class CaptureSessionService implements OnDestroy {
  private eegSub: Subscription | null = null;
  private currentSessionId: string | null = null;
  private eegTickCount = 0;

  constructor(
    private store: Store,
    private firestore: Firestore,
    private brainDevice: BrainDevice,
    private imuService: ImuService,
    private videoService: VideoRecorderService,
    private uploadService: CaptureUploadService,
  ) {}

  async startSession(workerToken: string, taskType: string, taskLabel: string, shopId: string): Promise<string> {
    const sessionRef = doc(collection(this.firestore, 'captures'));
    const sessionId = sessionRef.id;
    this.currentSessionId = sessionId;
    this.eegTickCount = 0;

    const sessionDoc: CaptureSession = {
      sessionId,
      workerId: workerToken,
      taskType,
      taskLabel,
      startTime: Timestamp.now(),
      status: 'recording',
      eegTickCount: 0,
      consentVersion: CONSENT_VERSION,
      shopId,
    };
    await setDoc(sessionRef, sessionDoc);

    const sessionStart = Date.now();
    this.imuService.startRecording(sessionStart);
    this.videoService.startRecording();

    this.eegSub = combineLatest([this.brainDevice.focus$, this.brainDevice.calm$])
      .pipe(filter(([f, c]) => f !== null && c !== null))
      .subscribe(([focus, calm]) => {
        this.writeEegTick(sessionId, focus!, calm!);
      });

    this.store.dispatch(new CaptureActions.StartRecording(sessionId));
    return sessionId;
  }

  async stopSession(): Promise<void> {
    if (!this.currentSessionId) return;
    const sessionId = this.currentSessionId;

    this.eegSub?.unsubscribe();
    this.eegSub = null;

    this.store.dispatch(new CaptureActions.StopRecording());

    const [videoBlob, imuBuffers] = await Promise.all([
      this.videoService.stopRecording(),
      Promise.resolve(this.imuService.stopRecording()),
    ]);

    await updateDoc(doc(this.firestore, 'captures', sessionId), {
      status: 'uploading',
      endTime: Timestamp.now(),
      eegTickCount: this.eegTickCount,
    });

    try {
      const paths = await this.uploadService.uploadSession(
        sessionId,
        videoBlob,
        imuBuffers.left,
        imuBuffers.right,
      );

      await updateDoc(doc(this.firestore, 'captures', sessionId), {
        status: 'complete',
        videoPath: paths.videoPath,
        imuLeftPath: paths.imuLeftPath,
        imuRightPath: paths.imuRightPath,
      });

      this.store.dispatch(new CaptureActions.UploadComplete());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await updateDoc(doc(this.firestore, 'captures', sessionId), { status: 'failed' });
      this.store.dispatch(new CaptureActions.UploadFailed(message));
    } finally {
      this.currentSessionId = null;
    }
  }

  private writeEegTick(sessionId: string, focus: number, calm: number): void {
    this.eegTickCount++;
    const tickRef = doc(collection(this.firestore, `captures/${sessionId}/eeg`));
    setDoc(tickRef, {
      t: Timestamp.now(),
      focus,
      calm,
      inFlow: false, // TODO: replace with FlowDetectorService.inFlow$ when implemented
    }).catch(console.error);
  }

  ngOnDestroy(): void {
    this.eegSub?.unsubscribe();
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/capture-session.service.ts
git commit -m "feat(capture): add CaptureSessionService orchestrating EEG + IMU + video"
```

---

## Task 8: Route + CaptureShellComponent

**Files:**
- Create: `src/app/modules/capture/capture.routes.ts`
- Create: `src/app/modules/capture/components/capture-shell/capture-shell.component.ts`
- Modify: `src/app/app.routes.ts`

- [ ] **Step 1: Create capture routes**

```typescript
// src/app/modules/capture/capture.routes.ts
import { Routes } from '@angular/router';
import { CaptureShellComponent } from './components/capture-shell/capture-shell.component';

export const CAPTURE_ROUTES: Routes = [
  {
    path: '',
    component: CaptureShellComponent,
  },
];
```

- [ ] **Step 2: Create CaptureShellComponent**

The shell is a simple host that reads `CaptureState.status` and renders the appropriate child screen.

```typescript
// src/app/modules/capture/components/capture-shell/capture-shell.component.ts
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureState } from '../../state/capture.state';
import { CaptureStatus } from '../../state/capture.model';
import { WorkerConsentComponent } from '../worker-consent/worker-consent.component';
import { HardwareSetupComponent } from '../hardware-setup/hardware-setup.component';
import { TaskSelectorComponent } from '../task-selector/task-selector.component';
import { LiveCaptureComponent } from '../live-capture/live-capture.component';
import { UploadProgressComponent } from '../upload-progress/upload-progress.component';

@Component({
  selector: 'app-capture-shell',
  standalone: true,
  imports: [
    CommonModule,
    WorkerConsentComponent,
    HardwareSetupComponent,
    TaskSelectorComponent,
    LiveCaptureComponent,
    UploadProgressComponent,
  ],
  template: `
    <div class="capture-shell">
      @switch (status()) {
        @case ('idle') { <app-worker-consent /> }
        @case ('setup') { <app-hardware-setup /> }
        @case ('recording') { <app-live-capture /> }
        @case ('uploading') { <app-upload-progress /> }
        @case ('done') { <app-upload-progress /> }
        @case ('error') { <app-upload-progress /> }
        @default { <app-worker-consent /> }
      }
    </div>
  `,
  styles: [`
    .capture-shell {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      background: #0f1923;
      padding: 24px;
    }
  `],
})
export class CaptureShellComponent {
  private store = inject(Store);
  protected status = toSignal(this.store.select(CaptureState.status), { initialValue: 'idle' as CaptureStatus });
}
```

Note: `TaskSelectorComponent` is rendered from `WorkerConsentComponent` after consent, or from `HardwareSetupComponent` after hardware is ready. The shell uses `status` to decide which top-level screen to show. Task selection happens between `setup` and `recording` — handled inside `HardwareSetupComponent` (it advances the state to show task selector inline, or you can add a `'task'` status). **Simplest approach:** add a `'task'` status to `CaptureStateModel` and `CaptureStatus`.

- [ ] **Step 3: Add `'task'` to CaptureStatus and update state**

In `src/app/modules/capture/state/capture.model.ts`, update:

```typescript
export type CaptureStatus =
  | 'idle'
  | 'setup'
  | 'task'
  | 'recording'
  | 'uploading'
  | 'done'
  | 'error';
```

In `src/app/modules/capture/state/capture.actions.ts`, add:

```typescript
export class AdvanceToTask {
  static readonly type = '[Capture] Advance To Task';
}
```

In `src/app/modules/capture/state/capture.state.ts`, add:

```typescript
@Action(CaptureActions.AdvanceToTask)
advanceToTask({ patchState }: StateContext<CaptureStateModel>) {
  patchState({ status: 'task' });
}
```

Update `CaptureShellComponent` template to add `@case ('task') { <app-task-selector /> }`.

- [ ] **Step 4: Wire `/capture` into `app.routes.ts`**

```typescript
// src/app/app.routes.ts
import { Routes } from '@angular/router';
import { DroneSimComponent } from './core/visualisations/drone-sim/drone-sim.component';
import { DashboardComponent } from './shared/components/layout/dashboard-layout/dashboard.component';
import { DashboardLayoutComponent } from './shared/components/layout/dashboard-layout/dashboard-layout.component';
import { ExercisesOverviewComponent } from './modules/language-learning/components/exercises-overview/exercises-overview.component';
import { SpeakingExerciseComponent } from './modules/language-learning/components/speaking-exercise/speaking-exercise.component';
import { CAPTURE_ROUTES } from './modules/capture/capture.routes';

export const routes: Routes = [
  {
    path: '',
    component: DashboardLayoutComponent,
    children: [
      { path: 'dashboard', component: DashboardComponent },
      {
        path: 'exercises',
        children: [
          { path: '', component: ExercisesOverviewComponent },
          {
            path: 'speaking',
            children: [
              { path: '', component: ExercisesOverviewComponent },
              { path: ':id', component: SpeakingExerciseComponent },
            ],
          },
        ],
      },
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    ],
  },
  {
    path: 'droneSim',
    component: DroneSimComponent,
  },
  {
    path: 'capture',
    children: CAPTURE_ROUTES,
  },
];
```

- [ ] **Step 5: Verify compilation**

```bash
ng build --configuration development
```

Expected: build succeeds. Navigate to `http://localhost:4200/capture` in browser after `ng serve` — should render the capture shell (blank or consent screen).

- [ ] **Step 6: Commit**

```bash
git add src/app/modules/capture/capture.routes.ts \
        src/app/modules/capture/components/capture-shell/capture-shell.component.ts \
        src/app/modules/capture/state/capture.model.ts \
        src/app/modules/capture/state/capture.actions.ts \
        src/app/modules/capture/state/capture.state.ts \
        src/app/app.routes.ts
git commit -m "feat(capture): add /capture route, CaptureShellComponent with status-driven screen routing"
```

---

## Task 9: WorkerConsentComponent

**Files:**
- Create: `src/app/modules/capture/components/worker-consent/worker-consent.component.ts`

Displays consent text, collects acknowledgement, writes `workers/{workerId}` doc to Firestore, then advances state to `'setup'`.

- [ ] **Step 1: Create WorkerConsentComponent**

```typescript
// src/app/modules/capture/components/worker-consent/worker-consent.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { Firestore, doc, setDoc, Timestamp } from '@angular/fire/firestore';
import { WorkerTokenService } from '../../services/worker-token.service';
import { CaptureActions } from '../../state/capture.actions';
import { CONSENT_VERSION } from '../../models/capture-session.model';

@Component({
  selector: 'app-worker-consent',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="consent-card">
      <h1 class="consent-title">Datenerfassung — Einwilligung</h1>
      <p class="consent-body">
        Diese App erfasst EEG-Gehirnsignale, IMU-Handbewegungsdaten und Videoaufnahmen
        während Ihrer Arbeitstätigkeit. Alle Daten werden anonymisiert gespeichert —
        Ihr Name und Ihre persönlichen Daten werden nicht erhoben. Die Daten werden
        ausschließlich für die Entwicklung von KI-Modellen im Bereich Robotik verwendet.
        Sie können Ihre Einwilligung jederzeit widerrufen und die Löschung Ihrer Daten
        verlangen.
      </p>
      <label class="consent-check">
        <input type="checkbox" [checked]="agreed()" (change)="agreed.set(!agreed())" />
        Ich stimme der Erfassung und Verarbeitung meiner Daten zu (Version {{ version }}).
      </label>
      <button class="consent-btn" [disabled]="!agreed() || saving()" (click)="accept()">
        {{ saving() ? 'Wird gespeichert…' : 'Weiter' }}
      </button>
      @if (error()) {
        <p class="consent-error">{{ error() }}</p>
      }
    </div>
  `,
  styles: [`
    .consent-card {
      background: #1a2535; border-radius: 16px; padding: 40px;
      max-width: 560px; color: #e8edf5;
    }
    .consent-title { font-family: 'DM Sans', sans-serif; font-size: 22px; margin-bottom: 20px; }
    .consent-body { font-size: 14px; line-height: 1.7; color: #9aa8c4; margin-bottom: 24px; }
    .consent-check { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; margin-bottom: 28px; cursor: pointer; }
    .consent-btn {
      width: 100%; padding: 14px; border-radius: 10px; border: none;
      background: #1976D2; color: #fff; font-size: 16px; cursor: pointer;
    }
    .consent-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .consent-error { color: #ef5350; font-size: 13px; margin-top: 12px; }
  `],
})
export class WorkerConsentComponent {
  private store = inject(Store);
  private firestore = inject(Firestore);
  private tokenService = inject(WorkerTokenService);

  protected version = CONSENT_VERSION;
  protected agreed = signal(false);
  protected saving = signal(false);
  protected error = signal<string | null>(null);

  async accept(): Promise<void> {
    this.saving.set(true);
    this.error.set(null);
    try {
      const workerToken = this.tokenService.getOrCreate();
      await setDoc(doc(this.firestore, 'workers', workerToken), {
        consentTimestamp: Timestamp.now(),
        consentVersion: CONSENT_VERSION,
        skillTags: [],
        sessionCount: 0,
      }, { merge: true });
      this.store.dispatch([
        new CaptureActions.SetWorker(workerToken),
        new CaptureActions.StartSetup(),
      ]);
    } catch (e) {
      this.error.set('Fehler beim Speichern. Bitte erneut versuchen.');
    } finally {
      this.saving.set(false);
    }
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

- [ ] **Step 3: Smoke test in browser**

```bash
ng serve
```

Navigate to `http://localhost:4200/capture`. Verify consent screen renders. Check the checkbox, click "Weiter". Verify Firestore `workers/` collection has a new document.

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/components/worker-consent/worker-consent.component.ts
git commit -m "feat(capture): add WorkerConsentComponent with GDPR consent flow and Firestore write"
```

---

## Task 10: HardwareSetupComponent

**Files:**
- Create: `src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts`

Guides the worker through connecting left IMU glove, right IMU glove, and camera. Shows status chip per device. Advances to `'task'` state only when all three are ready.

- [ ] **Step 1: Create HardwareSetupComponent**

```typescript
// src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { combineLatest, map } from 'rxjs';
import { ImuService } from '../../services/imu.service';
import { VideoRecorderService } from '../../services/video-recorder.service';
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
import { CaptureActions } from '../../state/capture.actions';

@Component({
  selector: 'app-hardware-setup',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="setup-card">
      <h2 class="setup-title">Hardware einrichten</h2>

      @if (!bluetoothSupported) {
        <p class="setup-error">
          Web Bluetooth wird von diesem Browser nicht unterstützt.
          Bitte Chrome auf Android verwenden.
        </p>
      } @else {
        <div class="device-list">
          <div class="device-row">
            <span class="device-label">Linker Handschuh</span>
            <span class="chip" [class.chip--ok]="leftOk()">{{ leftOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
            <button class="btn-sm" [disabled]="leftOk() || connecting()" (click)="connectLeft()">Verbinden</button>
          </div>
          <div class="device-row">
            <span class="device-label">Rechter Handschuh</span>
            <span class="chip" [class.chip--ok]="rightOk()">{{ rightOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
            <button class="btn-sm" [disabled]="rightOk() || connecting()" (click)="connectRight()">Verbinden</button>
          </div>
          <div class="device-row">
            <span class="device-label">Kamera</span>
            <span class="chip" [class.chip--ok]="cameraOk()">{{ cameraOk() ? '✓ Bereit' : 'Nicht bereit' }}</span>
            <button class="btn-sm" [disabled]="cameraOk() || connecting()" (click)="connectCamera()">Zugriff erlauben</button>
          </div>
          <div class="device-row">
            <span class="device-label">EEG Headset</span>
            <span class="chip" [class.chip--ok]="eegOk()">{{ eegOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
          </div>
        </div>

        @if (connectError()) {
          <p class="setup-error">{{ connectError() }}</p>
        }

        <button class="btn-primary" [disabled]="!allReady() || connecting()" (click)="advance()">
          Weiter
        </button>
      }
    </div>
  `,
  styles: [`
    .setup-card { background: #1a2535; border-radius: 16px; padding: 40px; max-width: 520px; color: #e8edf5; }
    .setup-title { font-size: 20px; margin-bottom: 28px; }
    .device-list { display: flex; flex-direction: column; gap: 16px; margin-bottom: 32px; }
    .device-row { display: flex; align-items: center; gap: 12px; }
    .device-label { flex: 1; font-size: 14px; color: #9aa8c4; }
    .chip { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #2a3545; color: #9aa8c4; }
    .chip--ok { background: #1b3a2a; color: #4caf50; }
    .btn-sm { padding: 6px 14px; border-radius: 8px; border: 1px solid #2a3f5f; background: transparent; color: #9aa8c4; font-size: 12px; cursor: pointer; }
    .btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
    .btn-primary { width: 100%; padding: 14px; border-radius: 10px; border: none; background: #1976D2; color: #fff; font-size: 16px; cursor: pointer; }
    .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
    .setup-error { color: #ef5350; font-size: 13px; margin-bottom: 16px; }
  `],
})
export class HardwareSetupComponent {
  private store = inject(Store);
  private imuService = inject(ImuService);
  private videoService = inject(VideoRecorderService);
  private brainDevice = inject(BrainDevice);

  protected bluetoothSupported = this.imuService.isSupported;
  protected leftOk = toSignal(this.imuService.leftConnected$, { initialValue: false });
  protected rightOk = toSignal(this.imuService.rightConnected$, { initialValue: false });
  protected cameraOk = toSignal(this.videoService.cameraReady$, { initialValue: false });
  protected eegOk = toSignal(
    this.brainDevice.state$.pipe(map((s) => s.isLoggedIn)),
    { initialValue: false },
  );
  protected connecting = signal(false);
  protected connectError = signal<string | null>(null);

  protected allReady = toSignal(
    combineLatest([
      this.imuService.leftConnected$,
      this.imuService.rightConnected$,
      this.videoService.cameraReady$,
      this.brainDevice.state$.pipe(map((s) => s.isLoggedIn)),
    ]).pipe(map(([l, r, cam, eeg]) => l && r && cam && eeg)),
    { initialValue: false },
  );

  async connectLeft(): Promise<void> {
    await this.connect(() => this.imuService.connect('left'));
  }

  async connectRight(): Promise<void> {
    await this.connect(() => this.imuService.connect('right'));
  }

  async connectCamera(): Promise<void> {
    await this.connect(() => this.videoService.requestCamera());
  }

  advance(): void {
    this.store.dispatch(new CaptureActions.AdvanceToTask());
  }

  private async connect(fn: () => Promise<void>): Promise<void> {
    this.connecting.set(true);
    this.connectError.set(null);
    try {
      await fn();
    } catch (e) {
      this.connectError.set(e instanceof Error ? e.message : 'Verbindung fehlgeschlagen.');
    } finally {
      this.connecting.set(false);
    }
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts
git commit -m "feat(capture): add HardwareSetupComponent with BLE glove + camera + EEG status"
```

---

## Task 11: TaskSelectorComponent

**Files:**
- Create: `src/app/modules/capture/components/task-selector/task-selector.component.ts`

Worker picks a `taskType` from a predefined list and enters a free-text `taskLabel`. Dispatches `SetTask` + `StartRecording` via `CaptureSessionService`.

- [ ] **Step 1: Create TaskSelectorComponent**

```typescript
// src/app/modules/capture/components/task-selector/task-selector.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureSessionService } from '../../services/capture-session.service';
import { CaptureActions } from '../../state/capture.actions';
import { CaptureState } from '../../state/capture.state';
import { TASK_TYPES } from '../../models/capture-session.model';

const SHOP_ID = 'pilot-shop-01'; // TODO: make configurable per deployment

@Component({
  selector: 'app-task-selector',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="task-card">
      <h2 class="task-title">Aufgabe auswählen</h2>

      <label class="field-label">Aufgabentyp</label>
      <select class="field-select" [(ngModel)]="selectedType">
        @for (t of taskTypes; track t) {
          <option [value]="t">{{ t }}</option>
        }
      </select>

      <label class="field-label">Beschreibung (optional)</label>
      <input class="field-input" [(ngModel)]="taskLabel" placeholder="z. B. Bremssattel BMW 3er wechseln" />

      @if (starting()) {
        <p class="task-status">Aufzeichnung wird gestartet…</p>
      }
      @if (error()) {
        <p class="task-error">{{ error() }}</p>
      }

      <button class="btn-primary" [disabled]="!selectedType || starting()" (click)="start()">
        Aufzeichnung starten
      </button>
    </div>
  `,
  styles: [`
    .task-card { background: #1a2535; border-radius: 16px; padding: 40px; max-width: 480px; color: #e8edf5; }
    .task-title { font-size: 20px; margin-bottom: 28px; }
    .field-label { display: block; font-size: 12px; color: #9aa8c4; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 6px; margin-top: 20px; }
    .field-select, .field-input {
      width: 100%; padding: 10px 14px; border-radius: 8px;
      border: 1px solid #2a3f5f; background: #111c2a; color: #e8edf5;
      font-size: 14px; box-sizing: border-box;
    }
    .btn-primary { margin-top: 32px; width: 100%; padding: 14px; border-radius: 10px; border: none; background: #1976D2; color: #fff; font-size: 16px; cursor: pointer; }
    .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
    .task-status { color: #9aa8c4; font-size: 13px; margin-top: 16px; }
    .task-error { color: #ef5350; font-size: 13px; margin-top: 12px; }
  `],
})
export class TaskSelectorComponent {
  private store = inject(Store);
  private captureService = inject(CaptureSessionService);

  protected taskTypes = TASK_TYPES;
  protected selectedType = TASK_TYPES[0];
  protected taskLabel = '';
  protected starting = signal(false);
  protected error = signal<string | null>(null);

  private workerToken = toSignal(this.store.select(CaptureState.workerToken), { initialValue: null });

  async start(): Promise<void> {
    this.starting.set(true);
    this.error.set(null);
    try {
      const token = this.workerToken() ?? '';
      await this.captureService.startSession(token, this.selectedType, this.taskLabel, SHOP_ID);
    } catch (e) {
      this.error.set(e instanceof Error ? e.message : 'Fehler beim Starten.');
      this.starting.set(false);
    }
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/components/task-selector/task-selector.component.ts
git commit -m "feat(capture): add TaskSelectorComponent with task type picker and session start"
```

---

## Task 12: LiveCaptureComponent

**Files:**
- Create: `src/app/modules/capture/components/live-capture/live-capture.component.ts`

Shows EEG arc rings (reuses `MetricRingComponent`), IMU connection chips, live video preview, and STOP button. On STOP calls `CaptureSessionService.stopSession()`.

- [ ] **Step 1: Create LiveCaptureComponent**

```typescript
// src/app/modules/capture/components/live-capture/live-capture.component.ts
import { Component, inject, OnInit, OnDestroy, ElementRef, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
import { ImuService } from '../../services/imu.service';
import { VideoRecorderService } from '../../services/video-recorder.service';
import { CaptureSessionService } from '../../services/capture-session.service';
import { MetricRingComponent } from '../../../../shared/components/layout/dashboard-layout/widgets/metric-ring.component';

@Component({
  selector: 'app-live-capture',
  standalone: true,
  imports: [CommonModule, MetricRingComponent],
  template: `
    <div class="live-card">
      <div class="status-row">
        <span class="rec-dot"></span>
        <span class="rec-label">REC</span>
        <span class="chip" [class.chip--ok]="leftOk()">L {{ leftOk() ? '✓' : '!' }}</span>
        <span class="chip" [class.chip--ok]="rightOk()">R {{ rightOk() ? '✓' : '!' }}</span>
      </div>

      <div class="rings-row">
        <app-metric-ring [value]="focus()" label="Focus" icon="psychology" color="#1976D2" paleColor="#E3F2FD" />
        <app-metric-ring [value]="calm()" label="Calm" icon="self_improvement" color="#388E3C" paleColor="#E8F5E9" />
      </div>

      <video #videoPreview class="video-preview" autoplay muted playsinline></video>

      <button class="btn-stop" [disabled]="stopping()" (click)="stop()">
        {{ stopping() ? 'Wird beendet…' : '■ Aufzeichnung beenden' }}
      </button>
    </div>
  `,
  styles: [`
    .live-card { background: #1a2535; border-radius: 16px; padding: 32px; max-width: 520px; color: #e8edf5; display: flex; flex-direction: column; gap: 24px; }
    .status-row { display: flex; align-items: center; gap: 10px; }
    .rec-dot { width: 10px; height: 10px; border-radius: 50%; background: #ef5350; animation: blink 1s step-start infinite; }
    .rec-label { font-size: 12px; font-weight: 700; color: #ef5350; letter-spacing: .1em; flex: 1; }
    .chip { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #2a3545; color: #9aa8c4; }
    .chip--ok { background: #1b3a2a; color: #4caf50; }
    .rings-row { display: flex; justify-content: center; gap: 32px; }
    .video-preview { width: 100%; border-radius: 10px; background: #111; max-height: 200px; object-fit: cover; }
    .btn-stop { width: 100%; padding: 16px; border-radius: 10px; border: 2px solid #ef5350; background: transparent; color: #ef5350; font-size: 16px; font-weight: 600; cursor: pointer; }
    .btn-stop:disabled { opacity: 0.4; cursor: not-allowed; }
    @keyframes blink { 50% { opacity: 0; } }
  `],
})
export class LiveCaptureComponent implements AfterViewInit {
  @ViewChild('videoPreview') videoRef!: ElementRef<HTMLVideoElement>;

  private store = inject(Store);
  private brainDevice = inject(BrainDevice);
  private imuService = inject(ImuService);
  private videoService = inject(VideoRecorderService);
  private captureService = inject(CaptureSessionService);

  protected focus = toSignal(this.brainDevice.focus$, { initialValue: null });
  protected calm = toSignal(this.brainDevice.calm$, { initialValue: null });
  protected leftOk = toSignal(this.imuService.leftConnected$, { initialValue: false });
  protected rightOk = toSignal(this.imuService.rightConnected$, { initialValue: false });
  protected stopping = toSignal(
    this.store.select((s: any) => s.capture?.status === 'uploading'),
    { initialValue: false },
  );

  ngAfterViewInit(): void {
    const stream = this.videoService.previewStream;
    if (stream) this.videoRef.nativeElement.srcObject = stream;
  }

  async stop(): Promise<void> {
    await this.captureService.stopSession();
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/components/live-capture/live-capture.component.ts
git commit -m "feat(capture): add LiveCaptureComponent with EEG rings, IMU chips, video preview"
```

---

## Task 13: UploadProgressComponent

**Files:**
- Create: `src/app/modules/capture/components/upload-progress/upload-progress.component.ts`

Shows combined upload progress bar. On completion shows session ID. On error shows retry option that calls `CaptureActions.Reset` to restart.

- [ ] **Step 1: Create UploadProgressComponent**

```typescript
// src/app/modules/capture/components/upload-progress/upload-progress.component.ts
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureState } from '../../state/capture.state';
import { CaptureUploadService } from '../../services/capture-upload.service';
import { CaptureActions } from '../../state/capture.actions';

@Component({
  selector: 'app-upload-progress',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="progress-card">
      @switch (status()) {
        @case ('uploading') {
          <h2 class="progress-title">Wird hochgeladen…</h2>
          <div class="bar-track">
            <div class="bar-fill" [style.width.%]="progress()"></div>
          </div>
          <p class="progress-pct">{{ progress() }}%</p>
        }
        @case ('done') {
          <h2 class="progress-title">Aufzeichnung abgeschlossen</h2>
          <p class="progress-id">Session-ID: <code>{{ sessionId() }}</code></p>
          <button class="btn-primary" (click)="reset()">Neue Aufzeichnung</button>
        }
        @case ('error') {
          <h2 class="progress-title progress-title--error">Upload fehlgeschlagen</h2>
          <p class="progress-error">{{ error() }}</p>
          <button class="btn-primary" (click)="reset()">Erneut versuchen</button>
        }
      }
    </div>
  `,
  styles: [`
    .progress-card { background: #1a2535; border-radius: 16px; padding: 40px; max-width: 480px; color: #e8edf5; text-align: center; }
    .progress-title { font-size: 20px; margin-bottom: 24px; }
    .progress-title--error { color: #ef5350; }
    .bar-track { width: 100%; height: 8px; background: #2a3545; border-radius: 4px; overflow: hidden; margin-bottom: 12px; }
    .bar-fill { height: 100%; background: #1976D2; border-radius: 4px; transition: width 0.3s; }
    .progress-pct { color: #9aa8c4; font-size: 14px; }
    .progress-id { color: #9aa8c4; font-size: 13px; margin-bottom: 24px; }
    .progress-id code { color: #e8edf5; font-family: 'DM Mono', monospace; }
    .progress-error { color: #ef5350; font-size: 13px; margin-bottom: 24px; }
    .btn-primary { padding: 14px 32px; border-radius: 10px; border: none; background: #1976D2; color: #fff; font-size: 15px; cursor: pointer; }
  `],
})
export class UploadProgressComponent {
  private store = inject(Store);
  private uploadService = inject(CaptureUploadService);

  protected status = toSignal(this.store.select(CaptureState.status), { initialValue: 'uploading' as any });
  protected sessionId = toSignal(this.store.select(CaptureState.sessionId), { initialValue: null });
  protected error = toSignal(this.store.select(CaptureState.error), { initialValue: null });
  protected progress = toSignal(this.uploadService.progress$, { initialValue: 0 });

  reset(): void {
    this.store.dispatch(new CaptureActions.Reset());
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

- [ ] **Step 3: End-to-end smoke test (mock IMU + camera)**

Run `ng serve`. Navigate to `http://localhost:4200/capture`. Walk through:
1. Consent screen renders in German — checkbox enables "Weiter" button.
2. After consent, hardware setup screen appears.
3. (Cannot test BLE without hardware — verify UI renders, error messages show correctly for unsupported browser.)
4. Verify all screen transitions compile and render without console errors.

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/components/upload-progress/upload-progress.component.ts
git commit -m "feat(capture): add UploadProgressComponent with progress bar, done confirmation, error retry"
```

---

## Task 14: Final wiring verification

- [ ] **Step 1: Confirm `main.ts` has all providers**

Verify `src/main.ts` contains:
- `provideStorage(() => getStorage())`
- `CaptureState` in `provideStore([ExerciseState, CaptureState], ...)`

- [ ] **Step 2: Full production build**

```bash
ng build
```

Expected: production build succeeds with no errors. Bundle warnings about size are acceptable (video recording adds weight).

- [ ] **Step 3: Walk the full flow in browser**

```bash
ng serve
```

Navigate to `/capture`. Walk through all 5 screens. Verify state transitions in Redux DevTools (NGXS logger in console should show each action dispatch).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(capture): wire all capture providers and verify full flow"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✓ Consent screen + GDPR versioning (Task 9)
- ✓ Hardware setup: BLE left/right + camera + EEG status (Task 10)
- ✓ Task selector with predefined types + free-text label (Task 11)
- ✓ Live capture: EEG rings + IMU chips + video preview + STOP (Task 12)
- ✓ Upload progress + done + error states (Task 13)
- ✓ Firebase Storage: video + imu_left.bin + imu_right.bin (Task 6)
- ✓ Firestore: `captures/{id}` doc + `eeg/` subcollection (Task 7)
- ✓ `workers/{workerId}` consent doc (Task 9)
- ✓ Worker token via localStorage UUID (Task 3)
- ✓ IMU binary buffer (Float32, 7 floats/frame) (Task 4)
- ✓ EEG ticks write on each BrainDevice emission (Task 7)
- ✓ `CaptureState` with all 7 status values (Task 2)
- ✓ `inFlow: false` stub with TODO comment (Task 7)

**Gaps noted:**
- `shopId` is hardcoded as `'pilot-shop-01'` in `TaskSelectorComponent`. Make configurable per-device before field deployment.
- `MediaRecorder` `mimeType: 'video/mp4; codecs=avc1'` may not be supported on all Android devices. Add a fallback to `'video/webm'` if needed during pilot.
- Firebase Storage security rules not covered — must be updated in Firebase console before real sessions.
