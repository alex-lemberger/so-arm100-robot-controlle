# Video Ingest Augment Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp ingest-video`: augment an existing raw session by copying an opaque `.mp4` into its `video/` slot, registering a video `StreamRef` in `device_config.json`, and re-sealing `checksums.sha256` — so the consent video filter (slice 2) operates on real data.

**Architecture:** One new module `src/htdp/ingest/video.py` (`VideoSidecar` model, `VideoIngestError`, `ingest_video` orchestrator) plus one CLI command. Augments an already-finalized raw session in place. No change to `ingest_xdf`, `synth`, downstream stages, or any persisted schema.

**Tech Stack:** Python ≥3.11, pydantic v2, typer, pytest. Stdlib `shutil` only — no media libraries.

## Global Constraints

Copied verbatim from `AGENTS.md`:

- Python `>=3.11`. mypy `strict` must pass on the gate targets (`src/htdp/ingest` is already a target).
- ruff: `line-length = 100`, `line-ending = lf`. `uv run ruff format --check . && uv run ruff check .` clean.
- Canonical output only: JSON via `io.canonical.dump_json`; checksums via `io.checksums.write_checksums`. Do not change canonical formats.
- **No partial writes:** validate inputs and guard duplicates BEFORE copying any file. The `.mp4` is opaque — never decode/transcode/introspect it.
- **No persisted-schema model change** (the sidecar model is local to `ingest/video.py`; registration reuses the existing `StreamRef`) → no JSON-Schema re-export.
- Reuse existing schemas/modules. Do NOT touch `synth`, `validate`, `processing`, `qc`, `replay`, `release`, the existing `ingest/*` files, or `schemas/*`.
- Deterministic: same inputs → identical session folder.

**Reference — `StreamRef` schema** (`src/htdp/schemas/models.py`): `name: str`, `path: str`, `fmt: str`, `role: str`, `rate_hz: float | None = None`. **`DeviceConfig`**: `device_config_id: str`, `frame: CoordinateFrame`, `streams: list[StreamRef]`.

**Reference — raw session layout** (what `ingest-video` augments): a finalized folder with `session.json`, `consent.json`, `device_config.json`, `notes.md`, `checksums.sha256`, `streams/…`, and an (initially empty) `video/` dir. `validate_session` requires `device_config.json` streams to exist on disk and `checksums.sha256` to match all files.

**Reference — optional-error CLI pattern** (`src/htdp/cli.py`, e.g. the `ingest` command): import inside the command, `try/except (...) → typer.echo("error: ...", err=True); raise typer.Exit(1)`.

**Reference — canonical JSON helper** (`io.canonical.dump_json`) accepts a pydantic `BaseModel` or a dict and writes sorted-keys, 2-space-indent, trailing-`\n`.

---

### Task 1: `video.py` — `VideoSidecar` model + `VideoIngestError`

**Files:**
- Create: `src/htdp/ingest/video.py`
- Test: `tests/test_video_sidecar.py`

**Interfaces:**
- Consumes: nothing from earlier slices.
- Produces:
  - `class VideoIngestError(RuntimeError)`
  - `class VideoSidecar(BaseModel)` with `model_config = ConfigDict(extra="forbid")`, fields `name: str` (min length 1), `fps: float` (> 0).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_video_sidecar.py
import pytest
from pydantic import ValidationError

from htdp.ingest.video import VideoIngestError, VideoSidecar


def test_valid_sidecar():
    s = VideoSidecar(name="frontal", fps=30.0)
    assert s.name == "frontal" and s.fps == 30.0


def test_video_ingest_error_is_runtime_error():
    assert issubclass(VideoIngestError, RuntimeError)


def test_empty_name_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="", fps=30.0)


def test_nonpositive_fps_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="frontal", fps=0.0)


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        VideoSidecar(name="frontal", fps=30.0, codec="h264")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_sidecar.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.ingest.video'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/htdp/ingest/video.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VideoIngestError(RuntimeError):
    """Raised when a video cannot be ingested into a raw session."""


class VideoSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    fps: float = Field(gt=0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_sidecar.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/video.py tests/test_video_sidecar.py
git commit -m "feat(video): VideoSidecar model + VideoIngestError"
```

---

### Task 2: `video.py` — `ingest_video` orchestrator

**Files:**
- Modify: `src/htdp/ingest/video.py` (append)
- Test: `tests/test_video_ingest.py`

**Interfaces:**
- Consumes: `VideoSidecar`, `VideoIngestError` (Task 1); `io.canonical.dump_json`; `io.checksums.write_checksums`; schemas `DeviceConfig`, `StreamRef`.
- Produces: `ingest_video(session_dir: Path, mp4_path: Path, sidecar_path: Path, force: bool = False) -> Path`.
  - Validates: `mp4_path` exists, `session_dir/device_config.json` exists → else `VideoIngestError`.
  - Loads + validates sidecar (`ValidationError` on bad input).
  - Loads `DeviceConfig`; if a `role="video"` StreamRef named `name` already exists → `VideoIngestError` unless `force` (then drop the matching one first).
  - Copies mp4 → `session_dir/video/<name>.mp4`; appends `StreamRef(name, path=f"video/{name}.mp4", fmt="mp4", role="video", rate_hz=fps)`; `dump_json` device config; `write_checksums`.
  - All validation/guards precede the copy (no partial writes). Returns `session_dir`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_video_ingest.py
import json
from pathlib import Path

import pytest

from htdp.ingest.video import VideoIngestError, ingest_video
from htdp.schemas.models import DeviceConfig
from htdp.synth.generate import generate_session
from htdp.validate import validate_session


def _session(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return tmp_path / "raw" / "synth-0001"


def _sidecar(tmp_path: Path, name: str = "frontal", fps: float = 30.0) -> Path:
    p = tmp_path / "video.json"
    p.write_text(json.dumps({"name": name, "fps": fps}), encoding="utf-8")
    return p


def _mp4(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftyp")  # opaque dummy bytes, never decoded
    return p


def test_happy_path_registers_and_validates(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    assert (session / "video" / "frontal.mp4").exists()
    device = DeviceConfig.model_validate_json(
        (session / "device_config.json").read_text(encoding="utf-8")
    )
    vids = [s for s in device.streams if s.role == "video"]
    assert len(vids) == 1
    assert vids[0].name == "frontal"
    assert vids[0].path == "video/frontal.mp4"
    assert vids[0].fmt == "mp4"
    assert vids[0].rate_hz == 30.0
    assert validate_session(session) == []  # checksums re-sealed


def test_duplicate_name_without_force_raises(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    with pytest.raises(VideoIngestError):
        ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))


def test_force_overwrites_without_duplicating_stream(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path, fps=60.0), force=True)
    device = DeviceConfig.model_validate_json(
        (session / "device_config.json").read_text(encoding="utf-8")
    )
    vids = [s for s in device.streams if s.role == "video"]
    assert len(vids) == 1  # replaced, not duplicated
    assert vids[0].rate_hz == 60.0
    assert validate_session(session) == []


def test_missing_mp4_raises_before_any_write(tmp_path: Path):
    session = _session(tmp_path)
    with pytest.raises(VideoIngestError):
        ingest_video(session, tmp_path / "nope.mp4", _sidecar(tmp_path))
    assert not (session / "video" / "frontal.mp4").exists()


def test_missing_device_config_raises(tmp_path: Path):
    session = _session(tmp_path)
    (session / "device_config.json").unlink()
    with pytest.raises(VideoIngestError):
        ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_ingest.py -v`
Expected: FAIL — `ImportError: cannot import name 'ingest_video'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/htdp/ingest/video.py` (add imports at top of the file):

```python
import shutil
from pathlib import Path

from htdp.io.canonical import dump_json
from htdp.io.checksums import write_checksums
from htdp.schemas.models import DeviceConfig, StreamRef
```

```python
def ingest_video(
    session_dir: Path,
    mp4_path: Path,
    sidecar_path: Path,
    force: bool = False,
) -> Path:
    if not mp4_path.exists():
        raise VideoIngestError(f"video file not found: {mp4_path}")
    device_path = session_dir / "device_config.json"
    if not device_path.exists():
        raise VideoIngestError(f"device_config.json not found in session: {session_dir}")

    sidecar = VideoSidecar.model_validate_json(sidecar_path.read_text(encoding="utf-8"))
    device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))

    rel = f"video/{sidecar.name}.mp4"
    existing = [s for s in device.streams if s.role == "video" and s.name == sidecar.name]
    if existing and not force:
        raise VideoIngestError(
            f"video stream '{sidecar.name}' already exists (use force=True)"
        )
    device.streams = [
        s for s in device.streams if not (s.role == "video" and s.name == sidecar.name)
    ]

    (session_dir / "video").mkdir(exist_ok=True)
    shutil.copyfile(mp4_path, session_dir / rel)
    device.streams.append(
        StreamRef(name=sidecar.name, path=rel, fmt="mp4", role="video", rate_hz=sidecar.fps)
    )
    dump_json(device, device_path)
    write_checksums(session_dir)
    return session_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_ingest.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/ingest/video.py tests/test_video_ingest.py
git commit -m "feat(video): ingest_video augment with re-seal and duplicate guard"
```

---

### Task 3: loop-closure with consent filtering

**Files:**
- Test: `tests/test_video_consent_filtering.py` (new test only — no source change)

**Interfaces:**
- Consumes: `ingest_video` (Task 2); `package_release` (existing); `resolve_absent` behavior via packaging.
- Produces: proof that an ingested video is filtered correctly by consent at release time. **No production code in this task** — if any source change is needed to make these pass, STOP and report (it would indicate a defect in Task 2 or in slice 2).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_video_consent_filtering.py
import json
from pathlib import Path

from htdp.ingest.video import ingest_video
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _session_with_video(tmp_path: Path, allow_video: bool) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    session = tmp_path / "raw" / "synth-0001"
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sidecar = tmp_path / "video.json"
    sidecar.write_text(json.dumps({"name": "frontal", "fps": 30.0}), encoding="utf-8")
    ingest_video(session, mp4, sidecar)
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["distribute_raw_video"] = allow_video
    consent.write_text(json.dumps(data), encoding="utf-8")
    # consent edit invalidates checksums; re-seal so the session validates.
    from htdp.io.checksums import write_checksums

    write_checksums(session)
    return tmp_path / "raw"


def test_allowed_video_survives_packaging(tmp_path: Path):
    raw = _session_with_video(tmp_path, allow_video=True)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert (out / "data/synth-0001/video/frontal.mp4").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" not in manifest["absent_modalities"]


def test_forbidden_video_dropped_at_packaging(tmp_path: Path):
    raw = _session_with_video(tmp_path, allow_video=False)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert not (out / "data/synth-0001/video/frontal.mp4").exists()
    assert (out / "data/synth-0001/streams/motion_right_wrist.csv").exists()  # motion intact
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_consent_filtering.py -v`
Expected: FAIL initially only if Task 2 is incomplete. If Task 2 is done, these should PASS immediately (they exercise existing wiring). Run them; if they PASS, that is the expected outcome for this task — proceed to commit. If they FAIL, STOP and report (defect in Task 2 or slice 2), do not patch around it.

- [ ] **Step 3: (no implementation)**

This task adds tests only. There is no source change. If Step 2 passed, skip to Step 4.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_consent_filtering.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_video_consent_filtering.py
git commit -m "test(video): consent filtering drops/keeps ingested video"
```

---

### Task 4: CLI `ingest-video` command

**Files:**
- Modify: `src/htdp/cli.py` (add command after `ingest`)
- Test: `tests/test_cli_shell.py` (append; reuse the file's `CliRunner`/`app` pattern)

**Interfaces:**
- Consumes: `ingest_video`, `VideoIngestError` (Task 2).
- Produces: `htdp ingest-video <session_dir> <clip.mp4> <video.json> [--force]`. Exits `1` on `VideoIngestError | ValidationError | FileNotFoundError`, printing `error: ...` to stderr. Note: typer maps an underscore command function name to a hyphenated command (`ingest_video` → `ingest-video`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_shell.py`:

```python
def test_ingest_video_happy_and_missing(tmp_path):
    import json

    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    session = tmp_path / "raw" / "synth-0001"
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sidecar = tmp_path / "video.json"
    sidecar.write_text(json.dumps({"name": "frontal", "fps": 30.0}), encoding="utf-8")

    runner = CliRunner()
    ok = runner.invoke(app, ["ingest-video", str(session), str(mp4), str(sidecar)])
    assert ok.exit_code == 0, ok.output
    assert (session / "video" / "frontal.mp4").exists()

    bad = runner.invoke(
        app, ["ingest-video", str(session), str(tmp_path / "nope.mp4"), str(sidecar)]
    )
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shell.py -k ingest_video -v`
Expected: FAIL — no command `ingest-video` (usage error / exit 2)

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `ingest` command:

```python
@app.command()
def ingest_video(
    session_dir: Path,
    mp4_file: Path,
    sidecar: Path,
    force: bool = False,
) -> None:
    """Augment a raw session with a video file (registers it in device_config)."""
    from pydantic import ValidationError

    from htdp.ingest.video import VideoIngestError, ingest_video as _ingest_video

    try:
        d = _ingest_video(session_dir, mp4_file, sidecar, force=force)
    except (VideoIngestError, ValidationError, FileNotFoundError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_shell.py -k ingest_video -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shell.py
git commit -m "feat(video): add htdp ingest-video CLI command"
```

---

### Task 5: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md` (video StreamRef + opaque-file policy)
- Modify: `AGENTS.md` (ingest-video usage + re-checksum note)
- Modify: `docs/ROADMAP.md` (mark video capture in progress)

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — document the video stream: a `StreamRef` with `role="video"`, `fmt="mp4"`, `path="video/<name>.mp4"`, `rate_hz` = declared fps. Note the `.mp4` is stored opaque (no decode/transcode/introspection).

`AGENTS.md` — add usage `htdp ingest-video <session_dir> <clip.mp4> <video.json> [--force]`; note that `ingest-video` re-writes `device_config.json` + `checksums.sha256` of an existing raw session as a **raw-construction** step (populating the `video/` slot), which is distinct from the prohibited *processing-stage* mutation of raw.

`docs/ROADMAP.md` — change the "Video capture (MP4 population in the `video/` slot)" bullet to mark progress, e.g. append `— **in progress (ingest-video landed)**`.

- [ ] **Step 2: Run the full gate**

Run:
```
uv run ruff format --check . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest
```
Expected: ruff clean; pytest all pass (only the pre-existing mujoco replay skip remains if the replay extra is absent); mypy `Success`.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(video): document ingest-video and the opaque video stream"
```

---

## Self-Review

**Spec coverage** (`2026-06-21-video-ingest-design.md`):
- `VideoSidecar` (local model, name>0, fps>0) + `VideoIngestError` → Task 1. ✓
- `ingest_video` orchestrator: validate, guard duplicate, copy, register StreamRef, re-checksum, no partial writes → Task 2. ✓
- Standalone augment of an existing raw session; validate passes after re-seal → Task 2 test. ✓
- Opaque mp4 (dummy bytes, no decode) → Tasks 2–4 fixtures. ✓
- Duplicate guard + `force` overwrite-without-dup → Task 2. ✓
- Loop closure with consent filtering (allowed kept / forbidden dropped) → Task 3. ✓
- CLI `ingest-video` with error→exit-1 pattern → Task 4. ✓
- Docs (DATA_CONTRACT, AGENTS re-checksum note, ROADMAP), no schema re-export → Task 5. ✓
- Non-goals (no decode, no frame sync, multi-cam via repeated calls, no schema change) respected throughout.

**No-touch check:** only new files (`ingest/video.py`, the new tests) plus appends to `cli.py` and docs. `ingest_xdf`, `synth`, `release`, `validate`, `processing`, `qc`, `replay`, `schemas` are untouched.

**Placeholder scan:** none — every code/test step is concrete. (Task 3 Step 2 explicitly states the tests may pass immediately against existing wiring; that is the intended outcome, with a STOP instruction if they fail.)

**Type consistency:** `VideoSidecar.name/fps` (Task 1) consumed in Task 2; `ingest_video(session_dir, mp4_path, sidecar_path, force)` signature (Task 2) matches the CLI call in Task 4 (`_ingest_video(session_dir, mp4_file, sidecar, force=force)`); `StreamRef(name, path, fmt, role, rate_hz)` matches the existing schema; the registered `path="video/<name>.mp4"` is the same string asserted in Tasks 2–3 and dropped by slice-2's `MODALITY_GLOBS["video"] = ("video/**/*",)`.
```
