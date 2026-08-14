"""Geometry and reproducibility checks for board pose randomization.

Pure numpy -- deliberately no Isaac import, so this runs anywhere (the sim image is
only needed to render, not to check the maths). Run:

    docker run --rm -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" lerobot-train:latest \
        python3 tests/test_board_randomization.py
"""

import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from augmentation.randomization import sample_variation  # noqa: E402
from isaac.scene_setup import board_component_pose  # noqa: E402

CFG = yaml.safe_load((ROOT / "configs" / "simulation.yaml").read_text())
IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def test_seeds_reproduce_previous_object_draws():
    """Board draws were appended last so old seeds still give the old object variation."""
    cfg = CFG["randomization"]
    stripped = {k: v for k, v in cfg.items() if not k.startswith("board_")}
    ok = True
    for seed in (0, 1, 42, 12345):
        with_board = sample_variation(cfg, seed=seed)
        without = sample_variation(stripped, seed=seed)
        same = (
            with_board.object_offset_x == without.object_offset_x
            and with_board.object_offset_y == without.object_offset_y
            and with_board.yaw_deg == without.yaw_deg
            and with_board.mass_scale == without.mass_scale
            and with_board.friction_scale == without.friction_scale
            and with_board.robot_joint_noise_deg == without.robot_joint_noise_deg
        )
        ok &= check(f"seed {seed}: object/mass/friction/joints unchanged by adding board", same)
        ok &= check(f"seed {seed}: board actually varies", with_board.board_offset_x != 0.0)
        ok &= check(f"seed {seed}: absent board config -> no board motion", without.board_offset_x == 0.0)
    return ok


def test_sampled_board_pose_within_configured_range():
    cfg = CFG["randomization"]
    xs, ys, yaws = [], [], []
    for seed in range(400):
        v = sample_variation(cfg, seed=seed)
        xs.append(v.board_offset_x); ys.append(v.board_offset_y); yaws.append(v.board_yaw_deg)
    xr, yr = cfg["board_position"]["x"], cfg["board_position"]["y"]
    wr = cfg["board_rotation_deg"]["yaw"]
    ok = check("board x within range", xr[0] <= min(xs) and max(xs) <= xr[1])
    ok &= check("board y within range", yr[0] <= min(ys) and max(ys) <= yr[1])
    ok &= check("board yaw within range", wr[0] <= min(yaws) and max(yaws) <= wr[1])
    # The whole point is that it exceeds the ~19mm real-world displacement seen 08-14.
    ok &= check("range covers the observed 19mm drift with margin", max(abs(xr[0]), xr[1]) >= 0.019,
                f"x range {xr} does not reach 19mm")
    return ok


def test_recesses_stay_on_the_slab_under_yaw():
    """A rotated board must carry its recesses with it -- the failure mode of moving
    the slab alone is recesses sliding off into empty space."""
    board = CFG["board"]
    base_pos = np.array(board["position"], dtype=np.float64)
    base_quat = np.array([1.0, 0.0, 0.0, 0.0])
    size = board["size"]
    local_z = size[2] / 2.0 + 0.001

    class V:
        board_offset_x = 0.0
        board_offset_y = 0.0
        board_yaw_deg = 10.0

    slab_pos, _ = board_component_pose(base_pos, base_quat, np.zeros(3), IDENTITY, V)
    ok = True
    for rec in board["recesses"]:
        local = np.array([rec["offset"][0], rec["offset"][1], local_z])
        pos, _ = board_component_pose(base_pos, base_quat, local, IDENTITY, V)
        # Distance from slab centre must be preserved exactly by a rigid rotation.
        d_before = np.linalg.norm(local[:2])
        d_after = np.linalg.norm((pos - slab_pos)[:2])
        ok &= check(f"recess {rec['id']:9s} keeps its distance from slab centre under yaw",
                    abs(d_before - d_after) < 1e-9, f"{d_before:.6f} vs {d_after:.6f}")
        # And must still lie inside the slab footprint.
        local_after = pos[:2] - slab_pos[:2]
        rot = np.array([[np.cos(np.deg2rad(-10)), -np.sin(np.deg2rad(-10))],
                        [np.sin(np.deg2rad(-10)),  np.cos(np.deg2rad(-10))]])
        unrotated = rot @ local_after
        inside = abs(unrotated[0]) <= size[0] / 2 and abs(unrotated[1]) <= size[1] / 2
        ok &= check(f"recess {rec['id']:9s} stays within the slab footprint", inside)
    return ok


def test_translation_moves_everything_equally():
    board = CFG["board"]
    base_pos = np.array(board["position"], dtype=np.float64)
    base_quat = np.array([1.0, 0.0, 0.0, 0.0])

    class V:
        board_offset_x = 0.02
        board_offset_y = -0.015
        board_yaw_deg = 0.0

    locals_ = [np.zeros(3)] + [np.array([r["offset"][0], r["offset"][1], 0.007]) for r in board["recesses"]]
    deltas = []
    for local in locals_:
        rest, _ = board_component_pose(base_pos, base_quat, local, IDENTITY)
        moved, _ = board_component_pose(base_pos, base_quat, local, IDENTITY, V)
        deltas.append(moved - rest)
    spread = np.abs(np.array(deltas) - deltas[0]).max()
    ok = check("pure translation shifts every component identically", spread < 1e-12)
    ok &= check("translation magnitude is what was asked for",
                np.allclose(deltas[0], [0.02, -0.015, 0.0]))
    return ok


def test_no_variation_is_identity():
    board = CFG["board"]
    base_pos = np.array(board["position"], dtype=np.float64)
    local = np.array([0.05, -0.055, 0.007])
    pos, quat = board_component_pose(base_pos, np.array([1.0, 0.0, 0.0, 0.0]), local, IDENTITY)
    ok = check("variation=None leaves the component at its base pose", np.allclose(pos, base_pos + local))
    ok &= check("variation=None leaves orientation identity", np.allclose(quat, IDENTITY))
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (
        test_seeds_reproduce_previous_object_draws,
        test_sampled_board_pose_within_configured_range,
        test_recesses_stay_on_the_slab_under_yaw,
        test_translation_moves_everything_equally,
        test_no_variation_is_identity,
    ):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
