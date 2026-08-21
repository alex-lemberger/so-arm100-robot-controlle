#!/bin/bash
# One supervised policy rollout trial: home to the demonstrations' start pose,
# then run the closed-loop policy and leave the artifact under a fresh tag.
# Centralised so a sweep of checkpoints is one loop and not N hand-written
# hw_docker.sh lines (see docs/RUNBOOK.md, "Running a policy closed-loop").
#
#   ./run_rollout_trial.sh <tag> <checkpoint-dir> [extra args...]
#   ./run_rollout_trial.sh --force-framing <tag> <ckpt>   # roll out anyway
set -e
cd "$(dirname "$0")"
FORCE_FRAMING=0
if [ "$1" = "--force-framing" ]; then FORCE_FRAMING=1; shift; fi
TAG="$1"; CKPT="$2"; shift 2
OUT="outputs/hardware-test/$TAG"
if [ -e "$OUT" ]; then echo "refusing to reuse tag $TAG ($OUT exists)"; exit 1; fi
echo "=== $TAG :: $CKPT"
# Keep homing quiet on success, but show why it failed -- a bare "homing FAILED"
# with the output discarded tells you nothing, and the first connect after
# preflight releases the port can fail transiently and succeed on a retry.
HOME_LOG=$(mktemp)
if ! ./home_arm.sh >"$HOME_LOG" 2>&1; then
  echo "homing FAILED -- output follows; a first-connect failure often passes on a retry"
  tail -30 "$HOME_LOG"
  rm -f "$HOME_LOG"
  exit 1
fi

# home_arm.py judges the peg's wrist framing against the demos and returns 0
# either way. Surface that verdict and make it binding: on 2026-08-21 bench3
# started at wrist x=0.66 (+2.3 sd, board out of frame), the arm reached a
# perfectly in-distribution JOINT posture, and the policy then hovered for 8
# chunks and never closed the gripper. The warning had been printed into
# /dev/null. Framing is the precision-critical input -- see the 2026-08-16
# measurement in robot_learning/home_arm.py.
grep -E "peg in the wrist view|inside the demos|outside the demos|FRAME EDGE" "$HOME_LOG" || true
if grep -qE "outside the demos' usual framing|AT THE FRAME EDGE" "$HOME_LOG"; then
  if [ "$FORCE_FRAMING" = "1" ]; then
    echo "framing is out of distribution -- continuing anyway (--force-framing)"
  else
    echo "REFUSING to roll out: the peg is outside the demos' framing, so the wrist"
    echo "view is out of distribution before the policy has done anything."
    echo "Reposition the piece (and keep the board in the wrist view), or pass"
    echo "--force-framing to run it deliberately as an out-of-distribution probe."
    rm -f "$HOME_LOG"
    exit 2
  fi
fi
rm -f "$HOME_LOG"
./hw_docker.sh python robot_learning/supervised_policy_rollout.py \
  --checkpoint "$CKPT" \
  --prompt "Pick up the circle piece and place it in its matching pocket." \
  --output-dir "$OUT" --confirm-motion "$@" 2>&1 \
  | grep -E "Completed supervised policy chunk|STOPPED|Disconnected"
