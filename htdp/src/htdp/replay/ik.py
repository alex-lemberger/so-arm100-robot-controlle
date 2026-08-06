from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from htdp.replay.player import load_release_pose

_ARM_XML = Path(__file__).parent / "assets" / "arm.xml"


class IkUnavailable(RuntimeError):
    """Raised when mink/daqp/mujoco are not installed."""


@dataclass
class IkResult:
    joint_trajectory: list[list[float]]
    max_error: float
    timestamps: list[float]
    targets: list[tuple[float, float, float]]
    errors: list[float]
    target_orientations: list[tuple[float, float, float, float]]
    orientation_errors: list[float]
    max_orientation_error: float


def replay_release_ik(
    release_dir: Path, max_steps: int = 50, ik_iters: int = 10, orientation_cost: float = 0.0
) -> IkResult:
    try:
        import mink  # type: ignore[import-not-found]
        import mujoco  # type: ignore[import-not-found]
        import numpy as np
        from mink.lie.se3 import SE3  # type: ignore[import-not-found]
        from mink.lie.so3 import SO3  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise IkUnavailable("install with: uv sync --extra replay") from exc

    pose = load_release_pose(release_dir)["right_wrist"]
    model = mujoco.MjModel.from_xml_path(str(_ARM_XML))
    data = mujoco.MjData(model)
    cfg = mink.Configuration(model)
    cfg.update(data.qpos)
    task = mink.FrameTask(
        frame_name="eef",
        frame_type="body",
        position_cost=1.0,
        orientation_cost=orientation_cost,
        lm_damping=1.0,
    )
    limits = [mink.ConfigurationLimit(model)]
    eid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "eef")
    dt = model.opt.timestep

    n = min(max_steps, len(pose))
    trajectory: list[list[float]] = []
    timestamps: list[float] = []
    targets: list[tuple[float, float, float]] = []
    errors: list[float] = []
    target_orientations: list[tuple[float, float, float, float]] = []
    orientation_errors: list[float] = []
    max_error = 0.0
    max_orientation_error = 0.0
    for i in range(n):
        t, x, y, z, qw, qx, qy, qz = pose[i]
        target_pos = np.array([x, y, z])
        target_quat = np.array([qw, qx, qy, qz])
        if orientation_cost > 0:
            task.set_target(SE3.from_rotation_and_translation(SO3(wxyz=target_quat), target_pos))
        else:
            task.set_target(SE3.from_translation(target_pos))
        for _ in range(ik_iters):
            vel = mink.solve_ik(cfg, [task], dt, "daqp", limits=limits)
            cfg.integrate_inplace(vel, dt)
        mujoco.mj_forward(model, cfg.data)
        trajectory.append([float(q) for q in cfg.data.qpos])
        err = float(np.linalg.norm(cfg.data.xpos[eid] - target_pos))
        ori_err = float(
            np.linalg.norm((SO3(wxyz=target_quat).inverse() @ SO3(wxyz=cfg.data.xquat[eid])).log())
        )
        timestamps.append(float(t))
        targets.append((float(x), float(y), float(z)))
        errors.append(err)
        target_orientations.append((float(qw), float(qx), float(qy), float(qz)))
        orientation_errors.append(ori_err)
        max_error = max(max_error, err)
        max_orientation_error = max(max_orientation_error, ori_err)
    return IkResult(
        joint_trajectory=trajectory,
        max_error=max_error,
        timestamps=timestamps,
        targets=targets,
        errors=errors,
        target_orientations=target_orientations,
        orientation_errors=orientation_errors,
        max_orientation_error=max_orientation_error,
    )


def write_ik_trajectory(result: IkResult, out_path: Path, *, force: bool = False) -> Path:
    """Write an IkResult to a CSV trajectory file. Pure stdlib — no IK deps."""
    if out_path.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {out_path} (use --force)")
    joint_count = len(result.joint_trajectory[0]) if result.joint_trajectory else 0
    header = (
        ["timestamp_s"]
        + [f"q{j}" for j in range(joint_count)]
        + ["target_x", "target_y", "target_z", "tracking_error_m"]
        + ["target_qw", "target_qx", "target_qy", "target_qz", "orientation_error_rad"]
    )
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(len(result.joint_trajectory)):
            tx, ty, tz = result.targets[i]
            qw, qx, qy, qz = result.target_orientations[i]
            writer.writerow(
                [
                    result.timestamps[i],
                    *result.joint_trajectory[i],
                    tx,
                    ty,
                    tz,
                    result.errors[i],
                    qw,
                    qx,
                    qy,
                    qz,
                    result.orientation_errors[i],
                ]
            )
    return out_path
