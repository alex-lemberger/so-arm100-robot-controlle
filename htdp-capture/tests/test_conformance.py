import csv

import pytest

pytest.importorskip("pylsl")
pytest.importorskip("pyxdf")
ingest = pytest.importorskip("htdp.ingest.session")

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
        duration_s=0.4,
    )


def test_capture_roundtrips_through_htdp_ingest(tmp_path):
    cfg = _config()
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
    )

    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)

    # Raw session structure exists with per-tracker motion + events.
    assert (raw / "session.json").is_file()
    assert (raw / "streams" / "motion_right_wrist.csv").is_file()
    assert (raw / "streams" / "motion_object.csv").is_file()
    assert (raw / "streams" / "events.csv").is_file()

    # Motion rows carry the contract columns, quality preserved, timestamps rebased to >= 0.
    with (raw / "streams" / "motion_right_wrist.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 0
    assert set(rows[0]) >= {
        "timestamp_s", "tracker_id", "x_m", "y_m", "z_m",
        "qw", "qx", "qy", "qz", "quality", "defect_tag",
    }
    assert rows[0]["tracker_id"] == "right_wrist"
    assert all(float(r["quality"]) == 1.0 for r in rows)
    assert min(float(r["timestamp_s"]) for r in rows) >= 0.0


def test_dropout_quality_survives_roundtrip(tmp_path):
    cfg = _config()
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz, dropout_frames=set(range(1000))),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
    )
    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)
    with (raw / "streams" / "motion_right_wrist.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(float(r["quality"]) == 0.0 for r in rows)


def test_capture_with_eeg_roundtrips_through_htdp_ingest(tmp_path):
    cfg = _config()
    cfg.eeg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"], rate_hz=200.0)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    run_capture(
        cfg,
        MockPoseSource(cfg.trackers, rate_hz=cfg.rate_hz),
        ScriptedMarkerSource(default_schedule()),
        xdf,
        sidecar,
        eeg_source=MockEegSource(cfg.eeg),
    )

    raw = tmp_path / "raw" / "cap-0001"
    ingest.ingest_xdf(xdf, sidecar, raw)

    # Motion + events still land (eeg is additive).
    assert (raw / "streams" / "motion_right_wrist.csv").is_file()
    assert (raw / "streams" / "events.csv").is_file()

    # EEG CSV exists with the label columns + timestamp.
    eeg_csv = raw / "streams" / "eeg_amp0.csv"
    assert eeg_csv.is_file()
    with eeg_csv.open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) > 0
    assert set(rows[0]) == {"timestamp_s", "Fp1", "Fp2", "C3"}
    # Per-channel sine => columns are not all identical within a row.
    assert len({rows[0]["Fp1"], rows[0]["Fp2"], rows[0]["C3"]}) > 1
    # Timestamps rebased to motion t0 (>= 0).
    assert min(float(r["timestamp_s"]) for r in rows) >= 0.0
