from pathlib import Path

import pytest

from htdp.synth.generate import generate_session
from htdp.schemas.enums import ReleaseProfile
from htdp.release.package import package_release
from htdp.replay.player import load_release_motion, replay_release, ReplayUnavailable  # noqa: F401

mujoco = pytest.importorskip("mujoco")


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return package_release(
        ["synth-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def test_load_release_motion_has_all_trackers(tmp_path: Path):
    motion = load_release_motion(_release(tmp_path))
    assert set(motion) == {"right_wrist", "left_wrist", "torso", "object"}


def test_replay_steps_headless(tmp_path: Path):
    frames = replay_release(_release(tmp_path), headless=True, max_steps=10)
    assert frames == 10
