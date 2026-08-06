from htdp.export.tabular import SUFFIXES, matrix_to_tsv, motion_wide


def _row(tracker: str, ts: str, x: str = "0.000000") -> dict[str, str]:
    base = {s: "0.000000" for s in SUFFIXES}
    base.update({"timestamp_s": ts, "tracker_id": tracker, "x_m": x})
    return base


def test_header_lists_timestamp_then_each_tracker_suffix():
    header, _ = motion_wide([_row("a", "0.000000")], ["a", "b"])
    assert header[0] == "timestamp_s"
    assert header[1:9] == [f"a_{s}" for s in SUFFIXES]
    assert header[9:17] == [f"b_{s}" for s in SUFFIXES]


def test_union_timestamps_sorted_and_na_filled():
    rows = [_row("a", "0.000000", x="1.000000"), _row("b", "0.010000", x="2.000000")]
    header, matrix = motion_wide(rows, ["a", "b"])
    assert [r[0] for r in matrix] == ["0.000000", "0.010000"]  # union, sorted
    # at t=0 a is present, b is missing -> b columns n/a
    assert matrix[0][1] == "1.000000"  # a_x_m
    assert matrix[0][9] == "n/a"  # b_x_m
    # at t=0.01 a is missing -> a columns n/a, b present
    assert matrix[1][1] == "n/a"  # a_x_m
    assert matrix[1][9] == "2.000000"  # b_x_m


def test_matrix_to_tsv_tab_joined():
    text = matrix_to_tsv(["x", "y"], [["1", "2"], ["3", "n/a"]])
    assert text == "x\ty\n1\t2\n3\tn/a\n"
