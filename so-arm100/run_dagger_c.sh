#!/bin/bash
set -e
cd "$(dirname "$0")"
./hw_docker.sh python robot_learning/loop.py dagger \
  --checkpoint outputs/train/smolvla_grasp_v1_mixed_10r_100s_30000/checkpoints/030000/pretrained_model \
  --episodes 10 \
  --tag transport
