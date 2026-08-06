import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { JointState, CartesianPos } from '../types';
import { forwardKinematics, ARM_L1, ARM_L2, ARM_L3, ARM_L4 } from '../utils/kinematics';
import { Maximize2, RotateCcw, Eye, Layers, Compass, Box } from 'lucide-react';

interface Arm3DCanvasProps {
  joints: JointState;
  showTrajectory?: boolean;
  trajectoryPoints?: CartesianPos[];
}

export const Arm3DCanvas: React.FC<Arm3DCanvasProps> = ({
  joints,
  showTrajectory = true,
  trajectoryPoints = []
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  // Mesh refs for articulation
  const basePivotRef = useRef<THREE.Group | null>(null);
  const shoulderPivotRef = useRef<THREE.Group | null>(null);
  const elbowPivotRef = useRef<THREE.Group | null>(null);
  const wristPitchPivotRef = useRef<THREE.Group | null>(null);
  const wristRollPivotRef = useRef<THREE.Group | null>(null);
  const leftClawRef = useRef<THREE.Mesh | null>(null);
  const rightClawRef = useRef<THREE.Mesh | null>(null);
  const targetMeshRef = useRef<THREE.Mesh | null>(null);
  const trajectoryLineRef = useRef<THREE.Line | null>(null);
  const renderFrameRef = useRef<number | null>(null);
  const requestRenderRef = useRef<() => void>(() => {});

  // Orbit state
  const isDraggingRef = useRef(false);
  const previousMousePositionRef = useRef({ x: 0, y: 0 });
  const cameraAngleRef = useRef({ alpha: Math.PI / 4, beta: Math.PI / 6, distance: 450 });

  const [cameraMode, setCameraMode] = useState<'perspective' | 'top' | 'side' | 'front'>('perspective');
  const cameraModeRef = useRef(cameraMode);
  const [showGrid, setShowGrid] = useState(true);
  const [showReachDome, setShowReachDome] = useState(false);

  // Calculated End Effector Pos
  const endPos = forwardKinematics(joints);

  // Initialize Three.js Scene
  useEffect(() => {
    if (!mountRef.current) return;
    const container = mountRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight || 450;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x09090b); // Zinc-950 background
    scene.fog = new THREE.FogExp2(0x09090b, 0.0015);
    sceneRef.current = scene;

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 1, 2000);
    cameraRef.current = camera;
    updateCameraPosition();

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    rendererRef.current = renderer;

    // Clear container and append
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // 4. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(200, 400, 200);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 1024;
    dirLight.shadow.mapSize.height = 1024;
    dirLight.shadow.camera.near = 10;
    dirLight.shadow.camera.far = 1000;
    dirLight.shadow.camera.left = -300;
    dirLight.shadow.camera.right = -300;
    dirLight.shadow.camera.top = 300;
    dirLight.shadow.camera.bottom = -300;
    scene.add(dirLight);

    const blueSpot = new THREE.SpotLight(0x3b82f6, 1.5);
    blueSpot.position.set(-200, 300, -200);
    scene.add(blueSpot);

    // 5. Grid Floor & Coordinates
    const grid = new THREE.GridHelper(600, 30, 0x3b82f6, 0x334155);
    grid.position.y = 0;
    grid.name = 'grid';
    scene.add(grid);

    // Workspace Floor plane
    const floorGeo = new THREE.PlaneGeometry(600, 600);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.8,
      metalness: 0.2
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // Reach Dome hemisphere
    const domeGeo = new THREE.SphereGeometry(ARM_L2 + ARM_L3 + ARM_L4, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2);
    const domeMat = new THREE.MeshBasicMaterial({
      color: 0x3b82f6,
      wireframe: true,
      transparent: true,
      opacity: 0.12
    });
    const dome = new THREE.Mesh(domeGeo, domeMat);
    dome.position.y = ARM_L1;
    dome.name = 'reachDome';
    dome.visible = showReachDome;
    scene.add(dome);

    // 6. Build Robot Arm Articulated Mesh Hierarchy
    const materials = {
      baseMat: new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4, metalness: 0.6 }),
      bracketMat: new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.3, metalness: 0.5 }), // SO-ARM Cyan
      jointMat: new THREE.MeshStandardMaterial({ color: 0xf97316, roughness: 0.3, metalness: 0.4 }),   // Servo Accent Orange
      metalMat: new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.2, metalness: 0.8 }),
      clawMat: new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.3, metalness: 0.7 })
    };

    // Root Assembly Group
    const armGroup = new THREE.Group();
    scene.add(armGroup);

    // Base Stand (Fixed)
    const baseGeo = new THREE.CylinderGeometry(45, 55, 25, 32);
    const baseMesh = new THREE.Mesh(baseGeo, materials.baseMat);
    baseMesh.position.y = 12.5;
    baseMesh.castShadow = true;
    baseMesh.receiveShadow = true;
    armGroup.add(baseMesh);

    // Servo 1 Accent ring
    const s1Ring = new THREE.Mesh(new THREE.CylinderGeometry(40, 40, 6, 32), materials.jointMat);
    s1Ring.position.y = 28;
    armGroup.add(s1Ring);

    // --- BASE YAW PIVOT (S1) ---
    const basePivot = new THREE.Group();
    basePivot.position.y = ARM_L1; // ~105mm up
    armGroup.add(basePivot);
    basePivotRef.current = basePivot;

    // Shoulder Bracket Body
    const shoulderBracketGeo = new THREE.BoxGeometry(45, 40, 40);
    const shoulderBracket = new THREE.Mesh(shoulderBracketGeo, materials.bracketMat);
    shoulderBracket.castShadow = true;
    basePivot.add(shoulderBracket);

    // --- SHOULDER PITCH PIVOT (S2) ---
    const shoulderPivot = new THREE.Group();
    basePivot.add(shoulderPivot);
    shoulderPivotRef.current = shoulderPivot;

    // Shoulder Servo Hub
    const s2Hub = new THREE.Mesh(new THREE.CylinderGeometry(18, 18, 38, 24), materials.jointMat);
    s2Hub.rotation.z = Math.PI / 2;
    shoulderPivot.add(s2Hub);

    // Link 2 (Upper Arm)
    const link2Mesh = new THREE.Mesh(new THREE.BoxGeometry(20, ARM_L2, 28), materials.bracketMat);
    link2Mesh.position.y = ARM_L2 / 2;
    link2Mesh.castShadow = true;
    shoulderPivot.add(link2Mesh);

    // Carbon fiber accent bar on Link 2
    const rod2 = new THREE.Mesh(new THREE.CylinderGeometry(4, 4, ARM_L2 - 10, 16), materials.metalMat);
    rod2.position.y = ARM_L2 / 2;
    rod2.position.z = 16;
    shoulderPivot.add(rod2);

    // --- ELBOW PITCH PIVOT (S3) ---
    const elbowPivot = new THREE.Group();
    elbowPivot.position.y = ARM_L2;
    shoulderPivot.add(elbowPivot);
    elbowPivotRef.current = elbowPivot;

    // S3 Servo Hub
    const s3Hub = new THREE.Mesh(new THREE.CylinderGeometry(16, 16, 34, 24), materials.jointMat);
    s3Hub.rotation.z = Math.PI / 2;
    elbowPivot.add(s3Hub);

    // Link 3 (Forearm)
    const link3Mesh = new THREE.Mesh(new THREE.BoxGeometry(18, ARM_L3, 24), materials.bracketMat);
    link3Mesh.position.y = ARM_L3 / 2;
    link3Mesh.castShadow = true;
    elbowPivot.add(link3Mesh);

    // --- WRIST PITCH PIVOT (S4) ---
    const wristPitchPivot = new THREE.Group();
    wristPitchPivot.position.y = ARM_L3;
    elbowPivot.add(wristPitchPivot);
    wristPitchPivotRef.current = wristPitchPivot;

    const s4Hub = new THREE.Mesh(new THREE.CylinderGeometry(14, 14, 30, 20), materials.jointMat);
    s4Hub.rotation.z = Math.PI / 2;
    wristPitchPivot.add(s4Hub);

    // --- WRIST ROLL PIVOT (S5) ---
    const wristRollPivot = new THREE.Group();
    wristRollPivot.position.y = 15;
    wristPitchPivot.add(wristRollPivot);
    wristRollPivotRef.current = wristRollPivot;

    const s5Cyl = new THREE.Mesh(new THREE.CylinderGeometry(14, 14, 35, 24), materials.metalMat);
    s5Cyl.position.y = 17.5;
    s5Cyl.castShadow = true;
    wristRollPivot.add(s5Cyl);

    // --- GRIPPER END EFFECTOR (S6) ---
    const gripperBase = new THREE.Mesh(new THREE.BoxGeometry(38, 12, 25), materials.bracketMat);
    gripperBase.position.y = 35;
    gripperBase.castShadow = true;
    wristRollPivot.add(gripperBase);

    // Left & Right Claw Fingers
    const clawShapeGeo = new THREE.BoxGeometry(8, ARM_L4 - 35, 12);
    
    const leftClaw = new THREE.Mesh(clawShapeGeo, materials.clawMat);
    leftClaw.position.set(-10, 35 + (ARM_L4 - 35) / 2, 0);
    leftClaw.castShadow = true;
    wristRollPivot.add(leftClaw);
    leftClawRef.current = leftClaw;

    const rightClaw = new THREE.Mesh(clawShapeGeo, materials.clawMat);
    rightClaw.position.set(10, 35 + (ARM_L4 - 35) / 2, 0);
    rightClaw.castShadow = true;
    wristRollPivot.add(rightClaw);
    rightClawRef.current = rightClaw;

    // Target Payload Box on table
    const targetGeo = new THREE.BoxGeometry(24, 24, 24);
    const targetMat = new THREE.MeshStandardMaterial({
      color: 0xef4444, // Red target block
      roughness: 0.3,
      metalness: 0.3,
      emissive: 0x7f1d1d,
      emissiveIntensity: 0.3
    });
    const targetMesh = new THREE.Mesh(targetGeo, targetMat);
    targetMesh.position.set(140, 12, 0);
    targetMesh.castShadow = true;
    targetMesh.receiveShadow = true;
    scene.add(targetMesh);
    targetMeshRef.current = targetMesh;

    // Mouse Controls Setup
    const handleMouseDown = (e: MouseEvent) => {
      isDraggingRef.current = true;
      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const deltaX = e.clientX - previousMousePositionRef.current.x;
      const deltaY = e.clientY - previousMousePositionRef.current.y;

      cameraAngleRef.current.alpha -= deltaX * 0.008;
      cameraAngleRef.current.beta = Math.max(0.05, Math.min(Math.PI / 2 - 0.02, cameraAngleRef.current.beta + deltaY * 0.008));

      previousMousePositionRef.current = { x: e.clientX, y: e.clientY };
      updateCameraPosition();
      requestRenderRef.current();
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
    };

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      cameraAngleRef.current.distance = Math.max(150, Math.min(900, cameraAngleRef.current.distance + e.deltaY * 0.5));
      updateCameraPosition();
      requestRenderRef.current();
    };

    container.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    container.addEventListener('wheel', handleWheel, { passive: false });

    // 7. Render only after a scene change instead of continuously at 60 FPS.
    const render = () => {
      renderFrameRef.current = null;
      if (rendererRef.current && sceneRef.current && cameraRef.current) {
        rendererRef.current.render(sceneRef.current, cameraRef.current);
      }
    };
    const requestRender = () => {
      if (renderFrameRef.current === null) {
        renderFrameRef.current = requestAnimationFrame(render);
      }
    };
    requestRenderRef.current = requestRender;
    requestRender();

    // 8. Handle Window Resize
    const handleResize = () => {
      if (!mountRef.current || !rendererRef.current || !cameraRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight || 450;
      cameraRef.current.aspect = w / h;
      cameraRef.current.updateProjectionMatrix();
      rendererRef.current.setSize(w, h);
      requestRender();
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      if (renderFrameRef.current !== null) {
        cancelAnimationFrame(renderFrameRef.current);
      }
      renderFrameRef.current = null;
      requestRenderRef.current = () => {};
      resizeObserver.disconnect();
      container.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      container.removeEventListener('wheel', handleWheel);
      if (trajectoryLineRef.current) {
        trajectoryLineRef.current.geometry.dispose();
        (trajectoryLineRef.current.material as THREE.Material).dispose();
      }
      if (rendererRef.current && rendererRef.current.domElement) {
        rendererRef.current.dispose();
      }
    };
  }, []);

  // Update Orbit Camera Position based on cameraMode or drag angles
  const updateCameraPosition = () => {
    if (!cameraRef.current) return;
    const { alpha, beta, distance } = cameraAngleRef.current;

    if (cameraModeRef.current === 'top') {
      cameraRef.current.position.set(0, distance, 1);
      cameraRef.current.lookAt(0, 80, 0);
    } else if (cameraModeRef.current === 'side') {
      cameraRef.current.position.set(distance, 120, 0);
      cameraRef.current.lookAt(0, 100, 0);
    } else if (cameraModeRef.current === 'front') {
      cameraRef.current.position.set(0, 120, distance);
      cameraRef.current.lookAt(0, 100, 0);
    } else {
      const x = distance * Math.sin(beta) * Math.cos(alpha);
      const y = distance * Math.cos(beta);
      const z = distance * Math.sin(beta) * Math.sin(alpha);
      cameraRef.current.position.set(x, y, z);
      cameraRef.current.lookAt(0, 100, 0);
    }
  };

  useEffect(() => {
    cameraModeRef.current = cameraMode;
    updateCameraPosition();
    requestRenderRef.current();
  }, [cameraMode]);

  // Update Joint Rotations in Three.js Scene whenever `joints` prop changes
  useEffect(() => {
    const DEG2RAD = Math.PI / 180;

    if (basePivotRef.current) {
      basePivotRef.current.rotation.y = joints.base * DEG2RAD;
    }
    if (shoulderPivotRef.current) {
      shoulderPivotRef.current.rotation.z = -joints.shoulder * DEG2RAD;
    }
    if (elbowPivotRef.current) {
      elbowPivotRef.current.rotation.z = -joints.elbow * DEG2RAD;
    }
    if (wristPitchPivotRef.current) {
      wristPitchPivotRef.current.rotation.z = -joints.wristPitch * DEG2RAD;
    }
    if (wristRollPivotRef.current) {
      wristRollPivotRef.current.rotation.y = joints.wristRoll * DEG2RAD;
    }

    // Animate Claw Aperture (0% = 4mm apart, 100% = 24mm apart)
    if (leftClawRef.current && rightClawRef.current) {
      const apertureOffset = 4 + (joints.gripper / 100) * 16;
      leftClawRef.current.position.x = -apertureOffset;
      rightClawRef.current.position.x = apertureOffset;
    }

    // Update Reach Dome visibility
    if (sceneRef.current) {
      const dome = sceneRef.current.getObjectByName('reachDome');
      if (dome) dome.visible = showReachDome;
      const grid = sceneRef.current.getObjectByName('grid');
      if (grid) grid.visible = showGrid;
    }
    requestRenderRef.current();
  }, [joints, showReachDome, showGrid]);

  // Trajectory Line Overlay
  useEffect(() => {
    if (!sceneRef.current) return;

    if (trajectoryLineRef.current) {
      sceneRef.current.remove(trajectoryLineRef.current);
      trajectoryLineRef.current.geometry.dispose();
      (trajectoryLineRef.current.material as THREE.Material).dispose();
      trajectoryLineRef.current = null;
    }

    if (showTrajectory && trajectoryPoints.length > 1) {
      const points = trajectoryPoints.map(p => new THREE.Vector3(p.x, p.z, p.y));
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineDashedMaterial({
        color: 0x38bdf8,
        dashSize: 10,
        gapSize: 5,
        linewidth: 2
      });
      const line = new THREE.Line(geometry, material);
      line.computeLineDistances();
      sceneRef.current.add(line);
      trajectoryLineRef.current = line;
    }
    requestRenderRef.current();
  }, [showTrajectory, trajectoryPoints]);

  const resetCamera = () => {
    cameraAngleRef.current = { alpha: Math.PI / 4, beta: Math.PI / 6, distance: 450 };
    setCameraMode('perspective');
    updateCameraPosition();
    requestRenderRef.current();
  };

  return (
    <div className="relative w-full h-[460px] bg-zinc-950 rounded-sm overflow-hidden border border-zinc-800 shadow-2xl flex flex-col">
      {/* Top Header Overlay Bar */}
      <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-2.5 bg-zinc-900/90 backdrop-blur-md px-3.5 py-1.5 rounded-sm border border-zinc-700/80 shadow-lg pointer-events-auto">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs font-black tracking-wider text-white uppercase italic">
            3D DIGITAL TWIN (SO-ARM100)
          </span>
        </div>

        {/* Viewport Action Controls */}
        <div className="flex items-center gap-1.5 bg-zinc-900/90 backdrop-blur-md p-1 rounded-sm border border-zinc-700/80 shadow-lg pointer-events-auto">
          <button
            onClick={() => setCameraMode(cameraMode === 'perspective' ? 'top' : cameraMode === 'top' ? 'side' : cameraMode === 'side' ? 'front' : 'perspective')}
            className="px-2.5 py-1 text-xs font-bold text-zinc-300 hover:text-white hover:bg-zinc-800 rounded-sm transition flex items-center gap-1 uppercase tracking-tight"
            title="Cycle View Camera"
          >
            <Eye className="w-3.5 h-3.5 text-amber-400" />
            <span className="capitalize">{cameraMode}</span>
          </button>

          <button
            onClick={() => setShowGrid(!showGrid)}
            className={`px-2 py-1 text-xs font-bold uppercase tracking-tight rounded-sm transition flex items-center gap-1 ${
              showGrid ? 'bg-amber-400 text-zinc-950' : 'text-zinc-400 hover:bg-zinc-800'
            }`}
            title="Toggle Floor Grid"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Grid</span>
          </button>

          <button
            onClick={() => setShowReachDome(!showReachDome)}
            className={`px-2 py-1 text-xs font-bold uppercase tracking-tight rounded-sm transition flex items-center gap-1 ${
              showReachDome ? 'bg-amber-400 text-zinc-950' : 'text-zinc-400 hover:bg-zinc-800'
            }`}
            title="Toggle Workspace Reach Envelope"
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Reach</span>
          </button>

          <button
            onClick={resetCamera}
            className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-sm transition"
            title="Reset Camera View"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 3D Canvas Mount */}
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Bottom Telemetry Overlay Badge */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
        <div className="bg-zinc-900/90 backdrop-blur-md px-3.5 py-2 rounded-sm border border-zinc-700/80 shadow-xl pointer-events-auto flex items-center gap-4 text-xs font-mono font-bold">
          <div>
            <span className="text-zinc-400">X:</span>{' '}
            <span className="text-amber-400">{endPos.x} mm</span>
          </div>
          <div>
            <span className="text-zinc-400">Y:</span>{' '}
            <span className="text-amber-400">{endPos.y} mm</span>
          </div>
          <div>
            <span className="text-zinc-400">Z:</span>{' '}
            <span className="text-amber-400">{endPos.z} mm</span>
          </div>
          <div className="hidden sm:block border-l border-zinc-700 pl-3">
            <span className="text-zinc-400">PITCH:</span>{' '}
            <span className="text-cyan-400">{endPos.pitch}°</span>
          </div>
          <div className="hidden sm:block">
            <span className="text-zinc-400">ROLL:</span>{' '}
            <span className="text-cyan-400">{endPos.roll}°</span>
          </div>
        </div>

        {/* Payload Status */}
        <div className="bg-zinc-900/90 backdrop-blur-md px-3.5 py-2 rounded-sm border border-zinc-700/80 shadow-xl pointer-events-auto flex items-center gap-2 text-xs font-bold uppercase tracking-tight">
          <Box className="w-3.5 h-3.5 text-rose-400" />
          <span className="text-zinc-300">Payload:</span>
          <span className="font-mono text-emerald-400">
            {joints.gripper < 30 ? 'GRASPED' : 'OPEN'}
          </span>
        </div>
      </div>
    </div>
  );
};
