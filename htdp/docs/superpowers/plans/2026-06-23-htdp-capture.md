# htdp-capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a hardware-free VIVE→LSL→XDF capture app (`htdp-capture`) that emits a contract-conforming `.xdf` + `ingest.json` consumable by `htdp ingest`.

**Architecture:** A `PoseSource`/`MarkerSource` abstraction feeds real `pylsl` outlets (`cf_double64` motion per tracker + one `cf_string` events stream). An in-house inlet recorder drains the loopback streams; an in-house XDF writer serializes them; a sidecar builder emits `ingest.json`. `MockPoseSource` + `ScriptedMarkerSource` make the whole spine runnable and CI-testable with no hardware. OpenVR is deferred.

**Tech Stack:** Python 3.11+, `pylsl` (+ bundled liblsl), `numpy`, `pyxdf` (writer validation), `pytest`, `ruff`, `mypy`. `htdp` is a dev/test-only dependency for the round-trip conformance test. Tooling via `uv`.

## Global Constraints

- New **separate repo** at `/Users/alexanderlemberger/htdp-capture`. All paths below are relative to that repo root. Do NOT put code in `human-task-dataset-pipeline`.
- Package name `htdp_capture`, layout `src/htdp_capture/`.
- Python `>=3.11`.
- Motion XDF channel_format = `double64`; outlets = `cf_double64`. Events = `string`/`cf_string`.
- Motion channel order is EXACTLY `("x_m","y_m","z_m","qw","qx","qy","qz","quality")`.
- `tracker_id` ∈ `("right_wrist","left_wrist","torso","object")`.
- Events stream name = `"events"`, type `"Markers"`, nominal_srate `0.0`.
- Event payload = `json.dumps({event_id,label,phase,confidence,notes}, sort_keys=True)`; `source` is NOT included (ingest forces `"real"`).
- XDF magic prefix `b"XDF:"`; chunk framing mirrors htdp `tests/_xdf_writer.py` (tags 1=fileheader, 2=streamheader, 3=samples, 6=streamfooter).
- Recorder/ingest must NOT dejitter or clock-sync (htdp ingest reads timestamps verbatim).
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. Frequent commits. DRY. YAGNI.
- `ruff check` and `mypy src/htdp_capture` clean at every commit.
- LSL-dependent tests (integration + conformance) use `pytest.importorskip("pylsl")` so they cleanly SKIP when liblsl is absent — but the implementer MUST run them with `pylsl` installed and confirm they RUN (not skip) before claiming green (htdp false-green lesson).

---

### Task 1: Repo scaffold + contract constants

**Files:**
- Create: `/Users/alexanderlemberger/htdp-capture/pyproject.toml`
- Create: `/Users/alexanderlemberger/htdp-capture/.gitignore`
- Create: `/Users/alexanderlemberger/htdp-capture/README.md`
- Create: `src/htdp_capture/__init__.py`
- Create: `src/htdp_capture/contract.py`
- Test: `tests/test_contract.py`

**Interfaces:**
- Produces: `contract.MOTION_CHANNELS: tuple[str,...]`, `contract.TRACKER_IDS: tuple[str,...]`, `contract.EVENTS_STREAM_NAME: str`, `contract.EVENT_LABELS: tuple[str,...]`, `contract.MOTION_CHANNEL_INDEX: dict[str,int]`.

- [ ] **Step 1: Scaffold the repo**

```bash
mkdir -p /Users/alexanderlemberger/htdp-capture/src/htdp_capture /Users/alexanderlemberger/htdp-capture/tests
cd /Users/alexanderlemberger/htdp-capture
git init -q
```

Create `pyproject.toml`:

```toml
[project]
name = "htdp-capture"
version = "0.1.0"
description = "Hardware-free VIVE->LSL->XDF capture app feeding htdp ingest"
requires-python = ">=3.11"
dependencies = ["pylsl>=1.16", "numpy>=1.26", "pyxdf>=1.16"]

[project.scripts]
htdp-capture = "htdp_capture.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6", "mypy>=1.11", "htdp"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/htdp_capture"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "BLE"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/htdp_capture"]
```

Create `.gitignore`:

```
__pycache__/
*.pyc
.venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
dist/
*.xdf
```

Create `README.md`:

```markdown
# htdp-capture

Hardware-free VIVE -> LSL -> XDF capture app. Emits a contract-conforming
`.xdf` + `ingest.json` consumable by `htdp ingest`. Mock pose/marker sources
make it runnable with no hardware; the OpenVR adapter is a later milestone.

See `docs` in human-task-dataset-pipeline for the design spec/plan.
```

Create empty `src/htdp_capture/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

Create `tests/test_contract.py`:

```python
from htdp_capture import contract


def test_motion_channels_exact_order():
    assert contract.MOTION_CHANNELS == (
        "x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality",
    )


def test_tracker_ids():
    assert contract.TRACKER_IDS == ("right_wrist", "left_wrist", "torso", "object")


def test_events_stream_name():
    assert contract.EVENTS_STREAM_NAME == "events"


def test_event_labels():
    assert contract.EVENT_LABELS == ("start", "grasp", "release", "place", "stop")


def test_motion_channel_index_maps_each_channel_to_its_position():
    assert contract.MOTION_CHANNEL_INDEX == {
        "x_m": 0, "y_m": 1, "z_m": 2, "qw": 3,
        "qx": 4, "qy": 5, "qz": 6, "quality": 7,
    }
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/alexanderlemberger/htdp-capture && uv run --extra dev pytest tests/test_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp_capture.contract'`

- [ ] **Step 4: Write minimal implementation**

Create `src/htdp_capture/contract.py`:

```python
from __future__ import annotations

MOTION_CHANNELS: tuple[str, ...] = (
    "x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality",
)
TRACKER_IDS: tuple[str, ...] = ("right_wrist", "left_wrist", "torso", "object")
EVENTS_STREAM_NAME: str = "events"
EVENT_LABELS: tuple[str, ...] = ("start", "grasp", "release", "place", "stop")
MOTION_CHANNEL_INDEX: dict[str, int] = {k: i for i, k in enumerate(MOTION_CHANNELS)}
```

- [ ] **Step 5: Run test + lint + type to verify pass**

Run: `cd /Users/alexanderlemberger/htdp-capture && uv run --extra dev pytest tests/test_contract.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: tests PASS, ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/alexanderlemberger/htdp-capture
git add -A
git commit -m "feat: scaffold repo + contract constants"
```

---

### Task 2: Pose + PoseSource + MockPoseSource

**Files:**
- Create: `src/htdp_capture/pose_source.py`
- Create: `src/htdp_capture/mock_pose.py`
- Test: `tests/test_mock_pose.py`

**Interfaces:**
- Consumes: `contract.TRACKER_IDS`.
- Produces: `pose_source.Pose(t:float, pos:tuple[float,float,float], quat:tuple[float,float,float,float], quality:float)`; `pose_source.PoseSource` ABC with `trackers()->list[str]`, `poll()->dict[str,Pose]`, `close()->None`; `mock_pose.MockPoseSource(trackers, rate_hz=100.0, dropout_frames=None, clock=time.monotonic)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_mock_pose.py`:

```python
import pytest

from htdp_capture.mock_pose import MockPoseSource
from htdp_capture.pose_source import Pose


def _fixed_clock():
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.01
        return state["t"]

    return clock


def test_trackers_must_be_in_contract():
    with pytest.raises(ValueError):
        MockPoseSource(["nose"])


def test_poll_returns_one_pose_per_tracker():
    src = MockPoseSource(["right_wrist", "object"], clock=_fixed_clock())
    sample = src.poll()
    assert set(sample) == {"right_wrist", "object"}
    assert all(isinstance(p, Pose) for p in sample.values())


def test_quality_is_one_by_default():
    src = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    assert src.poll()["right_wrist"].quality == 1.0


def test_dropout_frame_sets_quality_zero():
    src = MockPoseSource(["right_wrist"], dropout_frames={1}, clock=_fixed_clock())
    assert src.poll()["right_wrist"].quality == 1.0   # frame 0
    assert src.poll()["right_wrist"].quality == 0.0   # frame 1


def test_motion_is_deterministic_per_frame():
    a = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    b = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    assert a.poll()["right_wrist"].pos == b.poll()["right_wrist"].pos


def test_quat_is_unit_wxyz():
    src = MockPoseSource(["torso"], clock=_fixed_clock())
    assert src.poll()["torso"].quat == (1.0, 0.0, 0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_mock_pose.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/pose_source.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    t: float
    pos: tuple[float, float, float]
    quat: tuple[float, float, float, float]  # w, x, y, z
    quality: float


class PoseSource(ABC):
    @abstractmethod
    def trackers(self) -> list[str]: ...

    @abstractmethod
    def poll(self) -> dict[str, Pose]: ...

    def close(self) -> None:  # default no-op; hardware sources override
        return None
```

Create `src/htdp_capture/mock_pose.py`:

```python
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.pose_source import Pose, PoseSource


class MockPoseSource(PoseSource):
    """Hardware-free synthetic pose source: deterministic circular motion."""

    def __init__(
        self,
        trackers: Iterable[str],
        rate_hz: float = 100.0,
        dropout_frames: set[int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        tlist = list(trackers)
        for t in tlist:
            if t not in TRACKER_IDS:
                raise ValueError(f"tracker '{t}' not in contract {TRACKER_IDS}")
        self._trackers = tlist
        self._rate_hz = rate_hz
        self._dropout = set(dropout_frames or set())
        self._clock = clock
        self._frame = 0

    def trackers(self) -> list[str]:
        return list(self._trackers)

    def poll(self) -> dict[str, Pose]:
        frame = self._frame
        t = self._clock()
        quality = 0.0 if frame in self._dropout else 1.0
        out: dict[str, Pose] = {}
        for i, tracker in enumerate(self._trackers):
            phase = frame * 0.1 + i
            pos = (math.cos(phase), math.sin(phase), 0.5)
            out[tracker] = Pose(t=t, pos=pos, quat=(1.0, 0.0, 0.0, 0.0), quality=quality)
        self._frame += 1
        return out
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_mock_pose.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Pose, PoseSource ABC, MockPoseSource"
```

---

### Task 3: MarkerEvent + MarkerSource + ScriptedMarkerSource

**Files:**
- Create: `src/htdp_capture/marker_source.py`
- Create: `src/htdp_capture/scripted_marker.py`
- Test: `tests/test_scripted_marker.py`

**Interfaces:**
- Produces: `marker_source.MarkerEvent(event_id:int, label:str, phase:str, confidence:float=1.0, notes:str="")` with `.to_json()->str`; `marker_source.MarkerSource` ABC with `poll()->list[tuple[float,MarkerEvent]]`, `close()->None`; `scripted_marker.ScriptedMarkerSource(schedule:list[tuple[float,MarkerEvent]], clock=time.monotonic)`; `scripted_marker.default_schedule()->list[tuple[float,MarkerEvent]]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scripted_marker.py`:

```python
import json

from htdp_capture.marker_source import MarkerEvent
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_to_json_has_payload_keys_and_no_source():
    payload = json.loads(MarkerEvent(1, "start", "reach", 0.9, "n").to_json())
    assert payload == {
        "event_id": 1, "label": "start", "phase": "reach",
        "confidence": 0.9, "notes": "n",
    }
    assert "source" not in payload


def test_to_json_is_sorted():
    s = MarkerEvent(1, "start", "reach").to_json()
    assert s == json.dumps(json.loads(s), sort_keys=True)


def test_due_events_fire_after_their_offset():
    clock = FakeClock()
    src = ScriptedMarkerSource(
        [(0.0, MarkerEvent(1, "start", "p")), (0.5, MarkerEvent(2, "stop", "p"))],
        clock=clock,
    )
    first = src.poll()  # establishes start at t=100.0, offset 0.0 due
    assert [e.event_id for _, e in first] == [1]
    clock.t = 100.6
    second = src.poll()  # offset 0.5 now due
    assert [e.event_id for _, e in second] == [2]


def test_events_are_not_refired():
    clock = FakeClock()
    src = ScriptedMarkerSource([(0.0, MarkerEvent(1, "start", "p"))], clock=clock)
    assert len(src.poll()) == 1
    assert src.poll() == []


def test_marker_timestamp_is_start_plus_offset():
    clock = FakeClock()
    src = ScriptedMarkerSource([(0.25, MarkerEvent(1, "start", "p"))], clock=clock)
    src.poll()           # start = 100.0
    clock.t = 100.5
    [(ts, _)] = src.poll()
    assert ts == 100.25


def test_default_schedule_uses_event_label_vocab():
    labels = [e.label for _, e in default_schedule()]
    assert labels == ["start", "grasp", "place", "release", "stop"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_scripted_marker.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/marker_source.py`:

```python
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerEvent:
    event_id: int
    label: str
    phase: str
    confidence: float = 1.0
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "label": self.label,
                "phase": self.phase,
                "confidence": self.confidence,
                "notes": self.notes,
            },
            sort_keys=True,
        )


class MarkerSource(ABC):
    @abstractmethod
    def poll(self) -> list[tuple[float, MarkerEvent]]: ...

    def close(self) -> None:
        return None
```

Create `src/htdp_capture/scripted_marker.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable

from htdp_capture.marker_source import MarkerEvent, MarkerSource


class ScriptedMarkerSource(MarkerSource):
    """Fires a fixed schedule of events at offsets from the first poll."""

    def __init__(
        self,
        schedule: list[tuple[float, MarkerEvent]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._schedule = sorted(schedule, key=lambda item: item[0])
        self._clock = clock
        self._start: float | None = None
        self._idx = 0

    def poll(self) -> list[tuple[float, MarkerEvent]]:
        now = self._clock()
        if self._start is None:
            self._start = now
        elapsed = now - self._start
        due: list[tuple[float, MarkerEvent]] = []
        while self._idx < len(self._schedule) and self._schedule[self._idx][0] <= elapsed:
            offset, event = self._schedule[self._idx]
            due.append((self._start + offset, event))
            self._idx += 1
        return due


def default_schedule() -> list[tuple[float, MarkerEvent]]:
    return [
        (0.0, MarkerEvent(1, "start", "reach")),
        (0.5, MarkerEvent(2, "grasp", "grasp")),
        (1.0, MarkerEvent(3, "place", "transport")),
        (1.5, MarkerEvent(4, "release", "release")),
        (2.0, MarkerEvent(5, "stop", "done")),
    ]
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_scripted_marker.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: MarkerEvent, MarkerSource ABC, ScriptedMarkerSource"
```

---

### Task 4: CaptureConfig + validation

**Files:**
- Create: `src/htdp_capture/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `contract.TRACKER_IDS`.
- Produces: `config.ConfigError(Exception)`; `config.CaptureConfig(trackers:list[str], session:dict, consent:dict, device_config:dict, rate_hz:float=100.0, duration_s:float=2.0, frame_rotation:tuple[float,float,float,float]|None=None, schedule:list[tuple[float,MarkerEvent]]|None=None)` with `.validate()->None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
import pytest

from htdp_capture.config import CaptureConfig, ConfigError


def _cfg(**over):
    base = dict(
        trackers=["right_wrist"],
        session={"session_id": "s"},
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "d"},
    )
    base.update(over)
    return CaptureConfig(**base)


def test_valid_config_passes():
    _cfg().validate()  # no raise


def test_empty_trackers_rejected():
    with pytest.raises(ConfigError):
        _cfg(trackers=[]).validate()


def test_unknown_tracker_rejected():
    with pytest.raises(ConfigError):
        _cfg(trackers=["nose"]).validate()


def test_bad_frame_rotation_length_rejected():
    with pytest.raises(ConfigError):
        _cfg(frame_rotation=(1.0, 0.0, 0.0)).validate()


def test_good_frame_rotation_passes():
    _cfg(frame_rotation=(1.0, 0.0, 0.0, 0.0)).validate()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_config.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.marker_source import MarkerEvent


class ConfigError(Exception):
    """Raised when a CaptureConfig is invalid."""


@dataclass
class CaptureConfig:
    trackers: list[str]
    session: dict[str, object]
    consent: dict[str, object]
    device_config: dict[str, object]
    rate_hz: float = 100.0
    duration_s: float = 2.0
    frame_rotation: tuple[float, float, float, float] | None = None
    schedule: list[tuple[float, MarkerEvent]] | None = field(default=None)

    def validate(self) -> None:
        if not self.trackers:
            raise ConfigError("at least one tracker is required")
        for t in self.trackers:
            if t not in TRACKER_IDS:
                raise ConfigError(f"tracker '{t}' not in contract {TRACKER_IDS}")
        if self.frame_rotation is not None and len(self.frame_rotation) != 4:
            raise ConfigError("frame_rotation must be a 4-tuple (w, x, y, z)")
        if self.rate_hz <= 0:
            raise ConfigError("rate_hz must be positive")
        if self.duration_s <= 0:
            raise ConfigError("duration_s must be positive")
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_config.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: CaptureConfig + validation"
```

---

### Task 5: sidecar builder

**Files:**
- Create: `src/htdp_capture/sidecar.py`
- Test: `tests/test_sidecar.py`

**Interfaces:**
- Consumes: `config.CaptureConfig`, `contract.MOTION_CHANNEL_INDEX`, `contract.EVENTS_STREAM_NAME`.
- Produces: `sidecar.build_sidecar(config: CaptureConfig) -> dict[str, object]`.

**Note:** The test imports htdp's `validate_sidecar` (dev dep) to prove the sidecar satisfies the real contract. The session/consent/device blocks in the test MUST be full valid schema instances — build them from htdp models so the test is honest.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sidecar.py`:

```python
from htdp_capture.config import CaptureConfig
from htdp_capture.sidecar import build_sidecar


def _full_config(**over):
    session = {
        "session_id": "cap-0001",
        "participant_id": "p1",
        "protocol_id": "proto",
        "consent_form_version": "v1",
        "device_config_id": "vive-01",
        "start_time_s": 0.0,
    }
    consent = {"consent_form_version": "v1"}
    device_config = {"device_config_id": "vive-01"}
    base = dict(
        trackers=["right_wrist", "object"],
        session=session,
        consent=consent,
        device_config=device_config,
    )
    base.update(over)
    return CaptureConfig(**base)


def test_top_level_keys():
    sc = build_sidecar(_full_config())
    assert set(sc) >= {"session", "consent", "device_config", "ingest_map"}


def test_motion_entries_have_full_channel_map():
    sc = build_sidecar(_full_config())
    rw = sc["ingest_map"]["right_wrist"]
    assert rw["role"] == "motion"
    assert rw["tracker_id"] == "right_wrist"
    assert rw["channels"] == {
        "x_m": 0, "y_m": 1, "z_m": 2, "qw": 3,
        "qx": 4, "qy": 5, "qz": 6, "quality": 7,
    }


def test_events_entry_present():
    sc = build_sidecar(_full_config())
    assert sc["ingest_map"]["events"] == {"role": "events"}


def test_identity_frame_transform_is_omitted():
    sc = build_sidecar(_full_config(frame_rotation=(1.0, 0.0, 0.0, 0.0)))
    assert "frame_transform" not in sc


def test_nonidentity_frame_transform_present():
    sc = build_sidecar(_full_config(frame_rotation=(0.0, 1.0, 0.0, 0.0)))
    assert sc["frame_transform"] == {"rotation": [0.0, 1.0, 0.0, 0.0]}


def test_sidecar_satisfies_htdp_validate_sidecar():
    # The contract guard: htdp must accept the sidecar we emit.
    from htdp.ingest.session import validate_sidecar

    sc = build_sidecar(_full_config())
    parsed = validate_sidecar(sc)
    assert set(parsed.ingest_map.motion) == {"right_wrist", "object"}
    assert parsed.ingest_map.events_stream == "events"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_sidecar.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/sidecar.py`:

```python
from __future__ import annotations

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNEL_INDEX

_IDENTITY = (1.0, 0.0, 0.0, 0.0)


def build_sidecar(config: CaptureConfig) -> dict[str, object]:
    ingest_map: dict[str, object] = {
        tracker: {
            "role": "motion",
            "tracker_id": tracker,
            "channels": dict(MOTION_CHANNEL_INDEX),
        }
        for tracker in config.trackers
    }
    ingest_map[EVENTS_STREAM_NAME] = {"role": "events"}

    sidecar: dict[str, object] = {
        "session": config.session,
        "consent": config.consent,
        "device_config": config.device_config,
        "ingest_map": ingest_map,
    }
    if config.frame_rotation is not None and tuple(config.frame_rotation) != _IDENTITY:
        sidecar["frame_transform"] = {"rotation": list(config.frame_rotation)}
    return sidecar
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_sidecar.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (incl. the htdp `validate_sidecar` test — confirm it RUNS, not skips), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: sidecar builder (passes htdp validate_sidecar)"
```

---

### Task 6: XDF writer

**Files:**
- Create: `src/htdp_capture/xdf_writer.py`
- Test: `tests/test_xdf_writer.py`

**Interfaces:**
- Produces: `xdf_writer.CapturedStream(name:str, fmt:str, n_channels:int, srate:float, stamps:list[float], numeric:list[list[float]]|None=None, strings:list[str]|None=None)`; `xdf_writer.write_xdf(streams:list[CapturedStream], out_path:Path, *, force:bool=False) -> Path`; raises `xdf_writer.XdfWriteError`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_xdf_writer.py`:

```python
import pyxdf
import pytest

from htdp_capture.xdf_writer import CapturedStream, XdfWriteError, write_xdf


def _motion_stream():
    return CapturedStream(
        name="right_wrist", fmt="double64", n_channels=8, srate=100.0,
        stamps=[1000.0, 1000.01],
        numeric=[[0.1, 0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 1.0],
                 [0.4, 0.5, 0.6, 1.0, 0.0, 0.0, 0.0, 1.0]],
    )


def _events_stream():
    return CapturedStream(
        name="events", fmt="string", n_channels=1, srate=0.0,
        stamps=[1000.0],
        strings=['{"event_id": 1, "label": "start"}'],
    )


def test_writes_xdf_magic_prefix(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    assert out.read_bytes().startswith(b"XDF:")


def test_roundtrips_numeric_via_pyxdf(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    s = streams[0]
    assert s["info"]["name"][0] == "right_wrist"
    assert s["info"]["channel_format"][0] == "double64"
    assert [list(map(float, row)) for row in s["time_series"]] == _motion_stream().numeric
    assert [float(t) for t in s["time_stamps"]] == _motion_stream().stamps


def test_roundtrips_string_via_pyxdf(tmp_path):
    out = write_xdf([_events_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    s = streams[0]
    assert s["info"]["channel_format"][0] == "string"
    assert [row[0] for row in s["time_series"]] == _events_stream().strings


def test_channel_labels_present_in_xml(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    labels = [c["label"][0] for c in streams[0]["info"]["desc"][0]["channels"][0]["channel"]]
    assert labels == ["x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality"]


def test_force_guard(tmp_path):
    p = tmp_path / "rec.xdf"
    write_xdf([_motion_stream()], p)
    with pytest.raises(FileExistsError):
        write_xdf([_motion_stream()], p)
    write_xdf([_motion_stream()], p, force=True)  # no raise


def test_empty_stream_rejected(tmp_path):
    empty = CapturedStream("right_wrist", "double64", 8, 100.0, [], numeric=[])
    with pytest.raises(XdfWriteError):
        write_xdf([empty], tmp_path / "rec.xdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_xdf_writer.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/xdf_writer.py`:

```python
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from htdp_capture.contract import MOTION_CHANNELS


class XdfWriteError(Exception):
    """Raised on an invalid stream set (e.g. empty capture)."""


@dataclass
class CapturedStream:
    name: str
    fmt: str  # "double64" or "string"
    n_channels: int
    srate: float
    stamps: list[float]
    numeric: list[list[float]] | None = None
    strings: list[str] | None = None


def _chunk(tag: int, content: bytes) -> bytes:
    body = struct.pack("<H", tag) + content
    return b"\x04" + struct.pack("<I", len(body)) + body


def _channels_xml(n_channels: int) -> str:
    # Motion streams carry the contract labels; others get generic labels.
    if n_channels == len(MOTION_CHANNELS):
        labels = MOTION_CHANNELS
    else:
        labels = tuple(f"ch{i}" for i in range(n_channels))
    inner = "".join(f"<channel><label>{label}</label></channel>" for label in labels)
    return f"<desc><channels>{inner}</channels></desc>"


def _stream_header(stream_id: int, s: CapturedStream) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<name>{s.name}</name><type>{s.name}</type>"
        f"<channel_count>{s.n_channels}</channel_count>"
        f"<nominal_srate>{s.srate}</nominal_srate>"
        f"<channel_format>{s.fmt}</channel_format>"
        f"{_channels_xml(s.n_channels)}</info>"
    )
    return _chunk(2, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def _samples_numeric(stream_id: int, stamps: list[float], rows: list[list[float]]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, row in zip(stamps, rows):
        out += b"\x08" + struct.pack("<d", ts)
        out += b"".join(struct.pack("<d", v) for v in row)
    return _chunk(3, out)


def _samples_string(stream_id: int, stamps: list[float], rows: list[str]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, value in zip(stamps, rows):
        encoded = value.encode("utf-8")
        out += b"\x08" + struct.pack("<d", ts)
        out += b"\x04" + struct.pack("<I", len(encoded)) + encoded
    return _chunk(3, out)


def _stream_footer(stream_id: int, stamps: list[float]) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<first_timestamp>{stamps[0]}</first_timestamp>"
        f"<last_timestamp>{stamps[-1]}</last_timestamp>"
        f"<sample_count>{len(stamps)}</sample_count></info>"
    )
    return _chunk(6, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def write_xdf(streams: list[CapturedStream], out_path: Path, *, force: bool = False) -> Path:
    if not streams:
        raise XdfWriteError("no streams to write")
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} already exists (use force=True)")

    blob = b"XDF:"
    blob += _chunk(1, b'<?xml version="1.0"?><info><version>1.0</version></info>')
    for stream_id, s in enumerate(streams, start=1):
        if not s.stamps:
            raise XdfWriteError(f"stream '{s.name}' has no samples")
        blob += _stream_header(stream_id, s)
        if s.fmt == "string":
            assert s.strings is not None
            blob += _samples_string(stream_id, s.stamps, s.strings)
        else:
            assert s.numeric is not None
            blob += _samples_numeric(stream_id, s.stamps, s.numeric)
        blob += _stream_footer(stream_id, s.stamps)

    out_path.write_bytes(blob)
    return out_path
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_xdf_writer.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: in-house XDF writer (pyxdf round-trip verified)"
```

---

### Task 7: LSL outlets

**Files:**
- Create: `src/htdp_capture/outlets.py`
- Test: `tests/test_outlets.py`

**Interfaces:**
- Consumes: `contract.MOTION_CHANNELS`, `contract.EVENTS_STREAM_NAME`.
- Produces: `outlets.make_motion_outlet(tracker_id:str, rate_hz:float) -> StreamOutlet`; `outlets.make_events_outlet() -> StreamOutlet`.

**Note:** This task needs real `pylsl`. Gate the test with `importorskip`. Run with pylsl installed and confirm it RUNS.

- [ ] **Step 1: Write the failing test**

Create `tests/test_outlets.py`:

```python
import pytest

pytest.importorskip("pylsl")

from htdp_capture.outlets import make_events_outlet, make_motion_outlet  # noqa: E402


def test_motion_outlet_has_8_channels_double64():
    outlet = make_motion_outlet("right_wrist", 100.0)
    info = outlet.get_info()
    assert info.name() == "right_wrist"
    assert info.type() == "motion"
    assert info.channel_count() == 8
    assert info.channel_format() == 1  # cf_double64 == 1


def test_motion_outlet_labels_in_contract_order():
    info = make_motion_outlet("torso", 100.0).get_info()
    ch = info.desc().child("channels").child("channel")
    labels = []
    while not ch.empty():
        labels.append(ch.child_value("label"))
        ch = ch.next_sibling()
    assert labels == ["x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality"]


def test_events_outlet_is_string_markers():
    info = make_events_outlet().get_info()
    assert info.name() == "events"
    assert info.type() == "Markers"
    assert info.channel_count() == 1
    assert info.channel_format() == 3  # cf_string == 3
    assert info.nominal_srate() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_outlets.py -v`
Expected: FAIL — module not found (NOT skipped; pylsl is installed via dev deps).

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/outlets.py`:

```python
from __future__ import annotations

from pylsl import StreamInfo, StreamOutlet, cf_double64, cf_string

from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS


def make_motion_outlet(tracker_id: str, rate_hz: float) -> StreamOutlet:
    info = StreamInfo(
        name=tracker_id,
        type="motion",
        channel_count=len(MOTION_CHANNELS),
        nominal_srate=rate_hz,
        channel_format=cf_double64,
        source_id=f"htdp_capture_motion_{tracker_id}",
    )
    channels = info.desc().append_child("channels")
    for label in MOTION_CHANNELS:
        channels.append_child("channel").append_child_value("label", label)
    return StreamOutlet(info)


def make_events_outlet() -> StreamOutlet:
    info = StreamInfo(
        name=EVENTS_STREAM_NAME,
        type="Markers",
        channel_count=1,
        nominal_srate=0.0,
        channel_format=cf_string,
        source_id="htdp_capture_events",
    )
    return StreamOutlet(info)
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_outlets.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (confirm RAN, not skipped), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: LSL motion + events outlets"
```

---

### Task 8: inlet recorder

**Files:**
- Create: `src/htdp_capture/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: `pylsl`, `xdf_writer.CapturedStream`.
- Produces: `recorder.RecorderError`; `recorder.StreamRecorder(name:str, fmt:str, n_channels:int, srate:float, *, timeout:float=5.0)` with `.drain()->None` and `.to_captured()->CapturedStream`.

**Note:** Real pylsl loopback. Gate with `importorskip`. The test pushes through an outlet, then drains the recorder.

- [ ] **Step 1: Write the failing test**

Create `tests/test_recorder.py`:

```python
import time

import pytest

pytest.importorskip("pylsl")

from htdp_capture.outlets import make_motion_outlet  # noqa: E402
from htdp_capture.recorder import RecorderError, StreamRecorder  # noqa: E402


def test_missing_stream_raises():
    with pytest.raises(RecorderError):
        StreamRecorder("nonexistent_stream_xyz", "double64", 8, 100.0, timeout=0.5)


def test_drain_captures_pushed_numeric_samples():
    outlet = make_motion_outlet("right_wrist", 100.0)
    rec = StreamRecorder("right_wrist", "double64", 8, 100.0, timeout=5.0)
    sample = [0.1, 0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 1.0]
    outlet.push_sample(sample, timestamp=1000.0)
    time.sleep(0.2)  # let LSL deliver
    rec.drain()
    captured = rec.to_captured()
    assert captured.name == "right_wrist"
    assert captured.fmt == "double64"
    assert captured.numeric == [sample]
    assert captured.stamps == [1000.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_recorder.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/recorder.py`:

```python
from __future__ import annotations

from pylsl import StreamInlet, proc_none, resolve_byprop

from htdp_capture.xdf_writer import CapturedStream


class RecorderError(Exception):
    """Raised when a stream cannot be resolved."""


class StreamRecorder:
    """Resolves one named LSL stream and drains its samples into buffers."""

    def __init__(
        self,
        name: str,
        fmt: str,
        n_channels: int,
        srate: float,
        *,
        timeout: float = 5.0,
    ) -> None:
        results = resolve_byprop("name", name, timeout=timeout)
        if not results:
            raise RecorderError(f"LSL stream '{name}' not found within {timeout}s")
        # No clock-sync, no dejitter: keep timestamps verbatim (htdp reads them as-is).
        self._inlet = StreamInlet(results[0], processing_flags=proc_none)
        self._name = name
        self._fmt = fmt
        self._n_channels = n_channels
        self._srate = srate
        self._stamps: list[float] = []
        self._numeric: list[list[float]] = []
        self._strings: list[str] = []

    def drain(self) -> None:
        while True:
            sample, ts = self._inlet.pull_sample(timeout=0.0)
            if sample is None:
                break
            self._stamps.append(float(ts))
            if self._fmt == "string":
                self._strings.append(str(sample[0]))
            else:
                self._numeric.append([float(v) for v in sample])

    def to_captured(self) -> CapturedStream:
        return CapturedStream(
            name=self._name,
            fmt=self._fmt,
            n_channels=self._n_channels,
            srate=self._srate,
            stamps=self._stamps,
            numeric=self._numeric if self._fmt != "string" else None,
            strings=self._strings if self._fmt == "string" else None,
        )
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_recorder.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (confirm RAN), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: LSL inlet recorder"
```

---

### Task 9: app orchestrator

**Files:**
- Create: `src/htdp_capture/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `config.CaptureConfig`, `pose_source.PoseSource`, `marker_source.MarkerSource`, `outlets`, `recorder.StreamRecorder`, `xdf_writer.write_xdf`, `sidecar.build_sidecar`, `contract.MOTION_CHANNELS`/`EVENTS_STREAM_NAME`.
- Produces: `app.run_capture(config: CaptureConfig, pose_source: PoseSource, marker_source: MarkerSource, out_xdf: Path, out_sidecar: Path, *, force: bool=False, clock=time.monotonic, sleep=time.sleep) -> tuple[Path, Path]`.

**Behavior:** create motion outlets (one per tracker) + events outlet; create a `StreamRecorder` per stream (resolving the loopback); loop until `duration_s` elapses: poll pose source → push each tracker sample with `timestamp=pose.t` in `MOTION_CHANNELS` order; poll marker source → push each event's `to_json()` with its timestamp; `drain()` all recorders; sleep `1/rate_hz`. After the loop, drain once more. Assemble `CapturedStream`s (motion in tracker order, then events). Raise `XdfWriteError`-friendly guard if no motion samples. Write XDF + sidecar JSON.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
import json

import pytest

pytest.importorskip("pylsl")

from htdp_capture.app import run_capture  # noqa: E402
from htdp_capture.config import CaptureConfig  # noqa: E402
from htdp_capture.mock_pose import MockPoseSource  # noqa: E402
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule  # noqa: E402


def _config():
    return CaptureConfig(
        trackers=["right_wrist", "object"],
        session={
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "vive-01"},
        rate_hz=200.0,
        duration_s=0.3,
    )


def test_run_capture_writes_xdf_and_sidecar(tmp_path):
    cfg = _config()
    out_xdf = tmp_path / "rec.xdf"
    out_sidecar = tmp_path / "ingest.json"
    xdf_path, sc_path = run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        out_xdf,
        out_sidecar,
    )
    assert xdf_path.read_bytes().startswith(b"XDF:")
    sc = json.loads(sc_path.read_text())
    assert set(sc["ingest_map"]) == {"right_wrist", "object", "events"}


def test_captured_xdf_has_motion_samples(tmp_path):
    import pyxdf

    cfg = _config()
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        tmp_path / "rec.xdf",
        tmp_path / "ingest.json",
    )
    streams, _ = pyxdf.load_xdf(
        str(tmp_path / "rec.xdf"), dejitter_timestamps=False, synchronize_clocks=False
    )
    names = {s["info"]["name"][0] for s in streams}
    assert {"right_wrist", "object", "events"} <= names
    motion = next(s for s in streams if s["info"]["name"][0] == "right_wrist")
    assert len(motion["time_series"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_app.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/app.py`:

```python
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS
from htdp_capture.marker_source import MarkerSource
from htdp_capture.outlets import make_events_outlet, make_motion_outlet
from htdp_capture.pose_source import PoseSource
from htdp_capture.recorder import StreamRecorder
from htdp_capture.sidecar import build_sidecar
from htdp_capture.xdf_writer import CapturedStream, XdfWriteError, write_xdf


def run_capture(
    config: CaptureConfig,
    pose_source: PoseSource,
    marker_source: MarkerSource,
    out_xdf: Path,
    out_sidecar: Path,
    *,
    force: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    config.validate()

    motion_outlets = {t: make_motion_outlet(t, config.rate_hz) for t in config.trackers}
    events_outlet = make_events_outlet()

    motion_recorders = {
        t: StreamRecorder(t, "double64", len(MOTION_CHANNELS), config.rate_hz)
        for t in config.trackers
    }
    events_recorder = StreamRecorder(EVENTS_STREAM_NAME, "string", 1, 0.0)

    period = 1.0 / config.rate_hz
    start = clock()
    while clock() - start < config.duration_s:
        poses = pose_source.poll()
        for tracker, pose in poses.items():
            row = [*pose.pos, *pose.quat, pose.quality]
            motion_outlets[tracker].push_sample(row, timestamp=pose.t)
        for ts, event in marker_source.poll():
            events_outlet.push_sample([event.to_json()], timestamp=ts)
        for rec in motion_recorders.values():
            rec.drain()
        events_recorder.drain()
        sleep(period)

    for rec in motion_recorders.values():
        rec.drain()
    events_recorder.drain()
    pose_source.close()
    marker_source.close()

    streams: list[CapturedStream] = [motion_recorders[t].to_captured() for t in config.trackers]
    streams.append(events_recorder.to_captured())

    if all(not s.stamps for s in streams[:-1]):
        raise XdfWriteError("no motion samples captured")

    write_xdf(streams, out_xdf, force=force)
    out_sidecar.write_text(json.dumps(build_sidecar(config), indent=2), encoding="utf-8")
    return out_xdf, out_sidecar
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_app.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (confirm RAN), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: capture app orchestrator (pose+marker -> xdf+sidecar)"
```

---

### Task 10: CLI

**Files:**
- Create: `src/htdp_capture/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `app.run_capture`, `config.CaptureConfig`, `mock_pose.MockPoseSource`, `scripted_marker.ScriptedMarkerSource`/`default_schedule`.
- Produces: `cli.main(argv: list[str] | None = None) -> int`. A `record` subcommand that runs a mock capture to `--out-xdf`/`--out-sidecar` using a config JSON (`--config`) or sensible defaults.

**Config JSON shape** (operator-supplied, drives the sidecar blocks):
```json
{
  "trackers": ["right_wrist", "object"],
  "rate_hz": 100.0,
  "duration_s": 2.0,
  "session": {"session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
              "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0},
  "consent": {"consent_form_version": "v1"},
  "device_config": {"device_config_id": "vive-01"}
}
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
import json

import pytest

pytest.importorskip("pylsl")

from htdp_capture.cli import main  # noqa: E402


def _write_config(path):
    path.write_text(json.dumps({
        "trackers": ["right_wrist"],
        "rate_hz": 200.0,
        "duration_s": 0.2,
        "session": {
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        "consent": {"consent_form_version": "v1"},
        "device_config": {"device_config_id": "vive-01"},
    }))


def test_record_writes_outputs(tmp_path):
    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    rc = main(["record", "--config", str(cfg), "--out-xdf", str(xdf),
               "--out-sidecar", str(sidecar)])
    assert rc == 0
    assert xdf.read_bytes().startswith(b"XDF:")
    assert "ingest_map" in json.loads(sidecar.read_text())


def test_record_force_overwrites(tmp_path):
    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    args = ["record", "--config", str(cfg), "--out-xdf", str(xdf), "--out-sidecar", str(sidecar)]
    assert main(args) == 0
    assert main(args + ["--force"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_cli.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from htdp_capture.app import run_capture
from htdp_capture.config import CaptureConfig
from htdp_capture.mock_pose import MockPoseSource
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule


def _config_from_json(path: Path) -> CaptureConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CaptureConfig(
        trackers=list(raw["trackers"]),
        session=raw["session"],
        consent=raw["consent"],
        device_config=raw["device_config"],
        rate_hz=float(raw.get("rate_hz", 100.0)),
        duration_s=float(raw.get("duration_s", 2.0)),
        frame_rotation=tuple(raw["frame_rotation"]) if raw.get("frame_rotation") else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="htdp-capture")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="run a mock capture to XDF + sidecar")
    record.add_argument("--config", required=True, type=Path)
    record.add_argument("--out-xdf", required=True, type=Path)
    record.add_argument("--out-sidecar", required=True, type=Path)
    record.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "record":
        config = _config_from_json(args.config)
        run_capture(
            config,
            MockPoseSource(config.trackers, rate_hz=config.rate_hz),
            ScriptedMarkerSource(config.schedule or default_schedule()),
            args.out_xdf,
            args.out_sidecar,
            force=args.force,
        )
        return 0
    return 1
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_cli.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (confirm RAN), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: htdp-capture CLI (record subcommand)"
```

---

### Task 11: contract conformance — full round-trip through htdp ingest

**Files:**
- Test: `tests/test_conformance.py`

**Interfaces:**
- Consumes: `app.run_capture`, `htdp.ingest.session.ingest_xdf` (dev dep).

**Note:** THE payoff. Runs a real capture, then drives the real `htdp ingest` over the produced `.xdf` + `ingest.json`, and asserts the resulting raw session is valid and reflects what the mock emitted (per-tracker motion, events, quality). Gate on both `pylsl` and `htdp`+`pyxdf`. This is the contract guard — if htdp's contract drifts, it goes red.

- [ ] **Step 1: Write the failing test**

Create `tests/test_conformance.py`:

```python
import csv

import pytest

pytest.importorskip("pylsl")
pytest.importorskip("pyxdf")
ingest = pytest.importorskip("htdp.ingest.session")

from htdp_capture.app import run_capture  # noqa: E402
from htdp_capture.config import CaptureConfig  # noqa: E402
from htdp_capture.mock_pose import MockPoseSource  # noqa: E402
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule  # noqa: E402


def _config():
    return CaptureConfig(
        trackers=["right_wrist", "object"],
        session={
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "vive-01"},
        rate_hz=200.0,
        duration_s=0.4,
    )


def test_capture_roundtrips_through_htdp_ingest(tmp_path):
    cfg = _config()
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
    )

    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)

    # Raw session structure exists with per-tracker motion + events.
    assert (raw / "session.json").is_file()
    assert (raw / "streams" / "motion_right_wrist.csv").is_file()
    assert (raw / "streams" / "motion_object.csv").is_file()
    assert (raw / "streams" / "events.csv").is_file()

    # Motion rows carry the contract columns, quality preserved, timestamps rebased to >= 0.
    with (raw / "streams" / "motion_right_wrist.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 0
    assert set(rows[0]) >= {
        "timestamp_s", "tracker_id", "x_m", "y_m", "z_m",
        "qw", "qx", "qy", "qz", "quality", "defect_tag",
    }
    assert rows[0]["tracker_id"] == "right_wrist"
    assert all(float(r["quality"]) == 1.0 for r in rows)
    assert min(float(r["timestamp_s"]) for r in rows) >= 0.0


def test_dropout_quality_survives_roundtrip(tmp_path):
    cfg = _config()
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz, dropout_frames=set(range(1000))),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
    )
    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)
    with (raw / "streams" / "motion_right_wrist.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(float(r["quality"]) == 0.0 for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_conformance.py -v`
Expected: FAIL — `run_capture` produces output but if any contract mismatch exists, `ingest_xdf` raises; initially the test fails only if an upstream bug exists. If all prior tasks are correct it may PASS immediately — that is acceptable for an integration test (no separate red phase required when it composes already-tested units). If it fails, debug with systematic-debugging.

- [ ] **Step 3: Make it pass**

No new production code expected. If it fails, the failure points at a real contract bug in an earlier task — fix there, not here.

- [ ] **Step 4: Run full suite + lint + type**

Run: `uv run --extra dev pytest -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: ALL tests PASS. Confirm the LSL/htdp-gated tests RAN (not skipped) — grep the output for "skipped" and verify count is 0 with dev deps installed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test: end-to-end contract conformance via htdp ingest"
```

---

## Self-Review

**Spec coverage:**
- Separate repo → Task 1. ✓
- contract constants (channel order, trackers, events name, labels) → Task 1. ✓
- `quality` validity flag + dropout → Task 2 (MockPoseSource) + Task 11 (survives round-trip). ✓
- structured markers (JSON payload, EventLabel vocab) → Task 3. ✓
- config + full session/consent/device blocks + frame_transform → Task 4. ✓
- sidecar (full blocks + ingest_map + optional frame_transform; passes htdp validate) → Task 5. ✓
- own XDF writer (double64, XDF: prefix, pyxdf round-trip) → Task 6. ✓
- LSL outlets (cf_double64 motion + cf_string events) → Task 7. ✓
- in-house inlet recorder (no dejitter/sync) → Task 8. ✓
- app orchestrator → Task 9. ✓
- CLI → Task 10. ✓
- contract conformance round-trip through htdp ingest → Task 11. ✓
- OpenVR / real calibration / LabRecorder / EEG explicitly OUT — no task, correct. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `CapturedStream` defined in Task 6, consumed identically in Tasks 8/9. `run_capture` signature in Task 9 matches calls in Tasks 10/11. `MarkerEvent`/`Pose` field names consistent across tasks. `frame_rotation` 4-tuple consistent (config→sidecar). ✓
