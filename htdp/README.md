# Human-Task Dataset Pipeline (v0.2)

Consent-based human-task dataset pipeline for robotics. Filesystem-only spine with a CLI:
ingest real LSL/XDF + video + EEG recordings (or synthesize sessions), validate, process to
Parquet, QC, package consent-gated releases, export to BIDS / ROS 2, catalog, and replay on a
robot arm via inverse kinematics.

> **🤖 Robot-learning sim loop → [docs/SIM_LOOP.md](docs/SIM_LOOP.md)**
> A Franka Panda picks-and-places from a single camera image under true contact physics — a
> from-scratch MuJoCo + LeRobot + ACT imitation loop (scripted physics teacher → demos →
> transformer policy → closed-loop friction-grasp rollout). The visuomotor policy hits 87.5%
> (95% CI [74%, 95%], n=40) held-out from pixels alone, matching a state-based policy that was
> handed the object coordinates. This is the headline engineering work.

![Visuomotor policy: pixels to a friction grasp](docs/demo/m25_visuomotor_rollout.gif)

Narrated walkthrough (captions): [`docs/demo/m25_visuomotor_rollout_narrated.mp4`](docs/demo/m25_visuomotor_rollout_narrated.mp4)

## Install

```bash
uv sync                      # core
uv sync --extra ingest       # + pyxdf  (htdp ingest)
uv sync --extra replay       # + mujoco/mink/daqp  (htdp replay, replay-ik)
uv sync --extra rosbag       # + rosbags  (htdp export-release-rosbag)
uv sync --extra dev          # + pytest/ruff/mypy
```

Optional extras stay optional — core install and core tests require none of them.

## Pipeline

```bash
# --- get raw sessions ---
htdp synth --out data/raw                                  # synthetic session (seeded)
htdp ingest input.xdf ingest.json --out data/raw/<id>      # ingest an LSL .xdf recording
htdp ingest-video data/raw/<id> clip.mp4 video.json        # augment a session with video

# --- core pipeline (cwd anchored at data/) ---
htdp validate data/raw/<id>                                # schema + structure + checksums
htdp process  data/raw/<id>                                # raw CSV -> Parquet
htdp qc       data/processed/<id>                          # QC report (pass/warn/fail)
htdp package  <id...> --release <name> --profile <profile> # per-session consent-gated release

# --- export ---
htdp export-bids          data/raw/<id> out/               # single-session Motion/EEG BIDS
htdp export-release-bids  data/releases/<name> out/        # multi-subject BIDS
htdp export-release-rosbag data/releases/<name> out/       # one rosbag2 (mcap) per session

# --- catalog ---
htdp catalog          data/raw catalog.parquet             # one row per session
htdp catalog-query    catalog.parquet --protocol P --modality video --start-after 0
htdp catalog-releases data/releases releases.parquet       # one row per release

# --- replay ---
htdp replay    data/releases/<name>                        # MuJoCo mocap-body replay
htdp replay-ik data/releases/<name> --out traj.csv --orientation-cost 1.0  # IK on a 6-DOF arm

# --- teleop-replay demo (M1) ---
htdp sim-task --video docs/demo/m1_pick_place.mp4          # human-motion -> Franka Panda pick-and-place
```

## Teleop-replay demo (M1)

`htdp sim-task` closes the loop in simulation: a recorded wrist trajectory is retargeted
through differential IK onto a **Franka Emika Panda** arm in MuJoCo, which picks up an object
top-down and places it on a target — the teleoperation-style data-collection paradigm
(ALOHA / GELLO / LeRobot), driven by human motion. Headless and deterministic; `--video`
renders an MP4.

![M1 pick-and-place demo](docs/demo/m1_pick_place.gif)

## Imitation policy (M2)

```bash
htdp gen-demos   --out demos --n-train 200 --n-test 25   # scripted teacher -> LeRobot-format demos
htdp train-policy --demos demos --out policy.pt --steps 5000   # compact ACT, PyTorch/MPS
htdp eval-policy  --demos demos --policy policy.pt        # autonomous rollout vs IK baseline
```

A compact action-chunking transformer (ACT) is trained on scripted demonstrations and then
drives the Franka **autonomously closed-loop** in MuJoCo, generalizing to unseen cube
positions. On 25 held-out positions the learned policy reaches **100% success
(place_error 0.0025 m)**, matching the scripted-IK baseline. Scope: held-out positions are
drawn from the **same 10×10 cm region** as training (in-distribution interpolation), and
execution is **kinematic** (the policy reproduces the teacher's gripper trajectory; no actuator
dynamics). State-based observations (joint + object poses); demos are stored in LeRobotDataset
format. Visuomotor (pixels) is the M2.5 extension.

## Portfolio summary

One-line version for a CV / LinkedIn:

> Built a from-scratch visuomotor imitation-learning pipeline (MuJoCo + LeRobot + ACT
> transformer): a Franka Panda picks-and-places from a single camera image under true contact
> physics, hitting 87.5% held-out success (n=40, 95% CI [74%, 95%]) with zero privileged state —
> including a domain-randomization robustness study (100% under novel scene randomization) and
> an honest out-of-distribution generalization measurement (60% outside the training region).

Full write-up, war stories, and limitations: [docs/SIM_LOOP.md](docs/SIM_LOOP.md).

## Notes

- The CLI is anchored to a `data/` working directory: `process`/`package` read and write
  `data/raw`, `data/processed`, `data/releases` relative to the current directory.
- Consent filtering is **per-session** — a disallowed modality is dropped only from the
  sessions whose consent forbids it; the rest keep it.

See [CHANGELOG.md](CHANGELOG.md), [docs/ROADMAP.md](docs/ROADMAP.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md),
and [docs/ETHICS_AND_CONSENT.md](docs/ETHICS_AND_CONSENT.md).
