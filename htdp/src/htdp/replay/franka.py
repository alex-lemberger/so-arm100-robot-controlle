from __future__ import annotations

from pathlib import Path

FRANKA_XML = Path(__file__).parent / "assets" / "franka" / "panda.xml"

# Filled from introspection of the vendored MuJoCo Menagerie Franka Emika Panda model:
EEF_BODY = "hand"  # gripper palm body; its +z axis points out of the jaws (downward at home)
GRASP_SITE = "grasp_site"  # site between the fingertips that the IK tracks
ARM_JOINTS = ("joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "joint7")  # 7-DOF
FINGER_JOINTS = ("finger_joint1", "finger_joint2")


def load_model():  # type: ignore[no-untyped-def]
    import mujoco  # lazy

    return mujoco.MjModel.from_xml_path(str(FRANKA_XML))


def home_qpos():  # type: ignore[no-untyped-def]
    """The vendored ``home`` keyframe joint pose — a non-singular start for IK (the zero pose
    has the arm fully extended, a poor seed for differential IK)."""
    import mujoco

    model = load_model()  # type: ignore[no-untyped-call]
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    return model.key_qpos[key].copy()
