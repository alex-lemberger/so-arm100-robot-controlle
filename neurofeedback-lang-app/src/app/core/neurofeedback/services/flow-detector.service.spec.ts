import { initialFlowState, stepFlow, FlowState } from './flow-detector.service';
import { DEFAULT_FLOW_CONFIG, FlowConfig } from '../models/flow-config';

const CFG: FlowConfig = DEFAULT_FLOW_CONFIG;

/** Feed a constant focus/calm for `n` steps of `dt` seconds each. */
function run(focus: number | null, calm: number | null, n: number, dt = 1, cfg = CFG): FlowState {
  let s = initialFlowState();
  for (let i = 0; i < n; i++) { s = stepFlow(s, focus, calm, dt, cfg); }
  return s;
}

describe('stepFlow', () => {
  it('does not enter flow before the dwell time elapses', () => {
    // Good sample, but only 4s < dwellSeconds (5).
    const s = run(0.85, 0.6, 4, 1);
    expect(s.inFlow).toBe(false);
  });

  it('enters flow once the enter condition holds for dwellSeconds', () => {
    const s = run(0.85, 0.6, 6, 1);
    expect(s.inFlow).toBe(true);
  });

  it('stays in flow on a brief dip that remains above exitFocus (hysteresis)', () => {
    let s = run(0.85, 0.6, 6, 1);          // in flow
    expect(s.inFlow).toBe(true);
    s = stepFlow(s, 0.66, 0.6, 1, CFG);     // smoothedFocus stays >= exitFocus (0.62)
    expect(s.inFlow).toBe(true);
  });

  it('exits flow when smoothed focus drops below exitFocus', () => {
    let s = run(0.85, 0.6, 8, 1);          // firmly in flow, smoothedFocus ~0.85
    expect(s.inFlow).toBe(true);
    for (let i = 0; i < 6; i++) { s = stepFlow(s, 0.10, 0.6, 1, CFG); } // drag smoothedFocus down
    expect(s.inFlow).toBe(false);
  });

  it('exits flow when calm leaves the exit band', () => {
    let s = run(0.85, 0.6, 8, 1);
    expect(s.inFlow).toBe(true);
    for (let i = 0; i < 8; i++) { s = stepFlow(s, 0.85, 0.97, 1, CFG); } // calm too high
    expect(s.inFlow).toBe(false);
  });

  it('treats a null sample as not-in-flow and resets dwell', () => {
    let s = run(0.85, 0.6, 4, 1);          // partway through dwell
    s = stepFlow(s, null, 0.6, 1, CFG);
    expect(s.inFlow).toBe(false);
    expect(s.dwell).toBe(0);
  });

  it('respects a config override (dwellSeconds 0 enters immediately)', () => {
    const cfg: FlowConfig = { ...CFG, dwellSeconds: 0 };
    const s = run(0.85, 0.6, 1, 1, cfg);
    expect(s.inFlow).toBe(true);
  });
});

import { TestBed } from '@angular/core/testing';
import { BehaviorSubject, Observable } from 'rxjs';
import { FlowDetectorService } from './flow-detector.service';
import { FLOW_CONFIG } from '../models/flow-config';
import { BrainDevice, DeviceState, DeviceStatus } from '../brain-device';

class FakeDevice implements BrainDevice {
  focus$ = new BehaviorSubject<number | null>(null);
  calm$ = new BehaviorSubject<number | null>(null);
  state$ = new BehaviorSubject<DeviceState>({ isLoggedIn: true, error: null });
  extras$: Observable<Record<string, number>> = new BehaviorSubject({});
  connect() { return Promise.resolve(); }
  disconnect() { return Promise.resolve(); }
  getStatus(): Promise<DeviceStatus> { return Promise.resolve({ state: 'online' }); }
}

describe('FlowDetectorService', () => {
  let device: FakeDevice;
  let service: FlowDetectorService;

  beforeEach(() => {
    device = new FakeDevice();
    TestBed.configureTestingModule({
      providers: [
        FlowDetectorService,
        { provide: BrainDevice, useValue: device },
        // dwellSeconds 0 → enter as soon as a qualifying sample arrives (no timing)
        { provide: FLOW_CONFIG, useValue: { ...DEFAULT_FLOW_CONFIG, dwellSeconds: 0 } },
      ],
    });
    service = TestBed.inject(FlowDetectorService);
  });

  it('emits true once focus and calm enter the flow zone', () => {
    const seen: boolean[] = [];
    service.inFlow$.subscribe((v) => seen.push(v));
    device.focus$.next(0.85);
    device.calm$.next(0.60);
    expect(seen[seen.length - 1]).toBe(true);
  });

  it('emits false when focus leaves the flow zone', () => {
    const seen: boolean[] = [];
    service.inFlow$.subscribe((v) => seen.push(v));
    device.focus$.next(0.85);
    device.calm$.next(0.60);   // true (smoothed focus seeds at 0.85)
    device.focus$.next(0.10);  // smoothed → 0.625, still ≥ exitFocus (holds)
    device.focus$.next(0.10);  // smoothed → ~0.47, exits
    expect(seen[seen.length - 1]).toBe(false);
  });
});
