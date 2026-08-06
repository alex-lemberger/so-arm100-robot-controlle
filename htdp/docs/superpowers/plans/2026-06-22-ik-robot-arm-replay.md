# IK Robot-Arm Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `htdp replay-ik`: drive a vendored 5-DOF robot arm's end-effector along a release's `right_wrist` Cartesian path via `mink` differential IK, returning the joint-angle trajectory + worst-case tracking error. Headless, deterministic, offline.

**Architecture:** Extend `src/htdp/replay/` with a vendored arm MJCF (`assets/arm.xml`) and a new `ik.py` (`replay_release_ik`) that reuses slice-1's `load_release_motion`, wraps `mink.Configuration` + `FrameTask` + `solve_ik("daqp")`, and reports per-step EEF error. A new typer CLI command wraps it. The `replay` extra gains `mink` + `daqp`. `player.py` (mocap-sphere replay) is untouched.

**Tech Stack:** Python ≥3.11, typer, pytest. `mujoco` + `mink` + `daqp` (all under the `replay` extra). polars (already used by `load_release_motion`).

## Global Constraints

Copied verbatim from `AGENTS.md` + the spec:

- Python `>=3.11`. ruff: `line-length = 100`, `line-ending = lf`. Clean `format --check` + `check`.
- `src/htdp/replay` is **not** in the mypy gate command; keep it that way (do not add it).
- Edits limited to new `src/htdp/replay/ik.py`, new `src/htdp/replay/assets/arm.xml`, `src/htdp/cli.py`, `pyproject.toml`, new test `tests/test_ik_replay.py`, and docs. Do NOT touch `src/htdp/replay/player.py`, other modules, or any schema.
- **No persisted-schema change** → no JSON-Schema re-export.
- Position-only IK; single arm; `right_wrist`-driven; headless. No viewer, no orientation, no file export.
- Deterministic: same release → identical joint trajectory (verified bit-identical).
- **CRITICAL false-green guard:** `mink` + `daqp` are NOT installed in the base env. Before claiming any green, run `uv sync --extra replay --extra dev` and confirm the new tests **RUN, not SKIP**. A prior slice shipped 3 defects hidden behind skipped optional-dep tests.

**Verified facts (prototyped live against mink 1.2.0 / daqp 0.8.7):**
- Recipe: `cfg = mink.Configuration(model); cfg.update(data.qpos)` (NOT manual `np.copyto`); `FrameTask("eef","body",position_cost=1.0,orientation_cost=0.0,lm_damping=1.0)`; `limits=[mink.ConfigurationLimit(model)]`; per sample: `task.set_target(SE3.from_translation(np.array([x,y,z])))` then `ik_iters`× `solve_ik(cfg,[task],dt,"daqp",limits=limits)` + `cfg.integrate_inplace(vel,dt)`; `dt = model.opt.timestep`.
- `solve_ik` signature: `solve_ik(configuration, tasks, dt, solver, damping=1e-12, safety_break=False, limits=None, constraints=None)`.
- `FrameTask.__init__(frame_name, frame_type, position_cost, orientation_cost, gain=1.0, lm_damping=0.0)`.
- With `ik_iters=10` over the real synth `right_wrist` trajectory (400 samples): first-step error and max error over 30 steps are both **0.0000 m**. The arm has `nq == 5`.
- Synth `right_wrist` first sample ≈ (0.31, 0.02, 0.905); 400 samples available.
- `load_release_motion(release_dir)` returns `{tracker: [(t, x, y, z), …]}` and reads the **first** session of the release.

---

### Task 1: vendored arm + `ik.py` — `replay_release_ik`

**Files:**
- Create: `src/htdp/replay/assets/arm.xml`
- Create: `src/htdp/replay/ik.py`
- Modify: `pyproject.toml` (extend `replay` extra; ship the XML in the wheel)
- Test: `tests/test_ik_replay.py`

**Interfaces:**
- Consumes: `load_release_motion` (from `htdp.replay.player`).
- Produces:
  - `IkUnavailable(RuntimeError)`
  - `IkResult` dataclass: `joint_trajectory: list[list[float]]`, `max_error: float`
  - `replay_release_ik(release_dir: Path, max_steps: int = 50, ik_iters: int = 10) -> IkResult`

- [ ] **Step 1: Vendor the arm model**

Create `src/htdp/replay/assets/arm.xml` with exactly this content (a 5-DOF serial arm, terminal body `eef`; verified to solve the synth workspace to ~0 error):

```xml
<mujoco model="htdp_arm">
  <option timestep="0.01"/>
  <worldbody>
    <body name="link0">
      <joint name="j0" type="hinge" axis="0 0 1"/>
      <geom type="capsule" fromto="0 0 0 0 0 0.2" size="0.04"/>
      <body name="link1" pos="0 0 0.2">
        <joint name="j1" type="hinge" axis="0 1 0"/>
        <geom type="capsule" fromto="0 0 0 0 0 0.3" size="0.035"/>
        <body name="link2" pos="0 0 0.3">
          <joint name="j2" type="hinge" axis="0 1 0"/>
          <geom type="capsule" fromto="0 0 0 0 0 0.3" size="0.03"/>
          <body name="link3" pos="0 0 0.3">
            <joint name="j3" type="hinge" axis="0 1 0"/>
            <geom type="capsule" fromto="0 0 0 0 0 0.2" size="0.025"/>
            <body name="eef" pos="0 0 0.2">
              <joint name="j4" type="hinge" axis="0 1 0"/>
              <geom type="sphere" size="0.03"/>
            </body>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
</mujoco>
```

- [ ] **Step 2: Add the dependencies + ship the asset**

In `pyproject.toml`, extend the `replay` extra and add the XML to the wheel artifacts:

```toml
[project.optional-dependencies]
replay = ["mujoco>=3.1", "mink>=1.1", "daqp>=0.5"]
```
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/htdp"]
artifacts = ["src/htdp/qc/templates/*.j2", "src/htdp/replay/assets/*.xml"]
```

Then sync so the libs are importable:
```bash
uv sync --extra replay --extra dev
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_ik_replay.py
from pathlib import Path

import pytest

from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session

pytest.importorskip("mink")

from htdp.replay.ik import replay_release_ik  # noqa: E402


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw", tmp_path / "releases",
    )


def test_tracks_wrist_within_tolerance(tmp_path: Path):
    res = replay_release_ik(_release(tmp_path), max_steps=30)
    assert len(res.joint_trajectory) == 30
    assert all(len(row) == 5 for row in res.joint_trajectory)
    assert res.max_error < 0.05


def test_deterministic(tmp_path: Path):
    rel = _release(tmp_path)
    a = replay_release_ik(rel, max_steps=20)
    b = replay_release_ik(rel, max_steps=20)
    assert a.joint_trajectory == b.joint_trajectory
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run --extra replay --extra dev pytest tests/test_ik_replay.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.replay.ik'` (NOT skipped — `mink` is installed).

- [ ] **Step 5: Write minimal implementation**

Create `src/htdp/replay/ik.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from htdp.replay.player import load_release_motion

_ARM_XML = Path(__file__).parent / "assets" / "arm.xml"


class IkUnavailable(RuntimeError):
    """Raised when mink/daqp/mujoco are not installed."""


@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float


def replay_release_ik(
    release_dir: Path, max_steps: int = 50, ik_iters: int = 10
) -> IkResult:
    try:
        import mink  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
        from mink.lie.se3 import SE3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    wrist = load_release_motion(release_dir)["right_wrist"]
    model = mujoco.MjModel.from_xml_path(str(_ARM_XML))
    data = mujoco.MjData(model)
    cfg = mink.Configuration(model)
    cfg.update(data.qpos)
    task = mink.FrameTask(
        frame_name="eef",
        frame_type="body",
        position_cost=1.0,
        orientation_cost=0.0,
        lm_damping=1.0,
    )
    limits = [mink.ConfigurationLimit(model)]
    eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "eef")
    dt = model.opt.timestep

    n = min(max_steps, len(wrist))
    trajectory: list[list[float]] = []
    max_error = 0.0
    for i in range(n):
        _, x, y, z = wrist[i]
        target = np.array([x, y, z])
        task.set_target(SE3.from_translation(target))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        trajectory.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.xpos[eid] - target))
        max_error = max(max_error, err)
    return IkResult(joint_trajectory=trajectory, max_error=max_error)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --extra replay --extra dev pytest tests/test_ik_replay.py -v`
Expected: PASS (2 passed, 0 skipped). If any test SKIPs, STOP — the `replay` extra is not synced.

- [ ] **Step 7: Lint**

Run:
```bash
uv run ruff format src/htdp/replay/ik.py tests/test_ik_replay.py
uv run ruff check src/htdp/replay/ik.py tests/test_ik_replay.py
```
Expected: ruff clean. (mypy is not run on `src/htdp/replay` — it is not in the gate.)

- [ ] **Step 8: Commit**

```bash
git add src/htdp/replay/assets/arm.xml src/htdp/replay/ik.py pyproject.toml tests/test_ik_replay.py
git commit -m "feat(replay): IK arm trajectory from release wrist path (replay_release_ik)"
```

---

### Task 2: CLI `replay-ik`

**Files:**
- Modify: `src/htdp/cli.py` (add command after `replay`)
- Test: `tests/test_ik_replay.py` (append)

**Interfaces:**
- Consumes: `replay_release_ik`, `IkUnavailable`, `IkResult`.
- Produces: `htdp replay-ik <release_dir> [--max-steps N]`; exit 1 on `IkUnavailable`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ik_replay.py`:

```python
def test_cli_replay_ik(tmp_path: Path):
    from typer.testing import CliRunner

    from htdp.cli import app

    rel = _release(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["replay-ik", str(rel), "--max-steps", "10"])
    assert result.exit_code == 0, result.output
    assert "max tracking error" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra replay --extra dev pytest tests/test_ik_replay.py -k cli_replay_ik -v`
Expected: FAIL — no command `replay-ik` (usage error / exit 2).

- [ ] **Step 3: Write minimal implementation**

Add to `src/htdp/cli.py` after the `replay` command:

```python
@app.command()
def replay_ik(release_dir: Path, max_steps: int = 50) -> None:
    """Drive a robot arm along a release's wrist path via IK (headless)."""
    from htdp.replay.ik import IkUnavailable, replay_release_ik

    try:
        result = replay_release_ik(release_dir, max_steps=max_steps)
    except IkUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"stepped {len(result.joint_trajectory)} steps, "
        f"max tracking error {result.max_error:.4f} m"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra replay --extra dev pytest tests/test_ik_replay.py -k cli_replay_ik -v`
Expected: PASS (1 passed, 0 skipped).

- [ ] **Step 5: Commit**

```bash
git add src/htdp/cli.py tests/test_ik_replay.py
git commit -m "feat(replay): add htdp replay-ik CLI command"
```

---

### Task 3: Docs + full gate

**Files:**
- Modify: `docs/ARCHITECTURE.md` (or `docs/DATA_CONTRACT.md`), `AGENTS.md`, `docs/ROADMAP.md`

**Interfaces:** none.

- [ ] **Step 1: Update docs**

`docs/ARCHITECTURE.md` — add an "IK robot-arm replay" note: `htdp replay-ik` drives a
vendored 5-DOF arm (`src/htdp/replay/assets/arm.xml`) so its end-effector follows the
`right_wrist` Cartesian path of a release via `mink` differential IK; returns the joint
trajectory + max tracking error; headless, deterministic; position-only. (If
`docs/ARCHITECTURE.md` does not exist, put this note in `docs/DATA_CONTRACT.md` instead.)

`AGENTS.md` — add usage `htdp replay-ik <release_dir> [--max-steps N]`; note it needs the
`replay` extra (`uv sync --extra replay`) which now includes `mink` + `daqp`.

`docs/ROADMAP.md` — mark "IK / robot-arm replay (beyond mocap spheres)" as done.

- [ ] **Step 2: Run the full gate**

Run:
```bash
uv sync --extra replay --extra ingest --extra rosbag --extra dev
uv run ruff format --check . && uv run ruff check .
uv run pytest
uv run mypy src/htdp/schemas src/htdp/consent src/htdp/release src/htdp/io src/htdp/ingest src/htdp/export
```
Expected: ruff clean; pytest all pass — the new IK tests RUN (not skip) because `mink` is synced; the previously-skipped mujoco-replay test now RUNS too (mujoco is in the `replay` extra); mypy `Success`.

**Verification gate (false-green guard):** confirm the IK tests show as PASSED, not
SKIPPED: `uv run pytest -rs | grep -iE "ik_replay|mink"` must show no `SKIPPED` next to an
IK test.

- [ ] **Step 3: Commit**

```bash
git add docs/ AGENTS.md
git commit -m "docs(replay): document IK robot-arm replay"
```

---

## Self-Review

**Spec coverage** (`2026-06-22-ik-robot-arm-replay-design.md`):
- Vendored 5-DOF arm `assets/arm.xml`, terminal `eef` body → Task 1 Step 1. ✓
- `replay_release_ik(release_dir, max_steps, ik_iters)` reusing `load_release_motion`,
  returning `IkResult(joint_trajectory, max_error)` → Task 1 Step 5. ✓
- Verified IK recipe (`cfg.update`, FrameTask pos-only `lm_damping=1.0`, ConfigurationLimit,
  `solve_ik("daqp")`, integrate) → Task 1 Step 5. ✓
- `IkUnavailable` mirroring `ReplayUnavailable` → Task 1 Step 5. ✓
- Tracking (`max_error < 0.05`) + DOF (5) + determinism tests → Task 1 Step 3. ✓
- CLI `replay-ik` (exit 1 on `IkUnavailable`) → Task 2. ✓
- Dependency: extend `replay` extra with `mink>=1.1`, `daqp>=0.5`; ship XML in wheel → Task 1 Step 2. ✓
- Docs (ARCHITECTURE/DATA_CONTRACT, AGENTS, ROADMAP), no schema re-export → Task 3. ✓
- Non-goals (orientation, multi-arm, menagerie model, viewer, file export) — none implemented. ✓
- False-green guard (mink not installed → tests must RUN) → Global Constraints + Task 1 Steps 4/6 + Task 3 Step 2 grep. ✓

**No-touch check:** edits limited to new `replay/ik.py`, `replay/assets/arm.xml`, `cli.py`,
`pyproject.toml`, new `tests/test_ik_replay.py`, docs. `player.py`, other modules, and
schemas untouched.

**Placeholder scan:** none — the arm XML, IK recipe, return type, CLI, dep floors, and the
`ik_iters=10` choice (verified max_error 0.0) are all concrete.

**Type consistency:** `IkResult.joint_trajectory: list[list[float]]` row length (5) matches
the arm `nq` asserted in the test; `replay_release_ik(release_dir, max_steps, ik_iters)`
signature matches the Task 2 CLI call (`max_steps=max_steps`); `IkUnavailable` raised in
`ik.py` and caught in the CLI; `frame_name="eef"` matches the `eef` body in `arm.xml` and
the `mj_name2id(..., "eef")` lookup.
