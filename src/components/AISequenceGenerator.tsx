import React, { useState } from 'react';
import { Sequence } from '../types';
import { Sparkles, Mic, Play, Check, AlertCircle, Loader2, Wand2, Lightbulb } from 'lucide-react';

interface AISequenceGeneratorProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyGeneratedSequence: (seq: Sequence) => void;
}

export const AISequenceGenerator: React.FC<AISequenceGeneratorProps> = ({
  isOpen,
  onClose,
  onApplyGeneratedSequence
}) => {
  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [generatedPreview, setGeneratedPreview] = useState<Sequence | null>(null);

  if (!isOpen) return null;

  const quickPrompts = [
    'Pick up object on left table side and move it 15cm right',
    'Wave hello politely with wrist roll and shoulder gesture',
    'Scan table surface in a 3x3 camera inspection pattern',
    'Draw a 100mm square shape with end-effector on table plane',
    'Carefully stow arm into safe compact rest posture'
  ];

  const handleSpeechInput = () => {
    if (typeof window === 'undefined') return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser. Please type your prompt.');
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setPrompt(transcript);
    };

    recognition.start();
  };

  const handleGenerate = async (customPrompt?: string) => {
    const textToSubmit = customPrompt || prompt;
    if (!textToSubmit.trim()) return;

    setIsLoading(true);
    setErrorMessage(null);
    setGeneratedPreview(null);

    try {
      const response = await fetch('/api/ollama/generate-sequence', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: textToSubmit })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to generate trajectory');
      }

      const formattedSeq: Sequence = {
        id: `ai-seq-${Date.now()}`,
        title: data.title || 'AI Generated Routine',
        description: data.description || textToSubmit,
        category: 'ai',
        keyframes: data.keyframes.map((kf: any, idx: number) => ({
          id: `ai-kf-${idx}`,
          name: kf.name || `Pose ${idx + 1}`,
          durationMs: kf.durationMs || 1000,
          delayAfterMs: kf.delayAfterMs || 300,
          joints: kf.joints,
          comment: kf.comment
        })),
        loop: false,
        speedMultiplier: 1.0,
        createdAt: new Date().toISOString(),
        tags: ['Ollama AI', 'Auto-Generated']
      };

      setGeneratedPreview(formattedSeq);
    } catch (err: any) {
      console.error(err);
      setErrorMessage(err.message || 'Error communicating with Gemini AI server.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = () => {
    if (generatedPreview) {
      onApplyGeneratedSequence(generatedPreview);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-zinc-950 border border-zinc-800 rounded-sm w-full max-w-xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="p-5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-400 text-zinc-950 rounded-sm font-black">
              <Sparkles className="w-5 h-5 fill-current" />
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-[0.3em] text-zinc-500 font-bold block mb-0.5">
                AI Trajectory Copilot
              </span>
              <h3 className="text-xl font-black uppercase italic text-white tracking-tight">Gemini 3.6 Generator</h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-white text-xs px-2.5 py-1 rounded-sm bg-zinc-800 font-bold uppercase border border-zinc-700"
          >
            Close
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-4">
          {errorMessage && (
            <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3 rounded-sm text-xs flex items-center gap-2 font-mono">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Quick Suggestions */}
          <div>
            <label className="text-xs font-bold uppercase tracking-tight text-zinc-400 flex items-center gap-1.5 mb-2">
              <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
              <span>Suggested Robotic Tasks:</span>
            </label>
            <div className="flex flex-wrap gap-1.5">
              {quickPrompts.map((qp, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setPrompt(qp);
                    handleGenerate(qp);
                  }}
                  className="px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-200 text-xs rounded-sm border border-zinc-800 transition text-left font-bold"
                >
                  {qp}
                </button>
              ))}
            </div>
          </div>

          {/* Prompt Input Box */}
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase tracking-tight text-zinc-300">Custom Task Prompt:</label>
            <div className="relative">
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={3}
                placeholder="Describe what you want the robot arm to do... (e.g., 'Pick up a soda can on the right, rotate base to center, and gently set it down')"
                className="w-full bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-sm p-3 text-xs focus:outline-none focus:border-amber-400 resize-none pr-10"
              />
              <button
                onClick={handleSpeechInput}
                className={`absolute right-3 top-3 p-1.5 rounded-sm border transition ${
                  isListening
                    ? 'bg-rose-500/20 text-rose-400 border-rose-500/40 animate-pulse'
                    : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200 border-zinc-700'
                }`}
                title="Voice Dictation"
              >
                <Mic className="w-4 h-4" />
              </button>
            </div>
          </div>

          <button
            onClick={() => handleGenerate()}
            disabled={isLoading || !prompt.trim()}
            className="w-full py-3 bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm shadow-[0_0_15px_rgba(251,191,36,0.3)] transition flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin text-zinc-950" />
                <span>Computing Kinematics Trajectory...</span>
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4 fill-current" />
                <span>Generate Keyframe Routine with AI</span>
              </>
            )}
          </button>

          {/* AI Generated Sequence Preview */}
          {generatedPreview && (
            <div className="bg-zinc-900 p-4 rounded-sm border border-amber-400/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-black uppercase text-amber-400">{generatedPreview.title}</h4>
                  <p className="text-[11px] text-zinc-400">{generatedPreview.description}</p>
                </div>
                <span className="text-[10px] bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded-sm border border-amber-500/30 font-mono font-bold uppercase">
                  {generatedPreview.keyframes.length} KEYFRAMES
                </span>
              </div>

              {/* Step Timeline List */}
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {generatedPreview.keyframes.map((kf, index) => (
                  <div key={index} className="bg-zinc-950 p-2 rounded-sm border border-zinc-800 text-[11px] flex items-center justify-between font-mono">
                    <span className="text-zinc-200 font-bold">{index + 1}. {kf.name}</span>
                    <span className="text-amber-400">
                      B:{kf.joints.base}° S:{kf.joints.shoulder}° E:{kf.joints.elbow}° G:{kf.joints.gripper}%
                    </span>
                  </div>
                ))}
              </div>

              <button
                onClick={handleApply}
                className="w-full py-2 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-black text-xs uppercase tracking-tight rounded-sm transition flex items-center justify-center gap-1.5 shadow"
              >
                <Check className="w-4 h-4" />
                <span>Load Trajectory into Sequence Studio</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
