# Native LeRobot learning loop — design

**Date:** 2026-08-08
**Status:** approved, not yet implemented
**Supersedes (for the learning loop only):** the custom collection/eval path described in
`2026-08-05-episode-lerobot-dataset-design.md` and `2026-08-05-smolvla-shape-sort-finetune-design.md`.
The app-side recorder and Sequence Studio remain in the product; they stop being the
training-data and evaluation path.

## Goal

One task — inserting the circle piece into its matching hole — succeeding at a
**measurable rate**, with a full iteration cycle (record → train → evaluate) under two
hours instead of multiple days.

Prompt-following across multiple tasks is explicitly **out of scope for this spec**. It
returns once single-task success is real; see "Deferred" below.

## Why the current loop is slow

Measured from this project's own artifacts:

| Stage | Real cost |
|---|---|
| Recording 90 episodes | ~42 min total robot time (median 27 s/episode) |
| Dataset build | minutes |
| Training 30 k steps on the RTX 5070 | ~2 h, unattended |
| Evaluating one checkpoint | hours of hand-work for seconds of robot behaviour |

Data and training are cheap. **Evaluation is the whole bottleneck**, and it is manual:
screen-scrape two camera frames from Chrome → paste joint-state JSON on a CLI →
`closed_loop_step.py` writes a chunk → load into Sequence Studio → preview → arm → play →
repeat. At `durationMs: 500` per action step, one 50-step chunk is 25 s of playback for
1.7 s of modelled trajectory.

The compounding cost is the missing metric. With no success rate, every data and training
decision is a guess — which is exactly why the 29 → 55 episode expansion was inconclusive
(held-out MAE went 3.95 → 5.32, but on a *different* held-out split, and MAE is not task
success).

### Defects the current path bakes in

1. **State is off-distribution at inference.** `build_lerobot_dataset.py` sets
   `observation.state[t] = action[t-1]` — the previous *commanded target*, because the
   browser recorder never captures measured follower position
   (`metadata.json`: `actions.type = "commanded_joint_target"`). At inference the scripts
   are handed live joint state instead.
2. **Actions are stale and quantised.** Recorded at `sampleRateHz: 20`, nearest-hold
   upsampled to 30 fps video — every action is a staircase, ~1.5 frames behind.
3. **Playback is 15× time-dilated.** `run_policy_prompt.py:138` and
   `closed_loop_step.py:98` emit `durationMs: 500` per step against a policy trained at
   33 ms. Positions are right; rollout dynamics never match training.
4. **The language channel is a no-op.** `build_lerobot_dataset.py:33` hardcodes a single
   `TASK_STRING` across all 55 episodes. A single task string cannot teach language
   conditioning, so the observed "prompt phrasing matters a lot" was out-of-distribution
   sensitivity, not comprehension.
5. **Data density is wrong for the failure.** The grasp is 1–2 s of a 27 s episode —
   about 5 % of frames land on the phase that actually fails.

## Feasibility verified 2026-08-08

- `lerobot-record`, `lerobot-replay`, `lerobot-rollout`, `lerobot-eval` are all present in
  lerobot **0.6.1**, in both `~/lerobot/.venv` and the project's `.venv-lerobot`.
- **`scservo_sdk` imports fine in both venvs.** `AGENTS.md`'s note that `.venv-lerobot`
  lacks `feetech-servo-sdk` is stale and should be corrected.
- `lerobot-find-cameras opencv` reaches both task cameras directly at 1920×1080 — no
  browser involved:
  - **index 1 = overview** (top-down: arm + puzzle board)
  - **index 0 = wrist** (piece + "circle" hole)
  - index 2 = MacBook FaceTime, index 3 = dead
- Serial ports present: follower `/dev/cu.usbmodem5AE60582701`, leader
  `/dev/cu.usbmodem5B140329561`.
- Calibration profiles present: `robots/so_follower/white.json`,
  `teleoperators/so_leader/black_20260801.json`.

## Architecture

Four components, each replacing a hand-built one.

### 1. Collection — `lerobot-record`

```
lerobot-record \
  --robot.type=so100_follower \
  --robot.port=/dev/cu.usbmodem5AE60582701 \
  --robot.id=white \
  --teleop.type=so100_leader \
  --teleop.port=/dev/cu.usbmodem5B140329561 \
  --teleop.id=black_20260801 \
  --robot.cameras='{"overview":{"type":"opencv","index_or_path":1,"width":1280,"height":720,"fps":30},
                    "wrist":{"type":"opencv","index_or_path":0,"width":1280,"height":720,"fps":30}}' \
  --dataset.repo_id=local/circle_insert \
  --dataset.single_task="Insert the circle piece into its matching hole." \
  --dataset.episode_time_s=20 \
  --dataset.reset_time_s=10 \
  --dataset.num_episodes=50
```

This resolves defects 1–3 by construction: measured follower position as
`observation.state`, leader command as `action`, both at a true 30 Hz. It also brings
keyboard re-record of a bad episode mid-session and a built-in per-episode reset window.

Camera keys stay `overview` / `wrist`, consistent with existing project naming.

Two rules learned during step 0:

- **Never pass `--robot.max_relative_target` to `lerobot-record`.** The clamp is applied
  relative to the follower's current position and `lerobot-record` logs the **post-clamp**
  value as `action`, so it silently corrupts action labels whenever the leader moves
  quickly. It belongs on `lerobot-rollout` only; while teleoperating, the hand on the
  leader is the safety mechanism.
- **Recording is run by the human, in their own terminal, not through an agent.** It is
  interactive and human-paced: the operator needs the live `Recording episode N` cue and
  the keyboard controls for re-recording a bad take. Two throwaway takes driven by an
  agent produced 1,499 frames of a motionless arm purely because the operator could not
  see when the window was open.

### 2. Recording protocol

Diversity has now failed twice when left to intent — the 26-episode batch of 2026-08-07
was recorded specifically for start-position variation and delivered essentially none.
Enforce it structurally instead:

- **A fixed 3-position × 4-rotation grid** marked on the paper, cycled in order across
  episodes. Written down, not remembered.
- **A second, grasp-only dataset**: ~30 episodes of ~5 s each, arm starting just above the
  piece, covering reach → grasp → lift only. About 5 minutes of recording that puts 100 %
  of its frames on the failing phase instead of ~5 %.
- Train on the union of both datasets.

Trade-off, stated explicitly: mixing segment types biases the state distribution toward
"already near the piece". This is intended — that is where the policy fails — but if
full-task rollouts regress while grasps improve, the mix ratio is the first thing to
adjust.

### 3. Training — ACT first, on the Mac

With language out of scope, SmolVLA is 450 M parameters conditioned on a constant string.
ACT (~80 M) is the standard SO-100 single-task choice and trains locally on MPS.

The real reason is diagnostic, not cost: today there is no way to tell "the data does not
support the motion" apart from "the VLA is undertrained". A fast ACT run answers the first
question directly.

The Windows RTX 5070 box stays available for SmolVLA once multi-task work resumes; its
setup docs remain valid. **Push the dataset to a private HF repo** so the manual 1.3 GB USB
shuttle between machines disappears.

### 4. Evaluation — `lerobot-rollout`

Autonomous closed-loop execution at 30 Hz on real hardware, N episodes, capped by
`episode_time_s`, with the rollouts recorded as a dataset for review.

**The metric becomes k/N task success, human-labelled per rollout.** Held-out MAE is
retained only as a cheap secondary signal, and only ever compared across checkpoints on an
identical frozen held-out split — the 29-ep vs 55-ep comparison violated this and should
not be cited as evidence.

## Safety

This is the first time the arm moves autonomously, outside the app's Arm Motion gate. That
is a new risk class for this project and gets explicit handling:

- `lerobot-replay` of a known-good recorded episode must round-trip **before** any policy
  drives the arm.
- Human hand on the power switch for every rollout; clear workspace.
- Capped `episode_time_s` so a diverging rollout terminates on its own.
- Reduced maximum velocity for the first rollout session.
- Before any teleoperation start, the leader must be physically positioned to roughly
  match the follower's current pose. A large commanded jump caused a real wrist-roll
  overload fault on 2026-08-05.

## What is retired

Retired as the **training-data and evaluation path** (files kept in the repo, archived):

- `robot_learning/build_lerobot_dataset.py`
- `robot_learning/generate_episode_contact_sheets.py`
- `robot_learning/closed_loop_step.py`
- `robot_learning/run_policy_prompt.py`
- the in-app episode recorder as a source of training data

`robot_learning/eval_smolvla_held_out.py` is kept for the secondary MAE signal.

**Unchanged:** the app remains the human-facing control UI, 3D twin, and Sequence Studio.
The 55-episode dataset and every existing checkpoint are archived, not deleted.

## Known frictions

- Chrome and LeRobot cannot hold the serial ports or cameras simultaneously. The Chrome
  tab must be **fully closed**, not merely navigated away from, to release a port.
- Two 1280×720 camera streams may exceed comfortable MPS memory for ACT; downscaling in
  the dataset config is the fallback.
- Camera indices are not guaranteed stable across reboots or USB re-plugs. Re-run
  `lerobot-find-cameras opencv` if a recording looks wrong, and confirm index 1 is the
  overview before a session.
- The app's `JointState` degrees/percent convention differs from LeRobot's native
  tick-derived convention. Datasets recorded by `lerobot-record` are in LeRobot's
  convention, so the existing 55-episode dataset and the new one are **not** mixable, and
  checkpoints trained on the new data will not feed Sequence Studio without a conversion
  that this spec does not build.

## Tooling

`robot_learning/loop.py` wraps the three stages so a cycle is three short commands rather
than hand-assembled 15-flag lines. All hardware ids, ports, camera indices and conventions
live in one `CONFIG`. It builds and execs LeRobot's own CLIs and prints each command first,
so anything it does can be run by hand; `--dry-run` prints without executing.

```
python robot_learning/loop.py record --episodes 50           # full task, prints the pose grid
python robot_learning/loop.py record --episodes 30 --grasp-only
python robot_learning/loop.py train  --steps 40000           # ACT on MPS
python robot_learning/loop.py eval   --checkpoint <path> --episodes 10
```

`robot_learning/probe_native_hardware.py` is the read-only pre-flight check: it connects to
the follower and both cameras and reads one observation without ever sending an action.

## Sequencing

**Step 0 — hardware go/no-go.** Results, 2026-08-08:

1. **PASS** — read-only observation probe: follower reachable, both cameras returning
   `(720, 1280, 3)`, real encoder readings.
2. **PASS** — `lerobot-teleoperate` mirrored leader to follower, clean 30 Hz for 20 s, no
   faults, torque released cleanly on disconnect.
3. **PARTIAL** — `lerobot-record` plumbing proven (600 and 899 frames, correct feature
   schema, two 1280×720 mp4s, `robot_type=so_follower`), but both takes captured a
   motionless arm; see the second rule above. Needs one operator-driven take with real
   motion.
   - **Defect 1 confirmed fixed**: commanded vs. measured elbow held a constant ~5–6 unit
     gap (steady-state droop under gravity). Under the old pipeline that number is 0 by
     construction, because state *was* the command. The state channel is genuinely the
     encoders.
   - Still unverified: that state and action diverge *dynamically* under motion.
4. **NOT RUN** — `lerobot-replay` one recorded episode back.

**Step 1** — record 50 full-task episodes on the position grid.
**Step 2** — record ~30 grasp-only episodes.
**Step 3** — train ACT on the union.
**Step 4** — `lerobot-rollout` 10 episodes → baseline success rate.
**Step 5** — iterate on *data* against what the rollouts show failing, not on
hyperparameters.

## Success criteria

- Step 0 round-trips: a recorded episode replays on hardware.
- A full record → train → evaluate cycle completes in under two hours of wall time, with
  under ~45 minutes of human attention.
- A baseline k/N success rate exists for the circle-insert task — any number, including
  zero. Having the number is the deliverable; improving it is the next cycle.

## Deferred

- **Multi-task prompt following.** Returns after single-task success. The 34 uncurated
  2026-08-05 episodes are a genuinely different task (lifting a piece off the board) and
  are free second-task data when that time comes.
- **The safety-gated autonomous runtime** from `2026-08-03-policy-hardware-control-design.md`
  (policy server, dead-man switch, per-tick clamps). `lerobot-rollout` plus the manual
  safeguards above covers supervised evaluation; that spec's fuller runtime is still not
  started.
- **Converting new-convention checkpoints back into Sequence Studio sequences.**
