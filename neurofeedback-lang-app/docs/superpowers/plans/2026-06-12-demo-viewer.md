# Demo Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `/demo` route — a Three.js robot arm with articulated hand tracing a drywall boustrophedon path on a wall plane, overlaid with a mock EEG signal — to pitch the Handwerk capture platform concept.

**Architecture:** Three new files in `src/app/demo/`: `DemoEegService` (sinusoidal mock EEG signals), `DemoMotionService` (boustrophedon waypoints, analytical IK, finger curl), and `DemoComponent` (Three.js scene + HTML overlay). No WebSocket, no auth, no Supabase. Route wired as lazy-loaded `/demo`, nav item added.

**Tech Stack:** Angular 19 (standalone), Three.js (already installed), `MeshPhongMaterial` primitives only, `OrbitControls`, Angular signals + `effect()`.

---

> **⚠️ Note on tests:** `ng test` is broken project-wide (Neurosity SDK / Karma conflict). Skip spec files. Use `npx tsc --noEmit` after every TypeScript task as the compile gate. `ng build --configuration development` for final verification.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/app/demo/demo-eeg.service.ts` | Create | Sinusoidal focus/calm signals, `tick(deltaMs)` |
| `src/app/demo/demo-motion.service.ts` | Create | Waypoints, IK solver, finger curl logic |
| `src/app/demo/demo.component.ts` | Create | Three.js scene, RAF loop, HTML overlay template + styles |
| `src/app/app.routes.ts` | Modify | Add lazy `/demo` route before wildcard |
| `src/app/shared/components/layout/navigation/navigation.component.ts` | Modify | Add Demo nav item to `items` array |

---

## Task 1: DemoEegService — mock EEG signal

**Files:**
- Create: `src/app/demo/demo-eeg.service.ts`

- [ ] **Step 1: Create the service**

```typescript
// src/app/demo/demo-eeg.service.ts
import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class DemoEegService {
  private _t = 0;

  readonly focus = signal(0.6);
  readonly calm = signal(0.5);

  tick(deltaMs: number): void {
    this._t += deltaMs / 1000;
    this.focus.set(0.625 + 0.275 * Math.sin((2 * Math.PI * this._t) / 12));
    this.calm.set(0.500 + 0.250 * Math.sin((2 * Math.PI * this._t) / 15 + Math.PI * 0.6));
  }
}
```

- [ ] **Step 2: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/demo/demo-eeg.service.ts
git commit -m "feat(demo): add DemoEegService with sinusoidal focus/calm signals"
```

---

## Task 2: DemoMotionService — waypoints + IK + finger curl

**Files:**
- Create: `src/app/demo/demo-motion.service.ts`

- [ ] **Step 1: Create the service with all motion logic**

```typescript
// src/app/demo/demo-motion.service.ts
import { Injectable } from '@angular/core';

export interface MotionFrame {
  shoulderPan: number;    // Y-axis rotation — horizontal sweep
  shoulderTilt: number;   // X-axis rotation — elevation
  elbowAngle: number;     // X-axis rotation — elbow bend (law of cosines)
  wristAngle: number;     // keep 0 in v1 (perpendicular to wall)
  fingerCurl: number;     // radians applied to all proximal + medial phalanges
  state: 'grip' | 'release' | 'tighten';
}

// Arm geometry constants (metres)
const L1 = 0.35;   // upper arm
const L2 = 0.30;   // forearm

// Shoulder pivot position in world space
const SHOULDER = { x: 0, y: 0.45, z: 0 };

// Wall working surface
const WALL_Z = -0.40;
const PATH_W = 0.50;  // wall path width
const PATH_H = 0.40;  // wall path height
const PATH_Y0 = 0.25; // bottom of path (world Y)
const COLS = 4;
const ROWS = 5;

function buildWaypoints(): [number, number, number][] {
  const pts: [number, number, number][] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const col = r % 2 === 0 ? c : COLS - 1 - c;
      pts.push([
        -PATH_W / 2 + (col / (COLS - 1)) * PATH_W,
        PATH_Y0 + (r / (ROWS - 1)) * PATH_H,
        WALL_Z,
      ]);
    }
  }
  return pts;
}

function solveIK(tx: number, ty: number, tz: number): { pan: number; tilt: number; elbow: number } {
  const dx = tx - SHOULDER.x;
  const dy = ty - SHOULDER.y;
  const dz = tz - SHOULDER.z;

  const horizontalDist = Math.sqrt(dx * dx + dz * dz);
  const d = Math.sqrt(horizontalDist * horizontalDist + dy * dy);
  const dClamped = Math.min(Math.max(d, Math.abs(L1 - L2) + 0.001), L1 + L2 - 0.001);

  const pan = Math.atan2(dx, -dz);
  const elevAngle = Math.atan2(dy, horizontalDist);

  const cosElbow = (dClamped * dClamped - L1 * L1 - L2 * L2) / (2 * L1 * L2);
  const elbow = Math.acos(Math.max(-1, Math.min(1, cosElbow)));

  const cosAlpha = (dClamped * dClamped + L1 * L1 - L2 * L2) / (2 * dClamped * L1);
  const alpha = Math.acos(Math.max(-1, Math.min(1, cosAlpha)));
  const tilt = elevAngle + alpha;

  return { pan, tilt, elbow };
}

function fingerCurl(state: 'grip' | 'release' | 'tighten', focus: number): number {
  const DEG = Math.PI / 180;
  switch (state) {
    case 'release':  return 10 * DEG;
    case 'grip':     return 40 * DEG;
    case 'tighten':  return (40 + 25 * Math.max(0, (focus - 0.7) / 0.3)) * DEG;
  }
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.min(1, Math.max(0, t));
}

@Injectable({ providedIn: 'root' })
export class DemoMotionService {
  private readonly waypoints = buildWaypoints();
  private waypointIndex = 0;
  private progress = 0;          // 0–1 between current and next waypoint
  private readonly SPEED = 1 / 8; // full path in 8 seconds

  private _curl = 10 * (Math.PI / 180);

  tick(deltaMs: number, focus: number): MotionFrame {
    const dt = deltaMs / 1000;
    this.progress += dt * this.SPEED * this.waypoints.length;
    if (this.progress >= 1) {
      this.progress -= 1;
      this.waypointIndex = (this.waypointIndex + 1) % this.waypoints.length;
    }

    const curr = this.waypoints[this.waypointIndex];
    const next = this.waypoints[(this.waypointIndex + 1) % this.waypoints.length];
    const tx = lerp(curr[0], next[0], this.progress);
    const ty = lerp(curr[1], next[1], this.progress);
    const tz = lerp(curr[2], next[2], this.progress);

    const ik = solveIK(tx, ty, tz);

    // State: release when repositioning (large X jump between waypoints = new row)
    const isRepositioning = Math.abs(next[1] - curr[1]) > 0.01;
    const state: 'grip' | 'release' | 'tighten' =
      isRepositioning ? 'release' : focus > 0.7 ? 'tighten' : 'grip';

    const targetCurl = fingerCurl(state, focus);
    this._curl = lerp(this._curl, targetCurl, Math.min(1, dt * 4));

    return {
      shoulderPan: ik.pan,
      shoulderTilt: ik.tilt,
      elbowAngle: ik.elbow,
      wristAngle: 0,
      fingerCurl: this._curl,
      state,
    };
  }

  /** Returns the current tool-tip world position for the paint trail. */
  currentToolTip(frame: MotionFrame): [number, number, number] {
    const px = SHOULDER.x + (L1 + L2) * Math.sin(frame.shoulderPan);
    const py = SHOULDER.y + (L1 + L2) * Math.sin(frame.shoulderTilt);
    const pz = SHOULDER.z - (L1 + L2) * Math.cos(frame.shoulderPan);
    return [px, py, pz];
  }
}
```

- [ ] **Step 2: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/demo/demo-motion.service.ts
git commit -m "feat(demo): add DemoMotionService — waypoints, IK solver, finger curl"
```

---

## Task 3: DemoComponent — scaffold + Three.js scene init

**Files:**
- Create: `src/app/demo/demo.component.ts`

Build the component shell with Three.js scene, camera, lights, OrbitControls, ResizeObserver, and cleanup. No arm yet.

- [ ] **Step 1: Create the component**

```typescript
// src/app/demo/demo.component.ts
import {
  Component, ElementRef, OnDestroy, ViewChild, afterNextRender, effect, inject,
} from '@angular/core';
import {
  AmbientLight, Color, DirectionalLight, Mesh, MeshPhongMaterial, Object3D,
  PerspectiveCamera, Scene, WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { DemoEegService } from './demo-eeg.service';
import { DemoMotionService, MotionFrame } from './demo-motion.service';

@Component({
  selector: 'app-demo',
  standalone: true,
  template: `
    <div class="demo-wrap">
      <canvas #canvas></canvas>

      <div class="title-badge">Handwerk Capture Platform</div>

      <div class="rec-badge">
        <span class="rec-dot"></span>
        REC&nbsp;&nbsp;SESSION_001
      </div>

      <div class="eeg-panel">
        <div class="eeg-row">
          <span class="dot" [style.background]="dotColor"></span>
          <span class="eeg-label">FOCUS</span>
          <div class="bar"><div class="fill" [style.width.%]="focusPct"></div></div>
          <span class="eeg-val">{{ focusVal }}</span>
        </div>
        <div class="eeg-row">
          <span class="dot calm"></span>
          <span class="eeg-label">CALM</span>
          <div class="bar calm-bar"><div class="fill calm-fill" [style.width.%]="calmPct"></div></div>
          <span class="eeg-val">{{ calmVal }}</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; width: 100vw; height: 100vh; background: #0f172a; overflow: hidden; }

    .demo-wrap { position: relative; width: 100%; height: 100%; }

    canvas { display: block; width: 100%; height: 100%; }

    .title-badge {
      position: absolute; top: 20px; left: 20px;
      font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 600;
      color: rgba(255,255,255,0.55); letter-spacing: .5px;
    }

    .rec-badge {
      position: absolute; top: 20px; right: 20px;
      display: flex; align-items: center; gap: 7px;
      font-family: 'DM Mono', monospace; font-size: 12px; color: rgba(255,255,255,0.7);
    }
    .rec-dot {
      width: 8px; height: 8px; border-radius: 50%; background: #ef4444;
      animation: pulse 1.2s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.3; }
    }

    .eeg-panel {
      position: absolute; bottom: 24px; left: 24px;
      background: rgba(15,23,42,0.75); backdrop-filter: blur(6px);
      border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
      padding: 12px 16px; display: flex; flex-direction: column; gap: 8px;
    }
    .eeg-row { display: flex; align-items: center; gap: 10px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot.calm { background: #60a5fa; }
    .eeg-label {
      font-family: 'DM Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.5);
      width: 38px;
    }
    .bar {
      width: 100px; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px;
    }
    .fill { height: 100%; border-radius: 2px; background: #93c5fd; transition: width .1s; }
    .calm-fill { background: #60a5fa; }
    .eeg-val {
      font-family: 'DM Mono', monospace; font-size: 11px; color: rgba(255,255,255,0.7);
      width: 32px; text-align: right;
    }
  `],
})
export class DemoComponent implements OnDestroy {
  @ViewChild('canvas', { static: true }) private canvasRef!: ElementRef<HTMLCanvasElement>;

  private readonly eeg = inject(DemoEegService);
  private readonly motion = inject(DemoMotionService);

  // HTML overlay state (updated at ~10fps via interval)
  dotColor = '#93c5fd';
  focusPct = 60;
  calmPct  = 50;
  focusVal = '0.60';
  calmVal  = '0.50';

  private renderer: WebGLRenderer | null = null;
  private rafId = 0;
  private lastTime = 0;
  private resizeObserver: ResizeObserver | null = null;
  private overlayInterval = 0;

  // Three.js joints — populated in buildSkeleton()
  private shoulderPan!: Object3D;
  private shoulderTilt!: Object3D;
  private elbowPivot!: Object3D;
  private wristPivot!: Object3D;
  private fingerProximal: Object3D[] = [];  // 5 proximal joints (index 0=thumb)
  private fingerMedial: Object3D[]  = [];  // 5 medial joints
  private armMaterial!: MeshPhongMaterial;

  constructor() {
    afterNextRender(() => this.initScene());
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.rafId);
    clearInterval(this.overlayInterval);
    this.resizeObserver?.disconnect();
    this.armMaterial?.dispose();
    this.renderer?.dispose();
  }

  private initScene(): void {
    const canvas = this.canvasRef.nativeElement;
    if (!canvas.getContext('webgl2') && !canvas.getContext('webgl')) return;

    const w = canvas.clientWidth  || 800;
    const h = canvas.clientHeight || 600;

    const renderer = new WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(devicePixelRatio);
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x0f172a);
    this.renderer = renderer;

    const scene = new Scene();
    const camera = new PerspectiveCamera(45, w / h, 0.01, 50);
    camera.position.set(1.1, 0.8, 1.4);
    camera.lookAt(0, 0.45, -0.2);

    scene.add(new AmbientLight(0xffffff, 0.5));
    const key = new DirectionalLight(0xffffff, 0.8);
    key.position.set(1, 2, 1.5);
    scene.add(key);
    const fill = new DirectionalLight(0xffffff, 0.4);
    fill.position.set(-1, 0.5, 0.5);
    scene.add(fill);

    this.buildSkeleton(scene);
    this.buildWall(scene);

    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, 0.45, -0.2);
    controls.enablePan = false;
    controls.update();

    this.lastTime = performance.now();
    const loop = (now: number) => {
      this.rafId = requestAnimationFrame(loop);
      const dt = now - this.lastTime;
      this.lastTime = now;
      this.eeg.tick(dt);
      const frame = this.motion.tick(dt, this.eeg.focus());
      this.applyPose(frame);
      this.updateArmColor(this.eeg.focus());
      controls.update();
      renderer.render(scene, camera);
    };
    this.rafId = requestAnimationFrame(loop);

    this.resizeObserver = new ResizeObserver(() => {
      const nw = canvas.clientWidth;
      const nh = canvas.clientHeight;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh, false);
    });
    this.resizeObserver.observe(canvas);

    // HTML overlay at 10fps
    this.overlayInterval = window.setInterval(() => this.updateOverlay(), 100);
  }

  private updateOverlay(): void {
    const f = this.eeg.focus();
    const c = this.eeg.calm();
    this.focusPct = Math.round(f * 100);
    this.calmPct  = Math.round(c * 100);
    this.focusVal = f.toFixed(2);
    this.calmVal  = c.toFixed(2);
    this.dotColor = this.eegHexColor(f);
  }

  private eegHexColor(focus: number): string {
    if (focus <= 0.4)  return '#93c5fd';
    if (focus <= 0.65) return '#f59e0b';
    return '#ef4444';
  }

  private updateArmColor(focus: number): void {
    if (!this.armMaterial) return;
    const c = new Color();
    if (focus <= 0.4) {
      c.set(0x93c5fd);
    } else if (focus <= 0.65) {
      const t = (focus - 0.4) / 0.25;
      c.lerpColors(new Color(0x93c5fd), new Color(0xf59e0b), t);
    } else {
      const t = Math.min(1, (focus - 0.65) / 0.2);
      c.lerpColors(new Color(0xf59e0b), new Color(0xef4444), t);
    }
    this.armMaterial.color.copy(c);
  }

  private buildSkeleton(scene: Scene): void {
    // Implemented in Task 4
  }

  private buildWall(scene: Scene): void {
    // Implemented in Task 4
  }

  private applyPose(_frame: MotionFrame): void {
    // Implemented in Task 5
  }
}
```

- [ ] **Step 2: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/demo/demo.component.ts
git commit -m "feat(demo): scaffold DemoComponent — scene init, EEG overlay, RAF loop"
```

---

## Task 4: DemoComponent — arm skeleton + wall

Replace the empty `buildSkeleton` and `buildWall` stubs in `demo.component.ts`.

**Files:**
- Modify: `src/app/demo/demo.component.ts`

- [ ] **Step 1: First update the import block at the top of `demo.component.ts`**

Replace the existing `import { ... } from 'three'` block with:

```typescript
import {
  AmbientLight, BoxGeometry, Color, CylinderGeometry, DirectionalLight,
  Mesh, MeshPhongMaterial, Object3D, PerspectiveCamera, PlaneGeometry,
  Scene, SphereGeometry, WebGLRenderer,
} from 'three';
```

- [ ] **Step 2: Replace `buildSkeleton` with the full arm + hand hierarchy**

Replace the empty `buildSkeleton(scene: Scene): void { // Implemented in Task 4 }` method with:

```typescript
private buildSkeleton(scene: Scene): void {
  const mat = new MeshPhongMaterial({ color: 0x93c5fd });
  this.armMaterial = mat;

  const BONE_R  = 0.022;
  const JOINT_R = 0.032;

  const sphere = () => new Mesh(new SphereGeometry(JOINT_R, 10, 8), mat);
  const bone = (len: number) => {
    const cyl = new Mesh(new CylinderGeometry(BONE_R, BONE_R, len, 10), mat);
    cyl.rotation.x = Math.PI / 2;   // align cylinder to Z axis
    cyl.position.z = -len / 2;
    return cyl;
  };
  const node = (): Object3D => { const n = new Object3D(); n.add(sphere()); return n; };

  // Base pedestal
  const base = new Mesh(new CylinderGeometry(0.05, 0.07, 0.5, 16), mat);
  base.position.set(0, 0.25, 0);
  scene.add(base);

  // Shoulder (pan around Y, tilt around X)
  const shoulderPan = new Object3D();
  shoulderPan.position.set(0, 0.50, 0);
  scene.add(shoulderPan);
  this.shoulderPan = shoulderPan;

  const shoulderTilt = node();
  shoulderPan.add(shoulderTilt);
  this.shoulderTilt = shoulderTilt;

  // Upper arm
  const L1 = 0.35;
  shoulderTilt.add(bone(L1));

  // Elbow
  const elbowPivot = node();
  elbowPivot.position.z = -L1;
  shoulderTilt.add(elbowPivot);
  this.elbowPivot = elbowPivot;

  // Forearm
  const L2 = 0.30;
  elbowPivot.add(bone(L2));

  // Wrist
  const wristPivot = node();
  wristPivot.position.z = -L2;
  elbowPivot.add(wristPivot);
  this.wristPivot = wristPivot;

  // Palm
  const palm = new Mesh(
    new (require('three').BoxGeometry)(0.08, 0.03, 0.10), mat
  );
  palm.position.z = -0.06;
  wristPivot.add(palm);

  // Fingers: 5 chains (thumb + 4 fingers), each: metacarpal → proximal → distal
  const FINGER_SPREAD = [-0.03, -0.015, 0, 0.015, 0.03];  // X offsets
  const THUMB_ANGLE   = -0.5; // thumb angled outward
  const MC_LEN  = 0.025;
  const PX_LEN  = 0.030;
  const DI_LEN  = 0.022;

  for (let i = 0; i < 5; i++) {
    const isThumb = i === 0;
    const xOff = isThumb ? -0.035 : FINGER_SPREAD[i - 1] - 0.01;
    const baseZ = isThumb ? -0.04 : -0.11;

    // Metacarpal (attached to wrist, static)
    const mc = new Object3D();
    mc.position.set(xOff, 0, baseZ);
    if (isThumb) mc.rotation.y = THUMB_ANGLE;
    wristPivot.add(mc);
    mc.add(bone(MC_LEN));

    // Proximal phalange (curl joint)
    const proximal = new Object3D();
    proximal.position.z = -MC_LEN;
    mc.add(proximal);
    proximal.add(sphere());
    proximal.add(bone(PX_LEN));
    this.fingerProximal.push(proximal);

    // Medial phalange (follow curl at half angle)
    const medial = new Object3D();
    medial.position.z = -PX_LEN;
    proximal.add(medial);
    medial.add(sphere());
    medial.add(bone(DI_LEN));
    this.fingerMedial.push(medial);
  }
}
```

- [ ] **Step 3: Replace `buildWall` with wall plane + emissive surface**

Replace the empty `buildWall(scene: Scene): void { // Implemented in Task 4 }` method with:

```typescript
private buildWall(scene: Scene): void {
  const wallMat = new MeshPhongMaterial({
    color: 0x334155, emissive: 0x1e293b, side: 2,
  });
  const wall = new Mesh(new PlaneGeometry(0.8, 0.6), wallMat);
  wall.position.set(0, 0.45, -0.41);
  // PlaneGeometry faces +Z; rotate Math.PI so it faces the camera at +Z
  wall.rotation.y = Math.PI;
  scene.add(wall);
}
```

- [ ] **Step 4: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add src/app/demo/demo.component.ts
git commit -m "feat(demo): build arm skeleton + wall plane in DemoComponent"
```

---

## Task 5: DemoComponent — `applyPose` + paint trail

Replace the empty `applyPose` stub and add the paint trail to `buildWall`.

**Files:**
- Modify: `src/app/demo/demo.component.ts`

- [ ] **Step 1: Replace `applyPose` stub**

Replace `private applyPose(_frame: MotionFrame): void { // Implemented in Task 5 }` with:

```typescript
private applyPose(frame: MotionFrame): void {
  if (!this.shoulderPan) return;

  this.shoulderPan.rotation.y  = frame.shoulderPan;
  this.shoulderTilt.rotation.x = -frame.shoulderTilt;
  this.elbowPivot.rotation.x   = frame.elbowAngle;
  this.wristPivot.rotation.x   = frame.wristAngle;

  const curl = frame.fingerCurl;
  for (let i = 0; i < 5; i++) {
    if (this.fingerProximal[i]) this.fingerProximal[i].rotation.x = curl;
    if (this.fingerMedial[i])   this.fingerMedial[i].rotation.x   = curl * 0.6;
  }
}
```

- [ ] **Step 2: Add paint trail support**

Add the following private fields near the top of the class (after `fingerMedial`):

```typescript
private paintScene: Scene | null = null;
private lastPaintZ = -99;
```

In `initScene()`, after `this.buildSkeleton(scene)`, pass `scene` into a paint-trail store:
```typescript
this.paintScene = scene;
```

Add this private method:

```typescript
private addPaintDab(x: number, y: number, z: number): void {
  if (!this.paintScene) return;
  if (Math.abs(z - this.lastPaintZ) < 0.001) return; // only near wall
  this.lastPaintZ = z;

  const dab = new Mesh(
    new PlaneGeometry(0.04, 0.015),
    new MeshPhongMaterial({ color: 0x94a3b8, emissive: 0x64748b }),
  );
  dab.position.set(x, y, -0.405);
  dab.rotation.y = Math.PI;
  this.paintScene.add(dab);
}
```

In the RAF loop inside `initScene()`, after `this.applyPose(frame)`, add:
```typescript
const tip = this.motion.currentToolTip(frame);
if (Math.abs(tip[2] - (-0.40)) < 0.05) {
  this.addPaintDab(tip[0], tip[1], tip[2]);
}
```

- [ ] **Step 3: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/app/demo/demo.component.ts
git commit -m "feat(demo): apply IK pose to arm joints + add paint trail on wall"
```

---

## Task 6: Route + nav integration

**Files:**
- Modify: `src/app/app.routes.ts`
- Modify: `src/app/shared/components/layout/navigation/navigation.component.ts`

- [ ] **Step 1: Add `/demo` route to `app.routes.ts`**

In `src/app/app.routes.ts`, add the lazy demo route before the wildcard `'**'` entry:

```typescript
{
  path: 'demo',
  loadComponent: () =>
    import('./demo/demo.component').then(m => m.DemoComponent),
},
```

The final routes array should look like:
```typescript
export const routes: Routes = [
  {
    path: 'capture',
    children: CAPTURE_ROUTES,
  },
  {
    path: '',
    component: DashboardLayoutComponent,
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard', component: DashboardComponent },
      {
        path: 'exercises',
        children: [
          { path: '', component: ExercisesOverviewComponent },
          {
            path: 'speaking',
            children: [
              { path: '', component: ExercisesOverviewComponent },
              { path: ':id', component: SpeakingExerciseComponent },
            ],
          },
        ],
      },
    ],
  },
  {
    path: 'demo',
    loadComponent: () =>
      import('./demo/demo.component').then(m => m.DemoComponent),
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
```

- [ ] **Step 2: Add Demo nav item to `NavigationComponent`**

In `src/app/shared/components/layout/navigation/navigation.component.ts`, add to the `items` array:

```typescript
readonly items: NavItem[] = [
  { route: '/dashboard', icon: 'dashboard', label: 'Dashboard', exact: true },
  { route: '/exercises', icon: 'school',     label: 'Exercises' },
  { route: '/capture',   icon: 'sensors',    label: 'Capture',   exact: true },
  { route: '/demo',      icon: 'smart_toy',  label: 'Demo',      exact: true },
];
```

- [ ] **Step 3: Verify compile**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/app/app.routes.ts src/app/shared/components/layout/navigation/navigation.component.ts
git commit -m "feat(demo): add /demo route + nav item"
```

---

## Task 7: Final build verification

- [ ] **Step 1: Full TypeScript check**

```bash
npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 2: Development build**

```bash
ng build --configuration development
```
Expected: build succeeds, no errors, bundle includes the `demo` lazy chunk.

- [ ] **Step 3: Manual smoke test**

Run `npm start`, open `http://localhost:4200/demo`. Verify:
- Dark full-viewport page loads
- Robot arm visible, reaching toward wall plane
- Arm animates (moves along boustrophedon path)
- Arm color shifts between blue → amber → red over ~12 seconds
- EEG panel (bottom-left) updates with FOCUS/CALM bars
- REC badge (top-right) pulses
- OrbitControls: drag to rotate the scene
- Paint dabs appear on wall as arm passes

Visual tuning needed after smoke test — adjust `shoulderTilt` sign, `camera.position`, and `wall.rotation` if arm appears inverted or wall faces wrong direction. These are axis-convention corrections verified by inspection, not code bugs.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(demo): complete demo viewer — robot arm, EEG overlay, wall trail"
```

---

## Visual Tuning Reference

If the arm looks wrong after the smoke test, these are the common fixes:

| Symptom | Fix |
|---------|-----|
| Arm points backward (away from wall) | Negate `shoulderTilt` in `applyPose`: `this.shoulderTilt.rotation.x = frame.shoulderTilt` (remove minus) |
| Elbow bends wrong direction | Negate `elbowAngle`: `this.elbowPivot.rotation.x = -frame.elbowAngle` |
| Arm sweeps in wrong horizontal direction | Negate `shoulderPan`: `this.shoulderPan.rotation.y = -frame.shoulderPan` |
| Wall faces away from camera | Change `wall.rotation.y = 0` (remove `Math.PI`) |
| Arm too short / can't reach wall | Increase `L1` and `L2` in `DemoMotionService` by 0.05 each; move `WALL_Z` closer to 0 |
| Fingers curl wrong direction | Negate curl: `this.fingerProximal[i].rotation.x = -curl` |
