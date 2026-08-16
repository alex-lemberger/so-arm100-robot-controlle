#!/bin/bash
# Success as a function of where the object was
# (scripts/analyse_placement_generalization.py). No GPU, no Isaac.
#
#   ./analyse_placement.sh rollout_grasp_v1_r1 rollout_grasp_v1_r2
#   ./analyse_placement.sh --demos circle_grasp_v1
set -e
cd "$(dirname "$0")"
exec docker run --rm -i -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest python3 scripts/analyse_placement_generalization.py "$@"
