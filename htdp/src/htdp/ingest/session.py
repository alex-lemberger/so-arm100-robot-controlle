from __future__ import annotations
import json

from dataclasses import dataclass

from htdp.ingest.frame import IDENTITY, Quat, apply_transform
from htdp.ingest.mapping import IngestMap, extract_eeg, extract_motion, parse_ingest_map
from htdp.ingest.reader import load_xdf_streams
from htdp.schemas.models import (
    Consent,
    CoordinateFrame,
    DeviceConfig,
    Session,
    StreamRef,
)

import shutil
from importlib.metadata import version
from pathlib import Path

from htdp.io.canonical import dump_json, write_csv
from htdp.io.checksums import write_checksums

_MOTION_COLS = [
    "timestamp_s",
    "tracker_id",
    "x_m",
    "y_m",
    "z_m",
    "qw",
    "qx",
    "qy",
    "qz",
    "quality",
    "defect_tag",
]
_EVENT_COLS = [
    "timestamp_s",
    "event_id",
    "label",
    "phase",
    "source",
    "confidence",
    "notes",
]
_TRACKER_ORDER = ("right_wrist", "left_wrist", "torso", "object")


@dataclass
class ParsedSidecar:
    session: Session
    consent: Consent
    device_config: DeviceConfig
    ingest_map: IngestMap
    rotation: Quat


def _rotation_from_sidecar(sidecar: dict[str, object]) -> Quat:
    ft = sidecar.get("frame_transform")
    if not isinstance(ft, dict):
        return IDENTITY
    rot = ft.get("rotation")
    if rot is None:
        return IDENTITY
    w, x, y, z = (float(v) for v in rot)
    return (w, x, y, z)


def validate_sidecar(sidecar: dict[str, object]) -> ParsedSidecar:
    """Validate schema blocks + ingest_map before any XDF read or write (fail fast)."""
    session = Session.model_validate(sidecar["session"])
    consent = Consent.model_validate(sidecar["consent"])
    device_config = DeviceConfig.model_validate(sidecar["device_config"])
    ingest_map = parse_ingest_map(sidecar["ingest_map"])  # type: ignore[arg-type]
    return ParsedSidecar(
        session=session,
        consent=consent,
        device_config=device_config,
        ingest_map=ingest_map,
        rotation=_rotation_from_sidecar(sidecar),
    )


def compute_t0(motion_raw: dict[str, list[dict[str, object]]]) -> float:
    all_ts = [float(r["raw_ts"]) for rows in motion_raw.values() for r in rows]  # type: ignore[arg-type]
    if not all_ts:
        raise ValueError("no motion samples found")
    return min(all_ts)


def build_motion_rows(
    motion_raw: dict[str, list[dict[str, object]]],
    rotation: Quat,
    t0: float,
) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = {}
    for tracker, rows in motion_raw.items():
        built: list[dict[str, object]] = []
        for r in rows:
            pos = (
                float(r["x_m"]),  # type: ignore[arg-type]
                float(r["y_m"]),  # type: ignore[arg-type]
                float(r["z_m"]),  # type: ignore[arg-type]
            )
            quat = (
                float(r["qw"]),  # type: ignore[arg-type]
                float(r["qx"]),  # type: ignore[arg-type]
                float(r["qy"]),  # type: ignore[arg-type]
                float(r["qz"]),  # type: ignore[arg-type]
            )
            (px, py, pz), (qw, qx, qy, qz) = apply_transform(rotation, pos, quat)
            built.append(
                {
                    "timestamp_s": float(r["raw_ts"]) - t0,  # type: ignore[arg-type]
                    "tracker_id": r["tracker_id"],
                    "x_m": px,
                    "y_m": py,
                    "z_m": pz,
                    "qw": qw,
                    "qx": qx,
                    "qy": qy,
                    "qz": qz,
                    "quality": float(r["quality"]),  # type: ignore[arg-type]
                    "defect_tag": "",
                }
            )
        out[tracker] = built
    return out


def build_event_rows(
    stamps: list[float],
    payloads: list[str],
    t0: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ts, payload in zip(stamps, payloads):
        p = json.loads(payload)
        rows.append(
            {
                "timestamp_s": float(ts) - t0,
                "event_id": int(p["event_id"]),
                "label": str(p["label"]),
                "phase": str(p["phase"]),
                "source": "real",
                "confidence": float(p["confidence"]),
                "notes": str(p["notes"]),
            }
        )
    return rows


def write_raw_folder(
    out_dir: Path,
    *,
    session: Session,
    consent: Consent,
    device_config_id: str,
    motion_out: dict[str, list[dict[str, object]]],
    event_rows: list[dict[str, object]],
    source_xdf_name: str,
    eeg_out: dict[str, tuple[list[str], list[dict[str, object]]]] | None = None,
    force: bool = False,
) -> Path:
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"raw session already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    (out_dir / "streams").mkdir(parents=True)
    (out_dir / "video").mkdir()

    stream_refs: list[StreamRef] = []
    for tracker in _TRACKER_ORDER:
        if tracker not in motion_out:
            continue
        rel = f"streams/motion_{tracker}.csv"
        write_csv(motion_out[tracker], _MOTION_COLS, out_dir / rel)
        stream_refs.append(StreamRef(name=tracker, path=rel, fmt="csv", role="motion"))
    write_csv(event_rows, _EVENT_COLS, out_dir / "streams/events.csv")
    stream_refs.append(
        StreamRef(name="events", path="streams/events.csv", fmt="csv", role="events")
    )

    for eeg_id, (labels, rows) in (eeg_out or {}).items():
        rel = f"streams/eeg_{eeg_id}.csv"
        write_csv(rows, ["timestamp_s"] + labels, out_dir / rel)
        stream_refs.append(StreamRef(name=eeg_id, path=rel, fmt="csv", role="eeg"))

    device_out = DeviceConfig(
        device_config_id=device_config_id,
        frame=CoordinateFrame(),
        streams=stream_refs,
    )
    dump_json(session, out_dir / "session.json")
    dump_json(consent, out_dir / "consent.json")
    dump_json(device_out, out_dir / "device_config.json")
    (out_dir / "notes.md").write_text(
        f"# Ingested session {session.session_id}\n"
        f"Source: {source_xdf_name}. Ingested with htdp {version('htdp')}.\n",
        encoding="utf-8",
        newline="\n",
    )
    write_checksums(out_dir)
    return out_dir


def ingest_xdf(
    xdf_path: Path,
    sidecar_path: Path,
    out_dir: Path,
    force: bool = False,
) -> Path:
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    parsed = validate_sidecar(sidecar)  # fail fast before reading the XDF

    streams = load_xdf_streams(xdf_path)

    motion_raw: dict[str, list[dict[str, object]]] = {}
    for stream_name, m in parsed.ingest_map.motion.items():
        if stream_name not in streams:
            raise KeyError(f"ingest_map stream '{stream_name}' not found in XDF")
        motion_raw[m.tracker_id] = extract_motion(streams[stream_name], m)

    t0 = compute_t0(motion_raw)
    motion_out = build_motion_rows(motion_raw, parsed.rotation, t0)

    eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]] = {}
    for stream_name, em in parsed.ingest_map.eeg.items():
        if stream_name not in streams:
            raise KeyError(f"ingest_map eeg stream '{stream_name}' not found in XDF")
        eeg_raw[em.eeg_id] = extract_eeg(streams[stream_name], em)
    eeg_out = build_eeg_rows(eeg_raw, t0)

    ev = streams[parsed.ingest_map.events_stream]
    payloads = [s if isinstance(s, str) else "" for s in ev.time_series]
    event_rows = build_event_rows(ev.time_stamps, payloads, t0)

    session = parsed.session.model_copy(update={"start_time_s": t0})
    return write_raw_folder(
        out_dir,
        session=session,
        consent=parsed.consent,
        device_config_id=parsed.device_config.device_config_id,
        motion_out=motion_out,
        event_rows=event_rows,
        source_xdf_name=xdf_path.name,
        eeg_out=eeg_out,
        force=force,
    )


def build_eeg_rows(
    eeg_raw: dict[str, tuple[list[str], list[dict[str, object]]]],
    t0: float,
) -> dict[str, tuple[list[str], list[dict[str, object]]]]:
    out: dict[str, tuple[list[str], list[dict[str, object]]]] = {}
    for eeg_id, (labels, rows) in eeg_raw.items():
        built: list[dict[str, object]] = []
        for r in rows:
            new_row: dict[str, object] = {"timestamp_s": float(r["raw_ts"]) - t0}  # type: ignore[arg-type]
            for label in labels:
                new_row[label] = float(r[label])  # type: ignore[arg-type]
            built.append(new_row)
        out[eeg_id] = (labels, built)
    return out
