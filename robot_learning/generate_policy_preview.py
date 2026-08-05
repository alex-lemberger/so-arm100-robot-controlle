"""Generate a read-only ACT trajectory preview from one held-out episode."""

import argparse
import json
from pathlib import Path

import torch

from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.policies import make_pre_post_processors
from lerobot.policies.act.modeling_act import ACTPolicy


JOINT_NAMES = ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
JOINT_LIMITS = [(-180, 180), (-90, 90), (-120, 120), (-90, 90), (-180, 180), (0, 100)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", type=int, default=40)
    parser.add_argument("--stride", type=int, default=15)
    parser.add_argument("--max-keyframes", type=int, default=80)
    parser.add_argument(
        "--checkpoint",
        default="outputs/train/act_so100_pickplace_500/checkpoints/000500/pretrained_model",
    )
    parser.add_argument("--output", default="outputs/policy-preview.json")
    args = parser.parse_args()

    dataset_root = Path("data/external/svla_so100_pickplace").resolve()
    checkpoint = Path(args.checkpoint).resolve()
    dataset = LeRobotDataset(
        "local/svla_so100_pickplace",
        root=dataset_root,
        episodes=[args.episode],
        video_backend="pyav",
    )
    policy = ACTPolicy.from_pretrained(checkpoint, local_files_only=True).eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=checkpoint,
        preprocessor_overrides={"device_processor": {"device": "cpu"}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    policy.reset()
    preprocessor.reset()
    postprocessor.reset()

    keyframes = []
    for index in range(len(dataset)):
        row = dataset[index]
        observation = {
            key: value
            for key, value in row.items()
            if key in ("observation.images.top", "observation.images.wrist", "observation.state")
        }
        with torch.no_grad():
            predicted = postprocessor(policy.select_action(preprocessor(observation)))[0].tolist()

        if index % max(1, args.stride) != 0 or len(keyframes) >= args.max_keyframes:
            continue

        joints = {
            name: round(max(minimum, min(maximum, float(value))), 3)
            for name, value, (minimum, maximum) in zip(JOINT_NAMES, predicted, JOINT_LIMITS)
        }
        keyframes.append({
            "id": f"policy-preview-{index}",
            "name": f"Policy frame {index}",
            "durationMs": 500,
            "delayAfterMs": 0,
            "joints": joints,
            "comment": "Read-only ACT prediction preview; not a hardware command.",
        })

        if len(keyframes) >= args.max_keyframes:
            break

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "id": "policy-preview-act-so100",
        "title": f"ACT Policy Preview — Episode {args.episode}",
        "description": "Offline prediction preview from the held-out SO-100 pick-and-place dataset.",
        "category": "demo",
        "keyframes": keyframes,
        "loop": False,
        "speedMultiplier": 1,
        "createdAt": "2026-08-03T00:00:00.000Z",
        "tags": ["offline", "policy-preview", "no-hardware"],
    }, indent=2) + "\n")
    print(f"Wrote {len(keyframes)} preview keyframes to {output}")


if __name__ == "__main__":
    main()
