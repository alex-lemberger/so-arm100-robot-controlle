#!/bin/bash
# Put the arm in the start pose the demonstrations used, and report what the wrist
# camera sees (robot_learning/home_arm.py). Run before an eval.
#
#   ./home_arm.sh                # move there and check
#   ./home_arm.sh --check-only   # just look
set -e
cd "$(dirname "$0")"
exec ./hw_docker.sh python robot_learning/home_arm.py "$@"
