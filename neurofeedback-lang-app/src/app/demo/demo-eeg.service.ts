import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class DemoEegService {
  private _t = 0;

  readonly focus = signal(0.6);
  readonly calm = signal(0.5);

  tick(deltaMs: number): void {
    this._t += deltaMs / 1000;
    this.focus.set(0.625 + 0.275 * Math.sin((2 * Math.PI * this._t) / 12));
    this.calm.set(0.500 + 0.250 * Math.sin((2 * Math.PI * this._t) / 15 + Math.PI * 0.6));
  }
}