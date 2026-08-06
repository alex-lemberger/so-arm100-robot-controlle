# M2.5 B3 — Visuomotor ACT (result)

**Done:** A closed-loop policy that drives the true-physics friction grasp from the **front
camera image + proprioception only** — the privileged cube and target coordinates are removed
from the observation. The CNN must localise the cube and goal from pixels. This closes the
visuomotor track: pixels → action, end-to-end under contact physics.

## Result

| policy | observation | held-out success | mean place_error |
|--------|-------------|------------------|------------------|
| state ACT (A3) | joints+eef+**cube xyz+target xyz**+finger width (17) | 4/6 (67%) | 0.097 m |
| **visuomotor ACT (B3)** | front image (96×96) + **proprio only** (11) | **4/6 (67%)** | — |
| baseline (physics teacher) | — | 6/6 (100%) | 0.008 m |

(40 train / 6 held-out demos, 6000 steps, seed 0. Per-position: 4 clean places
`place_error` 0.006–0.019 m; 2 misses where the cube is not localised/lifted.)

The visuomotor policy **matches the state-based policy's 67%** while seeing none of the
privileged coordinates — it reads the cube and target from the image. That is the headline: the
arm picks and places under physics from pixels, not from handed-in object poses.

## How

- **Observation split** (`obs.py`): `PROPRIO_INDICES = [0..9, 16]` slices the proprioceptive
  subset (joints, eef xyz, finger width) out of the existing 17-dim state; cube xyz (10:13) and
  target xyz (13:16) are dropped. No demo regeneration — proprio is a slice of what B2 already
  stored, so there is one source of truth (`proprio_from_state` slices, `build_proprio_observation`
  builds; a test asserts they agree).
- **Policy** (`policy.py` `VisuomotorACTPolicy`): a small 3-stride CNN (96→48→24→12, global pool)
  → image feature, fused with proprio into one memory token, then the same learned-query
  transformer decoder + action head as the state ACT.
- **Training** (`train.py` `train_visuomotor`): loads the B2 image sidecar, normalises proprio
  (z-score, stats sliced from the full obs stats) and images (`/255`), with proprio noise +
  brightness jitter augmentation against covariate shift.
- **Rollout** (`rollout.py` `rollout_visuomotor_policy`): the same true-physics actuator /
  friction-grasp loop as A3, but each step renders the `front` frame through the **same
  `render_camera` path the demos used** (no train/rollout framing drift) and feeds image + proprio
  to the policy.
- CLI: `train-visuomotor`, `eval-visuomotor`.

## Gate

`test_visuomotor_policy_beats_zero_on_held_out`: trains from pixels and asserts nonzero held-out
success under true physics (seed 0 = 4/6). Plus shape/overfit tests for the CNN policy, a
proprio-drops-privileged test, a train-checkpoint test, and a deterministic visuomotor-rollout
test. `tests/learn tests/replay` green.

**M2.5 complete** — Track A (physics sim loop) + Track B (pixels) both shipped. The sim loop runs
end-to-end from camera pixels to a friction grasp under true contact physics, no kinematic
shortcut and no privileged state.

**Possible next:** wrist camera; domain randomisation (lighting/texture/cube colour) for sim-to-real
credibility; or buy a real SO-ARM100 (~150 €) now the sim loop is validated.
