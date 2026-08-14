# Phase 2 — Pre-Trained Physical Correction Layer

## Working Principle

> **Pre-train the correction mechanism, not every task.**

## 1. Objective

Build an experimental real-time correction layer for Physical AI.

The system should learn to detect when the physical outcome of an action differs from the expected outcome and immediately produce an appropriate corrective response.

The correction mechanism should be trained across many simulated situations and should not be tied to one specific manipulation task.

The long-term objective is to reduce the amount of task-specific training required by giving the robot reusable physical recovery behavior.

Instead of learning:

> "How do I perform every possible task?"

the system should learn:

> "How do I react when physical reality deviates from what I expected?"

---

# 2. Core Hypothesis

Traditional imitation learning attempts to learn approximately:

```text
observation
    ↓
policy
    ↓
action
```

The proposed architecture introduces an explicit feedback loop:

```text
current physical state
        ↓
     policy
        ↓
intended action
        ↓
expected next state
        ↓
      ACTION
        ↓
observed next state
        ↓
prediction error
        ↓
correction policy
        ↓
corrective action
```

The research hypothesis is:

> A pre-trained correction policy can provide reusable physical adaptation across multiple manipulation tasks and therefore reduce the amount of task-specific demonstration data required.

---

# 3. Relationship to Phase 1

Phase 1 builds:

```text
Real LeRobot demonstrations
        ↓
Dataset Bridge
        ↓
Isaac Sim / Isaac Lab
        ↓
Synthetic Movement Factory
        ↓
Policy training
```

Phase 2 should reuse this infrastructure.

Do not create a separate simulation pipeline.

The Synthetic Movement Factory becomes the training environment for the correction mechanism.

Phase 1 generates successful behavior.

Phase 2 intentionally generates deviations from successful behavior.

---

# 4. Fundamental Concept: Expected vs Observed State

For every action, maintain two states.

### Expected State

What the system predicts should happen after the action.

### Observed State

What actually happened.

Define:

```text
prediction_error =
observed_state - expected_state
```

The correction layer receives this discrepancy.

Conceptually:

```text
Expected:
object remains inside gripper

Observed:
object moves downward relative to gripper

Interpretation:
possible slip

Correction:
increase grip / adjust pose
```

The correction layer should therefore operate on physical relationships rather than raw task labels whenever possible.

---

# 5. Initial Physical State Vector

Reuse the Physical State Layer from Phase 1.

Initial state representation:

```text
robot joint state

end-effector pose

end-effector velocity

gripper state

object pose

object velocity

relative object/end-effector pose

distance to object

contact state

grasp state
```

Later extensions may include:

```text
force

torque

tactile pressure

slip estimate

collision state

object mass estimate

friction estimate

uncertainty
```

Do not add these until the basic architecture works.

---

# 6. Prediction Model V0

Create a component:

```text
Physical Predictor
```

Input:

```text
current physical state
+
intended action
```

Output:

```text
expected next physical state
```

Conceptually:

```text
(state_t, action_t)
        ↓
Physical Predictor
        ↓
expected_state_t+1
```

The first implementation does not need a sophisticated world model.

Start with simulator-derived transitions.

Isaac already provides exact next-state information.

Use this to construct training data.

---

# 7. Correction Policy

Create a separate component:

```text
Correction Policy
```

Input:

```text
expected state

observed state

prediction error

current robot state
```

Output:

```text
corrective action
```

Conceptually:

```text
expected_state
       +
observed_state
       ↓
prediction_error
       ↓
correction_policy
       ↓
delta_action
```

The final motor command becomes approximately:

```text
final_action =
policy_action + correction_action
```

The correction layer must remain separable from the main task policy.

---

# 8. Critical Architectural Requirement

The correction policy must NOT receive the task identity unless experimentally necessary.

Avoid:

```text
task = "pick red cube"
```

Prefer:

```text
object slipping downward

contact weakening

trajectory blocked

unexpected resistance

object displaced

grasp unstable
```

The purpose is to encourage task-independent physical recovery behavior.

---

# 9. Synthetic Disturbance Factory

Extend the existing Synthetic Movement Factory with:

```text
Disturbance Generator
```

Instead of only generating valid task variations, intentionally inject physical disturbances.

Initial disturbance classes:

```text
OBJECT_DISPLACEMENT

OBJECT_ROTATION

GRASP_OFFSET

FRICTION_CHANGE

MASS_CHANGE

TRAJECTORY_OBSTRUCTION

ACTUATOR_NOISE

ACTION_DELAY

EXTERNAL_OBJECT_MOTION
```

Later:

```text
GRIP_SLIP

CONTACT_LOSS

UNEXPECTED_COLLISION

SENSOR_NOISE

PARTIAL_OCCLUSION
```

---

# 10. Example Training Episode

Start from a successful grasp trajectory.

At timestep T:

```text
robot holds object successfully
```

Inject:

```text
friction reduced by 30%
```

Expected state:

```text
object remains fixed relative to gripper
```

Observed state:

```text
object moves downward
```

Prediction error:

```text
relative_object_z = -12 mm
```

Desired correction:

```text
increase grasp force
and/or
modify grasp pose
```

Store the complete transition.

---

# 11. Disturbance Dataset

Create a dedicated dataset.

Each sample should contain:

```text
episode_id

parent_episode

task

physical_state_before

intended_action

expected_state

disturbance

observed_state

prediction_error

corrective_action

recovery_success
```

Example:

```yaml
episode_id: correction_00182

parent_episode: synthetic_0042

disturbance:
  type: FRICTION_CHANGE
  magnitude: -0.30

prediction_error:
  object_relative_z: -0.012

correction:
  gripper_delta: +0.08

result:
  recovered: true
```

---

# 12. How to Obtain Corrective Actions

Initially obtain correction targets from simulation.

Possible approaches:

### Method A — Search

Generate several candidate corrective actions.

Simulate them.

Keep the action that restores the desired physical state.

### Method B — Controller

Use a deterministic controller as a temporary expert.

The controller produces recovery behavior.

The neural correction policy learns to imitate it.

### Method C — Reinforcement Learning

Reward recovery of the expected physical state.

Example:

```text
reward positive:
object returns to stable grasp

reward negative:
object dropped
collision
unstable motion
```

### Method D — Human Correction

For difficult situations, allow teleoperation correction.

Store these as:

```text
REAL_CORRECTION
```

Start with deterministic expert/controller or search where possible.

Do not begin with large-scale RL unless required.

---

# 13. First Correction Skill

Do NOT begin with general recovery.

Implement exactly one disturbance family first.

Recommended:

# Grasp Stability

Task:

```text
grasp object
lift object
hold object
```

Disturbances:

```text
object mass variation

friction variation

small grasp-position error
```

Desired universal behavior:

```text
detect instability
↓
adjust grip / pose
↓
stabilize object
```

This is the first proof of concept.

---

# 14. First Experiment

Train two systems.

## System A — Baseline

Standard task policy.

No correction layer.

## System B — Corrective

Same task policy.

Plus:

```text
Physical Predictor
+
Prediction Error
+
Correction Policy
```

Both systems receive identical task training data.

---

# 15. Evaluation

Test both systems under disturbances not present in the original task demonstrations.

Examples:

```text
different object mass

lower friction

slightly displaced object

small actuator delay
```

Measure:

```text
task success rate

recovery success rate

object drop rate

time to recovery

maximum prediction error

number of catastrophic failures
```

---

# 16. Primary Metric

The primary Phase 2 metric is:

```text
Recovery Success Rate
```

Definition:

```text
successful recoveries
---------------------
recoverable disturbances
```

Secondary metric:

```text
Task Success Under Disturbance
```

The correction layer is successful if it improves task success without requiring retraining of the main task policy.

---

# 17. Generalization Experiment

Once grasp correction works, keep the correction model frozen.

Do NOT retrain it.

Apply it to another task.

Example:

Training context:

```text
pick and lift
```

New task:

```text
pick and place
```

Then:

```text
handover
```

Test whether the same correction mechanism improves stability.

This experiment is critical.

If the correction policy only works for the original task, it is not yet a general learning shortcut.

---

# 18. Cross-Object Generalization

Train corrections using:

```text
cube
```

Then test:

```text
cylinder

bottle

different cube size

different material
```

Do not immediately retrain.

Measure zero-shot recovery performance first.

---

# 19. Prediction Error as a First-Class Signal

The architecture should treat prediction error as an explicit signal.

Example vector:

```text
Δ object position

Δ object rotation

Δ end-effector position

Δ velocity

Δ contact

Δ grasp state
```

Conceptually:

```text
ERROR_t =
OBSERVED_t - EXPECTED_t
```

This error should be logged for every timestep.

Even when no correction is applied.

This dataset may later become one of the most valuable outputs of the project.

---

# 20. Multi-Timescale Architecture

Design for three possible correction speeds.

Do not implement all three initially.

### Fast Loop

Target:

```text
10–100+ Hz
```

Responsibilities:

```text
slip

contact loss

force adjustment

small trajectory corrections
```

No LLM.

No high-level reasoning.

---

### Medium Loop

Target:

```text
1–10 Hz
```

Responsibilities:

```text
re-grasp

change approach

trajectory adjustment

local obstacle response
```

---

### Slow Loop

Target:

```text
seconds
```

Responsibilities:

```text
task replanning

select alternative strategy

request human assistance
```

The Phase 2 prototype should focus primarily on the fast and medium loops.

---

# 21. Important Principle

Do not retrain the entire policy every time something unexpected happens.

Preferred architecture:

```text
TASK POLICY
     │
     ▼
intended action
     │
     ├───────────────┐
     ▼               │
PHYSICAL WORLD       │
     │               │
     ▼               │
OBSERVED STATE       │
     │               │
     ▼               │
PREDICTION ERROR ◄───┘
     │
     ▼
CORRECTION POLICY
     │
     ▼
delta action
```

The task policy decides:

> What should I do?

The correction policy decides:

> Reality is not behaving as expected. How should I adapt?

---

# 22. Relationship to the Sensory-Cognitive Layer

The correction mechanism should consume the Physical State Layer rather than directly depending on Isaac internals.

Correct:

```text
Isaac
  ↓
Physical State Adapter
  ↓
Correction Layer
```

Real robot:

```text
Real Sensors
  ↓
Physical State Adapter
  ↓
Correction Layer
```

Avoid:

```text
Correction Policy
  ↓
Isaac-specific state
```

The correction mechanism should eventually be simulator-independent.

---

# 23. Sim-to-Real Strategy

Training sequence:

```text
Phase A

Isaac perfect state
↓
correction policy
```

Then:

```text
Phase B

Isaac state
+
noise
+
latency
+
parameter randomization
↓
correction policy
```

Then:

```text
Phase C

real robot perception
↓
same physical state representation
↓
same correction policy
```

The interface between simulation and reality must remain identical.

---

# 24. Safety Layer

The correction policy must never bypass hard safety constraints.

Final command pipeline:

```text
task policy
    ↓
correction policy
    ↓
safety controller
    ↓
motor command
```

Safety controller must enforce:

```text
joint limits

velocity limits

acceleration limits

workspace limits

collision constraints

emergency stop
```

Learned correction is advisory.

Hard safety constraints remain deterministic.

---

# 25. Agent Implementation Order

Do not build the entire architecture at once.

## Milestone 1

Extend the synthetic factory to inject one controlled disturbance.

Recommended:

```text
friction change
```

---

## Milestone 2

Record:

```text
expected state

observed state

prediction error
```

for every timestep.

---

## Milestone 3

Implement a deterministic correction expert.

Example:

```text
detect slip
→
increase grip
```

---

## Milestone 4

Generate at least:

```text
1,000 correction episodes
```

in simulation.

---

## Milestone 5

Train a small correction policy by imitation.

---

## Milestone 6

Compare:

```text
baseline
vs
baseline + correction
```

inside Isaac.

---

## Milestone 7

Introduce unseen disturbances.

---

## Milestone 8

Freeze correction policy.

Test on a different manipulation task.

---

## Milestone 9

Deploy the correction layer to the real LeRobot system.

Start with conservative limits.

---

# 26. Definition of Done — Phase 2A

Phase 2A is complete when:

- one physical disturbance can be generated automatically
- expected state is available
- observed state is available
- prediction error is calculated
- corrective action can be generated
- correction episodes can be recorded
- correction policy can be trained
- recovery performance can be measured

---

# 27. Definition of Done — Phase 2B

Phase 2B is complete when:

- correction policy improves recovery rate in simulation
- policy handles disturbance magnitudes not present during training
- correction model works with the main task policy frozen
- correction model transfers to at least one new manipulation task
- correction model transfers to at least one unseen object configuration

---

# 28. Definition of Done — Phase 2C

Phase 2C is complete when:

- the same correction interface runs on the physical robot
- prediction errors are calculated from real observations
- correction actions operate within hard safety limits
- at least one real disturbance can be recovered automatically
- recovery performance is measured against a no-correction baseline

---

# 29. Research Questions

The implementation should eventually provide experimental answers to:

1. Can corrective physical behavior be pre-trained independently of a specific manipulation task?

2. Does explicit prediction error improve recovery compared with a standard reactive policy?

3. Which physical-state variables are necessary for effective correction?

4. How much synthetic correction training transfers to the real robot?

5. Can one correction model generalize across objects?

6. Can one correction model generalize across tasks?

7. Can correction pre-training reduce the amount of task-specific demonstration data?

8. Can the correction mechanism eventually transfer across different robot embodiments?

---

# 30. Long-Term Research Direction

The desired architecture is not:

```text
TASK 1 → MODEL 1

TASK 2 → MODEL 2

TASK 3 → MODEL 3
```

The desired architecture is closer to:

```text
             GENERAL PHYSICAL PRIORS
                       │
                       ▼
              PHYSICAL PREDICTOR
                       │
                       ▼
              CORRECTION MODEL
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
          TASK A     TASK B     TASK C
```

Task-specific policies provide intent.

The shared correction model provides physical adaptation.

---

# 31. Long-Term Learning Shortcut

The larger hypothesis behind the project is:

```text
TASK KNOWLEDGE
      +
PHYSICAL PRIORS
      +
PREDICTION
      +
FAST FEEDBACK
      +
PRE-TRAINED CORRECTION
      =
LESS TASK-SPECIFIC TRAINING
```

The objective is not to pre-train every possible physical task.

The objective is to pre-train the robot's ability to respond intelligently when reality differs from expectation.

---

# 32. Guiding Principle

> **Do not teach the robot every possible mistake.  
> Teach it how to recognize and correct physical deviation.**

Or, in its shortest form:

> **Pre-train the correction mechanism, not every task.**