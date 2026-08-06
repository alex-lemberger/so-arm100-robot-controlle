import pytest

pytest.importorskip("mujoco")

from htdp.replay.franka import (
    ARM_JOINTS,
    EEF_BODY,
    FRANKA_XML,
    GRASP_SITE,
    home_qpos,
    load_model,
)


def test_model_loads_and_names_exist():
    import mujoco

    assert FRANKA_XML.exists()
    m = load_model()

    def has(objtype, name):
        return mujoco.mj_name2id(m, objtype, name) != -1

    assert has(mujoco.mjtObj.mjOBJ_BODY, EEF_BODY)
    assert has(mujoco.mjtObj.mjOBJ_SITE, GRASP_SITE)
    for j in ARM_JOINTS:
        assert has(mujoco.mjtObj.mjOBJ_JOINT, j), j
    assert len(ARM_JOINTS) == 7  # Franka Panda is a 7-DOF arm
    assert len(home_qpos()) == m.nq  # home keyframe covers the full configuration
