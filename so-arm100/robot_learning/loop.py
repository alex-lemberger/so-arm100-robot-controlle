"""The record -> train -> evaluate loop for the SO-ARM100 shape-sort task.

Three subcommands, one config. Every hardware id, port, camera index and
convention lives in CONFIG below instead of being retyped into 15-flag command
lines, which is where the old loop lost most of its time.

Two collection paths feed the same train/eval loop:

    # A) record in the app (self-paced), then convert
    python robot_learning/loop.py build  --name circle_insert_app
    python robot_learning/loop.py train  --dataset circle_insert_app --steps 40000
    python robot_learning/loop.py eval   --checkpoint <path> --episodes 10

    # B) record with LeRobot's own CLI (writes a dataset directly)
    python robot_learning/loop.py record --episodes 50
    python robot_learning/loop.py record --episodes 30 --grasp-only
    python robot_learning/loop.py train  --steps 40000

    python robot_learning/loop.py replay --episode 0   # safety gate, either path

This is a thin wrapper: it builds and execs LeRobot's own CLIs, printing the
command first. Nothing is reimplemented, so anything it does can be run by hand.
Use --dry-run to print the command without running it.

Design: docs/superpowers/specs/2026-08-08-native-lerobot-learning-loop-design.md
"""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG = {
    # ~/lerobot/.venv is the environment proven against this hardware.
    "venv_bin": Path.home() / "lerobot" / ".venv" / "bin",
    "follower": {"type": "so100_follower", "port": "/dev/cu.usbmodem5AE60582701", "id": "white"},
    "leader": {"type": "so100_leader", "port": "/dev/cu.usbmodem5B140329561", "id": "black_20260801"},
    # Verified 2026-08-08 with `lerobot-find-cameras opencv`. Indices are NOT
    # stable across reboots or USB re-plugs -- re-run the probe if a recording
    # looks wrong. index 2 is the MacBook FaceTime camera, index 3 is dead.
    "cameras": {
        "overview": {"type": "opencv", "index_or_path": 1, "width": 1280, "height": 720, "fps": 30},
        "wrist": {"type": "opencv", "index_or_path": 0, "width": 1280, "height": 720, "fps": 30},
    },
    "task": "Insert the circle piece into its matching hole.",
    # Rollout only. NOT used while recording: lerobot-record logs the
    # post-clamp value as `action`, so clamping there silently corrupts the
    # action labels whenever the leader moves quickly. While teleoperating,
    # the human hand on the leader is the safety mechanism.
    "rollout_max_relative_target": 5.0,
}

# Enforced start-pose diversity. Two previous recording sessions were meant to
# vary the piece's start pose and delivered essentially none, because it was
# left to intent. Cycle this grid in order and mark the positions on the paper.
POSITION_GRID = [(pos, rot) for pos in ("left", "centre", "right") for rot in (0, 45, 90, 135)]


def dataset_root(name: str) -> Path:
    return REPO_ROOT / "data" / "local" / "datasets" / name


def run(cmd: list[str], dry_run: bool) -> int:
    print("\n" + " \\\n  ".join(shlex.quote(part) for part in cmd) + "\n", flush=True)
    if dry_run:
        print("(--dry-run: not executed)")
        return 0
    return subprocess.call(cmd, cwd=REPO_ROOT)


def bin_path(name: str) -> str:
    return str(CONFIG["venv_bin"] / name)


def cmd_record(args: argparse.Namespace) -> int:
    name = args.name or ("grasp_only" if args.grasp_only else "circle_insert")
    root = dataset_root(name)
    if root.exists() and not args.resume:
        sys.exit(f"{root} already exists. Pass --resume to append, or choose --name.")

    episode_time = args.episode_time or (5 if args.grasp_only else 20)

    print(f"\nRecording '{name}': {args.episodes} episodes x {episode_time}s")
    if args.grasp_only:
        print("Grasp-only: start the arm just above the piece. Reach -> grasp -> lift, nothing else.")
        print("This exists because the grasp is ~5% of a full episode's frames -- the phase that fails.")
    else:
        print("\nCycle these start poses in order, one per episode:")
        for i in range(args.episodes):
            pos, rot = POSITION_GRID[i % len(POSITION_GRID)]
            print(f"  ep {i:>3}  piece {pos:<6} rotated {rot:>3} deg")

    print("\nRun this in YOUR terminal, not through an agent -- you need the live")
    print("'Recording episode N' cue and the keyboard controls to re-record a bad take.\n")

    cmd = [
        bin_path("lerobot-record"),
        f"--robot.type={CONFIG['follower']['type']}",
        f"--robot.port={CONFIG['follower']['port']}",
        f"--robot.id={CONFIG['follower']['id']}",
        f"--teleop.type={CONFIG['leader']['type']}",
        f"--teleop.port={CONFIG['leader']['port']}",
        f"--teleop.id={CONFIG['leader']['id']}",
        f"--robot.cameras={json.dumps(CONFIG['cameras'])}",
        f"--dataset.repo_id=local/{name}",
        f"--dataset.root={root}",
        f"--dataset.single_task={CONFIG['task']}",
        f"--dataset.num_episodes={args.episodes}",
        f"--dataset.episode_time_s={episode_time}",
        f"--dataset.reset_time_s={args.reset_time}",
        "--dataset.push_to_hub=false",
        "--display_data=false",
    ]
    if args.resume:
        cmd.append("--resume=true")
    return run(cmd, args.dry_run)


def cmd_build(args: argparse.Namespace) -> int:
    """Convert schemaVersion-2 app recordings into a LeRobot dataset.

    Only needed on the app-recorder path. `loop.py record` writes a LeRobot
    dataset directly, so it skips this step.
    """
    root = dataset_root(args.name)
    if root.exists():
        sys.exit(f"{root} already exists. Remove it or pass a different --name.")

    cmd = [
        str(CONFIG["venv_bin"] / "python"),
        "robot_learning/build_lerobot_dataset_v2.py",
        f"--manifest={args.manifest}",
        f"--episodes-root={args.episodes_root}",
        f"--output={root}",
        f"--repo-id=local/{args.name}",
        f"--task={CONFIG['task']}",
    ]
    print(f"\nBuilding '{args.name}' from app recordings listed in {args.manifest}")
    print("Episodes must be schemaVersion 2 (measured follower telemetry). v1")
    print("recordings are refused -- they have no real observation.state.\n")
    return run(cmd, args.dry_run)


def cmd_replay(args: argparse.Namespace) -> int:
    root = dataset_root(args.dataset)
    if not root.exists():
        sys.exit(f"No dataset at {root}. Record one first.")

    print(f"\nReplaying '{args.dataset}' episode {args.episode} on the follower.")
    print("This is the safety gate before any policy drives the arm: it proves the")
    print("recorded action column round-trips to real motion on this hardware.")
    print("The arm moves WITHOUT the app's Arm Motion gate -- hand on the power")
    print("switch, workspace clear, and the follower roughly at the episode's start pose.\n")

    cmd = [
        bin_path("lerobot-replay"),
        f"--robot.type={CONFIG['follower']['type']}",
        f"--robot.port={CONFIG['follower']['port']}",
        f"--robot.id={CONFIG['follower']['id']}",
        f"--dataset.repo_id=local/{args.dataset}",
        f"--dataset.root={root}",
        f"--dataset.episode={args.episode}",
    ]
    return run(cmd, args.dry_run)


def cmd_train(args: argparse.Namespace) -> int:
    root = dataset_root(args.dataset)
    if not root.exists():
        sys.exit(f"No dataset at {root}. Record one first.")

    job = args.job or f"{args.policy}_{args.dataset}_{args.steps}"
    cmd = [
        bin_path("lerobot-train"),
        f"--dataset.repo_id=local/{args.dataset}",
        f"--dataset.root={root}",
        f"--policy.type={args.policy}",
        f"--policy.device={args.device}",
        f"--steps={args.steps}",
        f"--batch_size={args.batch_size}",
        f"--output_dir=outputs/train/{job}",
        f"--job_name={job}",
        "--policy.push_to_hub=false",
    ]
    print(f"\nTraining {args.policy} on '{args.dataset}' for {args.steps} steps -> outputs/train/{job}")
    print("Keep the machine awake -- a 2026-08-06 run took ~5h instead of ~1h because it slept.")
    print("Prefix with `caffeinate -i` if running unattended.\n")
    return run(cmd, args.dry_run)


def cmd_eval(args: argparse.Namespace) -> int:
    checkpoint = Path(args.checkpoint)
    if not checkpoint.exists():
        sys.exit(f"No checkpoint at {checkpoint}")

    print(f"\nAutonomous rollout: {args.episodes} episodes x {args.episode_time}s")
    print(f"Per-step clamp: max_relative_target={CONFIG['rollout_max_relative_target']}")
    print("\nThe arm moves WITHOUT the app's Arm Motion gate. Before starting:")
    print("  - hand on the power switch")
    print("  - workspace clear")
    print("  - a recorded episode has been replayed successfully on this hardware")
    print("\nScore each rollout yourself and report k/N success. That number is the")
    print("metric -- held-out MAE only ever compares checkpoints on one frozen split.\n")

    cmd = [
        bin_path("lerobot-rollout"),
        f"--robot.type={CONFIG['follower']['type']}",
        f"--robot.port={CONFIG['follower']['port']}",
        f"--robot.id={CONFIG['follower']['id']}",
        f"--robot.max_relative_target={CONFIG['rollout_max_relative_target']}",
        f"--robot.cameras={json.dumps(CONFIG['cameras'])}",
        f"--policy.path={checkpoint}",
        f"--policy.device={args.device}",
        f"--dataset.repo_id=local/rollout_{args.tag}",
        f"--dataset.root={dataset_root('rollout_' + args.tag)}",
        f"--dataset.single_task={CONFIG['task']}",
        f"--dataset.num_episodes={args.episodes}",
        f"--dataset.episode_time_s={args.episode_time}",
        "--dataset.push_to_hub=false",
    ]
    return run(cmd, args.dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the command without running it")
    sub = parser.add_subparsers(dest="command", required=True)

    # --dry-run is accepted on either side of the subcommand. SUPPRESS keeps the
    # subparser copy from overwriting a flag already given before the subcommand.
    def add_dry_run(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS,
                       help="print the command without running it")
        return p

    p = add_dry_run(sub.add_parser("record", help="teleoperated demonstration collection"))
    p.add_argument("--episodes", type=int, default=50)
    p.add_argument("--name", help="dataset name (default: circle_insert, or grasp_only)")
    p.add_argument("--grasp-only", action="store_true", help="short reach->grasp->lift episodes")
    p.add_argument("--episode-time", type=int, help="seconds per episode (default 20, or 5 for grasp-only)")
    p.add_argument("--reset-time", type=int, default=10)
    p.add_argument("--resume", action="store_true", help="append to an existing dataset")
    p.set_defaults(func=cmd_record)

    p = add_dry_run(sub.add_parser("build", help="convert app recordings into a LeRobot dataset"))
    p.add_argument("--name", default="circle_insert_app", help="output dataset name")
    p.add_argument("--manifest", default="outputs/episode-review/curated-episodes.txt")
    p.add_argument("--episodes-root", default="data/local/episodes")
    p.set_defaults(func=cmd_build)

    p = add_dry_run(sub.add_parser("replay", help="replay a recorded episode on hardware (safety gate)"))
    p.add_argument("--dataset", default="circle_insert")
    p.add_argument("--episode", type=int, default=0)
    p.set_defaults(func=cmd_replay)

    p = add_dry_run(sub.add_parser("train", help="fit a policy on recorded demonstrations"))
    p.add_argument("--dataset", default="circle_insert")
    p.add_argument("--policy", default="act", choices=["act", "smolvla", "diffusion"])
    p.add_argument("--steps", type=int, default=40000)
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--device", default="mps")
    p.add_argument("--job", help="job name (default: <policy>_<dataset>_<steps>)")
    p.set_defaults(func=cmd_train)

    p = add_dry_run(sub.add_parser("eval", help="autonomous closed-loop rollout on real hardware"))
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--episode-time", type=int, default=30)
    p.add_argument("--device", default="mps")
    p.add_argument("--tag", default="latest", help="names the recorded rollout dataset")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
