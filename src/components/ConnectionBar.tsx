import React, { useState } from 'react';
import { ConnectionType, ConnectionStatus, TelemetryData } from '../types';
import { Wifi, Usb, Cpu, RefreshCw, AlertTriangle, ShieldCheck, Activity, Terminal } from 'lucide-react';

interface ConnectionBarProps {
  connectionType: ConnectionType;
  connectionStatus: ConnectionStatus;
  telemetry: TelemetryData;
  verifiedServoIds: number[];
  servoPositions: Record<number, number>;
  isMotionArmed: boolean;
  hasFeetechCalibration: boolean;
  isCalibrationVerified: boolean;
  onConnectWebSerial: (baudRate: number) => Promise<void>;
  onConnectWebSocket: (url: string) => void;
  onVerifyFeetechBus: () => Promise<void>;
  onToggleMotionArm: () => void;
  onDisconnect: () => void;
  onToggleSimulationMode: () => void;
  onOpenConsole: () => void;
}

export const ConnectionBar: React.FC<ConnectionBarProps> = ({
  connectionType,
  connectionStatus,
  telemetry,
  verifiedServoIds,
  servoPositions,
  isMotionArmed,
  hasFeetechCalibration,
  isCalibrationVerified,
  onConnectWebSerial,
  onConnectWebSocket,
  onVerifyFeetechBus,
  onToggleMotionArm,
  onDisconnect,
  onToggleSimulationMode,
  onOpenConsole
}) => {
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [wsUrl, setWsUrl] = useState('ws://192.168.4.1:8080');
  const [baudRate, setBaudRate] = useState(1000000); // SO-ARM100 STS3215 default 1Mbps
  const [connectingError, setConnectingError] = useState<string | null>(null);

  const isWebSerialAvailable = typeof window !== 'undefined' && 'serial' in navigator;

  const handleSerialConnectClick = async () => {
    setConnectingError(null);
    try {
      await onConnectWebSerial(baudRate);
      setShowConnectModal(false);
    } catch (err: any) {
      setConnectingError(err.message || 'WebSerial connection failed or was cancelled.');
    }
  };

  const handleWsConnectClick = () => {
    setConnectingError(null);
    onConnectWebSocket(wsUrl);
    setShowConnectModal(false);
  };

  return (
    <header className="bg-zinc-900/90 border-b border-zinc-800 px-6 py-4 flex flex-wrap items-center justify-between gap-4">
      {/* Brand & Connection Mode */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-sm bg-amber-400 text-zinc-950 flex items-center justify-center font-black text-lg shadow-[0_0_15px_rgba(251,191,36,0.4)]">
            SO
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
              Robotic Interface v2.4
            </span>
            <h1 className="text-2xl font-black tracking-tighter text-white uppercase italic leading-none flex items-center gap-2">
              SO-ARM100
              <span className="text-[10px] bg-zinc-800 text-amber-400 px-2 py-0.5 rounded-sm border border-zinc-700 font-mono font-bold uppercase not-italic">
                LeRobot Suite
              </span>
            </h1>
          </div>
        </div>
      </div>

      {/* Telemetry Live Gauges */}
      <div className="hidden lg:flex items-center gap-6 bg-zinc-950 px-5 py-2 rounded-sm border border-zinc-800 text-xs font-mono">
        <div>
          <p className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Voltage</p>
          <p className="text-emerald-400 font-bold text-sm">{telemetry.voltage.toFixed(1)} V</p>
        </div>
        <div className="border-l border-zinc-800 pl-5">
          <p className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Current</p>
          <p className="text-cyan-400 font-bold text-sm">{telemetry.current} mA</p>
        </div>
        <div className="border-l border-zinc-800 pl-5">
          <p className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Servo Temp</p>
          <p className="text-amber-400 font-bold text-sm">{telemetry.temp}°C</p>
        </div>
        <div className="border-l border-zinc-800 pl-5">
          <p className="text-[9px] uppercase tracking-widest text-zinc-500 font-bold">Packet Rate</p>
          <p className="text-zinc-100 font-bold text-sm">{telemetry.packetHz} Hz</p>
        </div>
      </div>

      {/* Connection Mode Selector & Status Button */}
      <div className="flex items-center gap-2">
        <button
          onClick={onOpenConsole}
          className="p-2.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-sm border border-zinc-700 transition"
          title="Open Serial Console Log"
        >
          <Terminal className="w-4 h-4 text-amber-400" />
        </button>

        {connectionStatus === 'connected' && connectionType !== 'simulation' ? (
          <div className="flex items-center gap-2">
            <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-3.5 py-1.5 rounded-sm text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>{connectionType}_ACTIVE</span>
            </span>

            {connectionType === 'webserial' && (
              <>
                <button
                  onClick={() => void onVerifyFeetechBus()}
                  className="px-3.5 py-1.5 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 text-xs font-black uppercase tracking-tight rounded-sm border border-cyan-500/30 transition"
                  title="Sends non-motion Feetech PING and present-position READ packets to IDs 1–6"
                >
                  Verify Servos {verifiedServoIds.length > 0 ? `${verifiedServoIds.length}/6` : ''}
                </button>

                <button
                  onClick={onToggleMotionArm}
                  disabled={!hasFeetechCalibration || !isCalibrationVerified || verifiedServoIds.length !== 6}
                  className={`px-3.5 py-1.5 text-xs font-black uppercase tracking-tight rounded-sm border transition ${
                    isMotionArmed
                      ? 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border-rose-500/40'
                      : hasFeetechCalibration && isCalibrationVerified && verifiedServoIds.length === 6
                        ? 'bg-amber-400 hover:bg-amber-300 text-zinc-950 border-amber-300'
                        : 'bg-zinc-800 text-zinc-500 border-zinc-700 cursor-not-allowed'
                  }`}
                  title={hasFeetechCalibration
                    ? verifiedServoIds.length === 6
                      ? isCalibrationVerified ? 'Explicitly arm calibrated physical motion' : 'Stored servo calibration does not yet match the saved calibration'
                      : 'Verify all six servos first'
                    : 'Add VITE_FEETECH_CALIBRATION to .env.local first'}
                >
                  {isMotionArmed ? 'Disarm Motion' : 'Arm Motion'}
                </button>
              </>
            )}

            <button
              onClick={onDisconnect}
              className="px-3.5 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-black uppercase tracking-tight rounded-sm border border-zinc-700 transition"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <button
            onClick={() => setShowConnectModal(true)}
            className="px-5 py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm shadow-[0_0_15px_rgba(251,191,36,0.3)] transition flex items-center gap-2"
          >
            <Usb className="w-4 h-4" />
            <span>Connect Hardware...</span>
          </button>
        )}
      </div>

      {connectionType === 'webserial' && connectionStatus === 'connected' && (
        <div className={`w-full -mt-2 text-[10px] font-mono border px-3 py-2 rounded-sm ${
          isMotionArmed
            ? 'bg-amber-400/10 border-amber-400/40 text-amber-200'
            : 'bg-zinc-950 border-zinc-800 text-zinc-400'
        }`}>
          {isMotionArmed
            ? 'CALIBRATED MOTION ARMED — keep clear and begin with a small joint adjustment.'
            : verifiedServoIds.length === 6
              ? `Servo bus verified. ${hasFeetechCalibration ? isCalibrationVerified ? 'Calibration matches; motion is still disarmed.' : 'Calibration does not match the servo registers; motion is locked.' : 'Add calibration before physical motion is available.'}`
              : 'Direct connection is open. Verify servo responses before physical motion is available.'}
          {Object.keys(servoPositions).length > 0 && ` Present ticks: ${Object.entries(servoPositions).map(([id, ticks]) => `S${id}=${ticks}`).join(', ')}.`}
        </div>
      )}

      {/* Wireless & Serial Connection Setup Modal */}
      {showConnectModal && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-sm w-full max-w-md overflow-hidden shadow-2xl flex flex-col">
            <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-black uppercase italic text-zinc-100">Connect Hardware</h3>
              </div>
              <button
                onClick={() => setShowConnectModal(false)}
                className="text-zinc-400 hover:text-white text-xs px-2.5 py-1 rounded-sm bg-zinc-800 font-bold uppercase border border-zinc-700"
              >
                Close
              </button>
            </div>

            <div className="p-5 flex flex-col gap-4 text-xs">
              {connectingError && (
                <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3 rounded-sm flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{connectingError}</span>
                </div>
              )}

              {/* WebSerial Option */}
              <div className="bg-zinc-900 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-bold text-zinc-200 uppercase tracking-tight">
                    <Usb className="w-4 h-4 text-cyan-400" />
                    <span>Option A: Direct USB WebSerial</span>
                  </div>
                  {isWebSerialAvailable ? (
                    <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded-sm border border-emerald-500/20 font-mono font-bold">
                      READY
                    </span>
                  ) : (
                    <span className="text-[10px] bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-sm border border-amber-500/20 font-mono font-bold">
                      SIMULATION
                    </span>
                  )}
                </div>
                <p className="text-zinc-400 text-[11px]">
                  Direct serial connection to Waveshare / Feetech STS3215 bus servo controller board.
                </p>

                <div className="flex items-center gap-2">
                  <label className="text-zinc-400 font-bold uppercase text-[10px]">Baud Rate:</label>
                  <select
                    value={baudRate}
                    onChange={e => setBaudRate(parseInt(e.target.value))}
                    className="bg-zinc-950 border border-zinc-700 text-zinc-200 rounded-sm px-2 py-1 font-mono text-xs"
                  >
                    <option value={1000000}>1,000,000 baud (STS3215 default)</option>
                    <option value={115200}>115,200 baud</option>
                    <option value={57600}>57,600 baud</option>
                  </select>
                </div>

                <button
                  onClick={handleSerialConnectClick}
                  className="w-full py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black uppercase tracking-tight rounded-sm transition"
                >
                  Select USB Serial Port & Connect
                </button>
              </div>

              {/* Wireless WiFi / WebSocket Option */}
              <div className="bg-zinc-900 p-4 rounded-sm border border-zinc-800 flex flex-col gap-3">
                <div className="flex items-center gap-2 font-bold text-zinc-200 uppercase tracking-tight">
                  <Wifi className="w-4 h-4 text-amber-400" />
                  <span>Option B: Wireless WiFi Bridge</span>
                </div>
                <p className="text-zinc-400 text-[11px]">
                  Connect wirelessly to ESP32, Raspberry Pi, or LeRobot python node on your WiFi network.
                </p>

                <input
                  type="text"
                  value={wsUrl}
                  onChange={e => setWsUrl(e.target.value)}
                  placeholder="ws://192.168.4.1:8080"
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 rounded-sm px-3 py-1.5 font-mono text-xs"
                />

                <button
                  onClick={handleWsConnectClick}
                  className="w-full py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-black uppercase tracking-tight rounded-sm border border-zinc-700 transition"
                >
                  Connect Wireless WebSocket
                </button>
              </div>

              {/* Digital Twin Simulation Mode */}
              <div className="bg-zinc-900 p-4 rounded-sm border border-zinc-800 flex items-center justify-between">
                <div>
                  <div className="font-bold text-zinc-200 uppercase tracking-tight flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>Digital Twin Simulation</span>
                  </div>
                  <p className="text-zinc-400 text-[11px] mt-0.5">
                    Test sequences & 3D kinematics safely without physical hardware.
                  </p>
                </div>

                <button
                  onClick={() => {
                    onToggleSimulationMode();
                    setShowConnectModal(false);
                  }}
                  className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-emerald-400 font-bold uppercase text-xs rounded-sm border border-zinc-700"
                >
                  Use Simulation
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};
