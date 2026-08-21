#!/bin/bash
# Establish the primary invariants before anyone debugs anything. Read-only.
#
# Why this exists (2026-08-17)
# ----------------------------
# Five hours went into re-establishing a setup that had been working, and every wrong
# turn had the same shape: a theory about a secondary layer -- packet echo, DTR/RTS,
# stale port handles, USB resets -- built on primary state that was unverified or
# quietly drifting. The primary state is small and completely checkable:
#
#   1. WHO OWNS THE PORTS.  A container held /dev/ttyACM0 for eight minutes while a
#      host /proc scan said "ports free", because container processes were not in that
#      scan. Chrome then failed to open the port and the failure was blamed on Chrome.
#      This checks containers AND host processes, and names the holder.
#   2. WHICH NODE IS WHICH ARM.  ttyACM numbering follows plug order and flipped three
#      times in six days. Resolved by USB adapter serial, which is stable, and compared
#      against loop.py CONFIG.
#   3. WHAT IS ACTUALLY IN THE SERVOS.  Calibration registers read twice and compared
#      against the calibration file, per servo. A `c` answered at lerobot's calibration
#      prompt silently rewrote these once already.
#   4. WHETHER THE MEASUREMENT ITSELF IS REPRODUCIBLE.  scripts/preflight_bus.py reads
#      every value twice and reports UNSTABLE rather than picking one. An earlier
#      non-deterministic read returned a plausible wrong number that was trusted as
#      ground truth for an hour.
#
# Nothing here writes to a servo, and no held port is ever opened -- a check that
# perturbs what it measures is not a check.
#
#   ./preflight.sh            # full check
#   ./preflight.sh --quiet    # verdict only
set -u
cd "$(dirname "$0")"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

FOLLOWER_SERIAL=5AE6058270
LEADER_SERIAL=5B14032956
CAL_ROOT="$HOME/.cache/huggingface/lerobot/calibration"

BLOCKERS=()
say() { [ $QUIET -eq 1 ] || echo "$@"; }
section() { [ $QUIET -eq 1 ] || { echo; echo "== $* =="; }; }

# ---------------------------------------------------------------- 1. ownership
section "1. Port ownership"
declare -A HOLDER=()

# Containers first: this is the half that was missing, and the half that cost an hour.
for cid in $(docker ps -q 2>/dev/null); do
    devs=$(docker inspect --format '{{range .HostConfig.Devices}}{{.PathOnHost}} {{end}}' "$cid" 2>/dev/null)
    cmd=$(docker inspect --format '{{.Config.Cmd}}' "$cid" 2>/dev/null | cut -c1-70)
    for d in $devs; do
        case "$d" in
            /dev/ttyACM*) HOLDER[$d]="container ${cid:0:12} ($cmd)";;
        esac
    done
done

# Then host processes.
for procdir in /proc/[0-9]*; do
    pid=${procdir#/proc/}
    [ -r "$procdir/fd" ] || continue
    for link in "$procdir"/fd/*; do
        target=$(readlink "$link" 2>/dev/null) || continue
        case "$target" in
            /dev/ttyACM*)
                name=$(cat "$procdir/comm" 2>/dev/null || echo "?")
                HOLDER[$target]="pid $pid ($name)"
                ;;
        esac
    done
done

for dev in /dev/ttyACM0 /dev/ttyACM1; do
    [ -e "$dev" ] || { say "  $dev  ABSENT"; BLOCKERS+=("$dev does not exist -- arm unplugged"); continue; }
    if [ -n "${HOLDER[$dev]:-}" ]; then
        say "  $dev  HELD BY ${HOLDER[$dev]}"
    else
        say "  $dev  free"
    fi
done
if [ ${#HOLDER[@]} -gt 0 ]; then
    say "  -> exactly one stack may own a port. Ctrl-C the teleop, or quit Chrome"
    say "     completely (Disconnect alone leaked the descriptor before 9caea12)."
fi

# ---------------------------------------------------------- 2. device identity
section "2. Device identity (by USB serial, not node name)"
declare -A BY_SERIAL=()
for dev in /dev/ttyACM*; do
    [ -e "$dev" ] || continue
    s=$(udevadm info -q property -n "$dev" 2>/dev/null | sed -n 's/^ID_SERIAL_SHORT=//p')
    [ -n "$s" ] && BY_SERIAL[$s]=$dev
done
FOLLOWER_DEV=${BY_SERIAL[$FOLLOWER_SERIAL]:-}
LEADER_DEV=${BY_SERIAL[$LEADER_SERIAL]:-}
CFG_FOLLOWER=$(sed -n 's/.*"follower": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)
CFG_LEADER=$(sed -n 's/.*"leader": {.*"port": "\([^"]*\)".*/\1/p' robot_learning/loop.py)

say "  follower white          ($FOLLOWER_SERIAL): ${FOLLOWER_DEV:-NOT FOUND}   CONFIG says $CFG_FOLLOWER"
say "  leader   black_20260801 ($LEADER_SERIAL): ${LEADER_DEV:-NOT FOUND}   CONFIG says $CFG_LEADER"
if [ -z "$FOLLOWER_DEV" ] || [ -z "$LEADER_DEV" ]; then
    BLOCKERS+=("an arm adapter is not present")
elif [ "$FOLLOWER_DEV" != "$CFG_FOLLOWER" ] || [ "$LEADER_DEV" != "$CFG_LEADER" ]; then
    BLOCKERS+=("loop.py CONFIG ports do not match the hardware -- fix CONFIG before running anything")
    say "  -> MISMATCH. Driving the leader through the follower's config caused the"
    say "     2026-08-12 Overload error. Fix CONFIG, do not edit the wrapper scripts."
else
    say "  -> OK, CONFIG matches the hardware"
fi

# ------------------------------------------------------------------ 3. cameras
section "3. Cameras"
for dev in /dev/video0 /dev/video2; do
    if [ -e "$dev" ]; then
        holder="${HOLDER[$dev]:-}"
        say "  $dev  present${holder:+  HELD BY $holder}"
    else
        say "  $dev  ABSENT"
        BLOCKERS+=("$dev missing -- recording needs overview=video0 and wrist=video2")
    fi
done
say "  -> node numbers move on replug; confirm the views look right before recording"

# --------------------------------------------------------- 4. bus+calibration
section "4. Servo bus and calibration (follower)"
if [ -z "$FOLLOWER_DEV" ]; then
    say "  skipped: follower adapter not present"
elif [ -n "${HOLDER[$FOLLOWER_DEV]:-}" ]; then
    say "  SKIPPED: ${HOLDER[$FOLLOWER_DEV]} owns $FOLLOWER_DEV."
    say "  This check will not steal a port. Release it and re-run."
    BLOCKERS+=("could not verify the servo bus -- $FOLLOWER_DEV is held")
else
    CAL="$CAL_ROOT/robots/so100_follower/white.json"
    # Captured, not piped. Piping into grep made the PIPELINE's status grep's, so the
    # bus check's own exit code was thrown away and this script printed GO directly
    # underneath six reported problems -- the exact silent-masking defect it exists to
    # catch. Command substitution keeps $? from the command itself.
    BUS_OUT=$(./hw_docker.sh python scripts/preflight_bus.py "$FOLLOWER_DEV" \
        "/root/.cache/huggingface/lerobot/calibration/robots/so100_follower/white.json" 2>&1)
    BUS_RC=$?
    echo "$BUS_OUT" | grep -vE "NVIDIA|CUDA|nvidia|Copyright|licen|governed|pulling|^={2,}|^$"
    if [ $BUS_RC -ne 0 ]; then
        BLOCKERS+=("servo bus or calibration check failed -- see the table above")
    fi
    say "  file: $CAL"
fi

# ------------------------------------------------------------------- verdict
echo
if [ ${#BLOCKERS[@]} -eq 0 ]; then
    echo "PREFLIGHT: GO -- ports owned by nobody, identity matches CONFIG, calibration matches file."
    exit 0
fi
echo "PREFLIGHT: NO-GO"
for b in "${BLOCKERS[@]}"; do echo "  - $b"; done
echo
echo "Fix these before forming any theory about anything else."
exit 1
