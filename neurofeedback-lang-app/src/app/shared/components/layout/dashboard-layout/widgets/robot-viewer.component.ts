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

const POSE_MAP: [JointName, 'x' | 'y' | 'z'][] = [
  ['l_hip_yaw',        'y'], ['l_hip_roll',       'x'], ['l_hip_pitch',      'z'],
  ['l_knee',           'z'], ['l_ankle',           'z'],
  ['r_hip_yaw',        'y'], ['r_hip_roll',        'x'], ['r_hip_pitch',      'z'],
  ['r_knee',           'z'], ['r_ankle',           'z'],
  ['torso_yaw',        'y'],
  ['l_shoulder_pitch', 'z'], ['l_shoulder_roll',   'x'], ['l_shoulder_yaw',   'y'], ['l_elbow', 'z'],
  ['r_shoulder_pitch', 'z'], ['r_shoulder_roll',   'x'], ['r_shoulder_yaw',   'y'], ['r_elbow', 'z'],
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

    const pelvis = new Object3D();
    pelvis.position.set(0, 0.98, 0);
    pelvis.add(new Mesh(new SphereGeometry(0.05, 10, 8), jointMat));
    scene.add(pelvis);

    // Left leg
    const lHipY = mkNode('l_hip_yaw');   lHipY.position.set(-0.10, 0, 0); pelvis.add(lHipY);
    const lHipR = mkNode('l_hip_roll');  lHipR.position.set(0, 0, 0);     lHipY.add(lHipR);
    const lHipP = mkNode('l_hip_pitch'); lHipP.position.set(0, 0, 0);     lHipR.add(lHipP);
    addBone(lHipP, new Vector3(0, -0.40, 0));
    const lKnee  = mkNode('l_knee');     lKnee.position.set(0, -0.40, 0); lHipP.add(lKnee);
    addBone(lKnee, new Vector3(0, -0.40, 0));
    const lAnkle = mkNode('l_ankle');    lAnkle.position.set(0, -0.40, 0); lKnee.add(lAnkle);
    addBone(lAnkle, new Vector3(0.06, -0.04, 0));

    // Right leg
    const rHipY = mkNode('r_hip_yaw');   rHipY.position.set(0.10, 0, 0);  pelvis.add(rHipY);
    const rHipR = mkNode('r_hip_roll');  rHipR.position.set(0, 0, 0);     rHipY.add(rHipR);
    const rHipP = mkNode('r_hip_pitch'); rHipP.position.set(0, 0, 0);     rHipR.add(rHipP);
    addBone(rHipP, new Vector3(0, -0.40, 0));
    const rKnee  = mkNode('r_knee');     rKnee.position.set(0, -0.40, 0); rHipP.add(rKnee);
    addBone(rKnee, new Vector3(0, -0.40, 0));
    const rAnkle = mkNode('r_ankle');    rAnkle.position.set(0, -0.40, 0); rKnee.add(rAnkle);
    addBone(rAnkle, new Vector3(-0.06, -0.04, 0));

    // Spine
    const torso = mkNode('torso_yaw');   torso.position.set(0, 0, 0); pelvis.add(torso);
    addBone(torso, new Vector3(0, 0.40, 0));

    const shoulders = new Object3D(); shoulders.position.set(0, 0.40, 0); torso.add(shoulders);
    addBone(shoulders, new Vector3(0, 0.10, 0));
    const head = new Mesh(new SphereGeometry(0.08, 10, 8), boneMat);
    head.position.set(0, 0.18, 0);
    shoulders.add(head);

    // Left arm
    const lShP   = mkNode('l_shoulder_pitch'); lShP.position.set(-0.20, 0, 0);  shoulders.add(lShP);
    const lShR   = mkNode('l_shoulder_roll');  lShR.position.set(0, 0, 0);     lShP.add(lShR);
    const lShY   = mkNode('l_shoulder_yaw');   lShY.position.set(0, 0, 0);     lShR.add(lShY);
    addBone(lShY, new Vector3(-0.25, 0, 0));   
    const lElbow = mkNode('l_elbow');           lElbow.position.set(-0.25, 0, 0); lShY.add(lElbow);
    addBone(lElbow, new Vector3(-0.22, 0, 0));  
      
    // Right arm
    const rShP   = mkNode('r_shoulder_pitch'); rShP.position.set(0.20, 0, 0);  shoulders.add(rShP);
    const rShR   = mkNode('r_shoulder_roll');  rShR.position.set(0, 0, 0);     rShP.add(rShR);
    const rShY   = mkNode('r_shoulder_yaw');   rShY.position.set(0, 0, 0);     rShR.add(rShY);
    addBone(rShY, new Vector3(0.25, 0, 0));
    const rElbow = mkNode('r_elbow');           rElbow.position.set(0.25, 0, 0); rShY.add(rElbow);
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