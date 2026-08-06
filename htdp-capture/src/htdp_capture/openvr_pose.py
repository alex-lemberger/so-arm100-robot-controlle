from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from htdp_capture.contract import TRACKER_IDS
from htdp_capture.openvr_convert import matrix_to_pos_quat, tracking_to_quality
from htdp_capture.pose_source import Pose, PoseSource


@dataclass(frozen=True)
class DevicePose:
    valid: bool
    connected: bool
    result: int
    matrix: Sequence[Sequence[float]]


class SystemHandle(Protocol):
    def device_poses(self) -> Sequence[DevicePose]: ...
    def serial(self, index: int) -> str: ...
    def shutdown(self) -> None: ...


def _validate_device_map(device_map: dict[str, str]) -> None:
    if not device_map:
        raise ValueError("device_map must be non-empty")
    if any(not serial for serial in device_map):
        raise ValueError("device_map serial keys must be non-empty")
    for tracker_id in device_map.values():
        if tracker_id not in TRACKER_IDS:
            raise ValueError(f"tracker '{tracker_id}' not in contract {TRACKER_IDS}")
    ids = list(device_map.values())
    if len(set(ids)) != len(ids):
        raise ValueError("device_map must not map two serials to the same tracker_id")


class OpenVRPoseSource(PoseSource):
    """Reads VIVE tracker poses from OpenVR through an injectable system handle.

    The real OpenVR system is built lazily only when no ``system`` is injected,
    so this module imports (and its tests run) on platforms where ``import openvr``
    fails (e.g. Apple Silicon). Tests inject a fake ``SystemHandle``.
    """

    def __init__(
        self,
        device_map: dict[str, str],
        *,
        system: SystemHandle | None = None,
        ok_result: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        _validate_device_map(device_map)
        self._device_map = dict(device_map)
        self._clock = clock

        if system is None:
            import openvr  # type: ignore[import-not-found]  # lazy; real-hardware path only (arm64 import fails, no stubs)

            self._system: SystemHandle = _OpenVRSystem(openvr)
            self._ok_result = int(openvr.TrackingResult_Running_OK)
            self._owns_system = True
        else:
            if ok_result is None:
                raise ValueError("ok_result is required when a system is injected")
            self._system = system
            self._ok_result = ok_result
            self._owns_system = False

    def trackers(self) -> list[str]:
        return sorted(self._device_map.values())

    def poll(self) -> dict[str, Pose]:
        t = self._clock()
        out: dict[str, Pose] = {}
        poses = self._system.device_poses()
        for index, dp in enumerate(poses):
            if not dp.connected:
                continue
            tracker_id = self._device_map.get(self._system.serial(index))
            if tracker_id is None:
                continue
            pos, quat = matrix_to_pos_quat(dp.matrix)
            quality = tracking_to_quality(dp.valid, dp.result, self._ok_result)
            out[tracker_id] = Pose(t=t, pos=pos, quat=quat, quality=quality)
        return out

    def close(self) -> None:
        if self._owns_system:
            self._system.shutdown()


class _OpenVRSystem:
    """Thin real-OpenVR wrapper (live-hardware mile; not unit-tested).

    Built only from ``OpenVRPoseSource.__init__`` when no system is injected.
    ``openvr`` is passed in already-imported so this class has no module-level
    dependency on it.
    """

    def __init__(self, openvr: object) -> None:
        self._openvr = openvr
        self._system = openvr.init(openvr.VRApplication_Background)  # type: ignore[attr-defined]
        self._count = int(openvr.k_unMaxTrackedDeviceCount)  # type: ignore[attr-defined]
        self._origin = openvr.TrackingUniverseStanding  # type: ignore[attr-defined]
        self._pose_array_t = openvr.TrackedDevicePose_t * self._count  # type: ignore[attr-defined]
        self._serial_prop = openvr.Prop_SerialNumber_String  # type: ignore[attr-defined]

    def device_poses(self) -> Sequence[DevicePose]:
        arr = self._pose_array_t()
        self._system.getDeviceToAbsoluteTrackingPose(self._origin, 0.0, arr)
        result: list[DevicePose] = []
        for p in arr:
            m = p.mDeviceToAbsoluteTracking.m
            matrix = [[float(m[r][c]) for c in range(4)] for r in range(3)]
            result.append(
                DevicePose(
                    valid=bool(p.bPoseIsValid),
                    connected=bool(p.bDeviceIsConnected),
                    result=int(p.eTrackingResult),
                    matrix=matrix,
                )
            )
        return result

    def serial(self, index: int) -> str:
        return str(self._system.getStringTrackedDeviceProperty(index, self._serial_prop))

    def shutdown(self) -> None:
        self._openvr.shutdown()  # type: ignore[attr-defined]
