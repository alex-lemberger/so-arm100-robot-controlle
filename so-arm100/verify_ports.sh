#!/bin/bash
# Confirms which /dev/ttyACM* node is the follower vs the leader.
# Port assignment is NOT stable across reboots/replugs -- re-run this every
# session before trusting robot_learning/loop.py's CONFIG, don't assume last
# session's mapping still holds.
set -e
cd "$(dirname "$0")"
echo "Current ports:"
ls /dev/ttyACM* 2>/dev/null
echo
read -p "Unplug the FOLLOWER arm's USB cable now, then press ENTER..." _
echo "Ports after unplugging the follower:"
ls /dev/ttyACM* 2>/dev/null
echo
echo "Whichever node from the first list is now MISSING is the follower."
echo "Plug it back in, then compare against CONFIG in robot_learning/loop.py:"
echo
grep -A1 '"follower":\|"leader":' robot_learning/loop.py
