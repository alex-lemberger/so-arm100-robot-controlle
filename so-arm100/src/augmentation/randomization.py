"""Sample per-episode randomization parameters for synthetic data generation
(AGENTS_NEW.md Task 9 / Sec 16-17).

No Isaac imports -- pure sampling from configs/simulation.yaml's `randomization`
section plus a seed, so it's testable standalone. src/isaac/scene_setup.py applies
the sampled Variation to the actual Isaac scene.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Variation:
    object_offset_x: float
    object_offset_y: float
    yaw_deg: float
    mass_scale: float
    friction_scale: float
    robot_joint_noise_deg: list[float]  # per-arm-joint, same order as robot_mapping.yaml's `joints`
    camera_noise_std: float  # sampled + recorded for provenance; not yet applied, see simulation.yaml
    # Board pose, added 2026-08-14. Defaults keep the board fixed, so a config
    # without a `board_position` section behaves exactly as before.
    board_offset_x: float = 0.0
    board_offset_y: float = 0.0
    board_yaw_deg: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def sample_variation(randomization_cfg: dict, seed: int, num_arm_joints: int = 5) -> Variation:
    """Deterministic given (randomization_cfg, seed) -- Rule 10: every experiment must
    be reproducible from its recorded seed alone."""
    rng = np.random.default_rng(seed)

    pos_cfg = randomization_cfg["object_position"]
    yaw_range = randomization_cfg["object_rotation_deg"]["yaw"]
    mass_cfg = randomization_cfg["mass_scale"]
    friction_cfg = randomization_cfg["friction_scale"]
    joint_noise_deg = randomization_cfg.get("robot_initial_joint_noise_deg", 0.0)
    camera_noise_std = randomization_cfg.get("camera_pixel_noise_std", 0.0)

    # Drawn LAST, deliberately. Every draw before this point keeps the position it
    # had before board randomization existed, so a given seed still reproduces the
    # exact object/mass/friction/joint variation of the already-generated datasets
    # (Rule 10). Inserting these earlier would silently invalidate every recorded
    # seed in data/synthetic/.
    board_pos_cfg = randomization_cfg.get("board_position")
    board_yaw_cfg = randomization_cfg.get("board_rotation_deg", {}).get("yaw")

    return Variation(
        object_offset_x=float(rng.uniform(*pos_cfg["x"])),
        object_offset_y=float(rng.uniform(*pos_cfg["y"])),
        yaw_deg=float(rng.uniform(*yaw_range)),
        mass_scale=float(rng.uniform(mass_cfg["min"], mass_cfg["max"])),
        friction_scale=float(rng.uniform(friction_cfg["min"], friction_cfg["max"])),
        robot_joint_noise_deg=rng.uniform(-joint_noise_deg, joint_noise_deg, size=num_arm_joints).tolist(),
        camera_noise_std=float(camera_noise_std),
        board_offset_x=float(rng.uniform(*board_pos_cfg["x"])) if board_pos_cfg else 0.0,
        board_offset_y=float(rng.uniform(*board_pos_cfg["y"])) if board_pos_cfg else 0.0,
        board_yaw_deg=float(rng.uniform(*board_yaw_cfg)) if board_yaw_cfg else 0.0,
    )
