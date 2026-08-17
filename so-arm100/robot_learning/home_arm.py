"""Drive the follower arm to a defined start pose, and check what the wrist sees.

Why this exists
---------------
The eval harness begins every episode from wherever the arm happens to be sitting,
and measurement on 2026-08-16 showed that pose is not one the demonstrations used.
Where the peg lands in the WRIST view at episode start:

    demos (81 episodes)   y = 0.48 +/- 0.15   centred
    rollout_grasp_v1_r1   y = 0.27            2/10 transports
    rollout_grasp_v1_r2   y = 0.15            0/10
    rollout_probe_1       y = 0.11            0/3, 100% of starts at the frame edge

Monotonic with performance, and r1 is already out of distribution even though its
peg was on the demos' own table position. The wrist camera moves with the arm, so
its framing is a function of the arm's pose as much as the object's -- and the wrist
view is the only channel with the resolution to servo onto a 13mm knob. Starting
outside the demonstrated framing puts the policy out of distribution in its most
precision-critical input before it has done anything.

The pose below is the median of the 16 demo episodes that framed the peg most
centrally. It is close to what the evals already do except in wrist_flex (56 vs 65),
though the framing depends on the whole arm rather than any one joint -- shoulder_lift
correlates with the peg's wrist-frame y at r=+0.68, elbow at -0.65, pan at -0.62,
wrist_flex at -0.50.

    ./home_arm.sh                 # move there, then report what the wrist sees
    ./home_arm.sh --check-only    # report without moving
    ./home_arm.sh --wrist-flex 60 # try a variant

Verify before trusting: the printed peg position is measured, not assumed, so a pose
that does not actually centre the peg says so.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "robot_learning"))

# Median of the demo starts that framed the peg centrally (y 0.42-0.54, x 0.35-0.55).
HOME_POSE = {
    "shoulder_pan.pos": 60.3,
    "shoulder_lift.pos": -103.7,
    "elbow_flex.pos": 96.9,
    "wrist_flex.pos": 56.0,
    "wrist_roll.pos": 16.3,
    "gripper.pos": 2.6,
}
# What the demos did, for judging the result.
DEMO_WRIST_Y = (0.482, 0.151)
DEMO_WRIST_X = (0.41, 0.11)

STEP_DEG = 1.5          # per-tick joint move: slow enough to be stoppable by hand
TICK_S = 0.03


# Hue floor of 30, not the 60 that scripts/analyse_placement_generalization.py uses.
# That 60 is correct for the OVERHEAD camera and wrong here: measured on a real wrist
# frame (2026-08-17), the peg's green sits at hue 44 and the board's empty circle at
# 48, so `hh > 60` matched 8 pixels in the whole 1280x720 image and the check reported
# PEG NOT VISIBLE while the peg was plainly there in the PNG it had just written. The
# wrist camera's white balance runs warmer than the overhead one -- the same hue slide
# align_board.py:67 documents. A narrow window is what made check_alignment.sh send us
# after the wrong object; do not re-narrow this without measuring a wrist frame first.
HUE = (30, 110)
# The loose peg is lit paper-side up (median V 76, S 129). A seated piece sits in a
# shadowed pocket and the empty circle is a hole (V 45, S 205). Without this the
# largest-blob rule can hand back the BOARD's position labelled as the peg's, which is
# the failure mode that costs a week -- a wrong number is worse than no number.
RECESS_MAX_V = 55


def peg_in_wrist(bgr):
    """Peg position in the wrist frame as fractions, plus every green candidate.

    Returns ((x, y) or None, candidates). Candidates are reported so a human can see
    what was found and rejected: this check is the readout for the home-pose
    experiment, and an instrument that fails silently is how the last two eval metrics
    went wrong.
    """
    import cv2

    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh, s, v = (hsv[:, :, i].astype(int) for i in range(3))
    mask = ((hh > HUE[0]) & (hh < HUE[1]) & (s > 45) & (v > 40)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)

    candidates = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area <= 2500:
            continue
        sel = labels == i
        candidates.append({
            "area": area,
            "xy": (float(cents[i][0] / w), float(cents[i][1] / h)),
            "v": int(np.median(v[sel])),
            "s": int(np.median(s[sel])),
        })
    candidates.sort(key=lambda c: -c["area"])

    lit = [c for c in candidates if c["v"] > RECESS_MAX_V]
    return (max(lit, key=lambda c: c["area"])["xy"] if lit else None), candidates


def report_wrist(robot) -> None:
    import cv2

    obs = robot.get_observation()
    # NOT `"wrist" in k`: the joint states are keyed wrist_flex.pos / wrist_roll.pos,
    # so that matches a float and fails one line later on .shape.
    key = next((k for k in obs if "wrist" in k and not k.endswith(".pos")), None)
    if key is None:
        print("  no wrist camera in the observation -- cannot check framing")
        return
    frame = obs[key]
    frame = frame[:, :, ::-1] if frame.shape[-1] == 3 else frame
    out = REPO_ROOT / "wrist_home_check.png"
    cv2.imwrite(str(out), np.ascontiguousarray(frame))
    found, candidates = peg_in_wrist(np.ascontiguousarray(frame))
    for c in candidates:
        role = "peg?" if c["v"] > RECESS_MAX_V else "recess/shadowed piece"
        print(f"    green blob area {c['area']:6d} at ({c['xy'][0]:.2f}, {c['xy'][1]:.2f})"
              f"  V={c['v']:3d} S={c['s']:3d}  -> {role}")
    if found is None:
        why = "no green found at all" if not candidates else "every green blob looked like a recess"
        print(f"  PEG NOT VISIBLE in the wrist view ({why}). Wrote {out} -- look at it.")
        return
    x, y = found
    zy = (y - DEMO_WRIST_Y[0]) / DEMO_WRIST_Y[1]
    zx = (x - DEMO_WRIST_X[0]) / DEMO_WRIST_X[1]
    print(f"  peg in the wrist view: x={x:.2f} ({zx:+.1f} sd), y={y:.2f} ({zy:+.1f} sd)"
          f"   demos: x {DEMO_WRIST_X[0]:.2f}, y {DEMO_WRIST_Y[0]:.2f}")
    edge = x < 0.15 or x > 0.85 or y < 0.15 or y > 0.85
    if edge:
        print("  AT THE FRAME EDGE -- worse than any demonstration start.")
    elif abs(zy) < 1.0 and abs(zx) < 1.0:
        print("  inside the demos' framing. This is the start pose they had.")
    else:
        print("  in frame but outside the demos' usual framing; adjust and re-run.")
    print(f"  wrote {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true", help="report framing, do not move")
    # Default read from loop.py CONFIG rather than written out again. This said
    # /dev/ttyACM1 as a literal until 2026-08-17, when the ttyACM assignment flipped
    # and that became the LEADER -- so the default would have driven the wrong arm.
    from loop import CONFIG

    ap.add_argument("--port", default=CONFIG["follower"]["port"],
                    help="follower serial port (default: loop.py CONFIG)")
    ap.add_argument("--id", default=CONFIG["follower"]["id"])
    for joint in ("shoulder-pan", "shoulder-lift", "elbow-flex", "wrist-flex", "wrist-roll", "gripper"):
        ap.add_argument(f"--{joint}", type=float, help=f"override {joint.replace('-', '_')}")
    args = ap.parse_args()

    target = dict(HOME_POSE)
    for joint in list(target):
        override = getattr(args, joint.split(".")[0], None)
        if override is not None:
            target[joint] = override

    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.robots.so_follower import SOFollower
    from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

    # fourcc=MJPG is not optional: uncompressed YUYV at 1280x720 tops out at 10fps
    # over USB on this hardware, and lerobot refuses a camera that cannot hit the
    # requested rate. Same reason loop.py's CONFIG sets it.
    cameras = {
        "wrist": OpenCVCameraConfig(index_or_path="/dev/video2", width=1280, height=720,
                                    fps=30, fourcc="MJPG"),
    }
    robot = SOFollower(SOFollowerRobotConfig(port=args.port, id=args.id, cameras=cameras))
    robot.connect()
    try:
        obs = robot.get_observation()
        current = {k: v for k, v in obs.items() if k.endswith(".pos")}
        print("current pose:")
        for k in target:
            print(f"  {k:20s} {current.get(k, float('nan')):8.2f}   target {target[k]:8.2f}")

        if not args.check_only:
            print("\nmoving...")
            # Interpolated, not a jump: a single send_action to a distant target makes
            # the servos sprint there, and this arm is usually a few centimetres from
            # the board and the peg when it starts.
            steps = int(max(abs(target[k] - current.get(k, target[k])) for k in target) / STEP_DEG) + 1
            for i in range(1, steps + 1):
                blend = {k: current.get(k, target[k]) + (target[k] - current.get(k, target[k])) * i / steps
                         for k in target}
                robot.send_action(blend)
                time.sleep(TICK_S)
            time.sleep(0.4)
            settled = {k: v for k, v in robot.get_observation().items() if k.endswith(".pos")}
            worst = max(abs(settled.get(k, 0) - target[k]) for k in target)
            print(f"  settled, worst joint error {worst:.2f} deg")

        print("\nwrist framing:")
        report_wrist(robot)
    finally:
        robot.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
