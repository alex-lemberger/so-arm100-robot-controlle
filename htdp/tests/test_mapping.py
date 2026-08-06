import pytest

from htdp.ingest.mapping import MappingError, parse_ingest_map

_CHANNELS = {"x_m": 0, "y_m": 1, "z_m": 2, "qw": 3, "qx": 4, "qy": 5, "qz": 6, "quality": 7}


def _valid_raw():
    return {
        "wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CHANNELS)},
        "marker": {"role": "events"},
    }


def test_parse_resolves_motion_and_events():
    im = parse_ingest_map(_valid_raw())
    assert im.events_stream == "marker"
    assert im.motion["wrist"].tracker_id == "right_wrist"
    assert im.motion["wrist"].channels["quality"] == 7


def test_parse_unknown_tracker_raises():
    raw = _valid_raw()
    raw["wrist"]["tracker_id"] = "nose"
    with pytest.raises(MappingError, match="nose"):
        parse_ingest_map(raw)


def test_parse_missing_channel_raises():
    raw = _valid_raw()
    del raw["wrist"]["channels"]["quality"]
    with pytest.raises(MappingError, match="quality"):
        parse_ingest_map(raw)


def test_parse_unknown_role_raises():
    raw = _valid_raw()
    raw["wrist"]["role"] = "video"
    with pytest.raises(MappingError, match="video"):
        parse_ingest_map(raw)


def test_parse_requires_exactly_one_events_stream():
    raw = {"wrist": {"role": "motion", "tracker_id": "right_wrist", "channels": dict(_CHANNELS)}}
    with pytest.raises(MappingError, match="events"):
        parse_ingest_map(raw)


def test_parse_requires_at_least_one_motion_stream():
    with pytest.raises(MappingError, match="motion"):
        parse_ingest_map({"marker": {"role": "events"}})


from htdp.ingest.mapping import extract_motion  # noqa: E402
from htdp.ingest.reader import XdfStream  # noqa: E402


def _motion_stream():
    return XdfStream(
        name="wrist",
        type="motion",
        channel_format="double64",
        time_stamps=[10.0, 10.01],
        time_series=[
            [0.1, 0.2, 0.9, 1.0, 0.0, 0.0, 0.0, 1.0],
            [0.11, 0.21, 0.91, 1.0, 0.0, 0.0, 0.0, 1.0],
        ],
    )


def test_extract_motion_builds_rows():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    rows = extract_motion(_motion_stream(), m)
    assert len(rows) == 2
    assert rows[0]["raw_ts"] == 10.0
    assert rows[0]["tracker_id"] == "right_wrist"
    assert rows[1]["x_m"] == 0.11
    assert rows[0]["quality"] == 1.0


def test_extract_motion_rejects_string_stream():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    bad = XdfStream(
        name="wrist", type="motion", channel_format="string", time_stamps=[0.0], time_series=["x"]
    )
    with pytest.raises(MappingError, match="numeric"):
        extract_motion(bad, m)


def test_extract_motion_channel_index_out_of_range_raises():
    m = parse_ingest_map(_valid_raw()).motion["wrist"]
    bad = _motion_stream()
    bad.time_series = [[0.1, 0.2]]  # too few channels
    with pytest.raises(MappingError, match="out of range"):
        extract_motion(bad, m)
