import React, { useState } from 'react';
import { TelemetryData } from '../types';
import { Terminal, Send, Trash2, Copy, Check, Shield } from 'lucide-react';

interface TelemetryLogConsoleProps {
  isOpen: boolean;
  onClose: () => void;
  telemetry: TelemetryData;
  onSendRawCommand: (cmd: string) => void;
  onClearLogs: () => void;
}

export const TelemetryLogConsole: React.FC<TelemetryLogConsoleProps> = ({
  isOpen,
  onClose,
  telemetry,
  onSendRawCommand,
  onClearLogs
}) => {
  const [customCmd, setCustomCmd] = useState('');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleSend = () => {
    if (!customCmd.trim()) return;
    onSendRawCommand(customCmd);
    setCustomCmd('');
  };

  const handleCopyLogs = () => {
    const text = telemetry.logs.map(l => `[${l.time}] ${l.type.toUpperCase()}: ${l.text}`).join('\n');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-zinc-950 border border-zinc-800 rounded-sm w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col h-[550px]">
        {/* Header */}
        <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-amber-400" />
            <h3 className="text-sm font-black uppercase tracking-tight text-white font-mono">SO-ARM100 Serial Command Console</h3>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-xs px-2.5 py-1 rounded-sm bg-zinc-800 font-bold uppercase border border-zinc-700"
          >
            Close
          </button>
        </div>

        {/* Telemetry Bar */}
        <div className="bg-zinc-950 px-4 py-2 border-b border-zinc-800 flex items-center justify-between text-xs font-mono text-zinc-400 font-bold uppercase">
          <div>Status: <span className="text-emerald-400">ONLINE</span></div>
          <div>Baud: <span className="text-amber-400">{telemetry.baudRate || 1000000} BPS</span></div>
          <div>Voltage: <span className="text-cyan-400">{telemetry.voltage.toFixed(1)}V</span></div>
          <div>Packet Rate: <span className="text-amber-400">{telemetry.packetHz} HZ</span></div>
        </div>

        {/* Terminal Screen */}
        <div className="flex-1 bg-zinc-950 p-4 font-mono text-xs overflow-y-auto space-y-1.5 text-zinc-300">
          {telemetry.logs.length === 0 ? (
            <div className="text-zinc-600 italic font-bold">No console logs yet...</div>
          ) : (
            telemetry.logs.map((log) => (
              <div key={log.id} className="flex items-start gap-2 leading-relaxed">
                <span className="text-zinc-600 text-[10px] shrink-0 font-sans font-bold">[{log.time}]</span>
                <span
                  className={`font-black shrink-0 uppercase text-[10px] ${
                    log.type === 'tx'
                      ? 'text-cyan-400'
                      : log.type === 'rx'
                      ? 'text-emerald-400'
                      : log.type === 'warn'
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }`}
                >
                  [{log.type}]:
                </span>
                <span className="break-all">{log.text}</span>
              </div>
            ))
          )}
        </div>

        {/* Command Input Bar */}
        <div className="p-3 border-t border-zinc-800 bg-zinc-900 flex items-center gap-2">
          <input
            type="text"
            value={customCmd}
            onChange={(e) => setCustomCmd(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type raw Feetech ASCII serial command (e.g. #1P2048T500! or READ_VOLT)..."
            className="flex-1 bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-sm px-3 py-2 text-xs font-mono font-bold focus:outline-none focus:border-amber-400"
          />
          <button
            onClick={handleSend}
            className="px-4 py-2 bg-amber-400 hover:bg-amber-300 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center gap-1.5 shadow"
          >
            <Send className="w-3.5 h-3.5 fill-current" />
            <span>Send</span>
          </button>

          <button
            onClick={handleCopyLogs}
            className="p-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-sm border border-zinc-700"
            title="Copy Logs"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>

          <button
            onClick={onClearLogs}
            className="p-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-sm border border-zinc-700"
            title="Clear Logs"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
