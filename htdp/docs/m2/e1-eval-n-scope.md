# M2.5 E1 — Eval Statistical Power (scoped milestone)

**Goal:** replace the n=6 held-out anecdote with n≥30 evaluations and a 95% confidence interval,
for both the state-based (A3) and visuomotor (B3) policies. No training changes, no new physics —
this is measurement hygiene. "67% (4/6)" becomes "X% [CI lo–hi], n=40", which is the difference
between an anecdote and a number a reviewer can trust.

**Order: E1 before C1.** C1's robustness table should be reported with this machinery (a DR
robustness claim on n=6 has the same anecdote problem).

## Design

### Position sampling (no new dataset)

Reuse `sample_cube_positions(n, seed)` (`src/htdp/learn/dataset.py`) with a dedicated eval seed
offset, disjoint from train (`seed`) and the legacy test split (`seed + 1000`):

- `EVAL_SEED_OFFSET = 2000` — eval positions = `sample_cube_positions(n, seed + 2000)`.
- Same `CUBE_REGION` — E1 stays an **in-distribution** measurement by design; OOD is a later
  milestone. State this in the report.

### Confidence interval

`wilson_ci(successes, n, z=1.96)` in `src/htdp/learn/eval.py` — closed-form Wilson score interval,
no scipy dependency. Unit-test against known values (e.g. 4/6 → ~[0.30, 0.90]; 27/40 → ~[0.52, 0.80]).

### Report shape

`_policy_at` / `_visuomotor_at` / `baseline_at` blocks gain `ci95: [lo, hi]` alongside the existing
`success_rate` / `mean_place_error` / `n`. Old keys unchanged (B1–B3 gates keep passing).

### CLI

`eval-policy` and `eval-visuomotor` gain `--n-positions N --eval-seed-offset 2000` (both optional).
When given, positions are freshly sampled as above instead of read from
`meta/test_positions.json`. **Default behavior unchanged** — no flags = legacy test_positions.json
path, so committed numbers stay reproducible.

## Build order (TDD, ~half session)

1. `wilson_ci` + unit tests (known values, edge cases 0/n and n/n).
2. Wire `ci95` into the three report blocks; existing eval tests updated to assert key presence.
3. CLI flags on both eval commands + test (monkeypatch small n; assert sampled positions differ
   from test_positions.json and are inside `CUBE_REGION`).
4. **Offline run (not a test gate):** `eval-policy` and `eval-visuomotor` at `--n-positions 40`.
   ~40 physics rollouts per policy + 40 teacher episodes — minutes of wall-time, too slow for the
   suite. Save reports to `docs/m2/e1-eval-n40-*.json`.
5. Update `docs/SIM_LOOP.md`: headline table gets n=40 numbers with CI; honest-limitations bullet
   rewritten ("n=6" → "n=40, in-distribution; CI reported").

## Gates

- Unit: `wilson_ci` correct on known values.
- Integration: eval report contains `ci95`, CLI sampling path produces n fresh in-region positions.
- Milestone done = SIM_LOOP.md shows n=40 ± CI for policy, visuomotor, and teacher baseline.

## Risks / watch-items

- **Numbers may move.** 4/6 could become anything in [40%, 80%] at n=40. That is the point —
  whatever it is, report it. Do not tune anything in E1 to chase the old 67%.
- Teacher baseline at n=40 also gets a CI — if teacher < 100%, that's a finding, not a bug to hide.
- Visuomotor rollout is the slow path (CNN + render per step). If 40 episodes exceed ~15 min,
  drop to n=30 — still fine; note it.
- `sample_cube_positions(seed+2000)` collision with train positions is measure-zero (continuous
  region) — no dedup needed; assert seeds differ, not positions.

**Then:** C1 domain randomization (docs/m2/c1-domain-randomization-scope.md), reporting its
robustness table with this same n≥30 + CI machinery.
