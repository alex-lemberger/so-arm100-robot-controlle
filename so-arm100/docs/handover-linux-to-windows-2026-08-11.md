# Handover: Linux → Windows, §19-21 training comparison (2026-08-11)

## Do we even need a separate Windows session?

Yes, for training specifically — but not for the reason you'd expect.

This Linux workstation and the Windows training box are **the same physical
machine**, dual-booted off the same NVMe drive. `/media/alex/F6E48479E4843DBD`
(where this entire repo lives on the Linux side) is literally the Windows
`C:` drive, mounted read/write via `ntfs3` (`/dev/nvme0n1p3` — confirmed by
`pagefile.sys`, `Program Files`, and `Users` sitting at its root). This
repo's path maps exactly to `C:\projects\so-arm100-robot-controlle\so-arm100`,
the same path every `windows-gpu-training-run-*.md` doc already uses.

**So there is no data to hand over.** Datasets A/B/C already sit at
`data/local/datasets/...` and will be there the moment you reboot into
Windows — no USB stick, no network share, no `robocopy`, unlike every
previous training run's setup step. Same in reverse: checkpoints
`lerobot-train` writes to `outputs/train/...` on Windows will already be
sitting there when you reboot back into Linux. Zero manual copying either
direction.

The actual reason to boot into Windows at all: that's the only machine with
a **verified CUDA-enabled SmolVLA training environment** (`windows-gpu-training-setup.md`
— Python 3.12.13, torch 2.11.0+cu128, lerobot 0.6.1[smolvla], transformers
5.5.4, RTX 5070 confirmed at ~5.3 steps/sec). The Linux-side Docker images
are not a substitute: `real-robot:latest` is explicitly CPU-only (built for
serial/dataset work, not training), and `leisaac-sim:latest` is scoped to
Isaac Sim, not a general PyTorch training stack. Reproducing the pinned
Windows env on Linux is possible in principle (same RTX 5070, GPU passthrough
already confirmed working via `docker run --gpus all`) but untested — not
worth doing just to avoid a reboot when the reboot itself costs nothing extra
now that the drive is shared.

## What to run on Windows

Prerequisite: confirm the existing `.venv-lerobot` environment still works
(`windows-gpu-training-setup.md` step 4 — `python -c "import torch;
print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"` should
print `True RTX 5070`). It was last used 2026-08-10 for the grasp-v1 run;
should still be intact.

Per AGENTS_NEW.md §19-21, train the **same policy architecture** on all
three datasets so the only variable between runs is the data itself:

| Dataset | Path | Episodes | Frames |
|---|---|---|---|
| A | `data/local/datasets/circle_grasp_v1_real10` | 10 real | 5,632 |
| B | `data/local/datasets/circle_grasp_v1_real50` | 50 real | 26,078 |
| C | `data/local/datasets/circle_grasp_v1_mixed_10r_100s` | 10 real + 100 synthetic | 61,952 |

All three: `robot_type=so_follower`, single task string `"Insert the circle
piece into its matching hole."`, `.mp4` video already (no re-encode needed).

**Flag before starting**: all three datasets have only
`observation.images.overview` — **no wrist camera**, unlike every prior
Windows training run (`circle_insert_50ep`, `circle_grasp_v1`, etc.), which
had both. This is a real difference in the Isaac replay/export pipeline
(`scripts/export_lerobot_dataset.py` only renders one camera), not a bug
introduced now — but confirm this is intentional before spending ~2h/run on
it. If a wrist view matters for this comparison, that's an Isaac-side fix
needed before training, not a Windows-side one.

### Smoke test each dataset first (10 steps, same pattern as every prior run)

```powershell
cd C:\projects\so-arm100-robot-controlle\so-arm100
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_grasp_v1_real10 `
  --dataset.root=data/local/datasets/circle_grasp_v1_real10 `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_grasp_v1_real10_smoke `
  --job_name=smolvla_grasp_v1_real10_smoke `
  --wandb.enable=false `
  --batch_size=32 `
  --steps=10 --save_freq=10 --log_freq=1 --eval_steps=5
```

Swap `repo_id`/`root`/`output_dir`/`job_name` for B and C. Watch for OOM at
batch 32 (drop to 24 if so, not straight to 8 — per `windows-gpu-training-run-grasp-v1.md`)
and note the printed s/step.

### Full runs (30,000 steps, identical settings across A/B/C)

```powershell
.venv-lerobot\Scripts\lerobot-train `
  --dataset.repo_id=local/circle_grasp_v1_real10 `
  --dataset.root=data/local/datasets/circle_grasp_v1_real10 `
  --dataset.video_backend=pyav `
  --dataset.eval_split=0.15 `
  --policy.path=lerobot/smolvla_base `
  --policy.push_to_hub=false `
  --policy.device=cuda `
  --policy.use_amp=false `
  --policy.input_features=null `
  --output_dir=outputs/train/smolvla_grasp_v1_real10_30000 `
  --job_name=smolvla_grasp_v1_real10_30000 `
  --wandb.enable=false `
  --batch_size=32 `
  --steps=30000 --eval_steps=500 --save_freq=5000 --log_freq=50 `
  2>&1 | Tee-Object -FilePath train-grasp-v1-real10.log
```

Repeat for B (`circle_grasp_v1_real50`) and C
(`circle_grasp_v1_mixed_10r_100s`), each with its own `--dataset.repo_id`,
`--dataset.root`, `--output_dir`/`--job_name`, and log file. `--eval_steps=500`
is not optional — its absence is why the 55-episode regression went
undetected until it was already on hardware (see `windows-gpu-training-run-grasp-v1.md`).

Dataset A is only 5,632 frames; running the full 30,000-step schedule on it
will pass over the data many more times than B or C. That's intentional for
this comparison (same architecture/steps, only the data differs, per
AGENTS_NEW.md §19) — don't shorten it to "avoid overfitting" without
checking with the project owner first, since a shorter schedule on A alone
would break the controlled comparison.

Expect roughly ~2h per run at the previously-measured ~5.3 steps/sec (more
for C given more frames per epoch, but step count — not epoch count — is
what's fixed here).

## After training: eval needs a new Docker image, confirmed

Every previous SmolVLA checkpoint was evaluated on real hardware from the
**Mac** (`robot_learning/loop.py eval`, `robot_learning/run_policy_prompt.py`).
The physical robot no longer lives there — it's on this Linux machine now
(see the arm-relocation handover docs). That means evaluation has to happen
here, not on the Mac as `windows-gpu-training-run-grasp-v1.md`'s "Evaluating
it back on the Mac" section describes.

**Tested 2026-08-11: `real-robot:latest` cannot run eval as-is, and it's not
a speed problem.**

- GPU passthrough itself is fine: `docker run --gpus all real-robot:latest`
  gives real CUDA access (`torch.cuda.is_available()` → `True`, RTX 5070,
  12.3GB VRAM).
- But the image is Python 3.10 with `lerobot==0.4.1`/`transformers==4.51.3`.
  Loading `outputs/train/smolvla_circle_grasp_v1_20000/checkpoints/020000/pretrained_model`
  (trained under the Windows pins, `lerobot==0.6.1`) fails immediately:
  `SmolVLAConfig` rejects fields the newer lerobot writes
  (`use_peft`, `pretrained_revision`, `rtc_config`, `compile_model`,
  `compile_mode`).
- Tried the obvious fix — `pip install lerobot==0.6.1` inside the container —
  and it fails outright: that version requires Python >=3.12, which this
  image doesn't have. Not a `pip install --upgrade` fix; needs a different
  base image.

**Before running eval on Linux**, build a new Docker image: Python >=3.12,
`lerobot[smolvla]==0.6.1`, `transformers==5.5.4`, CUDA-enabled torch (same
pins as `windows-gpu-training-setup.md`), plus the hardware bits
`real-robot:latest` already has — pyserial, the Feetech SDK, OpenCV, and
device passthrough for `/dev/ttyACM0`/`/dev/ttyACM1`/cameras. Then
`robot_learning/loop.py eval --checkpoint <path>` should work the same way
it did on the Mac. This is unstarted — nothing eval-capable exists on Linux
yet.

## Results (fill in after each run)

| Dataset | Final loss | Steps/sec | Wall time | Real-hardware success rate |
|---|---|---|---|---|
| A (10 real) | | | | |
| B (50 real) | | | | |
| C (10 real + 100 synthetic) | | | | |

This table is the actual answer to the project's primary research question
(AGENTS_NEW.md §32) once filled in.
