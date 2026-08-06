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
    meta_dir = tmp / "demos" / "meta"
    meta_dir.mkdir(parents=True)
    (meta_dir / "info.json").write_text("{}")
    (meta_dir / "stats.json").write_text("{}")
    (meta_dir / "test_positions.json").write_text("[]")
    episodes = "\n".join(f'{{"episode_index": {i}, "length": 10}}' for i in range(3))
    (meta_dir / "episodes.jsonl").write_text(episodes + "\n")


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
    assert body["demos"]["count"] == 3


def test_status_unseeded(tmp_path):
    client = TestClient(create_app(tmp_path))
    body = client.get("/status").json()
    assert body["tiers"]["raw"]["count"] == 0
    assert body["tiers"]["processed"]["count"] == 0
    assert body["tiers"]["releases"]["count"] == 0
    assert body["demos"] is None
    assert body["policy"]["present"] is False
    assert body["running_job"] is None


def test_jobs_empty(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/jobs").json() == {"jobs": []}


def test_get_missing_job_404(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/jobs/nope").status_code == 404
