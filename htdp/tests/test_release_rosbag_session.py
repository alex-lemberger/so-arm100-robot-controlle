from pathlib import Path

import pytest

pytest.importorskip("rosbags")

from rosbags.rosbag2 import Reader  # noqa: E402
from rosbags.typesys import Stores, get_typestore  # noqa: E402

from htdp.export.rosbag import RosbagExportError, _write_session_bag  # noqa: E402
from htdp.synth.generate import generate_session  # noqa: E402


def _read(bag: Path) -> tuple[dict[str, int], dict]:
    ts = get_typestore(Stores.ROS2_HUMBLE)
    counts: dict[str, int] = {}
    first_pose: dict = {}
    with Reader(bag) as rd:
        for conn, _t, raw in rd.messages():
            counts[conn.topic] = counts.get(conn.topic, 0) + 1
            if conn.topic == "/motion/rightwrist" and "x" not in first_pose:
                m = ts.deserialize_cdr(raw, conn.msgtype)
                first_pose = {
                    "x": m.pose.position.x,
                    "y": m.pose.position.y,
                    "z": m.pose.position.z,
                    "w": m.pose.orientation.w,
                }
    return counts, first_pose


def test_session_bag_topics_counts_and_values(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    bag = tmp_path / "bag"
    _write_session_bag(bag, tmp_path / "raw" / "synth-0001")
    assert (bag / "metadata.yaml").exists()
    counts, first_pose = _read(bag)
    # 4 motion trackers + events
    assert "/motion/rightwrist" in counts
    assert "/motion/leftwrist" in counts
    assert "/motion/torso" in counts
    assert "/motion/object" in counts
    assert "/events" in counts
    # first right_wrist row: x=0.309983,y=0.019967,z=0.904992,qw=1
    assert first_pose["x"] == pytest.approx(0.309983, abs=1e-6)
    assert first_pose["z"] == pytest.approx(0.904992, abs=1e-6)
    assert first_pose["w"] == pytest.approx(1.0, abs=1e-6)


def test_missing_metadata_raises(tmp_path: Path):
    empty = tmp_path / "raw" / "synth-9999"
    empty.mkdir(parents=True)
    with pytest.raises(RosbagExportError):
        _write_session_bag(tmp_path / "bag", empty)
