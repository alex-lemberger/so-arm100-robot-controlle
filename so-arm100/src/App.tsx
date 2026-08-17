/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { lazy, Suspense, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { JointState, Sequence, ConnectionType, ConnectionStatus, TelemetryData, LeaderArmState, Keyframe, ServoId } from './types';
import { DEFAULT_JOINTS, PRESET_SEQUENCES, SO_ARM100_SERVOS } from './constants';
import { interpolateJoints, formatSerialCommand, forwardKinematics } from './utils/kinematics';
import { buildPingPacket, buildReadPacket, buildSyncGoalPositionPacket, buildSyncReadPacket, bytesToHex, FEETECH_SIGN_BIT, FeetechPacket, parseFeetechPackets, readSignedWord } from './utils/feetech';
import { ConnectionBar } from './components/ConnectionBar';
import { ShieldAlert, Zap, Cpu, Sparkles, Sliders, Target, Layers, Radio, Database } from 'lucide-react';

const Arm3DCanvas = lazy(() => import('./components/Arm3DCanvas').then(module => ({ default: module.Arm3DCanvas })));
const JointControls = lazy(() => import('./components/JointControls').then(module => ({ default: module.JointControls })));
const KinematicsIKPanel = lazy(() => import('./components/KinematicsIKPanel').then(module => ({ default: module.KinematicsIKPanel })));
const SequenceStudio = lazy(() => import('./components/SequenceStudio').then(module => ({ default: module.SequenceStudio })));
const GamepadVisionOverlay = lazy(() => import('./components/GamepadVisionOverlay').then(module => ({ default: module.GamepadVisionOverlay })));
const LeaderArmPanel = lazy(() => import('./components/LeaderArmPanel').then(module => ({ default: module.LeaderArmPanel })));
const AISequenceGenerator = lazy(() => import('./components/AISequenceGenerator').then(module => ({ default: module.AISequenceGenerator })));
const TelemetryLogConsole = lazy(() => import('./components/TelemetryLogConsole').then(module => ({ default: module.TelemetryLogConsole })));
const DatasetPanel = lazy(() => import('./components/DatasetPanel').then(module => ({ default: module.DatasetPanel })));

const HARDWARE_COMMAND_INTERVAL_MS = 50;
const FEETECH_REPLY_TIMEOUT_MS = 300;
/**
 * Reply timeout for the episode sampling loop. Deliberately far shorter than
 * the 300 ms interactive timeout: at 1 Mbaud a reply takes well under a
 * millisecond, and the sampler runs on a ~33 ms budget, so a 300 ms stall
 * costs nine frames instead of one. Measured on the 2026-08-08 recording, 55
 * timeouts at 301 ms each consumed 16.6 s of a 25.5 s take and dragged the
 * achieved rate from 29.4 Hz down to 12.4 Hz.
 */
const FEETECH_SAMPLE_TIMEOUT_MS = 25;

type FeetechCalibration = Record<ServoId, { minTick: number; maxTick: number; homingOffset: number }>;

function readFeetechCalibration(): FeetechCalibration | null {
  const raw = import.meta.env.VITE_FEETECH_CALIBRATION;
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<FeetechCalibration>;
    const isValid = SO_ARM100_SERVOS.every((servo) => {
      const calibration = parsed[servo.id];
      return calibration
        && Number.isFinite(calibration.minTick)
        && Number.isFinite(calibration.maxTick)
        && calibration.minTick >= 0
        && calibration.minTick <= 4095
        && calibration.maxTick >= 0
        && calibration.maxTick <= 4095
        && calibration.minTick !== calibration.maxTick
        && Number.isInteger(calibration.homingOffset)
        && Math.abs(calibration.homingOffset) <= 2047;
    });
    return isValid ? parsed as FeetechCalibration : null;
  } catch {
    return null;
  }
}

function jointsToCalibratedTicks(joints: JointState, calibration: FeetechCalibration) {
  return SO_ARM100_SERVOS.map((servo) => {
    const value = joints[servo.id];
    const normalized = Math.max(0, Math.min(1, (value - servo.minAngle) / (servo.maxAngle - servo.minAngle)));
    const ticks = calibration[servo.id].minTick
      + normalized * (calibration[servo.id].maxTick - calibration[servo.id].minTick);
    return { id: servo.hardwareId, position: Math.round(ticks) };
  });
}

function calibratedTicksToJoints(positions: Record<number, number>, calibration: FeetechCalibration): JointState | null {
  const next = { ...DEFAULT_JOINTS };
  for (const servo of SO_ARM100_SERVOS) {
    const position = positions[servo.hardwareId];
    if (!Number.isFinite(position)) return null;
    const { minTick, maxTick } = calibration[servo.id];
    const normalized = (position - minTick) / (maxTick - minTick);
    next[servo.id] = Math.max(
      servo.minAngle,
      Math.min(servo.maxAngle, servo.minAngle + normalized * (servo.maxAngle - servo.minAngle)),
    );
  }
  return next;
}

const LoadingPanel = () => (
  <div className="min-h-28 rounded-sm border border-zinc-800 bg-zinc-900 animate-pulse" aria-label="Loading panel" />
);

export default function App() {
  // 1. Core Robot State
  const [joints, setJoints] = useState<JointState>(DEFAULT_JOINTS);
  const [isTorqueEnabled, setIsTorqueEnabled] = useState(true);
  const jointsRef = useRef<JointState>(DEFAULT_JOINTS);

  // 2. Connectivity State
  const [connectionType, setConnectionType] = useState<ConnectionType>('simulation');
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connected');
  const [verifiedServoIds, setVerifiedServoIds] = useState<number[]>([]);
  const [servoPositions, setServoPositions] = useState<Record<number, number>>({});
  const [isCalibrationVerified, setIsCalibrationVerified] = useState(false);
  const [isMotionArmed, setIsMotionArmed] = useState(false);
  const portWriterRef = useRef<any>(null);
  const serialPortRef = useRef<any>(null);
  const [followerSerialPort, setFollowerSerialPort] = useState<any>(null);
  const [leaderSerialPort, setLeaderSerialPort] = useState<any>(null);
  const serialReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const serialReadLoopActiveRef = useRef(false);
  const serialRxBufferRef = useRef<Uint8Array>(new Uint8Array());
  const pendingFeetechResponsesRef = useRef(new Map<number, (packet: FeetechPacket) => void>());
  /**
   * Wire tracing, switched on only around a Verify Servos run.
   *
   * "No Feetech replies received" is a single opaque outcome that cannot tell
   * "nothing came back at all" from "bytes came back and failed to parse" -- a dead
   * bus versus a framing or baud problem, which have nothing to do with each other.
   * On 2026-08-17 the follower answered 6/6 to a plain Python PING on the same port
   * at the same baud, with DTR/RTS making no difference, while the app saw 0/6. That
   * gap is only visible with the raw bytes in front of you.
   *
   * Off by default and auto-off after a run, because the 20Hz sampling loop during an
   * episode would otherwise flood the log ring and the console.
   */
  const serialTraceRef = useRef(false);
  const wsClientRef = useRef<WebSocket | null>(null);
  const pendingHardwareJointsRef = useRef<JointState | null>(null);
  const hardwareCommandTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastHardwareCommandAtRef = useRef(0);
  const hardwareMotionBlockReasonRef = useRef<string | null>(null);
  const feetechCalibration = useMemo(readFeetechCalibration, []);

  // 3. Telemetry State
  const [telemetry, setTelemetry] = useState<TelemetryData>({
    voltage: 11.8,
    current: 240,
    temp: 34,
    isTorqueEnabled: true,
    packetHz: 20,
    baudRate: 1000000,
    logs: [
      { id: '1', time: new Date().toLocaleTimeString(), text: 'SO-ARM100 Digital Twin Simulation Initialized.', type: 'info' }
    ]
  });

  // 4. Sequence & Playback State
  const [currentSequence, setCurrentSequence] = useState<Sequence>(PRESET_SEQUENCES[0]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeKeyframeIndex, setActiveKeyframeIndex] = useState(-1);

  // 5. Leader Arm & Control Mode Tabs
  const [leaderState, setLeaderState] = useState<LeaderArmState>({
    connected: false,
    connectionType: 'simulation',
    deviceName: 'Leader Arm (SO-ARM100)',
    isMirroring: false,
    isRecording: false,
    recordedFramesCount: 0,
    joints: { ...DEFAULT_JOINTS },
    offsets: { base: 0, shoulder: 0, elbow: 0, wristPitch: 0, wristRoll: 0, gripper: 0 },
    torqueOnLeader: false
  });
  const [controlTab, setControlTab] = useState<'fk' | 'ik' | 'teleop' | 'leader' | 'dataset'>('fk');

  // 6. Modals
  const [isAiGeneratorOpen, setIsAiGeneratorOpen] = useState(false);
  const [isConsoleOpen, setIsConsoleOpen] = useState(false);

  // Helper to append log to telemetry
  const logMessage = useCallback((text: string, type: 'info' | 'rx' | 'tx' | 'warn' | 'error') => {
    const newEntry = {
      id: `log-${Date.now()}-${Math.random()}`,
      time: new Date().toLocaleTimeString(),
      text,
      type
    };
    setTelemetry(prev => ({
      ...prev,
      lastCommand: type === 'tx' ? text : prev.lastCommand,
      logs: [newEntry, ...prev.logs.slice(0, 100)]
    }));

    // Mirror to the browser console as well as the in-app drawer.
    //
    // Until 2026-08-17 this function was the ONLY sink for every diagnostic the app
    // produces, and it wrote exclusively into telemetry.logs -- so unless the log
    // drawer happened to be open, the app was silent no matter what went wrong.
    // "Verify Servos does nothing, also no console output" was exactly this: the
    // handler ran and reported, into a panel nobody was looking at, while devtools
    // stayed empty. The button label compounded it by only showing "N/6" once at
    // least one servo replies, so a failed verify looks identical to a dead button.
    //
    // Also only the log ring holds the last 100 entries, so anything older was gone
    // for good. The console keeps its own scrollback, and console output can be
    // copied out of devtools and pasted to someone who is not at the bench.
    const sink = type === 'error' ? console.error : type === 'warn' ? console.warn : console.log;
    sink(`[SO-ARM100:${type}] ${text}`);
  }, []);

  // Text commands are intended for a controller bridge on WebSocket. Direct WebSerial
  // talks the Feetech binary bus and must not receive made-up ASCII commands.
  const sendSerialCommand = useCallback(async (cmdString: string, shouldLog = true) => {
    if (shouldLog) {
      logMessage(cmdString, 'tx');
    }

    if (portWriterRef.current) {
      logMessage('Direct WebSerial uses Feetech binary packets; raw ASCII commands are only supported through a WebSocket bridge.', 'warn');
    } else if (wsClientRef.current && wsClientRef.current.readyState === WebSocket.OPEN) {
      wsClientRef.current.send(cmdString);
    }
  }, [logMessage]);

  const sendFeetechPacket = useCallback(async (packet: Uint8Array, description: string, shouldLog = true) => {
    if (!portWriterRef.current) {
      throw new Error('No direct WebSerial connection is open.');
    }

    if (shouldLog) logMessage(`${description}: ${bytesToHex(packet)}`, 'tx');
    await portWriterRef.current.write(packet);
  }, [logMessage]);

  const processFeetechPacket = useCallback((packet: FeetechPacket) => {
    const resolver = pendingFeetechResponsesRef.current.get(packet.id);
    if (resolver) {
      pendingFeetechResponsesRef.current.delete(packet.id);
      resolver(packet);
    }
  }, []);

  const startSerialReader = useCallback(async (port: any) => {
    if (!port.readable) return;

    const reader = port.readable.getReader();
    serialReaderRef.current = reader;
    serialReadLoopActiveRef.current = true;

    try {
      while (serialReadLoopActiveRef.current) {
        const { value, done } = await reader.read();
        if (done) break;
        if (!value) continue;

        if (serialTraceRef.current) logMessage(`RX ${value.length}B: ${bytesToHex(value)}`, 'rx');

        const combined = new Uint8Array(serialRxBufferRef.current.length + value.length);
        combined.set(serialRxBufferRef.current);
        combined.set(value, serialRxBufferRef.current.length);
        const { packets, remainder } = parseFeetechPackets(combined);
        serialRxBufferRef.current = remainder.length > 1024 ? remainder.slice(-1024) : remainder;

        packets.forEach(processFeetechPacket);
      }
    } catch (err: any) {
      // The read loop dying means the connection is dead, whatever the message says.
      //
      // This used to only log. But handleConnectWebSerial starts this loop with
      // `void startSerialReader(port)`, so a failure here never reaches the connect
      // path -- it went on to set connectionType 'webserial' and connectionStatus
      // 'connected' regardless. On 2026-08-17 that produced a genuinely baffling
      // hour: Chrome handed out a phantom port (its device registry still held the
      // adapter's pre-replug entry), open() succeeded, the first read() threw "The
      // device has been lost", and the UI reported a healthy connection. Verify
      // Servos then wrote all six PINGs to a port with no reader attached and
      // reported "No Feetech replies received" -- which reads as dead hardware,
      // while the same servos answered 6/6 to a plain Python PING on the same port.
      //
      // So tear the connection down here and say what to do about it.
      if (serialReadLoopActiveRef.current) {
        serialReadLoopActiveRef.current = false;
        portWriterRef.current = null;
        serialPortRef.current = null;
        pendingFeetechResponsesRef.current.clear();
        setFollowerSerialPort(null);
        setVerifiedServoIds([]);
        setServoPositions({});
        setIsCalibrationVerified(false);
        setIsMotionArmed(false);
        setConnectionStatus('error');
        hardwareMotionBlockReasonRef.current = `Serial read failed: ${err.message}`;
        logMessage(
          `WebSerial receive error: ${err.message} -- the connection is dead, not just quiet, `
          + 'so verification and motion are locked. If this says the device has been lost, '
          + 'Chrome is offering a stale port for an adapter that was replugged: quit Chrome '
          + 'completely (every process), replug the adapter, then reopen and connect.',
          'error'
        );
      }
    } finally {
      if (serialReaderRef.current === reader) serialReaderRef.current = null;
      try {
        reader.releaseLock();
      } catch {}
    }
  }, [logMessage, processFeetechPacket]);

  const waitForFeetechResponse = useCallback((servoId: number, timeoutMs = FEETECH_REPLY_TIMEOUT_MS) => (
    new Promise<FeetechPacket | null>((resolve) => {
      const timeout = window.setTimeout(() => {
        pendingFeetechResponsesRef.current.delete(servoId);
        resolve(null);
      }, timeoutMs);

      pendingFeetechResponsesRef.current.set(servoId, (packet) => {
        window.clearTimeout(timeout);
        resolve(packet);
      });
    })
  ), []);

  const clearQueuedHardwareMotion = useCallback(() => {
    pendingHardwareJointsRef.current = null;
    if (hardwareCommandTimerRef.current !== null) {
      clearTimeout(hardwareCommandTimerRef.current);
      hardwareCommandTimerRef.current = null;
    }
  }, []);

  // Coalesce motion updates into a bounded 20 Hz hardware command stream.
  const queueHardwareMotion = useCallback((newJoints: JointState, durationMs = 100) => {
    if (connectionType === 'simulation') return;

    if (connectionType === 'webserial') {
      if (!feetechCalibration || !isMotionArmed) {
        const reason = !feetechCalibration
          ? 'Direct motion is locked: add a valid VITE_FEETECH_CALIBRATION before sending position packets.'
          : 'Direct motion is locked: verify the servo bus, then explicitly arm calibrated motion.';
        if (hardwareMotionBlockReasonRef.current !== reason) {
          hardwareMotionBlockReasonRef.current = reason;
          logMessage(reason, 'warn');
        }
        return;
      }
    }

    pendingHardwareJointsRef.current = newJoints;
    if (hardwareCommandTimerRef.current !== null) return;

    const flush = () => {
      hardwareCommandTimerRef.current = null;
      const pendingJoints = pendingHardwareJointsRef.current;
      pendingHardwareJointsRef.current = null;
      if (!pendingJoints) return;

      lastHardwareCommandAtRef.current = performance.now();
      if (connectionType === 'webserial' && feetechCalibration) {
        sendFeetechPacket(
          buildSyncGoalPositionPacket(jointsToCalibratedTicks(pendingJoints, feetechCalibration), durationMs),
          'SYNC_WRITE goal positions',
          false,
        ).catch((err: any) => logMessage(`Feetech motion TX error: ${err.message}`, 'error'));
      } else {
        sendSerialCommand(formatSerialCommand(pendingJoints, durationMs), false);
      }
    };

    const elapsed = performance.now() - lastHardwareCommandAtRef.current;
    hardwareCommandTimerRef.current = setTimeout(flush, Math.max(0, HARDWARE_COMMAND_INTERVAL_MS - elapsed));
  }, [connectionType, feetechCalibration, isMotionArmed, logMessage, sendFeetechPacket, sendSerialCommand]);

  const updateDisplayJoints = useCallback((newJoints: JointState) => {
    jointsRef.current = newJoints;
    setJoints(newJoints);
  }, []);

  // Handle joint changes from FK sliders, IK, gamepad, or sequence playback.
  const handleJointChange = useCallback((newJoints: JointState) => {
    updateDisplayJoints(newJoints);
    queueHardwareMotion(newJoints);
  }, [queueHardwareMotion, updateDisplayJoints]);

  const sendConfiguredSafetyCommand = useCallback((command: string | undefined, action: string) => {
    if (connectionType === 'simulation') {
      logMessage(`${action} engaged in simulation.`, 'warn');
      return;
    }
    if (!command) {
      logMessage(`${action} is software-only. Configure its raw command in .env.local before using hardware.`, 'error');
      return;
    }
    sendSerialCommand(command);
  }, [connectionType, logMessage, sendSerialCommand]);

  useEffect(() => clearQueuedHardwareMotion, [clearQueuedHardwareMotion]);

  // Connect WebSerial (Physical USB)
  const handleConnectWebSerial = async (baudRate: number) => {
    if (typeof window === 'undefined' || !('serial' in navigator)) {
      throw new Error('WebSerial API is not supported in this browser environment. Please use Simulation Mode.');
    }

    try {
      const port = await (navigator as any).serial.requestPort();
      if (port === leaderSerialPort) {
        throw new Error('This USB serial port is reserved for the leader arm. Disconnect the leader or select the other USB Single Serial device for the follower.');
      }
      await port.open({ baudRate });
      serialPortRef.current = port;
      setFollowerSerialPort(port);

      const writer = port.writable.getWriter();
      portWriterRef.current = writer;
      serialRxBufferRef.current = new Uint8Array();
      void startSerialReader(port);

      setConnectionType('webserial');
      setConnectionStatus('connected');
      setVerifiedServoIds([]);
      setServoPositions({});
      setIsCalibrationVerified(false);
      setIsMotionArmed(false);
      hardwareMotionBlockReasonRef.current = null;
      logMessage(`WebSerial open at ${baudRate} baud. Select "Verify servos" before attempting motion.`, 'info');
    } catch (err: any) {
      logMessage(`WebSerial Connection Failed: ${err.message}`, 'error');
      throw err;
    }
  };

  const queryFeetechPacket = useCallback(async (servoId: number, packet: Uint8Array, timeoutMs?: number) => {
    const responsePromise = waitForFeetechResponse(servoId, timeoutMs);
    try {
      await sendFeetechPacket(packet, `Query servo S${servoId}`, serialTraceRef.current);
      return await responsePromise;
    } catch (err) {
      pendingFeetechResponsesRef.current.delete(servoId);
      throw err;
    }
  }, [sendFeetechPacket, waitForFeetechResponse]);

  /**
   * Reads the follower's *measured* encoder positions (register 56) for all six
   * servos. READ only — no motion packet is sent, so this is safe to call while
   * teleoperating and does not require Arm Motion to be armed.
   *
   * Returns raw ticks alongside the decoded JointState. The raw ticks are the
   * point: they are the calibration-independent encoder truth, so a dataset
   * built from them can be expressed in LeRobot's own convention rather than
   * this app's degrees/percent one. Returns null if any servo fails to reply,
   * so a dropped sample is recorded as a gap instead of a fabricated value.
   */
  /**
   * Drops buffered bytes and abandoned reply handlers. A timed-out READ can
   * still land afterwards, which either satisfies the *next* request with
   * stale data or leaves the RX buffer misaligned mid-packet. Either way the
   * failure cascades: the 2026-08-08 recording lost samples in three clustered
   * runs (longest 29 consecutive), not as isolated misses. Resetting after a
   * bad sample keeps one failure from poisoning the ones that follow.
   */
  const resyncFeetechBus = useCallback(() => {
    serialRxBufferRef.current = new Uint8Array();
    pendingFeetechResponsesRef.current.clear();
  }, []);

  const syncReadFailuresRef = useRef(0);
  const syncReadDisabledRef = useRef(false);

  const readPresentTicksSequential = useCallback(async () => {
    const ticks: Record<number, number> = {};
    for (const servo of SO_ARM100_SERVOS) {
      const response = await queryFeetechPacket(
        servo.hardwareId,
        buildReadPacket(servo.hardwareId, 56, 2),
        FEETECH_SAMPLE_TIMEOUT_MS,
      );
      if (!response || response.parameters.length < 2) {
        resyncFeetechBus();
        return null;
      }
      ticks[servo.hardwareId] = readSignedWord(response.parameters, FEETECH_SIGN_BIT.presentPosition);
    }
    return ticks;
  }, [queryFeetechPacket, resyncFeetechBus]);

  const readPresentTicksSync = useCallback(async () => {
    const ids = SO_ARM100_SERVOS.map((servo) => servo.hardwareId);
    // Every reply handler must be registered before the broadcast goes out —
    // all six servos answer back-to-back with no further prompting.
    const pending = ids.map((id) => waitForFeetechResponse(id, FEETECH_SAMPLE_TIMEOUT_MS));
    let responses: (FeetechPacket | null)[];
    try {
      await sendFeetechPacket(buildSyncReadPacket(ids, 56, 2), 'Sync read present position', false);
      responses = await Promise.all(pending);
    } catch {
      resyncFeetechBus();
      return null;
    }

    const ticks: Record<number, number> = {};
    for (let index = 0; index < ids.length; index += 1) {
      const response = responses[index];
      if (!response || response.parameters.length < 2) {
        resyncFeetechBus();
        return null;
      }
      ticks[ids[index]] = readSignedWord(response.parameters, FEETECH_SIGN_BIT.presentPosition);
    }
    return ticks;
  }, [resyncFeetechBus, sendFeetechPacket, waitForFeetechResponse]);

  /**
   * Reads the follower's *measured* encoder positions (register 56) for all six
   * servos. READ only — no motion packet is sent, so this is safe to call while
   * teleoperating and does not require Arm Motion to be armed.
   *
   * Prefers one SYNC_READ broadcast over six individual READs to cut bus
   * contention, but falls back to sequential reads whenever sync read comes
   * back empty, and gives up on it entirely after three consecutive failures.
   * Sync read is unverified on this particular arm, and silently recording a
   * session with no telemetry would be far worse than losing the speedup.
   *
   * Returns raw ticks alongside the decoded JointState. The raw ticks are the
   * point: they are the calibration-independent encoder truth, so a dataset
   * built from them can be expressed in LeRobot's own convention rather than
   * this app's degrees/percent one. Returns null if the read fails, so a
   * dropped sample is recorded as a gap instead of a fabricated value.
   */
  const readMeasuredFollowerState = useCallback(async () => {
    if (!portWriterRef.current || connectionType !== 'webserial' || !feetechCalibration) return null;

    let ticks: Record<number, number> | null = null;
    if (!syncReadDisabledRef.current) {
      ticks = await readPresentTicksSync();
      if (ticks) {
        syncReadFailuresRef.current = 0;
      } else {
        syncReadFailuresRef.current += 1;
        if (syncReadFailuresRef.current >= 3) {
          syncReadDisabledRef.current = true;
          logMessage('Sync read failed three times; falling back to sequential servo reads for this session.', 'warn');
        }
      }
    }
    if (!ticks) ticks = await readPresentTicksSequential();
    if (!ticks) return null;

    const measuredJoints = calibratedTicksToJoints(ticks, feetechCalibration);
    if (!measuredJoints) return null;
    return { ticks, joints: measuredJoints };
  }, [connectionType, feetechCalibration, logMessage, readPresentTicksSequential, readPresentTicksSync]);

  /**
   * The tick values the app would write for a given commanded JointState —
   * exactly what `queueHardwareMotion` puts on the bus. Recorded alongside the
   * measured ticks so the action channel is in the same units as the state
   * channel.
   */
  const commandedJointsToTicks = useCallback((commanded: JointState) => {
    if (!feetechCalibration) return null;
    return Object.fromEntries(
      jointsToCalibratedTicks(commanded, feetechCalibration).map(({ id, position }) => [id, position]),
    ) as Record<number, number>;
  }, [feetechCalibration]);

  // This sends only PING and READ requests; neither command asks a servo to move.
  const handleVerifyFeetechBus = useCallback(async () => {
    if (!portWriterRef.current || connectionType !== 'webserial') {
      logMessage('Open a direct WebSerial connection before verifying the Feetech bus.', 'error');
      return;
    }

    // Trace the wire for this run only, then switch off so episode sampling stays quiet.
    // The window is generous: 6 servos x up to 3 queries x a 300ms timeout is ~5s worst case.
    serialTraceRef.current = true;
    window.setTimeout(() => { serialTraceRef.current = false; }, 15_000);

    setIsMotionArmed(false);
    setIsCalibrationVerified(false);
    hardwareMotionBlockReasonRef.current = null;
    logMessage('Verifying Feetech bus: sending non-motion PING packets to servo IDs 1–6…', 'info');

    const found: number[] = [];
    const positions: Record<number, number> = {};
    const calibrationMatches: number[] = [];

    for (const servo of SO_ARM100_SERVOS) {
      const pingResponse = await queryFeetechPacket(servo.hardwareId, buildPingPacket(servo.hardwareId));
      if (!pingResponse) continue;

      found.push(servo.hardwareId);
      const positionResponse = await queryFeetechPacket(
        servo.hardwareId,
        buildReadPacket(servo.hardwareId, 56, 2),
      );
      if (positionResponse && positionResponse.parameters.length >= 2) {
        positions[servo.hardwareId] = readSignedWord(positionResponse.parameters, FEETECH_SIGN_BIT.presentPosition);
      }

      if (feetechCalibration) {
        const limitsResponse = await queryFeetechPacket(
          servo.hardwareId,
          buildReadPacket(servo.hardwareId, 9, 4),
        );
        const offsetResponse = await queryFeetechPacket(
          servo.hardwareId,
          buildReadPacket(servo.hardwareId, 31, 2),
        );
        const expected = feetechCalibration[servo.id];
        const limitsMatch = limitsResponse && limitsResponse.parameters.length >= 4
          && (limitsResponse.parameters[0] | (limitsResponse.parameters[1] << 8)) === expected.minTick
          && (limitsResponse.parameters[2] | (limitsResponse.parameters[3] << 8)) === expected.maxTick;
        const offsetMatch = offsetResponse && offsetResponse.parameters.length >= 2
          && readSignedWord(offsetResponse.parameters, FEETECH_SIGN_BIT.homingOffset) === expected.homingOffset;

        if (limitsMatch && offsetMatch) calibrationMatches.push(servo.hardwareId);
      }
    }

    setVerifiedServoIds(found);
    setServoPositions(positions);
    const calibrationVerified = Boolean(feetechCalibration) && calibrationMatches.length === SO_ARM100_SERVOS.length;
    setIsCalibrationVerified(calibrationVerified);

    if (feetechCalibration && found.length === SO_ARM100_SERVOS.length) {
      const measuredJoints = calibratedTicksToJoints(positions, feetechCalibration);
      if (measuredJoints) {
        updateDisplayJoints(measuredJoints);
        logMessage('3D twin synchronized from the verified servo positions. No motion packet was sent.', 'info');
      }
    }

    if (found.length === 0) {
      logMessage('No Feetech replies received. Check that this is a TTL half-duplex servo adapter, power is on, the bus cable is connected, and the baud rate is 1,000,000.', 'error');
    } else {
      const positionSummary = Object.entries(positions).map(([id, position]) => `S${id}=${position}`).join(', ');
      logMessage(`Verified ${found.length}/6 Feetech servos: ${found.map(id => `S${id}`).join(', ')}.${positionSummary ? ` Present ticks: ${positionSummary}.` : ''}`, found.length === 6 ? 'info' : 'warn');
    }

    if (feetechCalibration && found.length === SO_ARM100_SERVOS.length) {
      if (calibrationVerified) {
        logMessage('Servo calibration registers match the saved follower "white" calibration.', 'info');
      } else {
        const mismatched = SO_ARM100_SERVOS
          .filter(servo => !calibrationMatches.includes(servo.hardwareId))
          .map(servo => `S${servo.hardwareId}`)
          .join(', ');
        logMessage(`Calibration mismatch on ${mismatched}. Motion remains locked; use LeRobot calibration to write the saved values before continuing.`, 'error');
      }
    }
  }, [connectionType, feetechCalibration, logMessage, queryFeetechPacket, updateDisplayJoints]);

  const handleToggleMotionArm = useCallback(() => {
    if (!feetechCalibration) {
      logMessage('Direct motion remains locked: VITE_FEETECH_CALIBRATION is missing or invalid.', 'error');
      return;
    }
    if (verifiedServoIds.length !== SO_ARM100_SERVOS.length || !isCalibrationVerified) {
      logMessage('Direct motion remains locked: all six servos must reply and their stored calibration must match before arming.', 'error');
      return;
    }

    if (isMotionArmed) {
      setIsMotionArmed(false);
      clearQueuedHardwareMotion();
      logMessage('Direct calibrated motion disarmed. Queued packets cleared.', 'warn');
      return;
    }

    if (window.confirm('Arm calibrated physical motion? Ensure the arm is clear, supported, and its calibration has been verified.')) {
      hardwareMotionBlockReasonRef.current = null;
      setIsMotionArmed(true);
      logMessage('Direct calibrated motion armed. Start with a small, slow joint adjustment.', 'warn');
    }
  }, [clearQueuedHardwareMotion, feetechCalibration, isCalibrationVerified, isMotionArmed, logMessage, verifiedServoIds.length]);

  // Connect WebSocket (Wireless WiFi)
  const handleConnectWebSocket = (url: string) => {
    try {
      setConnectionStatus('connecting');
      const ws = new WebSocket(url);

      ws.onopen = () => {
        wsClientRef.current = ws;
        setConnectionType('websocket');
        setConnectionStatus('connected');
        logMessage(`Connected to Wireless Robot Node at ${url}`, 'info');
      };

      ws.onerror = (err) => {
        setConnectionStatus('error');
        logMessage(`WebSocket connection error to ${url}`, 'error');
      };

      ws.onclose = () => {
        setConnectionStatus('disconnected');
        logMessage('WebSocket disconnected', 'warn');
      };
    } catch (err: any) {
      logMessage(`WebSocket error: ${err.message}`, 'error');
    }
  };

  // Disconnect Hardware
  const handleDisconnect = async () => {
    clearQueuedHardwareMotion();
    setIsMotionArmed(false);
    setVerifiedServoIds([]);
    setServoPositions({});
    setIsCalibrationVerified(false);
    pendingFeetechResponsesRef.current.clear();
    serialReadLoopActiveRef.current = false;
    if (serialReaderRef.current) {
      try {
        await serialReaderRef.current.cancel();
        // cancel() only unblocks the pending read; the lock is dropped by the read
        // loop's own finally, one microtask later. Closing before that lands makes
        // port.close() reject with "port is already locked" -- and the swallowed
        // catch below turned that into a silently leaked file descriptor. Measured
        // 2026-08-17: Chrome still held fd 87 on /dev/ttyACM0 twenty minutes after
        // Disconnect, so lerobot could not open the follower at all ("Could not
        // connect on port '/dev/ttyACM0'"), and only quitting the browser freed it.
        await Promise.resolve();
        try {
          serialReaderRef.current.releaseLock();
        } catch {}
      } catch {}
      serialReaderRef.current = null;
    }
    if (portWriterRef.current) {
      try {
        portWriterRef.current.releaseLock();
      } catch (e) {}
      portWriterRef.current = null;
    }
    if (serialPortRef.current) {
      // A close() failure must be reported, not swallowed. The OS descriptor stays
      // open when this rejects, the port keeps its exclusive lock, and the next thing
      // to want it -- lerobot, a fresh connect, anything -- fails with EBUSY for a
      // reason nothing on screen explains. Whoever hits that deserves to be told the
      // browser still owns the port and has to be quit.
      try {
        await serialPortRef.current.close();
      } catch (e: any) {
        logMessage(
          `Could not release the serial port: ${e?.message ?? e}. The browser still `
          + 'holds it, so lerobot and any new connection will fail with "device busy" '
          + 'until Chrome is quit completely.',
          'error'
        );
      }
      serialPortRef.current = null;
      setFollowerSerialPort(null);
    }
    if (wsClientRef.current) {
      wsClientRef.current.close();
      wsClientRef.current = null;
    }

    setConnectionType('simulation');
    setConnectionStatus('connected');
    hardwareMotionBlockReasonRef.current = null;
    logMessage('Switched to Digital Twin Simulation Mode.', 'info');
  };

  /**
   * A physical unplug orphans the WebSerial handle, and until now nothing noticed.
   *
   * The read loop above cannot detect it: on a removed device `reader.read()`
   * neither resolves with `done` nor reliably rejects, so it sits waiting on a port
   * whose device node the kernel has already destroyed. connectionStatus therefore
   * stayed 'connected', ConnectionBar kept rendering "Verify Servos", and every PING
   * went into a dead descriptor -- so verification returned 0/6 and the motion button
   * stayed locked with nothing on screen explaining why.
   *
   * Measured on 2026-08-17: Chrome held an fd opened at 12:35 against a /dev/ttyACM1
   * that the kernel had recreated at 12:57 after a replug. The calibration and the
   * servos were both fine; the handle was 22 minutes stale.
   *
   * navigator.serial fires 'disconnect' when the device goes away, so listen and say
   * so. The dead port is deliberately NOT closed: close() on a removed device can
   * reject or hang, and the handle is worthless regardless -- dropping the refs and
   * telling the operator to reconnect is the whole fix. A replugged device always
   * needs a freshly selected port; no amount of retrying revives the old one.
   */
  useEffect(() => {
    const serial = (navigator as any).serial;
    if (!serial?.addEventListener) return;

    const handleSerialDisconnect = (event: any) => {
      const port = event.target ?? event.port;
      if (!port) return;

      if (port === leaderSerialPort) {
        logMessage(
          'Leader arm unplugged: its WebSerial handle is now dead. Reconnect the leader '
          + 'adapter in the Leader Arm panel and verify its bus again.',
          'error'
        );
        return;
      }
      if (port !== serialPortRef.current) return;

      serialReadLoopActiveRef.current = false;
      serialReaderRef.current = null;
      portWriterRef.current = null;
      serialPortRef.current = null;
      pendingFeetechResponsesRef.current.clear();
      setFollowerSerialPort(null);

      setVerifiedServoIds([]);
      setServoPositions({});
      setIsCalibrationVerified(false);
      setIsMotionArmed(false);
      setConnectionStatus('disconnected');
      hardwareMotionBlockReasonRef.current = 'Follower arm was unplugged.';
      logMessage(
        'Follower arm unplugged: the WebSerial handle is dead, verification is cleared '
        + 'and motion is locked. Reconnect the follower adapter and run Verify Servos -- '
        + 'a replugged device always needs a freshly selected port.',
        'error'
      );
    };

    serial.addEventListener('disconnect', handleSerialDisconnect);
    return () => serial.removeEventListener('disconnect', handleSerialDisconnect);
  }, [leaderSerialPort, logMessage]);

  // Telemetry Simulation Tick
  useEffect(() => {
    const timer = setInterval(() => {
      setTelemetry(prev => ({
        ...prev,
        voltage: 11.7 + Math.random() * 0.3,
        current: isPlaying ? 450 + Math.round(Math.random() * 200) : 180 + Math.round(Math.random() * 40),
        temp: 34 + Math.round(Math.random() * 2),
        packetHz: isPlaying ? 50 : 20
      }));
    }, 2000);

    return () => clearInterval(timer);
  }, [isPlaying]);

  // Sequence Playback Engine Loop
  useEffect(() => {
    if (!isPlaying || currentSequence.keyframes.length === 0) return;

    let isCancelled = false;
    let currentKfIndex = 0;

    const playStep = async () => {
      while (!isCancelled) {
        if (currentKfIndex >= currentSequence.keyframes.length) {
          if (currentSequence.loop) {
            currentKfIndex = 0;
          } else {
            setIsPlaying(false);
            setActiveKeyframeIndex(-1);
            logMessage(`Sequence "${currentSequence.title}" playback completed.`, 'info');
            break;
          }
        }

        const kf = currentSequence.keyframes[currentKfIndex];
        setActiveKeyframeIndex(currentKfIndex);
        logMessage(`Executing Keyframe ${currentKfIndex + 1}: ${kf.name}`, 'info');

        // Smooth Interpolation Motion over durationMs
        const startJoints = { ...jointsRef.current };
        const endJoints = kf.joints;
        const duration = Math.max(100, kf.durationMs / (currentSequence.speedMultiplier || 1.0));
        const startTime = performance.now();

        await new Promise<void>(resolve => {
          const animateStep = (now: number) => {
            if (isCancelled) return resolve();
            const elapsed = now - startTime;
            const progress = Math.min(1, elapsed / duration);

            const nextJoints = interpolateJoints(startJoints, endJoints, progress);
            handleJointChange(nextJoints);

            if (progress < 1) {
              requestAnimationFrame(animateStep);
            } else {
              handleJointChange(endJoints);
              resolve();
            }
          };
          requestAnimationFrame(animateStep);
        });

        if (isCancelled) break;

        // Pause Delay after reaching keyframe
        if (kf.delayAfterMs > 0) {
          await new Promise(r => setTimeout(r, kf.delayAfterMs / (currentSequence.speedMultiplier || 1.0)));
        }

        currentKfIndex++;
      }
    };

    playStep();

    return () => {
      isCancelled = true;
    };
  }, [isPlaying, currentSequence, handleJointChange, logMessage]);

  // Emergency Stop (E-Stop)
  const handleEStop = useCallback(() => {
    clearQueuedHardwareMotion();
    setIsMotionArmed(false);
    setIsPlaying(false);
    setActiveKeyframeIndex(-1);
    const torqueDisableCommand = import.meta.env.VITE_TORQUE_DISABLE_COMMAND;
    sendConfiguredSafetyCommand(
      import.meta.env.VITE_ESTOP_COMMAND || torqueDisableCommand,
      'EMERGENCY STOP'
    );
    if (connectionType === 'simulation' || torqueDisableCommand) {
      setIsTorqueEnabled(false);
    }
  }, [clearQueuedHardwareMotion, connectionType, sendConfiguredSafetyCommand]);

  const handleTorqueToggle = useCallback(() => {
    const next = !isTorqueEnabled;
    const command = next ? import.meta.env.VITE_TORQUE_ENABLE_COMMAND : import.meta.env.VITE_TORQUE_DISABLE_COMMAND;
    if (connectionType !== 'simulation' && !command) {
      logMessage(`Torque ${next ? 'enable' : 'disable'} is not configured for this hardware controller.`, 'error');
      return;
    }
    setIsTorqueEnabled(next);
    sendConfiguredSafetyCommand(command, `TORQUE ${next ? 'ENABLE' : 'DISABLE'}`);
  }, [connectionType, isTorqueEnabled, logMessage, sendConfiguredSafetyCommand]);

  // Keyboard Shortcuts Listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return; // Don't trigger when typing in inputs
      }

      if (e.code === 'Space') {
        e.preventDefault();
        setIsPlaying(prev => !prev);
      } else if (e.code === 'KeyE' || e.code === 'Escape') {
        e.preventDefault();
        handleEStop();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleEStop]);

  // Compute trajectory points for 3D overlay
  const trajectoryPoints = useMemo(
    () => currentSequence.keyframes.map(kf => forwardKinematics(kf.joints)),
    [currentSequence.keyframes]
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans antialiased selection:bg-amber-400 selection:text-zinc-950">
      {/* Top Connection & Header Bar */}
      <ConnectionBar
        connectionType={connectionType}
        connectionStatus={connectionStatus}
        telemetry={telemetry}
        verifiedServoIds={verifiedServoIds}
        servoPositions={servoPositions}
        isMotionArmed={isMotionArmed}
        hasFeetechCalibration={Boolean(feetechCalibration)}
        isCalibrationVerified={isCalibrationVerified}
        onConnectWebSerial={handleConnectWebSerial}
        onConnectWebSocket={handleConnectWebSocket}
        onVerifyFeetechBus={handleVerifyFeetechBus}
        onToggleMotionArm={handleToggleMotionArm}
        onDisconnect={handleDisconnect}
        onToggleSimulationMode={() => {
          setConnectionType('simulation');
          setConnectionStatus('connected');
          logMessage('Simulation Mode Enabled', 'info');
        }}
        onOpenConsole={() => setIsConsoleOpen(true)}
      />

      {/* Main Content Layout */}
      <main className="flex-1 max-w-[1600px] w-full mx-auto p-4 md:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (3D Digital Twin & Manual Controls) - 7 cols */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          {/* 3D Canvas */}
          <Suspense fallback={<LoadingPanel />}>
            <Arm3DCanvas
              joints={joints}
              showTrajectory={true}
              trajectoryPoints={trajectoryPoints}
              activeKeyframeIndex={activeKeyframeIndex}
            />
          </Suspense>

          {/* Control Mode Tab Switcher */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 bg-zinc-900 p-1.5 rounded-sm border border-zinc-800">
            <button
              onClick={() => setControlTab('fk')}
              className={`py-2.5 text-xs font-black uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 ${
                controlTab === 'fk'
                  ? 'bg-amber-400 text-zinc-950 shadow-md'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
              }`}
            >
              <Sliders className="w-4 h-4" />
              <span>FK Joints</span>
            </button>

            <button
              onClick={() => setControlTab('ik')}
              className={`py-2.5 text-xs font-black uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 ${
                controlTab === 'ik'
                  ? 'bg-amber-400 text-zinc-950 shadow-md'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
              }`}
            >
              <Target className="w-4 h-4" />
              <span>3D IK Target</span>
            </button>

            <button
              onClick={() => setControlTab('leader')}
              className={`py-2.5 text-xs font-black uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 ${
                controlTab === 'leader'
                  ? 'bg-amber-400 text-zinc-950 shadow-md'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
              }`}
            >
              <Radio className="w-4 h-4" />
              <span>Leader Arm</span>
            </button>

            <button
              onClick={() => setControlTab('teleop')}
              className={`py-2.5 text-xs font-black uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 ${
                controlTab === 'teleop'
                  ? 'bg-amber-400 text-zinc-950 shadow-md'
                  : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
              }`}
            >
              <Cpu className="w-4 h-4" />
              <span>Gamepad & Vision</span>
            </button>

            <button
              onClick={() => setControlTab('dataset')}
              className={`py-2.5 text-xs font-black uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 ${
                controlTab === 'dataset' ? 'bg-amber-400 text-zinc-950 shadow-md' : 'text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800'
              }`}
            >
              <Database className="w-4 h-4" />
              <span>Dataset Lab</span>
            </button>
          </div>

          {/* Tab Content Panels */}
          {controlTab === 'fk' && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
              <Suspense fallback={<LoadingPanel />}>
                <JointControls
                  joints={joints}
                  onChange={handleJointChange}
                  isTorqueEnabled={isTorqueEnabled}
                  onToggleTorque={handleTorqueToggle}
                  disabled={isPlaying}
                />
              </Suspense>
              <Suspense fallback={<LoadingPanel />}>
                <GamepadVisionOverlay
                  joints={joints}
                  onJointChange={handleJointChange}
                  disabled={isPlaying}
                  enableGamepadControl={false}
                  showGamepadStatus={false}
                  readMeasuredFollowerState={readMeasuredFollowerState}
                  commandedJointsToTicks={commandedJointsToTicks}
                />
              </Suspense>
            </div>
          )}

          {controlTab === 'ik' && (
            <Suspense fallback={<LoadingPanel />}>
              <KinematicsIKPanel
                joints={joints}
                onChangeJoints={handleJointChange}
                disabled={isPlaying}
              />
            </Suspense>
          )}

          <div className={controlTab === 'leader' ? '' : 'hidden'}>
            <Suspense fallback={<LoadingPanel />}>
              <LeaderArmPanel
              leaderState={leaderState}
              followerJoints={joints}
              onUpdateLeaderState={(partial) => setLeaderState(prev => ({ ...prev, ...partial }))}
              onSyncLeaderToFollower={(leaderJoints) => handleJointChange(leaderJoints)}
              onSaveRecordedSequence={(recordedKeyframes) => {
                const newSeq: Sequence = {
                  id: `seq-leader-${Date.now()}`,
                  title: `Leader Demonstration (${recordedKeyframes.length} pts)`,
                  description: `Recorded via physical Leader Arm hand teleoperation demonstration on ${new Date().toLocaleTimeString()}.`,
                  category: 'custom',
                  keyframes: recordedKeyframes,
                  loop: false,
                  speedMultiplier: 1.0,
                  createdAt: new Date().toISOString()
                };
                setCurrentSequence(newSeq);
                logMessage(`Loaded ${recordedKeyframes.length} Leader teleoperation keyframes into Sequence Studio!`, 'info');
              }}
              followerSerialPort={followerSerialPort}
              onLeaderSerialPortChange={setLeaderSerialPort}
              />
            </Suspense>
          </div>

          {controlTab === 'teleop' && (
            <Suspense fallback={<LoadingPanel />}>
              <GamepadVisionOverlay
                joints={joints}
                onJointChange={handleJointChange}
                disabled={isPlaying}
                readMeasuredFollowerState={readMeasuredFollowerState}
                commandedJointsToTicks={commandedJointsToTicks}
              />
            </Suspense>
          )}

          {controlTab === 'dataset' && (
            <Suspense fallback={<LoadingPanel />}>
              <DatasetPanel
                onLoadPolicyPreview={(sequence) => {
                  setCurrentSequence(sequence);
                  if (sequence.keyframes.length > 0) updateDisplayJoints(sequence.keyframes[0].joints);
                  logMessage(`Loaded ${sequence.keyframes.length} offline policy preview keyframes. Hardware output remains disabled.`, 'info');
                }}
              />
            </Suspense>
          )}
        </div>

        {/* Right Column (Sequence Studio & AI Generator) - 5 cols */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Emergency Stop Banner */}
          <div className="bg-rose-950/40 border border-rose-500/40 p-4 rounded-sm flex items-center justify-between shadow-lg">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-rose-500/20 rounded-sm text-rose-400 border border-rose-500/30">
                <ShieldAlert className="w-5 h-5 animate-pulse" />
              </div>
              <div>
                <h3 className="text-xs font-black text-rose-300 uppercase tracking-widest font-mono">
                  EMERGENCY STOP SAFETY
                </h3>
                <p className="text-[11px] text-rose-300/80 font-bold">Press 'E' or 'Esc' to halt playback and clear queued motion. Configure a hardware command before physical use.</p>
              </div>
            </div>

            <button
              onClick={handleEStop}
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white font-black text-xs rounded-sm shadow-lg border border-rose-400/30 transition uppercase tracking-wider"
            >
              E-STOP
            </button>
          </div>

          {/* Sequence Studio */}
          <Suspense fallback={<LoadingPanel />}>
            <SequenceStudio
            currentSequence={currentSequence}
            onUpdateSequence={setCurrentSequence}
            currentJoints={joints}
            onPosePreview={updateDisplayJoints}
            isPlaying={isPlaying}
            activeKeyframeIndex={activeKeyframeIndex}
            onStartPlayback={() => setIsPlaying(true)}
            onPausePlayback={() => setIsPlaying(false)}
            onStopPlayback={() => {
              setIsPlaying(false);
              setActiveKeyframeIndex(-1);
              if (currentSequence.keyframes.length > 0) {
                updateDisplayJoints(currentSequence.keyframes[0].joints);
              }
            }}
            onOpenAiGenerator={() => setIsAiGeneratorOpen(true)}
            />
          </Suspense>
        </div>
      </main>

      {/* AI Generator Modal */}
      {isAiGeneratorOpen && (
        <Suspense fallback={<LoadingPanel />}>
          <AISequenceGenerator
            isOpen={isAiGeneratorOpen}
            onClose={() => setIsAiGeneratorOpen(false)}
            onApplyGeneratedSequence={(seq) => {
              setCurrentSequence(seq);
              if (seq.keyframes.length > 0) {
                updateDisplayJoints(seq.keyframes[0].joints);
              }
            }}
          />
        </Suspense>
      )}

      {/* Serial Telemetry Console Modal */}
      {isConsoleOpen && (
        <Suspense fallback={<LoadingPanel />}>
          <TelemetryLogConsole
            isOpen={isConsoleOpen}
            onClose={() => setIsConsoleOpen(false)}
            telemetry={telemetry}
            onSendRawCommand={sendSerialCommand}
            onClearLogs={() => setTelemetry(prev => ({ ...prev, logs: [] }))}
          />
        </Suspense>
      )}
    </div>
  );
}
