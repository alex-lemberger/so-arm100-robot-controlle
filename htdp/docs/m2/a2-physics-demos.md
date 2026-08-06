# M2.5 A2 — Physics-Teacher Demo Regeneration (result)

**Done:** `generate_demos` now records from the **physics friction-grasp teacher**
(`run_physics_episode`) instead of the M1/M2 kinematic teacher. Each demo row is one
settled IK-target pose; the friction grasp actuates the gripper, so the **finger-width
feature returns to the observation** (reverses the M2 constant-feature drop).

## Success zone (region restriction)

Swept the physics teacher across the old `CUBE_REGION` grid:

| x \ y | -0.20 | -0.18 | -0.16 | -0.14 | -0.12 | -0.10 |
|-------|-------|-------|-------|-------|-------|-------|
| 0.46  | fail (0.37) | fail | fail | fail | fail | fail (0.26) |
| 0.48  | OK | OK | OK | OK | OK | OK |
| 0.50  | OK | OK | OK | OK | OK | OK |
| 0.52  | OK | OK | OK | OK | OK | OK |
| 0.54  | OK | OK | OK | OK | OK | OK |

The whole `x=0.46` column fails the friction grasp; everything `x>=0.48` lifts and
places. `CUBE_REGION` x_lo raised `0.45 -> 0.48`. The failing column is excluded, not
over-tuned.

## Observation / action

- `OBS_DIM` 16 -> **17**. `finger_width = qpos[7] + qpos[8]` (0..0.08) appended LAST
  so the legacy 0:16 layout (joints, eef, cube, target) is unchanged. Measured std in a
  generated dataset ≈ 0.014 (> 0 — carries grasp state, no normalization landmine).
- Action repr unchanged (7 joint targets + gripper 1=close/0=open from the waypoint flag).

## Plumbing

- `run_physics_episode(..., on_sample=cb)` — `cb(model, data, closed)` fires **once per IK
  target at its settled state**, NOT per `mj_step`, so the 200-step grasp dwell collapses to
  one row instead of over-representing a single pose.

## Gates

`tests/learn/test_dataset.py` (region 0.48, obs dim 17, finger-width std > 0.01),
`tests/learn/test_obs.py` (finger-width feature), `tests/replay/test_physics_episode.py`
(on_sample cadence). Full `tests/learn tests/replay` = 24 passed, 1 skipped.

## Known A2/A3 seam (the 1 skip)

`test_policy_beats_zero_on_held_out` is **skipped**: demos are now physics (varying finger
width) but `rollout_policy` / `eval` are still **kinematic** (fingers held open) — the M2
teacher/executor mismatch in reverse. **A3** converts the rollout to the physics friction
grasp and re-enables this regression guard.

**Next (A3):** retrain the ACT policy on these physics demos AND switch `rollout_policy` to
the physics friction grasp so teacher and executor match; un-skip the end-to-end guard.
