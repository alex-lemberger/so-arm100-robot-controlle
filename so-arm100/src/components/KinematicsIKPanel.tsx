import React from 'react';
import { JointState, CartesianPos } from '../types';
import { forwardKinematics, inverseKinematics } from '../utils/kinematics';
import { Target, AlertCircle, CheckCircle2, ArrowUp, ArrowDown, ArrowLeft, ArrowRight } from 'lucide-react';

interface KinematicsIKPanelProps {
  joints: JointState;
  onChangeJoints: (newJoints: JointState) => void;
  disabled?: boolean;
}

export const KinematicsIKPanel: React.FC<KinematicsIKPanelProps> = ({
  joints,
  onChangeJoints,
  disabled = false
}) => {
  const currentCartesian = forwardKinematics(joints);
  const [target, setTarget] = React.useState<CartesianPos>(currentCartesian);

  // Keep target synced when joints change from external FK control
  React.useEffect(() => {
    setTarget(forwardKinematics(joints));
  }, [joints.base, joints.shoulder, joints.elbow, joints.wristPitch, joints.wristRoll]);

  // Try to solve IK whenever target coordinates change
  const ikResult = inverseKinematics(target, joints);
  const isReachable = ikResult !== null;

  const updateField = (key: keyof CartesianPos, delta: number) => {
    const nextTarget = {
      ...target,
      [key]: Math.round((target[key] + delta) * 10) / 10
    };
    setTarget(nextTarget);

    const solved = inverseKinematics(nextTarget, joints);
    if (solved) {
      onChangeJoints(solved);
    }
  };

  const handleDirectInputChange = (key: keyof CartesianPos, value: number) => {
    const nextTarget = {
      ...target,
      [key]: value
    };
    setTarget(nextTarget);

    const solved = inverseKinematics(nextTarget, joints);
    if (solved) {
      onChangeJoints(solved);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
            Inverse Kinematics Solver
          </span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight">3D Cartesian Targets</h2>
        </div>

        {/* Reachability Badge */}
        <div className="flex items-center gap-1.5 font-mono text-xs">
          {isReachable ? (
            <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/40 px-3 py-1 rounded-sm flex items-center gap-1.5 font-black uppercase tracking-wide">
              <CheckCircle2 className="w-4 h-4" />
              SOLVED_REACHABLE
            </span>
          ) : (
            <span className="bg-rose-500/10 text-rose-400 border border-rose-500/40 px-3 py-1 rounded-sm flex items-center gap-1.5 font-black uppercase tracking-wide">
              <AlertCircle className="w-4 h-4" />
              OUT_OF_WORKSPACE
            </span>
          )}
        </div>
      </div>

      {/* Cartesian Axis Controls */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* X Axis (Forward / Backward) */}
        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-400 font-bold uppercase tracking-tight">X-Axis (Depth)</span>
            <span className="font-mono text-amber-400 font-bold text-sm">{target.x} mm</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => updateField('x', -25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -25
            </button>
            <button
              onClick={() => updateField('x', -5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -5
            </button>
            <input
              type="number"
              value={target.x}
              disabled={disabled}
              onChange={e => handleDirectInputChange('x', parseFloat(e.target.value) || 0)}
              className="w-full bg-zinc-900 text-zinc-100 font-mono font-bold text-center text-xs py-1.5 rounded-sm border border-zinc-700"
            />
            <button
              onClick={() => updateField('x', 5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +5
            </button>
            <button
              onClick={() => updateField('x', 25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +25
            </button>
          </div>
        </div>

        {/* Y Axis (Lateral Left / Right) */}
        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-400 font-bold uppercase tracking-tight">Y-Axis (Lateral)</span>
            <span className="font-mono text-amber-400 font-bold text-sm">{target.y} mm</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => updateField('y', -25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -25
            </button>
            <button
              onClick={() => updateField('y', -5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -5
            </button>
            <input
              type="number"
              value={target.y}
              disabled={disabled}
              onChange={e => handleDirectInputChange('y', parseFloat(e.target.value) || 0)}
              className="w-full bg-zinc-900 text-zinc-100 font-mono font-bold text-center text-xs py-1.5 rounded-sm border border-zinc-700"
            />
            <button
              onClick={() => updateField('y', 5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +5
            </button>
            <button
              onClick={() => updateField('y', 25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +25
            </button>
          </div>
        </div>

        {/* Z Axis (Altitude Elevation) */}
        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-400 font-bold uppercase tracking-tight">Z-Axis (Elevation)</span>
            <span className="font-mono text-amber-400 font-bold text-sm">{target.z} mm</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => updateField('z', -25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -25
            </button>
            <button
              onClick={() => updateField('z', -5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              -5
            </button>
            <input
              type="number"
              value={target.z}
              disabled={disabled}
              onChange={e => handleDirectInputChange('z', parseFloat(e.target.value) || 0)}
              className="w-full bg-zinc-900 text-zinc-100 font-mono font-bold text-center text-xs py-1.5 rounded-sm border border-zinc-700"
            />
            <button
              onClick={() => updateField('z', 5)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +5
            </button>
            <button
              onClick={() => updateField('z', 25)}
              disabled={disabled}
              className="px-2.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700 transition"
            >
              +25
            </button>
          </div>
        </div>
      </div>

      {/* Orientation & Pitch/Roll Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex items-center justify-between">
          <span className="text-xs text-zinc-400 font-bold uppercase tracking-tight">Wrist Pitch Angle:</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => updateField('pitch', -10)}
              disabled={disabled}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700"
            >
              -10°
            </button>
            <span className="font-mono text-sm text-amber-400 font-bold w-16 text-center">{target.pitch}°</span>
            <button
              onClick={() => updateField('pitch', 10)}
              disabled={disabled}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700"
            >
              +10°
            </button>
          </div>
        </div>

        <div className="bg-zinc-950 p-4 rounded-sm border border-zinc-800 flex items-center justify-between">
          <span className="text-xs text-zinc-400 font-bold uppercase tracking-tight">Wrist Roll Angle:</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => updateField('roll', -15)}
              disabled={disabled}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700"
            >
              -15°
            </button>
            <span className="font-mono text-sm text-amber-400 font-bold w-16 text-center">{target.roll}°</span>
            <button
              onClick={() => updateField('roll', 15)}
              disabled={disabled}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-mono font-bold rounded-sm border border-zinc-700"
            >
              +15°
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
