import {
  Component, ElementRef, OnDestroy, ViewChild, afterNextRender, inject,
} from '@angular/core';
import {
  AmbientLight, BoxGeometry, Color, CylinderGeometry, DirectionalLight,
  FogExp2, GridHelper, Mesh, MeshPhongMaterial, Object3D, PerspectiveCamera,
  PlaneGeometry, Scene, SphereGeometry, WebGLRenderer,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { DemoEegService } from './demo-eeg.service';
import { DemoMotionService, MotionFrame } from './demo-motion.service';
import { EegPanelComponent } from './eeg-panel.component';

@Component({
  selector: 'app-demo',
  standalone: true,
  imports: [EegPanelComponent],
  template: `
    <div class="demo-wrap">
      <canvas #canvas></canvas>

      <div class="title-badge">Handwerk Capture Platform</div>

      <div class="rec-badge">
        <span class="rec-dot"></span>
        REC&nbsp;&nbsp;SESSION_001
      </div>

      <app-eeg-panel
        [dotColor]="dotColor"
        [focusPct]="focusPct"
        [calmPct]="calmPct"
        [focusVal]="focusVal"
        [calmVal]="calmVal"
      />
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; height: calc(100vh - 104px); background: #0f172a; overflow: hidden; border-radius: 12px; }

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
  private paintScene: Scene | null = null;
  private lastPaintX = -99;
  
  // Left arm joints
  private shoulderPan_L!: Object3D;
  private shoulderTilt_L!: Object3D;
  private elbowPivot_L!: Object3D;
  private wristPivot_L!: Object3D;
  private fingerProximal_L: Object3D[] = [];
  private fingerMedial_L: Object3D[] = [];
  private lastPaintX_L = -99;
  private dabMaterials: MeshPhongMaterial[] = [];

  // Center arm joints
  private shoulderPan_C!: Object3D;
  private shoulderTilt_C!: Object3D;
  private elbowPivot_C!: Object3D;
  private wristPivot_C!: Object3D;
  private fingerProximal_C: Object3D[] = [];
  private fingerMedial_C: Object3D[] = [];

  constructor() {
    afterNextRender(() => this.initScene());
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.rafId);
    clearInterval(this.overlayInterval);
    this.resizeObserver?.disconnect();
    this.armMaterial?.dispose();
    this.dabMaterials.forEach(m => m.dispose());
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
    const camera = new PerspectiveCamera(50, w / h, 0.01, 50);
    camera.position.set(0, 1.0, 2.2);
    camera.lookAt(0, 0.45, -0.2);

    scene.add(new AmbientLight(0xffffff, 0.5));
    const key = new DirectionalLight(0xffffff, 0.8);
    key.position.set(1, 2, 1.5);
    scene.add(key);
    const fill = new DirectionalLight(0xffffff, 0.4);
    fill.position.set(-1, 0.5, 0.5);
    scene.add(fill);

    this.buildSkeleton(scene);
    this.buildSkeletonLeft(scene);
    this.buildSkeletonCenter(scene);
    this.buildWall(scene);
    this.buildBackground(scene);

    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, 0.45, -0.25);
    controls.enablePan = false;
    controls.update();

    this.paintScene = scene;

    this.lastTime = performance.now();
    const loop = (now: number) => {
      this.rafId = requestAnimationFrame(loop);
      const dt = now - this.lastTime;
      this.lastTime = now;
      this.eeg.tick(dt);
      const frameR = this.motion.tickRight(dt, this.eeg.focus());
      this.applyPose(frameR);
      const frameL = this.motion.tickLeft(dt, this.eeg.focus());
      this.applyPoseLeft(frameL);
      this.updateArmColor(this.eeg.focus());
      controls.update();
      renderer.render(scene, camera);
      
      // Add paint dab if needed
      const tip = this.motion.currentToolTip(frameR);
      this.addPaintDab(tip[0], tip[1], tip[2], this.eeg.focus());
      
      // Add left arm paint dab if needed
      const tipL = this.motion.currentToolTipLeft(frameL);
      this.addPaintDabLeft(tipL[0], tipL[1], tipL[2], this.eeg.focus());

      const frameC = this.motion.tickCenter(dt, this.eeg.focus());
      this.applyPoseCenter(frameC);
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

  private dabColor(focus: number): number {
    if (focus <= 0.4)  return 0x93c5fd;  // blue
    if (focus <= 0.65) {
      const t = (focus - 0.4) / 0.25;
      // lerp blue→amber in hex: interpolate r/g/b
      const r = Math.round(0x93 + t * (0xf5 - 0x93));
      const g = Math.round(0xc5 + t * (0x9e - 0xc5));
      const b = Math.round(0xfd + t * (0x0b - 0xfd));
      return (r << 16) | (g << 8) | b;
    }
    const t = Math.min(1, (focus - 0.65) / 0.2);
    const r = Math.round(0xf5 + t * (0xef - 0xf5));
    const g = Math.round(0x9e + t * (0x44 - 0x9e));
    const b = Math.round(0x0b + t * (0x44 - 0x0b));
    return (r << 16) | (g << 8) | b;
  }

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
    base.position.set(0.55, 0.25, 0);
    scene.add(base);

    // Shoulder (pan around Y, tilt around X)
    const shoulderPan = new Object3D();
    shoulderPan.position.set(0.55, 0.50, 0);
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
      new BoxGeometry(0.08, 0.03, 0.10), mat
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

  private buildSkeletonLeft(scene: Scene): void {
    const BONE_R  = 0.022;
    const JOINT_R = 0.032;

    const sphere = () => new Mesh(new SphereGeometry(JOINT_R, 10, 8), this.armMaterial);
    const bone = (len: number) => {
      const cyl = new Mesh(new CylinderGeometry(BONE_R, BONE_R, len, 10), this.armMaterial);
      cyl.rotation.x = Math.PI / 2;   // align cylinder to Z axis
      cyl.position.z = -len / 2;
      return cyl;
    };
    const node = (): Object3D => { const n = new Object3D(); n.add(sphere()); return n; };

    // Base pedestal for left arm (offset to avoid overlap)
    const base = new Mesh(new CylinderGeometry(0.05, 0.07, 0.5, 16), this.armMaterial);
    base.position.set(-0.55, 0.25, 0);
    scene.add(base);

    // Shoulder (pan around Y, tilt around X)
    const shoulderPan = new Object3D();
    shoulderPan.position.set(-0.55, 0.50, 0);
    scene.add(shoulderPan);
    this.shoulderPan_L = shoulderPan;

    const shoulderTilt = node();
    shoulderPan.add(shoulderTilt);
    this.shoulderTilt_L = shoulderTilt;

    // Upper arm
    const L1 = 0.35;
    shoulderTilt.add(bone(L1));

    // Elbow
    const elbowPivot = node();
    elbowPivot.position.z = -L1;
    shoulderTilt.add(elbowPivot);
    this.elbowPivot_L = elbowPivot;

    // Forearm
    const L2 = 0.30;
    elbowPivot.add(bone(L2));

    // Wrist
    const wristPivot = node();
    wristPivot.position.z = -L2;
    elbowPivot.add(wristPivot);
    this.wristPivot_L = wristPivot;

    // Palm
    const palm = new Mesh(
      new BoxGeometry(0.08, 0.03, 0.10), this.armMaterial
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
      this.fingerProximal_L.push(proximal);

      // Medial phalange (follow curl at half angle)
      const medial = new Object3D();
      medial.position.z = -PX_LEN;
      proximal.add(medial);
      medial.add(sphere());
      medial.add(bone(DI_LEN));
      this.fingerMedial_L.push(medial);
    }
  }

  private buildWall(scene: Scene): void {
    const wallMat = new MeshPhongMaterial({
      color: 0x334155, emissive: 0x1e293b, side: 2,
    });
    const wall = new Mesh(new PlaneGeometry(1.2, 0.6), wallMat);
    wall.position.set(0, 0.45, -0.44);
    // PlaneGeometry faces +Z; rotate Math.PI so it faces the camera at +Z
    wall.rotation.y = Math.PI;
    scene.add(wall);
  }

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

  private applyPoseLeft(frame: MotionFrame): void {
    if (!this.shoulderPan_L) return;

    this.shoulderPan_L.rotation.y  = frame.shoulderPan;
    this.shoulderTilt_L.rotation.x = -frame.shoulderTilt;
    this.elbowPivot_L.rotation.x   = frame.elbowAngle;
    this.wristPivot_L.rotation.x   = frame.wristAngle;

    const curl = frame.fingerCurl;
    for (let i = 0; i < 5; i++) {
      if (this.fingerProximal_L[i]) this.fingerProximal_L[i].rotation.x = curl;
      if (this.fingerMedial_L[i])   this.fingerMedial_L[i].rotation.x   = curl * 0.6;
    }
  }

  private addPaintDab(x: number, y: number, _z: number, focus: number): void {
    if (!this.paintScene) return;
    if (Math.abs(x - this.lastPaintX) < 0.03) return;
    this.lastPaintX = x;

    const color = this.dabColor(focus);
    const mat = new MeshPhongMaterial({ color, emissive: color, emissiveIntensity: 0.3 });
    this.dabMaterials.push(mat);
    const dab = new Mesh(new PlaneGeometry(0.04, 0.015), mat);
    dab.position.set(x, y, -0.435);
    dab.rotation.y = Math.PI;
    this.paintScene.add(dab);
  }

  private addPaintDabLeft(x: number, y: number, _z: number, focus: number): void {
    if (!this.paintScene) return;
    if (Math.abs(x - this.lastPaintX_L) < 0.03) return;
    this.lastPaintX_L = x;

    const color = this.dabColor(focus);
    const mat = new MeshPhongMaterial({ color, emissive: color, emissiveIntensity: 0.3 });
    this.dabMaterials.push(mat);
    const dab = new Mesh(new PlaneGeometry(0.04, 0.015), mat);
    dab.position.set(x, y, -0.435);
    dab.rotation.y = Math.PI;
    this.paintScene.add(dab);
  }

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
    const THUMB_ANGLE   = -0.5;
    const MC_LEN = 0.025;
    const PX_LEN = 0.030;
    const DI_LEN = 0.022;

    for (let i = 0; i < 5; i++) {
      const isThumb = i === 0;
      const xOff = isThumb ? -0.035 : FINGER_SPREAD[i - 1] - 0.01;
      const baseZ = isThumb ? -0.04 : -0.11;

      const mc = new Object3D();
      mc.position.set(xOff, 0, baseZ);
      if (isThumb) mc.rotation.y = THUMB_ANGLE;
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

  private buildBackground(scene: Scene): void {
    scene.fog = new FogExp2(0x0f172a, 0.35);
    const grid = new GridHelper(6, 24, 0x1e3a5f, 0x1e293b);
    grid.position.y = 0;
    scene.add(grid);
  }
}