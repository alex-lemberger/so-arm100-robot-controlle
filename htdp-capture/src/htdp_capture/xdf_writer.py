from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from htdp_capture.contract import MOTION_CHANNELS


class XdfWriteError(Exception):
    """Raised on an invalid stream set (e.g. empty capture)."""


@dataclass
class CapturedStream:
    name: str
    fmt: str  # "double64" or "string"
    n_channels: int
    srate: float
    stamps: list[float]
    numeric: list[list[float]] | None = None
    strings: list[str] | None = None


def _chunk(tag: int, content: bytes) -> bytes:
    body = struct.pack("<H", tag) + content
    return b"\x04" + struct.pack("<I", len(body)) + body


def _channels_xml(n_channels: int) -> str:
    # Motion streams carry the contract labels; others get generic labels.
    if n_channels == len(MOTION_CHANNELS):
        labels = MOTION_CHANNELS
    else:
        labels = tuple(f"ch{i}" for i in range(n_channels))
    inner = "".join(f"<channel><label>{label}</label></channel>" for label in labels)
    return f"<desc><channels>{inner}</channels></desc>"


def _stream_header(stream_id: int, s: CapturedStream) -> bytes:
    xml = (
        '<?xml version="1.0"?><info>'
        f"<name>{s.name}</name><type>{s.name}</type>"
        f"<channel_count>{s.n_channels}</channel_count>"
        f"<nominal_srate>{s.srate}</nominal_srate>"
        f"<channel_format>{s.fmt}</channel_format>"
        f"{_channels_xml(s.n_channels)}</info>"
    )
    return _chunk(2, struct.pack("<I", stream_id) + xml.encode("utf-8"))


def _samples_numeric(stream_id: int, stamps: list[float], rows: list[list[float]]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, row in zip(stamps, rows, strict=True):
        out += b"\x08" + struct.pack("<d", ts)
        out += b"".join(struct.pack("<d", v) for v in row)
    return _chunk(3, out)


def _samples_string(stream_id: int, stamps: list[float], rows: list[str]) -> bytes:
    out = struct.pack("<I", stream_id) + b"\x04" + struct.pack("<I", len(stamps))
    for ts, value in zip(stamps, rows, strict=True):
        encoded = value.encode("utf-8")
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


def write_xdf(streams: list[CapturedStream], out_path: Path, *, force: bool = False) -> Path:
    if not streams:
        raise XdfWriteError("no streams to write")
    if out_path.exists() and not force:
        raise FileExistsError(f"{out_path} already exists (use force=True)")

    blob = b"XDF:"
    blob += _chunk(1, b'<?xml version="1.0"?><info><version>1.0</version></info>')
    for stream_id, s in enumerate(streams, start=1):
        if not s.stamps:
            raise XdfWriteError(f"stream '{s.name}' has no samples")
        blob += _stream_header(stream_id, s)
        if s.fmt == "string":
            assert s.strings is not None
            blob += _samples_string(stream_id, s.stamps, s.strings)
        else:
            assert s.numeric is not None
            blob += _samples_numeric(stream_id, s.stamps, s.numeric)
        blob += _stream_footer(stream_id, s.stamps)

    out_path.write_bytes(blob)
    return out_path
