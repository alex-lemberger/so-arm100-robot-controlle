from htdp.export.sidecars import (
    PARTICIPANTS_HEADER,
    dataset_description,
    motion_json,
    participants_rows,
    readme_text,
)


def test_dataset_description_has_bids_version():
    d = dataset_description("synth-0001")
    assert d["BIDSVersion"] == "1.10.0"
    assert d["Name"] == "synth-0001"


def test_motion_json_channel_counts():
    d = motion_json("task", "vive", ["a", "b"], 100.0)
    assert d["SamplingFrequency"] == 100.0
    assert d["TrackingSystemName"] == "vive"
    assert d["POSChannelCount"] == 6  # 3 * 2 trackers
    assert d["ORNTChannelCount"] == 8  # 4 * 2 trackers
    assert d["MotionChannelCount"] == 16  # 8 * 2 trackers


def test_participants_rows_and_header():
    assert PARTICIPANTS_HEADER == ["participant_id", "cohort"]
    rows = participants_rows("p0001", "synthetic")
    assert rows == [{"participant_id": "sub-p0001", "cohort": "synthetic"}]


def test_readme_mentions_session():
    assert "synth-0001" in readme_text("synth-0001")
