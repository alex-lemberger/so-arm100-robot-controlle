from __future__ import annotations

from dataclasses import dataclass

from htdp.replay.franka import FRANKA_XML, GRASP_SITE, home_qpos
from htdp.replay.ik import IkUnavailable


@dataclass
class ArmIkResult:
    joint_trajectory: list[list[float]]
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
    max_error: float


def solve_arm_ik(  # type: ignore[no-untyped-def]
    pose,
    *,
    ik_iters: int = 100,
    orientation_cost: float = 0.0,
    target_rotation=None,
) -> ArmIkResult:
    """Differential IK for the grasp site.

    ``orientation_cost`` > 0 biases the gripper toward ``target_rotation`` (a 3x3 world
    rotation matrix). Position is always tracked at unit cost; a soft orientation cost keeps
    the gripper pose consistent without sacrificing reach (the 5-DOF arm cannot hit an
    arbitrary full pose, so orientation is a bias, not a hard constraint).
    """
    try:
        import mink  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
        from mink.lie.se3 import SE3  # type: ignore[import-not-found]
        from mink.lie.so3 import SO3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    model = mujoco.MjModel.from_xml_path(str(FRANKA_XML))
    cfg = mink.Configuration(model)
    # seed from the non-singular home pose, not the extended zero pose
    cfg.update(home_qpos())  # type: ignore[no-untyped-call]
    task = mink.FrameTask(
        frame_name=GRASP_SITE,
        frame_type="site",
        position_cost=1.0,
        orientation_cost=orientation_cost,
        lm_damping=1.0,
    )
    rot = None if target_rotation is None else SO3.from_matrix(np.asarray(target_rotation))
    limits = [mink.ConfigurationLimit(model)]
    sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, GRASP_SITE)
    dt = model.opt.timestep

    traj: list[list[float]] = []
    ts: list[float] = []
    targets: list[tuple[float, float, float]] = []
    errors: list[float] = []
    max_error = 0.0
    for sample in pose:
        t, x, y, z = sample[0], sample[1], sample[2], sample[3]
        target = np.array([x, y, z])
        if rot is None:
            task.set_target(SE3.from_translation(target))
        else:
            task.set_target(SE3.from_rotation_and_translation(rot, target))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        traj.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.site_xpos[sid] - target))
        ts.append(float(t))
        targets.append((float(x), float(y), float(z)))
        errors.append(err)
        max_error = max(max_error, err)
    return ArmIkResult(traj, ts, targets, errors, max_error)
