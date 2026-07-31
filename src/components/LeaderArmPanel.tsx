import React, { useState, useEffect, useRef } from 'react';
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
import { JointState, LeaderArmState, Keyframe } from '../types';

interface LeaderArmPanelProps {
  leaderState: LeaderArmState;
  followerJoints: JointState;
  onUpdateLeaderState: (newState: Partial<LeaderArmState>) => void;
  onSyncLeaderToFollower: (joints: JointState) => void;
  onSaveRecordedSequence: (keyframes: Keyframe[]) => void;
}

export const LeaderArmPanel: React.FC<LeaderArmPanelProps> = ({
  leaderState,
  followerJoints,
  onUpdateLeaderState,
  onSyncLeaderToFollower,
  onSaveRecordedSequence
}) => {
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [recordedFrames, setRecordedFrames] = useState<Keyframe[]>([]);
  const [recordingTimer, setRecordingTimer] = useState(0);
  const [simulatedLeaderAngle, setSimulatedLeaderAngle] = useState<JointState>(followerJoints);

  // Recording timer logic
  useEffect(() => {
    let interval: any;
    if (leaderState.isRecording) {
      interval = setInterval(() => {
        setRecordingTimer(t => t + 1);

        // Record frame snapshot
        const newKf: Keyframe = {
          id: `kf-rec-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
          name: `Hand Demo Pose ${recordedFrames.length + 1}`,
          durationMs: 250,
          delayAfterMs: 0,
          joints: { ...leaderState.joints }
        };

        setRecordedFrames(prev => [...prev, newKf]);
        onUpdateLeaderState({ recordedFramesCount: recordedFrames.length + 1 });
      }, 250); // 4 FPS recording snapshot rate
    } else {
      setRecordingTimer(0);
    }

    return () => clearInterval(interval);
  }, [leaderState.isRecording, leaderState.joints, recordedFrames.length]);

  // Handle connection simulation or WebSerial connect for Leader
  const handleConnectLeaderSerial = async () => {
    try {
      if ('serial' in navigator) {
        // Request port specifically for leader
        const port = await (navigator as any).serial.requestPort();
        await port.open({ baudRate: 1000000 });
        onUpdateLeaderState({
          connected: true,
          connectionType: 'webserial',
          deviceName: 'Leader Arm (USB Serial)'
        });
        setShowConnectModal(false);
      } else {
        // Fallback simulation
        onUpdateLeaderState({
          connected: true,
          connectionType: 'simulation',
          deviceName: 'Simulated Leader Arm (Twin)'
        });
        setShowConnectModal(false);
      }
    } catch (err) {
      console.warn("Leader serial connect cancelled or failed, falling back to simulated leader.");
      onUpdateLeaderState({
        connected: true,
        connectionType: 'simulation',
        deviceName: 'Simulated Leader Arm'
      });
      setShowConnectModal(false);
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
    const next = !leaderState.isMirroring;
    onUpdateLeaderState({ isMirroring: next });
    if (next) {
      onSyncLeaderToFollower(leaderState.joints);
    }
  };

  const handleStartRecording = () => {
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
              <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-3 py-1.5 rounded-sm text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <span>LEADER_ONLINE</span>
              </span>
              <button
                onClick={() => onUpdateLeaderState({ connected: false })}
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
              When enabled, moving the physical Leader Arm by hand immediately mirrors all joint telemetry directly to the Follower Arm and 3D Digital Twin in real-time.
            </p>
          </div>

          <button
            onClick={handleToggleMirroring}
            className={`w-full py-3 font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-2 shadow ${
              leaderState.isMirroring
                ? 'bg-emerald-500 hover:bg-emerald-400 text-zinc-950'
                : 'bg-amber-400 hover:bg-amber-300 text-zinc-950 shadow-[0_0_15px_rgba(251,191,36,0.3)]'
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
            {leaderState.connected ? 'PHYSICAL ENCODERS ACTIVE' : 'VIRTUAL LEADER ENCODER TEST'}
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
                  className="w-full h-1.5 bg-zinc-800 rounded-sm appearance-none cursor-pointer accent-amber-400"
                />
              </div>
            );
          })}
        </div>
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
                  Connect dedicated USB serial cable to the Leader arm's Feetech bus servos (unpowered / compliant encoders).
                </p>
                <button
                  onClick={handleConnectLeaderSerial}
                  className="w-full py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black uppercase tracking-tight rounded-sm transition text-xs"
                >
                  Select Leader USB Serial Port
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
