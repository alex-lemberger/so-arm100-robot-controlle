# Human-Task Dataset Pipeline v0.1 (Synthetic Spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a filesystem-only Python CLI that turns one synthetic reach-grasp-place session into a trusted, reproducible dataset release — defects detected by QC, consent enforced, and a MuJoCo mocap replay proving the release is usable.

**Architecture:** A Python package `htdp` exposing a `typer` CLI with six commands (`synth, validate, process, qc, package, replay`) over three on-disk tiers (`data/raw` immutable, `data/processed` regenerable, `data/releases` versioned product). Pydantic schemas are the data contract; canonical JSON/CSV serialization + checksums give reproducibility. No servers, no hardware, no database.

**Tech Stack:** Python 3.11+, `uv` (+ `uv.lock`), `typer`, `pydantic` v2, `polars` (CSV/Parquet), `pyarrow`, `jinja2` (QC HTML), `pytest`, `ruff`, `mypy`, `mujoco` (optional, replay only).

**Spec:** `docs/superpowers/specs/2026-06-20-human-task-dataset-pipeline-v0.1-design.md`

## Global Constraints

- v0.1 is **offline, deterministic, synthetic, filesystem-only**. No Postgres/MinIO/FastAPI/Docker, no real hardware/LSL/XDF, no video/EEG data, no ROS/BIDS, no IK/robot replay, no dashboard. (spec §0, §16)
- Raw data is **immutable**: `process` never writes under `data/raw/`; `synth` refuses overwrite without `--force`. (spec §6.1)
- **Never bypass consent checks.** `package` blocks on conflict and writes nothing (atomic staging). (spec §8)
- **Reproducibility:** same code + `uv.lock` + platform class + seed + inputs → identical release-manifest checksums. JSON sorted-keys/UTF-8; CSV stable column order + fixed float precision (6 dp) + `\n` line endings + UTF-8; generated timestamps seed-derived; tool versions recorded but excluded from reproducibility checksum. (spec §11)
- **Coordinate frame:** meters, seconds, right-handed (x=right, y=forward, z=up), quaternion order `w,x,y,z`. (spec §4.1)
- **QC severity:** `pass`/`warn`/`fail`. Dropped samples + clock drift = `warn`. Missing stream / bad timestamps / checksum mismatch / malformed consent = `fail`. (spec §7.1)
- Motion CSV columns: `timestamp_s,tracker_id,x_m,y_m,z_m,qw,qx,qy,qz,quality,defect_tag`. (spec §4.2)
- Event CSV columns: `timestamp_s,event_id,label,phase,source,confidence,notes`. (spec §4.3)
- Quality gate before every commit: `ruff format --check . && ruff check . && pytest`. `mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io`. (spec §12)
- Keep fixtures tiny and deterministic. Update schemas and docs together. Make errors explicit.

---

### Task 1: Project scaffold + tooling + CLI shell

**Files:**
- Create: `pyproject.toml`, `uv.lock` (generated), `.gitignore`, `README.md`
- Create: `src/htdp/__init__.py`, `src/htdp/cli.py`
- Create: `tests/__init__.py`, `tests/test_cli_shell.py`

**Interfaces:**
- Produces: `htdp.cli.app` (a `typer.Typer`); console-script `htdp`. Six command stubs registered: `synth, validate, process, qc, package, replay`.

- [ ] **Step 1: Initialize the project with uv**

```bash
mkdir -p human-task-dataset-pipeline && cd human-task-dataset-pipeline
git init
uv init --package --name htdp --python 3.11
mkdir -p src/htdp tests
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "htdp"
version = "0.1.0"
description = "Consent-based human-task dataset pipeline (synthetic spine)"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydantic>=2.7",
    "polars>=1.0",
    "pyarrow>=16.0",
    "jinja2>=3.1",
]

[project.optional-dependencies]
replay = ["mujoco>=3.1"]
dev = ["pytest>=8.0", "ruff>=0.5", "mypy>=1.10"]

[project.scripts]
htdp = "htdp.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.format]
line-ending = "lf"

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Install and lock**

```bash
uv sync --extra dev
```
Expected: creates `.venv` and `uv.lock`.

- [ ] **Step 4: Write the failing test**

```python
# tests/test_cli_shell.py
from typer.testing import CliRunner
from htdp.cli import app

runner = CliRunner()

def test_cli_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("synth", "validate", "process", "qc", "package", "replay"):
        assert cmd in result.stdout
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shell.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.cli'`

- [ ] **Step 6: Write the CLI shell**

```python
# src/htdp/cli.py
from pathlib import Path
import typer

app = typer.Typer(help="Human-task dataset pipeline (v0.1 synthetic spine)", no_args_is_help=True)

@app.command()
def synth(out: Path = typer.Option(..., "--out"), seed: int = 0, force: bool = False) -> None:
    """Generate a synthetic session."""
    raise typer.Exit(0)

@app.command()
def validate(raw_dir: Path) -> None:
    """Validate a raw session folder."""
    raise typer.Exit(0)

@app.command()
def process(raw_dir: Path) -> None:
    """Process a raw session into Parquet."""
    raise typer.Exit(0)

@app.command()
def qc(processed_dir: Path) -> None:
    """Generate a QC report."""
    raise typer.Exit(0)

@app.command()
def package(session_ids: list[str], release: str = typer.Option(...), profile: str = typer.Option(...)) -> None:
    """Package a dataset release (consent-gated)."""
    raise typer.Exit(0)

@app.command()
def replay(release_dir: Path) -> None:
    """Replay a packaged release in MuJoCo."""
    raise typer.Exit(0)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_shell.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: scaffold htdp package, tooling, and CLI shell"
```

---

### Task 2: Schemas + JSON Schema export

**Files:**
- Create: `src/htdp/schemas/__init__.py`, `src/htdp/schemas/models.py`, `src/htdp/schemas/enums.py`, `src/htdp/schemas/export.py`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces enums: `EventLabel`, `QcStatus`, `CheckSeverity`, `ReleaseProfile`, `ProcessingStatus`.
- Produces models: `Consent`, `CoordinateFrame`, `StreamRef`, `DeviceConfig`, `EventMarker`, `Participant`, `TaskProtocol`, `Session`, `Manifest`, `DatasetRelease`.
- Produces `export_json_schemas(out_dir: Path) -> list[Path]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schemas.py
import pytest
from pydantic import ValidationError
from htdp.schemas.enums import EventLabel, ReleaseProfile
from htdp.schemas.models import Consent, Session

def test_consent_requires_form_version():
    with pytest.raises(ValidationError):
        Consent()  # type: ignore[call-arg]

def test_consent_defaults_are_restrictive():
    c = Consent(consent_form_version="v1")
    assert c.commercial_use is False
    assert c.model_training is False

def test_event_label_enum_values():
    assert {e.value for e in EventLabel} == {"start", "grasp", "release", "place", "stop"}

def test_session_round_trips_json():
    s = Session(
        session_id="s-001", participant_id="p-001", protocol_id="reach-grasp-place",
        consent_form_version="v1", device_config_id="vive-synth",
        start_time_s=0.0, qc_status="pass", processing_status="processed",
    )
    assert Session.model_validate_json(s.model_dump_json()) == s

def test_release_profiles_exist():
    assert {p.value for p in ReleaseProfile} == {"internal_research", "public_sample", "commercial_dataset"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.schemas'`

- [ ] **Step 3: Write the enums**

```python
# src/htdp/schemas/enums.py
from enum import Enum

class EventLabel(str, Enum):
    START = "start"
    GRASP = "grasp"
    RELEASE = "release"
    PLACE = "place"
    STOP = "stop"

class QcStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

class CheckSeverity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

class ProcessingStatus(str, Enum):
    RAW = "raw"
    PROCESSED = "processed"

class ReleaseProfile(str, Enum):
    INTERNAL_RESEARCH = "internal_research"
    PUBLIC_SAMPLE = "public_sample"
    COMMERCIAL_DATASET = "commercial_dataset"
```

- [ ] **Step 4: Write the models**

```python
# src/htdp/schemas/models.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from htdp.schemas.enums import EventLabel, ProcessingStatus, QcStatus

class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Consent(_Base):
    consent_form_version: str
    commercial_use: bool = False
    distribute_raw_video: bool = False
    distribute_raw_eeg: bool = False
    derived_features_only: bool = False
    model_training: bool = False
    public_release: bool = False
    internal_only: bool = True
    third_party_access: bool = False
    delete_after: str | None = None  # ISO date, seed-derived in synth

class CoordinateFrame(_Base):
    units: str = "meters"
    time_unit: str = "seconds"
    handedness: str = "right"
    axes: str = "x=right,y=forward,z=up"
    quaternion_order: str = "w,x,y,z"

class StreamRef(_Base):
    name: str
    path: str
    fmt: str
    role: str
    rate_hz: float | None = None

class DeviceConfig(_Base):
    device_config_id: str
    frame: CoordinateFrame = Field(default_factory=CoordinateFrame)
    streams: list[StreamRef] = Field(default_factory=list)

class EventMarker(_Base):
    timestamp_s: float
    event_id: int
    label: EventLabel
    phase: str
    source: str = "synthetic"
    confidence: float = 1.0
    notes: str = ""

class Participant(_Base):
    participant_id: str
    cohort: str = "synthetic"

class TaskProtocol(_Base):
    protocol_id: str
    title: str
    phases: list[str]

class Session(_Base):
    session_id: str
    participant_id: str
    protocol_id: str
    consent_form_version: str
    device_config_id: str
    start_time_s: float
    qc_status: QcStatus = QcStatus.PASS
    processing_status: ProcessingStatus = ProcessingStatus.RAW

class Manifest(_Base):
    session_id: str
    inputs: dict[str, str]   # rel path -> sha256
    outputs: dict[str, str]  # rel path -> sha256
    tool_versions: dict[str, str]  # recorded, EXCLUDED from reproducibility hash
    seed: int

class DatasetRelease(_Base):
    release_name: str
    profile: str
    session_ids: list[str]
    absent_modalities: list[str] = Field(default_factory=list)
    manifest_sha256: str
```

- [ ] **Step 5: Write JSON Schema export**

```python
# src/htdp/schemas/export.py
import json
from pathlib import Path
from htdp.schemas import models

_EXPORTED = [
    models.Consent, models.DeviceConfig, models.EventMarker,
    models.Session, models.Manifest, models.DatasetRelease,
    models.Participant, models.TaskProtocol,
]

def export_json_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in _EXPORTED:
        path = out_dir / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written
```

- [ ] **Step 6: Add `__init__.py`**

```python
# src/htdp/schemas/__init__.py
```

- [ ] **Step 7: Run tests + typecheck**

Run: `uv run pytest tests/test_schemas.py -v && uv run mypy src/htdp/schemas`
Expected: PASS, no type errors.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: pydantic schemas, enums, and JSON Schema export"
```

---

### Task 3: Canonical IO + checksums

**Files:**
- Create: `src/htdp/io/__init__.py`, `src/htdp/io/canonical.py`, `src/htdp/io/checksums.py`
- Test: `tests/test_canonical.py`, `tests/test_checksums.py`

**Interfaces:**
- Produces `dump_json(obj: dict | BaseModel, path: Path) -> None` (sorted keys, `\n`, UTF-8).
- Produces `write_csv(rows: list[dict], columns: list[str], path: Path) -> None` (fixed 6dp floats, `\n`).
- Produces `sha256_bytes(data: bytes) -> str`, `sha256_file(path: Path) -> str`.
- Produces `write_checksums(session_dir: Path) -> Path` (writes `checksums.sha256`), `verify_checksums(session_dir: Path) -> list[str]` (returns list of mismatched/missing rel paths; empty = OK).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_canonical.py
from pathlib import Path
from htdp.io.canonical import dump_json, write_csv

def test_dump_json_is_sorted_and_stable(tmp_path: Path):
    p = tmp_path / "a.json"
    dump_json({"b": 1, "a": 2}, p)
    assert p.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "b": 1\n}\n'

def test_write_csv_fixed_precision(tmp_path: Path):
    p = tmp_path / "m.csv"
    write_csv([{"x": 1.23456789, "n": "k"}], ["x", "n"], p)
    assert p.read_text(encoding="utf-8") == "x,n\n1.234568,k\n"
```

```python
# tests/test_checksums.py
from pathlib import Path
from htdp.io.checksums import sha256_bytes, write_checksums, verify_checksums

def test_sha256_bytes_known_value():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

def test_checksums_roundtrip_and_tamper_detection(tmp_path: Path):
    (tmp_path / "streams").mkdir()
    f = tmp_path / "streams" / "a.csv"
    f.write_text("x\n1\n", encoding="utf-8")
    write_checksums(tmp_path)
    assert verify_checksums(tmp_path) == []
    f.write_text("x\n2\n", encoding="utf-8")  # tamper
    assert "streams/a.csv" in verify_checksums(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_canonical.py tests/test_checksums.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.io'`

- [ ] **Step 3: Write canonical IO**

```python
# src/htdp/io/canonical.py
import json
from pathlib import Path
from pydantic import BaseModel

def dump_json(obj: dict | BaseModel, path: Path) -> None:
    data = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")

def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)

def write_csv(rows: list[dict], columns: list[str], path: Path) -> None:
    lines = [",".join(columns)]
    lines.extend(",".join(_fmt(row[c]) for c in columns) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Write checksums**

```python
# src/htdp/io/checksums.py
import hashlib
from pathlib import Path

_CHECKSUM_FILE = "checksums.sha256"

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def _iter_files(session_dir: Path) -> list[Path]:
    return sorted(
        p for p in session_dir.rglob("*")
        if p.is_file() and p.name != _CHECKSUM_FILE
    )

def write_checksums(session_dir: Path) -> Path:
    lines = [
        f"{sha256_file(p)}  {p.relative_to(session_dir).as_posix()}"
        for p in _iter_files(session_dir)
    ]
    out = session_dir / _CHECKSUM_FILE
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out

def verify_checksums(session_dir: Path) -> list[str]:
    recorded: dict[str, str] = {}
    cfile = session_dir / _CHECKSUM_FILE
    for line in cfile.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        recorded[rel] = digest
    mismatches: list[str] = []
    present = {p.relative_to(session_dir).as_posix() for p in _iter_files(session_dir)}
    for rel, digest in recorded.items():
        path = session_dir / rel
        if not path.exists() or sha256_file(path) != digest:
            mismatches.append(rel)
    mismatches.extend(rel for rel in present - set(recorded))  # unexpected new files
    return sorted(set(mismatches))
```

- [ ] **Step 5: Add `__init__.py`**

```python
# src/htdp/io/__init__.py
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_canonical.py tests/test_checksums.py -v && uv run mypy src/htdp/io`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: canonical JSON/CSV serialization and checksum tooling"
```

---

### Task 4: Synthetic session generator (seeded + defects + immutability)

**Files:**
- Create: `src/htdp/synth/__init__.py`, `src/htdp/synth/generate.py`
- Modify: `src/htdp/cli.py` (wire `synth`)
- Test: `tests/test_synth.py`

**Interfaces:**
- Consumes: `htdp.schemas.models` (Session, Consent, DeviceConfig, StreamRef, CoordinateFrame), `htdp.io.canonical.dump_json/write_csv`, `htdp.io.checksums.write_checksums`.
- Produces: `generate_session(out_dir: Path, seed: int, force: bool = False) -> Path` — writes the full `data/raw/<session_id>/` tree and returns the session dir. `session_id = f"synth-{seed:04d}"`. Deterministic: start epoch fixed at `start_time_s = 0.0`; all timestamps seed-derived. Injects a dropped-sample gap in `motion_left_wrist.csv` and a clock-drift offset on `motion_object.csv`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_synth.py
from pathlib import Path
import pytest
from htdp.synth.generate import generate_session

def test_generates_expected_tree(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    assert d.name == "synth-0001"
    for rel in ("session.json", "consent.json", "device_config.json", "notes.md",
                "checksums.sha256", "streams/motion_right_wrist.csv",
                "streams/motion_left_wrist.csv", "streams/motion_torso.csv",
                "streams/motion_object.csv", "streams/events.csv"):
        assert (d / rel).exists(), rel
    assert (d / "video").is_dir()

def test_is_deterministic(tmp_path: Path):
    a = generate_session(tmp_path / "a", seed=7)
    b = generate_session(tmp_path / "b", seed=7)
    assert (a / "streams/motion_right_wrist.csv").read_bytes() == (b / "streams/motion_right_wrist.csv").read_bytes()

def test_refuses_overwrite_without_force(tmp_path: Path):
    generate_session(tmp_path, seed=1)
    with pytest.raises(FileExistsError):
        generate_session(tmp_path, seed=1)
    generate_session(tmp_path, seed=1, force=True)  # ok

def test_injects_defect_tags(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    left = (d / "streams/motion_left_wrist.csv").read_text(encoding="utf-8")
    obj = (d / "streams/motion_object.csv").read_text(encoding="utf-8")
    assert "dropped_gap" in left
    assert "clock_drift" in obj
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_synth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.synth'`

- [ ] **Step 3: Write the generator**

```python
# src/htdp/synth/generate.py
from __future__ import annotations
import math
import shutil
from pathlib import Path
from htdp.io.canonical import dump_json, write_csv
from htdp.io.checksums import write_checksums
from htdp.schemas.enums import EventLabel
from htdp.schemas.models import (
    Consent, CoordinateFrame, DeviceConfig, Session, StreamRef,
)

_RATE_HZ = 100.0
_DURATION_S = 4.0
_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")
_MOTION_COLS = ["timestamp_s", "tracker_id", "x_m", "y_m", "z_m",
                "qw", "qx", "qy", "qz", "quality", "defect_tag"]
_EVENT_COLS = ["timestamp_s", "event_id", "label", "phase", "source", "confidence", "notes"]

def _trajectory(tracker: str, seed: int) -> list[dict]:
    n = int(_RATE_HZ * _DURATION_S)
    phase = (seed % 7) * 0.1
    rows: list[dict] = []
    for i in range(n):
        t = i / _RATE_HZ
        reach = math.sin(math.pi * t / _DURATION_S + phase)
        base = {"right_wrist": 0.3, "left_wrist": -0.3, "torso": 0.0, "object": 0.5}[tracker]
        defect_tag = ""
        ts = t
        if tracker == "left_wrist" and 100 <= i < 110:  # dropped-sample gap
            defect_tag = "dropped_gap"
            continue
        if tracker == "object":  # clock-drift offset
            ts = t + 0.05 * (t / _DURATION_S)
            defect_tag = "clock_drift"
        rows.append({
            "timestamp_s": ts, "tracker_id": tracker,
            "x_m": base + 0.1 * reach, "y_m": 0.2 * reach, "z_m": 0.9 + 0.05 * reach,
            "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0,
            "quality": 1.0, "defect_tag": defect_tag,
        })
    return rows

def _events() -> list[dict]:
    spec = [(0.0, EventLabel.START, "approach"), (1.0, EventLabel.GRASP, "grasp"),
            (2.0, EventLabel.RELEASE, "transport"), (3.0, EventLabel.PLACE, "place"),
            (4.0, EventLabel.STOP, "done")]
    return [
        {"timestamp_s": t, "event_id": i, "label": label.value, "phase": phase,
         "source": "synthetic", "confidence": 1.0, "notes": ""}
        for i, (t, label, phase) in enumerate(spec)
    ]

def generate_session(out_dir: Path, seed: int, force: bool = False) -> Path:
    session_id = f"synth-{seed:04d}"
    session_dir = out_dir / session_id
    if session_dir.exists():
        if not force:
            raise FileExistsError(f"raw session already exists: {session_dir} (use force=True)")
        shutil.rmtree(session_dir)
    (session_dir / "streams").mkdir(parents=True)
    (session_dir / "video").mkdir()

    streams: list[StreamRef] = []
    for tracker in _TRACKERS:
        rel = f"streams/motion_{tracker}.csv"
        write_csv(_trajectory(tracker, seed), _MOTION_COLS, session_dir / rel)
        streams.append(StreamRef(name=tracker, path=rel, fmt="csv", role="motion", rate_hz=_RATE_HZ))
    write_csv(_events(), _EVENT_COLS, session_dir / "streams/events.csv")
    streams.append(StreamRef(name="events", path="streams/events.csv", fmt="csv", role="events"))

    device = DeviceConfig(device_config_id="vive-synth", frame=CoordinateFrame(), streams=streams)
    consent = Consent(consent_form_version="v1", commercial_use=True, model_training=True,
                      third_party_access=True, public_release=True, internal_only=False,
                      delete_after="2030-01-01")
    session = Session(session_id=session_id, participant_id=f"p-{seed:04d}",
                      protocol_id="reach-grasp-place", consent_form_version="v1",
                      device_config_id="vive-synth", start_time_s=0.0)

    dump_json(session, session_dir / "session.json")
    dump_json(consent, session_dir / "consent.json")
    dump_json(device, session_dir / "device_config.json")
    (session_dir / "notes.md").write_text(
        f"# Synthetic session {session_id}\nSeed {seed}. Reach-grasp-place. Defects injected.\n",
        encoding="utf-8", newline="\n")
    write_checksums(session_dir)
    return session_dir
```

- [ ] **Step 4: Add `__init__.py` and wire CLI**

```python
# src/htdp/synth/__init__.py
```

Replace the `synth` command body in `src/htdp/cli.py`:

```python
@app.command()
def synth(out: Path = typer.Option(..., "--out"), seed: int = 0, force: bool = False) -> None:
    """Generate a synthetic session."""
    from htdp.synth.generate import generate_session
    try:
        d = generate_session(out, seed=seed, force=force)
    except FileExistsError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_synth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: seeded synthetic session generator with injected defects"
```

---

### Task 5: Raw validation

**Files:**
- Create: `src/htdp/validate.py`
- Modify: `src/htdp/cli.py` (wire `validate`)
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `htdp.io.checksums.verify_checksums`, `htdp.schemas.models` (Session, Consent, DeviceConfig).
- Produces: `validate_session(raw_dir: Path) -> list[str]` — returns list of problem strings (empty = valid). Checks: required files present; `session.json`/`consent.json`/`device_config.json` parse against schemas; checksums verify; declared streams exist on disk.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate.py
from pathlib import Path
from htdp.synth.generate import generate_session
from htdp.validate import validate_session

def test_clean_session_validates(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    assert validate_session(d) == []

def test_tampered_session_fails(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    (d / "streams/events.csv").write_text("corrupt\n", encoding="utf-8")
    problems = validate_session(d)
    assert any("checksum" in p for p in problems)

def test_missing_file_fails(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    (d / "session.json").unlink()
    problems = validate_session(d)
    assert any("session.json" in p for p in problems)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.validate'`

- [ ] **Step 3: Write validation**

```python
# src/htdp/validate.py
from pathlib import Path
from pydantic import ValidationError
from htdp.io.checksums import verify_checksums
from htdp.schemas.models import Consent, DeviceConfig, Session

_REQUIRED = ("session.json", "consent.json", "device_config.json",
             "notes.md", "checksums.sha256", "streams/events.csv")

def validate_session(raw_dir: Path) -> list[str]:
    problems: list[str] = []
    for rel in _REQUIRED:
        if not (raw_dir / rel).exists():
            problems.append(f"missing required file: {rel}")
    if problems:
        return problems  # cannot proceed without core files

    for rel, model in (("session.json", Session), ("consent.json", Consent),
                       ("device_config.json", DeviceConfig)):
        try:
            model.model_validate_json((raw_dir / rel).read_text(encoding="utf-8"))
        except ValidationError as exc:
            problems.append(f"schema error in {rel}: {exc.error_count()} issue(s)")

    for rel in verify_checksums(raw_dir):
        problems.append(f"checksum mismatch: {rel}")

    device = DeviceConfig.model_validate_json((raw_dir / "device_config.json").read_text(encoding="utf-8"))
    for stream in device.streams:
        if not (raw_dir / stream.path).exists():
            problems.append(f"declared stream missing on disk: {stream.path}")
    return problems
```

- [ ] **Step 4: Wire CLI**

```python
@app.command()
def validate(raw_dir: Path) -> None:
    """Validate a raw session folder."""
    from htdp.validate import validate_session
    problems = validate_session(raw_dir)
    if problems:
        for p in problems:
            typer.echo(f"FAIL: {p}", err=True)
        raise typer.Exit(1)
    typer.echo("OK")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: raw session validation (schema + checksums + stream presence)"
```

---

### Task 6: Processing → Parquet (raw read-only)

**Files:**
- Create: `src/htdp/processing/__init__.py`, `src/htdp/processing/extract.py`
- Modify: `src/htdp/cli.py` (wire `process`)
- Test: `tests/test_processing.py`

**Interfaces:**
- Consumes: `htdp.io.checksums.sha256_file`, `htdp.schemas.models.Manifest`, `htdp.validate.validate_session`.
- Produces: `process_session(raw_dir: Path, processed_root: Path) -> Path` — returns processed session dir. Writes `motion.parquet` (all trackers concatenated, sorted by `tracker_id,timestamp_s`), `events.parquet`, and `manifest.json`. Raw dir is never modified. `tool_versions` recorded but excluded from any reproducibility checksum.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_processing.py
from pathlib import Path
import polars as pl
import pytest
from htdp.synth.generate import generate_session
from htdp.processing.extract import process_session
from htdp.io.checksums import write_checksums, verify_checksums

def test_process_writes_parquet_and_manifest(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    out = process_session(raw, tmp_path / "processed")
    assert (out / "motion.parquet").exists()
    assert (out / "events.parquet").exists()
    assert (out / "manifest.json").exists()
    df = pl.read_parquet(out / "motion.parquet")
    assert set(df["tracker_id"].unique()) == {"right_wrist", "left_wrist", "torso", "object"}

def test_process_does_not_modify_raw(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    write_checksums(raw)
    process_session(raw, tmp_path / "processed")
    assert verify_checksums(raw) == []

def test_process_rejects_invalid_raw(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    (raw / "streams/events.csv").write_text("corrupt\n", encoding="utf-8")
    with pytest.raises(ValueError):
        process_session(raw, tmp_path / "processed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_processing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.processing'`

- [ ] **Step 3: Write processing**

```python
# src/htdp/processing/extract.py
from __future__ import annotations
import importlib.metadata as md
from pathlib import Path
import polars as pl
from htdp.io.canonical import dump_json
from htdp.io.checksums import sha256_file
from htdp.schemas.models import DeviceConfig, Manifest
from htdp.validate import validate_session

def _tool_versions() -> dict[str, str]:
    return {pkg: md.version(pkg) for pkg in ("polars", "pydantic")}

def process_session(raw_dir: Path, processed_root: Path) -> Path:
    problems = validate_session(raw_dir)
    if problems:
        raise ValueError(f"cannot process invalid raw session: {problems}")

    device = DeviceConfig.model_validate_json((raw_dir / "device_config.json").read_text(encoding="utf-8"))
    motion_paths = [raw_dir / s.path for s in device.streams if s.role == "motion"]
    motion = pl.concat([pl.read_csv(p) for p in motion_paths]).sort(["tracker_id", "timestamp_s"])
    events = pl.read_csv(raw_dir / "streams/events.csv").sort("timestamp_s")

    out = processed_root / raw_dir.name
    out.mkdir(parents=True, exist_ok=True)
    motion.write_parquet(out / "motion.parquet")
    events.write_parquet(out / "events.parquet")

    inputs = {
        p.relative_to(raw_dir).as_posix(): sha256_file(p)
        for p in sorted(raw_dir.rglob("*")) if p.is_file()
    }
    outputs = {f.name: sha256_file(f) for f in sorted(out.glob("*.parquet"))}
    seed = int(raw_dir.name.split("-")[-1])
    manifest = Manifest(session_id=raw_dir.name, inputs=inputs, outputs=outputs,
                        tool_versions=_tool_versions(), seed=seed)
    dump_json(manifest, out / "manifest.json")
    return out
```

- [ ] **Step 4: Add `__init__.py` and wire CLI**

```python
# src/htdp/processing/__init__.py
```

```python
@app.command()
def process(raw_dir: Path) -> None:
    """Process a raw session into Parquet."""
    from htdp.processing.extract import process_session
    try:
        out = process_session(raw_dir, Path("data/processed"))
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {out}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_processing.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: process raw session into Parquet with manifest (raw read-only)"
```

---

### Task 7: QC checks + report (pass/warn/fail, JSON + HTML)

**Files:**
- Create: `src/htdp/qc/__init__.py`, `src/htdp/qc/checks.py`, `src/htdp/qc/report.py`, `src/htdp/qc/templates/report.html.j2`
- Modify: `src/htdp/cli.py` (wire `qc`)
- Test: `tests/test_qc.py`

**Interfaces:**
- Consumes: processed `motion.parquet`, `events.parquet`.
- Produces: `run_qc(processed_dir: Path) -> dict` with shape `{"overall": "pass|warn|fail", "checks": [{"name": str, "severity": "pass|warn|fail", "detail": str}, ...]}`. Writes `qc_report.json` and `qc_report.html`. Dropped-sample gap + clock-drift = `warn`; non-monotonic timestamps / missing tracker = `fail`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qc.py
from pathlib import Path
import json
from htdp.synth.generate import generate_session
from htdp.processing.extract import process_session
from htdp.qc.checks import run_qc

def _processed(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    return process_session(raw, tmp_path / "processed")

def test_qc_detects_dropped_samples_as_warn(tmp_path: Path):
    report = run_qc(_processed(tmp_path))
    drop = next(c for c in report["checks"] if c["name"] == "dropped_samples")
    assert drop["severity"] == "warn"

def test_qc_detects_clock_drift_as_warn(tmp_path: Path):
    report = run_qc(_processed(tmp_path))
    drift = next(c for c in report["checks"] if c["name"] == "clock_drift")
    assert drift["severity"] == "warn"

def test_qc_overall_is_warn_not_fail(tmp_path: Path):
    report = run_qc(_processed(tmp_path))
    assert report["overall"] == "warn"

def test_qc_writes_json_and_html(tmp_path: Path):
    out = _processed(tmp_path)
    run_qc(out)
    assert (out / "qc_report.json").exists()
    assert (out / "qc_report.html").exists()
    data = json.loads((out / "qc_report.json").read_text(encoding="utf-8"))
    assert data["overall"] == "warn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_qc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.qc'`

- [ ] **Step 3: Write the checks**

```python
# src/htdp/qc/checks.py
from __future__ import annotations
from pathlib import Path
import polars as pl
from htdp.qc.report import write_reports

_EXPECTED_TRACKERS = {"right_wrist", "left_wrist", "torso", "object"}
_RATE_HZ = 100.0

def _worst(severities: list[str]) -> str:
    for level in ("fail", "warn", "pass"):
        if level in severities:
            return level
    return "pass"

def run_qc(processed_dir: Path) -> dict:
    motion = pl.read_parquet(processed_dir / "motion.parquet")
    events = pl.read_parquet(processed_dir / "events.parquet")
    checks: list[dict] = []

    present = set(motion["tracker_id"].unique())
    missing = _EXPECTED_TRACKERS - present
    checks.append({"name": "trackers_present", "severity": "fail" if missing else "pass",
                   "detail": f"missing={sorted(missing)}" if missing else "all trackers present"})

    mono_ok = True
    for tracker in present:
        ts = motion.filter(pl.col("tracker_id") == tracker)["timestamp_s"].to_list()
        if any(b <= a for a, b in zip(ts, ts[1:])):
            mono_ok = False
    checks.append({"name": "monotonic_timestamps", "severity": "pass" if mono_ok else "fail",
                   "detail": "ok" if mono_ok else "non-monotonic timestamps found"})

    gap_found = False
    for tracker in present:
        ts = motion.filter(pl.col("tracker_id") == tracker)["timestamp_s"].to_list()
        diffs = [b - a for a, b in zip(ts, ts[1:])]
        if any(d > 1.5 / _RATE_HZ for d in diffs):
            gap_found = True
    checks.append({"name": "dropped_samples", "severity": "warn" if gap_found else "pass",
                   "detail": "gap detected" if gap_found else "no gaps"})

    drift_found = "clock_drift" in set(motion["defect_tag"].unique())
    checks.append({"name": "clock_drift", "severity": "warn" if drift_found else "pass",
                   "detail": "drift tag present" if drift_found else "no drift"})

    labels = events["label"].to_list()
    order_ok = labels == ["start", "grasp", "release", "place", "stop"]
    checks.append({"name": "event_order", "severity": "pass" if order_ok else "fail",
                   "detail": "ok" if order_ok else f"unexpected order: {labels}"})

    report = {"overall": _worst([c["severity"] for c in checks]), "checks": checks}
    write_reports(report, processed_dir)
    return report
```

- [ ] **Step 4: Write the report writers + template**

```python
# src/htdp/qc/report.py
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from htdp.io.canonical import dump_json

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

def write_reports(report: dict, out_dir: Path) -> None:
    dump_json(report, out_dir / "qc_report.json")
    html = _ENV.get_template("report.html.j2").render(report=report)
    (out_dir / "qc_report.html").write_text(html, encoding="utf-8", newline="\n")
```

```jinja
{# src/htdp/qc/templates/report.html.j2 #}
<!doctype html>
<html><head><meta charset="utf-8"><title>QC Report</title></head>
<body>
<h1>QC Report — overall: {{ report.overall }}</h1>
<table border="1" cellpadding="6">
<tr><th>Check</th><th>Severity</th><th>Detail</th></tr>
{% for c in report.checks %}
<tr><td>{{ c.name }}</td><td>{{ c.severity }}</td><td>{{ c.detail }}</td></tr>
{% endfor %}
</table>
</body></html>
```

- [ ] **Step 5: Add `__init__.py`, ensure template packaging, wire CLI**

```python
# src/htdp/qc/__init__.py
```

Add to `pyproject.toml` under `[tool.hatch.build.targets.wheel]` so the template ships:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/htdp"]
artifacts = ["src/htdp/qc/templates/*.j2"]
```

```python
@app.command()
def qc(processed_dir: Path) -> None:
    """Generate a QC report."""
    from htdp.qc.checks import run_qc
    report = run_qc(processed_dir)
    typer.echo(f"overall: {report['overall']}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_qc.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: QC checks with pass/warn/fail severity and JSON+HTML report"
```

---

### Task 8: Consent gate + release profiles

**Files:**
- Create: `src/htdp/consent/__init__.py`, `src/htdp/consent/profiles.py`
- Test: `tests/test_consent.py`

**Interfaces:**
- Consumes: `htdp.schemas.models.Consent`, `htdp.schemas.enums.ReleaseProfile`.
- Produces: `REQUIRED_FLAGS: dict[ReleaseProfile, tuple[str, ...]]`; `check_consent(consent: Consent, profile: ReleaseProfile) -> list[str]` — returns list of missing required flags (empty = allowed).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_consent.py
from htdp.schemas.models import Consent
from htdp.schemas.enums import ReleaseProfile
from htdp.consent.profiles import check_consent

def _full_consent(**over) -> Consent:
    base = dict(consent_form_version="v1", commercial_use=True, model_training=True,
                third_party_access=True, public_release=True, internal_only=False)
    base.update(over)
    return Consent(**base)

def test_commercial_profile_allows_when_flags_set():
    assert check_consent(_full_consent(), ReleaseProfile.COMMERCIAL_DATASET) == []

def test_commercial_profile_blocks_when_flag_missing():
    missing = check_consent(_full_consent(model_training=False), ReleaseProfile.COMMERCIAL_DATASET)
    assert "model_training" in missing

def test_internal_research_profile_minimal():
    assert check_consent(Consent(consent_form_version="v1"), ReleaseProfile.INTERNAL_RESEARCH) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_consent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.consent'`

- [ ] **Step 3: Write the consent profiles**

```python
# src/htdp/consent/profiles.py
from htdp.schemas.enums import ReleaseProfile
from htdp.schemas.models import Consent

REQUIRED_FLAGS: dict[ReleaseProfile, tuple[str, ...]] = {
    ReleaseProfile.INTERNAL_RESEARCH: (),
    ReleaseProfile.PUBLIC_SAMPLE: ("public_release",),
    ReleaseProfile.COMMERCIAL_DATASET: ("commercial_use", "model_training", "third_party_access"),
}

def check_consent(consent: Consent, profile: ReleaseProfile) -> list[str]:
    return [flag for flag in REQUIRED_FLAGS[profile] if not getattr(consent, flag)]
```

- [ ] **Step 4: Add `__init__.py`**

```python
# src/htdp/consent/__init__.py
```

- [ ] **Step 5: Run tests + typecheck**

Run: `uv run pytest tests/test_consent.py -v && uv run mypy src/htdp/consent`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: consent release profiles and block-on-conflict gate"
```

---

### Task 9: Release packaging (atomic staging + reproducibility)

**Files:**
- Create: `src/htdp/release/__init__.py`, `src/htdp/release/package.py`
- Modify: `src/htdp/cli.py` (wire `package`)
- Test: `tests/test_release.py`

**Interfaces:**
- Consumes: `htdp.consent.profiles.check_consent`, `htdp.io.canonical.dump_json/write_csv`, `htdp.io.checksums.sha256_file/write_checksums`, `htdp.schemas` (Consent, DatasetRelease, ReleaseProfile).
- Produces: `package_release(session_ids: list[str], release_name: str, profile: ReleaseProfile, raw_root: Path, releases_root: Path) -> Path`. Raises `ConsentError` (define in module) on conflict, leaving no release dir. Builds in a temp staging dir, computes a `manifest_sha256` over canonical sorted `{rel_path: sha256}` of packaged data files (timestamps/tool versions excluded), then atomically `os.replace`s staging into `releases_root/release_name`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_release.py
from pathlib import Path
import json
import pytest
from htdp.synth.generate import generate_session
from htdp.schemas.enums import ReleaseProfile
from htdp.release.package import package_release, ConsentError

def _raw(tmp_path: Path, seed: int = 1) -> Path:
    generate_session(tmp_path / "raw", seed=seed)
    return tmp_path / "raw"

def test_package_builds_release(tmp_path: Path):
    raw = _raw(tmp_path)
    out = package_release(["synth-0001"], "rel-v0.1", ReleaseProfile.COMMERCIAL_DATASET,
                          raw, tmp_path / "releases")
    assert (out / "manifest.json").exists()
    assert (out / "checksums.sha256").exists()
    assert (out / "data/synth-0001/session.json").exists()

def test_package_blocks_on_consent_conflict(tmp_path: Path):
    raw = _raw(tmp_path)
    consent = raw / "synth-0001/consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["model_training"] = False
    consent.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConsentError):
        package_release(["synth-0001"], "rel-bad", ReleaseProfile.COMMERCIAL_DATASET,
                        raw, tmp_path / "releases")
    assert not (tmp_path / "releases" / "rel-bad").exists()  # no partial output

def test_package_is_reproducible(tmp_path: Path):
    raw = _raw(tmp_path)
    a = package_release(["synth-0001"], "rel-a", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "ra")
    b = package_release(["synth-0001"], "rel-b", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "rb")
    sha_a = json.loads((a / "manifest.json").read_text())["manifest_sha256"]
    sha_b = json.loads((b / "manifest.json").read_text())["manifest_sha256"]
    assert sha_a == sha_b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_release.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.release'`

- [ ] **Step 3: Write packaging**

```python
# src/htdp/release/package.py
from __future__ import annotations
import json
import os
import shutil
import tempfile
from pathlib import Path
from htdp.consent.profiles import check_consent
from htdp.io.canonical import dump_json, write_csv
from htdp.io.checksums import sha256_bytes, sha256_file, write_checksums
from htdp.schemas.enums import ReleaseProfile
from htdp.schemas.models import Consent, DatasetRelease, Session

class ConsentError(RuntimeError):
    """Raised when a session's consent does not permit the requested release profile."""

_LICENSE = "Synthetic data. CC-BY-4.0 for v0.1 demonstration release.\n"

def _manifest_sha(staging_data: Path) -> str:
    files = sorted(p for p in staging_data.rglob("*") if p.is_file())
    digest_map = {p.relative_to(staging_data).as_posix(): sha256_file(p) for p in files}
    canonical = json.dumps(digest_map, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256_bytes(canonical)

def package_release(session_ids: list[str], release_name: str, profile: ReleaseProfile,
                    raw_root: Path, releases_root: Path) -> Path:
    final = releases_root / release_name
    if final.exists():
        raise FileExistsError(f"release already exists: {final}")

    # Consent gate FIRST — fail before any output.
    for sid in session_ids:
        consent = Consent.model_validate_json((raw_root / sid / "consent.json").read_text(encoding="utf-8"))
        missing = check_consent(consent, profile)
        if missing:
            raise ConsentError(f"{sid}: profile {profile.value} requires {missing}")

    # v0.1: video + EEG are never captured -> always recorded absent (spec §8.1).
    absent = ["eeg", "video"]

    releases_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_name}.", dir=releases_root))
    try:
        data_dir = staging / "data"
        participants: list[dict] = []
        sessions: list[dict] = []
        for sid in session_ids:
            shutil.copytree(raw_root / sid, data_dir / sid)
            session = Session.model_validate_json((raw_root / sid / "session.json").read_text(encoding="utf-8"))
            participants.append({"participant_id": session.participant_id, "cohort": "synthetic"})
            sessions.append({"session_id": sid, "participant_id": session.participant_id,
                             "protocol_id": session.protocol_id})

        write_csv(participants, ["participant_id", "cohort"], staging / "participants.csv")
        write_csv(sessions, ["session_id", "participant_id", "protocol_id"], staging / "sessions.csv")
        (staging / "README.md").write_text(f"# {release_name}\nSynthetic reach-grasp-place release (v0.1).\n",
                                           encoding="utf-8", newline="\n")
        (staging / "LICENSE").write_text(_LICENSE, encoding="utf-8", newline="\n")
        (staging / "protocol.md").write_text("# reach-grasp-place\nReach, grasp, transport, place.\n",
                                             encoding="utf-8", newline="\n")

        manifest_sha = _manifest_sha(data_dir)
        release = DatasetRelease(release_name=release_name, profile=profile.value,
                                 session_ids=session_ids, absent_modalities=sorted(absent),
                                 manifest_sha256=manifest_sha)
        dump_json(release, staging / "manifest.json")
        write_checksums(staging)
        os.replace(staging, final)  # atomic
        return final
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
```

- [ ] **Step 4: Add `__init__.py` and wire CLI**

```python
# src/htdp/release/__init__.py
```

```python
@app.command()
def package(session_ids: list[str], release: str = typer.Option(...), profile: str = typer.Option(...)) -> None:
    """Package a dataset release (consent-gated)."""
    from htdp.release.package import package_release, ConsentError
    from htdp.schemas.enums import ReleaseProfile
    try:
        out = package_release(session_ids, release, ReleaseProfile(profile),
                              Path("data/raw"), Path("data/releases"))
    except ConsentError as exc:
        typer.echo(f"CONSENT BLOCK: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"wrote {out}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_release.py -v && uv run mypy src/htdp/release`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: consent-gated atomic release packaging with reproducible manifest hash"
```

---

### Task 10: MuJoCo mocap replay (optional dep) + docs + AGENTS.md

**Files:**
- Create: `src/htdp/replay/__init__.py`, `src/htdp/replay/player.py`
- Modify: `src/htdp/cli.py` (wire `replay`)
- Create: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/ETHICS_AND_CONSENT.md`, `docs/ROADMAP.md`, `protocols/reach-grasp-place.md`
- Test: `tests/test_replay.py`

**Interfaces:**
- Consumes: packaged release `data/<sid>/streams/motion_*.csv` (read from release).
- Produces: `load_release_motion(release_dir: Path) -> dict[str, list[tuple[float, float, float, float]]]` (tracker → list of (t,x,y,z)); `replay_release(release_dir: Path, headless: bool = True, max_steps: int = 50) -> int` (returns frames stepped; raises `ReplayUnavailable` if mujoco missing).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_replay.py
from pathlib import Path
import pytest
from htdp.synth.generate import generate_session
from htdp.schemas.enums import ReleaseProfile
from htdp.release.package import package_release
from htdp.replay.player import load_release_motion, replay_release, ReplayUnavailable

mujoco = pytest.importorskip("mujoco")

def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return package_release(["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
                           tmp_path / "raw", tmp_path / "releases")

def test_load_release_motion_has_all_trackers(tmp_path: Path):
    motion = load_release_motion(_release(tmp_path))
    assert set(motion) == {"right_wrist", "left_wrist", "torso", "object"}

def test_replay_steps_headless(tmp_path: Path):
    frames = replay_release(_release(tmp_path), headless=True, max_steps=10)
    assert frames == 10
```

- [ ] **Step 2: Run tests to verify they fail (or skip if no mujoco)**

Run: `uv run pytest tests/test_replay.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'htdp.replay'` (if mujoco installed), else SKIPPED.

- [ ] **Step 3: Write the replay player**

```python
# src/htdp/replay/player.py
from __future__ import annotations
from pathlib import Path
import polars as pl

class ReplayUnavailable(RuntimeError):
    """Raised when MuJoCo is not installed."""

_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")

def load_release_motion(release_dir: Path) -> dict[str, list[tuple[float, float, float, float]]]:
    out: dict[str, list[tuple[float, float, float, float]]] = {}
    sessions = sorted((release_dir / "data").iterdir())
    sid = sessions[0].name
    for tracker in _TRACKERS:
        df = pl.read_csv(release_dir / "data" / sid / "streams" / f"motion_{tracker}.csv")
        out[tracker] = [(r["timestamp_s"], r["x_m"], r["y_m"], r["z_m"]) for r in df.iter_rows(named=True)]
    return out

def _model_xml() -> str:
    bodies = "\n".join(
        f'<body name="{t}" mocap="true" pos="0 0 1">'
        f'<geom type="sphere" size="0.03" rgba="0.2 0.6 1 1"/></body>'
        for t in _TRACKERS
    )
    return f'<mujoco><worldbody>{bodies}</worldbody></mujoco>'

def replay_release(release_dir: Path, headless: bool = True, max_steps: int = 50) -> int:
    try:
        import mujoco
    except ModuleNotFoundError as exc:
        raise ReplayUnavailable("install with: uv sync --extra replay") from exc

    motion = load_release_motion(release_dir)
    model = mujoco.MjModel.from_xml_string(_model_xml())
    data = mujoco.MjData(model)
    n = min(max_steps, min(len(v) for v in motion.values()))
    for i in range(n):
        for j, tracker in enumerate(_TRACKERS):
            _, x, y, z = motion[tracker][i]
            data.mocap_pos[j] = [x, y, z]
        mujoco.mj_step(model, data)
    return n
```

- [ ] **Step 4: Add `__init__.py` and wire CLI**

```python
# src/htdp/replay/__init__.py
```

```python
@app.command()
def replay(release_dir: Path) -> None:
    """Replay a packaged release in MuJoCo."""
    from htdp.replay.player import replay_release, ReplayUnavailable
    try:
        frames = replay_release(release_dir)
    except ReplayUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"stepped {frames} frames")
```

- [ ] **Step 5: Write AGENTS.md and docs**

```markdown
<!-- AGENTS.md -->
# AGENTS.md — Human-Task Dataset Pipeline (v0.1)

This project is a **consent-based human-task dataset pipeline for robotics**. The
product unit is a **dataset release**, not an app. v0.1 is a synthetic, filesystem-only
spine.

## Hard rules
- Do NOT add servers (Postgres/MinIO/FastAPI), Docker, dashboards, real hardware,
  LSL/XDF, video, EEG, ROS, or IK/robot replay in v0.1.
- Do NOT store raw data in a database.
- Do NOT bypass consent checks. `package` blocks on conflict and writes nothing.
- Do NOT modify raw data during processing. Raw is immutable.
- Keep fixtures tiny and deterministic. Update schemas and docs together.
- Preserve manifests + checksums. Make errors explicit.

## Quality gate (run before every commit)
`uv run ruff format --check . && uv run ruff check . && uv run pytest`
Typecheck: `uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io`

## Reproducibility
Same code + uv.lock + platform + seed + inputs → identical release-manifest checksum.
Canonical JSON (sorted keys, UTF-8) and CSV (stable columns, 6dp floats, \n). Generated
timestamps seed-derived; tool versions recorded but excluded from the reproducibility hash.
```

Write `docs/ARCHITECTURE.md` (layers + CLI surface from spec §2/§10), `docs/DATA_CONTRACT.md` (folder convention + CSV columns from spec §4), `docs/ETHICS_AND_CONSENT.md` (consent flags + profiles from spec §5/§8), `docs/ROADMAP.md` (v0.1 done → v0.2 deferred list from spec §16), and `protocols/reach-grasp-place.md` (goal, setup, phases, events). Each file restates the relevant spec section in prose.

- [ ] **Step 6: Export JSON schemas into docs and run full gate**

```bash
uv run python -c "from pathlib import Path; from htdp.schemas.export import export_json_schemas; export_json_schemas(Path('docs/schemas'))"
uv run ruff format --check . && uv run ruff check . && uv run pytest
```
Expected: all green (replay tests skipped if mujoco absent).

- [ ] **Step 7: End-to-end smoke (manual verification)**

```bash
uv run htdp synth --out data/raw --seed 1
uv run htdp validate data/raw/synth-0001
uv run htdp process data/raw/synth-0001
uv run htdp qc data/processed/synth-0001
uv run htdp package synth-0001 --release human-reach-grasp-place-v0.1 --profile commercial_dataset
```
Expected: validate prints `OK`; qc prints `overall: warn`; package prints `wrote data/releases/...`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: MuJoCo mocap replay, AGENTS.md, docs, and JSON Schema export"
```

---

## Self-Review

**Spec coverage:**
- §0 boundary → Global Constraints + AGENTS.md (Task 10). §1 success criterion → end-to-end smoke (Task 10 Step 7) + reproducibility test (Task 9). §2 architecture → Tasks 1–10. §3 repo layout → Task 1 + per-task files. §4 data contract + 4.1/4.2/4.3 → Task 4 (columns, frame, video slot). §5 schemas → Task 2. §6 synth + defects + 6.1 immutability → Task 4. §7 QC + 7.1 severity → Task 7. §8 consent + profiles + atomicity → Tasks 8, 9. §9 replay (optional) → Task 10. §10 CLI → wired across Tasks 1,4,5,6,7,9,10. §11 reproducibility → Task 3 (canonical) + Task 9 (manifest hash). §12 tooling → Task 1. §13 testing → every task. §14 build order → task order. §15 AGENTS.md → Task 10. §16 out-of-scope → Global Constraints.
- No gaps found.

**Placeholder scan:** No TBD/TODO; every code step has complete code. Doc files in Task 10 Step 5 specify exact content source (named spec sections) rather than placeholder text.

**Type consistency:** `generate_session`, `validate_session`, `process_session`, `run_qc`, `check_consent`, `package_release`, `replay_release`, `ConsentError`, `ReplayUnavailable`, `ReleaseProfile`, `Consent`, `Session`, `Manifest`, `DatasetRelease` used consistently across producing and consuming tasks. `run_qc` returns the dict shape consumed nowhere downstream except its own report writer. `manifest_sha256` field defined in Task 2, set in Task 9, asserted in Task 9 tests.

One note for the implementer: in Task 9 `package_release`, the v0.1 `absent` detection always records `eeg` (never captured) and records `video` when the slot is empty — this matches spec §8.1 ("their absence should be recorded"). If `video/` is later populated, revisit.
