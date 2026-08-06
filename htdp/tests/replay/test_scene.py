import pytest

pytest.importorskip("mujoco")

from htdp.replay.scene import (
    GRASP_WELD,
    OBJECT_BODY,
    TARGET_SITE,
    load_scene,
    object_xy,
    target_xy,
)


def test_scene_has_object_target_and_weld():
    import mujoco

    m = load_scene()
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, OBJECT_BODY) != -1
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, TARGET_SITE) != -1
    assert mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_EQUALITY, GRASP_WELD) != -1
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    assert len(object_xy(d)) == 2 and len(target_xy(m)) == 2
