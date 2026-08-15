#!/bin/bash
# Check the sim scene against a real frame before generating any data.
# See src/bridge/scene_gate.py for why this is a gate and not a suggestion.
set -e
cd "$(dirname "$0")"
exec ./sim_docker.sh scripts/check_scene_gate.py "$@"
