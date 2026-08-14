# SmolVLA fine-tune: full 30,000-step run on the Windows GPU box

Prerequisite: `windows-gpu-training-setup.md` completed (CUDA verified,
lerobot 0.6.1 installed, `data/local/lerobot_dataset/` copied over).

## Why 30,000 steps

`lerobot-train`'s SmolVLA scheduler (`CosineDecayWithWarmupSchedulerConfig`)
auto-scales warmup+decay to finish exactly at whatever `--steps` you pass
when that's less than its built-in `scheduler_decay_steps=30000` default —
that's what happened at the earlier 2000-step run on the Mac (LR hit its
2.5e-06 floor by step 2000, not because of a manual override). Passing
`--steps=30000` uses SmolVLA's own designed schedule as-is, no scaling
applied. Previous runs (500, 2000 steps) showed task-relevant behavior on
real hardware but never completed an actual pick — 30,000 steps is the
properly-scheduled real run this project has been deferring pending
faster-than-MPS hardware.

## Smoke test first

Same pattern as every previous training run in this project (see
`docs/superpowers/plans/2026-08-05-smolvla-shape-sort-smoke-run.md`) — a
short run first to catch problems before committing hours to it:

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/shape_sort_teleop `
  --dataset.root=data/local/lerobot_dataset `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_shape_sort_smoke_cuda `
  --job_name=smolvla_shape_sort_smoke_cuda `
  --wandb.enable=false `
  --steps=10 `
  --save_freq=10 `
  --log_freq=1
```

Two flags differ from the Mac command:

- `--policy.use_amp=false` — SmolVLA uses BFloat16 weights; PyTorch's
  AMP GradScaler doesn't support BFloat16 and throws
  `NotImplementedError` on the first backward pass. BFloat16 is native
  precision on Blackwell and doesn't need gradient scaling, so AMP can
  simply be disabled.
- `--policy.input_features=null` — `lerobot/smolvla_base` ships with a
  3-camera input config (`camera1/2/3`); this dataset has 2 cameras
  (`overview`/`wrist`). Passing `null` tells lerobot to infer input
  features from the dataset instead of the base checkpoint config,
  resolving the mismatch without renaming dataset keys.

Confirms: SmolVLA base weights download (first invocation only — ~450M
params from the Hugging Face Hub, needs network access, not cached on this
machine yet), the dataset's features (6-dim state/action, `overview`/`wrist`
camera keys) load without a schema mismatch on CUDA, loss decreases across
the 10 steps, and a checkpoint is written to
`outputs/train/smolvla_shape_sort_smoke_cuda/checkpoints/`.

**Also note the actual per-step time it prints.** That confirms or corrects
the ~5-10x-over-MPS estimate before committing to the full run below.

## Full run

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/shape_sort_teleop `
  --dataset.root=data/local/lerobot_dataset `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_shape_sort_30000 `
  --job_name=smolvla_shape_sort_30000 `
  --wandb.enable=false `
  --steps=30000 `
  --save_freq=5000 `
  --log_freq=50
```

Differences from the smoke test: `--steps=30000` for the real schedule,
`--save_freq=5000` writes a checkpoint every 5000 steps (6 checkpoints
total: 5000, 10000, ..., 30000) instead of only at the very end — lets you
compare checkpoints or recover progress without waiting for the full run,
and `--log_freq=50` keeps console output readable over a multi-hour run.

**Resuming after an interruption.** Windows cannot create symlinks without
Developer Mode enabled, so lerobot's `checkpoints/last` convenience link
will not be written. If the run is interrupted, resume by pointing
`--config_path` at the highest-numbered checkpoint directory explicitly:

```powershell
.venv-lerobot\Scripts\lerobot-train `
  ... (same flags as above, minus --policy.path) ... `
  --resume=true `
  --config_path=outputs/train/smolvla_shape_sort_30000/checkpoints/005000/pretrained_model
```

Replace `005000` with the actual latest checkpoint step.

## After it finishes

**Actual results (2026-08-07 run):** loss 0.469 → 0.031 over 30,000 steps,
~5.3 steps/sec sustained, ~2 hours wall time (vs ~17h estimated on Mac MPS —
roughly 10× speedup). GPU memory peaked at 3.06 GB of 12 GB available.
All 6 checkpoints written: 005000, 010000, 015000, 020000, 025000, 030000.

1. Verify: printed loss trend across the run (should decrease well past
   where the 500/2000-step runs plateaued), and a
   `checkpoints/030000/pretrained_model/` directory with the expected
   contents.
2. Run the held-out-split MAE evaluation the finetune design spec
   (`docs/superpowers/specs/2026-08-05-smolvla-shape-sort-finetune-design.md`)
   calls for, before any physical hardware test.
3. Copy `outputs/train/smolvla_shape_sort_30000/` back to the Mac (same
   transfer method as the dataset) to run it against real hardware via
   `robot_learning/run_policy_prompt.py`, exactly like the 500/2000-step
   checkpoints were tested.

## Re-run on the expanded 55-episode dataset (2026-08-07)

The 30k-step run above never completed an actual grasp on real hardware
(see `episode-lerobot-dataset-pipeline` project notes). Closed-loop
debugging on the Mac traced this to a lack of training diversity right at
the close-range pre-grasp geometry, not a bug — the fix decided on was
recording more demonstrations, biased toward varying the piece's starting
position/rotation, and retraining from scratch (not resumed from the
30,000-step checkpoint).

`data/lerobot_dataset/` has been rebuilt from 29 → 55 episodes (45,782
frames, ~300 MB) and is already present on this machine. Dataset is ready
— no transfer needed.

Same full-run command as above, with a distinct `--output_dir`/`--job_name`
so it doesn't overwrite the existing `smolvla_shape_sort_30000` checkpoints:

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/shape_sort_teleop `
  --dataset.root=data/lerobot_dataset `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_shape_sort_55ep_30000 `
  --job_name=smolvla_shape_sort_55ep_30000 `
  --wandb.enable=false `
  --steps=30000 `
  --save_freq=5000 `
  --log_freq=50
```

Based on the prior run's throughput (~5.3 steps/sec on this RTX 5070),
expect roughly the same ~2h wall time. Same smoke-test-first pattern
applies if you want to sanity-check before committing to the full run —
reuse the smoke-test command above, just pointed at the new
`data/local/lerobot_dataset`.

After it finishes: copy `outputs/train/smolvla_shape_sort_55ep_30000/` back
to the Mac and run the held-out MAE eval
(`robot_learning/eval_smolvla_held_out.py`) before any physical hardware
test, same as the first run.
