from __future__ import annotations

from collections import Counter

import shutil
from pathlib import Path

from htdp.export.eeg_bids import (
    EEG_CHANNELS_HEADER,
    eeg_binary,
    eeg_channels_rows,
    eeg_json,
    estimate_fs,
    vhdr_text,
    vmrk_text,
)
from htdp.export.labels import sanitize
from htdp.export.sidecars import (
    PARTICIPANTS_HEADER,
    dataset_description,
    motion_json,
    readme_text,
)
from htdp.export.tabular import (
    CHANNELS_HEADER,
    EVENTS_HEADER,
    channels_rows,
    dicts_to_tsv,
    events_rows,
    matrix_to_tsv,
    motion_wide,
)
from htdp.io.canonical import dump_json
from htdp.schemas.models import DeviceConfig, Session


class BidsExportError(RuntimeError):
    """Raised when a session/release cannot be exported to BIDS."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:] if line]


def _read_eeg_csv(path: Path) -> tuple[list[str], list[float], list[list[float]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    labels = lines[0].split(",")[1:]
    timestamps: list[float] = []
    samples: list[list[float]] = []
    for line in lines[1:]:
        if not line:
            continue
        cells = line.split(",")
        timestamps.append(float(cells[0]))
        samples.append([float(c) for c in cells[1:]])
    return labels, timestamps, samples


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_session_bids(out_dir: Path, raw_dir: Path, ses: str | None) -> dict[str, str]:
    session_path = raw_dir / "session.json"
    device_path = raw_dir / "device_config.json"
    if not session_path.exists() or not device_path.exists():
        raise BidsExportError(f"raw session missing metadata: {raw_dir}")

    session = Session.model_validate_json(session_path.read_text(encoding="utf-8"))
    device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))
    motion_streams = [s for s in device.streams if s.role == "motion"]
    if not motion_streams:
        raise BidsExportError(f"no motion streams in {raw_dir}")

    trackers = [s.name for s in motion_streams]
    fps = motion_streams[0].rate_hz or 100.0
    rows: list[dict[str, str]] = []
    for s in motion_streams:
        rows.extend(_read_csv(raw_dir / s.path))
    events_path = raw_dir / "streams/events.csv"
    events = _read_csv(events_path) if events_path.exists() else []

    sub = sanitize(session.participant_id)
    task = sanitize(session.protocol_id)
    tracksys = sanitize(device.device_config_id)
    ent = f"sub-{sub}" + (f"_ses-{ses}" if ses else "")
    subj_dir = out_dir / f"sub-{sub}"
    if ses:
        subj_dir = subj_dir / f"ses-{ses}"

    motion_dir = subj_dir / "motion"
    motion_dir.mkdir(parents=True)
    m_stem = f"{ent}_task-{task}_tracksys-{tracksys}"
    m_header, m_matrix = motion_wide(rows, trackers)
    _write_text(motion_dir / f"{m_stem}_motion.tsv", matrix_to_tsv(m_header, m_matrix))
    dump_json(motion_json(task, tracksys, trackers, fps), motion_dir / f"{m_stem}_motion.json")
    _write_text(
        motion_dir / f"{m_stem}_channels.tsv",
        dicts_to_tsv(CHANNELS_HEADER, channels_rows(trackers, fps)),
    )
    _write_text(
        motion_dir / f"{ent}_task-{task}_events.tsv",
        dicts_to_tsv(EVENTS_HEADER, events_rows(events)),
    )

    eeg_streams = [s for s in device.streams if s.role == "eeg" and (raw_dir / s.path).exists()]
    if eeg_streams:
        eeg_dir = subj_dir / "eeg"
        eeg_dir.mkdir(parents=True)
        for s in eeg_streams:
            labels, timestamps, samples = _read_eeg_csv(raw_dir / s.path)
            try:
                fs = estimate_fs(timestamps)
            except ValueError as exc:
                raise BidsExportError(f"eeg stream '{s.name}': {exc}") from exc
            acq = sanitize(s.name)
            eeg_stem = f"{ent}_task-{task}_acq-{acq}"
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vhdr", vhdr_text(eeg_stem, labels, fs))
            _write_text(eeg_dir / f"{eeg_stem}_eeg.vmrk", vmrk_text(eeg_stem))
            (eeg_dir / f"{eeg_stem}_eeg.eeg").write_bytes(eeg_binary(samples))
            dump_json(eeg_json(task, len(labels), fs), eeg_dir / f"{eeg_stem}_eeg.json")
            _write_text(
                eeg_dir / f"{eeg_stem}_channels.tsv",
                dicts_to_tsv(EEG_CHANNELS_HEADER, eeg_channels_rows(labels)),
            )

    return {"participant_id": f"sub-{sub}", "cohort": "n/a"}


def export_motion_bids(raw_dir: Path, out_dir: Path, force: bool = False) -> Path:
    session_path = raw_dir / "session.json"
    if not session_path.exists() or not (raw_dir / "device_config.json").exists():
        raise BidsExportError(f"raw session missing metadata: {raw_dir}")
    session = Session.model_validate_json(session_path.read_text(encoding="utf-8"))

    if out_dir.exists():
        if not force:
            raise BidsExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    row = _write_session_bids(out_dir, raw_dir, ses=None)
    dump_json(dataset_description(session.session_id), out_dir / "dataset_description.json")
    _write_text(out_dir / "README", readme_text(session.session_id))
    _write_text(out_dir / "participants.tsv", dicts_to_tsv(PARTICIPANTS_HEADER, [row]))
    return out_dir


def export_release_bids(release_dir: Path, out_dir: Path, force: bool = False) -> Path:
    data_dir = release_dir / "data"
    if not data_dir.is_dir():
        raise BidsExportError(f"release has no data/ directory: {release_dir}")
    session_dirs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    if not session_dirs:
        raise BidsExportError(f"release has no sessions: {release_dir}")

    subs: list[str] = []
    for sd in session_dirs:
        session = Session.model_validate_json((sd / "session.json").read_text(encoding="utf-8"))
        subs.append(sanitize(session.participant_id))
    counts = Counter(subs)

    if out_dir.exists():
        if not force:
            raise BidsExportError(f"output already exists: {out_dir} (use force=True)")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for sd, sub in zip(session_dirs, subs):
        ses = sanitize(sd.name) if counts[sub] > 1 else None
        row = _write_session_bids(out_dir, sd, ses)
        if row["participant_id"] not in seen:
            rows.append(row)
            seen.add(row["participant_id"])

    dump_json(dataset_description(release_dir.name), out_dir / "dataset_description.json")
    _write_text(out_dir / "README", readme_text(release_dir.name))
    _write_text(out_dir / "participants.tsv", dicts_to_tsv(PARTICIPANTS_HEADER, rows))
    return out_dir
