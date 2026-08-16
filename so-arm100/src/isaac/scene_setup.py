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

    The colour is bound as a material, not left to displayColor. displayColor is
    enough on the board's pieces, which are raw meshes, but the loose peg is an
    Isaac `DynamicCylinder` and Isaac binds a material to it for its `color:` --
    and a material binding is INHERITED by children, where displayColor is not. So
    the peg's knob rendered in the peg's own teal (2026-08-16: found by rendering
    the peg close up and looking at it -- top-down it vanished into the piece
    entirely). On the real board every knob is bare birch, and the contrast is the
    point: the knob is what the gripper closes on.

    Binding a material on the knob is not enough on its own, either: Isaac binds
    the peg's with `strongerThanDescendants`, which beats anything a child binds.
    So the parent's binding is weakened here first. That only lets descendants
    override it -- the peg keeps its own colour.
    """
    import omni.usd
    from pxr import Gf, UsdGeom, UsdShade

    stage = omni.usd.get_context().get_stage()
    knob = UsdGeom.Cylinder.Define(stage, f"{parent_prim_path}/knob")
    knob.CreateRadiusAttr(radius)
    knob.CreateHeightAttr(height)
    knob.CreateAxisAttr("Z")
    knob.CreateExtentAttr([(-radius, -radius, -height / 2), (radius, radius, height / 2)])
    knob.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    UsdGeom.Xformable(knob).AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, z_offset))

    parent_rel = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(parent_prim_path)).GetDirectBindingRel()
    if parent_rel and parent_rel.GetTargets():
        UsdShade.MaterialBindingAPI.SetMaterialBindingStrength(
            parent_rel, UsdShade.Tokens.weakerThanDescendants)
    _bind_color_material(stage, knob.GetPrim(), f"{parent_prim_path}/knob/material", color)
    return knob


def _bind_color_material(stage, prim, material_path: str, color):
    """Bind a flat UsdPreviewSurface of `color` to `prim`, overriding anything an
    ancestor binds. See `_attach_knob` for why a bound material rather than
    displayColor."""
    from pxr import Gf, Sdf, UsdShade

    material = UsdShade.Material.Define(stage, material_path)
    shader = UsdShade.Shader.Define(stage, f"{material_path}/shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.7)   # matte, like wood
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")

    binding = UsdShade.MaterialBindingAPI.Apply(prim)
    binding.Bind(material)
    return material


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


def recess_outline(rec: dict[str, Any], segments: int = 48):
    """The recess's outline as an explicit polygon, circles included.

    `recess_verts` returns None for a circle so the piece can stay an analytic
    cylinder. The POCKET cut into the slab is a mesh either way, so it needs the
    circle as vertices -- sampled densely enough to read as round.
    """
    import numpy as np

    verts = recess_verts(rec)
    if verts is not None:
        return verts
    ang = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    r = float(rec["radius"])
    return np.stack([r * np.cos(ang), r * np.sin(ang)], axis=1)


def _inset_polygon(verts_2d, inset: float):
    """Shrink a convex outline by moving every edge `inset` inward and re-intersecting
    neighbours.

    Not the same as scaling about the centre, which moves a distant edge further than
    a near one and so would inset the rhombus's long flanks less than its short ones.
    This is exact for any convex polygon, which all six pieces are.

    Assumes counter-clockwise winding -- which `_regular_polygon_verts`, `_rect_verts`
    and `_rhombus_verts` all produce.
    """
    import numpy as np

    v = np.asarray(verts_2d, dtype=np.float64)
    n = len(v)
    lines = []
    for i in range(n):
        e = v[(i + 1) % n] - v[i]
        nrm = np.array([-e[1], e[0]], dtype=np.float64)   # left of a CCW edge = interior
        nrm /= np.linalg.norm(nrm)
        lines.append((nrm, float(np.dot(nrm, v[i])) + inset))

    out = []
    for i in range(n):
        (n1, d1), (n2, d2) = lines[i - 1], lines[i]       # the two edges meeting at v[i]
        a = np.array([n1, n2])
        if abs(np.linalg.det(a)) < 1e-12:
            raise ValueError(f"cannot inset: edges {i - 1} and {i} are collinear")
        out.append(np.linalg.solve(a, np.array([d1, d2])))
    return np.array(out)


def piece_verts(rec: dict[str, Any], clearance: float):
    """2D outline of the PIECE that seats in `rec` -- the recess inset by `clearance`
    on every side -- or None for a circle, whose piece stays an analytic cylinder of
    radius `rec["radius"] - clearance`.

    A piece is NOT the size of its recess. docs/reference/toy.png draws every shape as
    a double outline and dimensions the OUTER one ("recess side 46mm"); the inner line
    is the piece. Measured off that drawing at its own 174mm scale, the gap is 2.0mm
    per side on all three shapes it can be read cleanly on: circle 49.9 -> 45.8mm,
    square 46.2 -> 42.1mm, rectangle 43.3 -> 39.4mm. A piece cut to its recess's exact
    size could not be lifted out of the hole it gets inserted into, and once the recess
    is a real pocket it renders as z-fighting stripes down the pocket walls.
    """
    verts = recess_verts(rec)
    if verts is None:
        return None
    return _inset_polygon(verts, clearance)


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


def _ray_box_hit(origin, direction, box):
    """Where a ray leaving `origin` (inside the axis-aligned `box`, given as
    (xmin, xmax, ymin, ymax) in the same frame as `origin`) crosses its boundary."""
    import numpy as np

    origin = np.asarray(origin, dtype=np.float64)
    ts = []
    for d, o, lo, hi in ((direction[0], origin[0], box[0], box[1]),
                         (direction[1], origin[1], box[2], box[3])):
        if abs(d) > 1e-12:
            ts.append(((hi if d > 0 else lo) - o) / d)
    t = min(t for t in ts if t > 0)
    return origin + t * np.asarray(direction, dtype=np.float64)


def _ray_polygon_hit(origin, direction, verts):
    """Where a ray leaving `origin` (inside the polygon) crosses its edges. Takes the
    nearest forward crossing, so a slightly non-convex outline still works."""
    best = None
    n = len(verts)
    for i in range(n):
        a = verts[i]
        b = verts[(i + 1) % n]
        e = b - a
        denom = direction[0] * (-e[1]) + direction[1] * e[0]
        if abs(denom) < 1e-12:
            continue
        diff = a - origin
        t = (diff[0] * (-e[1]) + diff[1] * e[0]) / denom
        u = (diff[0] * (-direction[1]) + diff[1] * direction[0]) / denom
        if t > 1e-9 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
            best = t
    if best is None:
        raise ValueError("ray from inside the polygon found no exit -- outline is malformed")
    return origin + best * direction


def _cluster_1d(items, lo: float, hi: float):
    """Group `items` -- (min, max, payload) intervals -- into maximal overlapping
    clusters, and give each cluster a slice of [lo, hi] cut halfway through the gap to
    its neighbour. Returns [(slice_lo, slice_hi, [payload, ...]), ...], left to right.
    """
    clusters: list[list] = []
    for imin, imax, payload in sorted(items, key=lambda it: it[0]):
        if clusters and imin <= clusters[-1][1]:
            clusters[-1][1] = max(clusters[-1][1], imax)
            clusters[-1][2].append(payload)
        else:
            clusters.append([imin, imax, [payload]])

    out = []
    for k, (cmin, cmax, payloads) in enumerate(clusters):
        left = lo if k == 0 else (clusters[k - 1][1] + cmin) / 2.0
        right = hi if k == len(clusters) - 1 else (cmax + clusters[k + 1][0]) / 2.0
        out.append((left, right, payloads))
    return out


def pocket_cells(size, boxes, names=None):
    """Split the slab's top face into one axis-aligned cell per pocket.

    Six holes in one face is a polygon-with-holes triangulation, which is real
    machinery. This sidesteps it: cut the face into rectangles that each contain
    exactly one hole, and the single-hole ring tiling that already worked handles each
    cell on its own. Neighbouring cells meet along a shared straight line in one plane,
    so the T-junctions where their vertices do not line up cannot open a visible crack.

    Columns first, then rows WITHIN each column -- not a global grid. On this board a
    global grid does not exist: the diamond hangs down to y=-1.7mm while the square
    reaches up to +0.4mm, so no single horizontal line separates the two rows, even
    though one separates them inside each column.

    `boxes` are (xmin, xmax, ymin, ymax) in the board's own frame, in pocket order.
    Returns cells (xmin, xmax, ymin, ymax) in that same order. Pure numpy-free
    arithmetic, so the partition is unit-testable without Isaac.
    """
    def label(i):
        return names[i] if names else str(i)

    hw, hh = size[0] / 2.0, size[1] / 2.0
    cells: list[Any] = [None] * len(boxes)
    for x0, x1, column in _cluster_1d([(b[0], b[1], i) for i, b in enumerate(boxes)], -hw, hw):
        for y0, y1, members in _cluster_1d([(boxes[i][2], boxes[i][3], i) for i in column], -hh, hh):
            if len(members) != 1:
                raise NotImplementedError(
                    f"pockets {[label(i) for i in members]} share a cell: they overlap in "
                    "both x and y, so no rectangular cut separates them. Triangulate the "
                    "top face as one polygon with several holes instead.")
            cells[members[0]] = (x0, x1, y0, y1)
    return cells


def _slab_with_pockets_mesh(stage, path: str, size, pockets, depth: float, board_color):
    """The board slab with a real blind pocket cut into its top face for EVERY recess.

    A seated piece does not sit ON the board, it sits IN it. Until 2026-08-16 only the
    one empty recess was a hole and the five seated pieces were 2mm plates lying on an
    unbroken slab -- so they read as stickers, and the empty socket stood out for the
    wrong reason (it was the only shape with any depth at all, rather than the only one
    without a piece in it). Every recess is cut here; the piece that fills it is a
    separate prim dropped into the hole, see `add_board`.

    Each pocket gets a cell of the top face (`pocket_cells`) and that cell is tiled as
    a ring between the pocket outline and the cell's rectangle: both loops sampled
    along the same sorted bearings taken from the pocket's centre (the pocket's own
    vertices, plus the cell's four corners so the cell outline stays exactly
    rectangular). A cell is convex and contains its pocket's centre, so corresponding
    points never cross and the ring tiles the cell exactly once.

    `pockets` is a list of (centre_xy, verts_2d, floor_color, name).
    """
    import numpy as np
    from pxr import Gf, UsdGeom, UsdPhysics, Vt

    sx, sy, sz = size
    hw, hh, hz = sx / 2.0, sy / 2.0, sz / 2.0
    floor_z = hz - depth

    boxes = []
    for centre, verts, _floor_color, _name in pockets:
        v = np.asarray(verts, dtype=np.float64) + np.asarray(centre, dtype=np.float64)
        boxes.append((v[:, 0].min(), v[:, 0].max(), v[:, 1].min(), v[:, 1].max()))
    cells = pocket_cells(size, boxes, names=[p[3] for p in pockets])

    points: list[Any] = []
    counts: list[int] = []
    indices: list[int] = []
    colors: list[Any] = []

    def add_point(x, y, z):
        points.append(Gf.Vec3f(float(x), float(y), float(z)))
        return len(points) - 1

    def add_face(ids, color):
        counts.append(len(ids))
        indices.extend(ids)
        colors.append(Gf.Vec3f(*color))     # one colour per face -- `uniform`, set below

    board_rgb = tuple(float(c) for c in board_color)

    for (centre, verts, floor_color, _name), cell in zip(pockets, cells):
        centre = np.asarray(centre, dtype=np.float64)
        hole = np.asarray(verts, dtype=np.float64) + centre
        x0, x1, y0, y1 = cell
        corners = np.array([[x1, y1], [x0, y1], [x0, y0], [x1, y0]], dtype=np.float64)
        rel = np.vstack([hole - centre, corners - centre])
        bearings = sorted({round(float(np.arctan2(v[1], v[0])), 9) for v in rel})
        dirs = np.array([[np.cos(a), np.sin(a)] for a in bearings])

        inner = np.array([_ray_polygon_hit(centre, d, hole) for d in dirs])
        outer = np.array([_ray_box_hit(centre, d, cell) for d in dirs])
        n = len(dirs)

        inner_top = [add_point(p[0], p[1], hz) for p in inner]
        outer_top = [add_point(p[0], p[1], hz) for p in outer]
        inner_floor = [add_point(p[0], p[1], floor_z) for p in inner]
        floor_hub = add_point(centre[0], centre[1], floor_z)
        floor_rgb = tuple(float(c) for c in floor_color)

        for i in range(n):
            j = (i + 1) % n
            add_face([inner_top[i], inner_top[j], outer_top[j], outer_top[i]], board_rgb)
            add_face([inner_top[j], inner_top[i], inner_floor[i], inner_floor[j]], board_rgb)
            add_face([floor_hub, inner_floor[i], inner_floor[j]], floor_rgb)

    # Outer walls and underside, once for the whole slab rather than once per cell.
    rim = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    rim_top = [add_point(x, y, hz) for x, y in rim]
    rim_bot = [add_point(x, y, -hz) for x, y in rim]
    for i in range(4):
        j = (i + 1) % 4
        add_face([rim_top[i], rim_bot[i], rim_bot[j], rim_top[j]], board_rgb)
    add_face(list(reversed(rim_bot)), board_rgb)

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray(points))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(indices))
    mesh.CreateSubdivisionSchemeAttr("none")      # else it renders as a blob
    mesh.CreateExtentAttr([(-hw, -hh, -hz), (hw, hh, hz)])

    # Per-face colour so each pocket floor keeps its recess's paint while the rest of
    # the slab stays birch -- the floor is what you see through an empty hole, and in
    # board_reference_demo.png the circle's is teal with "circle" printed on it.
    attr = mesh.CreateDisplayColorAttr(Vt.Vec3fArray(colors))
    attr.SetMetadata("interpolation", "uniform")

    # The slab was a FixedCuboid, i.e. a collider. Keep it one, but as the exact
    # triangle mesh -- so the holes are holes to physics too, not just to the camera.
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    return mesh


def add_board(world, scene_cfg: dict[str, Any]):
    """Add the shape-sorter board to `world.scene`: the slab with a real pocket cut for
    every recess, the piece seated in each recess marked `filled: true`, and a knob on
    each of those pieces.

    Returns a list of (handle, local_offset, local_quat_wxyz) for
    `apply_board_variation`, or None if the config has no `board` section (older
    configs stay valid and simply have no board).

    Pieces are Visual prims: no collider, because motion is replayed rather than
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
    board_color = list(board_cfg.get("color", [0.85, 0.72, 0.50]))
    recesses = board_cfg.get("recesses", [])
    depth = float(board_cfg.get("recess_depth", 0.008))
    clearance = float(board_cfg.get("piece_clearance", 0.0))
    piece_thickness = float(board_cfg.get("piece_thickness", size[2]))

    components: list[tuple[Any, Any, Any]] = []
    slab_pos, slab_quat = board_component_pose(base_pos, base_quat, np.zeros(3), identity)

    if recesses:
        # EVERY recess is cut, filled or not -- a seated piece sits in a hole, and a
        # board whose pieces lie on an unbroken surface is a board of stickers.
        slab = SingleXFormPrim(
            prim_path="/World/board_slab", name="board_slab",
            position=slab_pos.astype(np.float32), orientation=slab_quat.astype(np.float32),
        )
        _slab_with_pockets_mesh(
            stage, "/World/board_slab/geom", size,
            pockets=[(rec["offset"], recess_outline(rec),
                      list(rec.get("color", [0.5, 0.5, 0.5])), rec["id"])
                     for rec in recesses],
            depth=depth,
            board_color=board_color,
        )
    else:
        slab = world.scene.add(
            FixedCuboid(
                prim_path="/World/board_slab",
                name="board_slab",
                position=slab_pos.astype(np.float32),
                orientation=slab_quat.astype(np.float32),
                scale=np.array(size, dtype=np.float32),
                color=np.array(board_color, dtype=np.float32),
            )
        )
    components.append((slab, np.zeros(3), identity))

    # A seated piece rests on its pocket floor, so it stands (piece_thickness -
    # recess_depth) proud of the board: 4mm on these numbers. That is what
    # board_reference_demo.png shows -- every seated piece has a visible painted rim
    # standing above the birch, which is also what makes the empty circle read as a
    # hole rather than as a dark shape.
    local_z = size[2] / 2.0 - depth + piece_thickness / 2.0
    knob_r, knob_h, knob_color = _knob_dims(scene_cfg)

    for rec in recesses:
        if not rec.get("filled", True):
            # No piece: this recess is a bare pocket and its paint is the pocket floor,
            # already cut above. Drawing anything here is what made the empty socket
            # look like a sixth seated piece.
            continue

        local_offset = np.array([rec["offset"][0], rec["offset"][1], local_z], dtype=np.float64)
        local_quat = _yaw_quat_wxyz(rec.get("yaw_deg", 0.0))
        pos, quat = board_component_pose(base_pos, base_quat, local_offset, local_quat)
        color = list(rec.get("color", [0.5, 0.5, 0.5]))

        # An Xform wrapper carrying the geometry as a child. The wrapper keeps unit
        # scale so the knob parented under it is not squashed (see _prism_mesh), and
        # SingleXFormPrim gives apply_board_variation the set_world_pose it needs.
        prim_path = f"/World/board_piece_{rec['id']}"
        handle = SingleXFormPrim(
            prim_path=prim_path,
            name=f"board_piece_{rec['id']}",
            position=pos.astype(np.float32),
            orientation=quat.astype(np.float32),
        )
        verts = piece_verts(rec, clearance)
        if verts is None:
            _disc_geom(stage, f"{prim_path}/geom", rec["radius"] - clearance, piece_thickness, color)
        else:
            _prism_mesh(stage, f"{prim_path}/geom", verts, piece_thickness, color)
        components.append((handle, local_offset, local_quat))

        # Every seated piece carries a knob. The empty recess has none, and that is
        # the only thing marking the insertion target apart from five distractors.
        _attach_knob(prim_path, knob_r, knob_h, knob_color,
                     z_offset=piece_thickness / 2.0 + knob_h / 2.0)

    return components


class SceneHandles(NamedTuple):
    """Everything `build_scene` created, for the callers that re-tune it per episode."""

    object: Any                 # the loose peg (dynamic rigid body)
    material: Any               # its physics material, for friction variation
    board_components: Any       # [(handle, local_offset, local_quat), ...], or None
    lights: SceneLights


def build_scene(world, scene_cfg: dict[str, Any]) -> SceneHandles:
    """Assemble THE scene -- table, peg, board, lights -- into `world`.

    Every path that renders or simulates must go through this, and none of them may
    call `add_table_and_object` / `add_board` / `add_lighting` directly.

    That rule is not stylistic. Until 2026-08-16 scripts/export_lerobot_dataset.py --
    the script that renders the pixels a policy actually trains on -- built the table,
    the peg and the lights, and never called `add_board`. So **every synthetic frame
    ever exported showed the peg with nothing to insert it into**, while
    generate_synthetic.py simulated the same episodes WITH a board. That is the Dataset
    C defect (see src/bridge/scene_gate.py) recurring one script over, and the scene
    gate could not catch it: the gate renders its own scene, correctly, and then
    approves a config -- so it attests to a scene the exporter never built.

    A gate that renders its own scene can only ever check the config. Making the scene
    one function is what makes "the approved scene" and "the exported scene" the same
    object. tests/test_scene_is_built_whole.py fails if a script reaches past it.

    Must be called before `world.reset()`, same as the robot articulation.
    """
    obj, material = add_table_and_object(world, scene_cfg)
    board_components = add_board(world, scene_cfg)
    lights = add_lighting(scene_cfg)
    return SceneHandles(object=obj, material=material,
                        board_components=board_components, lights=lights)


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
