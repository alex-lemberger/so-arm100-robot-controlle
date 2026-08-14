"""Export a mixed real + synthetic training dataset in native LeRobot format
(AGENTS_NEW.md Task 18).

Real episodes are read straight from the source LeRobot dataset (already in
the right format). Synthetic episodes are re-simulated in Isaac -- using the
EXACT recorded Variation from their scripts/generate_synthetic.py JSON, not
re-sampled, so this reproduces the physics run that JSON's own validation
stats describe -- this time with the camera rendering enabled (parked/broken
in the 08-11 session, fixed later the same day; see src/isaac/camera_capture.py).

A synthetic episode's action/observation.state are copied verbatim from its
parent real episode's own per-frame values, in the real dataset's own units --
Task 9 deliberately does not re-plan motion (Rule 4), so the parent's
recording IS the correct label for every synthetic frame. Only the rendered
image (and the object's randomized pose/mass/friction driving it) differs.

Scope cuts, both to keep this a "small script" (Rule 2) and because nothing
downstream needs them yet:
  - Overview camera only, at the real dataset's own resolution (drop the
    wrist camera -- rendering it for synthetic episodes would need a second,
    wrist-relative camera whose pose tracks forward kinematics per frame).
  - Provenance is kept as an integer `episode_source_type_id` feature
    (0=REAL_HUMAN, 1=SIM_SYNTHETIC, matching AGENTS_NEW.md Sec 17's source
    types) PLUS a `meta/provenance.json` sidecar with the full detail
    (parent episode, seed, randomization) that LeRobot's own schema has no
    field for. Task 18 says "keep provenance metadata... do not silently
    mix" -- this is how.

Must run under Isaac's bundled Python (has isaacsim, lerobot, pyarrow, PIL
all in one interpreter -- confirmed 2026-08-11):

    /isaac-sim/python.sh scripts/export_lerobot_dataset.py \\
        --real-dataset data/circle_grasp_v1 --real-episodes 0-9 \\
        --synthetic-dir data/synthetic/circle_grasp_v1 --synthetic-episodes all \\
        --config configs/robot_mapping.yaml --scene-config configs/simulation.yaml \\
        --output data/local/datasets/circle_grasp_v1_mixed_10r_100s \\
        --repo-id local/circle_grasp_v1_mixed_10r_100s
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SOURCE_TYPE_ID = {"REAL_HUMAN": 0, "SIM_SYNTHETIC": 1}


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-dataset", required=True, help="Path to the source real LeRobot dataset")
    parser.add_argument("--real-episodes", default="", help='Real episode indices to include, e.g. "0-9" (default: none)')
    parser.add_argument("--synthetic-dir", default=None, help="Path to a scripts/generate_synthetic.py output dir")
    parser.add_argument(
        "--synthetic-episodes",
        default="all",
        help='Synthetic episode indices, e.g. "0-99", or "all" for every status="ok" entry in manifest.json',
    )
    parser.add_argument("--config", required=True, help="robot_mapping.yaml (needed only if --synthetic-dir is set)")
    parser.add_argument("--scene-config", default=None, help="simulation.yaml (needed only if --synthetic-dir is set)")
    parser.add_argument("--settle-steps", type=int, default=60)
    parser.add_argument("--output", required=True, help="Directory to write the merged dataset to")
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--gui", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    real_episodes = parse_episode_list(args.real_episodes) if args.real_episodes else []
    if not real_episodes and not args.synthetic_dir:
        raise ValueError("Nothing to export: pass --real-episodes and/or --synthetic-dir")

    # SimulationApp must exist before any other isaacsim/omni import -- even though
    # real-only exports don't touch Isaac, this script always runs under Isaac's
    # Python (it's the one interpreter with both `lerobot` and `isaacsim`).
    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": not args.gui})

    import numpy as np
    import yaml
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    repo_src = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(repo_src))
    from augmentation.randomization import Variation  # noqa: E402

    real_ds = LeRobotDataset(repo_id="local/real_source", root=args.real_dataset)
    real_image_feature = real_ds.features["observation.images.overview"]
    resolution_hw = tuple(real_image_feature["shape"][:2])  # (H, W) -- match real frames exactly, no resizing
    joint_names = real_ds.features["action"]["names"]

    ep_meta = {row["episode_index"]: row for row in real_ds.meta.episodes}

    def real_episode_rows(ep_idx: int):
        row = ep_meta[ep_idx]
        return range(row["dataset_from_index"], row["dataset_to_index"])

    features = {
        "action": {"dtype": "float32", "shape": (6,), "names": joint_names},
        "observation.state": {"dtype": "float32", "shape": (6,), "names": joint_names},
        "observation.images.overview": {
            "dtype": "video",
            "shape": (*resolution_hw, 3),
            "names": ["height", "width", "channels"],
        },
        "episode_source_type_id": {"dtype": "int64", "shape": (1,), "names": None},
    }

    out_root = Path(args.output)
    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        fps=real_ds.fps,
        features=features,
        root=out_root,
        robot_type=real_ds.meta.robot_type,
    )

    provenance: list[dict] = []

    print(f"Exporting {len(real_episodes)} real episode(s) from {args.real_dataset}")
    for ep_idx in real_episodes:
        for row_idx in real_episode_rows(ep_idx):
            row = real_ds[row_idx]
            # LeRobotDataset's own read path returns images CHW (standard torch image
            # convention); our merged dataset's feature shape follows the source
            # dataset's on-disk convention (HWC, matching robot_learning's precedent
            # in build_lerobot_dataset_v2.py) -- permute back before re-adding.
            image_hwc = row["observation.images.overview"].permute(1, 2, 0).contiguous()
            dataset.add_frame(
                {
                    "observation.images.overview": image_hwc,
                    "observation.state": row["observation.state"],
                    "action": row["action"],
                    "episode_source_type_id": np.array([SOURCE_TYPE_ID["REAL_HUMAN"]], dtype=np.int64),
                    "task": row["task"],
                }
            )
        dataset.save_episode()
        provenance.append({"episode_index": len(provenance), "source_type": "REAL_HUMAN", "real_episode": ep_idx})
        print(f"  real episode {ep_idx}: {len(list(real_episode_rows(ep_idx)))} frames")

    if args.synthetic_dir:
        if not args.scene_config:
            raise ValueError("--scene-config is required when --synthetic-dir is set")

        synth_dir = Path(args.synthetic_dir)
        manifest = json.loads((synth_dir / "manifest.json").read_text())
        if args.synthetic_episodes == "all":
            synth_indices = [m["episode_id"] for m in manifest if m["status"] == "ok"]
        else:
            wanted = set(parse_episode_list(args.synthetic_episodes))
            synth_indices = [m["episode_id"] for m in manifest if m["status"] == "ok" and int(m["episode_id"].split("_")[1]) in wanted]

        print(f"Exporting {len(synth_indices)} synthetic episode(s) from {synth_dir}")

        from isaacsim.core.api import World
        from isaacsim.core.api.robots import Robot
        from isaacsim.core.utils.stage import add_reference_to_stage

        from bridge.trajectory_converter import convert_episode, load_robot_mapping  # noqa: E402
        from isaac.camera_capture import capture_rgb, create_camera, warm_up  # noqa: E402
        from isaac.replay_loop import settle_to_first_frame  # noqa: E402
        from isaac.scene_setup import add_table_and_object, apply_variation, load_scene_config  # noqa: E402
        from isaacsim.core.utils.types import ArticulationAction
        from pxr import UsdLux
        import omni.replicator.core as rep
        import omni.usd

        cfg = yaml.safe_load(Path(args.config).read_text())
        usd_path = cfg["isaac_robot"]["asset_path"]
        control_hz = cfg["real_robot"]["control_frequency"]
        arm_joints, gripper_joint = load_robot_mapping(args.config)
        isaac_joint_order = [j.isaac_name for j in [*arm_joints, gripper_joint]]
        scene_cfg = load_scene_config(args.scene_config)

        world = World(stage_units_in_meters=1.0, physics_dt=1.0 / control_hz, rendering_dt=1.0 / control_hz)
        add_reference_to_stage(usd_path=usd_path, prim_path="/World/so_arm100")
        robot = world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
        scene_object, scene_material = add_table_and_object(world, scene_cfg)

        stage = omni.usd.get_context().get_stage()
        UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(2000)
        distant = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
        distant.CreateIntensityAttr(20000)
        distant.AddRotateXYZOp().Set((-45.0, 30.0, 0.0))
        camera = create_camera(
            position=scene_cfg["camera"]["position"],
            look_at=scene_cfg["camera"]["target"],
            resolution=(resolution_hw[1], resolution_hw[0]),  # (W, H)
        )

        world.reset()
        robot.initialize()
        warm_up(world, camera)
        reorder = np.array([robot.dof_names.index(n) for n in isaac_joint_order])

        parent_cache: dict[int, tuple] = {}  # parent real episode idx -> (rows, timesteps)

        def parent_data(parent_ep: int):
            if parent_ep not in parent_cache:
                rows = list(real_episode_rows(parent_ep))
                timesteps = convert_episode(args.real_dataset, parent_ep, args.config)
                parent_cache[parent_ep] = (rows, timesteps)
            return parent_cache[parent_ep]

        for episode_id in synth_indices:
            record = json.loads((synth_dir / f"{episode_id}.json").read_text())
            parent_ep = int(record["parent_episode"].rsplit("_", 1)[-1])
            rows, timesteps = parent_data(parent_ep)
            variation = Variation(**record["randomization"])

            world.reset()
            apply_variation(scene_object, scene_material, scene_cfg["object"], variation)
            start_pose = np.zeros(len(robot.dof_names), dtype=np.float32)
            start_pose[reorder[:5]] = np.deg2rad(variation.robot_joint_noise_deg)
            robot.set_joint_positions(start_pose)
            settle_to_first_frame(world, robot, reorder, timesteps[0].action, args.settle_steps, render=True)

            n = min(len(timesteps), len(rows))
            for t in range(n):
                target = np.zeros(len(robot.dof_names), dtype=np.float32)
                target[reorder] = timesteps[t].action
                robot.apply_action(ArticulationAction(joint_positions=target))
                world.step(render=True)
                rep.orchestrator.step(rt_subframes=1)

                frame = capture_rgb(camera)
                real_row = real_ds[rows[t]]
                dataset.add_frame(
                    {
                        "observation.images.overview": frame[:, :, :3],
                        "observation.state": real_row["observation.state"],
                        "action": real_row["action"],
                        "episode_source_type_id": np.array([SOURCE_TYPE_ID["SIM_SYNTHETIC"]], dtype=np.int64),
                        "task": real_row["task"],
                    }
                )
            dataset.save_episode()
            provenance.append(
                {
                    "episode_index": len(provenance),
                    "source_type": "SIM_SYNTHETIC",
                    "parent_episode": parent_ep,
                    "seed": record["seed"],
                    "randomization": record["randomization"],
                }
            )
            print(f"  {episode_id} <- real episode {parent_ep}: {n} frames")

    dataset.finalize()
    (out_root / "meta" / "provenance.json").write_text(json.dumps(provenance, indent=2))

    n_real = sum(1 for p in provenance if p["source_type"] == "REAL_HUMAN")
    n_synth = sum(1 for p in provenance if p["source_type"] == "SIM_SYNTHETIC")
    print(f"\nExported {n_real} real + {n_synth} synthetic episodes -> {out_root}")

    simulation_app.close()


if __name__ == "__main__":
    main()
