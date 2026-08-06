# Local Model Task — Third Arm + Background

Paste the block below as your first message to aider.
Add files first: `/add src/app/demo/demo-motion.service.ts src/app/demo/demo.component.ts`

---

```
You are adding a third robot arm and a background to an existing Angular 19 Three.js demo at:
/Users/alexanderlemberger/neurofeedback-lang-app

Read both files fully before writing any code.

## Files to change (ONLY these two)

1. src/app/demo/demo-motion.service.ts
2. src/app/demo/demo.component.ts

---

## Change 1: Third arm — floor worker (demo-motion.service.ts)

Add a third arm that works on a HORIZONTAL floor plane instead of the vertical wall.
This arm stirs/spreads compound in a circular path on the floor — visually distinct from the two wall arms.

### Constants to add (top of file, near existing constants)

```typescript
const SHOULDER_C = { x: 0, y: 0.45, z: 0.55 }; // center arm, behind camera plane, faces floor

const FLOOR_Y    = 0.05;  // floor working height (world Y)
const FLOOR_R    = 0.20;  // circular path radius on floor
const FLOOR_SEGMENTS = 20; // waypoints around circle
```

### buildFloorWaypoints() function to add

```typescript
function buildFloorWaypoints(): [number, number, number][] {
  const pts: [number, number, number][] = [];
  for (let i = 0; i < FLOOR_SEGMENTS; i++) {
    const angle = (i / FLOOR_SEGMENTS) * Math.PI * 2;
    pts.push([
      SHOULDER_C.x + FLOOR_R * Math.cos(angle),
      FLOOR_Y,
      SHOULDER_C.z + FLOOR_R * Math.sin(angle),
    ]);
  }
  return pts;
}
```

### solveIKFloor() function to add

IK for a target below the shoulder (floor arm points downward):

```typescript
function solveIKFloor(tx: number, ty: number, tz: number): { pan: number; tilt: number; elbow: number } {
  const dx = tx - SHOULDER_C.x;
  const dy = ty - SHOULDER_C.y;
  const dz = tz - SHOULDER_C.z;

  const horizontalDist = Math.sqrt(dx * dx + dz * dz);
  const d = Math.sqrt(horizontalDist * horizontalDist + dy * dy);
  const dClamped = Math.min(Math.max(d, Math.abs(L1 - L2) + 0.001), L1 + L2 - 0.001);

  const pan = Math.atan2(dx, dz);
  const elevAngle = Math.atan2(dy, horizontalDist); // negative — arm points down

  const cosElbow = (dClamped * dClamped - L1 * L1 - L2 * L2) / (2 * L1 * L2);
  const elbow = Math.acos(Math.max(-1, Math.min(1, cosElbow)));

  const cosAlpha = (dClamped * dClamped + L1 * L1 - L2 * L2) / (2 * dClamped * L1);
  const alpha = Math.acos(Math.max(-1, Math.min(1, cosAlpha)));
  const tilt = elevAngle + alpha;

  return { pan, tilt, elbow };
}
```

### DemoMotionService: add center arm state + tickCenter()

Inside the class, add a `_center` state field alongside `_right` and `_left`:

```typescript
private readonly _center: DemoMotionState = {
  waypoints: buildFloorWaypoints(),
  waypointIndex: 0,
  progress: 0,
  curl: 10 * (Math.PI / 180),
};
```

Add `tickCenter(deltaMs: number, focus: number): MotionFrame`:

```typescript
tickCenter(deltaMs: number, focus: number): MotionFrame {
  const dt = deltaMs / 1000;
  const s = this._center;
  s.progress += dt * this.SPEED * s.waypoints.length;
  if (s.progress >= 1) {
    s.progress -= 1;
    s.waypointIndex = (s.waypointIndex + 1) % s.waypoints.length;
  }

  const curr = s.waypoints[s.waypointIndex];
  const next  = s.waypoints[(s.waypointIndex + 1) % s.waypoints.length];
  const tx = lerp(curr[0], next[0], s.progress);
  const ty = lerp(curr[1], next[1], s.progress);
  const tz = lerp(curr[2], next[2], s.progress);

  const ik = solveIKFloor(tx, ty, tz);
  const state: 'grip' | 'release' | 'tighten' = focus > 0.7 ? 'tighten' : 'grip';
  const targetCurl = fingerCurl(state, focus);
  s.curl = lerp(s.curl, targetCurl, Math.min(1, dt * 4));

  return {
    shoulderPan: ik.pan,
    shoulderTilt: ik.tilt,
    elbowAngle: ik.elbow,
    wristAngle: 0,
    fingerCurl: s.curl,
    state,
  };
}
```

Add `currentToolTipCenter(frame: MotionFrame): [number, number, number]`:

```typescript
currentToolTipCenter(frame: MotionFrame): [number, number, number] {
  const px = SHOULDER_C.x + (L1 + L2) * Math.sin(frame.shoulderPan) * Math.cos(frame.shoulderTilt);
  const py = SHOULDER_C.y - (L1 + L2) * Math.sin(frame.shoulderTilt);
  const pz = SHOULDER_C.z + (L1 + L2) * Math.cos(frame.shoulderPan) * Math.cos(frame.shoulderTilt);
  return [px, py, pz];
}
```

---

## Change 2: Scene — third skeleton + background (demo.component.ts)

### 2a: Add joint fields for center arm (after fingerMedial_L fields)

```typescript
private shoulderPan_C!: Object3D;
private shoulderTilt_C!: Object3D;
private elbowPivot_C!: Object3D;
private wristPivot_C!: Object3D;
private fingerProximal_C: Object3D[] = [];
private fingerMedial_C: Object3D[]   = [];
```

### 2b: Add import for GridHelper and Fog

In the `import { ... } from 'three'` block, add: `GridHelper, FogExp2`

### 2c: Add buildSkeletonCenter(scene: Scene)

Copy `buildSkeletonLeft` exactly, but:
- Base position: `x = 0, z = 0.55` (center, toward camera)
- shoulderPan position: `x = 0, z = 0.55`
- Assign joints to `_C` fields
- Use the same `armMaterial`

```typescript
private buildSkeletonCenter(scene: Scene): void {
  const mat = this.armMaterial;
  const BONE_R  = 0.022;
  const JOINT_R = 0.032;

  const sphere = () => new Mesh(new SphereGeometry(JOINT_R, 10, 8), mat);
  const bone = (len: number) => {
    const cyl = new Mesh(new CylinderGeometry(BONE_R, BONE_R, len, 10), mat);
    cyl.rotation.x = Math.PI / 2;
    cyl.position.z = -len / 2;
    return cyl;
  };
  const node = (): Object3D => { const n = new Object3D(); n.add(sphere()); return n; };

  const base = new Mesh(new CylinderGeometry(0.05, 0.07, 0.5, 16), mat);
  base.position.set(0, 0.25, 0.55);
  scene.add(base);

  const shoulderPan = new Object3D();
  shoulderPan.position.set(0, 0.50, 0.55);
  scene.add(shoulderPan);
  this.shoulderPan_C = shoulderPan;

  const shoulderTilt = node();
  shoulderPan.add(shoulderTilt);
  this.shoulderTilt_C = shoulderTilt;

  const L1 = 0.35;
  shoulderTilt.add(bone(L1));

  const elbowPivot = node();
  elbowPivot.position.z = -L1;
  shoulderTilt.add(elbowPivot);
  this.elbowPivot_C = elbowPivot;

  const L2 = 0.30;
  elbowPivot.add(bone(L2));

  const wristPivot = node();
  wristPivot.position.z = -L2;
  elbowPivot.add(wristPivot);
  this.wristPivot_C = wristPivot;

  const palm = new Mesh(new BoxGeometry(0.08, 0.03, 0.10), mat);
  palm.position.z = -0.06;
  wristPivot.add(palm);

  const FINGER_SPREAD = [-0.03, -0.015, 0, 0.015, 0.03];
  const MC_LEN = 0.025;
  const PX_LEN = 0.030;
  const DI_LEN = 0.022;

  for (let i = 0; i < 5; i++) {
    const isThumb = i === 0;
    const xOff = isThumb ? -0.035 : FINGER_SPREAD[i - 1] - 0.01;
    const baseZ = isThumb ? -0.04 : -0.11;

    const mc = new Object3D();
    mc.position.set(xOff, 0, baseZ);
    if (isThumb) mc.rotation.y = -0.5;
    wristPivot.add(mc);
    mc.add(bone(MC_LEN));

    const proximal = new Object3D();
    proximal.position.z = -MC_LEN;
    mc.add(proximal);
    proximal.add(sphere());
    proximal.add(bone(PX_LEN));
    this.fingerProximal_C.push(proximal);

    const medial = new Object3D();
    medial.position.z = -PX_LEN;
    proximal.add(medial);
    medial.add(sphere());
    medial.add(bone(DI_LEN));
    this.fingerMedial_C.push(medial);
  }
}
```

### 2d: Add applyPoseCenter(frame: MotionFrame)

```typescript
private applyPoseCenter(frame: MotionFrame): void {
  if (!this.shoulderPan_C) return;
  this.shoulderPan_C.rotation.y  = frame.shoulderPan;
  this.shoulderTilt_C.rotation.x = -frame.shoulderTilt;
  this.elbowPivot_C.rotation.x   = frame.elbowAngle;
  this.wristPivot_C.rotation.x   = frame.wristAngle;
  for (let i = 0; i < 5; i++) {
    if (this.fingerProximal_C[i]) this.fingerProximal_C[i].rotation.x = frame.fingerCurl;
    if (this.fingerMedial_C[i])   this.fingerMedial_C[i].rotation.x   = frame.fingerCurl * 0.6;
  }
}
```

### 2e: Add buildBackground(scene: Scene)

```typescript
private buildBackground(scene: Scene): void {
  // Exponential fog — fades geometry into background colour
  scene.fog = new FogExp2(0x0f172a, 0.35);

  // Grid floor
  const grid = new GridHelper(6, 24, 0x1e3a5f, 0x1e293b);
  grid.position.y = 0;
  scene.add(grid);
}
```

### 2f: Wire everything in initScene()

After `this.buildWall(scene)`, add:
```typescript
this.buildSkeletonCenter(scene);
this.buildBackground(scene);
```

In the RAF loop, after the existing `tipL` block, add:
```typescript
const frameC = this.motion.tickCenter(dt, this.eeg.focus());
this.applyPoseCenter(frameC);
```

---

## Constraints

- DO NOT edit any file not listed above
- DO NOT add npm packages
- DO NOT use `any`, `as unknown as`, or `@ts-ignore`
- DO NOT commit
- After every change: npx tsc --noEmit
- Final: ng build --configuration development

## Verification

1. `npx tsc --noEmit` → zero errors
2. `ng build --configuration development` → succeeds
3. Navigate to http://localhost:4200/demo:
   - Three arms visible: two reaching wall, one pointing down toward floor
   - Grid floor visible below arms
   - Fog fades distant geometry into dark background
   - All three arms animate and color-shift with EEG signal
```
