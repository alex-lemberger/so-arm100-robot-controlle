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
  --policy.use_amp=true `
  --output_dir=outputs/train/smolvla_shape_sort_smoke_cuda `
  --job_name=smolvla_shape_sort_smoke_cuda `
  --wandb.enable=false `
  --steps=10 `
  --save_freq=10 `
  --log_freq=1
```

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
  --policy.use_amp=true `
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

## After it finishes

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
