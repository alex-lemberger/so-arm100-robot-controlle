"""Print the structure and key statistics of a LeRobot v3 dataset.

Usage:
    python scripts/inspect_dataset.py --dataset data/circle_grasp_v1
    python scripts/inspect_dataset.py --dataset data/circle_grasp_v1 --episode 0
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq


def load_info(root: Path) -> dict:
    return json.loads((root / "meta" / "info.json").read_text())


def load_tasks(root: Path) -> list[str]:
    tasks_path = root / "meta" / "tasks.parquet"
    if not tasks_path.exists():
        return []
    table = pq.read_table(tasks_path)
    return table.column("task").to_pylist()


def load_episodes_meta(root: Path) -> list[dict]:
    ep_dir = root / "meta" / "episodes" / "chunk-000"
    parquet_files = sorted(ep_dir.glob("file-*.parquet"))
    if not parquet_files:
        return []
    table = pq.read_table(parquet_files[0])
    return table.to_pydict()


def load_episode_frames(root: Path, episode_index: int, info: dict) -> dict | None:
    data_path_tpl = info["data_path"]
    chunk = episode_index // info["chunks_size"]
    file_idx = 0
    data_file = root / data_path_tpl.format(chunk_index=chunk, file_index=file_idx)
    if not data_file.exists():
        return None
    table = pq.read_table(data_file, filters=[("episode_index", "=", episode_index)])
    if table.num_rows == 0:
        return None
    return {col: table.column(col).to_pylist() for col in table.schema.names}


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, help="Path to LeRobot dataset root")
    parser.add_argument("--episode", type=int, default=None, help="Episode index to inspect")
    args = parser.parse_args()

    root = Path(args.dataset)
    if not root.exists():
        print(f"Dataset not found: {root}")
        return

    info = load_info(root)

    print_section("Dataset Overview")
    print(f"  Path:             {root.resolve()}")
    print(f"  Version:          {info['codebase_version']}")
    print(f"  Robot type:       {info.get('robot_type', 'unknown')}")
    print(f"  FPS:              {info['fps']}")
    print(f"  Total episodes:   {info['total_episodes']}")
    print(f"  Total frames:     {info['total_frames']}")
    print(f"  Total tasks:      {info['total_tasks']}")

    tasks = load_tasks(root)
    if tasks:
        print_section("Tasks")
        for i, t in enumerate(tasks):
            print(f"  [{i}] {t}")

    print_section("Features")
    for name, feat in info["features"].items():
        shape = feat["shape"]
        dtype = feat["dtype"]
        names = feat.get("names")
        if names:
            print(f"  {name}  shape={shape}  dtype={dtype}")
            for n in names:
                print(f"      - {n}")
        else:
            print(f"  {name}  shape={shape}  dtype={dtype}")

    print_section("Observation Fields")
    obs_fields = [k for k in info["features"] if k.startswith("observation")]
    action_fields = [k for k in info["features"] if k.startswith("action")]
    camera_fields = [k for k in obs_fields if "image" in k]
    state_fields = [k for k in obs_fields if "state" in k]
    print(f"  State:   {state_fields}")
    print(f"  Cameras: {camera_fields}")
    print(f"  Action:  {action_fields}")

    joint_names = info["features"].get("action", {}).get("names", [])
    action_dim = info["features"].get("action", {}).get("shape", [0])[0]
    state_dim = info["features"].get("observation.state", {}).get("shape", [0])[0]
    print_section("Joint / Action Summary")
    print(f"  Action dim:  {action_dim}")
    print(f"  State dim:   {state_dim}")
    print(f"  Joint names: {joint_names}")

    if args.episode is not None:
        ep_idx = args.episode
        frames = load_episode_frames(root, ep_idx, info)
        if frames is None:
            print(f"\nEpisode {ep_idx} not found in dataset.")
            return

        n_frames = len(frames["index"])
        duration = frames["timestamp"][-1] - frames["timestamp"][0] if n_frames > 1 else 0.0
        task_idx = frames["task_index"][0] if "task_index" in frames else None
        task_str = tasks[task_idx] if tasks and task_idx is not None else "unknown"

        print_section(f"Episode {ep_idx}")
        print(f"  Frames:    {n_frames}")
        print(f"  Duration:  {float(duration):.2f}s")
        print(f"  Task:      [{task_idx}] {task_str}")

        if "action" in frames:
            actions = np.array(frames["action"], dtype=np.float32)
            states = np.array(frames.get("observation.state", frames["action"]), dtype=np.float32)

            print(f"\n  First state:  {states[0].tolist()}")
            print(f"  Last  state:  {states[-1].tolist()}")
            print(f"\n  Joint ranges (state):")
            for i, name in enumerate(joint_names):
                lo, hi = states[:, i].min(), states[:, i].max()
                print(f"    {name:<20}  [{lo:>8.2f}, {hi:>8.2f}]")


if __name__ == "__main__":
    main()
