// src/app/modules/capture/components/upload-progress/upload-progress.component.ts
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureState } from '../../state/capture.state';
import { CaptureActions } from '../../state/capture.actions';

@Component({
  selector: 'app-upload-progress',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <div class="progress-card">
      @switch (status()) {
        @case ('uploading') {
          <h2 class="progress-title">Wird hochgeladen…</h2>
          <div class="bar-track">
            <div class="bar-fill" [style.width.%]="progress()"></div>
          </div>
          <p class="progress-pct">{{ progress() }}%</p>
        }
        @case ('done') {
          <h2 class="progress-title">Aufzeichnung abgeschlossen</h2>
          <p class="progress-id">Session-ID: <code>{{ sessionId() }}</code></p>
          <div class="btn-row">
            <a class="btn-secondary" routerLink="/dashboard">Zur Übersicht</a>
            <button class="btn-primary" (click)="reset()">Neue Aufzeichnung</button>
          </div>
        }
        @case ('error') {
          <h2 class="progress-title progress-title--error">Upload fehlgeschlagen</h2>
          <p class="progress-error">{{ error() }}</p>
          <button class="btn-primary" (click)="reset()">Erneut versuchen</button>
        }
      }
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; }
    .progress-card { background: #1a2535; border-radius: 16px; padding: 40px; width: 100%; max-width: 480px; margin: 0 auto; box-sizing: border-box; color: #e8edf5; text-align: center; }
    .progress-title { font-size: 20px; margin-bottom: 24px; }
    .progress-title--error { color: #ef5350; }
    .bar-track { width: 100%; height: 8px; background: #2a3545; border-radius: 4px; overflow: hidden; margin-bottom: 12px; }
    .bar-fill { height: 100%; background: #1976D2; border-radius: 4px; transition: width 0.3s; }
    .progress-pct { color: #9aa8c4; font-size: 14px; }
    .progress-id { color: #9aa8c4; font-size: 13px; margin-bottom: 24px; }
    .progress-id code { color: #e8edf5; font-family: 'DM Mono', monospace; }
    .progress-error { color: #ef5350; font-size: 13px; margin-bottom: 24px; }
    .btn-row { display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; }
    .btn-primary { padding: 14px 32px; border-radius: 10px; border: none; background: #1976D2; color: #fff; font-size: 15px; cursor: pointer; }
    .btn-secondary { padding: 14px 32px; border-radius: 10px; border: 1.5px solid #2a3f5f; background: transparent; color: #9aa8c4; font-size: 15px; text-decoration: none; display: inline-flex; align-items: center; }
    .btn-secondary:hover { border-color: #1976D2; color: #e8edf5; }
  `],
})
export class UploadProgressComponent {
  private store = inject(Store);

  protected status = toSignal(this.store.select(CaptureState.status), { initialValue: 'uploading' as any });
  protected sessionId = toSignal(this.store.select(CaptureState.sessionId), { initialValue: null });
  protected error = toSignal(this.store.select(CaptureState.error), { initialValue: null });
  protected progress = toSignal(this.store.select(CaptureState.uploadProgress), { initialValue: 0 });

  reset(): void {
    this.store.dispatch(new CaptureActions.Reset());
  }
}
