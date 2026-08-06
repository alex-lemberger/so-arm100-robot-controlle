import pytest

from htdp.export.eeg_bids import estimate_fs


def test_two_samples_250hz():
    assert estimate_fs([0.0, 0.004]) == pytest.approx(250.0)


def test_three_samples_250hz():
    assert estimate_fs([0.0, 0.004, 0.008]) == pytest.approx(250.0)


def test_single_sample_raises():
    with pytest.raises(ValueError):
        estimate_fs([0.0])


def test_zero_span_raises():
    with pytest.raises(ValueError):
        estimate_fs([1.0, 1.0])
