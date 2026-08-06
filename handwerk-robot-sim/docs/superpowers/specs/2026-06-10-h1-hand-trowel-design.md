# H1 Dexterous Hand + Trowel Grasping — Design Spec

**Date:** 2026-06-10  
**Status:** Approved

## Goal

Add a 5-finger dexterous hand to the H1 humanoid's right arm. The hand grasps a trowel object (real contact physics) and holds it throughout the existing troweling animation. Grip strength is modulated by EEG fatigue/inFlow signals, matching the existing arm-motion modulation pattern.

## Model Structure

New directory `models/h1_hand/` alongside existing `h1/` and `ur5e/`.

### Files

| File | Purpose |
|------|---------|
| `models/h1_hand/h1_hand.xml` | H1 body + right hand bodies + trowel free body |
| `models/h1_hand/scene.xml` | Floor, lighting, includes h1_hand.xml |
| `sim/trowel_h1_hand.py` | Animation targets: 19 arm DOF + 5 finger tendons |

Modified: `sim/ws_server.py` — add `h1_hand` model choice + hand control branch.

### Hand Attachment

H1's right arm terminates at `right_elbow_link`; forearm tip sphere at local `pos="0.28 0 -0.015"`. A fixed `palm` body (no joint) attaches there. Keeping the elbow as the last controlled arm joint avoids adding a wrist actuator and keeps the existing 19-DOF PD controller unchanged.

### Hand Anatomy

- **Palm**: box geom ~60×80×15mm
- **5 fingers**: each has 3 revolute joints (MCP → PIP → DIP), capsule geoms
  - Thumb: slightly abducted offset from palm
  - Index / Middle / Ring / Pinky: standard fan layout
- **15 joints total**
- **5 position actuators** — each finger's 3 joints coupled via MuJoCo `tendon/fixed` so one ctrl value (0.0 = open, 1.0 = closed) drives all 3 phalanges proportionally

### Trowel

Free body placed in front of the palm at scene init:
- Blade: flat box geom ~250×80×5mm
- Handle: capsule geom ~120mm long

The trowel is an independent physics body. Fingers close around it; contact + friction hold it during arm motion.

## Animation (`sim/trowel_h1_hand.py`)

Returns 24 targets: indices 0–18 = arm/body DOF, indices 19–23 = finger tendons.

### Phases

| Phase | Condition | Arm | Fingers |
|-------|-----------|-----|---------|
| Grasp | `t < 1.5s` | Hold HOME pose | Ramp 0.0 → 0.85 over 1.5s |
| Trowel | `t ≥ 1.5s` | Existing `troweling_targets()` motion | Hold grip |

### EEG Modulation

Same pattern as existing arm modulation in `trowel_h1.py`:

```python
grip = 0.85 - fatigue * 0.25   # fatigue=1 → grip=0.60 (loose)
if in_flow:
    grip = 1.0                  # flow state → firm confident hold

# Primary grip fingers (thumb, index, middle) at full grip
# Passive fingers (ring, pinky) at grip * 0.70
```

## Physics Tuning

Grasping contact requires careful parameter choices:

| Parameter | Value | Reason |
|-----------|-------|--------|
| `friction` on finger geoms + trowel handle | `"1.5 0.1 0.1"` | High lateral friction prevents slip during arm sweep |
| `condim` on finger/trowel contact pair | `4` | Enables torsional + lateral friction (required for stable grasp) |
| `solimp` on fingertip geoms | `"0.95 0.99 0.001"` | Soft contact prevents jitter at grasp |
| `armature` on finger joints | `0.001` | Damps oscillation at closed position |

## `ws_server.py` Changes

1. Add `h1_hand` to `--model` argparse choices
2. Load `models/h1_hand/scene.xml` when selected
3. Split control write:
   - Arm DOF 0–18: existing PD controller unchanged
   - Finger DOF 19–23: write `data.ctrl[19:24]` directly (position actuators, no PD needed)
4. Import `trowel_h1_hand.troweling_targets` alongside existing `trowel_h1` import

## Test Sequence (manual)

1. `mjpython sim/ws_server.py --model h1_hand` — verify hand loads, trowel visible in palm region
2. Observe grasp phase (0–1.5s) — fingers close cleanly, no interpenetration explosion
3. Observe troweling phase — trowel stays in hand throughout arm sweep
4. Send `{"cmd":"replay", "eegTicks":[...], "durationMs":5000}` from Angular — verify grip changes with fatigue/inFlow values

No automated tests (no test infra in sim).

## Out of Scope

- Left hand
- Wrist joint (pronation/supination)
- Finger independence (each finger is a single coupled DOF, not anatomically independent)
- IK-driven grasping (scripted animation only)
