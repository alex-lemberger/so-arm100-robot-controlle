import json
from pathlib import Path

import pytest

from htdp.export.bids import BidsExportError, export_motion_bids
from htdp.synth.generate import generate_session

_STEM = "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
_MOTION_DIR = "sub-p0001/motion"


def _export(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return export_motion_bids(tmp_path / "raw" / "synth-0001", tmp_path / "bids")


def test_tree_layout(tmp_path: Path):
    out = _export(tmp_path)
    for rel in (
        "dataset_description.json",
        "README",
        "participants.tsv",
        f"{_MOTION_DIR}/{_STEM}_motion.tsv",
        f"{_MOTION_DIR}/{_STEM}_motion.json",
        f"{_MOTION_DIR}/{_STEM}_channels.tsv",
        f"{_MOTION_DIR}/sub-p0001_task-reachgraspplace_events.tsv",
    ):
        assert (out / rel).exists(), rel


def test_motion_tsv_header_and_gap(tmp_path: Path):
    out = _export(tmp_path)
    lines = (out / f"{_MOTION_DIR}/{_STEM}_motion.tsv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    assert header[0] == "timestamp_s"
    assert "right_wrist_x_m" in header and "object_quality" in header
    # left_wrist has a dropped-sample gap -> at least one row carries n/a for it
    lw_idx = header.index("left_wrist_x_m")
    assert any(row.split("\t")[lw_idx] == "n/a" for row in lines[1:])


def test_channels_row_count_matches_columns(tmp_path: Path):
    out = _export(tmp_path)
    motion_lines = (out / f"{_MOTION_DIR}/{_STEM}_motion.tsv").read_text().splitlines()
    data_cols = len(motion_lines[0].split("\t")) - 1  # minus timestamp_s
    chan_lines = (out / f"{_MOTION_DIR}/{_STEM}_channels.tsv").read_text().splitlines()
    assert len(chan_lines) - 1 == data_cols  # minus header


def test_dataset_description_parses(tmp_path: Path):
    out = _export(tmp_path)
    d = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert d["BIDSVersion"] == "1.10.0"


def test_events_onsets_match(tmp_path: Path):
    out = _export(tmp_path)
    ev = (out / f"{_MOTION_DIR}/sub-p0001_task-reachgraspplace_events.tsv").read_text().splitlines()
    assert ev[0] == "onset\tduration\ttrial_type\tvalue"
    assert ev[1].split("\t")[0] == "0.000000"  # first event onset


def test_existing_out_dir_requires_force(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    export_motion_bids(src, tmp_path / "bids")
    with pytest.raises(BidsExportError):
        export_motion_bids(src, tmp_path / "bids")
    export_motion_bids(src, tmp_path / "bids", force=True)  # ok


def test_missing_session_json_raises(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    (src / "session.json").unlink()
    with pytest.raises(BidsExportError):
        export_motion_bids(src, tmp_path / "bids")
