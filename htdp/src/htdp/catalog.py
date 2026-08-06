"""Multi-session catalog — scan raw sessions into a Parquet index."""

from pathlib import Path

import polars as pl
from pydantic import ValidationError

from htdp.schemas.models import DatasetRelease, DeviceConfig, Session


class CatalogError(RuntimeError):
    """Raised when the catalog cannot be built."""


_COLUMNS = [
    "session_id",
    "participant_id",
    "protocol_id",
    "device_config_id",
    "consent_form_version",
    "qc_status",
    "processing_status",
    "start_time_s",
    "modalities",
]

_RELEASE_COLUMNS = [
    "release_name",
    "profile",
    "n_sessions",
    "session_ids",
    "absent_modalities",
    "manifest_sha256",
]


def scan_sessions(sessions_dir: Path) -> list[dict[str, str | float]]:
    """Scan a directory of raw session folders and return one row dict per session."""
    if not sessions_dir.is_dir():
        raise CatalogError(f"not a directory: {sessions_dir}")
    session_dirs = sorted(
        p for p in sessions_dir.iterdir() if p.is_dir() and (p / "session.json").exists()
    )
    if not session_dirs:
        raise CatalogError(f"no sessions found in {sessions_dir}")

    rows: list[dict[str, str | float]] = []
    for sd in session_dirs:
        device_path = sd / "device_config.json"
        if not device_path.exists():
            raise CatalogError(f"session missing device_config.json: {sd}")
        try:
            session = Session.model_validate_json((sd / "session.json").read_text(encoding="utf-8"))
            device = DeviceConfig.model_validate_json(device_path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise CatalogError(f"invalid session metadata in {sd}: {exc}") from exc

        modalities = ",".join(sorted({s.role for s in device.streams}))
        rows.append(
            {
                "session_id": session.session_id,
                "participant_id": session.participant_id,
                "protocol_id": session.protocol_id,
                "device_config_id": session.device_config_id,
                "consent_form_version": session.consent_form_version,
                "qc_status": session.qc_status.value,
                "processing_status": session.processing_status.value,
                "start_time_s": session.start_time_s,
                "modalities": modalities,
            }
        )
    return sorted(rows, key=lambda r: r["session_id"])


def build_catalog(sessions_dir: Path, out_path: Path) -> Path:
    """Build a Parquet catalog from the given sessions directory and write to out_path."""
    rows = scan_sessions(sessions_dir)
    df = pl.DataFrame(rows).select(_COLUMNS)
    df.write_parquet(out_path)
    return out_path


def scan_releases(releases_dir: Path) -> list[dict[str, str | int]]:
    """Scan a directory of packaged releases and return one row dict per release."""
    if not releases_dir.is_dir():
        raise CatalogError(f"not a directory: {releases_dir}")
    release_dirs = sorted(
        p for p in releases_dir.iterdir() if p.is_dir() and (p / "manifest.json").exists()
    )
    if not release_dirs:
        raise CatalogError(f"no releases found in {releases_dir}")

    rows: list[dict[str, str | int]] = []
    for rd in release_dirs:
        try:
            release = DatasetRelease.model_validate_json(
                (rd / "manifest.json").read_text(encoding="utf-8")
            )
        except ValidationError as exc:
            raise CatalogError(f"invalid release manifest in {rd}: {exc}") from exc
        rows.append(
            {
                "release_name": release.release_name,
                "profile": release.profile,
                "n_sessions": len(release.session_ids),
                "session_ids": ",".join(sorted(release.session_ids)),
                "absent_modalities": ",".join(sorted(release.absent_modalities)),
                "manifest_sha256": release.manifest_sha256,
            }
        )
    return sorted(rows, key=lambda r: r["release_name"])


def build_release_catalog(releases_dir: Path, out_path: Path) -> Path:
    """Build a Parquet release inventory from the given releases directory."""
    rows = scan_releases(releases_dir)
    df = pl.DataFrame(rows).select(_RELEASE_COLUMNS)
    df.write_parquet(out_path)
    return out_path


def query_catalog(
    catalog_path: Path,
    *,
    protocol: str | None = None,
    qc_status: str | None = None,
    participant: str | None = None,
    processing_status: str | None = None,
    modality: str | None = None,
    start_after: float | None = None,
    start_before: float | None = None,
) -> list[str]:
    if not catalog_path.is_file():
        raise CatalogError(f"catalog not found: {catalog_path}")
    try:
        df = pl.read_parquet(catalog_path)
    except Exception as exc:  # noqa: BLE001 -- surface any unreadable parquet as CatalogError
        raise CatalogError(f"cannot read catalog {catalog_path}: {exc}") from exc

    if protocol is not None:
        df = df.filter(pl.col("protocol_id") == protocol)
    if qc_status is not None:
        df = df.filter(pl.col("qc_status") == qc_status)
    if participant is not None:
        df = df.filter(pl.col("participant_id") == participant)
    if processing_status is not None:
        df = df.filter(pl.col("processing_status") == processing_status)
    if modality is not None:
        df = df.filter(pl.col("modalities").str.split(",").list.contains(modality))
    if start_after is not None:
        df = df.filter(pl.col("start_time_s") >= start_after)
    if start_before is not None:
        df = df.filter(pl.col("start_time_s") <= start_before)

    return sorted(df["session_id"].to_list())
