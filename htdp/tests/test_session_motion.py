import pytest

from htdp.ingest.frame import IDENTITY
from htdp.ingest.session import build_motion_rows, compute_t0


def _raw():
    return {
        "right_wrist": [
            {
                "raw_ts": 1000.0,
                "tracker_id": "right_wrist",
                "x_m": 1.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "quality": 1.0,
            },
            {
                "raw_ts": 1000.01,
                "tracker_id": "right_wrist",
                "x_m": 1.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "quality": 0.5,
            },
        ],
        "object": [
            {
                "raw_ts": 1000.05,
                "tracker_id": "object",
                "x_m": 0.0,
                "y_m": 0.0,
                "z_m": 0.0,
                "qw": 1.0,
                "qx": 0.0,
                "qy": 0.0,
                "qz": 0.0,
                "quality": 1.0,
            },
        ],
    }


def test_compute_t0_is_global_min():
    assert compute_t0(_raw()) == 1000.0


def test_compute_t0_empty_raises():
    with pytest.raises(ValueError):
        compute_t0({})


def test_build_motion_rows_rebases_and_tags():
    out = build_motion_rows(_raw(), IDENTITY, 1000.0)
    rw = out["right_wrist"]
    assert rw[0]["timestamp_s"] == pytest.approx(0.0, abs=1e-9)
    assert rw[1]["timestamp_s"] == pytest.approx(0.01, abs=1e-9)
    assert rw[0]["defect_tag"] == ""
    assert rw[1]["quality"] == 0.5
    assert out["object"][0]["timestamp_s"] == pytest.approx(0.05, abs=1e-9)


def test_build_motion_rows_applies_rotation():
    rot = (0.7071067811865476, 0.0, 0.0, 0.7071067811865476)  # 90° about z
    out = build_motion_rows(_raw(), rot, 1000.0)
    row = out["right_wrist"][0]
    assert row["x_m"] == pytest.approx(0.0, abs=1e-9)
    assert row["y_m"] == pytest.approx(1.0, abs=1e-9)
