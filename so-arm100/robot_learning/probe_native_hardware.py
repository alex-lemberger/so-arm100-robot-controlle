"""Step 0.1 of the native LeRobot learning loop: a read-only hardware probe.

Connects to the SO-100 follower and both task cameras through LeRobot's own
Robot API and reads a single observation. It NEVER sends an action, so the arm
cannot move -- this exists to prove the native path (ports, calibration,
camera indices, observation keys) works before anything commands the hardware.

See docs/superpowers/specs/2026-08-08-native-lerobot-learning-loop-design.md.

Run with an env that has scservo_sdk, e.g.:
    ~/lerobot/.venv/bin/python robot_learning/probe_native_hardware.py
"""

import argparse

import numpy as np

from lerobot.cameras.opencv import OpenCVCameraConfig
from lerobot.robots.so100_follower import SO100Follower, SO100FollowerConfig

FOLLOWER_PORT = "/dev/cu.usbmodem5AE60582701"
FOLLOWER_ID = "white"
# Verified 2026-08-08 via `lerobot-find-cameras opencv`; re-check after a reboot
# or USB re-plug, indices are not guaranteed stable.
OVERVIEW_INDEX = 1
WRIST_INDEX = 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=FOLLOWER_PORT)
    parser.add_argument("--id", default=FOLLOWER_ID)
    parser.add_argument("--overview-index", type=int, default=OVERVIEW_INDEX)
    parser.add_argument("--wrist-index", type=int, default=WRIST_INDEX)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    cameras = {
        "overview": OpenCVCameraConfig(
            index_or_path=args.overview_index, width=args.width, height=args.height, fps=args.fps
        ),
        "wrist": OpenCVCameraConfig(
            index_or_path=args.wrist_index, width=args.width, height=args.height, fps=args.fps
        ),
    }
    robot = SO100Follower(SO100FollowerConfig(port=args.port, id=args.id, cameras=cameras))

    print(f"Connecting to follower '{args.id}' on {args.port} (no torque, no motion)...")
    robot.connect(calibrate=False)
    try:
        observation = robot.get_observation()
    finally:
        robot.disconnect()
        print("Disconnected.")

    print("\nObservation keys:")
    joints, images = {}, {}
    for key, value in observation.items():
        if isinstance(value, np.ndarray) and value.ndim == 3:
            images[key] = value
        else:
            joints[key] = value

    print("\n  Measured joint state (real encoder readings, not commanded targets):")
    for key, value in joints.items():
        print(f"    {key:<28} {value:>10.3f}")

    print("\n  Camera frames:")
    for key, value in images.items():
        print(f"    {key:<28} shape={value.shape} dtype={value.dtype} mean={value.mean():.1f}")
        if value.mean() < 1.0:
            print(f"      WARNING: '{key}' frame is essentially black -- wrong camera index?")

    missing = [name for name in ("overview", "wrist") if name not in images]
    if missing:
        raise SystemExit(f"\nFAIL: expected camera frames for {missing}, got {sorted(images)}")
    if not joints:
        raise SystemExit("\nFAIL: no joint readings in the observation")
    print("\nPASS: follower and both cameras reachable through LeRobot's native API.")


if __name__ == "__main__":
    main()
