# M2 — Imitation Policy (Franka Pick-and-Place) Design

**Date:** 2026-06-27
**Status:** Approved design, pre-plan
**Supersedes:** the one-line M2 sketch in the portfolio re-scope memory.

## Goal

Close a **generalizing learned-control loop**: collect demonstrations from the M1 scripted
Franka pick-and-place, train an imitation policy, and run it **autonomously closed-loop** in
MuJoCo over **held-out cube positions**, beating/matching the scripted-IK baseline on a
success-rate metric. State-based observations only (pixels are deferred to M2.5).

This is the robotics-employer story: data → train → autonomous policy that generalizes, with
an honest success-rate report against a baseline.

## Scope decisions (locked)

- **Bar:** generalizing policy, tightly scoped (A). Randomize cube start; fixed target.
- **Stack:** hybrid (C). Adopt the **LeRobotDataset format** on disk; own a **compact ACT**
  policy + training loop (no full `lerobot` library dependency for M2). Real `lerobot` can load
  the dataset later; swapping in its trainer is a future M2.5 option.
- **Observation:** low-dim **state** (A). Pixels = M2.5.
- **Control:** closed-loop **position actuators** (A). Policy outputs joint position targets +
  gripper command; sim steps Franka position actuators (real PD physics). Grasp = M1 kinematic
  attach, **triggered by the policy's gripper-close action when the grasp site is near the
  cube** (not scripted).

### Explicitly deferred (YAGNI / anti-scope-creep)

Pixels/visuomotor (M2.5), ACT CVAE branch, temporal ensembling, spatial extrapolation
(held-out corners), target randomization, multi-task. Each is a flag or a later milestone, not
M2.

## Architecture & data flow

```
M1 scripted episode (Franka IK pick-place), randomized cube xy
        │  run N times (seeded)
        ▼
[1] data-gen ──► LeRobotDataset-format demos on disk
        │         per frame: (observation.state, action) + episode boundaries
        ▼
[2] train ──► compact ACT policy (PyTorch, MPS) ──► policy.pt (+ norm stats)
        │
        ▼
[3] eval rollout ──► closed-loop actuator control in MuJoCo over HELD-OUT cube xy;
                     grasp-attach gated on gripper action + cube proximity
        │
        ▼
   success-rate + place-error vs scripted-IK baseline ──► JSON + printed report
```

### Observation (state vector, dim 17)

7 arm joint positions + 1 gripper width + 3 EEF/grasp-site xyz + 3 cube xyz + 3 target xyz.

### Action (dim 8)

7 joint position targets + 1 gripper command (0 = open, 1 = close). ACT predicts a **chunk** of
`k` actions (k ≈ 20).

## Components

New package `src/htdp/learn/`; one change to `replay/episode.py`. All behind a new `learn`
optional extra (torch + dataset deps), lazy-imported so the base suite stays green without it.

| Module | Purpose | Depends on |
|--------|---------|-----------|
| `replay/episode.py` *(modify)* | add `cube_xy` arg (randomized start); expose per-frame `(obs, action)` so the scripted run is the **teacher** | mujoco |
| `learn/obs.py` | build the state-obs vector + action vector from sim state — **single source of truth** shared by data-gen and rollout | mujoco |
| `learn/dataset.py` | run N randomized scripted episodes → write LeRobotDataset format; held-out split; per-feature stats | episode, obs |
| `learn/policy.py` | compact ACT (transformer enc-dec, action-chunking; CVAE flag default off) | torch |
| `learn/train.py` | MPS training loop, L1 action loss, checkpoint `policy.pt` + norm stats | policy, dataset |
| `learn/rollout.py` | closed-loop eval in MuJoCo: policy → actuator `ctrl`; grasp-attach gating | policy, obs, mujoco |
| `learn/eval.py` | policy vs scripted-IK baseline over held-out set → success-rate + place-error report | rollout, episode |

CLI commands (lazy, behind `learn` extra): `htdp gen-demos`, `htdp train-policy`,
`htdp eval-policy`.

**Critical boundary:** `learn/obs.py` defines the obs+action layout used by **both** data-gen
and rollout, so training and deployment cannot silently disagree (a classic imitation bug).

## Dataset

- **Randomization:** cube start xy uniform in a 10×10 cm patch on the table
  (x ∈ [0.45, 0.55], y ∈ [−0.20, −0.10]); cube z fixed (resting on table). **Target fixed** at
  (0.5, 0.15, 0.205).
- **Split:** independent seeded random positions — **100 train demos, 25 held-out test**
  (in-distribution generalization).
- **Frame granularity:** one `(obs, action)` per interpolated waypoint step (~200/episode,
  not per physics sub-step) → ~20k train frames.
- **Format — LeRobotDataset (minimal faithful v2 subset):**
  ```
  demos/
    data/chunk-000/episode_000000.parquet   # observation.state, action,
                                             # timestamp, frame_index,
                                             # episode_index, index
    meta/info.json        # fps, feature shapes/names/dtypes, codebase version
    meta/episodes.jsonl    # per-episode length + task string
    meta/stats.json        # per-feature mean/std/min/max for normalization
  ```
  Our trainer reads this directly; real `lerobot` can load it later.

## Policy & training

- **Compact ACT:** obs (17) → linear embed → transformer encoder (hidden 256, 4 heads, 2–3
  layers) → decoder with `k` learned query tokens → action head (dim 8 per token). ~1–2M params.
- **CVAE off by default** (demos are unimodal scripted); `--cvae` flag for later.
- **Normalization:** obs/action standardized via `meta/stats.json` (mean/std).
- **Training:** L1 loss on the action chunk; AdamW, lr 1e-4, batch 64, ~a few k steps to
  val-loss plateau; runs on **MPS**. Output: `policy.pt` + bundled norm stats. Fixed seed
  (reproducible-enough; full MPS determinism not guaranteed — documented).
- **Rollout execution:** predict chunk → execute all `k` actions open-loop (write actuator
  `ctrl`, step `settle` sim steps each) → re-predict. No temporal ensembling for tight scope
  (flag for later).

## Eval & baseline

- **Rollout** per held-out cube xy: build obs → policy chunk → write actuator `ctrl` (joint
  targets + gripper), `mj_step` `settle` times (PD-tracked physics). **Grasp gating:** gripper
  command = close AND `grasp_site` within ~3 cm of cube → attach (M1 kinematic slave); open →
  release.
- **Success:** cube ends < 3 cm from target xy AND was lifted while attached.
- **Baseline:** scripted-IK `run_episode` at the same 25 positions (≈100% success, place-err
  ≈ 0).
- **Report** (`learn/eval.py`): JSON + printed table — policy vs baseline: success-rate
  (n/25), mean place-error. The M2 headline artifact.
- **M2 target:** policy ≥ **80% success** on the 25 held-out positions.

**Action-space consistency:** demo `action` = the scripted run's IK joint solution per step
(the joint *target*); rollout feeds the same quantity to actuators. Train and deploy speak the
same action language. Minor train/deploy gap: data-gen is kinematic-exact, rollout is
actuator-tracked — ACT tolerates this (risk 2).

## Testing

All heavy tests gated `pytest.importorskip("torch")` (and mujoco) so the base suite stays
green without the `learn` extra.

- `obs.py` — obs/action vector shape + values from a known sim state (the shared contract).
- `dataset.py` — gen 2 tiny episodes → LeRobotDataset files exist, parquet columns correct,
  `meta/*.json` valid, stats finite, deterministic under seed.
- `policy.py` — forward-pass shapes (obs batch → action chunk); overfit-one-batch loss drops.
- `train.py` *(slow)* — train ~50 steps on a 2-episode set → checkpoint written, loss finite.
- `rollout.py` — one episode with an untrained policy → returns result, applies `ctrl`, no
  crash; seeded determinism.
- `eval.py` *(slow)* — end-to-end smoke: gen 2 → train 50 steps → eval 2 positions → report
  structure.

## Risks & mitigations

1. **Policy < 80% success** → unimodal scripted demos suit ACT; bump demos/chunk/epochs; the
   10×10 cm patch is deliberately small.
2. **Actuator-tracking vs kinematic-demo gap** → tune actuator gains / `settle`; fallback =
   record action as the *achieved* joint pos rather than the commanded target.
3. **MPS slow / nondeterministic** → documented; CPU fallback path.
4. **Grasp gating brittle under physics** → proximity threshold + robust M1 kinematic attach;
   tune threshold.
5. **LeRobot format drift** → implement a documented minimal subset; full `lerobot` load is a
   stretch, not a requirement.
6. **Scope creep** → pixels, CVAE, temporal ensembling, spatial extrapolation all deferred.

## Global constraints (carried from M1)

- Python ≥ 3.11; `mypy --strict` passes; `ruff` line-length 100, LF endings.
- New heavy code behind the `learn` extra, lazy-imported; importing `htdp.learn.*` at module
  load must NOT require torch/mujoco. Raise a clear "install with: uv sync --extra learn" error.
- Determinism where feasible (seeded data-gen + eval); MPS training documented as
  reproducible-enough, not bit-exact.
- Existing `htdp sim-task` / `replay` paths stay working.
