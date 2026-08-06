# Robot-Lab Control Center — Sub-project A: Serving + Control Spine

**Date:** 2026-07-12
**Repos:** `neurofeedback-lang-app` (Angular dashboard) + `human-task-dataset-pipeline` (Python `htdp`)
**Status:** design, pending user review

## Purpose

Turn the Angular app into a **control center** for the robot-arm learning process that
lives in `human-task-dataset-pipeline`. The dashboard both *views* pipeline data and
*controls* the pipeline scripts (teleop, record, train, eval). This spec covers **only
sub-project A** — the serving + control spine that every later view builds on.

The pipeline is filesystem-first Python with no server. Sub-project A adds a read-only +
job-runner HTTP surface (`htdp serve`) and the Angular client/shell that drives it.

## Full-feature decomposition (context)

The overall control center is built as four sub-projects, each with its own
spec → plan → implementation cycle. This document details **A** only.

| Sub-project | Scope | Repos |
|---|---|---|
| **A. Serving + control spine** | `htdp serve` FastAPI (read endpoints + job runner) + app API client + `LabState` + `/lab` shell with live status panel, jobs panel, one runnable job button | both |
| **B. Metrics view** | eval/training metrics endpoints (read `docs/m2/*.json` + training logs) + charts | both |
| **C. Dataset browser** | catalog / QC / releases endpoints + browser UI | both |
| **D. Live sim viewer** | Franka Panda `/sim` WS rollout + Three.js Franka viewer + teleop-save recording | both |

Design decisions locked during brainstorming:

- Data bridge = **thin FastAPI read API** in the pipeline repo (not static export, not Supabase).
- Sim source = **pipeline Franka Panda** (the visuomotor learning loop), not the H1 handwerk sim.
- App identity = **add as a new `/lab` section**; existing routes (dashboard, exercises,
  capture) untouched.
- Job concurrency = **one at a time** (shared MPS/sim); further requests queue.
- "Record" in A = **`htdp gen-demos`** (scripted-teacher demos); teleop-save deferred to D.

### The "no servers" exception

The pipeline's v0.1 design (`docs/ARCHITECTURE.md`) states **"No servers."** `htdp serve`
is a deliberate v0.2 exception, justified and bounded:

- **Read-only + job-runner only** — serves existing filesystem tiers and spawns existing
  `htdp` subcommands. It creates no new data representation and is never part of the dataset
  product (the release remains the product unit).
- **Optional extra** — `uv sync --extra serve`; core install and core tests require none of it.
- **Localhost-only** — binds `127.0.0.1`; not a network service.

This exception must be recorded in the pipeline's `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`
so it reads as an intended v0.2 addition, not scope drift.

## Sub-project A architecture

### A.1 Pipeline: `htdp serve`

New module `src/htdp/serve/` behind optional extra `serve` (adds `fastapi`, `uvicorn`).
New CLI command:

```
htdp serve [--host 127.0.0.1] [--port 8000] [--data-dir .]
```

Anchored to a `data-dir` (default cwd) the same way `process`/`package` are cwd-anchored.

#### Read endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/health` | `{ "ok": true, "version": "<htdp version>" }` |
| `GET` | `/status` | `PipelineStatus` (below) |
| `GET` | `/jobs` | `{ "jobs": [JobSummary, ...] }` — current + recent (bounded, newest first) |
| `GET` | `/jobs/{id}` | `Job` |

`PipelineStatus` (Pydantic model — source of truth for the contract):

```jsonc
{
  "data_dir": "/abs/path",
  "tiers": {
    "raw":       { "count": 12 },     // # session dirs in data/raw
    "processed": { "count":  8 },     // # session dirs in data/processed
    "releases":  { "count":  3 }      // # release dirs in data/releases
  },
  "demos":  { "count": 225 },          // episodes in demos/ (meta count), or null if absent
  "policy": { "present": true, "path": "policy.pt", "mtime_s": 1752000000.0 },
  "running_job": "job-abc123" | null   // convenience mirror of the active job id
}
```

Read endpoints touch the filesystem only (directory listing + a manifest/meta read). They
never mutate `data/`. Counts are cheap directory scans; no Parquet is loaded in A (that is
B/C work).

#### Job runner — the control primitive

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/jobs` | Body `{ "kind": "<allowlisted>", "args": {..} }` → `{ "job_id": "..." }`. Enqueues; starts immediately if idle, else `queued`. |
| `GET` | `/jobs/{id}` | Full `Job` record. |
| `POST` | `/jobs/{id}/cancel` | Requests cancellation (terminates the subprocess if running; drops it if queued). |
| `WS` | `/jobs/{id}/logs` | Streams `JobLogMessage`s: stdout lines + parsed progress, then a terminal `status` frame. Late subscribers get buffered backlog first. |

`Job` model:

```jsonc
{
  "id": "job-abc123",
  "kind": "gen-demos",
  "args": { "n_train": 200, "n_test": 25 },
  "status": "queued" | "running" | "done" | "failed" | "cancelled",
  "exit_code": 0 | null,
  "created_s": 1752000000.0,
  "started_s": 1752000001.0 | null,
  "ended_s":   1752000050.0 | null,
  "error": null | "short message"
}
```

`JobLogMessage` (WS frames):

```jsonc
{ "type": "log",      "line": "step 1200/5000  loss 0.031" }
{ "type": "progress", "current": 1200, "total": 5000 }        // when parseable
{ "type": "status",   "status": "done", "exit_code": 0 }      // terminal frame
```

**`JobManager`** (single instance, `providedIn`-equivalent module singleton):

- **In-memory registry** — `dict[job_id, Job]` + per-job log ring buffer. Ephemeral; lost on
  server restart (acceptable for local dev).
- **Max 1 running** — a single `asyncio` worker pulls from a FIFO queue. New `POST /jobs`
  while busy → `queued`. (Queue depth is unbounded but practically tiny; no priority.)
- **Subprocess spawn** — `asyncio.create_subprocess_exec("htdp", <subcmd>, *argv)`. **Never
  `shell=True`; never a shell string.** stdout/stderr read line-by-line, appended to the ring
  buffer, broadcast to WS subscribers, and scanned by a per-kind progress parser.
- **Cancellation** — `process.terminate()` (SIGTERM), then SIGKILL after a grace period;
  status → `cancelled`.

##### Security boundary (the reason this is safe to run)

The server executes **only** known `htdp` subcommands with **validated, typed args** — never
user-supplied shell or flags. Each `kind` maps to a fixed argv template with a typed args
model; anything not in the allowlist is rejected `400`.

`kind` allowlist for sub-project A:

| kind | htdp subcommand | args model (validated) |
|---|---|---|
| `synth` | `synth --out data/raw/<generated-id> --seed <int>` | `{ seed?: int }` |
| `gen-demos` | `gen-demos --out demos --n-train <int> --n-test <int>` | `{ n_train?: int(1..2000), n_test?: int(1..500) }` |
| `sim-task` | `sim-task [--video <path>]` | `{ video?: existing-path }` |
| `train-policy` | `train-policy --demos demos --out policy.pt --steps <int>` | `{ steps?: int(1..50000) }` |
| `eval-policy` | `eval-policy --demos demos --policy policy.pt` | `{}` |

Output paths are **server-controlled**, never taken from the request (prevents path
traversal / writing outside `data-dir`). Numeric args are range-clamped by Pydantic
validators. B/C/D extend the allowlist; the mechanism does not change.

Bind address defaults to `127.0.0.1`. CORS allows the dev origin `http://localhost:4200`.

### A.2 App: typed client + `/lab` shell

New feature area `src/app/modules/lab/` (mirrors the `modules/capture/` layout) plus a
cross-cutting client under `core/pipeline/`.

- **`environment.ts`** — add `pipelineApiUrl: 'http://localhost:8000'` and
  `pipelineSimWsUrl: 'ws://localhost:8000/sim'` (the latter unused until D).
- **`core/pipeline/pipeline-api.service.ts`** — `PipelineApiService` (`providedIn: 'root'`):
  typed `fetch` wrappers `getStatus()`, `listJobs()`, `getJob(id)`, `startJob(kind, args)`,
  `cancelJob(id)`, and `jobLogs(id)` returning an `Observable<JobLogMessage>` over a WS.
  TS interfaces (`PipelineStatus`, `Job`, `JobLogMessage`) **mirror the Pydantic models**;
  kept in sync by hand, contract pinned in this spec (§A.3).
- **`modules/lab/state/lab.state.ts`** — `LabState`. Signal-based service (matches the app's
  "prefer Signals for new component state" convention; NGXS only if it needs cross-feature
  actions, which A does not). Holds:
  - `status` signal — polled from `GET /status` (interval ~3s while `/lab` is active; stop on destroy).
  - `jobs` signal — from `GET /jobs`.
  - `activeJobLog` — lines/progress for the currently watched job via the log WS.
- **Routing** — add `/lab` **outside** the dashboard shell (sibling of `/capture` in
  `app.routes.ts`), lazy-loaded. Add a nav entry to `NavigationComponent`.
- **`LabShellComponent`** — the vertical slice:
  - **Status panel** — tier counts, demos count, policy present/mtime, connection state
    (reuses the app's plain-SVG/`input()` widget style, not d3).
  - **Jobs panel** — running job + queue, streamed log tail, progress bar, Cancel button.
  - **Run launcher** — pick a `kind` (A allowlist) + minimal args, `startJob`. Firing
    `gen-demos` and watching it stream to completion is the acceptance demo for A.

### A.3 Contract

The Pydantic models in `src/htdp/serve/models.py` are the **single source of truth**. The
app's TS interfaces mirror them. This spec pins the JSON shapes for `PipelineStatus`, `Job`,
`JobSummary`, and `JobLogMessage` (above) so sub-projects B/C/D extend rather than
renegotiate them. Any field change is a contract change — update both sides + this spec.

## Error handling

- **Server unreachable** — `PipelineApiService` surfaces a typed `offline` state; the shell
  shows "pipeline server not running — run `htdp serve`" rather than erroring. Status polling
  backs off and retries (mirrors `SimBridgeService`'s reconnect ethos).
- **Bad job request** — unknown `kind` or out-of-range args → `400` with a message rendered
  in the launcher.
- **Job failure** — non-zero exit → `status: failed`, `error` populated, terminal WS frame
  sent; the log tail remains visible for diagnosis.
- **Cancel race** — cancel on an already-finished job is a no-op `200`.
- **WS drop** — the log WS reconnect re-sends buffered backlog so a brief disconnect doesn't
  lose lines.

## Testing

**Pipeline (pytest):**
- `JobManager`: queueing (2nd job waits), single-concurrency invariant, successful run
  (fake fast subcommand), failure (non-zero exit → `failed`), cancel (running → `cancelled`).
- Argv builder: each allowlisted `kind` produces the expected argv; unknown `kind` rejected;
  out-of-range args rejected; **no request-supplied output paths reach argv**.
- Read endpoints via FastAPI `TestClient`: `/health`, `/status` against a temp `data-dir`
  with known tier contents.
- All `serve` tests gated behind `pytest.importorskip("fastapi")` so the core suite (which
  has no `serve` extra) still passes clean.

**App:** unit-test `PipelineApiService` mapping and `LabState` transitions with a mocked
fetch/WS. (Karma is currently broken repo-wide per CLAUDE.md; specs are written but treated
as write-only until that's fixed — verify compilation with `ng build --configuration
development` and `npx tsc --noEmit`.)

**Manual acceptance for A:** `htdp serve` up → open `/lab` → status panel shows real tier
counts → click Run `gen-demos` (small n) → logs stream, progress advances, job ends `done`,
status panel demo count increases.

## Out of scope for sub-project A

- Metrics charts and reading `docs/m2/*.json` / training curves (**B**).
- Catalog / QC / release browsing and Parquet loading (**C**).
- The Franka Panda `/sim` WS stream, Three.js Franka viewer, and teleop-save recording (**D**).
- Auth, multi-user, remote/hosted serving, job persistence across restarts.
- Any change to the pipeline's data tiers, schemas, or existing CLI commands.
