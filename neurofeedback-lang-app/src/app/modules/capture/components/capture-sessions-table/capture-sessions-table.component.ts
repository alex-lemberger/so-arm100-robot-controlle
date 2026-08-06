// src/app/modules/capture/services/capture-sessions-table.component.ts
import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureHistoryService } from '../../services/capture-history.service';
import { CaptureModeService } from '../../services/capture-mode.service';
import { CaptureRow } from '../../models/capture-session.model';
import { SupabaseCaptureService } from '../../services/supabase-capture.service';
import { SimBridgeService, SimEegTick } from '../../../../core/sim-bridge/sim-bridge.service';
import { SimControlComponent } from '../../../../shared/components/layout/dashboard-layout/widgets/sim-control.component';
import { environment } from '../../../../environments/environment';

function formatDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
}

function formatDuration(created: string, ended: string | null): string {
  if (!ended) return '—';
  const ms = new Date(ended).getTime() - new Date(created).getTime();
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
  const s = (totalSec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function storageUrl(path: string | null): string | null {
  if (!path) return null;
  return `${environment.supabase.url}/storage/v1/object/public/captures/${path}`;
}

@Component({
  selector: 'app-capture-sessions-table',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule, SimControlComponent],
  template: `
    <div class="tbl-wrap">
      @if (sessions().length === 0) {
        <div class="empty">
          <mat-icon class="empty__icon">history</mat-icon>
          <span class="empty__text">Noch keine Aufzeichnungen</span>
        </div>
      } @else {
        <table class="tbl">
          <thead>
            <tr>
              <th class="col-toggle"></th>
              <th>Datum/Zeit</th>
              <th>Aufgabe</th>
              <th>Dauer</th>
              <th>Status</th>
              <th class="num">EEG Ticks</th>
              <th>Video</th>
              <th>IMU L</th>
              <th>IMU R</th>
              <th>EEG</th>
              <th>Sim</th>
            </tr>
          </thead>
          <tbody>
            @for (row of sessions(); track row.id) {
              <tr [class.tr--expanded]="expandedRowId() === row.id">
                <td class="col-toggle">
                  @if (row.status === 'complete') {
                    <button class="toggle-btn" (click)="toggleExpand(row.id)"
                            [attr.aria-expanded]="expandedRowId() === row.id">
                      <mat-icon class="toggle-icon" [class.toggle-icon--open]="expandedRowId() === row.id">
                        chevron_right
                      </mat-icon>
                    </button>
                  }
                </td>
                <td>{{ formatDate(row.created_at) }}</td>
                <td>
                  <span class="task-type">{{ row.task_type }}</span>
                  @if (row.task_label) {
                    <span class="task-label">{{ row.task_label }}</span>
                  }
                </td>
                <td class="num">{{ formatDuration(row.created_at, row.ended_at) }}</td>
                <td>
                  <span class="chip"
                        [class.chip--green]="row.status === 'complete'"
                        [class.chip--red]="row.status === 'failed'"
                        [class.chip--amber]="row.status === 'recording' || row.status === 'uploading'">
                    {{ row.status }}
                  </span>
                </td>
                <td class="num">{{ row.eeg_tick_count }}</td>
                <td>
                  @if (storageUrl(row.video_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.imu_left_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.imu_right_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.eeg_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (simBridge.status() !== 'disconnected' && row.status === 'complete') {
                    <button mat-icon-button class="transfer-btn"
                      [disabled]="simBridge.status() === 'replaying' || simBridge.status() === 'paused' || transferring() !== null"
                      (click)="transfer(row)">
                      <mat-icon>play_circle</mat-icon>
                    </button>
                  } @else {
                    <span>—</span>
                  }
                </td>
              </tr>
              @if (expandedRowId() === row.id) {
                <tr class="expansion-row">
                  <td colspan="11">
                    <div class="expansion-panel">
                      <app-sim-control />
                    </div>
                  </td>
                </tr>
              }
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }
    .tbl-wrap { overflow-x: auto; }
    .tbl { width: 100%; border-collapse: collapse; }
    thead tr { background: #f4f7fb; }
    thead th {
      padding: 11px 16px;
      font-size: 11px; font-weight: 600; letter-spacing: .06em;
      text-transform: uppercase; color: #9aa8c4;
      text-align: left; white-space: nowrap;
      border-bottom: 1px solid #dde5f2;
    }
    thead th.num { text-align: right; }
    thead th.col-toggle { width: 40px; padding: 0 0 0 12px; }
    thead th:last-child { padding-right: 24px; }
    tbody tr { border-bottom: 1px solid #eef2fa; transition: background .1s; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover:not(.expansion-row) { background: #f8fafd; }
    tbody td { padding: 11px 16px; white-space: nowrap; color: #18253f; font-size: 13px; }
    tbody td:last-child { padding-right: 24px; }
    .col-toggle { width: 40px; padding: 0 0 0 12px !important; }
    .toggle-btn {
      background: none; border: none; cursor: pointer; padding: 4px;
      display: flex; align-items: center; justify-content: center;
      border-radius: 4px; color: #9aa8c4;
    }
    .toggle-btn:hover { background: #eef2fa; color: #1976d2; }
    .toggle-icon { font-size: 18px; height: 18px; width: 18px; transition: transform .2s; }
    .toggle-icon--open { transform: rotate(90deg); }
    .tr--expanded { background: #f4f7fb; }
    .tr--expanded:hover { background: #f4f7fb !important; }
    .expansion-row { background: #f4f7fb; }
    .expansion-row:hover { background: #f4f7fb !important; }
    .expansion-row td { padding: 0 24px 20px 52px; border-bottom: 2px solid #dde5f2; }
    .expansion-panel { max-width: 560px; }
    .num { font-family: 'DM Mono', ui-monospace, monospace; color: #5a6a8e; text-align: right; }
    .chip {
      padding: 3px 9px; border-radius: 20px;
      font-size: 11px; font-weight: 600; display: inline-block;
      background: #eef2f9; color: #9aa8c4;
    }
    .chip--green { background: #e8f5ee; color: #2e7d32; }
    .chip--red   { background: #fce8e8; color: #c62828; }
    .chip--amber { background: #fff3e0; color: #e65100; }
    .file-link {
      color: #1976d2; display: inline-flex;
      align-items: center; gap: 2px; text-decoration: none; opacity: .8;
    }
    .file-link:hover { opacity: 1; }
    .file-link mat-icon { font-size: 14px; height: 14px; width: 14px; }
    .empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 10px; padding: 48px 24px; color: #9aa8c4;
    }
    .empty__icon { font-size: 36px; height: 36px; width: 36px; }
    .empty__text { font-size: 14px; }
    .transfer-btn { color: #1976d2; }
    .transfer-btn[disabled] { color: #9aa8c4; }
    .task-type { display: block; font-size: 13px; color: #18253f; }
    .task-label { display: block; font-size: 11px; color: #9aa8c4; margin-top: 2px; }
  `],
})
export class CaptureSessionsTableComponent {
  private historyService = inject(CaptureHistoryService);
  private supabaseCapture = inject(SupabaseCaptureService);
  private captureMode = inject(CaptureModeService);
  protected simBridge = inject(SimBridgeService);
  private snackBar = inject(MatSnackBar);

  protected sessions = toSignal(this.historyService.sessions$, { initialValue: [] as CaptureRow[] });
  protected transferring = signal<string | null>(null);
  protected expandedRowId = signal<string | null>(null);

  protected formatDate = formatDate;
  protected formatDuration = formatDuration;

  protected storageUrl(path: string | null): string | null {
    return storageUrl(path);
  }

  protected toggleExpand(id: string): void {
    this.expandedRowId.update(current => current === id ? null : id);
  }

  protected async transfer(row: CaptureRow): Promise<void> {
    this.transferring.set(row.id);
    try {
      const eegTicks = this.captureMode.isMock()
        ? this.syntheticTicks(row.eeg_tick_count ?? 20)
        : (await this.supabaseCapture.fetchEegTicks(row.id!))
            .map(t => ({ ...t, inFlow: t.inFlow ?? false }));
      const sent = this.simBridge.transferSession({
        sessionId: row.id!,
        taskLabel: row.task_label ?? '',
        durationMs: this.durationMs(row.created_at, row.ended_at),
        eegTicks,
      });
      if (sent) {
        this.expandedRowId.set(row.id);
      } else {
        this.snackBar.open('Sim nicht verbunden', 'Schließen', { duration: 3000, verticalPosition: 'top' });
      }
    } catch {
      this.snackBar.open('Sitzungsdaten konnten nicht geladen werden', 'Schließen', { duration: 3000, verticalPosition: 'top' });
    } finally {
      this.transferring.set(null);
    }
  }

  private durationMs(created: string, ended: string | null | undefined): number {
    if (!ended) return 0;
    return new Date(ended).getTime() - new Date(created).getTime();
  }

  private syntheticTicks(n: number): SimEegTick[] {
    const count = Math.max(n, 20);
    return Array.from({ length: count }, (_, i) => {
      const t = i / (count - 1);
      return {
        focus: 0.5 + 0.3 * Math.sin(2 * Math.PI * 1.5 * t),
        calm: 0.6 + 0.2 * Math.cos(2 * Math.PI * t),
        load: 0.4 + 0.2 * Math.sin(2 * Math.PI * 0.7 * t),
        fatigue: 0.1 + 0.4 * t,
        inFlow: t > 0.35 && t < 0.75,
      };
    });
  }
}
