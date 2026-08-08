# SmolVLA fine-tune on the trimmed 50-episode dataset (Windows RTX 5070)

Fourth run on the Windows box. The environment there is already set up from
the previous three (`windows-gpu-training-setup.md`); only the dataset
changes. Flag reasoning lives in `windows-gpu-training-run.md`; the
dataset-specific reasoning for this 50-episode batch lives in
`windows-gpu-training-run-50ep.md`. This doc covers only what is new.

## Why retrain

The untrimmed 30,000-step checkpoint
(`smolvla_circle_insert_50ep_30000`) runs the task on real hardware but
its motion is visibly jerky. Measured on 2026-08-08, inside a single
50-action chunk -- with the control loop at a clean 30 Hz, no clamping,
and no chunk splicing involved -- the policy reverses direction **36
times** where the demonstration it was trained on reverses **once**, at
**3.4x** the per-step amplitude. Raising the flow-matching integration
steps (10 / 20 / 30 / 50) does not help, so this is not an integration
artifact: the model learned a noisy action distribution.

The most likely cause is the training data's stationary padding. The app
recorder starts before the operator does and stops after, so **every one
of the 50 episodes** opened with a motionless arm (mean 2.6 s) and closed
with another (mean 2.9 s) -- 25% of all frames. A still arm at the start
pose and a still arm mid-pause produce near-identical observations, so the
policy was fitting both "hold position" and "move" against inputs it
cannot tell apart. Oscillating between those two modes is exactly the
alternating pattern measured above.

This dataset removes that padding.

## What is different from the previous run

| | untrimmed | trimmed |
|---|---|---|
| Dataset dir | `data/local/datasets/circle_insert_50ep` | `data/local/datasets/circle_insert_50ep_trimmed` |
| `--dataset.repo_id` | `local/circle_insert_50ep` | `local/circle_insert_50ep_trimmed` |
| Frames | 33,707 | 26,078 |
| Size | 954 MB | 754 MB |

Same 50 episodes, same manifest, same task string, same schema. Built with
`build_lerobot_dataset_v2.py --trim-stationary` (threshold 8.0 ticks/sample,
0.3 s of stillness kept on each side). Trimming removed 5.1 s per episode on
average and no episode fell below 13.3 s, so nothing ate into a demonstration.

**Train from scratch** (`--policy.path=lerobot/smolvla_base`), not resumed
from the untrimmed checkpoint -- the point is to not inherit the learned
"hold position" mode.

## Copy the dataset over

New path; leave the untrimmed copy in place so the two checkpoints stay
comparable. 9 files, 790,257,179 bytes.

```
5dafbd75456270cfd6b1823b9a4c3edf  data/chunk-000/file-000.parquet
320833ca4626e0533efc3741c340d332  meta/episodes/chunk-000/file-000.parquet
61e235bd58004bcfd863ddab0fa0c296  meta/info.json
edb3c374f9e01cf3f0f09526ea4b065f  meta/stats.json
54779ccdfb78a6a3fbd107d0dd64383d  meta/tasks.parquet
afa161ac49a4c6499b4f508efd209ff0  videos/observation.images.overview/chunk-000/file-000.mp4
92de53c948908277338f53b07c3e38ca  videos/observation.images.overview/chunk-000/file-001.mp4
0c2d2a19b84b1746b5350bf1ac477573  videos/observation.images.overview/chunk-000/file-002.mp4
02ce5559ce74e25df115aa1537597a2a  videos/observation.images.wrist/chunk-000/file-000.mp4
```

Strip the macOS metadata after copying, then check the count and total:

```powershell
cd C:\projects\so-arm100-robot-controlle\so-arm100\data\local\datasets\circle_insert_50ep_trimmed
Get-ChildItem -Recurse -Force | Where-Object { $_.Name -like "._*" -or $_.Name -eq ".DS_Store" } | Remove-Item -Force -Confirm:$false
Get-ChildItem -Recurse -File | Measure-Object -Property Length -Sum | Select-Object Count, Sum
```

Expect **Count 9, Sum 790257179**.

## Smoke test, then the full run

```powershell
cd C:\projects\so-arm100-robot-controlle\so-arm100
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_insert_50ep_trimmed `
  --dataset.root=data/local/datasets/circle_insert_50ep_trimmed `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_circle_insert_50ep_trimmed_20000 `
  --job_name=smolvla_circle_insert_50ep_trimmed_20000 `
  --wandb.enable=false `
  --batch_size=32 `
  --steps=20000 `
  --save_freq=5000 `
  --log_freq=50
```

**`--batch_size=32` is the most important change in this run, more than the
trimming.** `lerobot-train` defaults to `batch_size=8` (`configs/train.py:101`)
and none of the previous runs overrode it, so every checkpoint this project has
produced was trained at 8, peaking at **3.06 GB of the 5070's 12 GB** -- the
card three-quarters idle. An 8x smaller batch than the SmolVLA guide's 64 means
correspondingly noisier gradients, a standard cause of the noisy action
distribution measured on the untrimmed checkpoint (36 direction reversals inside
one chunk where the demonstration has 1).

**Do not use batch 64 on this card.** Measured 2026-08-08: batch 64 projected
**25 hours** for 30k steps, i.e. ~3.0 s/step, against ~1.5 s/step if it scaled
linearly from the 0.19 s/step seen at batch 8. That 2x-worse-than-linear cost is
VRAM pressure on 12 GB, not useful compute. 32 stays in the linear region.

**20,000 steps, not 30,000.** That is the figure the SmolVLA guide recommends,
and 30,000 was only ever chosen when each step saw 8 samples. `lerobot-train`'s
scheduler auto-scales warmup and decay to whatever `--steps` is passed, so a
shorter run is properly scheduled rather than truncated. At 32 x 20,000 the
model sees 640k samples -- **2.7x the 240k of the original 8 x 30,000 run** --
in an estimated ~4 hours.

For the smoke test, change `--steps=10 --save_freq=10 --log_freq=1` and use
a `_smoke` suffix on `--output_dir`/`--job_name`. That is where an OOM will
show up -- catch it in 10 steps, not hours in. If batch 32 OOMs, drop to 24
rather than back to 8; the batch size is the variable being tested. Also note
the printed s/step: above ~1.2 s/step the card is thrashing and the batch
should come down.

**Save the console output this time.** The previous run's log never made it
back to the Mac, so there is no loss curve to compare against. Pipe it:
`... 2>&1 | Tee-Object -FilePath train-trimmed.log`.

## Evaluating it back on the Mac

The rollout harness was substantially wrong until 2026-08-08 and is now
fixed in `robot_learning/loop.py`. Use `loop.py eval`, which applies all
three fixes by default:

- `--inference.type=rtc` — the default sync engine blocks the control loop
  on a full policy forward pass every tick, running it at **3.3 Hz against
  a 30 Hz target**. Each 50-action chunk (1.67 s of intended motion)
  stretched over ~15 s, so the arm crawled and looked like it was doing
  nothing at all.
- `--inference.rtc.execution_horizon=10` with `max_guidance_weight=10.0` —
  the values both `docs/source/rtc.mdx` and `docs/source/smolvla.mdx` use.
  The RTC doc gives "typical values: 8-12" and warns that higher means
  smoother transitions but *less reactivity*. 10.0 guidance weight is
  documented as optimal for 10-step flow matching, which SmolVLA is.
- `max_relative_target=25.0`, was 5.0 — 52% of training frames have some
  joint commanded more than 5.0 ahead of measured position (shoulder_lift
  p95 12.4, p99 20.9, max 38.1, since it leads the follower against
  gravity). The old clamp truncated normal commands on every other tick.

Do **not** add `--interpolation_multiplier`. 90 Hz with 3x interpolation was
tried on hardware and the arm stopped moving entirely.

Score k/N by hand. Compare against the untrimmed checkpoint measured under
this same fixed harness -- not against any k/N recorded before 2026-08-08,
which were all taken through the broken loop and are not comparable.
