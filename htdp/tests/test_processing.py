from pathlib import Path

import polars as pl
import pytest

from htdp.io.checksums import verify_checksums, write_checksums
from htdp.processing.extract import process_session
from htdp.synth.generate import generate_session


def test_process_writes_parquet_and_manifest(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    out = process_session(raw, tmp_path / "processed")
    assert (out / "motion.parquet").exists()
    assert (out / "events.parquet").exists()
    assert (out / "manifest.json").exists()
    df = pl.read_parquet(out / "motion.parquet")
    assert set(df["tracker_id"].unique()) == {"right_wrist", "left_wrist", "torso", "object"}


def test_process_does_not_modify_raw(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    write_checksums(raw)
    process_session(raw, tmp_path / "processed")
    assert verify_checksums(raw) == []


def test_process_rejects_invalid_raw(tmp_path: Path):
    raw = generate_session(tmp_path / "raw", seed=1)
    (raw / "streams/events.csv").write_text("corrupt\n", encoding="utf-8")
    with pytest.raises(ValueError):
        process_session(raw, tmp_path / "processed")
