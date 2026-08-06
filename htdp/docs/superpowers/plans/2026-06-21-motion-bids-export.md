# Motion-BIDS Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp export-bids`: read a single raw session and write a minimal, faithful Motion-BIDS (BEP029) dataset tree (long→wide motion pivot with `n/a` fill, channels/sidecar/events), so consumers can read htdp motion in a standard layout.

**Architecture:** New `src/htdp/export/` package — three pure builder modules (`labels`, `tabular`, `sidecars`) + a thin I/O orchestrator (`bids`) + one CLI command. Reads the raw session (self-contained: motion CSVs + metadata JSON), writes a separate BIDS tree. No change to any existing stage or schema. No new third-party dependency (stdlib only).

**Tech Stack:** Python ≥3.11, pydantic v2 (existing schemas), typer, pytest. Stdlib only in the export path.

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` must pass on `src/htdp/export` (Task 8 adds it to the gate target list).
- ruff: `line-length = 100`, `line-ending = lf`. `uv run ruff format --check . && uv run ruff check .` clean.
- Canonical: JSON via `io.canonical.dump_json` (sorted keys, 2-space indent, trailing `\n`). TSV/text files written with `newline="\n"`. Motion float values are emitted **verbatim** from the raw CSV (already 6dp) — do not reformat them.
- **No partial writes:** parse + build every output string in memory FIRST; create dirs and write only at the end. The `.mp4`/raw is never decoded; the export is **read-only** (writes a separate tree, never mutates raw/processed/releases).
- **No persisted-schema change** → no JSON-Schema re-export.
- Do NOT touch `synth`, `validate`, `processing`, `qc`, `replay`, `release`, `ingest`, or `schemas`.
- Deterministic: same raw session → identical BIDS tree.

**Reference — `Session`/`DeviceConfig`/`StreamRef`** (`src/htdp/schemas/models.py`): `Session.participant_id`, `Session.protocol_id`, `Session.session_id`; `DeviceConfig.device_config_id`, `DeviceConfig.streams: list[StreamRef]`; `StreamRef.name`, `.path`, `.role`, `.rate_hz`.

**Reference — raw motion CSV columns** (verbatim): `timestamp_s, tracker_id, x_m, y_m, z_m, qw, qx, qy, qz, quality, defect_tag`. **`defect_tag` is NOT exported** (htdp QC metadata, not motion). Events CSV columns: `timestamp_s, event_id, label, phase, source, confidence, notes`.

**Reference — the 8 exported per-tracker suffixes** (column + channel order): `("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")`.

---

### Task 1: `export/labels.py` — `sanitize` + `entity_stem`

**Files:**
- Create: `src/htdp/export/__init__.py` (empty)
- Create: `src/htdp/export/labels.py`
- Test: `tests/test_bids_labels.py`

**Interfaces:**
- Produces: `sanitize(label: str) -> str` (keep `[A-Za-z0-9]`, drop the rest);
  `entity_stem(sub: str, task: str, tracksys: str) -> str` → `"sub-<sub>_task-<task>_tracksys-<tracksys>"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_labels.py
from htdp.export.labels import entity_stem, sanitize


def test_sanitize_strips_non_alphanumeric():
    assert sanitize("p-0001") == "p0001"
    assert sanitize("reach-grasp-place") == "reachgraspplace"
    assert sanitize("vive_synth 2") == "vivesynth2"


def test_entity_stem_format():
    assert entity_stem("p0001", "reachgraspplace", "vivesynth") == (
        "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_labels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.export'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/export/__init__.py
```

(empty file)

```python
# src/htdp/export/labels.py
from __future__ import annotations


def sanitize(label: str) -> str:
    """Reduce a label to BIDS-safe alphanumerics (drop separators/punctuation)."""
    return "".join(c for c in label if c.isalnum())


def entity_stem(sub: str, task: str, tracksys: str) -> str:
    return f"sub-{sub}_task-{task}_tracksys-{tracksys}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_labels.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/__init__.py src/htdp/export/labels.py tests/test_bids_labels.py
git commit -m "feat(export): BIDS label sanitize + entity_stem"
```

---

### Task 2: `export/tabular.py` — `motion_wide` + `matrix_to_tsv`

**Files:**
- Create: `src/htdp/export/tabular.py`
- Test: `tests/test_bids_motion_wide.py`

**Interfaces:**
- Produces:
  - `SUFFIXES: tuple[str, ...] = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")`
  - `motion_wide(rows: list[dict[str, str]], trackers: list[str]) -> tuple[list[str], list[list[str]]]` — header `["timestamp_s", "<tracker>_<suffix>", …]` (trackers in given order, suffixes in `SUFFIXES` order); one row per **distinct** `timestamp_s` (sorted by float), missing tracker samples → `"n/a"`. Values copied verbatim from `rows`.
  - `matrix_to_tsv(header: list[str], matrix: list[list[str]]) -> str` — tab-joined, `\n`-terminated.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_motion_wide.py
from htdp.export.tabular import SUFFIXES, matrix_to_tsv, motion_wide


def _row(tracker: str, ts: str, x: str = "0.000000") -> dict[str, str]:
    base = {s: "0.000000" for s in SUFFIXES}
    base.update({"timestamp_s": ts, "tracker_id": tracker, "x_m": x})
    return base


def test_header_lists_timestamp_then_each_tracker_suffix():
    header, _ = motion_wide([_row("a", "0.000000")], ["a", "b"])
    assert header[0] == "timestamp_s"
    assert header[1:9] == [f"a_{s}" for s in SUFFIXES]
    assert header[9:17] == [f"b_{s}" for s in SUFFIXES]


def test_union_timestamps_sorted_and_na_filled():
    rows = [_row("a", "0.000000", x="1.000000"), _row("b", "0.010000", x="2.000000")]
    header, matrix = motion_wide(rows, ["a", "b"])
    assert [r[0] for r in matrix] == ["0.000000", "0.010000"]  # union, sorted
    # at t=0 a is present, b is missing -> b columns n/a
    assert matrix[0][1] == "1.000000"  # a_x_m
    assert matrix[0][9] == "n/a"  # b_x_m
    # at t=0.01 a is missing -> a columns n/a, b present
    assert matrix[1][1] == "n/a"  # a_x_m
    assert matrix[1][9] == "2.000000"  # b_x_m


def test_matrix_to_tsv_tab_joined():
    text = matrix_to_tsv(["x", "y"], [["1", "2"], ["3", "n/a"]])
    assert text == "x\ty\n1\t2\n3\tn/a\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_motion_wide.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.export.tabular'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/export/tabular.py
from __future__ import annotations

SUFFIXES: tuple[str, ...] = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")


def motion_wide(
    rows: list[dict[str, str]],
    trackers: list[str],
) -> tuple[list[str], list[list[str]]]:
    by_tracker: dict[str, dict[str, dict[str, str]]] = {}
    for r in rows:
        by_tracker.setdefault(r["tracker_id"], {})[r["timestamp_s"]] = r
    all_ts = sorted({r["timestamp_s"] for r in rows}, key=float)
    header = ["timestamp_s"] + [f"{t}_{s}" for t in trackers for s in SUFFIXES]
    matrix: list[list[str]] = []
    for ts in all_ts:
        out_row = [ts]
        for t in trackers:
            cell = by_tracker.get(t, {}).get(ts)
            for s in SUFFIXES:
                out_row.append(cell[s] if cell is not None else "n/a")
        matrix.append(out_row)
    return header, matrix


def matrix_to_tsv(header: list[str], matrix: list[list[str]]) -> str:
    lines = ["\t".join(header)]
    lines.extend("\t".join(row) for row in matrix)
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_motion_wide.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/tabular.py tests/test_bids_motion_wide.py
git commit -m "feat(export): motion long->wide pivot with n/a fill"
```

---

### Task 3: `export/tabular.py` — `channels_rows` + `dicts_to_tsv`

**Files:**
- Modify: `src/htdp/export/tabular.py` (append)
- Test: `tests/test_bids_channels.py`

**Interfaces:**
- Consumes: `SUFFIXES` (Task 2).
- Produces:
  - `SUFFIX_META: dict[str, tuple[str, str, str]]` — suffix → `(type, component, units)`.
  - `CHANNELS_HEADER: list[str] = ["name", "type", "component", "tracked_point", "units", "sampling_frequency"]`
  - `channels_rows(trackers: list[str], fps: float) -> list[dict[str, str]]` — one row per `<tracker>_<suffix>`.
  - `dicts_to_tsv(header: list[str], rows: list[dict[str, str]]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_channels.py
from htdp.export.tabular import CHANNELS_HEADER, channels_rows, dicts_to_tsv


def test_one_row_per_tracker_suffix():
    rows = channels_rows(["a", "b"], 100.0)
    assert len(rows) == 16  # 2 trackers * 8 suffixes
    names = [r["name"] for r in rows]
    assert "a_x_m" in names and "b_quality" in names


def test_channel_types_and_units():
    rows = {r["name"]: r for r in channels_rows(["a"], 100.0)}
    assert rows["a_x_m"]["type"] == "POS" and rows["a_x_m"]["units"] == "m"
    assert rows["a_qw"]["type"] == "ORNT" and rows["a_qw"]["component"] == "quat_w"
    assert rows["a_quality"]["type"] == "MISC"
    assert rows["a_x_m"]["tracked_point"] == "a"
    assert rows["a_x_m"]["sampling_frequency"] == "100.0"


def test_dicts_to_tsv_orders_by_header():
    text = dicts_to_tsv(["a", "b"], [{"a": "1", "b": "2"}])
    assert text == "a\tb\n1\t2\n"


def test_channels_rows_serialize_with_header():
    text = dicts_to_tsv(CHANNELS_HEADER, channels_rows(["a"], 100.0))
    assert text.splitlines()[0] == "\t".join(CHANNELS_HEADER)
    assert len(text.splitlines()) == 1 + 8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_channels.py -v`
Expected: FAIL — `ImportError: cannot import name 'channels_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/export/tabular.py`:

```python
SUFFIX_META: dict[str, tuple[str, str, str]] = {
    "x_m": ("POS", "x", "m"),
    "y_m": ("POS", "y", "m"),
    "z_m": ("POS", "z", "m"),
    "qw": ("ORNT", "quat_w", "n/a"),
    "qx": ("ORNT", "quat_x", "n/a"),
    "qy": ("ORNT", "quat_y", "n/a"),
    "qz": ("ORNT", "quat_z", "n/a"),
    "quality": ("MISC", "n/a", "n/a"),
}
CHANNELS_HEADER: list[str] = [
    "name", "type", "component", "tracked_point", "units", "sampling_frequency",
]


def channels_rows(trackers: list[str], fps: float) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for t in trackers:
        for s in SUFFIXES:
            typ, component, units = SUFFIX_META[s]
            rows.append({
                "name": f"{t}_{s}",
                "type": typ,
                "component": component,
                "tracked_point": t,
                "units": units,
                "sampling_frequency": str(fps),
            })
    return rows


def dicts_to_tsv(header: list[str], rows: list[dict[str, str]]) -> str:
    lines = ["\t".join(header)]
    lines.extend("\t".join(r[h] for h in header) for r in rows)
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_channels.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/tabular.py tests/test_bids_channels.py
git commit -m "feat(export): BIDS channels_rows + dicts_to_tsv"
```

---

### Task 4: `export/tabular.py` — `events_rows`

**Files:**
- Modify: `src/htdp/export/tabular.py` (append)
- Test: `tests/test_bids_events.py`

**Interfaces:**
- Produces:
  - `EVENTS_HEADER: list[str] = ["onset", "duration", "trial_type", "value"]`
  - `events_rows(events: list[dict[str, str]]) -> list[dict[str, str]]` — `onset=timestamp_s`, `duration="n/a"`, `trial_type=label`, `value=event_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_events.py
from htdp.export.tabular import EVENTS_HEADER, dicts_to_tsv, events_rows


def _ev(ts: str, eid: str, label: str) -> dict[str, str]:
    return {"timestamp_s": ts, "event_id": eid, "label": label, "phase": "p",
            "source": "synthetic", "confidence": "1.000000", "notes": ""}


def test_events_rows_mapping():
    rows = events_rows([_ev("0.000000", "0", "start"), _ev("1.000000", "1", "grasp")])
    assert rows[0] == {"onset": "0.000000", "duration": "n/a",
                       "trial_type": "start", "value": "0"}
    assert rows[1]["trial_type"] == "grasp"


def test_events_serialize_with_header():
    text = dicts_to_tsv(EVENTS_HEADER, events_rows([_ev("0.000000", "0", "start")]))
    assert text.splitlines()[0] == "onset\tduration\ttrial_type\tvalue"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_events.py -v`
Expected: FAIL — `ImportError: cannot import name 'events_rows'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/export/tabular.py`:

```python
EVENTS_HEADER: list[str] = ["onset", "duration", "trial_type", "value"]


def events_rows(events: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "onset": e["timestamp_s"],
            "duration": "n/a",
            "trial_type": e["label"],
            "value": e["event_id"],
        }
        for e in events
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/tabular.py tests/test_bids_events.py
git commit -m "feat(export): BIDS events_rows mapping"
```

---

### Task 5: `export/sidecars.py` — JSON/text builders

**Files:**
- Create: `src/htdp/export/sidecars.py`
- Test: `tests/test_bids_sidecars.py`

**Interfaces:**
- Produces:
  - `PARTICIPANTS_HEADER: list[str] = ["participant_id", "cohort"]`
  - `dataset_description(session_id: str) -> dict[str, object]`
  - `motion_json(task: str, tracksys: str, trackers: list[str], fps: float) -> dict[str, object]`
  - `participants_rows(sub: str, cohort: str) -> list[dict[str, str]]`
  - `readme_text(session_id: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_sidecars.py
from htdp.export.sidecars import (
    PARTICIPANTS_HEADER,
    dataset_description,
    motion_json,
    participants_rows,
    readme_text,
)


def test_dataset_description_has_bids_version():
    d = dataset_description("synth-0001")
    assert d["BIDSVersion"] == "1.10.0"
    assert d["Name"] == "synth-0001"


def test_motion_json_channel_counts():
    d = motion_json("task", "vive", ["a", "b"], 100.0)
    assert d["SamplingFrequency"] == 100.0
    assert d["TrackingSystemName"] == "vive"
    assert d["POSChannelCount"] == 6  # 3 * 2 trackers
    assert d["ORNTChannelCount"] == 8  # 4 * 2 trackers
    assert d["MotionChannelCount"] == 16  # 8 * 2 trackers


def test_participants_rows_and_header():
    assert PARTICIPANTS_HEADER == ["participant_id", "cohort"]
    rows = participants_rows("p0001", "synthetic")
    assert rows == [{"participant_id": "sub-p0001", "cohort": "synthetic"}]


def test_readme_mentions_session():
    assert "synth-0001" in readme_text("synth-0001")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_sidecars.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.export.sidecars'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/export/sidecars.py
from __future__ import annotations

PARTICIPANTS_HEADER: list[str] = ["participant_id", "cohort"]


def dataset_description(session_id: str) -> dict[str, object]:
    return {
        "Name": session_id,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "GeneratedBy": [{"Name": "htdp"}],
    }


def motion_json(
    task: str, tracksys: str, trackers: list[str], fps: float
) -> dict[str, object]:
    n = len(trackers)
    return {
        "TaskName": task,
        "SamplingFrequency": fps,
        "TrackingSystemName": tracksys,
        "MotionChannelCount": 8 * n,
        "POSChannelCount": 3 * n,
        "ORNTChannelCount": 4 * n,
        "ACCELChannelCount": 0,
        "GYROChannelCount": 0,
        "MAGNChannelCount": 0,
        "SpatialAxes": "RFU",
    }


def participants_rows(sub: str, cohort: str) -> list[dict[str, str]]:
    return [{"participant_id": f"sub-{sub}", "cohort": cohort}]


def readme_text(session_id: str) -> str:
    return (
        f"# Motion-BIDS export of {session_id}\n\n"
        "Single-session export from the htdp pipeline. Motion is stored with an "
        "explicit `timestamp_s` column and `n/a` for missing samples (irregular "
        "sampling preserved, not resampled).\n"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_sidecars.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/sidecars.py tests/test_bids_sidecars.py
git commit -m "feat(export): BIDS dataset_description, motion_json, participants, README"
```

---

### Task 6: `export/bids.py` — orchestrator

**Files:**
- Create: `src/htdp/export/bids.py`
- Test: `tests/test_bids_export.py`

**Interfaces:**
- Consumes: `labels`, `tabular`, `sidecars` (Tasks 1–5); schemas `Session`/`DeviceConfig`; `io.canonical.dump_json`.
- Produces:
  - `class BidsExportError(RuntimeError)`
  - `export_motion_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> Path` — reads metadata + motion CSVs, derives labels, builds all content in memory, writes the BIDS tree, returns `out_dir`. Raises `BidsExportError` on missing `session.json`/`device_config.json`, no motion streams, or existing `out_dir` without `force`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bids_export.py
import json
from pathlib import Path

import pytest

from htdp.export.bids import BidsExportError, export_motion_bids
from htdp.synth.generate import generate_session

_STEM = "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
_MOTION_DIR = "sub-p0001/motion"


def _export(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return export_motion_bids(tmp_path / "raw" / "synth-0001", tmp_path / "bids")


def test_tree_layout(tmp_path: Path):
    out = _export(tmp_path)
    for rel in (
        "dataset_description.json",
        "README",
        "participants.tsv",
        f"{_MOTION_DIR}/{_STEM}_motion.tsv",
        f"{_MOTION_DIR}/{_STEM}_motion.json",
        f"{_MOTION_DIR}/{_STEM}_channels.tsv",
        f"{_MOTION_DIR}/sub-p0001_task-reachgraspplace_events.tsv",
    ):
        assert (out / rel).exists(), rel


def test_motion_tsv_header_and_gap(tmp_path: Path):
    out = _export(tmp_path)
    lines = (out / f"{_MOTION_DIR}/{_STEM}_motion.tsv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    assert header[0] == "timestamp_s"
    assert "right_wrist_x_m" in header and "object_quality" in header
    # left_wrist has a dropped-sample gap -> at least one row carries n/a for it
    lw_idx = header.index("left_wrist_x_m")
    assert any(row.split("\t")[lw_idx] == "n/a" for row in lines[1:])


def test_channels_row_count_matches_columns(tmp_path: Path):
    out = _export(tmp_path)
    motion_lines = (out / f"{_MOTION_DIR}/{_STEM}_motion.tsv").read_text().splitlines()
    data_cols = len(motion_lines[0].split("\t")) - 1  # minus timestamp_s
    chan_lines = (out / f"{_MOTION_DIR}/{_STEM}_channels.tsv").read_text().splitlines()
    assert len(chan_lines) - 1 == data_cols  # minus header


def test_dataset_description_parses(tmp_path: Path):
    out = _export(tmp_path)
    d = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert d["BIDSVersion"] == "1.10.0"


def test_events_onsets_match(tmp_path: Path):
    out = _export(tmp_path)
    ev = (out / f"{_MOTION_DIR}/sub-p0001_task-reachgraspplace_events.tsv").read_text().splitlines()
    assert ev[0] == "onset\tduration\ttrial_type\tvalue"
    assert ev[1].split("\t")[0] == "0.000000"  # first event onset


def test_existing_out_dir_requires_force(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    export_motion_bids(src, tmp_path / "bids")
    with pytest.raises(BidsExportError):
        export_motion_bids(src, tmp_path / "bids")
    export_motion_bids(src, tmp_path / "bids", force=True)  # ok


def test_missing_session_json_raises(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    (src / "session.json").unlink()
    with pytest.raises(BidsExportError):
        export_motion_bids(src, tmp_path / "bids")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bids_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.export.bids'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/export/bids.py
from __future__ import annotations

import shutil
from pathlib import Path

from htdp.export.labels import entity_stem, sanitize
from htdp.export.sidecars import (
    PARTICIPANTS_HEADER,
    dataset_description,
    motion_json,
    participants_rows,
    readme_text,
)
from htdp.export.tabular import (
    CHANNELS_HEADER,
    EVENTS_HEADER,
    channels_rows,
    dicts_to_tsv,
    events_rows,
    matrix_to_tsv,
    motion_wide,
)
from htdp.io.canonical import dump_json
from htdp.schemas.models import DeviceConfig, Session


class BidsExportError(RuntimeError):
    """Raised when a raw session cannot be exported to Motion-BIDS."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def export_motion_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> Path:
    session_path = raw_dir / "session.json"
    device_path = raw_dir / "device_config.json"
    if not session_path.exists() or not device_path.exists():
        raise BidsExportError(f"raw session missing metadata: {raw_dir}")

    session = Session.model_validate_json(session_path.read_text(encoding="utf-8"))
    device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))
    motion_streams = [s for s in device.streams if s.role == "motion"]
    if not motion_streams:
        raise BidsExportError(f"no motion streams in {raw_dir}")

    trackers = [s.name for s in motion_streams]
    fps = motion_streams[0].rate_hz or 100.0
    rows: list[dict[str, str]] = []
    for s in motion_streams:
        rows.extend(_read_csv(raw_dir / s.path))
    events_path = raw_dir / "streams/events.csv"
    events = _read_csv(events_path) if events_path.exists() else []

    sub = sanitize(session.participant_id)
    task = sanitize(session.protocol_id)
    tracksys = sanitize(device.device_config_id)
    stem = entity_stem(sub, task, tracksys)

    m_header, m_matrix = motion_wide(rows, trackers)
    motion_tsv = matrix_to_tsv(m_header, m_matrix)
    channels_tsv = dicts_to_tsv(CHANNELS_HEADER, channels_rows(trackers, fps))
    events_tsv = dicts_to_tsv(EVENTS_HEADER, events_rows(events))
    participants_tsv = dicts_to_tsv(
        PARTICIPANTS_HEADER, participants_rows(sub, "n/a")
    )
    desc = dataset_description(session.session_id)
    sidecar = motion_json(task, tracksys, trackers, fps)
    readme = readme_text(session.session_id)

    if out_dir.exists():
        if not force:
            raise BidsExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    motion_dir = out_dir / f"sub-{sub}" / "motion"
    motion_dir.mkdir(parents=True)

    dump_json(desc, out_dir / "dataset_description.json")
    _write_text(out_dir / "README", readme)
    _write_text(out_dir / "participants.tsv", participants_tsv)
    _write_text(motion_dir / f"{stem}_motion.tsv", motion_tsv)
    dump_json(sidecar, motion_dir / f"{stem}_motion.json")
    _write_text(motion_dir / f"{stem}_channels.tsv", channels_tsv)
    _write_text(motion_dir / f"sub-{sub}_task-{task}_events.tsv", events_tsv)
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bids_export.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/bids.py tests/test_bids_export.py
git commit -m "feat(export): export_motion_bids orchestrator"
```

---

### Task 7: CLI `export-bids` command

**Files:**
- Modify: `src/htdp/cli.py` (add command after `ingest_video`)
- Test: `tests/test_cli_shell.py` (append; reuse the file's `CliRunner`/`app` pattern)

**Interfaces:**
- Consumes: `export_motion_bids`, `BidsExportError` (Task 6).
- Produces: `htdp export-bids <raw_dir> <out_dir> [--force]`. Exits `1` on `BidsExportError`, printing `error: ...` to stderr.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_shell.py`:

```python
def test_export_bids_happy_and_missing(tmp_path):
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    runner = CliRunner()
    ok = runner.invoke(app, ["export-bids", str(src), str(tmp_path / "bids")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bids" / "dataset_description.json").exists()

    bad = runner.invoke(app, ["export-bids", str(tmp_path / "nope"), str(tmp_path / "b2")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shell.py -k export_bids -v`
Expected: FAIL — no command `export-bids` (usage error / exit 2)

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `ingest_video` command:

```python
@app.command()
def export_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a raw session to a minimal Motion-BIDS dataset tree."""
    from htdp.export.bids import BidsExportError, export_motion_bids

    try:
        d = export_motion_bids(raw_dir, out_dir, force=force)
    except BidsExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_shell.py -k export_bids -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shell.py
git commit -m "feat(export): add htdp export-bids CLI command"
```

---

### Task 8: Docs + mypy gate + full suite

**Files:**
- Modify: `AGENTS.md` (typecheck targets + usage)
- Modify: `STATUS.md` (typecheck targets)
- Modify: `docs/DATA_CONTRACT.md` (Motion-BIDS export note)
- Modify: `docs/ROADMAP.md` (mark Motion-BIDS in progress)

**Interfaces:** none.

- [ ] **Step 1: Add `src/htdp/export` to the mypy gate**

In `AGENTS.md`, change the Typecheck line to:

```
Typecheck: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export`
```

Make the identical edit to the `mypy` line in `STATUS.md`.

- [ ] **Step 2: Run the typecheck to verify export is clean**

Run: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export`
Expected: `Success: no issues found`
(If issues appear, fix annotations in the offending `export` module before continuing.)

- [ ] **Step 3: Update docs**

`docs/DATA_CONTRACT.md` — add a "Motion-BIDS export" note: single raw session →
minimal BIDS tree; irregular sampling preserved via an explicit `timestamp_s` column
and `n/a` fill (no resampling); `defect_tag` not exported; BIDS version 1.10.0;
labels sanitized to alphanumerics.

`AGENTS.md` — add usage `htdp export-bids <raw_dir> <out_dir> [--force]`; note it is a
**read-only export** (writes a separate tree, never mutates raw/processed/releases).

`docs/ROADMAP.md` — change the "Motion-BIDS export" bullet to mark progress
(e.g. append `— **in progress (single-session export landed)**`).

- [ ] **Step 4: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass (only the pre-existing mujoco replay skip remains if the replay extra is absent); mypy `Success`.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md STATUS.md docs/DATA_CONTRACT.md docs/ROADMAP.md
git commit -m "docs(export): document Motion-BIDS export and add mypy target"
```

---

## Self-Review

**Spec coverage** (`2026-06-21-motion-bids-export-design.md`):
- `labels.py` sanitize + entity_stem → Task 1. ✓
- `tabular.py` motion_wide (union ts, n/a fill) → Task 2; channels_rows (POS/ORNT/MISC) → Task 3; events_rows → Task 4; TSV helpers → Tasks 2–3. ✓
- `sidecars.py` dataset_description / motion_json / participants / README → Task 5. ✓
- `bids.py` orchestrator (read raw, build, write tree, errors, force) → Task 6. ✓
- CLI `export-bids` → Task 7. ✓
- Single session, raw source, explicit timestamp column, `defect_tag` excluded, no resampling → Tasks 2 & 6. ✓
- Read-only, no schema change, stdlib only → throughout. ✓
- Docs + mypy target → Task 8. ✓
- Non-goals (regular-grid resampling, release/multi-subject, EEG/video BIDS, external validator) — none implemented. ✓

**No-touch check:** only new files under `src/htdp/export/` + new tests, plus appends to `cli.py`, `AGENTS.md`, `STATUS.md`, `docs/*`. No existing stage or schema modified.

**Placeholder scan:** none — every code/test step is concrete.

**Type consistency:** `sanitize`/`entity_stem` (Task 1) used in Task 6; `SUFFIXES` (Task 2) drives `channels_rows` (Task 3) and `motion_wide` header; `motion_wide -> (list[str], list[list[str]])` consumed by `matrix_to_tsv`; `channels_rows`/`events_rows`/`participants_rows -> list[dict[str,str]]` consumed by `dicts_to_tsv` with the matching `*_HEADER`; `motion_json(task, tracksys, trackers, fps)` and `dataset_description(session_id)` signatures match the Task 6 calls; `export_motion_bids(raw_dir, out_dir, force)` matches the Task 7 CLI call. Every TSV builder pairs with its exported `*_HEADER` constant.
```
