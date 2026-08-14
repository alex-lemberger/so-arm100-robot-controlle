"""Add a table and one object to the Isaac Sim scene (AGENTS_NEW.md Task 7).

Isaac-specific (Rule 5: keep Isaac code separate from bridge/kinematics code) --
only import this from scripts that already boot Isaac's own Python interpreter.

See configs/simulation.yaml for why "table" is a thin static slab at z=0 rather
than a raised platform, and for where the object dimensions/position came from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


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


def add_board(world, scene_cfg: dict[str, Any]):
    """Add the shape-sorter board -- slab plus one visual marker per recess -- to
    `world.scene`. Returns a list of (handle, local_offset, local_quat_wxyz) for
    `apply_board_variation`, or None if the config has no `board` section (older
    configs stay valid and simply have no board).

    Recesses are Visual* prims: no collider, because motion is replayed rather than
    re-planned (Rule 4) so nothing is ever actually inserted, and a collider there
    would only risk spurious contacts with the replayed peg.

    Must be called before `world.reset()`, same as the robot and the table.
    """
    import numpy as np
    from isaacsim.core.api.objects import FixedCuboid, VisualCuboid, VisualCylinder

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

    for rec in board_cfg.get("recesses", []):
        local_offset = np.array([rec["offset"][0], rec["offset"][1], local_z], dtype=np.float64)
        # Per-recess yaw in the board's own frame: the diamond is a square plate
        # turned 45 degrees. Stored with the component so it survives every
        # subsequent board move rather than being re-derived.
        local_quat = _yaw_quat_wxyz(rec.get("yaw_deg", 0.0))
        pos, quat = board_component_pose(base_pos, base_quat, local_offset, local_quat)
        color = np.array(rec.get("color", [0.5, 0.5, 0.5]), dtype=np.float32)
        common = dict(
            prim_path=f"/World/board_recess_{rec['id']}",
            name=f"board_recess_{rec['id']}",
            position=pos.astype(np.float32),
            orientation=quat.astype(np.float32),
            color=color,
        )
        if rec["shape"] == "cylinder":
            handle = world.scene.add(VisualCylinder(radius=rec["radius"], height=disc_thickness, **common))
        elif rec["shape"] == "cuboid":
            sx, sy = rec["size"]
            handle = world.scene.add(VisualCuboid(scale=np.array([sx, sy, disc_thickness], dtype=np.float32), **common))
        else:
            raise NotImplementedError(f"Unsupported recess shape {rec['shape']!r} for {rec['id']!r}")
        components.append((handle, local_offset, local_quat))

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
