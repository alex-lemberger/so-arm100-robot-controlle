// src/app/modules/capture/components/task-selector/task-selector.component.ts
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureSessionService } from '../../services/capture-session.service';
import { CaptureActions } from '../../state/capture.actions';
import { CaptureState } from '../../state/capture.state';
import { TASK_TYPES } from '../../models/capture-session.model';
import { environment } from '../../../../environments/environment';

@Component({
  selector: 'app-task-selector',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="task-card">
      <h2 class="task-title">Aufgabe auswählen</h2>

      <label class="field-label">Aufgabentyp</label>
      <select class="field-select" [(ngModel)]="selectedType">
        @for (t of taskTypes; track t) {
          <option [value]="t">{{ t }}</option>
        }
      </select>

      <label class="field-label">Beschreibung (optional)</label>
      <input class="field-input" [(ngModel)]="taskLabel" placeholder="z. B. Bremssattel BMW 3er wechseln" />

      @if (starting()) {
        <p class="task-status">Aufzeichnung wird gestartet…</p>
      }
      @if (error()) {
        <p class="task-error">{{ error() }}</p>
      }

      <button class="btn-primary" [disabled]="!selectedType || starting()" (click)="start()">
        Aufzeichnung starten
      </button>
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; }
    .task-card { background: #1a2535; border-radius: 16px; padding: 40px; width: 100%; max-width: 480px; margin: 0 auto; box-sizing: border-box; color: #e8edf5; }
    .task-title { font-size: 20px; margin-bottom: 28px; }
    .field-label { display: block; font-size: 12px; color: #9aa8c4; text-transform: uppercase; letter-spacing: .07em; margin-bottom: 6px; margin-top: 20px; }
    .field-select, .field-input {
      width: 100%; padding: 10px 14px; border-radius: 8px;
      border: 1px solid #2a3f5f; background: #111c2a; color: #e8edf5;
      font-size: 14px; box-sizing: border-box;
    }
    .btn-primary { margin-top: 32px; width: 100%; padding: 14px; border-radius: 10px; border: none; background: #1976D2; color: #fff; font-size: 16px; cursor: pointer; }
    .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
    .task-status { color: #9aa8c4; font-size: 13px; margin-top: 16px; }
    .task-error { color: #ef5350; font-size: 13px; margin-top: 12px; }
  `],
})
export class TaskSelectorComponent {
  private store = inject(Store);
  private captureService = inject(CaptureSessionService);

  protected taskTypes = TASK_TYPES;
  protected selectedType = TASK_TYPES[0];
  protected taskLabel = '';
  protected starting = signal(false);
  protected error = signal<string | null>(null);

  private workerToken = toSignal(this.store.select(CaptureState.workerToken), { initialValue: null });

  async start(): Promise<void> {
    this.starting.set(true);
    this.error.set(null);
    try {
      const token = this.workerToken() ?? '';
      this.store.dispatch(new CaptureActions.SetTask(this.selectedType, this.taskLabel));
      await this.captureService.startSession(token, this.selectedType, this.taskLabel, environment.shopId);
    } catch (e) {
      this.error.set(e instanceof Error ? e.message : 'Fehler beim Starten.');
      this.starting.set(false);
    }
  }
}
