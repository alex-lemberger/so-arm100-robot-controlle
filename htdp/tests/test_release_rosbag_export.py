# tests/test_release_rosbag_export.py
from pathlib import Path

import pytest

pytest.importorskip("rosbags")

from rosbags.rosbag2 import Reader  # noqa: E402

from htdp.export.rosbag import RosbagExportError, export_release_rosbag  # noqa: E402
from htdp.release.package import package_release  # noqa: E402
from htdp.schemas.enums import ReleaseProfile  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    return package_release(
        ["synth-0001", "synth-0002"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def _topics(bag: Path) -> set[str]:
    with Reader(bag) as rd:
        return {c.topic for c in rd.connections}


def test_one_bag_per_session(tmp_path: Path):
    out = export_release_rosbag(_release(tmp_path), tmp_path / "bags")
    bags = sorted(p.name for p in out.iterdir() if p.is_dir())
    assert len(bags) == 2
    for name in bags:
        topics = _topics(out / name)
        assert "/events" in topics
        assert any(t.startswith("/motion/") for t in topics)


def test_missing_data_dir_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(RosbagExportError):
        export_release_rosbag(tmp_path / "empty", tmp_path / "bags")


def test_empty_release_raises(tmp_path: Path):
    rel = tmp_path / "rel"
    (rel / "data").mkdir(parents=True)
    with pytest.raises(RosbagExportError):
        export_release_rosbag(rel, tmp_path / "bags")


def test_force_overwrite(tmp_path: Path):
    rel = _release(tmp_path)
    export_release_rosbag(rel, tmp_path / "bags")
    with pytest.raises(RosbagExportError):
        export_release_rosbag(rel, tmp_path / "bags")
    export_release_rosbag(rel, tmp_path / "bags", force=True)  # ok
