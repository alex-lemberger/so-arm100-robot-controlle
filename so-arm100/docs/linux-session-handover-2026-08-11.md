# Linux Session Handover — 2026-08-11

## What this session picks up from

Continuation of `linux-session-handover-2026-08-10.md`. That session's "immediate task"
(find the Isaac joint names) is done. This session built the rest of the deterministic
replay pipeline (AGENTS_NEW.md Tasks 4-6) and got it numerically validated.

**Read `AGENTS_NEW.md` at the repo root first if anything below is unclear** — it's still
the authoritative pipeline spec. This doc is status + exact commands, not a redesign.

---

## Where we are: Stage 1 replay validation gate is PASSED

AGENTS_NEW.md §3: *"Do not begin synthetic generation until deterministic replay works."*
That gate is now met, numerically:

```
so-arm100/data/evaluation/replay_episode_000.json
{
  "num_frames": 635,
  "mean_joint_error_rad": 0.0042,
  "max_joint_error_rad": 0.376,
  "mean_ee_error_m": 0.00303,   // 3.03mm -- target from Sec 10 is <10mm. PASSES.
  "max_ee_error_m": 0.0686      // 68.6mm spike, concentrated on shoulder_lift mid-episode
}
```

Reproduce with:
```bash
docker run --rm --gpus all -e PYTHONUNBUFFERED=1 \
  -v "$(pwd)/..:$(pwd)/.." \
  -v "/media/alex/F6E48479E4843DBD/Users/info/Downloads/Robots/RobotStudio/so100:/media/alex/F6E48479E4843DBD/Users/info/Downloads/Robots/RobotStudio/so100:ro" \
  -w "$(pwd)" \
  leisaac-sim:latest bash -c \
  "/isaac-sim/python.sh scripts/replay_episode.py --dataset data/circle_grasp_v1 --episode 0 --config configs/robot_mapping.yaml"
```
(run from `so-arm100/`; adjust the first `-v` to mount the actual repo root at the same
absolute path so `configs/robot_mapping.yaml`'s `asset_path` resolves unmodified)

---

## What was built this session

| File | Task | Status |
|---|---|---|
| `configs/robot_mapping.yaml` | joint mapping (already existed as placeholder) | **Filled in + 2 real bugs fixed** (see below) |
| `src/bridge/trajectory_converter.py` | AGENTS_NEW.md Task 4 | Done, no Isaac imports, runs anywhere |
| `src/kinematics/forward_kinematics.py` | Task 10 | Done, chain extracted from the real USD, sanity-checked |
| `src/bridge/validation.py` | Task 6 | Done, writes `data/evaluation/replay_episode_NNN.json` |
| `scripts/replay_episode.py` | Task 5 | Done — joint replay verified; `--capture-dir` camera capture is a **known unresolved bug**, non-blocking (see below) |
| `docs/current_system.md` | Phase 0 doc | Updated with all findings below |

---

## Key facts for continuing (don't rediscover these)

### 1. The correct USD asset is NOT in either third-party Isaac repo on this machine

`~/projects/isaac-sim/leisaac` and `~/projects/isaac-sim/Sim-to-Real-SO-101-Workshop` are
real, working Isaac Lab projects already on this machine -- but they're for the **SO-101**
(a different, newer arm), not our **SO-100** hardware. Do not use their USD assets or
their joint configs.

The correct asset is:
```
/media/alex/F6E48479E4843DBD/Users/info/Downloads/Robots/RobotStudio/so100/so100.usd
```
This lives outside the repo, on a Windows-shared NTFS drive, in a Windows user's Downloads
folder. It's the real deal though -- joint names under `/so_arm100/joints/` match the real
LeRobot robot exactly (`shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`,
`wrist_roll`, `gripper`), articulation root at `/so_arm100/root_joint`. Consider copying it
into the repo (e.g. `so-arm100/assets/isaac/`) at some point so the pipeline doesn't depend
on a path on someone's Downloads folder surviving.

### 2. This machine has no native Python environment at all

No `pip`, no `numpy`, nothing outside system Python. Isaac Sim itself isn't installed
natively either (no `isaac-sim.sh` on PATH) -- everything runs through Docker images:

- **`real-robot:latest`** — has `lerobot`, `pyarrow`, `numpy`, `pyyaml`. No GPU/Isaac. Use
  this for anything that's pure LeRobot dataset work (`inspect_dataset.py`,
  `trajectory_converter.py` standalone testing).
- **`leisaac-sim:latest`** (28.9GB) — has a full `/isaac-sim` install AND, conveniently,
  `/isaac-sim/python.sh` (the bundled Kit Python) already has `pyyaml`, `pyarrow`, `numpy`,
  `PIL` alongside `isaacsim`/`omni`. This is the one and only interpreter that can run
  `replay_episode.py` (needs both LeRobot deps and Isaac). GPU passthrough works with
  `--gpus all`. Headless boot takes ~10-14s.

Isaac Sim headless smoke-tested fine: `SimulationApp({"headless": True})` boots, loads the
USD as a controllable `Robot`/`SingleArticulation`, DOF names match the USD exactly, and
`apply_action(ArticulationAction(joint_positions=...))` drives it through the existing
USD-authored PD drives (stiffness/damping/maxForce already tuned per-joint in the asset).

**Gotcha:** `docker run ... | tail -N` silently reports the exit code of `tail`, not of
`docker run`/the script. If you pipe a Docker run through `tail` for readability, exit-code
checks on it are meaningless -- either check for error strings explicitly, or don't pipe and
just read the full output file (background runs already write one).

**Gotcha:** Isaac's Python output can vanish entirely if you don't set `PYTHONUNBUFFERED=1`
(or don't flush) -- `simulation_app.close()` does a fast/hard shutdown (`--/app/fastShutdown=True`
in the Kit launch args) that can skip flushing Python's stdout buffer, silently dropping every
`print()` in the script even on a clean exit.

### 3. robot_mapping.yaml -- what was verified, and 2 real bugs fixed

Verified by loading `pxr.Usd`/`pxr.UsdPhysics` **without booting the full Kit app** --
just `PYTHONPATH`/`LD_LIBRARY_PATH` pointed at `leisaac-sim:latest`'s
`omni.usd.libs-*` extension directory. Much faster than a full Isaac Sim boot for
pure USD inspection; see `docs/current_system.md` for the exact command.

- All 6 joint names match the real robot exactly -- no renaming needed.
- **Gripper is a revolute (rotational, degrees) joint, not prismatic/linear as the
  original placeholder config assumed.** `configs/robot_mapping.yaml`'s gripper section
  now treats it like the other 5 joints (degrees -> radians), with `scale`/`offset`
  linearly mapping real 0-100% onto the USD's `[-11.46, 114.59]` degree range. That
  polarity (0%=closed -> lower limit) is still **unverified against real hardware**.
- USD-authored joint limit/drive attributes are always in **degrees** (USD physics
  schema convention for revolute joints); Isaac's runtime articulation API takes
  **radians**. `trajectory_converter.py` applies `deg2rad` uniformly to all 6 joints.
- **`shoulder_lift` and `elbow_flex` needed `invert: true`.** Found this by running
  `trajectory_converter.py` and cross-checking its output against the USD's own joint
  limits -- all 635 frames of `circle_grasp_v1` episode 0 were outside Isaac's limit
  range on exactly those two joints, in a way consistent with an inverted sign
  convention (real robot's positive direction is Isaac's negative, for those two only).
  Fixed and reverified clean across episodes 0, 40, 60, 80.

### 4. Forward kinematics

`src/kinematics/forward_kinematics.py` is a from-scratch chain FK (5 arm joints,
excludes the gripper jaw), built from the exact per-joint `physics:localPos0` /
`physics:localRot0` / `physics:axis` values read off the real USD (see the module's
docstring for the extraction command). Sanity-checked against real converted data:
EE positions cluster ~0.23-0.30m from base across the episode, consistent with the arm's
actual physical reach -- no blow-up, no NaN.

### 5. Cold-start replay artifact -- now handled

First validation pass (before adding `--settle-steps`) showed a misleading 149.9mm max EE
error, entirely caused by the sim resetting to the USD's zero pose while episode 0's first
frame is ~100° away on `shoulder_lift`/`elbow_flex`. `replay_episode.py` now holds frame 0's
target for `--settle-steps` steps (default 60) before the *measured* replay starts. This
dropped mean EE error from 8.52mm to 3.03mm and max from 149.9mm to 68.6mm. Default is on;
pass `--settle-steps 0` to disable.

### 6. Camera capture (`--capture-dir`) — known broken, not blocking

Spent a long time on this; parking it rather than continuing to burn Isaac-boot cycles on
what AGENTS_NEW.md §11 explicitly marks optional ("optionally record simulated camera
output"). Individually confirmed correct via direct queries, yet the saved PNGs still don't
show the robot:
- Camera world position/orientation (verified via `get_world_pose()` + hand-checked the
  rotation matrix math)
- Clipping range (USD's default 1.0m near-plane was culling the whole robot at first --
  fixed via `set_clipping_range(0.01, 100.0)`, confirmed via `GetAttribute("clippingRange")`)
- Render product returns real non-empty uint8 data (confirmed shape/dtype/min/max after
  adding `rep.orchestrator.step()` warm-up calls, needed alongside `world.step(render=True)`)
- Lighting reaching the render (confirmed -- pixel values respond to light intensity changes)

Despite all of that individually checking out, the frames are still flat/uniform (no robot
silhouette) -- brightness tracks light intensity but nothing else changes. Best guess left
untested: the render product created by `Camera.initialize()` may not actually be bound to
`/World/replay_camera` (there's a suspicious `/Render/OmniverseKit/HydraTextures/Replicator`
generic path showing up, which sounds more like a default-viewport texture than one scoped
to our camera prim). Next debugging step, if picked back up: check
`camera.get_render_product_path()` and manually verify which prim it's actually rendering
from, or try `rep.create.camera()` + `rep.create.render_product()` directly (the pattern
Isaac's own `standalone_examples/benchmarks/benchmark_camera.py` uses) instead of the
`isaacsim.sensors.camera.Camera` wrapper.

---

## Next step: Task 7 (scene matching) then Task 9 (synthetic generation)

Per AGENTS_NEW.md's own research design (§19-21), the thing that actually proves the
synthetic-augmentation effect is training the same policy on:
- **A**: 10 real episodes
- **B**: 50 real episodes
- **C**: 10 real + 500 synthetic episodes

...and comparing real-world success rate. Getting there requires, in order (Rule 4 --
don't skip ahead):

1. **Task 7 — add table + one object to the scene.** Currently `replay_episode.py`
   loads *only* the robot, nothing else. Synthetic generation needs something to
   randomize (object position/yaw/mass/friction per §16). Keep it minimal per §13:
   robot + table + one object + camera, no complex room.
2. **Task 9 — `scripts/generate_synthetic.py`.** Randomize object pose/mass/friction
   within the conservative ranges given in §16, starting at 10 real → 100 synthetic
   (not 500 yet, per Task 9's explicit note "Do not target thousands yet").
3. Export + train datasets A/B/C (Tasks 18-19), evaluate on the real robot (§20),
   compare success rates (§21) -- this is the actual proof.

Not yet needed for the *first* synthetic-augmentation proof (separate research branch,
§24-25): `src/physical_state/state_builder.py` (Task 8). That's for the physical-state-vs-baseline
comparison, a distinct experiment from "does synthetic data reduce real-demo count."

---

## Repo layout addendum

```
so-arm100/
├── src/
│   ├── bridge/
│   │   ├── trajectory_converter.py   <- new this session
│   │   └── validation.py             <- new this session
│   └── kinematics/
│       └── forward_kinematics.py     <- new this session
├── scripts/
│   ├── inspect_dataset.py            <- from 08-10 session
│   └── replay_episode.py             <- new this session
├── data/
│   └── evaluation/
│       └── replay_episode_000.json   <- new this session
└── docs/
    └── linux-session-handover-2026-08-11.md   <- this file
```
