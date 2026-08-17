#!/bin/bash
# Plain teleoperation, no recording -- drive the follower from the leader.
#
# Purpose (2026-08-15): after R0 scored 0/10 with grasp succeeding only 2/10,
# this is the 5-minute test that separates "the policy is weak at grasp" from
# "this gripper/rail can no longer grasp reliably". Grasp the peg by hand ~5
# times. Reliable by hand => hardware is cleared and the problem is the policy
# or the train/eval appearance gap; fiddly by hand => hardware moves to the top
# of the list before any re-recording.
#
# Ports/ids/cameras come from loop.py CONFIG (run ./verify_ports.sh first).
# No cameras are passed: this is a mechanical check and skipping them keeps
# startup fast and avoids the fps/fourcc path entirely.
set -e
cd "$(dirname "$0")"

# Ports are READ from loop.py CONFIG, not repeated here.
#
# The header above always claimed they came from CONFIG, but they were duplicated as
# literals -- so when the ttyACM assignment flipped on 2026-08-17 (the third flip in
# six days) this script still named the old mapping. Running it would have driven the
# LEADER through the follower's config, which is exactly the mistake behind the
# 2026-08-12 Overload error. One source of truth, or the copy goes stale in silence.
FOLLOWER_PORT=$(sed -n 's/.*"follower": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)
LEADER_PORT=$(sed -n 's/.*"leader": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)
if [ -z "$FOLLOWER_PORT" ] || [ -z "$LEADER_PORT" ]; then
  echo "Could not read follower/leader ports from robot_learning/loop.py CONFIG." >&2
  exit 1
fi
echo "follower $FOLLOWER_PORT   leader $LEADER_PORT   (read from loop.py CONFIG)"
echo "If that looks wrong, run ./verify_ports.sh -- do not edit this script."

exec ./hw_docker.sh lerobot-teleoperate \
  --robot.type=so100_follower \
  --robot.port="$FOLLOWER_PORT" \
  --robot.id=white \
  --teleop.type=so100_leader \
  --teleop.port="$LEADER_PORT" \
  --teleop.id=black_20260801
