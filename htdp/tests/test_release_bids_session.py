from pathlib import Path

from htdp.export.bids import _write_session_bids
from htdp.synth.generate import generate_session


def test_ses_entity_in_path_and_filename(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = tmp_path / "bids"
    out.mkdir()
    row = _write_session_bids(out, tmp_path / "raw" / "synth-0001", ses="01")
    motion = out / "sub-p0001" / "ses-01" / "motion"
    assert (motion / "sub-p0001_ses-01_task-reachgraspplace_tracksys-vivesynth_motion.tsv").exists()
    assert (motion / "sub-p0001_ses-01_task-reachgraspplace_events.tsv").exists()
    assert row == {"participant_id": "sub-p0001", "cohort": "n/a"}


def test_no_ses_flat_layout(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = tmp_path / "bids"
    out.mkdir()
    _write_session_bids(out, tmp_path / "raw" / "synth-0001", ses=None)
    stem = "sub-p0001_task-reachgraspplace_tracksys-vivesynth"
    assert (out / "sub-p0001" / "motion" / f"{stem}_motion.tsv").exists()
    assert not (out / "sub-p0001" / "ses-01").exists()
