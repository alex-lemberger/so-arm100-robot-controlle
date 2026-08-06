import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")

from htdp.replay.episode import run_episode


def test_cube_xy_override_is_picked_and_placed():
    a = run_episode(cube_xy=(0.47, -0.18))
    assert abs(a.object_start_xy[0] - 0.47) < 1e-6
    assert abs(a.object_start_xy[1] - (-0.18)) < 1e-6
    assert a.place_error < 0.05  # still placed at the (fixed) target
    assert a.grasp_dist < 0.02   # gripper really on the (moved) cube

    # grasp flag is delivered to on_step at least once
    seen = []
    run_episode(cube_xy=(0.47, -0.18), on_step=lambda d, f, g: seen.append(g))
    assert any(seen) and not all(seen)  # grasp toggles on then off
