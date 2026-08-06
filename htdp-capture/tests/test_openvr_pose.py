import pytest

from htdp_capture.openvr_convert import matrix_to_pos_quat
from htdp_capture.openvr_pose import DevicePose, OpenVRPoseSource

_OK = 200


def _identity(tx=0.0, ty=0.0, tz=0.0):
    return [[1.0, 0.0, 0.0, tx], [0.0, 1.0, 0.0, ty], [0.0, 0.0, 1.0, tz]]


class _FakeSystem:
    """Fake SystemHandle: fixed device list indexed by position."""

    def __init__(self, devices):
        # devices: list of (serial, DevicePose)
        self._devices = devices
        self.shutdown_called = False

    def device_poses(self):
        return [dp for _, dp in self._devices]

    def serial(self, index):
        return self._devices[index][0]

    def shutdown(self):
        self.shutdown_called = True


def _clock():
    state = {"t": 0.0}

    def c() -> float:
        state["t"] += 1.0
        return state["t"]

    return c


def test_poll_returns_only_mapped_trackers():
    devices = [
        ("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(1.0))),
        ("LHR-OBJ", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(2.0))),
        (
            "LHR-CONTROLLER",
            DevicePose(valid=True, connected=True, result=_OK, matrix=_identity(9.0)),
        ),
    ]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist", "LHR-OBJ": "object"},
        system=_FakeSystem(devices),
        ok_result=_OK,
        clock=_clock(),
    )
    out = src.poll()
    assert set(out) == {"right_wrist", "object"}  # controller omitted


def test_poll_converts_pose_via_pure_module():
    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    devices = [("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=m))]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    pose = src.poll()["right_wrist"]
    exp_pos, exp_quat = matrix_to_pos_quat(m)
    assert pose.pos == exp_pos
    assert pose.quat == exp_quat
    assert pose.quality == 1.0


def test_invalid_device_included_with_zero_quality():
    devices = [
        ("LHR-WRIST", DevicePose(valid=False, connected=True, result=_OK, matrix=_identity()))
    ]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    out = src.poll()
    assert "right_wrist" in out
    assert out["right_wrist"].quality == 0.0


def test_disconnected_mapped_device_is_omitted():
    devices = [
        ("LHR-WRIST", DevicePose(valid=False, connected=False, result=_OK, matrix=_identity()))
    ]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    assert src.poll() == {}


def test_trackers_returns_sorted_mapped_ids():
    src = OpenVRPoseSource(
        {"LHR-OBJ": "object", "LHR-WRIST": "right_wrist"},
        system=_FakeSystem([]),
        ok_result=_OK,
        clock=_clock(),
    )
    assert src.trackers() == ["object", "right_wrist"]


def test_close_does_not_shutdown_injected_system():
    fake = _FakeSystem([])
    src = OpenVRPoseSource({"LHR-WRIST": "right_wrist"}, system=fake, ok_result=_OK, clock=_clock())
    src.close()
    assert fake.shutdown_called is False


def test_injected_system_requires_ok_result():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"LHR-WRIST": "right_wrist"}, system=_FakeSystem([]))


def test_bad_tracker_id_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"LHR-X": "elbow"}, system=_FakeSystem([]), ok_result=_OK)


def test_duplicate_tracker_id_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource(
            {"LHR-A": "right_wrist", "LHR-B": "right_wrist"},
            system=_FakeSystem([]),
            ok_result=_OK,
        )


def test_empty_serial_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({"": "right_wrist"}, system=_FakeSystem([]), ok_result=_OK)


def test_empty_device_map_rejected():
    with pytest.raises(ValueError):
        OpenVRPoseSource({}, system=_FakeSystem([]), ok_result=_OK)


def test_timestamp_comes_from_clock():
    devices = [
        ("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=_identity()))
    ]
    src = OpenVRPoseSource(
        {"LHR-WRIST": "right_wrist"}, system=_FakeSystem(devices), ok_result=_OK, clock=_clock()
    )
    assert src.poll()["right_wrist"].t == 1.0
    assert src.poll()["right_wrist"].t == 2.0
