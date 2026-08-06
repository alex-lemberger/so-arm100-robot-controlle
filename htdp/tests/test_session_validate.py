import pytest
from pydantic import ValidationError

from htdp.ingest.frame import IDENTITY
from htdp.ingest.mapping import MappingError
from htdp.ingest.session import validate_sidecar

_CH = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _sidecar():
    return {
        "session": {
            "session_id": "real-0001",
            "participant_id": "p1",
            "protocol_id": "reach-grasp-place",
            "consent_form_version": "v1",
            "device_config_id": "vive-1",
            "start_time_s": 0.0,
        },
        "consent": {"consent_form_version": "v1"},
        "device_config": {"device_config_id": "vive-1"},
        "ingest_map": {
            "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CH)},
            "marker": {"role": "events"},
        },
    }


def test_validate_sidecar_ok_defaults_to_identity_rotation():
    parsed = validate_sidecar(_sidecar())
    assert parsed.session.session_id == "real-0001"
    assert parsed.ingest_map.events_stream == "marker"
    assert parsed.rotation == IDENTITY


def test_validate_sidecar_reads_frame_transform():
    sc = _sidecar()
    sc["frame_transform"] = {"rotation": [0.0, 1.0, 0.0, 0.0]}
    assert validate_sidecar(sc).rotation == (0.0, 1.0, 0.0, 0.0)


def test_validate_sidecar_bad_session_raises_validation_error():
    sc = _sidecar()
    del sc["session"]["session_id"]
    with pytest.raises(ValidationError):
        validate_sidecar(sc)


def test_validate_sidecar_bad_map_raises_mapping_error():
    sc = _sidecar()
    sc["ingest_map"]["wrist"]["tracker_id"] = "nose"
    with pytest.raises(MappingError):
        validate_sidecar(sc)
