"""Scripted inspection-and-reach animation for the Unitree H1 humanoid.

Joint order matches the XML actuator list (19 DOF):
  0  left_hip_yaw       5  right_hip_yaw      10 torso (yaw)
  1  left_hip_roll      6  right_hip_roll      11 left_shoulder_pitch
  2  left_hip_pitch     7  right_hip_pitch     12 left_shoulder_roll
  3  left_knee          8  right_knee          13 left_shoulder_yaw
  4  left_ankle         9  right_ankle         14 left_elbow
                                                15 right_shoulder_pitch
                                                16 right_shoulder_roll
                                                17 right_shoulder_yaw
                                                18 right_elbow

Animation: slow torso sweep + right arm overhead arc + left arm counterbalance.
EEG modulation: fatigue slows motion; inFlow raises amplitude.
"""
from __future__ import annotations
import numpy as np

N_JOINTS = 19

# Neutral standing pose (legs bent, arms at sides) — matches XML keyframe.
HOME = np.zeros(N_JOINTS)
HOME[2] = -0.4    # left_hip_pitch
HOME[3] =  0.8    # left_knee
HOME[4] = -0.4    # left_ankle
HOME[7] = -0.4    # right_hip_pitch
HOME[8] =  0.8    # right_knee
HOME[9] = -0.4    # right_ankle

# Motion parameters
TURN_HZ   = 0.12   # torso sweep: full cycle ~8s
REACH_HZ  = 0.20   # arm arc: full cycle ~5s
DETAIL_HZ = 0.80   # elbow detail: ~1.25s

MIN_SPEED = 0.35   # fatigue=1 → motion slows to 35% of base


def troweling_targets(
    t: float,
    fatigue: float | None = None,
    in_flow: bool = False,
) -> np.ndarray:
    """Return H1 joint targets for wall-time t (seconds).

    fatigue 0–1: slows all motion when high.
    in_flow: raises arm amplitude (EEG flow state = bigger gestures).
    """
    _f = max(0.0, min(1.0, fatigue if fatigue is not None else 0.0))
    speed = 1.0 - _f * (1.0 - MIN_SPEED)
    ts = t * speed  # fatigue-scaled time

    flow_boost = 0.25 if in_flow else 0.0

    q = HOME.copy()

    # --- torso yaw: slow survey turn left/right ---
    q[10] = 0.55 * np.sin(2 * np.pi * TURN_HZ * ts)

    # --- right arm: big overhead arc (pitch + roll + elbow) ---
    reach = np.sin(2 * np.pi * REACH_HZ * ts)          # -1 … +1
    q[15] = 0.75 + (0.65 + flow_boost) * reach          # 0.1 → 1.4 rad (forward/up)
    q[16] = -0.15 + -0.18 * np.cos(2 * np.pi * REACH_HZ * ts)  # -0.33 … +0.03 rad
    q[17] =  0.20 * np.sin(2 * np.pi * DETAIL_HZ * ts)  # wrist yaw detail
    q[18] =  0.35 + 0.40 * abs(np.cos(2 * np.pi * REACH_HZ * ts))  # elbow bends at sides

    # --- left arm: counterbalance (opposite phase) ---
    q[11] = 0.45 + (0.35 + flow_boost) * (-reach)       # mirror right
    q[12] = 0.05                                          # slight outward
    q[14] = 0.25 + 0.20 * abs(np.sin(2 * np.pi * REACH_HZ * ts))

    return q
