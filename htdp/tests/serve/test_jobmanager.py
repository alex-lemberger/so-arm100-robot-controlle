import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from htdp.serve.jobs import JobKindError, JobManager
from htdp.serve.models import JobStatus


def _fake_htdp(script: str) -> list[str]:
    # Replace the "htdp <subcmd>" prefix with a python one-liner ignoring the argv tail.
    return [sys.executable, "-c", script, "--"]


@pytest.mark.asyncio
async def test_successful_job_runs_to_done():
    mgr = JobManager(Path("."), htdp_cmd=_fake_htdp("print('hello'); print('1/2'); print('2/2')"))
    job = await mgr.submit("eval-policy", {})
    frames = [f async for f in mgr.subscribe(job.id)]
    assert frames[-1].type == "status"
    assert frames[-1].status == JobStatus.done
    assert any(f.type == "log" and f.line == "hello" for f in frames)
    assert any(f.type == "progress" and f.current == 1 and f.total == 2 for f in frames)
    assert mgr.get(job.id).status == JobStatus.done


@pytest.mark.asyncio
async def test_failed_job_reports_failed():
    mgr = JobManager(Path("."), htdp_cmd=_fake_htdp("import sys; sys.exit(3)"))
    job = await mgr.submit("eval-policy", {})
    async for _ in mgr.subscribe(job.id):
        pass
    got = mgr.get(job.id)
    assert got.status == JobStatus.failed
    assert got.exit_code == 3


@pytest.mark.asyncio
async def test_second_job_queues_behind_first():
    mgr = JobManager(Path("."), htdp_cmd=_fake_htdp("import time; time.sleep(0.5)"))
    a = await mgr.submit("eval-policy", {})
    b = await mgr.submit("eval-policy", {})
    assert a.status == JobStatus.running
    assert b.status == JobStatus.queued
    async for _ in mgr.subscribe(a.id):
        pass
    async for _ in mgr.subscribe(b.id):
        pass
    assert mgr.get(b.id).status == JobStatus.done


@pytest.mark.asyncio
async def test_cancel_running_job():
    mgr = JobManager(Path("."), htdp_cmd=_fake_htdp("import time; time.sleep(30)"))
    job = await mgr.submit("eval-policy", {})
    await asyncio.sleep(0.1)
    assert await mgr.cancel(job.id) is True
    async for _ in mgr.subscribe(job.id):
        pass
    assert mgr.get(job.id).status == JobStatus.cancelled


@pytest.mark.asyncio
async def test_bad_kind_rejected():
    mgr = JobManager(Path("."))
    with pytest.raises(JobKindError):
        await mgr.submit("nope", {})
