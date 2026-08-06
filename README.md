# Robotics monorepo

Five self-contained projects, each in its own top-level folder with its own
build tooling. None of them share code or dependencies with each other.

## SO-ARM100 hardware control

- **`so-arm100/`** — React/Vite/TS teleoperation UI and Python training
  scripts for the physical SO-ARM100 arm: joint control, kinematics, dataset
  recording, and SmolVLA/ACT policy fine-tuning. See `so-arm100/AGENTS.md`
  for setup, hardware state, and current dataset/checkpoint status.

## Human-task capture / imitation learning

These four form one family: a consent-based pipeline for capturing human
task demonstrations and training imitation-learning policies from them,
independent of the SO-ARM100 hardware above.

- **`htdp/`** — `human-task-dataset-pipeline`: the core `htdp` CLI (ingest,
  validate, process, QC, package, export, replay) plus a from-scratch
  MuJoCo + LeRobot + ACT visuomotor imitation-learning research loop on a
  Franka Panda. See `htdp/STATUS.md` and `htdp/README.md`.
- **`htdp-capture/`** — hardware capture companion to `htdp`: VIVE tracker
  poses (OpenVR) and EEG streams over LSL, written out as `.xdf` for
  `htdp ingest`. See `htdp-capture/README.md`.
- **`handwerk-robot-sim/`** — a MuJoCo cobot simulation (UR5e troweling
  demo), a stand-in for the future cobot that would consume `htdp` releases
  of captured Handwerk (craft) skill data. See `handwerk-robot-sim/README.md`.
- **`neurofeedback-lang-app/`** — the original Angular control-center app
  that `htdp` was spun off from on 2026-06-20; still cross-linked as a
  companion dashboard.

## Working in this repo

Each project folder is independently installable and runnable — `cd` into
it and follow that project's own README. There is no root-level build step
that spans all five.
