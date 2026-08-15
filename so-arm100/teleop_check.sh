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
exec ./hw_docker.sh lerobot-teleoperate \
  --robot.type=so100_follower \
  --robot.port=/dev/ttyACM1 \
  --robot.id=white \
  --teleop.type=so100_leader \
  --teleop.port=/dev/ttyACM0 \
  --teleop.id=black_20260801
