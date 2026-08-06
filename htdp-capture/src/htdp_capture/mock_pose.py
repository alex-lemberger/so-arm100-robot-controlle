from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.pose_source import Pose, PoseSource


class MockPoseSource(PoseSource):
    """Hardware-free synthetic pose source: deterministic circular motion."""

    def __init__(
        self,
        trackers: Iterable[str],
        rate_hz: float = 100.0,
        dropout_frames: set[int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        tlist = list(trackers)
        for t in tlist:
            if t not in TRACKER_IDS:
                raise ValueError(f"tracker '{t}' not in contract {TRACKER_IDS}")
        self._trackers = tlist
        self._rate_hz = rate_hz
        self._dropout = set(dropout_frames or set())
        self._clock = clock
        self._frame = 0

    def trackers(self) -> list[str]:
        return list(self._trackers)

    def poll(self) -> dict[str, Pose]:
        frame = self._frame
        t = self._clock()
        quality = 0.0 if frame in self._dropout else 1.0
        out: dict[str, Pose] = {}
        for i, tracker in enumerate(self._trackers):
            phase = frame * 0.1 + i
            pos = (math.cos(phase), math.sin(phase), 0.5)
            out[tracker] = Pose(t=t, pos=pos, quat=(1.0, 0.0, 0.0, 0.0), quality=quality)
        self._frame += 1
        return out
