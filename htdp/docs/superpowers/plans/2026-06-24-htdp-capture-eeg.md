# htdp-capture EEG Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, additive EEG stream to the `htdp-capture` app so a recording carries EEG alongside motion + events, round-tripping through `htdp ingest`.

**Architecture:** New `EegSource` ABC + `MockEegSource` (per-channel deterministic sine) feed an optional `cf_double64` eeg LSL outlet; `CaptureConfig` gains an optional `eeg` field; `build_sidecar` adds an eeg `ingest_map` entry; `run_capture` wires the eeg outlet+recorder when configured. Motion+events code paths are untouched; eeg reuses the numeric `xdf_writer`/`recorder` paths.

**Tech Stack:** Python 3.11+, `pylsl`, `numpy`, `pyxdf`; `htdp` dev-dep for conformance. Same repo/tooling as the spine.

## Global Constraints

- Repo: `/Users/alexanderlemberger/htdp-capture`. All paths relative to it.
- **Additive only.** Do NOT change motion/events behavior. Existing tests must stay green. `eeg=None` (default) ⇒ byte-identical behavior to today.
- EEG stream: LSL name `eeg_<eeg_id>`, type `"eeg"`, `cf_double64`, `channel_count = len(channels)`, labels in XML `desc/channels` in list order.
- EEG XDF channel_format = `double64` (reuses the numeric writer path).
- Sidecar eeg entry (keyed by LSL stream name): `{"role":"eeg","eeg_id":<id>,"channels":{<label>:<index>,...}}`, index = position in the labels list.
- EEG has NO quality channel.
- LSL connection-priming applies to the eeg outlet too: it MUST be in the `_wait_for_consumers` set before the push loop (samples pushed before the inlet connects are dropped — see the spine's recorder/app design).
- Recorder must NOT dejitter/clock-sync (unchanged).
- TDD: failing test first, watch it fail, minimal impl, watch it pass, commit. One commit per task, exact message. DRY/YAGNI.
- `ruff check .` and `mypy src/htdp_capture` clean at every commit.
- LSL/htdp/pyxdf-gated tests use `pytest.importorskip`; run them WITH deps installed and confirm they RAN (grep output for "skip" → 0). False greens are the enemy (a fallback/bypass that dodges the real path is a hard reject — see the spine's history).
- Gate command after every task:
  `uv run --extra dev pytest -q && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`

---

### Task 1: EegSource + EegConfig + MockEegSource + stream-name helper

**Files:**
- Create: `src/htdp_capture/eeg_source.py`
- Create: `src/htdp_capture/mock_eeg.py`
- Modify: `src/htdp_capture/contract.py` (append `eeg_stream_name`)
- Test: `tests/test_mock_eeg.py`, `tests/test_contract.py` (append one test)

**Interfaces:**
- Produces: `eeg_source.EegConfig(eeg_id:str, channels:list[str], rate_hz:float=250.0)`; `eeg_source.EegSource` ABC with `poll()->list[tuple[float,list[float]]]`, `close()->None`; `mock_eeg.MockEegSource(config:EegConfig, clock=time.monotonic)`; `contract.eeg_stream_name(eeg_id:str)->str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mock_eeg.py`:

```python
import math

from htdp_capture.eeg_source import EegConfig
from htdp_capture.mock_eeg import MockEegSource


def _fixed_clock():
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.004
        return state["t"]

    return clock


def test_poll_returns_one_sample_with_one_value_per_channel():
    cfg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    batch = src.poll()
    assert len(batch) == 1
    ts, sample = batch[0]
    assert isinstance(ts, float)
    assert len(sample) == 3


def test_first_frame_values_are_per_channel_sine():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b", "c", "d"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    _, sample = src.poll()[0]
    assert sample == [math.sin(0 * 0.1 + i) for i in range(4)]


def test_channels_are_distinct():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b", "c"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    _, sample = src.poll()[0]
    assert len(set(sample)) == 3


def test_deterministic_across_instances():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b"])
    a = MockEegSource(cfg, clock=_fixed_clock())
    b = MockEegSource(cfg, clock=_fixed_clock())
    assert a.poll()[0][1] == b.poll()[0][1]


def test_frame_advances_signal():
    cfg = EegConfig(eeg_id="amp0", channels=["a"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    first = src.poll()[0][1]
    second = src.poll()[0][1]
    assert first != second
```

Append to `tests/test_contract.py`:

```python
def test_eeg_stream_name():
    assert contract.eeg_stream_name("amp0") == "eeg_amp0"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alexanderlemberger/htdp-capture && uv run --extra dev pytest tests/test_mock_eeg.py tests/test_contract.py::test_eeg_stream_name -v`
Expected: FAIL — module/attribute not found.

- [ ] **Step 3: Write minimal implementation**

Create `src/htdp_capture/eeg_source.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EegConfig:
    eeg_id: str
    channels: list[str]
    rate_hz: float = 250.0


class EegSource(ABC):
    @abstractmethod
    def poll(self) -> list[tuple[float, list[float]]]: ...

    def close(self) -> None:  # default no-op; hardware sources override
        return None
```

Create `src/htdp_capture/mock_eeg.py`:

```python
from __future__ import annotations

import math
import time
from collections.abc import Callable

from htdp_capture.eeg_source import EegConfig, EegSource


class MockEegSource(EegSource):
    """Hardware-free synthetic EEG: per-channel deterministic sine."""

    def __init__(
        self,
        config: EegConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._channels = list(config.channels)
        self._clock = clock
        self._frame = 0

    def poll(self) -> list[tuple[float, list[float]]]:
        frame = self._frame
        t = self._clock()
        sample = [math.sin(frame * 0.1 + i) for i in range(len(self._channels))]
        self._frame += 1
        return [(t, sample)]
```

Append to `src/htdp_capture/contract.py`:

```python


def eeg_stream_name(eeg_id: str) -> str:
    return f"eeg_{eeg_id}"
```

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_mock_eeg.py tests/test_contract.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: EegSource, EegConfig, MockEegSource, eeg_stream_name"
```

---

### Task 2: CaptureConfig eeg field + validation

**Files:**
- Modify: `src/htdp_capture/config.py`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: `eeg_source.EegConfig`.
- Produces: `CaptureConfig.eeg: EegConfig | None = None`; `validate()` enforces eeg rules when set.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
from htdp_capture.eeg_source import EegConfig


def _eeg_cfg(**over):
    base = dict(
        trackers=["right_wrist"],
        session={"session_id": "s"},
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "d"},
    )
    base.update(over)
    return CaptureConfig(**base)


def test_no_eeg_is_valid():
    _eeg_cfg().validate()  # eeg defaults to None


def test_valid_eeg_passes():
    _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2"])).validate()


def test_empty_eeg_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="", channels=["Fp1"])).validate()


def test_empty_channels_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=[])).validate()


def test_duplicate_channel_labels_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp1"])).validate()


def test_bad_eeg_rate_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1"], rate_hz=0.0)).validate()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_config.py -v`
Expected: FAIL — `CaptureConfig` has no `eeg` parameter.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `src/htdp_capture/config.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass, field

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.eeg_source import EegConfig
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
    eeg: EegConfig | None = None

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
        if self.eeg is not None:
            self._validate_eeg(self.eeg)

    @staticmethod
    def _validate_eeg(eeg: EegConfig) -> None:
        if not eeg.eeg_id:
            raise ConfigError("eeg_id must be non-empty")
        if not eeg.channels:
            raise ConfigError("eeg.channels must be non-empty")
        if len(set(eeg.channels)) != len(eeg.channels):
            raise ConfigError("eeg.channels must not contain duplicate labels")
        if eeg.rate_hz <= 0:
            raise ConfigError("eeg.rate_hz must be positive")
```

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_config.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (incl. existing config tests), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: optional eeg field + validation on CaptureConfig"
```

---

### Task 3: sidecar eeg entry

**Files:**
- Modify: `src/htdp_capture/sidecar.py`
- Test: `tests/test_sidecar.py` (append)

**Interfaces:**
- Consumes: `contract.eeg_stream_name`, `config.CaptureConfig.eeg`.
- Produces: `build_sidecar` adds `ingest_map[eeg_stream_name(eeg_id)] = {"role":"eeg","eeg_id":...,"channels":{label:idx}}` when `config.eeg` set.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sidecar.py`:

```python
from htdp_capture.eeg_source import EegConfig


def test_no_eeg_has_no_eeg_entry():
    sc = build_sidecar(_full_config())
    assert not any(k.startswith("eeg_") for k in sc["ingest_map"])


def test_eeg_entry_shape():
    sc = build_sidecar(_full_config(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"])))
    entry = sc["ingest_map"]["eeg_amp0"]
    assert entry == {
        "role": "eeg",
        "eeg_id": "amp0",
        "channels": {"Fp1": 0, "Fp2": 1, "C3": 2},
    }


def test_eeg_sidecar_satisfies_htdp_validate_sidecar():
    from htdp.ingest.session import validate_sidecar

    sc = build_sidecar(_full_config(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2"])))
    parsed = validate_sidecar(sc)
    assert "eeg_amp0" in parsed.ingest_map.eeg
    assert parsed.ingest_map.eeg["eeg_amp0"].eeg_id == "amp0"
```

Note: `_full_config` already exists in `tests/test_sidecar.py` from the spine; it accepts `**over`, so passing `eeg=...` works. Verify it does; if `_full_config` does not forward `eeg`, the test's `_full_config(eeg=...)` call still flows through `CaptureConfig(**base)` since `base.update(over)` includes `eeg`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_sidecar.py -v`
Expected: FAIL — `eeg_amp0` key not present.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `src/htdp_capture/sidecar.py` with:

```python
from __future__ import annotations

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNEL_INDEX, eeg_stream_name

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

    if config.eeg is not None:
        ingest_map[eeg_stream_name(config.eeg.eeg_id)] = {
            "role": "eeg",
            "eeg_id": config.eeg.eeg_id,
            "channels": {label: i for i, label in enumerate(config.eeg.channels)},
        }

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

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_sidecar.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (incl. htdp `validate_sidecar` eeg test — confirm RAN), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: sidecar eeg ingest_map entry"
```

---

### Task 4: eeg LSL outlet

**Files:**
- Modify: `src/htdp_capture/outlets.py`
- Test: `tests/test_outlets.py` (append)

**Interfaces:**
- Consumes: `contract.eeg_stream_name`.
- Produces: `outlets.make_eeg_outlet(eeg_id:str, labels:list[str], rate_hz:float) -> StreamOutlet`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_outlets.py`:

```python
from htdp_capture.outlets import make_eeg_outlet  # noqa: E402


def test_eeg_outlet_double64_named_and_labeled():
    outlet = make_eeg_outlet("amp0", ["Fp1", "Fp2", "C3"], 250.0)
    info = outlet.get_info()
    assert info.name() == "eeg_amp0"
    assert info.type() == "eeg"
    assert info.channel_count() == 3
    assert info.channel_format() == 1  # cf_double64 == 1
    assert info.nominal_srate() == 250.0
    ch = info.desc().child("channels").child("channel")
    labels = []
    while not ch.empty():
        labels.append(ch.child_value("label"))
        ch = ch.next_sibling()
    assert labels == ["Fp1", "Fp2", "C3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_outlets.py -v`
Expected: FAIL — `make_eeg_outlet` not defined.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `src/htdp_capture/outlets.py` with:

```python
from __future__ import annotations

from pylsl import StreamInfo, StreamOutlet, cf_double64, cf_string

from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS, eeg_stream_name


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


def make_eeg_outlet(eeg_id: str, labels: list[str], rate_hz: float) -> StreamOutlet:
    info = StreamInfo(
        name=eeg_stream_name(eeg_id),
        type="eeg",
        channel_count=len(labels),
        nominal_srate=rate_hz,
        channel_format=cf_double64,
        source_id=f"htdp_capture_eeg_{eeg_id}",
    )
    channels = info.desc().append_child("channels")
    for label in labels:
        channels.append_child("channel").append_child_value("label", label)
    return StreamOutlet(info)
```

- [ ] **Step 4: Run test + lint + type**

Run: `uv run --extra dev pytest tests/test_outlets.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (confirm RAN, not skipped), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: eeg LSL outlet"
```

---

### Task 5: wire eeg into run_capture

**Files:**
- Modify: `src/htdp_capture/app.py`
- Test: `tests/test_app.py` (append)

**Interfaces:**
- Consumes: `eeg_source.EegSource`, `mock_eeg.MockEegSource`, `outlets.make_eeg_outlet`, `contract.eeg_stream_name`.
- Produces: `run_capture(..., eeg_source: EegSource | None = None)`; when `config.eeg` set, captures the eeg stream into the XDF.

**Behavior:** `run_capture` gains an optional `eeg_source` param. When `config.eeg` is set, an `eeg_source` MUST be provided (else `ValueError`). Create the eeg outlet + a `StreamRecorder(eeg_stream_name, "double64", len(channels), rate_hz)`; include the eeg outlet in `_wait_for_consumers`; in the loop, `eeg_source.poll()` and push each `(ts, sample)` to the eeg outlet; drain the eeg recorder with the others; append the eeg `CapturedStream` after events. When `config.eeg` is None, behavior is byte-identical to today.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
from htdp_capture.eeg_source import EegConfig  # noqa: E402
from htdp_capture.mock_eeg import MockEegSource  # noqa: E402


def _eeg_config():
    cfg = _config()
    cfg.eeg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"], rate_hz=200.0)
    return cfg


def test_capture_with_eeg_writes_eeg_stream(tmp_path):
    import pyxdf

    cfg = _eeg_config()
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        tmp_path / "rec.xdf",
        tmp_path / "ingest.json",
        eeg_source=MockEegSource(cfg.eeg),
    )
    streams, _ = pyxdf.load_xdf(
        str(tmp_path / "rec.xdf"), dejitter_timestamps=False, synchronize_clocks=False
    )
    eeg = next(s for s in streams if s["info"]["name"][0] == "eeg_amp0")
    assert int(eeg["info"]["channel_count"][0]) == 3
    assert len(eeg["time_series"]) > 0


def test_capture_without_eeg_has_no_eeg_stream(tmp_path):
    import pyxdf

    cfg = _config()  # no eeg
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
    assert not any(s["info"]["name"][0].startswith("eeg_") for s in streams)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev pytest tests/test_app.py -v`
Expected: FAIL — `run_capture` has no `eeg_source` parameter.

- [ ] **Step 3: Write minimal implementation**

Replace the full contents of `src/htdp_capture/app.py` with:

```python
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pylsl import StreamOutlet

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS, eeg_stream_name
from htdp_capture.eeg_source import EegSource
from htdp_capture.marker_source import MarkerSource
from htdp_capture.outlets import make_eeg_outlet, make_events_outlet, make_motion_outlet
from htdp_capture.pose_source import PoseSource
from htdp_capture.recorder import StreamRecorder
from htdp_capture.sidecar import build_sidecar
from htdp_capture.xdf_writer import CapturedStream, XdfWriteError, write_xdf


def _wait_for_consumers(
    outlets: list[StreamOutlet], timeout: float, sleep: Callable[[float], None]
) -> None:
    """Block until every outlet has a connected consumer (its recorder inlet).

    Samples pushed before an inlet connects are dropped, so the capture loop must
    not start pushing until all consumers are present.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(o.have_consumers() for o in outlets):
            return
        sleep(0.02)


def run_capture(
    config: CaptureConfig,
    pose_source: PoseSource,
    marker_source: MarkerSource,
    out_xdf: Path,
    out_sidecar: Path,
    *,
    eeg_source: EegSource | None = None,
    force: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    config.validate()
    if config.eeg is not None and eeg_source is None:
        raise ValueError("config.eeg is set but no eeg_source was provided")

    motion_outlets = {t: make_motion_outlet(t, config.rate_hz) for t in config.trackers}
    events_outlet = make_events_outlet()

    # Creating a StreamRecorder opens its inlet, registering it as a consumer.
    motion_recorders = {
        t: StreamRecorder(t, "double64", len(MOTION_CHANNELS), config.rate_hz)
        for t in config.trackers
    }
    events_recorder = StreamRecorder(EVENTS_STREAM_NAME, "string", 1, 0.0)

    eeg_outlet: StreamOutlet | None = None
    eeg_recorder: StreamRecorder | None = None
    if config.eeg is not None:
        eeg_outlet = make_eeg_outlet(config.eeg.eeg_id, config.eeg.channels, config.eeg.rate_hz)
        eeg_recorder = StreamRecorder(
            eeg_stream_name(config.eeg.eeg_id),
            "double64",
            len(config.eeg.channels),
            config.eeg.rate_hz,
        )

    outlets = [*motion_outlets.values(), events_outlet]
    if eeg_outlet is not None:
        outlets.append(eeg_outlet)
    # Do not push until every outlet sees its consumer, or early samples are lost.
    _wait_for_consumers(outlets, timeout=5.0, sleep=sleep)

    period = 1.0 / config.rate_hz
    start = clock()
    while clock() - start < config.duration_s:
        for tracker, pose in pose_source.poll().items():
            row = [*pose.pos, *pose.quat, pose.quality]
            motion_outlets[tracker].push_sample(row, timestamp=pose.t)
        for ts, event in marker_source.poll():
            events_outlet.push_sample([event.to_json()], timestamp=ts)
        if eeg_source is not None and eeg_outlet is not None:
            for ts, sample in eeg_source.poll():
                eeg_outlet.push_sample(sample, timestamp=ts)
        for rec in motion_recorders.values():
            rec.drain()
        events_recorder.drain()
        if eeg_recorder is not None:
            eeg_recorder.drain()
        sleep(period)

    # Final drain to collect any samples still in flight.
    for rec in motion_recorders.values():
        rec.drain()
    events_recorder.drain()
    if eeg_recorder is not None:
        eeg_recorder.drain()
    pose_source.close()
    marker_source.close()
    if eeg_source is not None:
        eeg_source.close()

    streams: list[CapturedStream] = [motion_recorders[t].to_captured() for t in config.trackers]
    streams.append(events_recorder.to_captured())
    if eeg_recorder is not None:
        streams.append(eeg_recorder.to_captured())

    if all(not s.stamps for s in streams[: len(config.trackers)]):
        raise XdfWriteError("no motion samples captured")

    write_xdf(streams, out_xdf, force=force)
    out_sidecar.write_text(json.dumps(build_sidecar(config), indent=2), encoding="utf-8")
    return out_xdf, out_sidecar
```

- [ ] **Step 4: Run tests + lint + type**

Run: `uv run --extra dev pytest tests/test_app.py -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Expected: PASS (incl. existing app tests + both new ones; confirm RAN), clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: wire optional eeg stream into run_capture"
```

---

### Task 6: end-to-end EEG conformance through htdp ingest

**Files:**
- Test: `tests/test_conformance.py` (append)

**Interfaces:**
- Consumes: `run_capture` with eeg, `htdp.ingest.session.ingest_xdf`.

**Note:** THE payoff for this feature — real capture WITH eeg → real `htdp ingest` → assert the eeg CSV lands with the right columns + values, and motion/events still land (additive, non-disruptive). Gated on pylsl+pyxdf+htdp; must RUN not skip.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_conformance.py`:

```python
from htdp_capture.eeg_source import EegConfig  # noqa: E402
from htdp_capture.mock_eeg import MockEegSource  # noqa: E402


def test_capture_with_eeg_roundtrips_through_htdp_ingest(tmp_path):
    cfg = _config()
    cfg.eeg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"], rate_hz=200.0)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
        eeg_source=MockEegSource(cfg.eeg),
    )

    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)

    # Motion + events still land (eeg is additive).
    assert (raw / "streams" / "motion_right_wrist.csv").is_file()
    assert (raw / "streams" / "events.csv").is_file()

    # EEG CSV exists with the label columns + timestamp.
    eeg_csv = raw / "streams" / "eeg_amp0.csv"
    assert eeg_csv.is_file()
    with eeg_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 0
    assert set(rows[0]) == {"timestamp_s", "Fp1", "Fp2", "C3"}
    # Per-channel sine => columns are not all identical within a row.
    assert len({rows[0]["Fp1"], rows[0]["Fp2"], rows[0]["C3"]}) > 1
    # Timestamps rebased to motion t0 (>= 0).
    assert min(float(r["timestamp_s"]) for r in rows) >= 0.0
```

Note: `csv`, `ingest`, `_config`, `MockPoseSource`, `ScriptedMarkerSource`, `default_schedule` are already imported at the top of `tests/test_conformance.py` from the spine. Do not re-import them.

- [ ] **Step 2: Run test to verify it fails (or passes cleanly)**

Run: `uv run --extra dev pytest tests/test_conformance.py::test_capture_with_eeg_roundtrips_through_htdp_ingest -v`
Expected: this composes already-tested units; it should PASS. If it FAILS, the failure points at a real contract bug in Tasks 1-5 — fix there, not here (use systematic-debugging).

- [ ] **Step 3: Make it pass**

No new production code expected.

- [ ] **Step 4: Run full suite + lint + type + skip-check**

Run: `uv run --extra dev pytest -v && uv run --extra dev ruff check . && uv run --extra dev mypy src/htdp_capture`
Then confirm 0 skips with deps present: `uv run --extra dev pytest -q 2>&1 | grep -ic skip` → must print `0`.
Expected: ALL tests PASS, 0 skipped, clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "test: end-to-end EEG conformance via htdp ingest"
```

---

## Self-Review

**Spec coverage:**
- `EegSource` ABC + `MockEegSource` (per-channel sine) → Task 1. ✓
- `eeg_stream_name` helper → Task 1. ✓
- `EegConfig` (eeg_id, channels, rate_hz=250) + count derived from labels → Task 1. ✓
- optional `eeg` field + validation (empty id/channels/dupe/bad rate) → Task 2. ✓
- sidecar eeg entry + htdp `validate_sidecar` guard → Task 3. ✓
- eeg `cf_double64` outlet, name `eeg_<id>`, labels → Task 4. ✓
- wire into `run_capture`, connection-priming includes eeg, additive → Task 5. ✓
- regression: no-eeg → no eeg stream → Task 5. ✓
- conformance round-trip (eeg csv columns+values, motion/events still land) → Task 6. ✓
- out-of-scope (hardware source, quality, filtering, multi-amp) → no task, correct. ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `EegConfig(eeg_id, channels, rate_hz)` consistent across Tasks 1-5. `EegSource.poll()->list[tuple[float,list[float]]]` consumed identically in Task 5. `eeg_stream_name` used in contract/outlets/sidecar/app uniformly. `run_capture` new `eeg_source` kw-only param matches calls in Tasks 5/6. `make_eeg_outlet(eeg_id, labels, rate_hz)` signature consistent (Task 4 def, Task 5 call). The "no motion samples" guard uses `streams[:len(config.trackers)]` so the appended eeg stream never satisfies the motion check. ✓
