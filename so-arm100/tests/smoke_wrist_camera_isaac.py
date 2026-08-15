"""Render the overview and wrist views at rest and with the arm moved.

The wrist camera has to track forward kinematics, and the only convincing proof
is a picture: an empty or mis-aimed frame is exactly the failure the 08-11
camera bug produced while every individual check passed. So this writes PNGs to
look at, and also asserts numerically that the camera moved with its link.

    ./sim_docker.sh tests/smoke_wrist_camera_isaac.py
"""
import sys
import traceback
from pathlib import Path

from isaacsim import SimulationApp

OUT = Path("wrist_camera_smoke")
LOG = open("smoke_wrist_camera_result.txt", "w", buffering=1)


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
    from isaacsim.core.utils.types import ArticulationAction

    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT / "src"))
    from isaac.camera_capture import (
        capture_rgb,
        capture_tracked_rgb,
        create_camera,
        create_tracked_camera,
        _world_xform,
        warm_up,
    )
    from isaac.scene_setup import add_board, add_table_and_object, load_scene_config

    OUT.mkdir(exist_ok=True)
    cfg = yaml.safe_load((ROOT / "configs" / "robot_mapping.yaml").read_text())
    scene_cfg = load_scene_config(str(ROOT / "configs" / "simulation.yaml"))

    world = World(stage_units_in_meters=1.0, physics_dt=1 / 30, rendering_dt=1 / 30)
    add_reference_to_stage(usd_path=cfg["isaac_robot"]["asset_path"], prim_path="/World/so_arm100")
    robot = world.scene.add(Robot(prim_path="/World/so_arm100", name="so_arm100"))
    add_table_and_object(world, scene_cfg)
    add_board(world, scene_cfg)

    # so100.usd carries no lights of its own -- without these the RTX render is
    # just black, which is indistinguishable from a mis-aimed camera.
    import omni.usd
    from pxr import Gf, UsdLux
    _stage = omni.usd.get_context().get_stage()
    UsdLux.DomeLight.Define(_stage, "/World/DomeLight").CreateIntensityAttr(1000)
    _distant = UsdLux.DistantLight.Define(_stage, "/World/DistantLight")
    _distant.CreateIntensityAttr(2500)
    _distant.AddRotateXYZOp().Set(Gf.Vec3f(-45.0, 0.0, 45.0))

    world.reset()
    robot.initialize()  # without this the articulation ignores apply_action entirely

    overview = create_camera(scene_cfg["camera"]["position"], scene_cfg["camera"]["target"], (640, 480),
                             scene_cfg["camera"].get("focal_length"))
    wc = scene_cfg["wrist_camera"]
    link = f"/World/so_arm100/{wc['parent_link']}"
    wrist = create_tracked_camera(wc["position"], wc["target"], link, (640, 480),
                                  wc.get("focal_length"))
    log(f"wrist camera attached to {link}")
    warm_up(world, overview)
    warm_up(world, wrist.camera)

    stage = omni.usd.get_context().get_stage()

    def cam_pos():
        return np.array(_world_xform(stage, wrist.camera.prim_path).ExtractTranslation())

    def link_pos():
        from isaac.camera_capture import _link_xform
        return np.array(_link_xform(link).ExtractTranslation())

    def shoot(tag):
        for _ in range(3):
            world.step(render=True)
        import omni.replicator.core as rep
        rep.orchestrator.step(rt_subframes=1)
        o, w = capture_rgb(overview), capture_tracked_rgb(wrist)
        for name, arr in (("overview", o), ("wrist", w)):
            if arr is None or not arr.size:
                log(f"  {tag}/{name}: NO DATA")
                return False
            Image.fromarray(arr[:, :, :3]).save(OUT / f"{tag}_{name}.png")
            log(f"  {tag}/{name}: saved, mean pixel {arr[:, :, :3].mean():.1f}")
        return True

    log("\n-- rest pose --")
    ok = shoot("rest")
    rest_cam, rest_link = cam_pos(), link_pos()
    log(f"  camera world pos {np.round(rest_cam, 4)}   link world pos {np.round(rest_link, 4)}")

    log(f"  joints at rest: {np.round(robot.get_joint_positions(), 4)}")
    log("\n-- arm moved (shoulder_pan +40deg, shoulder_lift -35deg) --")
    target = np.zeros(len(robot.dof_names), dtype=np.float32)
    names = list(robot.dof_names)
    target[names.index("shoulder_pan")] = np.deg2rad(40)
    target[names.index("shoulder_lift")] = np.deg2rad(-35)
    # Teleport rather than drive to the pose. What is under test here is whether
    # the camera follows its link, not whether the position drives converge --
    # apply_action barely moved this articulation (joints drifted toward zero
    # instead of the target), which is a separate drive-tuning question.
    # set_joint_positions is what scripts/export_lerobot_dataset.py uses to place
    # the arm at an episode's start pose anyway.
    import omni.replicator.core as rep
    robot.set_joint_positions(target)
    for _ in range(3):
        world.step(render=True)
        rep.orchestrator.step(rt_subframes=1)
    log(f"  joints after:   {np.round(robot.get_joint_positions(), 4)}")
    log(f"  commanded:      {np.round(target, 4)}")
    ok &= shoot("moved")
    moved_cam, moved_link = cam_pos(), link_pos()
    log(f"  camera world pos {np.round(moved_cam, 4)}   link world pos {np.round(moved_link, 4)}")

    cam_delta = np.linalg.norm(moved_cam - rest_cam)
    link_delta = np.linalg.norm(moved_link - rest_link)
    log(f"\ncamera moved {cam_delta*1000:.1f}mm, link moved {link_delta*1000:.1f}mm")
    moved_enough = cam_delta > 0.02
    ok &= moved_enough
    log(f"camera tracked the link (moved >20mm): {moved_enough}")

    # Rigid attachment: the camera-to-link distance must be identical before/after.
    d_rest = np.linalg.norm(rest_cam - rest_link)
    d_moved = np.linalg.norm(moved_cam - moved_link)
    rigid = abs(d_rest - d_moved) < 1e-4
    ok &= rigid
    log(f"rigid offset preserved: {rigid}  ({d_rest:.5f}m -> {d_moved:.5f}m)")

    log("\nSMOKE TEST " + ("PASSED" if ok else "FAILED"))
except Exception:
    log("EXCEPTION:\n" + traceback.format_exc())
    ok = False

LOG.close()
simulation_app.close()
sys.exit(0 if ok else 1)
