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
