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
| `smolvla_circle_insert_50ep_30000` (pre-Isaac baseline) | overview + **wrist** | **3/10** |
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
