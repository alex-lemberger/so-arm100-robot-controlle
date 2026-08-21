#!/bin/bash
# Canonical docker invocation for anything that boots Isaac Sim (scene gate,
# replay validation, synthetic generation, the tests/smoke_*_isaac.py files).
# The sibling of hw_docker.sh: that one is the single source of truth for the
# hardware flags, this one for the sim flags. Never hand-write this line --
# the /Users mount below is easy to forget and its absence shows up as an
# unrelated-looking `is_homogeneous` assertion deep inside articulation
# initialization, because the robot USD lives under it.
#
#   ./sim_docker.sh tests/smoke_lighting_isaac.py
#   ./sim_docker.sh scripts/replay_episode.py --episode 0 ...
set -e
cd "$(dirname "$0")"
exec docker run --rm --gpus all \
  -v "$(pwd)/..:$(pwd)/.." \
  -v /media/alex/F6E48479E4843DBD/Users:/media/alex/F6E48479E4843DBD/Users:ro \
  -w "$(pwd)" \
  leisaac-sim:latest \
  /workspace/isaaclab/_isaac_sim/python.sh "$@"
