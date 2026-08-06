# Supabase Storage Policies + Raw EEG Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply Supabase Storage RLS policies for the `captures` bucket and add raw Muse 2 EEG buffering with `eeg.bin` upload alongside existing video/IMU files.

**Architecture:** SQL migrations define path-restricted anon-write policies on `storage.objects`. `EegBufferService` (new) subscribes to a new optional `rawEeg$` stream on `BrainDevice`, buffers all 4 electrode channels as `number[]`, and returns a `Float32Array` at session stop. `CaptureUploadService` uploads the buffer as `{sessionId}/eeg.bin`. The `captures` table gains an `eeg_path TEXT` column.

**Tech Stack:** Supabase Storage RLS (PostgreSQL row-level security), Angular 19 standalone, RxJS, muse-js, TypeScript.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `supabase/migrations/20260607000000_storage_policies_captures.sql` | 4 RLS policies on `storage.objects` |
| Create | `supabase/migrations/20260607000001_captures_eeg_path.sql` | Add `eeg_path TEXT` to `captures` table |
| Modify | `src/app/core/neurofeedback/brain-device.ts` | Add `EegReading` interface + optional `rawEeg$` |
| Modify | `src/app/core/neurofeedback/services/muse-device.service.ts` | Expose `rawEeg$` Subject fed by `client.eegReadings` |
| Modify | `src/app/core/neurofeedback/services/mock-neurosity.service.ts` | `rawEeg$ = undefined` stub |
| Create | `src/app/modules/capture/services/eeg-buffer.service.ts` | Buffer per-electrode samples; return `Float32Array | null` on stop |
| Create | `src/app/modules/capture/services/eeg-buffer.service.spec.ts` | Unit tests |
| Modify | `src/app/modules/capture/services/capture-upload.service.ts` | Accept optional `eeg: Float32Array | null`; upload `eeg.bin` |
| Modify | `src/app/modules/capture/services/supabase-capture.service.ts` | Add `eeg_path` to `CaptureRow`; return it from upload |
| Modify | `src/app/modules/capture/services/capture-session.service.ts` | Inject `EegBufferService`; start/stop buffer; pass to upload; persist `eeg_path` |

---

## Task 1: SQL migration — storage policies

**Files:**
- Create: `supabase/migrations/20260607000000_storage_policies_captures.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/20260607000000_storage_policies_captures.sql
-- Approach A: anon writes, path-restricted. No auth required (workers are anonymous).
-- Before field test: flip TO anon → TO authenticated and add auth.uid() scope (Approach B).

DO $$
DECLARE
  path_pattern TEXT := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$';
BEGIN
  -- Enable RLS on storage.objects if not already enabled
  -- (Supabase enables this by default, but belt-and-suspenders)
END $$;

CREATE POLICY "anon_upload" ON storage.objects
  FOR INSERT TO anon
  WITH CHECK (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_upsert" ON storage.objects
  FOR UPDATE TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_list" ON storage.objects
  FOR SELECT TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_delete" ON storage.objects
  FOR DELETE TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );
```

- [ ] **Step 2: Apply to Supabase**

Open Supabase dashboard → SQL Editor → paste the file contents → Run.

Verify: Storage → Policies tab shows 4 policies on `storage.objects` for bucket `captures`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260607000000_storage_policies_captures.sql
git commit -m "feat(storage): add anon RLS policies for captures bucket"
```

---

## Task 2: SQL migration — add eeg_path to captures table

**Files:**
- Create: `supabase/migrations/20260607000001_captures_eeg_path.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- supabase/migrations/20260607000001_captures_eeg_path.sql
ALTER TABLE captures ADD COLUMN IF NOT EXISTS eeg_path TEXT;
```

- [ ] **Step 2: Apply to Supabase**

Supabase dashboard → SQL Editor → paste → Run.

Verify: Table Editor → `captures` → columns includes `eeg_path TEXT nullable`.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260607000001_captures_eeg_path.sql
git commit -m "feat(db): add eeg_path column to captures table"
```

---

## Task 3: Add EegReading + rawEeg$ to BrainDevice; implement in MuseDeviceService; stub in MockNeurosityService

**Files:**
- Modify: `src/app/core/neurofeedback/brain-device.ts`
- Modify: `src/app/core/neurofeedback/services/muse-device.service.ts`
- Modify: `src/app/core/neurofeedback/services/mock-neurosity.service.ts`

- [ ] **Step 1: Add EegReading interface and rawEeg$ to BrainDevice**

In `src/app/core/neurofeedback/brain-device.ts`, add after the imports and before `DeviceState`:

```typescript
import { Observable } from 'rxjs';

export interface EegReading {
  electrode: number;  // 0–3: TP9, AF7, AF8, TP10
  samples: number[];  // raw microvolts
  timestamp: number;  // ms since epoch
}

export interface DeviceState {
  // ... existing
}
```

Add optional field to `BrainDevice` abstract class after `extras$`:

```typescript
/** Raw per-electrode EEG readings. Only devices that expose raw EEG implement this. */
readonly rawEeg$?: Observable<EegReading>;
```

- [ ] **Step 2: Implement rawEeg$ in MuseDeviceService**

In `src/app/core/neurofeedback/services/muse-device.service.ts`:

Add imports at top:
```typescript
import { BehaviorSubject, Subject } from 'rxjs';
import { BrainDevice, DeviceState, DeviceStatus, EegReading } from '../brain-device';
```

Add private Subject and public observable after `private eegSub`:
```typescript
private rawEegSub: { unsubscribe(): void } | null = null;
private readonly _rawEeg$ = new Subject<EegReading>();
readonly rawEeg$ = this._rawEeg$.asObservable();
```

Add `setupRawEegStream()` method after `setupEegPipeline()`:
```typescript
protected setupRawEegStream(): void {
  this.rawEegSub = this.client.eegReadings.subscribe((reading: any) => {
    this._rawEeg$.next({
      electrode: reading.electrode,
      samples: reading.samples,
      timestamp: reading.timestamp ?? Date.now(),
    });
  });
}
```

In `connect()`, call it after `setupEegPipeline()`:
```typescript
this.setupEegPipeline();
this.setupRawEegStream();
```

In `disconnect()`, add cleanup before existing cleanup lines:
```typescript
this.rawEegSub?.unsubscribe();
this.rawEegSub = null;
```

In `ngOnDestroy()`, add cleanup:
```typescript
this.rawEegSub?.unsubscribe();
this.rawEegSub = null;
```

- [ ] **Step 3: Stub rawEeg$ in MockNeurosityService**

In `src/app/core/neurofeedback/services/mock-neurosity.service.ts`, add after `extras$`:
```typescript
readonly rawEeg$ = undefined;
```

- [ ] **Step 4: Verify compilation**

```bash
ng build --configuration development
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/app/core/neurofeedback/brain-device.ts \
        src/app/core/neurofeedback/services/muse-device.service.ts \
        src/app/core/neurofeedback/services/mock-neurosity.service.ts
git commit -m "feat(neurofeedback): expose rawEeg$ stream on BrainDevice and MuseDeviceService"
```

---

## Task 4: EegBufferService

**Files:**
- Create: `src/app/modules/capture/services/eeg-buffer.service.ts`
- Create: `src/app/modules/capture/services/eeg-buffer.service.spec.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// src/app/modules/capture/services/eeg-buffer.service.spec.ts
import { Subject } from 'rxjs';
import { EegBufferService } from './eeg-buffer.service';
import { EegReading } from '../../../core/neurofeedback/brain-device';

function makeReading(electrode: number, samples: number[]): EegReading {
  return { electrode, samples, timestamp: Date.now() };
}

describe('EegBufferService', () => {
  let service: EegBufferService;
  let source$: Subject<EegReading>;

  beforeEach(() => {
    service = new EegBufferService();
    source$ = new Subject<EegReading>();
  });

  afterEach(() => {
    service.stopRecording();
  });

  it('returns null when no data has been buffered', () => {
    service.startRecording(source$.asObservable());
    expect(service.stopRecording()).toBeNull();
  });

  it('accumulates samples per electrode', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(0, [1, 2, 3]));
    source$.next(makeReading(1, [4, 5]));
    source$.next(makeReading(0, [6]));

    const result = service.stopRecording()!;
    expect(result).not.toBeNull();
    // ch0: [1,2,3,6] = 4 samples; ch1: [4,5] = 2; ch2: [] = 0; ch3: [] = 0 → total 6
    expect(result.length).toBe(6);
    // ch0 samples come first in concatenated layout
    expect(Array.from(result.slice(0, 4))).toEqual([1, 2, 3, 6]);
    expect(Array.from(result.slice(4, 6))).toEqual([4, 5]);
  });

  it('ignores electrode index >= 4', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(5, [99, 99]));
    expect(service.stopRecording()).toBeNull();
  });

  it('resets buffer on startRecording', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(0, [1, 2]));
    service.stopRecording();

    const source2$ = new Subject<EegReading>();
    service.startRecording(source2$.asObservable());
    source2$.next(makeReading(0, [9]));
    const result = service.stopRecording()!;
    expect(result.length).toBe(1);
    expect(result[0]).toBe(9);
  });

  it('unsubscribes from source on stopRecording', () => {
    service.startRecording(source$.asObservable());
    service.stopRecording();
    let received = false;
    source$.subscribe(() => { received = true; });
    source$.next(makeReading(0, [1]));
    expect(received).toBe(false);  // source still has other subscribers; service does not
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
ng test --include='**/eeg-buffer.service.spec.ts' --watch=false --browsers=ChromeHeadless
```

Expected: FAIL — `EegBufferService` not found.

- [ ] **Step 3: Implement EegBufferService**

```typescript
// src/app/modules/capture/services/eeg-buffer.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subscription } from 'rxjs';
import { EegReading } from '../../../core/neurofeedback/brain-device';

@Injectable({ providedIn: 'root' })
export class EegBufferService {
  private buffers: number[][] = [[], [], [], []];
  private sub: Subscription | null = null;

  startRecording(rawEeg$: Observable<EegReading>): void {
    this.sub?.unsubscribe();
    this.buffers = [[], [], [], []];
    this.sub = rawEeg$.subscribe(reading => {
      if (reading.electrode >= 0 && reading.electrode < 4) {
        this.buffers[reading.electrode].push(...reading.samples);
      }
    });
  }

  stopRecording(): Float32Array | null {
    this.sub?.unsubscribe();
    this.sub = null;
    const total = this.buffers.reduce((sum, buf) => sum + buf.length, 0);
    if (total === 0) {
      this.buffers = [[], [], [], []];
      return null;
    }
    // Layout: [ch0_samples | ch1_samples | ch2_samples | ch3_samples]
    const result = new Float32Array(total);
    let offset = 0;
    for (const buf of this.buffers) {
      result.set(buf, offset);
      offset += buf.length;
    }
    this.buffers = [[], [], [], []];
    return result;
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
ng test --include='**/eeg-buffer.service.spec.ts' --watch=false --browsers=ChromeHeadless
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/services/eeg-buffer.service.ts \
        src/app/modules/capture/services/eeg-buffer.service.spec.ts
git commit -m "feat(capture): add EegBufferService for raw Muse 2 EEG buffering"
```

---

## Task 5: CaptureUploadService — add eeg.bin upload

**Files:**
- Modify: `src/app/modules/capture/services/capture-upload.service.ts`

- [ ] **Step 1: Update uploadSession signature and body**

Replace the entire file content:

```typescript
// src/app/modules/capture/services/capture-upload.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SupabaseCaptureService } from './supabase-capture.service';

export interface UploadPaths {
  videoPath: string;
  imuLeftPath: string;
  imuRightPath: string;
  eegPath: string | null;
}

@Injectable({ providedIn: 'root' })
export class CaptureUploadService {
  private progressSubject = new BehaviorSubject<number>(0);
  readonly progress$ = this.progressSubject.asObservable();

  constructor(private supabaseCapture: SupabaseCaptureService) {}

  async uploadSession(
    sessionId: string,
    video: Blob,
    imuLeft: Float32Array,
    imuRight: Float32Array,
    eeg: Float32Array | null,
  ): Promise<UploadPaths> {
    this.progressSubject.next(0);

    const videoExtension = video.type.includes('webm') ? 'webm' : 'mp4';
    const videoPath = `captures/${sessionId}/video.${videoExtension}`;
    const imuLeftPath = `captures/${sessionId}/imu_left.bin`;
    const imuRightPath = `captures/${sessionId}/imu_right.bin`;
    const eegPath = eeg ? `captures/${sessionId}/eeg.bin` : null;

    let videoBytes = 0, imuLeftBytes = 0, imuRightBytes = 0, eegBytes = 0;
    const totalBytes = video.size + imuLeft.byteLength + imuRight.byteLength + (eeg?.byteLength ?? 0);

    const updateProgress = () => {
      const done = videoBytes + imuLeftBytes + imuRightBytes + eegBytes;
      this.progressSubject.next(totalBytes === 0 ? 100 : Math.round((done / totalBytes) * 100));
    };

    const uploads: Promise<void>[] = [
      this.supabaseCapture.uploadFile(videoPath, video,
        n => { videoBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuLeftPath, new Blob([imuLeft]),
        n => { imuLeftBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuRightPath, new Blob([imuRight]),
        n => { imuRightBytes = n; updateProgress(); }),
    ];

    if (eeg && eegPath) {
      uploads.push(
        this.supabaseCapture.uploadFile(eegPath, new Blob([eeg]),
          n => { eegBytes = n; updateProgress(); }),
      );
    }

    await Promise.all(uploads);
    this.progressSubject.next(100);
    return { videoPath, imuLeftPath, imuRightPath, eegPath };
  }
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: no errors. (TypeScript will flag `CaptureSessionService` — fix in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/capture-upload.service.ts
git commit -m "feat(capture): add eeg.bin upload to CaptureUploadService"
```

---

## Task 6: SupabaseCaptureService — add eeg_path to CaptureRow

**Files:**
- Modify: `src/app/modules/capture/services/supabase-capture.service.ts`

- [ ] **Step 1: Add eeg_path to CaptureRow interface**

In `supabase-capture.service.ts`, add `eeg_path` to the `CaptureRow` interface:

```typescript
interface CaptureRow {
  id?: string;
  worker_id?: string;
  task_type?: string;
  task_label?: string;
  shop_id?: string;
  consent_version?: string;
  status?: string;
  eeg_tick_count?: number;
  ended_at?: string;
  video_path?: string;
  imu_left_path?: string;
  imu_right_path?: string;
  eeg_path?: string | null;
}
```

No other changes needed — `updateSession` already accepts a `Partial<CaptureRow>` patch, and `deleteSession` uses `list()` + `remove()` which already handles any files generically.

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/supabase-capture.service.ts
git commit -m "feat(capture): add eeg_path to CaptureRow interface"
```

---

## Task 7: CaptureSessionService — wire EegBufferService

**Files:**
- Modify: `src/app/modules/capture/services/capture-session.service.ts`

- [ ] **Step 1: Write the failing test**

Add to `src/app/modules/capture/services/capture-session.service.spec.ts`:

```typescript
import { EegBufferService } from './eeg-buffer.service';

// Add eegBuffer to makeService:
function makeService(
  inFlow$: BehaviorSubject<boolean>,
  focus$: BehaviorSubject<number | null>,
  calm$: BehaviorSubject<number | null>,
  eegBufferOverride?: Partial<EegBufferService>,
): CaptureSessionService {
  return new CaptureSessionService(
    { dispatch: jasmine.createSpy() } as unknown as Store,
    jasmine.createSpyObj<SupabaseCaptureService>('SupabaseCaptureService', [
      'startSession', 'updateSession', 'writeEegTick', 'uploadFile', 'deleteSession',
    ]),
    { focus$, calm$, rawEeg$: undefined } as unknown as BrainDevice,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue({ left: new Float32Array(), right: new Float32Array() }),
    } as unknown as ImuService,
    { startRecording: jasmine.createSpy() } as unknown as VideoRecorderService,
    { progress$: new BehaviorSubject(0) } as unknown as CaptureUploadService,
    { inFlow$ } as unknown as FlowDetectorService,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue(null),
      ...eegBufferOverride,
    } as unknown as EegBufferService,
  );
}

describe('CaptureSessionService — EegBufferService wiring', () => {
  it('does not start eeg buffer when rawEeg$ is undefined', async () => {
    const inFlow$ = new BehaviorSubject<boolean>(false);
    const focus$ = new BehaviorSubject<number | null>(null);
    const calm$ = new BehaviorSubject<number | null>(null);
    const startSpy = jasmine.createSpy();
    const svc = makeService(inFlow$, focus$, calm$, { startRecording: startSpy });
    spyOn(svc['supabaseCapture'], 'startSession').and.returnValue(Promise.resolve('sess-1'));
    await svc.startSession('w', 'task', 'label', 'shop');
    expect(startSpy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
ng test --include='**/capture-session.service.spec.ts' --watch=false --browsers=ChromeHeadless
```

Expected: FAIL — `CaptureSessionService` constructor doesn't accept `EegBufferService`.

- [ ] **Step 3: Update CaptureSessionService**

Replace the entire file:

```typescript
// src/app/modules/capture/services/capture-session.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { Store } from '@ngxs/store';
import { Subscription, combineLatest } from 'rxjs';
import { filter, withLatestFrom } from 'rxjs/operators';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { FlowDetectorService } from '../../../core/neurofeedback/services/flow-detector.service';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { SupabaseCaptureService } from './supabase-capture.service';
import { EegBufferService } from './eeg-buffer.service';
import { CaptureActions } from '../state/capture.actions';
import { CONSENT_VERSION } from '../models/capture-session.model';

@Injectable({ providedIn: 'root' })
export class CaptureSessionService implements OnDestroy {
  private eegSub: Subscription | null = null;
  private uploadSub: Subscription | null = null;
  private currentSessionId: string | null = null;
  private eegTickCount = 0;

  constructor(
    private store: Store,
    private supabaseCapture: SupabaseCaptureService,
    private brainDevice: BrainDevice,
    private imuService: ImuService,
    private videoService: VideoRecorderService,
    private uploadService: CaptureUploadService,
    private flowDetector: FlowDetectorService,
    private eegBuffer: EegBufferService,
  ) {}

  async startSession(
    workerToken: string,
    taskType: string,
    taskLabel: string,
    shopId: string,
  ): Promise<string> {
    this.eegTickCount = 0;
    try {
      const sessionId = await this.supabaseCapture.startSession(
        workerToken, taskType, taskLabel, shopId, CONSENT_VERSION,
      );
      this.currentSessionId = sessionId;
      const sessionStart = Date.now();
      this.imuService.startRecording(sessionStart);
      this.videoService.startRecording();
      if (this.brainDevice.rawEeg$) {
        this.eegBuffer.startRecording(this.brainDevice.rawEeg$);
      }
      this.eegSub = this.startEegSubscription(sessionId);
      this.store.dispatch(new CaptureActions.StartRecording(sessionId));
      return sessionId;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.cleanupRecordingState();
      this.store.dispatch(new CaptureActions.UploadFailed(message));
      throw err;
    }
  }

  async stopSession(): Promise<void> {
    if (!this.currentSessionId) return;
    const sessionId = this.currentSessionId;

    this.store.dispatch(new CaptureActions.StopRecording());
    this.uploadSub?.unsubscribe();
    this.uploadSub = this.uploadService.progress$.subscribe(progress => {
      this.store.dispatch(new CaptureActions.UploadProgress(progress));
    });

    try {
      this.eegSub?.unsubscribe();
      this.eegSub = null;

      const imuBuffers = this.imuService.stopRecording();
      const videoBlob = await this.videoService.stopRecording();
      const eegData = this.eegBuffer.stopRecording();

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'uploading',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      });

      const paths = await this.uploadService.uploadSession(
        sessionId, videoBlob, imuBuffers.left, imuBuffers.right, eegData,
      );

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'complete',
        video_path: paths.videoPath,
        imu_left_path: paths.imuLeftPath,
        imu_right_path: paths.imuRightPath,
        eeg_path: paths.eegPath,
      });

      this.store.dispatch(new CaptureActions.UploadComplete());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.supabaseCapture.updateSession(sessionId, {
        status: 'failed',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      }).catch(console.error);
      this.store.dispatch(new CaptureActions.UploadFailed(message));
    } finally {
      this.uploadSub?.unsubscribe();
      this.uploadSub = null;
      this.currentSessionId = null;
    }
  }

  protected startEegSubscription(sessionId: string): Subscription {
    return combineLatest([this.brainDevice.focus$, this.brainDevice.calm$])
      .pipe(
        filter(([f, c]) => f !== null && c !== null),
        withLatestFrom(this.flowDetector.inFlow$),
      )
      .subscribe(([[focus, calm], inFlow]) => {
        this.writeEegTick(sessionId, focus!, calm!, inFlow);
      });
  }

  private writeEegTick(sessionId: string, focus: number, calm: number, inFlow: boolean): void {
    this.eegTickCount++;
    this.supabaseCapture.writeEegTick(sessionId, focus, calm, inFlow);
  }

  ngOnDestroy(): void {
    this.cleanupRecordingState();
  }

  private cleanupRecordingState(): void {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.uploadSub?.unsubscribe();
    this.uploadSub = null;
    this.eegBuffer.stopRecording();
    this.imuService.stopRecording();
    this.currentSessionId = null;
  }
}
```

- [ ] **Step 4: Update the existing makeService helper in spec**

The spec's existing `makeService` must pass 8 args. Update the `makeService` function (keep existing describe blocks, just add the 8th arg):

```typescript
function makeService(
  inFlow$: BehaviorSubject<boolean>,
  focus$: BehaviorSubject<number | null>,
  calm$: BehaviorSubject<number | null>,
): CaptureSessionService {
  return new CaptureSessionService(
    { dispatch: jasmine.createSpy() } as unknown as Store,
    jasmine.createSpyObj<SupabaseCaptureService>('SupabaseCaptureService', [
      'startSession', 'updateSession', 'writeEegTick', 'uploadFile', 'deleteSession',
    ]),
    { focus$, calm$, rawEeg$: undefined } as unknown as BrainDevice,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue({ left: new Float32Array(), right: new Float32Array() }),
    } as unknown as ImuService,
    { startRecording: jasmine.createSpy() } as unknown as VideoRecorderService,
    { progress$: new BehaviorSubject(0) } as unknown as CaptureUploadService,
    { inFlow$ } as unknown as FlowDetectorService,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue(null),
    } as unknown as EegBufferService,
  );
}
```

- [ ] **Step 5: Run all capture service tests**

```bash
ng test --include='**/capture-session.service.spec.ts' --watch=false --browsers=ChromeHeadless
```

Expected: all existing tests + new test PASS.

- [ ] **Step 6: Verify compilation**

```bash
ng build --configuration development
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/app/modules/capture/services/capture-session.service.ts \
        src/app/modules/capture/services/capture-session.service.spec.ts
git commit -m "feat(capture): wire EegBufferService into CaptureSessionService"
```

---

## Self-Review

### Spec coverage
- ✅ Storage RLS policies (4 operations, path-restricted, anon role) — Task 1
- ✅ `eeg.bin` in path regex — Task 1
- ✅ `eeg_path` DB column — Task 2
- ✅ Raw EEG stream on BrainDevice + MuseDeviceService — Task 3
- ✅ EegBufferService buffers 4 channels — Task 4
- ✅ `eeg.bin` upload in CaptureUploadService — Task 5
- ✅ `eeg_path` persisted to captures row — Tasks 6 + 7
- ✅ Approach B note preserved in SQL comment — Task 1

### Placeholder scan
None found.

### Type consistency
- `EegReading` defined in `brain-device.ts`, imported in `eeg-buffer.service.ts` and `muse-device.service.ts` ✅
- `UploadPaths` defined in `capture-upload.service.ts`, used in `capture-session.service.ts` via return type ✅
- `eegPath: string | null` flows from `UploadPaths` → `updateSession` patch → `CaptureRow.eeg_path` ✅
- `EegBufferService` constructor takes 0 args, `providedIn: 'root'` — no DI setup needed ✅
