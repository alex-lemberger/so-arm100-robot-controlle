import json
from pathlib import Path

import pytest

from htdp.export.bids import BidsExportError, export_release_bids
from htdp.io.checksums import write_checksums
from htdp.release.package import package_release
from htdp.schemas.enums import ReleaseProfile
from htdp.synth.generate import generate_session


def _release(tmp_path: Path) -> Path:
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    return package_release(
        ["synth-0001", "synth-0002"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )


def test_two_subjects_and_aggregated_participants(tmp_path: Path):
    out = export_release_bids(_release(tmp_path), tmp_path / "bids")
    assert (out / "sub-p0001" / "motion").exists()
    assert (out / "sub-p0002" / "motion").exists()
    parts = (out / "participants.tsv").read_text(encoding="utf-8").splitlines()
    assert parts[0] == "participant_id\tcohort"
    assert len(parts) == 3  # header + 2 subjects
    desc = json.loads((out / "dataset_description.json").read_text(encoding="utf-8"))
    assert desc["Name"] == "rel"


def test_participant_collision_adds_ses(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    generate_session(tmp_path / "raw", seed=2)
    sp = tmp_path / "raw" / "synth-0002" / "session.json"
    data = json.loads(sp.read_text(encoding="utf-8"))
    data["participant_id"] = "p-0001"  # force collision
    sp.write_text(json.dumps(data), encoding="utf-8")
    write_checksums(tmp_path / "raw" / "synth-0002")
    rel = package_release(
        ["synth-0001", "synth-0002"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )
    out = export_release_bids(rel, tmp_path / "bids")
    assert (out / "sub-p0001" / "ses-synth0001" / "motion").exists()
    assert (out / "sub-p0001" / "ses-synth0002" / "motion").exists()
    parts = (out / "participants.tsv").read_text(encoding="utf-8").splitlines()
    assert len(parts) == 2  # header + 1 deduped subject


def test_missing_data_dir_raises(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(BidsExportError):
        export_release_bids(tmp_path / "empty", tmp_path / "bids")


def test_force_overwrite(tmp_path: Path):
    rel = _release(tmp_path)
    export_release_bids(rel, tmp_path / "bids")
    with pytest.raises(BidsExportError):
        export_release_bids(rel, tmp_path / "bids")
    export_release_bids(rel, tmp_path / "bids", force=True)  # ok


def test_forbidden_eeg_absent_from_release_bids(tmp_path: Path):
    pytest.importorskip("pyxdf")
    import json as _json

    from htdp.ingest.session import ingest_xdf
    from tests._xdf_writer import build_sidecar, write_xdf

    src = generate_session(tmp_path / "sr", seed=1)
    eeg = ("eeg", ["Fp1", "Cz"], [0.0, 0.004], [[1.0, 2.0], [1.5, 2.5]])
    write_xdf(src, tmp_path / "x.xdf", eeg=eeg)
    sc = tmp_path / "i.json"
    sc.write_text(_json.dumps(build_sidecar(src, eeg=("eeg", ["Fp1", "Cz"]))), encoding="utf-8")
    session = ingest_xdf(tmp_path / "x.xdf", sc, tmp_path / "raw" / "real-0001")
    consent = session / "consent.json"
    data = _json.loads(consent.read_text(encoding="utf-8"))
    data.update(
        {
            "distribute_raw_eeg": False,
            "commercial_use": True,
            "model_training": True,
            "third_party_access": True,
            "public_release": True,
            "internal_only": False,
        }
    )
    consent.write_text(_json.dumps(data), encoding="utf-8")
    write_checksums(session)
    rel = package_release(
        ["real-0001"],
        "rel",
        ReleaseProfile.COMMERCIAL_DATASET,
        tmp_path / "raw",
        tmp_path / "releases",
    )
    out = export_release_bids(rel, tmp_path / "bids")
    assert (out / "sub-p0001" / "motion").exists()
    assert not (out / "sub-p0001" / "eeg").exists()  # eeg dropped during packaging
