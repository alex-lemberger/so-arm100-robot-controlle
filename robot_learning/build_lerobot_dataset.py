"""Convert curated recorded episodes (data/local/episodes/) into a LeRobot
v3 dataset, using LeRobot's own writer API so the output format matches
exactly what lerobot-train expects.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import av

from lerobot.datasets.lerobot_dataset import LeRobotDataset

JOINT_NAME_MAP = {
    "base": "main_shoulder_pan",
    "shoulder": "main_shoulder_lift",
    "elbow": "main_elbow_flex",
    "wristPitch": "main_wrist_flex",
    "wristRoll": "main_wrist_roll",
    "gripper": "main_gripper",
}
JOINT_ORDER = ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
LEROBOT_JOINT_NAMES = [JOINT_NAME_MAP[joint] for joint in JOINT_ORDER]

TASK_STRING = "Pick up a shape piece and insert it into its matching hole on the puzzle board."

DATASET_FPS = 30

# LeRobot derives every frame's timeline position as frame_index / fps, so a
# recording whose actual camera frame rate doesn't match DATASET_FPS would
# silently time-warp the whole episode with no error. Real measured worst-case
# overview<->wrist pairing delta across all 29 recorded episodes is 0.034s
# (about one frame period at 30fps), so this tolerance has zero false-positive
# risk on real data while still catching a stalled/truncated camera stream.
MAX_FRAME_PAIRING_GAP_S = 0.1

FEATURES = {
    "action": {"dtype": "float32", "shape": (6,), "names": LEROBOT_JOINT_NAMES},
    "observation.state": {"dtype": "float32", "shape": (6,), "names": LEROBOT_JOINT_NAMES},
    "observation.images.overview": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
    "observation.images.wrist": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
}


def load_manifest(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    lines = path.read_text().splitlines()
    names = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not names:
        raise ValueError(f"No episodes listed in manifest {path}")
    return names


def decode_video_frames(path: Path) -> list[tuple[float, np.ndarray]]:
    """Returns [(timestamp_seconds, HWC uint8 RGB array), ...] in playback order."""
    container = av.open(str(path))
    stream = container.streams.video[0]
    frames = []
    for frame in container.decode(stream):
        t_sec = float(frame.pts * stream.time_base)
        frames.append((t_sec, frame.to_ndarray(format="rgb24")))
    container.close()
    return frames


def nearest_frame(
    frames: list[tuple[float, np.ndarray]],
    t_sec: float,
    max_gap_s: float = MAX_FRAME_PAIRING_GAP_S,
) -> np.ndarray:
    best_t, best_frame = min(frames, key=lambda item: abs(item[0] - t_sec))
    gap = abs(best_t - t_sec)
    if gap > max_gap_s:
        raise ValueError(
            f"No frame within {max_gap_s}s of target timestamp {t_sec:.3f}s "
            f"(nearest available was {best_t:.3f}s, gap={gap:.3f}s). This usually "
            "means a camera stream stalled or was truncated partway through the "
            "recording."
        )
    return best_frame


def joints_at(samples: list[dict], t_ms: float) -> dict:
    """Nearest joint sample at-or-before t_ms, holding the last sample for
    any timestamp past the final recorded sample (encoder-flush tail frames)."""
    candidate = samples[0]["joints"]
    for sample in samples:
        if sample["tMs"] <= t_ms:
            candidate = sample["joints"]
        else:
            break
    return candidate


def joints_to_action(joints: dict) -> np.ndarray:
    return np.array([joints[name] for name in JOINT_ORDER], dtype=np.float32)


def validate_episode_dir(episode_dir: Path, name: str) -> None:
    if not episode_dir.is_dir():
        raise FileNotFoundError(f"Episode directory not found: {episode_dir}")
    metadata_path = episode_dir / "metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata.json missing for episode: {name}")
    metadata = json.loads(metadata_path.read_text())
    for key in ("observations", "actions", "durationMs"):
        if key not in metadata:
            raise ValueError(f"metadata.json for {name} is missing required key: {key}")
    for role in ("overview", "wrist"):
        if role not in metadata["observations"]:
            raise ValueError(f"metadata.json for {name} is missing observations.{role}")
        actual_fps = metadata["observations"][role].get("settings", {}).get("frameRate")
        if actual_fps != DATASET_FPS:
            raise ValueError(
                f"Episode {name}: observations.{role}.settings.frameRate is "
                f"{actual_fps!r}, but the dataset is being built at fps={DATASET_FPS}. "
                "LeRobot derives frame timestamps as frame_index/fps, so a mismatch "
                "here would silently time-warp this episode's timeline."
            )


def convert_episode(dataset: LeRobotDataset, episode_dir: Path, name: str) -> int:
    validate_episode_dir(episode_dir, name)
    metadata = json.loads((episode_dir / "metadata.json").read_text())
    samples = metadata["actions"]["samples"]
    overview_path = episode_dir / metadata["observations"]["overview"]["file"]
    wrist_path = episode_dir / metadata["observations"]["wrist"]["file"]

    overview_frames = decode_video_frames(overview_path)
    wrist_frames = decode_video_frames(wrist_path)

    prev_action = None
    for t_sec, overview_image in overview_frames:
        t_ms = t_sec * 1000
        joints = joints_at(samples, t_ms)
        action = joints_to_action(joints)
        state = prev_action if prev_action is not None else action
        wrist_image = nearest_frame(wrist_frames, t_sec)

        dataset.add_frame({
            "observation.images.overview": overview_image,
            "observation.images.wrist": wrist_image,
            "action": action,
            "observation.state": state,
            "task": TASK_STRING,
        })
        prev_action = action

    dataset.save_episode()
    return len(overview_frames)


def build_dataset(manifest_path: Path, episodes_root: Path, output_root: Path, repo_id: str) -> None:
    episode_names = load_manifest(manifest_path)
    for name in episode_names:
        validate_episode_dir(episodes_root / name, name)

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=DATASET_FPS,
        features=FEATURES,
        root=output_root,
        robot_type="so100",
    )
    total_frames = 0
    for name in episode_names:
        total_frames += convert_episode(dataset, episodes_root / name, name)
        print(f"Converted episode {name}")

    dataset.finalize()
    print(f"Wrote {len(episode_names)} episodes, {total_frames} frames to {output_root}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="outputs/episode-review/curated-episodes.txt")
    parser.add_argument("--episodes-root", default="data/local/episodes")
    parser.add_argument("--output", default="data/local/lerobot_dataset")
    parser.add_argument("--repo-id", default="local/shape_sort_teleop")
    args = parser.parse_args()
    build_dataset(Path(args.manifest), Path(args.episodes_root), Path(args.output), args.repo_id)


if __name__ == "__main__":
    main()
