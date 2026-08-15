#!/bin/bash
# Confirms which /dev/ttyACM* node is the follower vs the leader.
#
# Port assignment is NOT stable across reboots/replugs, but the USB serial of
# each arm's adapter is. The serials are known from the Mac-era device names
# (macOS embeds the serial in the node name) recorded in loop.py's CONFIG:
#   /dev/cu.usbmodem5AE60582701 = follower "white"
#   /dev/cu.usbmodem5B140329561 = leader   "black_20260801"
# So the mapping can be resolved by reading serials -- no unplug test, no human.
# Cross-checked 2026-08-12 against the unplug test and 2026-08-15 after a
# re-enumeration; both agreed.
set -e
cd "$(dirname "$0")"

FOLLOWER_SERIAL=5AE6058270
LEADER_SERIAL=5B14032956

declare -A found
for dev in /dev/ttyACM*; do
    [ -e "$dev" ] || continue
    serial=$(udevadm info -q property -n "$dev" 2>/dev/null \
             | sed -n 's/^ID_SERIAL_SHORT=//p')
    [ -n "$serial" ] && found[$serial]=$dev
done

follower=${found[$FOLLOWER_SERIAL]}
leader=${found[$LEADER_SERIAL]}

echo "Detected by USB serial:"
echo "  follower white          ($FOLLOWER_SERIAL): ${follower:-NOT FOUND}"
echo "  leader   black_20260801 ($LEADER_SERIAL): ${leader:-NOT FOUND}"
echo
echo "robot_learning/loop.py CONFIG says:"
cfg_follower=$(sed -n 's/.*"follower": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)
cfg_leader=$(sed -n 's/.*"leader": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)
echo "  follower: $cfg_follower"
echo "  leader:   $cfg_leader"
echo

rc=0
if [ -z "$follower" ] || [ -z "$leader" ]; then
    echo "FAIL: an arm is not plugged in (or its adapter has an unexpected serial)."
    rc=1
elif [ "$follower" != "$cfg_follower" ] || [ "$leader" != "$cfg_leader" ]; then
    echo "MISMATCH: fix CONFIG in robot_learning/loop.py before running anything"
    echo "that touches the robot -- driving the leader through the follower's"
    echo "config is how the 2026-08-12 Overload error happened."
    rc=1
else
    echo "OK: ports match CONFIG."
fi
exit $rc
