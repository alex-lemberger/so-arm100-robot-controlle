from __future__ import annotations

import shutil
from pathlib import Path

from htdp.io.canonical import dump_json
from htdp.io.checksums import write_checksums
from htdp.schemas.models import DeviceConfig, StreamRef
from pydantic import BaseModel, ConfigDict, Field


class VideoIngestError(RuntimeError):
    """Raised when a video cannot be ingested into a raw session."""


class VideoSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    fps: float = Field(gt=0)


def ingest_video(
    session_dir: Path,
    mp4_path: Path,
    sidecar_path: Path,
    force: bool = False,
) -> Path:
    if not mp4_path.exists():
        raise VideoIngestError(f"video file not found: {mp4_path}")
    device_path = session_dir / "device_config.json"
    if not device_path.exists():
        raise VideoIngestError(f"device_config.json not found in session: {session_dir}")

    sidecar = VideoSidecar.model_validate_json(sidecar_path.read_text(encoding="utf-8"))
    device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))

    rel = f"video/{sidecar.name}.mp4"
    existing = [s for s in device.streams if s.role == "video" and s.name == sidecar.name]
    if existing and not force:
        raise VideoIngestError(f"video stream '{sidecar.name}' already exists (use force=True)")
    device.streams = [
        s for s in device.streams if not (s.role == "video" and s.name == sidecar.name)
    ]

    (session_dir / "video").mkdir(exist_ok=True)
    shutil.copyfile(mp4_path, session_dir / rel)
    device.streams.append(
        StreamRef(
            name=sidecar.name,
            path=rel,
            fmt="mp4",
            role="video",
            rate_hz=sidecar.fps,
        )
    )
    dump_json(device, device_path)
    write_checksums(session_dir)
    return session_dir
