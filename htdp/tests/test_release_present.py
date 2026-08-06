from pathlib import Path

from htdp.release.package import _present_by_session
from htdp.synth.generate import generate_session


def test_synth_session_has_no_video_or_eeg_present(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    assert _present_by_session(["synth-0001"], tmp_path / "raw") == {"synth-0001": set()}


def test_video_file_marks_video_present(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    (tmp_path / "raw" / "synth-0001" / "video" / "clip.mp4").write_bytes(b"\x00\x01")
    assert _present_by_session(["synth-0001"], tmp_path / "raw") == {"synth-0001": {"video"}}
