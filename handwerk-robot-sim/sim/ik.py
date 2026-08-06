"""Stretch (v1.5): Cartesian inverse kinematics for the UR5e end-effector.

Damped-least-squares IK: given a target XYZ for an end-effector site, iterate
joint angles until the site reaches it. Use this to drive a real wall-plane
zigzag (waypoints across a plane) instead of the scripted joints in
zigzag_demo.py.

NOT wired into v1, and NOT yet executed. Before use:
  - find the end-effector site name in models/ur5e/ur5e.xml (e.g. an
    'attachment_site' or wrist site); pass it as `site_name`.
  - add joint-limit clamping for a real path (model.jnt_range).
"""
from __future__ import annotations

import numpy as np
import mujoco
import mink
from mink.lie.se3 import SE3


def solve_ik(
    model: "mujoco.MjModel",
    data: "mujoco.MjData",
    site_name: str,
    target_pos: np.ndarray,
    *,
    iters: int = 100,
    tol: float = 1e-4,
    damping: float = 1e-2,
) -> np.ndarray:
    """Return joint positions (qpos) that put `site_name` at `target_pos`."""
    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name)
    if site_id < 0:
        raise ValueError(f"site '{site_name}' not found in model")

    jacp = np.zeros((3, model.nv))
    for _ in range(iters):
        mujoco.mj_forward(model, data)
        err = np.asarray(target_pos) - data.site_xpos[site_id]
        if np.linalg.norm(err) < tol:
            break
        mujoco.mj_jacSite(model, data, jacp, None, site_id)
        # dq = J^T (J J^T + lambda^2 I)^-1 err
        jjt = jacp @ jacp.T + (damping ** 2) * np.eye(3)
        dq = jacp.T @ np.linalg.solve(jjt, err)
        data.qpos[: model.nv] += dq[: model.nv]

    return data.qpos.copy()


def wall_zigzag(origin, width, height, rows, step):
    """Generate a zigzag of Cartesian waypoints across a vertical wall plane.

    origin: (x, y, z) top-left corner; width along +y, height along -z.
    Yields (x, y, z) points, boustrophedon (left-right then right-left).
    """
    ox, oy, oz = origin
    for r in range(rows):
        z = oz - (height * r / max(1, rows - 1))
        ys = np.arange(0, width + step, step)
        if r % 2:
            ys = ys[::-1]
        for y in ys:
            yield (ox, oy + y, z)


class H1IkSolver:
    """Online differential IK for H1 right arm using mink.

    Targets the right_elbow_link body frame. Joint limits enforced by
    mink.ConfigurationLimit. Root (freejoint) is pinned to keyframe origin
    after each step so the robot doesn't walk toward the target.
    """

    def __init__(self, model: mujoco.MjModel, root_qpos: np.ndarray) -> None:
        """
        model      — MjModel for the H1
        root_qpos  — qpos[0:7] from the standing keyframe; frozen after each step
        """
        self._model = model
        self._root_qpos = root_qpos.copy()
        self._cfg = mink.Configuration(model)
        self._task = mink.FrameTask(
            frame_name="right_elbow_link",
            frame_type="body",
            position_cost=1.0,
            orientation_cost=0.0,
        )
        self._limits = [mink.ConfigurationLimit(model)]

    def sync_from(self, data: mujoco.MjData) -> None:
        """Copy current sim qpos into the IK config and update kinematics."""
        np.copyto(self._cfg.data.qpos, data.qpos)
        mujoco.mj_kinematics(self._model, self._cfg.data)

    def set_target(self, pos: np.ndarray) -> None:
        """Set Cartesian target position for the right hand."""
        self._task.set_target(SE3.from_translation(pos))

    def step(self, dt: float) -> None:
        """Run one IK step; integrates cfg.data.qpos in-place."""
        vel = mink.solve_ik(
            self._cfg, [self._task], dt, "daqp", limits=self._limits
        )
        self._cfg.integrate_inplace(vel, dt)

    def sync_to(self, data: mujoco.MjData) -> None:
        """Copy IK result back to main sim data; restore frozen root."""
        np.copyto(data.qpos, self._cfg.data.qpos)
        data.qpos[0:7] = self._root_qpos
