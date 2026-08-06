export interface UserActivityMetrics {
  /** Time elapsed between prompt and response. */
  latencyMs: number;
  /** Frequency of incorrect answers in the current window. */
  errorRate: number;
  /** Average time between consecutive interactions. */
  sessionCadence: number;
  /** True if metrics are derived from software interaction, false for biometric data. */
  isProxy: boolean;
}

export interface UserInteractionEvent {
  type: 'response' | 'error';
  timestamp: number;
  payload?: Record<string, unknown>;
}
