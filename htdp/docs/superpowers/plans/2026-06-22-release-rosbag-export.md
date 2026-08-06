# Release-Level rosbag2 Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp export-release-rosbag`: export a packaged release into one rosbag2 (mcap) bag per session, carrying motion (per-tracker `geometry_msgs/PoseStamped`) and events (`std_msgs/String`). The dataset inherits the release's consent filtering.

**Architecture:** New module `src/htdp/export/rosbag.py` paralleling `export/bids.py`. `_write_session_bag` writes one rosbag2 bag from one raw-session folder; `export_release_rosbag` loops a release's `data/<sid>/` sessions, one bag per session named `sanitize(session_id)`, force-guarding the whole `out_dir`. A new typer CLI command wraps it. `rosbags` is a new optional dependency (pure-python, no ROS install).

**Tech Stack:** Python ≥3.11, pydantic v2, typer, pytest. `rosbags` (optional extra `rosbag`) for bag writing/reading.

## Global Constraints

Copied verbatim from `AGENTS.md` + the spec:

- Python `>=3.11`. mypy `strict = true` (global); `src/htdp/export` is in the gate target.
- ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check`.
- JSON via `io.canonical.dump_json`; text via `newline="\n"`. (Not needed here — rosbags owns all output.)
- **No partial writes:** validate the source before creating `out_dir`.
- **No persisted-schema change** → no JSON-Schema re-export.
- Edits limited to `src/htdp/export/rosbag.py` (new), `src/htdp/cli.py`, `pyproject.toml`, new tests, docs. Do NOT touch other `export/*` modules, `ingest`, `release`, `synth`, `schemas`, etc.
- Deterministic at the **logical** level (topics, counts, values), NOT byte-identical (mcap embeds a library-version string). Tests read the bag back; they never hash bytes.
- **CRITICAL false-green guard:** `rosbags` is NOT installed in the base env. Before claiming any green, run `uv sync --extra rosbag --extra dev` and confirm the new gated tests **RUN, not SKIP**. A prior slice shipped 3 defects hidden behind skipped optional-dep tests.

**Verified `rosbags` 0.11.x API (probed against the installed lib):**
- `from rosbags.rosbag2 import Writer, Reader`
- `from rosbags.rosbag2.writer import StoragePlugin` → `StoragePlugin.MCAP`
- `from rosbags.typesys import Stores, get_typestore`; `ts = get_typestore(Stores.ROS2_HUMBLE)`
- Static, mypy-friendly message classes:
  `from rosbags.typesys.stores.ros2_humble import geometry_msgs__msg__PoseStamped, geometry_msgs__msg__Pose, geometry_msgs__msg__Point, geometry_msgs__msg__Quaternion, std_msgs__msg__Header, std_msgs__msg__String, builtin_interfaces__msg__Time`
- `Writer(path, version=9, storage_plugin=StoragePlugin.MCAP)` — context manager; **`path` must NOT already exist** (Writer creates it, raises `WriterError` if present). Produces `path/<name>.mcap` + `path/metadata.yaml`.
- `conn = writer.add_connection(topic, MsgClass.__msgtype__, typestore=ts)`
- `writer.write(conn, timestamp_ns: int, ts.serialize_cdr(msg, MsgClass.__msgtype__))`
- Reader: `with Reader(path) as rd: rd.connections` (each has `.topic`, `.msgcount`, `.msgtype`); `for conn, t, raw in rd.messages(): msg = ts.deserialize_cdr(raw, conn.msgtype)`.

**Reference — release layout** (`release/package.py`): `releases/<name>/data/<sid>/` are consent-filtered raw-session folders (each has `session.json`, `device_config.json`, `streams/…`).

**Reference — raw stream formats (verified):**
- Per-tracker motion CSV (`role == "motion"`, one file per tracker): header `timestamp_s,tracker_id,x_m,y_m,z_m,qw,qx,qy,qz,quality,defect_tag`.
- Events CSV (`role == "events"`): header `timestamp_s,event_id,label,phase,source,confidence,notes`.
- `sanitize(label)` drops non-alphanumerics (so `right_wrist` → `rightwrist`).

---

### Task 1: `pyproject` extra + `rosbag.py` — `_write_session_bag`

**Files:**
- Modify: `pyproject.toml` (add `rosbag` extra)
- Create: `src/htdp/export/rosbag.py`
- Test: `tests/test_release_rosbag_session.py`

**Interfaces:**
- Produces:
  - `RosbagExportError(RuntimeError)`
  - `_write_session_bag(bag_dir: Path, raw_dir: Path) -> None` — writes one rosbag2 (mcap) bag into the not-yet-existing `bag_dir`. Topic `/motion/<sanitize(tracker)>` (`geometry_msgs/msg/PoseStamped`, one msg per CSV row) for every `role=="motion"` stream; topic `/events` (`std_msgs/msg/String`, one msg per row) if a `role=="events"` stream exists. Raises `RosbagExportError` on missing `session.json`/`device_config.json` or no motion stream.

- [ ] **Step 1: Add the optional dependency**

In `pyproject.toml`, under `[project.optional-dependencies]`, add the `rosbag` line (keep the others):

```toml
[project.optional-dependencies]
replay = ["mujoco>=3.1"]
ingest = ["pyxdf>=1.16"]
rosbag = ["rosbags>=0.10"]
dev = ["pytest>=8.0", "ruff>=0.5", "mypy>=1.10"]
```

Then sync so the lib is importable for the rest of this task:

```bash
uv sync --extra rosbag --extra dev --extra ingest --extra replay
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_release_rosbag_session.py
from pathlib import Path

import pytest

pytest.importorskip("rosbags")

from rosbags.rosbag2 import Reader  # noqa: E402
from rosbags.typesys import Stores, get_typestore  # noqa: E402

from htdp.export.rosbag import RosbagExportError, _write_session_bag  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402


def _read(bag: Path) -> tuple[dict[str, int], dict]:
    ts = get_typestore(Stores.ROS2_HUMBLE)
    counts: dict[str, int] = {}
    first_pose: dict = {}
    with Reader(bag) as rd:
        for conn, _t, raw in rd.messages():
            counts[conn.topic] = counts.get(conn.topic, 0) + 1
            if conn.topic == "/motion/rightwrist" and "x" not in first_pose:
                m = ts.deserialize_cdr(raw, conn.msgtype)
                first_pose = {
                    "x": m.pose.position.x,
                    "y": m.pose.position.y,
                    "z": m.pose.position.z,
                    "w": m.pose.orientation.w,
                }
    return counts, first_pose


def test_session_bag_topics_counts_and_values(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    bag = tmp_path / "bag"
    _write_session_bag(bag, tmp_path / "raw" / "synth-0001")
    assert (bag / "metadata.yaml").exists()
    counts, first_pose = _read(bag)
    # 4 motion trackers + events
    assert "/motion/rightwrist" in counts
    assert "/motion/leftwrist" in counts
    assert "/motion/torso" in counts
    assert "/motion/object" in counts
    assert "/events" in counts
    # first right_wrist row: x=0.309983,y=0.019967,z=0.904992,qw=1
    assert first_pose["x"] == pytest.approx(0.309983, abs=1e-6)
    assert first_pose["z"] == pytest.approx(0.904992, abs=1e-6)
    assert first_pose["w"] == pytest.approx(1.0, abs=1e-6)


def test_missing_metadata_raises(tmp_path: Path):
    empty = tmp_path / "raw" / "synth-9999"
    empty.mkdir(parents=True)
    with pytest.raises(RosbagExportError):
        _write_session_bag(tmp_path / "bag", empty)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --extra rosbag --extra dev pytest tests/test_release_rosbag_session.py -v`
Expected: FAIL — `ImportError: cannot import name '_write_session_bag'` (NOT skipped — `rosbags` is installed).

- [ ] **Step 4: Write minimal implementation**

Create `src/htdp/export/rosbag.py`:

```python
from __future__ import annotations

from pathlib import Path

from rosbags.rosbag2 import Writer
from rosbags.rosbag2.writer import StoragePlugin
from rosbags.typesys import Stores, get_typestore
from rosbags.typesys.stores.ros2_humble import (
    builtin_interfaces__msg__Time as Time,
    geometry_msgs__msg__Point as Point,
    geometry_msgs__msg__Pose as Pose,
    geometry_msgs__msg__PoseStamped as PoseStamped,
    geometry_msgs__msg__Quaternion as Quaternion,
    std_msgs__msg__Header as Header,
    std_msgs__msg__String as StringMsg,
)

from htdp.export.labels import sanitize
from htdp.schemas.models import DeviceConfig, Session

_TYPESTORE = get_typestore(Stores.ROS2_HUMBLE)


class RosbagExportError(RuntimeError):
    """Raised when a release/session cannot be exported to rosbag2."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


def _ns(timestamp_s: float) -> int:
    return int(round(timestamp_s * 1e9))


def _pose_stamped(row: dict[str, str], frame_id: str) -> PoseStamped:
    ns = _ns(float(row["timestamp_s"]))
    return PoseStamped(
        header=Header(
            stamp=Time(sec=ns // 1_000_000_000, nanosec=ns % 1_000_000_000),
            frame_id=frame_id,
        ),
        pose=Pose(
            position=Point(x=float(row["x_m"]), y=float(row["y_m"]), z=float(row["z_m"])),
            orientation=Quaternion(
                x=float(row["qx"]), y=float(row["qy"]), z=float(row["qz"]), w=float(row["qw"])
            ),
        ),
    )


def _write_session_bag(bag_dir: Path, raw_dir: Path) -> None:
    session_path = raw_dir / "session.json"
    device_path = raw_dir / "device_config.json"
    if not session_path.exists() or not device_path.exists():
        raise RosbagExportError(f"raw session missing metadata: {raw_dir}")

    Session.model_validate_json(session_path.read_text(encoding="utf-8"))
    device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))
    motion_streams = [s for s in device.streams if s.role == "motion"]
    if not motion_streams:
        raise RosbagExportError(f"no motion streams in {raw_dir}")
    event_streams = [s for s in device.streams if s.role == "events"]

    with Writer(bag_dir, version=9, storage_plugin=StoragePlugin.MCAP) as writer:
        for stream in motion_streams:
            topic = f"/motion/{sanitize(stream.name)}"
            conn = writer.add_connection(topic, PoseStamped.__msgtype__, typestore=_TYPESTORE)
            for row in _read_csv(raw_dir / stream.path):
                msg = _pose_stamped(row, stream.name)
                writer.write(conn, _ns(float(row["timestamp_s"])), _TYPESTORE.serialize_cdr(msg, PoseStamped.__msgtype__))
        for stream in event_streams:
            conn = writer.add_connection("/events", StringMsg.__msgtype__, typestore=_TYPESTORE)
            for row in _read_csv(raw_dir / stream.path):
                msg = StringMsg(data=row["label"])
                writer.write(conn, _ns(float(row["timestamp_s"])), _TYPESTORE.serialize_cdr(msg, StringMsg.__msgtype__))
```

(Note: `Session.model_validate_json` is called for validation/parity with the BIDS path even though only `device` fields are used here; keep it so a malformed `session.json` is rejected.)

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --extra rosbag --extra dev pytest tests/test_release_rosbag_session.py -v`
Expected: PASS (2 passed, 0 skipped). If any test SKIPs, STOP — the extra is not synced.

- [ ] **Step 6: Lint + type-check the new module**

Run:
```bash
uv run ruff format src/htdp/export/rosbag.py tests/test_release_rosbag_session.py
uv run ruff check src/htdp/export/rosbag.py tests/test_release_rosbag_session.py
uv run --extra rosbag mypy src/htdp/export
```
Expected: ruff clean; mypy `Success`. **If mypy reports `import-untyped` / `import-not-found` for `rosbags.*`**, add to `pyproject.toml`:
```toml
[[tool.mypy.overrides]]
module = "rosbags.*"
ignore_missing_imports = true
```
and re-run until `Success`. (The static `ros2_humble` classes are real dataclasses, so message construction itself should type-check; the override only covers an untyped top-level import if present.)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/htdp/export/rosbag.py tests/test_release_rosbag_session.py
git commit -m "feat(export): _write_session_bag rosbag2 mcap writer (motion+events)"
```

---

### Task 2: `rosbag.py` — `export_release_rosbag`

**Files:**
- Modify: `src/htdp/export/rosbag.py` (add imports + function)
- Test: `tests/test_release_rosbag_export.py`

**Interfaces:**
- Consumes: `_write_session_bag`, `RosbagExportError`, `sanitize`, `Session`.
- Produces: `export_release_rosbag(release_dir: Path, out_dir: Path, force: bool = False) -> Path` — loops `release_dir/data/<sid>/`, writes one bag per session into `out_dir/<sanitize(session_id)>/`, force-guards the whole `out_dir`. Raises `RosbagExportError` on missing `data/`, empty release, or existing `out_dir` without `force`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_release_rosbag_export.py
from pathlib import Path

import pytest

pytest.importorskip("rosbags")

from rosbags.rosbag2 import Reader  # noqa: E402

from htdp.export.rosbag import RosbagExportError, export_release_rosbag  # noqa: E402
from htdp.release.package import package_release  # noqa: E402
from htdp.schemas.enums import ReleaseProfile  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    return package_release(
        ["synth-0001", "synth-0002"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )


def _topics(bag: Path) -> set[str]:
    with Reader(bag) as rd:
        return {c.topic for c in rd.connections}


def test_one_bag_per_session(tmp_path: Path):
    out = export_release_rosbag(_release(tmp_path), tmp_path / "bags")
    bags = sorted(p.name for p in out.iterdir() if p.is_dir())
    assert len(bags) == 2
    for name in bags:
        topics = _topics(out / name)
        assert "/events" in topics
        assert any(t.startswith("/motion/") for t in topics)


def test_missing_data_dir_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(RosbagExportError):
        export_release_rosbag(tmp_path / "empty", tmp_path / "bags")


def test_empty_release_raises(tmp_path: Path):
    rel = tmp_path / "rel"
    (rel / "data").mkdir(parents=True)
    with pytest.raises(RosbagExportError):
        export_release_rosbag(rel, tmp_path / "bags")


def test_force_overwrite(tmp_path: Path):
    rel = _release(tmp_path)
    export_release_rosbag(rel, tmp_path / "bags")
    with pytest.raises(RosbagExportError):
        export_release_rosbag(rel, tmp_path / "bags")
    export_release_rosbag(rel, tmp_path / "bags", force=True)  # ok
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra rosbag --extra dev pytest tests/test_release_rosbag_export.py -v`
Expected: FAIL — `ImportError: cannot import name 'export_release_rosbag'` (NOT skipped).

- [ ] **Step 3: Write minimal implementation**

In `src/htdp/export/rosbag.py`, add `import shutil` to the top (after `from __future__ import annotations`):

```python
import shutil
```

Append the function at the end of the file:

```python
def export_release_rosbag(release_dir: Path, out_dir: Path, force: bool = False) -> Path:
    data_dir = release_dir / "data"
    if not data_dir.is_dir():
        raise RosbagExportError(f"release has no data/ directory: {release_dir}")
    session_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    if not session_dirs:
        raise RosbagExportError(f"release has no sessions: {release_dir}")

    if out_dir.exists():
        if not force:
            raise RosbagExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for sd in session_dirs:
        session = Session.model_validate_json((sd / "session.json").read_text(encoding="utf-8"))
        _write_session_bag(out_dir / sanitize(session.session_id), sd)
    return out_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra rosbag --extra dev pytest tests/test_release_rosbag_export.py tests/test_release_rosbag_session.py -v`
Expected: PASS (6 passed, 0 skipped).

- [ ] **Step 5: Lint + type-check**

Run:
```bash
uv run ruff format src/htdp/export/rosbag.py tests/test_release_rosbag_export.py
uv run ruff check src/htdp/export/rosbag.py tests/test_release_rosbag_export.py
uv run --extra rosbag mypy src/htdp/export
```
Expected: ruff clean; mypy `Success`.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/export/rosbag.py tests/test_release_rosbag_export.py
git commit -m "feat(export): export_release_rosbag one mcap bag per session"
```

---

### Task 3: CLI `export-release-rosbag`

**Files:**
- Modify: `src/htdp/cli.py` (add command after `export_release_bids`)
- Test: `tests/test_cli_shell.py` (append)

**Interfaces:**
- Consumes: `export_release_rosbag`, `RosbagExportError`.
- Produces: `htdp export-release-rosbag <release_dir> <out_dir> [--force]`; exit 1 on `RosbagExportError`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli_shell.py`:

```python
def test_export_release_rosbag_happy_and_missing(tmp_path):
    import pytest

    pytest.importorskip("rosbags")

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
    ok = runner.invoke(app, ["export-release-rosbag", str(rel), str(tmp_path / "bags")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bags" / "synth0001" / "metadata.yaml").exists()

    bad = runner.invoke(app, ["export-release-rosbag", str(tmp_path / "nope"), str(tmp_path / "b2")])
    assert bad.exit_code == 1
    assert "error:" in bad.output
```

(`sanitize("synth-0001")` → `synth0001`, hence the bag dir name.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra rosbag --extra dev pytest tests/test_cli_shell.py -k export_release_rosbag -v`
Expected: FAIL — no command `export-release-rosbag` (usage error / exit 2).

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `export_release_bids` command:

```python
@app.command()
def export_release_rosbag(release_dir: Path, out_dir: Path, force: bool = False) -> None:
    """Export a packaged release to one rosbag2 (mcap) bag per session."""
    from htdp.export.rosbag import RosbagExportError, export_release_rosbag as _export

    try:
        d = _export(release_dir, out_dir, force=force)
    except RosbagExportError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"wrote {d}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra rosbag --extra dev pytest tests/test_cli_shell.py -k export_release_rosbag -v`
Expected: PASS (1 passed, 0 skipped).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_cli_shell.py
git commit -m "feat(export): add htdp export-release-rosbag CLI command"
```

---

### Task 4: Docs + full gate

**Files:**
- Modify: `docs/DATA_CONTRACT.md`, `AGENTS.md`, `docs/ROADMAP.md`

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/DATA_CONTRACT.md` — add a "Release-level rosbag2 export" note: a packaged release exports to one rosbag2 (mcap) bag **per session** under `out_dir/<session_id>/`; motion → per-tracker topic `/motion/<tracker>` (`geometry_msgs/PoseStamped`), events → `/events` (`std_msgs/String`); the dataset inherits the release's consent filtering; EEG is not yet exported to rosbag2.

`AGENTS.md` — add usage `htdp export-release-rosbag <release_dir> <out_dir> [--force]`; note it is a read-only export of a packaged release and needs the `rosbag` extra (`uv sync --extra rosbag`).

`docs/ROADMAP.md` — mark "ROS 2 / rosbag2 export" as in progress/done (motion+events landed; EEG deferred).

- [ ] **Step 2: Run the full gate**

Run:
```bash
uv sync --extra rosbag --extra dev --extra ingest --extra replay
uv run ruff format --check . && uv run ruff check .
uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass — the new rosbag tests RUN (not skip) because `rosbags` is synced; only the pre-existing mujoco-replay test may skip if the `replay` extra binary is unavailable; mypy `Success`.

**Verification gate (false-green guard):** confirm the pytest summary shows the rosbag tests as PASSED, not SKIPPED. Grep the output: `uv run pytest -rs | grep -i rosbag` must show no `SKIPPED ... rosbag` lines.

- [ ] **Step 3: Commit**

```bash
git add docs/DATA_CONTRACT.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(export): document release-level rosbag2 export"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-release-rosbag-export-design.md`):
- `_write_session_bag` (motion per-tracker PoseStamped + events String, raises on missing metadata/no motion) → Task 1. ✓
- `export_release_rosbag` (loop `data/<sid>`, one bag per `sanitize(session_id)`, force-guard whole out_dir, errors on missing/empty/exists) → Task 2. ✓
- mcap storage via `rosbags`, optional `rosbag` extra → Task 1 (pyproject + Writer MCAP). ✓
- Message mapping (stamp ns, frame_id=tracker, pos xyz, orient xyzw, drop quality/defect_tag; String data=label, onset via log time) → Task 1 `_pose_stamped` / events loop. ✓
- Determinism = read-back, not byte hash → Tasks 1–2 tests reopen bags via `Reader`. ✓
- CLI `export-release-rosbag` → Task 3. ✓
- Docs (DATA_CONTRACT, AGENTS, ROADMAP), no schema re-export → Task 4. ✓
- Non-goals (EEG, tf/TransformStamped, single-raw-session cmd, sqlite3, single-bag) — none implemented. ✓
- False-green guard (rosbags not installed → tests must RUN) → Global Constraints + Task 1 Step 3/5 + Task 4 Step 2 grep. ✓

**No-touch check:** edits limited to new `export/rosbag.py`, `cli.py`, `pyproject.toml`, new tests, `tests/test_cli_shell.py`, docs. Other `export/*` modules, ingest, release, synth, schemas untouched.

**Placeholder scan:** none — every code/test step is concrete and uses the probed `rosbags` 0.11.x API.

**Type consistency:** `_write_session_bag(bag_dir, raw_dir) -> None` matches the `export_release_rosbag` caller (`out_dir / sanitize(session_id)`, `sd`); `RosbagExportError` raised in both functions and caught in the CLI; `export_release_rosbag(release_dir, out_dir, force) -> Path` matches the Task 3 CLI call; message classes imported statically from `rosbags.typesys.stores.ros2_humble` and used consistently in `_pose_stamped` and the events loop; `PoseStamped.__msgtype__` / `StringMsg.__msgtype__` strings match the `add_connection` + `serialize_cdr` calls.
