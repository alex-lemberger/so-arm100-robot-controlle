from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    t: float
    pos: tuple[float, float, float]
    quat: tuple[float, float, float, float]  # w, x, y, z
    quality: float


class PoseSource(ABC):
    @abstractmethod
    def trackers(self) -> list[str]: ...

    @abstractmethod
    def poll(self) -> dict[str, Pose]: ...

    def close(self) -> None:  # default no-op; hardware sources override
        return None
