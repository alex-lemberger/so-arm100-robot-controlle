// src/app/modules/capture/services/eeg-signal-quality.service.spec.ts
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { EegSignalQualityService, ElectrodeQuality } from './eeg-signal-quality.service';
import { EegReading } from '../../../core/neurofeedback/brain-device';

function makeReading(electrode: number, samples: number[]): EegReading {
  return { electrode, samples, timestamp: Date.now() };
}

// Variance ≈ 200 µV² — within [5, 2000] → 'good'
function goodSamples(n = 256): number[] {
  return Array.from({ length: n }, (_, i) => 20 * Math.sin(i * 0.1));
}

// Variance = 0 — below MIN_VARIANCE (5) → 'poor'
function flatSamples(n = 256): number[] {
  return Array(n).fill(0);
}

// Variance = 25,000,000 — above MAX_VARIANCE (2000) → 'poor'
function noisySamples(n = 256): number[] {
  return Array.from({ length: n }, (_, i) => i % 2 === 0 ? 5000 : -5000);
}

describe('EegSignalQualityService', () => {
  let service: EegSignalQualityService;
  let source$: Subject<EegReading>;
  let latestQuality: ElectrodeQuality[];
  let gateValues: boolean[];

  beforeEach(() => {
    jasmine.clock().install();
    jasmine.clock().mockDate(new Date());
    TestBed.configureTestingModule({});
    service = TestBed.inject(EegSignalQualityService);
    source$ = new Subject<EegReading>();
    latestQuality = [];
    gateValues = [];
    service.quality$.subscribe((q: ElectrodeQuality[]) => { latestQuality = q; });
    service.gateOpen$.subscribe((v: boolean) => { gateValues.push(v); });
  });

  afterEach(() => {
    service.stopMonitoring();
    jasmine.clock().uninstall();
  });

  it('emits unknown for all electrodes before 128 samples', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, goodSamples(64)));
    expect(latestQuality[0].state).toBe('unknown');
    expect(latestQuality[1].state).toBe('unknown');
    expect(latestQuality[2].state).toBe('unknown');
    expect(latestQuality[3].state).toBe('unknown');
  });

  it('emits good for variance in range', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, goodSamples(256)));
    expect(latestQuality[0].state).toBe('good');
  });

  it('emits poor for flat signal', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, flatSamples(256)));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('emits poor for noisy signal', () => {
    service.startMonitoring(source$.asObservable());
    source$.next(makeReading(0, noisySamples(256)));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('emits poor when window contains NaN', () => {
    service.startMonitoring(source$.asObservable());
    const samples = goodSamples(256);
    samples[10] = NaN;
    source$.next(makeReading(0, samples));
    expect(latestQuality[0].state).toBe('poor');
  });

  it('opens gate after 3 s of ≥3/4 good', () => {
    service.startMonitoring(source$.asObservable());
    // Send 256 samples for each electrode to get them all into the buffer
    for (let e = 0; e < 4; e++) {
      source$.next(makeReading(e, goodSamples(256)));
    }

    // Check that gate is initially closed
    expect(gateValues[gateValues.length - 1]).toBeFalse();

    // Advance time by 3 seconds and a bit more to trigger evaluation
    jasmine.clock().tick(3001);

    // Send one more reading to trigger the evaluation
    source$.next(makeReading(0, goodSamples(12)));

    // Check that gate is now open
    expect(gateValues[gateValues.length - 1]).toBeTrue();
  });

  it('resets gate timer when quality drops', () => {
    service.startMonitoring(source$.asObservable());
    // Set all electrodes to good initially
    for (let e = 0; e < 4; e++) {
      source$.next(makeReading(e, goodSamples(256)));
    }

    // Advance time by 1 second
    jasmine.clock().tick(1000);

    // Send one more reading to trigger evaluation at t=1s
    source$.next(makeReading(0, goodSamples(12)));

    // Drop 3 electrodes to poor
    for (let e = 0; e < 3; e++) {
      source$.next(makeReading(e, flatSamples(256)));
    }

    // Advance time by 3 seconds and a bit more to trigger evaluation after reset
    jasmine.clock().tick(3001);

    // Send one more reading to trigger the evaluation
    source$.next(makeReading(0, flatSamples(12)));

    // Check that gate is still closed (reset due to quality drop)
    expect(gateValues[gateValues.length - 1]).toBeFalse();
  });

  it('opens gate immediately when rawEeg$ is undefined', () => {
    service.startMonitoring(undefined);
    expect(gateValues[gateValues.length - 1]).toBeTrue();
  });

  it('ignores emissions after stopMonitoring', () => {
    service.startMonitoring(source$.asObservable());
    service.stopMonitoring();
    const qualityBeforeStop = [...latestQuality];
    source$.next(makeReading(0, goodSamples(256)));
    expect(latestQuality).toEqual(qualityBeforeStop);
  });
});