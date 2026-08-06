# IK Robot-Arm Replay — Design

**Date:** 2026-06-22
**Slice:** v0.2 — IK / robot-arm replay (beyond mocap spheres)
**Status:** approved, ready for implementation plan

## Goal

Add `htdp replay-ik`: drive a vendored robot arm's end-effector along the `right_wrist`
Cartesian trajectory of a packaged release using `mink` differential inverse kinematics,
and return the resulting joint-angle trajectory plus the worst-case end-effector tracking
error. Headless, deterministic, fully offline. This extends slice-1 replay (which drives
mocap spheres at recorded xyz) to actual arm kinematics: recorded wrist path → joint
trajectory.

## Non-Goals

- Orientation IK (position-only; the synth wrist quaternion is not used to pose the arm).
- A realistic / menagerie robot model (a minimal hand-authored arm proves the round trip;
  a real arm can swap in later — `frame_name="eef"` is the only coupling).
- Multiple arms / multi-tracker driving.
- A live viewer or GUI (headless only).
- Exporting the joint trajectory to a file (returned in memory; export is a later slice).
- Changing the existing `htdp replay` mocap-sphere path (`player.py` is untouched).

## Background (verified)

- Slice-1 replay lives in `src/htdp/replay/player.py`: `load_release_motion(release_dir)`
  returns `{tracker: [(t, x, y, z), …]}` for the four trackers from the **first** session
  of a release; `replay_release` drives mocap spheres headless. The `replay` extra is
  `mujoco>=3.1`, lazy-imported, gated test via `pytest.importorskip("mujoco")`.
- `mink` (1.2.0) + `daqp` (0.8.7) are NOT installed in the base env; both are needed for
  this slice and its tests.

## Verified IK recipe (prototyped live against mink 1.2.0 / daqp 0.8.7)

A minimal 5-DOF serial arm tracks a moving wrist-like path with **max error 0.017 m, mean
0.002 m**, and reruns are **bit-identical** (deterministic). The working recipe:

```python
import mujoco, numpy as np, mink
from mink.lie.se3 import SE3

model = mujoco.MjModel.from_xml_path(ARM_XML)
data = mujoco.MjData(model)
cfg = mink.Configuration(model)
cfg.update(data.qpos)                       # init (NOT manual copyto)
task = mink.FrameTask(
    frame_name="eef", frame_type="body",
    position_cost=1.0, orientation_cost=0.0, lm_damping=1.0,
)
limits = [mink.ConfigurationLimit(model)]
eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "eef")
dt = model.opt.timestep

for (x, y, z) in waypoints:                 # one waypoint per motion sample
    task.set_target(SE3.from_translation(np.array([x, y, z])))
    for _ in range(ik_iters):               # settle iterations per waypoint
        vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
        cfg.integrate_inplace(vel, dt)
    mujoco.mj_forward(model, cfg.data)
    qpos = cfg.data.qpos.copy()             # joint angles this step
    err = float(np.linalg.norm(cfg.data.xpos[eid] - np.array([x, y, z])))
```

Key gotchas confirmed: `cfg.update(qpos)` (not manual `np.copyto` + `mj_kinematics`) is
required for correct init; `lm_damping=1.0` stabilises; `solve_ik` signature is
`solve_ik(configuration, tasks, dt, solver, damping=1e-12, limits=…)`.

## Vendored arm model

`src/htdp/replay/assets/arm.xml` — a 5-DOF serial arm, primitive geoms, terminal body
named `eef`. Joint chain: base yaw (`j0`, z-axis) + four pitch/roll hinges; ~1.2 m reach,
covering the synth workspace (`right_wrist` ≈ (0.3, 0.02, 0.9)). Verified to solve to the
synth target with err ≈ 0. The exact XML is fixed in the implementation plan.

## Architecture

`src/htdp/replay/ik.py` (new):

- `IkUnavailable(RuntimeError)` — raised when `mink` (or `daqp`) is not importable; message
  `"install with: uv sync --extra replay"`. Mirrors `ReplayUnavailable`.
- `IkResult` — a small dataclass: `joint_trajectory: list[list[float]]` (one inner list of
  joint angles per step) and `max_error: float` (worst per-step EEF tracking error, metres).
- `replay_release_ik(release_dir: Path, max_steps: int = 50, ik_iters: int = 10) -> IkResult`
  — lazy-imports `mujoco` + `mink` (→ `IkUnavailable` on failure); reuses
  `load_release_motion` to get the `right_wrist` samples; loads `arm.xml`; runs the recipe
  above for `min(max_steps, len(samples))` samples; returns the trajectory + max error.

The arm XML path is resolved relative to the module (`Path(__file__).parent / "assets" /
"arm.xml"`).

## CLI

`src/htdp/cli.py`, new command after `replay`:

```
htdp replay-ik <release_dir> [--max-steps N]
```

Lazy-imports `replay_release_ik` / `IkUnavailable`; on `IkUnavailable` prints
`error: <msg>` to stderr and exits 1; on success prints
`stepped <n> steps, max tracking error <e> m`.

## Dependency

Extend the existing `replay` extra in `pyproject.toml`:

```toml
replay = ["mujoco>=3.1", "mink>=1.1", "daqp>=0.5"]
```

No new extra (IK is part of replay). `mink` pulls `qpsolvers`; `daqp` is the QP backend.

## Error Handling

- `mink`/`daqp`/`mujoco` not installed → `IkUnavailable`.
- Empty release / missing `right_wrist` motion → the existing `load_release_motion` failure
  surfaces (no new handling; same as slice-1 replay).
- Unreachable targets do not raise — `solve_ik` minimises residual; the returned
  `max_error` reports tracking quality (the test asserts it stays under tolerance for synth
  data).

## Testing

New `tests/test_ik_replay.py`, gated `pytest.importorskip("mink")` (and the test
constructs a synth release via `generate_session` + `package_release`, both already in the
base env):

- **Tracking:** `replay_release_ik(release, max_steps=30)` → `joint_trajectory` has 30 rows,
  each of length 5 (arm DOF); `max_error < 0.05` (well above the observed 0.017 but a safe
  gate against drift).
- **Determinism:** two calls on the same release produce equal `joint_trajectory`
  (`pytest.approx` / exact equality on the nested lists).
- **CLI:** `replay-ik` happy path exit 0, output contains `max tracking error`.
- **Unavailable path:** not directly unit-testable while `mink` is installed; covered by
  the lazy-import structure mirroring the proven `ReplayUnavailable` path. (No fake-uninstall
  test — out of scope.)

**Critical (false-green guard):** `mink` + `daqp` are not installed in the base env. The
executor MUST `uv sync --extra replay --extra dev` and confirm the new tests **RUN, not
SKIP** before claiming green. (A prior slice shipped defects behind skipped optional-dep
tests.)

## Files Touched

- New: `src/htdp/replay/ik.py`
- New: `src/htdp/replay/assets/arm.xml`
- New: `tests/test_ik_replay.py`
- Modify: `src/htdp/cli.py` (add `replay-ik` command)
- Modify: `pyproject.toml` (extend `replay` extra; ensure the `assets/*.xml` ships in the
  wheel — add a hatch force-include if the build excludes non-`.py` files)
- Modify: docs — `docs/DATA_CONTRACT.md` (or `ARCHITECTURE.md`), `AGENTS.md`, `docs/ROADMAP.md`

No change to `player.py`, other modules, or any schema. No persisted-schema change → no
JSON-Schema re-export.

## mypy

`mink` is likely untyped. If `mypy src/htdp/replay` (if in the gate) or a future gate
target flags `import-untyped` / `import-not-found` for `mink.*` / `daqp`, add a narrow
`[[tool.mypy.overrides]]` `ignore_missing_imports` for those modules — decided against real
mypy output in the plan. Note: `src/htdp/replay` is currently NOT in the mypy gate command;
the plan keeps it that way unless adding it is trivially clean.

## Determinism

Verified bit-identical reruns of the joint trajectory. Tests assert both a numeric
tracking-error tolerance and rerun equality.

## Self-Review

- **Placeholders:** none — the IK recipe, arm structure, return type, CLI, and dependency
  floors are concrete and prototyped.
- **Consistency:** `IkUnavailable` mirrors `ReplayUnavailable`; `replay_release_ik` reuses
  `load_release_motion`; arm DOF (5) matches the `joint_trajectory` row length asserted in
  tests; `eef` body name matches `FrameTask(frame_name="eef")`.
- **Scope:** single implementation plan — one module, one asset, one CLI command, one test
  file, dep + docs. Position-only, single arm, headless.
- **Ambiguity:** `ik_iters` (settle iterations per waypoint, default 10) and `max_steps`
  (sample cap, default 50, mirroring slice-1) are explicit; tracking metric is the
  worst-case per-step EEF position error in metres.
