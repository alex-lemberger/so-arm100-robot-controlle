from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.reader import load_xdf_streams  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def test_eeg_stream_round_trips_through_reader(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]])
    write_xdf(raw, xdf, eeg=eeg)
    streams = load_xdf_streams(xdf)
    assert "eeg" in streams
    assert streams["eeg"].channel_format == "double64"
    assert len(streams["eeg"].time_series[0]) == 3


def test_build_sidecar_adds_eeg_entry(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    sidecar = build_sidecar(raw, eeg=("eeg", ["Fp1", "Cz"]))
    entry = sidecar["ingest_map"]["eeg"]
    assert entry == {"role": "eeg", "eeg_id": "eeg", "channels": {"Fp1": 0, "Cz": 1}}
