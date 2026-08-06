import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from htdp.serve.app import create_app
from htdp.serve.jobs import JobManager


def _fake_mgr(tmp: Path):
    return JobManager(tmp, htdp_cmd=[sys.executable, "-c", "print('go'); print('1/1')", "--"])


def test_start_unknown_kind_400(tmp_path):
    client = TestClient(create_app(tmp_path, _fake_mgr(tmp_path)))
    r = client.post("/jobs", json={"kind": "rm-rf", "args": {}})
    assert r.status_code == 400


def test_start_and_stream_logs(tmp_path):
    # Use TestClient as a context manager: Starlette otherwise spins up a fresh
    # event-loop "portal" per call (when not entered), which tears down as soon
    # as the POST /jobs response is sent -- orphaning the JobManager's
    # asyncio.create_task(_execute(...)) background task before the subprocess
    # can finish, and deadlocking the subsequent WS subscribe() forever. A
    # single persistent portal across the POST and the WS call keeps that task
    # alive on the same loop.
    with TestClient(create_app(tmp_path, _fake_mgr(tmp_path))) as client:
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
