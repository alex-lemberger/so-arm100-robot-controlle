# EEG Ingest (XDF Adapter Extension) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest EEG from an LSL `.xdf` by extending the slice-1 XDF adapter with an `eeg` stream role, writing wide `streams/eeg_<id>.csv` + a `role="eeg"` StreamRef into the raw session — closing the loop with slice-2's consent EEG filter.

**Architecture:** Extend `ingest/mapping.py` (parse + extract EEG) and `ingest/session.py` (build + write EEG, wire into `ingest_xdf`); extend the `tests/_xdf_writer.py` test infra to emit an EEG stream. EEG rebased to the existing motion `t0`. Downstream (`validate`/`process`/`qc`/`package`/`export`) unchanged.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest, `pyxdf` (optional, round-trip only).

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` on `src/htdp/ingest` (already a gate target).
- ruff: `line-length = 100`, `line-ending = lf`. `uv run ruff format --check . && uv run ruff check .` clean.
- Canonical CSV via `io.canonical.write_csv` (stable columns, 6dp floats, `\n`).
- **No partial writes:** extract + build all rows in memory before `write_raw_folder`.
- **Regression safety:** the new `write_raw_folder` EEG parameter defaults to empty so existing slice-1 ingest tests behave identically. Existing `parse_ingest_map`/`IngestMap` usage must keep working (new `eeg` field defaults to empty).
- **No persisted-schema change** (`role` is a free string on `StreamRef`) → no JSON-Schema re-export.
- Do NOT touch `validate`, `processing`, `qc`, `replay`, `release`, `export`, `synth`, `schemas`, or `ingest/reader.py`/`ingest/frame.py`. This slice edits only `ingest/mapping.py`, `ingest/session.py`, `tests/_xdf_writer.py`, `cli.py` is NOT changed (the existing `ingest` command already ingests EEG via the sidecar).
- Deterministic: same inputs → identical raw folder.

**Reference — current `IngestMap`/`parse_ingest_map`** (`ingest/mapping.py`): roles `motion`/`events`; exactly one events stream, ≥1 motion stream; `extract_motion` rejects string-format and checks channel index range.

**Reference — `write_raw_folder`** (`ingest/session.py`): writes `streams/motion_*.csv` + `streams/events.csv`, builds `StreamRef`s, writes metadata, `write_checksums`. `compute_t0` = earliest motion sample (motion-only).

**Reference — EEG sidecar entry shape:**
`{"role": "eeg", "eeg_id": "eeg", "channels": {"Fp1": 0, "Fp2": 1, "Cz": 2}}` — `eeg_id` non-empty, `channels` non-empty ordered label→XDF-index map (order = CSV column order).

---

### Task 1: `mapping.py` — `EegStreamMap` + parse `eeg` role

**Files:**
- Modify: `src/htdp/ingest/mapping.py`
- Test: `tests/test_mapping_eeg.py`

**Interfaces:**
- Produces:
  - `@dataclass EegStreamMap` with `eeg_id: str`, `channels: dict[str, int]`.
  - `IngestMap` gains `eeg: dict[str, EegStreamMap]` (keyed by XDF stream name, default empty).
  - `parse_ingest_map` resolves `role="eeg"` entries; raises `MappingError` on missing/empty `eeg_id` or `channels`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mapping_eeg.py
import pytest

from htdp.ingest.mapping import EegStreamMap, MappingError, parse_ingest_map

_MCH = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _raw(eeg_entry):
    return {
        "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_MCH)},
        "brain": eeg_entry,
        "marker": {"role": "events"},
    }


def test_parse_resolves_eeg_entry():
    im = parse_ingest_map(_raw({"role": "eeg", "eeg_id": "eeg", "channels": {"Fp1": 0, "Cz": 1}}))
    assert "brain" in im.eeg
    assert im.eeg["brain"] == EegStreamMap(eeg_id="eeg", channels={"Fp1": 0, "Cz": 1})


def test_eeg_is_optional():
    im = parse_ingest_map({
        "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_MCH)},
        "marker": {"role": "events"},
    })
    assert im.eeg == {}


def test_eeg_missing_id_raises():
    with pytest.raises(MappingError, match="eeg_id"):
        parse_ingest_map(_raw({"role": "eeg", "channels": {"Fp1": 0}}))


def test_eeg_empty_channels_raises():
    with pytest.raises(MappingError, match="channels"):
        parse_ingest_map(_raw({"role": "eeg", "eeg_id": "eeg", "channels": {}}))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mapping_eeg.py -v`
Expected: FAIL — `ImportError: cannot import name 'EegStreamMap'`

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/ingest/mapping.py`, change the dataclass import:

```python
from dataclasses import dataclass
```

to:

```python
from dataclasses import dataclass, field
```

Add the `EegStreamMap` dataclass after `MotionStreamMap`:

```python
@dataclass
class EegStreamMap:
    eeg_id: str
    channels: dict[str, int]
```

Add the `eeg` field to `IngestMap`:

```python
@dataclass
class IngestMap:
    motion: dict[str, MotionStreamMap]
    events_stream: str
    eeg: dict[str, EegStreamMap] = field(default_factory=dict)
```

In `parse_ingest_map`, initialize an `eeg` accumulator and handle the role. Change the opening:

```python
def parse_ingest_map(raw: dict[str, object]) -> IngestMap:
    motion: dict[str, MotionStreamMap] = {}
    events_streams: list[str] = []
```

to:

```python
def parse_ingest_map(raw: dict[str, object]) -> IngestMap:
    motion: dict[str, MotionStreamMap] = {}
    eeg: dict[str, EegStreamMap] = {}
    events_streams: list[str] = []
```

Insert an `eeg` branch before the final `else` (after the `motion` branch closes, i.e. before `else: raise MappingError(... unknown role ...)`):

```python
        elif role == "eeg":
            eeg_id = entry.get("eeg_id")
            if not isinstance(eeg_id, str) or not eeg_id:
                raise MappingError(f"stream '{stream_name}' eeg entry needs non-empty 'eeg_id'")
            channels = entry.get("channels")
            if not isinstance(channels, dict) or not channels:
                raise MappingError(f"stream '{stream_name}' eeg entry needs non-empty 'channels'")
            eeg[stream_name] = EegStreamMap(
                eeg_id=eeg_id,
                channels={str(k): int(v) for k, v in channels.items()},
            )
```

Change the return:

```python
    return IngestMap(motion=motion, events_stream=events_streams[0])
```

to:

```python
    return IngestMap(motion=motion, events_stream=events_streams[0], eeg=eeg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mapping_eeg.py tests/test_mapping.py -v`
Expected: PASS (new eeg tests + all existing mapping tests green)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/mapping.py tests/test_mapping_eeg.py
git commit -m "feat(ingest): parse eeg role in ingest_map"
```

---

### Task 2: `mapping.py` — `extract_eeg`

**Files:**
- Modify: `src/htdp/ingest/mapping.py` (append)
- Test: `tests/test_mapping_eeg.py` (append)

**Interfaces:**
- Consumes: `XdfStream`, `EegStreamMap`, `MappingError`.
- Produces: `extract_eeg(stream: XdfStream, m: EegStreamMap) -> tuple[list[str], list[dict[str, object]]]` — returns `(labels, rows)` where `labels = list(m.channels)` (declared order) and each row is `{"raw_ts": float, <label>: float, …}`. Rejects string-format streams; raises `MappingError` on out-of-range channel index.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mapping_eeg.py`:

```python
from htdp.ingest.mapping import extract_eeg  # noqa: E402
from htdp.ingest.reader import XdfStream  # noqa: E402


def _eeg_stream():
    return XdfStream(
        name="brain", type="eeg", channel_format="double64",
        time_stamps=[5.0, 5.004],
        time_series=[[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]],
    )


def test_extract_eeg_builds_labelled_rows():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 0, "Fp2": 1, "Cz": 2})
    labels, rows = extract_eeg(_eeg_stream(), m)
    assert labels == ["Fp1", "Fp2", "Cz"]
    assert rows[0] == {"raw_ts": 5.0, "Fp1": 1.0, "Fp2": 2.0, "Cz": 3.0}
    assert rows[1]["Cz"] == 3.1


def test_extract_eeg_rejects_string_stream():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 0})
    bad = XdfStream(name="brain", type="eeg", channel_format="string",
                    time_stamps=[0.0], time_series=["x"])
    with pytest.raises(MappingError, match="numeric"):
        extract_eeg(bad, m)


def test_extract_eeg_channel_out_of_range():
    m = EegStreamMap(eeg_id="eeg", channels={"Fp1": 9})
    with pytest.raises(MappingError, match="out of range"):
        extract_eeg(_eeg_stream(), m)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mapping_eeg.py -k extract_eeg -v`
Expected: FAIL — `ImportError: cannot import name 'extract_eeg'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/mapping.py`:

```python
def extract_eeg(stream: XdfStream, m: EegStreamMap) -> tuple[list[str], list[dict[str, object]]]:
    if stream.channel_format == "string":
        raise MappingError(f"eeg stream '{stream.name}' must be numeric, got string format")
    labels = list(m.channels)
    rows: list[dict[str, object]] = []
    for ts, sample in zip(stream.time_stamps, stream.time_series):
        assert isinstance(sample, list)
        row: dict[str, object] = {"raw_ts": float(ts)}
        for label in labels:
            idx = m.channels[label]
            if idx >= len(sample):
                raise MappingError(
                    f"eeg stream '{stream.name}' channel '{label}' index {idx} "
                    f"out of range (sample has {len(sample)} channels)"
                )
            row[label] = float(sample[idx])
        rows.append(row)
    return labels, rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_mapping_eeg.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/mapping.py tests/test_mapping_eeg.py
git commit -m "feat(ingest): extract_eeg channel mapping"
```

---

### Task 3: `session.py` — `build_eeg_rows` (pure)

**Files:**
- Modify: `src/htdp/ingest/session.py` (append)
- Test: `tests/test_session_eeg.py`

**Interfaces:**
- Produces: `build_eeg_rows(eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]], t0: float) -> dict[str, tuple[list[str], list[dict[str, object]]]]` — per `eeg_id`, copy labels and rebase each row to `{"timestamp_s": raw_ts - t0, <label>: value, …}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_eeg.py
import pytest

from htdp.ingest.session import build_eeg_rows


def _raw():
    return {
        "eeg": (
            ["Fp1", "Cz"],
            [
                {"raw_ts": 1000.0, "Fp1": 1.0, "Cz": 2.0},
                {"raw_ts": 1000.01, "Fp1": 1.1, "Cz": 2.1},
            ],
        )
    }


def test_build_eeg_rows_rebases_and_keeps_labels():
    out = build_eeg_rows(_raw(), 1000.0)
    labels, rows = out["eeg"]
    assert labels == ["Fp1", "Cz"]
    assert rows[0]["timestamp_s"] == pytest.approx(0.0, abs=1e-9)
    assert rows[1]["timestamp_s"] == pytest.approx(0.01, abs=1e-9)
    assert rows[0]["Fp1"] == 1.0 and rows[1]["Cz"] == 2.1


def test_build_eeg_rows_allows_negative_timestamps():
    raw = {"eeg": (["Fp1"], [{"raw_ts": 999.5, "Fp1": 0.0}])}
    _labels, rows = build_eeg_rows(raw, 1000.0)["eeg"]
    assert rows[0]["timestamp_s"] == pytest.approx(-0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_eeg.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_eeg_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/session.py`:

```python
def build_eeg_rows(
    eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]],
    t0: float,
) -> dict[str, tuple[list[str], list[dict[str, object]]]]:
    out: dict[str, tuple[list[str], list[dict[str, object]]]] = {}
    for eeg_id, (labels, rows) in eeg_raw.items():
        built: list[dict[str, object]] = []
        for r in rows:
            new_row: dict[str, object] = {"timestamp_s": float(r["raw_ts"]) - t0}  # type: ignore[arg-type]
            for label in labels:
                new_row[label] = float(r[label])  # type: ignore[arg-type]
            built.append(new_row)
        out[eeg_id] = (labels, built)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_eeg.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_eeg.py
git commit -m "feat(ingest): build_eeg_rows rebase to motion t0"
```

---

### Task 4: `session.py` — `write_raw_folder` writes EEG

**Files:**
- Modify: `src/htdp/ingest/session.py` (`write_raw_folder`)
- Test: `tests/test_session_write_eeg.py`

**Interfaces:**
- Produces: `write_raw_folder` gains keyword-only `eeg_out: dict[str, tuple[list[str], list[dict[str, object]]]] | None = None`. For each `eeg_id`, writes `streams/eeg_<eeg_id>.csv` (columns `["timestamp_s"] + labels`) and appends `StreamRef(name=eeg_id, path, fmt="csv", role="eeg")`. Default `None` → no EEG written (existing behaviour).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_write_eeg.py
from pathlib import Path

from htdp.ingest.session import write_raw_folder
from htdp.schemas.models import Consent, DeviceConfig, Session
from htdp.validate import validate_session


def _session():
    return Session(
        session_id="real-0001", participant_id="p1", protocol_id="reach-grasp-place",
        consent_form_version="v1", device_config_id="vive-1", start_time_s=0.0,
    )


def _motion():
    return {
        "right_wrist": [
            {"timestamp_s": 0.0, "tracker_id": "right_wrist", "x_m": 0.1, "y_m": 0.2, "z_m": 0.9,
             "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "quality": 1.0, "defect_tag": ""},
        ],
    }


def _events():
    return [{"timestamp_s": 0.0, "event_id": 0, "label": "start", "phase": "approach",
             "source": "real", "confidence": 1.0, "notes": ""}]


def test_write_raw_folder_writes_eeg_and_validates(tmp_path: Path):
    eeg_out = {"eeg": (["Fp1", "Cz"], [{"timestamp_s": 0.0, "Fp1": 1.0, "Cz": 2.0}])}
    out = write_raw_folder(
        tmp_path / "real-0001", session=_session(), consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1", motion_out=_motion(), event_rows=_events(),
        source_xdf_name="rec.xdf", eeg_out=eeg_out,
    )
    eeg_csv = out / "streams" / "eeg_eeg.csv"
    assert eeg_csv.exists()
    assert eeg_csv.read_text(encoding="utf-8").splitlines()[0] == "timestamp_s,Fp1,Cz"
    device = DeviceConfig.model_validate_json((out / "device_config.json").read_text())
    assert any(s.role == "eeg" and s.name == "eeg" for s in device.streams)
    assert validate_session(out) == []


def test_write_raw_folder_without_eeg_unchanged(tmp_path: Path):
    out = write_raw_folder(
        tmp_path / "real-0001", session=_session(), consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1", motion_out=_motion(), event_rows=_events(),
        source_xdf_name="rec.xdf",
    )
    assert not list((out / "streams").glob("eeg_*.csv"))
    assert validate_session(out) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_write_eeg.py -v`
Expected: FAIL — `TypeError: write_raw_folder() got an unexpected keyword argument 'eeg_out'`

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/ingest/session.py`, change the `write_raw_folder` signature to add the keyword-only parameter (after `source_xdf_name: str,` and before `force: bool = False,`):

```python
    source_xdf_name: str,
    eeg_out: dict[str, tuple[list[str], list[dict[str, object]]]] | None = None,
    force: bool = False,
```

Then, immediately after the block that writes events and appends the events `StreamRef` (the lines ending with the `StreamRef(name="events", …)` append), insert the EEG writing loop **before** the `device_out = DeviceConfig(...)` line:

```python
    for eeg_id, (labels, rows) in (eeg_out or {}).items():
        rel = f"streams/eeg_{eeg_id}.csv"
        write_csv(rows, ["timestamp_s"] + labels, out_dir / rel)
        stream_refs.append(StreamRef(name=eeg_id, path=rel, fmt="csv", role="eeg"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_write_eeg.py tests/test_session_write.py -v`
Expected: PASS (new eeg-write tests + existing write tests green)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_session_write_eeg.py
git commit -m "feat(ingest): write_raw_folder emits eeg streams"
```

---

### Task 5: `_xdf_writer.py` — emit EEG stream + sidecar

**Files:**
- Modify: `tests/_xdf_writer.py`
- Test: `tests/test_xdf_writer_eeg.py`

**Interfaces:**
- Produces:
  - `write_xdf(raw_dir, xdf_path, eeg=None)` — optional `eeg: tuple[str, list[str], list[float], list[list[float]]] | None` = `(eeg_id, labels, stamps, samples)`; when given, appends a `double64` EEG stream named `eeg_id` whose timestamps are `stamps + CLOCK_BASE`.
  - `build_sidecar(raw_dir, eeg=None)` — optional `eeg: tuple[str, list[str]] | None` = `(eeg_id, labels)`; when given, adds an `ingest_map` entry keyed by `eeg_id` with `{"role": "eeg", "eeg_id": eeg_id, "channels": {label: i}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_xdf_writer_eeg.py
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.reader import load_xdf_streams  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def test_eeg_stream_round_trips_through_reader(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]])
    write_xdf(raw, xdf, eeg=eeg)
    streams = load_xdf_streams(xdf)
    assert "eeg" in streams
    assert streams["eeg"].channel_format == "double64"
    assert len(streams["eeg"].time_series[0]) == 3


def test_build_sidecar_adds_eeg_entry(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    sidecar = build_sidecar(raw, eeg=("eeg", ["Fp1", "Cz"]))
    entry = sidecar["ingest_map"]["eeg"]
    assert entry == {"role": "eeg", "eeg_id": "eeg", "channels": {"Fp1": 0, "Cz": 1}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_xdf_writer_eeg.py -v`
Expected: FAIL — `TypeError: write_xdf() got an unexpected keyword argument 'eeg'` (or SKIP without `pyxdf`)

- [ ] **Step 3: Write minimal implementation**

In `tests/_xdf_writer.py`, change the `write_xdf` signature and append the EEG stream before `xdf_path.write_bytes(blob)`:

```python
def write_xdf(
    raw_dir: Path,
    xdf_path: Path,
    eeg: tuple[str, list[str], list[float], list[list[float]]] | None = None,
) -> None:
```

Then, immediately before the final `xdf_path.write_bytes(blob)` line, insert:

```python
    if eeg is not None:
        eeg_id, labels, eeg_stamps, eeg_samples = eeg
        stamps = [t + CLOCK_BASE for t in eeg_stamps]
        blob += _stream_header(stream_id + 1, eeg_id, "double64", len(labels), 0.0)
        blob += _samples_numeric(stream_id + 1, stamps, eeg_samples)
        blob += _stream_footer(stream_id + 1, stamps)
```

Change the `build_sidecar` signature and add the EEG entry before the `return`:

```python
def build_sidecar(
    raw_dir: Path,
    eeg: tuple[str, list[str]] | None = None,
) -> dict[str, object]:
```

```python
    if eeg is not None:
        eeg_id, labels = eeg
        ingest_map[eeg_id] = {
            "role": "eeg",
            "eeg_id": eeg_id,
            "channels": {label: i for i, label in enumerate(labels)},
        }
```

(Insert the EEG entry after `ingest_map["events"] = {"role": "events"}` and before the `return {...}`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_xdf_writer_eeg.py -v`
Expected: PASS (2 passed) — or SKIP without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add tests/_xdf_writer.py tests/test_xdf_writer_eeg.py
git commit -m "test(ingest): xdf writer emits eeg stream + sidecar entry"
```

---

### Task 6: `session.py` — wire EEG into `ingest_xdf` (round-trip)

**Files:**
- Modify: `src/htdp/ingest/session.py` (`ingest_xdf`)
- Test: `tests/test_ingest_eeg_roundtrip.py`

**Interfaces:**
- Consumes: `extract_eeg` (Task 2), `build_eeg_rows` (Task 3), `write_raw_folder` EEG param (Task 4).
- Produces: `ingest_xdf` extracts EEG streams from the XDF, builds rebased rows, and passes `eeg_out` to `write_raw_folder`. A mapped EEG stream absent from the XDF → `KeyError` naming it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingest_eeg_roundtrip.py
import json
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session
from htdp.validate import validate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def _run(tmp_path: Path) -> Path:
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))),
                       encoding="utf-8")
    return ingest_xdf(xdf, sidecar, tmp_path / "ingested")


def test_eeg_csv_written_with_columns_and_values(tmp_path: Path):
    out = _run(tmp_path)
    eeg_csv = out / "streams" / "eeg_eeg.csv"
    lines = eeg_csv.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp_s,Fp1,Fp2,Cz"
    # t0 = earliest motion sample = CLOCK_BASE, so eeg ts rebases to its raw offset
    first = lines[1].split(",")
    assert first[0] == "0.000000"
    assert first[1] == "1.000000" and first[3] == "3.000000"


def test_eeg_session_validates(tmp_path: Path):
    assert validate_session(_run(tmp_path)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_eeg_roundtrip.py -v`
Expected: FAIL — `eeg_eeg.csv` not written (the `ingest_xdf` wiring is missing) — or SKIP without `pyxdf`.

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/ingest/session.py`, add `extract_eeg` to the mapping import:

```python
from htdp.ingest.mapping import IngestMap, extract_eeg, extract_motion, parse_ingest_map
```

In `ingest_xdf`, after the motion extraction loop and `t0`/`motion_out` computation, and before building `event_rows`, add EEG extraction; then pass `eeg_out` to `write_raw_folder`. Insert after the `motion_out = build_motion_rows(...)` line:

```python
    eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]] = {}
    for stream_name, em in parsed.ingest_map.eeg.items():
        if stream_name not in streams:
            raise KeyError(f"ingest_map eeg stream '{stream_name}' not found in XDF")
        eeg_raw[em.eeg_id] = extract_eeg(streams[stream_name], em)
    eeg_out = build_eeg_rows(eeg_raw, t0)
```

Change the final `return write_raw_folder(...)` call to pass `eeg_out=eeg_out` (add the argument before `force=force`):

```python
        source_xdf_name=xdf_path.name,
        eeg_out=eeg_out,
        force=force,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ingest_eeg_roundtrip.py tests/test_ingest_roundtrip.py -v`
Expected: PASS (eeg round-trip + existing motion round-trip green) — or SKIP without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/session.py tests/test_ingest_eeg_roundtrip.py
git commit -m "feat(ingest): wire eeg extraction into ingest_xdf"
```

---

### Task 7: loop-closure with consent filtering

**Files:**
- Test: `tests/test_eeg_consent_filtering.py` (new test only — no source change)

**Interfaces:**
- Consumes: `ingest_xdf` (Task 6), `package_release` (existing).
- Produces: proof that ingested EEG is filtered by consent at release time. **No production code** — if a source change is needed, STOP and report (defect in earlier task or slice 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_consent_filtering.py
import json
from pathlib import Path

import pytest

from htdp.io.checksums import write_checksums
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def _ingest_eeg_session(tmp_path: Path, allow_eeg: bool) -> Path:
    raw = generate_session(tmp_path / "synthraw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Cz"], [0.0, 0.004], [[1.0, 2.0], [1.1, 2.1]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Cz"]))), encoding="utf-8")
    session = ingest_xdf(xdf, sidecar, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data.update({
        "distribute_raw_eeg": allow_eeg,
        "commercial_use": True, "model_training": True,
        "third_party_access": True, "public_release": True, "internal_only": False,
    })
    consent.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(session)
    return tmp_path / "raw"


def test_allowed_eeg_survives_packaging(tmp_path: Path):
    raw = _ingest_eeg_session(tmp_path, allow_eeg=True)
    out = package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert (out / "data/real-0001/streams/eeg_eeg.csv").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "eeg" not in manifest["absent_modalities"]


def test_forbidden_eeg_dropped_at_packaging(tmp_path: Path):
    raw = _ingest_eeg_session(tmp_path, allow_eeg=False)
    out = package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert not (out / "data/real-0001/streams/eeg_eeg.csv").exists()
    assert (out / "data/real-0001/streams/motion_right_wrist.csv").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "eeg" in manifest["absent_modalities"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_consent_filtering.py -v`
Expected: PASS immediately if Tasks 1–6 are complete (exercises existing wiring) — that is the intended outcome; proceed to commit. If FAIL, STOP and report (do not patch around it). SKIP without `pyxdf`.

- [ ] **Step 3: (no implementation)**

Tests only. No source change. If Step 2 passed, skip to Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_consent_filtering.py -v`
Expected: PASS (2 passed) — or SKIP without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_eeg_consent_filtering.py
git commit -m "test(ingest): consent filtering drops/keeps ingested eeg"
```

---

### Task 8: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md` (EEG stream)
- Modify: `AGENTS.md` (eeg role in ingest_map)
- Modify: `docs/ROADMAP.md` (mark EEG capture in progress)

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — document the EEG stream: wide CSV `streams/eeg_<id>.csv`
(`timestamp_s` + one column per channel label in declared order), `role="eeg"`,
timestamps rebased to the motion `t0` (may be negative if EEG leads motion), sample
rate not recorded in this slice.

`AGENTS.md` — note the `ingest` sidecar's `ingest_map` now supports an `eeg` role
(`{"role":"eeg","eeg_id":...,"channels":{...}}`) alongside `motion`/`events`.

`docs/ROADMAP.md` — change the "EEG capture" bullet to mark progress (e.g. append
`— **in progress (XDF eeg ingest landed; EEG-BIDS still deferred)**`).

- [ ] **Step 2: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass (only the pre-existing mujoco replay skip remains if the replay extra is absent; `pyxdf`-gated eeg tests RUN when the `ingest` extra is installed); mypy `Success`.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(ingest): document eeg stream ingest"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-eeg-ingest-design.md`):
- `EegStreamMap` + `IngestMap.eeg` + parse eeg role (optional, validation) → Task 1. ✓
- `extract_eeg` (labelled rows, string/range errors) → Task 2. ✓
- `build_eeg_rows` rebase to motion t0 (incl. negative) → Task 3. ✓
- `write_raw_folder` writes `eeg_<id>.csv` + `role="eeg"` StreamRef, default empty → Task 4. ✓
- `_xdf_writer` EEG emit + sidecar entry → Task 5. ✓
- `ingest_xdf` wiring + KeyError on missing stream → Task 6. ✓
- Loop closure with consent eeg filter → Task 7. ✓
- Docs (DATA_CONTRACT, AGENTS, ROADMAP), no schema re-export → Task 8. ✓
- Regression: default-empty `eeg_out`, optional `eeg` field → existing slice-1 tests rerun in Tasks 1/4/6 and stay green. ✓
- Non-goals (EEG-BIDS, EEG QC/processing, sample rate, montage) — none implemented. ✓

**No-touch check:** edits limited to `ingest/mapping.py`, `ingest/session.py`,
`tests/_xdf_writer.py`, and new tests + docs. `validate`, `process`, `qc`, `release`,
`export`, `synth`, `schemas`, `reader.py`, `frame.py`, `cli.py` untouched.

**Placeholder scan:** none — every code/test step is concrete. (Task 7 Step 2 states the tests may pass immediately, with a STOP instruction if they fail.)

**Type consistency:** `EegStreamMap(eeg_id, channels)` (Task 1) consumed by `extract_eeg` (Task 2) and keyed into `eeg_raw` by `eeg_id` in `ingest_xdf` (Task 6); `extract_eeg -> tuple[list[str], list[dict[str,object]]]` matches `eeg_raw` values feeding `build_eeg_rows` (Task 3), whose output type matches `write_raw_folder`'s `eeg_out` param (Task 4); `_xdf_writer` `eeg` tuple shape `(eeg_id, labels, stamps, samples)` (Task 5) matches the round-trip caller (Task 6); the CSV header `["timestamp_s"] + labels` written in Task 4 matches the `timestamp_s,Fp1,Fp2,Cz` asserted in Task 6.
```
