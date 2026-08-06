# Roadmap

## v0.1 — Synthetic spine (complete)

The first milestone proves the *factory* works before any hardware exists.

**Done:**
- Python package + `uv`/`ruff`/`mypy`/`pytest` tooling
- Pydantic schemas + JSON Schema export (`docs/schemas/`)
- Seeded synthetic session generator with deliberate defect injection (dropped-sample gap + clock drift)
- Checksum-based immutability enforcement (`checksums.sha256`)
- Schema + structure + checksum validation (`htdp validate`)
- Processing pipeline: raw CSV → Parquet (`htdp process`, raw read-only)
- QC report: per-stream + cross-stream checks, pass/warn/fail severity, JSON + HTML output (`htdp qc`)
- Consent gate: block-on-conflict, three release profiles, atomic staging (`htdp package`)
- Reproducibility: identical release-manifest checksums across two runs
- MuJoCo mocap-body replay from the packaged release (optional dep, smoke-tested headless) (`htdp replay`)
- IK / robot-arm replay (beyond mocap spheres): differential IK with mink+daqp, vendored 6-DOF arm (`htdp replay-ik`), trajectory export to CSV (`--out`), full-pose orientation tracking (`--orientation-cost`)
- AGENTS.md harness instructions
- Docs: ARCHITECTURE, DATA_CONTRACT, ETHICS_AND_CONSENT, this ROADMAP
- Protocol: `protocols/reach-grasp-place.md`

---

## v0.2 — Real hardware ingest (planned, not started)

**Deferred from v0.1:**
- Postgres / MinIO / FastAPI / Docker Compose
- Angular operations dashboard
- Real hardware: VIVE tracker capture, LSL streaming, XDF ingest (`htdp ingest`: XDF → raw representation) — **in progress (XDF adapter landed)**
- Video capture (MP4 population in the `video/` slot) — **in progress (ingest-video landed)**
- EEG capture — **in progress (XDF eeg ingest landed; EEG-BIDS export landed)**
- ROS 2 / rosbag2 export — **done** (motion + events + EEG via `htdp export-release-rosbag`)
- Motion-BIDS export — **done** (single-session + multi-subject release-level export)
- Consent *filtering* — strip disallowed modalities from a release while still including the session — **done (per-session granularity landed; modality files dropped only from sessions whose consent forbids them)**
- Multi-session queryable catalog — **done** (`htdp catalog` + `htdp catalog-query` with range filters landed; release-level inventory via `htdp catalog-releases` landed)
- Agent-orchestration layer (Hermes / OpenClaw)
- Remote / multi-user access
- `htdp serve` — dashboard serving surface (read endpoints + single-concurrency job runner);
  localhost-only, optional `serve` extra. Consumed by the Angular control-center dashboard.

**Guiding principle for v0.2:** add one real modality at a time. Each modality adds an
`ingest` adapter that normalizes to the existing raw representation — the downstream
pipeline (validate → process → qc → package) must not change.

---

## Portfolio re-scope — M1: sim loop (done)

Per the 2026-06-26 re-scope (`docs/superpowers/specs/2026-06-26-portfolio-rescope-sim-loop-design.md`),
the project is re-aimed at a robotics-engineering portfolio: a working **human-motion →
robot** demo over a large dataset. EEG / VR-rig / platform work is frozen; the headline is
teleop-replay on a real robot model.

**M1 — done:** `htdp sim-task` retargets a recorded wrist trajectory through differential IK
onto a vendored **Franka Emika Panda** (MuJoCo Menagerie) 7-DOF arm, which picks an object
top-down and places it on a target. Headless, deterministic (`place_error_m=0.0000`,
`grasp_dist_m=0.0001`), `--video` renders an MP4 (`docs/demo/m1_pick_place.mp4`). IK tracks a
grasp site between the fingertips; the full waypoint path is solved as one warm-started
continuation (no per-waypoint reset). Grasp is a kinematic attach; collision bitmasks keep the
gripper from disturbing the object pre-grasp. (The original SO-ARM100 was dropped: its 5 DOF
cannot orient a gripper top-down at a tabletop target — see git history.)

**M2 — done:** state-based imitation learning. `htdp gen-demos` runs the M1 scripted teacher
over randomized cube positions and records `(observation.state, action)` demos in
LeRobotDataset format; `htdp train-policy` trains a compact action-chunking transformer (ACT)
in PyTorch/MPS with observation-noise augmentation; `htdp eval-policy` runs the learned policy
**autonomously closed-loop** (receding-horizon action chunks) over 25 held-out cube positions
and reports success-rate vs the scripted-IK baseline. Result: **policy 100% success,
place_error 0.0025 m**, matching the baseline (`docs/demo/m2_eval.json`). Scope: held-out
positions are sampled from the **same 10×10 cm region** as training (in-distribution
interpolation, not extrapolation to novel regions), and execution is **kinematic** (the policy
reproduces the teacher's gripper trajectory; no actuator dynamics). Grasp is the M1 kinematic
attach gated on the policy's gripper action. Three classic imitation pitfalls were found and
fixed in the process: a normalization landmine on a constant feature (gripper width — dropped),
a kinematic-vs-physics action mismatch (actuator control abandoned for kinematic, matching the
teacher), and compounding error (cut via obs-noise training + executing most of each action
chunk before re-planning). Visuomotor (pixels) + true-physics actuator control deferred to M2.5.

**M2.5 — next:** pixel observations (visuomotor ACT) and/or physics-actuator demos+control.

---

## Out of scope (named, not forgotten)

The following were considered and explicitly deferred — not missed:

- Postgres, MinIO, FastAPI, Docker in v0.1 (no concrete reason yet; filesystem suffices)
- LSL/XDF in v0.1 (a planned `ingest` step will bridge it; raw-as-CSV is intentional)
- Video and EEG (schema slots exist; data capture deferred)
- ROS 2 / rosbag2 — **done** for motion + events + EEG (`htdp export-release-rosbag`)
- IK/robot-arm replay — **done** (mocap spheres via `htdp replay`, differential IK + trajectory export via `htdp replay-ik --out`, orientation tracking via `--orientation-cost`)
- Multi-session catalog (single-session pipeline is enough for v0.1 trust claim)
