#!/bin/bash
set -e
cd "$(dirname "$0")"
./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_grasp_v1_dagger1_30000/checkpoints/020000/pretrained_model \
  --episodes 5 \
  --tag ckpt_020000_test2
