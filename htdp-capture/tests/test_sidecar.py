from htdp_capture.config import CaptureConfig
from htdp_capture.eeg_source import EegConfig
from htdp_capture.sidecar import build_sidecar


def _full_config(**over):
    session = {
        "session_id": "cap-0001",
        "participant_id": "p1",
        "protocol_id": "proto",
        "consent_form_version": "v1",
        "device_config_id": "vive-01",
        "start_time_s": 0.0,
    }
    consent = {"consent_form_version": "v1"}
    device_config = {"device_config_id": "vive-01"}
    base = dict(
        trackers=["right_wrist", "object"],
        session=session,
        consent=consent,
        device_config=device_config,
    )
    base.update(over)
    return CaptureConfig(**base)


def test_top_level_keys():
    sc = build_sidecar(_full_config())
    assert set(sc) >= {"session", "consent", "device_config", "ingest_map"}


def test_motion_entries_have_full_channel_map():
    sc = build_sidecar(_full_config())
    rw = sc["ingest_map"]["right_wrist"]
    assert rw["role"] == "motion"
    assert rw["tracker_id"] == "right_wrist"
    assert rw["channels"] == {
        "x_m": 0, "y_m": 1, "z_m": 2, "qw": 3,
        "qx": 4, "qy": 5, "qz": 6, "quality": 7,
    }


def test_events_entry_present():
    sc = build_sidecar(_full_config())
    assert sc["ingest_map"]["events"] == {"role": "events"}


def test_identity_frame_transform_is_omitted():
    sc = build_sidecar(_full_config(frame_rotation=(1.0, 0.0, 0.0, 0.0)))
    assert "frame_transform" not in sc


def test_nonidentity_frame_transform_present():
    sc = build_sidecar(_full_config(frame_rotation=(0.0, 1.0, 0.0, 0.0)))
    assert sc["frame_transform"] == {"rotation": [0.0, 1.0, 0.0, 0.0]}


def test_sidecar_satisfies_htdp_validate_sidecar():
    # The contract guard: htdp must accept the sidecar we emit.
    from htdp.ingest.session import validate_sidecar

    sc = build_sidecar(_full_config())
    parsed = validate_sidecar(sc)
    assert set(parsed.ingest_map.motion) == {"right_wrist", "object"}
    assert parsed.ingest_map.events_stream == "events"


def test_no_eeg_has_no_eeg_entry():
    sc = build_sidecar(_full_config())
    assert not any(k.startswith("eeg_") for k in sc["ingest_map"])


def test_eeg_entry_shape():
    sc = build_sidecar(_full_config(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"])))
    entry = sc["ingest_map"]["eeg_amp0"]
    assert entry == {
        "role": "eeg",
        "eeg_id": "amp0",
        "channels": {"Fp1": 0, "Fp2": 1, "C3": 2},
    }


def test_eeg_sidecar_satisfies_htdp_validate_sidecar():
    from htdp.ingest.session import validate_sidecar

    sc = build_sidecar(_full_config(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2"])))
    parsed = validate_sidecar(sc)
    assert "eeg_amp0" in parsed.ingest_map.eeg
    assert parsed.ingest_map.eeg["eeg_amp0"].eeg_id == "amp0"
