# Current System — SO-ARM100 Shape-Sort

Produced by Phase 0 inspection (AGENTS_NEW.md §5). Do not change architecture during this step.

**Hardware table below predates the 2026-08-11 Linux relocation — ports are
the old Mac values. See `docs/RUNBOOK.md` for current ports, docker
invocation, and calibration paths.** Kinematics/control/dataset-format
sections below are still accurate.

---

## Hardware

| Item | Value |
|---|---|
| Robot | SO-ARM100 follower arm (`so100_follower`) |
| Leader | SO-100 leader arm (`so100_leader`) |
| Follower port | `/dev/cu.usbmodem5AE60582701` |
| Leader port | `/dev/cu.usbmodem5B140329561` |
| Recording machine | MacBook (Mac) |
| Training machine | Windows PC with RTX 5070 |
| Simulation machine | Linux workstation with Isaac Sim |

---

## Robot Kinematics

6 DOF single arm.

| Index | Joint name (LeRobot) | Unit | Notes |
|---|---|---|---|
| 0 | `shoulder_pan` | degrees | horizontal rotation |
| 1 | `shoulder_lift` | degrees | forward/back |
| 2 | `elbow_flex` | degrees | |
| 3 | `wrist_flex` | degrees | |
| 4 | `wrist_roll` | degrees | |
| 5 | `gripper` | % | 0 = closed, 100 = open |

Raw servo values are Dynamixel ticks (0–4095). `normalize_ticks()` in `build_lerobot_dataset_v2.py` converts to degrees/%.

---

## Control

| Parameter | Value |
|---|---|
| Control mode | Position |
| Control frequency | 30 Hz |
| Max relative target (rollout) | 25.0 ticks |
| Gripper representation | Continuous float (not binary) |

---

## Cameras

| Name | Type | Resolution | FPS | Codec |
|---|---|---|---|---|
| `overview` | OpenCV index 1 | 1280×720 | 30 | AV1 |
| `wrist` | OpenCV index 0 | 1280×720 | 30 | AV1 |

Camera indices are not stable across reboots. Re-run `lerobot-find-cameras opencv` if recordings look wrong.

---

## Dataset Format

| Parameter | Value |
|---|---|
| LeRobot version | `v3.0` (`codebase_version`) |
| Storage | Parquet (data) + MP4 (video) |
| Action dtype | float32, shape [6] |
| Observation dtype | float32, shape [6] |
| Action = observation | Yes — position targets match measured state names |

### Field names in parquet

```
action:                  [shoulder_pan.pos, shoulder_lift.pos, elbow_flex.pos,
                          wrist_flex.pos, wrist_roll.pos, gripper.pos]
observation.state:       same
observation.images.*:    video references
timestamp, frame_index, episode_index, index, task_index
```

---

## Dataset Inventory

| Dataset | Episodes | Frames | Tasks | Size |
|---|---|---|---|---|
| `circle_insert_50ep` | 50 | ~26,078 | 1 | ~754 MB |
| `circle_insert_50ep_trimmed` | 50 | ~26,078 | 1 | ~754 MB |
| `circle_grasp_v1` | 81 (50 insert + 31 grasp) | 31,541 | 2 | 915 MB |

Task strings:
- `"Insert the circle piece into its matching hole."`
- `"Pick up the circle piece."`

---

## Existing Scripts

| Script | Purpose |
|---|---|
| `robot_learning/loop.py` | Record / train / eval thin wrapper |
| `robot_learning/build_lerobot_dataset_v2.py` | Convert app recordings → LeRobot v3 |
| `robot_learning/merge_datasets.py` | Merge two LeRobot datasets |
| `robot_learning/inspect_episode.py` | Health-check a raw app recording |
| `robot_learning/dagger_ui.py` | DAgger correction UI |
| `robot_learning/loop.py eval` | Rollout with RTC inference |

---

## Isaac Sim

| Item | Value |
|---|---|
| Host | Linux workstation |
| Status | Isaac Sim GUI not installed; `leisaac-sim:latest` Docker image (28.9GB, contains a full `/isaac-sim` install) is available and was used instead |
| Robot asset | RobotStudio SO-ARM100 USD at `/media/alex/F6E48479E4843DBD/Users/info/Downloads/Robots/RobotStudio/so100/so100.usd` (external to the repo, on a Windows-shared NTFS mount) |
| Isaac joint names | **Verified 2026-08-10** — identical to real LeRobot names, see `configs/robot_mapping.yaml` |

Also present on this machine (not used, kept for reference): two third-party SO-**101** Isaac Lab projects at `~/projects/isaac-sim/leisaac` and `~/projects/isaac-sim/Sim-to-Real-SO-101-Workshop`. These are for the newer SO-101 arm, not our SO-100 hardware, so the RobotStudio SO-100 asset above was used instead.

Joint names were read headlessly (no GUI, no Isaac Sim `.bat`/launcher) by loading `pxr.Usd` / `pxr.UsdPhysics` from the Docker image's `omni.usd.libs` extension directly:

```bash
docker run --rm -v /path/to/so100:/mnt/so100:ro leisaac-sim:latest bash -c '
export PYTHONPATH="/isaac-sim/extscache/omni.usd.libs-1.0.1+69cbf6ad.lx64.r.cp311:/isaac-sim/extscache/omni.usd.schema.physx-107.3.26+107.3.3.lx64.r.cp311.u353"
export LD_LIBRARY_PATH="/isaac-sim/extscache/omni.usd.libs-1.0.1+69cbf6ad.lx64.r.cp311/bin:$LD_LIBRARY_PATH"
/isaac-sim/kit/python/bin/python3 -c "
from pxr import Usd, UsdPhysics
stage = Usd.Stage.Open(\"/mnt/so100/so100.usd\")
for prim in stage.Traverse():
    if \"Joint\" in prim.GetTypeName():
        print(prim.GetPath(), prim.GetTypeName())
"'
```

Result — all 6 joints live under `/so_arm100/joints/`, names match the real robot exactly:

| Real name | Isaac name | Type | Axis | USD limit (deg) |
|---|---|---|---|---|
| shoulder_pan | shoulder_pan | Revolute | Y | -114.59 to 114.59 |
| shoulder_lift | shoulder_lift | Revolute | X | 0.0 to 200.54 |
| elbow_flex | elbow_flex | Revolute | X | -180.0 to 0.0 |
| wrist_flex | wrist_flex | Revolute | X | -143.24 to 68.75 |
| wrist_roll | wrist_roll | Revolute | Y | -180.0 to 180.0 |
| gripper | gripper | Revolute | Z | -11.46 to 114.59 |

Articulation root: `/so_arm100/root_joint` (has `ArticulationRootAPI`).

**Gripper is rotational, not linear.** The placeholder mapping assumed a prismatic (metres) gripper joint; the actual USD gripper joint is a `PhysicsRevoluteJoint` with an angular drive (`drive:angular:physics:*` attrs), same as the other 5 joints. `configs/robot_mapping.yaml` has been corrected accordingly.

**Units:** USD-authored joint limit/drive attributes are in degrees for every joint (USD physics schema convention for revolute joints). Isaac Sim's runtime articulation control API (`get/set_joint_positions`) operates in radians — confirmed by cross-referencing the third-party `Sim-to-Real-SO-101-Workshop` repo's `ArticulationCfg.InitialStateCfg.joint_pos`, which uses small radian-scale values (e.g. `-0.2736`) for the equivalent SO-101 joints. The trajectory converter must apply `deg2rad` to all six joints, including gripper.

---

## Scene: table + object (Task 7)

`configs/simulation.yaml` + `src/isaac/scene_setup.py` add a table and one object to the
Isaac scene, wired into `scripts/replay_episode.py` via an opt-in `--scene-config` flag
(off by default, so it can't perturb the already-validated bare-robot joint replay).

The real workspace has no elevated table -- the SO-ARM100 base sits directly on a desk
surface (see `circle_grasp_v1`'s `observation.images.overview` frame 0: robot base, a
wooden shape-sorter puzzle board, and a small "circle" peg all share one flat plane, on a
sheet of paper). So the sim "table" is a thin static `FixedCuboid` slab whose top face
sits at z=0 (the USD robot's own root height), and the "object" is a `DynamicCylinder`
standing in for the wooden peg -- both dimensions and starting position are eyeballed
from that camera frame, not yet measured on the real setup (see comments in
`configs/simulation.yaml`).

Verified 2026-08-11: re-ran `circle_grasp_v1` episode 0 with `--scene-config
configs/simulation.yaml` and compared against the bare-robot baseline
(`data/evaluation/replay_episode_000.json`). Mean EE error matched to 7 decimal places
(0.0030288m both runs), and the object's pose after 635 frames was essentially unchanged
from its initial placement (`[0.17999981, -0.04999984, 0.01400001]` vs initial
`[0.18, -0.05, 0.014]`) -- confirms the added static/dynamic bodies don't interpenetrate
or otherwise perturb the robot's tracked motion.

```bash
/isaac-sim/python.sh scripts/replay_episode.py \
  --dataset data/circle_grasp_v1 --episode 0 \
  --config configs/robot_mapping.yaml \
  --scene-config configs/simulation.yaml \
  --validation-out data/evaluation/replay_episode_000_with_scene.json
```

---

## Synthetic data generation (Task 9)

`scripts/generate_synthetic.py` boots Isaac once and loops in-process over N synthetic
episodes (no per-episode Kit reboot). Per episode it:

- samples a `Variation` (object x/y offset, yaw, mass scale, friction scale, robot initial
  joint noise, camera noise std) deterministically from `configs/simulation.yaml`'s
  `randomization:` section + a per-episode seed (`src/augmentation/randomization.py`, no
  Isaac imports, independently testable)
- applies it to the already-placed scene object via `src/isaac/scene_setup.py::apply_variation`
  (moves/rotates it, rescales mass, retunes a persistent `PhysicsMaterial`'s friction --
  doesn't recreate any prim, so it's safe to call every iteration)
- randomizes the robot's starting joint pose (small jitter around the USD zero-pose) before
  settling and replaying -- but replays the SAME commanded joint trajectory as the parent
  real episode. Motion is NOT re-planned at this stage (Rule 4) -- only the scene and the
  approach-to-frame-0 transient are randomized.

`scripts/replay_episode.py`'s settle/replay loop was factored out into `src/isaac/replay_loop.py`
so both scripts share one implementation; re-ran the bare-robot baseline after the refactor and
confirmed byte-identical output to the pre-refactor `replay_episode_000.json`.

Ran the Task 9 target for real: 10 real parent episodes (`circle_grasp_v1`, episodes 0-9) →
100 synthetic episodes, 2026-08-11. Isaac boots once (~14s) then averages ~2s/episode once
warmed up -- 100 episodes took ~4 minutes total wall time. Result: 100/100 succeeded, 0
failures, mean EE tracking error 6.47mm average (1.71-27.37mm range across episodes) -- no
physics blow-ups from any sampled combination of randomization params. Output:
`data/synthetic/circle_grasp_v1/` (`synthetic_NNNN.json` per episode with full commanded/
actual joint trajectories + provenance metadata per AGENTS_NEW.md Sec 17, plus `manifest.json`).

Camera pixel noise is sampled and recorded in provenance but not actually applied to any
render -- `--capture-dir` rendering is still the known-unresolved bug from the 08-11 session
(camera not bound to the right render product); not worth blocking Task 9's core
object/mass/friction randomization on a parked, non-blocking subsystem (Rule 4).

```bash
/isaac-sim/python.sh scripts/generate_synthetic.py \
  --dataset data/circle_grasp_v1 --parent-episodes 0-9 \
  --config configs/robot_mapping.yaml --scene-config configs/simulation.yaml \
  --num-synthetic 100 --seed 0
```

---

## Camera rendering fix + LeRobot export (Task 18)

The `--capture-dir` camera bug from the earlier 08-11 session is FIXED. Root cause was
never the render-product binding (the prior session's suspicion) -- it was the hand-derived
look-at quaternion math pointing the camera at empty space. Fix, in
`src/isaac/camera_capture.py`: use Replicator's own `rep.create.camera(position=...,
look_at=...)` + `rep.create.render_product()` + `AnnotatorRegistry.get_annotator("rgb")`
(the pattern Isaac's own `standalone_examples/api/isaacsim.replicator.examples/multi_camera.py`
uses), instead of `isaacsim.sensors.camera.Camera` + a hand-rolled quaternion. Verified
visually: robot + table + object all render correctly with lighting/shadows.

`scripts/export_lerobot_dataset.py` builds a real `LeRobotDataset` (native format, trainable
by the normal `lerobot-train` pipeline) mixing real and synthetic episodes:

- Real episodes are read straight from the source dataset via `LeRobotDataset` indexing
  (image tensors come back CHW from its read-path transform; permuted back to HWC to match
  the on-disk/feature-declared convention before re-adding).
- Synthetic episodes re-simulate in Isaac using the EXACT recorded `Variation` from their
  `scripts/generate_synthetic.py` JSON (not re-sampled -- reproduces the same physics run
  that JSON's validation stats describe), this time with rendering on. Each frame's
  `action`/`observation.state` are copied verbatim from the parent real episode's own
  per-frame values (Task 9 doesn't re-plan motion, so the parent's recording IS the correct
  label; only the rendered image differs, driven by the randomized object).
- Provenance: an `episode_source_type_id` feature (0=REAL_HUMAN, 1=SIM_SYNTHETIC) plus a
  `meta/provenance.json` sidecar with full detail (parent episode, seed, randomization) --
  LeRobot's own schema has no field for this, and Task 18 explicitly says keep it, don't
  silently mix.
- Scope cut: overview camera only (no wrist) -- rendering a wrist-relative camera for
  synthetic frames would need per-frame FK-driven positioning, not built yet.

Smoke-tested on 1 real + 2 synthetic episodes first (validated image channel-order handling,
resolution matching, provenance correctness) before running the full export target: all 10
real parent episodes + all 100 synthetic episodes (i.e. exactly "Dataset C" from Sec 19) into
`data/local/datasets/circle_grasp_v1_mixed_10r_100s`. Per-episode cost is dominated by RTX
rendering + video encoding, not physics (~0.07-0.09s/frame render+step, plus ~15-60s/episode
video-encode overhead that's present for real episodes too).

**Completed 2026-08-11**: 110 episodes (10 REAL_HUMAN + 100 SIM_SYNTHETIC, confirmed via
`meta/provenance.json`), 61,952 frames, 362MB, ~68 minutes wall time (real episodes ~7min,
synthetic ~61min). This dataset is trainable right now with the normal `lerobot-train`
pipeline.

Datasets A and B (Sec 19) were also built the same way, `--real-episodes` only (no
`--synthetic-dir`, so no Isaac rendering -- much faster, real episodes only take video
decode/re-encode time):

| Dataset | Episodes | Frames | Path | Wall time |
|---|---|---|---|---|
| A | 10 real (0-9) | 5,632 | `data/local/datasets/circle_grasp_v1_real10` | ~6 min |
| B | 50 real (0-49) | 26,078 | `data/local/datasets/circle_grasp_v1_real50` | ~24 min |
| C | 10 real (0-9) + 100 synthetic | 61,952 | `data/local/datasets/circle_grasp_v1_mixed_10r_100s` | ~68 min |

A's 10 real episodes are the same as C's real component (episodes 0-9), and B's 50 are a
superset of those -- deliberately controlled so the comparison isn't confounded by which
episodes were picked. All three are ready to train on. The actual A/B/C training comparison
(Sec 19-21 -- the project's primary research metric) is a Windows-GPU-training-machine step,
not a Linux/Isaac step, per this repo's 3-machine workflow.

```bash
/isaac-sim/python.sh scripts/export_lerobot_dataset.py \
  --real-dataset data/circle_grasp_v1 --real-episodes 0-9 \
  --synthetic-dir data/synthetic/circle_grasp_v1 --synthetic-episodes all \
  --config configs/robot_mapping.yaml --scene-config configs/simulation.yaml \
  --output data/local/datasets/circle_grasp_v1_mixed_10r_100s \
  --repo-id local/circle_grasp_v1_mixed_10r_100s
```

---

## Open Questions

1. ~~Isaac joint names~~ — resolved, see table above.
2. ~~USD asset path~~ — resolved: `/media/alex/F6E48479E4843DBD/Users/info/Downloads/Robots/RobotStudio/so100/so100.usd`. Consider copying into the repo (e.g. `so-arm100/assets/isaac/`) so the pipeline isn't tied to a path on a Windows-shared drive.
3. ~~Joint units in Isaac~~ — resolved: degrees in the USD, radians via the runtime API.
4. **Gripper mapping polarity** — `configs/robot_mapping.yaml` assumes real 0% (closed) maps to the Isaac lower limit and 100% (open) maps to the upper limit. Unverified against real hardware; confirm during first replay and flip `invert` if backwards.
5. **Tick → degree formula** — verify `normalize_ticks()` output matches Isaac's zero pose.
6. **No local LeRobot/Isaac Python environment yet on this machine** — no system `pip`, no `lerobot` package importable, and Isaac Sim itself is only available via the `leisaac-sim:latest` Docker image (no native GUI install found). `scripts/inspect_dataset.py` and the upcoming `trajectory_converter.py`/`replay_episode.py` will need an environment decision (native venv vs. running inside/alongside the Docker image) before they can actually be run.
7. **Table/object dimensions and position are eyeballed, not measured** — `configs/simulation.yaml`'s table slab size and the circle peg's radius/height/starting position come from looking at one video frame, not calipers/tape on the real setup. Fine for Task 9's conservative randomization ranges, but re-measure before trying to match real-world object placement precisely (e.g. for sim-to-real transfer evaluation in Sec 20-21).
