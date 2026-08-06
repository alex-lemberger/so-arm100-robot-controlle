from __future__ import annotations

from dataclasses import dataclass, field

from htdp.ingest.reader import XdfStream

CONTRACT_TRACKERS: tuple[str, ...] = ("right_wrist", "left_wrist", "torso", "object")
_MOTION_CHANNEL_KEYS: tuple[str, ...] = (
    "x_m",
    "y_m",
    "z_m",
    "qw",
    "qx",
    "qy",
    "qz",
    "quality",
)


class MappingError(Exception):
    """Raised when the ingest_map does not resolve against the contract or XDF."""


@dataclass
class MotionStreamMap:
    tracker_id: str
    channels: dict[str, int]


@dataclass
class EegStreamMap:
    eeg_id: str
    channels: dict[str, int]


@dataclass
class IngestMap:
    motion: dict[str, MotionStreamMap]
    events_stream: str
    eeg: dict[str, EegStreamMap] = field(default_factory=dict)


def parse_ingest_map(raw: dict[str, object]) -> IngestMap:
    motion: dict[str, MotionStreamMap] = {}
    events_streams: list[str] = []
    eeg: dict[str, EegStreamMap] = {}
    for stream_name, entry in raw.items():
        if not isinstance(entry, dict):
            raise MappingError(f"ingest_map entry for '{stream_name}' must be an object")
        role = entry.get("role")
        if role == "events":
            events_streams.append(stream_name)
        elif role == "motion":
            tracker_id = entry.get("tracker_id")
            if tracker_id not in CONTRACT_TRACKERS:
                raise MappingError(
                    f"stream '{stream_name}' tracker_id '{tracker_id}' "
                    f"not in contract trackers {CONTRACT_TRACKERS}"
                )
            channels = entry.get("channels")
            if not isinstance(channels, dict):
                raise MappingError(f"stream '{stream_name}' missing 'channels' map")
            missing = [k for k in _MOTION_CHANNEL_KEYS if k not in channels]
            if missing:
                raise MappingError(
                    f"stream '{stream_name}' channels missing keys: {', '.join(missing)}"
                )
            motion[stream_name] = MotionStreamMap(
                tracker_id=str(tracker_id),
                channels={k: int(channels[k]) for k in _MOTION_CHANNEL_KEYS},
            )
        elif role == "eeg":
            eeg_id = entry.get("eeg_id")
            if not eeg_id or not isinstance(eeg_id, str):
                raise MappingError(f"stream '{stream_name}' eeg entry needs non-empty 'eeg_id'")
            channels = entry.get("channels")
            if not isinstance(channels, dict) or not channels:
                raise MappingError(f"stream '{stream_name}' eeg entry needs non-empty 'channels'")
            eeg[stream_name] = EegStreamMap(
                eeg_id=eeg_id,
                channels={str(k): int(v) for k, v in channels.items()},
            )
        else:
            raise MappingError(f"stream '{stream_name}' has unknown role '{role}'")

    if len(events_streams) != 1:
        raise MappingError(
            f"ingest_map must declare exactly one 'events' stream, found {len(events_streams)}"
        )
    if not motion:
        raise MappingError("ingest_map must declare at least one 'motion' stream")
    return IngestMap(motion=motion, events_stream=events_streams[0], eeg=eeg)


def extract_motion(stream: XdfStream, m: MotionStreamMap) -> list[dict[str, object]]:
    if stream.channel_format == "string":
        raise MappingError(f"motion stream '{stream.name}' must be numeric, got string format")
    rows: list[dict[str, object]] = []
    for ts, sample in zip(stream.time_stamps, stream.time_series):
        assert isinstance(sample, list)
        row: dict[str, object] = {"raw_ts": float(ts), "tracker_id": m.tracker_id}
        for key in _MOTION_CHANNEL_KEYS:
            idx = m.channels[key]
            if idx >= len(sample):
                raise MappingError(
                    f"stream '{stream.name}' channel '{key}' index {idx} "
                    f"out of range (sample has {len(sample)} channels)"
                )
            row[key] = float(sample[idx])
        rows.append(row)
    return rows


def extract_eeg(stream: XdfStream, m: EegStreamMap) -> tuple[list[str], list[dict[str, object]]]:
    if stream.channel_format == "string":
        raise MappingError(f"eeg stream '{stream.name}' must be numeric, got string format")
    labels = list(m.channels)
    rows: list[dict[str, object]] = []
    for ts, sample in zip(stream.time_stamps, stream.time_series):
        assert isinstance(sample, list)
        row: dict[str, object] = {"raw_ts": float(ts)}
        for label in labels:
            idx = m.channels[label]
            if idx >= len(sample):
                raise MappingError(
                    f"eeg stream '{stream.name}' channel '{label}' index {idx} "
                    f"out of range (sample has {len(sample)} channels)"
                )
            row[label] = float(sample[idx])
        rows.append(row)
    return labels, rows
