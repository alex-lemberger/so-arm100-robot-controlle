"""Forward kinematics for the SO-ARM100's 5-DOF arm chain (excludes the gripper jaw).

Kinematic parameters (each joint's fixed parent-to-joint-frame transform, plus
its rotation axis) were extracted once from the RobotStudio SO-100 USD asset
(see docs/current_system.md) via:

    from pxr import Usd
    stage = Usd.Stage.Open(usd_path)
    prim = stage.GetPrimAtPath("/so_arm100/joints/<name>")
    prim.GetAttribute("physics:localPos0").Get()   # translation, joint frame in parent-link frame
    prim.GetAttribute("physics:localRot0").Get()   # rotation (w, x, y, z)
    prim.GetAttribute("physics:axis").Get()        # revolute axis: X, Y, or Z

Every joint's localPos1/localRot1 in that USD is identity, meaning the joint
frame in the CHILD link's frame coincides with the child link's own origin --
so each link's transform relative to its parent is simply:
    T(localPos0, localRot0) @ Rot(axis, theta)

No Isaac/pxr imports here -- this module must run on any machine (Rule 5). The
kinematic chain is a fixed constant, not re-derived at runtime.
"""

from __future__ import annotations

import numpy as np

# (name, local_pos0 [m], local_rot0 quat (w, x, y, z), rotation axis) per joint,
# in chain order base -> shoulder -> upper_arm -> lower_arm -> wrist -> gripper mount.
_CHAIN = [
    ("shoulder_pan", (0.0, -0.0452, 0.0165), (0.707109, 0.70710456, 0.0, 0.0), "Y"),
    ("shoulder_lift", (0.0, 0.1025, 0.0306), (0.62161, -0.7833269, 0.0, 0.0), "X"),
    ("elbow_flex", (0.0, 0.11257, 0.028), (0.707109, 0.70710456, 0.0, 0.0), "X"),
    ("wrist_flex", (0.0, 0.0052, 0.1349), (0.87758255, -0.47942555, 0.0, 0.0), "X"),
    ("wrist_roll", (0.0, -0.0601, 0.0), (0.707109, 0.0, 0.70710456, 0.0), "Y"),
]

JOINT_NAMES = [j[0] for j in _CHAIN]


def _quat_to_matrix(q: tuple[float, float, float, float]) -> np.ndarray:
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def _axis_rotation_matrix(axis: str, theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    if axis == "X":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "Y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])  # Z


def _link_transform(local_pos0, local_rot0, axis: str, theta: float) -> np.ndarray:
    """4x4 transform from a link's parent frame to the link's own frame."""
    r = _quat_to_matrix(local_rot0) @ _axis_rotation_matrix(axis, theta)
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = local_pos0
    return t


def forward_kinematics(joint_positions_rad: np.ndarray) -> np.ndarray:
    """End-effector (wrist/gripper-mount) position in the robot base frame.

    Args:
        joint_positions_rad: shape [5], radians, order
            [shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll]
            (matches robot_mapping.yaml's `joints` list / trajectory_converter's
            `Timestep.joint_positions`). Excludes the gripper jaw joint -- opening
            or closing the jaw doesn't move this reference point.

    Returns:
        np.ndarray shape [3]: (x, y, z) position in metres, base-link frame.
    """
    joint_positions_rad = np.asarray(joint_positions_rad, dtype=np.float64)
    if joint_positions_rad.shape != (len(_CHAIN),):
        raise ValueError(f"expected {len(_CHAIN)} joint angles, got shape {joint_positions_rad.shape}")

    t_total = np.eye(4)
    for (_, local_pos0, local_rot0, axis), theta in zip(_CHAIN, joint_positions_rad):
        t_total = t_total @ _link_transform(local_pos0, local_rot0, axis, theta)

    return t_total[:3, 3]
