#!/bin/bash
# Canonical docker invocation for GPU work that must NOT touch the robot:
# offline policy inference, held-out evaluation, dataset analysis, training.
# The third sibling of hw_docker.sh (hardware) and sim_docker.sh (Isaac):
# that one owns the device flags, this one deliberately has none, so nothing
# run through here can open a serial port or a camera while the bench is live.
#
#   ./gpu_docker.sh python robot_learning/eval_smolvla_held_out.py --checkpoint ...
#   ./gpu_docker.sh python robot_learning/diagnose_policy_chunk.py --observation ...
#
# The calibration directory is mounted READ-ONLY: dataset builders convert raw
# ticks with the same file the robot uses, so it has to be the live one rather
# than a copy that can drift -- but nothing run here may rewrite it (see the
# 2026-08-14 silent-recalibration incident in docs/RUNBOOK.md).
set -e
cd "$(dirname "$0")"
TTY_FLAGS="-i"
[ -t 0 ] && TTY_FLAGS="-it"
exec docker run --rm --gpus all --ipc=host $TTY_FLAGS \
  -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration:ro" \
  -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest \
  "$@"
