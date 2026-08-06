import struct

from htdp.export.eeg_bids import eeg_binary


def test_multiplexed_float32_round_trips():
    data = eeg_binary([[1.0, 2.0], [3.0, 4.0]])
    assert len(data) == 16  # 4 values * 4 bytes each
    assert list(struct.unpack("<ffff", data)) == [1.0, 2.0, 3.0, 4.0]


def test_empty_is_empty():
    assert eeg_binary([]) == b""
