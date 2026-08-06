from __future__ import annotations

from dataclasses import dataclass


def track_joint_targets(model, data, targets, gripper_ctrl, *, settle=20):  # type: ignore[no-untyped-def]
    """Drive the 7 arm position-servo actuators to each joint-target row under physics.

    ``targets`` is a sequence of 7-element joint-angle rows (e.g. ``solve_arm_ik(...).
    joint_trajectory``). For each row, ``data.ctrl[:7]`` is set to the row and ``data.ctrl[7]``
    to ``gripper_ctrl`` (0 = closed … 255 = open), then physics is advanced ``settle`` steps.
    No ``qpos`` overwrite — the actuators do the work.
    """
    import mujoco

    for row in targets:
        data.ctrl[:7] = row[:7]
        data.ctrl[7] = gripper_ctrl
        for _ in range(settle):
            mujoco.mj_step(model, data)


_Z_HI = 0.35   # clearance height for approach / lift / traverse (matches episode.py)
_Z_LO = 0.225  # cube centre = table_top(0.20) + cube_half(0.025)


@dataclass
class PhysicsEpisodeResult:
    object_start_xy: tuple[float, float]
    object_final_xy: tuple[float, float]
    target_xy: tuple[float, float]
    place_error: float
    lifted: bool
    frames_stepped: int


def _grasp_waypoints(cube, tgt):  # type: ignore[no-untyped-def]
    # (x, y, z, gripper_closed)
    return [
        (cube[0], cube[1], _Z_HI, False),  # approach above cube, open
        (cube[0], cube[1], _Z_LO, False),  # descend, open
        (cube[0], cube[1], _Z_LO, True),   # close on cube (held grip_settle extra steps)
        (cube[0], cube[1], _Z_HI, True),   # lift
        (tgt[0], tgt[1], _Z_HI, True),     # traverse
        (tgt[0], tgt[1], _Z_LO, True),     # descend to target
        (tgt[0], tgt[1], _Z_LO, False),    # release
        (tgt[0], tgt[1], _Z_HI, False),    # retreat
    ]


def run_physics_episode(  # type: ignore[no-untyped-def]
    cube_xy,
    *,
    interp: int = 25,
    settle: int = 20,
    grip_settle: int = 200,
    gripper_open: float = 255.0,
    gripper_close: float = 0.0,
    on_sample=None,
    model=None,
) -> "PhysicsEpisodeResult":
    """``model``, if given, is used as-is (e.g. already perturbed by
    ``domain_randomization.randomize_scene``) instead of a fresh load from the canonical XML."""
    import mujoco
    import numpy as np

    from htdp.replay.arm_ik import solve_arm_ik
    from htdp.replay.scene import OBJECT_BODY, OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_PHYSICS_XML

    if model is None:
        model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_PHYSICS_XML))
    data = mujoco.MjData(model)
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    mujoco.mj_resetDataKeyframe(model, data, key)

    cube_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr = int(model.jnt_qposadr[cube_jid])
    # The "home" keyframe only contains 9 arm/finger values; MuJoCo zeroes the cube
    # freejoint qpos (positions AND quaternion).  We must set all 7 DOFs explicitly so
    # the cube sits on the table at the correct xy and z=_Z_LO with identity rotation.
    data.qpos[cube_qadr : cube_qadr + 3] = [cube_xy[0], cube_xy[1], _Z_LO]
    data.qpos[cube_qadr + 3 : cube_qadr + 7] = [1.0, 0.0, 0.0, 0.0]
    mujoco.mj_forward(model, data)

    start_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    start_z = float(data.body(OBJECT_BODY).xpos[2])
    cube_pos = data.body(OBJECT_BODY).xpos.copy()
    tgt_pos = model.site(TARGET_SITE).pos
    tgt_xy = (float(tgt_pos[0]), float(tgt_pos[1]))

    # Interpolate Cartesian keyframes; solve the whole path in one warm-started IK call.
    path: list[tuple[float, float, float, float, float, float, float, float]] = []
    grip_closed: list[bool] = []
    waypoints = _grasp_waypoints(cube_pos, tgt_pos)  # type: ignore[no-untyped-call]
    prev = waypoints[0][:3]
    for x, y, z, closed in waypoints:
        for k in range(1, interp + 1):
            f = k / interp
            px = prev[0] + (x - prev[0]) * f
            py = prev[1] + (y - prev[1]) * f
            pz = prev[2] + (z - prev[2]) * f
            path.append((0.0, px, py, pz, 1.0, 0.0, 0.0, 0.0))
            grip_closed.append(closed)
        prev = (x, y, z)

    solutions = solve_arm_ik(path).joint_trajectory

    lifted = False
    frames = 0
    prev_closed = False
    for sol, closed in zip(solutions, grip_closed):
        gripper = gripper_close if closed else gripper_open
        # On the transition open->closed, seat the grip before moving on.
        n = settle + (grip_settle if closed and not prev_closed else 0)
        data.ctrl[:7] = sol[:7]
        data.ctrl[7] = gripper
        for _ in range(n):
            mujoco.mj_step(model, data)
            frames += 1
            if not lifted and float(data.body(OBJECT_BODY).xpos[2]) > start_z + 0.05:
                lifted = True
        # Emit one row per IK target, sampled at the SETTLED state (after this target's steps).
        if on_sample is not None:
            on_sample(model, data, closed)
        prev_closed = closed

    cube = data.body(OBJECT_BODY).xpos
    final_xy = (float(cube[0]), float(cube[1]))
    place_error = float(np.hypot(final_xy[0] - tgt_xy[0], final_xy[1] - tgt_xy[1]))
    return PhysicsEpisodeResult(start_xy, final_xy, tgt_xy, place_error, lifted, frames)
