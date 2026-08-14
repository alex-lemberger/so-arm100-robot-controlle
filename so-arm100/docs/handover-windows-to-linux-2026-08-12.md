# Handover: Windows → Linux, §19-21 training comparison complete (2026-08-12)

## What was done on Windows

All three policy training runs from AGENTS_NEW.md §19-21 are complete. Same
architecture (SmolVLA base, 30,000 steps, batch 32, `--policy.use_amp=false`,
`--policy.input_features=null`), only the training data differed:

| Dataset | Path | Episodes | Frames | Final loss | Eval loss | Wall time |
|---|---|---|---|---|---|---|
| A — 10 real | `outputs/train/smolvla_grasp_v1_real10_30000` | 10 | 5,632 | 0.009 | **1.296** | ~3h |
| B — 50 real | `outputs/train/smolvla_grasp_v1_real50_30000` | 50 | 26,078 | 0.025 | **0.818** | ~5h 40m |
| C — 10r + 100s | `outputs/train/smolvla_grasp_v1_mixed_10r_100s_30000` | 110 | 61,952 | 0.015 | **0.016** | ~2h* |

*C was interrupted at step 20,000 by a prior session and resumed from
`checkpoints/020000` in this session. Total step count is still 30,000 from scratch.

All runs completed cleanly (exit 0). Each has 6 checkpoints at 5,000-step intervals
(005000, 010000, ..., 030000). The `checkpoints/last` symlink is NOT written on
Windows (no Developer Mode) — reference checkpoints by number explicitly.

## The headline finding before hardware eval

**Run A is severely overfit.** 5,632 frames at 30,000 steps means ~209 epochs over
the same data. Training loss hit 0.009 but eval loss is 1.296 — the model memorized
the training set and cannot generalize. Expect poor real-hardware performance.

**Run C's eval loss (0.016) nearly matches its training loss (0.015).** That gap is
tight enough to suggest the 100 synthetic episodes act as strong regularization,
preventing memorization. C is the candidate to beat on hardware.

**Run B sits in between** — lower eval loss than A (0.818) but still a large
train/eval gap, consistent with "more data helps but not enough on its own."

These observations are predictions. Hardware eval is the ground truth.

## No data transfer needed

This Linux machine and the Windows training box are the same physical machine
dual-booted off the same NVMe. The checkpoint directories under
`so-arm100/outputs/train/` are already here — no copying needed in either direction.
Same applies to the three datasets under `data/local/datasets/`.

## Also done on Windows: Dockerfile for the new training image

`so-arm100/Dockerfile.lerobot` was written this session. It builds a single image
that covers both training and real-hardware eval on Linux — replacing the split
between `real-robot:latest` (hardware only, Python 3.10) and nothing (no
lerobot 0.6.1 image existed on Linux at all):

- Base: `nvidia/cuda:12.8.1-cudnn9-runtime-ubuntu22.04`
- Python 3.12 via deadsnakes PPA (lerobot 0.6.1 rejects Python <3.12 at install)
- `torch==2.11.0 torchvision==0.26.0` from `--index-url https://download.pytorch.org/whl/cu128` — installed before lerobot to prevent the solver pulling a CPU-only build
- `lerobot[smolvla,dataset]==0.6.1` + `transformers==5.5.4` re-pinned
- `pyserial`, `scservo_sdk`, `opencv-python-headless` for real-robot eval

PyAV (used by `--dataset.video_backend=pyav`) bundles its own ffmpeg in the
wheel — no system ffmpeg needed. `opencv-python-headless` supports camera
capture without a display server.

## What to do next on Linux: real-hardware eval

The physical SO-ARM100 (follower `/dev/ttyACM0`, leader `/dev/ttyACM1`,
overview `/dev/video0`, wrist `/dev/video2`) is on this machine and was confirmed
working 2026-08-11 (`linux-hardware-setup-2026-08-11.md`). Hardware setup is done.

**Blocker: `real-robot:latest` cannot load these checkpoints.** It is Python 3.10 +
lerobot 0.4.1; the checkpoints were written by lerobot 0.6.1 which adds fields
(`use_peft`, `pretrained_revision`, `rtc_config`, etc.) that the older
`SmolVLAConfig` rejects immediately. This was already diagnosed and documented in
`handover-linux-to-windows-2026-08-11.md`.

**The fix is a new Docker image.** `so-arm100/Dockerfile.lerobot` (written
2026-08-12) builds a lerobot 0.6.1 + Python 3.12 + CUDA image that also includes
the hardware stack (pyserial, scservo_sdk, opencv-python-headless). Build it first:

```bash
cd /media/alex/F6E48479E4843DBD/projects/so-arm100-robot-controlle/so-arm100
docker build -f Dockerfile.lerobot -t lerobot-train:latest .
```

Expected build time: 10-20 minutes (torch wheel alone is ~2 GB). CUDA passthrough
is already confirmed working on this machine (`docker run --gpus all` → RTX 5070).

### Run eval for each checkpoint

Use the 030000 checkpoint for each run (the fully converged model). Same pattern as
the Mac eval sessions, using `robot_learning/loop.py eval`:

```bash
docker run --rm --gpus all -it \
  --device=/dev/ttyACM0 --device=/dev/ttyACM1 \
  --device=/dev/video0 --device=/dev/video2 \
  -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
  -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest \
  python robot_learning/loop.py eval \
    --checkpoint outputs/train/smolvla_grasp_v1_real10_30000/checkpoints/030000/pretrained_model \
    --episodes 10
```

Swap `--checkpoint` for B and C. Run from `so-arm100/`. Port/camera indices are
confirmed for this machine (`linux-hardware-setup-2026-08-11.md`):
follower=`/dev/ttyACM0`, leader=`/dev/ttyACM1`, overview=`/dev/video0`,
wrist=`/dev/video2`.

**Run A first** — if eval loss predicts anything, A should fail visibly and quickly,
which confirms the eval setup is working before spending time on B and C.

### Record the success rates here

| Dataset | Checkpoint | Episodes tested | Success rate |
|---|---|---|---|
| A — 10 real | 030000 | 20 | **0/20** |
| B — 50 real | 030000 | 20 | **0/20** |
| C — 10r + 100s | 030000 | 20 | **0/20** |

This table is the answer to AGENTS_NEW.md §32.

### Scoring method: video review, not just live eye-scoring

Success is defined as the circle piece ending up fully inserted in its matching
hole (not just grasped) — see AGENTS_NEW.md §20's failure taxonomy, which treats
"grasp failure" and "placement failure" as distinct sub-failures of the same
pick→place task. `robot_learning/extract_eval_frames.py` (new this session) pulls
the last frame of each episode from the rollout dataset's own recorded video
(`data/local/datasets/rollout_<tag>/videos/...`) via PyAV, so success can be
verified from footage instead of relying purely on the observer's live call
mid-run. Run inside the `lerobot-train` container:

```bash
docker run --rm -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
  -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" lerobot-train:latest \
  python3 robot_learning/extract_eval_frames.py --dataset rollout_run_a --camera overview
```

Frames land in `outputs/eval-frames/<dataset>/<camera>/epNN.png`.

**A qualitative finding from the video, not visible in the 0/20 score alone:**
Run A (real10, severely overfit) never engaged with the piece at all in the one
episode inspected mid-run. Run B (real50) is different — mid-episode frames (e.g.
episode 0 at t≈15-22s) show the policy successfully reaching, grasping, and
lifting the piece off the table, but it never transports the piece toward the
puzzle board; it sets the piece back down near its start position instead of
attempting insertion. So B's 0/20 reflects a placement failure on top of a working
grasp, not a total non-mover — consistent with its mid-tier eval loss (0.818)
sitting between A's (1.296) and C's (0.016).

**C (10r+100s, the lowest eval loss and predicted best) also scored 0/20**, and
episode 0's mid-episode frame (t≈15s) shows the exact same pattern as B: grasps
the piece successfully, then never transports it toward the board. So the
train/eval loss gap (which predicted C would generalize best) did NOT translate
into hardware success — all three checkpoints share the same qualitative failure
mode (reach+grasp works, transport+insert doesn't), regardless of eval loss.
This is itself a finding: held-out loss on this task doesn't seem to be
measuring the compound skill that matters on hardware, likely because the
transport+insert phase is a small fraction of training frames relative to
reach+grasp (mirrors the ~5% figure `loop.py --grasp-only` cites for why the
grasp phase specifically needed isolating). Next step worth considering: a
policy trained explicitly on the transport+insert phase, or more demonstrations
weighted toward that phase, rather than more total episodes of the same
skew.
