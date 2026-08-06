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

// Shoulder pivot positions in world space (symmetric about x=0)
const SHOULDER   = { x:  0.55, y: 0.45, z: 0 };
const SHOULDER_L = { x: -0.55, y: 0.45, z: 0 };
const SHOULDER_C = { x:  0,    y: 0.45, z: 0.55 };

// Floor path constants (center arm)
const FLOOR_Y        = 0.05;
const FLOOR_R        = 0.20;
const FLOOR_SEGMENTS = 20;

// Wall working surface
const WALL_Z = -0.25;  // wrist stops here; palm+fingers reach ~-0.43 (wall face)
const PATH_W = 0.50;  // wall path width
const PATH_H = 0.40;  // wall path height
const PATH_Y0 = 0.25; // bottom of path (world Y)
const COLS = 4;
const ROWS = 5;

interface DemoMotionState {
  waypoints: [number, number, number][];
  waypointIndex: number;
  progress: number;
}

function buildWaypointsRight(): [number, number, number][] {
  const pts: [number, number, number][] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const col = r % 2 === 0 ? c : COLS - 1 - c;
      pts.push([
        (col / (COLS - 1)) * (PATH_W / 2),   // right half: 0 → +0.25
        PATH_Y0 + (r / (ROWS - 1)) * PATH_H,
        WALL_Z,
      ]);
    }
  }
  return pts;
}

function buildWaypointsLeft(): [number, number, number][] {
  const pts: [number, number, number][] = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const col = r % 2 === 0 ? c : COLS - 1 - c;
      pts.push([
        -PATH_W / 2 + (col / (COLS - 1)) * PATH_W / 2, // left half only
        PATH_Y0 + (r / (ROWS - 1)) * PATH_H,
        WALL_Z,
      ]);
    }
  }
  return pts;
}

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

function solveIKFloor(tx: number, ty: number, tz: number): { pan: number; tilt: number; elbow: number } {
  const dx = tx - SHOULDER_C.x;
  const dy = ty - SHOULDER_C.y;
  const dz = tz - SHOULDER_C.z;

  const horizontalDist = Math.sqrt(dx * dx + dz * dz);
  const d = Math.sqrt(horizontalDist * horizontalDist + dy * dy);
  const dClamped = Math.min(Math.max(d, Math.abs(L1 - L2) + 0.001), L1 + L2 - 0.001);

  const pan = Math.atan2(dx, dz);
  const elevAngle = Math.atan2(dy, horizontalDist);

  const cosElbow = (dClamped * dClamped - L1 * L1 - L2 * L2) / (2 * L1 * L2);
  const elbow = Math.acos(Math.max(-1, Math.min(1, cosElbow)));

  const cosAlpha = (dClamped * dClamped + L1 * L1 - L2 * L2) / (2 * dClamped * L1);
  const alpha = Math.acos(Math.max(-1, Math.min(1, cosAlpha)));
  const tilt = elevAngle + alpha;

  return { pan, tilt, elbow };
}

function solveIK(
  tx: number, ty: number, tz: number,
  shoulder = SHOULDER,
): { pan: number; tilt: number; elbow: number } {
  const dx = tx - shoulder.x;
  const dy = ty - shoulder.y;
  const dz = tz - shoulder.z;

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
  private readonly waypointsRight = buildWaypointsRight();
  private rightState: DemoMotionState = {
    waypoints: this.waypointsRight,
    waypointIndex: 0,
    progress: 0
  };
  private readonly SPEED = 1 / 8; // full path in 8 seconds

  private waypointsLeft = buildWaypointsLeft();
  private leftState: DemoMotionState = {
    waypoints: this.waypointsLeft,
    waypointIndex: 0,
    progress: 0
  };

  private _curl  = 10 * (Math.PI / 180);
  private _curlL = 10 * (Math.PI / 180);
  private _curlC = 10 * (Math.PI / 180);

  private readonly centerState: DemoMotionState = {
    waypoints: buildFloorWaypoints(),
    waypointIndex: 0,
    progress: 0,
  };

  tickRight(deltaMs: number, focus: number): MotionFrame {
    const dt = deltaMs / 1000;
    this.rightState.progress += dt * this.SPEED * this.rightState.waypoints.length;
    while (this.rightState.progress >= 1) {
      this.rightState.progress -= 1;
      this.rightState.waypointIndex = (this.rightState.waypointIndex + 1) % this.rightState.waypoints.length;
    }

    const curr = this.rightState.waypoints[this.rightState.waypointIndex];
    const next = this.rightState.waypoints[(this.rightState.waypointIndex + 1) % this.rightState.waypoints.length];
    const tx = lerp(curr[0], next[0], this.rightState.progress);
    const ty = lerp(curr[1], next[1], this.rightState.progress);
    const tz = lerp(curr[2], next[2], this.rightState.progress);

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

  tickLeft(deltaMs: number, focus: number): MotionFrame {
    const dt = deltaMs / 1000;
    this.leftState.progress += dt * this.SPEED * this.leftState.waypoints.length;
    while (this.leftState.progress >= 1) {
      this.leftState.progress -= 1;
      this.leftState.waypointIndex = (this.leftState.waypointIndex + 1) % this.leftState.waypoints.length;
    }

    const curr = this.leftState.waypoints[this.leftState.waypointIndex];
    const next = this.leftState.waypoints[(this.leftState.waypointIndex + 1) % this.leftState.waypoints.length];
    const tx = lerp(curr[0], next[0], this.leftState.progress);
    const ty = lerp(curr[1], next[1], this.leftState.progress);
    const tz = lerp(curr[2], next[2], this.leftState.progress);

    const ik = solveIK(tx, ty, tz, SHOULDER_L);

    // State: release when repositioning (large X jump between waypoints = new row)
    const isRepositioning = Math.abs(next[1] - curr[1]) > 0.01;
    const state: 'grip' | 'release' | 'tighten' =
      isRepositioning ? 'release' : focus > 0.7 ? 'tighten' : 'grip';

    const targetCurl = fingerCurl(state, focus);
    this._curlL = lerp(this._curlL, targetCurl, Math.min(1, dt * 4));

    // Mirror the shoulder pan to the left arm
    const frame = {
      shoulderPan: -ik.pan,  // negated for left arm
      shoulderTilt: ik.tilt,
      elbowAngle: ik.elbow,
      wristAngle: 0,
      fingerCurl: this._curlL,
      state,
    };

    return frame;
  }

  tickCenter(deltaMs: number, focus: number): MotionFrame {
    const dt = deltaMs / 1000;
    const s = this.centerState;
    s.progress += dt * this.SPEED * s.waypoints.length;
    while (s.progress >= 1) {
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
    this._curlC = lerp(this._curlC, targetCurl, Math.min(1, dt * 4));

    return {
      shoulderPan: ik.pan,
      shoulderTilt: ik.tilt,
      elbowAngle: ik.elbow,
      wristAngle: 0,
      fingerCurl: this._curlC,
      state,
    };
  }

  currentToolTipCenter(frame: MotionFrame): [number, number, number] {
    const px = SHOULDER_C.x + (L1 + L2) * Math.sin(frame.shoulderPan) * Math.cos(frame.shoulderTilt);
    const py = SHOULDER_C.y - (L1 + L2) * Math.sin(frame.shoulderTilt);
    const pz = SHOULDER_C.z + (L1 + L2) * Math.cos(frame.shoulderPan) * Math.cos(frame.shoulderTilt);
    return [px, py, pz];
  }

  /** Returns the current tool-tip world position for the paint trail. */
  currentToolTip(frame: MotionFrame): [number, number, number] {
    const px = SHOULDER.x + (L1 + L2) * Math.sin(frame.shoulderPan);
    const py = SHOULDER.y + (L1 + L2) * Math.sin(frame.shoulderTilt);
    const pz = SHOULDER.z - (L1 + L2) * Math.cos(frame.shoulderPan);
    return [px, py, pz];
  }

  currentToolTipLeft(frame: MotionFrame): [number, number, number] {
    const px = SHOULDER_L.x + (L1 + L2) * Math.sin(frame.shoulderPan);
    const py = SHOULDER_L.y + (L1 + L2) * Math.sin(frame.shoulderTilt);
    const pz = SHOULDER_L.z - (L1 + L2) * Math.cos(frame.shoulderPan);
    return [px, py, pz];
  }
}