"""FastAPI app factory for `htdp serve`: the HTTP/WS surface for the local pipeline.
Read endpoints (health/status/jobs) touch the filesystem only for counts and never
mutate `data/`. Job-control endpoints (POST /jobs, cancel, WS logs) spawn allowlisted
`htdp` subcommands via `JobManager`, which do write to `data/` (synth/gen-demos/train/
eval) or terminate a running subprocess (cancel)."""

from __future__ import annotations

from importlib.metadata import version as _pkg_version
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from htdp.serve.jobs import JobKindError, JobManager
from htdp.serve.models import StartJobRequest
from htdp.serve.status import read_status


def create_app(data_dir: Path, manager: JobManager | None = None) -> FastAPI:
    app = FastAPI(title="htdp serve", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.data_dir = data_dir
    app.state.manager = manager or JobManager(data_dir)

    @app.get("/health")
    def health() -> dict[str, object]:
        try:
            v = _pkg_version("htdp")
        except Exception:  # noqa: BLE001
            v = "unknown"
        return {"ok": True, "version": v}

    @app.get("/status")
    def status() -> dict[str, object]:
        return read_status(app.state.data_dir, app.state.manager).model_dump()

    @app.get("/jobs")
    def jobs() -> dict[str, object]:
        return {"jobs": [j.model_dump() for j in app.state.manager.list_jobs()]}

    @app.get("/jobs/{job_id}")
    def job(job_id: str) -> dict[str, object]:
        got = app.state.manager.get(job_id)
        if got is None:
            raise HTTPException(status_code=404, detail="job not found")
        dumped: dict[str, object] = got.model_dump()
        return dumped

    @app.post("/jobs")
    async def start_job(req: StartJobRequest) -> dict[str, object]:
        try:
            job = await app.state.manager.submit(req.kind, req.args)
        except JobKindError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job_id": job.id}

    @app.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, object]:
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

    return app
