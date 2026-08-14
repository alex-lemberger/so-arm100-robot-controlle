"""Render an RGB camera view of the scene via Replicator.

Supersedes an earlier attempt that used isaacsim.sensors.camera.Camera with a
hand-derived look-at quaternion: that produced flat, uniform (no-robot) frames
even though position/clipping/lighting/non-empty-render-data all individually
checked out. Root cause turned out to be the hand-derived orientation math
itself (pointed the camera at empty space), not the render-product binding --
confirmed 2026-08-11 by switching to Replicator's own `rep.create.camera(...,
look_at=...)` + `rep.create.render_product()` + `AnnotatorRegistry("rgb")`,
the exact pattern Isaac's own
`standalone_examples/api/isaacsim.replicator.examples/multi_camera.py` uses.

Isaac-specific (Rule 5) -- only import from a script that already booted
Isaac's own Python interpreter, after `SimulationApp` exists.
"""

from __future__ import annotations

from typing import NamedTuple


class SceneCamera(NamedTuple):
    prim_path: str
    annotator: object  # omni.replicator.core.AnnotatorRegistry rgb annotator


def create_camera(position, look_at, resolution: tuple[int, int] = (640, 480)) -> SceneCamera:
    """Create a Replicator camera + render product + attached rgb annotator.

    Must be called after `world.reset()` is not required, but before you try to
    read frames -- give the render product a few warm-up steps first, see
    `warm_up`.
    """
    import omni.replicator.core as rep
    import omni.usd

    camera = rep.create.camera(position=tuple(position), look_at=tuple(look_at))
    stage = omni.usd.get_context().get_stage()
    # rep.create.camera() returns a Replicator node wrapping a new ".../Camera_Xform/Camera"
    # prim; walking output_prims is fragile across Replicator versions, so just find the
    # single Camera-typed prim under /Replicator instead.
    camera_prim = next(
        p for p in stage.Traverse() if p.GetPath().HasPrefix("/Replicator") and p.GetTypeName() == "Camera"
    )
    camera_prim.GetAttribute("clippingRange").Set((0.01, 100.0))

    render_product = rep.create.render_product(str(camera_prim.GetPath()), resolution)
    annotator = rep.AnnotatorRegistry.get_annotator("rgb")
    annotator.attach(render_product)

    return SceneCamera(prim_path=str(camera_prim.GetPath()), annotator=annotator)


def warm_up(world, camera: SceneCamera, steps: int = 5) -> None:
    """The render product needs a few stepped frames before get_data() returns
    real pixels -- immediately after creation it comes back empty/shape (0,)."""
    import omni.replicator.core as rep

    for _ in range(steps):
        world.step(render=True)
        rep.orchestrator.step(rt_subframes=1)


def capture_rgb(camera: SceneCamera):
    """Returns an (H, W, 4) uint8 RGBA array, or None if the render product has
    no data yet (call `warm_up` first)."""
    data = camera.annotator.get_data()
    if data is None or not data.size:
        return None
    return data
