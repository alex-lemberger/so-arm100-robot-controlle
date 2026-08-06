import pytest

from htdp_capture.config import CaptureConfig, ConfigError
from htdp_capture.eeg_source import EegConfig


def _cfg(**over):
    base = dict(
        trackers=["right_wrist"],
        session={"session_id": "s"},
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "d"},
    )
    base.update(over)
    return CaptureConfig(**base)


def test_valid_config_passes():
    _cfg().validate()  # no raise


def test_empty_trackers_rejected():
    with pytest.raises(ConfigError):
        _cfg(trackers=[]).validate()


def test_unknown_tracker_rejected():
    with pytest.raises(ConfigError):
        _cfg(trackers=["nose"]).validate()


def test_bad_frame_rotation_length_rejected():
    with pytest.raises(ConfigError):
        _cfg(frame_rotation=(1.0, 0.0, 0.0)).validate()


def test_good_frame_rotation_passes():
    _cfg(frame_rotation=(1.0, 0.0, 0.0, 0.0)).validate()


def _eeg_cfg(**over):
    base = dict(
        trackers=["right_wrist"],
        session={"session_id": "s"},
        consent={"consent_form_version": "v1"},
        device_config={"device_config_id": "d"},
    )
    base.update(over)
    return CaptureConfig(**base)


def test_no_eeg_is_valid():
    _eeg_cfg().validate()  # eeg defaults to None


def test_valid_eeg_passes():
    _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2"])).validate()


def test_empty_eeg_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="", channels=["Fp1"])).validate()


def test_empty_channels_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=[])).validate()


def test_duplicate_channel_labels_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1", "Fp1"])).validate()


def test_bad_eeg_rate_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(eeg=EegConfig(eeg_id="amp0", channels=["Fp1"], rate_hz=0.0)).validate()


def test_no_device_map_is_valid():
    _eeg_cfg().validate()  # device_map defaults to None


def test_valid_device_map_passes():
    _eeg_cfg(device_map={"LHR-A": "right_wrist", "LHR-B": "object"}).validate()


def test_empty_device_map_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={}).validate()


def test_device_map_bad_tracker_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"LHR-A": "elbow"}).validate()


def test_device_map_duplicate_tracker_id_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"LHR-A": "right_wrist", "LHR-B": "right_wrist"}).validate()


def test_device_map_empty_serial_rejected():
    with pytest.raises(ConfigError):
        _eeg_cfg(device_map={"": "right_wrist"}).validate()
