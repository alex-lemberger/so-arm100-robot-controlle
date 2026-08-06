import { focusFromCadence, IDEAL_MS, MAX_MS } from './focus-from-cadence';

describe('focusFromCadence', () => {
  it('returns 1 when gap is 0', () => {
    expect(focusFromCadence(0)).toBe(1);
  });

  it('returns 1 when gap equals IDEAL_MS', () => {
    expect(focusFromCadence(IDEAL_MS)).toBe(1);
  });

  it('returns 0 when gap equals MAX_MS', () => {
    expect(focusFromCadence(MAX_MS)).toBe(0);
  });

  it('returns 0 when gap exceeds MAX_MS', () => {
    expect(focusFromCadence(MAX_MS + 1)).toBe(0);
  });

  it('returns ~0.5 when gap is midpoint between IDEAL_MS and MAX_MS', () => {
    const midpoint = (IDEAL_MS + MAX_MS) / 2; // 34000
    expect(focusFromCadence(midpoint)).toBeCloseTo(0.5, 5);
  });
});
