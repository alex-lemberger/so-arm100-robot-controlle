import { Injectable } from '@angular/core';
import { BehaviorSubject, of } from 'rxjs';
import { EngagementSource } from './engagement-source';
import { UserActivityMetrics, UserInteractionEvent } from './engagement-metrics.model';
import { focusFromCadence } from './focus-from-cadence';

@Injectable()
export class InteractionEngagementSource extends EngagementSource {
  private lastTs: number | null = null;
  private readonly _focus$ = new BehaviorSubject<number | null>(null);
  private sessionCadence = 0;

  readonly focus$ = this._focus$.asObservable();
  readonly calm$ = of(null);
  private readonly _metrics$ = new BehaviorSubject<UserActivityMetrics>({
    latencyMs: 0,
    errorRate: 0,
    sessionCadence: 0,
    isProxy: true,
  });

  recordInteraction(event: UserInteractionEvent): void {
    if (this.lastTs !== null) {
      const gap = event.timestamp - this.lastTs;
      this._focus$.next(focusFromCadence(gap));
      this.sessionCadence = gap;
      this._metrics$.next({
        latencyMs: 0,
        errorRate: 0,
        sessionCadence: this.sessionCadence,
        isProxy: true,
      });
    }
    this.lastTs = event.timestamp;
  }

  getInteractionMetrics() {
    return this._metrics$.asObservable();
  }
}
