# Robot-Lab Control Center — Sub-project A (Serving + Control Spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `htdp serve` (read-only + job-runner FastAPI) in the pipeline repo and a `/lab` control-center shell in the Angular app that shows live pipeline status and runs one `htdp` job end-to-end from a button.

**Architecture:** The pipeline gains an optional `serve` extra exposing read endpoints (filesystem tier counts) and a single-concurrency job runner that spawns allowlisted `htdp` subcommands and streams their logs over WebSocket. The Angular app gains a `core/pipeline` typed client, a signal-based `LabState`, and a lazy `/lab` shell — the sim viewer, metrics, and dataset browser are later sub-projects (B/C/D) that reuse this spine.

**Tech Stack:** Python 3.11, FastAPI + uvicorn, Typer, Pydantic v2, asyncio subprocess, pytest. Angular 19 standalone, Signals, RxJS, native `fetch` + `WebSocket`.

## Global Constraints

- Pipeline package is `htdp`; CLI entry is `htdp.cli:app` (Typer). Repo: `~/human-task-dataset-pipeline`.
- App repo: `~/neurofeedback-lang-app`. Component selector prefix `app`. Prefer Signals for new component state (per CLAUDE.md).
- `serve` is an **optional extra**: `uv sync --extra serve`. Core install and core tests must pass without it. All `serve` tests gated behind `pytest.importorskip("fastapi")`.
- Server binds `127.0.0.1` only. CORS allows origin `http://localhost:4200`.
- Job runner: **max 1 running**, FIFO queue. Subprocess spawn is `asyncio.create_subprocess_exec` — **never `shell=True`, never a shell string**.
- Job runner executes **only allowlisted `kind`s** with typed, range-validated args. **Output paths are server-controlled, never taken from the request.**
- Pipeline quality gate (run before each pipeline commit): `uv run ruff format --check . && uv run ruff check . && uv run pytest`; plus `uv run mypy src/htdp/serve`.
- App has no working `ng test` (Karma broken repo-wide). App-side specs are write-only; **verify compilation** with `npx tsc --noEmit` and `ng build --configuration development`.
- Contract source of truth = Pydantic models in `src/htdp/serve/models.py`; TS interfaces mirror them. Frozen shapes are in the spec (`docs/superpowers/specs/2026-07-12-robot-lab-control-center-spine-design.md`).
- Do not modify any existing `htdp` CLI command, schema, or data tier.

---

## File Structure

**Pipeline repo (`~/human-task-dataset-pipeline`):**
- Create `src/htdp/serve/__init__.py` — package marker.
- Create `src/htdp/serve/models.py` — Pydantic contract models.
- Create `src/htdp/serve/jobs.py` — `JobManager`, `JobSpec` allowlist, argv builder.
- Create `src/htdp/serve/status.py` — filesystem status reader.
- Create `src/htdp/serve/app.py` — FastAPI app factory `create_app(data_dir)`.
- Modify `src/htdp/cli.py` — add `serve` command.
- Modify `pyproject.toml` — add `serve` extra + mypy override.
- Modify `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` — record the "no servers" v0.2 exception.
- Create tests under `tests/serve/`.

**App repo (`~/neurofeedback-lang-app`):**
- Modify `src/app/environments/environment.ts` — add `pipelineApiUrl`, `pipelineSimWsUrl`.
- Create `src/app/core/pipeline/pipeline.models.ts` — TS interfaces mirroring Pydantic.
- Create `src/app/core/pipeline/pipeline-api.service.ts` — typed client.
- Create `src/app/modules/lab/state/lab.state.ts` — signal-based `LabState`.
- Create `src/app/modules/lab/lab.routes.ts` — `/lab` routes.
- Create `src/app/modules/lab/components/lab-shell/lab-shell.component.ts` — the shell.
- Modify `src/app/app.routes.ts` — register `/lab`.
- Modify `src/app/shared/components/layout/navigation/navigation.component.ts` — nav entry.
- Create matching `.spec.ts` files (write-only).

---

## PIPELINE REPO TASKS

All pipeline tasks run with cwd = `~/human-task-dataset-pipeline`. Install once before Task 1:

```bash
uv sync --extra dev
uv add --optional serve "fastapi>=0.110" "uvicorn>=0.27" "httpx>=0.27"
uv sync --extra serve --extra dev
```

(`httpx` is needed by FastAPI's `TestClient`.)

### Task 1: Contract models + job allowlist/argv builder

**Files:**
- Create: `src/htdp/serve/__init__.py`
- Create: `src/htdp/serve/models.py`
- Create: `src/htdp/serve/jobs.py` (argv builder portion only this task)
- Test: `tests/serve/__init__.py`, `tests/serve/test_argv.py`

**Interfaces:**
- Produces:
  - `models.PipelineStatus`, `models.TierCount`, `models.CountBlock`, `models.PolicyInfo`, `models.Job`, `models.JobSummary`, `models.JobStatus` (str enum), `models.JobLogMessage`.
  - `models.StartJobRequest {kind: str, args: dict}`.
  - `jobs.build_argv(kind: str, args: dict, data_dir: Path) -> list[str]` — returns argv **excluding** the leading `htdp` (e.g. `["gen-demos", "--out", "demos", ...]`). Raises `jobs.JobKindError` on unknown kind or invalid args.
  - `jobs.ALLOWED_KINDS: frozenset[str]`.

- [ ] **Step 1: Create package markers**

Create `src/htdp/serve/__init__.py` (empty) and `tests/serve/__init__.py` (empty).

- [ ] **Step 2: Write the failing argv test**

Create `tests/serve/test_argv.py`:

```python
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from htdp.serve.jobs import ALLOWED_KINDS, JobKindError, build_argv


def test_gen_demos_argv_uses_server_paths():
    argv = build_argv("gen-demos", {"n_train": 10, "n_test": 2}, Path("/data"))
    assert argv == ["gen-demos", "--out", "demos", "--n-train", "10", "--n-test", "2"]


def test_unknown_kind_rejected():
    with pytest.raises(JobKindError):
        build_argv("rm-rf", {}, Path("/data"))


def test_out_of_range_arg_rejected():
    with pytest.raises(JobKindError):
        build_argv("gen-demos", {"n_train": 999999}, Path("/data"))


def test_request_cannot_inject_output_path():
    # An attacker-supplied 'out' must be ignored, not forwarded.
    argv = build_argv("gen-demos", {"out": "/etc/passwd", "n_train": 5}, Path("/data"))
    assert "/etc/passwd" not in argv
    assert "demos" in argv


def test_train_policy_argv():
    argv = build_argv("train-policy", {"steps": 100}, Path("/data"))
    assert argv == ["train-policy", "--demos", "demos", "--out", "policy.pt", "--steps", "100"]


def test_eval_policy_argv():
    assert build_argv("eval-policy", {}, Path("/data")) == [
        "eval-policy", "--demos", "demos", "--policy", "policy.pt",
    ]


def test_all_allowed_kinds_build():
    for kind in ALLOWED_KINDS:
        build_argv(kind, {}, Path("/data"))  # defaults must be valid
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/serve/test_argv.py -v`
Expected: FAIL — `ModuleNotFoundError: htdp.serve.jobs`.

- [ ] **Step 4: Write models**

Create `src/htdp/serve/models.py`:

```python
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


class Tiers(BaseModel):
    raw: CountBlock
    processed: CountBlock
    releases: CountBlock


class PolicyInfo(BaseModel):
    present: bool
    path: str | None = None
    mtime_s: float | None = None


class PipelineStatus(BaseModel):
    data_dir: str
    tiers: Tiers
    demos: CountBlock | None = None
    policy: PolicyInfo
    running_job: str | None = None


class Job(BaseModel):
    id: str
    kind: str
    args: dict = Field(default_factory=dict)
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
    args: dict = Field(default_factory=dict)


class JobLogMessage(BaseModel):
    type: str            # "log" | "progress" | "status"
    line: str | None = None
    current: int | None = None
    total: int | None = None
    status: JobStatus | None = None
    exit_code: int | None = None
```

- [ ] **Step 5: Write argv builder**

Create `src/htdp/serve/jobs.py`:

```python
"""Job kind allowlist + argv builder. Security boundary: only known htdp subcommands,
typed/validated args, server-controlled output paths."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class JobKindError(ValueError):
    """Raised for an unknown job kind or invalid job args."""


class _GenDemosArgs(BaseModel):
    n_train: int = Field(100, ge=1, le=2000)
    n_test: int = Field(25, ge=1, le=500)
    seed: int = Field(0, ge=0)


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
    return ["gen-demos", "--out", "demos", "--n-train", str(a.n_train),
            "--n-test", str(a.n_test), "--seed", str(a.seed)]


def _train_argv(a: _TrainArgs, data_dir: Path) -> list[str]:
    return ["train-policy", "--demos", "demos", "--out", "policy.pt", "--steps", str(a.steps)]


def _eval_argv(a: _EmptyArgs, data_dir: Path) -> list[str]:
    return ["eval-policy", "--demos", "demos", "--policy", "policy.pt"]


_SPECS: dict[str, tuple[type[BaseModel], Callable]] = {
    "synth": (_SynthArgs, _synth_argv),
    "gen-demos": (_GenDemosArgs, _gen_demos_argv),
    "train-policy": (_TrainArgs, _train_argv),
    "eval-policy": (_EmptyArgs, _eval_argv),
}

ALLOWED_KINDS = frozenset(_SPECS)


def build_argv(kind: str, args: dict, data_dir: Path) -> list[str]:
    spec = _SPECS.get(kind)
    if spec is None:
        raise JobKindError(f"unknown job kind: {kind!r}")
    model_cls, builder = spec
    try:
        parsed = model_cls.model_validate(args or {})
    except ValidationError as exc:
        raise JobKindError(f"invalid args for {kind!r}: {exc}") from exc
    return builder(parsed, data_dir)
```

Note: `sim-task` from the spec allowlist is deferred to sub-project D (it needs the video/path handling that belongs with the viewer); A ships `synth`, `gen-demos`, `train-policy`, `eval-policy`.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/serve/test_argv.py -v`
Expected: PASS (7 passed).

- [ ] **Step 7: Quality gate + commit**

```bash
uv run ruff format . && uv run ruff check . && uv run pytest tests/serve/ -q
uv run mypy src/htdp/serve
git add src/htdp/serve pyproject.toml uv.lock tests/serve
git commit -m "feat(serve): job-kind allowlist, argv builder, contract models"
```

### Task 2: JobManager (queue, single concurrency, subprocess, cancel, logs)

**Files:**
- Modify: `src/htdp/serve/jobs.py` (append `JobManager`)
- Test: `tests/serve/test_jobmanager.py`

**Interfaces:**
- Consumes: `build_argv`, `Job`, `JobStatus`, `JobLogMessage` from Task 1.
- Produces:
  - `jobs.JobManager(data_dir: Path, htdp_cmd: list[str] = ["htdp"])`.
  - `async submit(kind: str, args: dict) -> Job` — validates via `build_argv`, enqueues, returns the `queued`/`running` job. Raises `JobKindError` on bad input.
  - `get(job_id: str) -> Job | None`; `list_jobs() -> list[JobSummary]` (newest first, bounded to 50).
  - `async cancel(job_id: str) -> bool`.
  - `async subscribe(job_id: str) -> AsyncIterator[JobLogMessage]` — yields buffered backlog then live frames until the terminal `status` frame.
  - `running_job_id -> str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/serve/test_jobmanager.py`:

```python
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
```

Add to `pyproject.toml` dev extra if missing: `pytest-asyncio>=0.23`, and under `[tool.pytest.ini_options]` add `asyncio_mode = "auto"`. (Run `uv add --optional dev "pytest-asyncio>=0.23" && uv sync --extra serve --extra dev`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/serve/test_jobmanager.py -v`
Expected: FAIL — `ImportError: cannot import name 'JobManager'`.

- [ ] **Step 3: Implement JobManager**

Append to `src/htdp/serve/jobs.py`:

```python
import asyncio
import re
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator

from htdp.serve.models import Job, JobLogMessage, JobStatus, JobSummary

_PROGRESS_RE = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_MAX_JOBS = 50
_LOG_BUFFER = 2000


class _JobRun:
    def __init__(self, job: Job, argv: list[str]) -> None:
        self.job = job
        self.argv = argv
        self.buffer: deque[JobLogMessage] = deque(maxlen=_LOG_BUFFER)
        self.subscribers: list[asyncio.Queue[JobLogMessage | None]] = []
        self.proc: asyncio.subprocess.Process | None = None
        self.done = asyncio.Event()

    def emit(self, msg: JobLogMessage) -> None:
        self.buffer.append(msg)
        for q in self.subscribers:
            q.put_nowait(msg)

    def close(self) -> None:
        for q in self.subscribers:
            q.put_nowait(None)


class JobManager:
    def __init__(self, data_dir: Path, htdp_cmd: list[str] | None = None) -> None:
        self._data_dir = data_dir
        self._htdp = list(htdp_cmd) if htdp_cmd else ["htdp"]
        self._runs: dict[str, _JobRun] = {}
        self._order: deque[str] = deque()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running_id: str | None = None
        self._worker: asyncio.Task | None = None

    @property
    def running_job_id(self) -> str | None:
        return self._running_id

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_loop())

    async def submit(self, kind: str, args: dict) -> Job:
        argv = build_argv(kind, args, self._data_dir)  # raises JobKindError
        job = Job(id=f"job-{uuid.uuid4().hex[:8]}", kind=kind, args=args or {},
                  status=JobStatus.queued, created_s=time.time())
        self._runs[job.id] = _JobRun(job, argv)
        self._order.appendleft(job.id)
        while len(self._order) > _MAX_JOBS:
            self._runs.pop(self._order.pop(), None)
        self._ensure_worker()
        if self._running_id is None:
            job.status = JobStatus.running  # optimistic; worker confirms immediately
        await self._queue.put(job.id)
        return job

    def get(self, job_id: str) -> Job | None:
        run = self._runs.get(job_id)
        return run.job if run else None

    def list_jobs(self) -> list[JobSummary]:
        return [JobSummary(id=r.job.id, kind=r.job.kind, status=r.job.status,
                           created_s=r.job.created_s)
                for jid in self._order if (r := self._runs.get(jid))]

    async def cancel(self, job_id: str) -> bool:
        run = self._runs.get(job_id)
        if run is None or run.job.status in (JobStatus.done, JobStatus.failed,
                                             JobStatus.cancelled):
            return False
        run.job.status = JobStatus.cancelled
        if run.proc and run.proc.returncode is None:
            run.proc.terminate()
        return True

    async def subscribe(self, job_id: str) -> AsyncIterator[JobLogMessage]:
        run = self._runs.get(job_id)
        if run is None:
            return
        q: asyncio.Queue[JobLogMessage | None] = asyncio.Queue()
        for msg in list(run.buffer):
            q.put_nowait(msg)
        if run.job.status in (JobStatus.done, JobStatus.failed, JobStatus.cancelled):
            q.put_nowait(None)
        else:
            run.subscribers.append(q)
        while True:
            msg = await q.get()
            if msg is None:
                return
            yield msg

    async def _run_loop(self) -> None:
        while True:
            try:
                job_id = await asyncio.wait_for(self._queue.get(), timeout=30)
            except asyncio.TimeoutError:
                return  # idle; a new submit re-spawns the worker
            run = self._runs.get(job_id)
            if run is None or run.job.status == JobStatus.cancelled:
                if run:
                    run.close()
                continue
            await self._execute(run)

    async def _execute(self, run: _JobRun) -> None:
        job = run.job
        self._running_id = job.id
        job.status = JobStatus.running
        job.started_s = time.time()
        try:
            run.proc = await asyncio.create_subprocess_exec(
                *self._htdp, *run.argv, cwd=str(self._data_dir),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            assert run.proc.stdout is not None
            async for raw in run.proc.stdout:
                line = raw.decode(errors="replace").rstrip("\n")
                run.emit(JobLogMessage(type="log", line=line))
                m = _PROGRESS_RE.search(line)
                if m:
                    run.emit(JobLogMessage(type="progress",
                                           current=int(m.group(1)), total=int(m.group(2))))
            code = await run.proc.wait()
        except Exception as exc:  # noqa: BLE001 - surface any spawn error as a failed job
            job.status = JobStatus.failed
            job.error = str(exc)
            job.ended_s = time.time()
            run.emit(JobLogMessage(type="status", status=job.status, exit_code=None))
            run.close()
            self._running_id = None
            return
        job.exit_code = code
        job.ended_s = time.time()
        if job.status == JobStatus.cancelled:
            pass
        elif code == 0:
            job.status = JobStatus.done
        else:
            job.status = JobStatus.failed
            job.error = f"exit code {code}"
        run.emit(JobLogMessage(type="status", status=job.status, exit_code=code))
        run.close()
        self._running_id = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/serve/test_jobmanager.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Quality gate + commit**

```bash
uv run ruff format . && uv run ruff check . && uv run pytest tests/serve/ -q
uv run mypy src/htdp/serve
git add src/htdp/serve tests/serve pyproject.toml uv.lock
git commit -m "feat(serve): single-concurrency JobManager with log streaming + cancel"
```

### Task 3: Status reader + read endpoints

**Files:**
- Create: `src/htdp/serve/status.py`
- Create: `src/htdp/serve/app.py`
- Test: `tests/serve/test_read_endpoints.py`

**Interfaces:**
- Consumes: models from Task 1, `JobManager` from Task 2.
- Produces:
  - `status.read_status(data_dir: Path, manager: JobManager) -> PipelineStatus`.
  - `app.create_app(data_dir: Path, manager: JobManager | None = None) -> FastAPI` with routes `GET /health`, `GET /status`, `GET /jobs`, `GET /jobs/{id}`. Stores the manager on `app.state.manager`.

- [ ] **Step 1: Write the failing test**

Create `tests/serve/test_read_endpoints.py`:

```python
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from htdp.serve.app import create_app


def _seed(tmp: Path) -> None:
    for i in range(2):
        (tmp / "data" / "raw" / f"synth-{i:04d}").mkdir(parents=True)
    (tmp / "data" / "processed" / "synth-0000").mkdir(parents=True)
    (tmp / "data" / "releases").mkdir(parents=True)
    (tmp / "policy.pt").write_bytes(b"x")


def test_health(tmp_path):
    client = TestClient(create_app(tmp_path))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_status_counts(tmp_path):
    _seed(tmp_path)
    client = TestClient(create_app(tmp_path))
    body = client.get("/status").json()
    assert body["tiers"]["raw"]["count"] == 2
    assert body["tiers"]["processed"]["count"] == 1
    assert body["tiers"]["releases"]["count"] == 0
    assert body["policy"]["present"] is True
    assert body["running_job"] is None


def test_jobs_empty(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/jobs").json() == {"jobs": []}


def test_get_missing_job_404(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/jobs/nope").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/serve/test_read_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: htdp.serve.app`.

- [ ] **Step 3: Implement status reader**

Create `src/htdp/serve/status.py`:

```python
from __future__ import annotations

from pathlib import Path

from htdp.serve.jobs import JobManager
from htdp.serve.models import CountBlock, PipelineStatus, PolicyInfo, Tiers


def _count_dirs(p: Path) -> int:
    return sum(1 for c in p.iterdir() if c.is_dir()) if p.is_dir() else 0


def _demos_count(data_dir: Path) -> CountBlock | None:
    meta = data_dir / "demos" / "meta"
    if not meta.is_dir():
        return None
    return CountBlock(count=sum(1 for _ in meta.glob("*")))


def read_status(data_dir: Path, manager: JobManager) -> PipelineStatus:
    policy_path = data_dir / "policy.pt"
    policy = PolicyInfo(present=policy_path.is_file())
    if policy.present:
        policy.path = "policy.pt"
        policy.mtime_s = policy_path.stat().st_mtime
    return PipelineStatus(
        data_dir=str(data_dir.resolve()),
        tiers=Tiers(
            raw=CountBlock(count=_count_dirs(data_dir / "data" / "raw")),
            processed=CountBlock(count=_count_dirs(data_dir / "data" / "processed")),
            releases=CountBlock(count=_count_dirs(data_dir / "data" / "releases")),
        ),
        demos=_demos_count(data_dir),
        policy=policy,
        running_job=manager.running_job_id,
    )
```

- [ ] **Step 4: Implement app factory (read routes only)**

Create `src/htdp/serve/app.py`:

```python
from __future__ import annotations

from importlib.metadata import version as _pkg_version
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from htdp.serve.jobs import JobManager
from htdp.serve.status import read_status


def create_app(data_dir: Path, manager: JobManager | None = None) -> FastAPI:
    app = FastAPI(title="htdp serve", version="0.2.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:4200"],
        allow_methods=["*"], allow_headers=["*"],
    )
    app.state.data_dir = data_dir
    app.state.manager = manager or JobManager(data_dir)

    @app.get("/health")
    def health() -> dict:
        try:
            v = _pkg_version("htdp")
        except Exception:  # noqa: BLE001
            v = "unknown"
        return {"ok": True, "version": v}

    @app.get("/status")
    def status() -> dict:
        return read_status(app.state.data_dir, app.state.manager).model_dump()

    @app.get("/jobs")
    def jobs() -> dict:
        return {"jobs": [j.model_dump() for j in app.state.manager.list_jobs()]}

    @app.get("/jobs/{job_id}")
    def job(job_id: str) -> dict:
        got = app.state.manager.get(job_id)
        if got is None:
            raise HTTPException(status_code=404, detail="job not found")
        return got.model_dump()

    return app
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/serve/test_read_endpoints.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Quality gate + commit**

```bash
uv run ruff format . && uv run ruff check . && uv run pytest tests/serve/ -q
uv run mypy src/htdp/serve
git add src/htdp/serve tests/serve
git commit -m "feat(serve): status reader + read endpoints (health/status/jobs)"
```

### Task 4: Job control endpoints + log WebSocket

**Files:**
- Modify: `src/htdp/serve/app.py` (add POST/cancel/WS)
- Test: `tests/serve/test_job_endpoints.py`

**Interfaces:**
- Consumes: everything above.
- Produces routes: `POST /jobs` (`StartJobRequest` → `{job_id}`), `POST /jobs/{id}/cancel`, `WS /jobs/{id}/logs`.

- [ ] **Step 1: Write the failing test**

Create `tests/serve/test_job_endpoints.py`:

```python
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from htdp.serve.app import create_app
from htdp.serve.jobs import JobManager


def _fake_mgr(tmp: Path):
    return JobManager(tmp, htdp_cmd=[sys.executable, "-c",
                                     "print('go'); print('1/1')", "--"])


def test_start_unknown_kind_400(tmp_path):
    client = TestClient(create_app(tmp_path, _fake_mgr(tmp_path)))
    r = client.post("/jobs", json={"kind": "rm-rf", "args": {}})
    assert r.status_code == 400


def test_start_and_stream_logs(tmp_path):
    client = TestClient(create_app(tmp_path, _fake_mgr(tmp_path)))
    job_id = client.post("/jobs", json={"kind": "eval-policy", "args": {}}).json()["job_id"]
    frames = []
    with client.websocket_connect(f"/jobs/{job_id}/logs") as ws:
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame["type"] == "status":
                break
    assert frames[-1]["status"] == "done"
    assert any(f.get("line") == "go" for f in frames)


def test_bad_args_400(tmp_path):
    client = TestClient(create_app(tmp_path, _fake_mgr(tmp_path)))
    r = client.post("/jobs", json={"kind": "gen-demos", "args": {"n_train": 10**9}})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/serve/test_job_endpoints.py -v`
Expected: FAIL — 404/405 on `POST /jobs` (route absent).

- [ ] **Step 3: Add job routes to app.py**

Insert into `create_app` (before `return app`), and add imports at top:

```python
from fastapi import WebSocket, WebSocketDisconnect
from htdp.serve.jobs import JobKindError
from htdp.serve.models import StartJobRequest
```

```python
    @app.post("/jobs")
    async def start_job(req: StartJobRequest) -> dict:
        try:
            job = await app.state.manager.submit(req.kind, req.args)
        except JobKindError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job_id": job.id}

    @app.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict:
        ok = await app.state.manager.cancel(job_id)
        return {"cancelled": ok}

    @app.websocket("/jobs/{job_id}/logs")
    async def job_logs(ws: WebSocket, job_id: str) -> None:
        await ws.accept()
        try:
            async for msg in app.state.manager.subscribe(job_id):
                await ws.send_json(msg.model_dump(exclude_none=True))
        except WebSocketDisconnect:
            return
        await ws.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/serve/test_job_endpoints.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Full serve suite + quality gate + commit**

```bash
uv run pytest tests/serve/ -q
uv run ruff format . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/serve
git add src/htdp/serve tests/serve
git commit -m "feat(serve): job start/cancel endpoints + log WebSocket"
```

### Task 5: `htdp serve` CLI command + docs exception note

**Files:**
- Modify: `src/htdp/cli.py` (add `serve` command at end)
- Modify: `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`
- Test: `tests/serve/test_cli_serve.py`

**Interfaces:**
- Consumes: `create_app`.
- Produces: `htdp serve [--host] [--port] [--data-dir]`.

- [ ] **Step 1: Write the failing test**

Create `tests/serve/test_cli_serve.py`:

```python
import pytest

pytest.importorskip("fastapi")
from typer.testing import CliRunner

from htdp.cli import app


def test_serve_command_registered():
    result = CliRunner().invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--port" in result.output
    assert "--data-dir" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/serve/test_cli_serve.py -v`
Expected: FAIL — `serve` not a known command (exit_code != 0).

- [ ] **Step 3: Add the CLI command**

Append to `src/htdp/cli.py`:

```python
@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    data_dir: Path = typer.Option(Path("."), "--data-dir"),
) -> None:
    """Run the read-only + job-runner dashboard server (optional extra: serve)."""
    try:
        import uvicorn

        from htdp.serve.app import create_app
    except ImportError as exc:
        typer.echo("error: install the serve extra: uv sync --extra serve", err=True)
        raise typer.Exit(1) from exc

    uvicorn.run(create_app(data_dir.resolve()), host=host, port=port)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/serve/test_cli_serve.py -v`
Expected: PASS.

- [ ] **Step 5: Record the "no servers" exception in docs**

In `docs/ARCHITECTURE.md`, under "Design constraints (v0.1)", append a note after the `**No servers**` bullet:

```markdown
> **v0.2 exception — `htdp serve`.** A read-only + job-runner dashboard server
> (optional extra `serve`, localhost-only, `uv sync --extra serve`) exposes filesystem
> tier status and spawns allowlisted `htdp` subcommands for the control-center dashboard.
> It creates no new data representation and is never part of the dataset product.
```

In `docs/ROADMAP.md`, add under the v0.2 section a line:

```markdown
- `htdp serve` — dashboard serving surface (read endpoints + single-concurrency job runner);
  localhost-only, optional `serve` extra. Consumed by the Angular control-center dashboard.
```

- [ ] **Step 6: Full gate + commit**

```bash
uv run ruff format . && uv run ruff check . && uv run pytest
uv run mypy src/htdp/serve
git add src/htdp/cli.py docs/ARCHITECTURE.md docs/ROADMAP.md tests/serve
git commit -m "feat(serve): htdp serve CLI command + document no-servers v0.2 exception"
```

- [ ] **Step 7: Manual smoke (record output in the task notes)**

```bash
uv run htdp serve --port 8000 &
sleep 2
curl -s localhost:8000/health
curl -s localhost:8000/status
kill %1
```

Expected: `{"ok":true,...}` and a status JSON with tier counts.

---

## APP REPO TASKS

All app tasks run with cwd = `~/neurofeedback-lang-app`. There is no working `ng test`; verify with `npx tsc --noEmit` and `ng build --configuration development`.

### Task 6: environment config + PipelineApiService

**Files:**
- Modify: `src/app/environments/environment.ts`
- Create: `src/app/core/pipeline/pipeline.models.ts`
- Create: `src/app/core/pipeline/pipeline-api.service.ts`
- Create: `src/app/core/pipeline/pipeline-api.service.spec.ts` (write-only)

**Interfaces:**
- Produces:
  - Models mirroring Pydantic: `PipelineStatus`, `Tiers`, `CountBlock`, `PolicyInfo`, `Job`, `JobSummary`, `JobLogMessage`, `JobStatus` (union type), `StartJobRequest`.
  - `PipelineApiService` with: `getStatus(): Promise<PipelineStatus>`, `listJobs(): Promise<JobSummary[]>`, `getJob(id): Promise<Job>`, `startJob(kind, args): Promise<string>` (returns job_id), `cancelJob(id): Promise<boolean>`, `jobLogs(id): Observable<JobLogMessage>`.

- [ ] **Step 1: Add environment keys**

In `src/app/environments/environment.ts`, add inside the object (after `simWsUrl`):

```typescript
  pipelineApiUrl: 'http://localhost:8000',
  pipelineSimWsUrl: 'ws://localhost:8000/sim', // used by sub-project D
```

- [ ] **Step 2: Create the models file**

Create `src/app/core/pipeline/pipeline.models.ts`:

```typescript
// Mirrors src/htdp/serve/models.py — keep in sync (contract per spec).
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface CountBlock { count: number; }
export interface Tiers { raw: CountBlock; processed: CountBlock; releases: CountBlock; }
export interface PolicyInfo { present: boolean; path?: string | null; mtime_s?: number | null; }

export interface PipelineStatus {
  data_dir: string;
  tiers: Tiers;
  demos?: CountBlock | null;
  policy: PolicyInfo;
  running_job: string | null;
}

export interface Job {
  id: string;
  kind: string;
  args: Record<string, unknown>;
  status: JobStatus;
  exit_code?: number | null;
  created_s: number;
  started_s?: number | null;
  ended_s?: number | null;
  error?: string | null;
}

export interface JobSummary {
  id: string; kind: string; status: JobStatus; created_s: number;
}

export interface JobLogMessage {
  type: 'log' | 'progress' | 'status';
  line?: string;
  current?: number;
  total?: number;
  status?: JobStatus;
  exit_code?: number;
}
```

- [ ] **Step 3: Write the failing service spec**

Create `src/app/core/pipeline/pipeline-api.service.spec.ts`:

```typescript
import { PipelineApiService } from './pipeline-api.service';

describe('PipelineApiService', () => {
  it('startJob posts kind+args and returns job_id', async () => {
    const svc = new PipelineApiService();
    spyOn(window, 'fetch').and.resolveTo(
      new Response(JSON.stringify({ job_id: 'job-1' }), { status: 200 }),
    );
    const id = await svc.startJob('gen-demos', { n_train: 10 });
    expect(id).toBe('job-1');
  });

  it('getStatus rejects on non-ok response', async () => {
    const svc = new PipelineApiService();
    spyOn(window, 'fetch').and.resolveTo(new Response('nope', { status: 500 }));
    await expectAsync(svc.getStatus()).toBeRejected();
  });
});
```

- [ ] **Step 4: Implement the service**

Create `src/app/core/pipeline/pipeline-api.service.ts`:

```typescript
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { Job, JobLogMessage, JobSummary, PipelineStatus } from './pipeline.models';

@Injectable({ providedIn: 'root' })
export class PipelineApiService {
  private readonly base = environment.pipelineApiUrl;

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.base}${path}`, init);
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  getStatus(): Promise<PipelineStatus> { return this.json('/status'); }

  async listJobs(): Promise<JobSummary[]> {
    const body = await this.json<{ jobs: JobSummary[] }>('/jobs');
    return body.jobs;
  }

  getJob(id: string): Promise<Job> { return this.json(`/jobs/${id}`); }

  async startJob(kind: string, args: Record<string, unknown>): Promise<string> {
    const body = await this.json<{ job_id: string }>('/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, args }),
    });
    return body.job_id;
  }

  async cancelJob(id: string): Promise<boolean> {
    const body = await this.json<{ cancelled: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' });
    return body.cancelled;
  }

  jobLogs(id: string): Observable<JobLogMessage> {
    const wsBase = this.base.replace(/^http/, 'ws');
    return new Observable<JobLogMessage>(sub => {
      const ws = new WebSocket(`${wsBase}/jobs/${id}/logs`);
      ws.onmessage = ev => {
        try { sub.next(JSON.parse(ev.data as string) as JobLogMessage); } catch { /* ignore */ }
      };
      ws.onerror = () => sub.error(new Error('job log ws error'));
      ws.onclose = () => sub.complete();
      return () => ws.close();
    });
  }
}
```

- [ ] **Step 5: Verify compilation**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit** (only if the user has asked you to commit; otherwise leave staged per repo convention)

```bash
git add src/app/environments/environment.ts src/app/core/pipeline
git commit -m "feat(lab): pipeline API client + typed contract models"
```

### Task 7: LabState signal service

**Files:**
- Create: `src/app/modules/lab/state/lab.state.ts`
- Create: `src/app/modules/lab/state/lab.state.spec.ts` (write-only)

**Interfaces:**
- Consumes: `PipelineApiService`, models.
- Produces `LabState` (`providedIn: 'root'`) with signals: `status: Signal<PipelineStatus | null>`, `jobs: Signal<JobSummary[]>`, `connection: Signal<'online'|'offline'|'unknown'>`, `logLines: Signal<string[]>`, `progress: Signal<{current:number;total:number}|null>`, `watchedJobStatus: Signal<JobStatus|null>`; methods `startPolling()`, `stopPolling()`, `run(kind,args)`, `watch(jobId)`, `cancel(jobId)`.

- [ ] **Step 1: Write the failing spec**

Create `src/app/modules/lab/state/lab.state.spec.ts`:

```typescript
import { LabState } from './lab.state';

function fakeApi(overrides: Partial<any> = {}): any {
  return {
    getStatus: jasmine.createSpy().and.resolveTo({
      data_dir: '/d', tiers: { raw: { count: 1 }, processed: { count: 0 }, releases: { count: 0 } },
      policy: { present: false }, running_job: null,
    }),
    listJobs: jasmine.createSpy().and.resolveTo([]),
    startJob: jasmine.createSpy().and.resolveTo('job-9'),
    cancelJob: jasmine.createSpy().and.resolveTo(true),
    jobLogs: jasmine.createSpy(),
    ...overrides,
  };
}

describe('LabState', () => {
  it('refresh populates status and marks online', async () => {
    const state = new LabState(fakeApi());
    await state.refresh();
    expect(state.status()?.tiers.raw.count).toBe(1);
    expect(state.connection()).toBe('online');
  });

  it('refresh marks offline when the API throws', async () => {
    const api = fakeApi({ getStatus: jasmine.createSpy().and.rejectWith(new Error('down')) });
    const state = new LabState(api);
    await state.refresh();
    expect(state.connection()).toBe('offline');
  });

  it('run returns the new job id', async () => {
    const state = new LabState(fakeApi());
    expect(await state.run('gen-demos', { n_train: 5 })).toBe('job-9');
  });
});
```

- [ ] **Step 2: Run/verify it fails (compilation)**

Run: `npx tsc --noEmit`
Expected: FAIL — `Cannot find module './lab.state'`.

- [ ] **Step 3: Implement LabState**

Create `src/app/modules/lab/state/lab.state.ts`:

```typescript
import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { PipelineApiService } from '../../../core/pipeline/pipeline-api.service';
import { JobStatus, JobSummary, PipelineStatus } from '../../../core/pipeline/pipeline.models';

const POLL_MS = 3000;

@Injectable({ providedIn: 'root' })
export class LabState {
  private readonly api: PipelineApiService;
  constructor(api?: PipelineApiService) { this.api = api ?? inject(PipelineApiService); }

  private readonly _status = signal<PipelineStatus | null>(null);
  private readonly _jobs = signal<JobSummary[]>([]);
  private readonly _connection = signal<'online' | 'offline' | 'unknown'>('unknown');
  private readonly _logLines = signal<string[]>([]);
  private readonly _progress = signal<{ current: number; total: number } | null>(null);
  private readonly _watchedStatus = signal<JobStatus | null>(null);

  readonly status = computed(() => this._status());
  readonly jobs = computed(() => this._jobs());
  readonly connection = computed(() => this._connection());
  readonly logLines = computed(() => this._logLines());
  readonly progress = computed(() => this._progress());
  readonly watchedJobStatus = computed(() => this._watchedStatus());

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private logSub: Subscription | null = null;

  async refresh(): Promise<void> {
    try {
      const [status, jobs] = await Promise.all([this.api.getStatus(), this.api.listJobs()]);
      this._status.set(status);
      this._jobs.set(jobs);
      this._connection.set('online');
    } catch {
      this._connection.set('offline');
    }
  }

  startPolling(): void {
    if (this.pollTimer !== null) return;
    void this.refresh();
    this.pollTimer = setInterval(() => void this.refresh(), POLL_MS);
  }

  stopPolling(): void {
    if (this.pollTimer !== null) { clearInterval(this.pollTimer); this.pollTimer = null; }
  }

  async run(kind: string, args: Record<string, unknown>): Promise<string> {
    const id = await this.api.startJob(kind, args);
    this.watch(id);
    void this.refresh();
    return id;
  }

  watch(jobId: string): void {
    this.logSub?.unsubscribe();
    this._logLines.set([]);
    this._progress.set(null);
    this._watchedStatus.set('running');
    this.logSub = this.api.jobLogs(jobId).subscribe({
      next: msg => {
        if (msg.type === 'log' && msg.line !== undefined) {
          this._logLines.update(l => [...l.slice(-500), msg.line!]);
        } else if (msg.type === 'progress' && msg.current !== undefined && msg.total !== undefined) {
          this._progress.set({ current: msg.current, total: msg.total });
        } else if (msg.type === 'status' && msg.status) {
          this._watchedStatus.set(msg.status);
          void this.refresh();
        }
      },
      error: () => this._watchedStatus.set(null),
    });
  }

  async cancel(jobId: string): Promise<void> {
    await this.api.cancelJob(jobId);
    void this.refresh();
  }
}
```

- [ ] **Step 4: Verify compilation**

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit** (only if asked)

```bash
git add src/app/modules/lab/state
git commit -m "feat(lab): LabState signal service (status polling, run, watch, cancel)"
```

### Task 8: LabShellComponent + routing + nav entry

**Files:**
- Create: `src/app/modules/lab/components/lab-shell/lab-shell.component.ts`
- Create: `src/app/modules/lab/lab.routes.ts`
- Modify: `src/app/app.routes.ts`
- Modify: `src/app/shared/components/layout/navigation/navigation.component.ts`

**Interfaces:**
- Consumes: `LabState`.
- Produces: `LabShellComponent` (route `''`), `LAB_ROUTES`.

- [ ] **Step 1: Create the shell component**

Create `src/app/modules/lab/components/lab-shell/lab-shell.component.ts`:

```typescript
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { LabState } from '../../state/lab.state';

const JOB_KINDS = ['gen-demos', 'synth', 'train-policy', 'eval-policy'] as const;

@Component({
  selector: 'app-lab-shell',
  standalone: true,
  template: `
    <div class="lab">
      <header class="lab__head">
        <h1>Robot Lab</h1>
        <span class="lab__conn" [class.lab__conn--on]="state.connection() === 'online'">
          {{ state.connection() === 'online' ? 'server online' : 'server offline — run htdp serve' }}
        </span>
      </header>

      @if (state.status(); as s) {
        <section class="lab__tiles">
          <div class="tile"><span class="tile__n">{{ s.tiers.raw.count }}</span><span class="tile__l">raw</span></div>
          <div class="tile"><span class="tile__n">{{ s.tiers.processed.count }}</span><span class="tile__l">processed</span></div>
          <div class="tile"><span class="tile__n">{{ s.tiers.releases.count }}</span><span class="tile__l">releases</span></div>
          <div class="tile"><span class="tile__n">{{ s.demos?.count ?? 0 }}</span><span class="tile__l">demos</span></div>
          <div class="tile"><span class="tile__n">{{ s.policy.present ? 'yes' : 'no' }}</span><span class="tile__l">policy</span></div>
        </section>
      }

      <section class="lab__run">
        <label>Run job
          <select [value]="kind()" (change)="kind.set($any($event.target).value)">
            @for (k of kinds; track k) { <option [value]="k">{{ k }}</option> }
          </select>
        </label>
        <button (click)="run()" [disabled]="state.connection() !== 'online'">Run</button>
        @if (state.watchedJobStatus(); as js) { <span class="lab__jobstatus">{{ js }}</span> }
      </section>

      @if (state.progress(); as p) {
        <div class="lab__bar"><div class="lab__bar-fill" [style.width.%]="(p.current / p.total) * 100"></div></div>
      }

      <pre class="lab__logs">{{ state.logLines().join('\n') }}</pre>
    </div>
  `,
  styles: [`
    :host { display: block; padding: 24px; font-family: 'DM Sans', sans-serif; }
    .lab__head { display: flex; align-items: baseline; gap: 16px; }
    .lab__conn { font-family: 'DM Mono', monospace; font-size: 12px; color: #ef4444; }
    .lab__conn--on { color: #10b981; }
    .lab__tiles { display: flex; gap: 12px; margin: 20px 0; flex-wrap: wrap; }
    .tile { display: flex; flex-direction: column; padding: 14px 20px; border-radius: 10px; background: #f1f5f9; min-width: 84px; }
    .tile__n { font-family: 'DM Mono', monospace; font-size: 24px; font-weight: 600; }
    .tile__l { font-size: 12px; color: #64748b; }
    .lab__run { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .lab__bar { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-bottom: 12px; }
    .lab__bar-fill { height: 100%; background: #6366f1; transition: width .2s; }
    .lab__logs { background: #0f172a; color: #cbd5e1; font-family: 'DM Mono', monospace; font-size: 12px; padding: 14px; border-radius: 10px; height: 300px; overflow: auto; white-space: pre-wrap; }
  `],
})
export class LabShellComponent implements OnInit, OnDestroy {
  protected readonly state = inject(LabState);
  protected readonly kinds = JOB_KINDS;
  protected readonly kind = signal<(typeof JOB_KINDS)[number]>('gen-demos');

  ngOnInit(): void { this.state.startPolling(); }
  ngOnDestroy(): void { this.state.stopPolling(); }

  run(): void {
    const args = this.kind() === 'gen-demos' ? { n_train: 20, n_test: 4 } : {};
    void this.state.run(this.kind(), args);
  }
}
```

- [ ] **Step 2: Create lab routes**

Create `src/app/modules/lab/lab.routes.ts`:

```typescript
import { Routes } from '@angular/router';

export const LAB_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/lab-shell/lab-shell.component').then(m => m.LabShellComponent),
  },
];
```

- [ ] **Step 3: Register the route**

In `src/app/app.routes.ts`, add the import at top:

```typescript
import { LAB_ROUTES } from './modules/lab/lab.routes';
```

And add a top-level route sibling to `capture` (before the `''` shell route):

```typescript
  {
    path: 'lab',
    children: LAB_ROUTES,
  },
```

- [ ] **Step 4: Add the nav entry**

In `src/app/shared/components/layout/navigation/navigation.component.ts`, add to the nav items array (after the `demo` entry):

```typescript
    { route: '/lab', icon: 'precision_manufacturing', label: 'Robot Lab', exact: true },
```

- [ ] **Step 5: Verify compilation + build**

Run: `npx tsc --noEmit && ng build --configuration development`
Expected: build succeeds, no type errors.

- [ ] **Step 6: Manual acceptance (record result)**

1. Pipeline: `uv run htdp serve --port 8000` (in a directory with a `data/` tree, e.g. the pipeline repo root).
2. App: `npm start`, open `http://localhost:4200/lab`.
3. Confirm the status tiles show real counts and connection shows "server online".
4. Select `gen-demos`, click Run; confirm logs stream, progress bar advances, job status reaches `done`, and the demos tile count increases on the next poll.

- [ ] **Step 7: Commit** (only if asked)

```bash
git add src/app/modules/lab src/app/app.routes.ts src/app/shared/components/layout/navigation/navigation.component.ts
git commit -m "feat(lab): /lab control-center shell with status tiles + job runner"
```

---

## Self-Review Notes

- **Spec coverage:** §A.1 read endpoints → Task 3; job runner + WS → Tasks 2/4; security allowlist → Task 1; §A.2 client → Task 6, `LabState` → Task 7, `/lab` shell + routing + nav → Task 8; §A.3 contract pinned in Task 1 models + Task 6 mirror; "no servers" exception → Task 5. Sim WS/metrics/dataset browser correctly deferred (B/C/D).
- **Deviation from spec allowlist:** `sim-task` is deferred from A to D (needs path/video handling that lives with the viewer). A ships `synth`, `gen-demos`, `train-policy`, `eval-policy`. Recorded here intentionally.
- **Type consistency:** `PipelineStatus`/`Job`/`JobLogMessage`/`JobStatus` names identical across Pydantic (Task 1) and TS (Task 6); `JobManager` method names (`submit`/`get`/`list_jobs`/`cancel`/`subscribe`/`running_job_id`) used consistently in Tasks 2–4; `LabState` signal/method names consistent between Task 7 impl and Task 8 template.
- **Commit steps** in app tasks are gated "only if asked" to respect the repo's no-concurrent-commits rule; pipeline tasks commit normally (separate repo, no local-model executor there).
