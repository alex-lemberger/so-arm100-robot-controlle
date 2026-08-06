from pathlib import Path

from htdp.release.package import package_release
from htdp.replay.player import load_release_pose
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return package_release(
        ["synth-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def test_load_release_pose_has_quaternion(tmp_path: Path):
    pose = load_release_pose(_release(tmp_path))
    assert "right_wrist" in pose
    row = pose["right_wrist"][0]
    assert len(row) == 8
    _, x, y, z, qw, qx, qy, qz = row
    assert (qw, qx, qy, qz) == (1.0, 0.0, 0.0, 0.0)  # synth identity quat
