"""Checks for the damped-least-squares IK (src/kinematics/inverse_kinematics.py).

Pure numpy, no Isaac. The point of every test here is that IK is the component that
makes the mislabelling axes safe to switch on, so an IK that is quietly wrong would
reintroduce exactly the defect it was built to remove -- silently, and in the labels
rather than the pixels.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bridge.trajectory_converter import load_robot_mapping  # noqa: E402
from kinematics.forward_kinematics import (  # noqa: E402
    forward_kinematics,
    forward_kinematics_pose,
)
from kinematics.inverse_kinematics import (  # noqa: E402
    jacobian,
    joint_limits_from_mapping,
    solve_ik,
)

ARM, _GRIPPER = load_robot_mapping(ROOT / "configs" / "robot_mapping.yaml")
LIMITS = joint_limits_from_mapping(ARM)
RNG = np.random.default_rng(20260816)


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def _random_q(n=1):
    """Joint configurations inside the USD-authored limits."""
    out = []
    for _ in range(n):
        q = []
        for lim in LIMITS:
            lo, hi = (-1.0, 1.0) if lim is None else lim
            q.append(RNG.uniform(max(lo, -2.0), min(hi, 2.0)))
        out.append(np.array(q))
    return out


def test_forward_kinematics_pose_agrees_with_position():
    """The 4x4 must have the original function's answer in its translation column,
    or every orientation number computed from it describes a different arm."""
    ok = True
    for q in _random_q(20):
        ok &= np.allclose(forward_kinematics_pose(q)[:3, 3], forward_kinematics(q), atol=1e-12)
    return check("forward_kinematics_pose's translation == forward_kinematics", ok)


def test_jacobian_matches_finite_difference_of_fk():
    """A Jacobian that disagrees with its own FK is the 2026-08-10 sign-convention
    bug in a new place: everything converges, to the wrong pose."""
    ok = True
    for q in _random_q(8):
        j = jacobian(q)
        for i in range(5):
            d = np.zeros(5); d[i] = 1e-5
            fd = (forward_kinematics(q + d) - forward_kinematics(q - d)) / 2e-5
            ok &= np.allclose(j[:, i], fd, atol=1e-7)
    return check("jacobian columns match a finite difference of the FK", ok)


def test_round_trip_reaches_reachable_targets():
    """FK a random posture, perturb the tip, and ask IK to get back there."""
    ok = True
    errs, iters = [], []
    for q in _random_q(40):
        target = forward_kinematics(q) + RNG.uniform(-0.03, 0.03, 3)
        res = solve_ik(target, q_init=q, joint_limits=LIMITS)
        if res.hit_limits:      # the target may genuinely be outside the workspace
            continue
        errs.append(res.position_error_m); iters.append(res.iterations)
        ok &= res.converged
    ok = check(f"IK reaches perturbed targets ({len(errs)} unclamped cases)", ok,
               f"worst error {max(errs)*1000:.3f}mm")
    ok &= check("and sub-millimetre", max(errs) < 1e-3, f"{max(errs)*1000:.3f}mm")
    print(f"        median {np.median(iters):.0f} iterations, worst "
          f"{max(errs)*1000:.4f}mm over {len(errs)} solves")
    return ok


def test_exact_target_is_a_fixed_point():
    """Asking for the pose the arm is already in must not move it."""
    ok = True
    for q in _random_q(20):
        res = solve_ik(forward_kinematics(q), q_init=q, joint_limits=LIMITS)
        ok &= res.converged and np.allclose(res.q, q, atol=1e-6)
    return check("IK leaves an already-satisfied posture alone", ok)


def test_approach_direction_is_what_the_nullspace_buys():
    """What the redundancy is actually spent on.

    An earlier version of this test asserted that IK returns the joint configuration
    NEAREST the reference posture. That is not what the solver promises and cannot be:
    five joints against position (3) plus approach direction (2) have nothing left
    over, so joint-space proximity is not separately controllable. Measured, a
    near-seeded solve drifts up to 1.1 rad in joint space -- while holding the tip and
    the gripper's approach, which is what the warped episode is judged on.

    So the guarantee under test is the one that matters for a grasp: whatever the
    joints do, the gripper still points the way the demonstrator pointed it.
    """
    ok = True
    worst = 0.0
    for q in _random_q(15):
        target = forward_kinematics(q) + np.array([0.02, 0.0, 0.0])
        near = solve_ik(target, q_init=q, q_ref=q, joint_limits=LIMITS)
        far = solve_ik(target, q_init=q + RNG.uniform(-0.4, 0.4, 5), q_ref=q,
                       joint_limits=LIMITS)
        for res in (near, far):
            if res.converged:
                worst = max(worst, res.orientation_change_deg)
                ok &= res.orientation_change_deg < 20.0
    return check("approach direction is held regardless of the seed", ok,
                 f"worst {worst:.1f} deg")


def test_orientation_barely_moves_for_small_displacements():
    """Position-only IK on a redundant arm could roll the gripper over while hitting
    the target. For the centimetres this is used at, it must not."""
    rots = []
    for q in _random_q(25):
        target = forward_kinematics(q) + np.array([0.02, 0.02, 0.0])
        res = solve_ik(target, q_init=q, q_ref=q, joint_limits=LIMITS)
        if res.converged:
            rots.append(res.orientation_change_deg)
    ok = check("gripper orientation drifts < 20 deg over a 28mm move",
               max(rots) < 20.0, f"worst {max(rots):.1f} deg")
    print(f"        median {np.median(rots):.1f} deg, worst {max(rots):.1f} deg "
          f"over {len(rots)} solves")
    return ok


def test_limits_are_respected():
    """A target outside the workspace must clamp and SAY so, not return an angle the
    arm cannot reach and let the replay discover it."""
    q = np.zeros(5)
    far = forward_kinematics(q) + np.array([10.0, 0.0, 0.0])
    res = solve_ik(far, q_init=q, joint_limits=LIMITS)
    ok = check("an unreachable target does not converge", not res.converged,
               f"error {res.position_error_m:.3f}m")
    inside = True
    for i, lim in enumerate(LIMITS):
        if lim is not None:
            inside &= lim[0] - 1e-9 <= res.q[i] <= lim[1] + 1e-9
    ok &= check("and the returned angles are still inside the joint limits", inside)
    return ok


if __name__ == "__main__":
    results = {}
    for fn in (test_forward_kinematics_pose_agrees_with_position,
               test_jacobian_matches_finite_difference_of_fk,
               test_round_trip_reaches_reachable_targets,
               test_exact_target_is_a_fixed_point,
               test_approach_direction_is_what_the_nullspace_buys,
               test_orientation_barely_moves_for_small_displacements,
               test_limits_are_respected):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
