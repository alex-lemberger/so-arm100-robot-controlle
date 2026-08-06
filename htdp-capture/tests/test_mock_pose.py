import pytest

from htdp_capture.mock_pose import MockPoseSource
from htdp_capture.pose_source import Pose


def _fixed_clock():
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.01
        return state["t"]

    return clock


def test_trackers_must_be_in_contract():
    with pytest.raises(ValueError):
        MockPoseSource(["nose"])


def test_poll_returns_one_pose_per_tracker():
    src = MockPoseSource(["right_wrist", "object"], clock=_fixed_clock())
    sample = src.poll()
    assert set(sample) == {"right_wrist", "object"}
    assert all(isinstance(p, Pose) for p in sample.values())


def test_quality_is_one_by_default():
    src = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    assert src.poll()["right_wrist"].quality == 1.0


def test_dropout_frame_sets_quality_zero():
    src = MockPoseSource(["right_wrist"], dropout_frames={1}, clock=_fixed_clock())
    assert src.poll()["right_wrist"].quality == 1.0   # frame 0
    assert src.poll()["right_wrist"].quality == 0.0   # frame 1


def test_motion_is_deterministic_per_frame():
    a = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    b = MockPoseSource(["right_wrist"], clock=_fixed_clock())
    assert a.poll()["right_wrist"].pos == b.poll()["right_wrist"].pos


def test_quat_is_unit_wxyz():
    src = MockPoseSource(["torso"], clock=_fixed_clock())
    assert src.poll()["torso"].quat == (1.0, 0.0, 0.0, 0.0)
