import pytest

pytest.importorskip("pylsl")
pytest.importorskip("pyxdf")

from htdp_capture.app import run_capture  # noqa: E402
from htdp_capture.config import CaptureConfig  # noqa: E402
from htdp_capture.openvr_convert import matrix_to_pos_quat  # noqa: E402
from htdp_capture.openvr_pose import DevicePose, OpenVRPoseSource  # noqa: E402
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule  # noqa: E402

_OK = 200


class _FakeSystem:
    def __init__(self, devices):
        self._devices = devices

    def device_poses(self):
        return [dp for _, dp in self._devices]

    def serial(self, index):
        return self._devices[index][0]

    def shutdown(self):
        pass


def _config(device_map):
    return CaptureConfig(
        trackers=sorted(device_map.values()),
        session={
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "vive-01"},
        rate_hz=200.0,
        duration_s=0.4,
        device_map=device_map,
    )


def test_openvr_source_is_drop_in_through_run_capture(tmp_path):
    import pyxdf

    m = [[0.0, -1.0, 0.0, 1.0], [1.0, 0.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0]]
    device_map = {"LHR-WRIST": "right_wrist"}
    devices = [("LHR-WRIST", DevicePose(valid=True, connected=True, result=_OK, matrix=m))]
    cfg = _config(device_map)

    xdf = tmp_path / "rec.xdf"
    run_capture(
        cfg,
        OpenVRPoseSource(device_map, system=_FakeSystem(devices), ok_result=_OK),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        xdf,
        tmp_path / "ingest.json",
    )

    streams, _ = pyxdf.load_xdf(str(xdf), dejitter_timestamps=False, synchronize_clocks=False)
    motion = next(s for s in streams if s["info"]["name"][0] == "right_wrist")
    assert len(motion["time_series"]) > 0

    exp_pos, exp_quat = matrix_to_pos_quat(m)
    row = motion["time_series"][0]
    # channel order: x_m,y_m,z_m,qw,qx,qy,qz,quality
    assert tuple(round(v, 6) for v in row[0:3]) == tuple(round(v, 6) for v in exp_pos)
    assert tuple(round(v, 6) for v in row[3:7]) == tuple(round(v, 6) for v in exp_quat)
    assert row[7] == 1.0
