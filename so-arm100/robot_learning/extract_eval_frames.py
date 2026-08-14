"""Extract the last frame of each episode from a rollout dataset's videos.

Lets an eval session's success/failure be reviewed from the recorded footage
instead of relying purely on live eye-scoring during the run.

Usage (inside the lerobot-train container, repo mounted):
    python robot_learning/extract_eval_frames.py --dataset rollout_run_a
"""
import argparse
from pathlib import Path

import av
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent


def extract_last_frame(video_path: Path, at_timestamp: float, out_path: Path) -> None:
    container = av.open(str(video_path))
    stream = container.streams.video[0]
    # Seek slightly before the target timestamp then decode forward to the
    # last frame at or before it -- seeking lands on the nearest keyframe,
    # not the exact timestamp.
    target_pts = max(0, at_timestamp - 0.5)
    container.seek(int(target_pts / stream.time_base), stream=stream)
    last_frame = None
    for frame in container.decode(stream):
        if float(frame.pts * stream.time_base) > at_timestamp:
            break
        last_frame = frame
    if last_frame is None:
        raise RuntimeError(f"No frame found at or before {at_timestamp}s in {video_path}")
    last_frame.to_image().save(out_path)
    container.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="rollout dataset name, e.g. rollout_run_a")
    parser.add_argument("--camera", default="overview", choices=["overview", "wrist"])
    parser.add_argument("--out", help="output dir (default: outputs/eval-frames/<dataset>/<camera>)")
    args = parser.parse_args()

    root = REPO_ROOT / "data" / "local" / "datasets" / args.dataset
    episodes = pd.read_parquet(root / "meta" / "episodes" / "chunk-000" / "file-000.parquet")

    out_dir = Path(args.out) if args.out else REPO_ROOT / "outputs" / "eval-frames" / args.dataset / args.camera
    out_dir.mkdir(parents=True, exist_ok=True)

    col = f"videos/observation.images.{args.camera}"
    for _, row in episodes.sort_values("episode_index").iterrows():
        ep = int(row["episode_index"])
        chunk = int(row[f"{col}/chunk_index"])
        file_idx = int(row[f"{col}/file_index"])
        to_ts = float(row[f"{col}/to_timestamp"])
        video_path = root / "videos" / f"observation.images.{args.camera}" / f"chunk-{chunk:03d}" / f"file-{file_idx:03d}.mp4"
        out_path = out_dir / f"ep{ep:02d}.png"
        extract_last_frame(video_path, to_ts, out_path)
        print(f"episode {ep}: {out_path}")


if __name__ == "__main__":
    main()
