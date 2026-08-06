import json
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session
from htdp.validate import validate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import CLOCK_BASE, build_sidecar, write_xdf  # noqa: E402

_MOTION = ("right_wrist", "left_wrist", "torso", "object")


def _strip_defect(csv_text: str) -> list[tuple[str, ...]]:
    lines = csv_text.splitlines()
    header = lines[0].split(",")
    keep = [i for i, c in enumerate(header) if c != "defect_tag"]
    return [tuple(line.split(",")[i] for i in keep) for line in lines]


def _run(tmp_path: Path) -> tuple[Path, Path]:
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    write_xdf(raw, xdf)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(json.dumps(build_sidecar(raw)), encoding="utf-8")
    return raw, ingest_xdf(xdf, sidecar, tmp_path / "ingested")


def test_ingested_session_validates(tmp_path: Path):
    _raw, out = _run(tmp_path)
    assert validate_session(out) == []


def test_geometry_matches_ignoring_defect_tag(tmp_path: Path):
    raw, out = _run(tmp_path)
    for t in _MOTION:
        orig = _strip_defect((raw / "streams" / f"motion_{t}.csv").read_text(encoding="utf-8"))
        got = _strip_defect((out / "streams" / f"motion_{t}.csv").read_text(encoding="utf-8"))
        assert got == orig, t


def test_start_time_records_absolute_t0(tmp_path: Path):
    _raw, out = _run(tmp_path)
    session = json.loads((out / "session.json").read_text(encoding="utf-8"))
    assert session["start_time_s"] == pytest.approx(CLOCK_BASE, abs=1e-6)


def test_events_source_is_real(tmp_path: Path):
    _raw, out = _run(tmp_path)
    events = (out / "streams" / "events.csv").read_text(encoding="utf-8")
    assert "real" in events and "synthetic" not in events
