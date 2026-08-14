# Linux Session Handover — 2026-08-10

## What this session is about

We are starting the Isaac Sim integration leg of the project. The goal is to build a bridge between real LeRobot demonstrations and Isaac Sim so we can generate synthetic variations and reduce the number of real human demonstrations needed.

The full pipeline spec is in `AGENTS_NEW.md` at the repo root. Read that first if anything below is unclear — it is the authoritative design document.

---

## Where we are

### Training run (Windows, just completed)

A new SmolVLA checkpoint was trained today:

```
outputs/train/smolvla_circle_grasp_v1_20000/
```

Dataset: `circle_grasp_v1` — 81 episodes (50 insert + 31 grasp-only), 2 task strings, 31,541 frames.

This is the **5th training run**. The previous best checkpoint scored **3/10 on hardware** — it reached the disc but lost it at gripper close. This run adds ~5× more grasp-frame coverage and introduces two distinct task instructions so that language becomes discriminative.

Checkpoint has not been evaluated on hardware yet. That evaluation happens on the Mac (not Linux).

### What was built today (Windows session)

Three new files were created to start the Isaac pipeline:

| File | Purpose |
|---|---|
| `so-arm100/docs/current_system.md` | Full system snapshot — joint names, units, dataset format, camera config |
| `so-arm100/scripts/inspect_dataset.py` | Reads any LeRobot v3 dataset and prints schema + episode stats |
| `so-arm100/configs/robot_mapping.yaml` | Joint mapping skeleton — Isaac joint names are TODO |

---

## Immediate task on Linux

**The one blocking item is the Isaac joint names.**

Everything else (trajectory converter, replay script, validation) can be written once we know what Isaac calls the joints in the SO-ARM100 USD asset.

### Step 1 — Find the USD asset path

Locate the SO-ARM100 USD on this machine. It is the 3D clone of the LeRobot arm. Common locations:

```bash
find / -name "*.usd" 2>/dev/null | grep -i "arm\|so100\|lerobot\|robot"
```

### Step 2 — Get the joint names

Open Isaac Sim and run this in the Script Editor (Window → Script Editor):

```python
from pxr import Usd
stage = Usd.Stage.Open("/path/to/so_arm100.usd")
for prim in stage.Traverse():
    t = prim.GetTypeName()
    if "Joint" in t:
        print(prim.GetPath(), t)
```

Or if the asset is already loaded in the stage:

```python
import omni.isaac.core.utils.stage as stage_utils
stage = stage_utils.get_current_stage()
for prim in stage.Traverse():
    t = prim.GetTypeName()
    if "Joint" in t:
        print(prim.GetPath(), t)
```

Copy the output. You are looking for 6 joints matching the real robot:

| Real name | Expected Isaac name (verify) |
|---|---|
| shoulder_pan | ? |
| shoulder_lift | ? |
| elbow_flex | ? |
| wrist_flex | ? |
| wrist_roll | ? |
| gripper | ? |

Fill in `configs/robot_mapping.yaml` under each joint's `isaac:` field and under `isaac_robot.asset_path`.

### Step 3 — Confirm joint units

Isaac Sim articulations operate in **radians** by default. Confirm this for the SO-ARM100 USD:

```python
from pxr import Usd, UsdPhysics
stage = Usd.Stage.Open("/path/to/so_arm100.usd")
for prim in stage.Traverse():
    if prim.HasAPI(UsdPhysics.RevoluteJointAPI):
        joint = UsdPhysics.RevoluteJoint(prim)
        print(prim.GetPath(), "lower:", joint.GetLowerLimitAttr().Get(),
              "upper:", joint.GetUpperLimitAttr().Get())
```

If limits look like ±180 they are degrees; if ±3.14 they are radians. This determines the `deg2rad` flag in the trajectory converter.

---

## What to build next (in order)

Once joint names are confirmed, build these in sequence. Do not skip ahead.

### 1. `src/bridge/trajectory_converter.py`

Converts one LeRobot episode into a list of normalized timesteps:

```python
{
    "timestamp": float,
    "joint_positions": np.ndarray,  # radians, shape [5]
    "gripper": float,               # metres or normalized
    "action": np.ndarray            # same as joint_positions + gripper
}
```

Steps inside the converter:
1. Read parquet frame by frame
2. Reorder joints to match Isaac order (may differ)
3. Apply `scale`, `offset`, `invert` from `robot_mapping.yaml`
4. Convert degrees → radians for revolute joints
5. Convert gripper % → Isaac linear position

No Isaac imports in this module. It must run on any machine.

### 2. `scripts/replay_episode.py`

```bash
python scripts/replay_episode.py \
  --dataset data/circle_grasp_v1 \
  --episode 0 \
  --config configs/robot_mapping.yaml
```

Launches Isaac Sim, loads the USD, applies converted joint targets frame-by-frame at 30 Hz. Success = the simulated arm visually follows the same path as the real recording.

### 3. `src/bridge/validation.py`

After replay, compare commanded vs actual Isaac joint state. Write:

```
data/evaluation/replay_episode_000.json
```

Target: mean EE error < 10 mm.

### 4. `scripts/generate_synthetic.py`

Only after replay validates. Randomizes object position, yaw, mass, friction within conservative ranges and generates variation episodes.

---

## Key facts about the real system

(Full details in `docs/current_system.md`)

- **6 DOF** single arm: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
- **Units in dataset:** degrees for joints, % for gripper (float32)
- **Control frequency:** 30 Hz
- **Dataset format:** LeRobot v3.0, parquet + AV1 MP4
- **Cameras:** `overview` (1280×720) + `wrist` (1280×720)
- **Task strings:**
  - `"Insert the circle piece into its matching hole."`
  - `"Pick up the circle piece."`

---

## Repo layout

```
so-arm100-robot-controlle/
├── AGENTS_NEW.md              ← pipeline spec, read this first
└── so-arm100/
    ├── configs/
    │   └── robot_mapping.yaml  ← fill in Isaac joint names
    ├── data/
    │   └── circle_grasp_v1/    ← 81-episode training dataset
    ├── docs/
    │   ├── current_system.md   ← system snapshot
    │   └── linux-session-handover-2026-08-10.md  ← this file
    ├── outputs/
    │   └── train/
    │       └── smolvla_circle_grasp_v1_20000/  ← latest checkpoint
    ├── robot_learning/
    │   ├── loop.py             ← record / train / eval entrypoint
    │   └── merge_datasets.py   ← merge two LeRobot datasets
    └── scripts/
        └── inspect_dataset.py  ← run this on any dataset to verify structure
```

---

## Rules (from AGENTS_NEW.md §28)

- Do not begin synthetic generation until deterministic replay works.
- Do not hard-code joint mapping — it lives in `configs/robot_mapping.yaml`.
- Keep LeRobot, Isaac, and physical-state code in separate modules.
- Every milestone produces a runnable command.
- No LLMs in the control loop.

---

## First command to run on Linux

```bash
cd /path/to/so-arm100-robot-controlle
python so-arm100/scripts/inspect_dataset.py \
  --dataset so-arm100/data/circle_grasp_v1 \
  --episode 0
```

This verifies the dataset is readable and shows the joint names and ranges that the bridge code must match.
