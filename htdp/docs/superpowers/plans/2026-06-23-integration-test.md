# End-to-End Integration Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CLI-level end-to-end test that threads the whole pipeline and asserts the cross-slice properties no unit test covers, plus gated segments for the optional-extra stages.

**Architecture:** One new test module `tests/test_integration_pipeline.py` driving the real `htdp` commands through `typer.testing.CliRunner`, with each test switching cwd via pytest `monkeypatch.chdir(tmp_path)` (so the CLI's hardcoded `data/` paths resolve; typer's CliRunner has no `isolated_filesystem`). A base-env core test always runs; `importorskip`-gated tests cover `replay-ik`, `export-release-rosbag`, and the XDF `ingest` entry. No production code change; one small docs note.

**Tech Stack:** Python, typer CliRunner, pytest. Optional extras: mink (replay), rosbags (rosbag), pyxdf (ingest).

## Global Constraints

- Test-only slice — NO production code change, no new dependency, no schema change.
- Drive the pipeline at CLI level via `CliRunner`; switch cwd with pytest `monkeypatch.chdir(tmp_path)` (typer's CliRunner has NO `isolated_filesystem`) because `process`/`package` hardcode cwd-relative `data/raw`, `data/processed`, `data/releases`. Each test takes `(tmp_path, monkeypatch)`.
- The core test is base-env and MUST run (never gated) — a missing extra must never hide a core regression.
- Each optional stage is its own `pytest.importorskip(...)` test: `mink` → replay-ik, `rosbags` → rosbag, `pyxdf` → ingest.
- Three verified ordering/naming constraints the test must honor: (1) cwd-anchored `data/`; (2) consent edits BEFORE `ingest-video` (which re-checksums) or `validate` fails on checksum mismatch; (3) `ingest --out` dir must be the session dir named `data/raw/synth-0001` (`process` parses an int from the dir name).
- All stages live-verified green: core thread + XDF segment confirmed end-to-end.
- `ingest-video` sidecar = `{"name":"cam0","fps":30.0}`; the mp4 is the 3 bytes `b"\x00\x01\x02"` (copied opaque). `tests/_xdf_writer.py` exposes `write_xdf(raw_session_dir, xdf_path)` and `build_sidecar(raw_session_dir) -> dict`.

---

### Task 1: Core end-to-end test + shared helpers

**Files:**
- Create: `tests/test_integration_pipeline.py`

**Interfaces:**
- Produces: `_run(runner, *args) -> Result` (asserts exit 0); `_build_core_release(runner) -> None` (synth ×2 + mixed video consent + ingest-video + package, in the current cwd); `test_full_pipeline_cli`.

- [ ] **Step 1: Write the core test + helpers**

Create `tests/test_integration_pipeline.py`:

```python
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from htdp.cli import app


def _run(runner: CliRunner, *args: str):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"htdp {' '.join(args)} failed:\n{result.output}"
    return result


def _build_core_release(runner: CliRunner) -> None:
    """synth 2 sessions, mixed video consent, ingest-video, package — in the current cwd.

    Order matters: edit consent BEFORE ingest-video (which re-checksums the folder), or
    validate would fail on a consent.json checksum mismatch.
    """
    _run(runner, "synth", "--out", "data/raw", "--seed", "1")
    _run(runner, "synth", "--out", "data/raw", "--seed", "2")
    Path("clip.mp4").write_bytes(b"\x00\x01\x02")
    Path("vid.json").write_text(json.dumps({"name": "cam0", "fps": 30.0}), encoding="utf-8")
    for sid, allow in [("synth-0001", True), ("synth-0002", False)]:
        cpath = Path(f"data/raw/{sid}/consent.json")
        c = json.loads(cpath.read_text(encoding="utf-8"))
        c["distribute_raw_video"] = allow
        cpath.write_text(json.dumps(c), encoding="utf-8")
        _run(runner, "ingest-video", f"data/raw/{sid}", "clip.mp4", "vid.json")
    _run(
        runner, "package", "synth-0001", "synth-0002",
        "--release", "rel", "--profile", "commercial_dataset",
    )


def test_full_pipeline_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)

    for sid in ["synth-0001", "synth-0002"]:
        _run(runner, "validate", f"data/raw/{sid}")
        _run(runner, "process", f"data/raw/{sid}")
        _run(runner, "qc", f"data/processed/{sid}")

    # per-session consent survived into the packaged release
    assert Path("data/releases/rel/data/synth-0001/video/cam0.mp4").exists()
    assert not Path("data/releases/rel/data/synth-0002/video/cam0.mp4").exists()
    man = json.loads(Path("data/releases/rel/manifest.json").read_text(encoding="utf-8"))
    assert man["absent_modalities_by_session"] == {
        "synth-0001": ["eeg"],
        "synth-0002": ["eeg", "video"],
    }
    assert man["absent_modalities"] == ["eeg"]

    # catalogs
    _run(runner, "catalog", "data/raw", "sess.parquet")
    _run(runner, "catalog-releases", "data/releases", "rel.parquet")
    q = _run(runner, "catalog-query", "sess.parquet", "--modality", "video")
    # grain consistency: the catalog reflects RAW device_config (both sessions carry the
    # video StreamRef), even though the release dropped video for synth-0002 by consent.
    assert sorted(q.output.split()) == ["synth-0001", "synth-0002"]

    # release-level BIDS export carries both subjects
    _run(runner, "export-release-bids", "data/releases/rel", "bids_out")
    assert Path("bids_out/dataset_description.json").exists()
    subs = sorted(p.name for p in Path("bids_out").glob("sub-*"))
    assert subs == ["sub-p0001", "sub-p0002"]
```

- [ ] **Step 2: Run the core test (base env)**

Run: `uv sync --extra dev && uv run pytest tests/test_integration_pipeline.py::test_full_pipeline_cli -v`
Expected: PASS. It RUNS (not skipped) with only the dev extra — no replay/rosbag/ingest extra needed.

- [ ] **Step 3: Lint**

Run: `uv run ruff format --check tests/test_integration_pipeline.py && uv run ruff check tests/test_integration_pipeline.py`
Expected: pass (run `uv run ruff format tests/test_integration_pipeline.py` first if format-check fails).

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: end-to-end CLI pipeline integration test"
```

---

### Task 2: Gated optional-extra segments

**Files:**
- Modify: `tests/test_integration_pipeline.py` (append three gated tests)

**Interfaces:**
- Consumes: `_run`, `_build_core_release` from Task 1.

- [ ] **Step 1: Append the three gated tests**

Append to `tests/test_integration_pipeline.py`:

```python
def test_pipeline_replay_ik(tmp_path, monkeypatch):
    pytest.importorskip("mink")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)
    _run(runner, "replay-ik", "data/releases/rel", "--max-steps", "10", "--out", "traj.csv")
    assert Path("traj.csv").exists()
    assert Path("traj.csv").read_text(encoding="utf-8").splitlines()[0].startswith("timestamp_s")


def test_pipeline_rosbag(tmp_path, monkeypatch):
    pytest.importorskip("rosbags")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)
    _run(runner, "export-release-rosbag", "data/releases/rel", "rosbag_out")
    bag_dirs = [p for p in Path("rosbag_out").iterdir() if p.is_dir()]
    assert bag_dirs  # at least one per-session bag directory


def test_pipeline_xdf_ingest(tmp_path, monkeypatch):
    pytest.importorskip("pyxdf")
    from tests._xdf_writer import build_sidecar, write_xdf

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _run(runner, "synth", "--out", "src", "--seed", "1")
    write_xdf(Path("src/synth-0001"), Path("s.xdf"))
    Path("ingest.json").write_text(
        json.dumps(build_sidecar(Path("src/synth-0001"))), encoding="utf-8"
    )
    # out-dir must be the session dir, named like synth-0001 (process parses an int
    # from the dir name).
    _run(runner, "ingest", "s.xdf", "ingest.json", "--out", "data/raw/synth-0001")
    _run(runner, "validate", "data/raw/synth-0001")
    _run(runner, "process", "data/raw/synth-0001")
```

- [ ] **Step 2: Run the gated tests with all extras synced (they MUST run, not skip)**

Run: `uv sync --extra dev --extra replay --extra rosbag --extra ingest && uv run pytest tests/test_integration_pipeline.py -v`
Expected: all 4 tests PASS, 0 skipped (every extra is installed, so `importorskip` does not skip).

- [ ] **Step 3: Confirm the gated tests SKIP cleanly without their extras (no hard failure)**

Run: `uv sync --extra dev && uv run pytest tests/test_integration_pipeline.py -v`
Expected: `test_full_pipeline_cli` PASSES; the three gated tests SKIP (their extras absent). 1 passed, 3 skipped — proving the core is independent and the gates are clean. (Then re-sync all extras for the final gate: `uv sync --extra dev --extra replay --extra rosbag --extra ingest`.)

- [ ] **Step 4: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest`
Expected: all pass (with all extras synced, the integration gated tests run; unrelated extras decide other modules' skips).

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: gated replay-ik / rosbag / xdf-ingest pipeline segments"
```

---

### Task 3: Docs note

**Files:**
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Add the integration-test + constraints note**

In `docs/ARCHITECTURE.md`, add a short subsection (near the pipeline/CLI description) noting:
`tests/test_integration_pipeline.py` threads the whole pipeline end-to-end through the CLI,
and recording the two cwd/checksum gotchas it encodes: (1) the CLI pipeline is anchored at a
`data/` working directory (`process`/`package` use `data/raw`, `data/processed`,
`data/releases`); (2) consent edits must precede a re-checksumming step (`ingest-video`) or a
raw session fails `validate` on a checksum mismatch; and (3) a raw session directory must be
named with the session-id convention (`synth-0001`) because `process` parses the session
number from the directory name. Keep the wording consistent with the surrounding doc.

- [ ] **Step 2: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: note end-to-end integration test and CLI cwd/checksum constraints"
```

---

## Self-Review

**1. Spec coverage:**
- Core CLI thread synth→ingest-video→validate→process→qc→package→catalog(s)→export-release-bids → Task 1. ✅
- Cross-slice consent assertion (A kept, B dropped, manifest by_session + intersection) → Task 1 Step 1. ✅
- Grain assertion (catalog-query video → both; release dropped B) → Task 1 Step 1. ✅
- `monkeypatch.chdir(tmp_path)` for cwd-anchored paths → Task 1. ✅
- Consent-before-ingest-video ordering → `_build_core_release` (Task 1). ✅
- Gated replay-ik / rosbag / xdf-ingest, each `importorskip`, core never gated → Task 2; clean-skip proof in Step 3. ✅
- XDF out-dir = session-dir name `synth-0001` (constraint 3) → Task 2 test + comment. ✅
- Reuse `tests._xdf_writer.write_xdf`/`build_sidecar` → Task 2. ✅
- Docs note with the three constraints → Task 3. ✅
- No production change / no new dep → no such task. ✅

**2. Placeholder scan:** No TBD/TODO; full test code inline; every command has expected output. ✅

**3. Type consistency:** `_run(runner, *args)` and `_build_core_release(runner)` signatures identical across Task 1 (definition) and Task 2 (callers). Release path `data/releases/rel`, sidecar `{"name":"cam0","fps":30.0}`, mp4 bytes, and the `synth-0001`/`synth-0002` ids are consistent across helper, core, and gated tests. All assertions match the live-verified prototype output. ✅
