# src/htdp/learn/eval.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from htdp.learn.rollout import load_policy, rollout_policy

# Dedicated eval seed, disjoint from the dataset splits (train=seed, test=seed+1000; all
# committed datasets use seed=0). Fresh eval positions must never echo either split.
EVAL_SEED = 2000


def eval_positions(
    demos_dir: Path, n_positions: int | None, *, eval_seed: int = EVAL_SEED
) -> list[tuple[float, float]]:
    """Positions to evaluate at: the dataset's legacy test split by default, or n freshly
    sampled in-region positions (seeded, reproducible) when n_positions is given."""
    if n_positions is None:
        raw = json.loads((Path(demos_dir) / "meta" / "test_positions.json").read_text())
        return [tuple(p) for p in raw]
    from htdp.learn.dataset import sample_cube_positions

    return [tuple(p) for p in sample_cube_positions(n_positions, eval_seed)]


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% interval for a binomial proportion (closed form, no scipy)."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * float(np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)))
    return (max(0.0, center - half), min(1.0, center + half))


def _report(succ: int, errs: list[float]) -> dict[str, float | int | list[float]]:
    n = len(errs)
    return {
        "success_rate": succ / n if n else 0.0,
        "mean_place_error": float(np.mean(errs)) if errs else 0.0,
        "n": n,
        "ci95": list(wilson_ci(succ, n)),
    }


def baseline_at(positions: list[tuple[float, float]]) -> dict[str, float | int]:
    # Baseline = the A2 physics friction-grasp teacher (the same executor the policy imitates),
    # so policy-vs-baseline is apples-to-apples under true physics.
    from htdp.replay.physics_episode import run_physics_episode

    errs: list[float] = []
    succ = 0
    for cube_xy in positions:
        r = run_physics_episode(cube_xy=tuple(cube_xy))
        errs.append(r.place_error)
        succ += int(r.lifted and r.place_error < 0.05)
    return _report(succ, errs)


def _policy_at(
    ckpt_path: Path, positions: list[tuple[float, float]]
) -> dict[str, float | int]:
    net, norm = load_policy(ckpt_path)
    errs: list[float] = []
    succ = 0
    for cube_xy in positions:
        r = rollout_policy(net, norm, cube_xy)
        errs.append(r.place_error)
        succ += int(r.success)
    return _report(succ, errs)


def _visuomotor_at(
    ckpt_path: Path,
    positions: list[tuple[float, float]],
    *,
    domain_randomize: bool = False,
    dr_seed_base: int = 5000,
) -> dict[str, float | int]:
    from htdp.learn.rollout import load_visuomotor_policy, rollout_visuomotor_policy

    net, norm = load_visuomotor_policy(ckpt_path)
    errs: list[float] = []
    succ = 0
    for i, cube_xy in enumerate(positions):
        r = rollout_visuomotor_policy(
            net, norm, cube_xy, domain_randomize=domain_randomize, dr_seed=dr_seed_base + i
        )
        errs.append(r.place_error)
        succ += int(r.success)
    return _report(succ, errs)


def evaluate(
    ckpt_path: Path,
    positions: list[tuple[float, float]],
    *,
    out_path: Path | None = None,
) -> dict[str, dict[str, float | int]]:
    report: dict[str, dict[str, float | int]] = {
        "policy": _policy_at(ckpt_path, positions),
        "baseline": baseline_at(positions),
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(report, indent=2))
    return report


def evaluate_visuomotor(
    ckpt_path: Path,
    positions: list[tuple[float, float]],
    *,
    out_path: Path | None = None,
    domain_randomize: bool = False,
    dr_seed_base: int = 5000,
) -> dict[str, dict[str, float | int]]:
    """Closed-loop visuomotor policy (pixels + proprio) vs the physics friction-grasp baseline.

    ``domain_randomize`` reports the C1 "novel DR seeds" robustness cell (docs/m2/
    c1-domain-randomization-scope.md): each position gets its own scene randomization
    (dr_seed_base + index), independent of any DR used at train time.
    """
    report: dict[str, dict[str, float | int]] = {
        "policy": _visuomotor_at(
            ckpt_path, positions, domain_randomize=domain_randomize, dr_seed_base=dr_seed_base
        ),
        "baseline": baseline_at(positions),
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(report, indent=2))
    return report
