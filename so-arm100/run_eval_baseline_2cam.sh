#!/bin/bash
# R0 control eval -- see docs/replan-2026-08-14-camera-confound.md
#
# Re-evaluates the ONLY checkpoint that ever scored non-zero on this task
# (3/10, trained on circle_insert_50ep with overview+wrist) on the current
# Linux hardware. Every result since the machine move has been ambiguous
# because there is no known-good reference on this machine: if this scores
# ~3/10 the harness and hardware are sound and the single-camera datasets
# are the problem; if it scores 0/10 the fault is in the eval path or the
# hardware and rebuilding datasets would be wasted effort.
#
# 10 episodes, not 20, so the number is directly comparable to the
# historical 3/10.
set -e
cd "$(dirname "$0")"
./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_circle_insert_50ep_30000/checkpoints/030000/pretrained_model \
  --episodes 10 \
  --tag baseline_2cam_r0
