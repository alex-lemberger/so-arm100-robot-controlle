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
#
# RUN ./check_alignment.sh FIRST. The 2026-08-14 attempt scored 0/10 with the
# board ~19mm out of place, which is fatal for seating and nearly harmless for
# grasp and transport -- exactly the pattern observed. A tag is required
# because reusing one hits FileExistsError.
#
#   ./run_eval_baseline_2cam.sh baseline_2cam_r1
set -e
cd "$(dirname "$0")"

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "usage: $0 <tag>    (e.g. baseline_2cam_r1 -- must not already exist)" >&2
  exit 2
fi
if [ -e "data/local/datasets/rollout_${TAG}" ]; then
  echo "data/local/datasets/rollout_${TAG} already exists -- pick a fresh tag." >&2
  exit 2
fi

echo "Reminder: ./check_alignment.sh should read ALIGNED before this is worth running."
./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_circle_insert_50ep_30000/checkpoints/030000/pretrained_model \
  --episodes 10 \
  --tag "$TAG"
