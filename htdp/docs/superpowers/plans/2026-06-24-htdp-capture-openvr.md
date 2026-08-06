# htdp-capture OpenVR pose source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `OpenVRPoseSource` that reads VIVE tracker poses from SteamVR/OpenVR and feeds them through the existing `PoseSource` interface into the capture pipeline — built and unit-tested hardware-free, with only the real `openvr.init()` deferred to a live-hardware mile.

**Architecture:** A pure conversion module (`openvr_convert.py`) turns OpenVR 3×4 pose matrices into `(pos, quat)` and validity flags into a binary quality. A thin adapter (`openvr_pose.py`) reads devices from an **injectable system handle**, maps device serials to contract tracker_ids via a config `device_map`, and emits `Pose` objects. Tests drive the adapter with a fake system + fixture matrices; the real OpenVR specifics live in one small wrapper built only when no system is injected. `OpenVRPoseSource` is a drop-in `PoseSource`, so `run_capture` consumes it unchanged.

**Tech Stack:** Python 3.11+, `openvr` (pyopenvr, optional extra), `pylsl`/`pyxdf` (drop-in integration test). Same repo/tooling as the spine.

## Global Constraints

- Repo: `/Users/alexanderlemberger/htdp-capture`. All paths relative to it.
- **Additive only.** Do NOT change `pose_source.py`, `outlets.py`, `recorder.py`, `app.py`, `sidecar.py`, `xdf_writer.py`. `MockPoseSource` users + all existing tests stay green. `device_map=None` (default) ⇒ byte-identical behavior to today.
- **arm64 import gotcha:** `import openvr` FAILS at import on Apple Silicon (the bundled dylib is x86_64-only). Therefore: `openvr_convert.py` MUST NOT import openvr at all; `openvr_pose.py` MUST NOT import openvr at module top — import it **lazily inside the real-init branch only** (`__init__` when `system is None`). This keeps the module + all fake-system tests importable on the dev Mac. The real path runs on the x86 SteamVR capture box (live mile).
- `Pose(t, pos=(x,y,z), quat=(w,x,y,z), quality)`; tracker_id ∈ `TRACKER_IDS = {right_wrist, left_wrist, torso, object}`.
- Quality is binary: `1.0` iff `pose_is_valid and tracking_result == ok_result`, else `0.0`.
- Missing/disconnected mapped device ⇒ omitted from `poll()`. Connected-but-invalid ⇒ included with quality `0.0`.
- Adapter emits raw OpenVR-native frame (no re-framing — deferred to live mile via existing `frame_transform`).
- TDD: failing test first, watch it fail, minimal impl, watch it pass, commit. One commit per task, exact message. DRY/YAGNI.
- `ruff check .` and `mypy src/htdp_capture` clean at every commit. (ruff selects E,F,I,B,UP,BLE — keep test imports at top of file to avoid E402; mypy is strict.)
- Gate command after every task:
  `uv run --extra dev pytest -q && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`

---

### Task 1: pure conversion — matrix→pose + tracking→quality

**Files:**
- Create: `src/htdp_capture/openvr_convert.py`
- Test: `tests/test_openvr_convert.py`

**Interfaces:**
- Produces:
  - `openvr_convert.matrix_to_pos_quat(m: Sequence[Sequence[float]]) -> tuple[tuple[float,float,float], tuple[float,float,float,float]]` — `m` is the 3×4 OpenVR rigid transform (`m[r][c]`, r∈0..2, c∈0..3). Returns `(pos, quat_wxyz)`, quaternion normalized.
  - `openvr_convert.tracking_to_quality(pose_is_valid: bool, tracking_result: int, ok_result: int) -> float`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openvr_convert.py`:

```python
import math

from htdp_capture.openvr_convert import matrix_to_pos_quat, tracking_to_quality

_SQRT_HALF = math.sqrt(0.5)


def _approx(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def test_identity_matrix_is_origin_and_identity_quat():
    m = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    pos, quat = matrix_to_pos_quat(m)
    assert pos == (0.0, 0.0, 0.0)
    assert _approx(quat, (1.0, 0.0, 0.0, 0.0))


def test_translation_column_is_extracted():
    m = [[1.0, 0.0, 0.0, 1.5], [0.0, 1.0, 0.0, -2.0], [0.0, 0.0, 1.0, 3.25]]
    pos, _ = matrix_to_pos_quat(m)
    assert pos == (1.5, -2.0, 3.25)


def test_90_deg_about_z():
    # rotation 90 deg about +z, translation (1,2,3)
    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    pos, quat = matrix_to_pos_quat(m)
    assert pos == (1.0, 2.0, 3.0)
    assert _approx(quat, (_SQRT_HALF, 0.0, 0.0, _SQRT_HALF))


def test_180_deg_about_x_hits_diagonal_branch():
    m = [[1.0, 0.0, 0.0, 0.0], [0.0, -1.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0]]
    _, quat = matrix_to_pos_quat(m)
    assert _approx(quat, (0.0, 1.0, 0.0, 0.0))


def test_quaternion_is_unit_norm():
    m = [[0.0, -1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    _, quat = matrix_to_pos_quat(m)
    assert abs(math.sqrt(sum(c * c for c in quat)) - 1.0) <= 1e-9


def test_quality_valid_and_ok_is_one():
    assert tracking_to_quality(True, 200, 200) == 1.0


def test_quality_valid_but_not_ok_is_zero():
    assert tracking_to_quality(True, 201, 200) == 0.0


def test_quality_invalid_is_zero():
    assert tracking_to_quality(False, 200, 200) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alexanderlemberger/htdp-capture && uv run --extra dev pytest tests/test_openvr_convert.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/openvr_convert.py`:

```python
from __future__ import annotations

import math
from collections.abc import Sequence


def matrix_to_pos_quat(
    m: Sequence[Sequence[float]],
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Convert an OpenVR 3x4 rigid transform to (position, quaternion wxyz).

    ``m`` is row-major: ``m[r][c]`` with r in 0..2, c in 0..3. The translation is
    the last column; the rotation is the leading 3x3. Uses Shepperd's method
    (picks the largest pivot for numerical stability) and returns a unit quaternion.
    """
    pos = (float(m[0][3]), float(m[1][3]), float(m[2][3]))

    r00, r01, r02 = m[0][0], m[0][1], m[0][2]
    r10, r11, r12 = m[1][0], m[1][1], m[1][2]
    r20, r21, r22 = m[2][0], m[2][1], m[2][2]
    trace = r00 + r11 + r22

    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (r21 - r12) / s
        y = (r02 - r20) / s
        z = (r10 - r01) / s
    elif r00 > r11 and r00 > r22:
        s = math.sqrt(1.0 + r00 - r11 - r22) * 2.0
        w = (r21 - r12) / s
        x = 0.25 * s
        y = (r01 + r10) / s
        z = (r02 + r20) / s
    elif r11 > r22:
        s = math.sqrt(1.0 + r11 - r00 - r22) * 2.0
        w = (r02 - r20) / s
        x = (r01 + r10) / s
        y = 0.25 * s
        z = (r12 + r21) / s
    else:
        s = math.sqrt(1.0 + r22 - r00 - r11) * 2.0
        w = (r10 - r01) / s
        x = (r02 + r20) / s
        y = (r12 + r21) / s
        z = 0.25 * s

    n = math.sqrt(w * w + x * x + y * y + z * z)
    return pos, (w / n, x / n, y / n, z / n)


def tracking_to_quality(pose_is_valid: bool, tracking_result: int, ok_result: int) -> float:
    """Binary validity flag: 1.0 only when the pose is valid AND tracking is OK."""
    return 1.0 if (pose_is_valid and tracking_result == ok_result) else 0.0
```

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_openvr_convert.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (8 tests), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: pure OpenVR matrix->pose + tracking->quality conversion"
```

---

### Task 2: OpenVRPoseSource adapter (injectable system)

**Files:**
- Create: `src/htdp_capture/openvr_pose.py`
- Test: `tests/test_openvr_pose.py`

**Interfaces:**
- Consumes: `openvr_convert.matrix_to_pos_quat`, `openvr_convert.tracking_to_quality`; `pose_source.Pose`, `pose_source.PoseSource`; `contract.TRACKER_IDS`.
- Produces:
  - `openvr_pose.DevicePose` dataclass: `valid: bool`, `connected: bool`, `result: int`, `matrix: Sequence[Sequence[float]]`.
  - `openvr_pose.SystemHandle` Protocol: `device_poses() -> Sequence[DevicePose]`, `serial(index: int) -> str`, `shutdown() -> None`.
  - `openvr_pose.OpenVRPoseSource(PoseSource)`:
    `__init__(self, device_map: dict[str,str], *, system: SystemHandle | None = None, ok_result: int | None = None, clock: Callable[[], float] = time.monotonic)`.
    `trackers() -> list[str]` (sorted mapped tracker_ids); `poll() -> dict[str, Pose]`; `close() -> None`.

**Behavior:** Validates `device_map` (non-empty serials, tracker_ids ∈ TRACKER_IDS, no duplicate tracker_ids) → `ValueError`. If `system is None`: lazy `import openvr`, build the real wrapper (`_OpenVRSystem`), and set `ok_result = openvr.TrackingResult_Running_OK`; mark the system as owned. If `system` is given, `ok_result` MUST also be given (else `ValueError`); the system is not owned. `poll()` reads `system.device_poses()`, and for each connected device whose `serial(i)` is in `device_map`, converts the matrix and emits a `Pose` keyed by tracker_id; disconnected or unmapped devices are skipped. `close()` calls `system.shutdown()` only if the system is owned (created internally).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openvr_pose.py`:

```python
import math

import pytest

from htdp_capture.openvr_convert import matrix_to_pos_quat
from htdp_capture.openvr_pose import DevicePose, OpenVRPoseSource

_OK = 200


def _identity(tx=0.0, ty=0.0, tz=0.0):
    return [[1.0, 0.0, 0.0, tx], [0.0, 1.0, 0.0, ty], [0.0, 0.0, 1.0, tz]]


class _FakeSystem:
    """Fake SystemHandle: fixed device list indexed by position."""

    def __init__(self, devices):
        # devices: list of (serial, DevicePose)
        self._devices = devices
        self.shutdown_called = False

    def device_poses(self):
        return [dp for _, dp in self._devices]

    def serial(self, index):
        return self._devices[index][0]

    def shutdown(self):
        self.shutdown_called = True


def _clock():
    state = {"t": 0.0}

    def c() -> float:
        state["t"] += 1.0
        return state["t"]

    return c


def test_poll_returns_only_mapped_trackers():
    devices = [
        ("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(1.0))),
        ("LHR-OBJ", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(2.0))),
        ("LHR-CONTROLLER", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(9.0))),
    ]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist", "LHR-OBJ": "object"},
        system=_FakeSystem(devices),
        ok_result=_OK,
        clock=_clock(),
    )
    out = src.poll()
    assert set(out) == {"right_wrist", "object"}  # controller omitted


def test_poll_converts_pose_via_pure_module():
    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    devices = [("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=m))]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    pose = src.poll()["right_wrist"]
    exp_pos, exp_quat = matrix_to_pos_quat(m)
    assert pose.pos == exp_pos
    assert pose.quat == exp_quat
    assert pose.quality == 1.0


def test_invalid_device_included_with_zero_quality():
    devices = [("LHR-WRIST", DevicePose(valid=False, connected=True, result=_OK, matrix=_identity()))]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    out = src.poll()
    assert "right_wrist" in out
    assert out["right_wrist"].quality == 0.0


def test_disconnected_mapped_device_is_omitted():
    devices = [("LHR-WRIST", DevicePose(valid=False, connected=False, result=_OK, matrix=_identity()))]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    assert src.poll() == {}


def test_trackers_returns_sorted_mapped_ids():
    src = OpenVRPoseSource(
        {"LHR-OBJ": "object", "LHR-WRIST": "right_wrist"},
        system=_FakeSystem([]),
        ok_result=_OK,
        clock=_clock(),
    )
    assert src.trackers() == ["object", "right_wrist"]


def test_close_does_not_shutdown_injected_system():
    fake = _FakeSystem([])
    src = OpenVRPoseSource({"LHR-WRIST": "right_wrist"}, system=fake, ok_result=_OK, clock=_clock())
    src.close()
    assert fake.shutdown_called is False


def test_injected_system_requires_ok_result():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"LHR-WRIST": "right_wrist"}, system=_FakeSystem([]))


def test_bad_tracker_id_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"LHR-X": "elbow"}, system=_FakeSystem([]), ok_result=_OK)


def test_duplicate_tracker_id_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource(
            {"LHR-A": "right_wrist", "LHR-B": "right_wrist"},
            system=_FakeSystem([]),
            ok_result=_OK,
        )


def test_empty_serial_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"": "right_wrist"}, system=_FakeSystem([]), ok_result=_OK)


def test_empty_device_map_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({}, system=_FakeSystem([]), ok_result=_OK)


def test_timestamp_comes_from_clock():
    devices = [("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity()))]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    assert src.poll()["right_wrist"].t == 1.0
    assert src.poll()["right_wrist"].t == 2.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_openvr_pose.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/openvr_pose.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.openvr_convert import matrix_to_pos_quat, tracking_to_quality
from htdp_capture.pose_source import Pose, PoseSource


@dataclass(frozen=True)
class DevicePose:
    valid: bool
    connected: bool
    result: int
    matrix: Sequence[Sequence[float]]


class SystemHandle(Protocol):
    def device_poses(self) -> Sequence[DevicePose]: ...
    def serial(self, index: int) -> str: ...
    def shutdown(self) -> None: ...


def _validate_device_map(device_map: dict[str, str]) -> None:
    if not device_map:
        raise ValueError("device_map must be non-empty")
    if any(not serial for serial in device_map):
        raise ValueError("device_map serial keys must be non-empty")
    for tracker_id in device_map.values():
        if tracker_id not in TRACKER_IDS:
            raise ValueError(f"tracker '{tracker_id}' not in contract {TRACKER_IDS}")
    ids = list(device_map.values())
    if len(set(ids)) != len(ids):
        raise ValueError("device_map must not map two serials to the same tracker_id")


class OpenVRPoseSource(PoseSource):
    """Reads VIVE tracker poses from OpenVR through an injectable system handle.

    The real OpenVR system is built lazily only when no ``system`` is injected,
    so this module imports (and its tests run) on platforms where ``import openvr``
    fails (e.g. Apple Silicon). Tests inject a fake ``SystemHandle``.
    """

    def __init__(
        self,
        device_map: dict[str, str],
        *,
        system: SystemHandle | None = None,
        ok_result: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_device_map(device_map)
        self._device_map = dict(device_map)
        self._clock = clock

        if system is None:
            import openvr  # type: ignore[import-not-found]  # lazy; real-hardware path only (arm64 import fails, no stubs)

            self._system: SystemHandle = _OpenVRSystem(openvr)
            self._ok_result = int(openvr.TrackingResult_Running_OK)
            self._owns_system = True
        else:
            if ok_result is None:
                raise ValueError("ok_result is required when a system is injected")
            self._system = system
            self._ok_result = ok_result
            self._owns_system = False

    def trackers(self) -> list[str]:
        return sorted(self._device_map.values())

    def poll(self) -> dict[str, Pose]:
        t = self._clock()
        out: dict[str, Pose] = {}
        poses = self._system.device_poses()
        for index, dp in enumerate(poses):
            if not dp.connected:
                continue
            tracker_id = self._device_map.get(self._system.serial(index))
            if tracker_id is None:
                continue
            pos, quat = matrix_to_pos_quat(dp.matrix)
            quality = tracking_to_quality(dp.valid, dp.result, self._ok_result)
            out[tracker_id] = Pose(t=t, pos=pos, quat=quat, quality=quality)
        return out

    def close(self) -> None:
        if self._owns_system:
            self._system.shutdown()


class _OpenVRSystem:
    """Thin real-OpenVR wrapper (live-hardware mile; not unit-tested).

    Built only from ``OpenVRPoseSource.__init__`` when no system is injected.
    ``openvr`` is passed in already-imported so this class has no module-level
    dependency on it.
    """

    def __init__(self, openvr: object) -> None:
        self._openvr = openvr
        self._system = openvr.init(openvr.VRApplication_Background)  # type: ignore[attr-defined]
        self._count = int(openvr.k_unMaxTrackedDeviceCount)  # type: ignore[attr-defined]
        self._origin = openvr.TrackingUniverseStanding  # type: ignore[attr-defined]
        self._pose_array_t = openvr.TrackedDevicePose_t * self._count  # type: ignore[attr-defined]
        self._serial_prop = openvr.Prop_SerialNumber_String  # type: ignore[attr-defined]

    def device_poses(self) -> Sequence[DevicePose]:
        arr = self._pose_array_t()
        self._system.getDeviceToAbsoluteTrackingPose(self._origin, 0.0, arr)
        result: list[DevicePose] = []
        for p in arr:
            m = p.mDeviceToAbsoluteTracking.m
            matrix = [[float(m[r][c]) for c in range(4)] for r in range(3)]
            result.append(
                DevicePose(
                    valid=bool(p.bPoseIsValid),
                    connected=bool(p.bDeviceIsConnected),
                    result=int(p.eTrackingResult),
                    matrix=matrix,
                )
            )
        return result

    def serial(self, index: int) -> str:
        return str(self._system.getStringTrackedDeviceProperty(index, self._serial_prop))

    def shutdown(self) -> None:
        self._openvr.shutdown()  # type: ignore[attr-defined]
```

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_openvr_pose.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (12 tests), clean. (`_OpenVRSystem` carries `# type: ignore[attr-defined]` because `openvr` is typed as `object`; mypy strict is satisfied.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: OpenVRPoseSource adapter with injectable system handle"
```

---

### Task 3: CaptureConfig device_map field + validation

**Files:**
- Modify: `src/htdp_capture/config.py`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Produces: `CaptureConfig.device_map: dict[str,str] | None = None`; `validate()` enforces device_map rules when set (reusing the same rules as the adapter).

**Note:** `device_map` is metadata describing which physical serials drive an OpenVR run; it does NOT change the sidecar (the ingest_map is still keyed by tracker_id). Validation mirrors `openvr_pose._validate_device_map` but raises `ConfigError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py` (the `EegConfig` import already added in an earlier feature is at the top; add nothing new to imports):

```python
def test_no_device_map_is_valid():
    _eeg_cfg().validate()  # device_map defaults to None


def test_valid_device_map_passes():
    _eeg_cfg(device_map={"LHR-A": "right_wrist", "LHR-B": "object"}).validate()


def test_empty_device_map_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={}).validate()


def test_device_map_bad_tracker_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"LHR-A": "elbow"}).validate()


def test_device_map_duplicate_tracker_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"LHR-A": "right_wrist", "LHR-B": "right_wrist"}).validate()


def test_device_map_empty_serial_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"": "right_wrist"}).validate()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_config.py -v`
Expected: FAIL — `CaptureConfig` has no `device_map` parameter.

- [ ] **Step 3: Write minimal implementation**

In `src/htdp_capture/config.py`, add the field after `eeg`:

```python
    eeg: EegConfig | None = None
    device_map: dict[str, str] | None = None
```

In `validate()`, add after the eeg block:

```python
        if self.device_map is not None:
            self._validate_device_map(self.device_map)
```

And add the static method (mirrors the adapter's rules, raises `ConfigError`):

```python
    @staticmethod
    def _validate_device_map(device_map: dict[str, str]) -> None:
        if not device_map:
            raise ConfigError("device_map must be non-empty")
        if any(not serial for serial in device_map):
            raise ConfigError("device_map serial keys must be non-empty")
        for tracker_id in device_map.values():
            if tracker_id not in TRACKER_IDS:
                raise ConfigError(f"tracker '{tracker_id}' not in contract {TRACKER_IDS}")
        ids = list(device_map.values())
        if len(set(ids)) != len(ids):
            raise ConfigError("device_map must not map two serials to the same tracker_id")
```

(`TRACKER_IDS` is already imported in `config.py` from `htdp_capture.contract`.)

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_config.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (incl. existing config tests), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: optional device_map field + validation on CaptureConfig"
```

---

### Task 4: openvr optional dependency + README note

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

**Note:** No test code — this task's deliverable is the dependency declaration + docs. It is its own reviewable unit (a reviewer can accept/reject the dep choice independently). Do NOT add `openvr` to the `dev` extra: it fails to import on arm64 and nothing in the test suite imports it (the adapter lazy-imports it only in the real path). The capture box installs `--extra openvr`.

- [ ] **Step 1: Add the optional extra**

In `pyproject.toml`, under `[project.optional-dependencies]`, add an `openvr` extra alongside `dev`:

```toml
[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6", "mypy>=1.11", "htdp"]
openvr = ["openvr>=2.0"]
```

- [ ] **Step 2: Document in README**

Add a section to `README.md` describing the real-hardware pose source:

```markdown
## Real-hardware capture (OpenVR)

`OpenVRPoseSource` reads VIVE tracker poses from SteamVR via OpenVR and is a
drop-in `PoseSource` for `run_capture`. Install the extra on the SteamVR machine:

    uv sync --extra openvr

Map each physical tracker's serial to a contract tracker_id and pass it as
`CaptureConfig.device_map`, e.g. `{"LHR-1A2B3C4D": "right_wrist"}`. Only mapped,
connected devices are captured; HMD/controllers/base stations are ignored.

**Platform note:** `import openvr` requires an x86_64 build of the OpenVR runtime
and a running SteamVR; it fails to import on Apple Silicon. The conversion and
adapter logic are unit-tested hardware-free with an injected system handle — the
real `openvr.init()` path runs on the SteamVR capture box.

Deferred to the live-hardware mile: CLI wiring, a real-tracker smoke test, and
`frame_transform` calibration against the measured world origin.
```

- [ ] **Step 3: Verify the suite is unaffected**

Run: `uv run --extra dev pytest -q && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean (no behavior change; dep + docs only).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "build: add openvr optional extra + README real-hardware note"
```

---

### Task 5: drop-in integration — OpenVRPoseSource through run_capture → XDF

**Files:**
- Create: `tests/test_openvr_integration.py`

**Interfaces:**
- Consumes: `app.run_capture`, `openvr_pose.OpenVRPoseSource` + `DevicePose`, `scripted_marker.ScriptedMarkerSource`/`default_schedule`, `config.CaptureConfig`.

**Note:** THE payoff — proves `OpenVRPoseSource` is a true `PoseSource` drop-in by capturing through the real outlets→recorder→XDF path (no bypass), with a fake system supplying poses. Gated on pylsl+pyxdf; must RUN not skip. `config.trackers` must equal the `device_map` values (run_capture builds outlets from `config.trackers`).

- [ ] **Step 1: Write the test**

Create `tests/test_openvr_integration.py`:

```python
import pytest

pytest.importorskip("pylsl")
pytest.importorskip("pyxdf")

from htdp_capture.app import run_capture  # noqa: E402
from htdp_capture.config import CaptureConfig  # noqa: E402
from htdp_capture.openvr_convert import matrix_to_pos_quat  # noqa: E402
from htdp_capture.openvr_pose import DevicePose, OpenVRPoseSource  # noqa: E402
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule  # noqa: E402

_OK = 200


class _FakeSystem:
    def __init__(self, devices):
        self._devices = devices

    def device_poses(self):
        return [dp for _, dp in self._devices]

    def serial(self, index):
        return self._devices[index][0]

    def shutdown(self):
        pass


def _config(device_map):
    return CaptureConfig(
        trackers=sorted(device_map.values()),
        session={
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "vive-01"},
        rate_hz=200.0,
        duration_s=0.4,
        device_map=device_map,
    )


def test_openvr_source_is_drop_in_through_run_capture(tmp_path):
    import pyxdf

    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    device_map = {"LHR-WRIST": "right_wrist"}
    devices = [("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=m))]
    cfg = _config(device_map)

    xdf = tmp_path / "rec.xdf"
    run_capture(
        cfg,
        OpenVRPoseSource(device_map, system=_FakeSystem(devices), ok_result=_OK),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        xdf,
        tmp_path / "ingest.json",
    )

    streams, _ = pyxdf.load_xdf(str(xdf), dejitter_timestamps=False, synchronize_clocks=False)
    motion = next(s for s in streams if s["info"]["name"][0] == "right_wrist")
    assert len(motion["time_series"]) > 0

    exp_pos, exp_quat = matrix_to_pos_quat(m)
    row = motion["time_series"][0]
    # channel order: x_m,y_m,z_m,qw,qx,qy,qz,quality
    assert tuple(round(v, 6) for v in row[0:3]) == tuple(round(v, 6) for v in exp_pos)
    assert tuple(round(v, 6) for v in row[3:7]) == tuple(round(v, 6) for v in exp_quat)
    assert row[7] == 1.0
```

- [ ] **Step 2: Run the test**

Run: `uv run --extra dev pytest tests/test_openvr_integration.py -v`
Expected: PASS — the OpenVR-converted pose flows through real LSL outlets into the XDF with the right channel values. If it FAILS, the failure is a real wiring bug in Tasks 1-2 (fix there, use systematic-debugging).

- [ ] **Step 3: Run full suite + lint + type + skip-check**

Run: `uv run --extra dev pytest -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Then confirm 0 skips with deps present: `uv run --extra dev pytest -q 2>&1 | grep -ic skip` → must print `0`.
Expected: ALL tests PASS, 0 skipped, clean.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "test: OpenVRPoseSource drop-in integration through run_capture"
```

---

## Self-Review

**Spec coverage:**
- pure `matrix_to_pos_quat` + `tracking_to_quality` → Task 1. ✓
- `OpenVRPoseSource` (injectable system, device_map, omit-missing, binary quality) → Task 2. ✓
- lazy openvr import (arm64 gotcha) → Task 2 (`__init__` real branch) + Global Constraints. ✓
- `_OpenVRSystem` real wrapper (live-mile shell, thin, ignored by tests) → Task 2. ✓
- `CaptureConfig.device_map` + validation → Task 3. ✓
- `openvr` optional extra + README note → Task 4. ✓
- drop-in integration through real outlets (no bypass, must RUN) → Task 5. ✓
- deferred items (CLI wiring, live smoke, frame calibration) → no task, documented in README + spec. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `DevicePose(valid,connected,result,matrix)` identical across Tasks 2 & 5 and the fakes. `OpenVRPoseSource(device_map, *, system, ok_result, clock)` signature consistent in Tasks 2 & 5. `matrix_to_pos_quat`/`tracking_to_quality` signatures consistent Tasks 1→2→5. `SystemHandle` Protocol (`device_poses`/`serial`/`shutdown`) matches both `_FakeSystem` (tests) and `_OpenVRSystem` (real). `_validate_device_map` rules in Task 2 (ValueError) and `CaptureConfig._validate_device_map` in Task 3 (ConfigError) are deliberately parallel, not shared (different exception types, different layers). ✓

**arm64 safety:** No module-level `import openvr` anywhere; only inside `OpenVRPoseSource.__init__`'s `system is None` branch. `openvr_convert.py` has zero openvr reference. All tests inject fakes → suite runs on the dev Mac. ✓
