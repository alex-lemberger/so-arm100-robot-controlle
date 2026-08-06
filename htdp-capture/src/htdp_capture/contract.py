from __future__ import annotations

MOTION_CHANNELS: tuple[str, ...] = (
    "x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality",
)
TRACKER_IDS: tuple[str, ...] = ("right_wrist", "left_wrist", "torso", "object")
EVENTS_STREAM_NAME: str = "events"
EVENT_LABELS: tuple[str, ...] = ("start", "grasp", "release", "place", "stop")
MOTION_CHANNEL_INDEX: dict[str, int] = {k: i for i, k in enumerate(MOTION_CHANNELS)}


def eeg_stream_name(eeg_id: str) -> str:
    return f"eeg_{eeg_id}"
