from __future__ import annotations

import struct


def estimate_fs(timestamps: list[float]) -> float:
    if len(timestamps) < 2:
        raise ValueError("need at least two samples to estimate sampling frequency")
    span = timestamps[-1] - timestamps[0]
    if span <= 0:
        raise ValueError("zero or negative time span")
    return (len(timestamps) - 1) / span


def eeg_binary(samples: list[list[float]]) -> bytes:
    return b"".join(struct.pack("<f", v) for row in samples for v in row)


def vhdr_text(stem: str, labels: list[str], fs: float) -> str:
    interval = 1_000_000.0 / fs
    channel_lines = "\n".join(f"Ch{i}={label},,1,µV" for i, label in enumerate(labels, start=1))
    return (
        "Brain Vision Data Exchange Header File Version 1.0\n\n"
        "[Common Infos]\n"
        "Codepage=UTF-8\n"
        f"DataFile={stem}_eeg.eeg\n"
        f"MarkerFile={stem}_eeg.vmrk\n"
        "DataFormat=BINARY\n"
        "DataOrientation=MULTIPLEXED\n"
        f"NumberOfChannels={len(labels)}\n"
        f"SamplingInterval={interval}\n\n"
        "[Binary Infos]\n"
        "BinaryFormat=IEEE_FLOAT_32\n\n"
        "[Channel Infos]\n"
        f"{channel_lines}\n"
    )


def vmrk_text(stem: str) -> str:
    return (
        "Brain Vision Data Exchange Marker File, Version 1.0\n\n"
        "[Common Infos]\n"
        "Codepage=UTF-8\n"
        f"DataFile={stem}_eeg.eeg\n\n"
        "[Marker Infos]\n"
        "Mk1=New Segment,,1,1,0\n"
    )


EEG_CHANNELS_HEADER: list[str] = ["name", "type", "units"]


def eeg_channels_rows(labels: list[str]) -> list[dict[str, str]]:
    return [{"name": label, "type": "EEG", "units": "µV"} for label in labels]


def eeg_json(task: str, n_channels: int, fs: float) -> dict[str, object]:
    return {
        "TaskName": task,
        "SamplingFrequency": fs,
        "EEGReference": "n/a",
        "PowerLineFrequency": "n/a",
        "SoftwareFilters": "n/a",
        "EEGChannelCount": n_channels,
        "RecordingType": "continuous",
    }
