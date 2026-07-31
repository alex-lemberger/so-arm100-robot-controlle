import React, { useEffect, useState, useRef } from 'react';
import { GamepadMapping, JointState } from '../types';
import { Gamepad, Camera, Crosshair, AlertCircle } from 'lucide-react';

interface GamepadVisionOverlayProps {
  joints: JointState;
  onJointChange: (newJoints: JointState) => void;
  disabled?: boolean;
}

export const GamepadVisionOverlay: React.FC<GamepadVisionOverlayProps> = ({
  joints,
  onJointChange,
  disabled = false
}) => {
  const [gamepadState, setGamepadState] = useState<GamepadMapping | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Poll Gamepad API
  useEffect(() => {
    let animationFrameId: number;

    const pollGamepad = () => {
      if (typeof navigator !== 'undefined' && 'getGamepads' in navigator) {
        const gamepads = navigator.getGamepads();
        const activeGp = Array.from(gamepads).find(g => g !== null);

        if (activeGp) {
          setGamepadState({
            connected: true,
            id: activeGp.id,
            axes: Array.from(activeGp.axes),
            buttons: activeGp.buttons.map(b => b.pressed)
          });

          // Tele-op joystick control: drive arm based on joystick displacement
          if (!disabled) {
            const axis0 = activeGp.axes[0] || 0; // Left Stick X -> Base
            const axis1 = activeGp.axes[1] || 0; // Left Stick Y -> Shoulder
            const axis2 = activeGp.axes[2] || 0; // Right Stick X -> Wrist Roll
            const axis3 = activeGp.axes[3] || 0; // Right Stick Y -> Elbow

            const deadzone = 0.15;
            let updated = false;
            let nextJoints = { ...joints };

            if (Math.abs(axis0) > deadzone) {
              nextJoints.base = Math.max(-180, Math.min(180, nextJoints.base - axis0 * 1.5));
              updated = true;
            }
            if (Math.abs(axis1) > deadzone) {
              nextJoints.shoulder = Math.max(-90, Math.min(90, nextJoints.shoulder - axis1 * 1.5));
              updated = true;
            }
            if (Math.abs(axis3) > deadzone) {
              nextJoints.elbow = Math.max(-120, Math.min(120, nextJoints.elbow - axis3 * 1.5));
              updated = true;
            }

            // Triggers for Gripper
            if (activeGp.buttons[6]?.pressed) { // L2 -> Open
              nextJoints.gripper = Math.min(100, nextJoints.gripper + 3);
              updated = true;
            }
            if (activeGp.buttons[7]?.pressed) { // R2 -> Close
              nextJoints.gripper = Math.max(0, nextJoints.gripper - 3);
              updated = true;
            }

            if (updated) {
              onJointChange({
                base: Math.round(nextJoints.base * 10) / 10,
                shoulder: Math.round(nextJoints.shoulder * 10) / 10,
                elbow: Math.round(nextJoints.elbow * 10) / 10,
                wristPitch: nextJoints.wristPitch,
                wristRoll: Math.round(nextJoints.wristRoll * 10) / 10,
                gripper: Math.round(nextJoints.gripper)
              });
            }
          }
        } else {
          setGamepadState(null);
        }
      }
      animationFrameId = requestAnimationFrame(pollGamepad);
    };

    pollGamepad();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [joints, disabled, onJointChange]);

  // Toggle Camera Feed
  const toggleCamera = async () => {
    if (cameraActive) {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(t => t.stop());
        videoRef.current.srcObject = null;
      }
      setCameraActive(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraActive(true);
      } catch (err) {
        alert('Could not access camera feed. Check permissions.');
      }
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
            Wireless Tele-Op & Vision
          </span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight">Joystick & Camera Stream</h2>
        </div>

        <button
          onClick={toggleCamera}
          className={`px-3.5 py-1.5 rounded-sm text-xs font-black uppercase tracking-tight flex items-center gap-1.5 transition ${
            cameraActive
              ? 'bg-rose-500/10 text-rose-400 border border-rose-500/40'
              : 'bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border border-zinc-700'
          }`}
        >
          <Camera className="w-3.5 h-3.5" />
          <span>{cameraActive ? 'Stop Webcam Feed' : 'Launch Vision Overlay'}</span>
        </button>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Gamepad Status */}
        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-tight text-zinc-200 flex items-center gap-1.5">
              <Gamepad className="w-4 h-4 text-amber-400" />
              Joystick Controller Mapping
            </span>
            {gamepadState?.connected ? (
              <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-sm font-mono font-bold uppercase">
                ACTIVE
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
        </div>

        {/* Vision Feed Screen */}
        <div className="relative bg-zinc-950 h-36 rounded-sm border border-zinc-800 overflow-hidden flex items-center justify-center">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`w-full h-full object-cover ${cameraActive ? 'block' : 'hidden'}`}
          />

          {!cameraActive ? (
            <div className="flex flex-col items-center gap-2 text-zinc-500 text-xs font-bold uppercase tracking-tight">
              <Crosshair className="w-6 h-6 text-zinc-600" />
              <span>Camera Stream Inactive</span>
            </div>
          ) : (
            /* Vision Target Overlay Reticle */
            <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
              <div className="w-20 h-20 border-2 border-dashed border-amber-400 rounded-sm flex items-center justify-center animate-pulse">
                <Crosshair className="w-6 h-6 text-amber-400" />
              </div>
              <div className="absolute top-2 left-2 bg-zinc-900/90 px-2.5 py-0.5 rounded-sm text-[10px] font-mono text-amber-400 border border-zinc-700 font-bold uppercase">
                VISION RETICLE ACTIVE
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
