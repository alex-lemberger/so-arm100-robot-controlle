# Handwerk Capture Platform — Implementation Summary

Date: 2026-06-04

## Summary

The Handwerk capture platform has a first-pass Phase 1 implementation in the
Angular app. The feature adds a `/capture` route where a worker can move through
consent, hardware setup, task selection, live recording, and upload progress.

The implementation compiles and reflects the intended architecture from the
capture plan, but it is not field-ready. Real hardware protocol integration,
Firebase Storage rules, real-device validation, and GDPR/operator workflows are
still required before pilot deployment.

## Implemented

### Core Architecture

- `CaptureState` for session status, worker token, task selection, session ID,
  upload progress, and error state.
- Capture models for sessions, EEG ticks, IMU frames, consent version, and task
  types.
- `WorkerTokenService` for anonymous worker UUID persistence in `localStorage`.
- `ImuService` placeholder BLE implementation for left/right hand IMU capture.
- `VideoRecorderService` using `getUserMedia` and `MediaRecorder`, with MIME
  fallback from MP4 to WebM.
- `CaptureUploadService` for resumable Firebase Storage uploads.
- `CaptureSessionService` orchestration for session documents, EEG tick writes,
  video/IMU stop, uploads, and success/failure status updates.

### Routing And Screens

- `/capture` route outside the dashboard shell.
- `CaptureShellComponent` for status-driven screen routing.
- `WorkerConsentComponent` for consent acknowledgement and worker record writes.
- `HardwareSetupComponent` for BLE glove, camera, and EEG connection checks.
- `TaskSelectorComponent` for task type and free-text task label.
- `LiveCaptureComponent` with EEG rings, IMU chips, video preview, and stop flow.
- `UploadProgressComponent` backed by NGXS upload progress state.

### Integration Fixes

- Upload progress now flows through `CaptureState`.
- Task selection dispatches `CaptureActions.SetTask`.
- EEG setup has an explicit connect path.
- Failed start/stop/upload paths move state toward `error` and mark Firestore
  sessions failed when possible.
- Dashboard weekly bar chart no longer triggers Angular `NG0955` duplicate-key
  warnings.

## Current Hardware Direction

The recommended Phase 1 hardware path is:

- 2x MbientLab MetaMotionS sensors for active left/right hand or wrist capture.
- 1x spare MetaMotionS sensor.
- 1x Neurosity Crown for EEG focus/calm capture.
- 1x Android tablet running Chrome for Web Bluetooth, camera, and upload.
- Durable work gloves or wrist straps with repeatable sensor mounts.

See `docs/superpowers/specs/2026-06-04-handwerk-hardware-list.md` for the full
hardware list and alternatives.

## Remaining Work

- Replace placeholder IMU UUIDs/protocol handling with the selected hardware's
  real BLE/GATT protocol.
- Add Firebase Storage rules for authenticated writes to `captures/{sessionId}/`.
- Decide whether `/capture` should require Firebase login or allow anonymous
  pilot capture.
- Make `shopId` configurable instead of hardcoded.
- Integrate `FlowDetectorService`; current EEG ticks still use `inFlow: false`.
- Field-test the complete flow on Android Chrome with real hardware.
- Add GDPR deletion/export and failed-session operator workflows.
- Add automated coverage once the known Karma/Neurosity test blocker is fixed
  or bypassed.

## Verification

Latest implementation verification used:

```bash
npm run build -- --configuration development
```

Result: build completed successfully.

`ng test` is not used as the primary verification path because the repository
documents a known Karma failure from the `@neurosity/sdk` browser bundle.

## Related Documents

- `docs/PROJECT_INTENT.md`
- `docs/superpowers/plans/2026-06-04-handwerk-capture-platform.md`
- `docs/superpowers/progress/2026-06-04-handwerk-capture-progress.md`
- `docs/superpowers/specs/2026-06-04-handwerk-hardware-list.md`
