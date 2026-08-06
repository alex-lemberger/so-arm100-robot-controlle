# H1 Dexterous Hand + Trowel Grasping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5-finger grasping hand to H1's right wrist, place a trowel free body in the scene, and animate the hand closing around the handle before executing the existing troweling sweep.

**Architecture:** `models/h1_hand/h1_hand.xml` is a copy of h1.xml extended with palm + finger bodies on `right_elbow_link` and all actuators replaced with `<position>` actuators (arm + fingers) so a single `mj_step` loop drives both arm tracking and finger contact physics. `sim/trowel_h1_hand.py` returns 34-element ctrl targets (19 arm + 15 finger joints). `ws_server.py` gains an `h1_hand` model branch that calls this module.

**Tech Stack:** MuJoCo ≥ 3.1 (MJCF XML), Python 3.12, NumPy, existing ws_server.py / trowel_h1.py patterns.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `models/h1_hand/h1_hand.xml` | H1 bodies + hand bodies + all position actuators |
| Create | `models/h1_hand/scene.xml` | Floor, lights, trowel free body, keyframe |
| Create | `sim/trowel_h1_hand.py` | 34-DOF animation targets: arm HOME→trowel + finger grasp ramp |
| Modify | `sim/ws_server.py` | Add `h1_hand` model choice + `mj_step`-based control branch |

---

## Joint / Actuator Index Reference

```
ctrl[0]   left_hip_yaw        ctrl[10]  torso
ctrl[1]   left_hip_roll       ctrl[11]  left_shoulder_pitch
ctrl[2]   left_hip_pitch      ctrl[12]  left_shoulder_roll
ctrl[3]   left_knee           ctrl[13]  left_shoulder_yaw
ctrl[4]   left_ankle          ctrl[14]  left_elbow
ctrl[5]   right_hip_yaw       ctrl[15]  right_shoulder_pitch
ctrl[6]   right_hip_roll      ctrl[16]  right_shoulder_roll
ctrl[7]   right_hip_pitch     ctrl[17]  right_shoulder_yaw
ctrl[8]   right_knee          ctrl[18]  right_elbow
ctrl[9]   right_ankle
ctrl[19]  thumb_mcp  ctrl[20] thumb_pip  ctrl[21] thumb_dip
ctrl[22]  index_mcp  ctrl[23] index_pip  ctrl[24] index_dip
ctrl[25]  middle_mcp ctrl[26] middle_pip ctrl[27] middle_dip
ctrl[28]  ring_mcp   ctrl[29] ring_pip   ctrl[30] ring_dip
ctrl[31]  pinky_mcp  ctrl[32] pinky_pip  ctrl[33] pinky_dip
```

qpos order (48 total): `freejoint[7] + H1_joints[19] + finger_joints[15] + trowel_freejoint[7]`

---

## Task 1: Scaffold `models/h1_hand/h1_hand.xml` (copy + patch header)

**Files:**
- Create: `models/h1_hand/h1_hand.xml`

- [ ] **Step 1: Copy h1.xml**

```bash
mkdir -p ~/handwerk-robot-sim/models/h1_hand
cp ~/handwerk-robot-sim/models/h1/h1.xml ~/handwerk-robot-sim/models/h1_hand/h1_hand.xml
```

- [ ] **Step 2: Patch model name and meshdir**

In `models/h1_hand/h1_hand.xml`, change line 1–2:

Old:
```xml
<mujoco model="h1">
  <compiler angle="radian" meshdir="assets" autolimits="true"/>
```

New:
```xml
<mujoco model="h1_hand">
  <compiler angle="radian" meshdir="../h1/assets" autolimits="true"/>
```

- [ ] **Step 3: Verify model loads**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
import mujoco
m = mujoco.MjModel.from_xml_path("models/h1_hand/h1_hand.xml")
print("nu:", m.nu, "nq:", m.nq)  # expect: nu=19 nq=26
EOF
```

Expected output: `nu: 19 nq: 26`

- [ ] **Step 4: Commit**

```bash
cd ~/handwerk-robot-sim
git add models/h1_hand/h1_hand.xml
git commit -m "feat(h1-hand): scaffold h1_hand.xml from h1 copy"
```

---

## Task 2: Add palm + finger bodies to `h1_hand.xml`

**Files:**
- Modify: `models/h1_hand/h1_hand.xml`

The hand attaches to `right_elbow_link` at local offset `pos="0.28 0 -0.015"` (forearm tip). Fingers extend in local +X from the palm. Joint axis `0 1 0` (Y axis) = flexion.

- [ ] **Step 1: Insert palm + 5 finger chains inside `right_elbow_link`**

Find the closing `</body>` of `right_elbow_link` (after the sphere collision geom at line ~209) and insert before it:

```xml
              <!-- ── RIGHT HAND ───────────────────────────────────────── -->
              <body name="palm" pos="0.28 0 -0.015">
                <geom name="palm_geom" type="box" size="0.04 0.04 0.01"
                      friction="1.5 0.1 0.1" condim="4" rgba="0.85 0.65 0.5 1"/>

                <!-- THUMB (abducted +Y) -->
                <body name="thumb_prox" pos="0.015 0.035 0">
                  <joint name="thumb_mcp" axis="0 1 0" range="0 1.3" armature="0.001"/>
                  <geom type="capsule" fromto="0 0 0 0.03 0 0" size="0.009"
                        friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                  <body name="thumb_mid" pos="0.03 0 0">
                    <joint name="thumb_pip" axis="0 1 0" range="0 1.2" armature="0.001"/>
                    <geom type="capsule" fromto="0 0 0 0.025 0 0" size="0.008"
                          friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    <body name="thumb_dist" pos="0.025 0 0">
                      <joint name="thumb_dip" axis="0 1 0" range="0 1.0" armature="0.001"/>
                      <geom type="capsule" fromto="0 0 0 0.02 0 0" size="0.007"
                            friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    </body>
                  </body>
                </body>

                <!-- INDEX -->
                <body name="index_prox" pos="0.04 0.025 0">
                  <joint name="index_mcp" axis="0 1 0" range="0 1.5" armature="0.001"/>
                  <geom type="capsule" fromto="0 0 0 0.04 0 0" size="0.008"
                        friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                  <body name="index_mid" pos="0.04 0 0">
                    <joint name="index_pip" axis="0 1 0" range="0 1.4" armature="0.001"/>
                    <geom type="capsule" fromto="0 0 0 0.025 0 0" size="0.007"
                          friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    <body name="index_dist" pos="0.025 0 0">
                      <joint name="index_dip" axis="0 1 0" range="0 1.2" armature="0.001"/>
                      <geom type="capsule" fromto="0 0 0 0.018 0 0" size="0.006"
                            friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    </body>
                  </body>
                </body>

                <!-- MIDDLE (longest) -->
                <body name="middle_prox" pos="0.04 0.008 0">
                  <joint name="middle_mcp" axis="0 1 0" range="0 1.5" armature="0.001"/>
                  <geom type="capsule" fromto="0 0 0 0.045 0 0" size="0.008"
                        friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                  <body name="middle_mid" pos="0.045 0 0">
                    <joint name="middle_pip" axis="0 1 0" range="0 1.4" armature="0.001"/>
                    <geom type="capsule" fromto="0 0 0 0.028 0 0" size="0.007"
                          friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    <body name="middle_dist" pos="0.028 0 0">
                      <joint name="middle_dip" axis="0 1 0" range="0 1.2" armature="0.001"/>
                      <geom type="capsule" fromto="0 0 0 0.020 0 0" size="0.006"
                            friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    </body>
                  </body>
                </body>

                <!-- RING -->
                <body name="ring_prox" pos="0.04 -0.008 0">
                  <joint name="ring_mcp" axis="0 1 0" range="0 1.5" armature="0.001"/>
                  <geom type="capsule" fromto="0 0 0 0.04 0 0" size="0.008"
                        friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                  <body name="ring_mid" pos="0.04 0 0">
                    <joint name="ring_pip" axis="0 1 0" range="0 1.4" armature="0.001"/>
                    <geom type="capsule" fromto="0 0 0 0.025 0 0" size="0.007"
                          friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    <body name="ring_dist" pos="0.025 0 0">
                      <joint name="ring_dip" axis="0 1 0" range="0 1.2" armature="0.001"/>
                      <geom type="capsule" fromto="0 0 0 0.018 0 0" size="0.006"
                            friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    </body>
                  </body>
                </body>

                <!-- PINKY (shorter) -->
                <body name="pinky_prox" pos="0.035 -0.025 0">
                  <joint name="pinky_mcp" axis="0 1 0" range="0 1.5" armature="0.001"/>
                  <geom type="capsule" fromto="0 0 0 0.033 0 0" size="0.007"
                        friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                  <body name="pinky_mid" pos="0.033 0 0">
                    <joint name="pinky_pip" axis="0 1 0" range="0 1.4" armature="0.001"/>
                    <geom type="capsule" fromto="0 0 0 0.020 0 0" size="0.006"
                          friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    <body name="pinky_dist" pos="0.020 0 0">
                      <joint name="pinky_dip" axis="0 1 0" range="0 1.2" armature="0.001"/>
                      <geom type="capsule" fromto="0 0 0 0.015 0 0" size="0.005"
                            friction="1.5 0.1 0.1" condim="4" solimp="0.95 0.99 0.001" rgba="0.85 0.65 0.5 1"/>
                    </body>
                  </body>
                </body>

              </body><!-- /palm -->
```

- [ ] **Step 2: Verify model loads with 34 joints**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
import mujoco
m = mujoco.MjModel.from_xml_path("models/h1_hand/h1_hand.xml")
print("nq:", m.nq, "nv:", m.nv)
# expect nq=41 (7 freejoint + 19 H1 joints + 15 finger joints), nv=40
EOF
```

Expected: `nq: 41 nv: 40`

- [ ] **Step 3: Commit**

```bash
cd ~/handwerk-robot-sim
git add models/h1_hand/h1_hand.xml
git commit -m "feat(h1-hand): add palm + 5-finger bodies to right_elbow_link"
```

---

## Task 3: Replace arm actuators + add finger actuators in `h1_hand.xml`

**Files:**
- Modify: `models/h1_hand/h1_hand.xml`

Replace the entire `<actuator>` block (lines 223–243 in original) with position actuators. Arm joints use high kp (position tracking + gravity resistance). Finger joints use kp=5 (light, for contact compliance).

- [ ] **Step 1: Replace `<actuator>` block**

Find and replace the entire `<actuator>…</actuator>` section in `h1_hand.xml`:

```xml
  <actuator>
    <!-- ARM — position actuators (kp tuned for gravity tracking) -->
    <position name="left_hip_yaw"       joint="left_hip_yaw"       kp="200" ctrlrange="-0.43 0.43"/>
    <position name="left_hip_roll"      joint="left_hip_roll"      kp="200" ctrlrange="-0.43 0.43"/>
    <position name="left_hip_pitch"     joint="left_hip_pitch"     kp="200" ctrlrange="-1.57 1.57"/>
    <position name="left_knee"          joint="left_knee"          kp="200" ctrlrange="-0.26 2.05"/>
    <position name="left_ankle"         joint="left_ankle"         kp="100" ctrlrange="-0.87 0.52"/>
    <position name="right_hip_yaw"      joint="right_hip_yaw"      kp="200" ctrlrange="-0.43 0.43"/>
    <position name="right_hip_roll"     joint="right_hip_roll"     kp="200" ctrlrange="-0.43 0.43"/>
    <position name="right_hip_pitch"    joint="right_hip_pitch"    kp="200" ctrlrange="-1.57 1.57"/>
    <position name="right_knee"         joint="right_knee"         kp="200" ctrlrange="-0.26 2.05"/>
    <position name="right_ankle"        joint="right_ankle"        kp="100" ctrlrange="-0.87 0.52"/>
    <position name="torso"              joint="torso"              kp="200" ctrlrange="-2.35 2.35"/>
    <position name="left_shoulder_pitch" joint="left_shoulder_pitch" kp="50" ctrlrange="-2.87 2.87"/>
    <position name="left_shoulder_roll"  joint="left_shoulder_roll"  kp="50" ctrlrange="-0.34 3.11"/>
    <position name="left_shoulder_yaw"   joint="left_shoulder_yaw"   kp="20" ctrlrange="-1.3 4.45"/>
    <position name="left_elbow"          joint="left_elbow"          kp="20" ctrlrange="-1.25 2.61"/>
    <position name="right_shoulder_pitch" joint="right_shoulder_pitch" kp="50" ctrlrange="-2.87 2.87"/>
    <position name="right_shoulder_roll"  joint="right_shoulder_roll"  kp="50" ctrlrange="-3.11 0.34"/>
    <position name="right_shoulder_yaw"   joint="right_shoulder_yaw"   kp="20" ctrlrange="-4.45 1.3"/>
    <position name="right_elbow"          joint="right_elbow"          kp="20" ctrlrange="-1.25 2.61"/>
    <!-- FINGERS — kp=5 for contact compliance -->
    <position name="thumb_mcp_act"  joint="thumb_mcp"   kp="5" ctrlrange="0 1.3"/>
    <position name="thumb_pip_act"  joint="thumb_pip"   kp="5" ctrlrange="0 1.2"/>
    <position name="thumb_dip_act"  joint="thumb_dip"   kp="5" ctrlrange="0 1.0"/>
    <position name="index_mcp_act"  joint="index_mcp"   kp="5" ctrlrange="0 1.5"/>
    <position name="index_pip_act"  joint="index_pip"   kp="5" ctrlrange="0 1.4"/>
    <position name="index_dip_act"  joint="index_dip"   kp="5" ctrlrange="0 1.2"/>
    <position name="middle_mcp_act" joint="middle_mcp"  kp="5" ctrlrange="0 1.5"/>
    <position name="middle_pip_act" joint="middle_pip"  kp="5" ctrlrange="0 1.4"/>
    <position name="middle_dip_act" joint="middle_dip"  kp="5" ctrlrange="0 1.2"/>
    <position name="ring_mcp_act"   joint="ring_mcp"    kp="5" ctrlrange="0 1.5"/>
    <position name="ring_pip_act"   joint="ring_pip"    kp="5" ctrlrange="0 1.4"/>
    <position name="ring_dip_act"   joint="ring_dip"    kp="5" ctrlrange="0 1.2"/>
    <position name="pinky_mcp_act"  joint="pinky_mcp"   kp="5" ctrlrange="0 1.5"/>
    <position name="pinky_pip_act"  joint="pinky_pip"   kp="5" ctrlrange="0 1.4"/>
    <position name="pinky_dip_act"  joint="pinky_dip"   kp="5" ctrlrange="0 1.2"/>
  </actuator>
```

- [ ] **Step 2: Verify actuator count**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
import mujoco
m = mujoco.MjModel.from_xml_path("models/h1_hand/h1_hand.xml")
print("nu:", m.nu)  # expect 34 (19 arm + 15 finger)
EOF
```

Expected: `nu: 34`

- [ ] **Step 3: Commit**

```bash
cd ~/handwerk-robot-sim
git add models/h1_hand/h1_hand.xml
git commit -m "feat(h1-hand): replace motor actuators + add 15 finger position actuators"
```

---

## Task 4: Create `models/h1_hand/scene.xml` with trowel + keyframe

**Files:**
- Create: `models/h1_hand/scene.xml`

Trowel is a free body: capsule handle (Ø20mm × 120mm) + flat blade (250×80×5mm). Initial world position `"0.05 -0.3 0.6"` puts it roughly at H1's right hand side in HOME pose — **tune this value** during manual testing if needed.

Keyframe has 48 qpos: 7 (H1 freejoint) + 19 (H1 joints) + 15 (finger joints, all 0) + 7 (trowel freejoint).

- [ ] **Step 1: Write scene.xml**

```xml
<mujoco model="h1_hand scene">
  <include file="h1_hand.xml"/>

  <statistic center="0 0 1" extent="1.8"/>

  <visual>
    <headlight diffuse="0.6 0.6 0.6" ambient="0.3 0.3 0.3" specular="0 0 0"/>
    <rgba haze="0.15 0.25 0.35 1"/>
    <global azimuth="160" elevation="-20"/>
  </visual>

  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.3 0.5 0.7" rgb2="0 0 0" width="512" height="3072"/>
    <texture type="2d" name="groundplane" builtin="checker" mark="edge" rgb1="0.2 0.3 0.4" rgb2="0.1 0.2 0.3"
      markrgb="0.8 0.8 0.8" width="300" height="300"/>
    <material name="groundplane" texture="groundplane" texuniform="true" texrepeat="5 5" reflectance="0.2"/>
    <material name="steel" rgba="0.6 0.6 0.65 1"/>
    <material name="wood"  rgba="0.55 0.35 0.15 1"/>
  </asset>

  <worldbody>
    <light pos="0 0 3.5" dir="0 0 -1" directional="true"/>
    <geom name="floor" size="0 0 0.05" type="plane" material="groundplane"/>

    <!-- Trowel — free body; tune pos if not aligned with hand -->
    <body name="trowel" pos="0.05 -0.3 0.6">
      <freejoint/>
      <geom name="trowel_handle" type="capsule" fromto="0 0 0 0 0 0.12" size="0.01"
            material="wood" friction="1.5 0.1 0.1" condim="4" mass="0.15"/>
      <geom name="trowel_blade" type="box" size="0.125 0.04 0.0025"
            pos="0 0 0.19" material="steel" mass="0.25"/>
    </body>
  </worldbody>

  <!-- 48 qpos: H1 freejoint(7) + H1 joints(19) + finger joints(15=zeros) + trowel freejoint(7) -->
  <keyframe>
    <key name="home"
         qpos="0 0 0.98 1 0 0 0
               0 0 -0.4 0.8 -0.4 0 0 -0.4 0.8 -0.4 0 0 0 0 0 0 0 0 0
               0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
               0.05 -0.3 0.6 1 0 0 0"/>
  </keyframe>
</mujoco>
```

- [ ] **Step 2: Verify scene loads and qpos count is correct**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
import mujoco, numpy as np
m = mujoco.MjModel.from_xml_path("models/h1_hand/scene.xml")
d = mujoco.MjData(m)
mujoco.mj_resetDataKeyframe(m, d, 0)
print("nq:", m.nq)          # expect 48
print("nu:", m.nu)          # expect 34
print("nbody:", m.nbody)    # should be large (H1 + hand bodies + trowel)
mujoco.mj_step(m, d)
print("step OK — trowel z:", d.qpos[41 + 2])  # trowel z should be ~0.6
EOF
```

Expected:
```
nq: 48
nu: 34
nbody: <some number>
step OK — trowel z: 0.5...  (may drop slightly under gravity in one step)
```

- [ ] **Step 3: Commit**

```bash
cd ~/handwerk-robot-sim
git add models/h1_hand/scene.xml
git commit -m "feat(h1-hand): scene with trowel free body + 48-qpos keyframe"
```

---

## Task 5: Write `sim/trowel_h1_hand.py`

**Files:**
- Create: `sim/trowel_h1_hand.py`

Returns 34-element ctrl targets. Phase 1 (0–1.5s): arm holds HOME, fingers ramp open→grip. Phase 2 (≥1.5s): delegates to existing `troweling_targets` for arm, holds grip. EEG modulates grip the same way fatigue/inFlow modulates arm speed in `trowel_h1.py`.

- [ ] **Step 1: Write the module**

```python
"""Animation targets for H1 + right dexterous hand grasping a trowel.

ctrl[0:19]  — arm position targets (same joints as trowel_h1.py)
ctrl[19:34] — finger position targets (15 joints, 3 per finger)

Finger joint order:
  19–21  thumb  (mcp, pip, dip)   max: (1.3, 1.2, 1.0)
  22–24  index  (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  25–27  middle (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  28–30  ring   (mcp, pip, dip)   max: (1.5, 1.4, 1.2)
  31–33  pinky  (mcp, pip, dip)   max: (1.5, 1.4, 1.2)

Phases:
  t < GRASP_S : arm holds HOME, fingers ramp 0 → grip target
  t >= GRASP_S: existing troweling arm motion, fingers hold grip
"""
from __future__ import annotations
import numpy as np

try:
    from .trowel_h1 import troweling_targets as _arm_targets, HOME as _ARM_HOME
except ImportError:
    from trowel_h1 import troweling_targets as _arm_targets, HOME as _ARM_HOME  # type: ignore[no-redef]

GRASP_S = 1.5  # seconds for grasp ramp

# Max flexion per finger joint [rad]: (mcp, pip, dip)
_MAX = np.array([
    [1.3, 1.2, 1.0],  # thumb
    [1.5, 1.4, 1.2],  # index
    [1.5, 1.4, 1.2],  # middle
    [1.5, 1.4, 1.2],  # ring
    [1.5, 1.4, 1.2],  # pinky
])  # shape (5, 3)

# Home ctrl for arm (34 values: 19 arm angles + 15 zeros for open fingers)
HOME = np.zeros(34)
HOME[:19] = _ARM_HOME


def _finger_ctrl(grip: float, passive: float) -> np.ndarray:
    """Return 15 finger ctrl targets.

    grip    : 0–1, primary grip (thumb, index, middle)
    passive : 0–1, passive wrap  (ring, pinky)
    """
    scales = np.array([grip, grip, grip, passive, passive])  # (5,) per finger
    return (_MAX * scales[:, np.newaxis]).ravel()             # (15,)


def troweling_targets(
    t: float,
    fatigue: float | None = None,
    in_flow: bool = False,
) -> np.ndarray:
    """Return 34-element ctrl array for H1 + hand at wall-time t (seconds).

    fatigue 0–1 : slows arm motion and loosens grip.
    in_flow     : maximises grip and arm amplitude.
    """
    _f = max(0.0, min(1.0, fatigue if fatigue is not None else 0.0))
    grip = 1.0 if in_flow else 0.85 - _f * 0.25
    passive = grip * 0.70

    if t < GRASP_S:
        ramp = t / GRASP_S
        arm = _ARM_HOME.copy()
        fingers = _finger_ctrl(ramp * grip, ramp * passive)
    else:
        arm = _arm_targets(t - GRASP_S, fatigue=fatigue, in_flow=in_flow)
        fingers = _finger_ctrl(grip, passive)

    return np.concatenate([arm, fingers])
```

- [ ] **Step 2: Smoke-test the module**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
import sys; sys.path.insert(0, 'sim')
from trowel_h1_hand import troweling_targets, HOME
import numpy as np

out_0   = troweling_targets(0.0)
out_075 = troweling_targets(0.75)   # mid-grasp
out_15  = troweling_targets(1.5)    # troweling start
out_5   = troweling_targets(5.0, fatigue=0.8)
out_eeg = troweling_targets(3.0, in_flow=True)

assert out_0.shape == (34,),    f"bad shape: {out_0.shape}"
assert np.all(out_0[19:] == 0), "fingers not open at t=0"
assert out_075[19] > 0,         "thumb_mcp not ramping at t=0.75"
assert out_075[19] < out_15[19], "grip not increasing toward t=1.5"
assert out_eeg[19] > out_5[19], "inFlow should grip harder than fatigue=0.8"
print("all assertions pass")
print("grip at t=3 fatigue=0.8:", round(out_5[19], 3), "(expect ~0.65)")
print("grip at t=3 in_flow:    ", round(out_eeg[19], 3), "(expect 1.3)")
EOF
```

Expected:
```
all assertions pass
grip at t=3 fatigue=0.8: 0.65
grip at t=3 in_flow:     1.3
```

- [ ] **Step 3: Commit**

```bash
cd ~/handwerk-robot-sim
git add sim/trowel_h1_hand.py
git commit -m "feat(h1-hand): trowel_h1_hand animation module (34-DOF grasp + trowel)"
```

---

## Task 6: Extend `sim/ws_server.py` with `h1_hand` model branch

**Files:**
- Modify: `sim/ws_server.py`

Four changes: (1) new import, (2) `h1_hand` in argparse, (3) model path lookup, (4) new control branch in main loop.

- [ ] **Step 1: Add import after the existing `trowel_h1` import (line ~38)**

After:
```python
try:
    from .trowel_h1 import troweling_targets as h1_targets
except ImportError:
    from trowel_h1 import troweling_targets as h1_targets  # type: ignore[no-redef]
```

Add:
```python
try:
    from .trowel_h1_hand import troweling_targets as h1_hand_targets, HOME as _H1_HAND_HOME
except ImportError:
    from trowel_h1_hand import troweling_targets as h1_hand_targets, HOME as _H1_HAND_HOME  # type: ignore[no-redef]
```

- [ ] **Step 2: Extend argparse choices (line ~215)**

Change:
```python
    parser.add_argument('--model', choices=['h1', 'ur5e'], default='h1')
```

To:
```python
    parser.add_argument('--model', choices=['h1', 'ur5e', 'h1_hand'], default='h1')
```

- [ ] **Step 3: Replace model_path single-line assignment with dict lookup**

Change:
```python
    model_path = f'models/{"h1/scene.xml" if args.model == "h1" else "ur5e/scene.xml"}'
    home = _H1_STAND if args.model == 'h1' else _UR5E_HOME
```

To:
```python
    _model_paths = {
        'h1':      'models/h1/scene.xml',
        'ur5e':    'models/ur5e/scene.xml',
        'h1_hand': 'models/h1_hand/scene.xml',
    }
    model_path = _model_paths[args.model]
    home = _H1_HAND_HOME if args.model == 'h1_hand' else (_H1_STAND if args.model == 'h1' else _UR5E_HOME)
```

- [ ] **Step 4: Add `h1_hand` control branch in the main loop**

Change:
```python
    use_pd = (args.model == 'h1')  # H1 has torque motors; UR5e has position actuators
```

To:
```python
    use_pd = (args.model == 'h1')        # H1 kinematic (mj_forward, writes qpos)
    use_h1_hand = (args.model == 'h1_hand')  # H1+hand physics (mj_step, position actuators)
```

Then replace the entire section from `eeg = None` through the final `else: # idle` block with the restructured version below. The key change: eeg tick extraction is factored out to the top so both the h1_hand branch and original branches share it.

```python
            eeg = None
            if status == 'replaying':
                with _lock:
                    ticks = state['replay_ticks']
                    total = state['total_ticks']
                    if total > 0:
                        dur = state['duration_ms']
                        tick_interval_ms = dur / total if total > 0 else 100.0
                        state['elapsed_ms'] += model.opt.timestep * 1000
                        new_idx = min(int(state['elapsed_ms'] / tick_interval_ms), total - 1)
                        state['tick'] = new_idx
                        eeg = ticks[new_idx]
                        state['eeg_tick'] = eeg
                        if new_idx >= total - 1:
                            state['status'] = 'idle'
                            eeg = None

            if use_h1_hand:
                # H1 + hand: full physics via mj_step, all position actuators
                if status == 'replaying' and eeg is not None:
                    fatigue = eeg.get('fatigue')
                    in_flow = eeg.get('inFlow', False)
                    targets = h1_hand_targets(t, fatigue=fatigue, in_flow=in_flow)
                    data.ctrl[:model.nu] = targets[:model.nu]
                elif status == 'idle':
                    data.ctrl[:model.nu] = home[:model.nu]
                mujoco.mj_step(model, data)

            elif status == 'replaying':
                if eeg is not None:
                    fatigue = eeg.get('fatigue')
                    in_flow = eeg.get('inFlow', False)
                    if args.model == 'h1':
                        targets = h1_targets(t, fatigue=fatigue, in_flow=in_flow)
                    else:
                        targets = _ur5e_targets(t)
                if use_pd:
                    if eeg is not None:
                        data.qpos[7:7 + model.nu] = targets[:model.nu]
                    mujoco.mj_forward(model, data)
                else:
                    data.ctrl[:model.nu] = targets[:model.nu] if eeg is not None else home[:model.nu]
                    mujoco.mj_step(model, data)

            elif status == 'paused':
                if use_pd:
                    mujoco.mj_forward(model, data)
                else:
                    mujoco.mj_step(model, data)

            else:  # idle
                if use_pd:
                    mujoco.mj_resetDataKeyframe(model, data, 0)
                    mujoco.mj_forward(model, data)
                else:
                    data.ctrl[:model.nu] = home[:model.nu]
                    mujoco.mj_step(model, data)
```

- [ ] **Step 5: Commit**

```bash
cd ~/handwerk-robot-sim
git add sim/ws_server.py
git commit -m "feat(h1-hand): add h1_hand model branch to ws_server"
```

---

## Task 7: Manual integration tests

No automated test infra — run manually and observe.

- [ ] **Test 1: Model opens in viewer**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
mjpython sim/ws_server.py --model h1_hand
```

Expected: MuJoCo viewer opens. H1 stands in home pose. Right hand visible at forearm tip with 5 fingers open. Trowel body visible near the hand (may fall to floor — that's OK; position will be tuned).

If trowel falls far from hand: open `models/h1_hand/scene.xml`, adjust `<body name="trowel" pos="X Y Z">` until the handle sits inside the open fingers.

- [ ] **Test 2: Grasp animation (send replay command)**

With the viewer running, open a second terminal and send a minimal replay:

```bash
python - <<'EOF'
import asyncio, json, websockets

async def send():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as ws:
        msg = {
            "cmd": "replay",
            "sessionId": "test",
            "taskLabel": "grasp_test",
            "eegTicks": [
                {"focus": 0.7, "calm": 0.6, "load": 0.4, "fatigue": 0.1, "inFlow": False}
            ] * 20,
            "durationMs": 10000
        }
        await ws.send(json.dumps(msg))
        print("sent replay")
        async for raw in ws:
            state = json.loads(raw)
            print(f"tick {state['tick']}/{state['totalTicks']}  status={state['status']}")
            if state['status'] == 'idle':
                break

asyncio.run(send())
EOF
```

Expected: viewer shows fingers closing over 1.5s, then arm performs troweling sweep while trowel stays in hand. Terminal prints tick progress.

- [ ] **Test 3: EEG modulation**

Replace one tick in the list above with `"fatigue": 0.9` and repeat. Expected: visibly weaker grip (fingers don't close as far). Replace with `"inFlow": True` → fingers close fully (grip=1.0 → `thumb_mcp` reaches 1.3 rad).

- [ ] **Test 4: Pause / resume**

During a replay, send `{"cmd": "pause"}` then `{"cmd": "resume"}`. Expected: robot freezes, trowel stays held, resumes motion.

- [ ] **Tune if needed**

If fingers don't wrap around handle:
- Adjust trowel `pos` in scene.xml to move handle into finger curl radius
- Or adjust finger origin positions in h1_hand.xml (`index_prox pos="..."` etc.)

If trowel slips during troweling sweep:
- Increase friction in h1_hand.xml finger geoms: `friction="2.0 0.2 0.2"`
- Or increase kp for finger actuators: `kp="8"`

- [ ] **Step 3: Commit tuning changes (if any)**

```bash
cd ~/handwerk-robot-sim
git add models/h1_hand/h1_hand.xml models/h1_hand/scene.xml
git commit -m "fix(h1-hand): tune finger positions and trowel placement"
```
