import { JointState, CartesianPos } from '../types';

// SO-ARM100 Physical Dimensions (millimeters)
export const ARM_L1 = 105; // Base pivot height from table
export const ARM_L2 = 125; // Upper arm length (Shoulder to Elbow)
export const ARM_L3 = 125; // Forearm length (Elbow to Wrist)
export const ARM_L4 = 85;  // End effector length (Wrist to Gripper tip)

const DEG2RAD = Math.PI / 180;
const RAD2DEG = 180 / Math.PI;

/**
 * Calculates 3D End-Effector Position (Cartesian FK) from joint angles
 */
export function forwardKinematics(joints: JointState): CartesianPos {
  const theta1 = joints.base * DEG2RAD;
  const theta2 = joints.shoulder * DEG2RAD;
  const theta3 = joints.elbow * DEG2RAD;
  const theta4 = joints.wristPitch * DEG2RAD;

  // Cumulative pitch angles relative to horizon
  const phi2 = theta2;
  const phi3 = phi2 + theta3;
  const phi4 = phi3 + theta4;

  // Radial distance from base center
  const r = ARM_L2 * Math.cos(phi2) + ARM_L3 * Math.cos(phi3) + ARM_L4 * Math.cos(phi4);

  // Cartesian coordinates
  const x = r * Math.cos(theta1);
  const y = r * Math.sin(theta1);
  const z = ARM_L1 + ARM_L2 * Math.sin(phi2) + ARM_L3 * Math.sin(phi3) + ARM_L4 * Math.sin(phi4);

  const pitch = phi4 * RAD2DEG;
  const roll = joints.wristRoll;

  return {
    x: Math.round(x * 10) / 10,
    y: Math.round(y * 10) / 10,
    z: Math.round(z * 10) / 10,
    pitch: Math.round(pitch * 10) / 10,
    roll: Math.round(roll * 10) / 10
  };
}

/**
 * Inverse Kinematics (IK) - Solves joint angles for target 3D Cartesian position
 */
export function inverseKinematics(target: CartesianPos, currentJoints: JointState): JointState | null {
  const { x, y, z, pitch, roll } = target;

  // 1. Base Angle
  const baseRad = Math.atan2(y, x);
  const base = baseRad * RAD2DEG;

  // 2. Radial projection
  const rTotal = Math.sqrt(x * x + y * y);

  // Target pitch relative to horizon
  const pitchRad = pitch * DEG2RAD;

  // Calculate wrist center (W) position
  const rWrist = rTotal - ARM_L4 * Math.cos(pitchRad);
  const zWrist = (z - ARM_L1) - ARM_L4 * Math.sin(pitchRad);

  const D2 = rWrist * rWrist + zWrist * zWrist;
  const D = Math.sqrt(D2);

  // Check workspace boundary
  const maxReach = ARM_L2 + ARM_L3;
  const minReach = Math.abs(ARM_L2 - ARM_L3);

  if (D > maxReach || D < minReach || isNaN(D)) {
    return null; // Out of reachable workspace
  }

  // Cosine law for elbow joint (theta3)
  const cosTheta3 = (D2 - ARM_L2 * ARM_L2 - ARM_L3 * ARM_L3) / (2 * ARM_L2 * ARM_L3);
  const clampedCos3 = Math.max(-1, Math.min(1, cosTheta3));
  const theta3Rad = Math.acos(clampedCos3); // elbow angle

  // Shoulder angle (theta2)
  const alpha = Math.atan2(zWrist, rWrist);
  const beta = Math.atan2(ARM_L3 * Math.sin(theta3Rad), ARM_L2 + ARM_L3 * Math.cos(theta3Rad));
  const theta2Rad = alpha - beta;

  // Wrist pitch (theta4)
  const theta4Rad = pitchRad - (theta2Rad + theta3Rad);

  const newBase = Math.max(-180, Math.min(180, Math.round(base * 10) / 10));
  const newShoulder = Math.max(-90, Math.min(90, Math.round(theta2Rad * RAD2DEG * 10) / 10));
  const newElbow = Math.max(-120, Math.min(120, Math.round(theta3Rad * RAD2DEG * 10) / 10));
  const newWristPitch = Math.max(-90, Math.min(90, Math.round(theta4Rad * RAD2DEG * 10) / 10));
  const newWristRoll = Math.max(-180, Math.min(180, Math.round(roll * 10) / 10));

  return {
    base: newBase,
    shoulder: newShoulder,
    elbow: newElbow,
    wristPitch: newWristPitch,
    wristRoll: newWristRoll,
    gripper: currentJoints.gripper
  };
}

/**
 * Converts joint angles (-180..180 deg) into STS3215 raw servo steps (0..4095)
 */
export function angleToRawTicks(angle: number, minAngle: number, maxAngle: number): number {
  const norm = (angle - minAngle) / (maxAngle - minAngle);
  return Math.round(Math.max(0, Math.min(4095, norm * 4095)));
}

/**
 * Converts raw servo ticks (0..4095) back to degrees
 */
export function rawTicksToAngle(ticks: number, minAngle: number, maxAngle: number): number {
  const norm = ticks / 4095;
  return Math.round((minAngle + norm * (maxAngle - minAngle)) * 10) / 10;
}

/**
 * Formats command string for SO-ARM100 Feetech Serial Protocol / WebSerial
 * Format: #1P1500#2P2048#3P1024#4P2048#5P2048#6P1000T500!
 */
export function formatSerialCommand(joints: JointState, durationMs: number = 500): string {
  const b = angleToRawTicks(joints.base, -180, 180);
  const s = angleToRawTicks(joints.shoulder, -90, 90);
  const e = angleToRawTicks(joints.elbow, -120, 120);
  const wp = angleToRawTicks(joints.wristPitch, -90, 90);
  const wr = angleToRawTicks(joints.wristRoll, -180, 180);
  const g = angleToRawTicks(joints.gripper, 0, 100);

  return `#1P${b}#2P${s}#3P${e}#4P${wp}#5P${wr}#6P${g}T${durationMs}!`;
}

/**
 * Interpolates between two joint states for smooth animation / transition
 */
export function interpolateJoints(start: JointState, end: JointState, t: number): JointState {
  // t is 0..1
  const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t; // Smooth ease-in-out
  return {
    base: start.base + (end.base - start.base) * ease,
    shoulder: start.shoulder + (end.shoulder - start.shoulder) * ease,
    elbow: start.elbow + (end.elbow - start.elbow) * ease,
    wristPitch: start.wristPitch + (end.wristPitch - start.wristPitch) * ease,
    wristRoll: start.wristRoll + (end.wristRoll - start.wristRoll) * ease,
    gripper: start.gripper + (end.gripper - start.gripper) * ease
  };
}
