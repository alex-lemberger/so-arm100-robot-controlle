from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerEvent:
    event_id: int
    label: str
    phase: str
    confidence: float = 1.0
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "label": self.label,
                "phase": self.phase,
                "confidence": self.confidence,
                "notes": self.notes,
            },
            sort_keys=True,
        )


class MarkerSource(ABC):
    @abstractmethod
    def poll(self) -> list[tuple[float, MarkerEvent]]: ...

    def close(self) -> None:
        return None
