import React, { useState, useEffect, useMemo, useRef } from 'react';
import { 
  Radio, 
  Usb, 
  Wifi, 
  Play, 
  Square, 
  RefreshCw, 
  Activity, 
  Sliders, 
  ShieldAlert, 
  Sparkles, 
  Download, 
  Check, 
  Zap, 
  Compass, 
  Save,
  ArrowRightLeft
} from 'lucide-react';
import { JointState, LeaderArmState, Keyframe, ServoId } from '../types';
import { SO_ARM100_SERVOS } from '../constants';
import { buildPingPacket, buildReadPacket, FEETECH_SIGN_BIT, FeetechPacket, parseFeetechPackets, readSignedWord } from '../utils/feetech';

const LEADER_BAUD_RATE = 1_000_000;
const LEADER_REPLY_TIMEOUT_MS = 150;

type LeaderCalibration = Record<ServoId, { minTick: number; maxTick: number; homingOffset: number }>;
type LeaderConnectionStatus = 'disconnected' | 'verifying' | 'ready' | 'simulation' | 'error';

function readLeaderCalibration(): LeaderCalibration | null {
  const raw = import.meta.env.VITE_LEADER_FEETECH_CALIBRATION;
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<LeaderCalibration>;
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
    return isValid ? parsed as LeaderCalibration : null;
  } catch {
    return null;
  }
}

function leaderTicksToJoints(positions: Record<number, number>, calibration: LeaderCalibration): JointState | null {
  const joints = {} as JointState;
  for (const servo of SO_ARM100_SERVOS) {
    const position = positions[servo.hardwareId];
    if (!Number.isFinite(position)) return null;
    const calibrationEntry = calibration[servo.id];
    const normalized = (position - calibrationEntry.minTick) / (calibrationEntry.maxTick - calibrationEntry.minTick);
    joints[servo.id] = Math.max(
      servo.minAngle,
      Math.min(servo.maxAngle, servo.minAngle + normalized * (servo.maxAngle - servo.minAngle)),
    );
  }
  return joints;
}

interface LeaderArmPanelProps {
  leaderState: LeaderArmState;
  followerJoints: JointState;
  onUpdateLeaderState: (newState: Partial<LeaderArmState>) => void;
  onSyncLeaderToFollower: (joints: JointState) => void;
  onSaveRecordedSequence: (keyframes: Keyframe[]) => void;
  followerSerialPort: any;
  onLeaderSerialPortChange: (port: any | null) => void;
}

export const LeaderArmPanel: React.FC<LeaderArmPanelProps> = ({
  leaderState,
  followerJoints,
  onUpdateLeaderState,
  onSyncLeaderToFollower,
  onSaveRecordedSequence,
  followerSerialPort,
  onLeaderSerialPortChange
}) => {
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [recordedFrames, setRecordedFrames] = useState<Keyframe[]>([]);
  const [recordingTimer, setRecordingTimer] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<LeaderConnectionStatus>('disconnected');
  const [connectionMessage, setConnectionMessage] = useState('Select the dedicated leader serial adapter, then verify its encoder bus.');
  const [observedLeaderRegisters, setObservedLeaderRegisters] = useState<Record<number, { minTick: number; maxTick: number; homingOffset: number }>>({});
  const leaderJointsRef = useRef(leaderState.joints);
  const recordedFrameCountRef = useRef(0);
  const onUpdateLeaderStateRef = useRef(onUpdateLeaderState);
  const onSyncLeaderToFollowerRef = useRef(onSyncLeaderToFollower);
  const isMirroringRef = useRef(leaderState.isMirroring);
  const leaderPortRef = useRef<any>(null);
  const leaderWriterRef = useRef<any>(null);
  const leaderReaderRef = useRef<ReadableStreamDefaultReader<Uint8Array> | null>(null);
  const leaderReadLoopActiveRef = useRef(false);
  const leaderPollingActiveRef = useRef(false);
  const leaderRxBufferRef = useRef<Uint8Array>(new Uint8Array());
  const pendingResponsesRef = useRef(new Map<number, (packet: FeetechPacket) => void>());
  const leaderCalibration = useMemo(readLeaderCalibration, []);

  useEffect(() => {
    leaderJointsRef.current = leaderState.joints;
  }, [leaderState.joints]);

  useEffect(() => {
    onUpdateLeaderStateRef.current = onUpdateLeaderState;
  }, [onUpdateLeaderState]);

  useEffect(() => {
    onSyncLeaderToFollowerRef.current = onSyncLeaderToFollower;
  }, [onSyncLeaderToFollower]);

  useEffect(() => {
    isMirroringRef.current = leaderState.isMirroring;
  }, [leaderState.isMirroring]);

  // Recording timer logic
  useEffect(() => {
    let interval: any;
    if (leaderState.isRecording) {
      interval = setInterval(() => {
        setRecordingTimer(t => t + 1);

        // Record frame snapshot
        const newKf: Keyframe = {
          id: `kf-rec-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
          name: `Hand Demo Pose ${recordedFrameCountRef.current + 1}`,
          durationMs: 250,
          delayAfterMs: 0,
          joints: { ...leaderJointsRef.current }
        };

        recordedFrameCountRef.current += 1;
        setRecordedFrames(prev => [...prev, newKf]);
        onUpdateLeaderStateRef.current({ recordedFramesCount: recordedFrameCountRef.current });
      }, 250); // 4 FPS recording snapshot rate
    } else {
      setRecordingTimer(0);
    }

    return () => clearInterval(interval);
  }, [leaderState.isRecording]);

  const waitForLeaderResponse = (servoId: number, timeoutMs = LEADER_REPLY_TIMEOUT_MS) => (
    new Promise<FeetechPacket | null>((resolve) => {
      const timeout = window.setTimeout(() => {
        pendingResponsesRef.current.delete(servoId);
        resolve(null);
      }, timeoutMs);
      pendingResponsesRef.current.set(servoId, (packet) => {
        window.clearTimeout(timeout);
        resolve(packet);
      });
    })
  );

  const startLeaderReader = async (port: any) => {
    if (!port.readable) return;
    const reader = port.readable.getReader();
    leaderReaderRef.current = reader;
    leaderReadLoopActiveRef.current = true;

    try {
      while (leaderReadLoopActiveRef.current) {
        const { value, done } = await reader.read();
        if (done) break;
        if (!value) continue;
        const combined = new Uint8Array(leaderRxBufferRef.current.length + value.length);
        combined.set(leaderRxBufferRef.current);
        combined.set(value, leaderRxBufferRef.current.length);
        const { packets, remainder } = parseFeetechPackets(combined);
        leaderRxBufferRef.current = remainder.length > 1024 ? remainder.slice(-1024) : remainder;
        packets.forEach((packet) => {
          const resolve = pendingResponsesRef.current.get(packet.id);
          if (resolve) {
            pendingResponsesRef.current.delete(packet.id);
            resolve(packet);
          }
        });
      }
    } catch (error) {
      if (leaderReadLoopActiveRef.current) {
        setConnectionStatus('error');
        setConnectionMessage(`Leader serial read failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      }
    } finally {
      if (leaderReaderRef.current === reader) leaderReaderRef.current = null;
      try {
        reader.releaseLock();
      } catch {}
    }
  };

  const queryLeader = async (servoId: number, packet: Uint8Array) => {
    if (!leaderWriterRef.current) throw new Error('Leader serial port is not open.');
    const response = waitForLeaderResponse(servoId);
    try {
      await leaderWriterRef.current.write(packet);
      return await response;
    } catch (error) {
      pendingResponsesRef.current.delete(servoId);
      throw error;
    }
  };

  const startLeaderPolling = () => {
    if (!leaderCalibration || leaderPollingActiveRef.current) return;
    leaderPollingActiveRef.current = true;
    void (async () => {
      while (leaderPollingActiveRef.current) {
        const cycleStartedAt = performance.now();
        const positions: Record<number, number> = {};
        for (const servo of SO_ARM100_SERVOS) {
          const response = await queryLeader(servo.hardwareId, buildReadPacket(servo.hardwareId, 56, 2));
          if (response?.parameters.length >= 2) {
            positions[servo.hardwareId] = readSignedWord(response.parameters, FEETECH_SIGN_BIT.presentPosition);
          }
        }
        const joints = leaderTicksToJoints(positions, leaderCalibration);
        if (joints) {
          leaderJointsRef.current = joints;
          onUpdateLeaderStateRef.current({ joints });
          if (isMirroringRef.current) onSyncLeaderToFollowerRef.current(joints);
        }
        const waitMs = Math.max(0, 50 - (performance.now() - cycleStartedAt));
        await new Promise((resolve) => window.setTimeout(resolve, waitMs));
      }
    })().catch((error) => {
      leaderPollingActiveRef.current = false;
      setConnectionStatus('error');
      setConnectionMessage(`Leader encoder polling failed: ${error instanceof Error ? error.message : 'unknown error'}`);
    });
  };

  const verifyLeaderBus = async () => {
    if (!leaderCalibration) {
      setConnectionStatus('error');
      setConnectionMessage('Leader calibration is missing or invalid. Add VITE_LEADER_FEETECH_CALIBRATION before verification.');
      return;
    }

    setConnectionStatus('verifying');
    setConnectionMessage('Verifying IDs 1–6 with PING and READ only. No leader motion command will be sent.');
    const found: number[] = [];
    const calibrationMatches: number[] = [];
    const observed: Record<number, { minTick: number; maxTick: number; homingOffset: number }> = {};

    try {
      for (const servo of SO_ARM100_SERVOS) {
        const pingResponse = await queryLeader(servo.hardwareId, buildPingPacket(servo.hardwareId));
        if (!pingResponse) continue;
        found.push(servo.hardwareId);

        const limitsResponse = await queryLeader(servo.hardwareId, buildReadPacket(servo.hardwareId, 9, 4));
        const offsetResponse = await queryLeader(servo.hardwareId, buildReadPacket(servo.hardwareId, 31, 2));
        const expected = leaderCalibration[servo.id];
        if (limitsResponse?.parameters.length >= 4 && offsetResponse?.parameters.length >= 2) {
          observed[servo.hardwareId] = {
            minTick: limitsResponse.parameters[0] | (limitsResponse.parameters[1] << 8),
            maxTick: limitsResponse.parameters[2] | (limitsResponse.parameters[3] << 8),
            homingOffset: readSignedWord(offsetResponse.parameters, FEETECH_SIGN_BIT.homingOffset)
          };
        }
        const limitsMatch = limitsResponse?.parameters.length >= 4
          && (limitsResponse.parameters[0] | (limitsResponse.parameters[1] << 8)) === expected.minTick
          && (limitsResponse.parameters[2] | (limitsResponse.parameters[3] << 8)) === expected.maxTick;
        const offsetMatch = offsetResponse?.parameters.length >= 2
          && readSignedWord(offsetResponse.parameters, FEETECH_SIGN_BIT.homingOffset) === expected.homingOffset;
        if (limitsMatch && offsetMatch) calibrationMatches.push(servo.hardwareId);
      }
    } catch (error) {
      setConnectionStatus('error');
      setConnectionMessage(`Leader verification failed: ${error instanceof Error ? error.message : 'unknown error'}`);
      return;
    }

    if (found.length !== SO_ARM100_SERVOS.length) {
      setObservedLeaderRegisters(observed);
      setConnectionStatus('error');
      setConnectionMessage(`Leader verification found ${found.length}/6 servos. Check its power, cable, adapter, and 1,000,000 baud connection.`);
      return;
    }
    if (calibrationMatches.length !== SO_ARM100_SERVOS.length) {
      setObservedLeaderRegisters(observed);
      const mismatched = SO_ARM100_SERVOS
        .filter((servo) => !calibrationMatches.includes(servo.hardwareId))
        .map((servo) => `S${servo.hardwareId}`)
        .join(', ');
      setConnectionStatus('error');
      const observedSummary = Object.entries(observed)
        .map(([id, value]) => `S${id}=${value.minTick}/${value.maxTick}/${value.homingOffset}`)
        .join(', ');
      setConnectionMessage(`Leader calibration mismatch on ${mismatched}. Passive reads remain blocked. Observed min/max/offset: ${observedSummary || 'unavailable'}.`);
      return;
    }

    setObservedLeaderRegisters(observed);
    setConnectionStatus('ready');
    setConnectionMessage('Leader IDs and calibration registers match. Passive 20 Hz encoder reads are active; no leader motion command has been sent.');
    startLeaderPolling();
  };

  const handleDisconnectLeader = async () => {
    leaderPollingActiveRef.current = false;
    onUpdateLeaderState({ connected: false, isMirroring: false, isRecording: false });
    leaderReadLoopActiveRef.current = false;
    pendingResponsesRef.current.clear();
    try {
      await leaderReaderRef.current?.cancel();
    } catch {}
    try {
      leaderWriterRef.current?.releaseLock();
    } catch {}
    leaderWriterRef.current = null;
    try {
      await leaderPortRef.current?.close();
    } catch {}
    leaderPortRef.current = null;
    onLeaderSerialPortChange(null);
    setConnectionStatus('disconnected');
    setConnectionMessage('Leader disconnected.');
  };

  // Opens the dedicated leader bus, then verifies it using PING/READ packets only.
  const handleConnectLeaderSerial = async () => {
    if (!('serial' in navigator)) {
      setConnectionStatus('error');
      setConnectionMessage('WebSerial is unavailable. Use a current Chrome or Edge browser.');
      return;
    }
    if (!leaderCalibration) {
      setConnectionStatus('error');
      setConnectionMessage('Leader calibration is missing. Add the saved black leader calibration to .env.local, restart the dev server, then reconnect.');
      return;
    }

    try {
      const port = await (navigator as any).serial.requestPort();
      if (port === followerSerialPort) {
        setConnectionStatus('error');
        setConnectionMessage('That USB serial port is already assigned to the follower. Select the other USB Single Serial device for the leader.');
        setShowConnectModal(false);
        return;
      }
      await port.open({ baudRate: LEADER_BAUD_RATE });
      leaderPortRef.current = port;
      onLeaderSerialPortChange(port);
      leaderWriterRef.current = port.writable.getWriter();
      leaderRxBufferRef.current = new Uint8Array();
      void startLeaderReader(port);
      onUpdateLeaderState({ connected: true, connectionType: 'webserial', deviceName: 'Leader Arm (passive Feetech read)' });
      setShowConnectModal(false);
      await verifyLeaderBus();
    } catch (error) {
      await handleDisconnectLeader();
      setShowConnectModal(false);
      setConnectionStatus('error');
      setConnectionMessage(`Leader connection failed: ${error instanceof Error ? error.message : 'port selection cancelled'}`);
    }
  };

  // Simulate leader arm joint movement when drag/knob tested
  const handleSimulateLeaderChange = (joint: keyof JointState, val: number) => {
    const nextJoints = { ...leaderState.joints, [joint]: val };
    onUpdateLeaderState({ joints: nextJoints });
    if (leaderState.isMirroring) {
      onSyncLeaderToFollower(nextJoints);
    }
  };

  const handleToggleMirroring = () => {
    const canMirror = leaderState.connectionType === 'simulation' || connectionStatus === 'ready';
    if (!canMirror) {
      setConnectionMessage('Live mirroring remains locked until the physical leader has passed its non-motion verification.');
      return;
    }
    const next = !leaderState.isMirroring;
    if (next && !window.confirm('Enable leader-to-follower mirroring? The follower must be separately verified and explicitly armed before it can move. Start with one small leader movement in a clear workspace.')) {
      return;
    }
    onUpdateLeaderState({ isMirroring: next });
    if (next) {
      onSyncLeaderToFollower(leaderState.joints);
    }
  };

  const handleStartRecording = () => {
    recordedFrameCountRef.current = 0;
    setRecordedFrames([]);
    onUpdateLeaderState({ isRecording: true });
  };

  const handleStopRecording = () => {
    onUpdateLeaderState({ isRecording: false });
  };

  const handleExportRecording = () => {
    if (recordedFrames.length === 0) return;
    onSaveRecordedSequence(recordedFrames);
  };

  useEffect(() => () => {
    void handleDisconnectLeader();
  }, []);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-amber-400 font-bold block mb-0.5">
            LeRobot Bilateral Teleoperation
          </span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight flex items-center gap-2">
            Leader Arm Controller
            <span className="text-xs bg-zinc-800 text-amber-400 px-2.5 py-1 rounded-sm border border-zinc-700 font-mono font-bold uppercase not-italic">
              SO-ARM100 Leader Mode
            </span>
          </h2>
        </div>

        {/* Quick Connection Switch */}
        <div className="flex items-center gap-2">
          {leaderState.connected ? (
            <div className="flex items-center gap-2">
              {/* One label per state.
                  This collapsed 'disconnected', 'verifying' AND 'error' into a single
                  LEADER_UNVERIFIED, so a verification still in flight looked identical
                  to a hard failure and to never having connected -- while a green
                  pulsing dot said "fine" through all three. On 2026-08-17 that badge
                  is what sent an hour of debugging into the wrong half of the system:
                  it was read as "the leader arm is broken" when the arm was perfect and
                  the real message was sitting in connectionMessage below. The actual
                  reason always lives there; this is only ever a summary. */}
              <span className={`border px-3 py-1.5 rounded-sm text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-2 ${
                connectionStatus === 'ready' || connectionStatus === 'simulation'
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : connectionStatus === 'error'
                    ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              }`}>
                <span className={`w-2 h-2 rounded-full ${
                  connectionStatus === 'ready' || connectionStatus === 'simulation'
                    ? 'bg-emerald-400 animate-ping'
                    : connectionStatus === 'error'
                      ? 'bg-rose-400'
                      : 'bg-amber-400 animate-ping'
                }`} />
                <span>{
                  connectionStatus === 'ready' ? 'LEADER_READY'
                    : connectionStatus === 'simulation' ? 'LEADER_SIMULATED'
                    : connectionStatus === 'verifying' ? 'LEADER_VERIFYING'
                    : connectionStatus === 'error' ? 'LEADER_ERROR'
                    : 'LEADER_DISCONNECTED'
                }</span>
              </span>
              <button
                onClick={() => void handleDisconnectLeader()}
                className="px-3.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold uppercase rounded-sm border border-zinc-700"
              >
                Disconnect
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowConnectModal(true)}
              className="px-4 py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm shadow-[0_0_15px_rgba(251,191,36,0.3)] transition flex items-center gap-2"
            >
              <Radio className="w-4 h-4" />
              <span>Connect Leader Hardware...</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Status & Mirror Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Mirroring Sync Toggle */}
        <div className="bg-zinc-950 p-5 rounded-sm border border-zinc-800 flex flex-col justify-between gap-4">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                <ArrowRightLeft className="w-4 h-4 text-amber-400" />
                Live Teleoperation Mirroring
              </span>
              {leaderState.isMirroring ? (
                <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-sm border border-emerald-500/30 font-mono font-bold uppercase">
                  ACTIVE_SYNCING
                </span>
              ) : (
                <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-sm border border-zinc-700 font-mono font-bold uppercase">
                  STANDBY
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-2 leading-relaxed">
              Physical leader telemetry is passive-read only. Mirroring stays locked until all six IDs and calibration registers match; follower motion still requires its separate arm step.
            </p>
          </div>

          <button
            onClick={handleToggleMirroring}
            disabled={leaderState.connectionType !== 'simulation' && connectionStatus !== 'ready'}
            className={`w-full py-3 font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-2 shadow ${
              leaderState.isMirroring
                ? 'bg-emerald-500 hover:bg-emerald-400 text-zinc-950'
                : 'bg-amber-400 hover:bg-amber-300 text-zinc-950 shadow-[0_0_15px_rgba(251,191,36,0.3)] disabled:cursor-not-allowed disabled:opacity-40'
            }`}
          >
            <Zap className="w-4 h-4 fill-current" />
            <span>{leaderState.isMirroring ? 'STOP MIRRORING' : 'ENABLE LIVE MIRROR MODE'}</span>
          </button>
        </div>

        {/* LeRobot Hand Demonstration Recorder */}
        <div className="bg-zinc-950 p-5 rounded-sm border border-zinc-800 flex flex-col justify-between gap-4">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                Demonstration Trajectory Collector
              </span>
              {leaderState.isRecording && (
                <span className="text-[10px] bg-rose-500/10 text-rose-400 px-2 py-0.5 rounded-sm border border-rose-500/30 font-mono font-bold uppercase animate-pulse">
                  REC ({recordingTimer}s)
                </span>
              )}
            </div>
            <p className="text-xs text-zinc-400 mt-2 leading-relaxed">
              Record physical hand-guided demonstrations for imitation learning or sequence playback.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {!leaderState.isRecording ? (
              <button
                onClick={handleStartRecording}
                className="flex-1 py-3 bg-rose-600 hover:bg-rose-500 text-white font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-2 shadow"
              >
                <Play className="w-4 h-4 fill-current" />
                <span>Start Recording Demo</span>
              </button>
            ) : (
              <button
                onClick={handleStopRecording}
                className="flex-1 py-3 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-2 shadow"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>Stop Recording ({recordedFrames.length} Frames)</span>
              </button>
            )}

            {recordedFrames.length > 0 && !leaderState.isRecording && (
              <button
                onClick={handleExportRecording}
                className="px-4 py-3 bg-zinc-800 hover:bg-zinc-700 text-amber-400 font-black text-xs uppercase tracking-tight rounded-sm border border-zinc-700 transition flex items-center gap-1.5"
                title="Send trajectory to Sequence Studio"
              >
                <Save className="w-4 h-4" />
                <span>Save Sequence</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Leader Arm Joint Encoders Readout / Simulation Control */}
      <div className="bg-zinc-950 p-5 rounded-sm border border-zinc-800 space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <span className="text-xs font-black uppercase tracking-widest text-zinc-300 font-mono">
            Leader Arm Joint Encoder Telemetry
          </span>
          <span className="text-[10px] text-zinc-500 font-mono font-bold uppercase">
            {connectionStatus === 'ready' ? 'PASSIVE PHYSICAL ENCODERS ACTIVE' : connectionStatus === 'simulation' ? 'VIRTUAL LEADER ENCODER TEST' : 'ENCODER READS UNVERIFIED'}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {(['base', 'shoulder', 'elbow', 'wristPitch', 'wristRoll', 'gripper'] as Array<keyof JointState>).map((joint) => {
            const val = leaderState.joints[joint];
            const isDeg = joint !== 'gripper';
            return (
              <div key={joint} className="bg-zinc-900 p-3 rounded-sm border border-zinc-800 flex flex-col gap-2">
                <div className="flex items-center justify-between text-[11px] font-bold">
                  <span className="text-zinc-400 uppercase tracking-tight">{joint}</span>
                  <span className="font-mono text-amber-400 font-black">
                    {val}{isDeg ? '°' : '%'}
                  </span>
                </div>
                <input
                  type="range"
                  min={joint === 'gripper' ? 0 : joint === 'shoulder' || joint === 'wristPitch' ? -90 : -180}
                  max={joint === 'gripper' ? 100 : joint === 'shoulder' || joint === 'wristPitch' ? 90 : 180}
                  value={val}
                  onChange={(e) => handleSimulateLeaderChange(joint, parseFloat(e.target.value))}
                  disabled={leaderState.connectionType === 'webserial'}
                  className="w-full h-1.5 bg-zinc-800 rounded-sm appearance-none cursor-pointer accent-amber-400"
                />
              </div>
            );
          })}
        </div>
      </div>

      <div className={`rounded-sm border px-4 py-3 text-xs ${
        connectionStatus === 'ready' || connectionStatus === 'simulation'
          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
          : connectionStatus === 'error'
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-100'
            : 'border-zinc-700 bg-zinc-950 text-zinc-400'
      }`}>
        <span className="font-black uppercase tracking-wider">Leader status: </span>{connectionMessage}
        {Object.keys(observedLeaderRegisters).length > 0 && (
          <div className="mt-2 font-mono text-[10px] leading-relaxed opacity-90">
            Observed registers (min/max/offset): {(Object.entries(observedLeaderRegisters) as Array<[string, { minTick: number; maxTick: number; homingOffset: number }]>)
              .map(([id, value]) => `S${id}=${value.minTick}/${value.maxTick}/${value.homingOffset}`)
              .join(' · ')}
          </div>
        )}
      </div>

      {/* Connection Setup Modal for Leader */}
      {showConnectModal && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-sm w-full max-w-md overflow-hidden shadow-2xl flex flex-col">
            <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-black uppercase italic text-zinc-100">Connect Leader Arm</h3>
              </div>
              <button
                onClick={() => setShowConnectModal(false)}
                className="text-zinc-400 hover:text-white text-xs px-2.5 py-1 rounded-sm bg-zinc-800 font-bold uppercase border border-zinc-700"
              >
                Close
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="bg-zinc-900 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-zinc-200 uppercase tracking-tight text-xs flex items-center gap-2">
                    <Usb className="w-4 h-4 text-cyan-400" />
                    Direct USB WebSerial for Leader Arm
                  </span>
                </div>
                <p className="text-zinc-400 text-[11px]">
                  Select the other dedicated USB adapter for the leader only. The app blocks the follower-assigned port, then checks against the leader `black` calibration using PING/READ packets only.
                </p>
                <button
                  onClick={handleConnectLeaderSerial}
                  className="w-full py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black uppercase tracking-tight rounded-sm transition text-xs"
                >
                  Select Leader USB Port & Verify
                </button>
              </div>

              <div className="bg-zinc-900 p-4 rounded-sm border border-zinc-800 flex flex-col gap-2">
                <span className="font-bold text-zinc-200 uppercase tracking-tight text-xs flex items-center gap-2">
                  <Compass className="w-4 h-4 text-emerald-400" />
                  Virtual Digital Twin Leader
                </span>
                <p className="text-zinc-400 text-[11px]">
                  Test bilateral teleoperation using virtual sliders or secondary on-screen twin controls.
                </p>
                <button
                  onClick={() => {
                    onUpdateLeaderState({
                      connected: true,
                      connectionType: 'simulation',
                      deviceName: 'Virtual Twin Leader Arm'
                    });
                    setConnectionStatus('simulation');
                    setConnectionMessage('Virtual leader enabled for UI-only testing.');
                    setShowConnectModal(false);
                  }}
                  className="w-full py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-bold uppercase text-xs rounded-sm border border-zinc-700 transition"
                >
                  Use Virtual Leader
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
