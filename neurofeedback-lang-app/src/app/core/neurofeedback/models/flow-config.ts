import { InjectionToken } from '@angular/core';

/** Tunable thresholds for flow-state classification. All metric bounds are 0–1. */
export interface FlowConfig {
  /** EMA smoothing factor (0–1); higher = more responsive, noisier. */
  alpha: number;
  /** Min smoothed focus to enter flow. */
  enterFocus: number;
  /** Smoothed focus below this exits flow (hysteresis; < enterFocus). */
  exitFocus: number;
  /** Calm sweet-spot bounds to enter flow. */
  enterCalmLo: number;
  enterCalmHi: number;
  /** Calm exit bounds (wider than enter bounds; hysteresis). */
  exitCalmLo: number;
  exitCalmHi: number;
  /** Seconds the enter condition must hold before flow is declared. */
  dwellSeconds: number;
}

export const DEFAULT_FLOW_CONFIG: FlowConfig = {
  alpha: 0.3,
  enterFocus: 0.70,
  exitFocus: 0.62,
  enterCalmLo: 0.45,
  enterCalmHi: 0.85,
  exitCalmLo: 0.40,
  exitCalmHi: 0.90,
  dwellSeconds: 5,
};

/** Overridable in tests / future per-user tuning. */
export const FLOW_CONFIG = new InjectionToken<FlowConfig>('FLOW_CONFIG', {
  providedIn: 'root',
  factory: () => DEFAULT_FLOW_CONFIG,
});
