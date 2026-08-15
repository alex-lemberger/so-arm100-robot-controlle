#!/bin/bash
# Canonical way to run the pure-Python test suite. There is no native Python env on
# this machine (no numpy, no torch outside the images -- see docs/RUNBOOK.md), so the
# tests only ever run in a container. This is the non-hardware counterpart to
# hw_docker.sh: no --device, no calibration mount, nothing that needs the robot.
#
#   ./run_tests.sh                 # every tests/test_*.py
#   ./run_tests.sh test_scene_gate # just the ones whose name matches
#
# tests/smoke_*_isaac.py are NOT run here -- they need leisaac-sim:latest and a
# display. See docs/RUNBOOK.md.
set -e
cd "$(dirname "$0")"

PATTERN="${1:-}"
mapfile -t TESTS < <(ls tests/test_*.py | { [ -n "$PATTERN" ] && grep -- "$PATTERN" || cat; })
if [ ${#TESTS[@]} -eq 0 ]; then
  echo "No tests matched '${PATTERN}'" >&2
  exit 1
fi

run() {
  docker run --rm -i -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" lerobot-train:latest "$@"
}

FAILED=()
for t in "${TESTS[@]}"; do
  echo "=============================================================="
  echo "$t"
  echo "=============================================================="
  run python3 "$t" || FAILED+=("$t")
done

echo
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "ALL SUITES PASS (${#TESTS[@]})"
else
  echo "FAILED SUITES: ${FAILED[*]}"
  exit 1
fi
