from __future__ import annotations

import math
import time
from collections.abc import Callable

from htdp_capture.eeg_source import EegConfig, EegSource


class MockEegSource(EegSource):
    """Hardware-free synthetic EEG: per-channel deterministic sine."""

    def __init__(
        self,
        config: EegConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._channels = list(config.channels)
        self._clock = clock
        self._frame = 0

    def poll(self) -> list[tuple[float, list[float]]]:
        frame = self._frame
        t = self._clock()
        sample = [math.sin(frame * 0.1 + i) for i in range(len(self._channels))]
        self._frame += 1
        return [(t, sample)]
