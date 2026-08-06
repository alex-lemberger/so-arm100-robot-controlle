from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class IngestUnavailable(RuntimeError):
    """Raised when pyxdf is not installed."""


@dataclass
class XdfStream:
    name: str
    type: str
    channel_format: str
    time_stamps: list[float]
    time_series: list[list[float]] | list[str]


def load_xdf_streams(path: Path) -> dict[str, XdfStream]:
    try:
        import pyxdf  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestUnavailable("install with: uv sync --extra ingest") from exc

    # Keep recorded timestamps verbatim: pyxdf's default dejitter resamples them
    # onto a regression line, and clock-sync would shift them. Ingest must record
    # the LSL clock as captured; drift is detected downstream by `qc`, not here.
    streams, _ = pyxdf.load_xdf(str(path), dejitter_timestamps=False, synchronize_clocks=False)
    out: dict[str, XdfStream] = {}
    for s in streams:
        info = s["info"]
        fmt = str(info["channel_format"][0])
        ts = [float(t) for t in s["time_stamps"]]
        series: list[list[float]] | list[str]
        if fmt == "string":
            series = [str(row[0]) for row in s["time_series"]]
        else:
            series = [[float(v) for v in row] for row in s["time_series"]]
        name = str(info["name"][0])
        out[name] = XdfStream(
            name=name,
            type=str(info["type"][0]),
            channel_format=fmt,
            time_stamps=ts,
            time_series=series,
        )
    return out
