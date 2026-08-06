from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("mink")  # IK backend
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


def test_friction_grasp_lifts_cube():
    from htdp.replay.physics_episode import run_physics_episode

    res = run_physics_episode(cube_xy=(0.50, -0.15))
    assert res.lifted, "cube was not lifted by the friction grasp"


def test_physics_pick_and_place_succeeds():
    from htdp.replay.physics_episode import run_physics_episode

    res = run_physics_episode(cube_xy=(0.50, -0.15))
    assert res.lifted
    assert res.place_error < 0.05, f"place_error {res.place_error:.3f} m too high"


def test_on_sample_fires_once_per_ik_sample_with_settled_state():
    """The demo recorder needs one settled (model, data, closed) row per IK target, NOT one per
    mj_step — otherwise the 200-step grasp dwell over-represents a single pose."""
    from htdp.replay.physics_episode import run_physics_episode

    samples = []

    def on_sample(model, data, closed):  # type: ignore[no-untyped-def]
        samples.append((closed, float(data.qpos[7] + data.qpos[8])))

    res = run_physics_episode(cube_xy=(0.50, -0.15), on_sample=on_sample)
    assert res.lifted

    # interp(25) * 8 waypoints = 200 IK samples -> 200 callback rows (one per target, not per step)
    assert len(samples) == 200

    closed_flags = [c for c, _ in samples]
    assert any(closed_flags) and not all(closed_flags)  # grip toggles on then off

    widths = [w for _, w in samples]
    assert max(widths) - min(widths) > 0.01  # fingers actually move (no constant-feature landmine)
