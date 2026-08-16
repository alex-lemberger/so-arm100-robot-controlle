"""Render the board close up from several angles, headless, so a human can look.

`view_scene.sh` needs an X server and a person at the keyboard. This is the same
scene rendered to PNGs instead, which is what you want when checking one specific
piece of geometry -- and what you can do over ssh or from a script.

    ./render_board.sh                       # writes board_views/*.png
    ./render_board.sh --out-dir /tmp/foo --light-scale 0.75

Views: `top` looks straight down at the board, `oblique` is the three-quarter angle
that shows depth, and `grazing` sits almost on the table so the pockets read as
pockets. Between them they answer "is a piece IN the board or ON it", which no
single overhead frame can.

Written 2026-08-16 while cutting the pockets. It immediately earned itself: the
loose peg's knob turned out to be rendering in the peg's own teal rather than
birch (Isaac binds the peg's material `strongerThanDescendants`, which beat the
knob's own binding), and top-down the knob was simply invisible. Every automated
check passed throughout.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VIEWS = {
    # name: (camera offset from the board centre, look-at offset from it)
    "top":     ((0.0, 0.0, 0.42), (0.0, 0.0, 0.0)),
    "oblique": ((0.10, -0.20, 0.22), (0.0, 0.0, 0.006)),
    "grazing": ((-0.02, -0.26, 0.075), (0.0, -0.01, 0.008)),
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene-config", default=str(ROOT / "configs" / "simulation.yaml"))
    ap.add_argument("--out-dir", default=str(ROOT / "board_views"))
    ap.add_argument("--resolution", type=int, default=900)
    ap.add_argument("--focal-length", type=float, default=24.0)
    ap.add_argument("--light-scale", type=float, default=1.0,
                    help="multiply the configured light intensities, e.g. 0.75 or 1.15")
    return ap.parse_args()


args = parse_args()

from isaacsim import SimulationApp  # noqa: E402

simulation_app = SimulationApp({"headless": True})

import omni.replicator.core as rep  # noqa: E402
from isaacsim.core.api import World  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from augmentation.randomization import Variation  # noqa: E402
from isaac.camera_capture import capture_rgb, create_camera, warm_up  # noqa: E402
from isaac.scene_setup import (  # noqa: E402
    LIGHT_CONVERGENCE_STEPS,
    add_board,
    add_lighting,
    add_table_and_object,
    apply_lighting_variation,
    load_scene_config,
)

out_dir = Path(args.out_dir)
out_dir.mkdir(parents=True, exist_ok=True)

scene_cfg = load_scene_config(args.scene_config)
world = World(stage_units_in_meters=1.0, physics_dt=1 / 30, rendering_dt=1 / 30)
add_table_and_object(world, scene_cfg)
add_board(world, scene_cfg)
lights = add_lighting(scene_cfg)
world.reset()

if args.light_scale != 1.0:
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0,
        light_intensity_scale=args.light_scale, distant_light_yaw_deg=0.0))

bx, by, _bz = scene_cfg["board"]["position"]
res = (args.resolution, args.resolution)
cameras = {
    name: create_camera([bx + p[0], by + p[1], p[2]], [bx + t[0], by + t[1], t[2]],
                        res, args.focal_length)
    for name, (p, t) in VIEWS.items()
}
for camera in cameras.values():
    warm_up(world, camera)

# A lighting change takes ~10 rendered frames to appear; burn the same number of
# steps the exporter does rather than capturing a frame lit for the previous state.
for _ in range(LIGHT_CONVERGENCE_STEPS):
    world.step(render=True)
    rep.orchestrator.step(rt_subframes=1)

for name, camera in cameras.items():
    frame = capture_rgb(camera)
    if frame is None or not frame.size:
        print(f"{name}: camera returned no data")
        continue
    path = out_dir / f"board_{name}.png"
    Image.fromarray(frame[:, :, :3]).save(path)
    print(f"wrote {path}")

simulation_app.close()
