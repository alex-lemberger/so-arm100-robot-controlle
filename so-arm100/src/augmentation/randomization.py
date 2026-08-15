"""Sample per-episode randomization parameters for synthetic data generation
(AGENTS_NEW.md Task 9 / Sec 16-17).

No Isaac imports -- pure sampling from configs/simulation.yaml's `randomization`
section plus a seed, so it's testable standalone. src/isaac/scene_setup.py applies
the sampled Variation to the actual Isaac scene.

LABEL-PRESERVING vs LABEL-BREAKING (added 2026-08-15)
----------------------------------------------------
scripts/generate_synthetic.py copies the parent episode's action trajectory
VERBATIM (Rule 4: motion is not re-planned at this stage). That makes an axis
safe to randomize only if moving it leaves those copied actions correct:

  label-preserving -- mass_scale, friction_scale, robot_initial_joint_noise_deg
    (spent before the settle-to-frame-0 phase), camera_pixel_noise_std, and
    object_rotation_deg.yaw (the peg is a cylinder, so yaw is geometrically a
    no-op -- this stops being true the moment a non-symmetric object is used).

  label-breaking -- object_position, board_position, board_rotation_deg. These
    move the thing the trajectory was reaching for while the labels still say
    "reach where it used to be", which trains the policy to IGNORE the target's
    position. That is the exact failure being fought on hardware (grasp 4/8 on
    rollout_grasp_v1_r1), so a dataset containing these episodes is actively
    harmful, not merely diluted. Fixing them needs IK to re-plan the reach; the
    repo has forward kinematics only.

Label-breaking ranges therefore live under `randomization.label_breaking:` and
are sampled but ZEROED unless the caller passes allow_label_breaking=True
(scripts/generate_synthetic.py: --allow-label-breaking). Do not flip that flag
until the actions are re-planned per variation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

# Keys that used to sit at the top level of `randomization:` and now must live under
# `label_breaking:`. A config still carrying them at the top level is a pre-2026-08-15
# config that would silently generate mislabelled episodes, so we refuse it outright
# rather than guessing at the author's intent.
_LABEL_BREAKING_KEYS = ("object_position", "board_position", "board_rotation_deg")


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
    # Provenance, added 2026-08-15: records whether the pose axes above were allowed
    # to be non-zero, so a dataset can be audited from its own episode records.
    label_breaking_applied: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def sample_variation(
    randomization_cfg: dict,
    seed: int,
    num_arm_joints: int = 5,
    allow_label_breaking: bool = False,
) -> Variation:
    """Deterministic given (randomization_cfg, seed) -- Rule 10: every experiment must
    be reproducible from its recorded seed alone.

    With allow_label_breaking=False (the default) the pose axes under
    `label_breaking:` are still DRAWN and then discarded, so the random stream --
    and therefore every label-preserving value for a given seed -- is identical
    either way. See the module docstring for why they are off by default.
    """
    stale = [k for k in _LABEL_BREAKING_KEYS if k in randomization_cfg]
    if stale:
        raise ValueError(
            f"randomization: has label-breaking key(s) {stale} at the top level. "
            "These move the target while the copied action labels do not follow, which "
            "trains the policy to ignore the target's position. Move them under "
            "`label_breaking:` (see configs/simulation.yaml) and pass "
            "--allow-label-breaking only once actions are re-planned per variation."
        )

    rng = np.random.default_rng(seed)

    breaking_cfg = randomization_cfg.get("label_breaking", {})
    pos_cfg = breaking_cfg.get("object_position")
    yaw_range = randomization_cfg["object_rotation_deg"]["yaw"]
    mass_cfg = randomization_cfg["mass_scale"]
    friction_cfg = randomization_cfg["friction_scale"]
    joint_noise_deg = randomization_cfg.get("robot_initial_joint_noise_deg", 0.0)
    camera_noise_std = randomization_cfg.get("camera_pixel_noise_std", 0.0)

    # Draw order below is FROZEN. Every draw keeps the position it had when the
    # dataset that used it was generated, so a given seed still reproduces the exact
    # variation of the already-generated data/synthetic/ episodes (Rule 10).
    # Reordering, adding or conditionally skipping a draw silently invalidates every
    # recorded seed -- which is why the label-breaking draws below happen even when
    # their values are about to be thrown away.
    object_offset_x = float(rng.uniform(*pos_cfg["x"])) if pos_cfg else 0.0
    object_offset_y = float(rng.uniform(*pos_cfg["y"])) if pos_cfg else 0.0
    yaw_deg = float(rng.uniform(*yaw_range))
    mass_scale = float(rng.uniform(mass_cfg["min"], mass_cfg["max"]))
    friction_scale = float(rng.uniform(friction_cfg["min"], friction_cfg["max"]))
    robot_joint_noise_deg = rng.uniform(-joint_noise_deg, joint_noise_deg, size=num_arm_joints).tolist()

    board_pos_cfg = breaking_cfg.get("board_position")
    board_yaw_cfg = breaking_cfg.get("board_rotation_deg", {}).get("yaw")
    board_offset_x = float(rng.uniform(*board_pos_cfg["x"])) if board_pos_cfg else 0.0
    board_offset_y = float(rng.uniform(*board_pos_cfg["y"])) if board_pos_cfg else 0.0
    board_yaw_deg = float(rng.uniform(*board_yaw_cfg)) if board_yaw_cfg else 0.0

    if not allow_label_breaking:
        object_offset_x = object_offset_y = 0.0
        board_offset_x = board_offset_y = board_yaw_deg = 0.0

    return Variation(
        object_offset_x=object_offset_x,
        object_offset_y=object_offset_y,
        yaw_deg=yaw_deg,
        mass_scale=mass_scale,
        friction_scale=friction_scale,
        robot_joint_noise_deg=robot_joint_noise_deg,
        camera_noise_std=float(camera_noise_std),
        board_offset_x=board_offset_x,
        board_offset_y=board_offset_y,
        board_yaw_deg=board_yaw_deg,
        label_breaking_applied=bool(allow_label_breaking),
    )
