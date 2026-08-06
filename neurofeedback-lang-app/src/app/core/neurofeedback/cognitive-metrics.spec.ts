import {
  loadFromBands, fatigueIndex, fatigueFromIndex,
  stepCognitive, initialCognitiveState, BASELINE_MS,
} from './cognitive-metrics';

describe('cognitive-metrics', () => {
  it('loadFromBands returns theta share', () => expect(loadFromBands(0.6, 0.2)).toBeCloseTo(0.75, 5));
  it('loadFromBands null when theta+alpha is 0', () => expect(loadFromBands(0, 0)).toBeNull());

  it('fatigueIndex computes (theta+alpha)/beta', () => expect(fatigueIndex(0.3, 0.3, 0.4)).toBeCloseTo(1.5, 5));
  it('fatigueIndex null when beta is 0', () => expect(fatigueIndex(0.5, 0.5, 0)).toBeNull());

  it('fatigueFromIndex is 0 at baseline', () => expect(fatigueFromIndex(1.5, 1.5)).toBe(0));
  it('fatigueFromIndex ~1 when index doubles', () => expect(fatigueFromIndex(3.0, 1.5)).toBe(1));
  it('fatigueFromIndex clamps below 0', () => expect(fatigueFromIndex(0.5, 1.5)).toBe(0));

  it('stepCognitive: null fatigue during baseline window', () => {
    const s = stepCognitive(initialCognitiveState(), { theta: 0.3, alpha: 0.3, beta: 0.4 }, 0);
    expect(s.fatigue).toBeNull();
    expect(s.load).toBeCloseTo(0.5, 5);
    expect(s.baselineCount).toBe(1);
  });

  it('stepCognitive: freezes baseline and reports rising fatigue after window', () => {
    let s = initialCognitiveState();
    s = stepCognitive(s, { theta: 0.3, alpha: 0.3, beta: 0.4 }, 0);          // index 1.5 -> baseline
    s = stepCognitive(s, { theta: 0.3, alpha: 0.3, beta: 0.2 }, BASELINE_MS + 1); // index 3.0
    expect(s.baseline).toBeCloseTo(1.5, 5);
    expect(s.fatigue).toBe(1);
  });

  it('stepCognitive: signalOk false on non-finite bands', () => {
    const s = stepCognitive(initialCognitiveState(), { theta: NaN, alpha: 0.3, beta: 0.4 }, 0);
    expect(s.signalOk).toBe(false);
  });
});
