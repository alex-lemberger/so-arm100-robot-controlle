from __future__ import annotations

import math
import shutil
from pathlib import Path

from htdp.io.canonical import dump_json, write_csv
from htdp.io.checksums import write_checksums
from htdp.schemas.enums import EventLabel
from htdp.schemas.models import (
    Consent,
    CoordinateFrame,
    DeviceConfig,
    Session,
    StreamRef,
)

_RATE_HZ = 100.0
_DURATION_S = 4.0
_TRACKERS = ("right_wrist", "left_wrist", "torso", "object")
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


def _trajectory(tracker: str, seed: int) -> list[dict[str, object]]:
    n = int(_RATE_HZ * _DURATION_S)
    phase = (seed % 7) * 0.1
    rows: list[dict[str, object]] = []
    for i in range(n):
        t = i / _RATE_HZ
        reach = math.sin(math.pi * t / _DURATION_S + phase)
        base = {"right_wrist": 0.3, "left_wrist": -0.3, "torso": 0.0, "object": 0.5}[tracker]
        defect_tag = ""
        ts = t
        if tracker == "left_wrist" and 100 <= i < 110:  # dropped-sample gap — skip rows
            continue
        if tracker == "left_wrist" and i == 110:  # boundary marker after gap
            defect_tag = "dropped_gap"
        if tracker == "object":  # clock-drift offset
            ts = t + 0.05 * (t / _DURATION_S)
            defect_tag = "clock_drift"
        rows.append(
            {
                "timestamp_s": ts,
                "tracker_id": tracker,
                "x_m": base + 0.1 * reach,
                "y_m": 0.2 * reach,
                "z_m": 0.9 + 0.05 * reach,
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "quality": 1.0,
                "defect_tag": defect_tag,
            }
        )
    return rows


def _events() -> list[dict[str, object]]:
    spec = [
        (0.0, EventLabel.START, "approach"),
        (1.0, EventLabel.GRASP, "grasp"),
        (2.0, EventLabel.RELEASE, "transport"),
        (3.0, EventLabel.PLACE, "place"),
        (4.0, EventLabel.STOP, "done"),
    ]
    return [
        {
            "timestamp_s": t,
            "event_id": i,
            "label": label.value,
            "phase": phase,
            "source": "synthetic",
            "confidence": 1.0,
            "notes": "",
        }
        for i, (t, label, phase) in enumerate(spec)
    ]


def generate_session(out_dir: Path, seed: int, force: bool = False) -> Path:
    session_id = f"synth-{seed:04d}"
    session_dir = out_dir / session_id
    if session_dir.exists():
        if not force:
            raise FileExistsError(f"raw session already exists: {session_dir} (use force=True)")
        shutil.rmtree(session_dir)
    (session_dir / "streams").mkdir(parents=True)
    (session_dir / "video").mkdir()

    streams: list[StreamRef] = []
    for tracker in _TRACKERS:
        rel = f"streams/motion_{tracker}.csv"
        write_csv(_trajectory(tracker, seed), _MOTION_COLS, session_dir / rel)
        streams.append(
            StreamRef(
                name=tracker,
                path=rel,
                fmt="csv",
                role="motion",
                rate_hz=_RATE_HZ,
            )
        )
    write_csv(_events(), _EVENT_COLS, session_dir / "streams/events.csv")
    streams.append(
        StreamRef(
            name="events",
            path="streams/events.csv",
            fmt="csv",
            role="events",
        )
    )

    device = DeviceConfig(
        device_config_id="vive-synth",
        frame=CoordinateFrame(),
        streams=streams,
    )
    consent = Consent(
        consent_form_version="v1",
        commercial_use=True,
        model_training=True,
        third_party_access=True,
        public_release=True,
        internal_only=False,
        delete_after="2030-01-01",
    )
    session = Session(
        session_id=session_id,
        participant_id=f"p-{seed:04d}",
        protocol_id="reach-grasp-place",
        consent_form_version="v1",
        device_config_id="vive-synth",
        start_time_s=0.0,
    )

    dump_json(session, session_dir / "session.json")
    dump_json(consent, session_dir / "consent.json")
    dump_json(device, session_dir / "device_config.json")
    (session_dir / "notes.md").write_text(
        f"# Synthetic session {session_id}\nSeed {seed}. Reach-grasp-place. Defects injected.\n",
        encoding="utf-8",
        newline="\n",
    )
    write_checksums(session_dir)
    return session_dir
