from htdp.export.eeg_bids import EEG_CHANNELS_HEADER, eeg_channels_rows, eeg_json


def test_channels_rows():
    assert EEG_CHANNELS_HEADER == ["name", "type", "units"]
    rows = eeg_channels_rows(["Fp1", "Cz"])
    assert rows == [
        {"name": "Fp1", "type": "EEG", "units": "µV"},
        {"name": "Cz", "type": "EEG", "units": "µV"},
    ]


def test_eeg_json_fields():
    d = eeg_json("reachgraspplace", 3, 250.0)
    assert d["TaskName"] == "reachgraspplace"
    assert d["SamplingFrequency"] == 250.0
    assert d["EEGChannelCount"] == 3
    assert d["RecordingType"] == "continuous"
    assert d["EEGReference"] == "n/a"
    assert d["PowerLineFrequency"] == "n/a"
