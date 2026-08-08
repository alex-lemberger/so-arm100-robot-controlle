"""Convert a recorded episode into a Keyframe Sequence Studio JSON file.

Lets a real teleoperation take be previewed in the 3D twin and played back
through the app's Arm Motion gate, instead of `lerobot-replay` driving the
follower with no gate in front of it.

Joint values are read from the recording's `commanded.joints`, which is
already in the app's JointState convention (degrees, gripper percent). That
avoids inverting the dataset's LeRobot tick-derived units -- a conversion
with nothing to check it against here.

A 25 s take is ~750 samples; Sequence Studio wants keyframes, not frames.
The trajectory is simplified with Ramer-Douglas-Peucker over the normalized
6-D joint path, so direction changes survive and the still stretches
collapse. Gripper transitions are pinned regardless -- losing the frame
where the grasp happens would silently change what the sequence does.

Usage:
    python robot_learning/episode_to_sequence.py                  # newest episode
    python robot_learning/episode_to_sequence.py <episode-dir>
    python robot_learning/episode_to_sequence.py <dir> --tolerance=0.02
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np

EPISODES_ROOT = Path("data/local/episodes")
JOINT_ORDER = ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
JOINT_LIMITS = {
    "base": (-180, 180),
    "shoulder": (-90, 90),
    "elbow": (-120, 120),
    "wristPitch": (-90, 90),
    "wristRoll": (-180, 180),
    "gripper": (0, 100),
}


def rdp_indices(points: np.ndarray, tolerance: float) -> list[int]:
    """Ramer-Douglas-Peucker, returning kept indices. Iterative, so a 750-point
    path can't blow the recursion limit."""
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        line = points[end] - points[start]
        length = np.linalg.norm(line)
        segment = points[start + 1 : end] - points[start]
        if length < 1e-12:
            dist = np.linalg.norm(segment, axis=1)
        else:
            unit = line / length
            projection = np.outer(segment @ unit, unit)
            dist = np.linalg.norm(segment - projection, axis=1)
        offset = int(np.argmax(dist))
        if dist[offset] > tolerance:
            index = start + 1 + offset
            keep.add(index)
            stack.append((start, index))
            stack.append((index, end))
    return sorted(keep)


def gripper_transition_indices(gripper: np.ndarray, threshold: float) -> set[int]:
    """Indices bracketing every open/close event, so grasp and release survive
    simplification even when the arm is barely moving through them."""
    span = gripper.max() - gripper.min()
    if span < 1e-6:
        return set()
    level = gripper > (gripper.min() + span / 2)
    changes = np.nonzero(level[1:] != level[:-1])[0]
    out: set[int] = set()
    for index in changes:
        out.add(int(index))
        out.add(int(index) + 1)
    return out


def load_episode(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    meta = json.loads((path / "metadata.json").read_text())
    if meta.get("schemaVersion") != 2:
        raise SystemExit(
            f"{path.name} is schemaVersion {meta.get('schemaVersion')}; this tool needs 2."
        )
    samples = meta["timeseries"]["samples"]
    joints = np.array(
        [[s["commanded"]["joints"][name] for name in JOINT_ORDER] for s in samples], dtype=float
    )
    times = np.array([s["tMs"] for s in samples], dtype=float)
    return joints, times, meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", nargs="?", help="episode directory (default: newest)")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.015,
        help="RDP tolerance in normalized joint units; higher = fewer keyframes",
    )
    parser.add_argument("--output", help="output JSON path")
    parser.add_argument(
        "--lead-in-ms",
        type=int,
        default=2500,
        help="duration of the move from wherever the arm is into the start pose",
    )
    parser.add_argument(
        "--min-duration-ms",
        type=int,
        default=120,
        help=(
            "drop keyframes closer together than this. RDP happily keeps two "
            "poses one 33ms sample apart; the app's playback loop and command "
            "coalescing cannot service a hop that short and it plays as jitter. "
            "Total sequence time is preserved -- the dropped interval is added "
            "to the keyframe that absorbs it."
        ),
    )
    args = parser.parse_args()

    if args.episode:
        episode = Path(args.episode)
    else:
        candidates = sorted(p.parent for p in EPISODES_ROOT.glob("*/metadata.json"))
        if not candidates:
            raise SystemExit(f"No episodes under {EPISODES_ROOT}")
        episode = candidates[-1]

    joints, times, meta = load_episode(episode)

    span = joints.max(axis=0) - joints.min(axis=0)
    normalized = joints / np.where(span > 1e-9, span, 1.0)
    kept = set(rdp_indices(normalized, args.tolerance))
    gripper_events = gripper_transition_indices(joints[:, JOINT_ORDER.index("gripper")], 0.5)
    kept |= gripper_events
    indices = sorted(kept)

    # Thin out hops the app cannot play smoothly. Walk forward keeping a
    # keyframe only once enough time has passed since the last one kept.
    # Gripper events and the final pose are never dropped -- a smooth sequence
    # that misses the grasp would be worse than a slightly rough one.
    if args.min_duration_ms > 0 and len(indices) > 2:
        thinned = [indices[0]]
        for index in indices[1:-1]:
            if index in gripper_events or times[index] - times[thinned[-1]] >= args.min_duration_ms:
                thinned.append(index)
        thinned.append(indices[-1])
        indices = thinned

    keyframes = []
    for position, index in enumerate(indices):
        pose = {
            name: round(float(np.clip(joints[index, axis], *JOINT_LIMITS[name])), 2)
            for axis, name in enumerate(JOINT_ORDER)
        }
        if position == 0:
            duration = args.lead_in_ms
        else:
            duration = int(round(times[index] - times[indices[position - 1]]))
        keyframes.append(
            {
                "id": f"ep-{episode.name}-{index}",
                "name": f"t={times[index] / 1000:.2f}s",
                "durationMs": max(duration, 20),
                "delayAfterMs": 0,
                "joints": pose,
                "comment": (
                    f"Recorded teleoperation, {episode.name}. First move eases in from "
                    "the arm's current pose -- check the 3D twin before arming."
                )
                if position == 0
                else None,
            }
        )

    output = Path(args.output) if args.output else Path(f"outputs/sequence-{episode.name}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "id": f"episode-{episode.name}",
                "title": f"Recorded take {episode.name}",
                "description": (
                    f"Real teleoperation demonstration from {episode.name}, "
                    f"{len(keyframes)} keyframes simplified from {len(joints)} samples "
                    f"over {times[-1] / 1000:.1f}s."
                ),
                "category": "task",
                "keyframes": keyframes,
                "loop": False,
                "speedMultiplier": 1,
                "createdAt": datetime.now().isoformat(),
                "tags": ["recorded", "teleop", "schema-v2"],
            },
            indent=2,
        )
        + "\n"
    )

    total = sum(k["durationMs"] for k in keyframes) - args.lead_in_ms
    print(f"{episode.name}: {len(joints)} samples -> {len(keyframes)} keyframes")
    print(f"original {times[-1] / 1000:.1f}s, sequence {total / 1000:.1f}s (+{args.lead_in_ms}ms lead-in)")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
