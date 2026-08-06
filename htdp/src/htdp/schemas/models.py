from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from htdp.schemas.enums import EventLabel, ProcessingStatus, QcStatus


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Consent(_Base):
    consent_form_version: str
    commercial_use: bool = False
    distribute_raw_video: bool = False
    distribute_raw_eeg: bool = False
    derived_features_only: bool = False
    model_training: bool = False
    public_release: bool = False
    internal_only: bool = True
    third_party_access: bool = False
    delete_after: str | None = None  # ISO date, seed-derived in synth


class CoordinateFrame(_Base):
    units: str = "meters"
    time_unit: str = "seconds"
    handedness: str = "right"
    axes: str = "x=right,y=forward,z=up"
    quaternion_order: str = "w,x,y,z"


class StreamRef(_Base):
    name: str
    path: str
    fmt: str
    role: str
    rate_hz: float | None = None


class DeviceConfig(_Base):
    device_config_id: str
    frame: CoordinateFrame = Field(default_factory=CoordinateFrame)
    streams: list[StreamRef] = Field(default_factory=list)


class EventMarker(_Base):
    timestamp_s: float
    event_id: int
    label: EventLabel
    phase: str
    source: str = "synthetic"
    confidence: float = 1.0
    notes: str = ""


class Participant(_Base):
    participant_id: str
    cohort: str = "synthetic"


class TaskProtocol(_Base):
    protocol_id: str
    title: str
    phases: list[str]


class Session(_Base):
    session_id: str
    participant_id: str
    protocol_id: str
    consent_form_version: str
    device_config_id: str
    start_time_s: float
    qc_status: QcStatus = QcStatus.PASS
    processing_status: ProcessingStatus = ProcessingStatus.RAW


class Manifest(_Base):
    session_id: str
    inputs: dict[str, str]  # rel path -> sha256
    outputs: dict[str, str]  # rel path -> sha256
    tool_versions: dict[str, str]  # recorded, EXCLUDED from reproducibility hash
    seed: int


class DatasetRelease(_Base):
    release_name: str
    profile: str
    session_ids: list[str]
    absent_modalities: list[str] = Field(default_factory=list)
    absent_modalities_by_session: dict[str, list[str]] = Field(default_factory=dict)
    manifest_sha256: str
