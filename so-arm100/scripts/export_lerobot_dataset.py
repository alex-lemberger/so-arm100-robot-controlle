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
  - Both cameras, each at the real dataset's own resolution. The wrist view was
    dropped originally because rendering it needs a wrist-relative camera whose
    pose tracks forward kinematics per frame; that camera now exists
    (src/isaac/camera_capture.py::create_tracked_camera). Dropping it was the
    single change that most plausibly explains A/B/C's 0/20 -- every policy that
    scored non-zero on this task was trained overview+wrist.
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
    parser.add_argument("--skip-scene-gate", action="store_true",
                        help="render synthetic episodes from a scene that has not been checked "
                             "against reality; recorded in the output's provenance")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    real_episodes = parse_episode_list(args.real_episodes) if args.real_episodes else []
    if not real_episodes and not args.synthetic_dir:
        raise ValueError("Nothing to export: pass --real-episodes and/or --synthetic-dir")

    # Scene gate BEFORE booting Isaac, and only when synthetic frames are actually
    # being rendered -- a real-only export touches no scene. See
    # src/bridge/scene_gate.py for why this is a gate.
    gate_note = "not applicable (real episodes only)"
    if args.synthetic_dir:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from bridge.scene_gate import require_gate  # noqa: E402

        if not args.scene_config:
            raise ValueError("--scene-config is required with --synthetic-dir (the scene gate needs it)")
        gate_note = require_gate(args.scene_config, override=args.skip_scene_gate)
    print(f"scene gate: {gate_note}")

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
    if "observation.images.wrist" not in real_ds.features:
        raise ValueError(
            f"{args.real_dataset} has no observation.images.wrist. Every policy that scored "
            "non-zero on this task used overview+wrist; exporting overview-only is what "
            "produced Datasets A/B/C. Use a source dataset with both cameras."
        )
    wrist_resolution_hw = tuple(real_ds.features["observation.images.wrist"]["shape"][:2])
    joint_names = real_ds.features["action"]["names"]

    ep_meta = {row["episode_index"]: row for row in real_ds.meta.episodes}

    def real_episode_rows(ep_idx: int):
        row = ep_meta[ep_idx]
        return range(row["dataset_from_index"], row["dataset_to_index"])

    # Both cameras. Dropping the wrist view is the single change that most
    # plausibly explains A/B/C's 0/20 -- every policy that ever scored non-zero on
    # this task was trained overview+wrist, and the three that scored nothing were
    # overview-only. Synthetic episodes can carry a wrist view now because the
    # renderer has a camera that tracks the gripper link
    # (src/isaac/camera_capture.py::create_tracked_camera).
    features = {
        "action": {"dtype": "float32", "shape": (6,), "names": joint_names},
        "observation.state": {"dtype": "float32", "shape": (6,), "names": joint_names},
        "observation.images.overview": {
            "dtype": "video",
            "shape": (*resolution_hw, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.images.wrist": {
            "dtype": "video",
            "shape": (*wrist_resolution_hw, 3),
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
            wrist_hwc = row["observation.images.wrist"].permute(1, 2, 0).contiguous()
            dataset.add_frame(
                {
                    "observation.images.overview": image_hwc,
                    "observation.images.wrist": wrist_hwc,
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
        from isaac.camera_capture import (  # noqa: E402
            capture_rgb,
            capture_tracked_rgb,
            create_camera,
            create_tracked_camera,
            warm_up,
        )
        from isaac.replay_loop import settle_to_first_frame  # noqa: E402
        from isaac.scene_setup import (  # noqa: E402
            LIGHT_CONVERGENCE_STEPS,
            apply_lighting_variation,
            apply_variation,
            build_scene,
            load_scene_config,
        )
        from isaacsim.core.utils.types import ArticulationAction
        import omni.replicator.core as rep

        cfg = yaml.safe_load(Path(args.config).read_text())
        usd_path = cfg["isaac_robot"]["asset_path"]
        control_hz = cfg["real_robot"]["control_frequency"]
        arm_joints, gripper_joint = load_robot_mapping(args.config)
        isaac_joint_order = [j.isaac_name for j in [*arm_joints, gripper_joint]]
        scene_cfg = load_scene_config(args.scene_config)

        world = World(stage_units_in_meters=1.0, physics_dt=1.0 / control_hz, rendering_dt=1.0 / control_hz)
        add_reference_to_stage(usd_path=usd_path, prim_path="/World/so_arm100")
        robot = world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
        # build_scene, not add_table_and_object + add_lighting. Until 2026-08-16 this
        # was exactly those two calls and no add_board, so every frame this script has
        # ever rendered showed the peg with nothing to insert it into -- while
        # generate_synthetic.py simulated the same episodes with a board present. The
        # scene gate passed throughout: it renders its own (correct) scene.
        scene = build_scene(world, scene_cfg)
        scene_object, scene_material = scene.object, scene.material
        lights = scene.lights
        # The settle phase is the only thing between a lighting change and the first
        # captured frame, so it has to be long enough for the renderer to converge on
        # the new exposure. At the default 60 it is, by a wide margin -- this guards
        # the case where someone shortens it to speed up an export and silently gets
        # the previous episode's lighting on every episode's opening frames.
        if args.settle_steps < LIGHT_CONVERGENCE_STEPS:
            raise ValueError(
                f"--settle-steps {args.settle_steps} is below LIGHT_CONVERGENCE_STEPS "
                f"({LIGHT_CONVERGENCE_STEPS}); the first frames of each episode would be lit "
                "by the previous episode's variation. See src/isaac/scene_setup.py."
            )
        wrist_cfg = scene_cfg.get("wrist_camera")
        if wrist_cfg is None:
            raise ValueError(
                f"{args.scene_config} has no `wrist_camera` section, so synthetic episodes "
                "cannot carry the wrist view the real ones do."
            )
        camera = create_camera(
            position=scene_cfg["camera"]["position"],
            look_at=scene_cfg["camera"]["target"],
            resolution=(resolution_hw[1], resolution_hw[0]),  # (W, H)
            focal_length=scene_cfg["camera"].get("focal_length"),
        )

        world.reset()
        robot.initialize()
        wrist_camera = create_tracked_camera(
            wrist_cfg["position"],
            wrist_cfg["target"],
            f"/World/so_arm100/{wrist_cfg['parent_link']}",
            (wrist_resolution_hw[1], wrist_resolution_hw[0]),  # (W, H)
            wrist_cfg.get("focal_length"),
        )
        warm_up(world, camera)
        warm_up(world, wrist_camera.camera)
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
            # Lighting is re-applied per episode from the recorded Variation, and is
            # always a scale from the config's base -- never a nudge to the previous
            # episode's value, which would drift the dataset darker or brighter as it
            # went.
            apply_lighting_variation(lights, variation)
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
                wrist_frame = capture_tracked_rgb(wrist_camera)
                real_row = real_ds[rows[t]]
                dataset.add_frame(
                    {
                        "observation.images.overview": frame[:, :, :3],
                        "observation.images.wrist": wrist_frame[:, :, :3],
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
    # provenance.json keeps its existing list-of-episodes shape -- circle_grasp_v1_mixed_10r_100s
    # is already written that way and there is no reason to make old and new datasets
    # disagree. The scene gate goes in its own sidecar instead, so a dataset still
    # records whether the scene it came from had been checked.
    (out_root / "meta" / "provenance.json").write_text(json.dumps(provenance, indent=2))
    (out_root / "meta" / "scene_gate.json").write_text(json.dumps({"scene_gate": gate_note}, indent=2))

    n_real = sum(1 for p in provenance if p["source_type"] == "REAL_HUMAN")
    n_synth = sum(1 for p in provenance if p["source_type"] == "SIM_SYNTHETIC")
    print(f"\nExported {n_real} real + {n_synth} synthetic episodes -> {out_root}")

    simulation_app.close()


if __name__ == "__main__":
    main()
