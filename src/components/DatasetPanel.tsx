import React, { useEffect, useState } from 'react';
import { Sequence } from '../types';
import { Database, Eye, LoaderCircle, TriangleAlert } from 'lucide-react';

type DatasetSummary = {
  id: string;
  robotType: string;
  episodes: number;
  frames: number;
  fps: number;
  cameras: string[];
  actionJoints: string[];
  videos: { top: string; wrist: string };
};

interface DatasetPanelProps {
  onLoadPolicyPreview: (sequence: Sequence) => void;
}

export const DatasetPanel: React.FC<DatasetPanelProps> = ({ onLoadPolicyPreview }) => {
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [camera, setCamera] = useState<'top' | 'wrist'>('top');
  const [error, setError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/dataset/svla-so100')
      .then(async response => {
        if (!response.ok) throw new Error((await response.json()).error || 'Dataset unavailable');
        return response.json() as Promise<DatasetSummary>;
      })
      .then(value => { if (!cancelled) setDataset(value); })
      .catch(err => { if (!cancelled) setError(err.message); });
    return () => { cancelled = true; };
  }, []);

  const loadPolicyPreview = async () => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const response = await fetch('/api/policy/preview');
      const value = await response.json();
      if (!response.ok) throw new Error(value.error || 'Policy preview unavailable');
      onLoadPolicyPreview(value as Sequence);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Policy preview unavailable');
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <section className="bg-zinc-900 border border-zinc-800 rounded-sm p-6 shadow-2xl flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4 border-b border-zinc-800 pb-4">
        <div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-1">Local LeRobot source</span>
          <h2 className="text-2xl font-black uppercase italic text-white tracking-tight">Dataset Lab</h2>
          <p className="text-xs text-zinc-400 mt-1">Read-only synchronized demonstrations for visual review and training preparation.</p>
        </div>
        <Database className="w-6 h-6 text-amber-400 shrink-0" />
      </div>

      {error ? (
        <div className="flex items-center gap-2 text-rose-300 text-sm bg-rose-950/30 border border-rose-500/30 p-3 rounded-sm">
          <TriangleAlert className="w-4 h-4 shrink-0" /> {error}
        </div>
      ) : !dataset ? (
        <div className="flex items-center gap-2 text-zinc-400 text-sm"><LoaderCircle className="w-4 h-4 animate-spin" /> Loading dataset metadata…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              ['Robot', dataset.robotType.toUpperCase()],
              ['Episodes', dataset.episodes.toString()],
              ['Frames', dataset.frames.toLocaleString()],
              ['Rate', `${dataset.fps} FPS`]
            ].map(([label, value]) => (
              <div key={label} className="bg-zinc-950 border border-zinc-800 rounded-sm p-3">
                <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">{label}</div>
                <div className="text-sm text-zinc-100 font-mono font-bold mt-1">{value}</div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {(['top', 'wrist'] as const).map(view => (
              <button
                key={view}
                onClick={() => setCamera(view)}
                className={`px-3 py-2 rounded-sm text-xs font-black uppercase tracking-wider flex items-center gap-2 ${camera === view ? 'bg-amber-400 text-zinc-950' : 'bg-zinc-800 text-zinc-400 hover:text-zinc-100'}`}
              >
                <Eye className="w-4 h-4" /> {view === 'top' ? 'Overview / Top' : 'Wrist'}
              </button>
            ))}
          </div>

          <div className="aspect-video bg-zinc-950 border border-zinc-800 rounded-sm overflow-hidden">
            <video key={camera} className="w-full h-full object-contain" controls preload="metadata" src={dataset.videos[camera]} />
          </div>

          <div className="text-[11px] text-zinc-500 font-mono">
            Actions: {dataset.actionJoints.join(' · ')}
          </div>

          <div className="border-t border-zinc-800 pt-4 flex flex-col gap-2">
            <button
              onClick={loadPolicyPreview}
              disabled={previewLoading}
              className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-zinc-100 text-xs font-black uppercase tracking-wider rounded-sm"
            >
              {previewLoading ? 'Loading policy preview…' : 'Load Policy Preview into 3D View'}
            </button>
            <p className="text-[10px] text-amber-300/80 font-mono">OFFLINE ONLY — this preview cannot send hardware commands.</p>
            {previewError && <p className="text-[11px] text-rose-300">{previewError}</p>}
          </div>
        </>
      )}
    </section>
  );
};
