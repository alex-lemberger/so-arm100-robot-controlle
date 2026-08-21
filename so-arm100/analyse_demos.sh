#!/bin/bash
# What is in the demonstrations, by BEHAVIOUR rather than by episode count
# (scripts/analyse_demo_composition.py). Needs no GPU and no Isaac -- same image
# and mounts as run_tests.sh.
#
#   ./analyse_demos.sh                    # every dataset under data/
#   ./analyse_demos.sh circle_grasp_v1
set -e
cd "$(dirname "$0")"
exec docker run --rm -i -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest python3 scripts/analyse_demo_composition.py "$@"
