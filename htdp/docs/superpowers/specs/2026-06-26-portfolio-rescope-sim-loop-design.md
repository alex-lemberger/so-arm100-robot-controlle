# Portfolio Re-Scope — Sim Loop (SO-ARM100) — Design

**Date:** 2026-06-26
**Type:** Strategic re-scope + milestone decomposition
**Status:** approved (brainstorm), pending spec review

## Why this document exists

The project began as "a human-task dataset pipeline to contribute to human-aware
robotics." Honest assessment of that goal: as a *dataset that advances the field*, the
project is underpowered against funded labs (Open X-Embodiment, DROID, Ego4D/EgoExo4D,
AgiBot) — solo capture cannot out-scale them, and EEG is a weak signal for manipulation.

This document re-aims the project at the goal the owner actually has, and prunes the scope
to match it.

## Goal (re-stated)

**Primary (B): a portfolio / door-opener for a robotics-company engineering role.** The
deliverable is a *working system with a demo video*, not a paper and not a large dataset.
Success = a recruiter or robotics engineer watches "human motion → robot executes the
task" and reads it as evidence of end-to-end systems skill on a modern robot-learning
stack.

**Secondary (A): a research contribution only if it falls out for free.** Not pursued
directly; not allowed to add scope.

## Audience and what it values

Target = robotics companies hiring engineers. They value, in order:

1. Working systems on real-ish hardware, end-to-end, that actually run.
2. Clean, tested, reproducible engineering (already a project strength).
3. Fluency with the current robot-learning stack — MuJoCo, **LeRobot**, imitation
   learning, teleoperation-style data collection, SO-ARM100.

They do **not** value: large datasets, neuroscience formats, or novel modalities that
don't drive a robot.

## Scope decisions (what changes)

### Cut / freeze

- **EEG — frozen, removed from the narrative.** Highest build cost, near-zero signal for
  a manipulation portfolio, and (with BIDS) makes the author read as a neuro researcher
  rather than a robotics engineer. Existing EEG code stays in the repo (it works, it's
  tested) but is dropped from the README/demo story. No further EEG investment.
- **VR-lighthouse capture rig (~950€) — deferred, not a prerequisite.** It only buys
  *self-captured* input. The portfolio centerpiece does not require it. Buy last, if ever.
- **BIDS export — demoted from the headline.** It's a neuroimaging standard. It stays as a
  supported export (it works), but the robot-facing story leads with rosbag2 (have it) and
  a LeRobot-compatible dataset format (to add). BIDS is not deleted; it's just not the
  pitch.
- **Platform phase (Postgres/MinIO/FastAPI/Docker, agent orchestration) — stays parked.**
  Off-message for this goal. Not revived unless the goal changes.

### Reframe (no new code, just naming)

- **The capture spine is positioned as *teleoperation data collection*** — the same
  paradigm as ALOHA / GELLO / LeRobot / SO-ARM100 leader-follower. The existing
  pose-stream → retarget → arm path *is* a teleop-replay pipeline; it is described as one.

### Add (the actual work)

Two milestones, each a standalone, demo-able portfolio artifact. Ship M1 first; M2 only if
time allows. Each gets its own spec → plan → implementation cycle (this document does not
plan their internals).

## Milestone 1 — Teleop-replay closes in sim (SO-ARM100)

**One-line:** a recorded/public human wrist trajectory drives a **simulated SO-ARM100** in
MuJoCo to perform a pick-and-place task, end to end, headless-or-viewer, deterministic.

**Why first:** lowest risk, and ~half-built. The repo already has vendored-arm IK
(`src/htdp/replay/ik.py`, mink + daqp, position + orientation tracking), a replay player
(`src/htdp/replay/player.py`), a synthetic motion generator (`src/htdp/synth/generate.py`),
and trajectory CSV export. If retarget+replay cannot work in sim, no hardware purchase
would rescue it; if it works in sim, swapping to a real arm later is mostly a driver layer.

**What's new in M1 (sketch — detailed in its own spec):**

- Swap the hand-authored 5/6-DOF `arm.xml` for a real **SO-ARM100 MuJoCo model** (from
  MuJoCo Menagerie / the LeRobot ecosystem), wired to the existing `mink` `FrameTask`
  (the spec notes `frame_name="eef"` is the only coupling — confirm/adjust for the new
  model's end-effector body).
- A minimal **task scene**: a table, an object to grasp, a target placement. Defines what
  "the task" visibly is in the demo.
- A simple **gripper / contact** step so "place" is real, not just an end-effector hover.
- **Input source for M1:** a public human-motion or mocap wrist trajectory (or the
  existing synthetic generator) — *no capture hardware*. The point is to prove the loop,
  not to use self-captured data yet.
- **Deliverable:** a recorded demo video + the existing determinism/tracking-error metrics
  reported for the real arm model.

**M1 done =** human-motion trajectory in → SO-ARM100 picks and places the object in sim,
reproducibly, with a video to show it.

## Milestone 2 — Learned policy (imitation learning)

**One-line:** collect N demonstrations in the M1 sim, train an imitation-learning policy
(LeRobot / ACT-style), and show the SO-ARM100 performing the task **autonomously** from the
learned policy.

**Why second:** higher wow and the strongest signal for robot-learning roles ("I collected
data *and* trained a policy that works"), but it carries the ML training/tuning risk. M1
must be solid first because M2 consumes M1's sim + task as its data source.

**What's new in M2 (sketch — detailed in its own spec):**

- Export M1 rollouts in a **LeRobot-compatible dataset format** (this is also the
  robot-facing export that replaces BIDS in the headline).
- Train an imitation policy with LeRobot; evaluate success rate vs a scripted/IK baseline.
- **Deliverable:** a second demo video (autonomous policy) + a short success-rate metric.

**M2 done =** a learned policy drives the SO-ARM100 to complete the task autonomously in
sim, with a reported success rate beating the no-learning baseline.

## Hardware sequencing (spend nothing now)

```
M1  Sim loop closes (public data → MuJoCo SO-ARM100)   0€     proves the hard part
M2  Learned policy in sim                              0€     strongest single artifact
--- buy only after the above demo-able ---
    Swap sim arm → real SO-ARM100 (~150€)              buy when sim loop works
    Swap public data → self-capture (VR rig ~950€)     buy last, optional polish
```

Each purchase is made against a validated design, not a guess. Real-arm and self-capture
are explicitly **out of scope for this document** — they are future milestones unlocked by
M1/M2.

## Non-goals (this re-scope)

- No new EEG work; no reviving the platform phase; no VR-rig purchase.
- No real-arm work yet (M1/M2 are sim-only).
- No large-dataset push; data volume is not a success metric here.
- No research-paper framing; the secondary research angle is opportunistic only.

## Risks

- **SO-ARM100 model fidelity / IK coupling.** The new model's joint layout and
  end-effector body may need IK re-tuning vs the hand-authored arm. Mitigated by M1 being
  scoped narrowly around exactly this swap.
- **M2 training is the genuinely hard, time-variable part.** Mitigated by M1 being a
  complete portfolio artifact on its own — M2 is upside, not a dependency for "done."
- **Scope creep back toward dataset/EEG/platform.** Mitigated by the explicit cut list
  above; revisit only on a goal change.

## Decomposition / next step

This document sets strategy and decomposes into M1 and M2. It does **not** design their
internals. Next: write the **M1 implementation plan** (SO-ARM100 swap + task scene +
gripper + public-input wiring + demo). M2 gets its own spec + plan after M1 ships.
