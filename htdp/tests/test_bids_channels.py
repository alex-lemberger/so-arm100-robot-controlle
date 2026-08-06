from htdp.export.tabular import CHANNELS_HEADER, channels_rows, dicts_to_tsv


def test_one_row_per_tracker_suffix():
    rows = channels_rows(["a", "b"], 100.0)
    assert len(rows) == 16  # 2 trackers * 8 suffixes
    names = [r["name"] for r in rows]
    assert "a_x_m" in names and "b_quality" in names


def test_channel_types_and_units():
    rows = {r["name"]: r for r in channels_rows(["a"], 100.0)}
    assert rows["a_x_m"]["type"] == "POS" and rows["a_x_m"]["units"] == "m"
    assert rows["a_qw"]["type"] == "ORNT" and rows["a_qw"]["component"] == "quat_w"
    assert rows["a_quality"]["type"] == "MISC"
    assert rows["a_x_m"]["tracked_point"] == "a"
    assert rows["a_x_m"]["sampling_frequency"] == "100.0"


def test_dicts_to_tsv_orders_by_header():
    text = dicts_to_tsv(["a", "b"], [{"a": "1", "b": "2"}])
    assert text == "a\tb\n1\t2\n"


def test_channels_rows_serialize_with_header():
    text = dicts_to_tsv(CHANNELS_HEADER, channels_rows(["a"], 100.0))
    assert text.splitlines()[0] == "\t".join(CHANNELS_HEADER)
    assert len(text.splitlines()) == 1 + 8
