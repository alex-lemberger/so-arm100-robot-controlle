# H1 Robot Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed a live Three.js stick-figure visualization of the H1 humanoid inside the `SimControlComponent` dashboard card, driven by the existing `bridge.joints()` signal.

**Architecture:** New standalone `RobotViewerComponent` owns a Three.js scene on a `<canvas>` element. A signal `effect()` watches `joints` input and calls `updatePose()` each time new joint angles arrive from the WS. The component is embedded directly inside `SimControlComponent` above existing controls.

**Tech Stack:** Angular 19 Signals, Three.js (WebGLRenderer + Object3D hierarchy), OrbitControls from `three/addons/`

---

## File Map

| Action | Path |
|--------|------|
| Create | `src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts` |
| Modify | `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts` |
| Modify | `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts` |

---

## Task 1: Install Three.js

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
npm install three
npm install --save-dev @types/three
```

- [ ] **Step 2: Verify types resolve**

```bash
node -e "require('three'); console.log('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "chore: add three.js dependency"
```

---

## Task 2: Create RobotViewerComponent

**Files:**
- Create: `src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts`

- [ ] **Step 1: Create the component**

Create `src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts`:

```typescript
import {
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  afterNextRender,
  effect,
  input,
} from '@angular/core';
import {
  AmbientLight,
  CylinderGeometry,
  DirectionalLight,
  Mesh,
  MeshPhongMaterial,
  Object3D,
  PerspectiveCamera,
  Scene,
  SphereGeometry,
  Vector3,
  WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SimStatus } from '../../../../../core/sim-bridge/sim-bridge.service';

type JointName =
  | 'l_hip_yaw' | 'l_hip_roll' | 'l_hip_pitch' | 'l_knee' | 'l_ankle'
  | 'r_hip_yaw' | 'r_hip_roll' | 'r_hip_pitch' | 'r_knee' | 'r_ankle'
  | 'torso_yaw'
  | 'l_shoulder_pitch' | 'l_shoulder_roll' | 'l_shoulder_yaw' | 'l_elbow'
  | 'r_shoulder_pitch' | 'r_shoulder_roll' | 'r_shoulder_yaw' | 'r_elbow';

// ctrl index → [jointName, rotationAxis]
const POSE_MAP: [JointName, 'x' | 'y' | 'z'][] = [
  ['l_hip_yaw',        'y'],
  ['l_hip_roll',       'x'],
  ['l_hip_pitch',      'z'],
  ['l_knee',           'z'],
  ['l_ankle',          'z'],
  ['r_hip_yaw',        'y'],
  ['r_hip_roll',       'x'],
  ['r_hip_pitch',      'z'],
  ['r_knee',           'z'],
  ['r_ankle',          'z'],
  ['torso_yaw',        'y'],
  ['l_shoulder_pitch', 'z'],
  ['l_shoulder_roll',  'x'],
  ['l_shoulder_yaw',   'y'],
  ['l_elbow',          'z'],
  ['r_shoulder_pitch', 'z'],
  ['r_shoulder_roll',  'x'],
  ['r_shoulder_yaw',   'y'],
  ['r_elbow',          'z'],
];

@Component({
  selector: 'app-robot-viewer',
  standalone: true,
  template: `<canvas #canvas style="display:block;width:100%;height:220px;"></canvas>`,
})
export class RobotViewerComponent implements OnDestroy {
  @ViewChild('canvas', { static: true }) private canvasRef!: ElementRef<HTMLCanvasElement>;

  readonly joints = input<number[]>([]);
  readonly status = input<SimStatus>('disconnected');

  private renderer: WebGLRenderer | null = null;
  private rafId = 0;
  private readonly _joints = new Map<JointName, Object3D>();
  private _materials: MeshPhongMaterial[] = [];
  private resizeObserver: ResizeObserver | null = null;

  constructor() {
    afterNextRender(() => this.initThreeJs());

    effect(() => {
      const j = this.joints();
      if (j.length >= 19) this.updatePose(j);
    });

    effect(() => {
      const opacity = this.status() === 'disconnected' ? 0.3 : 1.0;
      for (const m of this._materials) m.opacity = opacity;
    });
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.rafId);
    this.resizeObserver?.disconnect();
    for (const m of this._materials) m.dispose();
    this.renderer?.dispose();
  }

  private initThreeJs(): void {
    const canvas = this.canvasRef.nativeElement;
    if (!canvas.getContext('webgl2') && !canvas.getContext('webgl')) return;

    const w = canvas.clientWidth  || 400;
    const h = canvas.clientHeight || 220;

    const renderer = new WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(devicePixelRatio);
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x0f172a);
    this.renderer = renderer;

    const scene = new Scene();

    const camera = new PerspectiveCamera(45, w / h, 0.01, 100);
    camera.position.set(0, 1.2, 2.5);
    camera.lookAt(0, 0.9, 0);

    scene.add(new AmbientLight(0xffffff, 0.6));
    const dir = new DirectionalLight(0xffffff, 0.8);
    dir.position.set(1, 3, 2);
    scene.add(dir);

    this.buildSkeleton(scene);

    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, 0.9, 0);
    controls.enablePan = false;
    controls.update();

    const loop = () => {
      this.rafId = requestAnimationFrame(loop);
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    this.resizeObserver = new ResizeObserver(() => {
      const nw = canvas.clientWidth;
      const nh = canvas.clientHeight;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh, false);
    });
    this.resizeObserver.observe(canvas);
  }

  private buildSkeleton(scene: Scene): void {
    const BONE_R  = 0.025;
    const JOINT_R = 0.035;
    const boneMat  = new MeshPhongMaterial({ color: 0x93c5fd, transparent: true });
    const jointMat = new MeshPhongMaterial({ color: 0x60a5fa, transparent: true });
    this._materials = [boneMat, jointMat];

    const mkNode = (name: JointName): Object3D => {
      const n = new Object3D();
      n.add(new Mesh(new SphereGeometry(JOINT_R, 8, 6), jointMat));
      this._joints.set(name, n);
      return n;
    };

    const addBone = (parent: Object3D, to: Vector3): void => {
      const len = to.length();
      const cyl = new Mesh(new CylinderGeometry(BONE_R, BONE_R, len, 8), boneMat);
      cyl.position.copy(to).multiplyScalar(0.5);
      cyl.quaternion.setFromUnitVectors(new Vector3(0, 1, 0), to.clone().normalize());
      parent.add(cyl);
    };

    // Root
    const pelvis = new Object3D();
    pelvis.position.set(0, 0.98, 0);
    pelvis.add(new Mesh(new SphereGeometry(0.05, 10, 8), jointMat));
    scene.add(pelvis);

    // ── Left leg ──────────────────────────────────────────
    const lHipY = mkNode('l_hip_yaw');   lHipY.position.set(-0.10, 0, 0); pelvis.add(lHipY);
    const lHipR = mkNode('l_hip_roll');  lHipR.position.set(0, 0, 0);     lHipY.add(lHipR);
    const lHipP = mkNode('l_hip_pitch'); lHipP.position.set(0, 0, 0);     lHipR.add(lHipP);
    addBone(lHipP, new Vector3(0, -0.40, 0));
    const lKnee = mkNode('l_knee');      lKnee.position.set(0, -0.40, 0); lHipP.add(lKnee);
    addBone(lKnee, new Vector3(0, -0.40, 0));
    const lAnkle = mkNode('l_ankle');    lAnkle.position.set(0, -0.40, 0); lKnee.add(lAnkle);
    addBone(lAnkle, new Vector3(0.06, -0.04, 0));

    // ── Right leg ─────────────────────────────────────────
    const rHipY = mkNode('r_hip_yaw');   rHipY.position.set(0.10, 0, 0);  pelvis.add(rHipY);
    const rHipR = mkNode('r_hip_roll');  rHipR.position.set(0, 0, 0);     rHipY.add(rHipR);
    const rHipP = mkNode('r_hip_pitch'); rHipP.position.set(0, 0, 0);     rHipR.add(rHipP);
    addBone(rHipP, new Vector3(0, -0.40, 0));
    const rKnee = mkNode('r_knee');      rKnee.position.set(0, -0.40, 0); rHipP.add(rKnee);
    addBone(rKnee, new Vector3(0, -0.40, 0));
    const rAnkle = mkNode('r_ankle');    rAnkle.position.set(0, -0.40, 0); rKnee.add(rAnkle);
    addBone(rAnkle, new Vector3(-0.06, -0.04, 0));

    // ── Spine ─────────────────────────────────────────────
    const torso = mkNode('torso_yaw');   torso.position.set(0, 0, 0);     pelvis.add(torso);
    addBone(torso, new Vector3(0, 0.40, 0));

    const shoulders = new Object3D();   shoulders.position.set(0, 0.40, 0); torso.add(shoulders);
    addBone(shoulders, new Vector3(0, 0.10, 0));
    const head = new Mesh(new SphereGeometry(0.08, 10, 8), boneMat);
    head.position.set(0, 0.18, 0);
    shoulders.add(head);

    // ── Left arm ──────────────────────────────────────────
    const lShP = mkNode('l_shoulder_pitch'); lShP.position.set(-0.20, 0, 0); shoulders.add(lShP);
    const lShR = mkNode('l_shoulder_roll');  lShR.position.set(0, 0, 0);     lShP.add(lShR);
    const lShY = mkNode('l_shoulder_yaw');   lShY.position.set(0, 0, 0);     lShR.add(lShY);
    addBone(lShY, new Vector3(-0.25, 0, 0));
    const lElbow = mkNode('l_elbow');        lElbow.position.set(-0.25, 0, 0); lShY.add(lElbow);
    addBone(lElbow, new Vector3(-0.22, 0, 0));

    // ── Right arm ─────────────────────────────────────────
    const rShP = mkNode('r_shoulder_pitch'); rShP.position.set(0.20, 0, 0);  shoulders.add(rShP);
    const rShR = mkNode('r_shoulder_roll');  rShR.position.set(0, 0, 0);     rShP.add(rShR);
    const rShY = mkNode('r_shoulder_yaw');   rShY.position.set(0, 0, 0);     rShR.add(rShY);
    addBone(rShY, new Vector3(0.25, 0, 0));
    const rElbow = mkNode('r_elbow');        rElbow.position.set(0.25, 0, 0); rShY.add(rElbow);
    addBone(rElbow, new Vector3(0.22, 0, 0));
  }

  private updatePose(joints: number[]): void {
    for (let i = 0; i < POSE_MAP.length; i++) {
      const [name, axis] = POSE_MAP[i];
      const node = this._joints.get(name);
      if (node) node.rotation[axis] = joints[i];
    }
  }
}
```

- [ ] **Step 2: Verify build**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
ng build --configuration development 2>&1 | tail -15
```

Expected: `Application bundle generation complete.` with no errors.

- [ ] **Step 3: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts
git commit -m "feat(sim): add RobotViewerComponent — Three.js H1 stick figure"
```

---

## Task 3: Integrate into SimControlComponent

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`
- Modify: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts`

- [ ] **Step 1: Update SimControlComponent**

In `sim-control.component.ts`:

1. Add `RobotViewerComponent` to `imports`:

```typescript
import { RobotViewerComponent } from './robot-viewer.component';
// ...
imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule, RobotViewerComponent],
```

2. Add `<app-robot-viewer>` as first child inside `.sim`, before the header:

```html
<div class="sim">
  <app-robot-viewer
    [joints]="bridge.joints()"
    [status]="status()">
  </app-robot-viewer>

  <div class="sim__header">
    ...
```

3. Add canvas container style (so the viewer card doesn't overflow):

```scss
app-robot-viewer { display: block; margin: -16px -20px 12px; border-radius: 12px 12px 0 0; overflow: hidden; }
```

- [ ] **Step 2: Update SimControlComponent spec**

The spec's `makeBridgeSpy` is missing `joints` and `launching`. Update it so the component doesn't throw when `RobotViewerComponent` is included:

```typescript
function makeBridgeSpy() {
  return {
    status:         signal<any>('disconnected'),
    tick:           signal(0),
    totalTicks:     signal(0),
    currentEegTick: signal(null),
    joints:         signal<number[]>([]),
    launching:      signal(false),
    isCloudSim:     false,
    connect: jasmine.createSpy('connect'),
    pause:   jasmine.createSpy('pause'),
    resume:  jasmine.createSpy('resume'),
    stop:    jasmine.createSpy('stop'),
  };
}
```

Also add `NO_ERRORS_SCHEMA` from `@angular/core/testing` to stop Karma from complaining about the canvas / WebGL context in test env:

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NO_ERRORS_SCHEMA } from '@angular/core';
// ...
await TestBed.configureTestingModule({
  imports: [SimControlComponent],
  providers: [{ provide: SimBridgeService, useValue: bridge }],
  schemas: [NO_ERRORS_SCHEMA],
}).compileComponents();
```

- [ ] **Step 3: Verify build**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
ng build --configuration development 2>&1 | tail -15
```

Expected: `Application bundle generation complete.` with no errors.

- [ ] **Step 4: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts \
        src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts
git commit -m "feat(sim): embed RobotViewerComponent in SimControlComponent card"
```

---

## Task 4: Visual Verification

**Files:** none (manual test)

- [ ] **Step 1: Start dev server**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
npm start
```

Navigate to `http://localhost:4200/dashboard`.

- [ ] **Step 2: Check idle state**

Expected: dark navy canvas (220px) at top of Sim card, light-blue H1 stick figure visible in standing pose. Status dot amber/disconnected → skeleton dimmed to ~30% opacity.

- [ ] **Step 3: Connect and play demo**

Click **Connect** (prod env) or run sim locally. Once status reaches `idle` (green dot), click **Play Demo**.

Expected: skeleton animates — arms and legs shift as EEG-modulated ctrl values update. Progress bar below advances.

- [ ] **Step 4: Verify rotation drag**

Click and drag on the canvas. Expected: orbit controls let you rotate the view around the skeleton.

- [ ] **Step 5: Note axis tuning**

If joints rotate on wrong axes (e.g., knee bending sideways instead of forward), update the axis entry in `POSE_MAP` in `robot-viewer.component.ts`. The mapping is:

```typescript
// entry format: [jointName, 'x' | 'y' | 'z']
// yaw joints  → 'y'  (rotation around vertical)
// roll joints → 'x'  (lateral tilt)
// pitch/knee/ankle/elbow → 'z'  (forward/back flex) — adjust if wrong
```

Change `'z'` ↔ `'x'` for pitch-like joints if they bend in wrong plane. No rebuild step — `ng serve` hot-reloads.

- [ ] **Step 6: Commit any axis fixes**

```bash
git add src/app/shared/components/layout/dashboard-layout/widgets/robot-viewer.component.ts
git commit -m "fix(sim): tune H1 joint rotation axes after visual inspection"
```

---

## Task 5: Push

- [ ] **Step 1: Push to origin**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
git push origin master
```
