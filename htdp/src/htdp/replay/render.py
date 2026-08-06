from __future__ import annotations

from pathlib import Path

from htdp.replay.ik import IkUnavailable
from htdp.replay.scene import TASK_SCENE_PHYSICS_XML, TASK_SCENE_XML


def render_camera(model, data, *, camera, height: int, width: int, renderer=None):  # type: ignore[no-untyped-def]
    """Grab a single RGB frame (H, W, 3) from a NAMED camera at the current physics state.

    Reusable visual-observation primitive: B2 image demos and B3 visuomotor rollout render the
    policy's pixels through this same path, so train-time and rollout-time framing cannot drift.
    Pass a persistent ``renderer`` (a ``mujoco.Renderer``) to capture many frames without paying
    the per-call renderer construction (its height/width win); otherwise one is made and closed.
    """
    import mujoco

    if renderer is not None:
        renderer.update_scene(data, camera=camera)
        return renderer.render()

    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera=camera)
        return renderer.render()
    finally:
        renderer.close()


def render_episode(out_path: Path, *, fps: int = 30, every: int = 10, force: bool = False) -> Path:
    """Run the pick-and-place episode and write an MP4 of it.

    Captures one frame every ``every`` simulation steps via an offscreen MuJoCo renderer.
    Refuses to overwrite an existing file unless ``force``.
    """
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    try:
        import imageio.v3 as iio  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    from htdp.replay.episode import run_episode  # lazy import avoids a cycle

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    renderer = mujoco.Renderer(model, height=480, width=640)
    frames: list[np.ndarray] = []

    def on_step(data, step_index, grasp_active):  # type: ignore[no-untyped-def]
        if step_index % every == 0:
            renderer.update_scene(data)
            frames.append(renderer.render())

    run_episode(on_step=on_step)
    renderer.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, frames, fps=fps, codec="libx264")
    return out_path


def render_physics_episode(
    out_path: Path,
    cube_xy: tuple[float, float],
    *,
    camera: str = "front",
    height: int = 480,
    width: int = 640,
    fps: int = 30,
    force: bool = False,
) -> Path:
    """Run the PHYSICS friction-grasp episode and write an MP4 from the named ``camera``.

    Captures one frame per settled IK target via ``run_physics_episode``'s ``on_sample`` hook
    (~200 frames/episode). Same physics scene and camera the visuomotor demos will use.
    """
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    try:
        import imageio.v3 as iio  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    from htdp.replay.physics_episode import run_physics_episode  # lazy import avoids a cycle

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    renderer = mujoco.Renderer(model, height=height, width=width)
    frames: list[np.ndarray] = []

    def on_sample(_model, data, _closed):  # type: ignore[no-untyped-def]
        renderer.update_scene(data, camera=camera)
        frames.append(renderer.render())

    run_physics_episode(cube_xy=cube_xy, on_sample=on_sample)
    renderer.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, frames, fps=fps, codec="libx264")
    return out_path
