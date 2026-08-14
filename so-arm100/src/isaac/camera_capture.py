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


def create_camera(position, look_at, resolution: tuple[int, int] = (640, 480),
                  focal_length: float | None = None) -> SceneCamera:
    """Create a Replicator camera + render product + attached rgb annotator.

    Must be called after `world.reset()` is not required, but before you try to
    read frames -- give the render product a few warm-up steps first, see
    `warm_up`.
    """
    import omni.replicator.core as rep
    import omni.usd

    stage = omni.usd.get_context().get_stage()

    def _replicator_cameras():
        return {
            str(p.GetPath())
            for p in stage.Traverse()
            if p.GetPath().HasPrefix("/Replicator") and p.GetTypeName() == "Camera"
        }

    # Diff before/after rather than assuming there is only one. Walking the node's
    # output_prims is fragile across Replicator versions, but so was the previous
    # "find the single Camera prim" -- with a second camera (the wrist) it silently
    # returned the FIRST one, so both cameras rendered the same view.
    before = _replicator_cameras()
    camera = rep.create.camera(position=tuple(position), look_at=tuple(look_at))
    new_paths = _replicator_cameras() - before
    if len(new_paths) != 1:
        raise RuntimeError(f"expected exactly one new Replicator camera, got {sorted(new_paths)}")
    camera_prim = stage.GetPrimAtPath(next(iter(new_paths)))
    camera_prim.GetAttribute("clippingRange").Set((0.01, 100.0))
    if focal_length is not None:
        # USD default is 50mm against a 20.955mm aperture (~46 deg horizontal),
        # much narrower than the real overview webcam -- at 50mm the scene does not
        # fit the frame from any sensible standoff. Smaller = wider.
        camera_prim.GetAttribute("focalLength").Set(float(focal_length))

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


class TrackedCamera(NamedTuple):
    """A camera rigidly attached to a robot link, e.g. the wrist camera.

    Rather than re-deriving a look-at orientation in the link's local frame -- the
    exact class of hand-rolled quaternion maths that produced the 08-11 empty-frame
    bug -- this creates the camera through the same known-good
    `rep.create.camera(position, look_at)` path used for the overview, in WORLD
    coordinates at the robot's rest pose, and then simply preserves the rigid
    offset between camera and link from that moment on.

    So the config says "at rest, the wrist camera sits here and looks there", which
    is directly checkable against a rendered frame, and the tracking is one matrix
    multiply per frame with no orientation maths at all.
    """

    camera: SceneCamera
    link_path: str
    offset: object  # Gf.Matrix4d: camera-world-from-link-world, constant


def _world_xform(stage, prim_path: str):
    """USD-authored world transform. Fine for prims nothing simulates (the camera);
    NOT valid for articulation links -- see `_link_xform`."""
    from pxr import Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        raise ValueError(f"no prim at {prim_path}")
    return UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())


def _link_xform(link_path: str):
    """World transform of a simulated link, read through the physics view.

    PhysX writes pose updates to Fabric, not back to the USD stage, so
    UsdGeom.ComputeLocalToWorldTransform on an articulation link returns its
    authored rest pose forever. Reading it that way made the wrist camera hold
    still while the arm swung -- the link appeared to move 0.3mm over a 40 degree
    shoulder rotation.
    """
    from isaacsim.core.prims import SingleXFormPrim
    from pxr import Gf

    pos, quat_wxyz = SingleXFormPrim(link_path).get_world_pose()
    w, x, y, z = (float(v) for v in quat_wxyz)
    m = Gf.Matrix4d()
    m.SetRotate(Gf.Rotation(Gf.Quatd(w, Gf.Vec3d(x, y, z))))
    m.SetTranslateOnly(Gf.Vec3d(*(float(v) for v in pos)))
    return m


def create_tracked_camera(position, look_at, link_path: str, resolution=(640, 480),
                          focal_length: float | None = None) -> TrackedCamera:
    """Create a camera that follows `link_path`, posed in world coordinates as of
    the robot's CURRENT pose. Call after `world.reset()` so the link is at rest.
    """
    import omni.usd

    camera = create_camera(position, look_at, resolution, focal_length)
    stage = omni.usd.get_context().get_stage()

    cam_world = _world_xform(stage, camera.prim_path)
    link_world = _link_xform(link_path)
    # USD is row-vector (v' = v * M), so world = local * parent and the constant
    # rigid offset satisfies cam_world = offset * link_world.
    offset = cam_world * link_world.GetInverse()
    return TrackedCamera(camera=camera, link_path=link_path, offset=offset)


def update_tracked_camera(tracked: TrackedCamera) -> None:
    """Re-pose the camera from its link's current transform. Call once per frame,
    after stepping physics and before `capture_rgb`."""
    import omni.usd
    from pxr import UsdGeom

    stage = omni.usd.get_context().get_stage()
    desired = tracked.offset * _link_xform(tracked.link_path)

    cam_prim = stage.GetPrimAtPath(tracked.camera.prim_path)
    parent_world = _world_xform(stage, str(cam_prim.GetParent().GetPath()))
    UsdGeom.Xformable(cam_prim).MakeMatrixXform().Set(desired * parent_world.GetInverse())


def capture_tracked_rgb(tracked: TrackedCamera):
    """Update the pose, then read the frame."""
    update_tracked_camera(tracked)
    return capture_rgb(tracked.camera)
