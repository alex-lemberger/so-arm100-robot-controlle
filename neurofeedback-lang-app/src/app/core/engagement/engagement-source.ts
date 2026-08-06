import { Observable } from 'rxjs';
import { UserActivityMetrics, UserInteractionEvent } from './engagement-metrics.model';

/**
 * Vendor-neutral engagement data contract.
 * Doubles as the Angular DI token (abstract class = runtime token + type).
 */
export abstract class EngagementSource {
  /** Focus probability stream, 0–1, null until first reading arrives. */
  abstract readonly focus$: Observable<number | null>;
  /** Calm probability stream, 0–1, null when unavailable or until data arrives. */
  abstract readonly calm$: Observable<number | null>;

  /** Returns interaction/activity metrics observable. */
  abstract getInteractionMetrics(): Observable<UserActivityMetrics>;

  /** Ingests a raw user interaction event to update internal proxy metrics. */
  abstract recordInteraction(event: UserInteractionEvent): void;
}
