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
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG = {
    # ~/lerobot/.venv is the environment proven against this hardware on Mac;
    # on Linux this resolves through a symlink to /usr/local/bin inside
    # lerobot-train:latest (see Dockerfile.lerobot) instead of a real venv.
    "venv_bin": Path.home() / "lerobot" / ".venv" / "bin",
    # Re-detected on Linux 2026-08-11 after the physical move (see
    # docs/linux-hardware-setup-2026-08-11.md) -- ports/indices are NOT
    # portable across machines. Mac was /dev/cu.usbmodem5AE60582701 (follower)
    # / /dev/cu.usbmodem5B140329561 (leader).
    # CORRECTED 2026-08-12: enumeration flipped since the 08-11 check (USB
    # replug/reboot reorders ttyACM assignment) -- an eval run hit an Overload
    # error while trying to disable torque through what CONFIG called the
    # follower, and the user confirmed by feel it was actually the physical
    # leader. Re-verified by unplugging the follower's cable alone: /dev/ttyACM1
    # disappeared, /dev/ttyACM0 remained -- so ttyACM0 is the leader, ttyACM1
    # is the follower. This mapping is NOT stable across reboots/replugs;
    # re-verify with the same unplug test if ports are ever in doubt.
    "follower": {"type": "so100_follower", "port": "/dev/ttyACM1", "id": "white"},
    "leader": {"type": "so100_leader", "port": "/dev/ttyACM0", "id": "black_20260801"},
    # Verified 2026-08-11 via lerobot-find-cameras + visual match (Mac indices
    # were overview=1, wrist=0 -- also not portable).
    # fourcc=MJPG: uncompressed YUYV at 1280x720 can't sustain 30fps over USB
    # (maxes out at 10fps) -- MJPG compression is required to hit the requested
    # fps at this resolution. Confirmed 2026-08-12 on this hardware.
    "cameras": {
        "overview": {"type": "opencv", "index_or_path": "/dev/video0", "width": 1280, "height": 720, "fps": 30, "fourcc": "MJPG"},
        "wrist": {"type": "opencv", "index_or_path": "/dev/video2", "width": 1280, "height": 720, "fps": 30, "fourcc": "MJPG"},
    },
    "task": "Insert the circle piece into its matching hole.",
    # Rollout only. NOT used while recording: lerobot-record logs the
    # post-clamp value as `action`, so clamping there silently corrupts the
    # action labels whenever the leader moves quickly. While teleoperating,
    # the human hand on the leader is the safety mechanism.
    #
    # 25.0, not the 5.0 this started at. Measured against the 50-episode
    # dataset, |commanded - measured| exceeds 5.0 on some joint in 52% of all
    # training frames -- shoulder_lift alone sits at p95 12.4, p99 20.9, max
    # 38.1, because it leads the follower while fighting gravity. A 5.0 clamp
    # therefore truncated normal commands on every other tick, and since each
    # tick re-clamps from a different measured position, the result was visible
    # jitter on hardware rather than a safety margin. 25.0 clears the p99 of
    # every joint while still bounding a runaway. For reference, lerobot-replay
    # runs this same action column with no clamp at all.
    "rollout_max_relative_target": 25.0,
}

# Enforced placement diversity: a coarse pattern for the human to follow, one row per
# episode. Two previous recording sessions were meant to vary the piece's start pose
# and delivered essentially none, because it was left to intent. Two things this fixes
# about the version that produced circle_grasp_v1's 15x19mm patch of actual placements
# (measured 2026-08-16: three dense clusters over 81 episodes):
#
#   - That grid varied left/centre/right ONLY. It never asked for near/far variation
#     at all, so every episode sat at roughly one distance from the base and half the
#     coverage was missing by construction.
#   - Positions are ordered so the piece MOVES EVERY EPISODE. Rotation is the outer
#     loop, so consecutive rows never repeat a spot; the old nesting would have left
#     the piece in one place for four takes running.
#
# Deliberately NOT millimetres, and deliberately not surveyed. Standard LeRobot
# practice is that the human moves the object by eye between takes -- what matters is
# that consecutive episodes look different and the whole reachable area gets used, not
# that anyone can name the coordinates afterwards. The extremes are named as extremes
# because the point of the far corners is that they are awkward: "left" with nothing
# else said drifts toward the middle over a long session, which is what happened twice.
REACH = ("near", "mid", "far")          # distance out from the arm's base
SIDE = ("left", "centre", "right")
POSITION_GRID = [(f"{reach} {side}", rot)
                 for rot in (0, 45, 90, 135)
                 for reach in REACH
                 for side in SIDE]


def dataset_root(name: str) -> Path:
    return REPO_ROOT / "data" / "local" / "datasets" / name


def resolve_checkpoint(args: argparse.Namespace) -> Path:
    """Turn --checkpoint / --run / nothing into a pretrained_model path.

    Exists because the full path is ~95 characters, and pasting a command that
    long into a terminal wraps it mid-token: a paste that split
    `.../trimmed_20000/c` from `heckpoints/...` is what sent zsh looking for a
    command called `heckpoints`. Short commands are not a convenience here,
    they are the difference between the session starting and not.
    """
    if args.checkpoint:
        return Path(args.checkpoint)

    runs = REPO_ROOT / "outputs" / "train"
    if args.run:
        candidates = [runs / args.run]
        if not candidates[0].is_dir():
            sys.exit(f"No training run at {candidates[0]}")
    else:
        # Most recently modified run that actually has checkpoints. Ambiguous
        # by nature, so the resolved path is always printed before anything
        # touches the hardware.
        candidates = sorted(
            (d for d in runs.iterdir() if (d / "checkpoints").is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            sys.exit(f"No training runs with checkpoints under {runs}. Pass --checkpoint.")

    run_dir = candidates[0]
    steps = sorted(
        (d for d in (run_dir / "checkpoints").iterdir() if d.name.isdigit()),
        key=lambda d: int(d.name),
    )
    if not steps:
        sys.exit(f"No numbered checkpoints under {run_dir / 'checkpoints'}. Pass --checkpoint.")
    return steps[-1] / "pretrained_model"


def add_checkpoint_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--checkpoint", help="explicit path to a pretrained_model directory")
    parser.add_argument("--run", help="training run under outputs/train (uses its last checkpoint)")
    return parser


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
            print(f"  ep {i:>3}  piece {pos:<12} rotated {rot:>3} deg")

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


def cmd_grid(args: argparse.Namespace) -> int:
    """Print the start-pose grid for a session recorded in the app.

    `record` prints this for the lerobot-record path, but app recordings never
    pass through it. Diversity has been left to intent twice and delivered
    essentially none both times, so the grid needs to be visible either way.
    """
    print(f"\nStart-pose grid — {args.episodes} episodes. Mark the positions on the paper.\n")
    for i in range(args.episodes):
        pos, rot = POSITION_GRID[i % len(POSITION_GRID)]
        print(f"  ep {i:>3}  piece {pos:<12} rotated {rot:>3} deg")
    print("\nCycle in order. Do not improvise -- that is what failed the last two times.\n")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    """Convert schemaVersion-2 app recordings into a LeRobot dataset.

    Only needed on the app-recorder path. `loop.py record` writes a LeRobot
    dataset directly, so it skips this step.
    """
    root = dataset_root(args.name)
    if root.exists():
        sys.exit(f"{root} already exists. Remove it or pass a different --name.")

    # The existing curated-episodes.txt lists schemaVersion-1 episodes, which
    # the v2 builder correctly refuses. Rather than fail with a confusing error,
    # offer a fresh manifest of every v2 episode for the human to trim.
    manifest = Path(args.manifest)
    if not manifest.is_file():
        episodes_root = REPO_ROOT / args.episodes_root
        found = []
        for path in sorted(episodes_root.glob("*/metadata.json")):
            try:
                if json.loads(path.read_text()).get("schemaVersion") == 2:
                    found.append(path.parent.name)
            except (json.JSONDecodeError, OSError):
                continue
        if not found:
            sys.exit(f"No schemaVersion-2 episodes found under {episodes_root}.")
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            "# schemaVersion-2 episodes, newest last. Delete the lines for bad\n"
            "# takes, then re-run this command.\n" + "\n".join(found) + "\n"
        )
        sys.exit(
            f"Wrote a manifest of {len(found)} schemaVersion-2 episode(s) to {manifest}.\n"
            "Review it, delete any bad takes, then run this command again."
        )

    cmd = [
        str(CONFIG["venv_bin"] / "python"),
        "robot_learning/build_lerobot_dataset_v2.py",
        f"--manifest={args.manifest}",
        f"--episodes-root={args.episodes_root}",
        f"--output={root}",
        f"--repo-id=local/{args.name}",
        # A grasp-only session is a different instruction from the full insert,
        # and giving it its own string is what makes language discriminative:
        # measured 2026-08-09, the 20k checkpoint reacts to prompt wording but
        # not to its meaning, because all 26,078 training frames carried one
        # identical task string. Two tasks in one dataset is what changes that.
        f"--task={args.task or CONFIG['task']}",
    ]
    if args.trim:
        cmd.append("--trim-stationary")
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

    # Name the job after the base checkpoint when fine-tuning one, not after
    # --policy (which keeps its "act" default and would mislabel a SmolVLA run).
    stem = args.base.rsplit("/", 1)[-1].removesuffix("_base") if args.base else args.policy
    job = args.job or f"{stem}_{args.dataset}_{args.steps}" + ("_lora" if args.lora else "")
    cmd = [
        bin_path("lerobot-train"),
        f"--dataset.repo_id=local/{args.dataset}",
        f"--dataset.root={root}",
        f"--policy.device={args.device}",
        f"--steps={args.steps}",
        f"--batch_size={args.batch_size}",
        f"--output_dir=outputs/train/{job}",
        f"--job_name={job}",
        "--policy.push_to_hub=false",
    ]

    if args.base:
        # Fine-tune from a pretrained base. --policy.input_features=null makes
        # lerobot infer the camera keys from the dataset instead of taking the
        # base checkpoint's own 3-camera config, which this 2-camera setup does
        # not match.
        cmd += [f"--policy.path={args.base}", "--policy.input_features=null"]
    else:
        cmd.append(f"--policy.type={args.policy}")

    if args.lora:
        # Parameter-efficient fine-tuning (docs/source/peft_training.mdx).
        # Adapts a low-rank matrix instead of all 450M parameters: cheaper
        # backward pass, so a larger batch fits, and the resulting adapter is a
        # fraction of a full checkpoint -- the 30k full fine-tune produced 7.4 GB
        # that had to move over USB. By default PEFT targets q_proj/v_proj in
        # SmolVLA's LM expert plus the state and action projections.
        #
        # The 10x learning rate is not optional. The PEFT doc: "The learning
        # rate ... can usually be scaled by a factor of 10 compared to the
        # learning rate used for full fine-tuning (e.g., 1e-4 normal, so 1e-3
        # using LoRA)." A LoRA run left at the full-fine-tune LR just
        # underfits quietly.
        cmd += [
            "--peft.method_type=LORA",
            f"--peft.r={args.lora_r}",
            f"--peft.lora_alpha={args.lora_alpha}",
            f"--policy.optimizer_lr={args.lr}",
            f"--policy.scheduler_decay_lr={args.lr / 10}",
        ]

    label = f"{args.base or args.policy}{' + LoRA r=' + str(args.lora_r) if args.lora else ''}"
    print(f"\nTraining {label} on '{args.dataset}' for {args.steps} steps -> outputs/train/{job}")
    print(f"batch_size={args.batch_size}" + (f", lr={args.lr} (10x, LoRA)" if args.lora else ""))
    print("Keep the machine awake -- a 2026-08-06 run took ~5h instead of ~1h because it slept.")
    print("Prefix with `caffeinate -i` if running unattended.\n")
    return run(cmd, args.dry_run)


def cmd_dagger(args: argparse.Namespace) -> int:
    """Human-in-the-loop correction collection (docs/source/hil_data_collection.mdx).

    Behavioural cloning only ever sees successful demonstrations, so at
    deployment small errors compound into states that appear nowhere in the
    training set. DAgger records the recovery from *this* policy's actual
    failures: run it on the arm, take over on the leader when it is about to
    fail, and the correction is saved as training data. Fine-tune on demos plus
    corrections, then repeat against the new failure modes.

    Cheaper and better targeted than recording another 50 blind demonstrations.
    """
    if args.rehearse:
        # rehearse() imports lerobot, so it has to run under the venv python.
        return run(
            [bin_path("python"), str(REPO_ROOT / "robot_learning" / "dagger_ui.py"),
             "--target", str(min(args.episodes, 3))],
            args.dry_run,
        )

    checkpoint = resolve_checkpoint(args)
    if not checkpoint.exists():
        sys.exit(f"No checkpoint at {checkpoint}")

    # lerobot-rollout rejects any dataset whose name lacks the `rollout_`
    # prefix (rollout/context.py:356); its own examples use rollout_dagger_*.
    dataset_name = f"rollout_dagger_{args.tag}"
    root = dataset_root(dataset_name)

    # A session that saved nothing still leaves a root behind (just info.json),
    # and LeRobotDataset.create then refuses the next attempt. Four sessions on
    # 2026-08-09 saved nothing, so this is the common case, not the rare one.
    if root.exists():
        has_episodes = (root / "meta" / "episodes").exists()
        if has_episodes:
            sys.exit(f"{root} already holds recorded episodes. Use a different --tag.")
        shutil.rmtree(root)
        print(f"Cleared empty {root.name} from a previous run.")

    print(f"\nHuman-in-the-loop correction collection -> local/{dataset_name}")
    print(f"Policy: {checkpoint}")
    print(f"Leader: {CONFIG['leader']['type']} on {CONFIG['leader']['port']}")
    print(f"\nThe sequence, per correction:  SPACE -> TAB -> drive -> TAB")
    print("  SPACE  take the arm from the policy (or give it back)")
    print("  TAB    start recording, then save -- only works after SPACE")
    print("  ESC    finish the session")
    print("\nTAB while the policy is driving does nothing. SPACE always comes first.")
    print("Practise with `--rehearse` first if you want; it needs no hardware.\n")

    cmd = [
        bin_path("lerobot-rollout"),
        "--strategy.type=dagger",
        f"--inference.type={args.inference}",
        f"--inference.rtc.execution_horizon={args.execution_horizon}",
        f"--robot.type={CONFIG['follower']['type']}",
        f"--robot.port={CONFIG['follower']['port']}",
        f"--robot.id={CONFIG['follower']['id']}",
        f"--robot.max_relative_target={CONFIG['rollout_max_relative_target']}",
        f"--robot.cameras={json.dumps(CONFIG['cameras'])}",
        # DAgger refuses to start without a teleoperator: it has to mirror the
        # follower's pose onto the leader at handover, which needs active motors.
        f"--teleop.type={CONFIG['leader']['type']}",
        f"--teleop.port={CONFIG['leader']['port']}",
        f"--teleop.id={CONFIG['leader']['id']}",
        f"--policy.path={checkpoint}",
        f"--policy.device={args.device}",
        f"--dataset.repo_id=local/{dataset_name}",
        f"--dataset.root={dataset_root(dataset_name)}",
        f"--dataset.single_task={CONFIG['task']}",
        f"--dataset.num_episodes={args.episodes}",
        f"--dataset.episode_time_s={args.episode_time}",
        "--dataset.push_to_hub=false",
    ]
    if args.record_autonomous:
        cmd.append("--strategy.record_autonomous=true")
    if args.raw or args.dry_run:
        return run(cmd, args.dry_run)

    from dagger_ui import run_with_status
    print("\n" + " \\\n  ".join(shlex.quote(part) for part in cmd) + "\n", flush=True)
    return run_with_status(cmd, target_episodes=args.episodes)


def cmd_merge(args: argparse.Namespace) -> int:
    """Combine demonstrations and DAgger corrections into one trainable dataset.

    `lerobot-train` takes exactly one dataset -- MultiLeRobotDataset raises
    NotImplementedError in this version -- so demos and corrections, which land
    in separate datasets, have to be merged on disk first. This runs LeRobot's
    own `aggregate_datasets`; see robot_learning/merge_datasets.py for why that
    is not a file copy in the v3.0 layout.
    """
    print(f"\nMerging {', '.join(args.sources)} -> local/{args.into}")
    print("Corrections are a small fraction of the demo frames; that is expected --")
    print("they are on-policy states the demonstrations never visit.\n")
    return run(
        [bin_path("python"), str(REPO_ROOT / "robot_learning" / "merge_datasets.py"),
         "--into", args.into, *args.sources],
        args.dry_run,
    )


def cmd_eval(args: argparse.Namespace) -> int:
    checkpoint = resolve_checkpoint(args)
    if not checkpoint.exists():
        sys.exit(f"No checkpoint at {checkpoint}")

    print(f"\nAutonomous rollout: {args.episodes} episodes x {args.episode_time}s")
    print(f"Per-step clamp: max_relative_target={CONFIG['rollout_max_relative_target']}")
    print("\nThe arm moves WITHOUT the app's Arm Motion gate. Before starting:")
    print("  - hand on the power switch")
    print("  - workspace clear")
    print("  - a recorded episode has been replayed successfully on this hardware")
    print(f"Reset window between episodes: {args.reset_time}s -- reposition the piece then.")
    print("\nKeyboard, during the run:")
    print("  right arrow  end the current episode (or reset phase) early")
    print("  left arrow   discard the current episode and re-record it")
    print("  escape       stop the session")
    print("\nScore each rollout yourself and report k/N success. That number is the")
    print("metric -- held-out MAE only ever compares checkpoints on one frozen split.\n")

    cmd = [
        bin_path("lerobot-rollout"),
        # `episodic` mirrors lerobot-record: N episodes, a reset window between
        # each, keyboard control. The default `base` strategy refuses a dataset
        # outright ("Base strategy does not record data"), and without a
        # recorded dataset there is nothing to review after the run.
        "--strategy.type=episodic",
        # Real-time chunking, not the default sync engine. Sync blocks the
        # control loop on a full policy inference every tick, which on this Mac
        # ran the loop at 3.3 Hz against a 30 Hz target -- each 50-action chunk
        # (1.67s of intended motion) stretched over ~15s, so the arm crawled and
        # looked like it was doing nothing. RTC serves the chunk from a buffer
        # while the next one computes; measured 30 Hz with no dropped ticks.
        f"--inference.type={args.inference}",
        # 10 is the documented value: docs/source/rtc.mdx gives "typical values
        # 8-12" and warns that higher means smoother transitions but LESS
        # reactivity; both the RTC and SmolVLA docs use 10 alongside
        # max_guidance_weight=10.0 (optimal for 10-step flow matching). This was
        # briefly set to 25 on 2026-08-08 by reasoning rather than by reading,
        # before the residual jitter was traced to the policy itself rather than
        # to chunk splicing. Do NOT pair with --interpolation_multiplier: 90Hz
        # plus 3x interpolation was tried on hardware and the arm stopped
        # moving entirely.
        f"--inference.rtc.execution_horizon={args.execution_horizon}",
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
        f"--dataset.reset_time_s={args.reset_time}",
        "--dataset.push_to_hub=false",
    ]
    if args.resume:
        # --episodes is how many MORE to record this session, not the total:
        # the episodic strategy counts from zero each run and appends.
        cmd.append("--resume=true")
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

    p = sub.add_parser("grid", help="print the start-pose grid for an app recording session")
    p.add_argument("--episodes", type=int, default=50)
    p.set_defaults(func=cmd_grid)

    p = add_dry_run(sub.add_parser("build", help="convert app recordings into a LeRobot dataset"))
    p.add_argument("--name", default="circle_insert_app", help="output dataset name")
    p.add_argument("--manifest", default="outputs/episode-review/curated-episodes.txt")
    p.add_argument("--episodes-root", default="data/local/episodes")
    p.add_argument("--task", help=f"instruction for these episodes (default: {CONFIG['task']!r})")
    p.add_argument(
        "--trim",
        action="store_true",
        help="drop the motionless lead-in and tail of each take (as circle_insert_50ep_trimmed was built)",
    )
    p.set_defaults(func=cmd_build)

    p = add_dry_run(sub.add_parser("replay", help="replay a recorded episode on hardware (safety gate)"))
    p.add_argument("--dataset", default="circle_insert")
    p.add_argument("--episode", type=int, default=0)
    p.set_defaults(func=cmd_replay)

    p = add_dry_run(sub.add_parser("train", help="fit a policy on recorded demonstrations"))
    p.add_argument("--dataset", default="circle_insert")
    p.add_argument("--policy", default="act", choices=["act", "smolvla", "diffusion"])
    p.add_argument("--base", help="fine-tune from a pretrained base, e.g. lerobot/smolvla_base")
    p.add_argument("--steps", type=int, default=20000,
                   help="20000 is the SmolVLA guide's figure; the scheduler auto-scales to it")
    p.add_argument("--batch-size", type=int, default=32,
                   help=("32, not lerobot-train's default of 8. Every checkpoint this project "
                         "made before 2026-08-08 silently used 8 while the SmolVLA guide uses 64. "
                         "Batch 64 was measured at ~3.0s/step on the 12GB 5070 -- VRAM thrashing, "
                         "2x worse than linear. Above ~1.2s/step, come down."))
    p.add_argument("--lora", action="store_true",
                   help="parameter-efficient fine-tuning: small adapter instead of a 7.4GB checkpoint")
    p.add_argument("--lora-r", type=int, default=64, help="LoRA rank; higher is closer to full fine-tuning")
    p.add_argument("--lora-alpha", type=int, default=64, help="LoRA scaling (scaling = alpha / r)")
    p.add_argument("--lr", type=float, default=1e-3,
                   help="LoRA wants ~10x the full-fine-tune LR (1e-4 -> 1e-3); only applied with --lora")
    p.add_argument("--device", default="mps")
    p.add_argument("--job", help="job name (default: <policy>_<dataset>_<steps>)")
    p.set_defaults(func=cmd_train)

    p = add_checkpoint_args(add_dry_run(sub.add_parser("dagger", help="human-in-the-loop correction collection")))
    p.add_argument("--episodes", type=int, default=10, help="correction episodes to collect")
    p.add_argument("--episode-time", type=int, default=60)
    p.add_argument("--record-autonomous", action="store_true",
                   help="also record the autonomous frames, not just the correction windows")
    p.add_argument("--inference", default="rtc", choices=["rtc", "sync"])
    p.add_argument("--execution-horizon", type=int, default=10)
    p.add_argument("--device", default="mps")
    p.add_argument("--tag", default="latest", help="names the recorded correction dataset")
    p.add_argument("--rehearse", action="store_true",
                   help="practise the key sequence with no robot connected")
    p.add_argument("--raw", action="store_true",
                   help="show LeRobot's unfiltered output instead of the status display")
    p.set_defaults(func=cmd_dagger)

    p = add_dry_run(sub.add_parser("merge", help="combine demonstrations and corrections into one dataset"))
    p.add_argument("sources", nargs="+", help="dataset names under data/local/datasets")
    p.add_argument("--into", required=True, help="name of the merged dataset to write")
    p.set_defaults(func=cmd_merge)

    p = add_checkpoint_args(add_dry_run(sub.add_parser("eval", help="autonomous closed-loop rollout on real hardware")))
    p.add_argument("--episodes", type=int, default=10)
    p.add_argument("--episode-time", type=int, default=30)
    p.add_argument("--reset-time", type=int, default=15,
                   help="seconds between episodes to reposition the piece")
    p.add_argument("--device", default="mps")
    p.add_argument("--tag", default="latest", help="names the recorded rollout dataset")
    p.add_argument("--inference", default="rtc", choices=["rtc", "sync"],
                   help="rtc keeps the control loop at 30Hz; sync drops it to ~3Hz on this machine")
    p.add_argument("--execution-horizon", type=int, default=10,
                   help="actions committed per chunk before RTC splices in the next one (docs: 8-12)")
    p.add_argument("--resume", action="store_true",
                   help=("append to an existing rollout dataset (--episodes = how many more). "
                         "Broken for local-only datasets: LeRobotDataset.resume queries the HF "
                         "Hub for a version and 401s. Use a fresh --tag instead."))
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
