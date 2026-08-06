from htdp_capture import contract


def test_motion_channels_exact_order():
    assert contract.MOTION_CHANNELS == (
        "x_m", "y_m", "z_m", "qw", "qx", "qy", "qz", "quality",
    )


def test_tracker_ids():
    assert contract.TRACKER_IDS == ("right_wrist", "left_wrist", "torso", "object")


def test_events_stream_name():
    assert contract.EVENTS_STREAM_NAME == "events"


def test_event_labels():
    assert contract.EVENT_LABELS == ("start", "grasp", "release", "place", "stop")


def test_motion_channel_index_maps_each_channel_to_its_position():
    assert contract.MOTION_CHANNEL_INDEX == {
        "x_m": 0, "y_m": 1, "z_m": 2, "qw": 3,
        "qx": 4, "qy": 5, "qz": 6, "quality": 7,
    }


def test_eeg_stream_name():
    assert contract.eeg_stream_name("amp0") == "eeg_amp0"
