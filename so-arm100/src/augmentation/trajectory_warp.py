"""Re-plan a demonstrated episode for an object that has moved.

The problem this solves
-----------------------
`scripts/generate_synthetic.py` copies the parent episode's actions verbatim. Move
the peg and the frames show it somewhere new while the labels still reach where it
used to be -- which trains a policy to ignore the target's position, the exact
failure measured on hardware (transport 4/10 with the peg on the demos' spot, 0/10
with it 22mm away; see docs/RUNBOOK.md). That is why every pose axis in
`randomization.label_breaking` is inert.

Warping makes those axes honest: displace the object, and re-plan the joint
trajectory so the actions reach the object's NEW position.

Which part of the trajectory moves
----------------------------------
Not all of it. An insertion episode reaches for the peg, grasps it, carries it to the
board, and releases. Moving the peg moves the reach; it does not move the board. So
the displacement is applied with a weight that is

    1.0   up to the grasp          -- the approach must arrive at the new peg
    1->0  from grasp to release    -- the carry must still arrive at the board
    0.0   after the release        -- the retreat was never about the peg

Applying the displacement uniformly would drag the insertion off the hole, which
mislabels the second half of the episode while fixing the first.

The grasp and release are read from the gripper channel rather than assumed: they are
where it closes and where it opens. On a grasp-only episode there is no release, and
the weight simply stays at 1.

What this does NOT do
---------------------
It does not re-time anything: frame k of the warp is frame k of the parent, so the
episode keeps its duration, its velocities and its contact schedule. It does not
re-plan around obstacles. It assumes the demonstrated posture remains appropriate a
few centimetres away, which is what the nullspace term in `solve_ik` enforces and
what `orientation_change_deg` in the returned diagnostics lets you check. Large
displacements will eventually break that assumption, and `WarpResult` is built to
show you when rather than to hide it.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from kinematics.forward_kinematics import forward_kinematics, forward_kinematics_pose
from kinematics.inverse_kinematics import solve_ik

GRIPPER_CLOSE_RAD = -0.01   # per-frame change counting as the jaw closing
GRIPPER_OPEN_RAD = 0.01

# How far the object may be displaced before a warped episode stops resembling the
# demonstration it came from. MEASURED 2026-08-16 over 27 reach-phase postures of
# circle_grasp_v1 episode 0, 8 displacement directions each, with the task-priority IK:
#
#   displacement   worst IK error   unconverged   gripper rotation (median / p90 / worst)
#          5 mm          0.15 mm           0            0.9 /  2.4 /  3.1 deg
#         10 mm          0.48 mm           0            2.0 /  4.9 /  6.2 deg
#         20 mm          0.50 mm           0            3.3 /  9.8 / 12.6 deg
#         30 mm          0.48 mm           0            6.0 / 15.1 / 19.0 deg
#         40 mm          1.81 mm           4            6.8 / 19.7 / 25.2 deg
#         50 mm          5.23 mm           9            9.6 / 24.9 / 32.6 deg
#
# Position stays sub-millimetre to 30mm and then the arm starts running out of
# workspace, which the solver reports rather than hides. The gripper's approach tilts
# about 0.2 deg per mm of displacement -- half what position-only IK gave, and the
# reason solve_ik carries an orientation task at all.
#
# This is a real ceiling on what warping can do: it fills IN a demonstration's
# neighbourhood, it does not move it across the table. Covering a 15cm workspace still
# needs real demonstrations spread across it (see docs/RUNBOOK.md on placement
# coverage) -- warping then makes that grid continuous instead of a set of points.
MAX_SAFE_DISPLACEMENT_M = 0.03


class WarpResult(NamedTuple):
    joint_positions: np.ndarray      # [T, 5] re-planned arm joints, radians
    weights: np.ndarray              # [T] displacement weight actually applied
    grasp_index: int | None
    release_index: int | None
    max_position_error_m: float      # worst IK residual over the episode
    max_orientation_change_deg: float
    max_joint_step_rad: float        # largest frame-to-frame joint jump
    parent_max_joint_step_rad: float # ... and the parent's own, to judge it against
    unconverged_frames: int

    @property
    def ok(self) -> bool:
        """Whether the warp is fit to train on.

        Thresholds are the replay gate's own (AGENTS_NEW.md Sec 10 wants EE error
        under 10mm; IK is held an order tighter) plus a continuity bound, because a
        trajectory that satisfies every waypoint and jumps between them is not
        something the arm can execute.

        Continuity is judged against THE PARENT, not an absolute number. The question
        is whether warping introduced roughness, and the demonstration is the only
        thing that can answer it -- a fixed 0.15 rad bound flagged a warp whose largest
        joint step was 0.238 rad and identical to the parent's, i.e. one that had added
        nothing at all.
        """
        return (self.unconverged_frames == 0
                and self.max_position_error_m < 1e-3
                and self.max_joint_step_rad <= max(1.5 * self.parent_max_joint_step_rad, 0.05)
                and self.max_orientation_change_deg < 20.0)


def find_grasp_release(gripper_rad) -> tuple[int | None, int | None]:
    """(grasp, release) frame indices, from where the jaw closes and re-opens.

    The grasp is the last sustained closing before the release, not the first twitch:
    demonstrators often pre-close slightly while approaching.
    """
    g = np.asarray(gripper_rad, dtype=np.float64)
    d = np.diff(g)
    closing = np.flatnonzero(d < GRIPPER_CLOSE_RAD)
    opening = np.flatnonzero(d > GRIPPER_OPEN_RAD)
    if closing.size == 0:
        return None, None
    grasp = int(closing[-1]) + 1 if opening.size == 0 else None
    if opening.size:
        release = int(opening[-1]) + 1
        before = closing[closing < release]
        if before.size == 0:
            return None, release
        grasp = int(before[-1]) + 1
        return grasp, release
    return grasp, None


def displacement_weights(n_frames: int, grasp_index, release_index) -> np.ndarray:
    """1.0 through the grasp, ramped to 0 by the release, 0 after. See the module
    docstring for why the carry has to give the displacement back."""
    w = np.ones(n_frames, dtype=np.float64)
    if grasp_index is None:
        return w
    if release_index is None or release_index <= grasp_index:
        return w
    ramp = np.linspace(1.0, 0.0, release_index - grasp_index, endpoint=False)
    w[grasp_index:release_index] = ramp
    w[release_index:] = 0.0
    return w


def warp_trajectory(joint_positions, gripper_rad, displacement_xy,
                    joint_limits=None, **ik_kwargs) -> WarpResult:
    """Re-plan `joint_positions` for an object displaced by `displacement_xy` metres.

    `joint_positions` is [T, 5] in radians (Isaac order, as
    `trajectory_converter.Timestep.joint_positions`). The displacement is in the
    world/base XY plane -- the peg stays on the table.

    Every frame is solved warm-started from the previous solved frame and pulled
    toward the parent frame's own posture, so the result is the demonstrated motion
    displaced rather than an independent solution per frame.
    """
    q_parent = np.asarray(joint_positions, dtype=np.float64)
    if q_parent.ndim != 2 or q_parent.shape[1] != 5:
        raise ValueError(f"expected joint_positions [T, 5], got {q_parent.shape}")
    delta = np.array([displacement_xy[0], displacement_xy[1], 0.0], dtype=np.float64)
    if np.linalg.norm(delta) > MAX_SAFE_DISPLACEMENT_M:
        # Loud, not silent: past this the IK stops converging and the gripper's
        # approach tilts far enough that the grasp in the warped episode is not the
        # grasp that was demonstrated. Generating such an episode anyway is how a
        # dataset ends up mislabelled in a new way.
        raise ValueError(
            f"displacement {np.linalg.norm(delta)*1000:.0f}mm exceeds "
            f"MAX_SAFE_DISPLACEMENT_M ({MAX_SAFE_DISPLACEMENT_M*1000:.0f}mm); see the "
            "measured table in this module. Spread real demonstrations across the "
            "workspace instead of warping one across it.")

    grasp, release = find_grasp_release(gripper_rad)
    weights = displacement_weights(len(q_parent), grasp, release)

    out = np.empty_like(q_parent)
    q_seed = q_parent[0].copy()
    worst_err = worst_rot = 0.0
    unconverged = 0
    for t, (q_t, w) in enumerate(zip(q_parent, weights)):
        if w == 0.0:
            # Nothing to solve: this part of the episode was never about the object,
            # so it keeps the demonstrator's joints EXACTLY rather than a re-solve
            # that would differ in the last decimal for no reason.
            out[t] = q_t
            q_seed = q_t.copy()
            continue
        target = forward_kinematics(q_t) + w * delta
        res = solve_ik(target, q_init=q_seed, q_ref=q_t, joint_limits=joint_limits, **ik_kwargs)
        out[t] = res.q
        q_seed = res.q
        worst_err = max(worst_err, res.position_error_m)
        worst_rot = max(worst_rot, res.orientation_change_deg)
        unconverged += not res.converged

    steps = np.abs(np.diff(out, axis=0)).max() if len(out) > 1 else 0.0
    parent_steps = np.abs(np.diff(q_parent, axis=0)).max() if len(q_parent) > 1 else 0.0
    return WarpResult(
        joint_positions=out,
        weights=weights,
        grasp_index=grasp,
        release_index=release,
        max_position_error_m=float(worst_err),
        max_orientation_change_deg=float(worst_rot),
        max_joint_step_rad=float(steps),
        parent_max_joint_step_rad=float(parent_steps),
        unconverged_frames=int(unconverged),
    )
