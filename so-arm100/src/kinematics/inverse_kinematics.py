"""Position IK for the SO-ARM100's 5-DOF arm, by damped least squares on the FK.

Why this exists
---------------
Every pose axis of the synthetic pipeline is gated off (see
src/augmentation/randomization.py) for one reason: moving the object while copying
the parent episode's actions verbatim mislabels the episode. Re-planning the actions
needs IK, and the repo had forward kinematics only.

It does not need a library. The arm is five revolute joints, `forward_kinematics`
already composes the chain, and damped least squares over a finite-difference
Jacobian is a hundred lines of standard numerics.

The redundancy is the useful part
---------------------------------
Five joints against a three-component position target leaves two degrees of freedom
unconstrained. That is exactly what trajectory warping wants: of all the joint
configurations that put the gripper at the new object position, take the one closest
to what the demonstrator actually did. So the solver carries a nullspace pull toward
a reference posture (`q_ref`), and warping passes the demo's own joints as that
reference. The result is the demonstrated motion, displaced -- not a fresh solution
that happens to share an endpoint.

Position only, deliberately
---------------------------
Six-DOF pose tracking is not available to a 5-DOF arm, so orientation is left to the
nullspace term rather than constrained. For the small displacements this is built for
(a few centimetres) the posture stays near the demo's and so does the approach
direction; `orientation_change_deg` reports how far it actually drifted, because
"the gripper quietly rolled over on the way" is the failure worth catching, and
position error cannot see it.

Pure numpy, no Isaac (Rule 5) -- it runs anywhere the tests do.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .forward_kinematics import forward_kinematics, forward_kinematics_pose

N_JOINTS = 5

# Cost of moving each joint, in the weighted least-squares sense: higher means the
# solver spends it more reluctantly. [shoulder_pan, shoulder_lift, elbow_flex,
# wrist_flex, wrist_roll].
#
# Neutral, after measuring. The theory was that making the wrist pair expensive would
# stop the solver reaching a displaced target by rolling the gripper over instead of
# moving the arm. Swept on 60 real demo postures x 6 displacements: weights of 1, 3,
# 6, 12 and 25 on the wrist left the worst gripper rotation at 36 degrees throughout
# and made the median WORSE (12.5 -> 15.6 deg), while costing position accuracy at the
# high end. So the drift is not the wrist being cheap; it is what position-only IK on
# a 5-DOF arm does, and the honest response is to bound and report it rather than to
# tune a knob that does not move it. See `orientation_change_deg` and
# augmentation.trajectory_warp.MAX_SAFE_DISPLACEMENT_M.
DEFAULT_JOINT_WEIGHTS = np.array([1.0, 1.0, 1.0, 1.0, 1.0])


class IKResult(NamedTuple):
    q: np.ndarray                 # [5] solved joint angles, radians
    position_error_m: float       # remaining distance to the target
    converged: bool               # error under tolerance AND limits respected
    iterations: int
    hit_limits: tuple[str, ...]   # joints that ended clamped at a limit
    orientation_change_deg: float # gripper rotation vs `q_ref` (or `q_init`)


def _rotvec(r: np.ndarray) -> np.ndarray:
    """Rotation matrix -> rotation vector (axis * angle), for small angles."""
    v = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]]) / 2.0
    sin = np.linalg.norm(v)
    cos = (np.trace(r) - 1.0) / 2.0
    angle = np.arctan2(sin, np.clip(cos, -1.0, 1.0))
    return v if sin < 1e-9 else v * (angle / sin)


def orientation_error(r_current: np.ndarray, r_target: np.ndarray) -> np.ndarray:
    """Rotation vector taking `r_current` to `r_target`, in the base frame."""
    return _rotvec(r_target @ r_current.T)


def pose_jacobian(q: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """6x5: the position Jacobian stacked on the orientation one.

    Five joints cannot track a full 6-DOF pose, but they are exactly enough for
    position (3) plus an approach DIRECTION (2), and that is what matters for a
    grasp: which way the gripper points, with roll about its own axis free. Rather
    than pick an axis and hard-code which one is 'forward', the solver takes the full
    orientation error at a low weight and lets damped least squares find the
    compromise -- position is weighted to stay exact, orientation is best-effort, and
    the one unreachable degree of freedom is whichever the geometry cannot supply.
    """
    q = np.asarray(q, dtype=np.float64)
    j = np.zeros((6, N_JOINTS))
    for i in range(N_JOINTS):
        dq = np.zeros(N_JOINTS)
        dq[i] = eps
        hi, lo = forward_kinematics_pose(q + dq), forward_kinematics_pose(q - dq)
        j[:3, i] = (hi[:3, 3] - lo[:3, 3]) / (2 * eps)
        j[3:, i] = _rotvec(hi[:3, :3] @ lo[:3, :3].T) / (2 * eps)
    return j


def jacobian(q: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """3x5 position Jacobian by central differences.

    Analytic would be faster and no more accurate at this scale: the chain is five
    links, and a central difference on a smooth composition of rotations is exact to
    ~1e-10 here. Finite differences also mean the Jacobian cannot silently disagree
    with the FK it is supposed to differentiate, which for this repo is the more
    valuable property -- the sign-convention bugs found on 2026-08-10 were exactly
    that kind of disagreement.
    """
    q = np.asarray(q, dtype=np.float64)
    j = np.zeros((3, N_JOINTS))
    for i in range(N_JOINTS):
        dq = np.zeros(N_JOINTS)
        dq[i] = eps
        j[:, i] = (forward_kinematics(q + dq) - forward_kinematics(q - dq)) / (2 * eps)
    return j


def _rotation_angle_deg(r_a: np.ndarray, r_b: np.ndarray) -> float:
    """Angle of the rotation taking `r_a` to `r_b`, in degrees."""
    cos = (np.trace(r_a.T @ r_b) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def solve_ik(
    target_xyz,
    q_init,
    q_ref=None,
    joint_limits=None,
    tol_m: float = 5e-4,
    max_iter: int = 200,
    damping: float = 0.02,
    nullspace_gain: float = 0.02,
    max_step_rad: float = 0.1,
    joint_weights=None,
    orientation_weight: float = 1.0,
) -> IKResult:
    """Joint angles putting the end effector at `target_xyz`.

    `q_init` seeds the search (warm-start from the previous frame when warping a
    trajectory, so the solution stays on the same branch instead of flipping the
    elbow mid-episode). `q_ref` is the posture the nullspace pulls toward, defaulting
    to `q_init`.

    `joint_limits` is [(lo, hi), ...] in radians; None leaves a joint free. Solutions
    are clamped into range every iteration rather than at the end, so the solver
    optimises within the reachable set instead of converging somewhere illegal and
    being snapped out of it afterwards.

    `tol_m` defaults to 0.5mm -- an order of magnitude under the 10mm replay gate
    (AGENTS_NEW.md Sec 10), so IK is never the dominant error term in a warped
    episode.
    """
    q = np.asarray(q_init, dtype=np.float64).copy()
    if q.shape != (N_JOINTS,):
        raise ValueError(f"expected {N_JOINTS} joint angles, got shape {q.shape}")
    target = np.asarray(target_xyz, dtype=np.float64)
    ref = q.copy() if q_ref is None else np.asarray(q_ref, dtype=np.float64).copy()
    r_start = forward_kinematics_pose(ref)[:3, :3]

    lo = np.full(N_JOINTS, -np.inf)
    hi = np.full(N_JOINTS, np.inf)
    if joint_limits is not None:
        for i, lim in enumerate(joint_limits):
            if lim is not None:
                lo[i], hi[i] = float(lim[0]), float(lim[1])

    # Weighted least squares: w_inv scales how freely each joint is spent.
    weights = DEFAULT_JOINT_WEIGHTS if joint_weights is None else np.asarray(joint_weights, float)
    w_inv = np.diag(1.0 / weights)

    eye3 = np.eye(3)
    eye_n = np.eye(N_JOINTS)
    prev_rot_norm = np.inf
    iterations = 0
    for iterations in range(1, max_iter + 1):
        pose = forward_kinematics_pose(q)
        pos_err = target - pose[:3, 3]
        rot_err = orientation_error(pose[:3, :3], r_start)
        err_norm = float(np.linalg.norm(pos_err))
        rot_norm = float(np.linalg.norm(rot_err))
        # Stop when the PRIMARY task is satisfied and the secondary one has stopped
        # improving. Waiting for orientation to hit a tolerance instead burns every
        # iteration of the cap on a task the arm often cannot fully satisfy -- five
        # joints, six objectives -- which cost a median 200 iterations per solve where
        # 5 would do. At ~600 frames an episode and 100 episodes a dataset, that is the
        # difference between minutes and hours.
        if err_norm < tol_m and abs(prev_rot_norm - rot_norm) < 1e-6:
            break
        prev_rot_norm = rot_norm

        j6 = pose_jacobian(q)
        j_pos, j_rot = j6[:3, :], j6[3:, :]

        # TASK PRIORITY, not a weighted blend. Position is the primary task and gets
        # the full solution; orientation and posture are pushed only through the
        # nullspace of position, so they cannot trade the tip away.
        #
        # Weighting the two against each other was tried first and is the wrong shape
        # for this arm: at an orientation weight of 0.12 the gripper held to 1-5
        # degrees but position error went to 3mm at a 5mm displacement and 33mm at
        # 50mm, because five joints cannot serve both and least squares simply picks
        # a compromise. With priority, position stays sub-millimetre by construction
        # and orientation gets whatever the remaining two degrees of freedom allow.
        lam2 = (damping ** 2) * max(err_norm / 0.01, 0.02)
        jt = w_inv @ j_pos.T
        pinv = jt @ np.linalg.inv(j_pos @ jt + lam2 * eye3)
        dq = pinv @ pos_err

        nullspace = eye_n - pinv @ j_pos
        secondary = (orientation_weight * (j_rot.T @ rot_err)
                     + nullspace_gain * (ref - q))
        dq += nullspace @ secondary

        step = np.linalg.norm(dq)
        if step > max_step_rad:
            dq *= max_step_rad / step
        q = np.clip(q + dq, lo, hi)

    final_err = float(np.linalg.norm(target - forward_kinematics(q)))
    at_limit = tuple(
        f"j{i}" for i in range(N_JOINTS)
        if np.isfinite(lo[i]) and (abs(q[i] - lo[i]) < 1e-9 or abs(q[i] - hi[i]) < 1e-9)
    )
    return IKResult(
        q=q,
        position_error_m=final_err,
        converged=final_err < tol_m,
        iterations=iterations,
        hit_limits=at_limit,
        orientation_change_deg=_rotation_angle_deg(r_start, forward_kinematics_pose(q)[:3, :3]),
    )


def joint_limits_from_mapping(arm_joints) -> list[tuple[float, float] | None]:
    """[(lo, hi) radians or None] from `trajectory_converter.load_robot_mapping`'s
    arm joints, whose `isaac_limit_deg` are the USD-authored limits."""
    out = []
    for joint in arm_joints:
        lim = getattr(joint, "isaac_limit_deg", None)
        out.append(None if lim is None else (np.radians(lim[0]), np.radians(lim[1])))
    return out
