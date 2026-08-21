# SO-ARM100 Runbook — current state

This is the single canonical "what's true right now" doc. Unlike the dated
`docs/linux-session-handover-*.md` / `docs/handover-*.md` files (which are
point-in-time session logs, kept for history), **this file gets edited in
place** whenever a fact here goes stale. If you find something wrong here,
fix it here directly rather than writing a new dated doc.

`AGENTS.md`'s "Verified hardware setup" section predates the machine move
described below and still lists Mac ports/paths — treat this file as the
override for anything hardware-related.

Last verified: 2026-08-17.

## Machine

This Linux workstation is physically colocated with the robot (moved here
2026-08-11) and is also, via dual-boot on the same NVMe drive, the Windows
GPU training box — `data/local/datasets/` and `outputs/train/` need zero
copying between the two. There is no native Python environment on this
machine; everything runs through Docker.

## Docker images

- **`lerobot-train:latest`** (built from `Dockerfile.lerobot`) — Python 3.12,
  lerobot 0.6.1, CUDA. Use this for everything real-hardware or
  checkpoint-related: eval, dagger, record, merge, build, train.
- `real-robot:latest` — older, Python 3.10, lerobot 0.4.1. **Cannot load
  checkpoints trained with lerobot 0.6.1** (config/field mismatches). Don't
  use it for anything that touches a trained checkpoint.
- `leisaac-sim:latest` — Isaac Sim only (replay validation, synthetic data
  generation). Unrelated to real-hardware eval.

## Hardware

- Follower arm: id `white`, USB adapter serial **5AE6058270**.
- Leader arm: id `black_20260801`, USB adapter serial **5B14032956**.
- **Identify the arms by adapter serial, never by `/dev/ttyACM*` number.** The
  numbering follows plug order and flipped three times in six days (08-11,
  08-12, 08-17). Any node number written in this file is a snapshot, not a fact.
  `./preflight.sh` (or `./verify_ports.sh`) resolves the mapping by serial and
  checks it against `CONFIG` in `robot_learning/loop.py`. As of 2026-08-17 the
  follower is `ttyACM0` and the leader `ttyACM1` — the reverse of 08-12.
- Only `loop.py CONFIG` names ports; `teleop_check.sh` and `home_arm.py` read
  them from it. Never re-type a port into a wrapper script — two of them held a
  stale mapping after the 08-17 flip, and running one would have driven the
  leader through the follower's config (the 2026-08-12 Overload error).
- Cameras: overview=`/dev/video0`, wrist=`/dev/video2`. Both need
  `"fourcc": "MJPG"` in the camera config or they cap out at 10fps instead
  of the requested 30fps (USB bandwidth limit of uncompressed YUYV).
- **Calibration files live on the HOST**, not in this repo:
  `~/.cache/huggingface/lerobot/calibration/{robots/so100_follower,teleoperators/so100_leader}/*.json`.

## Before every session: `./preflight.sh`

**Run it first, every time, and again after anything touches the hardware.**

Hardware state is not like software state. Software state is reconstructible — a
checkout and a rebuild give you a known starting point. Hardware state is persistent,
invisible to git, owned exclusively by one process at a time, and *changed by the act of
touching it*. Nothing in this repository can tell you what is currently in the servos'
EEPROM or who holds a serial port. You have to ask the hardware.

```bash
./preflight.sh            # GO / NO-GO, read-only, ~10 seconds
```

It establishes the four facts every other conclusion depends on:

| check | why it matters |
|---|---|
| Port ownership — containers **and** host processes | one owner per port; two tools that each work alone will break each other |
| Device identity by USB adapter serial | `ttyACM` numbering follows plug order and flipped 3x in 6 days |
| Servo calibration registers vs the calibration file | a `c` at lerobot's prompt rewrote these once, invisibly |
| Camera nodes present | node numbers move on replug |

It is read-only, never writes a servo register, and **refuses to open a port another
process owns** (reports SKIPPED and NO-GO instead) — a check that perturbs what it
measures is not a check. Every value is read twice and reported only if both reads
agree, otherwise `UNSTABLE`; replies are validated for header, id and payload length
before their bytes are believed.

Run it:

- at the start of every session
- after any replug of an arm or a camera
- after anything lerobot connects to (it can rewrite calibration)
- before switching between the React app and the Python stack
- **before forming any theory about a misbehaviour**

That last one is the expensive lesson from 2026-08-17. Five hours went into theories
about packet echo, DTR/RTS, stale Chrome port handles and USB resets, while all four
primary facts above were unverified or drifting underneath. The check costs ten seconds.
Its absence cost five hours.

### Two rules that follow

**One stack owns a port at a time.** Before any Python hardware command, disconnect
hardware in the app and confirm Chrome no longer owns `/dev/ttyACM*`; if there is any
doubt, quit Chrome completely. Before connecting in the app, Ctrl-C any teleop and
confirm `docker ps` is empty. A real ownership conflict produces `Failed to open serial
port`, `Errno 16 Device or resource busy`, or lerobot's `Could not connect on port`.
Do not automatically classify Chrome's `The device has been lost` as an ownership
conflict: on 2026-08-17 that message was reproduced with no competing owner and was an
app connection-sequencing regression (see "React app WebSerial" below).

**At lerobot's calibration prompt, press ENTER — never `c`.** `c` runs a fresh
calibration and writes newly measured values. Interrupted before saving, it leaves every
calibration file on disk at its old values while the hardware has drifted away from
them — and everything downstream then reports a mismatch that reads exactly like a
software bug.

**LeRobot 0.6.1's existing-file restore is not durable on this arm.** Its reconnect
path calls `write_calibration()` while the Feetech EEPROM `Lock` register is still 1,
so the expected values read back correctly from live registers but revert after USB
power is removed. Its default `bus.disconnect()` also calls `disable_torque()`, which
writes `Lock=0` again. A durable repair must do this exact sequence:

1. `disable_torque()` (torque off and `Lock=0`) and verify both.
2. Write every saved `Homing_Offset`, `Min_Position_Limit`, and
   `Max_Position_Limit`; read every value back twice.
3. Write and verify `Lock=1` on all six servos.
4. Call `disconnect(disable_torque=False)` so disconnect does not unlock them again.
5. Physically replug the adapter, then run `./preflight.sh`. Only values that still
   match after that power cycle are proven to be in EEPROM.

For follower `white`, the durable values verified after a physical replug on
2026-08-17 are:

| servo | min | max | homing offset | Lock |
|---|---:|---:|---:|---:|
| S1 | 715 | 3253 | -1317 | 1 |
| S2 | 888 | 3288 | -960 | 1 |
| S3 | 774 | 3005 | -851 | 1 |
| S4 | 914 | 3229 | -685 | 1 |
| S5 | 0 | 4095 | 453 | 1 |
| S6 | 2002 | 3507 | -1647 | 1 |

### React app WebSerial

The proven follower connection sequence is deliberately manual:

1. Click **Connect Hardware** and explicitly select the attached follower adapter.
2. Let the port open without sending identification traffic.
3. Click **Verify Servos**; only after verification may motion be armed.

Do not reintroduce session-start auto-connect or an immediate calibration probe. Commit
`c5039fe` added both, and the app began failing immediately after `open()` with Chrome's
`The device has been lost`. Chrome 151, the 7.0.0-28 kernel, the USB topology, and the
adapter were unchanged from a successful 30 Hz recording on 2026-08-11; the kernel log
showed normal enumeration and no reset/error, and Python still read the same bus at
1 Mbaud. Restoring the earlier manual open-then-verify sequence immediately restored
recording and produced 60 new episodes. The exact Chrome/CDC-ACM timing race is not
proven, but the regression boundary is.

Both CH adapters report the same VID:PID (`1a86:55d3`), so the browser's product name
does not distinguish leader from follower. Keep only the intended arm attached while
granting a new browser port if the chooser is ambiguous. Stream errors must clear
verification, lock motion, release reader/writer locks, and close the failed port; they
must not silently leave the UI in a connected state or delete the browser permission.

## Running anything that touches the real robot

**Always go through `./hw_docker.sh <command>` — never hand-write a
`docker run` line for hardware.** It is the single place the device/mount
flags live. If a port remaps or a flag needs to change, fix it there once;
every script that calls it picks up the fix automatically.

```bash
./hw_docker.sh python robot_learning/loop.py eval --checkpoint <path> --episodes 20 --tag <tag>
./hw_docker.sh python robot_learning/loop.py dagger --checkpoint <path> --episodes 10 --tag <tag>
```

Existing wrapped scripts (all just call `hw_docker.sh` with fixed args):
`run_eval_a.sh`, `run_eval_b.sh`, `run_eval_c.sh`, `run_eval_020000.sh`,
`run_dagger_c.sh`. Copy one of these for a new eval rather than writing a
fresh `docker run` — that's exactly how the calibration mount got dropped
on 2026-08-14 (an ad-hoc command omitted it, causing a silent full
recalibration and an invalid eval result).

## Running the tests

**`./run_tests.sh`** — every `tests/test_*.py`, in `lerobot-train:latest`.
`./run_tests.sh <pattern>` filters by filename. There is no native Python env
on this machine (no numpy outside the images), so tests only ever run in a
container; this is the non-hardware counterpart to `hw_docker.sh`.

The `tests/smoke_*_isaac.py` files boot Isaac and are **not** in that run.
Go through **`./sim_docker.sh <script> [args]`** for those and for anything
else that needs `leisaac-sim:latest`:

```bash
./sim_docker.sh tests/smoke_lighting_isaac.py     # writes lighting_smoke/*.png
./sim_docker.sh tests/smoke_wrist_camera_isaac.py
```

Never hand-write that `docker run` line. The full SO-101 new-calibration USD
composition is vendored at `assets/isaac/so101_new_calib/`; simulation no longer
depends on a personal Downloads path or an extra `/Users` bind mount.

**`./gpu_docker.sh <command>`** is the third wrapper: `lerobot-train:latest`
with the GPU and the repo mount but **no `--device` flags at all**, for offline
policy inference, held-out evaluation, dataset analysis, and training. Use it
instead of the bare `docker run` line this file used to spell out. Because it
cannot open `/dev/ttyACM*` or `/dev/video*`, nothing run through it can take
the serial port away from a live bench.

```bash
./gpu_docker.sh python robot_learning/eval_smolvla_held_out.py --checkpoint <path> ...
./gpu_docker.sh python robot_learning/diagnose_policy_chunk.py --checkpoint <path>
```

## Looking at the scene

**`./view_scene.sh`** opens the sim scene in a window with a camera you can
fly — the same scene `export_lerobot_dataset.py` builds, so if it looks wrong
there it is wrong in the data. `--light-scale 0.75` / `1.15` show the ends of
the randomization range. It is `sim_docker.sh` plus X11 passthrough (kept
separate: the GUI flags and the Xauthority mount are needless for the headless
runs, which is everything else).

**`./render_board.sh`** is the headless counterpart: the board from three
angles (`top`, `oblique`, `grazing`) written to `board_views/*.png`, no X server
and no person at the keyboard needed. Use it when you are checking one specific
piece of geometry, or over ssh. The `grazing` view in particular is what shows
whether a piece is IN the board or ON it — which no overhead frame can.

The scene gate's side-by-side is one fixed camera and will not show you
everything. The missing knobs (below) were spotted in it, but only because
someone looked; the automated checks all passed. The pocketless board and the
teal knob were not visible in it at all — those needed the close-up renders.

## One scene, one builder

`scene_setup.build_scene(world, scene_cfg)` is the only supported way to put the
scene into a World. Nothing may call `add_table_and_object` / `add_board` /
`add_lighting` directly, and `tests/test_scene_is_built_whole.py` fails if
anything does.

This is not tidiness. Until 2026-08-16 `scripts/export_lerobot_dataset.py` — the
script that renders the pixels a policy actually trains on — called
`add_table_and_object` and `add_lighting` and **never called `add_board`**. Every
synthetic frame it ever exported showed the peg with nothing to insert it into,
while `scripts/generate_synthetic.py` simulated those same episodes *with* a
board. Nothing failed; the scene gate passed throughout, because the gate renders
its own scene — it built the board correctly, looked right, and then approved a
*config*, attesting to a scene the exporter never built.

That is the Dataset C defect (`src/bridge/scene_gate.py`) recurring one script
over, and no amount of care inside the gate can catch it: a gate cannot see what
another script assembles. Making the scene one function is what makes "the
approved scene" and "the exported scene" the same object.

The gate's fingerprint covers `configs/simulation.yaml`, `configs/robot_mapping.yaml`,
the complete vendored robot USD composition, and the code that turns them into a
picture (`src/isaac/scene_setup.py` and `src/isaac/camera_capture.py`). Whole-file
hashes mean even a comment-only edit invalidates an approval: there is no reliable
way to infer which scene edit changes pixels without rendering and looking, which
is exactly what the approval attests to.

It was config-only until 2026-08-16, and that gap was not theoretical — the board
was rebuilt (pockets cut, pieces reshaped and reseated, knob materials rebound)
entirely in `scene_setup.py`, and an approval taken beforehand would have been
carried straight across it. Approvals written before that day have no
`scene_sha256` and are refused by name.

## Re-planning a demo onto a moved object (IK + trajectory warping)

`src/kinematics/inverse_kinematics.py` and `src/augmentation/trajectory_warp.py`,
added 2026-08-16. Together they are what makes
`randomization.label_breaking.object_position` honest: displace the peg and
re-plan the joint trajectory so the actions reach where it now is, instead of
copying actions that reach where it used to be.

No library was needed. The arm is five revolute joints, `forward_kinematics`
already composes the chain, and damped least squares over a finite-difference
Jacobian is about a hundred lines.

**Task priority, not a weighted blend.** Position is the primary task and is
solved exactly; the gripper's approach direction is pushed through the nullspace
of position. Weighting the two against each other was tried first and is the wrong
shape for a 5-DOF arm — at an orientation weight of 0.12 the gripper held to 1–5°
but position error hit 3mm at a 5mm displacement and 33mm at 50mm, because five
joints cannot serve six objectives and least squares just picks a compromise.

**Do not expect joint-space proximity as well.** Position (3) plus approach
direction (2) consumes all five joints, so "the nearest configuration to the
demonstrator's" is not additionally available — solutions drift up to ~1.1 rad in
joint space while holding the tip and the approach. That is fine: what a warped
episode is judged on is the end-effector path, not the elbow.

**Measured envelope** (27 reach postures of `circle_grasp_v1` ep0, 8 directions):

| displacement | worst IK error | unconverged | gripper rotation (med / p90 / worst) |
|---|---|---|---|
| 10 mm | 0.48 mm | 0 | 2.0 / 4.9 / 6.2° |
| 20 mm | 0.50 mm | 0 | 3.3 / 9.8 / 12.6° |
| 30 mm | 0.48 mm | 0 | 6.0 / 15.1 / 19.0° |
| 40 mm | 1.81 mm | 4 | 6.8 / 19.7 / 25.2° |
| 50 mm | 5.23 mm | 9 | 9.6 / 24.9 / 32.6° |

`MAX_SAFE_DISPLACEMENT_M = 0.03`, and a larger request **raises** rather than
returning a quietly bad episode. Approach tilt runs about 0.2°/mm — half what
position-only IK gave.

**Warping fills in a neighbourhood; it does not move a demo across the table.**
Covering a 15cm workspace still needs real demonstrations spread across it. The
combination is the point: a grid of real placements every ~5cm, each warped ±3cm,
gives continuous coverage instead of a set of points.

Only the reach is displaced. The weight is 1.0 through the grasp, ramps to 0 by
the release, and is 0 after — because the peg moved and the board did not.
Displacing the whole episode uniformly would fix the grasp label and break the
insert label.

This is now wired into `scripts/generate_synthetic.py` behind the explicit
`--warp-object-position` flag. A per-parent pose sidecar is mandatory when more
than one parent is used; for the new top-camera set it is
`outputs/episode-review/parent-object-poses-topcam-59.json`. The old
`--allow-label-breaking` path is retired and raises immediately. Board pose remains
fixed because moving the insertion target still requires a board-aware warp.

## Synthetic data: label-preserving vs label-breaking

`scripts/generate_synthetic.py` records a new commanded trajectory whenever object
XY is randomized. It also records the measured simulated state, so the exporter can
convert both back to the real dataset's units; parent labels are never copied onto a
moved scene.

- **Safe, on by default:** mass, friction, initial joint pose (spent before
  the settle-to-frame-0 phase), camera noise, and peg yaw (the peg is a
  cylinder, so yaw is geometrically a no-op — this stops being true for a
  non-symmetric object).
- **Warped explicitly:** object XY. Use `--warp-object-position` and
  `--parent-object-poses`; the safe envelope is ±30mm and every generated episode
  must pass the IK quality gate.
- **Still inert:** board pose. Moving the insertion target without a second,
  board-aware warp would mislabel the insert phase.

### Controlled grasp and insertion outcome

The imported SO-101 fingers are shorter than the physical SO-100 contact geometry,
so raw Isaac contact cannot reproduce the recorded grasp. Synthetic replay uses a
transparent controlled model in `src/isaac/kinematic_grasp.py`: at grasp, a visual
proxy follows the measured gripper-relative pose while the rigid peg is parked; a
smooth endpoint correction accounts for the peg shifting inside the real fingers;
at release, the proxy remains seated at the measured circle target while the rigid
body stays parked. An earlier version handed the body back to PhysX, but a cylinder
placed on the 4mm blind-pocket backing intermittently tunnelled through it and fell
tens of metres; unrelated mass/friction draws then decided dataset eligibility.
Provenance calls the deterministic replacement `visual_proxy_controlled_seating` and
task outcomes `controlled_visual_proxy_endpoint`—it is an honest replay model, not a
claim of physics-validated contact. The exporter uses the exact same model.

Generation refuses an episode unless it demonstrates lift, transport, and final
seating. The 2026-08-17 smoke at
`data/synthetic/circle_insert_topcam_59_newcalib_smoke/` passed with 53.4mm lift,
0.76mm final XY error, 0.203mm maximum warp residual, 4.11° maximum orientation
change, and zero unconverged frames. It used the measured circle target
`[-0.04170, -0.16952]m`, derived from all 59 final overview frames.

```bash
./sim_docker.sh scripts/generate_synthetic.py \
  --dataset data/local/datasets/circle_insert_topcam_59_trimmed \
  --parent-episodes 0 \
  --parent-object-poses outputs/episode-review/parent-object-poses-topcam-59.json \
  --config configs/robot_mapping.yaml --scene-config configs/simulation.yaml \
  --warp-object-position --num-synthetic 1 --seed 0 \
  --out-dir data/synthetic/circle_insert_topcam_59_newcalib_smoke \
  --skip-scene-gate
```

`--skip-scene-gate` was appropriate only for that trajectory-only functional smoke
and is recorded in its provenance. The production scene was re-rendered against
`docs/reference/topcam-2026-08-17-episode-000-frame-000.png` and approved by Alex on
2026-08-17. `gate_status("configs/simulation.yaml")` is current; any scene config,
builder, camera-builder, robot mapping, or vendored USD change invalidates it.

The gate-enforced end-to-end exporter smoke is
`data/local/datasets/circle_insert_topcam_59_synth_export_final_smoke/`: one synthetic
episode, 320 frames at 30 FPS, both 1280x720 AV1 cameras, no flat frames, warp quality
gate passed (0.203mm maximum residual), and controlled-grasp provenance recorded as
`visual_proxy_rigid_body_parked`. Its `meta/scene_gate.json` records the approval;
no override was used.

### Synthetic-to-real ratio experiment

The production experiment is frozen in
`data/evaluation/sim_real_ratio_experiment.json`. It reserves 12 spatially distributed
real peg placements as a real-only holdout and uses the other 47 as training episodes
and Isaac parents. Never generate synthetic children from the held-out episodes.

The synthetic pool contains 94 passing episodes: exactly two children per training
parent. Nested prefixes produce matched S:R conditions of 0, 0.25, 0.5, 1, and 2
without changing the real training set. Use the same initialization, optimizer steps,
training seed, held-out set, and hardware protocol for every condition. This ratio
ablation—not one arbitrary mixed-data result—is the project's primary sim-to-real
measurement.

The shared training controls and exact master-dataset prefixes are frozen in
`configs/sim_real_ratio_training.json`. The file pins the LeRobot Docker image by
image digest, SmolVLA base by Hub commit and file hashes, seed, deterministic cuDNN,
optimizer/scheduler, camera mapping, batch size, and step count. Launch through the
validator so an incomplete master, changed base, or incorrect prefix fails before GPU
training starts:

On the current single RTX 5070 (12 GB), batch 32 exceeded VRAM during the smoke
test. Batch 24 is the validated shared setting; it uses about 8.5 GB during
training and takes roughly 3–3.5 hours per 20,000-step condition. The five-condition
sweep is therefore a research-cost decision of about 16–18 hours and should be
paused at condition boundaries when unattended time is limited. Do not silently
change the batch size within a ratio comparison.

```bash
# One 10-step end-to-end gate first.
python3 robot_learning/train_sim_real_ratio.py --condition real_only --smoke

# Then run every full condition sequentially from the same immutable base.
for condition in real_only synth_025x synth_050x synth_100x synth_200x; do
  python3 robot_learning/train_sim_real_ratio.py --condition "$condition"
done
```

The five selected master prefixes are respectively episodes `0:47`, `0:59`,
`0:71`, `0:94`, and `0:141`. The master contains no holdout data and training-time
evaluation stays disabled. Evaluate each saved checkpoint against the original
59-real-episode dataset and explicit experiment holdout:

```bash
./gpu_docker.sh python robot_learning/eval_smolvla_held_out.py \
  --checkpoint outputs/train/<condition>/checkpoints/020000/pretrained_model \
  --dataset-root data/local/datasets/circle_insert_topcam_59_trimmed \
  --repo-id local/circle_insert_topcam_59_trimmed \
  --experiment data/evaluation/sim_real_ratio_experiment.json \
  --device cuda --output outputs/evaluation/<condition>-held-out-mae.json
```

The next capability layer is the six-shape prompt-conditioned task described in
`docs/multi-shape-synthetic-learning-plan.md`. Canonical learned-policy skills live in
`configs/shape_sort_skills.json`; use `--skill place_circle` (or another registered
skill) with `robot_learning/run_policy_prompt.py` and
`robot_learning/closed_loop_step.py`. These are SmolVLA policy tools. The React
`/api/ollama/generate-sequence` endpoint remains a separate language-to-keyframe
planner and must not be presented as a trained visual skill.

Generation retries rejected warps until the requested number of passing episodes is
reached. For this first controlled pool, `--object-warp-scale 0.25` converts the
configured +/-30mm per-axis draw into +/-7.5mm per axis (10.61mm maximum radial
displacement), matching the measured reliable IK envelope. The applied scale, seed,
attempt index, actual offset, warp metrics, and task outcome are recorded per episode.

### Synthetic wrist camera

The wrist camera is rigidly tracked from the imported robot's `gripper` link. Its
current rest-pose calibration is position `[0.0, 0.0, 0.30]`, target
`[0.0, -0.28, 0.24]`, focal length 15mm. These numbers were selected against real
episode 0 at frames 0/40/151/200/245/300/319 so the board, circle, jaws, and loose or
carried peg remain in view. The old pose appeared correct at frame 0 only because
the exporter updated the tracked camera after rendering; later frames pointed into
the arm or went black. The exporter now updates the camera after physics and before
Replicator renders the timestep.

Validate after any wrist-camera change with both:

```bash
./sim_docker.sh tests/smoke_wrist_camera_isaac.py
./sim_docker.sh scripts/export_lerobot_dataset.py \
  --real-dataset data/local/datasets/circle_insert_topcam_59_trimmed \
  --synthetic-dir data/synthetic/circle_insert_topcam_59_newcalib_smoke \
  --synthetic-episodes 0 --config configs/robot_mapping.yaml \
  --scene-config configs/simulation.yaml \
  --output data/local/datasets/<fresh-smoke-name> \
  --repo-id local/<fresh-smoke-name>
```

Do not accept the wrist smoke's movement assertion alone: decode the exported wrist
video and inspect approach, grasp, carry, release, and retreat frames. The bug above
preserved a perfectly rigid camera-to-link offset while producing useless pixels.

### Lighting

`lighting:` in `configs/simulation.yaml` holds the scene lights, and
`randomization.light_intensity_scale` / `distant_light_yaw_deg` jitter them per
episode. Lighting is the one label-preserving axis that targets something
measured: the rollout workspace read V 151–164 against the demos' V 180–188.

Two things that were found by measuring rather than reading the code, and that
will silently break this axis again if forgotten:

- **The old hard-coded lighting (dome 2000 / distant 20000) blew the render
  out** — mean pixel 245/255 with **37% of pixels clipped**. Scaling intensity
  moved the frame mean by 0.1%, because there was no headroom. Every synthetic
  frame exported before 2026-08-15 was clipped like this. The base is now
  dome 250 / distant 625: mean ~167, nothing clipped, and the ±scale range
  produces a real 15% swing. `tests/smoke_lighting_isaac.py` asserts the
  bright end still doesn't clip.
- **A lighting change takes ~10 rendered frames to appear.** The USD attribute
  reads back immediately but the RTX render walks to the new exposure.
  `LIGHT_CONVERGENCE_STEPS` (15, in `src/isaac/scene_setup.py`) is the burn-in;
  the exporter refuses `--settle-steps` below it, since otherwise each
  episode's opening frames carry the *previous* episode's lighting — an
  artifact correlated with episode order.

`scripts/check_scene_gate.py` renders with these same lights as of 2026-08-15.
It previously used dome 1000 / distant 2500 at a different azimuth, so the
side-by-side a human approved was not lit like the frames that went to
training. **The gate approval is stale — re-run `./check_scene_gate.sh` and
look at the picture before generating or exporting anything.**

### The board, the peg, and the knobs

`docs/reference/toy.png` is a dimensioned drawing and is the authority for board
geometry. Three things it settles that the sim had wrong until 2026-08-15,
found by looking at the gate's side-by-side:

- **The knob.** 13mm across, 13mm tall, one centred on every piece. The gripper
  closes on the *knob*, not the piece — a 13mm post standing proud of a 50mm
  disc. The sim had no knobs at all and offered a bare 40mm cylinder, i.e. the
  wrong object at exactly the moment the policy decides how wide to close.
- **The peg is the circle piece.** In `board_reference_demo.png` five pieces are
  seated and the circle recess is empty, its piece on the table. So the peg has
  to be the piece that fits that recess. It was 0.02 against a 0.025 recess — a
  peg that could not have come out of the hole it gets inserted into — then 0.025
  exactly, which is the *recess*, not the piece (see clearance, below). It is now
  0.023. `tests/test_board_randomization.py` guards the relationship, not the
  number.
- **`filled:` per recess.** A seated piece carries a knob; an empty recess is a
  bare painted floor, drawn darker. The sim drew all six identically, so the hole
  the policy has to find looked exactly like the five it must ignore.
- **Two shapes were not in the scene at all.** `triangle` and `pentagon` were
  `shape: cylinder` placeholders that were never replaced, and the diamond was a
  39mm square at yaw 45 (55x55mm) rather than the drawing's rhombus (side 42mm,
  drawn 45.9 wide x 68.5 tall). Recesses are now real extruded outlines --
  `shape: polygon|rect|rhombus|circle` — built by `recess_verts()`.
- **The peg was on the wrong side.** `[0.14, -0.13]` had the right reach and the
  wrong sign in x. Derived properly from `board_reference_demo.png`: locate five
  recesses by colour, least-squares fit board-frame → pixels (2–6px residuals on
  a 1280px frame), invert the peg through it. Board frame (+165, −117)mm → world
  `[-0.165, -0.106]`.

Three more, found on 2026-08-16 by rendering the board close up and looking:

- **Every recess is a pocket.** Only the empty circle was cut; the five seated
  pieces were 2mm plates lying on an unbroken slab, so they read as stickers and
  the empty recess stood out for the wrong reason — it was the only shape on the
  board with any depth, rather than the only one without a piece in it. The slab
  mesh now cuts all six (`_slab_with_pockets_mesh`), and the pieces are the
  board's own 12mm thickness sitting on the pocket floors, standing 4mm proud.
  `recess_depth: 0.008` is the one number here that is **not** measured — the
  drawing's "8mm" is a horizontal gap from the circle to the board's right edge,
  not a depth, and toy.png does not dimension the depth at all.
- **A piece is 2mm smaller than its recess, per side.** toy.png draws every shape
  as a double outline and dimensions the OUTER one ("recess side 46mm"); the
  inner line is the piece. Measured on the three that read cleanly: circle
  49.9 → 45.8, square 46.2 → 42.1, rectangle 43.3 → 39.4. So `board.piece_clearance`
  is 0.002 and every `size`/`side`/`radius` in the config is the recess.
- **A material binding is inherited by children; displayColor is not.** The peg's
  knob rendered in the peg's own teal, and top-down it was invisible. Isaac binds
  the peg's `color:` material with `strongerThanDescendants`, which beats anything
  a child binds — so `_attach_knob` weakens the parent's binding *and* binds the
  knob's own. This only bites on Isaac core objects (`DynamicCylinder` and
  friends); the board's raw meshes carry displayColor and are fine.

Reading toy.png numerically is reliable — the drawing is to scale, and measuring
it against its own 174mm board reproduced every dimension it also states in text
(triangle side 52 → 51.5 measured; pentagon side 32 → 51.1×50.0 vs 51.8×49.2
predicted; square 46 → 46.2; circle 50 → 50.3; diamond side 42 → 41.2 implied
from its diagonals). Use that method rather than eyeballing.

The board's 180° yaw is **correct** — checked by inverting the robot's position
through the same fit: it lands at board-frame bearing −109°, against −90°
expected for 180° and 0/+90/−180° for the alternatives. (The ~19° and the extra
range are the robot base being elevated above the plane a planar fit assumes;
the flat objects fit to a few px.)

`data/synthetic/circle_grasp_v1/` (100 episodes, pre-2026-08-15) was
generated with the pose axes live and is mislabelled — see the
`DO_NOT_TRAIN_ON_THIS.md` in that directory. Its seeds still reproduce
bit-identically, so it can be regenerated once the re-planning exists.

## Datasets and cameras

**Every policy that has ever worked on this task used TWO cameras
(`observation.images.overview` + `observation.images.wrist`).** The only
checkpoint with a nonzero hardware success rate
(3/10) is two-camera. **That checkpoint is
`outputs/train/smolvla_circle_insert_50ep_trimmed_20000/checkpoints/020000` --
the TRIMMED, batch-32, 20k-step run** (docs/windows-gpu-training-run-grasp-v1.md:
"The trimmed batch-32 checkpoint scores 3/10 on hardware"). It is NOT
`smolvla_circle_insert_50ep_30000`, which is a different run (untrimmed dataset,
30k steps, batch 8) with no established hardware score. Three eval sessions on
2026-08-14 were spent on that wrong checkpoint; its 0/10 and 2/10 results are
not evidence about the harness, the hardware, or the board.

**R0 was finally run against that correct checkpoint on 2026-08-15: 0/10.**
Grasp succeeded on 2 of 10 episodes, insert on none. Board (6.4px/~4mm), peg
(~7px/~4mm) and ports were all verified beforehand. The failure matches the
checkpoint's *documented* signature exactly -- windows-gpu-training-run-grasp-v1.md:
"the arm reaches the disc and loses it at or just after closing the gripper" --
so this is the known-weak grasp phase, not a new fault.

**The 3/10 has never been reproduced on this machine.** It was already the
"previous best" in docs/linux-session-handover-2026-08-10.md, i.e. measured on
the Mac setup on or before 2026-08-10; the hardware moved here 2026-08-11.
Treat 3/10 as a pre-move number, not a target this setup has ever hit. There is
no known-good reference on this machine at that point -- see below, that changed the same day.

Teleop check the same day: **5/5 solid grasps by hand** through the same
gripper (`./teleop_check.sh`). The gripper and the 5.2V rail are cleared --
poor autonomous grasp is not a hardware fault. Review of the R0 rollout's own
footage shows the arm reaching the peg in nearly every episode and failing at
the moment of closing, matching the documented signature. Perception is
locating the peg despite the workspace reading ~15-20% darker than the demos
(rollout V 151-164 vs demo V 180-188), so illumination is a real distribution
shift but not what breaks the grasp.

### The metric is success vs OBJECT POSITION (`./analyse_placement.sh`)

A single success rate cannot tell a policy that *sees the peg and adapts* from one
that replays a trajectory ending where the peg usually is. Those produce the same
number and are opposite outcomes, and the second is what this project exists not
to build. So placement is not a nuisance to null out before a run — it is the
independent variable. Record it per episode and report success against it.

`./analyse_placement.sh <rollout>` reads outcomes off the video rather than
eye-scoring: **transport** (the peg left the table region — it was picked up and
carried), **disturbed** (moved >15mm, never lifted), **untouched**.

**Measured 2026-08-16, and this is the project's core result so far:**

| run | peg start | transports |
|---|---|---|
| `rollout_grasp_v1_r1` | y≈574 (the demos' dense region) | **4/10** |
| `rollout_grasp_v1_r2` | y≈611 (~22mm lower) | **0/10** |
| `rollout_grasp_v1_r3` | y≈612 (same) | **0/10** |

r3 repeated r2 with nothing changed: **0/20 transports** at the displaced
position against 4/10 at the demos'. Note also r3's episodes 5-9, where the peg's
start position stops varying at all (332.5±0.3, 615.6±0.5) — the arm had stopped
moving it, so nobody was resetting it between episodes. An eval that stops
perturbing its own setup is worth noticing in the log.

The board was correctly aligned in both (4.4px, 3.5px). ~22mm of peg displacement
took transport from 4/10 to 0/10 — the policy nudged the peg in 6 episodes and
lifted it in none.

**Why: the demos cover about 2cm.** `./analyse_placement.sh --demos circle_grasp_v1`
clusters the peg's start position over the 45 episodes where it is visible at frame
0 into three dense groups — 17, 13 and 11 episodes — whose centres are
(405,561), (401,591) and (381,570). That is a **~15 x 19mm patch**, plus 3 stray
episodes at x≈331 and a single outlier at y≈644. The nominal spread of 66 x 62mm is
almost entirely those four strays.

So the policy is competent in a 2cm neighbourhood and nowhere else, and the
training data never asked for more. This is a data-coverage result, not an
architecture one. Note also that the peg distribution is **not Gaussian** — quoting
it as a mean ± sd (as `align_board.py`'s constants do) hides the cluster structure
and makes a placement 20mm outside every dense cluster look like a reasonable
"2 sd".

### Pre-flight before any eval (`./verify_ports.sh`, `./check_alignment.sh`)

`check_alignment.sh` reports three things, and all three have bitten:

- **Board pose**, by phase correlation on gradient. Aim < 5px. Colour thresholding
  was tried first and drifted 15px between two captures of a stationary board.
- **Peg pose**, by gradient template match, judged against **the spread the demos
  themselves used** — not against a threshold. This used colour thresholding until
  2026-08-16 and failed the same way the board check already had: under a warm
  cast the peg's hue leaves the 70-100 window and it reports `MISSING` with no
  other symptom.

**The board and the peg are not the same kind of quantity**, and treating them
alike is why this check sent people after the wrong thing. Measured across all 81
episode starts of `circle_grasp_v1` (`scripts/measure_setup_distribution.py`):

| | demos' own spread, vs the reference frame |
|---|---|
| board | dx +1.0 ± 1.4, dy +0.2 ± 0.3, **max 4.1px (2.5mm)** — held still all session |
| peg | dx +21.1 ± 24.0, dy +1.2 ± 16.6, **median 34px (21mm)** — scattered |

So the board is worth aligning to a couple of millimetres, and the peg only needs
to land somewhere in the demos' range. The old fixed thresholds (<5px board, <12px
peg) were guesses, and the peg one was three times tighter than the demos' own
median — on 2026-08-16 it reported a correctly-placed peg as needing a 23mm
correction, on a setup whose position was pencil-marked and demonstrably unmoved.
Re-derive the constants with that script if the demo set changes.
- **Lighting**, as the bare paper's saturation and red-channel clipping.

**Give the camera time before believing any colour reading.** The overview
camera's auto-white-balance settles far slower than its exposure. Measured
2026-08-16 from a cold open: the paper read saturation 63 with 94% of its red
channel clipped, then 42, 29, 21 across successive captures, against the demos'
22. The first reading looks exactly like "the room's lighting is wrong" and is
not — it is the camera. `align_board.py` now reads 60 frames rather than 10.
Placement numbers were stable throughout; only the colour judgements moved.

This does **not** affect recording or eval: those go through lerobot's own camera
handling (`--robot.cameras`), the same path that captured the demos.

### What is actually in the demos (`./analyse_demos.sh`)

Episode counts say a dataset is big. They say nothing about whether the behaviour
the policy fails at is in there in any quantity. Measured 2026-08-16 on
`circle_grasp_v1`, the current best checkpoint's training set (81 eps, 31,541
frames):

| | share of frames |
|---|---|
| gripper **closing** — where "fails at closure" (4/8) lives | **2.7%** |
| gripper **opening** — where "never releases" lives | **2.5%** |
| arm essentially **still** (max joint step < 0.25°/frame) | **55.8%** |

The release is a median of **7 frames out of a 504-frame episode, 1.4%**. The 31
`Pick up the circle piece.` episodes contain **no releases at all** (0.15%
opening), so they add grasp coverage while diluting the release signal further.

Both failing behaviours together are ~5% of the training signal, and more than
half of the rest is *hold still*. That is a dataset-**composition** problem and it
is invisible to every number in `meta/info.json`.

**Trimming is not the lever, and this settles it:** `circle_grasp_v1`'s 50 insert
episodes *are* `circle_insert_50ep_trimmed` (26,078 frames, median 504, dead
lead-in 12 / tail 5, all identical). The raw `circle_insert_50ep` is 662 frames
with an 86-frame dead lead-in and an 85-frame tail. The best checkpoint is
already trained on trimmed data; trimming has been done.

Two consequences for how to spend effort:

- **Corrective (DAgger) demos must be short takes of the failing moment.** A full
  fresh episode adds ~13 frames of gripper actuation and ~490 frames of
  everything else, so it dilutes about as much as it teaches.
- **Phase-balanced sampling costs no new data at all** — reweighting frames near
  the gripper transitions is a training-time change against the data already on
  disk, and is worth trying before collecting anything.

Re-run `./analyse_demos.sh` after collecting corrective demos. The question is not
how many episodes were added, it is whether the share of the failing behaviour
moved.

### The current best checkpoint on this machine

```
outputs/train/smolvla_circle_grasp_v1_20000/checkpoints/020000/pretrained_model
```

Run it with `./run_eval_grasp_v1.sh <tag>`. Trained on `circle_grasp_v1`
(81 eps, 31,541 frames, ~5x the grasp coverage of the trimmed run, 2 task
strings), two cameras, 450M params. It had never been evaluated on hardware
until 2026-08-15 -- the 08-10 handover recorded "Checkpoint has not been
evaluated on hardware yet", then the PC move, the missing Linux eval image and
the Isaac work buried it for five days.

**Result 2026-08-15 (`rollout_grasp_v1_r1`), 8 of 10 episodes phase-logged:
grasp 4/8, transport 4/8, insert 1/8** -- including the first completed
insertion ever performed on this machine.

| phase | R0 (`trimmed_20000`) | `circle_grasp_v1_20000` | Fisher p |
|---|---|---|---|
| grasp | 2/10 | 4/8 | 0.32 |
| transport | 0/10 | 4/8 | **0.023** |
| insert | 0/10 | 1/8 | -- |

**Transport is the result that holds up statistically.** R0 never transported
once in 10; this checkpoint transported in every episode where it got a grasp.
The grasp improvement is real-looking but within noise at n=8 -- do not quote
it as established. The single insertion is an existence proof, not a rate.

**This is the first known-good reference on this machine**, which is what
every A/B comparison since the move has lacked. Treat it as the baseline any
new policy must beat, and re-measure it (10 episodes, same protocol) before
trusting a comparison against it.

Two failure modes remain, and they are distinct -- log them separately:
- **no grasp** (4/8) -- still the biggest single loss.
- **carried to the board but never released** (seen in both this run and R0):
  the arm transports and then holds on. It is not dropping short; it never
  reaches the state that triggers the open.

Datasets A/B/C (`circle_grasp_v1_real10`, `circle_grasp_v1_real50`,
`circle_grasp_v1_mixed_10r_100s`) and `grasp_v1_dagger1` are
**overview-only** — `scripts/export_lerobot_dataset.py` drops the wrist
camera by design (it can't render a wrist view for synthetic episodes). All
four scored 0/20 or degenerate on hardware. Treat any result from these four
datasets as confounded; see `docs/replan-2026-08-14-camera-confound.md`.

The *source* datasets (`data/circle_grasp_v1`, `data/circle_insert_50ep`)
still have both cameras — nothing was lost, the exports just need redoing.

## Board position

**The board's correct position is marked on the paper in pencil (2026-08-14).
Put it back on the marks before any eval or recording.** It is not decorative:
the demos in `circle_insert_50ep` were recorded with the board effectively
fixed (measured drift across the whole set: max 4.3px, ~2.5mm), so a policy
trained on them has no signal from which to handle a moved board. On
2026-08-14 the board was found ~19mm out of place and the eval scored 0/10 --
grasp and transport both worked, nothing seated. That size of offset is fatal
for seating a peg and nearly harmless for the coarser phases, which is exactly
the pattern seen.

Verify before trusting a run:

```bash
./check_alignment.sh --out board_alignment.png    # prints offset in px and mm
```

Under ~5px (~3mm) is fine. It overlays the live overview camera on
`docs/reference/board_reference_demo.png`, a real episode-start frame from the
demos themselves, and measures by phase correlation on gradient magnitude --
colour thresholding is NOT usable here, evening light halved the green pixel
count and moved two consecutive readings of a stationary board by 15px.

The board drifted ~32mm during the 2026-08-14 session. If it is ever unmarked
or knocked, re-check **after** a run as well as before, or the later episodes
are quietly confounded.

## Training

- `--base <checkpoint> --steps N` for "resuming" a run does **not**
  reconfigure the LR scheduler's decay target — it stays at whatever the
  original run's total steps was. A short resume run's LR may never decay
  properly as a result. Prefer a single continuous run sized for the real
  total step count; only use `--base` resume when you've confirmed the
  schedule mismatch doesn't matter for what you're testing.
- `--ipc=host` is required on `docker run` for any multi-worker training
  job through `lerobot-train:latest`, or the DataLoader crashes on a shared
  memory limit.

## Running a policy closed-loop on the arm

**The working checkpoint is
`outputs/train/circle_insert_real80_30k/checkpoints/030000/pretrained_model`**
(trained by `./train_deploy.sh` on all 80 episodes -- the 59 plus 21 recorded
for the place phase). It is the best checkpoint measured, and it does complete
the task: on 2026-08-21 `real80_bench1` grasped on chunk 6, transported on 7,
released the piece into the pocket on 10 and retreated on 11, with no overrun.
`circle_insert_real59_30k/checkpoints/030000` also completes the task
(2026-08-20) and is the fallback if the 80-episode model regresses.

**Do not read that as the 5-7mm insertion gap being closed.** After the first
two trials it looked closed, and this file said so; ten trials say something
weaker. Full record in `docs/bench-scores-real80.md`:

- grasped in 6 of 10
- seated in 5, but only **2 confirmed placed** (bench1, bench2). Two others
  (fixed02, fixed04) were **slides** -- released off-target, the piece found
  its own way in -- and one (bench4) was never asked about.

A slide is the policy getting away with an inaccurate release, which is the
very error the 21 place-phase episodes were meant to remove, so scoring it as
success hides the thing being measured. Nothing in the manifest distinguishes
the two: there is no video, the per-chunk stills are 1.7s apart, and the gripper
occludes the piece in the release frame. **Only a human watching can call it**,
so record placed/slid/missed per trial at the bench or the number is not
recoverable afterwards.

Final training loss does **not** rank these: `complete30_30k` had the lowest
loss of the three (0.015) and scored 0/3 on the bench, where `real80_30k` has
the highest (0.033) and works. Only the bench ranks a checkpoint.

**Wrist framing at the start decides the trial, and joint-space coverage does
not.** The failure (`real80_bench3`) stalled
at a joint posture 0.6 deg from a demonstrated grasp with 51 demos within
10 deg -- the *best*-covered of the three trials, better than either success.
What differed was the wrist view: the piece sat at x=0.66 (+2.3 sd against
`DEMO_WRIST_X = (0.41, 0.11)`) and the board's pocket was out of frame
entirely, where both successes had it as the largest blob at lower-left. The
policy then re-emitted "hover, stay open" from every fresh observation for 8
chunks and never requested a gripper close -- confirmed from the manifest's
`requested` channel, so the harness was blameless. Do not answer this failure
with more episodes or more joint-space coverage; the arm was where it belonged
and the camera was not. `run_rollout_trial.sh` now refuses to roll out when
`home_arm.py` reports the framing out of distribution (`--force-framing`
overrides, for a deliberate OOD probe).

**The grasp IS machine-checkable, even though the insertion is not.** A gripper
closing onto the 13mm knob stops where the knob is; one closing on air does not:

| trial | gripper after the close | outcome |
| --- | --- | --- |
| bench1, bench2, bench4 | 7.4, 7.4, 7.6 | holding the piece |
| bench5 | 2.4 | closed on nothing, twice |

No overlap. `scripts/grasp_verdict.py <output-dir>` reads this off the manifest
and also checks transport (every success swung the base to ~25 afterwards; the
failure never left the 48-55 band it grasped in). `run_rollout_trial.sh` runs it
automatically at the end of every trial. Insertion still has to be confirmed by
eye or from the final `overview.png` -- nothing logged distinguishes a piece
seated in the pocket from one dropped beside it. Thresholds come from four
trials on 2026-08-21; widen them if a run lands between them rather than
trusting the boundary.

**The second failure mode is closing a few degrees too high.** bench5 and bench6
passed the framing gate, approached correctly, and commanded the close at
shoulder -3.2/elbow 35.9 and shoulder +0.2/elbow 29.1, where all three successes
close at shoulder -7 and elbow 40 (agreeing within 1.1 and 0.8 deg). They shut
above the peg, reopened, re-approached and missed again, knocking the piece out
of position. Both had started low in the wrist frame (y 0.460 and 0.407), which
is what the `WORKING_WRIST_Y_MIN` floor now blocks. Distinct from bench3's
hover, where the policy never commanded a close at all.

**A third failure mode has no explanation yet, and it is the important one.**
bench7 started at y=0.53 -- inside the success band -- closed at shoulder -8.2,
elbow 39.0, which is the successes' own posture, with the piece measured at
(0.46, 0.56) in the close frame against the successes' (0.45-0.47, 0.55-0.56).
Start framing, close posture and close-frame vision were all normal, and the
gripper still caught nothing. Neither the framing gate nor the height story
covers it. **The gates are necessary, not sufficient: they remove known ways to
fail and do not make a trial succeed.** Full score across all ten trials is in
`docs/bench-scores-real80.md`: grasped 6 of 10, seated 5, confirmed placed 2.

**The y floor is not supported either.** `fixed03` grasped, transported and got
the piece to the board from y=0.45 -- below `WORKING_WRIST_Y_MIN`, so the gate
would have refused a trial that worked. And on `fixed04` the gate's own
measurement was wrong: `home_arm.py` locked onto the board's pocket and reported
the peg at x=0.07 when the wrist frame plainly shows it at x=0.44, which would
have refused a trial that succeeded. Treat the framing gate as an advisory
reading that needs the wrist frame checked, not an authority; `--force-framing`
exists for exactly this. Trust start-y only when measured off `chunk-00/wrist.png`
with the pocket region excluded.

Before answering an in-band miss with retraining, note what is not yet ruled
out: the piece sliding on the paper as the gripper descends, and simple
run-to-run unreliability at a rate a handful of trials cannot resolve. Ten
trials at a fixed, gate-clean start position would settle which.

Use `./run_rollout_trial.sh <fresh-tag>
<checkpoint>`, which homes first and then rolls out under a fresh tag. Anything
from the `topcam59_sim_real_ratio_v1_*` sweep reaches the peg and fails to grasp
it: those runs stopped at 20000 steps against a 30000-step decay schedule.


`robot_learning/supervised_policy_rollout.py`, through `./hw_docker.sh`, with
`--confirm-motion` and a person at the power switch:

```bash
./hw_docker.sh python robot_learning/supervised_policy_rollout.py \
  --checkpoint outputs/train/<run>/checkpoints/<step>/pretrained_model \
  --skill place_circle \
  --output-dir outputs/hardware-test/<tag> \
  --confirm-motion
```

**The three parameters that decide whether it can physically do the task**, all
learned the hard way on 2026-08-19 when a rollout of a good checkpoint moved
the arm vaguely toward the board and never grasped anything:

- **`--control-hz` must equal the dataset fps** (30 for every circle-insert
  dataset; check `meta/info.json`). A 50-step chunk is 1.67 s of demonstration.
  Running it at 10 Hz stretches it over 5.0 s and the arm crawls.
- **`--max-relative-target` is a per-step rate limit, not a per-chunk budget.**
  It is passed to `SOFollowerRobotConfig`, which re-reads `Present_Position`
  before every write. Never re-implement it locally against a state snapshot
  taken once per chunk: that becomes a positional cage, and the demonstrations
  move the shoulder a mean of 31.8 deg (max 92.8) over one 50-step chunk, so a
  +-10 cage throttles the task's main motion to a third of what it needs.
  Recorded per-step |delta| p99 is 5.84 deg on the shoulder, the fastest joint.
- **`--max-duration-s` and `--max-chunks` must cover a whole episode.**
  Demonstrations average 16.0 s (max 28.8 s). The defaults (12 chunks, 60 s)
  do; the original 6 chunks at 10 Hz ran out mid-approach.

Joint clamps in `robot_learning/*.py` are a backstop against a wild prediction,
**not** the app's UI slider range. `shoulder` must be at least `-115`: at
`(-90, 90)` it silently truncated 12.34% of every recorded action, so the
raised pose that every circle-insert episode *starts* from was unreachable.
Widen these whenever a new dataset's action range grows.

Diagnose a disappointing rollout **before** running the arm again.
`./gpu_docker.sh python robot_learning/diagnose_policy_chunk.py --checkpoint <path>`
replays the checkpoint against held-out demonstrations offline and prints, per
sampled frame, the chunk the policy wants against the motion the teleoperator
actually recorded. The rollout manifest also logs `requested` vs `sent` per
step plus `rate_limited_steps` and `overrun_s` per chunk: if `sent` differs
from `requested` on many steps the rate limit is binding, and if `overrun_s`
grows the loop is not holding `--control-hz`.

## Published SO-10x fine-tuning practice, and which parts apply here

Collected 2026-08-20 while diagnosing a policy that approaches correctly and
misses the grasp. **Checked** means measured against this project's own data;
treat the rest as reference, not as something already true here.

| claim | source | status here |
| --- | --- | --- |
| below ~50 episodes/task the model mostly memorises start positions | Trelis, ggando | applies -- the ratio sweep trained `real_only` on 47, and `train_deploy.sh` now uses all 59 |
| density beats count: 50 episodes over 30cm failed, 75 over 10cm succeeded | ggando | **checked, does not apply.** Our grasp points span 140 x 125 mm with a median 9 neighbours within 20mm. Already dense; recording more for coverage would be wasted |
| consistency beats count: 75 clean episodes beat 81 with mixed strategies | ggando | **checked, partly applies.** Median episode disagrees with same-position neighbours by 6.45 deg, but 15 of 57 exceed 8 deg and ep 9 reaches 32 deg. See below |
| performance is sensitive to lighting differing between recording and evaluation | ggando | **checked, not a factor.** Recorded overview mean 0.509 vs rollout 0.551, gap +0.042 |
| two cameras beat one (100% vs 80%) | ggando | applies; we have both. Ablation shows the wrist dominates (blanking it moves predictions 4.03 vs the overview's 1.11) |
| execute only ~15 of a 50-step chunk, replanning every 0.5 s | Trelis (ACT) | **checked, did not help.** `--max-steps-per-chunk 15` hovered for 40 chunks and never closed, where the 50-step version closed 4 times in 5 |
| 20k steps is a starting point, tune upward; loss often still dropping | LeRobot docs, ggando | applies. Our sweep stopped at 20k against a 30k decay schedule, so every swept checkpoint was frozen mid-decay |
| ACT sizing of roughly 2.5 training steps per frame | Trelis | reference only, and ACT rather than a pretrained VLA. At 28158 frames it would imply ~70k steps -- an upper bound to consider if 30k underperforms |
| evaluate with 10 episodes, 30 s each, 30 s reset, 5 s warmup | Trossen | adopt this for scoring; we have no automatic success detector, so eval is counted by watching |
| a diffusion policy conditions on two observations (t-1, t) to infer direction | Osmulski | reference. This SmolVLA config runs `n_obs_steps=1`; a single frame carries no velocity |

`robot_learning/audit_demo_consistency.py` regenerates the consistency and
lighting numbers and prints the outlier list. As of 2026-08-20 the episodes that
disagree most with neighbours grasping within 25mm are **9 (32.0 deg), 32
(17.3), 45 (13.1), 52 (11.8)** -- ep 9 grasps with the shoulder at +4.4 and the
elbow at 27.6 where its neighbours use roughly -25 and 40, a genuinely different
posture for the same target. Dropping just those four leaves 55 episodes, still
above the 50 floor; the 8-degree threshold flags 15 and would leave 44, which is
below it. If a clean-subset run is wanted, drop the four, not the fifteen.

An open issue with exactly our symptom -- policy reaches the target and never
closes -- is Robbyant/lingbot-vla#48. It has no published resolution. The
unanswered questions there worth knowing about: whether fully unfreezing the
vision/VLM stack hurts on small datasets, and whether action-dimension
zero-padding destabilises the gripper channel.

## Known recurring gotchas

- **`loop.py record --episode-time` defaults to 20s, which silently truncates
  the end of the task.** On 2026-08-17 this cut 27 of 60 circle-insert episodes
  off after the grasp and before the insertion, leaving the place phase with
  only ~33 demonstrations against ~60 for the pick -- and insertion is what the
  policy then failed at. It is not visible at recording time: the episodes look
  fine, they just stop early. The numbers: complete episodes grasped at 9.6s
  mean with 10.3s left to place; truncated ones grasped at 14.6s with 4.1s left.
  Placement needs 6-10s after the grasp. **Use `--episode-time 30`** so a slow
  grasp still leaves room to finish. Check any new dataset for this with
  `robot_learning/audit_demo_consistency.py` before training on it.
- **Do not "clean" a dataset by dropping its truncated episodes.** Tried
  2026-08-20: training on only the 30 complete circle-insert episodes scored
  0/3 on the bench and never transported at all, worse than the 59-episode
  checkpoint it was meant to improve. 30 is below the ~50 floor and the
  truncated episodes still carry pick and approach signal. Add complete
  episodes; do not subtract incomplete ones.

- Reusing a `--tag` from a previous attempt (even a failed/Ctrl-C'd one)
  hits `FileExistsError` — always use a fresh tag.
- An interrupted rollout leaves a valid `.mp4` but a broken dataset
  manifest — `robot_learning/extract_one_frame.py` still works on the raw
  video for diagnosis even when the dataset itself won't load.
- `RuntimeError: ... Overload error!` on `Torque_Enable` has more than one
  known cause: a follower/leader port swap (check with `verify_ports.sh`
  first), or — as of 2026-08-14 — an unexplained case with ports confirmed
  correct and no mechanical jam, still under investigation. Don't assume
  it's the port-swap without checking.

## Full history

Point-in-time session detail (exact commands, what broke, what was tried)
lives in the dated `docs/linux-session-handover-*.md` and
`docs/handover-*.md` files. Read the most recent one for narrative context
on how the project got here — but treat this file, not those, as the
source of truth for what's currently correct.
