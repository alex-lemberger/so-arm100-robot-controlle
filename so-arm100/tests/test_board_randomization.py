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
from isaac.scene_setup import (  # noqa: E402
    board_component_pose,
    piece_verts,
    pocket_cells,
    recess_outline,
    recess_verts,
)

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
    board = CFG["board"]
    circle = next(r for r in board["recesses"] if r["id"] == "circle")
    clearance = board["piece_clearance"]
    ok = check("peg radius == circle recess radius - clearance",
               abs(obj["radius"] - (circle["radius"] - clearance)) < 1e-9,
               f"{obj['radius']} vs {circle['radius']} - {clearance}")
    ok &= check("the recess is the drawing's 50mm diameter", circle["radius"] == 0.025,
                f"radius {circle['radius']}")
    # And the peg is the 46mm PIECE drawn inside it, not the recess itself. It was
    # 50mm until 2026-08-16: a peg that exactly filled the hole it comes out of.
    ok &= check("the peg is the drawing's 46mm piece", abs(obj["radius"] * 2 - 0.046) < 1e-9,
                f"diameter {obj['radius'] * 2}")
    # Pieces are the board's own thickness -- deeper than the recess, so they stand proud.
    ok &= check("peg is the board's thickness", abs(obj["height"] - board["size"][2]) < 1e-9,
                f"peg h {obj['height']} vs board {board['size'][2]}")
    ok &= check("peg thickness == the seated pieces' thickness",
                abs(obj["height"] - board["piece_thickness"]) < 1e-9,
                f"{obj['height']} vs {board['piece_thickness']}")
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


def test_recess_shapes_match_the_drawing():
    """Every stated dimension in docs/reference/toy.png, checked against the geometry
    actually built. `triangle` and `pentagon` were `shape: cylinder` placeholders
    until 2026-08-15 -- the two shapes were simply not in the scene."""
    by_id = {r["id"]: r for r in CFG["board"]["recesses"]}
    ok = check("no placeholder shapes left",
               not any(r["shape"] in ("cylinder", "cuboid") for r in by_id.values()),
               f"{[(r['id'], r['shape']) for r in by_id.values() if r['shape'] in ('cylinder', 'cuboid')]}")

    tri = recess_verts(by_id["triangle"])
    sides = [np.linalg.norm(tri[i] - tri[(i + 1) % 3]) for i in range(3)]
    ok &= check("triangle has 3 vertices", len(tri) == 3)
    ok &= check("triangle side is the drawing's 52mm", all(abs(s - 0.052) < 1e-6 for s in sides),
                f"sides {np.round(sides, 4)}")

    pent = recess_verts(by_id["pentagon"])
    psides = [np.linalg.norm(pent[i] - pent[(i + 1) % 5]) for i in range(5)]
    ok &= check("pentagon has 5 vertices", len(pent) == 5)
    ok &= check("pentagon side is the drawing's 32mm", all(abs(s - 0.032) < 1e-6 for s in psides),
                f"sides {np.round(psides, 4)}")

    rh = recess_verts(by_id["diamond"])
    rsides = [np.linalg.norm(rh[i] - rh[(i + 1) % 4]) for i in range(4)]
    w = rh[:, 0].max() - rh[:, 0].min()
    h = rh[:, 1].max() - rh[:, 1].min()
    ok &= check("rhombus side is the drawing's 42mm", all(abs(s - 0.042) < 5e-4 for s in rsides),
                f"sides {np.round(rsides, 4)}")
    # The specific complaint: it was a rotated square, 55x55mm. It must be TALLER.
    ok &= check("rhombus is taller than it is wide", h > w * 1.3, f"{w * 1000:.1f} wide x {h * 1000:.1f} tall")

    for name, expect in (("rectangle", (0.043, 0.063)), ("square", (0.046, 0.046))):
        v = recess_verts(by_id[name])
        got = (v[:, 0].max() - v[:, 0].min(), v[:, 1].max() - v[:, 1].min())
        ok &= check(f"{name} is {expect[0]*1000:.0f} x {expect[1]*1000:.0f} mm",
                    all(abs(g - e) < 1e-6 for g, e in zip(got, expect)), f"got {np.round(got, 4)}")
    return ok


def test_every_recess_fits_on_the_slab():
    """A shape whose real outline runs off the slab is a modelling error the old
    radius-only checks could not see."""
    size = CFG["board"]["size"]
    ok = True
    for rec in CFG["board"]["recesses"]:
        v = recess_verts(rec)
        if v is None:
            hw = hh = rec["radius"]
        else:
            hw = max(abs(v[:, 0].min()), v[:, 0].max())
            hh = max(abs(v[:, 1].min()), v[:, 1].max())
        ox, oy = rec["offset"]
        inside = abs(ox) + hw <= size[0] / 2 and abs(oy) + hh <= size[1] / 2
        ok &= check(f"{rec['id']:9s} fits within the slab", inside,
                    f"reaches x {abs(ox) + hw:.4f}, y {abs(oy) + hh:.4f} vs half-extent "
                    f"{size[0] / 2:.4f}, {size[1] / 2:.4f}")
    return ok


def test_recesses_do_not_overlap_each_other():
    """Bounding-box separation. Catches a mistyped offset, which is otherwise only
    visible by rendering and looking."""
    recs = CFG["board"]["recesses"]
    boxes = {}
    for rec in recs:
        v = recess_verts(rec)
        hw, hh = (rec["radius"], rec["radius"]) if v is None else (
            max(abs(v[:, 0].min()), v[:, 0].max()), max(abs(v[:, 1].min()), v[:, 1].max()))
        ox, oy = rec["offset"]
        boxes[rec["id"]] = (ox - hw, ox + hw, oy - hh, oy + hh)
    ok = True
    ids = list(boxes)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = boxes[ids[i]], boxes[ids[j]]
            sep = a[1] <= b[0] or b[1] <= a[0] or a[3] <= b[2] or b[3] <= a[2]
            ok &= check(f"{ids[i]} and {ids[j]} do not overlap", sep)
    return ok


def test_pieces_are_inset_from_their_recesses():
    """A piece is not the size of its recess.

    toy.png draws every shape as a double outline and dimensions the OUTER one
    ("recess side 46mm"); the inner line is the piece, 2.0mm inside it on every shape
    the drawing can be read cleanly on. The sim had them identical until 2026-08-16 --
    which is a piece that cannot be lifted out of its own hole, and, once the recess
    became a real pocket, z-fighting stripes down the pocket wall.

    The inset is checked edge by edge, not by bounding box: scaling a rhombus about
    its centre insets its long flanks less than its short ones, and a bbox check
    cannot see the difference.
    """
    clearance = CFG["board"]["piece_clearance"]
    ok = check("clearance is the drawing's 2mm", abs(clearance - 0.002) < 1e-9, f"{clearance}")
    for rec in CFG["board"]["recesses"]:
        outer = recess_verts(rec)
        inner = piece_verts(rec, clearance)
        if outer is None:                      # the circle: analytic, not a polygon
            ok &= check("circle piece is the recess less the clearance", inner is None)
            continue
        gaps = []
        for i in range(len(outer)):
            e = outer[(i + 1) % len(outer)] - outer[i]
            n = np.array([-e[1], e[0]]) / np.linalg.norm(e)     # inward, CCW winding
            gaps.append(min(float(np.dot(n, v - outer[i])) for v in inner))
        ok &= check(f"{rec['id']:9s} piece sits {clearance*1000:.0f}mm inside every recess edge",
                    all(abs(g - clearance) < 1e-9 for g in gaps),
                    f"edge gaps mm {np.round(np.array(gaps) * 1000, 3)}")
    return ok


def test_seated_pieces_stand_proud_of_the_board():
    """A seated piece rests on its pocket floor, so its thickness minus the recess
    depth is how far it stands above the birch -- 4mm on these numbers, which is what
    board_reference_demo.png shows. Until 2026-08-16 the pieces were 2mm plates lying
    ON an unbroken slab, so this quantity did not exist."""
    board = CFG["board"]
    depth, thickness, slab = board["recess_depth"], board["piece_thickness"], board["size"][2]
    proud = thickness - depth
    ok = check("the pocket is shallower than the piece is thick", proud > 0,
               f"depth {depth}, piece {thickness}")
    ok &= check("seated pieces stand 4mm proud", abs(proud - 0.004) < 1e-9, f"{proud * 1000:.1f}mm")
    ok &= check("the pocket does not cut through the slab", depth < slab,
                f"depth {depth} vs slab {slab}")
    # Where add_board puts the piece: centred on (slab_top - depth + thickness/2).
    local_z = slab / 2.0 - depth + thickness / 2.0
    ok &= check("piece bottom rests exactly on the pocket floor",
                abs((local_z - thickness / 2.0) - (slab / 2.0 - depth)) < 1e-12)
    ok &= check("piece top stands above the board's top face", local_z + thickness / 2.0 > slab / 2.0)
    return ok


def test_every_recess_gets_its_own_pocket_cell():
    """The slab's top face is cut into one rectangular cell per pocket, and each cell
    is tiled as a ring around its own hole (src/isaac/scene_setup.py). If two pockets
    landed in one cell the mesh would be built wrong, so the partition is checked here
    rather than discovered in a render.

    Note this board has NO global grid: the diamond hangs below y=0 and the square
    reaches above it, so the cut has to be columns-first, rows within each column.
    """
    board = CFG["board"]
    recesses = board["recesses"]
    size = board["size"]
    boxes = []
    for rec in recesses:
        v = recess_outline(rec) + np.array(rec["offset"], dtype=np.float64)
        boxes.append((v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max()))

    cells = pocket_cells(size, boxes, names=[r["id"] for r in recesses])
    ok = check("one cell per recess", len(cells) == len(recesses) and all(c is not None for c in cells))

    for rec, cell, box in zip(recesses, cells, boxes):
        x0, x1, y0, y1 = cell
        ok &= check(f"{rec['id']:9s} pocket lies strictly inside its cell",
                    x0 < box[0] and box[1] < x1 and y0 < box[2] and box[3] < y1,
                    f"pocket {np.round(box, 4)} vs cell {np.round(cell, 4)}")

    # Cells must tile the slab: disjoint interiors, and their areas summing to the face.
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            a, b = cells[i], cells[j]
            disjoint = a[1] <= b[0] or b[1] <= a[0] or a[3] <= b[2] or b[3] <= a[2]
            ok &= check(f"cells for {recesses[i]['id']} and {recesses[j]['id']} do not overlap",
                        disjoint, f"{np.round(a, 4)} vs {np.round(b, 4)}")
    area = sum((c[1] - c[0]) * (c[3] - c[2]) for c in cells)
    ok &= check("cells cover the whole top face", abs(area - size[0] * size[1]) < 1e-12,
                f"{area:.6f} vs {size[0] * size[1]:.6f}")
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
        test_recess_shapes_match_the_drawing,
        test_every_recess_fits_on_the_slab,
        test_recesses_do_not_overlap_each_other,
        test_pieces_are_inset_from_their_recesses,
        test_seated_pieces_stand_proud_of_the_board,
        test_every_recess_gets_its_own_pocket_cell,
    ):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
