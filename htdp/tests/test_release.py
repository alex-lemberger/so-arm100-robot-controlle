from pathlib import Path
import json
import pytest
from htdp.synth.generate import generate_session
from htdp.schemas.enums import ReleaseProfile
from htdp.release.package import package_release, ConsentError


def _raw(tmp_path: Path, seed: int = 1) -> Path:
    generate_session(tmp_path / "raw", seed=seed)
    return tmp_path / "raw"


def test_package_builds_release(tmp_path: Path):
    raw = _raw(tmp_path)
    out = package_release(
        ["synth-0001"],
        "rel-v0.1",
        ReleaseProfile.COMMERCIAL_DATASET,
        raw,
        tmp_path / "releases",
    )
    assert (out / "manifest.json").exists()
    assert (out / "checksums.sha256").exists()
    assert (out / "data/synth-0001/session.json").exists()


def test_package_blocks_on_consent_conflict(tmp_path: Path):
    raw = _raw(tmp_path)
    consent = raw / "synth-0001/consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["model_training"] = False
    consent.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConsentError):
        package_release(
            ["synth-0001"],
            "rel-bad",
            ReleaseProfile.COMMERCIAL_DATASET,
            raw,
            tmp_path / "releases",
        )
    assert not (tmp_path / "releases" / "rel-bad").exists()  # no partial output


def test_package_is_reproducible(tmp_path: Path):
    raw = _raw(tmp_path)
    a = package_release(
        ["synth-0001"], "rel-a", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "ra"
    )
    b = package_release(
        ["synth-0001"], "rel-b", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "rb"
    )
    sha_a = json.loads((a / "manifest.json").read_text())["manifest_sha256"]
    sha_b = json.loads((b / "manifest.json").read_text())["manifest_sha256"]
    assert sha_a == sha_b


def test_absent_modalities_recorded_when_video_present_but_forbidden(tmp_path: Path):
    raw = _raw(tmp_path)
    # video present on disk, but consent forbids distributing raw video
    (raw / "synth-0001" / "video" / "clip.mp4").write_bytes(b"\x00\x01")
    consent = raw / "synth-0001/consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data["distribute_raw_video"] = False
    consent.write_text(json.dumps(data), encoding="utf-8")
    out = package_release(
        ["synth-0001"], "rel-vid", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    manifest = json.loads((out / "manifest.json").read_text())
    assert "video" in manifest["absent_modalities"]
