#!/bin/bash
# Is the board back where the training demos had it? See
# docs/replan-2026-08-14-camera-confound.md and robot_learning/align_board.py.
set -e
cd "$(dirname "$0")"
./hw_docker.sh python robot_learning/align_board.py "$@"
