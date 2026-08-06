# H1 Robot Viewer — Design Spec

**Date:** 2026-06-12
**Status:** Approved

## Goal

Embed a live 3D stick-figure visualization of the H1 humanoid robot inside the existing `SimControlComponent` dashboard card. Joint angles stream via WebSocket (`SimBridgeService.joints()` signal) — no server changes required.

---

## Architecture

### New component: `RobotViewerComponent`

**Path:** `src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts`

Standalone Angular component. Owns the Three.js scene lifecycle.

**Inputs:**
- `joints = input<number[]>([])` — 19 H1 ctrl values from `bridge.joints()`
- `status = input<SimStatus>('disconnected')` — dims skeleton when disconnected

**Template:** single `<canvas #canvas>` element, height 220px, width 100%.

**Lifecycle:**
- `afterNextRender()` — create renderer, scene, camera, lights, skeleton, OrbitControls; start RAF loop
- Signal `effect()` — watches `joints`, calls `updatePose()` on change
- `ResizeObserver` on host element — updates `renderer.setSize()` + camera aspect ratio
- `ngOnDestroy` — `cancelAnimationFrame`, `renderer.dispose()`, dispose all geometries + materials

**Integration:** `SimControlComponent` adds `<app-robot-viewer>` above existing status/progress rows. Canvas height 220px.

---

## Skeleton Structure

Bones are `CylinderGeometry` segments (radius 0.025 m). Joint pivots are `SphereGeometry` nodes (radius 0.035 m). Each joint is a `THREE.Object3D` child of its parent — rotations compose up the chain.

**Approximate bone lengths (H1 proportions):**

| Segment | Length |
|---------|--------|
| Spine (pelvis → shoulder level) | 0.40 m |
| Thigh | 0.40 m |
| Shin | 0.40 m |
| Foot stub | 0.06 m |
| Upper arm | 0.25 m |
| Forearm | 0.22 m |
| Head sphere radius | 0.08 m |

**Hierarchy and joint → ctrl index mapping:**

```
pelvis (root, y ≈ 0.98 m)
├── torso          [10: torso_yaw     → rotation.y]   spine 0.40m → head sphere
│   ├── l_shoulder_pitch  [11 → rotation.z]
│   │   └── l_shoulder_roll  [12 → rotation.x]
│   │       └── l_shoulder_yaw  [13 → rotation.y]
│   │           └── l_elbow  [14 → rotation.z]  forearm 0.22m
│   └── r_shoulder_pitch  [15 → rotation.z]
│       └── r_shoulder_roll  [16 → rotation.x]
│           └── r_shoulder_yaw  [17 → rotation.y]
│               └── r_elbow  [18 → rotation.z]
├── l_hip_yaw      [0 → rotation.y]
│   └── l_hip_roll  [1 → rotation.x]
│       └── l_hip_pitch  [2 → rotation.z]  thigh 0.40m
│           └── l_knee  [3 → rotation.z]  shin 0.40m
│               └── l_ankle  [4 → rotation.z]  foot stub
└── r_hip_yaw      [5 → rotation.y]
    └── r_hip_roll  [6 → rotation.x]
        └── r_hip_pitch  [7 → rotation.z]  thigh 0.40m
            └── r_knee  [8 → rotation.z]  shin 0.40m
                └── r_ankle  [9 → rotation.z]  foot stub
```

Zero pose (all ctrl = 0) matches H1 neutral standing.

> **Note:** Exact Three.js rotation axes (x/y/z) per joint are approximations based on standard humanoid convention. Final axis assignments will be verified visually during implementation and corrected by inspection — the mapping table above is the implementation starting point, not a hard requirement.

---

## Data Flow

```
WS message → SimBridgeService._snap.update()
  → bridge.joints() signal changes
  → RobotViewerComponent effect()
  → updatePose(joints): sets joint.rotation.{x|y|z} per mapping table
  → Three.js RAF loop renders at ~60 fps (continuous, no per-frame rebuild)
```

No server-side changes. `q` field in WS messages already carries 19 ctrl values.

---

## Visual Style

| Property | Value |
|----------|-------|
| Canvas background | `#0f172a` (dark navy) |
| Bone color | `#93c5fd` (light blue) |
| Joint sphere color | `#60a5fa` |
| Material type | `MeshPhongMaterial` |
| Opacity when disconnected | 0.3 |
| Camera position | `(0, 1.2, 2.5)` looking at `(0, 0.9, 0)` |
| Lights | `AmbientLight` (0xffffff, 0.6) + `DirectionalLight` (0xffffff, 0.8) from above-front |
| Orbit controls | Enabled (rotate only; no pan/zoom by default) |

---

## Edge Cases

| Case | Behaviour |
|------|-----------|
| `joints.length < 19` | `updatePose` no-ops; skeleton holds last known pose |
| `status === 'disconnected'` | bone + joint material opacity → 0.3 |
| Canvas resize | `ResizeObserver` updates `renderer.setSize()` + `camera.aspect` |
| Component destroyed | RAF cancelled, renderer + all geometries + materials disposed |

---

## Dependencies

- `three` + `@types/three` added to `package.json` (prod dep)
- Only named imports used (tree-shakeable): `WebGLRenderer`, `Scene`, `PerspectiveCamera`, `CylinderGeometry`, `SphereGeometry`, `MeshPhongMaterial`, `Mesh`, `Object3D`, `AmbientLight`, `DirectionalLight`, `Vector3`
- `OrbitControls` from `three/addons/controls/OrbitControls.js`

---

## Out of Scope

- Loaded H1 meshes (STL/GLTF)
- Video streaming from HF Space
- Dedicated full-page route
- Floor grid or environment
