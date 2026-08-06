import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.replay.arm_ik import solve_arm_ik


def _line(n=20):
    # a short reachable Cartesian path in the Franka workspace (metres). The arm picks on a
    # table ~0.5 m in front of the base; targets sit near (0.5, 0, z) with z in [0.25, 0.35].
    # tuple = (t, x, y, z, qw, qx, qy, qz).
    return [
        (0.04 * i, 0.50, -0.10 + 0.01 * i, 0.35 - 0.005 * i, 1.0, 0.0, 0.0, 0.0) for i in range(n)
    ]


def test_arm_ik_tracks_and_is_deterministic():
    a = solve_arm_ik(_line())
    b = solve_arm_ik(_line())
    assert a.max_error < 0.03
    assert a.joint_trajectory == b.joint_trajectory
    assert len(a.joint_trajectory) == 20
