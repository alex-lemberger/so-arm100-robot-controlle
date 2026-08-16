# Session handover — 2026-08-16

Durable facts are already in `docs/RUNBOOK.md`. This is what happened, what it
means, and the one experiment that is set up and not yet run.

## The headline

The session started as "give the board's shapes their pockets" and ended somewhere
else entirely: **the policy has been evaluated, every time, from a starting pose
that puts the peg at the edge of the wrist camera's frame — a view no demonstration
ever had.** The wrist camera is the only channel with the resolution to servo onto a
13mm knob, so the policy has been out of distribution in its most precision-critical
input before it moves at all.

That was not the day's hypothesis. It replaced two earlier ones, both of which are
now known to be wrong or secondary.

## Do this first

```bash
./home_arm.sh --check-only     # what does the wrist see right now?
./home_arm.sh                  # move to the demos' framing, re-check
./hw_docker.sh python robot_learning/loop.py eval \
  --checkpoint outputs/train/smolvla_circle_grasp_v1_20000/checkpoints/020000/pretrained_model \
  --episodes 3 --tag probe_2
./analyse_placement.sh rollout_probe_2
```

Measured at 22:5x on 2026-08-16, before homing: peg at wrist-frame **y=0.09, −2.6 sd,
at the frame edge**. The demos sit at 0.48 ± 0.15. If homing moves that to ~0.48 and
the probe transports, the last two weeks of "the policy can't handle a moved object"
has a much simpler explanation.

**Caveat, and it matters:** `home_arm.sh` only sets the pose *before* the rollout
starts. `lerobot-rollout` begins each subsequent episode wherever the previous one
ended, so episodes 2 and 3 may drift back out of framing. Read the per-episode
numbers, not the aggregate. Making the pose stick per-episode needs either
`--teleop` (pose it by hand with the leader during each reset window) or a change to
the rollout loop.

## What was measured, in order of how much it changes

### 1. The wrist framing (the new finding)

Peg's position in the WRIST view at episode start, as a fraction of frame height:

| | y | at frame edge | genuine transports |
|---|---|---|---|
| demos (81 eps) | **0.48 ± 0.15** | 0% | — |
| `rollout_grasp_v1_r1` | 0.27 | 0% | 2/10 |
| `rollout_grasp_v1_r2` | 0.15 | 50% | 0/10 |
| `rollout_probe_1` | 0.11 | 100% | 0/3 |

Monotonic with performance. **r1 is already out of distribution** even though its peg
was on the demos' own table position — so fixing the peg's place on the table does
not fix the wrist view. The framing is a function of the whole arm pose:
shoulder_lift correlates with peg wrist-y at r=+0.68, elbow −0.65, pan −0.62,
wrist_flex −0.50.

The evals start every episode within ±0.2°; the demos started from all over
(shoulder_lift ±46°). That one fixed pose is the problem, and it differs from the
demos' central framing mostly in wrist_flex: **65.8 against 56.0**.

### 2. Two eval metrics were wrong, in opposite directions

- **`check_alignment.sh` sent us after the wrong object.** Its peg threshold (<12px)
  was three times tighter than the demos' own median offset, and it reported a
  correctly-placed, pencil-marked peg as needing a 23mm correction. Alex's "something
  is wrong here" was right and the tool was wrong. Fixed: the peg is judged against
  the demos' measured distribution, the board against its measured 4.1px worst case.
- **"Transport" counted shoves as carries.** A peg pushed out of the table region
  scored the same as one picked up. Alex watched probe_1 and said "it never grabbed
  it, just pushed it around"; the tool said 2 of 3 were transports. Fixed by
  requiring the gripper to be closed during the absence — which also **revised the
  baseline down: r1 is 2/10, not 4/10.**

A metric that disagrees with the person watching the robot is wrong by default.

### 3. The demos cover about 2cm

Clustering the peg's start position over `circle_grasp_v1`: three dense groups (17,
13, 11 episodes) whose centres span a **15 × 19mm patch**, plus three strays and one
outlier — and those four are what inflate the nominal 66 × 62mm spread. `loop.py`'s
`POSITION_GRID` says "left/centre/right" with no distances attached, which is why it
collapsed. Its own comment already said diversity "has been left to intent twice and
delivered essentially none"; this is the measurement of that.

### 4. The jaw runs narrow

Widest jaw before closing: demos 16.8% mean (11–31%), rollouts a flat ~12%. Inside
the demos' successful range, so not disqualifying, but it is the low end — less
margin when the approach is a few millimetres off, and a near-miss becomes a shove.

### 5. Training is not the problem

All runs annealed their LR to ~2.5e-6, i.e. the schedules completed. The best
checkpoint did **20.3 epochs over 81 episodes**. Training longer fits the same 2cm
patch harder. No validation loss is recorded anywhere, which is why train loss of
0.028 sits next to 2/10 on hardware.

## What was built

| | |
|---|---|
| `scene_setup.build_scene()` | the ONLY way to assemble the scene; `tests/test_scene_is_built_whole.py` fails if anything reaches past it |
| `./render_board.sh` | headless board renders (top/oblique/grazing) |
| `./analyse_demos.sh` | what is in a dataset by behaviour, not episode count |
| `./analyse_placement.sh` | success vs object position; the metric this project needs |
| `./home_arm.sh` | drive the arm to the demos' start framing, and check what the wrist sees |
| `scripts/measure_setup_distribution.py` | re-derive the alignment constants |
| `src/kinematics/inverse_kinematics.py` | task-priority DLS IK on the existing FK |
| `src/augmentation/trajectory_warp.py` | re-plan a demo onto a moved object, ±30mm |

Six test suites, all passing.

## The scene work (the session's original task)

All six recesses are cut as real pockets and the five seated pieces sit in them —
before today only the empty circle was a hole and the rest were 2mm plates lying on
an unbroken slab. Pieces are 2mm smaller than their recesses per side (measured off
toy.png, which dimensions the OUTER of its double outlines), and the peg went 0.025
→ 0.023 for the same reason.

And the reason it mattered less than expected: **`export_lerobot_dataset.py` never
called `add_board`.** Every synthetic frame ever exported showed the peg with
nothing to insert it into, while `generate_synthetic.py` simulated the same episodes
with a board. The scene gate passed throughout because it renders its own scene. Any
dataset exported before today has boardless synthetic frames.

## What NOT to re-litigate

- **The board is aligned.** 3.3px, inside the demos' 4.1px worst case, verified
  repeatedly. It is not the variable.
- **Making the wrist joints expensive does not fix IK orientation drift.** Swept 1,
  3, 6, 12, 25 over 60 real postures: worst rotation stayed at 36° and the median got
  worse. The weights are neutral on purpose.
- **Warping cannot move a demo across the table.** 30mm is the measured ceiling; past
  it the IK stops converging and it raises rather than emitting a bad episode.
- **`view_scene.sh` needs the GPU.** Close it before a bench session.

## Next, if the home-pose experiment does not explain it

1. Wire warping into `generate_synthetic.py` — the gated pose axes stay inert until
   it lands, and `--allow-label-breaking` still produces mislabelled episodes.
2. Random-crop augmentation. LeRobot's `--dataset.image_transforms` are photometric
   only; crop is the single most effective intervention in
   [arXiv 2307.03659](https://arxiv.org/html/2307.03659) and would need a small patch.
3. The placement grid, in millimetres this time — 3×3 at ~5cm, 8–10 episodes per
   cell, verified afterwards with `./analyse_placement.sh --demos`.

Note the order changed today. The grid was the top recommendation until the wrist
framing turned up; a policy evaluated outside its training distribution cannot tell
you whether more coverage would help.
