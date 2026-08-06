export type ServoId = 'base' | 'shoulder' | 'elbow' | 'wristPitch' | 'wristRoll' | 'gripper';

export interface ServoConfig {
  id: ServoId;
  name: string;
  hardwareId: number; // 1 to 6
  minAngle: number;
  maxAngle: number;
  defaultAngle: number;
  unit: 'deg' | '%';
  description: string;
}

export interface JointState {
  base: number;       // -180 to +180 deg
  shoulder: number;   // -90 to +90 deg
  elbow: number;      // -120 to +120 deg
  wristPitch: number; // -90 to +90 deg
  wristRoll: number;  // -180 to +180 deg
  gripper: number;    // 0 to 100 % (0 = fully closed, 100 = wide open)
}

export interface CartesianPos {
  x: number; // mm forward (+X)
  y: number; // mm lateral (+Y left, -Y right)
  z: number; // mm altitude (+Z up)
  pitch: number; // pitch angle in deg
  roll: number;  // roll angle in deg
}

export interface Keyframe {
  id: string;
  name: string;
  durationMs: number; // transition duration in ms
  delayAfterMs: number; // pause delay after reaching pose
  joints: JointState;
  comment?: string;
}

export interface Sequence {
  id: string;
  title: string;
  description: string;
  category: 'utility' | 'demo' | 'task' | 'custom' | 'ai';
  keyframes: Keyframe[];
  loop: boolean;
  speedMultiplier: number;
  createdAt: string;
  tags?: string[];
}

export type ConnectionType = 'simulation' | 'webserial' | 'websocket' | 'http';
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface LeaderArmState {
  connected: boolean;
  connectionType: ConnectionType;
  deviceName?: string;
  isMirroring: boolean;
  isRecording: boolean;
  recordedFramesCount: number;
  joints: JointState;
  offsets: JointState;
  torqueOnLeader: boolean;
}

export interface TelemetryData {
  voltage: number;      // Volts (e.g., 7.4V to 12.0V)
  current: number;      // mA
  temp: number;         // °C
  isTorqueEnabled: boolean;
  packetHz: number;     // Packets per second
  connectedDevice?: string;
  baudRate?: number;
  lastCommand?: string;
  logs: Array<{ id: string; time: string; text: string; type: 'info' | 'rx' | 'tx' | 'warn' | 'error' }>;
}

export interface GamepadMapping {
  connected: boolean;
  id: string;
  axes: number[];
  buttons: boolean[];
}

export interface VisionTarget {
  id: string;
  label: string;
  xRatio: number; // 0 to 1
  yRatio: number; // 0 to 1
  color: string;
  confidence: number;
}
