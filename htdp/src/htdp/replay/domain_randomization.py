from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DRConfig:
    """Runtime domain-randomization ranges (docs/m2/c1-domain-randomization-scope.md, option A:
    cube stays red so the B2/B3 red-pixel gate remains valid; only shade jitters)."""

    light_dir_jitter_deg: float = 15.0
    light_diffuse_range: tuple[float, float] = (0.4, 0.9)
    headlight_jitter: float = 0.1
    table_hue_range: tuple[float, float] = (0.0, 1.0)
    cam_pos_jitter_m: float = 0.02
    cam_angle_jitter_deg: float = 2.0
    cube_hue_jitter: float = 0.08  # mild shade jitter only — keeps red dominant
    cube_friction_scale_range: tuple[float, float] = (0.8, 1.2)
    cube_mass_scale_range: tuple[float, float] = (0.8, 1.2)


def _hsv_to_rgb(h: float, s: float, v: float):  # type: ignore[no-untyped-def]
    import colorsys

    return colorsys.hsv_to_rgb(h, s, v)


def _rotation_from_axis_angle(axis, angle_rad: float):  # type: ignore[no-untyped-def]
    import numpy as np

    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    C = 1 - c
    return np.array(
        [
            [x * x * C + c, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, y * y * C + c, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, z * z * C + c],
        ]
    )


def randomize_scene(model, rng, cfg: DRConfig | None = None) -> None:  # type: ignore[no-untyped-def]
    """Perturb ``mjModel`` fields in place: light, table color, camera pose, cube friction/mass.

    Applied per-episode after ``MjModel.from_xml_path(...)``, before stepping/rendering. Cube hue
    jitter is mild (option A) so it stays red and the red-pixel visibility gate stays valid.
    """
    import mujoco
    import numpy as np

    cfg = cfg or DRConfig()

    # light direction/intensity
    jitter_rad = np.deg2rad(cfg.light_dir_jitter_deg)
    axis = rng.normal(size=3)
    angle = rng.uniform(-jitter_rad, jitter_rad)
    rot = _rotation_from_axis_angle(axis, angle)
    model.light_dir[0] = rot @ model.light_dir[0]
    diffuse = rng.uniform(*cfg.light_diffuse_range)
    model.light_diffuse[0] = [diffuse, diffuse, diffuse]

    # headlight
    hl = rng.uniform(-cfg.headlight_jitter, cfg.headlight_jitter, size=3)
    model.vis.headlight.diffuse[:] = np.clip(model.vis.headlight.diffuse + hl, 0.0, 1.0)
    model.vis.headlight.ambient[:] = np.clip(model.vis.headlight.ambient + hl, 0.0, 1.0)

    # table color — full hue range
    table_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "table")
    h = rng.uniform(*cfg.table_hue_range)
    r, g, b = _hsv_to_rgb(h, 0.5, 0.8)
    model.geom_rgba[table_gid] = [r, g, b, 1.0]

    # camera pose — small position + rotation jitter
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "front")
    pos_jitter = rng.uniform(-cfg.cam_pos_jitter_m, cfg.cam_pos_jitter_m, size=3)
    model.cam_pos[cam_id] = model.cam_pos[cam_id] + pos_jitter
    cam_axis = rng.normal(size=3)
    cam_angle = rng.uniform(
        -np.deg2rad(cfg.cam_angle_jitter_deg), np.deg2rad(cfg.cam_angle_jitter_deg)
    )
    cam_rot = _rotation_from_axis_angle(cam_axis, cam_angle)
    mat0 = np.array(model.cam_mat0[cam_id]).reshape(3, 3)
    model.cam_mat0[cam_id] = (cam_rot @ mat0).flatten()

    # cube — mild hue jitter (stays red), friction/mass scale (keep grasp feasible)
    cube_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "cube_geom")
    cube_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "cube")
    hue_shift = rng.uniform(-cfg.cube_hue_jitter, cfg.cube_hue_jitter)
    base_h = 0.0  # red
    r, g, b = _hsv_to_rgb((base_h + hue_shift) % 1.0, 0.7, 0.9)
    model.geom_rgba[cube_gid] = [r, g, b, 1.0]
    fscale = rng.uniform(*cfg.cube_friction_scale_range)
    model.geom_friction[cube_gid] = model.geom_friction[cube_gid] * fscale
    mscale = rng.uniform(*cfg.cube_mass_scale_range)
    model.body_mass[cube_bid] = model.body_mass[cube_bid] * mscale
