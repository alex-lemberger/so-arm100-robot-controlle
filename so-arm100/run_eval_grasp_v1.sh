#!/bin/bash
# Eval the never-evaluated grasp-coverage checkpoint.
#
# `smolvla_circle_grasp_v1_20000/checkpoints/020000` was the 5th training run
# and was built to fix precisely the failure R0 still shows: the arm reaches
# the disc and loses it at or just after closing the gripper
# (docs/windows-gpu-training-run-grasp-v1.md). Its dataset `circle_grasp_v1`
# is 81 episodes / 31,541 frames -- the 50 insert episodes plus 31 grasp-only
# takes, about 5x the grasp-phase coverage of the trimmed run -- and it carries
# two task strings instead of one.
#
# It has TWO cameras (verified: input_features = state + overview + wrist), so
# it is not affected by the single-camera confound that invalidated datasets
# A/B/C (docs/replan-2026-08-14-camera-confound.md).
#
# It has never been run on hardware. docs/linux-session-handover-2026-08-10.md:
# "Checkpoint has not been evaluated on hardware yet. That evaluation happens
# on the Mac (not Linux)." The PC moved to the robot the next day, Linux had no
# eval-capable image until Dockerfile.lerobot existed, and the Isaac/camera
# work took the sessions after that. It was never picked back up.
#
# Verified 2026-08-15: loads clean, 450.0M params, both cameras.
#
# 10 episodes, matching R0, so the numbers are directly comparable:
#   R0 (trimmed_20000): 0/10 overall, grasp 2/10.
#
# Run ./check_alignment.sh and ./verify_ports.sh first.
#
#   ./run_eval_grasp_v1.sh grasp_v1_r1
set -e
cd "$(dirname "$0")"

TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "usage: $0 <tag>    (e.g. grasp_v1_r1 -- must not already exist)" >&2
  exit 2
fi
if [ -e "data/local/datasets/rollout_${TAG}" ]; then
  echo "data/local/datasets/rollout_${TAG} already exists -- pick a fresh tag." >&2
  exit 2
fi

./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_circle_grasp_v1_20000/checkpoints/020000/pretrained_model \
  --episodes 10 \
  --tag "$TAG"
