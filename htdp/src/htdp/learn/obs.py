from __future__ import annotations

import numpy as np

OBS_DIM = 17
ACTION_DIM = 8

# Finger width (sum of both finger joint positions) IS in the observation as of M2.5: the physics
# teacher actuates the gripper, so width varies across demos (std > 0) and carries real grasp
# state. (In M2 the kinematic teacher never moved the fingers, so width was constant — a
# normalization landmine — and was dropped. The physics teacher reverses that.) Appended LAST so
# the legacy 0:16 layout (joints, eef, cube, target) is unchanged.
OBS_NAMES = [
    *(f"q{i}" for i in range(7)),
    "eef_x", "eef_y", "eef_z",
    "cube_x", "cube_y", "cube_z",
    "tgt_x", "tgt_y", "tgt_z",
    "finger_width",
]
ACTION_NAMES = [*(f"q{i}_target" for i in range(7)), "gripper"]

# B3 visuomotor proprioception: the non-privileged subset of the 17-dim state — joints, eef
# position, finger width. The cube xyz (10:13) and target xyz (13:16) are DROPPED; the visuomotor
# policy must localise the cube and goal from pixels, not be handed them. Defined as indices into
# the full state so there is one source of truth (proprio_from_state slices, build_proprio builds).
PROPRIO_INDICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 16]
PROPRIO_DIM = len(PROPRIO_INDICES)
PROPRIO_NAMES = [OBS_NAMES[i] for i in PROPRIO_INDICES]


def proprio_from_state(state: np.ndarray) -> np.ndarray:
    """Slice the proprioceptive subset out of a full (…, 17) state array."""
    return state[..., PROPRIO_INDICES]


def build_proprio_observation(model, data, grasp_sid: int) -> np.ndarray:  # type: ignore[no-untyped-def]
    """Proprio observation, shape (11,): joints + eef xyz + finger width (no cube/target)."""
    return proprio_from_state(build_observation(model, data, grasp_sid))


def build_observation(model, data, grasp_sid: int) -> np.ndarray:  # type: ignore[no-untyped-def]
    """State observation, shape (17,). See OBS_NAMES for the layout."""
    eef = data.site_xpos[grasp_sid]
    cube = data.body("cube").xpos
    tgt = model.site("target").pos
    finger_width = float(data.qpos[7] + data.qpos[8])
    return np.concatenate(
        [
            data.qpos[:7],
            eef,
            cube,
            tgt,
            np.array([finger_width]),
        ]
    ).astype(np.float32)


def build_action(data, grasp_active: bool) -> np.ndarray:  # type: ignore[no-untyped-def]
    """Action, shape (8,): 7 joint position targets + gripper (1=close, 0=open)."""
    return np.concatenate(
        [data.qpos[:7], np.array([1.0 if grasp_active else 0.0])]
    ).astype(np.float32)
