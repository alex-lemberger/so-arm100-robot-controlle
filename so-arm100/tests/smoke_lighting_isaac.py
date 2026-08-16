"""Prove the lighting jitter axis actually changes the rendered pixels.

`light_intensity_scale` is only worth anything if it survives all the way to the
frames the exporter writes. Sampling the number correctly is what
tests/test_label_preserving_randomization.py checks; this renders the real scene at
the range's ends and asserts the picture responds -- the same reasoning as the
08-11 camera bug, where every individual check passed and the frames were empty.

Writes PNGs to look at as well as asserting numerically. Run:

    ./sim_docker.sh tests/smoke_lighting_isaac.py
"""
import sys
import traceback
from pathlib import Path

from isaacsim import SimulationApp

OUT = Path("lighting_smoke")
LOG = open("smoke_lighting_result.txt", "w", buffering=1)


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")


simulation_app = SimulationApp({"headless": True})
ok = False
try:
    import numpy as np
    import yaml
    from PIL import Image
    from isaacsim.core.api import World
    from isaacsim.core.api.robots import Robot
    from isaacsim.core.utils.stage import add_reference_to_stage

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT / "src"))
    from augmentation.randomization import Variation, sample_variation
    from isaac.camera_capture import capture_rgb, create_camera, warm_up
    from isaac.scene_setup import (
        LIGHT_CONVERGENCE_STEPS,
        build_scene,
        apply_lighting_variation,
        load_scene_config,
    )

    OUT.mkdir(exist_ok=True)
    cfg = yaml.safe_load((ROOT / "configs" / "robot_mapping.yaml").read_text())
    scene_cfg = load_scene_config(str(ROOT / "configs" / "simulation.yaml"))

    world = World(stage_units_in_meters=1.0, physics_dt=1 / 30, rendering_dt=1 / 30)
    add_reference_to_stage(usd_path=cfg["isaac_robot"]["asset_path"], prim_path="/World/so_arm100")
    world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
    lights = build_scene(world, scene_cfg).lights
    log(f"base lighting: dome {lights.base_dome_intensity}, distant "
        f"{lights.base_distant_intensity}, rotation {lights.base_distant_rotation_deg}")

    world.reset()
    camera = create_camera(scene_cfg["camera"]["position"], scene_cfg["camera"]["target"], (640, 480),
                           scene_cfg["camera"].get("focal_length"))
    warm_up(world, camera)

    def shoot(tag, steps=LIGHT_CONVERGENCE_STEPS):
        """Burn `steps` rendered frames before reading. The RTX renderer walks toward a
        new exposure over ~10 frames; measuring after 3 (as this test first did) reads
        a blend of the previous lighting and reports a non-monotonic swing."""
        import omni.replicator.core as rep
        for _ in range(steps):
            world.step(render=True)
            rep.orchestrator.step(rt_subframes=1)
        arr = capture_rgb(camera)
        if arr is None or not arr.size:
            log(f"  {tag}: NO DATA")
            return None
        rgb = arr[:, :, :3]
        Image.fromarray(rgb).save(OUT / f"{tag}.png")
        mean = float(rgb.mean())
        log(f"  {tag}: saved, mean pixel {mean:.2f}")
        return mean

    checks = []

    def check(name, cond, detail=""):
        # detail is the diagnosis, so only print it when there is something to diagnose
        log(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
        checks.append(cond)

    rcfg = scene_cfg["randomization"]
    lo = rcfg["light_intensity_scale"]["min"]
    hi = rcfg["light_intensity_scale"]["max"]

    log("\n-- neutral (scale 1.0, what every dataset before 2026-08-15 was lit at) --")
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0,
        friction_scale=1.0, robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0))
    neutral = shoot("neutral")

    log(f"\n-- darkest (scale {lo}) --")
    dark_v = Variation(object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0,
                       friction_scale=1.0, robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0,
                       light_intensity_scale=lo)
    apply_lighting_variation(lights, dark_v)
    dark = shoot("dark")

    log(f"\n-- brightest (scale {hi}) --")
    bright_v = Variation(object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0,
                         friction_scale=1.0, robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0,
                         light_intensity_scale=hi)
    apply_lighting_variation(lights, bright_v)
    bright = shoot("bright")

    log("\n-- shadow swing (light yaw at both ends, intensity held at 1.0) --")
    yaw_lo, yaw_hi = rcfg["distant_light_yaw_deg"]
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0, distant_light_yaw_deg=yaw_lo))
    yaw_a = shoot("yaw_min")
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0, distant_light_yaw_deg=yaw_hi))
    yaw_b = shoot("yaw_max")

    log("\n-- results --")
    if None in (neutral, dark, bright, yaw_a, yaw_b):
        check("all five frames rendered", False, "at least one capture returned no data")
    else:
        check("all five frames rendered", True)
        check("darkest < neutral", dark < neutral, f"{dark:.2f} vs {neutral:.2f}")
        check("brightest > neutral", bright > neutral, f"{bright:.2f} vs {neutral:.2f}")
        # The point of the axis is to span the ~0.80 workspace darkening measured on
        # rollout_grasp_v1_r1, so the swing has to be visible, not a rounding artifact.
        span = (bright - dark) / max(neutral, 1e-6)
        check("intensity swing is a real spread (>5% of neutral mean)", span > 0.05,
              f"span {span * 100:.1f}% of neutral")
        # Yaw moves shadows, not total exposure -- so the frames must differ from each
        # other while their means stay close. If the means diverge a lot, the light is
        # swinging out of the scene rather than around it.
        diff = float(np.abs(np.array(Image.open(OUT / "yaw_min.png"), dtype=float)
                            - np.array(Image.open(OUT / "yaw_max.png"), dtype=float)).mean())
        check("light yaw changes the image", diff > 0.5, f"mean abs pixel diff {diff:.2f}")
        check("light yaw does not blow out exposure",
              abs(yaw_a - yaw_b) / max(neutral, 1e-6) < 0.25,
              f"{yaw_a:.2f} vs {yaw_b:.2f}")

    log("\n-- the base lighting must leave headroom for the +15% end --")
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0, light_intensity_scale=hi))
    for _ in range(LIGHT_CONVERGENCE_STEPS):
        world.step(render=True)
        __import__("omni.replicator.core", fromlist=["orchestrator"]).orchestrator.step(rt_subframes=1)
    top = capture_rgb(camera)[:, :, :3]
    clipped = float((top >= 250).mean() * 100)
    # The values hard-coded in the exporter until 2026-08-15 clipped 37% of the frame,
    # which is what made this axis a no-op in the first place.
    check("brightest end does not clip the frame (<2% of pixels >=250)", clipped < 2.0,
          f"{clipped:.1f}% clipped")

    log(f"\n-- LIGHT_CONVERGENCE_STEPS ({LIGHT_CONVERGENCE_STEPS}) must still be enough --")
    apply_lighting_variation(lights, Variation(
        object_offset_x=0.0, object_offset_y=0.0, yaw_deg=0.0, mass_scale=1.0, friction_scale=1.0,
        robot_joint_noise_deg=[0.0] * 5, camera_noise_std=0.0, light_intensity_scale=lo))
    settled = shoot("converged_dark")
    extra = shoot("converged_dark_plus", steps=20)
    check("frame is settled by LIGHT_CONVERGENCE_STEPS", abs(settled - extra) < 1.0,
          f"{settled:.2f} then {extra:.2f} after 20 more steps -- raise the constant")

    ok = bool(checks) and all(checks)
    log("\n" + ("ALL PASS" if ok else "FAILED"))
except Exception:
    log("EXCEPTION:\n" + traceback.format_exc())
finally:
    LOG.close()
    simulation_app.close()
sys.exit(0 if ok else 1)
