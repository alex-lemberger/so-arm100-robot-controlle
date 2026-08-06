# M2.5 A1 — Physics-Grasp Rollout Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the pick-place scene can be driven by a scripted teacher under *true MuJoCo physics* (`mj_step` + actuators) with a *friction* grasp — no kinematic `qpos` overwrite, no kinematic attach.

**Architecture:** A new physics scene (`task_scene_physics.xml`) enables finger↔cube contact and keeps the grasp weld disabled. A new driver `run_physics_episode` reuses the existing IK joint trajectory but feeds it to `data.ctrl` (position-servo actuators already defined in `panda.xml`), steps physics with `mj_step`, and closes the gripper via `ctrl[7]` so the cube is held by friction. Existing kinematic scene/teacher (`task_scene.xml`, `run_episode`) are left untouched so M2 keeps working.

**Tech Stack:** Python 3.11, MuJoCo, NumPy, mink (IK, via existing `solve_arm_ik`), pytest.

## Global Constraints

- Spend 0€ — sim only, no new deps. MuJoCo + mink already vendored under `.venv` / `--extra replay`.
- Do NOT modify `task_scene.xml`, `run_episode` (`src/htdp/replay/episode.py`), or any M2 learn module — M2 must stay green.
- mypy `--strict` clean for new `src/htdp/...` modules (match existing `# type: ignore[no-untyped-def]` convention for MuJoCo calls).
- Position-servo actuators only (already in `panda.xml`: `ctrl[:7]` = joint angle targets, `ctrl[7]` = gripper, 0=closed … 255=open). No torque control.
- Friction grasp only — the weld `grasp` stays `active="false"`. No kinematic cube slaving.

---

### Task 1: Physics scene with finger↔cube contact

**Files:**
- Create: `src/htdp/replay/assets/franka/task_scene_physics.xml`
- Modify: `src/htdp/replay/scene.py` (add `TASK_SCENE_PHYSICS_XML` constant)
- Test: `tests/replay/test_physics_scene.py`

**Interfaces:**
- Produces: `TASK_SCENE_PHYSICS_XML: Path` in `htdp.replay.scene`.

**Background:** In `task_scene.xml` the cube has `contype="2" conaffinity="2"`, which shares no bit with the arm/finger collision geoms (bit 0). That deliberately prevents finger↔cube contact for the kinematic attach. For a friction grasp the cube must collide with the fingers. Set the cube to `contype="1" conaffinity="1"` (collides with arm/fingers/table/floor, all on bit 0/1). Keep the weld present but `active="false"`. Raise cube friction so it does not slip out of the jaws.

- [ ] **Step 1: Write the failing test**

```python
# tests/replay/test_physics_scene.py
from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from htdp.replay.scene import TASK_SCENE_PHYSICS_XML


def test_physics_scene_loads_and_weld_inactive():
    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    # weld exists but is inactive (friction grasp, not kinematic attach)
    eq_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_EQUALITY, "grasp")
    assert eq_id != -1
    assert model.eq_active0[eq_id] == 0


def test_fingers_can_contact_cube():
    """Close the gripper on the cube at the grasp pose and assert a finger-cube contact forms."""
    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    cube_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "cube_geom")
    # left/right finger collision geoms live under the hand; gather all hand-subtree geoms
    hand_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand")
    # Park the gripper around the cube: set finger joints near-closed, cube between pads.
    # Drive via a forward sim with the gripper command fully closed.
    data.ctrl[7] = 0.0  # close gripper
    for _ in range(200):
        mujoco.mj_step(model, data)
    # at least one contact involves the cube geom
    cube_contacts = [
        c for c in data.contact[: data.ncon] if cube_gid in (c.geom1, c.geom2)
    ]
    assert len(cube_contacts) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/replay/test_physics_scene.py -v`
Expected: FAIL — `ImportError: cannot import name 'TASK_SCENE_PHYSICS_XML'`.

- [ ] **Step 3: Create the physics scene file**

Copy `task_scene.xml` to `task_scene_physics.xml` and change ONLY the cube geom collision + friction (everything else identical):

```xml
<mujoco model="franka_task_physics">
  <include file="panda.xml"/>

  <statistic center="0.4 0 0.3" extent="0.9"/>

  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>
    <rgba haze="0.15 0.25 0.35 1"/>
    <global azimuth="140" elevation="-25"/>
  </visual>

  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>
    <texture type="2d" name="groundplane" builtin="checker" mark="edge" rgb1="0.2 0.3 0.4" rgb2="0.1 0.2 0.3"
      markrgb="0.8 0.8 0.8" width="300" height="300"/>
    <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" reflectance="0.2"/>
  </asset>

  <worldbody>
    <light pos="0.4 0 1.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" size="0 0 0.05" type="plane" material="groundplane"/>

    <geom name="table" type="box" pos="0.5 0.0 0.10" size="0.22 0.30 0.10" rgba="0.8 0.8 0.8 1"
      contype="1" conaffinity="1"/>

    <body name="cube" pos="0.50 -0.15 0.225">
      <freejoint name="cube_free"/>
      <!-- contype/conaffinity on bit 0 so the fingers (also bit 0) actually collide with the
           cube; high friction so the friction grasp does not slip under gravity. -->
      <geom name="cube_geom" type="box" size="0.025 0.025 0.025" rgba="0.9 0.3 0.2 1" mass="0.05"
        contype="1" conaffinity="1" friction="1.5 0.05 0.001"/>
    </body>

    <site name="target" pos="0.50 0.15 0.205" size="0.03" rgba="0.2 0.8 0.2 0.5"/>
  </worldbody>

  <equality>
    <weld name="grasp" body1="hand" body2="cube" active="false"/>
  </equality>
</mujoco>
```

- [ ] **Step 4: Add the scene constant**

In `src/htdp/replay/scene.py`, after the `TASK_SCENE_XML` line add:

```python
TASK_SCENE_PHYSICS_XML = Path(__file__).parent / "assets" / "franka" / "task_scene_physics.xml"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/replay/test_physics_scene.py -v`
Expected: PASS (both tests). If `test_fingers_can_contact_cube` fails because the cube falls or the gripper misses, that is fine for now ONLY if a cube contact still forms with the table; the assertion is "a contact involving the cube exists." If zero cube contacts form, the bitmask change is wrong — recheck `contype`/`conaffinity`.

- [ ] **Step 6: Commit**

```bash
git add src/htdp/replay/assets/franka/task_scene_physics.xml src/htdp/replay/scene.py tests/replay/test_physics_scene.py
git commit -m "feat(replay): physics scene with finger-cube friction contact

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Position-servo trajectory tracking under physics

**Files:**
- Create: `src/htdp/replay/physics_episode.py`
- Test: `tests/replay/test_physics_episode.py`

**Interfaces:**
- Consumes: `TASK_SCENE_PHYSICS_XML` (Task 1); `solve_arm_ik(pose) -> ArmIkResult` with `.joint_trajectory: list[list[float]]` (`htdp.replay.arm_ik`); `GRASP_SITE = "grasp_site"` (`htdp.replay.franka`); `OBJECT_FREEJOINT`, `TARGET_SITE` (`htdp.replay.scene`).
- Produces: `track_joint_targets(model, data, targets, gripper_ctrl, *, settle) -> None` — sets `data.ctrl[:7]` to each target row, `data.ctrl[7] = gripper_ctrl`, and `mj_step`s `settle` times per row. Pure side effect on `data`.

This task proves the actuators track an IK joint trajectory (the cube is ignored — gripper stays open). Success = the grasp site reaches the final commanded joint pose's forward-kinematic position within tolerance.

- [ ] **Step 1: Write the failing test**

```python
# tests/replay/test_physics_episode.py
from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mink")  # IK backend
mujoco = pytest.importorskip("mujoco")

from htdp.replay.arm_ik import solve_arm_ik
from htdp.replay.franka import GRASP_SITE
from htdp.replay.physics_episode import track_joint_targets
from htdp.replay.scene import TASK_SCENE_PHYSICS_XML


def test_actuators_track_ik_target():
    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)
    mujoco.mj_forward(model, data)
    grasp_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, GRASP_SITE)

    # IK a single reachable point above the table.
    target_xyz = (0.50, -0.15, 0.35)
    sol = solve_arm_ik([(0.0, *target_xyz, 1.0, 0.0, 0.0, 0.0)]).joint_trajectory
    track_joint_targets(model, data, sol, gripper_ctrl=255.0, settle=400)

    reached = data.site_xpos[grasp_sid]
    err = float(np.linalg.norm(np.array(target_xyz) - reached))
    assert err < 0.03, f"grasp site off target by {err:.3f} m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/replay/test_physics_episode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'htdp.replay.physics_episode'`.

- [ ] **Step 3: Write the driver**

```python
# src/htdp/replay/physics_episode.py
from __future__ import annotations


def track_joint_targets(model, data, targets, gripper_ctrl, *, settle=20):  # type: ignore[no-untyped-def]
    """Drive the 7 arm position-servo actuators to each joint-target row under physics.

    ``targets`` is a sequence of 7-element joint-angle rows (e.g. ``solve_arm_ik(...).
    joint_trajectory``). For each row, ``data.ctrl[:7]`` is set to the row and ``data.ctrl[7]``
    to ``gripper_ctrl`` (0 = closed … 255 = open), then physics is advanced ``settle`` steps.
    No ``qpos`` overwrite — the actuators do the work.
    """
    import mujoco

    for row in targets:
        data.ctrl[:7] = row[:7]
        data.ctrl[7] = gripper_ctrl
        for _ in range(settle):
            mujoco.mj_step(model, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/replay/test_physics_episode.py::test_actuators_track_ik_target -v`
Expected: PASS. If `err` is borderline (0.03–0.06), raise `settle` (the servo needs more steps to converge); do NOT lower the tolerance.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/replay/physics_episode.py tests/replay/test_physics_episode.py
git commit -m "feat(replay): position-servo joint-target tracking under mj_step

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Friction grasp — close gripper and lift the cube

**Files:**
- Modify: `src/htdp/replay/physics_episode.py` (add `run_physics_episode`)
- Test: `tests/replay/test_physics_episode.py` (add lift test)

**Interfaces:**
- Consumes: `track_joint_targets` (Task 2); `_waypoints`-style Cartesian path — reuse the height constants `_Z_HI = 0.35`, `_Z_LO = 0.225` from `episode.py` (copy the values, do not import the private name).
- Produces: `run_physics_episode(cube_xy, *, interp=25, settle=20, grip_settle=200, gripper_open=255.0, gripper_close=0.0) -> PhysicsEpisodeResult` with fields `object_start_xy: tuple[float,float]`, `object_final_xy: tuple[float,float]`, `target_xy: tuple[float,float]`, `place_error: float`, `lifted: bool`, `frames_stepped: int`.

The driver walks the same 8 Cartesian waypoints as the kinematic teacher, but: (a) it commands the gripper *open* on approach, *closed* from the grasp waypoint onward; (b) at the grasp waypoint it holds the closed gripper for `grip_settle` steps so the fingers seat on the cube before lifting; (c) the cube rises only because friction holds it. This task's gate is **lift**; full place is Task 4.

- [ ] **Step 1: Write the failing test**

```python
def test_friction_grasp_lifts_cube():
    from htdp.replay.physics_episode import run_physics_episode

    res = run_physics_episode(cube_xy=(0.50, -0.15))
    assert res.lifted, "cube was not lifted by the friction grasp"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/replay/test_physics_episode.py::test_friction_grasp_lifts_cube -v`
Expected: FAIL — `ImportError: cannot import name 'run_physics_episode'`.

- [ ] **Step 3: Implement `run_physics_episode`**

Append to `src/htdp/replay/physics_episode.py`:

```python
from dataclasses import dataclass

_Z_HI = 0.35   # clearance height for approach / lift / traverse (matches episode.py)
_Z_LO = 0.225  # cube centre = table_top(0.20) + cube_half(0.025)


@dataclass
class PhysicsEpisodeResult:
    object_start_xy: tuple[float, float]
    object_final_xy: tuple[float, float]
    target_xy: tuple[float, float]
    place_error: float
    lifted: bool
    frames_stepped: int


def _grasp_waypoints(cube, tgt):  # type: ignore[no-untyped-def]
    # (x, y, z, gripper_closed)
    return [
        (cube[0], cube[1], _Z_HI, False),  # approach above cube, open
        (cube[0], cube[1], _Z_LO, False),  # descend, open
        (cube[0], cube[1], _Z_LO, True),   # close on cube (held grip_settle extra steps)
        (cube[0], cube[1], _Z_HI, True),   # lift
        (tgt[0], tgt[1], _Z_HI, True),     # traverse
        (tgt[0], tgt[1], _Z_LO, True),     # descend to target
        (tgt[0], tgt[1], _Z_LO, False),    # release
        (tgt[0], tgt[1], _Z_HI, False),    # retreat
    ]


def run_physics_episode(  # type: ignore[no-untyped-def]
    cube_xy,
    *,
    interp: int = 25,
    settle: int = 20,
    grip_settle: int = 200,
    gripper_open: float = 255.0,
    gripper_close: float = 0.0,
) -> "PhysicsEpisodeResult":
    import mujoco
    import numpy as np

    from htdp.replay.arm_ik import solve_arm_ik
    from htdp.replay.franka import GRASP_SITE
    from htdp.replay.scene import OBJECT_BODY, OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_PHYSICS_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)

    cube_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr = int(model.jnt_qposadr[cube_jid])
    data.qpos[cube_qadr : cube_qadr + 2] = cube_xy
    mujoco.mj_forward(model, data)

    start_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    start_z = float(data.body(OBJECT_BODY).xpos[2])
    cube_pos = data.body(OBJECT_BODY).xpos.copy()
    tgt_pos = model.site(TARGET_SITE).pos
    tgt_xy = (float(tgt_pos[0]), float(tgt_pos[1]))

    # Interpolate Cartesian keyframes; solve the whole path in one warm-started IK call.
    path: list[tuple[float, float, float, float, float, float, float, float]] = []
    grip_closed: list[bool] = []
    prev = _grasp_waypoints(cube_pos, tgt_pos)[0][:3]
    for x, y, z, closed in _grasp_waypoints(cube_pos, tgt_pos):
        for k in range(1, interp + 1):
            f = k / interp
            px = prev[0] + (x - prev[0]) * f
            py = prev[1] + (y - prev[1]) * f
            pz = prev[2] + (z - prev[2]) * f
            path.append((0.0, px, py, pz, 1.0, 0.0, 0.0, 0.0))
            grip_closed.append(closed)
        prev = (x, y, z)

    solutions = solve_arm_ik(path).joint_trajectory

    lifted = False
    frames = 0
    prev_closed = False
    for sol, closed in zip(solutions, grip_closed):
        gripper = gripper_close if closed else gripper_open
        # On the transition open->closed, seat the grip before moving on.
        n = settle + (grip_settle if closed and not prev_closed else 0)
        data.ctrl[:7] = sol[:7]
        data.ctrl[7] = gripper
        for _ in range(n):
            mujoco.mj_step(model, data)
            frames += 1
            if float(data.body(OBJECT_BODY).xpos[2]) > start_z + 0.05:
                lifted = True
        prev_closed = closed

    cube = data.body(OBJECT_BODY).xpos
    final_xy = (float(cube[0]), float(cube[1]))
    place_error = float(np.hypot(final_xy[0] - tgt_xy[0], final_xy[1] - tgt_xy[1]))
    return PhysicsEpisodeResult(start_xy, final_xy, tgt_xy, place_error, lifted, frames)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/replay/test_physics_episode.py::test_friction_grasp_lifts_cube -v`
Expected: PASS.

**If it FAILS (cube not lifted), debug in this order — do not give up on the friction grasp:**
1. The fingers miss/under-grip → raise `grip_settle` (more seat time) and/or check `_Z_LO` lands the pads on the cube (the grasp site sits between fingertips; descend until pads straddle the cube body).
2. Cube slips out under gravity → raise cube `friction` (Task 1 scene, first component e.g. `2.0`) or confirm `ctrl[7]=0` actually closes (gripper actuator `ctrlrange="0 255"`, 0=closed).
3. IK can't reach `_Z_LO` over the cube → print `solve_arm_ik(path).max_error`; if large, the path is unreachable, not a grip problem.

- [ ] **Step 5: Commit**

```bash
git add src/htdp/replay/physics_episode.py tests/replay/test_physics_episode.py
git commit -m "feat(replay): friction grasp lifts cube under physics (no kinematic attach)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Full pick-and-place under physics (A1 gate)

**Files:**
- Test: `tests/replay/test_physics_episode.py` (add place test)
- Create: `docs/m2/a1-physics-grasp.md` (short result note)

**Interfaces:**
- Consumes: `run_physics_episode(...) -> PhysicsEpisodeResult` (Task 3).

This is the A1 acceptance gate: the scripted teacher, under true physics with a friction grasp, picks the cube and places it on the target.

- [ ] **Step 1: Write the failing/acceptance test**

```python
def test_physics_pick_and_place_succeeds():
    from htdp.replay.physics_episode import run_physics_episode

    res = run_physics_episode(cube_xy=(0.50, -0.15))
    assert res.lifted
    assert res.place_error < 0.05, f"place_error {res.place_error:.3f} m too high"
```

- [ ] **Step 2: Run test**

Run: `uv run pytest tests/replay/test_physics_episode.py::test_physics_pick_and_place_succeeds -v`
Expected: PASS if Task 3 tuning held; otherwise tune release timing — the cube should be over the target at `_Z_LO` before the gripper opens. If `place_error` is high, the cube is dropped early or slips during traverse: raise `settle` on the traverse rows or `grip_settle`.

- [ ] **Step 3: Sanity-check robustness across cube positions**

Run a quick spread (not committed — scratch check):

```bash
uv run python -c "
from htdp.replay.physics_episode import run_physics_episode
for xy in [(0.46,-0.18),(0.50,-0.15),(0.54,-0.12)]:
    r = run_physics_episode(cube_xy=xy)
    print(xy, 'lifted', r.lifted, 'place_err', round(r.place_error,3))
"
```
Expected: lifted True and place_err < 0.05 for all three. If one corner fails, note it in the result doc — do not over-tune; A2 will regenerate demos only over the success region.

- [ ] **Step 4: Write the result note**

Create `docs/m2/a1-physics-grasp.md`:

```markdown
# M2.5 A1 — Physics-Grasp Rollout (result)

**Done:** Scripted teacher picks and places the cube under true MuJoCo physics
(`mj_step` + position-servo actuators) with a **friction grasp** — no `qpos`
overwrite, no kinematic attach. Replaces the M1/M2 kinematic shortcut for the
sim loop.

**Scene:** `task_scene_physics.xml` — cube on collision bit 0 (collides with
fingers), friction raised, grasp weld left inactive.
**Driver:** `htdp.replay.physics_episode.run_physics_episode` — drives `data.ctrl`,
opens/closes the gripper, seats the grip for `grip_settle` steps before lifting.

**Gate:** `test_physics_pick_and_place_succeeds` — lifted and place_error < 0.05 m.

**Next (A2):** regenerate LeRobot demos from this physics teacher; finger width now
varies, so it returns to the observation (reverses the M2 constant-feature drop).
```

- [ ] **Step 5: Run the full replay+learn suite to confirm M2 still green**

Run: `uv run pytest tests/replay tests/learn -q`
Expected: PASS — no M2 regression (kinematic `task_scene.xml` / `run_episode` untouched).

- [ ] **Step 6: Commit**

```bash
git add tests/replay/test_physics_episode.py docs/m2/a1-physics-grasp.md
git commit -m "test(replay): A1 gate - physics friction pick-and-place succeeds

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- "Use actuators + `mj_step`, not kinematic write" → Tasks 2, 3 (`data.ctrl` + `mj_step`, no `qpos` overwrite).
- "Friction grasp, drop kinematic attach" → Task 1 (collision bitmask + friction, weld inactive) + Task 3 (gripper close + seat + lift by friction).
- "Prove scene with scripted teacher, no learning" → Task 4 gate uses the IK teacher trajectory, no policy.
- "Don't break M2" → Global Constraints + Task 4 Step 5 runs `tests/learn`.

**Placeholder scan:** No TBDs; every code step has full code; debug steps enumerate concrete ordered actions, not "handle edge cases."

**Type consistency:** `track_joint_targets(model, data, targets, gripper_ctrl, *, settle)` defined Task 2, reused Task 3. `run_physics_episode(cube_xy, *, ...) -> PhysicsEpisodeResult` defined Task 3, reused Task 4. Field names (`lifted`, `place_error`, `object_final_xy`) consistent across Tasks 3–4. Constants `_Z_HI=0.35`, `_Z_LO=0.225` match `episode.py` values (copied, not imported, per Global Constraints).

**Open risk:** friction-grasp tuning (`grip_settle`, friction coefficient, `_Z_LO` seating depth) is the only empirical unknown — Tasks 3 and 4 carry ordered debug ladders for it. If after exhausting them the top-down friction grasp proves unstable across the whole cube region, fall back is to narrow the cube region for A2 (noted in Task 4 Step 3), not to revert to kinematic attach.
