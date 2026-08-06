/** Ideal gap between interactions (ms). */
export const IDEAL_MS = 8000;
/** Maximum gap before focus drops to 0 (ms). */
export const MAX_MS = 60000;

/**
 * Pure function that maps interaction cadence (gap in ms) to a focus score 0–1.
 * gapMs ≤ IDEAL_MS → 1.0  |  gapMs ≥ MAX_MS → 0.0  |  linear between.
 */
export function focusFromCadence(gapMs: number): number {
  if (gapMs <= IDEAL_MS) return 1;
  if (gapMs >= MAX_MS) return 0;
  return 1 - (gapMs - IDEAL_MS) / (MAX_MS - IDEAL_MS);
}
