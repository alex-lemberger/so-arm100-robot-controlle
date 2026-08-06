# M2.5 OOD1 — Out-of-Distribution Position Generalization (scoped milestone)

**Goal:** answer the caveat already in `docs/SIM_LOOP.md` ("held-out positions are
in-distribution interpolation") with a real number. Eval the frozen, no-DR visuomotor policy on
cube positions **outside** the trained region — no retraining trick, no DR (that's a different,
already-answered axis — C1). If the policy falls apart outside the training band, that's the
honest finding.

**Depends on E1** (n≥30 + Wilson CI machinery) and is orthogonal to C1 (scene-appearance DR):
this axis is cube *position*, not scene appearance. Reuses both directly — no eval-machinery
changes needed.

## Region

Trained region (`CUBE_REGION`, `src/htdp/learn/dataset.py`): x ∈ [0.48, 0.55], y ∈ [-0.20, -0.10].

OOD region: **same x-band** (the friction-grasp-feasible zone confirmed in A1/A2 — x < 0.48 is
known to fail the grasp entirely, so it's not a fair "OOD" point, it's an infeasible one), **new
y-band** immediately adjacent: y ∈ [-0.29, -0.20] — still on the table (table half-extent y =
±0.30) and within IK reach, but never sampled during training or the E1 eval.

## Build order (TDD, ~half session)

1. **Feasibility sweep DONE** (offline, mirrors A1's 3-point sanity check): swept the physics
   teacher across x ∈ {0.48, 0.515, 0.55} × y ∈ {-0.20 … -0.30}. The whole y=-0.30 edge column
   fails to lift (place_error ≈ 0.51, same failure mode as A1's x=0.46 column) — every point at
   y ≥ -0.29 lifts cleanly (place_error ≤ 0.011). **OOD region fixed at y ∈ [-0.29, -0.20]**, the
   `-0.30` edge excluded rather than over-tuned (A1 precedent).
2. `sample_ood_positions(n, seed)` in `src/htdp/learn/dataset.py` — same shape as
   `sample_cube_positions`, samples the OOD y-band instead of `CUBE_REGION`. Unit test: positions
   fall in the OOD band, are disjoint from `CUBE_REGION`, and are seed-reproducible.
3. **Offline run (not a test gate):** retrain a plain (no-DR) visuomotor policy with the E1
   recipe (40 demos, 6000 steps, seed=0 — same config that produced the 87.5% headline number),
   then:
   - eval on n=40 **in-distribution** fresh positions (repro of the E1 number, sanity check the
     retrain matches),
   - eval on n=40 **OOD** positions (the headline number for this milestone), via
     `evaluate_visuomotor` — no eval-code changes, just pass OOD positions in directly (bypasses
     `eval_positions()`'s two existing paths, which only know `CUBE_REGION`/`test_positions.json`).
   Save both reports under `docs/m2/ood1-eval-n40-*.json`.
4. Update `docs/SIM_LOOP.md`: replace the "in-distribution interpolation" limitation bullet with
   the actual number (whatever it is — expect a real drop; do not tune anything to chase 87.5%).
5. `docs/m2/ood1-generalization-state.md` result doc (mirrors C1's).

## Non-goals (explicitly out of scope for this milestone)

- Distractor objects, mid-episode perturbation — separate OOD axes, not this one.
- Retraining *on* OOD positions (that would just enlarge the training region, not measure
  generalization).
- CLI flags — this is an offline measurement, not a reusable pipeline feature; no new CLI needed
  beyond what `eval-visuomotor` (or a direct Python call, like E1's state-policy repro) already
  provides.

## Risks / watch-items

- **x-band cutoff still applies.** Don't drift x below 0.48 in the OOD band — that measures
  "physically infeasible," not "OOD," conflating two different findings (A1 lesson).
- **Numbers may be much lower.** A CNN trained on one y-band may not transfer at all (near-zero
  success) — this is the expected, honest outcome the milestone exists to surface, not a bug to
  chase.
- Visuomotor rollout is the slow eval path (CNN + render/step) — if 2×40 rollouts (in-dist +
  OOD) plus a 6000-step retrain runs long, drop to n=30 for the OOD cell and note it (same
  allowance E1 gave itself).

**Then:** portfolio packaging (README GIFs, narrated demo clip, CV bullet); real SO-ARM100 mile
separately scoped in `r1-real-arm-scope.md`.
