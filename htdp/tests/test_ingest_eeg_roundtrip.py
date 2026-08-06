import json
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session
from htdp.validate import validate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def _run(tmp_path: Path) -> Path:
    raw = generate_session(tmp_path / "raw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.1, 2.1, 3.1]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(
        json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))), encoding="utf-8"
    )
    return ingest_xdf(xdf, sidecar, tmp_path / "ingested")


def test_eeg_csv_written_with_columns_and_values(tmp_path: Path):
    out = _run(tmp_path)
    eeg_csv = out / "streams" / "eeg_eeg.csv"
    lines = eeg_csv.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp_s,Fp1,Fp2,Cz"
    # t0 = earliest motion sample = CLOCK_BASE, so eeg ts rebases to its raw offset
    first = lines[1].split(",")
    assert first[0] == "0.000000"
    assert first[1] == "1.000000" and first[3] == "3.000000"


def test_eeg_session_validates(tmp_path: Path):
    assert validate_session(_run(tmp_path)) == []
