from __future__ import annotations


class ShapesortUnavailable(RuntimeError):
    """Raised when an optional shapesort dependency (opencv/whisper) is not installed."""

    def __init__(self, msg: str = "install with: uv sync --extra shapesort") -> None:
        super().__init__(msg)
