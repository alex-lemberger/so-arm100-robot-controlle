# M2.5 OOD1 — Out-of-Distribution Position Generalization: result

Scope: [ood1-generalization-scope.md](ood1-generalization-scope.md). Depends on E1 (n≥40 +
Wilson CI machinery); orthogonal to C1 (scene-appearance DR — this axis is cube *position*).

## What shipped

- Feasibility sweep confirmed the y=-0.30 edge column fails the friction grasp (same failure
  mode as A1's x=0.46 column) — `OOD_REGION` clamped to y ∈ [-0.29, -0.20], x-band unchanged.
- `sample_ood_positions(n, seed)` (`src/htdp/learn/dataset.py`) — same shape as
  `sample_cube_positions`, draws from `OOD_REGION` instead of `CUBE_REGION`. Unit test: seed-
  reproducible, positions inside the OOD band, disjoint from `CUBE_REGION` draws.
- No eval-machinery changes — `evaluate_visuomotor` already accepted an arbitrary position list;
  OOD positions were passed straight in.

## Offline n=40 result

Plain (no-DR) visuomotor policy, E1 recipe (40 demos, 6000 steps, seed=0):

| eval positions | success | 95% CI | mean place error |
|---|---|---|---|
| in-distribution (repro of E1) | 35/40 (87.5%) | [74%, 95%] | 0.050 m |
| **OOD** (y ∈ [-0.29,-0.20], never trained on) | **24/40 (60.0%)** | **[45%, 74%]** | 0.180 m |

Reports: `docs/m2/ood1-eval-n40-indist.json`, `docs/m2/ood1-eval-n40-ood.json`.

The in-distribution retrain reproduces E1's 87.5% [74,95] exactly, confirming the retrain is a
faithful repro (not a different policy). The physics teacher (baseline) stays 100% on **both**
position sets — the physics and IK generalize fine; the drop is entirely in the learned CNN
policy failing to localize/act correctly on cube positions it never saw. The two CIs barely
touch (74% vs 60%, upper/lower bound overlap at a single point) — a real, not noise-level, drop.

This is the answer to the caveat carried since M2.5 B3/E1: held-out numbers so far were
in-distribution interpolation. Outside the ~7×9 cm trained region, success roughly halves.

## Risks that held

- x-band cutoff respected — did not drift below x=0.48 (would have conflated "infeasible" with
  "OOD," the A1 lesson).
- Numbers were not tuned to chase a target — 60% is reported as measured.

**Then:** portfolio packaging (README GIFs, narrated demo clip, CV bullet); real SO-ARM100 mile
separately scoped in [r1-real-arm-scope.md](r1-real-arm-scope.md).
