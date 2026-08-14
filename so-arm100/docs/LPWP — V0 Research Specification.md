# LPWP — V0 Research Specification

This document is a companion to:

- `LPWP — Agentic Research Harness.md` — research framework and principles
- `Phase 2 — Pre-Trained Physical Correction Layer.md` — correction architecture

It fills the gaps left open in those documents and translates the research framework into
a concrete, hardware-grounded implementation plan for this specific system.

---

## 1. Thesis

> A small, structured physical state representation — estimated from the sensors already
> present on the SO-ARM100 — is sufficient to detect grasp disturbances and drive a
> pre-trained correction policy that transfers across manipulation tasks without retraining.

Three sub-claims, each testable independently:

| Claim | Experiment | What falsifies it |
|---|---|---|
| LPWP state is sufficient for disturbance detection | Exp-A | Recovery rate <70% vs. full-RGB baseline ≥90% |
| A pre-trained predictor can be built from sim data | Milestone 2 | Prediction error in sim does not correlate with observed disturbances |
| Correction transfers across tasks without retraining | Exp-D | Recovery rate drops >20 pp on new task with frozen corrector |

The third claim is the most ambitious. Treat it as a hypothesis, not an assumption.
If correction only transfers partially (error detection works but correction magnitude
needs tuning per task), that is still a meaningful and publishable result.

---

## 2. Hardware Constraints

The SO-ARM100 has:

- 6 DOF position-controlled arm at 30 Hz
- Feetech SCServo motors — expose `present_load` (motor current proxy) via SDK
- Two cameras: `overview` (1280×720, 30fps) and `wrist` (1280×720, 30fps)
- No dedicated force sensor, torque sensor, or tactile sensor
- FK implementation already exists: `src/kinematics/forward_kinematics.py`

These constraints directly determine what LPWP state fields are available at runtime
and which require estimation.

---

## 3. LPWP State Fields — Sourcing Plan

This is the canonical `PhysicalWorldProxyState` mapped to actual SO-ARM100 sensors.

### Fields available from existing hardware

| Field | Source | Latency | Notes |
|---|---|---|---|
| `eef_pose` | FK from `observation.state[0:5]` | <1 ms | Already in every dataset frame |
| `eef_velocity` | Finite difference of `eef_pose`, 1-step lag | <1 ms | Introduce at Milestone 2 |
| `gripper_state` | `observation.state[5]` direct | 0 ms | 0=closed, 100=open |
| `contact_probability` | Feetech `present_load` on gripper joint | <5 ms | Load spikes on contact; normalize to [0,1] |
| `grasp_probability` | `contact_probability × (gripper_state < 30)` | <5 ms | Heuristic for V0; refine with data |

### Fields requiring estimation (the hard ones)

| Field | V0 source | V1 source | V2 source |
|---|---|---|---|
| `object_relative_position` | Isaac ground truth | Isaac + noise | ArUco marker on object → OpenCV |
| `object_relative_orientation` | Isaac ground truth | Isaac + noise | ArUco marker on object → OpenCV |
| `object_relative_velocity` | Finite diff of above | Finite diff of above | Finite diff of above |

**Why ArUco for V2, not a learned pose estimator:**

An ArUco marker on the object gives 6-DOF pose at 30Hz from the existing overview camera
using pure OpenCV, with no training, no GPU, and <5ms latency. This lets the full
adapter-predictor-corrector pipeline be validated on real hardware before the hard
computer vision problem (markerless pose estimation) is tackled. Once the architecture
proves out with markers, swapping in a vision-based estimator is an isolated component
swap with a clear metric: does real-hardware recovery rate hold up when the marker is removed?

Markerless object pose estimation (FoundationPose, DINO-based, etc.) is a V3 problem.

### Fields deferred

| Field | When to introduce |
|---|---|
| `force / torque` | Only if `contact_probability` from servo current proves insufficient |
| `slip_estimate` | After Exp-A/C — only if velocity alone doesn't capture slip dynamics |
| `prediction_confidence` | After the predictor is trained — derive from ensemble or MC-dropout |

Every deferred field must justify its inclusion with a controlled ablation experiment
before it is added. Adding fields because they "might help" is not permitted.

---

## 4. Predictor Model

### Decision

A 3-layer MLP is the right model class for V0.

Input: `[lpwp_state (9), action (6)]` = 15 floats.
Output: `lpwp_state_next (9)` floats.
Architecture: `15 → 128 → 128 → 9`, ReLU activations, trained with MSE loss.
Size: ~50k parameters.
Inference: CPU, <1ms per step at 30Hz.

### Why not a transformer or neural ODE

The predictor must run alongside SmolVLA (450M params, GPU-bound at ~3 steps/sec).
Putting a second transformer on the same GPU creates a real-time budget conflict.
The predictor runs on CPU, separated from the GPU-resident task policy.
A small MLP over a 15-element input is sufficient for 50–200ms horizon prediction
of low-dimensional physical state. Start small; the ablation harness will reveal
if a recurrent model (GRU) is needed.

### When to upgrade to GRU

If prediction error on sequences longer than 1 step is unacceptably high after training
the MLP, replace with a 1-layer GRU (input=15, hidden=64, output=9, ~20k params).
Do not introduce sequence modelling speculatively.

### Training data source

Use Isaac transition tuples: `(state_t, action_t, state_t+1)` extracted from the
synthetic episode JSONs already in `data/synthetic/circle_grasp_v1/`.
Each episode contributes `N-1` training samples.
100 synthetic episodes × ~560 frames/episode ≈ 55,000 training tuples from existing data.
This is sufficient for V0; generate more disturbance episodes if validation loss plateaus.

---

## 5. Corrective Action Source

Use **Method B — Deterministic Controller** for V0.

For grasp stability (the first correction skill), a simple proportional controller
suffices as the expert:

```
if object_relative_z drops below threshold:
    gripper_delta = K × object_relative_z_error
    clamp(gripper_delta, -max_delta, +max_delta)
```

This produces labeled `(state, error) → delta_action` pairs directly from simulation
without RL or search. The correction policy then imitates the controller.

Method A (search) is the fallback if the controller produces insufficient coverage.
Method C (RL) is only introduced if imitation from a controller fails — it multiplies
complexity and is not warranted until Method B is demonstrated insufficient.
Method D (human DAgger) is reserved for edge cases where simulation cannot
produce the right corrective behavior (unusual disturbances, real-hardware-only phenomena).

---

## 6. Experiment Sequence (Revised from LPWP §15)

The LPWP document proposes experiments A–E. The order is revised here for two reasons:
(1) the sim-to-real bridge (Experiment E) must be validated before cross-task transfer
(Experiment D), because transfer results on sim-only are not the primary claim;
(2) ablations B and C should run before D to establish which state features matter
before committing to a transfer test.

| Order | Experiment | Question | Falsification threshold |
|---|---|---|---|
| 1 | **Exp-A** | Can grasp correction work without continuous RGB? | RSR <70% with LPWP-only |
| 2 | **Exp-C** | Does relative velocity materially improve correction? | <5 pp RSR drop when removed |
| 3 | **Exp-B** | Relative position vs. absolute position — which matters? | <5 pp RSR drop for relative |
| 4 | **Exp-E** | Does the same predictor/corrector survive noisy real-sensor state? | RSR drops >15 pp with noise |
| 5 | **Exp-D** | Can the frozen corrector transfer to a new task? | RSR drops >20 pp on new task |

*RSR = Recovery Success Rate. Thresholds are proposed targets, not assumed outcomes.*

Exp-E is now fourth because: if the predictor trained on Isaac ground truth fails under
noise, the correction policy is not yet real-hardware viable, and running Exp-D (transfer)
would be testing a broken foundation. Fix Exp-E first, then trust the Exp-D result.

---

## 7. Adapter Boundary — Concrete Implementation

Two adapters required. Both must output identical `PhysicalWorldProxyState`.

### IsaacPhysicalStateAdapter

Sources all fields directly from Isaac runtime APIs.
Inputs: `ArticulationView` joint positions + `RigidPrimView` object pose.
No estimation required.
This adapter is the V0 training and validation environment.

### RealRobotPhysicalStateAdapter

Three progressive configurations matching the Phase 2 §23 sim-to-real sequence:

**Config A — Isaac perfect (training):**
Not applicable — use `IsaacPhysicalStateAdapter`.

**Config B — Noisy sim (validation before real):**
Take `IsaacPhysicalStateAdapter` output and apply:
- Gaussian noise σ=5mm on object position (representative of camera estimation noise)
- Gaussian noise σ=3° on object orientation
- 1-step latency on object state (camera processing lag)

**Config C — Real hardware (ArUco bridge):**
- `eef_pose/velocity`: FK from servo positions
- `gripper_state`: servo position directly
- `contact_probability`: `present_load` from Feetech SDK, normalized
- `object_relative_*`: ArUco 6-DOF via OpenCV `aruco.estimatePoseSingleMarkers`
  from the `overview` camera (640×480 at 30fps is sufficient for marker detection;
  no need to run at full 1280×720)

**Config D — Real hardware (markerless):**
Future. Replace ArUco with a trained pose estimator. The `RealRobotPhysicalStateAdapter`
interface does not change — only its internal implementation.

---

## 8. Timing Budget at 30 Hz

One control cycle = 33ms.

| Component | Runs on | Budget | Notes |
|---|---|---|---|
| Servo read | CPU | ~2ms | Feetech SDK read |
| FK computation | CPU | <1ms | Already implemented |
| ArUco detection | CPU | ~5ms | At 640×480 |
| LPWP assembly | CPU | <1ms | Simple concatenation |
| Predictor (MLP) | CPU | <1ms | 50k params |
| Prediction error | CPU | <1ms | Vector subtraction |
| Corrector (MLP) | CPU | <1ms | Similar size |
| Safety clamp | CPU | <1ms | Joint/velocity limits |
| SmolVLA inference | GPU | ~330ms | Runs at its own rate (~3Hz) |
| Servo write | CPU | ~2ms | |

**Total LPWP loop: ~13ms — well within 33ms budget.**

SmolVLA runs asynchronously at ~3Hz on the GPU. The LPWP correction loop runs
synchronously at 30Hz on the CPU. The task policy provides intent; the correction loop
modifies the most recent action at each 30Hz tick. This is the intended architecture
from Phase 2 §20 (fast loop = 10–100Hz, medium loop = 1–10Hz).

---

## 9. Milestone Sequence

These map directly onto Phase 2 §25 milestones, with concrete implementation targets.

### M1 — Disturbance injection (1 type)

Extend `src/augmentation/randomization.py` with a `Disturbance` class distinct from
`Variation`. Initial type: `FRICTION_CHANGE` (already partially present in `Variation` —
extract into a separate disturbance API with deterministic seed, start_time, duration).

Output: Isaac episodes with mid-episode friction changes, full trajectory logged.

### M2 — Expected / observed / error recording

Add `PhysicalStateLogger` to the Isaac replay loop. For every timestep, record:
`{state_t, action_t, expected_state_t+1 (from predictor), observed_state_t+1, error_t}`.

Output: Disturbance dataset in the schema from Phase 2 §11.

### M3 — Predictor training

Train the 3-layer MLP predictor on `(state_t, action_t) → state_t+1` tuples from
`data/synthetic/circle_grasp_v1/`. Validate on held-out episodes. Target: mean
position prediction error <3mm at 1-step horizon.

Output: `models/lpwp_predictor_v0.pt`, training curve, validation metrics.

### M4 — Deterministic correction expert

Implement the proportional grasp stability controller in `src/correction/expert.py`.
Run it in Isaac on disturbance episodes; log `(state, error) → delta_action` pairs.
Target: 1,000+ correction episodes from `FRICTION_CHANGE` and `MASS_CHANGE` disturbances.

Output: Correction dataset, expert recovery success rate (the ceiling for the learned policy).

### M5 — Correction policy training

Train a small MLP corrector by behavioral cloning on the expert dataset.
Input: `[current_state (9), expected_state (9), prediction_error (9)]` = 27 floats.
Output: `delta_action (6)`.
Architecture: `27 → 128 → 128 → 6`.

Output: `models/lpwp_corrector_v0.pt`, training curve.

### M6 — Sim evaluation: baseline vs. corrected

Run Exp-A in Isaac. Compare:
- System A: task policy alone (SmolVLA or scripted)
- System B: task policy + LPWP corrector

Measure RSR under `FRICTION_CHANGE` and `MASS_CHANGE` disturbances.

Output: `experiments/lpwp_exp_001/` with full result contract (Phase 2 §20 schema).

### M7 — Ablation: Exp-C and Exp-B

Remove `object_relative_velocity` (Exp-C). Measure RSR delta.
Remove, then restore `object_relative_position` vs. absolute (Exp-B). Measure RSR delta.
Update RESEARCH_LEDGER.md with results (keep or remove each feature).

### M8 — Sim-to-real bridge validation (Exp-E)

Add noise to `IsaacPhysicalStateAdapter` output (Config B adapter). Re-run Exp-A.
If RSR drops <15pp, proceed to real hardware. If RSR drops >15pp:
(a) add Gaussian noise augmentation to predictor training, (b) repeat, (c) re-measure.

### M9 — Real hardware deployment

Mount ArUco marker on the circle piece. Build `RealRobotPhysicalStateAdapter` Config C.
Run System B on real robot. Measure RSR against System A baseline.
Apply corrections within hard safety limits: `±2.2° per step` (25 ticks max, consistent
with existing `max_relative_target` in the control loop).

### M10 — Cross-task transfer (Exp-D)

Freeze the corrector from M5 (no retraining).
Apply it to the insert task (not just grasp+lift). Measure RSR.
Record result in RESEARCH_LEDGER.md regardless of outcome.

---

## 10. Research Ledger Bootstrap

Create `RESEARCH_LEDGER.md` at the start of M6.
Every milestone from M6 onward adds one or more entries.
Negative results are mandatory entries — a "REMOVE FEATURE" or "DOES NOT TRANSFER"
result is as valuable as a positive one.

---

## 11. Safety Layer — SO-ARM100 Specific

The correction policy output `delta_action` (6 floats, joint deltas) must pass through
a deterministic safety layer before being added to the task policy action:

```python
delta_action = clip(delta_action, -MAX_DELTA, +MAX_DELTA)
final_action = task_action + delta_action
final_action = clip(final_action, joint_lower_limits, joint_upper_limits)
```

`MAX_DELTA` per joint: 2.2° (= 25 ticks, the existing `max_relative_target`).
Joint limits from `configs/robot_mapping.yaml`.

The safety layer is deterministic and cannot be bypassed by the learned policy.
This is not a temporary constraint — it is a permanent architectural requirement
(Phase 2 §24).

---

## 12. What This Spec Does Not Cover

- Wrist camera integration into LPWP (only `overview` is currently in the datasets;
  wrist can be added to the adapter later without changing the interface)
- Multi-object scenes (LPWP V0 tracks one object; multi-object is a later extension)
- Learned object pose estimation (ArUco bridge comes first; markerless is Config D)
- Cross-embodiment transfer (SO-101 or other arm; test this after Exp-D succeeds)
- LLM in the control loop — explicitly excluded at all timescales

---

## 13. Open Questions Requiring Experimental Answers

These cannot be resolved by design — they require data:

1. Does `present_load` from Feetech servos give a reliable enough contact signal,
   or does it require per-servo calibration that makes it impractical?

2. What noise level on object position estimation causes the predictor to fail?
   (This sets the requirement for the vision estimator in Config D.)

3. Does the 3-layer MLP predictor saturate on longer rollouts (>5 steps), and if so,
   does a GRU actually help?

4. Is task-independent correction achievable without any task conditioning, or does
   correction magnitude need to be scaled per task even if detection transfers?

These are research questions. Do not pre-answer them with architectural choices.
Instrument the experiments to answer them.
