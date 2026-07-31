import { ServoConfig, JointState, Sequence } from './types';

export const SO_ARM100_SERVOS: ServoConfig[] = [
  {
    id: 'base',
    name: 'Base Rotation (S1)',
    hardwareId: 1,
    minAngle: -180,
    maxAngle: 180,
    defaultAngle: 0,
    unit: 'deg',
    description: 'Rotates the arm left (-180°) to right (+180°)'
  },
  {
    id: 'shoulder',
    name: 'Shoulder Pitch (S2)',
    hardwareId: 2,
    minAngle: -90,
    maxAngle: 90,
    defaultAngle: 15,
    unit: 'deg',
    description: 'Tilts lower arm forward/backward'
  },
  {
    id: 'elbow',
    name: 'Elbow Pitch (S3)',
    hardwareId: 3,
    minAngle: -120,
    maxAngle: 120,
    defaultAngle: 45,
    unit: 'deg',
    description: 'Flexes/extends upper arm joint'
  },
  {
    id: 'wristPitch',
    name: 'Wrist Pitch (S4)',
    hardwareId: 4,
    minAngle: -90,
    maxAngle: 90,
    defaultAngle: -30,
    unit: 'deg',
    description: 'Tilts wrist up/down relative to forearm'
  },
  {
    id: 'wristRoll',
    name: 'Wrist Roll (S5)',
    hardwareId: 5,
    minAngle: -180,
    maxAngle: 180,
    defaultAngle: 0,
    unit: 'deg',
    description: 'Rotates end-effector clockwise/counter-clockwise'
  },
  {
    id: 'gripper',
    name: 'Gripper (S6)',
    hardwareId: 6,
    minAngle: 0,
    maxAngle: 100,
    defaultAngle: 40,
    unit: '%',
    description: 'End effector claw aperture (0% closed, 100% open)'
  }
];

export const DEFAULT_JOINTS: JointState = {
  base: 0,
  shoulder: 20,
  elbow: 40,
  wristPitch: -30,
  wristRoll: 0,
  gripper: 40
};

export const STOW_JOINTS: JointState = {
  base: 0,
  shoulder: -75,
  elbow: 110,
  wristPitch: -35,
  wristRoll: 0,
  gripper: 0
};

export const PRESET_SEQUENCES: Sequence[] = [
  {
    id: 'preset-pick-place',
    title: 'Pick & Place Task',
    description: 'Descends to table, closes gripper, lifts target, rotates 90° right, releases item, and stows.',
    category: 'task',
    loop: false,
    speedMultiplier: 1.0,
    createdAt: new Date().toISOString(),
    tags: ['Autonomous', 'Pick', 'Place'],
    keyframes: [
      {
        id: 'kf-pp-1',
        name: 'Hover Above Pick',
        durationMs: 1200,
        delayAfterMs: 300,
        joints: { base: -45, shoulder: 15, elbow: 45, wristPitch: -20, wristRoll: 0, gripper: 90 },
        comment: 'Positioning over target'
      },
      {
        id: 'kf-pp-2',
        name: 'Lower & Reach',
        durationMs: 1000,
        delayAfterMs: 400,
        joints: { base: -45, shoulder: 42, elbow: 55, wristPitch: -10, wristRoll: 0, gripper: 90 },
        comment: 'Lowering onto item'
      },
      {
        id: 'kf-pp-3',
        name: 'Gasp / Clamp Gripper',
        durationMs: 600,
        delayAfterMs: 500,
        joints: { base: -45, shoulder: 42, elbow: 55, wristPitch: -10, wristRoll: 0, gripper: 15 },
        comment: 'Securing payload'
      },
      {
        id: 'kf-pp-4',
        name: 'Elevate Payload',
        durationMs: 1200,
        delayAfterMs: 300,
        joints: { base: -45, shoulder: 10, elbow: 25, wristPitch: -25, wristRoll: 0, gripper: 15 },
        comment: 'Clearing obstacle height'
      },
      {
        id: 'kf-pp-5',
        name: 'Slew 90° to Drop Zone',
        durationMs: 1800,
        delayAfterMs: 400,
        joints: { base: 45, shoulder: 10, elbow: 25, wristPitch: -25, wristRoll: 0, gripper: 15 },
        comment: 'Rotating base joint'
      },
      {
        id: 'kf-pp-6',
        name: 'Lower to Drop Zone',
        durationMs: 1000,
        delayAfterMs: 400,
        joints: { base: 45, shoulder: 38, elbow: 50, wristPitch: -10, wristRoll: 0, gripper: 15 },
        comment: 'Setting down payload'
      },
      {
        id: 'kf-pp-7',
        name: 'Release Payload',
        durationMs: 600,
        delayAfterMs: 300,
        joints: { base: 45, shoulder: 38, elbow: 50, wristPitch: -10, wristRoll: 0, gripper: 85 },
        comment: 'Opening claw'
      },
      {
        id: 'kf-pp-8',
        name: 'Return Home',
        durationMs: 1500,
        delayAfterMs: 0,
        joints: DEFAULT_JOINTS,
        comment: 'Restoring home position'
      }
    ]
  },
  {
    id: 'preset-friendly-wave',
    title: 'Friendly Greeting Wave',
    description: 'Lifts arm, rotates wrist and tilts elbow in a smooth rhythmic greeting gesture.',
    category: 'demo',
    loop: false,
    speedMultiplier: 1.2,
    createdAt: new Date().toISOString(),
    tags: ['Greeting', 'Gestures'],
    keyframes: [
      {
        id: 'kf-wave-1',
        name: 'Raise Hand',
        durationMs: 1000,
        delayAfterMs: 100,
        joints: { base: 0, shoulder: 45, elbow: 65, wristPitch: 40, wristRoll: 0, gripper: 50 },
        comment: 'Elevating forearm'
      },
      {
        id: 'kf-wave-2',
        name: 'Wave Right',
        durationMs: 500,
        delayAfterMs: 50,
        joints: { base: 15, shoulder: 45, elbow: 65, wristPitch: 40, wristRoll: 45, gripper: 50 },
        comment: 'Roll right'
      },
      {
        id: 'kf-wave-3',
        name: 'Wave Left',
        durationMs: 500,
        delayAfterMs: 50,
        joints: { base: -15, shoulder: 45, elbow: 65, wristPitch: 40, wristRoll: -45, gripper: 50 },
        comment: 'Roll left'
      },
      {
        id: 'kf-wave-4',
        name: 'Wave Right 2',
        durationMs: 500,
        delayAfterMs: 50,
        joints: { base: 15, shoulder: 45, elbow: 65, wristPitch: 40, wristRoll: 45, gripper: 50 },
        comment: 'Roll right repeat'
      },
      {
        id: 'kf-wave-5',
        name: 'Wave Left 2',
        durationMs: 500,
        delayAfterMs: 200,
        joints: { base: -15, shoulder: 45, elbow: 65, wristPitch: 40, wristRoll: -45, gripper: 50 },
        comment: 'Roll left repeat'
      },
      {
        id: 'kf-wave-6',
        name: 'Return to Rest',
        durationMs: 1200,
        delayAfterMs: 0,
        joints: DEFAULT_JOINTS,
        comment: 'Lowering arm'
      }
    ]
  },
  {
    id: 'preset-inspection-sweep',
    title: 'Precision Inspection Grid',
    description: 'Systematic camera/sensor sweep across a 3x3 workspace grid maintaining vertical wrist angle.',
    category: 'utility',
    loop: false,
    speedMultiplier: 1.0,
    createdAt: new Date().toISOString(),
    tags: ['Inspection', 'Scanning'],
    keyframes: [
      {
        id: 'kf-ins-1',
        name: 'Scan Point A (Left Near)',
        durationMs: 1400,
        delayAfterMs: 500,
        joints: { base: -60, shoulder: 35, elbow: 45, wristPitch: 20, wristRoll: 0, gripper: 0 },
        comment: 'Grid 1,1'
      },
      {
        id: 'kf-ins-2',
        name: 'Scan Point B (Center Near)',
        durationMs: 1000,
        delayAfterMs: 500,
        joints: { base: 0, shoulder: 35, elbow: 45, wristPitch: 20, wristRoll: 0, gripper: 0 },
        comment: 'Grid 1,2'
      },
      {
        id: 'kf-ins-3',
        name: 'Scan Point C (Right Near)',
        durationMs: 1000,
        delayAfterMs: 500,
        joints: { base: 60, shoulder: 35, elbow: 45, wristPitch: 20, wristRoll: 0, gripper: 0 },
        comment: 'Grid 1,3'
      },
      {
        id: 'kf-ins-4',
        name: 'Scan Point D (Right Far)',
        durationMs: 1200,
        delayAfterMs: 500,
        joints: { base: 60, shoulder: 15, elbow: 25, wristPitch: 40, wristRoll: 0, gripper: 0 },
        comment: 'Grid 2,3'
      },
      {
        id: 'kf-ins-5',
        name: 'Scan Point E (Center Far)',
        durationMs: 1000,
        delayAfterMs: 500,
        joints: { base: 0, shoulder: 15, elbow: 25, wristPitch: 40, wristRoll: 0, gripper: 0 },
        comment: 'Grid 2,2'
      },
      {
        id: 'kf-ins-6',
        name: 'Scan Point F (Left Far)',
        durationMs: 1000,
        delayAfterMs: 500,
        joints: { base: -60, shoulder: 15, elbow: 25, wristPitch: 40, wristRoll: 0, gripper: 0 },
        comment: 'Grid 2,1'
      },
      {
        id: 'kf-ins-7',
        name: 'Home',
        durationMs: 1200,
        delayAfterMs: 0,
        joints: DEFAULT_JOINTS,
        comment: 'Inspection complete'
      }
    ]
  },
  {
    id: 'preset-stow-transport',
    title: 'Folded Safe Stow Position',
    description: 'Safely tucks all arm joints to minimize volume for storage, transport, or zero-torque rest.',
    category: 'utility',
    loop: false,
    speedMultiplier: 1.0,
    createdAt: new Date().toISOString(),
    tags: ['Safety', 'Stow'],
    keyframes: [
      {
        id: 'kf-stow-1',
        name: 'Stow Fold',
        durationMs: 1800,
        delayAfterMs: 0,
        joints: STOW_JOINTS,
        comment: 'Compact safe fold'
      }
    ]
  }
];
