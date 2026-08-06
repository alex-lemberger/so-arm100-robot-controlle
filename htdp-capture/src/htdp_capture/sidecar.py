from __future__ import annotations

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNEL_INDEX, eeg_stream_name

_IDENTITY = (1.0, 0.0, 0.0, 0.0)


def build_sidecar(config: CaptureConfig) -> dict[str, object]:
    ingest_map: dict[str, object] = {
        tracker: {
            "role": "motion",
            "tracker_id": tracker,
            "channels": dict(MOTION_CHANNEL_INDEX),
        }
        for tracker in config.trackers
    }
    ingest_map[EVENTS_STREAM_NAME] = {"role": "events"}

    if config.eeg is not None:
        ingest_map[eeg_stream_name(config.eeg.eeg_id)] = {
            "role": "eeg",
            "eeg_id": config.eeg.eeg_id,
            "channels": {label: i for i, label in enumerate(config.eeg.channels)},
        }

    sidecar: dict[str, object] = {
        "session": config.session,
        "consent": config.consent,
        "device_config": config.device_config,
        "ingest_map": ingest_map,
    }
    if config.frame_rotation is not None and tuple(config.frame_rotation) != _IDENTITY:
        sidecar["frame_transform"] = {"rotation": list(config.frame_rotation)}
    return sidecar
