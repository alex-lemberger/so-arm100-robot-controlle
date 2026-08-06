from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EegConfig:
    eeg_id: str
    channels: list[str]
    rate_hz: float = 250.0


class EegSource(ABC):
    @abstractmethod
    def poll(self) -> list[tuple[float, list[float]]]: ...

    def close(self) -> None:  # default no-op; hardware sources override
        return None
