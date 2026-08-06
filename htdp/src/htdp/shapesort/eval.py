from __future__ import annotations

from dataclasses import dataclass

from htdp.learn.eval import wilson_ci


@dataclass(frozen=True)
class TrialLog:
    outcome: str
    used_fallback: bool


def aggregate(trials: list[TrialLog]) -> dict[str, object]:
    """Aggregate trial logs into the report shape used by R1c/E1/C1/OOD1: success rate +
    Wilson 95% CI, per-outcome failure taxonomy, and the SmolVLA-fallback trigger rate.
    """
    n = len(trials)
    successes = sum(1 for t in trials if t.outcome == "success")
    lo, hi = wilson_ci(successes, n)

    taxonomy: dict[str, int] = {}
    for t in trials:
        taxonomy[t.outcome] = taxonomy.get(t.outcome, 0) + 1

    fallback_n = sum(1 for t in trials if t.used_fallback)

    return {
        "n": n,
        "success_rate": successes / n if n else 0.0,
        "ci95": [lo, hi],
        "failure_taxonomy": taxonomy,
        "fallback_trigger_rate": fallback_n / n if n else 0.0,
    }
