"""Replay one LeRobot episode in Isaac Sim.

Applies converted joint targets frame-by-frame through the physics-based
position drives already configured in the USD (stiffness/damping/maxForce),
so the arm moves the way it will during real synthetic-data replay -- not a
teleport of raw joint state.

Core replay (joint targets -> physics -> tracking-error readback) is verified
working end-to-end against circle_grasp_v1 episode 0. --capture-dir (optional
per AGENTS_NEW.md Sec 11) now works too -- see src/isaac/camera_capture.py for
what was actually wrong (hand-derived look-at math, not the render binding).

Must be run with Isaac Sim's bundled Python (has isaacsim, pyyaml, pyarrow,
numpy, PIL all in one interpreter):

    /isaac-sim/python.sh scripts/replay_episode.py \\
        --dataset data/circle_grasp_v1 \\
        --episode 0 \\
        --config configs/robot_mapping.yaml \\
        --capture-dir data/evaluation/replay_000_frames

No plain `python3 scripts/replay_episode.py` -- this script needs the Kit
app process, which only isaacsim's own interpreter can boot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to LeRobot dataset root")
    parser.add_argument("--episode", type=int, required=True, help="Episode index to replay")
    parser.add_argument("--config", required=True, help="Path to robot_mapping.yaml")
    parser.add_argument("--gui", action="store_true", help="Open the Isaac Sim window instead of running headless")
    parser.add_argument("--loop", action="store_true", help="Loop the replay until interrupted")
    parser.add_argument("--max-frames", type=int, default=None, help="Only replay the first N frames (debugging)")
    parser.add_argument(
        "--settle-steps",
        type=int,
        default=60,
        help="Steps to hold frame-0's target before measured replay starts, so the arm converges "
        "from the USD's zero pose to episode's actual starting pose first. Without this, tracking "
        "error is dominated by a cold-start transient rather than in-episode tracking quality. Set 0 to disable.",
    )
    parser.add_argument(
        "--capture-dir",
        default=None,
        help="If set, save periodic PNG frames from a fixed camera here (headless has no live view otherwise)",
    )
    parser.add_argument("--capture-every", type=int, default=30, help="Save one frame every N simulation steps")
    parser.add_argument(
        "--validation-out",
        default=None,
        help="Path to write the replay validation JSON "
        "(default: data/evaluation/replay_episode_<NNN>.json, per AGENTS_NEW.md Sec 12)",
    )
    parser.add_argument(
        "--scene-config",
        default=None,
        help="If set, add a table + one object per this YAML (configs/simulation.yaml) "
        "before replay (AGENTS_NEW.md Task 7). Off by default so it can't perturb the "
        "already-validated bare-robot joint replay.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

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
    from bridge.trajectory_converter import convert_episode, load_robot_mapping  # noqa: E402
    from bridge.validation import validate_replay, save_validation_result  # noqa: E402
    from isaac.scene_setup import add_lighting, build_scene, load_scene_config  # noqa: E402
    from isaac.replay_loop import run_replay, settle_to_first_frame  # noqa: E402
    from isaac.camera_capture import capture_rgb, create_camera, warm_up  # noqa: E402

    cfg = yaml.safe_load(Path(args.config).read_text())
    usd_path = cfg["isaac_robot"]["asset_path"]
    control_hz = cfg["real_robot"]["control_frequency"]

    arm_joints, gripper_joint = load_robot_mapping(args.config)
    isaac_joint_order = [j.isaac_name for j in [*arm_joints, gripper_joint]]

    print(f"Loading USD: {usd_path}")
    world = World(stage_units_in_meters=1.0, physics_dt=1.0 / control_hz, rendering_dt=1.0 / control_hz)
    add_reference_to_stage(usd_path=usd_path, prim_path="/World/so_arm100")
    robot = world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))

    scene_object = None
    scene_cfg: dict = {}   # stays empty without --scene-config; add_lighting then uses its defaults
    scene = None
    if args.scene_config:
        # THE scene, board included. Before 2026-08-16 this built the table and the peg
        # only, so a replay validated against a workspace with no insertion target in
        # it -- and the board is a collider, which is exactly the thing a replay ought
        # to be validated against.
        print(f"Adding the scene from {args.scene_config}")
        scene_cfg = load_scene_config(args.scene_config)
        scene = build_scene(world, scene_cfg)
        scene_object = scene.object

    camera = None
    if args.capture_dir:
        # so100.usd has no lights of its own -- without one the RTX render is just black.
        # RTX physically-based lighting needs much higher intensity (thousands of nits)
        # than a typical "reasonable-sounding" value to produce visible exposure.
        # Values live in the scene config's `lighting:` section (see scene_setup.py);
        # the numbers that used to be inline here are that section's defaults.
        # build_scene already defined them when --scene-config was given; without it
        # there is no scene config at all and add_lighting falls back to its defaults.
        if scene is None:
            add_lighting(scene_cfg)

        out_dir = Path(args.capture_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        camera = create_camera(position=(0.5, -0.5, 0.5), look_at=(0.0, 0.0, 0.1), resolution=(640, 480))

    world.reset()
    robot.initialize()
    if scene_object is not None:
        obj_pos, _ = scene_object.get_world_pose()
        print(f"Scene object '{scene_object.name}' initial pose: {obj_pos}")
    if camera is not None:
        warm_up(world, camera)

    print("Isaac DOF order: ", robot.dof_names)
    missing = [n for n in isaac_joint_order if n not in robot.dof_names]
    if missing:
        raise RuntimeError(
            f"robot_mapping.yaml names not found among Isaac DOFs {robot.dof_names}: {missing}"
        )
    # robot_mapping.yaml order may not match Isaac's internal DOF order -- reindex explicitly
    # rather than assuming they line up (Rule 6: no hard-coded joint mapping).
    reorder = np.array([robot.dof_names.index(n) for n in isaac_joint_order])

    print(f"Converting episode {args.episode} from {args.dataset}")
    timesteps = convert_episode(args.dataset, args.episode, args.config)
    if args.max_frames:
        timesteps = timesteps[: args.max_frames]
    print(f"{len(timesteps)} frames to replay at {control_hz} Hz")

    if args.settle_steps > 0:
        # The USD resets the arm to its zero pose, which can be ~100deg away from
        # episode's actual first frame on some joints. Without this, tracking error
        # is dominated by that one-time cold-start transient rather than by how well
        # Isaac's PD drives track the recording once caught up.
        print(f"Settling to frame 0's pose for {args.settle_steps} steps before measured replay...")
        settle_err = settle_to_first_frame(
            world, robot, reorder, timesteps[0].action, args.settle_steps, render=args.gui or camera is not None
        )
        print(f"  post-settle joint error vs frame 0: {settle_err:.4f} rad")

    def capture_frame(step_idx: int) -> None:
        if camera is None or step_idx % args.capture_every != 0:
            return
        frame = capture_rgb(camera)
        if frame is not None:
            print(
                f"  capture step {step_idx}: shape={frame.shape} dtype={frame.dtype} "
                f"min={frame.min()} max={frame.max()} mean={frame.mean():.3f}"
            )
            from PIL import Image

            rgb = frame[:, :, :3]
            if rgb.dtype != np.uint8:
                rgb = (np.clip(rgb, 0.0, 1.0) * 255).astype(np.uint8)
            Image.fromarray(rgb).save(out_dir / f"frame_{step_idx:05d}.png")
        else:
            print(f"  capture step {step_idx}: frame is empty, shape={None if frame is None else frame.shape}")

    def run_once() -> tuple[np.ndarray, np.ndarray]:
        return run_replay(
            world,
            robot,
            reorder,
            timesteps,
            render=args.gui or camera is not None,
            frame_callback=capture_frame if camera is not None else None,
        )

    if args.loop:
        print("Looping replay -- Ctrl+C to stop.")
        while simulation_app.is_running():
            commanded_log, actual_log = run_once()
            result = validate_replay(commanded_log, actual_log)
            print(
                f"  loop pass done: mean_joint_error={result['mean_joint_error_rad']:.4f} rad, "
                f"mean_ee_error={result['mean_ee_error_m']*1000:.1f} mm"
            )
    else:
        commanded_log, actual_log = run_once()
        result = validate_replay(commanded_log, actual_log)

        validation_out = args.validation_out or f"data/evaluation/replay_episode_{args.episode:03d}.json"
        save_validation_result(result, validation_out)

        print(f"\nReplay validation ({result['num_frames']} frames):")
        print(f"  mean joint error: {result['mean_joint_error_rad']:.4f} rad")
        print(f"  max joint error:  {result['max_joint_error_rad']:.4f} rad")
        print(f"  mean EE error:    {result['mean_ee_error_m']*1000:.2f} mm")
        print(f"  max EE error:     {result['max_ee_error_m']*1000:.2f} mm")
        print(f"  (AGENTS_NEW.md Sec 10 target: <10mm mean EE error)")
        print(f"Saved: {validation_out}")

        if scene_object is not None:
            obj_pos, _ = scene_object.get_world_pose()
            print(f"Scene object '{scene_object.name}' final pose: {obj_pos} (untouched if not grasped)")

    if camera is not None:
        print(f"Saved capture frames to {out_dir}")

    simulation_app.close()


if __name__ == "__main__":
    main()
