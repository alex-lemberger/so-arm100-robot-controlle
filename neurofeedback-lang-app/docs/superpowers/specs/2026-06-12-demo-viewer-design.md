# Handwerk Capture Demo Viewer — Design Spec

**Date:** 2026-06-12
**Status:** Approved

---

## Goal

A standalone public-facing `/demo` route that pitches the Handwerk capture platform concept. Shows a 3D robot arm with a fully articulated hand tracing a drywall boustrophedon path on a wall plane, overlaid with a mock EEG signal. Narrative: *we captured a skilled worker's motion + brain state — here is the robot replicating it.*

No WebSocket, no auth, no Supabase dependency in v1. Runs entirely client-side.

---

## Architecture

### New files

| Path | Purpose |
|------|---------|
| `src/app/demo/demo.component.ts` | Standalone Angular component — owns Three.js scene, canvas + HTML overlay |
| `src/app/demo/demo-motion.service.ts` | Scripted arm animation: boustrophedon waypoints, analytical IK, finger curl poses |
| `src/app/demo/demo-eeg.service.ts` | Mock EEG signal (sinusoidal focus/calm); injectable so real Supabase data can swap in for v2 |

### Wiring

- `/demo` added to `app.routes.ts` — lazy-loaded, no auth guard
- `NavigationComponent` sidebar gets a "Demo" nav entry
- No dependency on `SimBridgeService`, NGXS stores, or Supabase

---

## Scene Structure

### Robot arm kinematic chain (Three.js primitives only)

```
base (floor cylinder, static)
└── shoulder (sphere joint)
    └── upper arm (CylinderGeometry, ~0.30 m)
        └── elbow (sphere joint)
            └── forearm (CylinderGeometry, ~0.25 m)
                └── wrist (sphere joint)
                    └── palm (BoxGeometry, ~0.08 × 0.04 × 0.12 m)
                        ├── finger_1..5
                        │   metacarpal → proximal → distal
                        │   each: 2 cylinders + 3 sphere joints
                        └── thumb (2 joints, shorter, angled ~35° from index)
```

Total: 3 arm joints + 17 finger joints (5 × 3 + thumb 2). All `THREE.Object3D` hierarchy — rotations compose up the chain.

### Wall plane

- `PlaneGeometry` (0.8 × 0.6 m), vertical, ~0.5 m in front of arm base
- Slightly emissive grey (`emissive: 0x222222`) — readable against dark background
- Paint trail: flat quad meshes added progressively as tool tip passes each waypoint, visualising work done

### Camera

- 3/4 side angle — sees arm profile and wall face simultaneously
- `OrbitControls` enabled (rotate only, no pan)
- Starting position: `(1.2, 0.9, 1.8)` looking at `(0, 0.5, 0)`

### Lighting

- `AmbientLight` 0xffffff intensity 0.5
- `DirectionalLight` front-above (0xffffff, 0.8) — main key light
- `DirectionalLight` side (0xffffff, 0.4) — fills finger geometry depth

### Visual style

| Property | Value |
|----------|-------|
| Background | `#0f172a` |
| Base material | `MeshPhongMaterial` |
| Resting arm color | `#93c5fd` (calm blue) |
| Focus peak color | `#ef4444` (deep red via amber) |
| Opacity | 1.0 always (no disconnected dim — no status in demo) |

---

## Motion (`DemoMotionService`)

### Boustrophedon path

20 waypoints on the wall plane in a grid (4 columns × 5 rows). Arm moves left→right, steps down one row, right→left, repeats. One full pass ~8 seconds, then resets and loops.

### IK solver

Analytical 2-segment planar IK (shoulder → elbow → wrist):

1. Given target point `P` on wall, compute distance from shoulder origin
2. Solve elbow angle via law of cosines: `cos(θ_elbow) = (d² - L1² - L2²) / (2·L1·L2)`
3. Compute shoulder angle from atan2 + offset
4. Wrist rotation locked perpendicular to wall surface

Closed-form — no iterative solver. Fast and deterministic.

### Finger states

| State | Curl angle | When |
|-------|-----------|------|
| `grip` | ~40° | arm moving along wall |
| `release` | ~10° | arm repositioning between rows |
| `tighten` | scales 40°→65° with focus value | focus > 0.7 |

Transitions interpolated with `lerp` each frame. Finger spread: slight fan (index → pinky offset ~5° each). Thumb curls independently at ~35° base angle.

### Animation loop

Single `requestAnimationFrame` — advances waypoint `t`, calls IK, updates joint rotations, lerps finger curl, updates arm material color. No per-frame geometry rebuilds.

**Speed:** constant in v1. EEG-modulated speed is a v2 addition.

---

## EEG Overlay (`DemoEegService`)

### Mock signal

| Signal | Shape | Range |
|--------|-------|-------|
| `focus` | sine, period ~12s | 0.35 – 0.90 |
| `calm` | sine, period ~15s, slightly anti-correlated | 0.25 – 0.75 |

Both exposed as Angular signals via `toSignal()`.

### Arm color tint

Material color lerped each RAF frame:

```
focus ≤ 0.4  →  #93c5fd  (calm blue)
focus = 0.65 →  #f59e0b  (amber)
focus ≥ 0.85 →  #ef4444  (deep red)
```

All arm + finger materials share one `MeshPhongMaterial` color — updated atomically, no partial-state flicker.

### HTML overlay (Angular template, not Three.js)

Positioned absolute over canvas, bottom-left:

```
┌─────────────────────────────┐
│  ⬤ FOCUS    ████████░░  0.73│
│  ⬤CALM     █████░░░░░  0.41 │
└─────────────────────────────┘
```

- Dot color matches current arm tint
- DM Mono font (matches existing dashboard biometric style)
- Bar width = signal value × 100%
- Updates at ~10 fps via `setInterval` (decoupled from 60 fps RAF)

### REC badge

Top-right corner of canvas, HTML overlay:

```
● REC  SESSION_001
```

Red pulsing dot. Sells "this is replayed capture data" narrative even with scripted motion.

---

## Route + Integration

- `/demo` lazy-loaded in `app.routes.ts`, no auth guard
- Full-viewport dark page — no dashboard shell, no sidebar
- Canvas fills viewport. EEG panel + REC badge float over it as absolute-positioned Angular elements
- `"Handwerk Capture Platform"` title badge top-left
- `NavigationComponent` gets "Demo" link — same pattern as existing nav entries
- URL shareable and bookmarkable directly

---

## Data Flow

```
DemoEegService
  focus signal ──→ DemoComponent effect()
                     → lerp arm material color
                     → update HTML overlay bars

DemoMotionService
  RAF tick ──→ advance waypoint t
            → analytical IK → shoulder/elbow/wrist rotations
            → finger curl lerp (state + focus tighten)
            → add paint quad at tool tip when waypoint reached

ResizeObserver ──→ renderer.setSize() + camera.aspect update
```

---

## Edge Cases

| Case | Behaviour |
|------|-----------|
| Canvas resize | `ResizeObserver` updates renderer + camera aspect |
| IK out of reach | Clamp `cos(θ)` to [-1, 1] — arm holds last valid pose |
| Component destroyed | RAF cancelled, all geometries + materials disposed |
| WebGL unavailable | Canvas hidden, fallback text shown |

---

## Out of Scope (v1)

- Real Supabase session replay (v2 — requires IMU captures + IK mapping pipeline)
- EEG-modulated arm speed
- Split-view hand closeup panel
- Mobile / touch controls
- Video panel alongside arm
- GLTF/STL mesh loading
