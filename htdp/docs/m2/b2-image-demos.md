# M2.5 B2 — Image Demos (result)

**Done:** `generate_demos` now records a **96×96 RGB frame per demo row** from the `front`
camera, alongside the existing state/action. The pixels a B3 visuomotor policy will train on.
Train/policy are unchanged — `train.py` still reads only state+action — so B2 is a pure dataset
extension (clean seam to B3).

## Storage — sidecar `.npy`, not a parquet column

Each episode writes `episode_XXXXXX_image.npy` (uint8 `[T, 96, 96, 3]`) next to its
`episode_XXXXXX.parquet`, aligned 1:1 with the rows by `frame_index`. Rationale:

- A 96×96×3 image is 27 KB/frame; inlining it as a nested parquet column bloats the file and
  slows the low-dim read path (`train.py` globs `episode_*.parquet` and would now drag the
  pixels through every state-only load). The `.npy` glob is excluded, so state-based training is
  untouched.
- LeRobot itself sidecars images (as per-episode video); a sidecar array is the same idea,
  simpler for a sim dataset. B3 loads the `.npy` by `frame_index`.

`meta/info.json` gains an `observation.image` feature
(`dtype uint8`, `shape [96,96,3]`, `storage "sidecar_npy"`, `camera "front"`) so the dataset is
self-describing.

## Rendering

`_record_episode` builds one persistent `mujoco.Renderer` (96×96) from the teacher's own model
on the first `on_sample` and reuses it for every frame (no per-frame renderer construction), via
`render_camera(..., renderer=...)` — the same named-camera path B1 defined and B3 rollout will
reuse, so train/rollout framing can't drift.

## Gate

`test_generate_demos_writes_aligned_image_sidecar`: sidecar exists per episode, shape
`[rows,96,96,3]` uint8, and the **red cube is present** in the stack (> 20 red pixels) — a
zero/blank stack would silently train a blind visuomotor policy in B3 (the render false-green
lesson carried into the dataset). `tests/learn tests/replay` = **28 passed** (suite ~140 s; the
extra ~65 s is image rendering in every `generate_demos`).

**Next (B3):** visuomotor ACT — load the image sidecar in the dataset/trainer, add a small CNN
encoder, **drop the privileged cube/target xyz** from the observation (keep proprioception +
pixels), and render the same `front` frame in `rollout_policy` for closed-loop visuomotor
control. Wrist camera optional.
