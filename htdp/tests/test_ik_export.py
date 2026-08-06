import csv
from pathlib import Path

import pytest

from htdp.replay.ik import IkResult, write_ik_trajectory


def _sample() -> IkResult:
    return IkResult(
        joint_trajectory=[[0.1, 0.2], [0.3, 0.4]],
        max_error=0.5,
        timestamps=[0.0, 0.1],
        targets=[(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        errors=[0.1, 0.5],
        target_orientations=[(1.0, 0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)],
        orientation_errors=[0.0, 0.2],
        max_orientation_error=0.2,
    )


def test_writes_header_and_rows(tmp_path: Path):
    out = write_ik_trajectory(_sample(), tmp_path / "t.csv")
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows[0] == [
        "timestamp_s",
        "q0",
        "q1",
        "target_x",
        "target_y",
        "target_z",
        "tracking_error_m",
        "target_qw",
        "target_qx",
        "target_qy",
        "target_qz",
        "orientation_error_rad",
    ]
    assert len(rows) == 3
    assert rows[1] == [
        "0.0",
        "0.1",
        "0.2",
        "1.0",
        "2.0",
        "3.0",
        "0.1",
        "1.0",
        "0.0",
        "0.0",
        "0.0",
        "0.0",
    ]


def test_refuses_overwrite_without_force(tmp_path: Path):
    p = tmp_path / "t.csv"
    write_ik_trajectory(_sample(), p)
    with pytest.raises(FileExistsError):
        write_ik_trajectory(_sample(), p)


def test_force_overwrites(tmp_path: Path):
    p = tmp_path / "t.csv"
    p.write_text("OLD", encoding="utf-8")
    write_ik_trajectory(_sample(), p, force=True)
    assert "OLD" not in p.read_text(encoding="utf-8")


def test_empty_result_header_only(tmp_path: Path):
    out = write_ik_trajectory(IkResult([], 0.0, [], [], [], [], [], 0.0), tmp_path / "e.csv")
    rows = list(csv.reader(out.open(encoding="utf-8")))
    assert rows == [
        [
            "timestamp_s",
            "target_x",
            "target_y",
            "target_z",
            "tracking_error_m",
            "target_qw",
            "target_qx",
            "target_qy",
            "target_qz",
            "orientation_error_rad",
        ]
    ]
