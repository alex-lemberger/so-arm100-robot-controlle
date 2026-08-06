import pytest

from htdp.ingest.session import build_eeg_rows


def _raw():
    return {
        "eeg": (
            ["Fp1", "Cz"],
            [
                {"raw_ts": 1000.0, "Fp1": 1.0, "Cz": 2.0},
                {"raw_ts": 1000.01, "Fp1": 1.1, "Cz": 2.1},
            ],
        )
    }


def test_build_eeg_rows_rebases_and_keeps_labels():
    out = build_eeg_rows(_raw(), 1000.0)
    labels, rows = out["eeg"]
    assert labels == ["Fp1", "Cz"]
    assert rows[0]["timestamp_s"] == pytest.approx(0.0, abs=1e-9)
    assert rows[1]["timestamp_s"] == pytest.approx(0.01, abs=1e-9)
    assert rows[0]["Fp1"] == 1.0 and rows[1]["Cz"] == 2.1


def test_build_eeg_rows_allows_negative_timestamps():
    raw = {"eeg": (["Fp1"], [{"raw_ts": 999.5, "Fp1": 0.0}])}
    _labels, rows = build_eeg_rows(raw, 1000.0)["eeg"]
    assert rows[0]["timestamp_s"] == pytest.approx(-0.5)
