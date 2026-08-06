# M1 — Sim Loop (SO-ARM100 Pick-and-Place) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A recorded wrist trajectory drives a simulated SO-ARM100 in MuJoCo to pick an object and place it on a target, end-to-end, deterministic, with a rendered demo video.

**Architecture:** Extend the existing `htdp.replay` package. Reuse the proven `mink`+`daqp` differential-IK loop (`src/htdp/replay/ik.py`) but retarget it onto a vendored SO-ARM100 MJCF instead of the hand-authored `arm.xml`. Add a task scene (table + free-jointed object + target site), a scripted grasp implemented as a toggled MuJoCo `weld` equality constraint (robust vs friction grasping for a portfolio demo), an offscreen MP4 render, and a `htdp sim-task` CLI command. Input motion for M1 is the existing synthetic release (`htdp.synth`); real/public data is a later milestone.

**Tech Stack:** Python 3.11, MuJoCo ≥3.1, mink ≥1.1, daqp ≥0.5 (the existing `replay` extra), numpy, polars, typer. Video via `mujoco.Renderer` (offscreen) + `imageio[ffmpeg]`.

## Global Constraints

- Python `>=3.11`; `mypy --strict` must pass; `ruff` line-length 100, LF endings.
- IK/render/video code lives behind the `replay` optional extra and is **lazy-imported** inside functions; importing `htdp.replay.*` at module load must NOT require mujoco/mink. Raise `IkUnavailable`/`ReplayUnavailable` with `"install with: uv sync --extra replay"` when missing.
- New heavy test deps gated with `pytest.importorskip("mujoco")` (and `mink`, `imageio`) so the base test suite stays green without the extra.
- Determinism is a hard requirement: identical inputs → bit-identical joint trajectory and object final pose across reruns. No wall-clock, no unseeded RNG.
- Vendored model assets ship in the wheel: extend `[tool.hatch.build.targets.wheel].artifacts` to include the new asset glob.
- Existing `htdp replay`, `htdp replay-ik`, and `arm.xml` paths stay working and untouched.

---

### Task 1: Vendor the SO-ARM100 model + verified name map

**Files:**
- Create: `src/htdp/replay/assets/so_arm100/` (vendored MJCF + meshes from MuJoCo Menagerie `trs_so_arm100`)
- Create: `src/htdp/replay/so_arm100.py` (model path + introspected name constants + loader)
- Create: `tests/replay/test_so_arm100_model.py`
- Modify: `pyproject.toml` (wheel artifacts glob)

**Interfaces:**
- Produces:
  - `SO_ARM100_XML: Path` — absolute path to the vendored scene/arm MJCF.
  - `EEF_BODY: str` — name of the end-effector/gripper body the IK FrameTask tracks.
  - `ARM_JOINTS: tuple[str, ...]` — the 5 actuated arm joint names (excludes the gripper joint).
  - `GRIPPER_JOINT: str` — the gripper actuator joint name.
  - `load_model()` — returns a `mujoco.MjModel` from `SO_ARM100_XML` (lazy mujoco import).

- [ ] **Step 1: Vendor the model assets**

Download the SO-ARM100 MJCF + mesh files from MuJoCo Menagerie (`mujoco_menagerie/trs_so_arm100/`) and copy the `.xml` + `assets/*` into `src/htdp/replay/assets/so_arm100/`. Keep the upstream `LICENSE`/attribution file alongside them.

Run: `git -C /tmp clone --depth 1 https://github.com/google-deepmind/mujoco_menagerie` then copy `mujoco_menagerie/trs_so_arm100/*` into `src/htdp/replay/assets/so_arm100/`.
Expected: directory contains an `.xml` and an `assets/` (or `meshes/`) folder.

- [ ] **Step 2: Introspect names (runnable discovery, not a guess)**

The exact body/joint names come from the vendored file. Run this to print them:

```python
import mujoco
m = mujoco.MjModel.from_xml_path("src/htdp/replay/assets/so_arm100/scene.xml")  # or so_arm100.xml
print("BODIES:", [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(m.nbody)])
print("JOINTS:", [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, i) for i in range(m.njnt)])
```

Run: `uv run python -c "<above>"`
Expected: prints the body list (the gripper/jaw tip body) and the 6 joint names (5 arm + 1 gripper).

- [ ] **Step 3: Write `so_arm100.py` with the discovered names**

```python
from __future__ import annotations
from pathlib import Path

SO_ARM100_XML = Path(__file__).parent / "assets" / "so_arm100" / "scene.xml"  # match vendored filename

# Filled from the Step-2 introspection output:
EEF_BODY = "gripper"                # the tip/jaw body the IK target tracks
ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
GRIPPER_JOINT = "gripper"           # the jaw actuator joint

def load_model():  # type: ignore[no-untyped-def]
    import mujoco  # lazy
    return mujoco.MjModel.from_xml_path(str(SO_ARM100_XML))
```

(Replace the string literals with the actual Step-2 names before running the test.)

- [ ] **Step 4: Write the failing test**

```python
import pytest

pytest.importorskip("mujoco")

from htdp.replay.so_arm100 import (
    SO_ARM100_XML, EEF_BODY, ARM_JOINTS, GRIPPER_JOINT, load_model,
)

def test_model_loads_and_names_exist():
    import mujoco
    assert SO_ARM100_XML.exists()
    m = load_model()
    def has(objtype, name):
        return mujoco.mj_name2id(m, objtype, name) != -1
    assert has(mujoco.mjtObj.mjOBJ_BODY, EEF_BODY)
    for j in ARM_JOINTS:
        assert has(mujoco.mjtObj.mjOBJ_JOINT, j), j
    assert has(mujoco.mjtObj.mjOBJ_JOINT, GRIPPER_JOINT)
    assert len(ARM_JOINTS) == 5
```

- [ ] **Step 5: Run test to verify it fails, then passes after names are correct**

Run: `uv run --extra replay pytest tests/replay/test_so_arm100_model.py -v`
Expected: FAIL until Step-3 names match the model, then PASS.

- [ ] **Step 6: Add wheel artifact glob**

In `pyproject.toml`, change the artifacts line to include the new assets:

```toml
artifacts = ["src/htdp/qc/templates/*.j2", "src/htdp/replay/assets/*.xml", "src/htdp/replay/assets/so_arm100/**/*"]
```

- [ ] **Step 7: Commit**

```bash
git add src/htdp/replay/assets/so_arm100 src/htdp/replay/so_arm100.py tests/replay/test_so_arm100_model.py pyproject.toml
git commit -m "feat(replay): vendor SO-ARM100 MuJoCo model + verified name map"
```

---

### Task 2: Retarget IK onto the SO-ARM100

**Files:**
- Create: `src/htdp/replay/arm_ik.py` (SO-ARM100 position-tracking IK, modeled on `ik.py`)
- Create: `tests/replay/test_arm_ik.py`

**Interfaces:**
- Consumes: `so_arm100.SO_ARM100_XML`, `EEF_BODY`; `player.load_release_pose`.
- Produces:
  - `@dataclass ArmIkResult` with fields: `joint_trajectory: list[list[float]]`, `timestamps: list[float]`, `targets: list[tuple[float,float,float]]`, `errors: list[float]`, `max_error: float`.
  - `solve_arm_ik(pose: list[tuple[float,...]], *, ik_iters: int = 10) -> ArmIkResult` — runs differential IK so `EEF_BODY` tracks the xyz of each pose sample. Position-only (SO-ARM100 has 5 arm DOF; orientation is out of scope for M1).

- [ ] **Step 1: Write the failing test**

```python
import pytest
pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.replay.arm_ik import solve_arm_ik

def _line(n=20):
    # a short reachable Cartesian path in front of the SO-ARM100 base (metres)
    return [(0.04 * i, 0.0 + 0.18, 0.0, 0.10 + 0.005 * i, 1.0, 0.0, 0.0, 0.0) for i in range(n)]

def test_arm_ik_tracks_and_is_deterministic():
    a = solve_arm_ik(_line())
    b = solve_arm_ik(_line())
    assert a.max_error < 0.03                      # < 3 cm tip tracking error
    assert a.joint_trajectory == b.joint_trajectory  # bit-identical reruns
    assert len(a.joint_trajectory) == 20
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --extra replay pytest tests/replay/test_arm_ik.py -v`
Expected: FAIL with `ModuleNotFoundError: htdp.replay.arm_ik`.

- [ ] **Step 3: Implement `arm_ik.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from htdp.replay.ik import IkUnavailable
from htdp.replay.so_arm100 import EEF_BODY, SO_ARM100_XML


@dataclass
class ArmIkResult:
    joint_trajectory: list[list[float]]
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
    max_error: float


def solve_arm_ik(pose, *, ik_iters: int = 10) -> ArmIkResult:  # type: ignore[no-untyped-def]
    try:
        import mink  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
        from mink.lie.se3 import SE3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    model = mujoco.MjModel.from_xml_path(str(SO_ARM100_XML))
    data = mujoco.MjData(model)
    cfg = mink.Configuration(model)
    cfg.update(data.qpos)
    task = mink.FrameTask(
        frame_name=EEF_BODY, frame_type="body",
        position_cost=1.0, orientation_cost=0.0, lm_damping=1.0,
    )
    limits = [mink.ConfigurationLimit(model)]
    eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, EEF_BODY)
    dt = model.opt.timestep

    traj: list[list[float]] = []
    ts: list[float] = []
    targets: list[tuple[float, float, float]] = []
    errors: list[float] = []
    max_error = 0.0
    for sample in pose:
        t, x, y, z = sample[0], sample[1], sample[2], sample[3]
        target = np.array([x, y, z])
        task.set_target(SE3.from_translation(target))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        traj.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.xpos[eid] - target))
        ts.append(float(t)); targets.append((float(x), float(y), float(z))); errors.append(err)
        max_error = max(max_error, err)
    return ArmIkResult(traj, ts, targets, errors, max_error)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --extra replay pytest tests/replay/test_arm_ik.py -v`
Expected: PASS. If `max_error` is high, the test path is outside the SO-ARM100 workspace — shrink the `_line` reach toward the base, OR add a workspace-scale factor (note it for Task 5). If still failing, recheck `EEF_BODY` from Task 1 Step 2.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/replay/arm_ik.py tests/replay/test_arm_ik.py
git commit -m "feat(replay): position-tracking IK retargeted onto SO-ARM100"
```

---

### Task 3: Task scene — table, free-jointed object, target site

**Files:**
- Create: `src/htdp/replay/assets/so_arm100/task_scene.xml` (includes the vendored arm; adds table geom, a free-jointed cube, a target site, and a `weld` equality constraint disabled by default)
- Create: `src/htdp/replay/scene.py` (scene loader + body/site/equality id helpers)
- Create: `tests/replay/test_scene.py`

**Interfaces:**
- Consumes: vendored SO-ARM100 MJCF (via `<include>`).
- Produces:
  - `TASK_SCENE_XML: Path`
  - `OBJECT_BODY = "cube"`, `OBJECT_FREEJOINT = "cube_free"`, `TARGET_SITE = "target"`, `GRASP_WELD = "grasp"`
  - `load_scene()` -> `mujoco.MjModel`
  - `object_xy(data) -> tuple[float, float]` and `target_xy(model) -> tuple[float, float]` helpers.

- [ ] **Step 1: Author `task_scene.xml`**

```xml
<mujoco model="so_arm100_task">
  <include file="so_arm100.xml"/>            <!-- match the vendored arm filename -->
  <worldbody>
    <geom name="table" type="box" pos="0.15 0.18 -0.02" size="0.25 0.25 0.02" rgba="0.8 0.8 0.8 1"/>
    <body name="cube" pos="0.10 0.18 0.03">
      <freejoint name="cube_free"/>
      <geom name="cube_geom" type="box" size="0.015 0.015 0.015" rgba="0.9 0.3 0.2 1" mass="0.02"/>
    </body>
    <site name="target" pos="0.22 0.10 0.015" size="0.02" rgba="0.2 0.8 0.2 0.5"/>
  </worldbody>
  <equality>
    <weld name="grasp" body1="gripper" body2="cube" active="false"/>  <!-- body1 = EEF_BODY -->
  </equality>
</mujoco>
```

Adjust `body1` to the actual `EEF_BODY`, and `cube`/`target` positions so both sit within the SO-ARM100 workspace measured in Task 2.

- [ ] **Step 2: Write the failing test**

```python
import pytest
pytest.importorskip("mujoco")
from htdp.replay.scene import (
    load_scene, OBJECT_BODY, TARGET_SITE, GRASP_WELD, object_xy, target_xy,
)

def test_scene_has_object_target_and_weld():
    import mujoco
    m = load_scene()
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, OBJECT_BODY) != -1
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, TARGET_SITE) != -1
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_EQUALITY, GRASP_WELD) != -1
    d = mujoco.MjData(m); mujoco.mj_forward(m, d)
    assert len(object_xy(d)) == 2 and len(target_xy(m)) == 2
```

- [ ] **Step 3: Implement `scene.py`**

```python
from __future__ import annotations
from pathlib import Path

TASK_SCENE_XML = Path(__file__).parent / "assets" / "so_arm100" / "task_scene.xml"
OBJECT_BODY = "cube"
OBJECT_FREEJOINT = "cube_free"
TARGET_SITE = "target"
GRASP_WELD = "grasp"

def load_scene():  # type: ignore[no-untyped-def]
    import mujoco  # lazy
    return mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))

def object_xy(data):  # type: ignore[no-untyped-def]
    import mujoco  # noqa: F401
    return (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))

def target_xy(model):  # type: ignore[no-untyped-def]
    s = model.site(TARGET_SITE)
    return (float(s.pos[0]), float(s.pos[1]))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --extra replay pytest tests/replay/test_scene.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/replay/assets/so_arm100/task_scene.xml src/htdp/replay/scene.py tests/replay/test_scene.py
git commit -m "feat(replay): SO-ARM100 task scene with object, target, grasp weld"
```

---

### Task 4: Episode — scripted pick-and-place via toggled weld

**Files:**
- Create: `src/htdp/replay/episode.py` (drive the arm through approach→grasp→lift→move→place→release, stepping physics; toggle the `grasp` weld)
- Create: `tests/replay/test_episode.py`

**Interfaces:**
- Consumes: `scene.load_scene`, scene name constants; `arm_ik.solve_arm_ik`.
- Produces:
  - `@dataclass EpisodeResult` with: `object_start_xy`, `object_final_xy`, `target_xy`, `place_error: float`, `frames_stepped: int`, `qpos_trace: list[list[float]]`.
  - `run_episode(*, n_settle: int = 200, seed: int = 0) -> EpisodeResult` — builds a waypoint path (pickup above cube → descend → grasp → lift → traverse to target → descend → release), solves IK per waypoint with `solve_arm_ik`, applies joint targets to the arm qpos, toggles `model`/`data` weld `active` at grasp/release, and steps the sim. Deterministic (no RNG; `seed` reserved).

- [ ] **Step 1: Write the failing test**

```python
import pytest
pytest.importorskip("mujoco")
pytest.importorskip("mink")
from htdp.replay.episode import run_episode

def test_episode_places_object_near_target_deterministically():
    a = run_episode()
    b = run_episode()
    assert a.qpos_trace == b.qpos_trace                 # deterministic
    assert a.place_error < 0.05                          # object within 5 cm of target
    # object actually moved from its start toward the target:
    import math
    moved = math.dist(a.object_start_xy, a.object_final_xy)
    assert moved > 0.05
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --extra replay pytest tests/replay/test_episode.py -v`
Expected: FAIL with `ModuleNotFoundError: htdp.replay.episode`.

- [ ] **Step 3: Implement `episode.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from htdp.replay.arm_ik import solve_arm_ik
from htdp.replay.ik import IkUnavailable
from htdp.replay.scene import GRASP_WELD, OBJECT_BODY, TASK_SCENE_XML, TARGET_SITE


@dataclass
class EpisodeResult:
    object_start_xy: tuple[float, float]
    object_final_xy: tuple[float, float]
    target_xy: tuple[float, float]
    place_error: float
    frames_stepped: int
    qpos_trace: list[list[float]]


def _waypoints(model):  # type: ignore[no-untyped-def]
    # Cartesian path keyed off cube + target positions; (x,y,z,grasp_active)
    cube = model.body(OBJECT_BODY).pos
    tgt = model.site(TARGET_SITE).pos
    z_hi, z_lo = 0.12, 0.035
    return [
        (cube[0], cube[1], z_hi, False),  # approach above cube
        (cube[0], cube[1], z_lo, False),  # descend
        (cube[0], cube[1], z_lo, True),   # grasp (weld on)
        (cube[0], cube[1], z_hi, True),   # lift
        (tgt[0],  tgt[1],  z_hi, True),   # traverse
        (tgt[0],  tgt[1],  z_lo, True),   # descend to target
        (tgt[0],  tgt[1],  z_lo, False),  # release (weld off)
        (tgt[0],  tgt[1],  z_hi, False),  # retreat
    ]


def run_episode(*, n_settle: int = 200, seed: int = 0) -> EpisodeResult:
    try:
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    weld_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, GRASP_WELD)
    eq_active = model.eq_active0  # baseline; we flip data.eq_active per step

    nq_arm = solve_arm_ik([(0.0, *model.body(OBJECT_BODY).pos, 1, 0, 0, 0)]).joint_trajectory[0]
    n_arm = len(nq_arm)

    start_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    qtrace: list[list[float]] = []
    frames = 0
    for (x, y, z, grasp) in _waypoints(model):
        sol = solve_arm_ik([(0.0, x, y, z, 1.0, 0.0, 0.0, 0.0)]).joint_trajectory[0]
        data.eq_active[weld_id] = 1 if grasp else 0
        for _ in range(n_settle):
            data.qpos[:n_arm] = sol[:n_arm]          # drive arm joints to IK solution
            mujoco.mj_step(model, data)
            frames += 1
        qtrace.append([float(q) for q in data.qpos])

    final_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    tgt = (float(model.site(TARGET_SITE).pos[0]), float(model.site(TARGET_SITE).pos[1]))
    place_error = float(np.hypot(final_xy[0] - tgt[0], final_xy[1] - tgt[1]))
    return EpisodeResult(start_xy, final_xy, tgt, place_error, frames, qtrace)
```

- [ ] **Step 4: Run to verify it passes; tune if needed**

Run: `uv run --extra replay pytest tests/replay/test_episode.py -v`
Expected: PASS. Common tuning (engineering, not placeholder): if the cube doesn't follow the gripper, the weld activated before the gripper reached the cube — verify `z_lo` actually puts `EEF_BODY` at the cube; if the cube jitters loose, raise `n_settle`. If qpos slicing `[:n_arm]` overwrites the freejoint, confirm the arm joints are the first qpos entries (they are when the arm is `<include>`d before the cube body in the scene); otherwise index by joint addresses from `model.jnt_qposadr`.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/replay/episode.py tests/replay/test_episode.py
git commit -m "feat(replay): scripted SO-ARM100 pick-and-place episode (weld grasp)"
```

---

### Task 5: Render the episode to MP4

**Files:**
- Create: `src/htdp/replay/render.py` (offscreen frame capture → MP4)
- Modify: `src/htdp/replay/episode.py` (have `run_episode` optionally collect frames)
- Create: `tests/replay/test_render.py`
- Modify: `pyproject.toml` (add `imageio[ffmpeg]` to the `replay` extra)

**Interfaces:**
- Consumes: `EpisodeResult`/`run_episode`.
- Produces: `render_episode(out_path: Path, *, fps: int = 30, every: int = 10, force: bool = False) -> Path` — runs an episode capturing one frame every `every` sim steps via `mujoco.Renderer`, writes an MP4 with `imageio`, returns the path. Refuses to overwrite unless `force`.

- [ ] **Step 1: Add the dep**

In `pyproject.toml`: `replay = ["mujoco>=3.1", "mink>=1.1", "daqp>=0.5", "imageio[ffmpeg]>=2.34"]`. Run `uv sync --extra replay`.

- [ ] **Step 2: Write the failing test**

```python
import pytest
pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("imageio")
from htdp.replay.render import render_episode

def test_render_writes_nonempty_mp4(tmp_path):
    out = render_episode(tmp_path / "demo.mp4", every=40)
    assert out.exists() and out.stat().st_size > 10_000
    with pytest.raises(FileExistsError):
        render_episode(out, every=40)
```

- [ ] **Step 3: Add frame capture to `run_episode`**

Add a `capture: bool = False` param and an optional `frames: list` on `EpisodeResult`. When `capture`, inside the settle loop every `render_every` steps call a passed-in `renderer.update_scene(data); frames.append(renderer.render())`. Keep the default path (no capture) byte-identical to Task 4 so its determinism test still holds. (Concretely: thread an optional `on_step` callback through `run_episode`; `render.py` supplies it.)

- [ ] **Step 4: Implement `render.py`**

```python
from __future__ import annotations
from pathlib import Path

from htdp.replay.ik import IkUnavailable
from htdp.replay.scene import TASK_SCENE_XML


def render_episode(out_path: Path, *, fps: int = 30, every: int = 10, force: bool = False) -> Path:
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    try:
        import imageio.v3 as iio  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    from htdp.replay.episode import run_episode  # lazy, avoids cycle

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    renderer = mujoco.Renderer(model, height=480, width=640)
    frames: list = []

    def on_step(data, step_index):  # called by run_episode each sim step
        if step_index % every == 0:
            renderer.update_scene(data)
            frames.append(renderer.render())

    run_episode(on_step=on_step)
    renderer.close()
    iio.imwrite(out_path, frames, fps=fps, codec="libx264")
    return out_path
```

- [ ] **Step 5: Run to verify render + determinism both pass**

Run: `uv run --extra replay pytest tests/replay/test_render.py tests/replay/test_episode.py -v`
Expected: PASS (render writes MP4; the no-capture episode determinism test is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/htdp/replay/render.py src/htdp/replay/episode.py tests/replay/test_render.py pyproject.toml
git commit -m "feat(replay): render SO-ARM100 pick-and-place episode to MP4"
```

---

### Task 6: `htdp sim-task` CLI + docs

**Files:**
- Modify: `src/htdp/cli.py` (add `sim-task` command)
- Create: `tests/test_cli_sim_task.py`
- Modify: `docs/ROADMAP.md`, `README.md` (M1 milestone + how to run)

**Interfaces:**
- Consumes: `episode.run_episode`, `render.render_episode`.
- Produces: CLI command `htdp sim-task [--video PATH] [--force]` printing place-error + frames, optionally writing the MP4.

- [ ] **Step 1: Write the failing CLI test**

```python
from typer.testing import CliRunner
from htdp.cli import app

runner = CliRunner()

def test_sim_task_reports_metrics():
    import pytest
    pytest.importorskip("mujoco"); pytest.importorskip("mink")
    res = runner.invoke(app, ["sim-task"])
    assert res.exit_code == 0
    assert "place_error" in res.stdout
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --extra replay pytest tests/test_cli_sim_task.py -v`
Expected: FAIL (no `sim-task` command).

- [ ] **Step 3: Add the command** (follow the existing `replay_ik` pattern at `src/htdp/cli.py:175`)

```python
@app.command(name="sim-task")
def sim_task(
    video: Path | None = typer.Option(None, help="write demo MP4 to this path"),
    force: bool = typer.Option(False, help="overwrite an existing video"),
) -> None:
    """Run the SO-ARM100 pick-and-place sim episode; print metrics, optionally render."""
    from htdp.replay.episode import run_episode
    from htdp.replay.ik import IkUnavailable

    try:
        result = run_episode()
        if video is not None:
            from htdp.replay.render import render_episode
            render_episode(video, force=force)
    except IkUnavailable as exc:
        typer.echo(str(exc)); raise typer.Exit(code=1) from exc
    typer.echo(f"place_error_m={result.place_error:.4f} frames={result.frames_stepped}")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --extra replay pytest tests/test_cli_sim_task.py -v`
Expected: PASS.

- [ ] **Step 5: Generate the actual demo video (the portfolio artifact)**

Run: `uv run --extra replay htdp sim-task --video docs/demo/m1_pick_place.mp4`
Expected: prints `place_error_m=... frames=...`; MP4 exists. Eyeball it: arm picks the cube and places it on the green target.

- [ ] **Step 6: Update ROADMAP + README**

In `docs/ROADMAP.md` add an "M1 — Sim loop (SO-ARM100)" section marked done with the `htdp sim-task` command and the place-error metric. In `README.md`, lead the robotics story with: synthetic/recorded wrist trajectory → SO-ARM100 pick-and-place in MuJoCo (teleop-replay), rosbag2 export; link the demo video. Do not mention EEG in the headline.

- [ ] **Step 7: Full-suite gate + commit**

Run: `uv run --extra replay pytest -q` and `uv run mypy src` and `uv run ruff check src tests`
Expected: all green.

```bash
git add src/htdp/cli.py tests/test_cli_sim_task.py docs/ROADMAP.md README.md docs/demo/m1_pick_place.mp4
git commit -m "feat(cli): htdp sim-task pick-and-place demo + M1 docs"
```

---

## Self-Review

**Spec coverage (against `2026-06-26-portfolio-rescope-sim-loop-design.md`, M1 section):**
- "Swap arm.xml → real SO-ARM100 Menagerie model, wired to mink FrameTask, confirm `frame_name=eef` coupling" → Tasks 1–2.
- "Minimal task scene: table, object, target placement" → Task 3.
- "Gripper/contact step so place is real" → Task 4 (weld-based grasp; honest simplification documented in spec + plan).
- "Input = public/synthetic wrist trajectory, no capture hardware" → uses existing release pose / synth via `load_release_pose`-shaped input; Task 2 test feeds a trajectory directly. (Real public-data ingest is explicitly a later milestone.)
- "Deliverable: demo video + determinism/tracking-error metrics for the real arm" → Tasks 5 (video), 2 + 4 (determinism + tracking/place error), 6 (CLI surfaces metrics, generates the video).
- Global constraints (lazy import, optional extra, wheel artifacts, mypy strict, determinism) → Tasks 1 Step 6, all IK/render funcs lazy-import, Task 2/4 determinism tests.

**Placeholder scan:** Model-specific names (EEF_BODY, ARM_JOINTS, scene positions) are resolved by the runnable introspection in Task 1 Step 2, not left as TODO — this is the honest minimum, since exact names live in the vendored file. All code steps include runnable code.

**Type consistency:** `solve_arm_ik` accepts an 8-tuple pose `(t,x,y,z,qw,qx,qy,qz)` and only reads indices 0–3 — consistent across Task 2 test, Task 4 caller. `run_episode` gains an `on_step` callback (Task 5 Step 3) consumed by `render.py` (Task 5 Step 4) — names match. Scene constants (`OBJECT_BODY`, `TARGET_SITE`, `GRASP_WELD`) defined in Task 3, consumed unchanged in Tasks 4–5.

## Known risk carried into execution

The two genuinely uncertain spots, both isolated to one task each: (1) SO-ARM100 workspace scale vs the chosen cube/target positions (Task 2 Step 4 / Task 3) — mitigated by measuring reach in Task 2 before placing objects; (2) weld-grasp timing and qpos indexing (Task 4 Step 4) — mitigated by the explicit tuning notes. If the weld approach proves unstable, the fallback is a `tendon`/`adhesion` actuator, but try the weld first — it's the simplest robust grasp for a deterministic demo.
