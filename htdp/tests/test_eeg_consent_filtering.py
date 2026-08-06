import json
from pathlib import Path

import pytest

from htdp.io.checksums import write_checksums
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402


def _ingest_eeg_session(tmp_path: Path, allow_eeg: bool) -> Path:
    raw = generate_session(tmp_path / "synthraw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Cz"], [0.0, 0.004], [[1.0, 2.0], [1.1, 2.1]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "ingest.json"
    sidecar.write_text(json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Cz"]))), encoding="utf-8")
    session = ingest_xdf(xdf, sidecar, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = json.loads(consent.read_text(encoding="utf-8"))
    data.update(
        {
            "distribute_raw_eeg": allow_eeg,
            "commercial_use": True,
            "model_training": True,
            "third_party_access": True,
            "public_release": True,
            "internal_only": False,
        }
    )
    consent.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(session)
    return tmp_path / "raw"


def test_allowed_eeg_survives_packaging(tmp_path: Path):
    raw = _ingest_eeg_session(tmp_path, allow_eeg=True)
    out = package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert (out / "data/real-0001/streams/eeg_eeg.csv").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "eeg" not in manifest["absent_modalities"]


def test_forbidden_eeg_dropped_at_packaging(tmp_path: Path):
    raw = _ingest_eeg_session(tmp_path, allow_eeg=False)
    out = package_release(
        ["real-0001"], "rel", ReleaseProfile.COMMERCIAL_DATASET, raw, tmp_path / "releases"
    )
    assert not (out / "data/real-0001/streams/eeg_eeg.csv").exists()
    assert (out / "data/real-0001/streams/motion_right_wrist.csv").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert "eeg" in manifest["absent_modalities"]
