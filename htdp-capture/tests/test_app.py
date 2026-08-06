import json

import pytest

pytest.importorskip("pylsl")

from htdp_capture.app import run_capture  # noqa: E402
from htdp_capture.config import CaptureConfig  # noqa: E402
from htdp_capture.eeg_source import EegConfig  # noqa: E402
from htdp_capture.mock_eeg import MockEegSource  # noqa: E402
from htdp_capture.mock_pose import MockPoseSource  # noqa: E402
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule  # noqa: E402


def _config():
    return CaptureConfig(
        trackers=["right_wrist", "object"],
        session={
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "vive-01"},
        rate_hz=200.0,
        duration_s=0.3,
    )


def test_run_capture_writes_xdf_and_sidecar(tmp_path):
    cfg = _config()
    out_xdf = tmp_path / "rec.xdf"
    out_sidecar = tmp_path / "ingest.json"
    xdf_path, sc_path = run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        out_xdf,
        out_sidecar,
    )
    assert xdf_path.read_bytes().startswith(b"XDF:")
    sc = json.loads(sc_path.read_text())
    assert set(sc["ingest_map"]) == {"right_wrist", "object", "events"}


def test_captured_xdf_has_motion_samples(tmp_path):
    import pyxdf

    cfg = _config()
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        tmp_path / "rec.xdf",
        tmp_path / "ingest.json",
    )
    streams, _ = pyxdf.load_xdf(
        str(tmp_path / "rec.xdf"), dejitter_timestamps=False, synchronize_clocks=False
    )
    names = {s["info"]["name"][0] for s in streams}
    assert {"right_wrist", "object", "events"} <= names
    motion = next(s for s in streams if s["info"]["name"][0] == "right_wrist")
    assert len(motion["time_series"]) > 0


def _eeg_config():
    cfg = _config()
    cfg.eeg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"], rate_hz=200.0)
    return cfg


def test_capture_with_eeg_writes_eeg_stream(tmp_path):
    import pyxdf

    cfg = _eeg_config()
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        tmp_path / "rec.xdf",
        tmp_path / "ingest.json",
        eeg_source=MockEegSource(cfg.eeg),
    )
    streams, _ = pyxdf.load_xdf(
        str(tmp_path / "rec.xdf"), dejitter_timestamps=False, synchronize_clocks=False
    )
    eeg = next(s for s in streams if s["info"]["name"][0] == "eeg_amp0")
    assert int(eeg["info"]["channel_count"][0]) == 3
    assert len(eeg["time_series"]) > 0


def test_capture_without_eeg_has_no_eeg_stream(tmp_path):
    import pyxdf

    cfg = _config()  # no eeg
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource([(0.0, default_schedule()[0][1])]),
        tmp_path / "rec.xdf",
        tmp_path / "ingest.json",
    )
    streams, _ = pyxdf.load_xdf(
        str(tmp_path / "rec.xdf"), dejitter_timestamps=False, synchronize_clocks=False
    )
    assert not any(s["info"]["name"][0].startswith("eeg_") for s in streams)
