# Project Intent

## Short Version

This project is evolving from a neurofeedback language-learning prototype into a
multimodal skilled-work capture platform.

The immediate goal is to record real Handwerk and industrial work sessions with
consent, using synchronized EEG, hand/wrist motion, video, and task metadata.
Those recordings become the raw material for later dataset processing,
annotation, quality review, and AI/robotics training use cases.

## What We Are Building

The platform should let a worker perform a real task while the system captures:

- EEG focus and calm signals from a Muse 2 headset (primary; device-agnostic architecture supports Neurosity Crown when available).
- Left and right hand/wrist IMU motion from BLE sensors (Arduino Nano 33 BLE Sense) mounted on gloves.
- Video of the work surface from an Android tablet camera.
- Anonymous worker consent and session metadata.
- Task type, task description, timestamps, upload status, and failure state.

Phase 1 is the capture layer. It is not yet the full data product.

## Why This Matters

Skilled manual work contains tacit knowledge that is hard to write down:
timing, grip changes, hesitation, recovery from small mistakes, tool handling,
attention shifts, and sequencing under real-world constraints.

Most AI training data describes work from the outside: text manuals, videos,
checklists, or final outcomes. This project aims to capture work from multiple
angles at once:

- what the worker sees and does,
- how their hands move,
- when cognitive load or focus changes,
- what task context the data belongs to.

That combination can make the resulting dataset more useful than video alone.

## Current Phase

Phase 1 focuses on proving that we can capture reliable raw sessions:

- Guided `/capture` workflow in the Angular app.
- Firebase/Firestore metadata and EEG tick storage.
- Firebase Storage uploads for video and IMU binary files.
- Anonymous worker token and consent record.
- Hardware direction (revised 2026-06-05): Muse 2 EEG headset + two Arduino Nano
  33 BLE Sense IMU sensors on gloves/wrist straps + Android Chrome tablet.
  Neurosity Crown dropped — unavailable in Germany, over budget for pre-investor
  POC. `BrainDevice` abstraction allows Crown to be added later as a second adapter.

The current implementation compiles and demonstrates the intended architecture,
but it is not field-ready until the hardware protocol, Firebase rules, and real
device tests are complete.

## Product Thesis

If we can capture high-quality skilled-work sessions ethically and repeatedly,
we can build a data asset that sits between two worlds:

- the human craft world, where expertise is embodied and difficult to transfer;
- the robotics and AI world, where systems need examples of real physical skill.

The long-term opportunity is not just recording workers. It is creating a
structured bridge from human craft to machine-learnable data while preserving
consent, traceability, and worker dignity.

## Vision

A mature version of this platform could support:

- **Skill preservation:** capture expert workflows before knowledge leaves a
  workshop or industrial team.
- **Training feedback:** show apprentices how timing, hand movement, and focus
  differ from expert baselines.
- **Robotics datasets:** provide synchronized video, motion, and context for
  manipulation models.
- **Process intelligence:** identify which parts of a task create friction,
  hesitation, rework, or high cognitive load.
- **Worker-owned data models:** give workers and shops a controlled way to
  contribute valuable data without exposing personal identity.

The strongest version of the idea treats workers as data partners, not passive
subjects.

## Boundaries

This project should not become surveillance software.

Important boundaries:

- No names, email addresses, or personal identifiers in capture records.
- Consent must be explicit, versioned, and revocable.
- Data deletion/export workflows must exist before serious field deployment.
- The system should capture task performance and sensor traces, not rank workers
  as people.
- Any future marketplace or buyer portal must preserve consent, traceability,
  and partner control over what is shared.

## Near-Term Priorities

1. ✅ Live flow-state detection (`FlowDetectorService`) — complete (2026-06-05).
2. ✅ `BrainDevice` abstraction — complete (2026-06-05). Mock, Neurosity adapters done.
3. ✅ `MuseDeviceService` adapter — complete (2026-06-05). 22/22 specs green. Activate via `device: 'muse'` in `environment.ts`.
4. ✅ BLE IMU protocol for Arduino Nano 33 BLE Sense — complete (2026-06-06). Firmware (`arduino/glove-imu/glove-imu.ino`) + `ImuService` real UUIDs/parser/`error$`/auto-reconnect. 11/11 specs green. Pending: nRF Connect verification when hardware arrives.
5. Configure Firebase Storage rules for capture uploads.
6. Make pilot deployment settings configurable, including `shopId`.
7. Field-test the complete flow on Android Chrome with Muse 2 + Arduino IMU.
8. Define GDPR deletion/export and failed-session operator workflows.

## Related Documents

- `docs/superpowers/specs/2026-06-04-handwerk-data-platform-design.md`
- `docs/superpowers/plans/2026-06-04-handwerk-capture-platform.md`
- `docs/superpowers/progress/2026-06-04-handwerk-capture-progress.md`
- `docs/superpowers/specs/2026-06-04-handwerk-hardware-list.md`
- `docs/superpowers/specs/2026-06-04-flow-detection-design.md`
- `docs/superpowers/specs/2026-06-05-muse-device-adapter-design.md`
- `docs/superpowers/plans/2026-06-05-muse-device-adapter.md`
