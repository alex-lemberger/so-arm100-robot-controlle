// src/app/modules/capture/services/eeg-buffer.service.spec.ts
import { Subject } from 'rxjs';
import { EegBufferService } from './eeg-buffer.service';
import { EegReading } from '../../../core/neurofeedback/brain-device';

function makeReading(electrode: number, samples: number[]): EegReading {
  return { electrode, samples, timestamp: Date.now() };
}

describe('EegBufferService', () => {
  let service: EegBufferService;
  let source$: Subject<EegReading>;

  beforeEach(() => {
    service = new EegBufferService();
    source$ = new Subject<EegReading>();
  });

  afterEach(() => {
    service.stopRecording();
  });

  it('returns null when no data has been buffered', () => {
    service.startRecording(source$.asObservable());
    expect(service.stopRecording()).toBeNull();
  });

  it('accumulates samples per electrode', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(0, [1, 2, 3]));
    source$.next(makeReading(1, [4, 5]));
    source$.next(makeReading(0, [6]));

    const result = service.stopRecording()!;
    expect(result).not.toBeNull();
    // ch0: [1,2,3,6] = 4 samples; ch1: [4,5] = 2; ch2: [] = 0; ch3: [] = 0 → total 6
    expect(result.length).toBe(6);
    // ch0 samples come first in concatenated layout
    expect(Array.from(result.slice(0, 4))).toEqual([1, 2, 3, 6]);
    expect(Array.from(result.slice(4, 6))).toEqual([4, 5]);
  });

  it('ignores electrode index >= 4', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(5, [99, 99]));
    expect(service.stopRecording()).toBeNull();
  });

  it('resets buffer on startRecording', () => {
    service.startRecording(source$.asObservable());
    source$.next(makeReading(0, [1, 2]));
    service.stopRecording();

    const source2$ = new Subject<EegReading>();
    service.startRecording(source2$.asObservable());
    source2$.next(makeReading(0, [9]));
    const result = service.stopRecording()!;
    expect(result.length).toBe(1);
    expect(result[0]).toBe(9);
  });

});