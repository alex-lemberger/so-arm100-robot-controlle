from pathlib import Path

from htdp.ingest.session import write_raw_folder
from htdp.schemas.models import Consent, DeviceConfig, Session
from htdp.validate import validate_session


def _session():
    return Session(
        session_id="real-0001",
        participant_id="p1",
        protocol_id="reach-grasp-place",
        consent_form_version="v1",
        device_config_id="vive-1",
        start_time_s=0.0,
    )


def _motion():
    return {
        "right_wrist": [
            {
                "timestamp_s": 0.0,
                "tracker_id": "right_wrist",
                "x_m": 0.1,
                "y_m": 0.2,
                "z_m": 0.9,
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "quality": 1.0,
                "defect_tag": "",
            },
        ],
    }


def _events():
    return [
        {
            "timestamp_s": 0.0,
            "event_id": 0,
            "label": "start",
            "phase": "approach",
            "source": "real",
            "confidence": 1.0,
            "notes": "",
        }
    ]


def test_write_raw_folder_writes_eeg_and_validates(tmp_path: Path):
    eeg_out = {"eeg": (["Fp1", "Cz"], [{"timestamp_s": 0.0, "Fp1": 1.0, "Cz": 2.0}])}
    out = write_raw_folder(
        tmp_path / "real-0001",
        session=_session(),
        consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1",
        motion_out=_motion(),
        event_rows=_events(),
        source_xdf_name="rec.xdf",
        eeg_out=eeg_out,
    )
    eeg_csv = out / "streams" / "eeg_eeg.csv"
    assert eeg_csv.exists()
    assert eeg_csv.read_text(encoding="utf-8").splitlines()[0] == "timestamp_s,Fp1,Cz"
    device = DeviceConfig.model_validate_json((out / "device_config.json").read_text())
    assert any(s.role == "eeg" and s.name == "eeg" for s in device.streams)
    assert validate_session(out) == []


def test_write_raw_folder_without_eeg_unchanged(tmp_path: Path):
    out = write_raw_folder(
        tmp_path / "real-0001",
        session=_session(),
        consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1",
        motion_out=_motion(),
        event_rows=_events(),
        source_xdf_name="rec.xdf",
    )
    assert not list((out / "streams").glob("eeg_*.csv"))
    assert validate_session(out) == []
