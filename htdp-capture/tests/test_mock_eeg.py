import math

from htdp_capture.eeg_source import EegConfig
from htdp_capture.mock_eeg import MockEegSource


def _fixed_clock():
    state = {"t": 0.0}

    def clock() -> float:
        state["t"] += 0.004
        return state["t"]

    return clock


def test_poll_returns_one_sample_with_one_value_per_channel():
    cfg = EegConfig(eeg_id="amp0", channels=["Fp1", "Fp2", "C3"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    batch = src.poll()
    assert len(batch) == 1
    ts, sample = batch[0]
    assert isinstance(ts, float)
    assert len(sample) == 3


def test_first_frame_values_are_per_channel_sine():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b", "c", "d"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    _, sample = src.poll()[0]
    assert sample == [math.sin(0 * 0.1 + i) for i in range(4)]


def test_channels_are_distinct():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b", "c"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    _, sample = src.poll()[0]
    assert len(set(sample)) == 3


def test_deterministic_across_instances():
    cfg = EegConfig(eeg_id="amp0", channels=["a", "b"])
    a = MockEegSource(cfg, clock=_fixed_clock())
    b = MockEegSource(cfg, clock=_fixed_clock())
    assert a.poll()[0][1] == b.poll()[0][1]


def test_frame_advances_signal():
    cfg = EegConfig(eeg_id="amp0", channels=["a"])
    src = MockEegSource(cfg, clock=_fixed_clock())
    first = src.poll()[0][1]
    second = src.poll()[0][1]
    assert first != second
