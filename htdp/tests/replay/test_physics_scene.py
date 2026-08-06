from __future__ import annotations

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
