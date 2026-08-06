import json
from pathlib import Path

from htdp.ingest.video import ingest_video
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _session_with_video(tmp_path: Path, allow_video: bool) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    session = tmp_path / "raw" / "synth-0001"
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sidecar = tmp_path / "video.json"
    sidecar.write_text(json.dumps({"name": "frontal", "fps": 30.0}), encoding="utf-8")
    ingest_video(session, mp4, sidecar)
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["distribute_raw_video"] = allow_video
    consent.write_text(json.dumps(data), encoding="utf-8")
    # consent edit invalidates checksums; re-seal so the session validates.
    from htdp.io.checksums import write_checksums

    write_checksums(session)
    return tmp_path / "raw"


def test_allowed_video_survives_packaging(tmp_path: Path):
    raw = _session_with_video(tmp_path, allow_video=True)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert (out / "data/synth-0001/video/frontal.mp4").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" not in manifest["absent_modalities"]


def test_forbidden_video_dropped_at_packaging(tmp_path: Path):
    raw = _session_with_video(tmp_path, allow_video=False)
    out = package_release(
        ["synth-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert not (out / "data/synth-0001/video/frontal.mp4").exists()
    assert (out / "data/synth-0001/streams/motion_right_wrist.csv").exists()  # motion intact
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]
