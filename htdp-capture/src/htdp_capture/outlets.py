from __future__ import annotations

from pylsl import StreamInfo, StreamOutlet, cf_double64, cf_string

from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS, eeg_stream_name


def make_motion_outlet(tracker_id: str, rate_hz: float) -> StreamOutlet:
    info = StreamInfo(
        name=tracker_id,
        type="motion",
        channel_count=len(MOTION_CHANNELS),
        nominal_srate=rate_hz,
        channel_format=cf_double64,
        source_id=f"htdp_capture_motion_{tracker_id}",
    )
    channels = info.desc().append_child("channels")
    for label in MOTION_CHANNELS:
        channels.append_child("channel").append_child_value("label", label)
    return StreamOutlet(info)


def make_events_outlet() -> StreamOutlet:
    info = StreamInfo(
        name=EVENTS_STREAM_NAME,
        type="Markers",
        channel_count=1,
        nominal_srate=0.0,
        channel_format=cf_string,
        source_id="htdp_capture_events",
    )
    return StreamOutlet(info)


def make_eeg_outlet(eeg_id: str, labels: list[str], rate_hz: float) -> StreamOutlet:
    info = StreamInfo(
        name=eeg_stream_name(eeg_id),
        type="eeg",
        channel_count=len(labels),
        nominal_srate=rate_hz,
        channel_format=cf_double64,
        source_id=f"htdp_capture_eeg_{eeg_id}",
    )
    channels = info.desc().append_child("channels")
    for label in labels:
        channels.append_child("channel").append_child_value("label", label)
    return StreamOutlet(info)
