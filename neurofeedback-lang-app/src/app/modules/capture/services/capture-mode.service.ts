import { Injectable, signal } from '@angular/core';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class CaptureModeService {
  readonly isMock = signal(environment.device === 'mock');

  toggle(): void {
    this.isMock.update(v => !v);
  }
}
