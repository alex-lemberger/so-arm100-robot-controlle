# M2.5 C1 — Domain Randomization: result

Scope: [c1-domain-randomization-scope.md](c1-domain-randomization-scope.md). Depends on E1
(n≥30 + Wilson CI machinery).

## What shipped

- `randomize_scene(model, rng, cfg)` (`src/htdp/replay/domain_randomization.py`): perturbs light
  direction/intensity, headlight, table color (full hue), camera pose (±2 cm / ±2°), cube
  friction/mass. Cube hue jitter is mild (option A) — stays red, keeps the B2/B3 red-pixel gate
  valid.
- `generate_demos(..., domain_randomize=False)` — per-episode DR, seed = `seed + episode_index`.
  Default off.
- `rollout_visuomotor_policy(..., domain_randomize=False, dr_seed=0)` — one DR draw per rollout.
- `evaluate_visuomotor(..., domain_randomize=False, dr_seed_base=5000)` /
  `_visuomotor_at` — per-position seed = `dr_seed_base + index`, independent draws.
- CLI: `gen-demos --domain-randomize`, `eval-visuomotor --domain-randomize --dr-seed-base`.
- Gates: field-mutation unit tests, still-graspable-under-DR test, DR-off-by-default spy tests
  (dataset + rollout + eval), per-position-distinct-seed test, end-to-end CLI gate
  (`test_cli_domain_randomize_train_and_eval_end_to_end`: 40-demo DR train → eval under DR,
  asserts success > 0).

## Offline n=40 robustness run

Visuomotor policy trained **with** DR (n_train=100, seed=0, steps=6000), evaluated at n=40
(Wilson 95% CI):

| eval scene | success | CI | mean place error |
|---|---|---|---|
| canonical fixed scene | 39/40 (97.5%) | [87%, 100%] | 0.020 m |
| novel DR seeds (dr_seed_base=9000, disjoint from train-time seeds) | 40/40 (100%) | [91%, 100%] | 0.015 m |

Reports: `docs/m2/c1-eval-n40-canonical.json`, `docs/m2/c1-eval-n40-novel-dr.json`.

Both cells sit **above** the E1 no-DR visuomotor number (87.5% [74%, 95%]) and show no drop from
canonical to novel scenes — the extra visual variety at train time reads as a regularizer, not a
robustness cost. Did not run the "no-DR B3 policy on novel DR seeds" third cell (optional in the
scope doc, would need retaining and persisting the old non-DR checkpoint) — the two required
cells already answer the interview question the milestone targeted.

## Risks that held

- Red-pixel gate untouched (cube stays red under DR) — verified by
  `test_randomize_scene_changes_light_table_camera_and_cube_fields` (`r > g and r > b` assertion)
  and by the CLI gate's success-rate > 0 (a blind policy can't place).
- DR stayed default-off everywhere — the B1/B2/B3/E1 committed numbers and gates are untouched
  (verified by spy tests asserting `randomize_scene` uncalled when the flag is off).

**Then:** OOD generalization stress test (novel cube positions / distractors — C1 stayed
in-distribution positions), then portfolio packaging. Real SO-ARM100 mile is separately scoped in
[r1-real-arm-scope.md](r1-real-arm-scope.md).
