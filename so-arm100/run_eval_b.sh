#!/bin/bash
set -e
cd "$(dirname "$0")"
./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_grasp_v1_real50_30000/checkpoints/030000/pretrained_model \
  --episodes 20 \
  --tag run_b
