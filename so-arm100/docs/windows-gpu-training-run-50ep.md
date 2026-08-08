# SmolVLA fine-tune on the 50-episode circle-insert dataset (Windows RTX 5070)

Third run on the Windows box. Prerequisite: `windows-gpu-training-setup.md`
already completed there (CUDA verified, lerobot 0.6.1 installed). The
environment does not need rebuilding — only the dataset changes.

Read `windows-gpu-training-run.md` first for the reasoning behind the flag
choices (`--policy.use_amp=false`, `--policy.input_features=null`,
`--steps=30000`). This doc only covers what differs for this dataset.

## What is different this time

| | 55-episode run (2026-08-07) | This run |
|---|---|---|
| Dataset dir | `data/local/lerobot_dataset` | `data/local/datasets/circle_insert_50ep` |
| `--dataset.repo_id` | `local/shape_sort_teleop` | `local/circle_insert_50ep` |
| Task string | "Pick up a shape piece and insert it into its matching hole." | "Insert the circle piece into its matching hole." |
| Schema | v1 builder (app degrees/percent convention) | **v2 builder (LeRobot tick-derived convention)** |
| `observation.state` | commanded target, shifted one step | **measured follower encoder readings** |

The schema change is the important one. Every previous checkpoint was
trained against an `observation.state` that was really just the previous
commanded action — the policy never saw where the arm actually was. This
dataset has real follower telemetry, 100% coverage, zero dropped samples.

## Why retrain from scratch rather than resume

The 55-episode run regressed against the 29-episode one. Do not resume from
either checkpoint: their `observation.state` means something different from
this dataset's, so the learned state encoder would be actively wrong.
`--policy.path=lerobot/smolvla_base` from scratch, same as the earlier runs.

## Copy the dataset over

Same method as before (USB / network share / cloud drive). This dataset is
at a **new path** — do not overwrite the old `data/local/lerobot_dataset`
copy, since the archived 29/55-episode datasets are still the only thing the
earlier checkpoints can be evaluated against.

Then strip the macOS AppleDouble files, or `datasets` will crash with
"Parquet magic bytes not found":

```powershell
Get-ChildItem -Recurse -Force data/local/datasets/circle_insert_50ep `
  | Where-Object { $_.Name -like "._*" } `
  | Remove-Item -Force -Confirm:$false
```

Confirm sleep is still disabled (`powercfg /change standby-timeout-ac 0`).

## Smoke test

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_insert_50ep `
  --dataset.root=data/local/datasets/circle_insert_50ep `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_circle_insert_50ep_smoke `
  --job_name=smolvla_circle_insert_50ep_smoke `
  --wandb.enable=false `
  --steps=10 `
  --save_freq=10 `
  --log_freq=1
```

Codec and resolution are unchanged from the 55-episode dataset (AV1,
1280x720), which already decoded fine with the pyav backend on this box, so
no new decode risk. What the smoke test is actually confirming here is that
the v2 builder's feature schema loads without a mismatch — the feature names
are the same as before, but this is the first dataset the v2 builder has
produced for training.

## Full run

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_insert_50ep `
  --dataset.root=data/local/datasets/circle_insert_50ep `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_circle_insert_50ep_30000 `
  --job_name=smolvla_circle_insert_50ep_30000 `
  --wandb.enable=false `
  --steps=30000 `
  --save_freq=5000 `
  --log_freq=50
```

Expect roughly 2 hours at ~5.3 steps/sec, ~3 GB of the 12 GB VRAM, based on
the two previous runs on this box.

Resuming after an interruption works the same way as in
`windows-gpu-training-run.md` (`--resume=true --config_path=...` at the
highest checkpoint; Windows won't write the `checkpoints/last` symlink).

## After it finishes

1. Copy `outputs/train/smolvla_circle_insert_50ep_30000/` back to the Mac.
2. Replay a recorded episode on hardware first —
   `robot_learning/loop.py replay --dataset=circle_insert_50ep --episode=0`.
   This is the safety gate: it proves the action column round-trips to real
   motion before any policy drives the arm.
3. Then `robot_learning/loop.py eval --checkpoint=...`, and score k/N
   successes by hand. That number is the metric. Held-out MAE only compares
   checkpoints against one frozen split — it is not a success rate, and the
   55-episode run scored acceptably on it while getting worse in reality.

## Known limitation of this dataset

All 50 episodes are the **same piece into the same hole** (the green
circle), so the prompt cannot select a shape — a policy trained here learns
"go to the circle". Start positions vary continuously across roughly 190 x
110 px in the overview frame (about 55% of the board width), which is real
diversity, but it is not the discrete `loop.py grid` pattern and the board
itself never moved. If the goal becomes actual shape selection, that needs
episodes for the other five shapes.
