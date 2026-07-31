import React from 'react';
import { JointState, ServoId } from '../types';
import { SO_ARM100_SERVOS, DEFAULT_JOINTS, STOW_JOINTS } from '../constants';
import { Sliders, RotateCcw, ShieldCheck, Power, Zap, Hand } from 'lucide-react';

interface JointControlsProps {
  joints: JointState;
  onChange: (newJoints: JointState) => void;
  isTorqueEnabled: boolean;
  onToggleTorque: () => void;
  disabled?: boolean;
}

export const JointControls: React.FC<JointControlsProps> = ({
  joints,
  onChange,
  isTorqueEnabled,
  onToggleTorque,
  disabled = false
}) => {
  const handleSliderChange = (id: ServoId, value: number) => {
    onChange({
      ...joints,
      [id]: value
    });
  };

  const nudgeAngle = (id: ServoId, delta: number) => {
    const servo = SO_ARM100_SERVOS.find(s => s.id === id);
    if (!servo) return;
    const current = joints[id];
    const next = Math.max(servo.minAngle, Math.min(servo.maxAngle, current + delta));
    onChange({
      ...joints,
      [id]: Math.round(next * 10) / 10
    });
  };

  const applyPresetState = (target: JointState) => {
    onChange(target);
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-6">
      {/* Header bar */}
      <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
            Forward Kinematics
          </span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight">Manual Joint Control</h2>
        </div>

        {/* Global Action Tools */}
        <div className="flex items-center gap-2">
          <button
            onClick={onToggleTorque}
            className={`px-3.5 py-1.5 rounded-sm text-xs font-black uppercase tracking-tight flex items-center gap-1.5 transition ${
              isTorqueEnabled
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-500/20'
                : 'bg-rose-500/10 text-rose-400 border border-rose-500/40 hover:bg-rose-500/20'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            <span>{isTorqueEnabled ? 'TORQUE_ENGAGED' : 'TORQUE_OFF'}</span>
          </button>
        </div>
      </div>

      {/* Quick Pose Buttons */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <button
          onClick={() => applyPresetState(DEFAULT_JOINTS)}
          disabled={disabled}
          className="px-3.5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-xs font-black uppercase tracking-tight rounded-sm border border-zinc-700 transition flex items-center justify-center gap-2"
        >
          <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
          <span>Home State</span>
        </button>

        <button
          onClick={() => applyPresetState(STOW_JOINTS)}
          disabled={disabled}
          className="px-3.5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-xs font-black uppercase tracking-tight rounded-sm border border-zinc-700 transition flex items-center justify-center gap-2"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
          <span>Safe Stow</span>
        </button>

        <button
          onClick={() => applyPresetState({ base: 0, shoulder: 0, elbow: 0, wristPitch: 0, wristRoll: 0, gripper: 50 })}
          disabled={disabled}
          className="px-3.5 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-xs font-black uppercase tracking-tight rounded-sm border border-zinc-700 transition flex items-center justify-center gap-2"
        >
          <Zap className="w-3.5 h-3.5 text-amber-400" />
          <span>Zero Stand</span>
        </button>

        <button
          onClick={() => onChange({ ...joints, gripper: joints.gripper > 50 ? 0 : 90 })}
          disabled={disabled}
          className="px-3.5 py-2.5 bg-amber-400 text-zinc-950 hover:bg-amber-300 text-xs font-black uppercase tracking-tight rounded-sm shadow-[0_0_15px_rgba(251,191,36,0.3)] transition flex items-center justify-center gap-2"
        >
          <Hand className="w-3.5 h-3.5" />
          <span>{joints.gripper > 50 ? 'CLOSE CLAW' : 'OPEN CLAW'}</span>
        </button>
      </div>

      {/* Sliders Grid */}
      <div className="space-y-4">
        {SO_ARM100_SERVOS.map(servo => {
          const val = joints[servo.id];
          const isAtLimit = val <= servo.minAngle + 2 || val >= servo.maxAngle - 2;

          return (
            <div key={servo.id} className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-sm bg-zinc-800 border border-zinc-700 text-amber-400 font-mono font-black text-xs flex items-center justify-center">
                    S{servo.hardwareId}
                  </span>
                  <span className="font-bold text-sm text-zinc-100 uppercase tracking-tight">{servo.name}</span>
                </div>

                <div className="flex items-center gap-2">
                  {isAtLimit && (
                    <span className="text-[10px] font-mono font-bold text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-sm border border-amber-500/20 uppercase">
                      LIMIT_NEAR
                    </span>
                  )}
                  <span className="font-mono text-base font-bold text-amber-400 bg-zinc-900 px-3 py-1 rounded-sm border border-zinc-800">
                    {val}{servo.unit === 'deg' ? '°' : '%'}
                  </span>
                </div>
              </div>

              {/* Slider & Step Controls */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => nudgeAngle(servo.id, -10)}
                  disabled={disabled}
                  className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
                  title="Step -10"
                >
                  -10
                </button>
                <button
                  onClick={() => nudgeAngle(servo.id, -1)}
                  disabled={disabled}
                  className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
                  title="Step -1"
                >
                  -1
                </button>

                <input
                  type="range"
                  min={servo.minAngle}
                  max={servo.maxAngle}
                  step={1}
                  value={val}
                  disabled={disabled}
                  onChange={e => handleSliderChange(servo.id, parseFloat(e.target.value))}
                  className="flex-1 h-2 bg-zinc-800 rounded-sm appearance-none cursor-pointer accent-amber-400"
                />

                <button
                  onClick={() => nudgeAngle(servo.id, 1)}
                  disabled={disabled}
                  className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
                  title="Step +1"
                >
                  +1
                </button>
                <button
                  onClick={() => nudgeAngle(servo.id, 10)}
                  disabled={disabled}
                  className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
                  title="Step +10"
                >
                  +10
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
