import { Injectable, inject } from '@angular/core';
import { Observable, combineLatest } from 'rxjs';
import { distinctUntilChanged, map, scan, shareReplay } from 'rxjs/operators';
import { BrainDevice } from '../brain-device';
import { FlowConfig, FLOW_CONFIG } from '../models/flow-config';

export interface FlowState {
  /** Smoothed focus, null until first non-null sample. */
  smoothedFocus: number | null;
  /** Smoothed calm, null until first non-null sample. */
  smoothedCalm: number | null;
  /** Accumulated seconds the enter condition has held (while not yet in flow). */
  dwell: number;
  inFlow: boolean;
}

export function initialFlowState(): FlowState {
  return { smoothedFocus: null, smoothedCalm: null, dwell: 0, inFlow: false };
}

/**
 * Advance the flow classifier by one sample.
 * Pure: no clock, no streams. `dt` is seconds since the previous sample.
 */
export function stepFlow(
  s: FlowState,
  focus: number | null,
  calm: number | null,
  dt: number,
  cfg: FlowConfig,
): FlowState {
  if (focus == null || calm == null) {
    return { smoothedFocus: s.smoothedFocus, smoothedCalm: s.smoothedCalm, dwell: 0, inFlow: false };
  }

  const smoothedFocus = s.smoothedFocus == null ? focus : cfg.alpha * focus + (1 - cfg.alpha) * s.smoothedFocus;
  const smoothedCalm = s.smoothedCalm == null ? calm : cfg.alpha * calm + (1 - cfg.alpha) * s.smoothedCalm;

  if (s.inFlow) {
    const exit = smoothedFocus < cfg.exitFocus || smoothedCalm < cfg.exitCalmLo || smoothedCalm > cfg.exitCalmHi;
    return { smoothedFocus, smoothedCalm, dwell: 0, inFlow: !exit };
  }

  const enter = smoothedFocus >= cfg.enterFocus && smoothedCalm >= cfg.enterCalmLo && smoothedCalm <= cfg.enterCalmHi;
  const dwell = enter ? s.dwell + dt : 0;
  return { smoothedFocus, smoothedCalm, dwell, inFlow: dwell >= cfg.dwellSeconds };
}

interface ScanAcc { state: FlowState; last: number | null; }

/**
 * Classifies live flow state from the device focus/calm streams.
 * Single public output: `inFlow$`. Pure logic lives in `stepFlow`.
 */
@Injectable({ providedIn: 'root' })
export class FlowDetectorService {
  private readonly cfg = inject(FLOW_CONFIG);
  private readonly device = inject(BrainDevice);
  /** Injectable clock seam for deterministic tests. */
  protected now: () => number = () => Date.now();

  readonly inFlow$: Observable<boolean> = combineLatest([
    this.device.focus$,
    this.device.calm$,
  ]).pipe(
    scan<[number | null, number | null], ScanAcc>((acc, [focus, calm]) => {
      const t = this.now();
      const dt = acc.last == null ? 0 : Math.max(0, (t - acc.last) / 1000);
      return { state: stepFlow(acc.state, focus, calm, dt, this.cfg), last: t };
    }, { state: initialFlowState(), last: null }),
    map((acc) => acc.state.inFlow),
    distinctUntilChanged(),
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}
