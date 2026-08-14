# Linux session handover: 2026-08-14 evening

**Read `docs/RUNBOOK.md` first** for anything about ports, docker commands or
current hardware facts. This doc is only what to do next.

## Do this first

```bash
cd so-arm100
./check_alignment.sh --out board_alignment.png     # board AND peg, expect both green
./run_eval_baseline_2cam.sh r0_correct             # 10 episodes, needs you at the robot
```

Phase-log each episode: grasp / transport / insert, plus timeouts as their own
category. That is what turned an uninformative 0/10 into the finding that the
failure had moved forward two phases.

## The one thing that will waste your time if you miss it

**R0 has never actually been run.** All three eval attempts on 2026-08-14 used
the wrong checkpoint.

The 3/10 baseline is the **trimmed, batch-32, 20k-step** run:

```
outputs/train/smolvla_circle_insert_50ep_trimmed_20000/checkpoints/020000/pretrained_model
```

`docs/windows-gpu-training-run-grasp-v1.md` says it directly: *"The trimmed
batch-32 checkpoint scores 3/10 on hardware."* The runs used
`smolvla_circle_insert_50ep_30000/checkpoints/030000` instead — untrimmed
dataset, 30k steps, batch 8, **no established hardware score**.

So the 0/10 and 2/10 results say nothing about the harness, the hardware, the
board or the peg. `run_eval_baseline_2cam.sh` now points at the correct
checkpoint (verified: loads, two cameras, 450M params).

## State of the setup, verified this session

| | state |
|---|---|
| Board alignment | 6.6px (~4mm) — inside the demos' own ~2.5mm drift |
| Peg alignment | 10.0px (~6mm) — "where the demos put it" |
| Follower calibration | matches `white.json`, all 6 motors |
| Servos | all 12 respond, 24-30°C, 5.2V idle |
| Ports | follower `ttyACM1`, leader `ttyACM0`, matching CONFIG |
| Wrist camera | working — sharp frames, stats matching the demos |

Board and peg are pencil-marked. **The board is currently at the DEMO position
(~114mm from the base front edge), not the 65mm the user prefers.** That is
deliberate: R0 has to run under the conditions its checkpoint was trained on.
Once R0 clears the system, move the board back to 65mm and re-record there.

## What NOT to re-litigate

- **The wrist camera is fine.** It was briefly called broken on the basis of one
  blurry frame at t=0.2s; sampling across an episode shows board, peg and jaws
  clearly, with statistics matching the demos.
- **The follower calibration is correct.** Checked against `white.json` this
  session, all six motors.
- **No servo is dead.** One transient `no status packet` on id 4 at
  torque-enable; a retry connected fine. If it recurs *at torque-enable*, that is
  where the 5.2V rail is worth a look — not before.
- **A/B/C's 0/20 is explained**: they are overview-camera-only. Every policy that
  ever scored non-zero used overview+wrist. See
  `docs/replan-2026-08-14-camera-confound.md`.

## After R0

- **~3/10** → harness and hardware cleared. Move the board back to 65mm, mark the
  peg, re-record 50 episodes there, retrain.
- **grasp reliable but no insert** → seating is a policy gap; DAgger targeted at
  insertion.
- **still poor grasp with everything aligned** → distribution is not the problem;
  servo condition and the 5.2V rail move to the top before any recording.

The user asked directly whether a re-recorded 50 episodes guarantees a working
policy. It does not: the project's best ever result is 3/10, and grasp
reliability is currently the binding constraint. R0 is the cheap way to find out
whether recording is an investment or a waste.

## Also landed this session

Scene gate (`./check_scene_gate.sh`) now blocks synthetic generation until the
scene has been checked against a real frame and approved, keyed to a hash of
`configs/simulation.yaml`. The board is modelled from measured dimensions
(`docs/reference/toy.png`), the robot faces **-Y**, and the synthetic pipeline
renders the wrist view. Full detail in
`docs/replan-2026-08-14-camera-confound.md`.

Known-unfixed: `generate_synthetic.py` randomizes the scene but replays the
original trajectory, so randomized frames are paired with actions for the
*original* object pose. That mislabelling affects the existing peg randomization
and would affect board randomization. Fixing it needs IK, which the repo does not
have.

## Git

16 commits on branch `isaac-pipeline-recovery`, **not merged to master**.
