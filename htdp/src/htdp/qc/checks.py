from __future__ import annotations

from pathlib import Path

import polars as pl

from htdp.qc.report import write_reports

_EXPECTED_TRACKERS = {"right_wrist", "left_wrist", "torso", "object"}
_RATE_HZ = 100.0


def _worst(severities: list[str]) -> str:
    for level in ("fail", "warn", "pass"):
        if level in severities:
            return level
    return "pass"


def run_qc(processed_dir: Path) -> dict[str, object]:
    motion = pl.read_parquet(processed_dir / "motion.parquet")
    events = pl.read_parquet(processed_dir / "events.parquet")
    checks: list[dict[str, str]] = []

    present = set(motion["tracker_id"].unique().to_list())
    missing = _EXPECTED_TRACKERS - present
    checks.append(
        {
            "name": "trackers_present",
            "severity": "fail" if missing else "pass",
            "detail": f"missing={sorted(missing)}" if missing else "all trackers present",
        }
    )

    mono_ok = True
    for tracker in present:
        ts = motion.filter(pl.col("tracker_id") == tracker)["timestamp_s"].to_list()
        if any(b <= a for a, b in zip(ts, ts[1:])):
            mono_ok = False
    checks.append(
        {
            "name": "monotonic_timestamps",
            "severity": "pass" if mono_ok else "fail",
            "detail": "ok" if mono_ok else "non-monotonic timestamps found",
        }
    )

    gap_found = False
    for tracker in present:
        ts = motion.filter(pl.col("tracker_id") == tracker)["timestamp_s"].to_list()
        diffs = [b - a for a, b in zip(ts, ts[1:])]
        if any(d > 1.5 / _RATE_HZ for d in diffs):
            gap_found = True
    checks.append(
        {
            "name": "dropped_samples",
            "severity": "warn" if gap_found else "pass",
            "detail": "gap detected" if gap_found else "no gaps",
        }
    )

    _DRIFT_THRESHOLD_S = 0.02
    final_ts: dict[str, float] = {
        tracker: float(motion.filter(pl.col("tracker_id") == tracker)["timestamp_s"].max())  # type: ignore[arg-type]
        for tracker in present
    }
    final_ts_values = list(final_ts.values())
    sorted_values = sorted(final_ts_values)
    mid = len(sorted_values) // 2
    reference = (
        (sorted_values[mid - 1] + sorted_values[mid]) / 2.0
        if len(sorted_values) % 2 == 0
        else sorted_values[mid]
    )
    drifting = {
        t: final_ts[t] - reference
        for t in present
        if abs(final_ts[t] - reference) > _DRIFT_THRESHOLD_S
    }
    if drifting:
        detail = "; ".join(f"{t} offset={offset:+.4f}s" for t, offset in sorted(drifting.items()))
        drift_severity = "warn"
    else:
        detail = "no cross-stream drift detected"
        drift_severity = "pass"
    checks.append(
        {
            "name": "clock_drift",
            "severity": drift_severity,
            "detail": detail,
        }
    )

    labels = events["label"].to_list()
    order_ok = labels == ["start", "grasp", "release", "place", "stop"]
    checks.append(
        {
            "name": "event_order",
            "severity": "pass" if order_ok else "fail",
            "detail": "ok" if order_ok else f"unexpected order: {labels}",
        }
    )

    report: dict[str, object] = {
        "overall": _worst([c["severity"] for c in checks]),
        "checks": checks,
    }
    write_reports(report, processed_dir)
    return report
