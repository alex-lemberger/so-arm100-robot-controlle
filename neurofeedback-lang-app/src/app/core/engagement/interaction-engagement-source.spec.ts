import { Observable } from 'rxjs';
import { InteractionEngagementSource } from './interaction-engagement-source';
import { IDEAL_MS, MAX_MS } from './focus-from-cadence';

describe('InteractionEngagementSource', () => {
  let source: InteractionEngagementSource;

  beforeEach(() => {
    source = new InteractionEngagementSource();
  });

  /**
   * Reads the current value of a BehaviorSubject/`of`-backed stream synchronously.
   * focus$/calm$/metrics all emit their latest value on subscribe, so we perform
   * the interactions first and then read the resulting value.
   */
  function latest<T>(obs: Observable<T>): T {
    let value!: T;
    const sub = obs.subscribe((v) => (value = v));
    sub.unsubscribe();
    return value;
  }

  it('leaves focus null until a second interaction arrives', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    expect(latest(source.focus$)).toBeNull();
  });

  it('emits focus=1 for interactions within IDEAL_MS (~2s apart)', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    source.recordInteraction({ type: 'response', timestamp: 1000 + 2000 });
    expect(latest(source.focus$)).toBe(1);
  });

  it('emits focus=1 when the gap equals IDEAL_MS', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    source.recordInteraction({ type: 'response', timestamp: 1000 + IDEAL_MS });
    expect(latest(source.focus$)).toBe(1);
  });

  it('emits focus=0 when the gap reaches MAX_MS', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    source.recordInteraction({ type: 'response', timestamp: 1000 + MAX_MS });
    expect(latest(source.focus$)).toBe(0);
  });

  it('emits a low focus value for a long gap (~50s)', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    source.recordInteraction({ type: 'response', timestamp: 1000 + 50000 });
    expect(latest(source.focus$)).toBeLessThan(0.2);
  });

  it('emits calm=null', () => {
    expect(latest(source.calm$)).toBeNull();
  });

  it('getInteractionMetrics reports isProxy=true and the latest sessionCadence', () => {
    source.recordInteraction({ type: 'response', timestamp: 1000 });
    source.recordInteraction({ type: 'response', timestamp: 1000 + 5000 });
    const metrics = latest(source.getInteractionMetrics());
    expect(metrics.isProxy).toBe(true);
    expect(metrics.sessionCadence).toBe(5000);
  });
});
