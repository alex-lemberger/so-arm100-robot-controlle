"""Pydantic contract models for `htdp serve`. Source of truth for the HTTP/WS shapes."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class CountBlock(BaseModel):
    count: int


class TierCount(BaseModel):
    raw: CountBlock
    processed: CountBlock
    releases: CountBlock


class PolicyInfo(BaseModel):
    present: bool
    path: str | None = None
    mtime_s: float | None = None


class PipelineStatus(BaseModel):
    data_dir: str
    tiers: TierCount
    demos: CountBlock | None = None
    policy: PolicyInfo
    running_job: str | None = None


class Job(BaseModel):
    id: str
    kind: str
    args: dict[str, object] = Field(default_factory=dict)
    status: JobStatus
    exit_code: int | None = None
    created_s: float
    started_s: float | None = None
    ended_s: float | None = None
    error: str | None = None


class JobSummary(BaseModel):
    id: str
    kind: str
    status: JobStatus
    created_s: float


class StartJobRequest(BaseModel):
    kind: str
    args: dict[str, object] = Field(default_factory=dict)


class JobLogMessage(BaseModel):
    type: str  # "log" | "progress" | "status"
    line: str | None = None
    current: int | None = None
    total: int | None = None
    status: JobStatus | None = None
    exit_code: int | None = None
