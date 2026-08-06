from __future__ import annotations

from dataclasses import dataclass

from htdp.replay.arm_ik import solve_arm_ik
from htdp.replay.ik import IkUnavailable
from htdp.replay.franka import GRASP_SITE
from htdp.replay.scene import OBJECT_BODY, OBJECT_FREEJOINT, TARGET_SITE, TASK_SCENE_XML

# Vertical waypoint heights above the Franka manipulation table (top at z=0.20).
_Z_HI = 0.35  # clearance height for approach / lift / traverse
_Z_LO = 0.225  # cube centre = table_top(0.20) + cube_half(0.025); grasp site lands here


@dataclass
class EpisodeResult:
    object_start_xy: tuple[float, float]
    object_final_xy: tuple[float, float]
    target_xy: tuple[float, float]
    place_error: float
    grasp_dist: float  # closest fingers-to-cube distance at the instant the weld closes
    frames_stepped: int
    qpos_trace: list[list[float]]


def _waypoints(cube, tgt):  # type: ignore[no-untyped-def]
    # Cartesian path keyed off the live cube + target positions; (x, y, z, grasp_active).
    return [
        (cube[0], cube[1], _Z_HI, False),  # approach above cube
        (cube[0], cube[1], _Z_LO, False),  # descend to cube
        (cube[0], cube[1], _Z_LO, True),  # grasp (attach on)
        (cube[0], cube[1], _Z_HI, True),  # lift
        (tgt[0], tgt[1], _Z_HI, True),  # traverse to target
        (tgt[0], tgt[1], _Z_LO, True),  # descend to target
        (tgt[0], tgt[1], _Z_LO, False),  # release (attach off)
        (tgt[0], tgt[1], _Z_HI, False),  # retreat
    ]


def run_episode(*, interp: int = 25, settle: int = 6, seed: int = 0, cube_xy=None, on_step=None) -> EpisodeResult:  # type: ignore[no-untyped-def]
    try:
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    model = mujoco.MjModel.from_xml_path(str(TASK_SCENE_XML))
    data = mujoco.MjData(model)
    grasp_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, GRASP_SITE)
    cube_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, OBJECT_FREEJOINT)
    cube_qadr = int(model.jnt_qposadr[cube_jid])
    cube_vadr = int(model.jnt_dofadr[cube_jid])
    mujoco.mj_forward(model, data)

    if cube_xy is not None:
        data.qpos[cube_qadr : cube_qadr + 2] = cube_xy
        mujoco.mj_forward(model, data)

    start_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    cube_pos = data.body(OBJECT_BODY).xpos.copy()
    tgt_pos = model.site(TARGET_SITE).pos
    waypoints = _waypoints(cube_pos, tgt_pos)  # type: ignore[no-untyped-call]

    # Densely interpolate the Cartesian keyframes, then solve the WHOLE path in one IK call.
    # solve_arm_ik warm-starts each sample from the previous solution, so the arm tracks a
    # continuous path and never jumps to a far IK branch — a single-waypoint solve from the
    # home pose lands in local minima and cannot reach the place-side targets.
    path: list[tuple[float, float, float, float, float, float, float, float]] = []
    grasp_flags: list[bool] = []
    prev = waypoints[0][:3]
    for x, y, z, grasp in waypoints:
        for k in range(1, interp + 1):
            f = k / interp
            px = prev[0] + (x - prev[0]) * f
            py = prev[1] + (y - prev[1]) * f
            pz = prev[2] + (z - prev[2]) * f
            path.append((0.0, px, py, pz, 1.0, 0.0, 0.0, 0.0))
            grasp_flags.append(grasp)
        prev = (x, y, z)

    solutions = solve_arm_ik(path).joint_trajectory
    n_arm = len(solutions[0])

    # Grasp is a kinematic attach: while held, the cube's free joint is slaved to the grasp
    # site at the relative offset captured the instant the grasp closes. Deterministic and
    # exact — a robust stand-in for a friction grasp for this demo (see design spec).
    grasp_offset = {"v": None}
    grasp_dist = float("inf")  # closest fingers-to-cube distance at the weld-close instant
    frames = 0
    qtrace: list[list[float]] = []
    for step, (sol, grasp) in enumerate(zip(solutions, grasp_flags)):
        for _ in range(settle):
            data.qpos[:n_arm] = sol[:n_arm]
            data.qvel[:n_arm] = 0.0
            mujoco.mj_forward(model, data)  # refresh site_xpos before measuring/welding
            if grasp:
                if grasp_offset["v"] is None:
                    # Record how far the gripper actually is from the cube when the weld
                    # closes — a real grasp must be near zero, not a teleport from afar.
                    gap = data.body(OBJECT_BODY).xpos - data.site_xpos[grasp_sid]
                    grasp_dist = min(grasp_dist, float(np.linalg.norm(gap)))
                    grasp_offset["v"] = gap
                data.qpos[cube_qadr : cube_qadr + 3] = data.site_xpos[grasp_sid] + grasp_offset["v"]
                data.qpos[cube_qadr + 3 : cube_qadr + 7] = (1.0, 0.0, 0.0, 0.0)
                data.qvel[cube_vadr : cube_vadr + 6] = 0.0
            else:
                grasp_offset["v"] = None
            mujoco.mj_step(model, data)
            if on_step is not None:
                on_step(data, frames, grasp)
            frames += 1
        if (step + 1) % interp == 0:  # snapshot at each keyframe
            qtrace.append([float(q) for q in data.qpos])

    final_xy = (float(data.body(OBJECT_BODY).xpos[0]), float(data.body(OBJECT_BODY).xpos[1]))
    tgt = (float(model.site(TARGET_SITE).pos[0]), float(model.site(TARGET_SITE).pos[1]))
    place_error = float(np.hypot(final_xy[0] - tgt[0], final_xy[1] - tgt[1]))
    return EpisodeResult(start_xy, final_xy, tgt, place_error, grasp_dist, frames, qtrace)
