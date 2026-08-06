from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.reader import load_xdf_streams  # noqa: E402
from tests._xdf_writer import CLOCK_BASE, build_sidecar, write_xdf  # noqa: E402


def test_written_xdf_loads_with_expected_streams(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "session.xdf"
    write_xdf(raw, xdf)
    streams = load_xdf_streams(xdf)
    assert {"right_wrist", "left_wrist", "torso", "object", "events"} <= set(streams)
    assert streams["right_wrist"].channel_format == "double64"
    assert streams["events"].channel_format == "string"
    assert streams["right_wrist"].time_stamps[0] == pytest.approx(CLOCK_BASE, abs=1e-6)


def test_sidecar_maps_every_tracker_and_events(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    roles = {n: e["role"] for n, e in build_sidecar(raw)["ingest_map"].items()}
    assert roles == {
        "right_wrist": "motion",
        "left_wrist": "motion",
        "torso": "motion",
        "object": "motion",
        "events": "events",
    }
