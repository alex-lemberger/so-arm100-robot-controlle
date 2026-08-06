# EEG-BIDS Export (BrainVision) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `export-bids` so a session with EEG streams also emits a BIDS-valid BrainVision EEG dataset (`sub-/eeg/`) alongside `sub-/motion/`.

**Architecture:** New pure module `export/eeg_bids.py` (BrainVision builders) + an extension to the `export_motion_bids` orchestrator in `export/bids.py`. Stdlib `struct` only; no new dependency; no schema or CLI change.

**Tech Stack:** Python ≥3.11, pydantic v2, pytest, stdlib `struct`. `pyxdf` (optional) only for the integration test.

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` on `src/htdp/export` (already a gate target).
- ruff: `line-length = 100`, `line-ending = lf`. `uv run ruff format --check . && uv run ruff check .` clean.
- Text files written with `newline="\n"`; JSON via `io.canonical.dump_json`.
- **Regression safety:** a motion-only session must export exactly as in slice 4 (no `eeg/` dir). The eeg path runs only when `role="eeg"` streams exist.
- **No partial writes** beyond the existing motion-tree force guard; build eeg content in memory, write into the same out tree.
- **No persisted-schema change** → no JSON-Schema re-export.
- Do NOT touch `synth`, `validate`, `processing`, `qc`, `replay`, `release`, `ingest`, `schemas`, `cli.py`, or any `export/*` file other than `export/bids.py` (extended) and the new `export/eeg_bids.py`.
- Deterministic: same session → identical eeg files (byte-for-byte).

**Reference — EEG raw CSV** (`streams/eeg_<id>.csv`, from slice 5): header `timestamp_s,<label1>,<label2>,…`; 6dp float values. The EEG `StreamRef` has `role="eeg"`, `name=<eeg_id>`, `path="streams/eeg_<id>.csv"`.

**Reference — existing `export/bids.py`**: `export_motion_bids(raw_dir, out_dir, force=False)` writes `sub-/motion/` + `dataset_description.json` + `participants.tsv` + `README`; helpers `_write_text`, `sanitize` (from `labels`), `dump_json`, and `dicts_to_tsv` (from `tabular`) are available/imported there. `sub = sanitize(session.participant_id)`, `task = sanitize(session.protocol_id)`.

**Reference — BrainVision channel line format**: `Ch<i>=<name>,<ref>,<resolution>,<unit>` — we emit `Ch<i>=<label>,,1,µV` (empty ref, resolution 1, unit microvolt).

---

### Task 1: `eeg_bids.py` — `estimate_fs`

**Files:**
- Create: `src/htdp/export/eeg_bids.py`
- Test: `tests/test_eeg_bids_fs.py`

**Interfaces:**
- Produces: `estimate_fs(timestamps: list[float]) -> float` = `(n-1)/(t_last - t_first)`; raises `ValueError` if `<2` samples or span `<= 0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_bids_fs.py
import pytest

from htdp.export.eeg_bids import estimate_fs


def test_two_samples_250hz():
    assert estimate_fs([0.0, 0.004]) == pytest.approx(250.0)


def test_three_samples_250hz():
    assert estimate_fs([0.0, 0.004, 0.008]) == pytest.approx(250.0)


def test_single_sample_raises():
    with pytest.raises(ValueError):
        estimate_fs([0.0])


def test_zero_span_raises():
    with pytest.raises(ValueError):
        estimate_fs([1.0, 1.0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_bids_fs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.export.eeg_bids'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/export/eeg_bids.py
from __future__ import annotations


def estimate_fs(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        raise ValueError("need at least two samples to estimate sampling frequency")
    span = timestamps[-1] - timestamps[0]
    if span <= 0:
        raise ValueError("zero or negative time span")
    return (len(timestamps) - 1) / span
```

(`import struct` is added in Task 2, where it is first used — keep this file import-free for now so `ruff check` stays clean.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_bids_fs.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/eeg_bids.py tests/test_eeg_bids_fs.py
git commit -m "feat(export): estimate_fs for eeg sampling frequency"
```

---

### Task 2: `eeg_bids.py` — `eeg_binary`

**Files:**
- Modify: `src/htdp/export/eeg_bids.py` (add `import struct`; append `eeg_binary`)
- Test: `tests/test_eeg_bids_binary.py`

**Interfaces:**
- Produces: `eeg_binary(samples: list[list[float]]) -> bytes` — multiplexed little-endian IEEE `float32`: each sample row's channels in order.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_bids_binary.py
import struct

from htdp.export.eeg_bids import eeg_binary


def test_multiplexed_float32_round_trips():
    data = eeg_binary([[1.0, 2.0], [3.0, 4.0]])
    assert len(data) == 16  # 4 floats * 4 bytes
    assert list(struct.unpack("<4f", data)) == [1.0, 2.0, 3.0, 4.0]


def test_empty_is_empty():
    assert eeg_binary([]) == b""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_bids_binary.py -v`
Expected: FAIL — `ImportError: cannot import name 'eeg_binary'`

- [ ] **Step 3: Write minimal implementation**

Add `import struct` directly under `from __future__ import annotations` at the top of
`src/htdp/export/eeg_bids.py`:

```python
from __future__ import annotations

import struct
```

Then append:

```python
def eeg_binary(samples: list[list[float]]) -> bytes:
    return b"".join(struct.pack("<f", v) for row in samples for v in row)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_bids_binary.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/eeg_bids.py tests/test_eeg_bids_binary.py
git commit -m "feat(export): multiplexed float32 eeg binary packer"
```

---

### Task 3: `eeg_bids.py` — `vhdr_text` + `vmrk_text`

**Files:**
- Modify: `src/htdp/export/eeg_bids.py` (append)
- Test: `tests/test_eeg_bids_header.py`

**Interfaces:**
- Produces:
  - `vhdr_text(stem: str, labels: list[str], fs: float) -> str` — BrainVision header; `SamplingInterval = 1_000_000.0 / fs`; one `Ch<i>=<label>,,1,µV` line per channel.
  - `vmrk_text(stem: str) -> str` — marker file with a single `New Segment` marker.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_bids_header.py
from htdp.export.eeg_bids import vhdr_text, vmrk_text


def test_vhdr_core_fields():
    text = vhdr_text("sub-p0001_task-t_acq-eeg", ["Fp1", "Fp2", "Cz"], 250.0)
    assert "BinaryFormat=IEEE_FLOAT_32" in text
    assert "DataFormat=BINARY" in text
    assert "DataOrientation=MULTIPLEXED" in text
    assert "NumberOfChannels=3" in text
    assert "SamplingInterval=4000.0" in text
    assert "DataFile=sub-p0001_task-t_acq-eeg_eeg.eeg" in text
    assert "MarkerFile=sub-p0001_task-t_acq-eeg_eeg.vmrk" in text


def test_vhdr_channel_lines():
    text = vhdr_text("stem", ["Fp1", "Cz"], 250.0)
    assert "Ch1=Fp1,,1,µV" in text
    assert "Ch2=Cz,,1,µV" in text


def test_vmrk_has_new_segment_and_datafile():
    text = vmrk_text("sub-p0001_task-t_acq-eeg")
    assert "Mk1=New Segment" in text
    assert "DataFile=sub-p0001_task-t_acq-eeg_eeg.eeg" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_bids_header.py -v`
Expected: FAIL — `ImportError: cannot import name 'vhdr_text'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/export/eeg_bids.py`:

```python
def vhdr_text(stem: str, labels: list[str], fs: float) -> str:
    interval = 1_000_000.0 / fs
    channel_lines = "\n".join(
        f"Ch{i}={label},,1,µV" for i, label in enumerate(labels, start=1)
    )
    return (
        "Brain Vision Data Exchange Header File Version 1.0\n\n"
        "[Common Infos]\n"
        "Codepage=UTF-8\n"
        f"DataFile={stem}_eeg.eeg\n"
        f"MarkerFile={stem}_eeg.vmrk\n"
        "DataFormat=BINARY\n"
        "DataOrientation=MULTIPLEXED\n"
        f"NumberOfChannels={len(labels)}\n"
        f"SamplingInterval={interval}\n\n"
        "[Binary Infos]\n"
        "BinaryFormat=IEEE_FLOAT_32\n\n"
        "[Channel Infos]\n"
        f"{channel_lines}\n"
    )


def vmrk_text(stem: str) -> str:
    return (
        "Brain Vision Data Exchange Marker File, Version 1.0\n\n"
        "[Common Infos]\n"
        "Codepage=UTF-8\n"
        f"DataFile={stem}_eeg.eeg\n\n"
        "[Marker Infos]\n"
        "Mk1=New Segment,,1,1,0\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_bids_header.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/eeg_bids.py tests/test_eeg_bids_header.py
git commit -m "feat(export): BrainVision vhdr + vmrk text builders"
```

---

### Task 4: `eeg_bids.py` — `eeg_channels_rows` + `eeg_json`

**Files:**
- Modify: `src/htdp/export/eeg_bids.py` (append)
- Test: `tests/test_eeg_bids_meta.py`

**Interfaces:**
- Produces:
  - `EEG_CHANNELS_HEADER: list[str] = ["name", "type", "units"]`
  - `eeg_channels_rows(labels: list[str]) -> list[dict[str, str]]` — one row per channel, `type="EEG"`, `units="µV"`.
  - `eeg_json(task: str, n_channels: int, fs: float) -> dict[str, object]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_bids_meta.py
from htdp.export.eeg_bids import EEG_CHANNELS_HEADER, eeg_channels_rows, eeg_json


def test_channels_rows():
    assert EEG_CHANNELS_HEADER == ["name", "type", "units"]
    rows = eeg_channels_rows(["Fp1", "Cz"])
    assert rows == [
        {"name": "Fp1", "type": "EEG", "units": "µV"},
        {"name": "Cz", "type": "EEG", "units": "µV"},
    ]


def test_eeg_json_fields():
    d = eeg_json("reachgraspplace", 3, 250.0)
    assert d["TaskName"] == "reachgraspplace"
    assert d["SamplingFrequency"] == 250.0
    assert d["EEGChannelCount"] == 3
    assert d["RecordingType"] == "continuous"
    assert d["EEGReference"] == "n/a"
    assert d["PowerLineFrequency"] == "n/a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_bids_meta.py -v`
Expected: FAIL — `ImportError: cannot import name 'eeg_channels_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/export/eeg_bids.py`:

```python
EEG_CHANNELS_HEADER: list[str] = ["name", "type", "units"]


def eeg_channels_rows(labels: list[str]) -> list[dict[str, str]]:
    return [{"name": label, "type": "EEG", "units": "µV"} for label in labels]


def eeg_json(task: str, n_channels: int, fs: float) -> dict[str, object]:
    return {
        "TaskName": task,
        "SamplingFrequency": fs,
        "EEGReference": "n/a",
        "PowerLineFrequency": "n/a",
        "SoftwareFilters": "n/a",
        "EEGChannelCount": n_channels,
        "RecordingType": "continuous",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_bids_meta.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/eeg_bids.py tests/test_eeg_bids_meta.py
git commit -m "feat(export): eeg channels.tsv rows + eeg.json sidecar"
```

---

### Task 5: `bids.py` — `_read_eeg_csv` + orchestrator extension

**Files:**
- Modify: `src/htdp/export/bids.py`
- Test: `tests/test_eeg_bids_export.py`

**Interfaces:**
- Consumes: every `eeg_bids` builder (Tasks 1–4); existing `_write_text`, `sanitize`, `dump_json`, `dicts_to_tsv`.
- Produces:
  - `_read_eeg_csv(path: Path) -> tuple[list[str], list[float], list[list[float]]]` — `(labels, timestamps, samples)`; labels = header minus `timestamp_s`.
  - `export_motion_bids` also writes `sub-/eeg/` (the five BrainVision files per `role="eeg"` stream, `acq=sanitize(stream.name)`) when EEG streams exist. `estimate_fs` `ValueError` → `BidsExportError`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eeg_bids_export.py
import json
import struct
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.export.bids import export_motion_bids  # noqa: E402
from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402

_STEM = "sub-p0001_task-reachgraspplace_acq-eeg"
_EEG_DIR = "sub-p0001/eeg"


def _ingest_eeg(tmp_path: Path) -> Path:
    raw = generate_session(tmp_path / "synthraw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "i.json"
    sidecar.write_text(json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))),
                       encoding="utf-8")
    return ingest_xdf(xdf, sidecar, tmp_path / "raw" / "real-0001")


def test_eeg_files_written(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    for ext in ("_eeg.vhdr", "_eeg.vmrk", "_eeg.eeg", "_eeg.json", "_channels.tsv"):
        assert (out / _EEG_DIR / f"{_STEM}{ext}").exists(), ext


def test_vhdr_channel_count_and_interval(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    vhdr = (out / _EEG_DIR / f"{_STEM}_eeg.vhdr").read_text(encoding="utf-8")
    assert "NumberOfChannels=3" in vhdr
    assert "SamplingInterval=4000.0" in vhdr


def test_eeg_binary_unpacks_to_ingested_values(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    raw = (out / _EEG_DIR / f"{_STEM}_eeg.eeg").read_bytes()
    vals = list(struct.unpack("<" + "f" * (len(raw) // 4), raw))
    assert vals[:3] == pytest.approx([1.0, 2.0, 3.0])  # first sample (3 channels)
    assert vals[3:6] == pytest.approx([1.5, 2.5, 3.5])  # second sample


def test_channels_tsv_row_count(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    lines = (out / _EEG_DIR / f"{_STEM}_channels.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "name\ttype\tunits"
    assert len(lines) - 1 == 3


def test_eeg_json_sampling_frequency(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    d = json.loads((out / _EEG_DIR / f"{_STEM}_eeg.json").read_text(encoding="utf-8"))
    assert d["SamplingFrequency"] > 0
    assert d["EEGChannelCount"] == 3


def test_motion_only_session_has_no_eeg_dir(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = export_motion_bids(tmp_path / "raw" / "synth-0001", tmp_path / "bids")
    assert not (out / "sub-p0001" / "eeg").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eeg_bids_export.py -v`
Expected: FAIL — `test_eeg_files_written` etc. fail (no `eeg/` dir written) — or SKIP without `pyxdf`.

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/export/bids.py`, add the eeg_bids imports (after the `from htdp.export.tabular import (...)` block):

```python
from htdp.export.eeg_bids import (
    EEG_CHANNELS_HEADER,
    eeg_binary,
    eeg_channels_rows,
    eeg_json,
    estimate_fs,
    vhdr_text,
    vmrk_text,
)
```

Add the `_read_eeg_csv` helper next to `_read_csv`:

```python
def _read_eeg_csv(path: Path) -> tuple[list[str], list[float], list[list[float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    labels = lines[0].split(",")[1:]
    timestamps: list[float] = []
    samples: list[list[float]] = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split(",")
        timestamps.append(float(cells[0]))
        samples.append([float(c) for c in cells[1:]])
    return labels, timestamps, samples
```

In `export_motion_bids`, immediately before the final `return out_dir`, add the EEG export:

```python
    eeg_streams = [s for s in device.streams if s.role == "eeg"]
    if eeg_streams:
        eeg_dir = out_dir / f"sub-{sub}" / "eeg"
        eeg_dir.mkdir(parents=True)
        for s in eeg_streams:
            labels, timestamps, samples = _read_eeg_csv(raw_dir / s.path)
            try:
                fs = estimate_fs(timestamps)
            except ValueError as exc:
                raise BidsExportError(f"eeg stream '{s.name}': {exc}") from exc
            acq = sanitize(s.name)
            eeg_stem = f"sub-{sub}_task-{task}_acq-{acq}"
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vhdr", vhdr_text(eeg_stem, labels, fs))
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vmrk", vmrk_text(eeg_stem))
            (eeg_dir / f"{eeg_stem}_eeg.eeg").write_bytes(eeg_binary(samples))
            dump_json(eeg_json(task, len(labels), fs), eeg_dir / f"{eeg_stem}_eeg.json")
            _write_text(
                eeg_dir / f"{eeg_stem}_channels.tsv",
                dicts_to_tsv(EEG_CHANNELS_HEADER, eeg_channels_rows(labels)),
            )
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eeg_bids_export.py tests/test_bids_export.py -v`
Expected: PASS (eeg export tests + existing motion-BIDS tests green) — eeg cases SKIP only without `pyxdf`.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/bids.py tests/test_eeg_bids_export.py
git commit -m "feat(export): emit BrainVision eeg/ alongside motion in export-bids"
```

---

### Task 6: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md` (EEG-BIDS export)
- Modify: `docs/ROADMAP.md` (mark EEG-BIDS in progress/done)

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — add an "EEG-BIDS export" note: EEG is exported as
BrainVision (`.vhdr` header, `.vmrk` markers, `.eeg` binary multiplexed IEEE
float32) under `sub-/eeg/`, with `_channels.tsv` (type `EEG`, units µV) and an
`_eeg.json` sidecar. The export assumes a regular grid: the `timestamp_s` column is
dropped and `SamplingFrequency` is estimated from the timestamps
(`(n-1)/span`); reference, power-line frequency, and filters are recorded as `n/a`.

`docs/ROADMAP.md` — change the EEG-BIDS-related item to mark progress
(e.g. append `— **in progress (BrainVision eeg export landed)**`).

- [ ] **Step 2: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass (only the pre-existing mujoco replay skip if the replay extra is absent; `pyxdf`-gated eeg-export tests RUN when the `ingest` extra is installed); mypy `Success`.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md docs/ROADMAP.md
git commit -m "docs(export): document BrainVision EEG-BIDS export"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-eeg-bids-export-design.md`):
- `estimate_fs` (avg rate, <2/zero-span errors) → Task 1. ✓
- `eeg_binary` multiplexed float32 → Task 2. ✓
- `vhdr_text` + `vmrk_text` → Task 3. ✓
- `eeg_channels_rows` + `eeg_json` → Task 4. ✓
- `_read_eeg_csv` + orchestrator writes `sub-/eeg/` per stream (`acq` entity), fs error → `BidsExportError` → Task 5. ✓
- Regular-grid assumption (drop `timestamp_s`, estimated fs, `n/a` metadata) → Tasks 1/4/5. ✓
- Regression: motion-only → no `eeg/` dir; slice-4 tests green → Task 5 test + Step 4. ✓
- Docs (DATA_CONTRACT, ROADMAP), no schema re-export → Task 6. ✓
- Non-goals (EDF/EEGLAB, electrodes/coordsystem, reref/filter, per-sample timing, events-in-vmrk, multi-subject) — none implemented. ✓

**No-touch check:** edits limited to `export/bids.py` (extended) + new `export/eeg_bids.py` + new tests + docs. No other module, schema, or CLI changed.

**Placeholder scan:** none — every code/test step is concrete.

**Type consistency:** `estimate_fs(list[float]) -> float`, `eeg_binary(list[list[float]]) -> bytes`, `vhdr_text(str, list[str], float) -> str`, `vmrk_text(str) -> str`, `eeg_channels_rows(list[str]) -> list[dict[str,str]]`, `eeg_json(str, int, float) -> dict[str,object]` (Tasks 1–4) all match their calls in Task 5; `_read_eeg_csv -> (labels, timestamps, samples)` feeds `estimate_fs(timestamps)`, `eeg_binary(samples)`, and the label-based builders; `EEG_CHANNELS_HEADER` pairs with `eeg_channels_rows` via `dicts_to_tsv`; the `acq` stem `sub-<sub>_task-<task>_acq-<id>` is built identically where files are named and where `DataFile`/`MarkerFile` are embedded.
```
