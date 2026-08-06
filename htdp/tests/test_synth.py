from pathlib import Path
import pytest
from htdp.synth.generate import generate_session


def test_generates_expected_tree(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    assert d.name == "synth-0001"
    for rel in (
        "session.json",
        "consent.json",
        "device_config.json",
        "notes.md",
        "checksums.sha256",
        "streams/motion_right_wrist.csv",
        "streams/motion_left_wrist.csv",
        "streams/motion_torso.csv",
        "streams/motion_object.csv",
        "streams/events.csv",
    ):
        assert (d / rel).exists(), rel
    assert (d / "video").is_dir()


def test_is_deterministic(tmp_path: Path):
    a = generate_session(tmp_path / "a", seed=7)
    b = generate_session(tmp_path / "b", seed=7)
    assert (a / "streams/motion_right_wrist.csv").read_bytes() == (
        b / "streams/motion_right_wrist.csv"
    ).read_bytes()


def test_refuses_overwrite_without_force(tmp_path: Path):
    generate_session(tmp_path, seed=1)
    with pytest.raises(FileExistsError):
        generate_session(tmp_path, seed=1)
    generate_session(tmp_path, seed=1, force=True)  # ok


def test_injects_defect_tags(tmp_path: Path):
    d = generate_session(tmp_path, seed=1)
    left = (d / "streams/motion_left_wrist.csv").read_text(encoding="utf-8")
    obj = (d / "streams/motion_object.csv").read_text(encoding="utf-8")
    assert "dropped_gap" in left
    assert "clock_drift" in obj
