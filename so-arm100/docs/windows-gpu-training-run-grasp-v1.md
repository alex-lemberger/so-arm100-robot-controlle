# SmolVLA fine-tune on circle_grasp_v1 (Windows RTX 5070)

Fifth run on the Windows box. The environment there is already set up from the
previous four (`windows-gpu-training-setup.md`); flag reasoning lives in
`windows-gpu-training-run.md` and `windows-gpu-training-run-50ep-trimmed.md`.
This doc covers only what is new.

## Why retrain

The trimmed batch-32 checkpoint scores **3/10** on hardware — the project's
first completed insertions. Its failure is narrow and consistent: the arm
reaches the disc and loses it at or just after closing the gripper.

Grasping is roughly 5% of a full insert episode, so the 50 demonstrations
contain only about 1,300 frames of the phase that actually fails. This dataset
adds 31 short grasp-only takes recorded 2026-08-09 and 2026-08-10 — park just
above the piece, descend, close, lift a few cm, stop — which contribute 5,463
frames that are almost entirely grasp. That is roughly **five times the grasp
coverage** of the previous dataset.

The grasp takes carry their own task string. Until now every one of the 26,078
training frames shared a single instruction, and the resulting policy was
measured on 2026-08-09 to react to prompt *wording* but not to prompt *meaning*.
Two distinct instructions in one dataset is the precondition for language to
become discriminative at all.

## What is different from the previous run

| | 50ep trimmed | circle_grasp_v1 |
|---|---|---|
| Dataset dir | `data/local/datasets/circle_insert_50ep_trimmed` | `data/local/datasets/circle_grasp_v1` |
| `--dataset.repo_id` | `local/circle_insert_50ep_trimmed` | `local/circle_grasp_v1` |
| Episodes | 50 | 81 (50 insert + 31 grasp) |
| Frames | 26,078 | 31,541 (26,078 + 5,463) |
| Tasks | 1 | 2 |
| Size | 754 MB | 915 MB |

Built with `loop.py build --trim` and merged with `loop.py merge`. The grasp
takes were trimmed on the same settings as the insert episodes (threshold 8.0
ticks/sample, 0.3 s of stillness kept each side) so the two halves are
consistent; trimming kept 77% of the grasp frames and the shortest surviving
take is 3.1 s.

Two of the 2026-08-10 recordings are deliberately excluded, and the reasons are
recorded in `outputs/episode-review/grasp-only.txt`: one caught a motionless arm,
the other has a single out-of-range gripper sample.

**Train from scratch** (`--policy.path=lerobot/smolvla_base`), not resumed from
the 3/10 checkpoint. Full fine-tune, not LoRA — everything except the dataset
should match the run that produced 3/10, so that if the number moves it is the
data that moved it.

## Copy the dataset over

New path; leave the previous datasets in place so the checkpoints stay
comparable. 11 files, 959,370,995 bytes.

```
bb547b51b0795a5a92fb84b151d2f1e5  data/chunk-000/file-000.parquet
18e5be5035598489b03b60fb8ea28080  meta/episodes/chunk-000/file-000.parquet
65b9b67848fb030f28d40c224ccfa87f  meta/info.json
988db0429105543f55fac27d0146665a  meta/stats.json
92e30061d9bddeac1bd88328bc4b6bd0  meta/tasks.parquet
afa161ac49a4c6499b4f508efd209ff0  videos/observation.images.overview/chunk-000/file-000.mp4
92de53c948908277338f53b07c3e38ca  videos/observation.images.overview/chunk-000/file-001.mp4
0c2d2a19b84b1746b5350bf1ac477573  videos/observation.images.overview/chunk-000/file-002.mp4
802a7edca2b495be16d3ad3827d9009a  videos/observation.images.overview/chunk-000/file-003.mp4
02ce5559ce74e25df115aa1537597a2a  videos/observation.images.wrist/chunk-000/file-000.mp4
979d0af7e2b9e97eec10cbc60e5917e0  videos/observation.images.wrist/chunk-000/file-001.mp4
```

The first three overview videos and the first wrist video are byte-identical to
the trimmed 50-episode dataset, so if that copy is still on the box you only need
the four new files plus the five metadata files.

Strip the macOS metadata after copying, then check the count and total:

```powershell
cd C:\projects\so-arm100-robot-controlle\so-arm100\data\local\datasets\circle_grasp_v1
Get-ChildItem -Recurse -Force | Where-Object { $_.Name -like "._*" -or $_.Name -eq ".DS_Store" } | Remove-Item -Force -Confirm:$false
Get-ChildItem -Recurse -File | Measure-Object -Property Length -Sum | Select-Object Count, Sum
```

Expect **Count 11, Sum 959370995**.

## Smoke test, then the full run

```powershell
cd C:\projects\so-arm100-robot-controlle\so-arm100
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_grasp_v1 `
  --dataset.root=data/local/datasets/circle_grasp_v1 `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_circle_grasp_v1_20000 `
  --job_name=smolvla_circle_grasp_v1_20000 `
  --wandb.enable=false `
  --batch_size=32 `
  --steps=20000 `
  --eval_steps=500 `
  --save_freq=5000 `
  --log_freq=50 2>&1 | Tee-Object -FilePath train-grasp-v1.log
```

For the smoke test, change `--steps=10 --save_freq=10 --log_freq=1 --eval_steps=5`
and use a `_smoke` suffix on `--output_dir`/`--job_name`. Catch an OOM in 10 steps,
not four hours in. If batch 32 OOMs, drop to 24 rather than back to 8. If the
printed s/step goes above ~1.2 the card is thrashing and the batch should come
down.

### `--eval_steps=500` is new, and it matters

The previous run passed `--dataset.eval_split=0.15` but never set `--eval_steps`,
which defaults to **0** (`configs/train.py:109`). The split removed 15% of the
training data and then measured nothing on it. That is a large part of why the
55-episode regression was not caught until it was already on hardware.

The split is stratified per task (`datasets/factory.py:144`), so it holds out the
last 8 insert episodes and the last 5 grasp episodes — 68 train / 13 eval. A
grasp-specific held-out loss is exactly the signal this run needs, since the
whole hypothesis is about grasp quality.

Everything else is unchanged from the trimmed run: batch 32 (not 64 — measured at
~3.0 s/step on this card, VRAM thrashing), 20,000 steps at the SmolVLA guide's
figure with the scheduler auto-scaling to it, ~4 hours estimated. Disable Windows
sleep before starting.

## Evaluating it back on the Mac

Use `loop.py eval`, which applies the three rollout fixes by default
(`--inference.type=rtc`, `execution_horizon=10` with `max_guidance_weight=10.0`,
`max_relative_target=25.0`). Do not add `--interpolation_multiplier`. The full
reasoning is in `windows-gpu-training-run-50ep-trimmed.md`.

Two things specific to this checkpoint:

**Evaluate on the insert instruction.** The scored comparison against 3/10 is
`"Insert the circle piece into its matching hole."` — the same string the 50
demonstrations carry. Do not score the run on the grasp prompt and compare the
two numbers; they are different tasks.

**Then test the grasp prompt separately.** Running the same checkpoint on
`"Pick up the circle piece."` and seeing it stop after the lift, rather than
continuing toward the hole, is the direct test of whether language finally
carries meaning. That is a new measurement, not a regression check — the previous
checkpoints could not have passed it, since they only ever saw one instruction.
