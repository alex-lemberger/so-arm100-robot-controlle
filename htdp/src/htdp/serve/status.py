"""Filesystem status reader: counts data-tier directories + policy presence, never mutates."""

from __future__ import annotations

from pathlib import Path

from htdp.serve.jobs import JobManager
from htdp.serve.models import CountBlock, PipelineStatus, PolicyInfo, TierCount


def _count_dirs(p: Path) -> int:
    return sum(1 for c in p.iterdir() if c.is_dir()) if p.is_dir() else 0


def _demos_count(data_dir: Path) -> CountBlock | None:
    episodes_path = data_dir / "demos" / "meta" / "episodes.jsonl"
    if not episodes_path.is_file():
        return None
    with episodes_path.open() as fh:
        return CountBlock(count=sum(1 for line in fh if line.strip()))


def read_status(data_dir: Path, manager: JobManager) -> PipelineStatus:
    policy_path = data_dir / "policy.pt"
    policy = PolicyInfo(present=policy_path.is_file())
    if policy.present:
        policy.path = "policy.pt"
        policy.mtime_s = policy_path.stat().st_mtime
    return PipelineStatus(
        data_dir=str(data_dir.resolve()),
        tiers=TierCount(
            raw=CountBlock(count=_count_dirs(data_dir / "data" / "raw")),
            processed=CountBlock(count=_count_dirs(data_dir / "data" / "processed")),
            releases=CountBlock(count=_count_dirs(data_dir / "data" / "releases")),
        ),
        demos=_demos_count(data_dir),
        policy=policy,
        running_job=manager.running_job_id,
    )
