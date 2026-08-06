"""Throwaway test infra: synth raw session -> .xdf, for round-trip tests.

NOT shipped in the package public surface; lives under tests/ only.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

CLOCK_BASE: float = 1000.0
EVENT_PAYLOAD_KEYS: tuple[str, ...] = ("event_id", "label", "phase", "confidence", "notes")

_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")
_MOTION_CHANNEL_KEYS = ("x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality")


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


def _chunk(tag: int, content: bytes) -> bytes:
    body = struct.pack("<H", tag) + content
    return b"\x04" + struct.pack("<I", len(body)) + body


def _stream_header(stream_id: int, name: str, fmt: str, n_chan: int, srate: float) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<name>{name}</name><type>{name}</type>"
        f"<channel_count>{n_chan}</channel_count>"
        f"<nominal_srate>{srate}</nominal_srate>"
        f"<channel_format>{fmt}</channel_format></info>"
    )
    return _chunk(2, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def _samples_numeric(stream_id: int, stamps: list[float], rows: list[list[float]]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, row in zip(stamps, rows):
        out += b"\x08" + struct.pack("<d", ts)
        out += b"".join(struct.pack("<d", v) for v in row)
    return _chunk(3, out)


def _samples_string(stream_id: int, stamps: list[float], rows: list[str]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, s in zip(stamps, rows):
        encoded = s.encode("utf-8")
        out += b"\x08" + struct.pack("<d", ts)
        out += b"\x04" + struct.pack("<I", len(encoded)) + encoded
    return _chunk(3, out)


def _stream_footer(stream_id: int, stamps: list[float]) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<first_timestamp>{stamps[0]}</first_timestamp>"
        f"<last_timestamp>{stamps[-1]}</last_timestamp>"
        f"<sample_count>{len(stamps)}</sample_count></info>"
    )
    return _chunk(6, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def write_xdf(
    raw_dir: Path,
    xdf_path: Path,
    eeg: tuple[str, list[str], list[float], list[list[float]]] | None = None,
) -> None:
    blob = b"XDF:"
    blob += _chunk(1, b'<?xml version="1.0"?><info><version>1.0</version></info>')

    stream_id = 1
    for tracker in _TRACKERS:
        csv_data = _read_csv(raw_dir / f"streams/motion_{tracker}.csv")
        stamps = [float(r["timestamp_s"]) + CLOCK_BASE for r in csv_data]
        rows = [[float(r[k]) for k in _MOTION_CHANNEL_KEYS] for r in csv_data]
        blob += _stream_header(stream_id, tracker, "double64", len(_MOTION_CHANNEL_KEYS), 100.0)
        blob += _samples_numeric(stream_id, stamps, rows)
        blob += _stream_footer(stream_id, stamps)
        stream_id += 1

    ev_csv = _read_csv(raw_dir / "streams/events.csv")
    ev_stamps = [float(r["timestamp_s"]) + CLOCK_BASE for r in ev_csv]
    ev_payloads = [
        json.dumps(
            {
                "event_id": int(r["event_id"]),
                "label": r["label"],
                "phase": r["phase"],
                "confidence": float(r["confidence"]),
                "notes": r["notes"],
            },
            sort_keys=True,
        )
        for r in ev_csv
    ]
    blob += _stream_header(stream_id, "events", "string", 1, 0.0)
    blob += _samples_string(stream_id, ev_stamps, ev_payloads)
    blob += _stream_footer(stream_id, ev_stamps)

    if eeg is not None:
        eeg_id, labels, eeg_stamps, eeg_samples = eeg
        stamps = [t + CLOCK_BASE for t in eeg_stamps]
        blob += _stream_header(stream_id + 1, eeg_id, "double64", len(labels), 0.0)
        blob += _samples_numeric(stream_id + 1, stamps, eeg_samples)
        blob += _stream_footer(stream_id + 1, stamps)

    xdf_path.write_bytes(blob)


def build_sidecar(
    raw_dir: Path,
    eeg: tuple[str, list[str]] | None = None,
) -> dict[str, object]:
    session = json.loads((raw_dir / "session.json").read_text(encoding="utf-8"))
    consent = json.loads((raw_dir / "consent.json").read_text(encoding="utf-8"))
    device_config = json.loads((raw_dir / "device_config.json").read_text(encoding="utf-8"))
    channels = {k: i for i, k in enumerate(_MOTION_CHANNEL_KEYS)}
    ingest_map: dict[str, object] = {
        t: {"role": "motion", "tracker_id": t, "channels": dict(channels)} for t in _TRACKERS
    }
    ingest_map["events"] = {"role": "events"}

    if eeg is not None:
        eeg_id, labels = eeg
        ingest_map[eeg_id] = {
            "role": "eeg",
            "eeg_id": eeg_id,
            "channels": {label: i for i, label in enumerate(labels)},
        }

    return {
        "session": session,
        "consent": consent,
        "device_config": device_config,
        "ingest_map": ingest_map,
    }
