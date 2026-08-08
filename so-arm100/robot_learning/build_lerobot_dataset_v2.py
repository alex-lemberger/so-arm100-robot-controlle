"""Convert schemaVersion-2 app recordings into a LeRobot dataset that is
byte-compatible with what `lerobot-record` produces.

Why a v2 builder instead of editing the original:

1. `observation.state` is the follower's *measured* encoder position, not the
   previous commanded target. The v1 builder set `state[t] = action[t-1]`
   because the recorder never captured measured position, which put the policy
   off-distribution the moment it saw real hardware state at inference.
2. Frames are resampled from real per-sample timestamps by linear
   interpolation, not nearest-hold onto a fabricated fixed-rate grid. The v1
   staircase (20 Hz held up to 30 fps) is gone.
3. Values are emitted in **LeRobot's own convention** (DEGREES for the five
   body joints, RANGE_0_100 for the gripper) computed from raw servo ticks via
   the same formula as `MotorsBus._normalize`, using the same calibration file
   the robot uses. Feature names and `robot_type` match `lerobot-record`
   exactly, so `lerobot-rollout` can evaluate a checkpoint trained on this
   data. The v1 builder emitted the app's own degrees/percent convention,
   which nothing in LeRobot's hardware path understands.

Raw ticks are the pivot for (3): the servos already apply their written homing
offset, so register 56 reads the same value LeRobot's own bus reads, and the
app's degree convention never enters the dataset.
"""

import argparse
import json
from pathlib import Path

import av
import numpy as np

from lerobot.datasets.lerobot_dataset import LeRobotDataset

# Servo hardware id -> LeRobot motor name, in LeRobot's own feature order.
SERVO_TO_MOTOR = [
    (1, "shoulder_pan"),
    (2, "shoulder_lift"),
    (3, "elbow_flex"),
    (4, "wrist_flex"),
    (5, "wrist_roll"),
    (6, "gripper"),
]
FEATURE_NAMES = [f"{motor}.pos" for _, motor in SERVO_TO_MOTOR]

# so_follower uses use_degrees=True by default -> body joints are DEGREES,
# the gripper is RANGE_0_100. See so_follower.py:50-59.
DEGREES_MOTORS = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"}
STS3215_RESOLUTION = 4096

DEFAULT_CALIBRATION = (
    Path.home() / ".cache/huggingface/lerobot/calibration/robots/so_follower/white.json"
)
DEFAULT_TASK = "Insert the circle piece into its matching hole."

# A frame is dropped if the nearest bracketing samples are further apart than
# this, which means the serial bus stalled rather than merely ran slow.
MAX_SAMPLE_GAP_S = 0.2
# Overview<->wrist pairing tolerance, ~3 frame periods at 30fps.
MAX_FRAME_PAIRING_GAP_S = 0.1

FEATURES = {
    "action": {"dtype": "float32", "shape": (6,), "names": FEATURE_NAMES},
    "observation.state": {"dtype": "float32", "shape": (6,), "names": FEATURE_NAMES},
    "observation.images.overview": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
    "observation.images.wrist": {
        "dtype": "video", "shape": (720, 1280, 3), "names": ["height", "width", "channels"],
    },
}


def load_calibration(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"Follower calibration not found at {path}. This is the same file "
            "lerobot-record/rollout use; without it the tick->LeRobot-units "
            "conversion cannot be reproduced."
        )
    return json.loads(path.read_text())


def normalize_ticks(ticks: dict[int, float], calibration: dict) -> np.ndarray:
    """Mirrors `MotorsBus._normalize` (motors_bus.py:850-877) for the sts3215.

    Kept as an explicit reimplementation rather than importing the bus, because
    instantiating a MotorsBus would require an open serial port.
    """
    values = []
    for servo_id, motor in SERVO_TO_MOTOR:
        cal = calibration[motor]
        min_, max_ = cal["range_min"], cal["range_max"]
        if max_ == min_:
            raise ValueError(f"Invalid calibration for '{motor}': range_min == range_max.")
        raw = ticks[servo_id]

        if motor in DEGREES_MOTORS:
            mid = (min_ + max_) / 2
            norm = (raw - mid) * 360 / (STS3215_RESOLUTION - 1)
        else:
            bounded = min(max_, max(min_, raw))
            norm = ((bounded - min_) / (max_ - min_)) * 100
            if cal.get("drive_mode"):
                norm = 100 - norm

        if motor in DEGREES_MOTORS and cal.get("drive_mode"):
            # DEGREES ignores drive_mode upstream; flag rather than silently differ.
            raise NotImplementedError(
                f"Motor '{motor}' has drive_mode set, which LeRobot's DEGREES branch "
                "does not apply. This dataset would not match the robot's convention."
            )
        values.append(norm)
    return np.array(values, dtype=np.float32)


def decode_video_frames(path: Path) -> list[tuple[float, np.ndarray]]:
    container = av.open(str(path))
    stream = container.streams.video[0]
    frames = [
        (float(frame.pts * stream.time_base), frame.to_ndarray(format="rgb24"))
        for frame in container.decode(stream)
    ]
    container.close()
    return frames


def nearest_frame(frames: list[tuple[float, np.ndarray]], t_sec: float) -> np.ndarray:
    best_t, best_frame = min(frames, key=lambda item: abs(item[0] - t_sec))
    if abs(best_t - t_sec) > MAX_FRAME_PAIRING_GAP_S:
        raise ValueError(
            f"No frame within {MAX_FRAME_PAIRING_GAP_S}s of {t_sec:.3f}s "
            f"(nearest {best_t:.3f}s). A camera stream likely stalled or was truncated."
        )
    return best_frame


class TickTrack:
    """Per-servo tick timeseries with linear interpolation at arbitrary times."""

    def __init__(self, samples: list[tuple[float, dict[int, float]]]):
        if not samples:
            raise ValueError("No usable samples in this channel.")
        self.times = np.array([t for t, _ in samples], dtype=np.float64)
        self.ticks = {
            servo_id: np.array([s[servo_id] for _, s in samples], dtype=np.float64)
            for servo_id, _ in SERVO_TO_MOTOR
        }

    def at(self, t_sec: float) -> dict[int, float] | None:
        index = int(np.searchsorted(self.times, t_sec))
        lo = max(0, index - 1)
        hi = min(len(self.times) - 1, index)
        # Outside the recorded span, or across a stall -> no honest value.
        if t_sec < self.times[0] - MAX_SAMPLE_GAP_S or t_sec > self.times[-1] + MAX_SAMPLE_GAP_S:
            return None
        if self.times[hi] - self.times[lo] > MAX_SAMPLE_GAP_S:
            return None
        return {
            servo_id: float(np.interp(t_sec, self.times, series))
            for servo_id, series in self.ticks.items()
        }


def build_tracks(metadata: dict, name: str) -> tuple[TickTrack, TickTrack]:
    samples = metadata["timeseries"]["samples"]
    measured, commanded = [], []
    for sample in samples:
        t_sec = sample["tMs"] / 1000.0
        if sample.get("measured") and sample["measured"].get("ticks"):
            measured.append((t_sec, {int(k): v for k, v in sample["measured"]["ticks"].items()}))
        if sample.get("commanded") and sample["commanded"].get("ticks"):
            commanded.append((t_sec, {int(k): v for k, v in sample["commanded"]["ticks"].items()}))

    if not measured:
        raise ValueError(
            f"Episode {name} has no measured follower telemetry — it records commanded "
            "targets only and cannot be trained on. Re-record it with WebSerial "
            "connected and the servo bus verified."
        )
    if not commanded:
        raise ValueError(f"Episode {name} has no commanded tick samples.")
    return TickTrack(measured), TickTrack(commanded)


def validate_episode(metadata: dict, name: str) -> None:
    if metadata.get("schemaVersion") != 2:
        raise ValueError(
            f"Episode {name} is schemaVersion {metadata.get('schemaVersion')!r}, not 2. "
            "schemaVersion 1 recordings have no measured follower position and cannot "
            "be converted — use the archived v1 builder if you need the old dataset."
        )
    for role in ("overview", "wrist"):
        if role not in metadata.get("observations", {}):
            raise ValueError(f"Episode {name} is missing observations.{role}")


def motion_window(metadata: dict, threshold: float, pad_s: float) -> tuple[float, float]:
    """Time span (seconds) in which the arm is actually moving, plus padding.

    Every episode in the 2026-08-08 batch opens with the operator lining up the
    shot -- mean 2.6s of a motionless arm -- and closes with ~2.9s of the same,
    together a quarter of all frames. A policy trained on that learns to sit
    still at the start pose, and because a stationary arm produces an unchanging
    observation, it can re-predict "stay put" forever. Trimming to the moving
    span removes the stall without touching the demonstration itself.
    """
    samples = metadata["timeseries"]["samples"]
    times = np.array([s["tMs"] for s in samples], dtype=np.float64) / 1000.0
    joints = np.array(
        [[s["commanded"]["ticks"][str(i)] for i, _ in SERVO_TO_MOTOR] for s in samples],
        dtype=np.float64,
    )
    step = np.abs(np.diff(joints, axis=0)).sum(axis=1)
    moving = np.nonzero(step > threshold)[0]
    if moving.size == 0:
        return times[0], times[-1]
    start = max(times[0], times[moving[0]] - pad_s)
    end = min(times[-1], times[moving[-1] + 1] + pad_s)
    return start, end


def convert_episode(
    dataset: LeRobotDataset,
    episode_dir: Path,
    name: str,
    calibration: dict,
    task: str,
    trim: bool = False,
    trim_threshold: float = 8.0,
    trim_pad_s: float = 0.3,
) -> tuple[int, int]:
    metadata = json.loads((episode_dir / "metadata.json").read_text())
    validate_episode(metadata, name)
    measured_track, commanded_track = build_tracks(metadata, name)

    overview_frames = decode_video_frames(episode_dir / metadata["observations"]["overview"]["file"])
    wrist_frames = decode_video_frames(episode_dir / metadata["observations"]["wrist"]["file"])

    if trim:
        window_start, window_end = motion_window(metadata, trim_threshold, trim_pad_s)
    else:
        window_start, window_end = float("-inf"), float("inf")

    written = 0
    for t_sec, overview_image in overview_frames:
        if not (window_start <= t_sec <= window_end):
            continue
        measured_ticks = measured_track.at(t_sec)
        commanded_ticks = commanded_track.at(t_sec)
        # Drop rather than invent: a frame with no honest state or action label
        # is worse than one fewer frame.
        if measured_ticks is None or commanded_ticks is None:
            continue

        dataset.add_frame({
            "observation.images.overview": overview_image,
            "observation.images.wrist": nearest_frame(wrist_frames, t_sec),
            "observation.state": normalize_ticks(measured_ticks, calibration),
            "action": normalize_ticks(commanded_ticks, calibration),
            "task": task,
        })
        written += 1

    if written == 0:
        raise ValueError(f"Episode {name} produced no usable frames.")
    dataset.save_episode()
    return written, len(overview_frames) - written


def load_manifest(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Manifest not found: {path}")
    names = [
        line.strip() for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not names:
        raise ValueError(f"No episodes listed in {path}")
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="outputs/episode-review/curated-episodes.txt")
    parser.add_argument("--episodes-root", default="data/local/episodes")
    parser.add_argument("--output", default="data/local/datasets/circle_insert_app")
    parser.add_argument("--repo-id", default="local/circle_insert_app")
    parser.add_argument("--calibration", default=str(DEFAULT_CALIBRATION))
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--trim-stationary",
        action="store_true",
        help=(
            "drop the motionless lead-in and tail of each episode. The app "
            "recorder starts before the operator does and stops after, so a "
            "quarter of the 2026-08-08 batch is a still arm; a policy trained "
            "on it learns to sit at the start pose and can stall there."
        ),
    )
    parser.add_argument(
        "--trim-threshold",
        type=float,
        default=8.0,
        help="total per-sample tick movement across all joints counted as motion",
    )
    parser.add_argument(
        "--trim-pad",
        type=float,
        default=0.3,
        help="seconds of stillness kept on either side of the moving span",
    )
    args = parser.parse_args()

    calibration = load_calibration(Path(args.calibration))
    episodes_root = Path(args.episodes_root)
    names = load_manifest(Path(args.manifest))

    # Validate every episode before writing anything, so a bad one at position
    # 40 does not leave a half-built dataset behind.
    for name in names:
        metadata_path = episodes_root / name / "metadata.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"metadata.json missing for episode {name}")
        validate_episode(json.loads(metadata_path.read_text()), name)

    dataset = LeRobotDataset.create(
        repo_id=args.repo_id,
        fps=args.fps,
        features=FEATURES,
        root=Path(args.output),
        robot_type="so_follower",
    )

    total_written = total_dropped = 0
    for name in names:
        written, dropped = convert_episode(
            dataset,
            episodes_root / name,
            name,
            calibration,
            args.task,
            trim=args.trim_stationary,
            trim_threshold=args.trim_threshold,
            trim_pad_s=args.trim_pad,
        )
        total_written += written
        total_dropped += dropped
        print(f"Converted {name}: {written} frames" + (f" ({dropped} dropped)" if dropped else ""))

    dataset.finalize()
    print(
        f"\nWrote {len(names)} episodes, {total_written} frames to {args.output}"
        + (f" ({total_dropped} frames dropped for missing telemetry)" if total_dropped else "")
    )


if __name__ == "__main__":
    main()
