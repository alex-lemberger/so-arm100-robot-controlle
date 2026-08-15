# Re-plan, 2026-08-14: the §19–21 experiment is confounded by a dropped camera

## Summary

Datasets A, B, and C were all built **overview-camera-only**. Every policy that
ever worked on this task was trained **overview + wrist**. The uniform 0/20
result across A/B/C — and the "grasps fine, never transports" failure mode — is
consistent with a policy that cannot see whether it is actually holding the
piece.

The §19–21 experiment as run cannot answer the research question, and no amount
of DAgger correction or LR-schedule fixing on top of the current datasets will
change that. **Stop the Run D thread. Rebuild the datasets first.**

## Evidence

| Artifact | Cameras | Hardware result |
|---|---|---|
| `smolvla_circle_insert_50ep_30000` (pre-Isaac baseline) | overview + **wrist** | ~~3/10~~ **unknown** -- see the correction at the end of this doc; the 3/10 belongs to `..._trimmed_20000/020000`, which scored **0/10** on 2026-08-15 |
| Dataset A `circle_grasp_v1_real10` | overview only | 0/20 |
| Dataset B `circle_grasp_v1_real50` | overview only | 0/20 |
| Dataset C `circle_grasp_v1_mixed_10r_100s` | overview only | 0/20 |
| Run D `grasp_v1_dagger1` | overview only | degenerate (no motion) |

The source dataset still has both cameras:

```
data/circle_grasp_v1     81 eps, 31541 frames, [overview, wrist]
data/circle_insert_50ep  50 eps, 33707 frames, [overview, wrist]
```

(`circle_grasp_v1` = the 50 full insert demos + the 31 grasp-only takes from
commit `a7b1065`. Episodes 0–49 are the insert demos, which is what A and B
sampled — so the name is misleading but the content is right.)

The drop was deliberate and documented, in
`scripts/export_lerobot_dataset.py:19-21`:

> Overview camera only, at the real dataset's own resolution (drop the wrist
> camera — rendering it for synthetic episodes would need a second,
> wrist-relative camera whose pose tracks forward kinematics per frame).

That reasoning is sound **for the synthetic half of Dataset C**. The mistake is
that it was applied uniformly — Datasets A and B are pure real episodes that
need no Isaac rendering at all, and lost the wrist camera for no reason. The
consequence was flagged at the time as "worth confirming isn't a mistake before
training" and then never traced through to the 0/20 result.

## Correction to an earlier diagnosis

The 08-12 conclusion that occlusion/sensing was ruled out — "wrist-camera frames
confirm the policy can see both the grasped piece and the target hole" — used
wrist frames that the **rollout recorded but the policy never received as
input**. That diagnosis does not hold. Sensing is back on the table as the
leading explanation.

## Revised plan

Strategy (user's call, 2026-08-14): get *one* policy working again, then redo the
A/B/C comparison at a level where success rates are nonzero and comparable.

### R0 — Re-establish a known-good control (hardware, needs human)

Re-evaluate the old two-camera checkpoint
`outputs/train/smolvla_circle_insert_50ep_30000/checkpoints/030000/pretrained_model`
on the current Linux hardware, fresh `--tag`, 10 episodes.

Why first: every result since the machine move has been ambiguous because there
is **no known-good reference on this machine**. If this reproduces ~3/10, the
harness and hardware are trustworthy and the datasets are the problem. If it
scores 0/10, the problem is the eval path or the hardware, and rebuilding
datasets would waste days. This single trial de-ambiguates everything after it.

Note this checkpoint is lerobot-0.4.1-era; confirm `lerobot-train:latest` loads
it before booking hardware time.

### R1 — Rebuild A and B with both cameras (no Isaac needed)

Re-export from `data/circle_grasp_v1` episodes 0–9 (A) and 0–49 (B) keeping
`observation.images.wrist`, then retrain both with the unchanged recipe
(SmolVLA base, 30k steps, batch 32, single continuous run — **not** a `--base`
resume, per the LR-scheduler gotcha in RUNBOOK.md).

This restores the exact configuration that previously produced a nonzero success
rate, and A-vs-B alone is already a real sample-efficiency result (10 real vs 50
real) even before synthetic data enters.

### R2 — Decide Dataset C's cost

C needs a wrist-relative Isaac camera whose pose tracks FK per frame. The pieces
exist (`src/kinematics/forward_kinematics.py`, `src/isaac/camera_capture.py`
with the working Replicator pattern); it is a real but tractable task.

Do not start it until R1 shows a nonzero success rate — if two-camera A/B still
fail, the problem is upstream of synthetic data and C is wasted effort.

### R3 — DAgger / active learning (§22–23)

Correct, but premature. It belongs on top of a policy that works, not as a
rescue for a confounded one. Re-run it after R1/R2, seeded from the failures of
a two-camera policy.

## Explicitly dropped

- **`train_dagger1_clean30k` relaunch.** Trains on `grasp_v1_dagger1`, which is
  single-camera and inherits the confound. Would have cost several GPU hours and
  a hardware trial to produce another uninterpretable result.
- **The LR-resume-schedule hypothesis for Run D.** Still unproven, but no longer
  worth isolating — Run D's dataset is confounded regardless of the schedule.
  Keep the fix (single continuous runs) as standing practice.
- **The 5.2V / Overload-error hardware thread.** Per user, nothing physical
  changed; do not chase as degradation.

## Housekeeping (independent of the above)

1. **17 staged, uncommitted files (+2178)** — the whole Isaac bridge/kinematics/
   synthetic pipeline from 08-10/11. Never committed. Commit these.
2. **Every file in the repo shows as modified**: the working tree flipped to
   CRLF (committed content is LF), almost certainly Windows-side tooling on the
   shared NTFS drive. Add a `.gitattributes` with `* text=auto eol=lf` and
   renormalize, or the real diff stays invisible.
3. `./verify_ports.sh` — not yet run since the reboot.
4. Leader calibration (`black_20260801`) — fix attempted 08-14, never verified.
5. Stale root-owned `data/local/datasets/rollout_run_d` — remove.

---

# R0 result, 2026-08-14: 0/10 — but the failure moved forward two phases

| ep | grasp | transport | insert |
|---|---|---|---|
| 2, 3, 4 | ✓ | ✓ | ✗ |
| 5, 6 | ✗ | — | — |
| 7 | ✓ | ✓ | ✗ (closest) |
| 8, 9, 10 | ✗ | — | — |

Strict success **0/10**. Grasp 4/9. Insert 0/4 attempts. (Episode 1 unrecorded.)

## What 0/10 does and does not mean

The pre-registered reading of 0/10 was "the fault is in the eval path or the
hardware — stop." That reading does not survive the phase data. A broken eval
path does not produce a policy that repeatedly grasps a piece and carries it to
the board. The harness is sound and the checkpoint runs.

**The camera hypothesis is supported.** This two-camera policy transported the
piece repeatedly. Single-camera A/B/C never transported once in 40 combined
episodes. That is a real behavioural difference attributable to the wrist view.

**But 0/10 against this same checkpoint's historical 3/10 is a real
regression**, and the cause appears to be physical, not a matter of data.

## The board moved

Comparing an episode-start overview frame from `circle_insert_50ep` (the demos
this checkpoint trained on) against one from `rollout_baseline_2cam_r0`:

```
demo  green-feature centroid: (534.8, 343.4)
today green-feature centroid: (565.7, 337.5)
OFFSET dx=+30.9px dy=-5.9px  |d|=31.5px  (~19 mm)
```

A 50/50 blend of the two frames shows every board feature doubled, and the
doubling **grows toward the right edge** — so the board is rotated a few degrees
as well as translated. The background (towel, cutting mat) is unchanged, so the
workspace moved, not the camera. This is consistent with the arm's physical
relocation on 2026-08-11; the demos predate the move.

~19 mm plus rotation is fatal for peg-in-recess seating and largely harmless for
grasping (the policy locates the piece visually) and for transport (coarse).
That matches the observed failure pattern exactly.

**This also means A/B/C's 0/20 has two confounds, not one** — missing wrist
camera *and* a displaced board. Their result cannot be attributed to the camera
alone, and neither can it be used as a baseline for anything.

## Immediate next step, before any retraining

`./check_alignment.sh` overlays the live overview camera on
`docs/reference/board_reference_demo.png` and prints the offset in px and mm.
Nudge the board until it reads under ~5 px, then re-run
`./run_eval_baseline_2cam.sh` with a fresh tag.

If insertion starts working on a realigned board, R0 has passed, the harness and
hardware are cleared, and R1 proceeds with a trustworthy baseline. If it still
fails at 0 px offset, the board is not the explanation and the next suspect is
servo condition (the 5.2 V reading) or the grasp reliability drop.

**Do not retrain anything until the board is realigned.** Every dataset rebuilt
or policy trained against the current board pose would bake in the drift.

---

# Board pose belongs in the training distribution (user's point, 2026-08-14)

The board moving slightly is not noise to be eliminated — it is the deployment
condition. A policy that only works with the board at one pose is a scripted
trajectory with extra steps. Robustness to a shifted board should be a
first-class requirement.

## Measured: it was never in the training distribution

Board displacement across `circle_insert_50ep`, phase-correlated against the
first episode video:

| file | offset |
|---|---|
| file-000 | 0.0 px (reference) |
| file-001 | 3.7 px |
| file-002 | 3.9 px |
| file-003 | 4.3 px |

Max 4.3 px ≈ **2.5 mm**, and monotonic — slow creep across the recording
session, not deliberate variation. The board was effectively fixed, so no BC
policy trained on this data can be board-pose invariant. Tonight's ~16 mm
misalignment is 6-8x anything it ever saw.

## The synthetic pipeline has the same blind spot

`src/augmentation/randomization.py` samples `object_offset_x/y`, `yaw_deg`,
`mass_scale`, `friction_scale`, `robot_initial_joint_noise_deg`,
`camera_pixel_noise_std`. `scene_setup.apply_variation` moves and retunes the
*piece* only. **Board and table pose are never varied.**

So Dataset C's 100 synthetic episodes diversified only the axis the real demos
already varied, and inherited the fixed-board limitation wholesale. That is a
significant part of why C was never going to beat B on anything that matters.

## This gives synthetic augmentation a defensible thesis

"Fewer real demos for the same task" is weak — the rebuttal is "just record 40
more demos," which is cheaper than an Isaac pipeline. Board-pose invariance is
not: recording it for real means physically repositioning the board dozens of
times, while in sim it is one addition to the randomizer.

Revised primary claim, replacing the §21 framing:

> Real demos with a fixed board, plus synthetic episodes with randomized board
> pose, yield a policy that tolerates a displaced board — which the real data
> alone cannot produce at any episode count.

Directly testable: with the board aligned both policies should work; displaced
15-25 mm, only the synthetic-augmented one should survive. Evaluate across a
grid of board offsets rather than a single pose.

## Consequences for the plan

- Add board/table pose to `randomization.py` + `apply_variation` (translation in
  x/y and yaw). This becomes R2's main purpose, not just the wrist camera.
- Evaluation protocol gains a board-offset axis; §20's "randomize object
  position" should read "randomize object position *and board pose*."
- R0 is unaffected: it is a reproduction control and must run at the demos' own
  board pose. Robustness testing needs a policy trained for it, which does not
  exist yet.


---

# Correction, 2026-08-14: R0 was run against the wrong checkpoint

The 3/10 baseline is
`outputs/train/smolvla_circle_insert_50ep_trimmed_20000/checkpoints/020000` --
the trimmed, batch-32, 20,000-step run. `docs/windows-gpu-training-run-grasp-v1.md`
states it plainly: "The trimmed batch-32 checkpoint scores 3/10 on hardware --
the project's first completed insertions."

Every R0 attempt on 2026-08-14 used
`smolvla_circle_insert_50ep_30000/checkpoints/030000` instead: a different run,
on the untrimmed dataset, 30,000 steps at batch 8, with **no established
hardware score**. Both happen to be two-camera, so the camera reasoning in this
document stands; the checkpoint identification did not. It was an inference
written into this doc and RUNBOOK.md as if it were a recorded fact.

| checkpoint | dataset | steps | batch | hardware |
|---|---|---|---|---|
| `..._trimmed_20000/020000` | `circle_insert_50ep_trimmed` | 20000 | 32 | **3/10** |
| `..._50ep_30000/030000` | `circle_insert_50ep` | 30000 | 8 | unknown |

**Consequence: the 0/10 and 2/10 results from 2026-08-14 are not evidence about
the harness, the hardware, the board, or the peg.** They measure an unbenchmarked
checkpoint. The board and peg misalignments found along the way were real and are
now fixed, and the diagnostics built (alignment, servo scan, calibration check)
all stand -- but R0 itself has still never been run.

R0 remains outstanding, now against the correct checkpoint. Everything else is
ready for it: board 6.6px (~4mm), peg 10.0px (~6mm), follower calibration matches
white.json, all 12 servos healthy at 24-30C.
