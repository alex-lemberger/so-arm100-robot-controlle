"""Job kind allowlist + argv builder + JobManager. Security boundary: only known htdp
subcommands, typed/validated args, server-controlled output paths, and subprocess spawn
via argv list (never shell=True)."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from htdp.serve.models import Job, JobLogMessage, JobStatus, JobSummary


class JobKindError(ValueError):
    """Raised for an unknown job kind or invalid job args."""


class _GenDemosArgs(BaseModel):
    n_train: int = Field(100, ge=1, le=2000)
    n_test: int = Field(25, ge=1, le=500)


class _SynthArgs(BaseModel):
    seed: int = Field(0, ge=0)


class _TrainArgs(BaseModel):
    steps: int = Field(3000, ge=1, le=50000)


class _EmptyArgs(BaseModel):
    pass


# kind -> (args model, argv builder). Output paths are hardcoded here, never from request.
def _synth_argv(a: _SynthArgs, data_dir: Path) -> list[str]:
    return ["synth", "--out", f"data/raw/serve-{a.seed:04d}", "--seed", str(a.seed), "--force"]


def _gen_demos_argv(a: _GenDemosArgs, data_dir: Path) -> list[str]:
    return ["gen-demos", "--out", "demos", "--n-train", str(a.n_train), "--n-test", str(a.n_test)]


def _train_argv(a: _TrainArgs, data_dir: Path) -> list[str]:
    return ["train-policy", "--demos", "demos", "--out", "policy.pt", "--steps", str(a.steps)]


def _eval_argv(a: _EmptyArgs, data_dir: Path) -> list[str]:
    return ["eval-policy", "--demos", "demos", "--policy", "policy.pt"]


_SPECS: dict[str, tuple[type[BaseModel], Callable[[Any, Path], list[str]]]] = {
    "synth": (_SynthArgs, _synth_argv),
    "gen-demos": (_GenDemosArgs, _gen_demos_argv),
    "train-policy": (_TrainArgs, _train_argv),
    "eval-policy": (_EmptyArgs, _eval_argv),
}

ALLOWED_KINDS = frozenset(_SPECS)


def build_argv(kind: str, args: dict[str, object], data_dir: Path) -> list[str]:
    spec = _SPECS.get(kind)
    if spec is None:
        raise JobKindError(f"unknown job kind: {kind!r}")
    model_cls, builder = spec
    try:
        parsed = model_cls.model_validate(args or {})
    except ValidationError as exc:
        raise JobKindError(f"invalid args for {kind!r}: {exc}") from exc
    return builder(parsed, data_dir)


_PROGRESS_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_MAX_JOBS = 50
_LOG_BUFFER = 2000
_TERMINAL_STATUSES = (JobStatus.done, JobStatus.failed, JobStatus.cancelled)


def _status_of(job: Job) -> JobStatus:
    # Escape hatch for mypy: cancel() can mutate job.status concurrently while
    # _execute() awaits the subprocess, so re-read it through a call boundary
    # rather than let mypy narrow it away based on the earlier guard.
    return job.status


class _JobRun:
    def __init__(self, job: Job, argv: list[str]) -> None:
        self.job = job
        self.argv = argv
        self.buffer: deque[JobLogMessage] = deque(maxlen=_LOG_BUFFER)
        self.subscribers: list[asyncio.Queue[JobLogMessage | None]] = []
        self.proc: asyncio.subprocess.Process | None = None

    def emit(self, msg: JobLogMessage) -> None:
        self.buffer.append(msg)
        for q in self.subscribers:
            q.put_nowait(msg)

    def close(self) -> None:
        for q in self.subscribers:
            q.put_nowait(None)
        self.subscribers.clear()


class JobManager:
    """Single-concurrency async job runner: validates + spawns `htdp` subprocesses
    (never a shell), streams stdout as log/progress frames, and enforces a FIFO queue
    so at most one job runs at a time. Further submits queue behind the running job.
    """

    def __init__(self, data_dir: Path, htdp_cmd: list[str] | None = None) -> None:
        self._data_dir = data_dir
        self._htdp = list(htdp_cmd) if htdp_cmd else ["htdp"]
        self._runs: dict[str, _JobRun] = {}
        self._order: deque[str] = deque()  # newest-first job ids, bounded to _MAX_JOBS
        self._pending: deque[str] = deque()  # FIFO of queued job ids awaiting a turn
        self._running_id: str | None = None

    @property
    def running_job_id(self) -> str | None:
        return self._running_id

    async def submit(self, kind: str, args: dict[str, object]) -> Job:
        argv = build_argv(kind, args, self._data_dir)  # raises JobKindError
        job = Job(
            id=f"job-{uuid.uuid4().hex[:8]}",
            kind=kind,
            args=args or {},
            status=JobStatus.queued,
            created_s=time.time(),
        )
        run = _JobRun(job, argv)
        self._runs[job.id] = run
        self._order.appendleft(job.id)
        while len(self._order) > _MAX_JOBS:
            old_id = self._order.pop()
            if old_id != self._running_id and old_id not in self._pending:
                self._runs.pop(old_id, None)
        if self._running_id is None:
            self._start(run)
        else:
            self._pending.append(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        run = self._runs.get(job_id)
        return run.job if run else None

    def list_jobs(self) -> list[JobSummary]:
        summaries = []
        for jid in self._order:
            run = self._runs.get(jid)
            if run is None:
                continue
            summaries.append(
                JobSummary(
                    id=run.job.id,
                    kind=run.job.kind,
                    status=run.job.status,
                    created_s=run.job.created_s,
                )
            )
        return summaries

    async def cancel(self, job_id: str) -> bool:
        run = self._runs.get(job_id)
        if run is None or run.job.status in _TERMINAL_STATUSES:
            return False
        run.job.status = JobStatus.cancelled
        if job_id == self._running_id:
            if run.proc is not None and run.proc.returncode is None:
                run.proc.terminate()
            # _execute()'s finally clause closes the stream once the process exits.
        else:
            try:
                self._pending.remove(job_id)
            except ValueError:
                pass
            run.emit(JobLogMessage(type="status", status=JobStatus.cancelled, exit_code=None))
            run.close()
        return True

    async def subscribe(self, job_id: str) -> AsyncIterator[JobLogMessage]:
        run = self._runs.get(job_id)
        if run is None:
            return
        q: asyncio.Queue[JobLogMessage | None] = asyncio.Queue()
        for backlog_msg in list(run.buffer):
            q.put_nowait(backlog_msg)
        if run.job.status in _TERMINAL_STATUSES:
            q.put_nowait(None)
        else:
            run.subscribers.append(q)
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    return
                yield msg
        finally:
            # Ensure an abandoned subscriber (WS disconnect before job completion) is
            # pruned once this generator is closed/GC'd, so emit() stops pushing to it.
            try:
                run.subscribers.remove(q)
            except ValueError:
                pass

    def _start(self, run: _JobRun) -> None:
        self._running_id = run.job.id
        run.job.status = JobStatus.running
        # Reference intentionally not retained: the task streams its subprocess to
        # completion and hands off to the next queued job in its own finally clause,
        # so it always runs to done and is never garbage-collected while pending.
        asyncio.create_task(self._execute(run))

    def _advance(self) -> None:
        self._running_id = None
        while self._pending:
            next_id = self._pending.popleft()
            next_run = self._runs.get(next_id)
            if next_run is None:
                continue
            if next_run.job.status == JobStatus.cancelled:
                next_run.close()
                continue
            self._start(next_run)
            return

    async def _execute(self, run: _JobRun) -> None:
        # Everything below runs inside a finally-guarded block so the queue can never
        # wedge: whatever happens in the body, _advance() (which clears _running_id
        # and starts the next queued job) always runs exactly once at the end.
        job = run.job
        try:
            if job.status == JobStatus.cancelled:
                run.close()
                return
            job.started_s = time.time()
            try:
                run.proc = await asyncio.create_subprocess_exec(
                    *self._htdp,
                    *run.argv,
                    cwd=str(self._data_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert run.proc.stdout is not None
                async for raw in run.proc.stdout:
                    line = raw.decode(errors="replace").rstrip("\n")
                    run.emit(JobLogMessage(type="log", line=line))
                    m = _PROGRESS_RE.search(line)
                    if m:
                        run.emit(
                            JobLogMessage(
                                type="progress", current=int(m.group(1)), total=int(m.group(2))
                            )
                        )
                code = await run.proc.wait()
            except Exception as exc:  # noqa: BLE001 - surface any spawn/stream error as a failed job
                job.status = JobStatus.failed
                job.error = str(exc)
                job.ended_s = time.time()
                run.emit(JobLogMessage(type="status", status=job.status, exit_code=None))
                run.close()
                return
            job.exit_code = code
            job.ended_s = time.time()
            if _status_of(job) != JobStatus.cancelled:
                job.status = JobStatus.done if code == 0 else JobStatus.failed
                if job.status == JobStatus.failed:
                    job.error = f"exit code {code}"
            run.emit(JobLogMessage(type="status", status=job.status, exit_code=code))
            run.close()
        finally:
            self._advance()
