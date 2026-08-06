import { Injectable } from '@angular/core';
import { EMPTY, Observable } from 'rxjs';
import { EngagementSource } from './engagement-source';
import { UserActivityMetrics, UserInteractionEvent } from './engagement-metrics.model';
import { BrainDevice } from '../neurofeedback/brain-device';

/**
 * Premium tier — wraps a real BrainDevice and exposes its biometric streams directly.
 */
@Injectable()
export class EEGEngagementSource extends EngagementSource {
  readonly focus$: Observable<number | null>;
  readonly calm$: Observable<number | null>;

  constructor(device: BrainDevice) {
    super();
    this.focus$ = device.focus$;
    this.calm$ = device.calm$;
  }

  // Biometric sources don't need software-level interaction recording
  recordInteraction(_event: UserInteractionEvent): void {}

  getInteractionMetrics(): Observable<UserActivityMetrics> {
    return EMPTY;
  }
}
