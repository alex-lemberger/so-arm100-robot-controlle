import json
from pathlib import Path

import pytest

from htdp.ingest.video import VideoIngestError, ingest_video
from htdp.schemas.models import DeviceConfig
from htdp.synth.generate import generate_session
from htdp.validate import validate_session


def _session(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    return tmp_path / "raw" / "synth-0001"


def _sidecar(tmp_path: Path, name: str = "frontal", fps: float = 30.0) -> Path:
    p = tmp_path / "video.json"
    p.write_text(json.dumps({"name": name, "fps": fps}), encoding="utf-8")
    return p


def _mp4(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftyp")  # opaque dummy bytes, never decoded
    return p


def test_happy_path_registers_and_validates(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    assert (session / "video" / "frontal.mp4").exists()
    device = DeviceConfig.model_validate_json(
        (session / "device_config.json").read_text(encoding="utf-8")
    )
    vids = [s for s in device.streams if s.role == "video"]
    assert len(vids) == 1
    assert vids[0].name == "frontal"
    assert vids[0].path == "video/frontal.mp4"
    assert vids[0].fmt == "mp4"
    assert vids[0].rate_hz == 30.0
    assert validate_session(session) == []  # checksums re-sealed


def test_duplicate_name_without_force_raises(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    with pytest.raises(VideoIngestError):
        ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))


def test_force_overwrites_without_duplicating_stream(tmp_path: Path):
    session = _session(tmp_path)
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
    ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path, fps=60.0), force=True)
    device = DeviceConfig.model_validate_json(
        (session / "device_config.json").read_text(encoding="utf-8")
    )
    vids = [s for s in device.streams if s.role == "video"]
    assert len(vids) == 1  # replaced, not duplicated
    assert vids[0].rate_hz == 60.0
    assert validate_session(session) == []


def test_missing_mp4_raises_before_any_write(tmp_path: Path):
    session = _session(tmp_path)
    with pytest.raises(VideoIngestError):
        ingest_video(session, tmp_path / "nope.mp4", _sidecar(tmp_path))
    assert not (session / "video" / "frontal.mp4").exists()


def test_missing_device_config_raises(tmp_path: Path):
    session = _session(tmp_path)
    (session / "device_config.json").unlink()
    with pytest.raises(VideoIngestError):
        ingest_video(session, _mp4(tmp_path), _sidecar(tmp_path))
