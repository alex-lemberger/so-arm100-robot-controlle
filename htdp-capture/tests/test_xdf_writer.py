import pytest
import pyxdf

from htdp_capture.xdf_writer import CapturedStream, XdfWriteError, write_xdf


def _motion_stream():
    return CapturedStream(
        name="right_wrist", fmt="double64", n_channels=8, srate=100.0,
        stamps=[1000.0, 1000.01],
        numeric=[[0.1, 0.2, 0.3, 1.0, 0.0, 0.0, 0.0, 1.0],
                 [0.4, 0.5, 0.6, 1.0, 0.0, 0.0, 0.0, 1.0]],
    )


def _events_stream():
    return CapturedStream(
        name="events", fmt="string", n_channels=1, srate=0.0,
        stamps=[1000.0],
        strings=['{"event_id": 1, "label": "start"}'],
    )


def test_writes_xdf_magic_prefix(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    assert out.read_bytes().startswith(b"XDF:")


def test_roundtrips_numeric_via_pyxdf(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    s = streams[0]
    assert s["info"]["name"][0] == "right_wrist"
    assert s["info"]["channel_format"][0] == "double64"
    assert [list(map(float, row)) for row in s["time_series"]] == _motion_stream().numeric
    assert [float(t) for t in s["time_stamps"]] == _motion_stream().stamps


def test_roundtrips_string_via_pyxdf(tmp_path):
    out = write_xdf([_events_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    s = streams[0]
    assert s["info"]["channel_format"][0] == "string"
    assert [row[0] for row in s["time_series"]] == _events_stream().strings


def test_channel_labels_present_in_xml(tmp_path):
    out = write_xdf([_motion_stream()], tmp_path / "rec.xdf")
    streams, _ = pyxdf.load_xdf(str(out), dejitter_timestamps=False, synchronize_clocks=False)
    labels = [c["label"][0] for c in streams[0]["info"]["desc"][0]["channels"][0]["channel"]]
    assert labels == ["x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality"]


def test_force_guard(tmp_path):
    p = tmp_path / "rec.xdf"
    write_xdf([_motion_stream()], p)
    with pytest.raises(FileExistsError):
        write_xdf([_motion_stream()], p)
    write_xdf([_motion_stream()], p, force=True)  # no raise


def test_empty_stream_rejected(tmp_path):
    empty = CapturedStream("right_wrist", "double64", 8, 100.0, [], numeric=[])
    with pytest.raises(XdfWriteError):
        write_xdf([empty], tmp_path / "rec.xdf")
