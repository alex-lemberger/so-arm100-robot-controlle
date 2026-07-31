/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { JointState, Sequence, ConnectionType, ConnectionStatus, TelemetryData, LeaderArmState, Keyframe } from './types';
import { DEFAULT_JOINTS, PRESET_SEQUENCES } from './constants';
import { interpolateJoints, formatSerialCommand, forwardKinematics } from './utils/kinematics';
import { ConnectionBar } from './components/ConnectionBar';
import { Arm3DCanvas } from './components/Arm3DCanvas';
import { JointControls } from './components/JointControls';
import { KinematicsIKPanel } from './components/KinematicsIKPanel';
import { SequenceStudio } from './components/SequenceStudio';
import { GamepadVisionOverlay } from './components/GamepadVisionOverlay';
import { LeaderArmPanel } from './components/LeaderArmPanel';
import { AISequenceGenerator } from './components/AISequenceGenerator';
import { TelemetryLogConsole } from './components/TelemetryLogConsole';
import { ShieldAlert, Zap, Cpu, Sparkles, Sliders, Target, Layers, Radio } from 'lucide-react';

export default function App() {
  // 1. Core Robot State
  const [joints, setJoints] = useState<JointState>(DEFAULT_JOINTS);
  const [isTorqueEnabled, setIsTorqueEnabled] = useState(true);

  // 2. Connectivity State
  const [connectionType, setConnectionType] = useState<ConnectionType>('simulation');
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connected');
  const portWriterRef = useRef<any>(null);
  const serialPortRef = useRef<any>(null);
  const wsClientRef = useRef<WebSocket | null>(null);

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
  const [controlTab, setControlTab] = useState<'fk' | 'ik' | 'teleop' | 'leader'>('fk');

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
  }, []);

  // Send raw serial string over WebSerial or WebSocket if connected
  const sendSerialCommand = useCallback(async (cmdString: string) => {
    logMessage(cmdString, 'tx');

    if (portWriterRef.current) {
      try {
        const encoder = new TextEncoder();
        await portWriterRef.current.write(encoder.encode(cmdString + '\n'));
      } catch (err: any) {
        logMessage(`WebSerial TX Error: ${err.message}`, 'error');
      }
    } else if (wsClientRef.current && wsClientRef.current.readyState === WebSocket.OPEN) {
      wsClientRef.current.send(cmdString);
    }
  }, [logMessage]);

  // Handle Joint change from FK sliders, IK solver, or Gamepad
  const handleJointChange = useCallback((newJoints: JointState) => {
    setJoints(newJoints);

    // If physical hardware connected, format & send serial command
    if (connectionType !== 'simulation') {
      const serialCmd = formatSerialCommand(newJoints, 100);
      sendSerialCommand(serialCmd);
    }
  }, [connectionType, sendSerialCommand]);

  // Connect WebSerial (Physical USB)
  const handleConnectWebSerial = async (baudRate: number) => {
    if (typeof window === 'undefined' || !('serial' in navigator)) {
      throw new Error('WebSerial API is not supported in this browser environment. Please use Simulation Mode.');
    }

    try {
      const port = await (navigator as any).serial.requestPort();
      await port.open({ baudRate });
      serialPortRef.current = port;

      const writer = port.writable.getWriter();
      portWriterRef.current = writer;

      setConnectionType('webserial');
      setConnectionStatus('connected');
      logMessage(`Connected to WebSerial Port at ${baudRate} baud`, 'info');
    } catch (err: any) {
      logMessage(`WebSerial Connection Failed: ${err.message}`, 'error');
      throw err;
    }
  };

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
    if (portWriterRef.current) {
      try {
        portWriterRef.current.releaseLock();
      } catch (e) {}
      portWriterRef.current = null;
    }
    if (serialPortRef.current) {
      try {
        await serialPortRef.current.close();
      } catch (e) {}
      serialPortRef.current = null;
    }
    if (wsClientRef.current) {
      wsClientRef.current.close();
      wsClientRef.current = null;
    }

    setConnectionType('simulation');
    setConnectionStatus('connected');
    logMessage('Switched to Digital Twin Simulation Mode.', 'info');
  };

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
      while (!isCancelled && isPlaying) {
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
        const startJoints = { ...joints };
        const endJoints = kf.joints;
        const duration = Math.max(100, kf.durationMs / (currentSequence.speedMultiplier || 1.0));
        const startTime = performance.now();

        await new Promise<void>(resolve => {
          const animateStep = (now: number) => {
            if (isCancelled || !isPlaying) return resolve();
            const elapsed = now - startTime;
            const progress = Math.min(1, elapsed / duration);

            const nextJoints = interpolateJoints(startJoints, endJoints, progress);
            setJoints(nextJoints);

            if (progress < 1) {
              requestAnimationFrame(animateStep);
            } else {
              setJoints(endJoints);
              resolve();
            }
          };
          requestAnimationFrame(animateStep);
        });

        if (isCancelled || !isPlaying) break;

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
  }, [isPlaying, currentSequence]);

  // Emergency Stop (E-Stop)
  const handleEStop = () => {
    setIsPlaying(false);
    setActiveKeyframeIndex(-1);
    setIsTorqueEnabled(false);
    logMessage('EMERGENCY STOP ENGAGED! Servo torque disabled.', 'error');
  };

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
  }, []);

  // Compute trajectory points for 3D overlay
  const trajectoryPoints = currentSequence.keyframes.map(kf => forwardKinematics(kf.joints));

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans antialiased selection:bg-amber-400 selection:text-zinc-950">
      {/* Top Connection & Header Bar */}
      <ConnectionBar
        connectionType={connectionType}
        connectionStatus={connectionStatus}
        telemetry={telemetry}
        onConnectWebSerial={handleConnectWebSerial}
        onConnectWebSocket={handleConnectWebSocket}
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
          <Arm3DCanvas
            joints={joints}
            onJointChange={handleJointChange}
            showTrajectory={true}
            trajectoryPoints={trajectoryPoints}
            activeKeyframeIndex={activeKeyframeIndex}
          />

          {/* Control Mode Tab Switcher */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-zinc-900 p-1.5 rounded-sm border border-zinc-800">
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
          </div>

          {/* Tab Content Panels */}
          {controlTab === 'fk' && (
            <JointControls
              joints={joints}
              onChange={handleJointChange}
              isTorqueEnabled={isTorqueEnabled}
              onToggleTorque={() => {
                const next = !isTorqueEnabled;
                setIsTorqueEnabled(next);
                logMessage(`Torque ${next ? 'ENABLED' : 'DISABLED'}`, 'info');
              }}
              disabled={isPlaying}
            />
          )}

          {controlTab === 'ik' && (
            <KinematicsIKPanel
              joints={joints}
              onChangeJoints={handleJointChange}
              disabled={isPlaying}
            />
          )}

          {controlTab === 'leader' && (
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
            />
          )}

          {controlTab === 'teleop' && (
            <GamepadVisionOverlay
              joints={joints}
              onJointChange={handleJointChange}
              disabled={isPlaying}
            />
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
                <p className="text-[11px] text-rose-300/80 font-bold">Press 'E' or 'Esc' key to instantly halt all motion.</p>
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
          <SequenceStudio
            currentSequence={currentSequence}
            onUpdateSequence={setCurrentSequence}
            currentJoints={joints}
            onPosePreview={setJoints}
            isPlaying={isPlaying}
            activeKeyframeIndex={activeKeyframeIndex}
            onStartPlayback={() => setIsPlaying(true)}
            onPausePlayback={() => setIsPlaying(false)}
            onStopPlayback={() => {
              setIsPlaying(false);
              setActiveKeyframeIndex(-1);
              if (currentSequence.keyframes.length > 0) {
                setJoints(currentSequence.keyframes[0].joints);
              }
            }}
            onOpenAiGenerator={() => setIsAiGeneratorOpen(true)}
          />
        </div>
      </main>

      {/* AI Generator Modal */}
      <AISequenceGenerator
        isOpen={isAiGeneratorOpen}
        onClose={() => setIsAiGeneratorOpen(false)}
        onApplyGeneratedSequence={(seq) => {
          setCurrentSequence(seq);
          if (seq.keyframes.length > 0) {
            setJoints(seq.keyframes[0].joints);
          }
        }}
      />

      {/* Serial Telemetry Console Modal */}
      <TelemetryLogConsole
        isOpen={isConsoleOpen}
        onClose={() => setIsConsoleOpen(false)}
        telemetry={telemetry}
        onSendRawCommand={sendSerialCommand}
        onClearLogs={() => setTelemetry(prev => ({ ...prev, logs: [] }))}
      />
    </div>
  );
}
