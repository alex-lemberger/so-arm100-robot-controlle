from pathlib import Path
import json
from htdp.synth.generate import generate_session
from htdp.processing.extract import process_session
from htdp.qc.checks import run_qc


def _processed(tmp_path: Path) -> Path:
    raw = generate_session(tmp_path / "raw", seed=1)
    return process_session(raw, tmp_path / "processed")


def test_qc_detects_dropped_samples_as_warn(tmp_path: Path) -> None:
    report = run_qc(_processed(tmp_path))
    drop = next(c for c in report["checks"] if c["name"] == "dropped_samples")
    assert drop["severity"] == "warn"


def test_qc_detects_clock_drift_as_warn(tmp_path: Path) -> None:
    report = run_qc(_processed(tmp_path))
    drift = next(c for c in report["checks"] if c["name"] == "clock_drift")
    assert drift["severity"] == "warn"


def test_qc_overall_is_warn_not_fail(tmp_path: Path) -> None:
    report = run_qc(_processed(tmp_path))
    assert report["overall"] == "warn"


def test_qc_writes_json_and_html(tmp_path: Path) -> None:
    out = _processed(tmp_path)
    run_qc(out)
    assert (out / "qc_report.json").exists()
    assert (out / "qc_report.html").exists()
    data = json.loads((out / "qc_report.json").read_text(encoding="utf-8"))
    assert data["overall"] == "warn"
