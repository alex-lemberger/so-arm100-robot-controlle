import json
from pathlib import Path

from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def test_per_session_video_consent(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    raw = tmp_path / "raw"
    for sid, allow in [("synth-0001", True), ("synth-0002", False)]:
        (raw / sid / "video").mkdir(exist_ok=True)
        (raw / sid / "video" / "clip.mp4").write_bytes(b"\x00\x01")
        cpath = raw / sid / "consent.json"
        c = json.loads(cpath.read_text(encoding="utf-8"))
        c["distribute_raw_video"] = allow
        cpath.write_text(json.dumps(c), encoding="utf-8")

    out = package_release(
        ["synth-0001", "synth-0002"],
        "rel-mixed",
        ReleaseProfile.COMMERCIAL_DATASET,
        raw,
        tmp_path / "releases",
    )

    assert (out / "data/synth-0001/video/clip.mp4").exists()  # A allowed → kept
    assert not (out / "data/synth-0002/video/clip.mp4").exists()  # B forbidden → dropped
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert m["absent_modalities_by_session"] == {
        "synth-0001": ["eeg"],
        "synth-0002": ["eeg", "video"],
    }
    assert m["absent_modalities"] == ["eeg"]  # video kept by A → not fully absent
