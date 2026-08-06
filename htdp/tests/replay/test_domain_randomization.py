from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from htdp.replay.scene import TASK_SCENE_PHYSICS_XML


def _load_model():  # type: ignore[no-untyped-def]
    return mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))


def test_randomize_scene_changes_light_table_camera_and_cube_fields():
    from htdp.replay.domain_randomization import DRConfig, randomize_scene

    baseline = _load_model()
    model = _load_model()
    rng = np.random.default_rng(0)
    randomize_scene(model, rng, DRConfig())

    table_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "table")
    cube_gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "cube_geom")
    cube_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "cube")
    cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "front")

    assert not np.allclose(model.light_dir[0], baseline.light_dir[0])
    assert not np.allclose(model.light_diffuse[0], baseline.light_diffuse[0])
    assert not np.allclose(model.vis.headlight.diffuse, baseline.vis.headlight.diffuse)
    assert not np.allclose(model.geom_rgba[table_gid], baseline.geom_rgba[table_gid])
    assert not np.allclose(model.cam_pos[cam_id], baseline.cam_pos[cam_id])
    assert not np.allclose(model.cam_mat0[cam_id], baseline.cam_mat0[cam_id])
    assert not np.allclose(model.geom_friction[cube_gid], baseline.geom_friction[cube_gid])
    assert not np.allclose(model.body_mass[cube_bid], baseline.body_mass[cube_bid])
    # cube stays red-ish (option A): red channel still dominant
    r, g, b, _ = model.geom_rgba[cube_gid]
    assert r > g and r > b


def test_randomize_scene_is_seed_reproducible():
    from htdp.replay.domain_randomization import DRConfig, randomize_scene

    m1 = _load_model()
    m2 = _load_model()
    randomize_scene(m1, np.random.default_rng(42), DRConfig())
    randomize_scene(m2, np.random.default_rng(42), DRConfig())

    table_gid = mujoco.mj_name2id(m1, mujoco.mjtObj.mjOBJ_GEOM, "table")
    assert np.allclose(m1.geom_rgba[table_gid], m2.geom_rgba[table_gid])
    assert np.allclose(m1.light_dir[0], m2.light_dir[0])


def test_randomized_scene_still_graspable():
    """A teacher episode under DR must still lift and place the cube (mild jitter only)."""
    from htdp.replay.domain_randomization import DRConfig, randomize_scene
    from htdp.replay.physics_episode import run_physics_episode

    model = _load_model()
    randomize_scene(model, np.random.default_rng(7), DRConfig())

    result = run_physics_episode(cube_xy=(0.50, -0.15), model=model)
    assert result.lifted
    assert result.place_error < 0.05
