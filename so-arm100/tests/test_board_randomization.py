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


def _without_board(cfg):
    """`cfg` as it looked before board randomization existed (2026-08-14)."""
    breaking = {k: v for k, v in cfg.get("label_breaking", {}).items() if not k.startswith("board_")}
    return {**cfg, "label_breaking": breaking}


def test_seeds_reproduce_previous_object_draws():
    """Board draws were appended last so old seeds still give the old object variation."""
    cfg = CFG["randomization"]
    stripped = _without_board(cfg)
    ok = True
    for seed in (0, 1, 42, 12345):
        with_board = sample_variation(cfg, seed=seed, allow_label_breaking=True)
        without = sample_variation(stripped, seed=seed, allow_label_breaking=True)
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
        v = sample_variation(cfg, seed=seed, allow_label_breaking=True)
        xs.append(v.board_offset_x); ys.append(v.board_offset_y); yaws.append(v.board_yaw_deg)
    breaking = cfg["label_breaking"]
    xr, yr = breaking["board_position"]["x"], breaking["board_position"]["y"]
    wr = breaking["board_rotation_deg"]["yaw"]
    ok = check("board x within range", xr[0] <= min(xs) and max(xs) <= xr[1])
    ok &= check("board y within range", yr[0] <= min(ys) and max(ys) <= yr[1])
    ok &= check("board yaw within range", wr[0] <= min(yaws) and max(yaws) <= wr[1])
    # The whole point is that it exceeds the ~19mm real-world displacement seen 08-14.
    ok &= check("range covers the observed 19mm drift with margin", max(abs(xr[0]), xr[1]) >= 0.019,
                f"x range {xr} does not reach 19mm")
    return ok


def test_recesses_stay_on_the_slab_under_yaw():
    """A rotated board must carry its recesses with it -- the failure mode of moving
    the slab alone is recesses sliding off into empty space.

    Uses the board's REAL configured base rotation (currently -90 deg about Z, the
    offset between docs/reference/toy.png's orientation and how the board sits in
    the overview frame), not an assumed identity, so the check covers the geometry
    actually shipped.
    """
    from isaac.scene_setup import _quat_multiply_wxyz, _rotate_vec_wxyz, _yaw_quat_wxyz

    board = CFG["board"]
    base_pos = np.array(board["position"], dtype=np.float64)
    bx, by, bz, bw = board.get("rotation", [0.0, 0.0, 0.0, 1.0])
    base_quat = np.array([bw, bx, by, bz])
    size = board["size"]
    local_z = size[2] / 2.0 + 0.001

    class V:
        board_offset_x = 0.0
        board_offset_y = 0.0
        board_yaw_deg = 10.0

    slab_pos, _ = board_component_pose(base_pos, base_quat, np.zeros(3), IDENTITY, V)
    total = _quat_multiply_wxyz(_yaw_quat_wxyz(V.board_yaw_deg), base_quat)
    conj = np.array([total[0], -total[1], -total[2], -total[3]])

    ok = True
    for rec in board["recesses"]:
        local = np.array([rec["offset"][0], rec["offset"][1], local_z])
        pos, _ = board_component_pose(base_pos, base_quat, local, IDENTITY, V)
        d_before = np.linalg.norm(local[:2])
        d_after = np.linalg.norm((pos - slab_pos)[:2])
        ok &= check(f"recess {rec['id']:9s} keeps its distance from slab centre under yaw",
                    abs(d_before - d_after) < 1e-9, f"{d_before:.6f} vs {d_after:.6f}")
        # Undo the board's total rotation and confirm it lands back inside the slab.
        unrotated = _rotate_vec_wxyz(pos - slab_pos, conj)
        inside = abs(unrotated[0]) <= size[0] / 2 and abs(unrotated[1]) <= size[1] / 2
        ok &= check(f"recess {rec['id']:9s} stays within the slab footprint", inside,
                    f"local {np.round(unrotated[:2], 4)} vs half-extent "
                    f"{[size[0]/2, size[1]/2]}")
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


def test_peg_does_not_intersect_the_board():
    """The peg must spawn clear of the board slab.

    This is a real bug that appeared the moment the board position was measured:
    the peg's long-standing [0.18, -0.05] guess landed inside the newly-measured
    footprint and overlapped it in z, which would spawn the two interpenetrating.
    Both positions are independent estimates of the same physical setup, so they
    can drift apart again -- hence a guard rather than a one-off fix.
    """
    board, obj = CFG["board"], CFG["object"]
    bx, by, bz = board["position"]
    hx, hy, hz = [v / 2 for v in board["size"]]
    px, py, pz = obj["position"]
    r, h = obj["radius"], obj["height"]

    xy_clear = (
        px + r < bx - hx or px - r > bx + hx
        or py + r < by - hy or py - r > by + hy
    )
    z_clear = (pz + h / 2 < bz - hz) or (pz - h / 2 > bz + hz)
    ok = check("peg spawns clear of the board (in xy or above/below it)",
               xy_clear or z_clear,
               f"peg ({px}, {py}) r={r} vs board x[{bx-hx:.3f},{bx+hx:.3f}] "
               f"y[{by-hy:.3f},{by+hy:.3f}]")
    reach = (px**2 + py**2) ** 0.5
    ok &= check(f"peg still within arm reach ({reach:.3f}m)", 0.10 < reach < 0.32)
    return ok


def test_peg_matches_the_circle_recess():
    """The loose peg IS the circle piece -- board_reference_demo.png shows five
    pieces seated and the circle recess empty, with its piece on the table. So the
    peg's radius must equal the circle recess's, and both must equal the drawing's
    50mm. They were independently 0.02 and 0.025 until 2026-08-15, i.e. the sim
    showed a peg that could not have come out of the hole it is inserted into.
    """
    obj = CFG["object"]
    circle = next(r for r in CFG["board"]["recesses"] if r["id"] == "circle")
    ok = check("peg radius == circle recess radius", obj["radius"] == circle["radius"],
               f"{obj['radius']} vs {circle['radius']}")
    ok &= check("both are the drawing's 50mm diameter", obj["radius"] == 0.025,
                f"radius {obj['radius']}")
    # Pieces are the board's own thickness -- they sit flush in the recess.
    ok &= check("peg is the board's thickness", abs(obj["height"] - CFG["board"]["size"][2]) < 1e-9,
                f"peg h {obj['height']} vs board {CFG['board']['size'][2]}")
    # And it has to rest ON the table, not sunk into it or hovering.
    table_top = CFG["table"]["position"][2] + CFG["table"]["size"][2] / 2
    ok &= check("peg rests on the table top", abs(obj["position"][2] - (table_top + obj["height"] / 2)) < 1e-9,
                f"z {obj['position'][2]}, expected {table_top + obj['height'] / 2}")
    return ok


def test_knob_matches_the_drawing():
    """The knob is what the gripper closes on, so its size is not cosmetic: it sets
    how wide the jaws have to be. docs/reference/toy.png dimensions it at 13mm across
    and 13mm tall."""
    knob = CFG["knob"]
    ok = check("knob is 13mm across", abs(knob["radius"] * 2 - 0.013) < 1e-9, f"{knob['radius'] * 2}")
    ok &= check("knob is 13mm tall", abs(knob["height"] - 0.013) < 1e-9, f"{knob['height']}")
    # Much narrower than the piece it stands on -- that contrast is the whole point.
    ok &= check("knob is far narrower than the peg", knob["radius"] < CFG["object"]["radius"] / 2)
    return ok


def test_exactly_one_recess_is_empty_and_it_is_the_target():
    """Five seated pieces carry knobs; the circle recess is empty. That difference is
    the only thing distinguishing the insertion target from five distractors, and the
    sim drew all six the same until 2026-08-15."""
    recesses = CFG["board"]["recesses"]
    empty = [r["id"] for r in recesses if not r.get("filled", True)]
    ok = check("exactly one recess is empty", len(empty) == 1, f"empty: {empty}")
    ok &= check("the empty one is the circle", empty == ["circle"], f"empty: {empty}")
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (
        test_seeds_reproduce_previous_object_draws,
        test_sampled_board_pose_within_configured_range,
        test_recesses_stay_on_the_slab_under_yaw,
        test_translation_moves_everything_equally,
        test_no_variation_is_identity,
        test_peg_does_not_intersect_the_board,
        test_peg_matches_the_circle_recess,
        test_knob_matches_the_drawing,
        test_exactly_one_recess_is_empty_and_it_is_the_target,
    ):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
