from __future__ import annotations

from dataclasses import dataclass, field

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.eeg_source import EegConfig
from htdp_capture.marker_source import MarkerEvent


class ConfigError(Exception):
    """Raised when a CaptureConfig is invalid."""


@dataclass
class CaptureConfig:
    trackers: list[str]
    session: dict[str, object]
    consent: dict[str, object]
    device_config: dict[str, object]
    rate_hz: float = 100.0
    duration_s: float = 2.0
    frame_rotation: tuple[float, float, float, float] | None = None
    schedule: list[tuple[float, MarkerEvent]] | None = field(default=None)
    eeg: EegConfig | None = None
    device_map: dict[str, str] | None = None

    def validate(self) -> None:
        if not self.trackers:
            raise ConfigError("at least one tracker is required")
        for t in self.trackers:
            if t not in TRACKER_IDS:
                raise ConfigError(f"tracker '{t}' not in contract {TRACKER_IDS}")
        if self.frame_rotation is not None and len(self.frame_rotation) != 4:
            raise ConfigError("frame_rotation must be a 4-tuple (w, x, y, z)")
        if self.rate_hz <= 0:
            raise ConfigError("rate_hz must be positive")
        if self.duration_s <= 0:
            raise ConfigError("duration_s must be positive")
        if self.eeg is not None:
            self._validate_eeg(self.eeg)
        if self.device_map is not None:
            self._validate_device_map(self.device_map)

    @staticmethod
    def _validate_eeg(eeg: EegConfig) -> None:
        if not eeg.eeg_id:
            raise ConfigError("eeg_id must be non-empty")
        if not eeg.channels:
            raise ConfigError("eeg.channels must be non-empty")
        if len(set(eeg.channels)) != len(eeg.channels):
            raise ConfigError("eeg.channels must not contain duplicate labels")
        if eeg.rate_hz <= 0:
            raise ConfigError("eeg.rate_hz must be positive")

    @staticmethod
    def _validate_device_map(device_map: dict[str, str]) -> None:
        if not device_map:
            raise ConfigError("device_map must be non-empty")
        if any(not serial for serial in device_map):
            raise ConfigError("device_map serial keys must be non-empty")
        for tracker_id in device_map.values():
            if tracker_id not in TRACKER_IDS:
                raise ConfigError(f"tracker '{tracker_id}' not in contract {TRACKER_IDS}")
        ids = list(device_map.values())
        if len(set(ids)) != len(ids):
            raise ConfigError("device_map must not map two serials to the same tracker_id")
