from __future__ import annotations

import time
from collections.abc import Callable

from htdp_capture.marker_source import MarkerEvent, MarkerSource


class ScriptedMarkerSource(MarkerSource):
    """Fires a fixed schedule of events at offsets from the first poll."""

    def __init__(
        self,
        schedule: list[tuple[float, MarkerEvent]],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._schedule = sorted(schedule, key=lambda item: item[0])
        self._clock = clock
        self._start: float | None = None
        self._idx = 0

    def poll(self) -> list[tuple[float, MarkerEvent]]:
        now = self._clock()
        if self._start is None:
            self._start = now
        elapsed = now - self._start
        due: list[tuple[float, MarkerEvent]] = []
        while self._idx < len(self._schedule) and self._schedule[self._idx][0] <= elapsed:
            offset, event = self._schedule[self._idx]
            due.append((self._start + offset, event))
            self._idx += 1
        return due


def default_schedule() -> list[tuple[float, MarkerEvent]]:
    return [
        (0.0, MarkerEvent(1, "start", "reach")),
        (0.5, MarkerEvent(2, "grasp", "grasp")),
        (1.0, MarkerEvent(3, "place", "transport")),
        (1.5, MarkerEvent(4, "release", "release")),
        (2.0, MarkerEvent(5, "stop", "done")),
    ]
