import json
import struct
from pathlib import Path

import pytest

from htdp.synth.generate import generate_session

pytest.importorskip("pyxdf")

from htdp.export.bids import export_motion_bids  # noqa: E402
from htdp.ingest.session import ingest_xdf  # noqa: E402
from tests._xdf_writer import build_sidecar, write_xdf  # noqa: E402

_STEM = "sub-p0001_task-reachgraspplace_acq-eeg"
_EEG_DIR = "sub-p0001/eeg"


def _ingest_eeg(tmp_path: Path) -> Path:
    raw = generate_session(tmp_path / "synthraw", seed=1)
    xdf = tmp_path / "s.xdf"
    eeg = ("eeg", ["Fp1", "Fp2", "Cz"], [0.0, 0.004], [[1.0, 2.0, 3.0], [1.5, 2.5, 3.5]])
    write_xdf(raw, xdf, eeg=eeg)
    sidecar = tmp_path / "i.json"
    sidecar.write_text(
        json.dumps(build_sidecar(raw, eeg=("eeg", ["Fp1", "Fp2", "Cz"]))), encoding="utf-8"
    )
    return ingest_xdf(xdf, sidecar, tmp_path / "raw" / "real-0001")


def test_eeg_files_written(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    for ext in ("_eeg.vhdr", "_eeg.vmrk", "_eeg.eeg", "_eeg.json", "_channels.tsv"):
        assert (out / _EEG_DIR / f"{_STEM}{ext}").exists(), ext


def test_vhdr_channel_count_and_interval(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    vhdr = (out / _EEG_DIR / f"{_STEM}_eeg.vhdr").read_text(encoding="utf-8")
    assert "NumberOfChannels=3" in vhdr
    assert "SamplingInterval=4000.0" in vhdr


def test_eeg_binary_unpacks_to_ingested_values(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    raw = (out / _EEG_DIR / f"{_STEM}_eeg.eeg").read_bytes()
    vals = list(struct.unpack("<" + "f" * (len(raw) // 4), raw))
    assert vals[:3] == pytest.approx([1.0, 2.0, 3.0])  # first sample (3 channels)
    assert vals[3:6] == pytest.approx([1.5, 2.5, 3.5])  # second sample


def test_channels_tsv_row_count(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    lines = (out / _EEG_DIR / f"{_STEM}_channels.tsv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "name\ttype\tunits"
    assert len(lines) - 1 == 3


def test_eeg_json_sampling_frequency(tmp_path: Path):
    out = export_motion_bids(_ingest_eeg(tmp_path), tmp_path / "bids")
    d = json.loads((out / _EEG_DIR / f"{_STEM}_eeg.json").read_text(encoding="utf-8"))
    assert d["SamplingFrequency"] > 0
    assert d["EEGChannelCount"] == 3


def test_motion_only_session_has_no_eeg_dir(tmp_path: Path):
    generate_session(tmp_path / "raw", seed=1)
    out = export_motion_bids(tmp_path / "raw" / "synth-0001", tmp_path / "bids")
    assert not (out / "sub-p0001" / "eeg").exists()
