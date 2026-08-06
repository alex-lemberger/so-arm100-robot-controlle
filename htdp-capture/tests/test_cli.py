import json

import pytest

pytest.importorskip("pylsl")

from htdp_capture.cli import main  # noqa: E402


def _write_config(path):
    path.write_text(json.dumps({
        "trackers": ["right_wrist"],
        "rate_hz": 200.0,
        "duration_s": 0.2,
        "session": {
            "session_id": "cap-0001", "participant_id": "p1", "protocol_id": "proto",
            "consent_form_version": "v1", "device_config_id": "vive-01", "start_time_s": 0.0,
        },
        "consent": {"consent_form_version": "v1"},
        "device_config": {"device_config_id": "vive-01"},
    }))


def test_record_writes_outputs(tmp_path):
    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    rc = main(["record", "--config", str(cfg), "--out-xdf", str(xdf),
               "--out-sidecar", str(sidecar)])
    assert rc == 0
    assert xdf.read_bytes().startswith(b"XDF:")
    assert "ingest_map" in json.loads(sidecar.read_text())


def test_record_force_overwrites(tmp_path):
    cfg = tmp_path / "cfg.json"
    _write_config(cfg)
    xdf = tmp_path / "rec.xdf"
    sidecar = tmp_path / "ingest.json"
    args = ["record", "--config", str(cfg), "--out-xdf", str(xdf), "--out-sidecar", str(sidecar)]
    assert main(args) == 0
    assert main(args + ["--force"]) == 0
