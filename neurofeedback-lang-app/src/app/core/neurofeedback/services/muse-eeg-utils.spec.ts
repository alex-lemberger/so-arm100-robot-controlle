import { bandPowers, goertzel } from './muse-eeg-utils';

/** Pure sine wave at `hz` — 256 samples at 256 Hz sample rate. */
function sine(hz: number, samples = 256, rate = 256): number[] {
  return Array.from({ length: samples }, (_, i) =>
    Math.sin(2 * Math.PI * hz * i / rate)
  );
}

describe('goertzel', () => {
  it('returns high power at the target frequency', () => {
    const power = goertzel(sine(10), 10, 256);
    expect(power).toBeGreaterThan(1000);
  });

  it('returns near-zero power at a non-present frequency', () => {
    const power = goertzel(sine(10), 20, 256);
    expect(power).toBeLessThan(1);
  });
});

describe('bandPowers', () => {
  it('alpha dominates for a 10 Hz signal', () => {
    const p = bandPowers(sine(10));
    expect(p.alpha).toBeGreaterThan(p.beta);
    expect(p.alpha).toBeGreaterThan(p.theta);
  });

  it('beta dominates for a 20 Hz signal', () => {
    const p = bandPowers(sine(20));
    expect(p.beta).toBeGreaterThan(p.alpha);
    expect(p.beta).toBeGreaterThan(p.theta);
  });

  it('theta dominates for a 6 Hz signal', () => {
    const p = bandPowers(sine(6));
    expect(p.theta).toBeGreaterThan(p.alpha);
    expect(p.theta).toBeGreaterThan(p.beta);
  });

  it('all band powers are near-zero for a DC (flat) signal', () => {
    const flat = new Array(256).fill(1);
    const p = bandPowers(flat);
    expect(p.alpha + p.beta + p.theta).toBeLessThan(1);
  });
});