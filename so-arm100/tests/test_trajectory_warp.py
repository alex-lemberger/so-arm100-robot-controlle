"""Checks for re-planning a demonstrated episode onto a moved object
(src/augmentation/trajectory_warp.py).

This is the component that makes `randomization.label_breaking.object_position`
honest. If it is quietly wrong, the pipeline goes back to producing episodes whose
frames show the peg in one place and whose actions reach another -- the defect that
made data/synthetic/circle_grasp_v1 untrainable, except this time with a module named
after fixing it. So the tests below are mostly about the ways a warp can look fine and
be wrong.

Runs on a real episode of circle_grasp_v1, not a synthetic fixture: the failure modes
live in real gripper signals and real postures.
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from augmentation.trajectory_warp import (  # noqa: E402
    MAX_SAFE_DISPLACEMENT_M,
    displacement_weights,
    find_grasp_release,
    warp_trajectory,
)
from bridge.trajectory_converter import convert_episode, load_robot_mapping  # noqa: E402
from kinematics.forward_kinematics import forward_kinematics  # noqa: E402
from kinematics.inverse_kinematics import joint_limits_from_mapping  # noqa: E402

ARM, _G = load_robot_mapping(ROOT / "configs" / "robot_mapping.yaml")
LIMITS = joint_limits_from_mapping(ARM)
STEPS = convert_episode(ROOT / "data" / "circle_grasp_v1", 0,
                        ROOT / "configs" / "robot_mapping.yaml")
Q = np.array([t.joint_positions for t in STEPS])
GRIP = np.array([t.gripper for t in STEPS])
# Every 4th frame: the warp is per-frame independent given its seed, and this keeps
# the suite to seconds without changing what is exercised.
QS, GS = Q[::4], GRIP[::4]


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  -- ' + detail if detail and not cond else ''}")
    return cond


def test_grasp_and_release_are_found():
    grasp, release = find_grasp_release(GRIP)
    ok = check("a grasp is detected", grasp is not None, f"{grasp}")
    ok &= check("a release is detected", release is not None, f"{release}")
    if grasp is not None and release is not None:
        ok &= check("the grasp precedes the release", grasp < release, f"{grasp} -> {release}")
        ok &= check("both fall inside the episode", 0 < grasp and release < len(GRIP),
                    f"{grasp}, {release} of {len(GRIP)}")
        print(f"        gripper closes at frame {grasp}, opens at {release}, "
              f"of {len(GRIP)} ({100*grasp/len(GRIP):.0f}% and {100*release/len(GRIP):.0f}%)")
    return ok


def test_weights_hand_the_displacement_back_by_the_release():
    """The reach must arrive at the new peg; the insertion must still arrive at the
    board, which did not move. A uniform displacement would fix the first half of the
    episode and break the second."""
    w = displacement_weights(100, 30, 70)
    ok = check("full displacement through the grasp", np.all(w[:31] == 1.0))
    ok &= check("none of it after the release", np.all(w[70:] == 0.0))
    ok &= check("monotonic ramp in between", np.all(np.diff(w[30:70]) <= 0))
    ok &= check("no release -> the whole episode moves",
                np.all(displacement_weights(50, 10, None) == 1.0))
    ok &= check("no grasp -> the whole episode moves",
                np.all(displacement_weights(50, None, None) == 1.0))
    return ok


def test_zero_displacement_is_exactly_the_parent():
    """The identity case. If a zero warp perturbs the trajectory at all, then every
    warped episode carries an unexplained difference from its parent and Rule 10's
    reproducibility claim is gone."""
    res = warp_trajectory(QS, GS, (0.0, 0.0), joint_limits=LIMITS)
    ok = check("zero displacement returns the parent's joints exactly",
               np.allclose(res.joint_positions, QS, atol=1e-9),
               f"max diff {np.abs(res.joint_positions - QS).max():.2e}")
    ok &= check("and converges everywhere", res.unconverged_frames == 0)
    return ok


def test_the_reach_arrives_at_the_displaced_object():
    """The point of the exercise: at the grasp, the gripper must be where the peg now
    is -- not where the parent episode left it."""
    delta = (0.02, -0.015)
    res = warp_trajectory(QS, GS, delta, joint_limits=LIMITS)
    g = res.grasp_index
    parent_at_grasp = forward_kinematics(QS[g])
    warped_at_grasp = forward_kinematics(res.joint_positions[g])
    moved = warped_at_grasp - parent_at_grasp
    want = np.array([delta[0], delta[1], 0.0])
    ok = check("the gripper reaches the object's new position at the grasp",
               np.allclose(moved, want, atol=1.5e-3),
               f"moved {np.round(moved*1000, 2)}mm, wanted {np.round(want*1000, 2)}mm")
    ok &= check("the warp reports itself usable", res.ok,
                f"err {res.max_position_error_m*1000:.2f}mm, "
                f"rot {res.max_orientation_change_deg:.1f}deg, "
                f"step {res.max_joint_step_rad:.3f}rad, "
                f"unconverged {res.unconverged_frames}")
    print(f"        worst IK error {res.max_position_error_m*1000:.3f}mm, "
          f"worst gripper rotation {res.max_orientation_change_deg:.1f} deg, "
          f"largest joint step {res.max_joint_step_rad:.3f} rad")
    return ok


def test_the_insertion_still_targets_the_board():
    """The board did not move. If the warp drags the end of the episode along with the
    peg, it fixes the grasp label and breaks the insert label -- which is the same
    class of defect, just later in the episode."""
    res = warp_trajectory(QS, GS, (0.025, 0.0), joint_limits=LIMITS)
    r = res.release_index
    ok = check("a release was found so there is an insertion phase", r is not None)
    if r is None:
        return ok
    tail_parent = np.array([forward_kinematics(q) for q in QS[r:]])
    tail_warped = np.array([forward_kinematics(q) for q in res.joint_positions[r:]])
    drift = np.abs(tail_warped - tail_parent).max()
    ok &= check("the post-release trajectory is untouched", drift < 1e-9,
                f"drifted {drift*1000:.3f}mm")
    return ok


def test_continuity_is_preserved():
    """A warp can satisfy every waypoint and still be unexecutable if it jumps between
    them. The parent's own frame-to-frame motion is the yardstick."""
    res = warp_trajectory(QS, GS, (0.02, 0.02), joint_limits=LIMITS)
    parent_step = np.abs(np.diff(QS, axis=0)).max()
    ok = check("no joint step much larger than the parent's own",
               res.max_joint_step_rad < max(3 * parent_step, 0.15),
               f"warped {res.max_joint_step_rad:.3f} rad vs parent {parent_step:.3f} rad")
    print(f"        parent's largest joint step {parent_step:.3f} rad, "
          f"warped {res.max_joint_step_rad:.3f} rad")
    return ok


def test_joint_limits_are_respected():
    res = warp_trajectory(QS, GS, (0.02, 0.02), joint_limits=LIMITS)
    ok = True
    for i, lim in enumerate(LIMITS):
        if lim is None:
            continue
        col = res.joint_positions[:, i]
        ok &= check(f"joint {i} stays inside its USD limit",
                    col.min() >= lim[0] - 1e-9 and col.max() <= lim[1] + 1e-9,
                    f"[{col.min():.3f}, {col.max():.3f}] vs [{lim[0]:.3f}, {lim[1]:.3f}]")
    return ok


def test_oversized_displacement_is_refused():
    """Past the measured envelope the IK stops converging and the gripper's approach
    tilts far enough that the warped grasp is not the demonstrated one. That has to
    fail loudly -- a quietly bad episode is exactly what this module exists to stop."""
    try:
        warp_trajectory(QS, GS, (MAX_SAFE_DISPLACEMENT_M + 0.02, 0.0), joint_limits=LIMITS)
        return check("a displacement past the safe envelope raises", False)
    except ValueError as exc:
        return check("a displacement past the safe envelope raises", True, str(exc))


if __name__ == "__main__":
    results = {}
    for fn in (test_grasp_and_release_are_found,
               test_weights_hand_the_displacement_back_by_the_release,
               test_zero_displacement_is_exactly_the_parent,
               test_the_reach_arrives_at_the_displaced_object,
               test_the_insertion_still_targets_the_board,
               test_continuity_is_preserved,
               test_joint_limits_are_respected,
               test_oversized_displacement_is_refused):
        print(f"\n{fn.__name__}:")
        results[fn.__name__] = fn()
    failed = [k for k, v in results.items() if not v]
    print("\n" + ("ALL PASS" if not failed else f"FAILED: {failed}"))
    sys.exit(1 if failed else 0)
