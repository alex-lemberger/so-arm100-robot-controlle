from pathlib import Path

from pydantic import ValidationError

from htdp.io.checksums import verify_checksums
from htdp.schemas.models import Consent, DeviceConfig, Session

_REQUIRED = (
    "session.json",
    "consent.json",
    "device_config.json",
    "notes.md",
    "checksums.sha256",
    "streams/events.csv",
)


def validate_session(raw_dir: Path) -> list[str]:
    """Validate a raw session directory.

    Returns a list of problem strings; empty list means the session is valid.
    """
    problems: list[str] = []

    for rel in _REQUIRED:
        if not (raw_dir / rel).exists():
            problems.append(f"missing required file: {rel}")
    if problems:
        return problems

    for rel, model in (
        ("session.json", Session),
        ("consent.json", Consent),
        ("device_config.json", DeviceConfig),
    ):
        try:
            model.model_validate_json((raw_dir / rel).read_text(encoding="utf-8"))
        except ValidationError as exc:
            problems.append(f"schema error in {rel}: {exc.error_count()} issue(s)")

    for rel in verify_checksums(raw_dir):
        problems.append(f"checksum mismatch: {rel}")

    device = DeviceConfig.model_validate_json(
        (raw_dir / "device_config.json").read_text(encoding="utf-8")
    )
    for stream in device.streams:
        if not (raw_dir / stream.path).exists():
            problems.append(f"declared stream missing on disk: {stream.path}")

    return problems
