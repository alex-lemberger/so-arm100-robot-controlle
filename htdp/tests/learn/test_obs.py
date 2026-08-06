import pytest

pytest.importorskip("mujoco")

import numpy as np

from htdp.learn.obs import ACTION_DIM, OBS_DIM, build_action, build_observation


def test_obs_and_action_shapes_and_target():
    import mujoco

    from htdp.replay.scene import TASK_SCENE_XML, TARGET_SITE

    m = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    gsid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")

    obs = build_observation(m, d, gsid)
    assert obs.shape == (OBS_DIM,)
    # last three entries are the fixed target xyz
    tgt = m.site(TARGET_SITE).pos
    assert np.allclose(obs[13:16], tgt)

    act_open = build_action(d, False)
    act_closed = build_action(d, True)
    assert act_open.shape == (ACTION_DIM,)
    assert act_open[7] == 0.0 and act_closed[7] == 1.0
    assert np.allclose(act_open[:7], d.qpos[:7])


def test_proprio_drops_privileged_cube_and_target():
    """B3 visuomotor obs: proprioception only (joints, eef, finger width). The privileged cube and
    target xyz are removed -- the policy must read object/goal location from pixels, not state."""
    import mujoco

    from htdp.learn.obs import (
        PROPRIO_DIM,
        PROPRIO_INDICES,
        build_observation,
        build_proprio_observation,
        proprio_from_state,
    )
    from htdp.replay.scene import TASK_SCENE_PHYSICS_XML

    assert PROPRIO_DIM == 11
    # joints 0..6, eef 7..9, finger_width 16 -- never cube (10..12) or target (13..15)
    assert PROPRIO_INDICES == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 16]
    assert not any(i in PROPRIO_INDICES for i in (10, 11, 12, 13, 14, 15))

    m = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    d = mujoco.MjData(m)
    d.qpos[7] = d.qpos[8] = 0.03
    mujoco.mj_forward(m, d)
    gsid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")

    full = build_observation(m, d, gsid)
    prop = build_proprio_observation(m, d, gsid)
    assert prop.shape == (PROPRIO_DIM,)
    # built-direct equals slicing the full state -- one source of truth
    assert np.allclose(prop, proprio_from_state(full))
    assert np.allclose(prop, full[PROPRIO_INDICES])


def test_obs_last_entry_is_finger_width():
    """Physics teacher actuates the fingers, so width varies and returns to the observation.

    Appended at index 16 (after the fixed target xyz) so the legacy 0:16 layout is unchanged.
    """
    import mujoco

    from htdp.replay.scene import TASK_SCENE_PHYSICS_XML

    m = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    d = mujoco.MjData(m)
    gsid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "grasp_site")

    # Fingers wide open vs. fully closed must give different observed widths.
    d.qpos[7] = d.qpos[8] = 0.04
    mujoco.mj_forward(m, d)
    wide = build_observation(m, d, gsid)
    assert wide.shape == (OBS_DIM,)
    assert OBS_DIM == 17

    d.qpos[7] = d.qpos[8] = 0.0
    mujoco.mj_forward(m, d)
    closed = build_observation(m, d, gsid)

    assert wide[16] > closed[16]  # width feature tracks finger opening
    assert np.isclose(wide[16], 0.08)  # both fingers fully open
