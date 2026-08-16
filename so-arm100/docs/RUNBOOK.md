# SO-ARM100 Runbook — current state

This is the single canonical "what's true right now" doc. Unlike the dated
`docs/linux-session-handover-*.md` / `docs/handover-*.md` files (which are
point-in-time session logs, kept for history), **this file gets edited in
place** whenever a fact here goes stale. If you find something wrong here,
fix it here directly rather than writing a new dated doc.

`AGENTS.md`'s "Verified hardware setup" section predates the machine move
described below and still lists Mac ports/paths — treat this file as the
override for anything hardware-related.

Last verified: 2026-08-14.

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

- Follower arm: id `white`, port `/dev/ttyACM1`.
- Leader arm: id `black_20260801`, port `/dev/ttyACM0`.
- **Ports are NOT stable across reboots/replugs.** Run `./verify_ports.sh`
  every session before trusting the mapping above or the `CONFIG` dict in
  `robot_learning/loop.py` — don't assume a past session's mapping still
  holds just because nothing was consciously unplugged.
- Cameras: overview=`/dev/video0`, wrist=`/dev/video2`. Both need
  `"fourcc": "MJPG"` in the camera config or they cap out at 10fps instead
  of the requested 30fps (USB bandwidth limit of uncompressed YUYV).
- **Calibration files live on the HOST**, not in this repo:
  `~/.cache/huggingface/lerobot/calibration/{robots/so100_follower,teleoperators/so100_leader}/*.json`.

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

Never hand-write that `docker run` line. Omitting its `/Users` read-only
mount (where the robot USD lives) surfaces as an `is_homogeneous` assertion
deep inside articulation init, which looks nothing like a missing mount.

## Looking at the scene

**`./view_scene.sh`** opens the sim scene in a window with a camera you can
fly — the same scene `export_lerobot_dataset.py` builds, so if it looks wrong
there it is wrong in the data. `--light-scale 0.75` / `1.15` show the ends of
the randomization range. It is `sim_docker.sh` plus X11 passthrough (kept
separate: the GUI flags and the Xauthority mount are needless for the headless
runs, which is everything else).

The scene gate's side-by-side is one fixed camera and will not show you
everything. The missing knobs (below) were spotted in it, but only because
someone looked; the automated checks all passed. The pocketless board and the
teal knob were not visible in it at all — those needed the close-up renders.

## Synthetic data: label-preserving vs label-breaking

`scripts/generate_synthetic.py` copies the parent episode's actions
**verbatim** (Rule 4). An axis is therefore only safe to randomize if the
copied actions stay correct after it moves.

- **Safe, on by default:** mass, friction, initial joint pose (spent before
  the settle-to-frame-0 phase), camera noise, and peg yaw (the peg is a
  cylinder, so yaw is geometrically a no-op — this stops being true for a
  non-symmetric object).
- **Unsafe, inert:** object and board **pose**. Moving the target while the
  labels still reach for its old location trains the policy to ignore the
  target's position — the failure being fought on hardware. These live under
  `randomization.label_breaking:` in `configs/simulation.yaml` and stay zero
  unless `--allow-label-breaking` is passed. **Do not pass it** until the
  actions are re-planned per variation, which needs IK (the repo has forward
  kinematics only).

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

## Known recurring gotchas

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
