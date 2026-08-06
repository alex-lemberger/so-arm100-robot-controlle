from __future__ import annotations

import argparse
import json
from pathlib import Path

from htdp_capture.app import run_capture
from htdp_capture.config import CaptureConfig
from htdp_capture.mock_pose import MockPoseSource
from htdp_capture.scripted_marker import ScriptedMarkerSource, default_schedule


def _config_from_json(path: Path) -> CaptureConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return CaptureConfig(
        trackers=list(raw["trackers"]),
        session=raw["session"],
        consent=raw["consent"],
        device_config=raw["device_config"],
        rate_hz=float(raw.get("rate_hz", 100.0)),
        duration_s=float(raw.get("duration_s", 2.0)),
        frame_rotation=tuple(raw["frame_rotation"]) if raw.get("frame_rotation") else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="htdp-capture")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="run a mock capture to XDF + sidecar")
    record.add_argument("--config", required=True, type=Path)
    record.add_argument("--out-xdf", required=True, type=Path)
    record.add_argument("--out-sidecar", required=True, type=Path)
    record.add_argument("--force", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "record":
        config = _config_from_json(args.config)
        run_capture(
            config,
            MockPoseSource(config.trackers, rate_hz=config.rate_hz),
            ScriptedMarkerSource(config.schedule or default_schedule()),
            args.out_xdf,
            args.out_sidecar,
            force=args.force,
        )
        return 0
    return 1
