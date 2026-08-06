from __future__ import annotations

from htdp.learn.eval import wilson_ci
from htdp.shapesort.eval import TrialLog, aggregate


def test_aggregate_empty_list() -> None:
    report = aggregate([])
    assert report["n"] == 0
    assert report["success_rate"] == 0.0
    assert report["ci95"] == [0.0, 1.0]
    assert report["failure_taxonomy"] == {}
    assert report["fallback_trigger_rate"] == 0.0


def test_aggregate_mixed_outcomes() -> None:
    trials = [
        TrialLog(outcome="success", used_fallback=False),
        TrialLog(outcome="success", used_fallback=True),
        TrialLog(outcome="success", used_fallback=False),
        TrialLog(outcome="asr_miss", used_fallback=False),
        TrialLog(outcome="insert_fail", used_fallback=True),
    ]
    report = aggregate(trials)
    assert report["n"] == 5
    assert report["success_rate"] == 3 / 5
    assert report["failure_taxonomy"] == {"success": 3, "asr_miss": 1, "insert_fail": 1}
    assert report["fallback_trigger_rate"] == 2 / 5
    assert report["ci95"] == list(wilson_ci(3, 5))
