"""One step of a manually-supervised closed-loop SmolVLA rollout.

A single predict_action_chunk() call only sees ~1.7s ahead (chunk_size=50 @
30fps), far short of the ~8s it takes a real demo to reach its grasp phase
(see manifest gripper_min/max below for the open-to-grab signal). Reaching
that point needs multiple chunks predicted from fresh observations, not one
open-loop call — this script is one step of that loop.

It does not touch hardware and does not replace the play step. Each call:
  1. Takes a freshly captured camera pair + a freshly read live joint state
     (never a predicted one — real execution can diverge from what was
     predicted, so each chunk must start from what actually happened).
  2. Predicts the next chunk and writes it as a Sequence Studio-loadable
     sequence in --run-dir, auto-numbered.
  3. Appends a row to --run-dir/manifest.jsonl so a full rollout's history
     (prompts used, gripper range per chunk) stays reviewable afterward.

The loop is: you load chunk_N.json into Sequence Studio, preview it, decide
whether to arm and play it on hardware, then once the arm settles, capture
a fresh camera pair + joint state and call this again for chunk_{N+1}.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import torch

from lerobot.policies import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

from run_policy_prompt import JOINT_ORDER, action_tensor_to_joints, build_observation, camera_keys

GRASP_ATTEMPT_GRIPPER_THRESHOLD = 8.0  # % open; chunks below this never leave the resting/closed band


def next_iteration(run_dir: Path) -> int:
    existing = sorted(run_dir.glob("chunk_*.json"))
    if not existing:
        return 0
    return max(int(p.stem.split("_")[1]) for p in existing) + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Directory for this rollout's chunks + manifest")
    parser.add_argument("--overview-image", required=True)
    parser.add_argument("--wrist-image", required=True)
    parser.add_argument("--state", required=True, help="Freshly read live joint state JSON, not predicted")
    parser.add_argument("--prompt", required=True)
    parser.add_argument(
        "--checkpoint",
        default="outputs/train/smolvla_shape_sort_30000/checkpoints/030000/pretrained_model",
    )
    parser.add_argument("--max-steps", type=int, default=50)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    iteration = next_iteration(run_dir)

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
    num_steps = min(args.max_steps, chunk.shape[1])

    keyframes = []
    gripper_trace = []
    for step in range(num_steps):
        action = postprocessor(chunk[0, step])
        joints = action_tensor_to_joints(action)
        gripper_trace.append(joints["gripper"])
        keyframes.append({
            "id": f"chunk{iteration}-step-{step}",
            "name": f"Chunk {iteration} step {step}",
            "durationMs": 500,
            "delayAfterMs": 0,
            "joints": joints,
            "comment": f'Closed-loop chunk {iteration}, prompt: "{args.prompt}"' if step == 0 else None,
        })

    output_path = run_dir / f"chunk_{iteration}.json"
    output_path.write_text(json.dumps({
        "id": f"closed-loop-chunk-{iteration}",
        "title": f"Closed-loop chunk {iteration}: {args.prompt}",
        "description": f"Chunk {iteration} of a manually-supervised closed-loop rollout.",
        "category": "ai",
        "keyframes": keyframes,
        "loop": False,
        "speedMultiplier": 1,
        "createdAt": datetime.now().isoformat(),
        "tags": ["smolvla", "closed-loop", f"iteration-{iteration}", "not-hardware-verified"],
    }, indent=2) + "\n")

    gripper_min, gripper_max = min(gripper_trace), max(gripper_trace)
    manifest_path = run_dir / "manifest.jsonl"
    with manifest_path.open("a") as f:
        f.write(json.dumps({
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "prompt": args.prompt,
            "checkpoint": str(checkpoint),
            "overview_image": str(Path(args.overview_image).resolve()),
            "wrist_image": str(Path(args.wrist_image).resolve()),
            "start_state": state,
            "output": str(output_path),
            "gripper_min": gripper_min,
            "gripper_max": gripper_max,
            "predicted_end_state": keyframes[-1]["joints"],
        }) + "\n")

    grasp_note = (
        "gripper OPENED — possible grasp attempt in this chunk"
        if gripper_max > GRASP_ATTEMPT_GRIPPER_THRESHOLD
        else "flat — no grasp attempt predicted in this chunk"
    )
    print(f"Iteration {iteration}: wrote {num_steps} keyframes to {output_path}")
    print(f"Gripper range: {gripper_min:.2f}% - {gripper_max:.2f}%  ({grasp_note})")
    print(f"Predicted end state (for reference only — re-read real hardware before the next call):")
    print(f"  {keyframes[-1]['joints']}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
