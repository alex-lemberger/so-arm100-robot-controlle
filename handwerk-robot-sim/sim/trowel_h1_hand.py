"""Animation targets for H1 + right dexterous hand grasping a trowel.

ctrl[0:19]  — arm position targets (same joints as trowel_h1.py)
ctrl[19:34] — finger position targets (15 joints, 3 per finger)

Finger joint order:
  19-21  thumb  (mcp, pip, dip)   max: (1.3, 1.2, 1.0)
  22-24  index  (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  25-27  middle (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  28-30  ring   (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  31-33  pinky  (mcp, pip, dip)   max: (1.5, 1.4, 1.2)

Phases:
  t < GRASP_S : arm holds HOME, fingers ramp 0 → grip target
  t >= GRASP_S: existing troweling arm motion, fingers hold grip
"""
from __future__ import annotations
import numpy as np

try:
    from .trowel_h1 import troweling_targets as _arm_targets, HOME as _ARM_HOME
except ImportError:
    from trowel_h1 import troweling_targets as _arm_targets, HOME as _ARM_HOME  # type: ignore[no-redef]

GRASP_S = 1.5  # seconds for grasp ramp

# Max flexion per finger joint [rad]: (mcp, pip, dip)
_MAX = np.array([
    [1.3, 1.2, 1.0],  # thumb
    [1.5, 1.4, 1.2],  # index
    [1.5, 1.4, 1.2],  # middle
    [1.5, 1.4, 1.2],  # ring
    [1.5, 1.4, 1.2],  # pinky
])  # shape (5, 3)

# Home ctrl for arm (34 values: 19 arm angles + 15 zeros for open fingers)
HOME = np.zeros(34)
HOME[:19] = _ARM_HOME


def _finger_ctrl(grip: float, passive: float) -> np.ndarray:
    """Return 15 finger ctrl targets.

    grip    : 0-1, primary grip (thumb, index, middle)
    passive : 0-1, passive wrap  (ring, pinky)
    """
    scales = np.array([grip, grip, grip, passive, passive])  # (5,) per finger
    return (_MAX * scales[:, np.newaxis]).ravel()             # (15,)


def troweling_targets(
    t: float,
    fatigue: float | None = None,
    in_flow: bool = False,
) -> np.ndarray:
    """Return 34-element ctrl array for H1 + hand at wall-time t (seconds).

    fatigue 0-1 : slows arm motion and loosens grip.
    in_flow     : maximises grip and arm amplitude.
    """
    _f = max(0.0, min(1.0, fatigue if fatigue is not None else 0.0))
    grip = 1.0 if in_flow else 0.85 - _f * 0.25
    passive = grip * 0.70

    if t < GRASP_S:
        ramp = t / GRASP_S
        arm = _ARM_HOME.copy()
        fingers = _finger_ctrl(ramp * grip, ramp * passive)
    else:
        arm = _arm_targets(t - GRASP_S, fatigue=fatigue, in_flow=in_flow)
        fingers = _finger_ctrl(grip, passive)

    return np.concatenate([arm, fingers])
