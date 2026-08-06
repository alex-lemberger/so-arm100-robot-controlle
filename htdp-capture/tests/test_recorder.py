import time

import pytest

pytest.importorskip("pylsl")

from htdp_capture.outlets import make_motion_outlet  # noqa: E402
from htdp_capture.recorder import RecorderError, StreamRecorder  # noqa: E402


def _wait_for_consumer(outlet, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not outlet.have_consumers() and time.monotonic() < deadline:
        time.sleep(0.02)


def test_missing_stream_raises():
    with pytest.raises(RecorderError):
        StreamRecorder("nonexistent_stream_xyz", "double64", 8, 100.0, timeout=0.5)


def test_drain_captures_all_pushed_samples():
    # Realistic streaming: connect the inlet, wait until the outlet sees the
    # consumer, THEN push a stream of samples and drain them all.
    outlet = make_motion_outlet("right_wrist", 100.0)
    rec = StreamRecorder("right_wrist", "double64", 8, 100.0, timeout=5.0)
    _wait_for_consumer(outlet)

    samples = [[float(i)] * 8 for i in range(5)]
    stamps = [1000.0 + i for i in range(5)]
    for sample, ts in zip(samples, stamps, strict=True):
        outlet.push_sample(sample, timestamp=ts)

    deadline = time.monotonic() + 5.0
    while len(rec.to_captured().stamps) < 5 and time.monotonic() < deadline:
        rec.drain()

    captured = rec.to_captured()
    assert captured.name == "right_wrist"
    assert captured.fmt == "double64"
    assert captured.numeric == samples
    assert captured.stamps == stamps
