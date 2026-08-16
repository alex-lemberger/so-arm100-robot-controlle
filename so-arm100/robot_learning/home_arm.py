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


def peg_in_wrist(bgr):
    """(x, y) of the peg in the wrist frame as fractions, or None."""
    import cv2

    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh, s, v = (hsv[:, :, i].astype(int) for i in range(3))
    mask = ((hh > 60) & (hh < 110) & (s > 45) & (v > 40)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    blobs = [(stats[i, cv2.CC_STAT_AREA], cents[i]) for i in range(1, n)
             if stats[i, cv2.CC_STAT_AREA] > 2500]
    if not blobs:
        return None
    _area, c = max(blobs)
    return c[0] / w, c[1] / h


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
    found = peg_in_wrist(np.ascontiguousarray(frame))
    if found is None:
        print(f"  PEG NOT VISIBLE in the wrist view. Wrote {out} -- look at it.")
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
    ap.add_argument("--port", default="/dev/ttyACM1")
    ap.add_argument("--id", default="white")
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
