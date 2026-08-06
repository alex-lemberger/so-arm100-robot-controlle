# Protocol: Reach–Grasp–Place

**Protocol ID:** `reach-grasp-place-v0.1`
**Version:** 0.1
**Status:** Synthetic (no hardware capture in v0.1)

---

## Goal

Capture the full kinematic chain of a simple manual manipulation task — reaching for an
object, grasping it, transporting it, and placing it at a target location — as a
baseline robotics imitation-learning dataset. This is the seed protocol of the Task
Library.

The task is simple enough to be fully parameterised in a synthetic generator while being
rich enough to exercise all pipeline stages: multi-tracker motion, event markers, QC
defect detection, consent gating, and MuJoCo replay.

---

## Setup

### Environment
- One table-height surface (~75 cm).
- One graspable object (cylinder, ~8 cm diameter) at a fixed start position.
- One target zone marked on the surface, ~40 cm from the start object.
- Participant seated or standing, dominant hand free.

### Trackers
Four 6DoF trackers (VIVE or equivalent), coordinate frame per `device_config.json`:

| Tracker ID | Placement |
|------------|-----------|
| `right_wrist` | Dominant wrist (dorsal mount) |
| `left_wrist` | Non-dominant wrist (dorsal mount) |
| `torso` | Sternum, midline |
| `object` | Top surface of graspable object |

Coordinate frame: right-handed, x = participant right, y = forward, z = up. Units: meters.

### Data streams
- Four motion streams at ~100 Hz (one per tracker).
- One event stream (software markers).
- Video: empty slot in v0.1 (camera mount present but not recorded).
- EEG: empty slot in v0.1.

---

## Phases and events

The session is divided into five phases, each terminated by a software event marker.

| Phase | Event label | Description |
|-------|------------|-------------|
| Baseline | `start` | 5 s of rest; participant hands at sides. Marks session start. |
| Reach | `grasp` | Participant reaches for and grasps the object. |
| Transport | `release` | Participant moves the object toward the target zone. |
| Place | `place` | Participant places the object at the target zone and releases. |
| Return | `stop` | Participant returns hand to rest position. Marks session end. |

Event ordering invariant: `start < grasp < release < place < stop`. Any violation is a
QC `fail`.

### Typical session duration
~15–30 seconds per trial. Target 10–20 trials per participant session.

---

## Synthetic generation (v0.1)

The `htdp synth` command generates a plausible single trial:
- Wrist trajectories arc toward the object position, then toward the target zone.
- Object tracker moves with the right wrist during the transport phase.
- Events are placed at phase boundaries derived from the seed.
- Nominal rate: 100 Hz.

**Deliberate defects injected (seed-controlled):**
1. A **dropped-sample gap** in one motion stream (a ~50 ms window with no samples).
2. A **clock-drift offset** between two motion streams (~2 ms linear drift).

These defects are tagged via the `defect_tag` column and documented in the QC report.
They exist so QC has real signal to detect, not to simulate real-world data quality.

---

## QC expectations

A valid session passes all event-ordering checks. The two synthetic defects are expected
to appear as:
- `gap_detected: warn` on the stream with dropped samples.
- `cross_stream_drift: warn` on the drifting stream pair.

Overall QC status: `warn` (acceptable; session can be packaged).

A session is `fail` if: mandatory streams are missing, timestamps are non-monotonic,
checksums do not match, or consent is malformed.

---

## Consent requirements

To package under the `commercial_dataset` profile, the following flags must be `true`
in `consent.json`:
- `commercial_use`
- `model_training`
- `third_party_access`

See `docs/ETHICS_AND_CONSENT.md` for the full consent model.

---

## Future extensions (v0.2+)

- Multi-trial sessions (repeated reaches, randomised object positions).
- Video recording (MP4 in the `video/` slot).
- EEG co-capture (MUSE or equivalent).
- Bi-manual variants (both wrists active).
- Weighted objects (force sensor integration).
- Real LSL capture → XDF ingest → this same raw representation.
