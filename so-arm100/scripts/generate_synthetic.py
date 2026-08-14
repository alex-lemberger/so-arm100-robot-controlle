"""Generate synthetic episode variations from real demonstrations by domain-randomizing
object pose/mass/friction and the robot's initial joint pose, then replaying the SAME
commanded joint trajectory as the parent real episode through Isaac's physics-driven
articulation (AGENTS_NEW.md Task 9 / Sec 16-17).

This does NOT re-plan motion -- Stage 1 is deliberately naive (Rule 4: don't implement
later phases before earlier ones are proven, and Sec 16: "do not begin with extreme
randomization"). The commanded action trajectory is copied verbatim from the parent
episode; only the *scene* (and where the robot starts from) is randomized, producing
physically-varied object states paired with the same action labels.

Camera pixel noise is sampled and recorded in provenance for completeness, but not
applied -- --capture-dir rendering is a known-unresolved bug (see
docs/linux-session-handover-2026-08-11.md), not worth blocking this on per Rule 4.

Boots Isaac ONCE and loops over all synthetic episodes in-process (world.reset() between
each) rather than one Isaac boot per episode -- the ~10-14s Kit startup would otherwise
dominate wall-clock time for a run of 100.

Must run under Isaac's bundled Python, same as scripts/replay_episode.py:

    /isaac-sim/python.sh scripts/generate_synthetic.py \\
        --dataset data/circle_grasp_v1 \\
        --parent-episodes 0-9 \\
        --config configs/robot_mapping.yaml \\
        --scene-config configs/simulation.yaml \\
        --num-synthetic 100 \\
        --seed 0
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def parse_episode_list(spec: str) -> list[int]:
    """"0-9" -> [0..9]; "0,2,5" -> [0,2,5]; "0-2,7" -> [0,1,2,7]."""
    result: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(part))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to the real LeRobot dataset (parents)")
    parser.add_argument("--parent-episodes", required=True, help='Real episode indices to draw from, e.g. "0-9"')
    parser.add_argument("--config", required=True, help="Path to robot_mapping.yaml")
    parser.add_argument("--scene-config", required=True, help="Path to simulation.yaml (needs a randomization: section)")
    parser.add_argument("--num-synthetic", type=int, default=100, help="AGENTS_NEW.md Task 9: 10 real -> 100 synthetic")
    parser.add_argument("--seed", type=int, default=0, help="Base seed; episode seed = seed*100000 + index (Rule 10)")
    parser.add_argument("--settle-steps", type=int, default=60)
    parser.add_argument("--out-dir", default=None, help="default: data/synthetic/<dataset name>")
    parser.add_argument("--gui", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parent_episodes = parse_episode_list(args.parent_episodes)
    out_dir = Path(args.out_dir or f"data/synthetic/{Path(args.dataset).name}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # SimulationApp must exist before any other isaacsim/omni import.
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": not args.gui})

    import numpy as np
    import yaml
    from isaacsim.core.api import World
    from isaacsim.core.api.robots import Robot
    from isaacsim.core.utils.stage import add_reference_to_stage

    repo_src = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(repo_src))
    from augmentation.randomization import sample_variation  # noqa: E402
    from bridge.trajectory_converter import convert_episode, load_robot_mapping  # noqa: E402
    from bridge.validation import validate_replay  # noqa: E402
    from isaac.replay_loop import run_replay, settle_to_first_frame  # noqa: E402
    from isaac.scene_setup import (  # noqa: E402
        add_board,
        add_table_and_object,
        apply_board_variation,
        apply_variation,
        load_scene_config,
    )

    cfg = yaml.safe_load(Path(args.config).read_text())
    usd_path = cfg["isaac_robot"]["asset_path"]
    control_hz = cfg["real_robot"]["control_frequency"]
    arm_joints, gripper_joint = load_robot_mapping(args.config)
    isaac_joint_order = [j.isaac_name for j in [*arm_joints, gripper_joint]]

    scene_cfg = load_scene_config(args.scene_config)
    if "randomization" not in scene_cfg:
        raise ValueError(f"{args.scene_config} has no 'randomization' section (AGENTS_NEW.md Sec 16)")

    print(f"Loading USD: {usd_path}")
    world = World(stage_units_in_meters=1.0, physics_dt=1.0 / control_hz, rendering_dt=1.0 / control_hz)
    add_reference_to_stage(usd_path=usd_path, prim_path="/World/so_arm100")
    robot = world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
    scene_object, scene_material = add_table_and_object(world, scene_cfg)
    board_components = add_board(world, scene_cfg)

    world.reset()
    robot.initialize()
    print("Isaac DOF order:", robot.dof_names)
    missing = [n for n in isaac_joint_order if n not in robot.dof_names]
    if missing:
        raise RuntimeError(f"robot_mapping.yaml names not found among Isaac DOFs {robot.dof_names}: {missing}")
    # robot_mapping.yaml order may not match Isaac's internal DOF order -- reindex explicitly
    # rather than assuming they line up (Rule 6: no hard-coded joint mapping).
    reorder = np.array([robot.dof_names.index(n) for n in isaac_joint_order])

    print(f"Converting {len(parent_episodes)} parent episode(s) from {args.dataset}: {parent_episodes}")
    parent_trajectories = {ep: convert_episode(args.dataset, ep, args.config) for ep in parent_episodes}

    manifest = []
    for i in range(args.num_synthetic):
        parent_ep = parent_episodes[i % len(parent_episodes)]
        timesteps = parent_trajectories[parent_ep]
        episode_seed = args.seed * 100_000 + i
        episode_id = f"synthetic_{i:04d}"

        try:
            variation = sample_variation(scene_cfg["randomization"], seed=episode_seed)

            world.reset()
            apply_variation(scene_object, scene_material, scene_cfg["object"], variation)
            if board_components:
                apply_board_variation(board_components, scene_cfg["board"], variation)

            # Randomize where the arm starts from (Sec 16's "robot initial joint
            # position"), then settle to frame 0 as usual -- this perturbs the
            # transient approach, not the measured trajectory itself (Rule 4: not
            # re-planning motion at this stage).
            start_pose = np.zeros(len(robot.dof_names), dtype=np.float32)
            start_pose[reorder[:5]] = np.deg2rad(variation.robot_joint_noise_deg)
            robot.set_joint_positions(start_pose)

            settle_err = settle_to_first_frame(world, robot, reorder, timesteps[0].action, args.settle_steps)
            commanded_log, actual_log = run_replay(world, robot, reorder, timesteps)
            result = validate_replay(commanded_log, actual_log)

            obj_pos, _ = scene_object.get_world_pose()

            record = {
                "episode_id": episode_id,
                "source_type": "SIM_SYNTHETIC",
                "parent_episode": f"{Path(args.dataset).name}/episode_{parent_ep}",
                "seed": episode_seed,
                "randomization": variation.as_dict(),
                "object_final_pose": obj_pos.tolist(),
                "settle_error_rad": settle_err,
                "validation": result,
                "commanded_joint_positions_rad": commanded_log.tolist(),
                "actual_joint_positions_rad": actual_log.tolist(),
            }
            (out_dir / f"{episode_id}.json").write_text(json.dumps(record, indent=2))
            manifest.append(
                {
                    "episode_id": episode_id,
                    "parent_episode": parent_ep,
                    "seed": episode_seed,
                    "mean_ee_error_m": result["mean_ee_error_m"],
                    "status": "ok",
                }
            )
            print(
                f"[{i + 1}/{args.num_synthetic}] {episode_id} <- parent {parent_ep}: "
                f"mean EE error {result['mean_ee_error_m'] * 1000:.2f}mm, "
                f"obj offset ({variation.object_offset_x * 1000:.1f}, {variation.object_offset_y * 1000:.1f})mm "
                f"board ({variation.board_offset_x * 1000:+.1f}, {variation.board_offset_y * 1000:+.1f})mm "
                f"{variation.board_yaw_deg:+.1f}deg"
            )
        except Exception as exc:  # noqa: BLE001 -- isolate one bad randomized sample from the whole batch
            manifest.append(
                {
                    "episode_id": episode_id,
                    "parent_episode": parent_ep,
                    "seed": episode_seed,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            print(f"[{i + 1}/{args.num_synthetic}] {episode_id} FAILED: {exc}")
            traceback.print_exc()

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    n_ok = sum(1 for m in manifest if m["status"] == "ok")
    print(f"\nGenerated {n_ok}/{args.num_synthetic} synthetic episodes -> {out_dir}")

    simulation_app.close()


if __name__ == "__main__":
    main()
