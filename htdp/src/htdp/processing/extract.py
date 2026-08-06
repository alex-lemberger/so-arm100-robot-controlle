from __future__ import annotations

import importlib.metadata as md
from pathlib import Path

import polars as pl

from htdp.io.canonical import dump_json
from htdp.io.checksums import sha256_file
from htdp.schemas.models import DeviceConfig, Manifest
from htdp.validate import validate_session


def _tool_versions() -> dict[str, str]:
    return {pkg: md.version(pkg) for pkg in ("polars", "pydantic")}


def process_session(raw_dir: Path, processed_root: Path) -> Path:
    problems = validate_session(raw_dir)
    if problems:
        raise ValueError(f"cannot process invalid raw session: {problems}")

    device = DeviceConfig.model_validate_json(
        (raw_dir / "device_config.json").read_text(encoding="utf-8")
    )
    motion_paths = [raw_dir / s.path for s in device.streams if s.role == "motion"]
    motion = pl.concat([pl.read_csv(p) for p in motion_paths]).sort(["tracker_id", "timestamp_s"])
    events = pl.read_csv(raw_dir / "streams/events.csv").sort("timestamp_s")

    out = processed_root / raw_dir.name
    out.mkdir(parents=True, exist_ok=True)
    motion.write_parquet(out / "motion.parquet")
    events.write_parquet(out / "events.parquet")

    inputs = {
        p.relative_to(raw_dir).as_posix(): sha256_file(p)
        for p in sorted(raw_dir.rglob("*"))
        if p.is_file()
    }
    outputs = {f.name: sha256_file(f) for f in sorted(out.glob("*.parquet"))}
    seed = int(raw_dir.name.split("-")[-1])
    manifest = Manifest(
        session_id=raw_dir.name,
        inputs=inputs,
        outputs=outputs,
        tool_versions=_tool_versions(),
        seed=seed,
    )
    dump_json(manifest, out / "manifest.json")
    return out
