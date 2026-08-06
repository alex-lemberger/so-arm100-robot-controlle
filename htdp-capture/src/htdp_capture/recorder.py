from __future__ import annotations

from pylsl import StreamInlet, proc_none, resolve_byprop

from htdp_capture.xdf_writer import CapturedStream


class RecorderError(Exception):
    """Raised when a stream cannot be resolved."""


class StreamRecorder:
    """Resolves one named LSL stream and drains its samples into buffers."""

    def __init__(
        self,
        name: str,
        fmt: str,
        n_channels: int,
        srate: float,
        *,
        timeout: float = 5.0,
    ) -> None:
        results = resolve_byprop("name", name, timeout=timeout)
        if not results:
            raise RecorderError(f"LSL stream '{name}' not found within {timeout}s")
        # No clock-sync, no dejitter: keep timestamps verbatim (htdp reads them as-is).
        self._inlet = StreamInlet(results[0], processing_flags=proc_none)
        # Open the connection eagerly so the outlet registers this consumer BEFORE
        # any samples are pushed. Lazy connection (on first pull) drops samples that
        # were pushed before the inlet finished connecting.
        self._inlet.open_stream(timeout=timeout)
        self._name = name
        self._fmt = fmt
        self._n_channels = n_channels
        self._srate = srate
        self._stamps: list[float] = []
        self._numeric: list[list[float]] = []
        self._strings: list[str] = []

    def drain(self) -> None:
        while True:
            sample, ts = self._inlet.pull_sample(timeout=0.5)
            if sample is None:
                break
            self._stamps.append(float(ts))
            if self._fmt == "string":
                self._strings.append(str(sample[0]))
            else:
                self._numeric.append([float(v) for v in sample])

    def to_captured(self) -> CapturedStream:
        return CapturedStream(
            name=self._name,
            fmt=self._fmt,
            n_channels=self._n_channels,
            srate=self._srate,
            stamps=self._stamps,
            numeric=self._numeric if self._fmt != "string" else None,
            strings=self._strings if self._fmt == "string" else None,
        )
