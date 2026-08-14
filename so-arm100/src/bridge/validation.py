"""Compare a replayed (Isaac) trajectory against the commanded trajectory
(converted from the real recording) and report joint-space and end-effector
tracking error.

No Isaac imports -- consumes plain arrays of joint positions in radians, which
scripts/replay_episode.py captures during replay. AGENTS_NEW.md Task 6 / Sec 12.

`commanded` here means "what trajectory_converter.py produced from the real
recording", not real-hardware ground truth -- there is no motion-capture
reference. This measures how well Isaac's PD-driven articulation tracks the
target, not how well the simulated motion matches the real one.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from kinematics.forward_kinematics import forward_kinematics


def validate_replay(commanded: np.ndarray, actual: np.ndarray) -> dict:
    """
    Args:
        commanded: shape [N, 6] radians, columns = [5 arm joints, gripper] --
            the converted target trajectory (Timestep.action from trajectory_converter).
        actual: shape [N, 6] radians, same column order -- what Isaac's
            articulation actually reached at each step.

    Returns:
        dict with joint-space and end-effector error statistics, JSON-serializable.
    """
    commanded = np.asarray(commanded, dtype=np.float64)
    actual = np.asarray(actual, dtype=np.float64)
    if commanded.shape != actual.shape:
        raise ValueError(f"shape mismatch: commanded {commanded.shape} vs actual {actual.shape}")
    if commanded.ndim != 2 or commanded.shape[1] != 6:
        raise ValueError(f"expected shape [N, 6] (5 arm joints + gripper), got {commanded.shape}")

    joint_error = np.abs(commanded - actual)  # [N, 6]

    commanded_ee = np.array([forward_kinematics(row[:5]) for row in commanded])  # [N, 3]
    actual_ee = np.array([forward_kinematics(row[:5]) for row in actual])
    ee_error = np.linalg.norm(commanded_ee - actual_ee, axis=1)  # [N]

    return {
        "num_frames": int(commanded.shape[0]),
        "mean_joint_error_rad": float(joint_error.mean()),
        "max_joint_error_rad": float(joint_error.max()),
        "mean_ee_error_m": float(ee_error.mean()),
        "max_ee_error_m": float(ee_error.max()),
        "per_joint_mean_error_rad": joint_error.mean(axis=0).tolist(),
        "per_joint_max_error_rad": joint_error.max(axis=0).tolist(),
    }


def save_validation_result(result: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
