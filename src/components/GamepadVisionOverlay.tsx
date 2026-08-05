import React, { useEffect, useState, useRef } from 'react';
import { GamepadMapping, JointState } from '../types';
import { Gamepad, Camera, Crosshair, AlertCircle } from 'lucide-react';

type CameraRole = 'overview' | 'wrist';

type CameraSelections = Partial<Record<CameraRole, string>>;

const isTrainingCamera = (device: MediaDeviceInfo) => !/(facetime|(?:qbs|obs) virtual camera)/i.test(device.label);

interface CommandedJointSample {
  tMs: number;
  joints: JointState;
}

interface RecordingSession {
  startedAtIso: string;
  startedAtPerformanceMs: number;
  samples: CommandedJointSample[];
  recorders: Record<CameraRole, MediaRecorder>;
  chunks: Record<CameraRole, Blob[]>;
  cameraSettings: Record<CameraRole, MediaTrackSettings>;
  sampleTimerId: number;
  elapsedTimerId: number;
}

interface GamepadVisionOverlayProps {
  joints: JointState;
  onJointChange: (newJoints: JointState) => void;
  disabled?: boolean;
  enableGamepadControl?: boolean;
  showGamepadStatus?: boolean;
}

export const GamepadVisionOverlay: React.FC<GamepadVisionOverlayProps> = ({
  joints,
  onJointChange,
  disabled = false,
  enableGamepadControl = true,
  showGamepadStatus = true
}) => {
  const [gamepadState, setGamepadState] = useState<GamepadMapping | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraDevices, setCameraDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedCameraIds, setSelectedCameraIds] = useState<CameraSelections>({});
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isRecordingEpisode, setIsRecordingEpisode] = useState(false);
  const [recordingElapsedSeconds, setRecordingElapsedSeconds] = useState(0);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const overviewVideoRef = useRef<HTMLVideoElement>(null);
  const wristVideoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamsRef = useRef<Partial<Record<CameraRole, MediaStream>>>({});
  const recordingSessionRef = useRef<RecordingSession | null>(null);
  const jointsRef = useRef(joints);
  const onJointChangeRef = useRef(onJointChange);
  const disabledRef = useRef(disabled);

  useEffect(() => {
    jointsRef.current = joints;
  }, [joints]);

  useEffect(() => {
    onJointChangeRef.current = onJointChange;
  }, [onJointChange]);

  useEffect(() => {
    disabledRef.current = disabled || !enableGamepadControl;
  }, [disabled, enableGamepadControl]);

  // Poll Gamepad API
  useEffect(() => {
    let animationFrameId: number;
    let lastControlAt = performance.now();
    let lastStatusUpdateAt = 0;

    const pollGamepad = () => {
      const now = performance.now();
      if (typeof navigator !== 'undefined' && 'getGamepads' in navigator) {
        const gamepads = navigator.getGamepads();
        const activeGp = Array.from(gamepads).find(g => g !== null);

        if (activeGp) {
          // Status UI does not need to update at the browser frame rate.
          if (now - lastStatusUpdateAt >= 100) {
            lastStatusUpdateAt = now;
            setGamepadState({
              connected: true,
              id: activeGp.id,
              axes: Array.from(activeGp.axes),
              buttons: activeGp.buttons.map(b => b.pressed)
            });
          }

          // Tele-op at 30 Hz with time-based speed, independent of render rate.
          if (!disabledRef.current && now - lastControlAt >= 33) {
            const elapsedSeconds = Math.min(0.1, (now - lastControlAt) / 1000);
            lastControlAt = now;
            const axis0 = activeGp.axes[0] || 0; // Left Stick X -> Base
            const axis1 = activeGp.axes[1] || 0; // Left Stick Y -> Shoulder
            const axis2 = activeGp.axes[2] || 0; // Right Stick X -> Wrist Roll
            const axis3 = activeGp.axes[3] || 0; // Right Stick Y -> Elbow

            const deadzone = 0.15;
            let updated = false;
            const nextJoints = { ...jointsRef.current };
            const degreesPerSecond = 90;
            const gripperPercentPerSecond = 120;

            if (Math.abs(axis0) > deadzone) {
              nextJoints.base = Math.max(-180, Math.min(180, nextJoints.base - axis0 * degreesPerSecond * elapsedSeconds));
              updated = true;
            }
            if (Math.abs(axis1) > deadzone) {
              nextJoints.shoulder = Math.max(-90, Math.min(90, nextJoints.shoulder - axis1 * degreesPerSecond * elapsedSeconds));
              updated = true;
            }
            if (Math.abs(axis3) > deadzone) {
              nextJoints.elbow = Math.max(-120, Math.min(120, nextJoints.elbow - axis3 * degreesPerSecond * elapsedSeconds));
              updated = true;
            }
            if (Math.abs(axis2) > deadzone) {
              nextJoints.wristRoll = Math.max(-180, Math.min(180, nextJoints.wristRoll + axis2 * degreesPerSecond * elapsedSeconds));
              updated = true;
            }

            // Triggers for Gripper
            if (activeGp.buttons[6]?.pressed) { // L2 -> Open
              nextJoints.gripper = Math.min(100, nextJoints.gripper + gripperPercentPerSecond * elapsedSeconds);
              updated = true;
            }
            if (activeGp.buttons[7]?.pressed) { // R2 -> Close
              nextJoints.gripper = Math.max(0, nextJoints.gripper - gripperPercentPerSecond * elapsedSeconds);
              updated = true;
            }

            if (updated) {
              const roundedJoints = {
                base: Math.round(nextJoints.base * 10) / 10,
                shoulder: Math.round(nextJoints.shoulder * 10) / 10,
                elbow: Math.round(nextJoints.elbow * 10) / 10,
                wristPitch: nextJoints.wristPitch,
                wristRoll: Math.round(nextJoints.wristRoll * 10) / 10,
                gripper: Math.round(nextJoints.gripper)
              };
              jointsRef.current = roundedJoints;
              onJointChangeRef.current(roundedJoints);
            }
          }
        } else {
          setGamepadState(previous => previous === null ? previous : null);
        }
      }
      animationFrameId = requestAnimationFrame(pollGamepad);
    };

    pollGamepad();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const releaseCameras = () => {
    (Object.values(cameraStreamsRef.current) as Array<MediaStream | undefined>)
      .forEach((stream) => stream?.getTracks().forEach((track) => track.stop()));
    cameraStreamsRef.current = {};
    [overviewVideoRef, wristVideoRef].forEach((ref) => {
      if (ref.current) ref.current.srcObject = null;
    });
    setCameraActive(false);
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
  };

  const stopEpisodeRecording = async () => {
    const session = recordingSessionRef.current;
    if (!session) return;

    recordingSessionRef.current = null;
    window.clearInterval(session.sampleTimerId);
    window.clearInterval(session.elapsedTimerId);
    setIsRecordingEpisode(false);
    setRecordingElapsedSeconds(0);
    setSaveStatus('saving');
    setSaveMessage('Saving episode to the server…');

    await Promise.all((Object.values(session.recorders) as MediaRecorder[]).map((recorder) => new Promise<void>((resolve) => {
      if (recorder.state === 'inactive') {
        resolve();
        return;
      }
      recorder.addEventListener('stop', () => resolve(), { once: true });
      recorder.stop();
    })));

    const filePrefix = `so-arm100-episode-${session.startedAtIso.replace(/[:.]/g, '-')}`;
    const videoBlobs = (['overview', 'wrist'] as const).map((role) => {
      const recorder = session.recorders[role];
      const mimeType = recorder.mimeType || 'video/webm';
      const extension = mimeType.includes('mp4') ? 'mp4' : 'webm';
      return { role, mimeType, extension, blob: new Blob(session.chunks[role], { type: mimeType }) };
    });

    const metadata = {
      schemaVersion: 1,
      startedAt: session.startedAtIso,
      durationMs: Math.round(performance.now() - session.startedAtPerformanceMs),
      observations: {
        overview: { file: `overview.${videoBlobs[0].extension}`, settings: session.cameraSettings.overview },
        wrist: { file: `wrist.${videoBlobs[1].extension}`, settings: session.cameraSettings.wrist }
      },
      actions: {
        type: 'commanded_joint_target',
        unit: { base: 'degrees', shoulder: 'degrees', elbow: 'degrees', wristPitch: 'degrees', wristRoll: 'degrees', gripper: 'percent' },
        sampleRateHz: 20,
        samples: session.samples
      },
      note: 'Joint samples are commanded UI targets, not measured follower-arm position telemetry.'
    };

    // Browser download is the fallback path now, not the primary one — used
    // only if the server save fails, so a recorded demonstration is never
    // silently lost.
    const fallbackToDownload = (reason: string) => {
      videoBlobs.forEach(({ role, extension, blob }) => {
        downloadBlob(blob, `${filePrefix}-${role}.${extension}`);
      });
      downloadBlob(new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' }), `${filePrefix}-metadata.json`);
      setSaveStatus('error');
      setSaveMessage(`Could not save to the server (${reason}). Downloaded to your browser's Downloads folder instead.`);
    };

    try {
      const formData = new FormData();
      // Do not set a Content-Type header manually — fetch derives the
      // multipart boundary from the FormData instance itself.
      formData.append('metadata', JSON.stringify(metadata));
      videoBlobs.forEach(({ role, extension, blob }) => {
        formData.append(role, blob, `${role}.${extension}`);
      });

      const response = await fetch('/api/episodes', { method: 'POST', body: formData });
      if (!response.ok) {
        const body = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
        throw new Error(body.error || `HTTP ${response.status}`);
      }
      const result = await response.json() as { episodeDir: string };
      setSaveStatus('saved');
      setSaveMessage(`Episode saved to ${result.episodeDir}`);
    } catch (error) {
      fallbackToDownload(error instanceof Error ? error.message : 'unknown error');
    }
  };

  const stopCameras = () => {
    if (recordingSessionRef.current) {
      void stopEpisodeRecording().finally(releaseCameras);
      return;
    }
    releaseCameras();
  };

  const discoverCameras = async () => {
    if (!navigator.mediaDevices?.getUserMedia || !navigator.mediaDevices.enumerateDevices) {
      throw new Error('This browser does not support camera capture. Use a current Chrome or Edge browser.');
    }

    // Camera labels and reliable device IDs are generally only available after permission is granted.
    const permissionStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    permissionStream.getTracks().forEach((track) => track.stop());
    const devices = (await navigator.mediaDevices.enumerateDevices()).filter(
      (device) => device.kind === 'videoinput' && isTrainingCamera(device),
    );
    setCameraDevices(devices);
    return devices;
  };

  const startBothCameras = async () => {
    stopCameras();
    setCameraError(null);

    try {
      const devices = await discoverCameras();
      if (devices.length < 2) {
        throw new Error(`Two cameras are required, but the browser can only see ${devices.length}. Check USB connections and Chrome camera permissions.`);
      }

      const overviewId = devices.some((device) => device.deviceId === selectedCameraIds.overview)
        ? selectedCameraIds.overview!
        : devices[0].deviceId;
      const wristId = devices.some((device) => device.deviceId === selectedCameraIds.wrist && device.deviceId !== overviewId)
        ? selectedCameraIds.wrist!
        : devices.find((device) => device.deviceId !== overviewId)?.deviceId;

      if (!wristId) throw new Error('Choose two different camera devices for overview and wrist.');

      const selected = { overview: overviewId, wrist: wristId };
      setSelectedCameraIds(selected);

      const openCamera = (deviceId: string) => navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: { exact: deviceId },
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30, max: 30 }
        },
        audio: false
      });
      const overview = await openCamera(overviewId);
      let wrist: MediaStream;
      try {
        wrist = await openCamera(wristId);
      } catch (error) {
        overview.getTracks().forEach((track) => track.stop());
        throw error;
      }
      cameraStreamsRef.current = { overview, wrist };
      if (overviewVideoRef.current) overviewVideoRef.current.srcObject = overview;
      if (wristVideoRef.current) wristVideoRef.current.srcObject = wrist;
      setCameraActive(true);
    } catch (err) {
      stopCameras();
      setCameraError(err instanceof Error ? err.message : 'Could not start both camera streams.');
    }
  };

  const updateCameraSelection = (role: CameraRole, deviceId: string) => {
    setSelectedCameraIds((previous) => ({ ...previous, [role]: deviceId }));
  };

  const startEpisodeRecording = () => {
    setSaveStatus('idle');
    setSaveMessage(null);
    const overview = cameraStreamsRef.current.overview;
    const wrist = cameraStreamsRef.current.wrist;
    if (!overview || !wrist || !cameraActive) {
      setCameraError('Start both camera feeds before recording an episode.');
      return;
    }
    if (typeof MediaRecorder === 'undefined') {
      setCameraError('This browser does not support video recording. Use a current Chrome or Edge browser.');
      return;
    }

    try {
      const preferredMimeType = ['video/webm;codecs=vp9', 'video/webm', 'video/mp4']
        .find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
      const makeRecorder = (stream: MediaStream) => preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      const recorders = { overview: makeRecorder(overview), wrist: makeRecorder(wrist) };
      const chunks: Record<CameraRole, Blob[]> = { overview: [], wrist: [] };
      (['overview', 'wrist'] as const).forEach((role) => {
        recorders[role].addEventListener('dataavailable', (event) => {
          if (event.data.size > 0) chunks[role].push(event.data);
        });
      });

      const startedAtPerformanceMs = performance.now();
      const session: RecordingSession = {
        startedAtIso: new Date().toISOString(),
        startedAtPerformanceMs,
        samples: [{ tMs: 0, joints: { ...jointsRef.current } }],
        recorders,
        chunks,
        cameraSettings: {
          overview: overview.getVideoTracks()[0]?.getSettings() ?? {},
          wrist: wrist.getVideoTracks()[0]?.getSettings() ?? {}
        },
        sampleTimerId: window.setInterval(() => {
          const current = recordingSessionRef.current;
          if (!current) return;
          current.samples.push({
            tMs: Math.round(performance.now() - current.startedAtPerformanceMs),
            joints: { ...jointsRef.current }
          });
        }, 50),
        elapsedTimerId: window.setInterval(() => {
          const current = recordingSessionRef.current;
          if (current) setRecordingElapsedSeconds(Math.floor((performance.now() - current.startedAtPerformanceMs) / 1_000));
        }, 250)
      };

      recordingSessionRef.current = session;
      recorders.overview.start(1_000);
      recorders.wrist.start(1_000);
      setCameraError(null);
      setIsRecordingEpisode(true);
    } catch (error) {
      setCameraError(error instanceof Error ? error.message : 'Could not start the episode recorder.');
    }
  };

  useEffect(() => () => stopCameras(), []);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
            Wireless Tele-Op & Vision
          </span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight">
            {showGamepadStatus ? 'Joystick & Dual-Camera Stream' : 'Dual-Camera Stream'}
          </h2>
        </div>

        <button
          onClick={cameraActive ? stopCameras : startBothCameras}
          className={`px-3.5 py-1.5 rounded-sm text-xs font-black uppercase tracking-tight flex items-center gap-1.5 transition ${
            cameraActive
              ? 'bg-rose-500/10 text-rose-400 border border-rose-500/40'
              : 'bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border border-zinc-700'
          }`}
        >
          <Camera className="w-3.5 h-3.5" />
          <span>{cameraActive ? 'Stop Both Cameras' : 'Start Both Cameras'}</span>
        </button>
      </div>

      {/* Main Grid */}
      <div className={showGamepadStatus ? 'grid grid-cols-1 lg:grid-cols-[minmax(13rem,0.55fr)_minmax(0,1fr)] gap-4 items-start' : ''}>
        {/* Gamepad Status */}
        {showGamepadStatus && <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-tight text-zinc-200 flex items-center gap-1.5">
              <Gamepad className="w-4 h-4 text-amber-400" />
              Joystick Controller Mapping
            </span>
            {gamepadState?.connected ? (
              <span className={`text-[10px] px-2 py-0.5 rounded-sm font-mono font-bold uppercase border ${
                enableGamepadControl && !disabled
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : 'bg-zinc-800 text-zinc-400 border-zinc-700'
              }`}>
                {enableGamepadControl && !disabled ? 'ACTIVE' : 'MONITOR ONLY'}
              </span>
            ) : (
              <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-sm font-mono font-bold uppercase">
                NO_CONTROLLER
              </span>
            )}
          </div>

          {gamepadState?.connected ? (
            <div className="space-y-2 text-xs font-mono text-zinc-300">
              <div className="truncate text-zinc-400 text-[11px] font-bold">{gamepadState.id}</div>
              <div className="grid grid-cols-2 gap-2 text-[11px] bg-zinc-900 p-2.5 rounded-sm border border-zinc-800 font-bold">
                <div>LS-X (Base): <span className="text-amber-400">{gamepadState.axes[0]?.toFixed(2)}</span></div>
                <div>LS-Y (Shoulder): <span className="text-amber-400">{gamepadState.axes[1]?.toFixed(2)}</span></div>
                <div>RS-Y (Elbow): <span className="text-cyan-400">{gamepadState.axes[3]?.toFixed(2)}</span></div>
                <div>Triggers (Claw): <span className="text-emerald-400">L2/R2</span></div>
              </div>
            </div>
          ) : (
            <p className="text-xs text-zinc-400 leading-relaxed font-bold">
              Plug in an Xbox, PlayStation, or USB Gamepad controller to tele-operate the SO-ARM100 joints live using analog thumbsticks!
            </p>
          )}
        </div>}

        <div className="flex flex-col gap-4">
          {(['overview', 'wrist'] as const).map((role) => {
          const videoRef = role === 'overview' ? overviewVideoRef : wristVideoRef;
          const otherRole = role === 'overview' ? 'wrist' : 'overview';
          const roleLabel = role === 'overview' ? 'Overview Camera' : 'Wrist Camera';
          return (
            <div key={role} className="bg-zinc-950 rounded-sm border border-zinc-800 overflow-hidden">
              <div className="flex items-center justify-between gap-2 border-b border-zinc-800 px-3 py-2">
                <span className="text-[10px] font-black uppercase tracking-wider text-amber-400">{roleLabel}</span>
                <select
                  value={selectedCameraIds[role] ?? ''}
                  onChange={(event) => updateCameraSelection(role, event.target.value)}
                  disabled={cameraActive || cameraDevices.length === 0}
                  className="max-w-44 bg-zinc-900 border border-zinc-700 rounded-sm px-2 py-1 text-[10px] text-zinc-200 disabled:opacity-50"
                  aria-label={`Select ${roleLabel.toLowerCase()}`}
                >
                  {cameraDevices.length === 0 && <option value="">Detected after permission</option>}
                  {cameraDevices.map((device, deviceIndex) => (
                    <option
                      key={device.deviceId}
                      value={device.deviceId}
                      disabled={device.deviceId === selectedCameraIds[otherRole]}
                    >
                      {device.label || `Camera ${deviceIndex + 1}`}
                    </option>
                  ))}
                </select>
              </div>
              <div className="relative h-64 sm:h-72 flex items-center justify-center">
                <video ref={videoRef} autoPlay playsInline muted className={`w-full h-full object-cover ${cameraActive ? 'block' : 'hidden'}`} />
                {!cameraActive ? (
                  <div className="flex flex-col items-center gap-2 text-zinc-500 text-xs font-bold uppercase tracking-tight">
                    <Crosshair className="w-6 h-6 text-zinc-600" />
                    <span>{role.toUpperCase()} INACTIVE</span>
                  </div>
                ) : (
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                    <div className="w-16 h-16 border-2 border-dashed border-amber-400 rounded-sm flex items-center justify-center animate-pulse">
                      <Crosshair className="w-5 h-5 text-amber-400" />
                    </div>
                    <div className="absolute top-2 left-2 bg-zinc-900/90 px-2 py-0.5 rounded-sm text-[10px] font-mono text-amber-400 border border-zinc-700 font-bold uppercase">
                      {role.toUpperCase()} LIVE
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
          })}
        </div>
      </div>
      {cameraError && (
        <div className="flex items-start gap-2 rounded-sm border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
          <span>{cameraError}</span>
        </div>
      )}
      {saveStatus !== 'idle' && saveMessage && (
        <div className={`flex items-start gap-2 rounded-sm border px-3 py-2 text-xs ${
          saveStatus === 'error'
            ? 'border-rose-500/40 bg-rose-500/10 text-rose-200'
            : saveStatus === 'saving'
            ? 'border-zinc-700 bg-zinc-900 text-zinc-300'
            : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
        }`}>
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{saveMessage}</span>
        </div>
      )}
      <div className="flex flex-col gap-3 rounded-sm border border-zinc-800 bg-zinc-950 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-black uppercase tracking-wider text-zinc-100">Demonstration Recorder</span>
            {isRecordingEpisode && <span className="bg-rose-500/15 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-300">REC {recordingElapsedSeconds}s</span>}
          </div>
          <p className="mt-1 text-[11px] text-zinc-400">Records both videos and commanded joint targets at 20 Hz. It does not move the robot.</p>
        </div>
        <button
          onClick={isRecordingEpisode ? () => void stopEpisodeRecording() : startEpisodeRecording}
          disabled={!isRecordingEpisode && !cameraActive}
          className={`px-4 py-2 text-xs font-black uppercase tracking-tight transition disabled:cursor-not-allowed disabled:opacity-50 ${
            isRecordingEpisode
              ? 'border border-rose-500/40 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20'
              : 'border border-amber-400/40 bg-amber-400 text-zinc-950 hover:bg-amber-300'
          }`}
        >
          {isRecordingEpisode ? 'Stop & Save Episode' : 'Record Episode'}
        </button>
      </div>
    </div>
  );
};
