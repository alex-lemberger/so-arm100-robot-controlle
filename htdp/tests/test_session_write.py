from pathlib import Path

import pytest

from htdp.ingest.session import write_raw_folder
from htdp.schemas.models import Consent, Session
from htdp.validate import validate_session


def _session():
    return Session(
        session_id="real-0001",
        participant_id="p1",
        protocol_id="reach-grasp-place",
        consent_form_version="v1",
        device_config_id="vive-1",
        start_time_s=1000.0,
    )


def _motion_out():
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


def test_write_raw_folder_passes_validate(tmp_path: Path):
    out = write_raw_folder(
        tmp_path / "real-0001",
        session=_session(),
        consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1",
        motion_out=_motion_out(),
        event_rows=_events(),
        source_xdf_name="rec.xdf",
    )
    assert validate_session(out) == []
    assert (out / "video").is_dir()
    assert "rec.xdf" in (out / "notes.md").read_text(encoding="utf-8")


def test_write_raw_folder_refuses_overwrite_without_force(tmp_path: Path):
    kw = dict(
        session=_session(),
        consent=Consent(consent_form_version="v1"),
        device_config_id="vive-1",
        motion_out=_motion_out(),
        event_rows=_events(),
        source_xdf_name="rec.xdf",
    )
    write_raw_folder(tmp_path / "x", **kw)
    with pytest.raises(FileExistsError):
        write_raw_folder(tmp_path / "x", **kw)
    write_raw_folder(tmp_path / "x", force=True, **kw)  # ok
