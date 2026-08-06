# Handwerk Skill Data Platform — Design Spec (Phase 1: Capture)

_Date: 2026-06-04 · Status: approved (design), pending implementation plan_

## Goal

Build a multimodal skill-capture platform targeting German industrial assembly
and Handwerk (trades). Skilled workers wear EEG + IMU gloves + record video
during real work sessions. Captured data — anonymized, consented — is stored
for sale to robotics companies and AI labs as training datasets.

This spec covers **Phase 1 (Capture)** only: extending the existing Angular app
with a worker-facing capture mode that records EEG + IMU + video per session
and uploads raw data to Firebase Storage/Firestore.

## Background

Existing app: Angular 19 SPA with Neurosity EEG integration (`BrainDevice`
abstraction), Firebase/Firestore backend, NGXS state management. The capture
feature extends this app at a new `/capture` route rather than replacing it.

## Phases Overview

| Phase | Scope | Status |
|---|---|---|
| **1 — Capture** | Worker capture mode: EEG + IMU + video per session | This spec |
| **2 — Pipeline** | Anonymization, labeling, buyer-ready dataset export | Future spec |
| **3 — Marketplace** | Buyer portal, data catalog, revenue share accounting | Future spec |

Pilot target: 10–20 real sessions across 2–3 German Handwerk shops before
Phase 2 begins.

## Sensor Stack

| Sensor | Data | Rate | Transport |
|---|---|---|---|
| Neurosity Crown (EEG) | focus, calm, inFlow | 1 Hz | Existing `BrainDevice` |
| BLE IMU gloves (×2) | ax/ay/az, gx/gy/gz per hand | 50 Hz | Web Bluetooth API |
| Phone/tablet camera | MP4 video of work surface | Variable | MediaRecorder API |

Pilot devices standardize on **Chrome on Android tablet** — required for Web
Bluetooth support.

## Architecture

```
Existing                        New (Phase 1)
────────────────                ─────────────────────────────────────
BrainDevice (EEG) ─────────────► CaptureSessionService
                                    │  orchestrates all 3 streams
ImuService ────────────────────►    │  manages session lifecycle
  Web Bluetooth → BLE gloves        │  (start / stop / upload)
                                    │
VideoRecorderService ──────────►    │
  MediaRecorder API                 │
                                    ▼
CaptureUploadService ───────── Firebase Storage  (video + IMU binary)
                               Firestore          (session metadata + EEG ticks)
                               CaptureState       (NGXS session lifecycle)
```

## Data Model

### Firestore — session metadata
```
captures/{sessionId}
  workerId: string          // anonymized token — no real name stored
  taskType: string          // "engine_assembly" | "electrical_repair" | ...
  taskLabel: string         // free text description entered by worker
  startTime: Timestamp
  endTime: Timestamp
  status: "recording" | "uploading" | "complete" | "failed"
  videoPath: string         // Firebase Storage path
  imuPath: string           // Firebase Storage path
  eegTickCount: number
  consentVersion: string
  shopId: string            // pilot partner identifier
```

### Firestore — EEG ticks (subcollection)
```
captures/{sessionId}/eeg/{tickId}
  t: Timestamp
  focus: number             // 0–1
  calm: number              // 0–1
  inFlow: boolean
```

### Firebase Storage — binary files
```
captures/{sessionId}/video.mp4        // chunked resumable upload
captures/{sessionId}/imu_left.bin     // timestamp|ax|ay|az|gx|gy|gz @ 50Hz, left hand
captures/{sessionId}/imu_right.bin    // timestamp|ax|ay|az|gx|gy|gz @ 50Hz, right hand
```

### Workers — anonymized profiles
```
workers/{workerId}
  consentTimestamp: Timestamp
  consentVersion: string
  skillTags: string[]           // ["automotive", "electrical", ...]
  sessionCount: number
  // no name, email, or identifying info — GDPR Art. 9 compliance
```

### Worker token persistence

`workerToken` is a UUID generated on first consent and stored in browser
`localStorage`. On subsequent sessions the worker scans a QR code or the token
is pre-loaded — no login required. The token is the only link between a worker's
sessions; no account or PII is involved.

### GDPR

Neural and motion data qualify as **biometric data** under GDPR Art. 9.
Requirements:
- Explicit, versioned consent per worker stored in Firestore before any capture
- Data deletion right: delete all `captures/{sessionId}` Storage files +
  Firestore docs by sessionId on request
- No PII stored in any collection — workerIds are UUID tokens only

## New Services

### `CaptureSessionService`
Orchestrates all three streams. Responsibilities:
- Generate `sessionId` (UUID) on session start
- Subscribe to `BrainDevice.focus$` / `calm$` / `FlowDetectorService.inFlow$`,
  write EEG ticks to Firestore subcollection
- Delegate IMU buffering to `ImuService`
- Delegate video chunking to `VideoRecorderService`
- On stop: trigger uploads via `CaptureUploadService`, update session status

### `ImuService`
- Web Bluetooth scan and connect to left + right BLE glove
- Stream accelerometer + gyroscope at 50 Hz
- Buffer readings in memory as binary (Float32 typed array)
- Expose `leftConnected$: Observable<boolean>`, `rightConnected$: Observable<boolean>`
- On session stop: hand binary buffer to `CaptureUploadService`

### `VideoRecorderService`
- Request camera permission via `getUserMedia`
- Record via `MediaRecorder`, collect `Blob` chunks
- On session stop: assemble chunks, hand to `CaptureUploadService`

### `CaptureUploadService`
- Firebase Storage resumable uploads for video + IMU binary
- Expose `progress$: Observable<number>` (0–100, combined across streams)
- Auto-retry on network interruption
- On complete: update `captures/{sessionId}.status = "complete"`

## NGXS State — `CaptureState`

```ts
interface CaptureStateModel {
  workerToken: string | null;
  taskType: string | null;
  taskLabel: string | null;
  sessionId: string | null;
  status: 'idle' | 'setup' | 'recording' | 'uploading' | 'done' | 'error';
  uploadProgress: number;    // 0–100
}
```

Actions: `StartSetup`, `SetTask`, `StartRecording`, `StopRecording`,
`UploadProgress`, `UploadComplete`, `UploadFailed`.

## Route & Components

New route: `/capture` (outside dashboard shell, standalone).

### Screen sequence
```
1. Consent          — display consent text, worker acknowledges, version stored
                      to workers/{workerId}
2. Hardware Setup   — Web Bluetooth scan (left + right glove status chips),
                      camera permission check, EEG connection status
                      → cannot proceed until all 3 connected
3. Task Selector    — pick taskType from predefined list, enter taskLabel
                      (free text, e.g. "replacing brake caliper on BMW 3er")
4. Live Capture     — EEG arc ring (reuse dashboard widget)
                    — IMU status chips (left ✓ / right ✓, disconnect warning)
                    — video preview (live camera feed, muted)
                    — RECORD button → recording state
                    — STOP button → triggers upload
5. Upload Progress  — progress bar per stream (EEG / IMU / video)
                    — done confirmation with sessionId shown
```

### Reused from existing app
- `BrainDevice` EEG streams
- `FlowDetectorService` (`inFlow$` overlay on arc ring)
- Arc ring widget (`dashboard-layout/widgets/`)

### New components
- `CaptureShellComponent` — route host, `CaptureState` provider
- `WorkerConsentComponent` — consent display + acknowledgement
- `HardwareSetupComponent` — Bluetooth scan, camera check, EEG status
- `TaskSelectorComponent` — taskType picker + taskLabel input
- `LiveCaptureComponent` — recording view with all sensor overlays
- `UploadProgressComponent` — per-stream progress + completion state

## Error Handling

| Failure | Behavior |
|---|---|
| Web Bluetooth not supported | Block at setup, show "requires Chrome on Android" |
| IMU glove disconnects mid-session | Warn + pause IMU buffer; EEG + video continue |
| Camera permission denied | Block — video required for pilot data quality |
| EEG disconnects mid-session | Warn; IMU + video continue; EEG ticks gap-flagged |
| Upload fails | Resumable upload auto-retries; manual retry button on full failure |
| Network loss during recording | Buffer IMU + EEG in memory; upload queued on reconnect |
| App closed mid-session | Mark session `failed` in Firestore; partial files retained for operator review |

No automatic data deletion on failure — operator reviews and cleans manually.

## Dependencies

- **`FlowDetectorService`** — referenced in `CaptureSessionService` for `inFlow$`
  ticks. Implementation plan committed but not yet built (see
  `docs/superpowers/specs/2026-06-04-flow-detection-design.md`). Phase 1
  implementation must complete flow detection first, or stub `inFlow$` as
  `false` until it ships.

## Backend Migration Plan (Phase 2)

**Decision:** Phase 1 uses Firebase (Firestore + Storage) because `@angular/fire`
is already integrated and pilot scale (~20 sessions, ~$5–10 total cost) makes
the saving trivial. Phase 2 will migrate capture data to **Supabase** (Pro
account already available).

**Rationale for Supabase at Phase 2:**
- PostgreSQL is far better than Firestore for buyer-facing dataset queries
  (filter by taskType, focus average, duration, shopId, date range, etc.)
- Supabase Storage is S3-compatible, handles large binaries identically to
  Firebase Storage, and is cheaper at scale (100 GB included in Pro)
- Row-level security makes buyer data access control cleaner than Firestore rules
- Single backend for Phase 2 platform (session metadata + binary storage + auth)

**Migration scope for Phase 2 spec:**
- Session metadata + EEG ticks: Firestore → Supabase PostgreSQL tables
- Binary files (video, IMU): Firebase Storage → Supabase Storage
- Auth: Firebase Auth → Supabase Auth (or keep Firebase Auth, both are viable)
- Keep Firestore data model shallow in Phase 1 to avoid deep migration debt —
  no denormalization or collection-group queries that would be hard to port

## Out of Scope (Phase 1)

- Data processing, labeling, or anonymization pipeline
- Buyer portal or data catalog
- Revenue share accounting
- Runtime device selection beyond Neurosity Crown
- Session playback or review UI
- Multi-worker simultaneous capture
