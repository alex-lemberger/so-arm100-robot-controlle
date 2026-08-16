"""Open the Isaac Sim scene in a window so a human can look at it.

The scene gate's side-by-side is one fixed camera; this is the same scene with a
camera you can fly. Use it to check the things a single render cannot settle --
whether the knobs read at the scale they do in reality, whether the peg sits flat
on the table, whether the empty circle recess is distinguishable from the five
seated pieces.

Builds exactly what scripts/export_lerobot_dataset.py builds: same configs, same
`lighting:`, same board and peg. If it looks wrong here, it is wrong in the data.

    ./view_scene.sh                       # current configs
    ./view_scene.sh --light-scale 0.75    # the dark end of the randomization range

Close the window to exit.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene-config", default=str(ROOT / "configs" / "simulation.yaml"))
    ap.add_argument("--robot-config", default=str(ROOT / "configs" / "robot_mapping.yaml"))
    ap.add_argument("--light-scale", type=float, default=1.0,
                    help="multiply the configured light intensities, e.g. 0.75 or 1.15 "
                         "for the ends of randomization.light_intensity_scale")
    ap.add_argument("--light-yaw", type=float, default=0.0,
                    help="degrees added to the key light's azimuth")
    return ap.parse_args()


args = parse_args()

from isaacsim import SimulationApp  # noqa: E402

simulation_app = SimulationApp({"headless": False})

import yaml  # noqa: E402
from isaacsim.core.api import World  # noqa: E402
from isaacsim.core.api.robots import Robot  # noqa: E402
from isaacsim.core.utils.stage import add_reference_to_stage  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from augmentation.randomization import Variation  # noqa: E402
from isaac.scene_setup import (  # noqa: E402
    apply_lighting_variation,
    build_scene,
    load_scene_config,
)

robot_cfg = yaml.safe_load(Path(args.robot_config).read_text())
scene_cfg = load_scene_config(args.scene_config)

world = World(stage_units_in_meters=1.0, physics_dt=1 / 60, rendering_dt=1 / 60)
add_reference_to_stage(usd_path=robot_cfg["isaac_robot"]["asset_path"], prim_path="/World/so_arm100")
world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
lights = build_scene(world, scene_cfg).lights
world.reset()

if args.light_scale != 1.0 or args.light_yaw != 0.0:
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0,
        light_intensity_scale=args.light_scale, distant_light_yaw_deg=args.light_yaw))

print(f"Scene open. lights: dome {lights.base_dome_intensity} x {args.light_scale}, "
      f"distant {lights.base_distant_intensity} x {args.light_scale}, "
      f"yaw {args.light_yaw:+g} deg. Close the window to exit.")

while simulation_app.is_running():
    world.step(render=True)

simulation_app.close()
