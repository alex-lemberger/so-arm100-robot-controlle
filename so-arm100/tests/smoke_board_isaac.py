"""Smoke-test add_board/apply_board_variation against a REAL Isaac stage.

tests/test_board_randomization.py covers the pose maths in pure numpy, which runs
anywhere. This covers the half that maths cannot: that the Isaac API calls are
right -- the prim classes exist, take the arguments given, and that set_world_pose
actually lands the board where intended. Guessed-but-unrun Isaac API is exactly
how the camera-capture bug survived a whole session, so verify here before
trusting a change to scene_setup.

Isaac's python.sh launcher swallows stdout, so results go to a file next to it.

    docker run --rm --gpus all -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
        leisaac-sim:latest \
        /workspace/isaaclab/_isaac_sim/python.sh tests/smoke_board_isaac.py
    cat smoke_board_isaac_result.txt
"""
import sys
import traceback
from pathlib import Path

from isaacsim import SimulationApp

LOG = open("smoke_board_isaac_result.txt", "w", buffering=1)


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")


simulation_app = SimulationApp({"headless": True})

ok = False
try:
    import numpy as np
    from isaacsim.core.api import World

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from augmentation.randomization import sample_variation
    from isaac.scene_setup import add_board, apply_board_variation, load_scene_config

    cfg = load_scene_config("configs/simulation.yaml")
    world = World(stage_units_in_meters=1.0)
    components = add_board(world, cfg)
    log(f"add_board returned {len(components)} components")
    world.reset()

    def poses():
        return {h.name: h.get_world_pose()[0].copy() for h, _, _ in components}

    rest = poses()
    log("\n-- at rest --")
    for n, p in rest.items():
        log(f"  {n:24s} {np.round(p, 4)}")

    v = sample_variation(cfg["randomization"], seed=7)
    log(f"\nvariation: dx={v.board_offset_x*1000:+.1f}mm "
        f"dy={v.board_offset_y*1000:+.1f}mm yaw={v.board_yaw_deg:+.2f}deg")
    apply_board_variation(components, cfg["board"], v)
    world.step(render=False)

    moved = poses()
    log("\n-- after apply_board_variation --")
    for n, p in moved.items():
        log(f"  {n:24s} {np.round(p, 4)}  delta={np.round((p - rest[n])*1000, 2)}mm")

    ok = True
    slab_delta = moved["board_slab"] - rest["board_slab"]
    expected = np.array([v.board_offset_x, v.board_offset_y, 0.0])
    slab_ok = np.allclose(slab_delta, expected, atol=1e-5)
    ok &= slab_ok
    log(f"\nslab moved by exactly the sampled offset: {slab_ok}")

    centre = moved["board_slab"]
    rigid = True
    for h, local, _ in components[1:]:
        d_now = float(np.linalg.norm((moved[h.name] - centre)[:2]))
        d_ref = float(np.linalg.norm(local[:2]))
        if abs(d_now - d_ref) > 1e-5:
            rigid = False
            log(f"  RIGIDITY FAIL {h.name}: {d_ref:.5f} -> {d_now:.5f}")
    ok &= rigid
    log(f"all recesses kept their offset from the slab centre: {rigid}")

    log("\nSMOKE TEST " + ("PASSED" if ok else "FAILED"))
except Exception:
    log("EXCEPTION:\n" + traceback.format_exc())
    ok = False

LOG.close()
simulation_app.close()
sys.exit(0 if ok else 1)
