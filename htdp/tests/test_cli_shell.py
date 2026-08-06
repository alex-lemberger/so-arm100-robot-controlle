from typer.testing import CliRunner
from htdp.cli import app

runner = CliRunner()


def test_cli_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("synth", "validate", "process", "qc", "package", "replay"):
        assert cmd in result.stdout


def test_ingest_unavailable_exits_1(tmp_path, monkeypatch):
    import sys

    from typer.testing import CliRunner

    from htdp.cli import app

    (tmp_path / "s.xdf").write_bytes(b"XDF:")
    sc = tmp_path / "ingest.json"
    sc.write_text(
        '{"session":{"session_id":"r","participant_id":"p","protocol_id":"reach-grasp-place",'
        '"consent_form_version":"v1","device_config_id":"d","start_time_s":0.0},'
        '"consent":{"consent_form_version":"v1"},"device_config":{"device_config_id":"d"},'
        '"ingest_map":{"w":{"role":"motion","tracker_id":"right_wrist","channels":'
        '{"x_m":0,"y_m":1,"z_m":2,"qw":3,"qx":4,"qy":5,"qz":6,"quality":7}},'
        '"m":{"role":"events"}}}',
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "pyxdf", None)  # force IngestUnavailable
    result = CliRunner().invoke(
        app, ["ingest", str(tmp_path / "s.xdf"), str(sc), "--out", str(tmp_path / "out")]
    )
    assert result.exit_code == 1
    assert "error:" in result.output


def test_ingest_roundtrip_cli(tmp_path):
    import json

    import pytest as _pytest

    _pytest.importorskip("pyxdf")
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session
    from tests._xdf_writer import build_sidecar, write_xdf

    raw = generate_session(tmp_path / "raw", seed=1)
    write_xdf(raw, tmp_path / "s.xdf")
    sc = tmp_path / "ingest.json"
    sc.write_text(json.dumps(build_sidecar(raw)), encoding="utf-8")
    out = tmp_path / "ingested"
    result = CliRunner().invoke(
        app, ["ingest", str(tmp_path / "s.xdf"), str(sc), "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "session.json").exists()


def test_ingest_video_happy_and_missing(tmp_path):
    import json

    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    session = tmp_path / "raw" / "synth-0001"
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x18ftyp")
    sidecar = tmp_path / "video.json"
    sidecar.write_text(json.dumps({"name": "frontal", "fps": 30.0}), encoding="utf-8")

    runner = CliRunner()
    ok = runner.invoke(app, ["ingest-video", str(session), str(mp4), str(sidecar)])
    assert ok.exit_code == 0, ok.output
    assert (session / "video" / "frontal.mp4").exists()

    bad = runner.invoke(
        app, ["ingest-video", str(session), str(tmp_path / "nope.mp4"), str(sidecar)]
    )
    assert bad.exit_code == 1
    assert "error:" in bad.output


def test_export_bids_happy_and_missing(tmp_path):
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    src = tmp_path / "raw" / "synth-0001"
    runner = CliRunner()
    ok = runner.invoke(app, ["export-bids", str(src), str(tmp_path / "bids")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bids" / "dataset_description.json").exists()

    bad = runner.invoke(app, ["export-bids", str(tmp_path / "nope"), str(tmp_path / "b2")])
    assert bad.exit_code == 1
    assert "error:" in bad.output


def test_export_release_bids_happy_and_missing(tmp_path):
    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.release.package import package_release
    from htdp.schemas.enums import ReleaseProfile
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    rel = package_release(
        ["synth-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )
    runner = CliRunner()
    ok = runner.invoke(app, ["export-release-bids", str(rel), str(tmp_path / "bids")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bids" / "dataset_description.json").exists()

    bad = runner.invoke(app, ["export-release-bids", str(tmp_path / "nope"), str(tmp_path / "b2")])
    assert bad.exit_code == 1
    assert "error:" in bad.output


def test_export_release_rosbag_happy_and_missing(tmp_path):
    import pytest

    pytest.importorskip("rosbags")

    from typer.testing import CliRunner

    from htdp.cli import app
    from htdp.release.package import package_release
    from htdp.schemas.enums import ReleaseProfile
    from htdp.synth.generate import generate_session

    generate_session(tmp_path / "raw", seed=1)
    rel = package_release(
        ["synth-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )
    runner = CliRunner()
    ok = runner.invoke(app, ["export-release-rosbag", str(rel), str(tmp_path / "bags")])
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "bags" / "synth0001" / "metadata.yaml").exists()

    bad = runner.invoke(
        app, ["export-release-rosbag", str(tmp_path / "nope"), str(tmp_path / "b2")]
    )
    assert bad.exit_code == 1
    assert "error:" in bad.output
