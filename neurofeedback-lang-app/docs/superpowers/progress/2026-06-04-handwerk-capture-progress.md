# Handwerk Capture Platform — Current Progress

Date: 2026-06-04

## Current Status

Phase 1 capture is implemented as a first-pass Angular/Firebase feature at `/capture`.
The route, NGXS state, capture services, and guided screens exist and compile in the
development build.

The feature is not field-ready yet. Hardware UUIDs, Firebase Storage rules, real
device validation, and several data-quality/error-handling items remain.

## Implemented

- Arduino Nano 33 BLE Sense firmware (`arduino/glove-imu/glove-imu.ino`) — 50 Hz GATT notify, 12-byte Int16 packets, GloveLeft/GloveRight names.
- `ImuService` — real service/characteristic UUIDs, `namePrefix` BLE filter, corrected `parseFrame()`, `error$` per-hand, one-shot auto-reconnect on `gattserverdisconnected`, 11 specs green.
- `/capture` route outside the dashboard shell.
- `CaptureState` with worker, task, session, status, upload progress, and error state.
- Worker consent flow that creates or reuses an anonymous localStorage worker token
  and writes consent metadata to `workers/{workerId}`.
- Hardware setup screen for left IMU glove, right IMU glove, camera, and EEG connection.
- Task selector with predefined task types and free-text task label.
- Live capture screen with focus/calm rings, IMU connection chips, and camera preview.
- Upload progress screen backed by NGXS upload progress state.
- `CaptureSessionService` orchestration for session document creation, EEG tick writes,
  video/IMU stop, upload, and complete/failed status updates.
- Firebase Storage uploads for video plus left/right IMU binary buffers.
- MediaRecorder MIME fallback from MP4 to WebM, with matching uploaded video extension.
- Dashboard weekly bar chart tracking fix for Angular `NG0955` duplicate-key warnings.

## Fixed In Latest Pass

- Added an EEG connect path in hardware setup instead of gating forever on
  `BrainDevice.state$.isLoggedIn`.
- Dispatches `CaptureActions.SetTask` before starting capture.
- Bridges `CaptureUploadService.progress$` into `CaptureState.uploadProgress`.
- Routes upload progress UI through `CaptureState`.
- Wraps start/stop/upload errors so NGXS and Firestore move to failed state when possible.
- Adds supported video MIME selection instead of assuming `video/mp4; codecs=avc1`.
- Handles zero-byte upload progress defensively so progress stays numeric.
- Stops IMU recording before awaiting video stop during session shutdown.
- Fixes `@for` tracking in `WeeklyBarChartComponent` by using `$index` for fixed
  weekday slots.

## Remaining To-Dos

- Add Firebase Storage rules for authenticated writes to `captures/{sessionId}/`.
- Field-test the full flow on Chrome/Android with real gloves, real camera, and real EEG.
- Decide whether capture should require Firebase login or allow anonymous pilot capture.
- Add `FlowDetectorService` integration; current EEG ticks still use `inFlow: false`.
- Make `SHOP_ID` configurable per deployment instead of hardcoded as `pilot-shop-01`.
- Add a deletion/export operator workflow for GDPR requests.
- Add automated coverage once the existing Karma/Neurosity test setup is fixed or bypassed.

## Verification

Latest verification run:

```bash
npm run build -- --configuration development
```

Result: build completed successfully.

`ng test` is still not used for verification because the repository documents a
known Karma failure caused by the `@neurosity/sdk` browser bundle.

## Related Plan

- `docs/superpowers/plans/2026-06-04-handwerk-capture-platform.md`
