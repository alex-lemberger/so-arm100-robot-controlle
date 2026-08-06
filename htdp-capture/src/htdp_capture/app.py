from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from pylsl import StreamOutlet

from htdp_capture.config import CaptureConfig
from htdp_capture.contract import EVENTS_STREAM_NAME, MOTION_CHANNELS, eeg_stream_name
from htdp_capture.eeg_source import EegSource
from htdp_capture.marker_source import MarkerSource
from htdp_capture.outlets import make_eeg_outlet, make_events_outlet, make_motion_outlet
from htdp_capture.pose_source import PoseSource
from htdp_capture.recorder import StreamRecorder
from htdp_capture.sidecar import build_sidecar
from htdp_capture.xdf_writer import CapturedStream, XdfWriteError, write_xdf


def _wait_for_consumers(
    outlets: list[StreamOutlet], timeout: float, sleep: Callable[[float], None]
) -> None:
    """Block until every outlet has a connected consumer (its recorder inlet).

    Samples pushed before an inlet connects are dropped, so the capture loop must
    not start pushing until all consumers are present.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(o.have_consumers() for o in outlets):
            return
        sleep(0.02)


def run_capture(
    config: CaptureConfig,
    pose_source: PoseSource,
    marker_source: MarkerSource,
    out_xdf: Path,
    out_sidecar: Path,
    *,
    eeg_source: EegSource | None = None,
    force: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    config.validate()
    if config.eeg is not None and eeg_source is None:
        raise ValueError("config.eeg is set but no eeg_source was provided")

    motion_outlets = {t: make_motion_outlet(t, config.rate_hz) for t in config.trackers}
    events_outlet = make_events_outlet()

    # Creating a StreamRecorder opens its inlet, registering it as a consumer.
    motion_recorders = {
        t: StreamRecorder(t, "double64", len(MOTION_CHANNELS), config.rate_hz)
        for t in config.trackers
    }
    events_recorder = StreamRecorder(EVENTS_STREAM_NAME, "string", 1, 0.0)

    eeg_outlet: StreamOutlet | None = None
    eeg_recorder: StreamRecorder | None = None
    if config.eeg is not None:
        eeg_outlet = make_eeg_outlet(config.eeg.eeg_id, config.eeg.channels, config.eeg.rate_hz)
        eeg_recorder = StreamRecorder(
            eeg_stream_name(config.eeg.eeg_id),
            "double64",
            len(config.eeg.channels),
            config.eeg.rate_hz,
        )

    outlets = [*motion_outlets.values(), events_outlet]
    if eeg_outlet is not None:
        outlets.append(eeg_outlet)
    # Do not push until every outlet sees its consumer, or early samples are lost.
    _wait_for_consumers(outlets, timeout=5.0, sleep=sleep)

    period = 1.0 / config.rate_hz
    start = clock()
    while clock() - start < config.duration_s:
        for tracker, pose in pose_source.poll().items():
            row = [*pose.pos, *pose.quat, pose.quality]
            motion_outlets[tracker].push_sample(row, timestamp=pose.t)
        for ts, event in marker_source.poll():
            events_outlet.push_sample([event.to_json()], timestamp=ts)
        if eeg_source is not None and eeg_outlet is not None:
            for ts, sample in eeg_source.poll():
                eeg_outlet.push_sample(sample, timestamp=ts)
        for rec in motion_recorders.values():
            rec.drain()
        events_recorder.drain()
        if eeg_recorder is not None:
            eeg_recorder.drain()
        sleep(period)

    # Final drain to collect any samples still in flight.
    for rec in motion_recorders.values():
        rec.drain()
    events_recorder.drain()
    if eeg_recorder is not None:
        eeg_recorder.drain()
    pose_source.close()
    marker_source.close()
    if eeg_source is not None:
        eeg_source.close()

    streams: list[CapturedStream] = [motion_recorders[t].to_captured() for t in config.trackers]
    streams.append(events_recorder.to_captured())
    if eeg_recorder is not None:
        streams.append(eeg_recorder.to_captured())

    if all(not s.stamps for s in streams[: len(config.trackers)]):
        raise XdfWriteError("no motion samples captured")

    write_xdf(streams, out_xdf, force=force)
    out_sidecar.write_text(json.dumps(build_sidecar(config), indent=2), encoding="utf-8")
    return out_xdf, out_sidecar
