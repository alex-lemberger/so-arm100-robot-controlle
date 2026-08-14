"""Convert one LeRobot episode into normalized, Isaac-ready timesteps.

No Isaac imports here -- this module must run on any machine
(AGENTS_NEW.md Task 4 / Rule 5). Isaac-side replay lives in
scripts/replay_episode.py.

Usage:
    python src/bridge/trajectory_converter.py \\
        --dataset data/circle_grasp_v1 \\
        --episode 0 \\
        --config configs/robot_mapping.yaml
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import yaml


@dataclass(frozen=True)
class JointMapping:
    name: str
    real_field: str
    isaac_name: str
    unit: str
    scale: float
    offset: float
    invert: bool
    isaac_limit_deg: tuple[float, float] | None = None


@dataclass(frozen=True)
class Timestep:
    timestamp: float
    joint_positions: np.ndarray  # radians, shape [5] -- arm joints, Isaac order
    gripper: float               # radians
    action: np.ndarray           # radians, shape [6] -- joint_positions + gripper


def _joint_from_entry(entry: dict[str, Any], name: str | None = None) -> JointMapping:
    limit = entry.get("isaac_limit_deg")
    return JointMapping(
        name=name or entry["name"],
        real_field=entry["real"],
        isaac_name=entry["isaac"],
        unit=entry["unit"],
        scale=float(entry["scale"]),
        offset=float(entry["offset"]),
        invert=bool(entry["invert"]),
        isaac_limit_deg=tuple(limit) if limit else None,
    )


def load_robot_mapping(config_path: str | Path) -> tuple[list[JointMapping], JointMapping]:
    """Parse robot_mapping.yaml. Returns (arm_joints, gripper_joint)."""
    cfg = yaml.safe_load(Path(config_path).read_text())
    arm_joints = [_joint_from_entry(j) for j in cfg["joints"]]
    gripper_joint = _joint_from_entry(cfg["gripper"], name="gripper")
    return arm_joints, gripper_joint


def _load_episode_frames(root: Path, episode_index: int, info: dict) -> dict:
    data_path_tpl = info["data_path"]
    chunk = episode_index // info["chunks_size"]
    data_file = root / data_path_tpl.format(chunk_index=chunk, file_index=0)
    table = pq.read_table(data_file, filters=[("episode_index", "=", episode_index)])
    if table.num_rows == 0:
        raise ValueError(f"Episode {episode_index} not found in {root}")
    return {col: table.column(col).to_pylist() for col in table.schema.names}


def _apply_mapping(real_value: float, joint: JointMapping) -> float:
    """scale -> offset -> invert -> deg2rad.

    Every joint in robot_mapping.yaml (including gripper) targets degrees on
    the Isaac side: USD-authored revolute joint limits are always degrees,
    even though Isaac Sim's runtime articulation API takes radians. See
    docs/current_system.md ("Isaac Sim" section) for how this was verified.
    """
    value_deg = real_value * joint.scale + joint.offset
    if joint.invert:
        value_deg = -value_deg
    return math.radians(value_deg)


def convert_episode(
    dataset_root: str | Path,
    episode_index: int,
    robot_mapping_path: str | Path,
) -> list[Timestep]:
    """Convert one LeRobot episode into a list of normalized Isaac-ready timesteps."""
    root = Path(dataset_root)
    info = json.loads((root / "meta" / "info.json").read_text())
    frames = _load_episode_frames(root, episode_index, info)

    arm_joints, gripper_joint = load_robot_mapping(robot_mapping_path)

    action_names = info["features"]["action"]["names"]
    missing = [j.real_field for j in [*arm_joints, gripper_joint] if j.real_field not in action_names]
    if missing:
        raise ValueError(
            f"robot_mapping.yaml references fields not present in the dataset's "
            f"action names {action_names}: {missing}"
        )
    field_to_col = {name: idx for idx, name in enumerate(action_names)}

    timesteps: list[Timestep] = []
    for i in range(len(frames["timestamp"])):
        action_row = frames["action"][i]

        arm_rad = np.array(
            [_apply_mapping(action_row[field_to_col[j.real_field]], j) for j in arm_joints],
            dtype=np.float32,
        )
        gripper_rad = _apply_mapping(action_row[field_to_col[gripper_joint.real_field]], gripper_joint)
        full_action = np.concatenate([arm_rad, [gripper_rad]]).astype(np.float32)

        timesteps.append(
            Timestep(
                timestamp=float(frames["timestamp"][i]),
                joint_positions=arm_rad,
                gripper=float(gripper_rad),
                action=full_action,
            )
        )

    return timesteps


def _check_limits(timesteps: list[Timestep], arm_joints: list[JointMapping], gripper_joint: JointMapping) -> list[str]:
    """Flag any converted value that falls outside the USD-authored joint limits."""
    warnings: list[str] = []
    all_joints = [*arm_joints, gripper_joint]
    for j_idx, joint in enumerate(all_joints):
        if joint.isaac_limit_deg is None:
            continue
        lo, hi = (math.radians(v) for v in joint.isaac_limit_deg)
        values = np.array([t.action[j_idx] for t in timesteps])
        out_of_range = np.sum((values < lo) | (values > hi))
        if out_of_range:
            warnings.append(
                f"{joint.name}: {out_of_range}/{len(timesteps)} frames outside "
                f"Isaac limit [{lo:.3f}, {hi:.3f}] rad (got [{values.min():.3f}, {values.max():.3f}])"
            )
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to LeRobot dataset root")
    parser.add_argument("--episode", type=int, required=True, help="Episode index to convert")
    parser.add_argument("--config", required=True, help="Path to robot_mapping.yaml")
    args = parser.parse_args()

    arm_joints, gripper_joint = load_robot_mapping(args.config)
    timesteps = convert_episode(args.dataset, args.episode, args.config)

    print(f"Converted episode {args.episode}: {len(timesteps)} frames")
    print(f"\nFirst timestep:")
    print(f"  t={timesteps[0].timestamp:.3f}  action(rad)={timesteps[0].action.tolist()}")
    print(f"Last timestep:")
    print(f"  t={timesteps[-1].timestamp:.3f}  action(rad)={timesteps[-1].action.tolist()}")

    print(f"\nPer-joint range (radians):")
    all_joints = [*arm_joints, gripper_joint]
    for j_idx, joint in enumerate(all_joints):
        values = np.array([t.action[j_idx] for t in timesteps])
        print(f"  {joint.name:<16} [{values.min():>7.3f}, {values.max():>7.3f}]")

    warnings = _check_limits(timesteps, arm_joints, gripper_joint)
    if warnings:
        print(f"\nWARNINGS -- values outside Isaac USD joint limits:")
        for w in warnings:
            print(f"  {w}")
    else:
        print(f"\nAll frames within Isaac USD joint limits.")


if __name__ == "__main__":
    main()
