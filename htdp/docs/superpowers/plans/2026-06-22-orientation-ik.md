# Orientation IK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, best-effort orientation objective to `htdp replay-ik` (`--orientation-cost`, default 0.0), record per-step orientation error, and surface it in the summary and the trajectory CSV.

**Architecture:** A new `load_release_pose` reads the wrist quaternion the position-only loader drops; `replay_release_ik` gains an `orientation_cost` param that weights a `FrameTask` and always records the per-step target quaternion + geodesic orientation error; the pure CSV writer gains five orientation columns; the CLI exposes the flag. Default cost 0.0 keeps the slice-10/14 solve byte-identical.

**Tech Stack:** Python, polars (CSV read), stdlib `csv` (writer), typer (CLI), pytest. IK uses the optional `replay` extra (mink/mujoco/daqp).

## Global Constraints

- No new dependency, no new source module, no schema change → no JSON-Schema re-export.
- `src/htdp/replay/` and `src/htdp/cli.py` stay OUT of the mypy gate (unchanged policy).
- `--orientation-cost 0.0` (default) MUST leave the slice-10 solve byte-identical (use `SE3.from_translation`, not the rotation target, at cost 0) — proven by a trajectory-equality test.
- Orientation (target quat + error) is recorded for EVERY run regardless of cost → the CSV schema is stable. The writer indexes `target_orientations[i]`/`orientation_errors[i]` for each joint row, so `replay_release_ik` must keep all per-step lists equal length.
- The writer imports NO optional dep — its tests in `tests/test_ik_export.py` must stay ungated and RUN.
- `tests/test_ik_replay.py` has a module-level `pytest.importorskip("mink")` (line 10); tests appended there inherit that gate.
- **Verified-live mink API (do not deviate):** `from mink.lie.so3 import SO3`; `SO3(wxyz=np.array([w,x,y,z]))`; `SE3.from_rotation_and_translation(SO3(wxyz=q), np.array([x,y,z]))`; `FrameTask(..., orientation_cost=c)`; current eef orientation `cfg.data.xquat[eid]` (wxyz); geodesic error `float(np.linalg.norm((SO3(wxyz=target).inverse() @ SO3(wxyz=current)).log()))`.
- Synth writes constant identity quaternion (`qw=1, qx=qy=qz=0`); tests assert orientation error is finite/bounded and deterministic, NOT tight (the arm is 5-DOF).

---

### Task 1: `load_release_pose` (quaternion-bearing loader)

**Files:**
- Modify: `src/htdp/replay/player.py` (add `load_release_pose`)
- Create: `tests/test_load_pose.py` (NOT gated — polars is base)

**Interfaces:**
- Consumes: existing `_TRACKERS`, the motion CSVs (already have `qw,qx,qy,qz` columns).
- Produces: `load_release_pose(release_dir: Path) -> dict[str, list[tuple[float, float, float, float, float, float, float, float]]]` — per tracker, 8-tuples `(timestamp_s, x_m, y_m, z_m, qw, qx, qy, qz)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_load_pose.py`:

```python
from pathlib import Path

from htdp.release.package import package_release
from htdp.replay.player import load_release_pose
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return package_release(
        ["synth-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def test_load_release_pose_has_quaternion(tmp_path: Path):
    pose = load_release_pose(_release(tmp_path))
    assert "right_wrist" in pose
    row = pose["right_wrist"][0]
    assert len(row) == 8
    _, x, y, z, qw, qx, qy, qz = row
    assert (qw, qx, qy, qz) == (1.0, 0.0, 0.0, 0.0)  # synth identity quat
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_load_pose.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_release_pose'`.

- [ ] **Step 3: Add the loader**

In `src/htdp/replay/player.py`, add after `load_release_motion` (keep `load_release_motion` unchanged):

```python
def load_release_pose(
    release_dir: Path,
) -> dict[str, list[tuple[float, float, float, float, float, float, float, float]]]:
    out: dict[str, list[tuple[float, float, float, float, float, float, float, float]]] = {}
    sessions = sorted((release_dir / "data").iterdir())
    sid = sessions[0].name
    for tracker in _TRACKERS:
        df = pl.read_csv(release_dir / "data" / sid / "streams" / f"motion_{tracker}.csv")
        out[tracker] = [
            (r["timestamp_s"], r["x_m"], r["y_m"], r["z_m"], r["qw"], r["qx"], r["qy"], r["qz"])
            for r in df.iter_rows(named=True)
        ]
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_load_pose.py -v`
Expected: PASS (RUN, not skipped — no optional dep).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff format src/htdp/replay/player.py tests/test_load_pose.py
uv run ruff check src/htdp/replay/player.py tests/test_load_pose.py
git add src/htdp/replay/player.py tests/test_load_pose.py
git commit -m "feat(replay): load_release_pose reads wrist quaternion"
```

---

### Task 2: Orientation recording in `replay_release_ik` + IkResult fields + CSV columns

**Files:**
- Modify: `src/htdp/replay/ik.py` (`IkResult` fields, `replay_release_ik` orientation path, `write_ik_trajectory` columns)
- Modify: `tests/test_ik_export.py` (update `_sample` + expected header/rows — NOT gated)
- Modify: `tests/test_ik_replay.py` (append gated orientation tests)

**Interfaces:**
- Consumes: `load_release_pose` (Task 1); the verified mink `SO3`/`SE3`/`FrameTask` API.
- Produces:
  - `IkResult` gains `target_orientations: list[tuple[float,float,float,float]]`, `orientation_errors: list[float]`, `max_orientation_error: float`.
  - `replay_release_ik(release_dir, max_steps=50, ik_iters=10, orientation_cost=0.0) -> IkResult`.
  - `write_ik_trajectory` CSV header: `timestamp_s, q0..q{J-1}, target_x, target_y, target_z, tracking_error_m, target_qw, target_qx, target_qy, target_qz, orientation_error_rad`.

- [ ] **Step 1: Update the ungated writer tests (expect the new columns)**

In `tests/test_ik_export.py`, replace `_sample` and the affected assertions:

```python
def _sample() -> IkResult:
    return IkResult(
        joint_trajectory=[[0.1, 0.2], [0.3, 0.4]],
        max_error=0.5,
        timestamps=[0.0, 0.1],
        targets=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        errors=[0.1, 0.5],
        target_orientations=[(1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)],
        orientation_errors=[0.0, 0.2],
        max_orientation_error=0.2,
    )
```

Replace the header/row assertions in `test_writes_header_and_rows`:

```python
    assert rows[0] == [
        "timestamp_s", "q0", "q1", "target_x", "target_y", "target_z", "tracking_error_m",
        "target_qw", "target_qx", "target_qy", "target_qz", "orientation_error_rad",
    ]
    assert len(rows) == 3
    assert rows[1] == [
        "0.0", "0.1", "0.2", "1.0", "2.0", "3.0", "0.1", "1.0", "0.0", "0.0", "0.0", "0.0",
    ]
```

Replace the empty-result assertion in `test_empty_result_header_only`:

```python
def test_empty_result_header_only(tmp_path: Path):
    out = write_ik_trajectory(
        IkResult([], 0.0, [], [], [], [], [], 0.0), tmp_path / "e.csv"
    )
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows == [[
        "timestamp_s", "target_x", "target_y", "target_z", "tracking_error_m",
        "target_qw", "target_qx", "target_qy", "target_qz", "orientation_error_rad",
    ]]
```

- [ ] **Step 2: Write the gated orientation tests**

Append to `tests/test_ik_replay.py`:

```python
def test_orientation_recorded_at_zero_cost(tmp_path: Path):
    rel = _release(tmp_path)
    res = replay_release_ik(rel, max_steps=10)
    assert len(res.target_orientations) == 10
    assert len(res.orientation_errors) == 10
    assert all(len(q) == 4 for q in res.target_orientations)
    res0 = replay_release_ik(rel, max_steps=10, orientation_cost=0.0)
    assert res.joint_trajectory == res0.joint_trajectory


def test_orientation_cost_runs_and_is_deterministic(tmp_path: Path):
    rel = _release(tmp_path)
    a = replay_release_ik(rel, max_steps=10, orientation_cost=1.0)
    b = replay_release_ik(rel, max_steps=10, orientation_cost=1.0)
    assert isinstance(a.max_orientation_error, float)
    assert a.max_orientation_error >= 0.0
    assert a.joint_trajectory == b.joint_trajectory
```

- [ ] **Step 3: Run both test groups to verify they fail**

Run: `uv run pytest tests/test_ik_export.py tests/test_ik_replay.py -k "orientation or header or empty" -v`
Expected: FAIL — `test_ik_export.py` `_sample`/`IkResult(...)` raise `TypeError` (missing args) once the new expectations reference fields not on the dataclass; the gated tests fail because `replay_release_ik` has no `orientation_cost` param / `IkResult` has no `target_orientations`.

- [ ] **Step 4: Enrich the dataclass**

In `src/htdp/replay/ik.py`, replace the `IkResult` dataclass:

```python
@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
    target_orientations: list[tuple[float, float, float, float]]
    orientation_errors: list[float]
    max_orientation_error: float
```

- [ ] **Step 5: Rewrite `replay_release_ik` with the orientation path**

In `src/htdp/replay/ik.py`, replace the entire `replay_release_ik` function body:

```python
def replay_release_ik(
    release_dir: Path, max_steps: int = 50, ik_iters: int = 10, orientation_cost: float = 0.0
) -> IkResult:
    try:
        import mink  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
        from mink.lie.se3 import SE3  # type: ignore[import-not-found]
        from mink.lie.so3 import SO3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    pose = load_release_pose(release_dir)["right_wrist"]
    model = mujoco.MjModel.from_xml_path(str(_ARM_XML))
    data = mujoco.MjData(model)
    cfg = mink.Configuration(model)
    cfg.update(data.qpos)
    task = mink.FrameTask(
        frame_name="eef",
        frame_type="body",
        position_cost=1.0,
        orientation_cost=orientation_cost,
        lm_damping=1.0,
    )
    limits = [mink.ConfigurationLimit(model)]
    eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "eef")
    dt = model.opt.timestep

    n = min(max_steps, len(pose))
    trajectory: list[list[float]] = []
    timestamps: list[float] = []
    targets: list[tuple[float, float, float]] = []
    errors: list[float] = []
    target_orientations: list[tuple[float, float, float, float]] = []
    orientation_errors: list[float] = []
    max_error = 0.0
    max_orientation_error = 0.0
    for i in range(n):
        t, x, y, z, qw, qx, qy, qz = pose[i]
        target_pos = np.array([x, y, z])
        target_quat = np.array([qw, qx, qy, qz])
        if orientation_cost > 0:
            task.set_target(SE3.from_rotation_and_translation(SO3(wxyz=target_quat), target_pos))
        else:
            task.set_target(SE3.from_translation(target_pos))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        trajectory.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.xpos[eid] - target_pos))
        ori_err = float(
            np.linalg.norm((SO3(wxyz=target_quat).inverse() @ SO3(wxyz=cfg.data.xquat[eid])).log())
        )
        timestamps.append(float(t))
        targets.append((float(x), float(y), float(z)))
        errors.append(err)
        target_orientations.append((float(qw), float(qx), float(qy), float(qz)))
        orientation_errors.append(ori_err)
        max_error = max(max_error, err)
        max_orientation_error = max(max_orientation_error, ori_err)
    return IkResult(
        joint_trajectory=trajectory,
        max_error=max_error,
        timestamps=timestamps,
        targets=targets,
        errors=errors,
        target_orientations=target_orientations,
        orientation_errors=orientation_errors,
        max_orientation_error=max_orientation_error,
    )
```

Also update the import at the top of `ik.py` — replace `from htdp.replay.player import load_release_motion` with:

```python
from htdp.replay.player import load_release_pose
```

- [ ] **Step 6: Extend the CSV writer**

In `src/htdp/replay/ik.py`, replace `write_ik_trajectory`:

```python
def write_ik_trajectory(result: IkResult, out_path: Path, *, force: bool = False) -> Path:
    """Write an IkResult to a CSV trajectory file. Pure stdlib — no IK deps."""
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    joint_count = len(result.joint_trajectory[0]) if result.joint_trajectory else 0
    header = (
        ["timestamp_s"]
        + [f"q{j}" for j in range(joint_count)]
        + ["target_x", "target_y", "target_z", "tracking_error_m"]
        + ["target_qw", "target_qx", "target_qy", "target_qz", "orientation_error_rad"]
    )
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(len(result.joint_trajectory)):
            tx, ty, tz = result.targets[i]
            qw, qx, qy, qz = result.target_orientations[i]
            writer.writerow(
                [
                    result.timestamps[i],
                    *result.joint_trajectory[i],
                    tx, ty, tz, result.errors[i],
                    qw, qx, qy, qz, result.orientation_errors[i],
                ]
            )
    return out_path
```

- [ ] **Step 7: Run the test groups to verify they pass**

Run: `uv run pytest tests/test_ik_export.py tests/test_ik_replay.py -v`
Expected: all PASS. `test_ik_export.py` RUNS (no skip); `test_ik_replay.py` RUNS with mink (0 skipped), including the two new orientation tests and the unchanged slice-10/14 tests.

- [ ] **Step 8: Lint + commit**

```bash
uv run ruff format src/htdp/replay/ik.py tests/test_ik_export.py tests/test_ik_replay.py
uv run ruff check src/htdp/replay/ik.py tests/test_ik_export.py tests/test_ik_replay.py
git add src/htdp/replay/ik.py tests/test_ik_export.py tests/test_ik_replay.py
git commit -m "feat(replay): record orientation target + error, opt-in orientation_cost"
```

---

### Task 3: CLI `--orientation-cost`

**Files:**
- Modify: `src/htdp/cli.py` (`replay_ik` command)
- Modify: `tests/test_ik_replay.py` (append gated CLI test)

**Interfaces:**
- Consumes: `replay_release_ik(..., orientation_cost=...)` and `IkResult.max_orientation_error` (Task 2).
- Produces: CLI `htdp replay-ik <release_dir> [--max-steps N] [--out PATH] [--force] [--orientation-cost FLOAT]`.

- [ ] **Step 1: Write the failing gated CLI test**

Append to `tests/test_ik_replay.py`:

```python
def test_cli_orientation_cost_out(tmp_path: Path):
    import csv

    from typer.testing import CliRunner

    from htdp.cli import app

    rel = _release(tmp_path)
    out = tmp_path / "traj.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["replay-ik", str(rel), "--max-steps", "10", "--orientation-cost", "1.0", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert "max orientation error" in result.output
    header = next(csv.reader(out.open(encoding="utf-8")))
    assert header[-5:] == [
        "target_qw", "target_qx", "target_qy", "target_qz", "orientation_error_rad"
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ik_replay.py::test_cli_orientation_cost_out -v`
Expected: FAIL — typer reports `No such option: --orientation-cost` (exit code 2).

- [ ] **Step 3: Extend the CLI command**

In `src/htdp/cli.py`, replace the `replay_ik` command:

```python
@app.command()
def replay_ik(
    release_dir: Path,
    max_steps: int = 50,
    out: Path | None = typer.Option(None, "--out"),
    force: bool = typer.Option(False, "--force"),
    orientation_cost: float = typer.Option(0.0, "--orientation-cost"),
) -> None:
    """Drive a robot arm along a release's wrist path via IK (headless)."""
    from htdp.replay.ik import IkUnavailable, replay_release_ik, write_ik_trajectory

    try:
        result = replay_release_ik(
            release_dir, max_steps=max_steps, orientation_cost=orientation_cost
        )
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"stepped {len(result.joint_trajectory)} steps, "
        f"max tracking error {result.max_error:.4f} m, "
        f"max orientation error {result.max_orientation_error:.4f} rad"
    )
    if out is not None:
        try:
            written = write_ik_trajectory(result, out, force=force)
        except FileExistsError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"wrote {written} ({len(result.joint_trajectory)} steps)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ik_replay.py::test_cli_orientation_cost_out -v`
Expected: PASS.

- [ ] **Step 5: Full gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pytest`
Expected: all pass. (No mypy line — `replay/` and `cli.py` are outside the mypy gate.) If `ruff format --check` fails, run `uv run ruff format <touched files>` and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/cli.py tests/test_ik_replay.py
git commit -m "feat(replay): add --orientation-cost to replay-ik CLI"
```

---

### Task 4: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (replay-ik section)
- Modify: `AGENTS.md` (command list)
- Modify: `docs/ROADMAP.md` (IK line)

**Interfaces:** none (docs only).

- [ ] **Step 1: Locate replay-ik references**

Run: `grep -rn "replay-ik" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: lines describing `replay-ik` and its `--out`/`--force` options.

- [ ] **Step 2: Document `--orientation-cost`**

In each file's `replay-ik` description, add `--orientation-cost FLOAT` (default 0.0 = position-only; >0 weights best-effort wrist-orientation tracking on the 5-DOF arm). Note the trajectory CSV now also carries `target_qw/qx/qy/qz, orientation_error_rad` and the summary prints max orientation error. In `docs/ROADMAP.md`, note orientation IK landed on the IK line. Keep wording consistent with the existing replay/IK descriptions.

- [ ] **Step 3: Verify the orientation columns are documented**

Run: `grep -rn "orientation_error_rad\|orientation-cost" docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md`
Expected: the flag and the new CSV column appear, matching the writer/CLI output.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md AGENTS.md docs/ROADMAP.md
git commit -m "docs(replay): document replay-ik orientation cost + CSV columns"
```

---

## Self-Review

**1. Spec coverage:**
- `load_release_pose` (quaternion loader, `load_release_motion` untouched) → Task 1. ✅
- `IkResult` orientation fields → Task 2 Step 4. ✅
- `orientation_cost` param + weighted FrameTask + `from_rotation_and_translation` when >0, `from_translation` at 0 → Task 2 Step 5. ✅
- Always-record orientation target + geodesic error (verified `SO3` log expr, `cfg.data.xquat[eid]`) → Task 2 Step 5. ✅
- Default-cost solve byte-identical to slice 10 → `test_orientation_recorded_at_zero_cost` trajectory-equality assert. ✅
- cost>0 runs + deterministic, no tight error assertion → `test_orientation_cost_runs_and_is_deterministic`. ✅
- CSV gains 5 orientation columns, stable schema, empty→header-only → Task 2 Step 6 + updated `test_ik_export.py`. ✅
- CLI `--orientation-cost` default 0.0 + summary line → Task 3. ✅
- Pure writer stays unguarded (tests RUN) → `tests/test_ik_export.py` has no importorskip. ✅
- Docs → Task 4. ✅
- No new dep/module/schema → no JSON-Schema task. ✅

**2. Placeholder scan:** No TBD/TODO; every code step shows full code; every command has expected output. ✅

**3. Type consistency:** `IkResult` field order/names (`target_orientations: list[tuple[float,float,float,float]]`, `orientation_errors: list[float]`, `max_orientation_error: float`) identical across dataclass, solve loop return, writer indexing, and the `_sample`/empty-result test constructors (positional `IkResult([], 0.0, [], [], [], [], [], 0.0)` matches the 8-field order). `replay_release_ik(..., orientation_cost=0.0)` signature identical in solve, CLI call, and tests. `load_release_pose` returns 8-tuples consumed positionally as `t, x, y, z, qw, qx, qy, qz`. ✅
