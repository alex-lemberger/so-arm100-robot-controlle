# Linux session handover: 2026-08-15

**Read `docs/RUNBOOK.md` first** for ports, docker commands and current
hardware facts. This doc is only what happened and what to do next.

## The headline

**The project has a working reference on this machine for the first time since
the move, and its first completed insertion.**

`outputs/train/smolvla_circle_grasp_v1_20000/checkpoints/020000` had never been
evaluated on hardware. It sat unused for five days behind a line in the
2026-08-10 handover ("Checkpoint has not been evaluated on hardware yet. That
evaluation happens on the Mac (not Linux)"), while three sessions went into
re-evaluating a weaker checkpoint. It was built specifically to fix the grasp
failure everyone was chasing.

## Do this first

```bash
cd so-arm100
./verify_ports.sh                       # now serial-based, no unplug needed
./check_alignment.sh --out board_alignment.png
./run_eval_grasp_v1.sh grasp_v1_r2      # 10 episodes, needs you at the robot
```

Phase-log every episode: **grasp / transport / insert**, and keep
**"never released"** as its own category — it is a distinct failure from
"dropped short" and both have now been seen.

Why this first: today's rate rests on 8 episodes. Every comparison from here is
measured against it, so it is worth 20 minutes to pin down before anything is
built on top of it.

## Results, 2026-08-15

### R0 — `smolvla_circle_insert_50ep_trimmed_20000/checkpoints/020000`

The historical 3/10 checkpoint, run correctly for the first time. **0/10.**

| ep | grasp | transport | insert | notes |
|----|-------|-----------|--------|-------|
| 1–4 | no | – | – | no grasp |
| 5 | YES | ? | no | grasped, no insert |
| 6 | YES | ? | no | grasped, never released |
| 7–10 | no | – | – | no grasp |

Grasp 2/10, transport 0/10, insert 0/10.

### grasp_v1_r1 — `smolvla_circle_grasp_v1_20000/checkpoints/020000`

8 of 10 episodes logged (1–2 were not reported).

| ep | grasp | transport | insert | notes |
|----|-------|-----------|--------|-------|
| 1–2 | ? | ? | ? | not reported |
| 3 | YES | YES | no | |
| 4 | no | – | – | |
| 5 | YES | YES | no | |
| 6 | no | – | – | |
| 7 | YES | YES | no | never released |
| 8 | no | – | – | |
| 9 | no | – | – | |
| 10 | YES | YES | **YES** | first completed insertion on this machine |

| phase | R0 | grasp_v1 | Fisher p |
|---|---|---|---|
| grasp | 2/10 | 4/8 | 0.32 |
| transport | 0/10 | 4/8 | **0.023** |
| insert | 0/10 | 1/8 | — |

**Transport is the only part that holds up statistically.** R0 never
transported once; grasp_v1 transported in every episode where it grasped. The
grasp gain is within noise at n=8 — do not quote it as established. The single
insertion is an existence proof, not a rate.

## What NOT to re-litigate

Each of these cost real time to establish today.

- **The hardware is fine.** `./teleop_check.sh` gave 5/5 solid grasps by hand.
  The gripper and the 5.2V rail are cleared. Do not reopen this on the basis of
  a poor autonomous grasp rate — poor grasp is this task's oldest symptom.
- **Perception is fine.** Review of R0's own rollout footage shows the arm
  reaching the peg in nearly every episode and failing at the moment of
  closing. It is not failing to find the peg.
- **The board and peg were correctly placed** for both runs (board 6.4px/~4mm,
  peg ~7px/~4mm).
- **`check_alignment.sh` reporting `PEG: ... live=MISSING` is a detector bug,
  not a misplaced peg.** `peg_centroid()` in `robot_learning/align_board.py`
  uses fixed HSV thresholds (hue window 70–100); in daylight the peg reads ~49
  and the mask returns zero pixels. The board detector was already migrated to
  phase correlation for exactly this reason — the peg one never was. Cosmetic,
  but it will print every session until someone fixes it.
- **The 3/10 belongs to `trimmed_20000`**, confirmed against the primary source
  (`docs/windows-gpu-training-run-grasp-v1.md`). It was measured on or before
  2026-08-10, i.e. on the Mac setup, before the PC moved on 08-11. **It has
  never been reproduced on this machine and is not a target this setup has hit.**

## The decision waiting for you

**Next session on the robot, or on the pipeline?**

- **Robot**: re-measure the baseline, then DAgger. Needs you present throughout.
- **Pipeline**: re-export A/B/C with both cameras and retrain. Fully offline.

Recommended: the 20-minute re-measure to lock the baseline, then the bulk of the
time on the re-export — that is where the actual research question (§32) lives,
and it has been blocked for a week on a bug that is now fixed.

## Pipeline state — two facts that changed the plan

**The camera confound is fixed in tooling.** `scripts/export_lerobot_dataset.py`
now carries both cameras and hard-fails if the wrist view is missing. Datasets
A/B/C can be re-exported properly; the invalidated §19–21 experiment is
re-runnable.

**The synthetic action mislabelling is NOT fixed, and it is worse than a
nuisance.** `scripts/generate_synthetic.py` randomizes object position ±3cm
(`configs/simulation.yaml`, `randomization.object_position`) but copies the
parent episode's action trajectory verbatim. The frames show the peg in a new
place while the labels say "reach where it used to be" — that trains the policy
to ignore the peg's position, which is the exact failure being fought. **Any
dataset containing those episodes is actively harmful, not merely diluted.**

Fixing pose labels needs IK, which the repo does not have. **There is a way
around it that needs no IK:** restrict randomization to label-preserving axes —
lighting, exposure, texture. Those leave the actions exactly valid, and they
target something measured today: the R0 workspace ran ~15–20% darker than the
training demos (rollout V 151–164 vs demo V 180–188). A near-free version is
brightness/contrast jitter as a training-time augmentation on the real data —
no Isaac, no IK, one training run.

## Do not do yet

**DAgger on the never-release failure.** It is the most visible symptom, but it
rests on one observation out of four transports, and correcting a policy whose
baseline rate is not yet pinned down is how the previous DAgger round became
uninterpretable. Re-measure first.

## Hardware state at end of session

Follower `white` on `/dev/ttyACM1`, leader `black_20260801` on `/dev/ttyACM0`
(serial-verified — `verify_ports.sh` no longer needs an unplug test). Board and
peg are on their pencil marks at the **demo** position (~114mm from the base
front edge), not the 65mm the user prefers. Both eval runs used that position;
keep it until a decision is made to move and re-record.

**Check the arm is powered down / torque released before leaving it unattended.**

## Git

Branch `eval-grasp-v1-baseline` merged fast-forward into `master`; both are at
`cedef45`. `master` is **19 commits ahead of `origin/master` and unpushed**.

`so-arm100/package-lock.json` has an unrelated pre-existing modification (line
ending churn, ~516 lines). Left untouched deliberately.
