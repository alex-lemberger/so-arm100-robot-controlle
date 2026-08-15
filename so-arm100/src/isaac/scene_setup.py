"""Add a table and one object to the Isaac Sim scene (AGENTS_NEW.md Task 7).

Isaac-specific (Rule 5: keep Isaac code separate from bridge/kinematics code) --
only import this from scripts that already boot Isaac's own Python interpreter.

See configs/simulation.yaml for why "table" is a thin static slab at z=0 rather
than a raised platform, and for where the object dimensions/position came from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple


def load_scene_config(config_path: str | Path) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(Path(config_path).read_text())


def _xyzw_to_wxyz(q: list[float]) -> list[float]:
    """configs/simulation.yaml stores rotations as (x, y, z, w) (USD/ROS convention,
    matching AGENTS_NEW.md Sec 14's example). Isaac's core-API object constructors
    take (w, x, y, z) -- same scalar-first trap already documented for the replay
    camera quaternion in scripts/replay_episode.py."""
    x, y, z, w = q
    return [w, x, y, z]


def _quat_multiply_wxyz(q1, q2):
    """Hamilton product, both operands (w, x, y, z). Rotates q2 by q1 (q1 applied second
    in world space, i.e. result = q1 * q2)."""
    import numpy as np

    w1, x1, y1, z1 = q1
    w2, x2, y2, z2 = q2
    return np.array(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


# Rendered frames needed after a lighting change before the RTX renderer settles on
# the new exposure. MEASURED 2026-08-15: after setting the intensity attribute the
# frame mean walks from the old value to the new one over ~10 frames (at scale 0.75
# it went 163.6 -> 149.5 and was still moving at frame 8), even though the USD
# attribute reads back the new value immediately. Anything that changes the lighting
# and then captures must burn at least this many rendered steps first, or the opening
# frames of each episode carry the PREVIOUS episode's lighting -- an artifact
# correlated with episode order, which is the worst kind.
LIGHT_CONVERGENCE_STEPS = 15


class SceneLights(NamedTuple):
    """Handles for re-tuning the scene lights per synthetic episode without
    redefining the prims. Base values are captured at creation so a variation is
    always a scale/offset from the approved scene, never a compounding drift."""

    dome_intensity_attr: Any
    distant_intensity_attr: Any
    distant_rotate_op: Any
    base_dome_intensity: float
    base_distant_intensity: float
    base_distant_rotation_deg: tuple[float, float, float]


def _rotate_xyz_op(xformable):
    """Reuse the prim's existing rotateXYZ op if it has one. AddRotateXYZOp() raises
    on a prim that already carries the op, which is exactly what happens when a stage
    is re-opened or a light is defined twice in one process."""
    from pxr import UsdGeom

    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeRotateXYZ:
            return op
    return xformable.AddRotateXYZOp()


def add_lighting(scene_cfg: dict[str, Any]) -> SceneLights:
    """Define the scene's dome + distant lights from `scene_cfg["lighting"]`.

    Lived inline in scripts/export_lerobot_dataset.py until 2026-08-15, with the
    intensities hard-coded. It moved here so the values are configurable and, more
    to the point, so they can be randomized per episode -- lighting is one of the
    few axes that is genuinely label-preserving under verbatim action copying (it
    changes the pixels and nothing about where anything is).

    The fallback defaults below are the OLD hard-coded numbers, deliberately: a config
    with no `lighting:` section reproduces pre-2026-08-15 frames exactly. They are not
    good values -- they clip 37% of the frame at 255 (see configs/simulation.yaml,
    which sets far lower ones). They exist so old behaviour is reproducible, not so it
    is recommended.

    Only call this from a script that has already booted Isaac's interpreter.
    """
    import omni.usd
    from pxr import UsdGeom, UsdLux

    cfg = scene_cfg.get("lighting", {})
    dome_intensity = float(cfg.get("dome_intensity", 2000.0))
    distant_intensity = float(cfg.get("distant_intensity", 20000.0))
    distant_rotation = tuple(float(v) for v in cfg.get("distant_rotation_deg", [-45.0, 30.0, 0.0]))

    stage = omni.usd.get_context().get_stage()
    dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
    distant = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
    rotate_op = _rotate_xyz_op(UsdGeom.Xformable(distant.GetPrim()))
    rotate_op.Set(distant_rotation)

    return SceneLights(
        dome_intensity_attr=dome.CreateIntensityAttr(dome_intensity),
        distant_intensity_attr=distant.CreateIntensityAttr(distant_intensity),
        distant_rotate_op=rotate_op,
        base_dome_intensity=dome_intensity,
        base_distant_intensity=distant_intensity,
        base_distant_rotation_deg=distant_rotation,
    )


def apply_lighting_variation(lights: SceneLights, variation) -> None:
    """Scale both lights' intensity and swing the distant light's azimuth, per
    `augmentation.randomization.Variation`. Label-preserving: it changes only how
    the scene is lit, so the parent episode's copied actions stay exactly correct.

    Reads the variation's light fields with getattr defaults, because episode JSON
    written before 2026-08-15 has no light fields at all -- those records must
    re-export at the original baseline lighting, not crash or drift.

    The change is NOT visible in the next rendered frame: burn `LIGHT_CONVERGENCE_STEPS`
    rendered steps before capturing anything.
    """
    scale = float(getattr(variation, "light_intensity_scale", 1.0))
    yaw = float(getattr(variation, "distant_light_yaw_deg", 0.0))

    lights.dome_intensity_attr.Set(lights.base_dome_intensity * scale)
    lights.distant_intensity_attr.Set(lights.base_distant_intensity * scale)
    rx, ry, rz = lights.base_distant_rotation_deg
    lights.distant_rotate_op.Set((rx, ry, rz + yaw))


def _knob_dims(scene_cfg: dict[str, Any]) -> tuple[float, float, list[float]]:
    knob_cfg = scene_cfg.get("knob", {})
    return (
        float(knob_cfg.get("radius", 0.0065)),
        float(knob_cfg.get("height", 0.013)),
        list(knob_cfg.get("color", [0.93, 0.90, 0.84])),
    )


def _attach_knob(parent_prim_path: str, radius: float, height: float, color: list[float], z_offset: float):
    """Add a knob cylinder as a CHILD of `parent_prim_path`.

    Child, not a sibling, so it inherits the parent's transform -- a knob added as
    its own world-space prim would stay behind the moment the peg is nudged, and
    the peg is a dynamic body.

    Deliberately visual-only: no CollisionAPI. Motion is replayed rather than
    re-planned (Rule 4), so giving the knob a collider would change the replay's
    contact dynamics -- a real decision about how the sim behaves, separate from
    making it look right, and not one to smuggle in with a rendering fix.
    """
    import omni.usd
    from pxr import Gf, UsdGeom

    stage = omni.usd.get_context().get_stage()
    knob = UsdGeom.Cylinder.Define(stage, f"{parent_prim_path}/knob")
    knob.CreateRadiusAttr(radius)
    knob.CreateHeightAttr(height)
    knob.CreateAxisAttr("Z")
    knob.CreateExtentAttr([(-radius, -radius, -height / 2), (radius, radius, height / 2)])
    knob.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    UsdGeom.Xformable(knob).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, z_offset))
    return knob


def add_table_and_object(world, scene_cfg: dict[str, Any]):
    """Add the table (static) and one object (dynamic rigid body) to `world.scene`,
    plus a physics material on the object so friction can be re-tuned per synthetic
    episode without recreating the material prim each time (see `apply_variation`).

    Must be called before `world.reset()`, same as the robot articulation.
    Returns (object_handle, material_handle).
    """
    import numpy as np
    from isaacsim.core.api.materials import PhysicsMaterial
    from isaacsim.core.api.objects import DynamicCylinder, FixedCuboid

    table_cfg = scene_cfg["table"]
    world.scene.add(
        FixedCuboid(
            prim_path="/World/table",
            name="table",
            position=np.array(table_cfg["position"], dtype=np.float32),
            scale=np.array(table_cfg["size"], dtype=np.float32),
            color=np.array(table_cfg.get("color", [0.8, 0.8, 0.8]), dtype=np.float32),
        )
    )

    obj_cfg = scene_cfg["object"]
    if obj_cfg["shape"] != "cylinder":
        raise NotImplementedError(f"Only 'cylinder' objects supported so far, got {obj_cfg['shape']!r}")

    obj = world.scene.add(
        DynamicCylinder(
            prim_path=f"/World/{obj_cfg['id']}",
            name=obj_cfg["id"],
            position=np.array(obj_cfg["position"], dtype=np.float32),
            orientation=np.array(_xyzw_to_wxyz(obj_cfg.get("rotation", [0.0, 0.0, 0.0, 1.0])), dtype=np.float32),
            radius=obj_cfg["radius"],
            height=obj_cfg["height"],
            mass=obj_cfg.get("mass", 0.05),
            color=np.array(obj_cfg.get("color", [0.5, 0.5, 0.5]), dtype=np.float32),
        )
    )

    # The knob the gripper actually closes on. See `knob:` in configs/simulation.yaml.
    knob_r, knob_h, knob_color = _knob_dims(scene_cfg)
    _attach_knob(f"/World/{obj_cfg['id']}", knob_r, knob_h, knob_color,
                 z_offset=obj_cfg["height"] / 2.0 + knob_h / 2.0)

    base_friction = obj_cfg.get("base_friction", 0.5)
    material = PhysicsMaterial(
        prim_path=f"/World/{obj_cfg['id']}/physics_material",
        static_friction=base_friction,
        dynamic_friction=base_friction,
    )
    obj.apply_physics_material(material)

    return obj, material


def apply_variation(obj, material, object_cfg: dict[str, Any], variation) -> None:
    """Apply a sampled `augmentation.randomization.Variation` to an already-added
    scene object: offset position, rotate about Z by `yaw_deg`, and rescale mass/
    friction from `object_cfg`'s base values. Used by scripts/generate_synthetic.py
    once per synthetic episode -- does not recreate any prim, just moves/retunes the
    existing one, so it's safe to call repeatedly in a loop.
    """
    import numpy as np

    base_pos = np.array(object_cfg["position"], dtype=np.float64)
    new_pos = base_pos + np.array([variation.object_offset_x, variation.object_offset_y, 0.0])

    base_quat_wxyz = np.array(_xyzw_to_wxyz(object_cfg.get("rotation", [0.0, 0.0, 0.0, 1.0])))
    yaw_rad = np.deg2rad(variation.yaw_deg)
    yaw_quat_wxyz = np.array([np.cos(yaw_rad / 2), 0.0, 0.0, np.sin(yaw_rad / 2)])
    new_quat_wxyz = _quat_multiply_wxyz(yaw_quat_wxyz, base_quat_wxyz)

    obj.set_world_pose(position=new_pos.astype(np.float32), orientation=new_quat_wxyz.astype(np.float32))

    base_mass = object_cfg.get("mass", 0.05)
    obj.set_mass(base_mass * variation.mass_scale)

    base_friction = object_cfg.get("base_friction", 0.5)
    friction = base_friction * variation.friction_scale
    material.set_static_friction(friction)
    material.set_dynamic_friction(friction)


def _yaw_quat_wxyz(yaw_deg: float):
    """Rotation of `yaw_deg` about +Z, as (w, x, y, z)."""
    import numpy as np

    half = np.deg2rad(yaw_deg) / 2.0
    return np.array([np.cos(half), 0.0, 0.0, np.sin(half)])


def _rotate_vec_wxyz(v, q):
    """Rotate vector `v` by quaternion `q` (w, x, y, z), via v + 2w(u x v) + 2(u x (u x v))."""
    import numpy as np

    v = np.asarray(v, dtype=np.float64)
    w, u = q[0], np.asarray(q[1:], dtype=np.float64)
    t = np.cross(u, v)
    return v + 2.0 * w * t + 2.0 * np.cross(u, t)


def board_component_pose(board_base_pos, board_base_quat_wxyz, local_offset, local_quat_wxyz, variation=None):
    """World pose of one board component under a per-episode board variation.

    The board is several prims (the slab plus one visual disc/plate per recess) that
    must move as one rigid body. Rather than parent them under an Xform and move
    that -- which would mean a second, unexercised Isaac API on the critical path --
    each component's world pose is composed here analytically. Pure numpy, no Isaac
    import, so the geometry is unit-testable on any machine.

    `local_offset` is the component's position in the BOARD's own frame; it gets
    rotated by the board's total orientation so that recesses stay put on the slab
    as it yaws, instead of sliding off it.
    """
    import numpy as np

    base_pos = np.asarray(board_base_pos, dtype=np.float64)
    # Normalised on the way in: a hand-written quaternion in the config (0.7071
    # rather than 0.70710678) is not quite unit-length, and rotating an offset by it
    # rescales the board slightly -- small, but it silently moves every recess.
    base_quat = np.asarray(board_base_quat_wxyz, dtype=np.float64)
    base_quat = base_quat / np.linalg.norm(base_quat)

    if variation is None:
        total_quat = base_quat
        offset = np.zeros(3)
    else:
        total_quat = _quat_multiply_wxyz(_yaw_quat_wxyz(variation.board_yaw_deg), base_quat)
        offset = np.array([variation.board_offset_x, variation.board_offset_y, 0.0])

    world_pos = base_pos + _rotate_vec_wxyz(local_offset, total_quat) + offset
    world_quat = _quat_multiply_wxyz(total_quat, np.asarray(local_quat_wxyz, dtype=np.float64))
    return world_pos, world_quat


def _regular_polygon_verts(sides: int, side_length: float, apex_up: bool = True):
    """Vertices of a regular N-gon, centred on its circumcentre, in the board's own
    2D frame. `apex_up` puts a vertex at +y, which is how docs/reference/toy.png
    draws both the triangle and the pentagon.

    Circumradius from side length: R = s / (2 sin(pi/N)). Cross-checked against the
    drawing: side 52 triangle -> 52.0 wide x 45.0 tall (measured 51.5 x 45.2);
    side 32 pentagon -> 51.8 x 49.2 (measured 51.1 x 50.0).
    """
    import numpy as np

    radius = side_length / (2.0 * np.sin(np.pi / sides))
    start = np.pi / 2 if apex_up else 0.0
    angles = start + np.arange(sides) * 2.0 * np.pi / sides
    return np.stack([radius * np.cos(angles), radius * np.sin(angles)], axis=1)


def _rect_verts(width: float, height: float):
    import numpy as np

    hw, hh = width / 2.0, height / 2.0
    return np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]], dtype=np.float64)


def _rhombus_verts(width: float, height: float):
    """A rhombus is NOT a rotated square. toy.png's diamond states side 42mm and is
    drawn 45.9 wide x 68.5 tall -- markedly taller than wide. It was modelled as a
    39mm square at yaw 45 until 2026-08-15, i.e. 55mm x 55mm: too narrow and far too
    short. Diagonals are given directly here so the shape cannot drift back."""
    import numpy as np

    hw, hh = width / 2.0, height / 2.0
    return np.array([[0.0, -hh], [hw, 0.0], [0.0, hh], [-hw, 0.0]], dtype=np.float64)


def recess_verts(rec: dict[str, Any]):
    """2D outline for a recess spec, or None for a circle (which stays an analytic
    cylinder rather than a polygon approximation)."""
    shape = rec["shape"]
    if shape == "circle":
        return None
    if shape == "polygon":
        return _regular_polygon_verts(int(rec["sides"]), float(rec["side"]))
    if shape == "rect":
        return _rect_verts(*rec["size"])
    if shape == "rhombus":
        return _rhombus_verts(*rec["size"])
    raise NotImplementedError(f"Unsupported recess shape {shape!r} for {rec['id']!r}")


def _prism_mesh(stage, path: str, verts_2d, thickness: float, color):
    """Extrude a 2D outline into a flat prism as a UsdGeom.Mesh.

    A mesh rather than a scaled primitive on purpose. The recesses were VisualCuboids
    whose `scale` was the shape's size -- and USD scale is inherited by children, so
    the knob parented under a 46mm x 46mm x 2mm piece was squashed by those same
    factors and vanished. That is why the square, rectangle and diamond had no knobs
    while the two cylinder-based recesses did. Mesh points carry the dimensions, the
    prim keeps unit scale, and children stay the size they were built.
    """
    from pxr import Gf, UsdGeom, Vt

    n = len(verts_2d)
    hz = thickness / 2.0
    points = [Gf.Vec3f(float(x), float(y), -hz) for x, y in verts_2d]
    points += [Gf.Vec3f(float(x), float(y), +hz) for x, y in verts_2d]

    counts = [n, n]
    indices = list(range(n - 1, -1, -1))          # bottom, reversed so it faces -z
    indices += list(range(n, 2 * n))              # top
    for i in range(n):                            # side quads
        j = (i + 1) % n
        counts.append(4)
        indices += [i, j, j + n, i + n]

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray(points))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(indices))
    mesh.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*color)]))
    mesh.CreateSubdivisionSchemeAttr("none")      # else it renders as a blob
    xs = [v[0] for v in verts_2d]; ys = [v[1] for v in verts_2d]
    mesh.CreateExtentAttr([(min(xs), min(ys), -hz), (max(xs), max(ys), hz)])
    return mesh


def _disc_geom(stage, path: str, radius: float, thickness: float, color):
    from pxr import Gf, UsdGeom

    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(thickness)
    cyl.CreateAxisAttr("Z")
    cyl.CreateExtentAttr([(-radius, -radius, -thickness / 2), (radius, radius, thickness / 2)])
    cyl.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return cyl


def add_board(world, scene_cfg: dict[str, Any]):
    """Add the shape-sorter board -- slab, one visual marker per recess, and a knob
    on each recess whose piece is SEATED (`filled: true`) -- to `world.scene`. Returns a list of (handle, local_offset, local_quat_wxyz) for
    `apply_board_variation`, or None if the config has no `board` section (older
    configs stay valid and simply have no board).

    Recesses are Visual* prims: no collider, because motion is replayed rather than
    re-planned (Rule 4) so nothing is ever actually inserted, and a collider there
    would only risk spurious contacts with the replayed peg.

    Must be called before `world.reset()`, same as the robot and the table.
    """
    import numpy as np
    import omni.usd
    from isaacsim.core.api.objects import FixedCuboid
    from isaacsim.core.prims import SingleXFormPrim

    stage = omni.usd.get_context().get_stage()
    board_cfg = scene_cfg.get("board")
    if board_cfg is None:
        return None

    base_pos = np.array(board_cfg["position"], dtype=np.float64)
    base_quat = np.array(_xyzw_to_wxyz(board_cfg.get("rotation", [0.0, 0.0, 0.0, 1.0])))
    size = board_cfg["size"]
    identity = np.array([1.0, 0.0, 0.0, 0.0])

    components: list[tuple[Any, Any, Any]] = []

    slab_pos, slab_quat = board_component_pose(base_pos, base_quat, np.zeros(3), identity)
    slab = world.scene.add(
        FixedCuboid(
            prim_path="/World/board_slab",
            name="board_slab",
            position=slab_pos.astype(np.float32),
            orientation=slab_quat.astype(np.float32),
            scale=np.array(size, dtype=np.float32),
            color=np.array(board_cfg.get("color", [0.85, 0.72, 0.50]), dtype=np.float32),
        )
    )
    components.append((slab, np.zeros(3), identity))

    disc_thickness = 0.002
    local_z = size[2] / 2.0 + disc_thickness / 2.0  # sits on the slab's top face
    knob_r, knob_h, knob_color = _knob_dims(scene_cfg)

    for rec in board_cfg.get("recesses", []):
        local_offset = np.array([rec["offset"][0], rec["offset"][1], local_z], dtype=np.float64)
        local_quat = _yaw_quat_wxyz(rec.get("yaw_deg", 0.0))
        pos, quat = board_component_pose(base_pos, base_quat, local_offset, local_quat)
        filled = rec.get("filled", True)
        color = list(rec.get("color", [0.5, 0.5, 0.5]))
        if not filled:
            # An empty recess is a painted floor sitting in shadow, not a piece
            # standing on the surface. Darkening it is what stops the insertion
            # TARGET from reading as a sixth seated piece.
            color = [c * 0.65 for c in color]

        # An Xform wrapper carrying the geometry as a child. The wrapper keeps unit
        # scale so the knob parented under it is not squashed (see _prism_mesh), and
        # SingleXFormPrim gives apply_board_variation the set_world_pose it needs.
        prim_path = f"/World/board_recess_{rec['id']}"
        handle = SingleXFormPrim(
            prim_path=prim_path,
            name=f"board_recess_{rec['id']}",
            position=pos.astype(np.float32),
            orientation=quat.astype(np.float32),
        )
        verts = recess_verts(rec)
        if verts is None:
            _disc_geom(stage, f"{prim_path}/geom", rec["radius"], disc_thickness, color)
        else:
            _prism_mesh(stage, f"{prim_path}/geom", verts, disc_thickness, color)
        components.append((handle, local_offset, local_quat))

        # A SEATED piece carries a knob; an empty recess is a bare painted floor.
        # That difference is the only thing marking the insertion target apart from
        # the five distractors, so it is the last thing to leave out.
        if filled:
            _attach_knob(prim_path, knob_r, knob_h, knob_color,
                         z_offset=disc_thickness / 2.0 + knob_h / 2.0)

    return components


def apply_board_variation(board_components, board_cfg: dict[str, Any], variation) -> None:
    """Move the whole board -- slab and every recess together -- to the pose sampled
    for this synthetic episode. No-op when the scene has no board.

    This is the axis the real demonstrations never varied (measured drift across
    circle_insert_50ep: ~2.5mm), and therefore the one a policy trained on them alone
    cannot handle. See docs/replan-2026-08-14-camera-confound.md.
    """
    import numpy as np

    if not board_components:
        return

    base_pos = np.array(board_cfg["position"], dtype=np.float64)
    base_quat = np.array(_xyzw_to_wxyz(board_cfg.get("rotation", [0.0, 0.0, 0.0, 1.0])))

    for handle, local_offset, local_quat in board_components:
        pos, quat = board_component_pose(base_pos, base_quat, local_offset, local_quat, variation)
        handle.set_world_pose(position=pos.astype(np.float32), orientation=quat.astype(np.float32))
