# LPWP — Agentic Research Harness

## Lightweight Physical World Proxy

### Mission

Build and experimentally validate a **Lightweight Physical World Proxy (LPWP)**:

> A minimal, continuously updated representation of the physical world that contains only the information required for prediction, fast correction, and adaptive robot behavior.

The project does NOT attempt to reconstruct the complete physical world.

The central question is:

> What is the minimum physical state a robot must maintain in order to predict relevant consequences and correct its actions in real time?

---

# 1. Core Research Thesis

Modern robot-learning pipelines consume large amounts of raw sensory information:

- multiple RGB video streams
- depth
- joint states
- actuator commands
- force data
- tactile data
- simulation state
- task context

LPWP investigates whether most of this information can be reduced to a small, task-relevant physical representation.

The guiding principle is:

> Retain only the state required to predict the consequence of the next action.

This is an application of Occam's Razor to embodied intelligence.

The smallest representation that preserves useful adaptive behavior is preferred.

---

# 2. Project Principles

## P1 — Minimal State

More information is not automatically better.

Every state variable must justify its existence experimentally.

---

## P2 — Prediction Before Correction

The robot should maintain an expectation of what should happen next.

Correction is triggered by deviation between:

```text
EXPECTED STATE
      and
OBSERVED STATE
```

---

## P3 — Pre-Train Correction, Not Every Task

Task policies provide intent.

The correction system provides reusable physical adaptation.

A correction mechanism should ideally transfer between tasks.

---

## P4 — Simulation for Discovery

Isaac Sim / Isaac Lab provides privileged physical ground truth.

Use simulation to discover which physical variables matter.

Do not make the runtime LPWP dependent on Isaac.

---

## P5 — Reality Is the Final Benchmark

A result is not considered validated until it improves measurable behavior on the physical LeRobot platform.

> Every thesis must survive the real robot.

---

# 3. System Architecture

```text
                    TRAINING / RESEARCH

                  ISAAC SIM / ISAAC LAB
                           │
                    privileged state
                           │
                           ▼
                  ┌─────────────────┐
                  │ Feature Search  │
                  │ + Ablation Lab  │
                  └────────┬────────┘
                           │
                           ▼
                   LPWP DEFINITION
                           │
                    training data
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
       PREDICTOR                  CORRECTION POLICY


                         RUNTIME

      Cameras / Joints / Force / Tactile / etc.
                         │
                         ▼
                 SENSOR ADAPTERS
                         │
                         ▼
              ┌─────────────────────┐
              │        LPWP         │
              │ minimal physical    │
              │ world state         │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         PREDICTOR             TASK POLICY
              │                     │
       expected state          intended action
              │                     │
              └──────────┬──────────┘
                         ▼
                 PREDICTION ERROR
                         │
                         ▼
                CORRECTION POLICY
                         │
                         ▼
                  SAFETY LAYER
                         │
                         ▼
                       ROBOT
                         │
                         ▼
                     FEEDBACK
                         │
                         └──────────────→ LPWP
```

---

# 4. LPWP V0

Do not begin with a complex world representation.

Initial LPWP should contain only candidate variables such as:

```text
end_effector_pose

end_effector_velocity

object_relative_position

object_relative_orientation

object_relative_velocity

gripper_state

contact_state

grasp_state

prediction_confidence
```

Force, tactile, depth and other modalities are NOT mandatory for V0.

They should only be introduced if experiments demonstrate measurable value.

---

# 5. Canonical LPWP Interface

All simulation and real-world adapters must produce the same representation.

Example:

```python
PhysicalWorldProxyState(
    timestamp=...,

    eef_pose=...,
    eef_velocity=...,

    object_relative_position=...,
    object_relative_orientation=...,
    object_relative_velocity=...,

    gripper_state=...,

    contact_probability=...,
    grasp_probability=...,

    confidence=...
)
```

The core LPWP module must not know whether this state came from:

```text
Isaac ground truth
simulated cameras
real cameras
joint encoders
force sensors
tactile sensors
```

---

# 6. Adapter Boundary

Implement:

```text
IsaacPhysicalStateAdapter
```

and:

```text
RealRobotPhysicalStateAdapter
```

Both must output the same canonical LPWP state.

Never expose Isaac-specific state directly to the predictor or correction policy.

Correct:

```text
Isaac
  ↓
Isaac Adapter
  ↓
LPWP
  ↓
Predictor
```

Correct:

```text
Real Sensors
  ↓
Real Adapter
  ↓
LPWP
  ↓
Predictor
```

Incorrect:

```text
Isaac internal state
  ↓
Correction Policy
```

---

# 7. Research Harness

Every LPWP hypothesis must be expressed as an experiment.

An experiment definition must contain:

```yaml
experiment:
  id: lpwp_exp_001

  task:
    name: grasp_and_lift

  hypothesis:
    "Relative object motion is required for reliable slip correction."

  state_features:
    - object_relative_position
    - object_relative_velocity
    - gripper_state
    - contact_state

  removed_features: []

  disturbance:
    type: friction_change

  baseline:
    enabled: true

  metrics:
    - recovery_success_rate
    - task_success_rate
    - reaction_latency
    - object_drop_rate
```

No experiment should exist without a stated hypothesis.

---

# 8. Feature Ablation Harness

This is a central component of LPWP research.

Start with a state representation known to work.

Then remove information.

Example:

```text
FULL STATE
    ↓
remove absolute object position
    ↓
evaluate
    ↓
remove object velocity
    ↓
evaluate
    ↓
remove RGB input
    ↓
evaluate
    ↓
remove contact state
    ↓
evaluate
```

Record the performance change after each removal.

The goal is NOT:

> Find the largest useful state.

The goal is:

> Find the smallest state whose removal causes unacceptable degradation.

Call this:

# Minimal Sufficient Physical State — MSPS

---

# 9. MSPS Criterion

Define a target performance threshold.

Example:

```text
Recovery Success Rate >= 90%
```

If:

```text
State A = 94%
State B = 93%
State C = 92%
State D = 71%
```

then the information removed between C and D is considered important.

Prefer State C over A if A contains substantially more information without meaningful performance improvement.

---

# 10. Information Cost

Each feature should eventually have an approximate acquisition cost.

Example:

```yaml
feature:
  name: object_relative_velocity

  acquisition:
    sensor: RGB camera
    compute_cost: medium
    latency_ms: 18

  value:
    recovery_delta: +12%
```

This allows LPWP to optimize not only information quantity but also:

```text
latency
compute
sensor cost
bandwidth
energy
```

The eventual optimization objective is:

> Maximum adaptive performance per unit of sensory/computational cost.

---

# 11. Prediction Harness

Create:

```text
LPWPPredictor
```

Interface:

```python
expected_next_state = predictor.predict(
    current_proxy_state,
    intended_action
)
```

The predictor should initially operate over a short horizon.

Start with approximately:

```text
50–200 ms
```

Do not attempt long-horizon world simulation.

The predictor answers:

> Given this physical state and this action, what should happen immediately next?

---

# 12. Prediction Error

Create:

```text
LPWPPredictionError
```

Conceptually:

```python
error = compare(
    expected_next_state,
    observed_next_state
)
```

The error should preserve physical meaning.

Examples:

```text
unexpected object displacement

unexpected rotation

contact lost

grasp instability

unexpected resistance

trajectory deviation
```

Do not reduce everything immediately to one scalar loss.

---

# 13. Correction Harness

Create:

```text
LPWPCorrector
```

Interface:

```python
correction = corrector.correct(
    current_state,
    expected_state,
    observed_state,
    prediction_error
)
```

Output:

```text
delta_action
```

The task policy remains responsible for intent.

The corrector modifies execution only when necessary.

---

# 14. Disturbance Harness

Reuse the existing Synthetic Movement Factory.

Extend it with controlled disturbances:

```text
friction change

mass change

object displacement

grasp offset

action latency

actuator noise

contact loss

small collision

external object motion
```

Each disturbance must have:

```text
type

magnitude

start time

duration

random seed
```

---

# 15. Experiment Matrix

The first experiments should be deliberately small.

## Experiment A

Question:

> Can slip recovery work without RGB input?

Compare:

```text
camera + joints
```

against:

```text
LPWP state only
```

---

## Experiment B

Question:

> Is relative position more useful than absolute position?

Compare:

```text
absolute object pose
```

against:

```text
object pose relative to end-effector
```

---

## Experiment C

Question:

> Does relative velocity materially improve correction?

Remove it and measure degradation.

---

## Experiment D

Question:

> Can the same correction model transfer to a new task?

Train:

```text
grasp + lift
```

Freeze corrector.

Test:

```text
pick + place
```

---

## Experiment E

Question:

> Can the same LPWP operate with imperfect perception?

Progressively replace:

```text
Isaac ground truth
```

with:

```text
simulated perception
```

then:

```text
real perception
```

---

# 16. Runtime Escalation

LPWP should eventually support multiple information levels.

## Level 0 — Reflex State

Very small and fast.

Examples:

```text
contact
relative motion
gripper state
force
slip
```

Target:

```text
10–100+ Hz
```

---

## Level 1 — Local Physical State

Examples:

```text
object pose
local geometry
relative orientation
nearby obstacles
```

Used for:

```text
re-grasp
trajectory correction
local adaptation
```

---

## Level 2 — Scene State

Examples:

```text
multiple objects
task context
larger environment
```

Used only when lower levels cannot resolve the situation.

---

# 17. Escalation Principle

Do not continuously process maximum sensory information.

Start with the cheapest sufficient state.

Escalate only when:

```text
confidence drops

prediction error grows

correction fails

state becomes ambiguous
```

Conceptually:

```text
LEVEL 0
   │
   ├── sufficient → continue
   │
   └── uncertain
          ↓
       LEVEL 1
          │
          ├── sufficient → continue
          │
          └── uncertain
                 ↓
              LEVEL 2
```

---

# 18. Agent Skills

Agents working on LPWP should operate through narrowly defined skills.

## Skill: `lpwp-inspect`

Purpose:

Inspect existing state representations, sensors, datasets and simulation outputs.

Must not modify code.

Output:

```text
docs/inspection/<date>.md
```

---

## Skill: `lpwp-experiment`

Purpose:

Implement exactly one research hypothesis.

Required input:

```text
hypothesis
baseline
feature set
disturbance
metric
```

Must produce:

```text
experiment config
implementation
tests
results
short conclusion
```

---

## Skill: `lpwp-ablate`

Purpose:

Remove one state feature and measure performance impact.

Must not simultaneously modify policy architecture.

---

## Skill: `lpwp-disturb`

Purpose:

Add exactly one controlled disturbance type to the synthetic factory.

Must provide deterministic seed support.

---

## Skill: `lpwp-adapter`

Purpose:

Implement or modify a Physical State Adapter.

Must preserve the canonical LPWP interface.

---

## Skill: `lpwp-benchmark`

Purpose:

Run existing experiment definitions without modifying implementation.

Produces comparable metrics.

---

## Skill: `lpwp-transfer`

Purpose:

Freeze an existing predictor/corrector and evaluate it on a new:

```text
task
object
environment
or embodiment
```

Retraining is prohibited unless explicitly requested.

---

# 19. Agent Rules

Agents MUST:

1. Inspect existing code before modifying it.

2. Change one experimental variable at a time.

3. Preserve baseline behavior.

4. Record random seeds.

5. Keep simulation and real-world interfaces identical.

6. Separate perception from physical-state representation.

7. Separate task policy from correction policy.

8. Preserve raw experimental data.

9. Report negative results.

10. Prefer smaller representations when performance is equivalent.

Agents MUST NOT:

```text
add features because they "might help"

hide failed experiments

change multiple variables during an ablation

use Isaac-specific state outside adapters

replace deterministic safety with learned behavior

introduce an LLM into the fast control loop

optimize benchmark code differently between variants
```

---

# 20. Experiment Result Contract

Every experiment must produce:

```text
experiments/<experiment_id>/
```

containing:

```text
config.yaml

hypothesis.md

metrics.json

environment.json

results.md
```

`results.md` must answer exactly:

```text
What changed?

What was expected?

What happened?

Did the hypothesis survive?

What should be tested next?
```

---

# 21. Research Ledger

Maintain:

```text
RESEARCH_LEDGER.md
```

Example:

```text
LPWP-001
Hypothesis:
Relative velocity is necessary for slip correction.

Result:
Supported.

Baseline recovery:
71%

With relative velocity:
92%

Status:
KEEP FEATURE
```

Another example:

```text
LPWP-002
Hypothesis:
Absolute object position improves grasp recovery.

Result:
Not supported.

Without:
91%

With:
91.5%

Status:
REMOVE FEATURE
```

Negative results are valuable.

The ledger is the accumulated knowledge of the project.

---

# 22. Decision Rule

A new LPWP feature is accepted only if it provides measurable value.

Conceptually:

```text
VALUE(feature)
=
performance improvement
-----------------------
information + latency + compute cost
```

Exact mathematical optimization is not required initially.

The principle is mandatory.

---

# 23. First Research Target

Do not begin with a complete manipulation task.

Start with:

# Stable Grasp Under Disturbance

Robot:

```text
grasp object
lift object
hold object
```

Introduce:

```text
friction variation
mass variation
small grasp error
```

Question:

> What is the minimum physical state required to detect and recover from grasp instability?

This is LPWP Experiment Series 001.

---

# 24. Initial Success Criterion

LPWP V0 is considered interesting if:

```text
LPWP correction
```

produces significantly better recovery than baseline while using substantially less runtime sensory information than the full observation stream.

Example target:

```text
>= 90% recovery success

without continuous full RGB inference
```

This is a research target, not an assumed outcome.

---

# 25. Second Success Criterion

Freeze LPWP predictor and corrector.

Change the task.

If:

```text
grasp + lift
```

trained correction also improves:

```text
pick + place
```

without retraining the correction mechanism, the architecture has demonstrated initial task-independent transfer.

---

# 26. Third Success Criterion

Replace Isaac privileged state with real perception.

The canonical LPWP representation must remain unchanged.

If the same predictor/corrector continues to provide measurable benefit on the physical LeRobot system, LPWP has demonstrated initial sim-to-real viability.

---

# 27. Long-Term Embodiment Test

Eventually test:

```text
same LPWP semantics
+
same correction concept
+
different robot embodiment
```

The motor realization may change.

The physical concepts should not.

Example:

```text
"object slipping relative to grasp"
```

should remain meaningful independently of the exact robot hand.

---

# 28. Non-Goals

LPWP V0 is NOT:

```text
a general world model

a digital twin

a complete scene reconstruction system

an LLM robotics framework

a semantic knowledge graph

a replacement for task policies

a replacement for deterministic safety

a photorealistic representation of reality
```

LPWP is:

> A minimal actionable physical proxy.

---

# 29. Core Research Loop

Every development cycle follows:

```text
OBSERVE
   ↓
FORM HYPOTHESIS
   ↓
IMPLEMENT MINIMAL CHANGE
   ↓
SIMULATE
   ↓
MEASURE
   ↓
ABLATE
   ↓
TRANSFER
   ↓
TEST ON REAL ROBOT
   ↓
UPDATE RESEARCH LEDGER
```

Do not skip directly from idea to architecture expansion.

---

# 30. Final Guiding Principles

> **Sense less. Understand enough. Correct fast.**

> **Pre-train the correction mechanism, not every task.**

> **Every thesis must survive the real robot.**

> **The best physical-world representation is not the richest one. It is the smallest one that preserves adaptive behavior.**