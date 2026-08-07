"""Offline held-out-split MAE evaluation for a fine-tuned SmolVLA checkpoint.

Replicates lerobot.datasets.factory.make_train_eval_datasets' split logic
(last ceil(n_episodes * eval_split) episodes per task are held out) so this
evaluates on exactly the episodes the checkpoint never trained on, then runs
the policy frame-by-frame via select_action() (chunk-queued, matching real
deployment) and reports mean absolute error against the recorded actions.

Required before any physical-arm test, per
docs/superpowers/specs/2026-08-05-smolvla-shape-sort-finetune-design.md.
"""

import argparse
import json
import math
from pathlib import Path

import torch

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

JOINT_NAMES = [
    "main_shoulder_pan",
    "main_shoulder_lift",
    "main_elbow_flex",
    "main_wrist_flex",
    "main_wrist_roll",
    "main_gripper",
]


def held_out_episodes(dataset_root: Path, repo_id: str, eval_split: float) -> list[int]:
    """Reproduce make_train_eval_datasets' per-task split without loading video data."""
    full_meta = LeRobotDataset(repo_id, root=dataset_root, video_backend="pyav").meta
    episode_tasks = full_meta.episodes["tasks"]
    task_to_episodes: dict[str, list[int]] = {}
    for ep_idx in range(full_meta.total_episodes):
        task_key = episode_tasks[ep_idx][0] if episode_tasks[ep_idx] else ""
        task_to_episodes.setdefault(task_key, []).append(ep_idx)

    eval_episodes: list[int] = []
    for eps in task_to_episodes.values():
        n_eval = math.ceil(len(eps) * eval_split)
        eval_episodes.extend(eps[len(eps) - n_eval :])
    return sorted(eval_episodes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        default="outputs/train/smolvla_shape_sort_30000/checkpoints/030000/pretrained_model",
    )
    parser.add_argument("--dataset-root", default="data/local/lerobot_dataset")
    parser.add_argument("--repo-id", default="local/shape_sort_teleop")
    parser.add_argument("--eval-split", type=float, default=0.15)
    parser.add_argument("--device", default="mps")
    parser.add_argument("--output", default="outputs/smolvla_30000_held_out_mae.json")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root).resolve()
    checkpoint = Path(args.checkpoint).resolve()

    eval_episodes = held_out_episodes(dataset_root, args.repo_id, args.eval_split)
    print(f"Held-out episodes ({len(eval_episodes)}): {eval_episodes}")

    device = args.device if (args.device != "mps" or torch.backends.mps.is_available()) else "cpu"
    policy = SmolVLAPolicy.from_pretrained(checkpoint, local_files_only=True).to(device).eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=checkpoint,
        preprocessor_overrides={"device_processor": {"device": device}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )

    per_joint_abs_sum = torch.zeros(len(JOINT_NAMES))
    total_frames = 0
    per_episode_mae: dict[int, float] = {}

    for ep_idx in eval_episodes:
        dataset = LeRobotDataset(
            args.repo_id, root=dataset_root, episodes=[ep_idx], video_backend="pyav"
        )
        policy.reset()
        preprocessor.reset()
        postprocessor.reset()

        ep_abs_sum = torch.zeros(len(JOINT_NAMES))
        for index in range(len(dataset)):
            row = dataset[index]
            observation = {
                "observation.images.overview": row["observation.images.overview"],
                "observation.images.wrist": row["observation.images.wrist"],
                "observation.state": row["observation.state"],
                "task": row["task"],
            }
            with torch.no_grad():
                predicted = postprocessor(policy.select_action(preprocessor(observation)))[0].cpu()
            abs_err = (predicted - row["action"]).abs()
            ep_abs_sum += abs_err
            per_joint_abs_sum += abs_err

        ep_mae = (ep_abs_sum / len(dataset)).mean().item()
        per_episode_mae[ep_idx] = ep_mae
        total_frames += len(dataset)
        print(f"  episode {ep_idx}: {len(dataset)} frames, MAE = {ep_mae:.4f}")

    per_joint_mae = (per_joint_abs_sum / total_frames).tolist()
    overall_mae = sum(per_joint_mae) / len(per_joint_mae)

    print(f"\nOverall held-out MAE ({total_frames} frames, checkpoint {checkpoint.parent.name}): {overall_mae:.4f}")
    print("Per-joint MAE:")
    for name, value in zip(JOINT_NAMES, per_joint_mae):
        print(f"  {name}: {value:.4f}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "checkpoint": str(checkpoint),
        "eval_episodes": eval_episodes,
        "total_frames": total_frames,
        "overall_mae": overall_mae,
        "per_joint_mae": dict(zip(JOINT_NAMES, per_joint_mae)),
        "per_episode_mae": per_episode_mae,
    }, indent=2) + "\n")
    print(f"\nWrote report to {output}")


if __name__ == "__main__":
    main()
