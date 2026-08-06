import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from htdp.cli import app


def _run(runner: CliRunner, *args: str):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"htdp {' '.join(args)} failed:\n{result.output}"
    return result


def _build_core_release(runner: CliRunner) -> None:
    """synth 2 sessions, mixed video consent, ingest-video, package — in the current cwd.

    Order matters: edit consent BEFORE ingest-video (which re-checksums the folder), or
    validate would fail on a consent.json checksum mismatch.
    """
    _run(runner, "synth", "--out", "data/raw", "--seed", "1")
    _run(runner, "synth", "--out", "data/raw", "--seed", "2")
    Path("clip.mp4").write_bytes(b"\x00\x01\x02")
    Path("vid.json").write_text(json.dumps({"name": "cam0", "fps": 30.0}), encoding="utf-8")
    for sid, allow in [("synth-0001", True), ("synth-0002", False)]:
        cpath = Path(f"data/raw/{sid}/consent.json")
        c = json.loads(cpath.read_text(encoding="utf-8"))
        c["distribute_raw_video"] = allow
        cpath.write_text(json.dumps(c), encoding="utf-8")
        _run(runner, "ingest-video", f"data/raw/{sid}", "clip.mp4", "vid.json")
    _run(
        runner,
        "package",
        "synth-0001",
        "synth-0002",
        "--release",
        "rel",
        "--profile",
        "commercial_dataset",
    )


def test_full_pipeline_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)

    for sid in ["synth-0001", "synth-0002"]:
        _run(runner, "validate", f"data/raw/{sid}")
        _run(runner, "process", f"data/raw/{sid}")
        _run(runner, "qc", f"data/processed/{sid}")

    assert Path("data/releases/rel/data/synth-0001/video/cam0.mp4").exists()
    assert not Path("data/releases/rel/data/synth-0002/video/cam0.mp4").exists()
    man = json.loads(Path("data/releases/rel/manifest.json").read_text(encoding="utf-8"))
    assert man["absent_modalities_by_session"] == {
        "synth-0001": ["eeg"],
        "synth-0002": ["eeg", "video"],
    }
    assert man["absent_modalities"] == ["eeg"]

    _run(runner, "catalog", "data/raw", "sess.parquet")
    _run(runner, "catalog-releases", "data/releases", "rel.parquet")
    q = _run(runner, "catalog-query", "sess.parquet", "--modality", "video")
    assert sorted(q.output.split()) == ["synth-0001", "synth-0002"]

    _run(runner, "export-release-bids", "data/releases/rel", "bids_out")
    assert Path("bids_out/dataset_description.json").exists()
    subs = sorted(p.name for p in Path("bids_out").glob("sub-*"))
    assert subs == ["sub-p0001", "sub-p0002"]


def test_pipeline_replay_ik(tmp_path, monkeypatch):
    pytest.importorskip("mink")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)
    _run(runner, "replay-ik", "data/releases/rel", "--max-steps", "10", "--out", "traj.csv")
    assert Path("traj.csv").exists()
    assert Path("traj.csv").read_text(encoding="utf-8").splitlines()[0].startswith("timestamp_s")


def test_pipeline_rosbag(tmp_path, monkeypatch):
    pytest.importorskip("rosbags")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _build_core_release(runner)
    _run(runner, "export-release-rosbag", "data/releases/rel", "rosbag_out")
    bag_dirs = [p for p in Path("rosbag_out").iterdir() if p.is_dir()]
    assert bag_dirs


def test_pipeline_xdf_ingest(tmp_path, monkeypatch):
    pytest.importorskip("pyxdf")
    from tests._xdf_writer import build_sidecar, write_xdf

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _run(runner, "synth", "--out", "src", "--seed", "1")
    write_xdf(Path("src/synth-0001"), Path("s.xdf"))
    Path("ingest.json").write_text(
        json.dumps(build_sidecar(Path("src/synth-0001"))), encoding="utf-8"
    )
    _run(runner, "ingest", "s.xdf", "ingest.json", "--out", "data/raw/synth-0001")
    _run(runner, "validate", "data/raw/synth-0001")
    _run(runner, "process", "data/raw/synth-0001")
