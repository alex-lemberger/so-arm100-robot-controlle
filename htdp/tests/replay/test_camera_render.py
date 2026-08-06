import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("imageio")

import numpy as np


def _red_pixel_count(img: np.ndarray) -> int:
    """Pixels that are clearly the red cube (R high, G/B low) — not table, arm, floor or sky."""
    r, g, b = img[..., 0].astype(int), img[..., 1].astype(int), img[..., 2].astype(int)
    return int(np.count_nonzero((r > 120) & (g < 100) & (b < 100)))


def test_front_camera_frames_the_cube():
    """The named 'front' camera must actually look at the workspace: the red cube has to appear.

    A non-blank frame is not enough — a misaimed camera (pointed at a wall or the sky) still
    renders 'something'. Asserting the cube's red pixels are present is the render-side analogue
    of the M1 false-green video lesson (metrics green, picture wrong)."""
    import mujoco

    from htdp.replay.render import render_camera
    from htdp.replay.scene import TASK_SCENE_PHYSICS_XML

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)
    # cube_free is zeroed by the keyframe — seat the cube on the table where the scene places it.
    cube_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cube_free")
    qadr = int(model.jnt_qposadr[cube_jid])
    data.qpos[qadr : qadr + 7] = [0.50, -0.15, 0.225, 1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(model, data)

    img = render_camera(model, data, camera="front", height=96, width=96)
    assert img.shape == (96, 96, 3)
    assert _red_pixel_count(img) > 20, "front camera does not frame the cube"


def test_render_physics_episode_writes_nonempty_mp4(tmp_path):
    from htdp.replay.render import render_physics_episode

    out = render_physics_episode(tmp_path / "physics.mp4", cube_xy=(0.50, -0.15))
    assert out.exists() and out.stat().st_size > 10_000
    with pytest.raises(FileExistsError):
        render_physics_episode(out, cube_xy=(0.50, -0.15))
