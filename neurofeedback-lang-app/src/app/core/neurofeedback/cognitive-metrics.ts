/** Cognitive-state metrics from normalized EEG band powers (theta/alpha/beta as fractions). Heuristic, relative. */

export const BASELINE_MS = 30_000;  // fatigue baseline = mean index over first 30s of a session
export const FATIGUE_SPAN = 1.0;    // index doubling vs baseline => fatigue ~1.0

export interface Bands { theta: number; alpha: number; beta: number; }

export interface CognitiveState {
  baselineSum: number;
  baselineCount: number;
  baseline: number | null;   // frozen once the baseline window closes
  load: number | null;
  fatigue: number | null;
  signalOk: boolean;
}

export function initialCognitiveState(): CognitiveState {
  return { baselineSum: 0, baselineCount: 0, baseline: null, load: null, fatigue: null, signalOk: false };
}

/** Load: theta share of slow-band power, 0..1. null if theta+alpha == 0. */
export function loadFromBands(theta: number, alpha: number): number | null {
  const denom = theta + alpha;
  if (!(denom > 0)) return null;
  return theta / denom;
}

/** Fatigue index (theta+alpha)/beta. null if beta == 0. */
export function fatigueIndex(theta: number, alpha: number, beta: number): number | null {
  if (!(beta > 0)) return null;
  return (theta + alpha) / beta;
}

/** Relative fatigue from index vs baseline, clamped 0..1. */
export function fatigueFromIndex(index: number, baseline: number): number {
  if (!(baseline > 0)) return 0;
  const rise = (index / baseline - 1) / FATIGUE_SPAN;
  return Math.min(1, Math.max(0, rise));
}

function finite(n: number | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n);
}

/**
 * Fold one band-power sample into cognitive state.
 * @param elapsedMs ms since session start; drives the baseline window.
 */
export function stepCognitive(state: CognitiveState, bands: Partial<Bands>, elapsedMs: number): CognitiveState {
  const { theta, alpha, beta } = bands;
  if (!finite(theta) || !finite(alpha) || !finite(beta)) {
    return { ...state, load: null, fatigue: null, signalOk: false };
  }
  const load = loadFromBands(theta, alpha);
  const index = fatigueIndex(theta, alpha, beta);
  if (index === null) {
    return { ...state, load, fatigue: null, signalOk: true };
  }
  if (elapsedMs < BASELINE_MS) {
    return {
      ...state,
      baselineSum: state.baselineSum + index,
      baselineCount: state.baselineCount + 1,
      baseline: null,
      load, fatigue: null, signalOk: true,
    };
  }
  const baseline = state.baseline
    ?? (state.baselineCount > 0 ? state.baselineSum / state.baselineCount : index);
  return { ...state, baseline, load, fatigue: fatigueFromIndex(index, baseline), signalOk: true };
}
