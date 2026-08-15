# Session handover — 2026-08-15 (evening), Isaac scene asset

Durable facts live in `docs/RUNBOOK.md` and have already been written there.
This is what happened, what it means, and what to do next.

## The headline

Nothing was run on the robot. The whole session went into the Isaac side, and
the honest summary is: **the synthetic pipeline could not have produced usable
training data, for four independent reasons, and all four are now fixed.** None
of them were visible from a failing test — every automated check passed
throughout, including the scene gate's.

The other half of the headline: **the two most consequential findings came from
looking at pictures, not from reading code.** The exporter's blown-out lighting
showed up because a smoke test rendered a frame and measured it. The missing
board shapes showed up because Alex opened the scene in a viewport and looked.

## Do this first

```bash
cd so-arm100
./run_tests.sh                  # 3 suites, all green as of this commit
./view_scene.sh                 # open the scene and LOOK at it
./check_scene_gate.sh           # renders the side-by-side; approval is STALE
```

The gate is unapproved on purpose (`77f6f844` -> `3adec4d3`). `generate_synthetic.py`
will refuse until a human looks at `scene_gate_comparison.png` and runs
`./check_scene_gate.sh --approve <name>`. Do not approve it to unblock yourself;
the point of the gate is the looking.

## What was wrong, in order of consequence

### 1. Synthetic episodes were mislabelled, and it was worse than the note said

`generate_synthetic.py` randomized the peg's position +/-3cm while copying the
parent episode's action trajectory **verbatim**. Frames showed the peg in a new
place; labels said "reach where it used to be". That trains the policy to ignore
the target's position — the exact failure being fought on hardware.

The 2026-08-15 morning handover named `object_position`. **`board_position` and
`board_rotation_deg` have the same defect** — the insert phase's actions target
the board's old pose. The comment added on 08-14 arguing for board randomization
as "the axis that matters for deployment" is right about why it is wanted and
wrong that it was safe to switch on.

All three now live under `randomization.label_breaking:` and sample to zero
unless `--allow-label-breaking` is passed. A pre-split config carrying them at
the top level **raises** rather than being silently honoured. Episodes record
`randomization.label_breaking_applied` so a dataset is auditable from its own
records.

Rule 10 was verified, not assumed: the discarded draws still happen, and all 100
episodes in `data/synthetic/circle_grasp_v1` reproduce **bit-identically** from
their recorded seeds under the new code with the gate opened. That dataset is
marked `DO_NOT_TRAIN_ON_THIS.md` (untracked — `data/synthetic/` is gitignored,
and the directory is root-owned by Docker, so write into it via a container).

### 2. Every synthetic frame ever exported was blown out

`export_lerobot_dataset.py` had lighting hard-coded at dome 2000 / distant 20000.
Measured: **mean pixel 245/255 with 37% of pixels clipped at 255**. The new
`light_intensity_scale` axis moved the frame mean by 0.1% because there was no
headroom to move into.

Base is now dome 250 / distant 625 — mean ~167, nothing clipped, and the
[0.75, 1.15] range produces a real 15% swing (149 -> 174). The range is the one
value in the config with a *measured* target: rollout_grasp_v1_r1's workspace
read V 151-164 against the demos' V 180-188, i.e. ~0.80 of training brightness,
so 0.75 puts that inside the distribution rather than at its edge.

**A lighting change takes ~10 rendered frames to appear.** The USD attribute
reads back the new value immediately but the RTX render walks to the new
exposure — which is why the first measurement came out *non-monotonic*, each
frame being a blend with the previous state. `LIGHT_CONVERGENCE_STEPS` (15) is
the burn-in and the exporter refuses a `--settle-steps` below it; otherwise every
episode's opening frames carry the previous episode's exposure, correlated with
episode order.

Lighting was inline in three places and had drifted: `check_scene_gate.py`
rendered at dome 1000 / distant 2500 at a different azimuth while the exporter
shipped 2000 / 20000. **The side-by-side a human approved was never lit like the
frames that went into training** — which is most of what a scene gate is for.
All three now read `lighting:` from the scene config.

### 3. The board asset was wrong in six ways

Found by opening the scene in a viewport. Every check passed.

- **`triangle` and `pentagon` were `shape: cylinder`** — placeholders that were
  never replaced. Two of the six shapes were simply not in the scene.
- **The diamond was a 39mm square at yaw 45** (55x55mm) where the drawing has a
  rhombus, side 42mm, drawn 45.9 wide x 68.5 tall.
- **No knobs anywhere.** The knob is 13mm x 13mm and the gripper closes on the
  *knob*, not the piece. The sim offered a bare 40mm cylinder — the wrong object
  at exactly the moment the policy decides how wide to close.
- **Knobs then failed on square/rectangle/diamond.** Those recesses were
  `VisualCuboid`s whose `scale` carried the shape's size, and **USD scale is
  inherited by children**, so a knob parented under a 46x46x2mm piece was
  squashed by those factors into nothing. The two cylinder-based recesses kept
  theirs. Recesses are now unscaled meshes.
- **The peg was on the wrong side** — right reach, wrong sign in x.
- **The empty circle recess was a disc lying on the surface**, so the insertion
  target read as a sixth seated piece. It is now a real blind pocket cut into the
  slab mesh, 8mm deep, with the recess's paint on its floor.

### 4. The peg was not the piece it is supposed to be

The loose peg IS the circle piece: five pieces are seated and the circle recess
is empty, its piece on the table. So the peg's radius must equal the circle
recess's. They were independently 0.02 and 0.025 — the sim showed a peg that
could not have come out of the hole it gets inserted into. Now 50mm diameter and
12mm thick, the board's own thickness.

## Two methods worth reusing

**`docs/reference/toy.png` is to scale — read it numerically.** Measuring it
against its own stated 174mm board reproduces every dimension it also labels in
text: triangle side 52 -> 51.5 measured; pentagon side 32 -> 51.1x50.0 against
51.8x49.2 predicted; square 46 -> 46.2; circle 50 -> 50.3; diamond side 42 ->
41.2 implied from its diagonals. Do not eyeball this drawing.

**For object placement, fit a frame and invert it.** Colour-segment five recesses
in `board_reference_demo.png`, least-squares fit the board frame to pixels
(residuals came out 2-6px on a 1280px frame), then invert the loose peg through
it: board frame (+165, -117)mm, and with the board's 180-degree yaw that is world
`[-0.165, -0.106]`. The same fit confirmed the board's 180-degree yaw is correct
— inverting the robot's position puts it at board-frame bearing -109 degrees,
against -90 expected for 180 and 0/+90/-180 for the alternatives.

**Caveat on that fit: it is planar.** Elevated objects project outward — the
robot base by ~60mm and ~19 degrees. Use flat objects only. A top-down render
also made the board look 180 degrees off; that was a camera up-vector flip, not a
real error. Check numerically before "fixing" an orientation.

## New tooling

- **`./run_tests.sh [pattern]`** — every `tests/test_*.py` in
  `lerobot-train:latest`. No native Python env exists on this machine.
- **`./sim_docker.sh <script>`** — canonical `leisaac-sim` invocation. Omitting
  its `/Users` mount surfaces as an `is_homogeneous` assertion inside
  articulation init, which looks nothing like a missing mount.
- **`./view_scene.sh [--light-scale 0.75]`** — the scene in a window with a
  camera you can fly. X11 passthrough; needs the `-t`-only-when-a-TTY guard that
  `hw_docker.sh` documents.
- **`tests/smoke_lighting_isaac.py`** — renders and asserts the lighting axis
  actually changes pixels, that the bright end does not clip, and that
  `LIGHT_CONVERGENCE_STEPS` is still enough.

## What NOT to re-litigate

- The board's 180-degree yaw is correct. Checked numerically (above).
- The peg's knob is **visual-only, no collider**, on purpose. Motion is replayed
  rather than re-planned (Rule 4), so giving it a collider changes replay contact
  dynamics — a decision about how the sim behaves, not a rendering fix.
- The old hard-coded lighting defaults survive as fallbacks in
  `scene_setup.add_lighting` so pre-2026-08-15 frames stay reproducible. They are
  not good values and the docstring says so.
- `data/synthetic/circle_grasp_v1` is kept rather than deleted because its seeds
  still reproduce exactly once actions are re-planned.

## Next

**On the robot** — unchanged and still first when someone is at the bench:
`./run_eval_grasp_v1.sh grasp_v1_r2`, 10 episodes, ~20 min. Today's baseline
(grasp 4/8, transport 4/8, insert 1/8) rests on 8 episodes and every future
comparison is measured against it. Phase-log grasp / transport / insert and keep
"never released" as its own category.

**On the pipeline**, in order:

1. **Approve or reject the scene gate.** Everything downstream is blocked on it,
   deliberately.
2. **The sim camera does not match the real overview camera** — it sits closer
   and more oblique, and the config admits it is uncalibrated. This is now the
   largest remaining fidelity gap and it makes the side-by-side hard to judge.
   Calibrating it is the natural next task.
3. **Re-export A/B/C with both cameras** and retrain. The camera confound is
   fixed in tooling; this is where the actual research question (Sec 32) lives.
4. Only then consider regenerating synthetic data — and note that with the pose
   axes gated off, synthetic variation is currently lighting-only. That is honest
   rather than harmful, but it is thin. Re-planning actions per variation needs
   IK the repo does not have.

## Commits

```
11469ab fix: cut the empty recess as a real pocket instead of drawing a disc in it
9084458 fix: build the board's real shapes, from the drawing's own dimensions
5bab22a feat: give the scene its knobs -- and make the peg the piece it is
a73a6d4 feat: add the lighting jitter axis -- and fix the exposure that made it a no-op
9577867 fix: make the mislabelling synthetic axes impossible to generate by accident
```
