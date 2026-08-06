# htdp-capture OpenVR pose source (design)

**Date:** 2026-06-24
**Status:** Approved (brainstorm complete)
**Repo:** `htdp-capture` (`/Users/alexanderlemberger/htdp-capture`) — additive feature on the shipped motion+events(+eeg) spine.

## Purpose

Add a real-hardware pose source, `OpenVRPoseSource`, that reads VIVE tracker
poses from SteamVR via OpenVR and emits them through the existing `PoseSource`
interface — feeding the same outlets→recorder→XDF→`htdp ingest` path the
`MockPoseSource` already drives. This turns on real human-task motion data (the
app's reason to exist).

Posture mirrors the deferred-hardware pattern used for `MockEegSource`/real EEG:
the **conversion math and adapter wiring are built and unit-tested hardware-free**
(injectable OpenVR system + fixture pose matrices); only `openvr.init()` against
live trackers waits on the rig (the "live mile").

## Scope

**This slice ships (all offline-testable):**

- `openvr_convert.py` — pure conversion functions.
- `OpenVRPoseSource` — thin adapter with an injectable system handle.
- `CaptureConfig.device_map` field + validation.
- `openvr` optional dependency (extra).
- README note.

**Deferred to the live-hardware mile (needs the rig — separate slice):**

- CLI wiring (`record --openvr` + device_map source).
- live `openvr.init()` smoke against real trackers.
- real `frame_transform` calibration (measure base-station / world origin).
- one end-to-end real human-task capture.

## Contract (the interface to satisfy)

`PoseSource` (unchanged, `pose_source.py`):
- `trackers() -> list[str]`
- `poll() -> dict[str, Pose]`
- `close() -> None`

`Pose(t: float, pos: (x,y,z), quat: (w,x,y,z), quality: float)`. tracker_id ∈
`TRACKER_IDS = {right_wrist, left_wrist, torso, object}`.

## Decisions (locked in brainstorm)

1. **Library = raw `openvr` (pyopenvr).** Proper PyPI dep (optional extra,
   mirrors `pyxdf`/`mujoco`). Import works without SteamVR; only `.init()` needs
   the runtime. No vendoring `triad_openvr`; matrix conversion stays in our pure
   module.
2. **Tracker identity = explicit `device_map: {serial: tracker_id}` in config.**
   Data-declared (like `frame_transform`). Adapter emits only mapped serials;
   unknown devices (HMD, controllers, base stations) are ignored.
3. **Quality = binary.** `1.0 if (bPoseIsValid and eTrackingResult ==
   TrackingResult_Running_OK) else 0.0`. Matches MockPoseSource + the spine's
   validity-flag semantics. No invented gradations (YAGNI).
4. **Missing tracker → omit from poll.** A mapped device absent/asleep this poll
   is not in the returned dict (matches Mock's "return what you have"). A present
   but invalid device IS returned, with quality 0.0 (keeps frame alignment;
   downstream drops on quality).
5. **Frame = raw OpenVR-native.** Adapter emits poses in OpenVR's frame
   (right-handed, Y-up, meters, `TrackingUniverseStanding`). Real re-framing
   deferred to the live calibration mile via the existing `frame_transform`
   (identity default), applied downstream by `htdp ingest`. No new frame code.
6. **Offline testability via split + injection.** Pure conversion module tested
   against fixture matrices; adapter tested against a fake system returning
   canned pose arrays. Only the real `openvr.init()` line is untested (live mile).

## Architecture

New files + additive edits in `htdp_capture`:

```
htdp_capture/
  openvr_convert.py   # NEW: pure matrix->pose + tracking->quality (no openvr import needed at call time)
  openvr_pose.py      # NEW: OpenVRPoseSource (injectable system handle)
  config.py           # EDIT: CaptureConfig += device_map: dict[str,str] | None = None + validation
```

`pose_source.py`, `outlets.py`, `recorder.py`, `app.py`, `sidecar.py`,
`xdf_writer.py` are **untouched** — `OpenVRPoseSource` is a drop-in `PoseSource`,
so `run_capture` already consumes it.

## Interfaces

**`openvr_convert.py` (pure, no hardware):**

- `matrix_to_pos_quat(m34) -> tuple[(float,float,float), (float,float,float,float)]`
  - `m34` = the OpenVR 3×4 rigid-transform rows (`mDeviceToAbsoluteTracking.m`,
    a `[[..4],[..4],[..4]]`). Translation = `(m[0][3], m[1][3], m[2][3])`.
    Rotation 3×3 → quaternion `(w,x,y,z)` via Shepperd's method (numerically
    stable, picks the largest diagonal term). Returns a normalized quaternion.
- `tracking_to_quality(pose_is_valid: bool, tracking_result: int, ok_result: int)
  -> float` → `1.0` iff `pose_is_valid and tracking_result == ok_result`, else
  `0.0`. (`ok_result` injected so the pure module needs no `openvr` import.)

**`openvr_pose.py`:**

- `OpenVRPoseSource(PoseSource)`:
  - `__init__(self, device_map: dict[str,str], *, system=None, clock=time.monotonic,
    init_fn=<lazy openvr.init>, ok_result=<lazy openvr.TrackingResult_Running_OK>,
    origin=<lazy TrackingUniverseStanding>)`
    - validates each tracker_id ∈ TRACKER_IDS, no duplicate tracker_ids, serials
      non-empty (raises `ValueError`).
    - if `system is None`, calls `init_fn()` (real `openvr.init(...)`) and
      resolves the real `system` + constants — the only hardware-touching path.
    - builds a `serial -> tracker_id` lookup.
  - `trackers(self) -> list[str]` → the mapped tracker_ids (sorted, deterministic).
  - `poll(self) -> dict[str, Pose]`:
    - `t = clock()`.
    - get the pose array (`system.getDeviceToAbsoluteTrackingPose(origin, 0,
      ...)`), iterate device indices, read each device's serial
      (`getStringTrackedDeviceProperty(i, Prop_SerialNumber_String)`).
    - for each device whose serial is in `device_map`: convert via the pure
      module, build `Pose(t, pos, quat, quality)`; key by tracker_id.
    - devices not in `device_map`, or mapped devices absent from the array, are
      omitted.
  - `close(self) -> None` → `openvr.shutdown()` if a real system was created;
    no-op for an injected fake.

**`config.py`:**

- `CaptureConfig.device_map: dict[str, str] | None = None` (default None ⇒
  behavior unchanged; `MockPoseSource` users unaffected).
- `validate()` when `device_map` set: non-empty; every value ∈ TRACKER_IDS; no
  duplicate tracker_ids (two serials → same role is an error); serial keys
  non-empty → `ConfigError`. `device_map` is config metadata for the OpenVR run;
  it does not alter the sidecar (the sidecar's ingest_map is still keyed by
  tracker_id, which the outlets already emit).

## Data flow

Unchanged for Mock. For OpenVR:

`OpenVRPoseSource.poll()` → per-device pose matrix + validity → pure conversion →
`{tracker_id: Pose}` → `run_capture` pushes to the per-tracker motion outlets
exactly as today → recorder → XDF → `htdp ingest`. The adapter is a drop-in; no
downstream change.

## Error handling

- Construction: invalid `device_map` (empty, bad tracker_id, dup tracker_id,
  empty serial) → `ValueError`.
- `CaptureConfig.validate()`: same rules → `ConfigError`.
- Real `init_fn()` failure (no SteamVR / no HMD) → propagates the `openvr` error
  (live mile concern; not swallowed).
- A device present but invalid → emitted with quality 0.0 (not dropped at
  source); a device missing → omitted. The existing "no motion samples captured"
  guard in `run_capture` still applies.

## Testing (TDD, layered for hardware-free CI)

1. **Pure conversion (no deps):**
   - `matrix_to_pos_quat`: identity matrix → pos (0,0,0), quat (1,0,0,0);
     known 90°-about-Z rotation matrix → expected quaternion (within tolerance);
     translation column extracted correctly; result quaternion is unit-norm.
   - `tracking_to_quality`: valid+OK → 1.0; valid+not-OK → 0.0; invalid → 0.0.
2. **Adapter wiring (fake system, no hardware):** a `_FakeSystem` returns a
   canned pose array + serial lookup for, e.g., two mapped trackers + one
   unmapped device (a "controller"). Assert:
   - `poll()` returns only the mapped tracker_ids (unmapped serial omitted);
   - each Pose's pos/quat match the pure conversion of the canned matrix;
   - an invalid mapped device → quality 0.0, still present;
   - a mapped serial absent from the array → omitted from the dict;
   - `trackers()` == sorted mapped tracker_ids;
   - `close()` on an injected fake does not call real shutdown.
3. **Config validation:** `device_map` None valid; good map valid; empty map /
   bad tracker_id / duplicate tracker_id / empty serial → `ConfigError`.
4. **Drop-in integration (fake system + real outlets, importorskip pylsl):**
   `run_capture(config, OpenVRPoseSource(device_map, system=fake), ...)` →
   produces an XDF whose motion streams carry the converted poses (proves the
   adapter is a true `PoseSource` drop-in through the real LSL path, not just in
   isolation). Reuses the spine's connection-priming; must RUN not skip.

**False-green guard:** the conversion is the load-bearing logic — its tests must
assert real numeric values (identity + a known rotation), not just "is a
4-tuple". The drop-in test must exercise the real outlets→recorder path (no
bypass), per the spine's false-green history.

## Out of scope (deferred)

- CLI `record` OpenVR wiring + device_map source (live mile).
- live `openvr.init()` smoke + real-tracker capture (needs rig).
- real `frame_transform` calibration (needs rig + measured origin).
- velocity/angular-velocity channels, controller/HMD capture, pose prediction.

## Related

- htdp-capture spine + EEG shipped — [[vive-capture-kickoff]]
- LSL connection-priming requirement — [[htdp-capture-lsl-delivery]]
- `PoseSource`/`Pose` contract — `htdp_capture/pose_source.py`
- frame_transform (rotation-only quaternion, sidecar) — `htdp_capture/sidecar.py`
