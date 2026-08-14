# AGENTS.md

## Project: LeRobot ↔ Isaac Lab Physical AI Training Pipeline

## Objective

Build a practical training workflow for a real dual-arm LeRobot setup using:

- real-world teleoperation
- LeRobot datasets
- NVIDIA Isaac Sim
- NVIDIA Isaac Lab
- synthetic demonstration generation
- policy training
- real-world evaluation
- failure-driven retraining

The primary goal is to reduce the number of real human demonstrations required to teach manipulation tasks.

The first target is NOT a general robotics framework.

The first target is:

> Record a real LeRobot demonstration, replay it correctly in Isaac Sim, generate variations in Isaac Lab, train a policy with mixed real + synthetic data, and deploy it back to the real robot.

---

# 1. Current Hardware / Environment

Assume the following setup:

- Linux workstation
- NVIDIA GPU
- Isaac Sim installed
- Isaac Lab installed
- Hugging Face LeRobot installed
- two real LeRobot-compatible full arms
- teleoperation already working
- an existing Isaac Sim model of the robot already exists

Do not recreate the robot model unless the existing one is proven unusable.

---

# 2. High-Level Pipeline

The intended pipeline is:

```text
REAL ROBOT
    │
    │ teleoperation
    ▼
LEROBOT DATASET
    │
    │ conversion / enrichment
    ▼
DATASET BRIDGE
    │
    ▼
ISAAC SIM
    │
    │ replay validation
    ▼
ISAAC LAB
    │
    │ variation / augmentation
    ▼
SYNTHETIC DATASET
    │
    ▼
LEROBOT TRAINING DATASET
    │
    ▼
POLICY TRAINING
    │
    ▼
REAL ROBOT
    │
    ▼
FAILURE RECORDING
    │
    └──────────→ NEW HUMAN CORRECTIONS
```

---

# 3. Important Engineering Rule

Do not begin with training.

First make data transfer deterministic.

The first critical milestone is:

> One real teleoperation episode must replay correctly on the Isaac robot model.

Until this works, do not implement:

- large-scale synthetic data generation
- RL
- Mimic pipelines
- sensory-cognitive layers
- advanced policy architectures

---

# 4. Repository Structure

Use the following structure unless the existing repository already has a better compatible structure.

```text
project/
│
├── AGENTS.md
├── README.md
│
├── configs/
│   ├── robot_mapping.yaml
│   ├── task_pick_place.yaml
│   ├── task_handover.yaml
│   └── simulation.yaml
│
├── data/
│   ├── real/
│   ├── converted/
│   ├── synthetic/
│   └── evaluation/
│
├── src/
│   ├── lerobot_io/
│   │   ├── dataset_reader.py
│   │   ├── episode_reader.py
│   │   └── dataset_writer.py
│   │
│   ├── bridge/
│   │   ├── joint_mapper.py
│   │   ├── trajectory_converter.py
│   │   ├── timestamp_converter.py
│   │   └── validation.py
│   │
│   ├── kinematics/
│   │   ├── forward_kinematics.py
│   │   └── transforms.py
│   │
│   ├── isaac/
│   │   ├── robot_loader.py
│   │   ├── replay_episode.py
│   │   ├── scene_setup.py
│   │   └── object_setup.py
│   │
│   ├── augmentation/
│   │   ├── randomization.py
│   │   ├── trajectory_generation.py
│   │   └── synthetic_dataset_writer.py
│   │
│   ├── physical_state/
│   │   ├── state_builder.py
│   │   ├── object_state.py
│   │   └── relations.py
│   │
│   ├── training/
│   │   └── train_policy.py
│   │
│   └── evaluation/
│       ├── run_sim_eval.py
│       ├── run_real_eval.py
│       └── metrics.py
│
├── scripts/
│   ├── inspect_dataset.py
│   ├── convert_episode.py
│   ├── replay_episode.py
│   ├── generate_synthetic.py
│   ├── export_lerobot_dataset.py
│   └── evaluate_policy.py
│
└── tests/
```

---

# 5. Phase 0 — Inspect Existing System

Before modifying code, inspect the existing repository.

Identify:

- real robot class
- teleoperation entry point
- dataset recording command
- LeRobot dataset version
- joint names
- joint count
- control mode
- control frequency
- gripper representation
- camera configuration
- existing Isaac robot asset
- USD / URDF source
- Isaac articulation joint names
- existing training scripts

Create:

```text
docs/current_system.md
```

Document all discovered information.

Do not change architecture during this step.

---

# 6. Phase 1 — Record One Real Episode

Record one very simple task.

Initial task:

```text
pick object
move object
place object
```

Use one arm only.

Avoid dual-arm handover initially.

Record approximately 5–10 seconds.

The recorded episode must contain at minimum:

```text
timestamp
joint positions
action
gripper state
camera frames
episode id
task description
```

If available also preserve:

```text
joint velocity
joint torque
motor current
multiple cameras
```

Do not modify or normalize the original dataset.

The original real dataset must remain immutable.

---

# 7. Dataset Inspection Tool

Create:

```text
scripts/inspect_dataset.py
```

Usage:

```bash
python scripts/inspect_dataset.py --dataset <path> --episode 0
```

It must print:

```text
dataset version
episode count
episode duration
frame count
control frequency

observation fields
action fields
camera fields

joint names
joint dimensions
action dimensions
```

Also print the first and last state vector.

Goal:

Understand exactly what LeRobot records before implementing conversion.

---

# 8. Robot Mapping Configuration

Create:

```text
configs/robot_mapping.yaml
```

Example structure:

```yaml
real_robot:
  name: lerobot_dual_arm
  control_frequency: 30

isaac_robot:
  asset_path: assets/robot.usd

joints:
  - real: shoulder_pan
    isaac: shoulder_pan_joint
    scale: 1.0
    offset: 0.0
    invert: false

  - real: shoulder_lift
    isaac: shoulder_lift_joint
    scale: 1.0
    offset: 0.0
    invert: false

gripper:
  real: gripper
  isaac: gripper_joint
  scale: 1.0
  offset: 0.0
```

Support:

```text
scale
offset
direction inversion
joint reordering
```

Do not encode mapping inside Python source.

---

# 9. Dataset Bridge

Implement:

```text
src/bridge/trajectory_converter.py
```

Input:

```text
LeRobot episode
```

Output:

```text
normalized robot trajectory
```

Normalized timestep structure:

```python
{
    "timestamp": float,
    "joint_positions": np.ndarray,
    "joint_velocities": np.ndarray | None,
    "gripper": float,
    "action": np.ndarray
}
```

The converter must:

1. read LeRobot joint state
2. reorder joints
3. apply scale
4. apply offset
5. apply inversion
6. convert units if required
7. resample timestamps if required

Do not include Isaac imports in this module.

This module must remain simulator-independent.

---

# 10. Forward Kinematics

Implement:

```text
src/kinematics/forward_kinematics.py
```

For every timestep calculate:

```text
end effector position x y z
end effector quaternion
```

For dual-arm mode later calculate both arms:

```text
left_end_effector_pose
right_end_effector_pose
```

The FK implementation must be validated against Isaac.

Maximum acceptable initial positional discrepancy:

```text
< 10 mm
```

Target later:

```text
< 3–5 mm
```

---

# 11. Isaac Replay

Create:

```text
scripts/replay_episode.py
```

Usage:

```bash
python scripts/replay_episode.py \
  --dataset data/real/task_001 \
  --episode 0 \
  --config configs/robot_mapping.yaml
```

The script must:

1. launch Isaac Sim
2. load existing robot asset
3. create scene
4. load converted trajectory
5. reset robot
6. apply joint targets frame-by-frame
7. replay at recorded control frequency
8. optionally loop replay
9. optionally record simulated camera output

No ML is required.

Success criterion:

The simulated robot visually follows the same trajectory as the physical robot.

---

# 12. Replay Validation

Add automatic validation.

Compare:

```text
recorded joint state
vs
Isaac actual joint state
```

Calculate:

```text
mean joint error
max joint error
end-effector position error
```

Store result as JSON:

```text
data/evaluation/replay_episode_000.json
```

Example:

```json
{
  "mean_joint_error_rad": 0.012,
  "max_joint_error_rad": 0.041,
  "mean_ee_error_m": 0.008
}
```

---

# 13. Scene Matching

After robot motion replay works, reproduce the real workspace.

Initial environment should contain only:

```text
robot
table
one object
camera
```

Do not create a complex room.

Match approximately:

```text
table height
object dimensions
object starting position
camera position
camera orientation
robot base transform
```

Use a simple cube or block for the first task.

---

# 14. Object Pose Capture

The real pipeline eventually requires object pose.

Initial implementation can use a manually defined initial object position.

Later support vision-based object localization.

For the first simulation pipeline store:

```text
object_id
position
orientation
```

per episode.

Example:

```yaml
object:
  id: cube
  position: [0.32, -0.12, 0.04]
  rotation: [0, 0, 0, 1]
```

---

# 15. Physical State Representation V0

Create:

```text
src/physical_state/state_builder.py
```

Input:

```text
robot state
object state
```

Output example:

```python
{
    "eef_position": [x, y, z],
    "eef_orientation": [qx, qy, qz, qw],

    "object_position": [x, y, z],
    "object_orientation": [qx, qy, qz, qw],

    "eef_to_object": [dx, dy, dz],
    "distance_to_object": 0.083,

    "gripper_opening": 0.72,

    "object_velocity": [vx, vy, vz],

    "contact": False,
    "grasped": False
}
```

Do not use an LLM.

Do not use semantic reasoning yet.

This is a structured physical state vector only.

---

# 16. Synthetic Data Generation

Only begin after deterministic replay works.

Create:

```text
scripts/generate_synthetic.py
```

Input:

```text
one or more validated real demonstrations
```

Generate variations by randomizing:

```text
object x/y position
object yaw
robot initial joint position
friction
object mass
camera noise
```

Initial ranges must be conservative.

Example:

```yaml
randomization:
  object_position:
    x: [-0.03, 0.03]
    y: [-0.03, 0.03]

  object_rotation_deg:
    yaw: [-15, 15]

  mass_scale:
    min: 0.9
    max: 1.1

  friction_scale:
    min: 0.8
    max: 1.2
```

Do not begin with extreme randomization.

---

# 17. Synthetic Episode Metadata

Every generated episode must contain provenance.

Example:

```json
{
  "episode_id": "synthetic_0042",
  "source_type": "SIM_SYNTHETIC",
  "parent_episode": "real_0003",
  "seed": 183721,
  "randomization": {
    "object_offset_x": 0.018,
    "object_offset_y": -0.022,
    "yaw_deg": 8.2,
    "mass_scale": 1.04
  }
}
```

Allowed source types:

```text
REAL_HUMAN
SIM_REPLAY
SIM_SYNTHETIC
REAL_POLICY
REAL_CORRECTION
```

---

# 18. Export Back to LeRobot Format

Create:

```text
scripts/export_lerobot_dataset.py
```

Goal:

Create a training dataset that the normal LeRobot training pipeline can consume.

Dataset should support a mixture of:

```text
real episodes
synthetic episodes
```

Keep provenance metadata.

Do not silently mix them.

---

# 19. First Dataset Experiment

Create three datasets.

### Dataset A

```text
10 real episodes
```

### Dataset B

```text
50 real episodes
```

### Dataset C

```text
10 real episodes
+ 500 synthetic episodes
```

Train the same policy architecture on all three.

Do not change model architecture between experiments.

---

# 20. Evaluation

Use the same physical task for all policies.

Run at least:

```text
20 real-world evaluation episodes
```

per policy.

Randomize object position within a predefined test area.

Record:

```text
success
failure
grasp failure
collision
drop
placement failure
timeout
```

Calculate:

```text
success rate
failure type distribution
average completion time
```

---

# 21. Primary Research Metric

The main metric is:

```text
number of REAL demonstrations required
to achieve a target real-world success rate
```

Example target:

```text
80% success
```

The central comparison is:

```text
50 real demonstrations
vs
10 real demonstrations + synthetic augmentation
```

---

# 22. Failure-Driven Correction

When a trained policy fails:

Do not immediately add more random demonstrations.

Save the failed episode.

Create metadata:

```text
failure type
initial object pose
robot state
policy output
camera observations
```

Then perform one human correction using teleoperation.

Mark that episode:

```text
REAL_CORRECTION
```

Use this correction as a new seed for simulation augmentation.

---

# 23. Active Learning Loop

Target workflow:

```text
train
↓
deploy
↓
evaluate
↓
collect failures
↓
human correction
↓
simulation augmentation
↓
retrain
```

Avoid:

```text
train
↓
record another 100 random human demonstrations
```

---

# 24. Sensory-Cognitive Research Branch

Only start after the basic simulation/data pipeline works.

Create two policy input modes.

## Baseline

```text
camera
joint state
```

## Physical State Enhanced

```text
camera
joint state
physical state vector
```

The physical state vector should initially contain:

```text
eef position
eef orientation
object position
object orientation
relative position
distance
relative orientation
gripper state
contact state
object velocity
```

Do not include abstract semantic labels.

---

# 25. Cognitive Layer Experiment

Train both policies using exactly the same demonstrations.

Compare:

```text
training convergence
success rate
generalization
failure rate
number of demonstrations required
```

Primary hypothesis:

> Explicit physical relationships may improve sample efficiency.

Do not assume the hypothesis is correct.

The experiment must be capable of disproving it.

---

# 26. Simulator Ground Truth Experiment

Initially use perfect Isaac state for:

```text
object position
velocity
contact
```

This establishes an upper bound.

Then progressively replace perfect state with perception-derived state.

Order:

```text
1. Isaac ground truth
2. simulated vision
3. simulated vision + noise
4. real camera
```

This separation is important.

It distinguishes:

```text
policy learning problem
```

from

```text
perception problem
```

---

# 27. Logging

Every training run must save:

```text
experiment id
git commit
dataset id
dataset composition
real episode count
synthetic episode count
random seed
policy type
training config
physical state enabled yes/no
evaluation result
```

Store under:

```text
runs/<experiment_id>/
```

Example:

```text
runs/exp_2026_001/
├── config.yaml
├── metrics.json
├── training.log
└── notes.md
```

---

# 28. Agent Behavior Rules

The coding agent must follow these rules.

### Rule 1

Inspect before rewriting.

Do not replace existing working LeRobot or Isaac code unless necessary.

### Rule 2

Prefer small scripts over premature frameworks.

### Rule 3

Every milestone must produce a runnable command.

### Rule 4

Do not implement later phases if earlier validation fails.

### Rule 5

Keep LeRobot-specific, Isaac-specific and physical-state code separated.

### Rule 6

Do not hard-code robot joint mapping.

### Rule 7

Do not add distributed infrastructure.

No Kubernetes.

No message broker.

No cloud dependency.

### Rule 8

Do not introduce an LLM into the control loop.

### Rule 9

Prefer deterministic tests before ML experiments.

### Rule 10

Every experiment must be reproducible.

---

# 29. Immediate Agent Tasks

Execute these tasks in order.

## Task 1

Inspect repository.

Produce:

```text
docs/current_system.md
```

---

## Task 2

Identify LeRobot dataset structure.

Produce:

```text
scripts/inspect_dataset.py
```

---

## Task 3

Identify joint mapping between real robot and Isaac model.

Produce:

```text
configs/robot_mapping.yaml
```

---

## Task 4

Implement dataset converter.

Produce:

```text
src/bridge/trajectory_converter.py
```

---

## Task 5

Implement one-episode Isaac replay.

Produce:

```text
scripts/replay_episode.py
```

---

## Task 6

Validate replay numerically.

Produce:

```text
src/bridge/validation.py
```

---

## Task 7

Add object and table scene.

---

## Task 8

Implement physical-state V0.

Produce:

```text
src/physical_state/state_builder.py
```

---

## Task 9

Generate first synthetic variations.

Target:

```text
10 real episodes
→
100 synthetic episodes
```

Do not target thousands yet.

---

## Task 10

Export mixed dataset and train first policy.

---

# 30. Definition of Done — Stage 1

Stage 1 is complete only when all of the following are true.

- Real teleoperation episode can be recorded.
- Episode can be parsed programmatically.
- Real and Isaac joint mappings are documented.
- Episode can be replayed in Isaac.
- Replay error is measured.
- Object can be represented in simulation.
- End-effector pose can be calculated.
- Relative robot/object state can be generated.
- At least one real demonstration can generate multiple valid simulated variations.
- Synthetic episodes can be exported to the training pipeline.

---

# 31. Definition of Done — Stage 2

Stage 2 is complete when:

- one policy is trained from only real demonstrations
- one policy is trained from real + synthetic demonstrations
- both are evaluated on the physical robot
- results are recorded
- real demonstration count is compared

---

# 32. Definition of Done — Research Prototype

The first research prototype is complete when:

- baseline policy exists
- physical-state-enhanced policy exists
- both use the same training data
- both are evaluated under the same conditions
- sample efficiency is compared

Final research question:

> Can explicit physical-state representation plus simulation augmentation reduce the number of real-world demonstrations required to learn a reliable manipulation skill?

---

# 33. Non-Goals

For the initial project do NOT implement:

```text
general humanoid intelligence
LLM-based planning
multi-robot fleet learning
cloud training
distributed simulation
complex semantic world models
large-scale RL infrastructure
full autonomous task planning
custom robotics middleware
```

These can only be considered after the basic learning loop works.

---

# 34. First Practical Target

The first complete end-to-end demonstration should be:

```text
Real robot:
pick cube
move cube
place cube
```

Then:

```text
record demonstration
↓
replay in Isaac
↓
generate variations
↓
train policy
↓
run policy on physical robot
```

Only after this succeeds move to:

```text
dual-arm pick
↓
handover
↓
place
```

---

# 35. Core Principle

The system should maximize the information value of every real interaction.

Use:

```text
human demonstrations for intent
simulation for scale
physical state for structure
real failures for guidance
```

The project should not attempt to solve inefficient robot learning by simply collecting more human repetitions.