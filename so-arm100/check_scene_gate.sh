#!/bin/bash
# Check the sim scene against a real frame before generating any data.
# See src/bridge/scene_gate.py for why this is a gate and not a suggestion.
set -e
cd "$(dirname "$0")"
exec docker run --rm --gpus all \
  -v "$(pwd)/..:$(pwd)/.." \
  -v /media/alex/F6E48479E4843DBD/Users:/media/alex/F6E48479E4843DBD/Users:ro \
  -w "$(pwd)" \
  leisaac-sim:latest \
  /workspace/isaaclab/_isaac_sim/python.sh scripts/check_scene_gate.py "$@"
