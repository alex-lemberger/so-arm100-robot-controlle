from __future__ import annotations

from pathlib import Path

TASK_SCENE_XML = Path(__file__).parent / "assets" / "franka" / "task_scene.xml"
TASK_SCENE_PHYSICS_XML = Path(__file__).parent / "assets" / "franka" / "task_scene_physics.xml"
OBJECT_BODY = "cube"
OBJECT_FREEJOINT = "cube_free"
TARGET_SITE = "target"
GRASP_WELD = "grasp"


def load_scene():  # type: ignore[no-untyped-def]
    import mujoco  # lazy

    return mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))


def object_xy(data):  # type: ignore[no-untyped-def]
    return (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))


def target_xy(model):  # type: ignore[no-untyped-def]
    s = model.site(TARGET_SITE)
    return (float(s.pos[0]), float(s.pos[1]))
