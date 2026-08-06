# XDF Ingest Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp ingest`: convert a recorded LSL `.xdf` file plus an `ingest.json` sidecar into the existing v0.1 raw session folder, so the unchanged downstream pipeline (`validate → process → qc → package → replay`) can consume real motion captures.

**Architecture:** New `src/htdp/ingest/` package, decomposed into small single-purpose, individually-testable units — `frame` (pure quaternion transform), `reader` (pyxdf parse, optional-dep guarded), `mapping` (stream/channel → contract columns), `session` (a set of **pure** builder functions + one thin orchestrator). `ingest` is the structural inverse of `synth`. A throwaway `tests/_xdf_writer.py` round-trips a synth session through a real `.xdf` so the adapter is testable with zero hardware.

**Modularity principle (this plan's core constraint):** every task delivers exactly one named function/unit with its own test and its own commit. The `session` logic is split into **pure** functions (`validate_sidecar`, `compute_t0`, `build_motion_rows`, `build_event_rows`, `write_raw_folder`) that are unit-tested **without** `pyxdf`; only the final thin `ingest_xdf` orchestrator needs the optional dep. A reviewer can accept or reject any task independently.

**Tech Stack:** Python ≥3.11, pydantic v2, typer, `pyxdf` (new optional extra), pytest. Pure-python quaternion math (no numpy).

## Global Constraints

Copied verbatim from `AGENTS.md` / the spec — every task's requirements implicitly include these:

- Python `>=3.11`. mypy `strict` must pass on `src/htdp/ingest`.
- ruff: `line-length = 100`, `line-ending = lf`. Run `uv run ruff format --check . && uv run ruff check .` clean.
- Canonical output only: JSON via `io.canonical.dump_json` (sorted keys, 2-space indent, trailing `\n`); CSV via `io.canonical.write_csv` (stable columns, 6dp floats, `\n` line endings).
- **Raw is immutable / no partial writes:** build every row in memory first, then write the whole folder; never write into an existing pipeline stage.
- **Reuse existing pydantic schemas unchanged** (`Session`, `Consent`, `DeviceConfig`, `EventMarker`, `CoordinateFrame`, `StreamRef`). No schema model change → no JSON-Schema re-export.
- `pyxdf` is an **optional** extra; core install and core tests must pass without it (mirror the `replay`/`mujoco` pattern).
- Deterministic: same inputs → identical raw folder.
- Contract motion frame: `x=right, y=forward, z=up`, quaternion order `w,x,y,z`, units meters/seconds.
- Contract tracker set (reuse exactly): `("right_wrist", "left_wrist", "torso", "object")`.

**Reference — canonical column orders (re-declared in `ingest`, do NOT import private synth constants):**

```python
_MOTION_COLS = ["timestamp_s", "tracker_id", "x_m", "y_m", "z_m",
                "qw", "qx", "qy", "qz", "quality", "defect_tag"]
_EVENT_COLS = ["timestamp_s", "event_id", "label", "phase",
               "source", "confidence", "notes"]
```

**Reference — raw folder layout produced by `synth.generate_session` (the target shape):**

```
<session_id>/
  session.json  consent.json  device_config.json  notes.md  checksums.sha256
  streams/motion_right_wrist.csv  streams/motion_left_wrist.csv
  streams/motion_torso.csv        streams/motion_object.csv  streams/events.csv
  video/   (empty dir)
```

**Module map (what each file owns):**

| File | Owns | Pure? | pyxdf? | Task |
|------|------|-------|--------|------|
| `ingest/frame.py` | quaternion math + `apply_transform` | yes | no | 1–2 |
| `ingest/reader.py` | `XdfStream`, `IngestUnavailable`, `load_xdf_streams` | no (I/O) | yes | 3 |
| `ingest/mapping.py` | `parse_ingest_map`, `extract_motion` | yes | no | 4–5 |
| `tests/_xdf_writer.py` | synth→`.xdf` + sidecar builder (test infra) | n/a | yes | 6 |
| `ingest/session.py` | `validate_sidecar`, `compute_t0`, `build_motion_rows`, `build_event_rows`, `write_raw_folder` | yes | no | 7–10 |
| `ingest/session.py` | `ingest_xdf` orchestrator | no | yes | 11 |
| `cli.py` | `ingest` command | no | yes | 12 |
| docs + gate | — | — | — | 13 |

---

### Task 1: `frame.py` — quaternion primitives

**Files:**
- Create: `src/htdp/ingest/__init__.py` (empty)
- Create: `src/htdp/ingest/frame.py`
- Test: `tests/test_frame.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Quat = tuple[float, float, float, float]` (order `w, x, y, z`); `Vec3 = tuple[float, float, float]`
  - `IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)`
  - `quat_mul(a: Quat, b: Quat) -> Quat`
  - `rotate_vector(q: Quat, v: Vec3) -> Vec3`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_frame.py
import math

import pytest

from htdp.ingest.frame import IDENTITY, quat_mul, rotate_vector


def test_quat_mul_identity_left_and_right():
    q = (0.0, 0.0, 1.0, 0.0)
    assert quat_mul(IDENTITY, q) == pytest.approx(q)
    assert quat_mul(q, IDENTITY) == pytest.approx(q)


def test_rotate_vector_identity_is_noop():
    assert rotate_vector(IDENTITY, (1.0, 2.0, 3.0)) == pytest.approx((1.0, 2.0, 3.0))


def test_rotate_vector_90deg_about_z_maps_x_to_y():
    rot = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
    assert rotate_vector(rot, (1.0, 0.0, 0.0)) == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)


def test_rotate_vector_inverse_round_trips():
    rot = (math.cos(math.pi / 6), 0.0, math.sin(math.pi / 6), 0.0)  # 60° about y
    inv = (rot[0], -rot[1], -rot[2], -rot[3])
    v = (0.3, -0.7, 1.2)
    assert rotate_vector(inv, rotate_vector(rot, v)) == pytest.approx(v, abs=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_frame.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/ingest/__init__.py
```

(empty file)

```python
# src/htdp/ingest/frame.py
from __future__ import annotations

Quat = tuple[float, float, float, float]  # w, x, y, z
Vec3 = tuple[float, float, float]

IDENTITY: Quat = (1.0, 0.0, 0.0, 0.0)


def quat_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _conj(q: Quat) -> Quat:
    w, x, y, z = q
    return (w, -x, -y, -z)


def rotate_vector(q: Quat, v: Vec3) -> Vec3:
    p: Quat = (0.0, v[0], v[1], v[2])
    r = quat_mul(quat_mul(q, p), _conj(q))
    return (r[1], r[2], r[3])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_frame.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/__init__.py src/htdp/ingest/frame.py tests/test_frame.py
git commit -m "feat(ingest): quaternion primitives"
```

---

### Task 2: `frame.py` — `apply_transform`

**Files:**
- Modify: `src/htdp/ingest/frame.py` (append)
- Test: `tests/test_frame.py` (append)

**Interfaces:**
- Consumes: `quat_mul`, `rotate_vector`, `Quat`, `Vec3`, `IDENTITY` (Task 1).
- Produces: `apply_transform(rotation: Quat, pos: Vec3, quat: Quat) -> tuple[Vec3, Quat]` — rotates a position vector and composes orientation (`rotation ⊗ quat`) into the contract frame.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_frame.py`:

```python
def test_apply_transform_identity_is_noop():
    from htdp.ingest.frame import apply_transform

    pos, quat = apply_transform(IDENTITY, (1.0, 2.0, 3.0), (1.0, 0.0, 0.0, 0.0))
    assert pos == pytest.approx((1.0, 2.0, 3.0))
    assert quat == pytest.approx((1.0, 0.0, 0.0, 0.0))


def test_apply_transform_90deg_about_z():
    from htdp.ingest.frame import apply_transform

    rot = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))
    pos, quat = apply_transform(rot, (1.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
    assert pos == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert quat == pytest.approx(rot, abs=1e-9)  # rot ⊗ identity == rot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_frame.py -k apply_transform -v`
Expected: FAIL — `ImportError: cannot import name 'apply_transform'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/frame.py`:

```python
def apply_transform(rotation: Quat, pos: Vec3, quat: Quat) -> tuple[Vec3, Quat]:
    """Rotate a position vector and compose orientation into the contract frame."""
    return rotate_vector(rotation, pos), quat_mul(rotation, quat)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_frame.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/frame.py tests/test_frame.py
git commit -m "feat(ingest): apply_transform pos+orientation into contract frame"
```

---

### Task 3: `reader.py` — pyxdf parse with optional-dep guard

**Files:**
- Create: `src/htdp/ingest/reader.py`
- Modify: `pyproject.toml` (add `ingest` optional extra)
- Test: `tests/test_reader.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class IngestUnavailable(RuntimeError)`
  - `@dataclass XdfStream`: `name: str`, `type: str`, `channel_format: str`, `time_stamps: list[float]`, `time_series: list[list[float]] | list[str]`
  - `load_xdf_streams(path: Path) -> dict[str, XdfStream]` — keyed by stream name; string-format streams store `time_series` as `list[str]`, numeric as `list[list[float]]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reader.py
import sys
from pathlib import Path

import pytest

from htdp.ingest.reader import IngestUnavailable, XdfStream, load_xdf_streams


def test_ingest_unavailable_is_runtime_error():
    assert issubclass(IngestUnavailable, RuntimeError)


def test_xdf_stream_dataclass_fields():
    s = XdfStream(name="m", type="motion", channel_format="double64",
                  time_stamps=[0.0, 0.01], time_series=[[1.0], [2.0]])
    assert s.name == "m" and s.time_stamps[1] == 0.01


def test_missing_pyxdf_raises_ingest_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyxdf", None)  # forces ImportError on `import pyxdf`
    with pytest.raises(IngestUnavailable):
        load_xdf_streams(Path("nonexistent.xdf"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.ingest.reader'`

- [ ] **Step 3: Write minimal implementation**

Add to `pyproject.toml` under `[project.optional-dependencies]` (after the `replay` line):

```toml
ingest = ["pyxdf>=1.16"]
```

```python
# src/htdp/ingest/reader.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class IngestUnavailable(RuntimeError):
    """Raised when pyxdf is not installed."""


@dataclass
class XdfStream:
    name: str
    type: str
    channel_format: str
    time_stamps: list[float]
    time_series: list[list[float]] | list[str]


def load_xdf_streams(path: Path) -> dict[str, XdfStream]:
    try:
        import pyxdf  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestUnavailable("install with: uv sync --extra ingest") from exc

    streams, _ = pyxdf.load_xdf(str(path))
    out: dict[str, XdfStream] = {}
    for s in streams:
        info = s["info"]
        fmt = str(info["channel_format"][0])
        ts = [float(t) for t in s["time_stamps"]]
        series: list[list[float]] | list[str]
        if fmt == "string":
            series = [str(row[0]) for row in s["time_series"]]
        else:
            series = [[float(v) for v in row] for row in s["time_series"]]
        name = str(info["name"][0])
        out[name] = XdfStream(
            name=name, type=str(info["type"][0]), channel_format=fmt,
            time_stamps=ts, time_series=series,
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reader.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/htdp/ingest/reader.py tests/test_reader.py
git commit -m "feat(ingest): xdf reader with optional-dep guard"
```

---

### Task 4: `mapping.py` — `parse_ingest_map`

**Files:**
- Create: `src/htdp/ingest/mapping.py`
- Test: `tests/test_mapping.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (kept independent of `reader`).
- Produces:
  - `CONTRACT_TRACKERS: tuple[str, ...] = ("right_wrist", "left_wrist", "torso", "object")`
  - `_MOTION_CHANNEL_KEYS: tuple[str, ...] = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")`
  - `class MappingError(Exception)`
  - `@dataclass MotionStreamMap`: `tracker_id: str`, `channels: dict[str, int]`
  - `@dataclass IngestMap`: `motion: dict[str, MotionStreamMap]`, `events_stream: str`
  - `parse_ingest_map(raw: dict[str, object]) -> IngestMap`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mapping.py
import pytest

from htdp.ingest.mapping import MappingError, parse_ingest_map

_CHANNELS = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _valid_raw():
    return {
        "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CHANNELS)},
        "marker": {"role": "events"},
    }


def test_parse_resolves_motion_and_events():
    im = parse_ingest_map(_valid_raw())
    assert im.events_stream == "marker"
    assert im.motion["wrist"].tracker_id == "right_wrist"
    assert im.motion["wrist"].channels["quality"] == 7


def test_parse_unknown_tracker_raises():
    raw = _valid_raw()
    raw["wrist"]["tracker_id"] = "nose"
    with pytest.raises(MappingError, match="nose"):
        parse_ingest_map(raw)


def test_parse_missing_channel_raises():
    raw = _valid_raw()
    del raw["wrist"]["channels"]["quality"]
    with pytest.raises(MappingError, match="quality"):
        parse_ingest_map(raw)


def test_parse_unknown_role_raises():
    raw = _valid_raw()
    raw["wrist"]["role"] = "video"
    with pytest.raises(MappingError, match="video"):
        parse_ingest_map(raw)


def test_parse_requires_exactly_one_events_stream():
    raw = {"wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CHANNELS)}}
    with pytest.raises(MappingError, match="events"):
        parse_ingest_map(raw)


def test_parse_requires_at_least_one_motion_stream():
    with pytest.raises(MappingError, match="motion"):
        parse_ingest_map({"marker": {"role": "events"}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.ingest.mapping'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/ingest/mapping.py
from __future__ import annotations

from dataclasses import dataclass

CONTRACT_TRACKERS: tuple[str, ...] = ("right_wrist", "left_wrist", "torso", "object")
_MOTION_CHANNEL_KEYS: tuple[str, ...] = (
    "x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality",
)


class MappingError(Exception):
    """Raised when the ingest_map does not resolve against the contract or XDF."""


@dataclass
class MotionStreamMap:
    tracker_id: str
    channels: dict[str, int]


@dataclass
class IngestMap:
    motion: dict[str, MotionStreamMap]
    events_stream: str


def parse_ingest_map(raw: dict[str, object]) -> IngestMap:
    motion: dict[str, MotionStreamMap] = {}
    events_streams: list[str] = []
    for stream_name, entry in raw.items():
        if not isinstance(entry, dict):
            raise MappingError(f"ingest_map entry for '{stream_name}' must be an object")
        role = entry.get("role")
        if role == "events":
            events_streams.append(stream_name)
        elif role == "motion":
            tracker_id = entry.get("tracker_id")
            if tracker_id not in CONTRACT_TRACKERS:
                raise MappingError(
                    f"stream '{stream_name}' tracker_id '{tracker_id}' "
                    f"not in contract trackers {CONTRACT_TRACKERS}"
                )
            channels = entry.get("channels")
            if not isinstance(channels, dict):
                raise MappingError(f"stream '{stream_name}' missing 'channels' map")
            missing = [k for k in _MOTION_CHANNEL_KEYS if k not in channels]
            if missing:
                raise MappingError(
                    f"stream '{stream_name}' channels missing keys: {', '.join(missing)}"
                )
            motion[stream_name] = MotionStreamMap(
                tracker_id=str(tracker_id),
                channels={k: int(channels[k]) for k in _MOTION_CHANNEL_KEYS},
            )
        else:
            raise MappingError(f"stream '{stream_name}' has unknown role '{role}'")

    if len(events_streams) != 1:
        raise MappingError(
            f"ingest_map must declare exactly one 'events' stream, found {len(events_streams)}"
        )
    if not motion:
        raise MappingError("ingest_map must declare at least one 'motion' stream")
    return IngestMap(motion=motion, events_stream=events_streams[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mapping.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/mapping.py tests/test_mapping.py
git commit -m "feat(ingest): parse_ingest_map with contract validation"
```

---

### Task 5: `mapping.py` — `extract_motion`

**Files:**
- Modify: `src/htdp/ingest/mapping.py` (append)
- Test: `tests/test_mapping.py` (append)

**Interfaces:**
- Consumes: `XdfStream` from `htdp.ingest.reader` (Task 3); `MotionStreamMap`, `MappingError`, `_MOTION_CHANNEL_KEYS` (Task 4).
- Produces: `extract_motion(stream: XdfStream, m: MotionStreamMap) -> list[dict[str, object]]` — one dict per sample with keys `raw_ts, tracker_id, x_m, y_m, z_m, qw, qx, qy, qz, quality`. Raises `MappingError` on string-format motion stream or out-of-range channel index.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mapping.py`:

```python
from htdp.ingest.mapping import extract_motion  # noqa: E402
from htdp.ingest.reader import XdfStream  # noqa: E402


def _motion_stream():
    return XdfStream(
        name="wrist", type="motion", channel_format="double64",
        time_stamps=[10.0, 10.01],
        time_series=[[0.1, 0.2, 0.9, 1.0, 0.0, 0.0, 0.0, 1.0],
                     [0.11, 0.21, 0.91, 1.0, 0.0, 0.0, 0.0, 1.0]],
    )


def test_extract_motion_builds_rows():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    rows = extract_motion(_motion_stream(), m)
    assert len(rows) == 2
    assert rows[0]["raw_ts"] == 10.0
    assert rows[0]["tracker_id"] == "right_wrist"
    assert rows[1]["x_m"] == 0.11
    assert rows[0]["quality"] == 1.0


def test_extract_motion_rejects_string_stream():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    bad = XdfStream(name="wrist", type="motion", channel_format="string",
                    time_stamps=[0.0], time_series=["x"])
    with pytest.raises(MappingError, match="numeric"):
        extract_motion(bad, m)


def test_extract_motion_channel_index_out_of_range_raises():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    bad = _motion_stream()
    bad.time_series = [[0.1, 0.2]]  # too few channels
    with pytest.raises(MappingError, match="out of range"):
        extract_motion(bad, m)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mapping.py -k extract_motion -v`
Expected: FAIL — `ImportError: cannot import name 'extract_motion'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/mapping.py` (add the import at top):

```python
from htdp.ingest.reader import XdfStream
```

```python
def extract_motion(stream: XdfStream, m: MotionStreamMap) -> list[dict[str, object]]:
    if stream.channel_format == "string":
        raise MappingError(f"motion stream '{stream.name}' must be numeric, got string format")
    rows: list[dict[str, object]] = []
    for ts, sample in zip(stream.time_stamps, stream.time_series):
        assert isinstance(sample, list)
        row: dict[str, object] = {"raw_ts": float(ts), "tracker_id": m.tracker_id}
        for key in _MOTION_CHANNEL_KEYS:
            idx = m.channels[key]
            if idx >= len(sample):
                raise MappingError(
                    f"stream '{stream.name}' channel '{key}' index {idx} "
                    f"out of range (sample has {len(sample)} channels)"
                )
            row[key] = float(sample[idx])
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mapping.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/mapping.py tests/test_mapping.py
git commit -m "feat(ingest): extract_motion channel mapping"
```

---

### Task 6: `tests/_xdf_writer.py` — round-trip test infrastructure

**Files:**
- Create: `tests/_xdf_writer.py`
- Test: `tests/test_xdf_writer.py`

**Interfaces:**
- Consumes: `load_xdf_streams` (Task 3) for the verification test only.
- Produces (test-only infra, never imported by `src/`):
  - `CLOCK_BASE: float = 1000.0` — fixed absolute-clock offset added to every timestamp, so `ingest`'s rebase-to-`t0` is exercised (recovered `t0` must equal `CLOCK_BASE`).
  - `EVENT_PAYLOAD_KEYS: tuple[str, ...] = ("event_id", "label", "phase", "confidence", "notes")` — marker-string JSON field set (shared convention with `build_event_rows`, Task 9).
  - `write_xdf(raw_dir: Path, xdf_path: Path) -> None`
  - `build_sidecar(raw_dir: Path) -> dict[str, object]`

**Minimal XDF binary format** (all `pyxdf` needs):
- Magic ASCII `XDF:`.
- Chunk = `num_len_bytes` (1 byte `1|4|8`) + `length` (LE uint, counts the 2-byte tag + content) + `tag` (uint16 LE) + content.
- Tag 1 FileHeader: UTF-8 XML `<?xml version="1.0"?><info><version>1.0</version></info>`.
- Tag 2 StreamHeader: `stream_id` (uint32 LE) + UTF-8 XML with `name/type/channel_count/nominal_srate/channel_format`.
- Tag 3 Samples: `stream_id` (uint32 LE) + `\x04` + uint32 LE `num_samples`, then per sample `\x08` + float64 LE timestamp + channels (`double64`→float64 LE each; `string`→`\x04`+uint32 LE len+UTF-8 bytes).
- Tag 6 StreamFooter: `stream_id` (uint32 LE) + UTF-8 XML `first_timestamp/last_timestamp/sample_count`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_xdf_writer.py
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.reader import load_xdf_streams  # noqa: E402
from tests._xdf_writer import CLOCK_BASE, build_sidecar, write_xdf  # noqa: E402


def test_written_xdf_loads_with_expected_streams(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "session.xdf"
    write_xdf(raw, xdf)
    streams = load_xdf_streams(xdf)
    assert {"right_wrist", "left_wrist", "torso", "object", "events"} <= set(streams)
    assert streams["right_wrist"].channel_format == "double64"
    assert streams["events"].channel_format == "string"
    assert streams["right_wrist"].time_stamps[0] == pytest.approx(CLOCK_BASE, abs=1e-6)


def test_sidecar_maps_every_tracker_and_events(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    roles = {n: e["role"] for n, e in build_sidecar(raw)["ingest_map"].items()}
    assert roles == {
        "right_wrist": "motion", "left_wrist": "motion",
        "torso": "motion", "object": "motion", "events": "events",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xdf_writer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests._xdf_writer'` (or SKIP if `pyxdf` absent — `uv sync --extra ingest`)

- [ ] **Step 3: Write minimal implementation**

```python
# tests/_xdf_writer.py
"""Throwaway test infra: synth raw session -> .xdf, for round-trip tests.

NOT shipped in the package public surface; lives under tests/ only.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

CLOCK_BASE: float = 1000.0
EVENT_PAYLOAD_KEYS: tuple[str, ...] = ("event_id", "label", "phase", "confidence", "notes")

_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")
_MOTION_CHANNEL_KEYS = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


def _chunk(tag: int, content: bytes) -> bytes:
    body = struct.pack("<H", tag) + content
    return b"\x04" + struct.pack("<I", len(body)) + body


def _stream_header(stream_id: int, name: str, fmt: str, n_chan: int, srate: float) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<name>{name}</name><type>{name}</type>"
        f"<channel_count>{n_chan}</channel_count>"
        f"<nominal_srate>{srate}</nominal_srate>"
        f"<channel_format>{fmt}</channel_format></info>"
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
    for ts, s in zip(stamps, rows):
        b = s.encode("utf-8")
        out += b"\x08" + struct.pack("<d", ts)
        out += b"\x04" + struct.pack("<I", len(b)) + b
    return _chunk(3, out)


def _stream_footer(stream_id: int, stamps: list[float]) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<first_timestamp>{stamps[0]}</first_timestamp>"
        f"<last_timestamp>{stamps[-1]}</last_timestamp>"
        f"<sample_count>{len(stamps)}</sample_count></info>"
    )
    return _chunk(6, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def write_xdf(raw_dir: Path, xdf_path: Path) -> None:
    blob = b"XDF:"
    blob += _chunk(1, b'<?xml version="1.0"?><info><version>1.0</version></info>')

    stream_id = 1
    for tracker in _TRACKERS:
        rows_csv = _read_csv(raw_dir / "streams" / f"motion_{tracker}.csv")
        stamps = [float(r["timestamp_s"]) + CLOCK_BASE for r in rows_csv]
        values = [[float(r[k]) for k in _MOTION_CHANNEL_KEYS] for r in rows_csv]
        blob += _stream_header(stream_id, tracker, "double64", len(_MOTION_CHANNEL_KEYS), 100.0)
        blob += _samples_numeric(stream_id, stamps, values)
        blob += _stream_footer(stream_id, stamps)
        stream_id += 1

    ev_csv = _read_csv(raw_dir / "streams" / "events.csv")
    ev_stamps = [float(r["timestamp_s"]) + CLOCK_BASE for r in ev_csv]
    ev_payloads = [
        json.dumps(
            {
                "event_id": int(r["event_id"]), "label": r["label"], "phase": r["phase"],
                "confidence": float(r["confidence"]), "notes": r["notes"],
            },
            sort_keys=True,
        )
        for r in ev_csv
    ]
    blob += _stream_header(stream_id, "events", "string", 1, 0.0)
    blob += _samples_string(stream_id, ev_stamps, ev_payloads)
    blob += _stream_footer(stream_id, ev_stamps)

    xdf_path.write_bytes(blob)


def build_sidecar(raw_dir: Path) -> dict[str, object]:
    session = json.loads((raw_dir / "session.json").read_text(encoding="utf-8"))
    consent = json.loads((raw_dir / "consent.json").read_text(encoding="utf-8"))
    device_config = json.loads((raw_dir / "device_config.json").read_text(encoding="utf-8"))
    channels = {k: i for i, k in enumerate(_MOTION_CHANNEL_KEYS)}
    ingest_map: dict[str, object] = {
        t: {"role": "motion", "tracker_id": t, "channels": dict(channels)} for t in _TRACKERS
    }
    ingest_map["events"] = {"role": "events"}
    return {
        "session": session, "consent": consent,
        "device_config": device_config, "ingest_map": ingest_map,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xdf_writer.py -v`
Expected: PASS (2 passed) — or SKIP without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add tests/_xdf_writer.py tests/test_xdf_writer.py
git commit -m "test(ingest): minimal xdf writer + sidecar builder"
```

---

### Task 7: `session.py` — `validate_sidecar` (pure, no pyxdf)

**Files:**
- Create: `src/htdp/ingest/session.py`
- Test: `tests/test_session_validate.py`

**Interfaces:**
- Consumes: `IDENTITY`, `Quat` (Task 1); `IngestMap`, `parse_ingest_map` (Task 4); schemas `Session`/`Consent`/`DeviceConfig`.
- Produces:
  - `@dataclass ParsedSidecar`: `session: Session`, `consent: Consent`, `device_config: DeviceConfig`, `ingest_map: IngestMap`, `rotation: Quat`
  - `validate_sidecar(sidecar: dict[str, object]) -> ParsedSidecar` — validates the three schema blocks (raises `pydantic.ValidationError`), parses `ingest_map` (raises `MappingError`), reads optional `frame_transform.rotation` (default `IDENTITY`).
  - Module constants `_MOTION_COLS`, `_EVENT_COLS`, `_TRACKER_ORDER` (used by later tasks).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_validate.py
import pytest
from pydantic import ValidationError

from htdp.ingest.frame import IDENTITY
from htdp.ingest.mapping import MappingError
from htdp.ingest.session import validate_sidecar

_CH = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _sidecar():
    return {
        "session": {
            "session_id": "real-0001", "participant_id": "p1", "protocol_id": "reach-grasp-place",
            "consent_form_version": "v1", "device_config_id": "vive-1", "start_time_s": 0.0,
        },
        "consent": {"consent_form_version": "v1"},
        "device_config": {"device_config_id": "vive-1"},
        "ingest_map": {
            "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CH)},
            "marker": {"role": "events"},
        },
    }


def test_validate_sidecar_ok_defaults_to_identity_rotation():
    parsed = validate_sidecar(_sidecar())
    assert parsed.session.session_id == "real-0001"
    assert parsed.ingest_map.events_stream == "marker"
    assert parsed.rotation == IDENTITY


def test_validate_sidecar_reads_frame_transform():
    sc = _sidecar()
    sc["frame_transform"] = {"rotation": [0.0, 1.0, 0.0, 0.0]}
    assert validate_sidecar(sc).rotation == (0.0, 1.0, 0.0, 0.0)


def test_validate_sidecar_bad_session_raises_validation_error():
    sc = _sidecar()
    del sc["session"]["session_id"]
    with pytest.raises(ValidationError):
        validate_sidecar(sc)


def test_validate_sidecar_bad_map_raises_mapping_error():
    sc = _sidecar()
    sc["ingest_map"]["wrist"]["tracker_id"] = "nose"
    with pytest.raises(MappingError):
        validate_sidecar(sc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.ingest.session'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/ingest/session.py
from __future__ import annotations

from dataclasses import dataclass

from htdp.ingest.frame import IDENTITY, Quat
from htdp.ingest.mapping import IngestMap, parse_ingest_map
from htdp.schemas.models import Consent, DeviceConfig, Session

_MOTION_COLS = [
    "timestamp_s", "tracker_id", "x_m", "y_m", "z_m",
    "qw", "qx", "qy", "qz", "quality", "defect_tag",
]
_EVENT_COLS = [
    "timestamp_s", "event_id", "label", "phase", "source", "confidence", "notes",
]
_TRACKER_ORDER = ("right_wrist", "left_wrist", "torso", "object")


@dataclass
class ParsedSidecar:
    session: Session
    consent: Consent
    device_config: DeviceConfig
    ingest_map: IngestMap
    rotation: Quat


def _rotation_from_sidecar(sidecar: dict[str, object]) -> Quat:
    ft = sidecar.get("frame_transform")
    if not isinstance(ft, dict):
        return IDENTITY
    rot = ft.get("rotation")
    if rot is None:
        return IDENTITY
    w, x, y, z = (float(v) for v in rot)
    return (w, x, y, z)


def validate_sidecar(sidecar: dict[str, object]) -> ParsedSidecar:
    """Validate schema blocks + ingest_map before any XDF read or write (fail fast)."""
    session = Session.model_validate(sidecar["session"])
    consent = Consent.model_validate(sidecar["consent"])
    device_config = DeviceConfig.model_validate(sidecar["device_config"])
    ingest_map = parse_ingest_map(sidecar["ingest_map"])  # type: ignore[arg-type]
    return ParsedSidecar(
        session=session, consent=consent, device_config=device_config,
        ingest_map=ingest_map, rotation=_rotation_from_sidecar(sidecar),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_validate.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_validate.py
git commit -m "feat(ingest): validate_sidecar fail-fast schema+map check"
```

---

### Task 8: `session.py` — `compute_t0` + `build_motion_rows` (pure, no pyxdf)

**Files:**
- Modify: `src/htdp/ingest/session.py` (append)
- Test: `tests/test_session_motion.py`

**Interfaces:**
- Consumes: `apply_transform`, `Quat` (Tasks 1–2); `_MOTION_COLS` (Task 7).
- Produces:
  - `compute_t0(motion_raw: dict[str, list[dict[str, object]]]) -> float` — min `raw_ts` across all motion samples; raises `ValueError` if empty.
  - `build_motion_rows(motion_raw, rotation: Quat, t0: float) -> dict[str, list[dict[str, object]]]` — applies frame transform, rebases `timestamp_s = raw_ts - t0`, sets `defect_tag=""`; output dict values are rows keyed by `_MOTION_COLS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_motion.py
import pytest

from htdp.ingest.frame import IDENTITY
from htdp.ingest.session import build_motion_rows, compute_t0


def _raw():
    return {
        "right_wrist": [
            {"raw_ts": 1000.0, "tracker_id": "right_wrist", "x_m": 1.0, "y_m": 0.0, "z_m": 0.0,
             "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "quality": 1.0},
            {"raw_ts": 1000.01, "tracker_id": "right_wrist", "x_m": 1.0, "y_m": 0.0, "z_m": 0.0,
             "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "quality": 0.5},
        ],
        "object": [
            {"raw_ts": 1000.05, "tracker_id": "object", "x_m": 0.0, "y_m": 0.0, "z_m": 0.0,
             "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "quality": 1.0},
        ],
    }


def test_compute_t0_is_global_min():
    assert compute_t0(_raw()) == 1000.0


def test_compute_t0_empty_raises():
    with pytest.raises(ValueError):
        compute_t0({})


def test_build_motion_rows_rebases_and_tags():
    out = build_motion_rows(_raw(), IDENTITY, 1000.0)
    rw = out["right_wrist"]
    assert rw[0]["timestamp_s"] == pytest.approx(0.0, abs=1e-9)
    assert rw[1]["timestamp_s"] == pytest.approx(0.01, abs=1e-9)
    assert rw[0]["defect_tag"] == ""
    assert rw[1]["quality"] == 0.5
    assert out["object"][0]["timestamp_s"] == pytest.approx(0.05, abs=1e-9)


def test_build_motion_rows_applies_rotation():
    rot = (0.7071067811865476, 0.0, 0.0, 0.7071067811865476)  # 90° about z
    out = build_motion_rows(_raw(), rot, 1000.0)
    row = out["right_wrist"][0]
    assert row["x_m"] == pytest.approx(0.0, abs=1e-9)
    assert row["y_m"] == pytest.approx(1.0, abs=1e-9)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_motion.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_motion_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/session.py` (add `apply_transform` to the frame import):

```python
from htdp.ingest.frame import IDENTITY, Quat, apply_transform
```

```python
def compute_t0(motion_raw: dict[str, list[dict[str, object]]]) -> float:
    all_ts = [float(r["raw_ts"]) for rows in motion_raw.values() for r in rows]
    if not all_ts:
        raise ValueError("no motion samples found")
    return min(all_ts)


def build_motion_rows(
    motion_raw: dict[str, list[dict[str, object]]],
    rotation: Quat,
    t0: float,
) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    for tracker, rows in motion_raw.items():
        built: list[dict[str, object]] = []
        for r in rows:
            pos = (float(r["x_m"]), float(r["y_m"]), float(r["z_m"]))
            quat = (float(r["qw"]), float(r["qx"]), float(r["qy"]), float(r["qz"]))
            (px, py, pz), (qw, qx, qy, qz) = apply_transform(rotation, pos, quat)
            built.append({
                "timestamp_s": float(r["raw_ts"]) - t0, "tracker_id": tracker,
                "x_m": px, "y_m": py, "z_m": pz,
                "qw": qw, "qx": qx, "qy": qy, "qz": qz,
                "quality": float(r["quality"]), "defect_tag": "",
            })
        out[tracker] = built
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_motion.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_motion.py
git commit -m "feat(ingest): compute_t0 + build_motion_rows (frame + rebase)"
```

---

### Task 9: `session.py` — `build_event_rows` (pure, no pyxdf)

**Files:**
- Modify: `src/htdp/ingest/session.py` (append)
- Test: `tests/test_session_events.py`

**Interfaces:**
- Consumes: `_EVENT_COLS` (Task 7). JSON payload convention from `EVENT_PAYLOAD_KEYS` (Task 6).
- Produces: `build_event_rows(stamps: list[float], payloads: list[str], t0: float) -> list[dict[str, object]]` — decodes each marker JSON string, rebases `timestamp_s = ts - t0`, sets `source="real"`, columns per `_EVENT_COLS`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_events.py
import json

import pytest

from htdp.ingest.session import build_event_rows


def _payloads():
    return [
        json.dumps({"event_id": 0, "label": "start", "phase": "approach",
                    "confidence": 1.0, "notes": ""}, sort_keys=True),
        json.dumps({"event_id": 1, "label": "grasp", "phase": "grasp",
                    "confidence": 0.9, "notes": "x"}, sort_keys=True),
    ]


def test_build_event_rows_decodes_and_rebases():
    rows = build_event_rows([1000.0, 1001.0], _payloads(), 1000.0)
    assert rows[0]["timestamp_s"] == pytest.approx(0.0)
    assert rows[1]["timestamp_s"] == pytest.approx(1.0)
    assert rows[0]["label"] == "start"
    assert rows[1]["event_id"] == 1
    assert rows[1]["confidence"] == 0.9
    assert rows[1]["notes"] == "x"


def test_build_event_rows_sets_source_real():
    rows = build_event_rows([1000.0], _payloads()[:1], 1000.0)
    assert rows[0]["source"] == "real"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_events.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_event_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/session.py` (add `import json` at top):

```python
def build_event_rows(
    stamps: list[float],
    payloads: list[str],
    t0: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ts, payload in zip(stamps, payloads):
        p = json.loads(payload)
        rows.append({
            "timestamp_s": float(ts) - t0,
            "event_id": int(p["event_id"]),
            "label": str(p["label"]),
            "phase": str(p["phase"]),
            "source": "real",
            "confidence": float(p["confidence"]),
            "notes": str(p["notes"]),
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_events.py
git commit -m "feat(ingest): build_event_rows decode marker payloads"
```

---

### Task 10: `session.py` — `write_raw_folder` (pure fs, no pyxdf)

**Files:**
- Modify: `src/htdp/ingest/session.py` (append)
- Test: `tests/test_session_write.py`

**Interfaces:**
- Consumes: `_MOTION_COLS`, `_EVENT_COLS`, `_TRACKER_ORDER` (Task 7); schemas `Session`/`Consent`/`DeviceConfig`/`CoordinateFrame`/`StreamRef`; `io.canonical.dump_json`/`write_csv`; `io.checksums.write_checksums`. Output must pass existing `validate.validate_session`.
- Produces:
  - `write_raw_folder(out_dir: Path, *, session: Session, consent: Consent, device_config_id: str, motion_out: dict[str, list[dict[str, object]]], event_rows: list[dict[str, object]], source_xdf_name: str, force: bool = False) -> Path`
  - Writes `streams/motion_<tracker>.csv` (in `_TRACKER_ORDER`), `streams/events.csv`, `session.json`, `consent.json`, `device_config.json` (frame = `CoordinateFrame()`, streams rebuilt), `notes.md` (records `source_xdf_name` + tool version), empty `video/`, then `write_checksums`. Raises `FileExistsError` when target exists and `force` is False. **No partial writes** (caller passes fully-built data).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_write.py
from pathlib import Path

import pytest

from htdp.ingest.session import write_raw_folder
from htdp.schemas.models import Consent, Session
from htdp.validate import validate_session


def _session():
    return Session(
        session_id="real-0001", participant_id="p1", protocol_id="reach-grasp-place",
        consent_form_version="v1", device_config_id="vive-1", start_time_s=1000.0,
    )


def _motion_out():
    return {
        "right_wrist": [
            {"timestamp_s": 0.0, "tracker_id": "right_wrist", "x_m": 0.1, "y_m": 0.2, "z_m": 0.9,
             "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "quality": 1.0, "defect_tag": ""},
        ],
    }


def _events():
    return [{"timestamp_s": 0.0, "event_id": 0, "label": "start", "phase": "approach",
             "source": "real", "confidence": 1.0, "notes": ""}]


def test_write_raw_folder_passes_validate(tmp_path: Path):
    out = write_raw_folder(
        tmp_path / "real-0001", session=_session(), consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1", motion_out=_motion_out(), event_rows=_events(),
        source_xdf_name="rec.xdf",
    )
    assert validate_session(out) == []
    assert (out / "video").is_dir()
    assert "rec.xdf" in (out / "notes.md").read_text(encoding="utf-8")


def test_write_raw_folder_refuses_overwrite_without_force(tmp_path: Path):
    kw = dict(session=_session(), consent=Consent(consent_form_version="v1"),
              device_config_id="vive-1", motion_out=_motion_out(), event_rows=_events(),
              source_xdf_name="rec.xdf")
    write_raw_folder(tmp_path / "x", **kw)
    with pytest.raises(FileExistsError):
        write_raw_folder(tmp_path / "x", **kw)
    write_raw_folder(tmp_path / "x", force=True, **kw)  # ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_write.py -v`
Expected: FAIL — `ImportError: cannot import name 'write_raw_folder'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/session.py` (add imports at top):

```python
import shutil
from importlib.metadata import version
from pathlib import Path

from htdp.io.canonical import dump_json, write_csv
from htdp.io.checksums import write_checksums
from htdp.schemas.models import CoordinateFrame, StreamRef
```

```python
def write_raw_folder(
    out_dir: Path,
    *,
    session: Session,
    consent: Consent,
    device_config_id: str,
    motion_out: dict[str, list[dict[str, object]]],
    event_rows: list[dict[str, object]],
    source_xdf_name: str,
    force: bool = False,
) -> Path:
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"raw session already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    (out_dir / "streams").mkdir(parents=True)
    (out_dir / "video").mkdir()

    stream_refs: list[StreamRef] = []
    for tracker in _TRACKER_ORDER:
        if tracker not in motion_out:
            continue
        rel = f"streams/motion_{tracker}.csv"
        write_csv(motion_out[tracker], _MOTION_COLS, out_dir / rel)
        stream_refs.append(StreamRef(name=tracker, path=rel, fmt="csv", role="motion"))
    write_csv(event_rows, _EVENT_COLS, out_dir / "streams/events.csv")
    stream_refs.append(
        StreamRef(name="events", path="streams/events.csv", fmt="csv", role="events")
    )

    device_out = DeviceConfig(
        device_config_id=device_config_id, frame=CoordinateFrame(), streams=stream_refs,
    )
    dump_json(session, out_dir / "session.json")
    dump_json(consent, out_dir / "consent.json")
    dump_json(device_out, out_dir / "device_config.json")
    (out_dir / "notes.md").write_text(
        f"# Ingested session {session.session_id}\n"
        f"Source: {source_xdf_name}. Ingested with htdp {version('htdp')}.\n",
        encoding="utf-8", newline="\n",
    )
    write_checksums(out_dir)
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_write.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_write.py
git commit -m "feat(ingest): write_raw_folder canonical raw output"
```

---

### Task 11: `session.py` — `ingest_xdf` orchestrator + round-trip

**Files:**
- Modify: `src/htdp/ingest/session.py` (append)
- Test: `tests/test_ingest_roundtrip.py`

**Interfaces:**
- Consumes: every `session.py` helper (Tasks 7–10); `load_xdf_streams` (Task 3); `extract_motion` (Task 5).
- Produces: `ingest_xdf(xdf_path: Path, sidecar_path: Path, out_dir: Path, force: bool = False) -> Path` — thin orchestrator: load+validate sidecar → load xdf → extract motion per map → `compute_t0` → `build_motion_rows` → `build_event_rows` → `write_raw_folder` (with `session.start_time_s = t0`). Raises `KeyError` if a mapped stream is absent from the XDF.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_roundtrip.py
import json
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session
from htdp.validate import validate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import CLOCK_BASE, build_sidecar, write_xdf  # noqa: E402

_MOTION = ("right_wrist", "left_wrist", "torso", "object")


def _strip_defect(csv_text: str) -> list[tuple[str, ...]]:
    lines = csv_text.splitlines()
    header = lines[0].split(",")
    keep = [i for i, c in enumerate(header) if c != "defect_tag"]
    return [tuple(line.split(",")[i] for i in keep) for line in lines]


def _run(tmp_path: Path) -> tuple[Path, Path]:
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    write_xdf(raw, xdf)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(json.dumps(build_sidecar(raw)), encoding="utf-8")
    return raw, ingest_xdf(xdf, sidecar, tmp_path / "ingested")


def test_ingested_session_validates(tmp_path: Path):
    _raw, out = _run(tmp_path)
    assert validate_session(out) == []


def test_geometry_matches_ignoring_defect_tag(tmp_path: Path):
    raw, out = _run(tmp_path)
    for t in _MOTION:
        orig = _strip_defect((raw / "streams" / f"motion_{t}.csv").read_text(encoding="utf-8"))
        got = _strip_defect((out / "streams" / f"motion_{t}.csv").read_text(encoding="utf-8"))
        assert got == orig, t


def test_start_time_records_absolute_t0(tmp_path: Path):
    _raw, out = _run(tmp_path)
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["start_time_s"] == pytest.approx(CLOCK_BASE, abs=1e-6)


def test_events_source_is_real(tmp_path: Path):
    _raw, out = _run(tmp_path)
    events = (out / "streams" / "events.csv").read_text(encoding="utf-8")
    assert "real" in events and "synthetic" not in events
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_roundtrip.py -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_xdf'` (or SKIP without `pyxdf`)

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/session.py` (add imports at top):

```python
from htdp.ingest.mapping import extract_motion
from htdp.ingest.reader import load_xdf_streams
```

```python
def ingest_xdf(
    xdf_path: Path,
    sidecar_path: Path,
    out_dir: Path,
    force: bool = False,
) -> Path:
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    parsed = validate_sidecar(sidecar)  # fail fast before reading the XDF

    streams = load_xdf_streams(xdf_path)

    motion_raw: dict[str, list[dict[str, object]]] = {}
    for stream_name, m in parsed.ingest_map.motion.items():
        if stream_name not in streams:
            raise KeyError(f"ingest_map stream '{stream_name}' not found in XDF")
        motion_raw[m.tracker_id] = extract_motion(streams[stream_name], m)

    t0 = compute_t0(motion_raw)
    motion_out = build_motion_rows(motion_raw, parsed.rotation, t0)

    ev = streams[parsed.ingest_map.events_stream]
    payloads = [s if isinstance(s, str) else "" for s in ev.time_series]
    event_rows = build_event_rows(ev.time_stamps, payloads, t0)

    session = parsed.session.model_copy(update={"start_time_s": t0})
    return write_raw_folder(
        out_dir, session=session, consent=parsed.consent,
        device_config_id=parsed.device_config.device_config_id,
        motion_out=motion_out, event_rows=event_rows,
        source_xdf_name=xdf_path.name, force=force,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_roundtrip.py -v`
Expected: PASS (4 passed) — or SKIP without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_ingest_roundtrip.py
git commit -m "feat(ingest): ingest_xdf orchestrator with round-trip test"
```

---

### Task 12: CLI `ingest` command

**Files:**
- Modify: `src/htdp/cli.py` (add command after `synth`)
- Test: `tests/test_cli_shell.py` (append; reuse the file's existing `CliRunner`/`app` pattern)

**Interfaces:**
- Consumes: `ingest_xdf` (Task 11); `IngestUnavailable` (Task 3); `MappingError` (Task 4).
- Produces: `htdp ingest <file.xdf> <ingest.json> --out <dir> [--force]`. Exits `1` on `IngestUnavailable | MappingError | ValidationError | FileExistsError | KeyError`, printing `error: ...` to stderr.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_shell.py`:

```python
def test_ingest_unavailable_exits_1(tmp_path, monkeypatch):
    import sys

    from typer.testing import CliRunner

    from htdp.cli import app

    (tmp_path / "s.xdf").write_bytes(b"XDF:")
    sc = tmp_path / "ingest.json"
    sc.write_text(
        '{"session":{"session_id":"r","participant_id":"p","protocol_id":"reach-grasp-place",'
        '"consent_form_version":"v1","device_config_id":"d","start_time_s":0.0},'
        '"consent":{"consent_form_version":"v1"},"device_config":{"device_config_id":"d"},'
        '"ingest_map":{"w":{"role":"motion","tracker_id":"right_wrist","channels":'
        '{"x_m":0,"y_m":1,"z_m":2,"qw":3,"qx":4,"qy":5,"qz":6,"quality":7}},'
        '"m":{"role":"events"}}}',
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "pyxdf", None)  # force IngestUnavailable
    result = CliRunner().invoke(
        app, ["ingest", str(tmp_path / "s.xdf"), str(sc), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code == 1
    assert "error:" in result.output


def test_ingest_roundtrip_cli(tmp_path):
    import json

    import pytest as _pytest

    _pytest.importorskip("pyxdf")
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session
    from tests._xdf_writer import build_sidecar, write_xdf

    raw = generate_session(tmp_path / "raw", seed=1)
    write_xdf(raw, tmp_path / "s.xdf")
    sc = tmp_path / "ingest.json"
    sc.write_text(json.dumps(build_sidecar(raw)), encoding="utf-8")
    out = tmp_path / "ingested"
    result = CliRunner().invoke(
        app, ["ingest", str(tmp_path / "s.xdf"), str(sc), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "session.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shell.py -k ingest -v`
Expected: FAIL — no command `ingest` (usage error / exit 2)

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `synth` command:

```python
@app.command()
def ingest(
    xdf_file: Path,
    sidecar: Path,
    out: Path = typer.Option(..., "--out"),
    force: bool = False,
) -> None:
    """Ingest an LSL .xdf recording into a raw session folder."""
    from pydantic import ValidationError

    from htdp.ingest.mapping import MappingError
    from htdp.ingest.reader import IngestUnavailable
    from htdp.ingest.session import ingest_xdf

    try:
        d = ingest_xdf(xdf_file, sidecar, out, force=force)
    except (IngestUnavailable, MappingError, ValidationError, FileExistsError, KeyError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_shell.py -k ingest -v`
Expected: PASS (2 passed; round-trip case SKIPs without `pyxdf`)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shell.py
git commit -m "feat(ingest): add htdp ingest CLI command"
```

---

### Task 13: Docs, quality-gate typecheck, full suite

**Files:**
- Modify: `AGENTS.md` (typecheck targets ~line 18; architecture + usage)
- Modify: `STATUS.md` (typecheck targets ~line 68)
- Modify: `docs/ROADMAP.md:29` (mark XDF ingest in progress)
- Modify: `docs/DATA_CONTRACT.md` (note `source` may be `real`; new `htdp ingest` step + `ingest.json` sidecar shape incl optional `frame_transform`)
- Modify: `README.md` (currently 1 line — add `ingest` usage)

**Interfaces:** none.

- [ ] **Step 1: Add `src/htdp/ingest` to the mypy gate**

In `AGENTS.md` change the Typecheck line to:

```
Typecheck: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest`
```

Make the identical edit to the `mypy` line in `STATUS.md` (~line 68).

- [ ] **Step 2: Run the typecheck to verify ingest is clean**

Run: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest`
Expected: `Success: no issues found`
(If issues appear, fix annotations in the offending `ingest` module before continuing.)

- [ ] **Step 3: Update ROADMAP, DATA_CONTRACT, AGENTS, README**

`docs/ROADMAP.md` line 29 — mark progress:

```
- Real hardware: VIVE tracker capture, LSL streaming, XDF ingest (`htdp ingest`: XDF → raw representation) — **in progress (XDF adapter landed)**
```

`docs/DATA_CONTRACT.md` — add: `source` may be `"real"` for ingested captures (no schema column change); document the pre-raw `htdp ingest` step and the `ingest.json` sidecar (keys `session`, `consent`, `device_config`, `ingest_map`, optional `frame_transform: {"rotation": [w,x,y,z]}` — consumed by ingest, **not persisted** into `device_config.json`).

`AGENTS.md` — under "Architecture summary" note the optional pre-raw stage `ingest (xdf → raw/, optional)`; in usage add `htdp ingest <file.xdf> <ingest.json> --out data/raw` and the extra `uv sync --extra ingest`.

`README.md` — replace the single line with a minimal usage block listing `ingest` alongside the existing pipeline commands.

- [ ] **Step 4: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest
```
Expected: ruff clean; pytest all pass (`pyxdf`-gated tests SKIP only if the extra is not installed — run `uv sync --extra ingest` first to exercise the round-trip); mypy `Success`.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md STATUS.md docs/ROADMAP.md docs/DATA_CONTRACT.md README.md
git commit -m "docs(ingest): document htdp ingest, sidecar, and source=real"
```

---

## Self-Review

**Spec coverage** (`2026-06-20-xdf-ingest-adapter-design.md`):
- `reader.py` + `IngestUnavailable` → Task 3. ✓
- `mapping.py` + unmapped/missing/unknown-tracker errors → Tasks 4–5. ✓
- `frame.py` identity default, pure, isolated → Tasks 1–2. ✓
- `session.py` rebase t0, motion+event rows, `source="real"`, `defect_tag=""`, write via `io` → Tasks 7–11 (decomposed into pure helpers + thin orchestrator). ✓
- CLI `ingest` with optional-dep guard → Task 12. ✓
- Sidecar validated against existing schemas before writing → Task 7 (`validate_sidecar`, called first in Task 11 orchestrator). ✓
- `tests/_xdf_writer.py` round-trip infra → Task 6. ✓
- Tests: round-trip, frame unit, mapping errors, validate-passes → Tasks 1–2 / 4–5 / 6 / 10–11. ✓
- `pyxdf` optional extra → Task 3. ✓
- Docs (`source=real`, ROADMAP, README/AGENTS, no schema re-export) → Task 13. ✓
- Error handling: missing pyxdf, bad sidecar, missing stream/channel, unknown tracker, no partial writes → Tasks 3/5/7/10/11. ✓

**Modularity check:** 13 tasks, one named unit each, one commit each. Tasks 1–2, 4–5, 7–10 (8 of 13) are **pure and unit-tested without `pyxdf`**. Only Tasks 6, 11, 12 require the optional dep (and gate it with `importorskip`). Any task is independently reviewable.

**Resolved spec tension:** spec says the transform "lives in `device_config`", but the persisted `DeviceConfig` schema has no transform field and the spec also forbids a schema change / JSON-Schema re-export. Resolution: transform is an optional `frame_transform` key in the sidecar (Task 7), consumed but never persisted; written `device_config.json` records the contract `CoordinateFrame()` (identity). Honors both constraints.

**Placeholder scan:** none — every code/test step is concrete.

**Type consistency:** `Quat`/`Vec3`/`IDENTITY`/`apply_transform` (Tasks 1–2) used unchanged in Task 8; `XdfStream` fields (Task 3) consumed identically in Tasks 5/11; `IngestMap.motion`/`.events_stream`, `MotionStreamMap`, `extract_motion`/`parse_ingest_map` signatures (Tasks 4–5) match Tasks 7/11; `ParsedSidecar` (Task 7) consumed in Task 11; `_MOTION_COLS`/`_EVENT_COLS`/`_TRACKER_ORDER` defined once (Task 7) and reused in Tasks 8/10; `build_motion_rows`/`build_event_rows`/`compute_t0`/`write_raw_folder` signatures (Tasks 8–10) match the Task 11 orchestrator calls; `EVENT_PAYLOAD_KEYS` JSON convention shared between Task 6 writer and Task 9 decoder.
