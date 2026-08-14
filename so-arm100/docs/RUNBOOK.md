# SO-ARM100 Runbook — current state

This is the single canonical "what's true right now" doc. Unlike the dated
`docs/linux-session-handover-*.md` / `docs/handover-*.md` files (which are
point-in-time session logs, kept for history), **this file gets edited in
place** whenever a fact here goes stale. If you find something wrong here,
fix it here directly rather than writing a new dated doc.

`AGENTS.md`'s "Verified hardware setup" section predates the machine move
described below and still lists Mac ports/paths — treat this file as the
override for anything hardware-related.

Last verified: 2026-08-14.

## Machine

This Linux workstation is physically colocated with the robot (moved here
2026-08-11) and is also, via dual-boot on the same NVMe drive, the Windows
GPU training box — `data/local/datasets/` and `outputs/train/` need zero
copying between the two. There is no native Python environment on this
machine; everything runs through Docker.

## Docker images

- **`lerobot-train:latest`** (built from `Dockerfile.lerobot`) — Python 3.12,
  lerobot 0.6.1, CUDA. Use this for everything real-hardware or
  checkpoint-related: eval, dagger, record, merge, build, train.
- `real-robot:latest` — older, Python 3.10, lerobot 0.4.1. **Cannot load
  checkpoints trained with lerobot 0.6.1** (config/field mismatches). Don't
  use it for anything that touches a trained checkpoint.
- `leisaac-sim:latest` — Isaac Sim only (replay validation, synthetic data
  generation). Unrelated to real-hardware eval.

## Hardware

- Follower arm: id `white`, port `/dev/ttyACM1`.
- Leader arm: id `black_20260801`, port `/dev/ttyACM0`.
- **Ports are NOT stable across reboots/replugs.** Run `./verify_ports.sh`
  every session before trusting the mapping above or the `CONFIG` dict in
  `robot_learning/loop.py` — don't assume a past session's mapping still
  holds just because nothing was consciously unplugged.
- Cameras: overview=`/dev/video0`, wrist=`/dev/video2`. Both need
  `"fourcc": "MJPG"` in the camera config or they cap out at 10fps instead
  of the requested 30fps (USB bandwidth limit of uncompressed YUYV).
- **Calibration files live on the HOST**, not in this repo:
  `~/.cache/huggingface/lerobot/calibration/{robots/so100_follower,teleoperators/so100_leader}/*.json`.

## Running anything that touches the real robot

**Always go through `./hw_docker.sh <command>` — never hand-write a
`docker run` line for hardware.** It is the single place the device/mount
flags live. If a port remaps or a flag needs to change, fix it there once;
every script that calls it picks up the fix automatically.

```bash
./hw_docker.sh python robot_learning/loop.py eval --checkpoint <path> --episodes 20 --tag <tag>
./hw_docker.sh python robot_learning/loop.py dagger --checkpoint <path> --episodes 10 --tag <tag>
```

Existing wrapped scripts (all just call `hw_docker.sh` with fixed args):
`run_eval_a.sh`, `run_eval_b.sh`, `run_eval_c.sh`, `run_eval_020000.sh`,
`run_dagger_c.sh`. Copy one of these for a new eval rather than writing a
fresh `docker run` — that's exactly how the calibration mount got dropped
on 2026-08-14 (an ad-hoc command omitted it, causing a silent full
recalibration and an invalid eval result).

## Datasets and cameras

**Every policy that has ever worked on this task used TWO cameras
(`observation.images.overview` + `observation.images.wrist`).** The only
checkpoint with a nonzero hardware success rate
(`smolvla_circle_insert_50ep_30000`, 3/10) is two-camera.

Datasets A/B/C (`circle_grasp_v1_real10`, `circle_grasp_v1_real50`,
`circle_grasp_v1_mixed_10r_100s`) and `grasp_v1_dagger1` are
**overview-only** — `scripts/export_lerobot_dataset.py` drops the wrist
camera by design (it can't render a wrist view for synthetic episodes). All
four scored 0/20 or degenerate on hardware. Treat any result from these four
datasets as confounded; see `docs/replan-2026-08-14-camera-confound.md`.

The *source* datasets (`data/circle_grasp_v1`, `data/circle_insert_50ep`)
still have both cameras — nothing was lost, the exports just need redoing.

## Training

- `--base <checkpoint> --steps N` for "resuming" a run does **not**
  reconfigure the LR scheduler's decay target — it stays at whatever the
  original run's total steps was. A short resume run's LR may never decay
  properly as a result. Prefer a single continuous run sized for the real
  total step count; only use `--base` resume when you've confirmed the
  schedule mismatch doesn't matter for what you're testing.
- `--ipc=host` is required on `docker run` for any multi-worker training
  job through `lerobot-train:latest`, or the DataLoader crashes on a shared
  memory limit.

## Known recurring gotchas

- Reusing a `--tag` from a previous attempt (even a failed/Ctrl-C'd one)
  hits `FileExistsError` — always use a fresh tag.
- An interrupted rollout leaves a valid `.mp4` but a broken dataset
  manifest — `robot_learning/extract_one_frame.py` still works on the raw
  video for diagnosis even when the dataset itself won't load.
- `RuntimeError: ... Overload error!` on `Torque_Enable` has more than one
  known cause: a follower/leader port swap (check with `verify_ports.sh`
  first), or — as of 2026-08-14 — an unexplained case with ports confirmed
  correct and no mechanical jam, still under investigation. Don't assume
  it's the port-swap without checking.

## Full history

Point-in-time session detail (exact commands, what broke, what was tried)
lives in the dated `docs/linux-session-handover-*.md` and
`docs/handover-*.md` files. Read the most recent one for narrative context
on how the project got here — but treat this file, not those, as the
source of truth for what's currently correct.
