# Handwerk Skill Data Platform — Phase 1 Status Snapshot

Date: 2026-06-04

## Status

Phase 1 capture has a first-pass implementation in the Angular/Firebase app.
The implementation compiles and reflects the planned architecture, but it is
not field-ready.

This document captures the current design understanding after implementation,
review, and hardware planning. For the most operational current-state document,
see `docs/superpowers/progress/2026-06-04-handwerk-capture-progress.md`.

## Goal

Build a multimodal skill-capture platform for German industrial assembly and
Handwerk work. Skilled workers perform real tasks while the system records
anonymous, consented, synchronized sensor and video data.

The captured data is intended for later processing, annotation, quality review,
and possible AI/robotics training datasets.

## Current Phase

Phase 1 is capture only:

- consent and anonymous worker token,
- EEG focus/calm capture,
- left/right hand or wrist IMU capture,
- work-surface video capture,
- task metadata,
- Firebase/Firestore session metadata and EEG ticks,
- Firebase Storage uploads for video and IMU binaries.

Phase 1 does not include buyer portals, marketplace workflows, revenue sharing,
dataset exports, automated labeling, or production GDPR operator tooling.

## Current Architecture

```text
BrainDevice EEG streams
        |
        v
CaptureSessionService
        |
        +--> Firestore captures/{sessionId}
        +--> Firestore captures/{sessionId}/eeg/{tickId}
        +--> ImuService left/right buffers
        +--> VideoRecorderService video blob
        +--> CaptureUploadService Firebase Storage upload
        +--> CaptureState NGXS lifecycle state
```

## Data Model

### Firestore session metadata

```text
captures/{sessionId}
  sessionId: string
  workerId: string
  taskType: string
  taskLabel: string
  startTime: Timestamp
  endTime?: Timestamp
  status: "recording" | "uploading" | "complete" | "failed"
  videoPath?: string
  imuLeftPath?: string
  imuRightPath?: string
  eegTickCount: number
  consentVersion: string
  shopId: string
```

### Firestore EEG ticks

```text
captures/{sessionId}/eeg/{tickId}
  t: Timestamp
  focus: number
  calm: number
  inFlow: boolean
```

`inFlow` is currently stubbed as `false` until `FlowDetectorService` is
implemented and wired into capture.

### Firebase Storage

```text
captures/{sessionId}/video.mp4 or video.webm
captures/{sessionId}/imu_left.bin
captures/{sessionId}/imu_right.bin
```

## Hardware Direction

Recommended Phase 1 pilot kit:

- 2x MbientLab MetaMotionS sensors for active left/right hand or wrist capture.
- 1x spare MetaMotionS sensor.
- 1x Neurosity Crown for EEG focus/calm capture.
- 1x Android tablet running Chrome for Web Bluetooth, camera, and upload.
- Work gloves or wrist straps with repeatable sensor mounts.

See `docs/superpowers/specs/2026-06-04-handwerk-hardware-list.md` for hardware
alternatives and integration implications.

## Implementation Status

Implemented:

- `/capture` route outside the dashboard shell.
- Guided capture screens: consent, hardware setup, task selection, live capture,
  upload progress.
- `CaptureState` lifecycle model and actions.
- `WorkerTokenService`, `ImuService`, `VideoRecorderService`,
  `CaptureUploadService`, and `CaptureSessionService`.
- Firebase Storage provider setup.
- Firestore session and EEG tick writes.
- Video MIME fallback from MP4 to WebM.
- Upload progress bridged through NGXS state.
- Dashboard weekly bar chart duplicate tracking-key warning fixed.

Still open:

- Replace placeholder IMU protocol with real MetaMotionS/selected-device BLE
  protocol.
- Configure Firebase Storage rules.
- Decide Firebase-authenticated versus anonymous capture access.
- Make `shopId` deployment-configurable.
- Wire real `FlowDetectorService` output into EEG ticks.
- Field-test with real tablet, gloves, camera, EEG, and Firebase project.
- Build GDPR deletion/export and failed-session operator workflows.
- Add automated tests after fixing or bypassing the known Karma/Neurosity issue.

## Product Thesis

Skilled manual work contains tacit knowledge that is difficult to capture in
text alone: timing, hand movement, tool handling, hesitation, recovery from
small mistakes, and cognitive load changes.

The platform aims to capture that work as synchronized multimodal data. The
long-term opportunity is a dataset layer between human craft knowledge and
machine-learnable robotics or AI systems, while preserving consent,
traceability, and worker dignity.

## Boundaries

This should not become surveillance software.

Important boundaries:

- No names, email addresses, or personal identifiers in capture records.
- Consent must be explicit, versioned, and revocable.
- Data deletion/export workflows must exist before serious field deployment.
- The system captures task data and sensor traces, not worker worth.
- Future data sharing must preserve partner control and consent traceability.

## Backend Direction

Phase 1 uses Firebase because it is already integrated and suitable for a small
pilot. Phase 2 can evaluate Supabase/Postgres for buyer-facing dataset queries,
metadata filtering, access control, and larger-scale storage workflows.

## Related Documents

- `docs/PROJECT_INTENT.md`
- `docs/superpowers/plans/2026-06-04-handwerk-capture-platform.md`
- `docs/superpowers/progress/2026-06-04-handwerk-capture-progress.md`
- `docs/superpowers/specs/2026-06-04-handwerk-hardware-list.md`
