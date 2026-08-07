"""Run the fine-tuned SmolVLA checkpoint once on a live observation (two
camera snapshots + current joint state + a typed prompt) and write a short
Sequence Studio-compatible keyframe sequence from the predicted action chunk.

This does not touch hardware. Load the output JSON into Sequence Studio,
preview it in the 3D twin, and only then arm and play it through the app's
existing Arm Motion gate.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from lerobot.policies import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

LEROBOT_TO_APP = {
    "main_shoulder_pan": "base",
    "main_shoulder_lift": "shoulder",
    "main_elbow_flex": "elbow",
    "main_wrist_flex": "wristPitch",
    "main_wrist_roll": "wristRoll",
    "main_gripper": "gripper",
}
LEROBOT_ORDER = list(LEROBOT_TO_APP.keys())
APP_TO_LEROBOT = {v: k for k, v in LEROBOT_TO_APP.items()}
JOINT_ORDER = ["base", "shoulder", "elbow", "wristPitch", "wristRoll", "gripper"]
JOINT_LIMITS = {
    "base": (-180, 180),
    "shoulder": (-90, 90),
    "elbow": (-120, 120),
    "wristPitch": (-90, 90),
    "wristRoll": (-180, 180),
    "gripper": (0, 100),
}


def load_image_tensor(path: Path) -> torch.Tensor:
    image = Image.open(path).convert("RGB")
    array = np.asarray(image, dtype=np.float32) / 255.0  # HWC, [0, 1]
    return torch.from_numpy(array).permute(2, 0, 1)  # CHW


def camera_keys(policy) -> tuple[str, str]:
    """Derive (overview_key, wrist_key) from the checkpoint's own declared input
    features instead of assuming camera1/camera2 — checkpoints trained with
    --policy.input_features=null keep the dataset's native overview/wrist names,
    while earlier checkpoints were trained against a renamed camera1/camera2
    config. Sorted order happens to put overview before wrist and camera1
    before camera2, so it works for both without hardcoding either scheme."""
    visual_keys = sorted(
        key for key, feature in policy.config.input_features.items() if feature.type.value == "VISUAL"
    )
    if len(visual_keys) != 2:
        raise ValueError(f"Expected exactly 2 visual input features, got {visual_keys}")
    return visual_keys[0], visual_keys[1]


def build_observation(
    overview_path: Path, wrist_path: Path, state: dict, prompt: str, overview_key: str, wrist_key: str
) -> dict:
    state_vec = torch.tensor(
        [state[LEROBOT_TO_APP[name]] for name in LEROBOT_ORDER], dtype=torch.float32
    )
    return {
        overview_key: load_image_tensor(overview_path),
        wrist_key: load_image_tensor(wrist_path),
        "observation.state": state_vec,
        "task": prompt,
    }


def action_tensor_to_joints(action: torch.Tensor) -> dict:
    joints = {}
    for name, value in zip(LEROBOT_ORDER, action.tolist()):
        app_name = LEROBOT_TO_APP[name]
        low, high = JOINT_LIMITS[app_name]
        joints[app_name] = round(max(low, min(high, value)), 2)
    return {name: joints[name] for name in JOINT_ORDER}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overview-image", required=True)
    parser.add_argument("--wrist-image", required=True)
    parser.add_argument(
        "--state",
        required=True,
        help='JSON object of current joint values, e.g. \'{"base":0,"shoulder":0,"elbow":0,"wristPitch":0,"wristRoll":0,"gripper":50}\'',
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument(
        "--checkpoint",
        default="outputs/train/smolvla_shape_sort_500/checkpoints/000500/pretrained_model",
    )
    parser.add_argument("--max-steps", type=int, default=15)
    parser.add_argument("--output", default="outputs/policy-prompt-sequence.json")
    args = parser.parse_args()

    state = json.loads(args.state)
    missing = [name for name in JOINT_ORDER if name not in state]
    if missing:
        raise ValueError(f"--state is missing joints: {missing}")

    checkpoint = Path(args.checkpoint).resolve()
    policy = SmolVLAPolicy.from_pretrained(checkpoint, local_files_only=True).to("cpu").eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=checkpoint,
        preprocessor_overrides={"device_processor": {"device": "cpu"}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    policy.reset()
    preprocessor.reset()
    postprocessor.reset()

    overview_key, wrist_key = camera_keys(policy)
    observation = build_observation(
        Path(args.overview_image), Path(args.wrist_image), state, args.prompt, overview_key, wrist_key
    )

    with torch.no_grad():
        chunk = policy.predict_action_chunk(preprocessor(observation))
    # chunk: (batch=1, n_action_steps, action_dim)
    num_steps = min(args.max_steps, chunk.shape[1])

    keyframes = []
    for step in range(num_steps):
        action = postprocessor(chunk[0, step])
        joints = action_tensor_to_joints(action)
        keyframes.append({
            "id": f"policy-prompt-{step}",
            "name": f"Predicted step {step}",
            "durationMs": 500,
            "delayAfterMs": 0,
            "joints": joints,
            "comment": f'SmolVLA prediction for prompt: "{args.prompt}"' if step == 0 else None,
        })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "id": "policy-prompt-sequence",
        "title": f"SmolVLA: {args.prompt}",
        "description": f'Live SmolVLA prediction for the prompt "{args.prompt}", {num_steps} steps.',
        "category": "ai",
        "keyframes": keyframes,
        "loop": False,
        "speedMultiplier": 1,
        "createdAt": __import__("datetime").datetime.now().isoformat(),
        "tags": ["smolvla", "policy-prompt", "not-hardware-verified"],
    }, indent=2) + "\n")
    print(f"Wrote {num_steps} predicted keyframes to {output}")
    print("Load this into Sequence Studio, preview it in the 3D twin, THEN arm and play on hardware.")


if __name__ == "__main__":
    main()
