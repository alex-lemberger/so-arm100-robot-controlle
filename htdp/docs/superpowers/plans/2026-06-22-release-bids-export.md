# Release-Level BIDS Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp export-release-bids`: export a packaged release into one multi-subject BIDS dataset, reusing the per-session Motion-BIDS + BrainVision EEG-BIDS writers. The dataset inherits the release's consent filtering.

**Architecture:** Refactor `export/bids.py` to extract a per-session writer `_write_session_bids(out_dir, raw_dir, ses)` (with an optional `ses` entity); rewire single-session `export_motion_bids` to use it with `ses=None` (byte-identical output); add `export_release_bids` that loops a release's sessions, adds `ses-` on participant collision, and aggregates participants. Add a CLI command. No schema change.

**Tech Stack:** Python ≥3.11, pydantic v2, typer, pytest. `pyxdf` (optional) only for the eeg-inheritance test.

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` on `src/htdp/export` (gate target).
- ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check`.
- JSON via `io.canonical.dump_json`; text/TSV via `_write_text` (`newline="\n"`).
- **Regression safety (critical):** single-session `export_motion_bids` must produce byte-identical output after the refactor — the slice-4/6 tests (`test_bids_export.py`, `test_eeg_bids_export.py`) must stay green.
- **No partial writes:** validate the source before creating `out_dir`; build per-session content under the force-guarded tree.
- **No persisted-schema change** → no JSON-Schema re-export.
- Edits limited to `src/htdp/export/bids.py` and `src/htdp/cli.py` (+ new tests, docs). Do NOT touch other `export/*` modules, `ingest`, `release`, `synth`, `schemas`, etc.
- Deterministic: same release → identical BIDS tree.

**Reference — release layout** (`release/package.py`): `releases/<name>/data/<sid>/` are consent-filtered raw-session folders (each has `session.json`, `device_config.json`, `streams/…`); plus `manifest.json`, `participants.csv`, `README.md`, `LICENSE`, `protocol.md`, `checksums.sha256`.

**Reference — single-session output (must be preserved):** `sub-<sub>/motion/<sub>_task-<task>_tracksys-<tracksys>_motion.tsv|.json|_channels.tsv`, `sub-<sub>/motion/sub-<sub>_task-<task>_events.tsv`, `sub-<sub>/eeg/<sub>_task-<task>_acq-<id>_eeg.{vhdr,vmrk,eeg,json}|_channels.tsv`, plus top-level `dataset_description.json`/`README`/`participants.tsv`. (`sub = sanitize(participant_id)`, `task = sanitize(protocol_id)`, `tracksys = sanitize(device_config_id)`.)

---

### Task 1: refactor `bids.py` — extract `_write_session_bids`

**Files:**
- Modify (full rewrite): `src/htdp/export/bids.py`
- Test: `tests/test_release_bids_session.py`

**Interfaces:**
- Produces:
  - `_write_session_bids(out_dir: Path, raw_dir: Path, ses: str | None) -> dict[str, str]` — writes `sub-<sub>[/ses-<ses>]/motion(+eeg)` into an existing `out_dir`; returns `{"participant_id": f"sub-{sub}", "cohort": "n/a"}`. Raises `BidsExportError` on missing metadata or no motion streams.
  - `export_motion_bids(raw_dir, out_dir, force)` — unchanged public behaviour, now built on `_write_session_bids(ses=None)`.
- `BidsExportError`, `_read_csv`, `_read_eeg_csv`, `_write_text` unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_bids_session.py
from pathlib import Path

from htdp.export.bids import _write_session_bids
from htdp.synth.generate import generate_session


def test_ses_entity_in_path_and_filename(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = tmp_path / "bids"
    out.mkdir()
    row = _write_session_bids(out, tmp_path / "raw" / "synth-0001", ses="01")
    motion = out / "sub-p0001" / "ses-01" / "motion"
    assert (motion / "sub-p0001_ses-01_task-reachgraspplace_tracksys-vivesynth_motion.tsv").exists()
    assert (motion / "sub-p0001_ses-01_task-reachgraspplace_events.tsv").exists()
    assert row == {"participant_id": "sub-p0001", "cohort": "n/a"}


def test_no_ses_flat_layout(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = tmp_path / "bids"
    out.mkdir()
    _write_session_bids(out, tmp_path / "raw" / "synth-0001", ses=None)
    stem = "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
    assert (out / "sub-p0001" / "motion" / f"{stem}_motion.tsv").exists()
    assert not (out / "sub-p0001" / "ses-01").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_bids_session.py -v`
Expected: FAIL — `ImportError: cannot import name '_write_session_bids'`

- [ ] **Step 3: Write minimal implementation**

Replace the entire contents of `src/htdp/export/bids.py` with:

```python
from __future__ import annotations

import shutil
from pathlib import Path

from htdp.export.eeg_bids import (
    EEG_CHANNELS_HEADER,
    eeg_binary,
    eeg_channels_rows,
    eeg_json,
    estimate_fs,
    vhdr_text,
    vmrk_text,
)
from htdp.export.labels import sanitize
from htdp.export.sidecars import (
    PARTICIPANTS_HEADER,
    dataset_description,
    motion_json,
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
    """Raised when a session/release cannot be exported to BIDS."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


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


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_session_bids(out_dir: Path, raw_dir: Path, ses: str | None) -> dict[str, str]:
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
    ent = f"sub-{sub}" + (f"_ses-{ses}" if ses else "")
    subj_dir = out_dir / f"sub-{sub}"
    if ses:
        subj_dir = subj_dir / f"ses-{ses}"

    motion_dir = subj_dir / "motion"
    motion_dir.mkdir(parents=True)
    m_stem = f"{ent}_task-{task}_tracksys-{tracksys}"
    m_header, m_matrix = motion_wide(rows, trackers)
    _write_text(motion_dir / f"{m_stem}_motion.tsv", matrix_to_tsv(m_header, m_matrix))
    dump_json(motion_json(task, tracksys, trackers, fps), motion_dir / f"{m_stem}_motion.json")
    _write_text(
        motion_dir / f"{m_stem}_channels.tsv",
        dicts_to_tsv(CHANNELS_HEADER, channels_rows(trackers, fps)),
    )
    _write_text(
        motion_dir / f"{ent}_task-{task}_events.tsv",
        dicts_to_tsv(EVENTS_HEADER, events_rows(events)),
    )

    eeg_streams = [s for s in device.streams if s.role == "eeg"]
    if eeg_streams:
        eeg_dir = subj_dir / "eeg"
        eeg_dir.mkdir(parents=True)
        for s in eeg_streams:
            labels, timestamps, samples = _read_eeg_csv(raw_dir / s.path)
            try:
                fs = estimate_fs(timestamps)
            except ValueError as exc:
                raise BidsExportError(f"eeg stream '{s.name}': {exc}") from exc
            acq = sanitize(s.name)
            eeg_stem = f"{ent}_task-{task}_acq-{acq}"
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vhdr", vhdr_text(eeg_stem, labels, fs))
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vmrk", vmrk_text(eeg_stem))
            (eeg_dir / f"{eeg_stem}_eeg.eeg").write_bytes(eeg_binary(samples))
            dump_json(eeg_json(task, len(labels), fs), eeg_dir / f"{eeg_stem}_eeg.json")
            _write_text(
                eeg_dir / f"{eeg_stem}_channels.tsv",
                dicts_to_tsv(EEG_CHANNELS_HEADER, eeg_channels_rows(labels)),
            )

    return {"participant_id": f"sub-{sub}", "cohort": "n/a"}


def export_motion_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> Path:
    session_path = raw_dir / "session.json"
    if not session_path.exists() or not (raw_dir / "device_config.json").exists():
        raise BidsExportError(f"raw session missing metadata: {raw_dir}")
    session = Session.model_validate_json(session_path.read_text(encoding="utf-8"))

    if out_dir.exists():
        if not force:
            raise BidsExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    row = _write_session_bids(out_dir, raw_dir, ses=None)
    dump_json(dataset_description(session.session_id), out_dir / "dataset_description.json")
    _write_text(out_dir / "README", readme_text(session.session_id))
    _write_text(out_dir / "participants.tsv", dicts_to_tsv(PARTICIPANTS_HEADER, [row]))
    return out_dir
```

(Note: `entity_stem` and `participants_rows` imports are intentionally dropped — they are no longer used; their removal is part of this rewrite. ruff will flag them if left in.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_bids_session.py tests/test_bids_export.py tests/test_eeg_bids_export.py -v`
Expected: PASS — new ses tests + all existing slice-4/6 export tests green (single-session output unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/bids.py tests/test_release_bids_session.py
git commit -m "refactor(export): extract _write_session_bids with optional ses entity"
```

---

### Task 2: `bids.py` — `export_release_bids`

**Files:**
- Modify: `src/htdp/export/bids.py` (add import + function)
- Test: `tests/test_release_bids_export.py`

**Interfaces:**
- Consumes: `_write_session_bids`, `sanitize`, `dataset_description`, `readme_text`, `dicts_to_tsv`, `PARTICIPANTS_HEADER`, `Session`.
- Produces: `export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> Path` — loops `release_dir/data/<sid>/`, assigns `ses=sanitize(session_id)` when a participant repeats (else `None`), aggregates deduped participants, writes top-level `dataset_description`(release name)/README/participants once. Raises `BidsExportError` on missing `data/`, empty release, or existing `out_dir` without `force`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_bids_export.py
import json
from pathlib import Path

import pytest

from htdp.export.bids import BidsExportError, export_release_bids
from htdp.io.checksums import write_checksums
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    return package_release(
        ["synth-0001", "synth-0002"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )


def test_two_subjects_and_aggregated_participants(tmp_path: Path):
    out = export_release_bids(_release(tmp_path), tmp_path / "bids")
    assert (out / "sub-p0001" / "motion").exists()
    assert (out / "sub-p0002" / "motion").exists()
    parts = (out / "participants.tsv").read_text(encoding="utf-8").splitlines()
    assert parts[0] == "participant_id\tcohort"
    assert len(parts) == 3  # header + 2 subjects
    desc = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert desc["Name"] == "rel"


def test_participant_collision_adds_ses(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    sp = tmp_path / "raw" / "synth-0002" / "session.json"
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["participant_id"] = "p-0001"  # force collision
    sp.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(tmp_path / "raw" / "synth-0002")
    rel = package_release(
        ["synth-0001", "synth-0002"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )
    out = export_release_bids(rel, tmp_path / "bids")
    assert (out / "sub-p0001" / "ses-synth0001" / "motion").exists()
    assert (out / "sub-p0001" / "ses-synth0002" / "motion").exists()
    parts = (out / "participants.tsv").read_text(encoding="utf-8").splitlines()
    assert len(parts) == 2  # header + 1 deduped subject


def test_missing_data_dir_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(BidsExportError):
        export_release_bids(tmp_path / "empty", tmp_path / "bids")


def test_force_overwrite(tmp_path: Path):
    rel = _release(tmp_path)
    export_release_bids(rel, tmp_path / "bids")
    with pytest.raises(BidsExportError):
        export_release_bids(rel, tmp_path / "bids")
    export_release_bids(rel, tmp_path / "bids", force=True)  # ok
```

Append the consent-inheritance test (pyxdf-gated) in the same file:

```python
def test_forbidden_eeg_absent_from_release_bids(tmp_path: Path):
    pytest.importorskip("pyxdf")
    import json as _json

    from htdp.ingest.session import ingest_xdf
    from tests._xdf_writer import build_sidecar, write_xdf

    src = generate_session(tmp_path / "sr", seed=1)
    eeg = ("eeg", ["Fp1", "Cz"], [0.0, 0.004], [[1.0, 2.0], [1.5, 2.5]])
    write_xdf(src, tmp_path / "x.xdf", eeg=eeg)
    sc = tmp_path / "i.json"
    sc.write_text(_json.dumps(build_sidecar(src, eeg=("eeg", ["Fp1", "Cz"]))), encoding="utf-8")
    session = ingest_xdf(tmp_path / "x.xdf", sc, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = _json.loads(consent.read_text(encoding="utf-8"))
    data.update({
        "distribute_raw_eeg": False,
        "commercial_use": True, "model_training": True,
        "third_party_access": True, "public_release": True, "internal_only": False,
    })
    consent.write_text(_json.dumps(data), encoding="utf-8")
    write_checksums(session)
    rel = package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )
    out = export_release_bids(rel, tmp_path / "bids")
    assert (out / "sub-p0001" / "motion").exists()
    assert not (out / "sub-p0001" / "eeg").exists()  # eeg dropped during packaging
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_bids_export.py -v`
Expected: FAIL — `ImportError: cannot import name 'export_release_bids'`

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/export/bids.py`, add to the top imports:

```python
from collections import Counter
```

Append the function at the end of the file:

```python
def export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> Path:
    data_dir = release_dir / "data"
    if not data_dir.is_dir():
        raise BidsExportError(f"release has no data/ directory: {release_dir}")
    session_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    if not session_dirs:
        raise BidsExportError(f"release has no sessions: {release_dir}")

    subs: list[str] = []
    for sd in session_dirs:
        session = Session.model_validate_json((sd / "session.json").read_text(encoding="utf-8"))
        subs.append(sanitize(session.participant_id))
    counts = Counter(subs)

    if out_dir.exists():
        if not force:
            raise BidsExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for sd, sub in zip(session_dirs, subs):
        ses = sanitize(sd.name) if counts[sub] > 1 else None
        row = _write_session_bids(out_dir, sd, ses)
        if row["participant_id"] not in seen:
            rows.append(row)
            seen.add(row["participant_id"])

    dump_json(dataset_description(release_dir.name), out_dir / "dataset_description.json")
    _write_text(out_dir / "README", readme_text(release_dir.name))
    _write_text(out_dir / "participants.tsv", dicts_to_tsv(PARTICIPANTS_HEADER, rows))
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_bids_export.py -v`
Expected: PASS (4 passed + the eeg-inheritance test, which SKIPs only without `pyxdf`).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/export/bids.py tests/test_release_bids_export.py
git commit -m "feat(export): export_release_bids multi-subject dataset"
```

---

### Task 3: CLI `export-release-bids`

**Files:**
- Modify: `src/htdp/cli.py` (add command after `export_bids`)
- Test: `tests/test_cli_shell.py` (append)

**Interfaces:**
- Consumes: `export_release_bids`, `BidsExportError`.
- Produces: `htdp export-release-bids <release_dir> <out_dir> [--force]`; exit 1 on `BidsExportError`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_shell.py`:

```python
def test_export_release_bids_happy_and_missing(tmp_path):
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.release.package import package_release
    from htdp.schemas.enums import ReleaseProfile
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    rel = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )
    runner = CliRunner()
    ok = runner.invoke(app, ["export-release-bids", str(rel), str(tmp_path / "bids")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bids" / "dataset_description.json").exists()

    bad = runner.invoke(app, ["export-release-bids", str(tmp_path / "nope"), str(tmp_path / "b2")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shell.py -k export_release_bids -v`
Expected: FAIL — no command `export-release-bids` (usage error / exit 2)

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `export_bids` command:

```python
@app.command()
def export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a packaged release to a multi-subject BIDS dataset."""
    from htdp.export.bids import BidsExportError, export_release_bids as _export_release_bids

    try:
        d = _export_release_bids(release_dir, out_dir, force=force)
    except BidsExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_shell.py -k export_release_bids -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shell.py
git commit -m "feat(export): add htdp export-release-bids CLI command"
```

---

### Task 4: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md`, `AGENTS.md`, `docs/ROADMAP.md`

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — add a "Release-level BIDS export" note: a packaged release
exports to one multi-subject BIDS dataset; `sub-<participant>` (flat), with
`ses-<session>` only when a participant has more than one session in the release;
`dataset_description.Name` is the release name; the dataset inherits the release's
consent filtering (modalities dropped during packaging are absent).

`AGENTS.md` — add usage `htdp export-release-bids <release_dir> <out_dir> [--force]`;
note it is a read-only export of a packaged release.

`docs/ROADMAP.md` — mark release-level BIDS in progress/done.

- [ ] **Step 2: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass (only the pre-existing mujoco replay skip if the replay extra is absent; the eeg-inheritance test RUNs with `pyxdf` installed); mypy `Success`.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(export): document release-level BIDS export"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-release-bids-export-design.md`):
- `_write_session_bids` with optional `ses`, returns participant row, motion+eeg, raises on missing metadata/motion → Task 1. ✓
- `export_motion_bids` rewired, single-session output unchanged → Task 1 (existing tests in Step 4). ✓
- `export_release_bids` loop, collision `ses`, deduped participants, release-name dataset → Task 2. ✓
- Consent inheritance (forbidden eeg absent in release BIDS) → Task 2 (pyxdf-gated). ✓
- Errors (missing data/, empty, existing out_dir) → Task 2. ✓
- CLI `export-release-bids` → Task 3. ✓
- Docs (DATA_CONTRACT, AGENTS, ROADMAP), no schema re-export → Task 4. ✓
- Non-goals (multi-session-per-subject beyond ses-on-collision, scans.tsv/derivatives, cross-session events, other formats) — none implemented. ✓

**No-touch check:** edits limited to `export/bids.py` + `cli.py` + new tests + docs. Other `export/*` modules, ingest, release, synth, schemas untouched.

**Placeholder scan:** none — every code/test step is concrete.

**Regression note:** Task 1 is a full rewrite of `bids.py`; the `ses=None` path reproduces the prior filenames/dirs/contents exactly (motion stem `sub-<sub>_task-<task>_tracksys-<tracksys>`, events `sub-<sub>_task-<task>_events.tsv`, eeg stem `sub-<sub>_task-<task>_acq-<id>`, top-level files identical), so `test_bids_export.py` / `test_eeg_bids_export.py` are rerun in Step 4 as the guard.

**Type consistency:** `_write_session_bids(out_dir, raw_dir, ses) -> dict[str,str]` matches both callers (`export_motion_bids` with `ses=None`, `export_release_bids` with `ses=str|None`); `dataset_description`/`readme_text` take a name string (session id or release name); participant rows `{"participant_id","cohort"}` feed `dicts_to_tsv(PARTICIPANTS_HEADER, rows)`; `export_release_bids(release_dir, out_dir, force)` matches the Task 3 CLI call.
```
