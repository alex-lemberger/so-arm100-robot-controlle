from __future__ import annotations


class LearnUnavailable(RuntimeError):
    """Raised when an optional learning dependency (torch/mujoco) is not installed."""

    def __init__(self, msg: str = "install with: uv sync --extra learn") -> None:
        super().__init__(msg)
