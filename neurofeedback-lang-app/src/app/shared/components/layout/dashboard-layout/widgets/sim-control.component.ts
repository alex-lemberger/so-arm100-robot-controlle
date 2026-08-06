import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { SimBridgeService, SimEegTick } from '../../../../../core/sim-bridge/sim-bridge.service';
import { RobotViewerComponent } from './robot-viewer.component';

@Component({
  selector: 'app-sim-control',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule, RobotViewerComponent],
  template: `
    <div class="sim">
      <app-robot-viewer
        [joints]="bridge.joints()"
        [status]="status()">
      </app-robot-viewer>
      <div class="sim__header">
        <span class="sim__dot"
              [class.sim__dot--on]="status() !== 'disconnected'"
              [class.sim__dot--connecting]="status() === 'connecting'"></span>
        <span class="sim__title">Robot Sim</span>
      </div>

      @if (status() === 'connecting') {
        <div class="sim__offline">
          <span class="sim__connecting">Connecting…</span>
        </div>
      }

      @if (status() === 'disconnected') {
        <div class="sim__offline">
          <span>Sim offline</span>
          @if (!isCloudSim) {
            <button mat-stroked-button data-testid="btn-launch"
                    [disabled]="bridge.launching()"
                    (click)="launchSim()">
              {{ bridge.launching() ? '…' : 'Launch Sim' }}
            </button>
          }
          @if (isCloudSim) {
            <button mat-stroked-button data-testid="btn-connect"
                    (click)="bridge.connect()">
              Connect
            </button>
          }
        </div>
      }

      @if (status() === 'idle') {
        <div class="sim__idle">
          <span>Ready</span>
          <button mat-stroked-button data-testid="btn-play-demo" (click)="playDemo()">
            <mat-icon>play_arrow</mat-icon>
            Play Demo
          </button>
        </div>
      }

      @if (status() === 'replaying' || status() === 'paused') {
        <div class="sim__progress-wrap">
          <div class="sim__progress-bar">
            <div class="sim__progress-fill" [style.width.%]="progressPct()"></div>
          </div>
          <span class="sim__tick">{{ bridge.tick() }} / {{ bridge.totalTicks() }}</span>
        </div>

        <div class="sim__eeg">
          @if (bridge.currentEegTick(); as t) {
            <span class="sim__metric" title="Focus">F <span class="sim__val">{{ (t.focus * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Calm">C <span class="sim__val">{{ (t.calm * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Load">L <span class="sim__val">{{ ((t.load ?? 0) * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Fatigue">Fa <span class="sim__val">{{ ((t.fatigue ?? 0) * 100) | number:'1.0-0' }}</span></span>
            @if (t.inFlow) {
              <span class="sim__flow-badge">Flow</span>
            }
          }
        </div>

        <div class="sim__controls" role="group" aria-label="Playback controls">
          @if (status() === 'replaying') {
            <button mat-icon-button data-playback="true" data-testid="btn-pause" (click)="bridge.pause()" aria-label="Pause replay">
              <mat-icon aria-hidden="true">pause</mat-icon>
            </button>
          }
          @if (status() === 'paused') {
            <button mat-icon-button data-playback="true" data-testid="btn-resume" (click)="bridge.resume()" aria-label="Resume replay">
              <mat-icon aria-hidden="true">play_arrow</mat-icon>
            </button>
          }
          <button mat-icon-button data-playback="true" data-testid="btn-stop" (click)="bridge.stop()" aria-label="Stop replay">
            <mat-icon aria-hidden="true">stop</mat-icon>
          </button>
        </div>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }
    .sim { padding: 16px 20px; background: #fff; border-radius: 12px; border: 1px solid #dde5f2; }
    .sim__header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .sim__dot { width: 8px; height: 8px; border-radius: 50%; background: #cdd5e0; }
    .sim__dot--on { background: #2e7d32; }
    .sim__dot--connecting { background: #f59e0b; animation: pulse 1.2s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
    .sim__connecting { color: #f59e0b; font-size: 13px; }
    .sim__title { font-size: 12px; font-weight: 600; color: #9aa8c4; text-transform: uppercase; letter-spacing: .06em; }
    .sim__offline { display: flex; align-items: center; gap: 12px; color: #9aa8c4; font-size: 13px; }
    .sim__idle { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #9aa8c4; }
    .sim__progress-wrap { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
    .sim__progress-bar { flex: 1; height: 4px; background: #eef2fa; border-radius: 2px; overflow: hidden; }
    .sim__progress-fill { height: 100%; background: #1976d2; border-radius: 2px; transition: width .2s; }
    .sim__tick { font-family: var(--c-mono, 'DM Mono', monospace); font-size: 11px; color: #9aa8c4; white-space: nowrap; }
    .sim__eeg { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
    .sim__metric { font-size: 11px; color: #9aa8c4; }
    .sim__val { font-family: var(--c-mono, 'DM Mono', monospace); color: #18253f; }
    .sim__flow-badge { font-size: 10px; font-weight: 700; background: #e8f5ee; color: #2e7d32; padding: 2px 7px; border-radius: 10px; }
    .sim__controls { display: flex; gap: 4px; }
    app-robot-viewer { display: block; margin: -16px -20px 12px;
      border-radius: 12px 12px 0 0; overflow: hidden; }
  `],
})
export class SimControlComponent {
  protected readonly bridge = inject(SimBridgeService);
  private readonly snackBar = inject(MatSnackBar);
  protected readonly status = this.bridge.status;
  protected readonly isCloudSim = this.bridge.isCloudSim;

  protected async launchSim(): Promise<void> {
    try {
      await this.bridge.launchSim();
    } catch {
      this.snackBar.open(
        'Launcher not running — start with: npm run dev',
        'OK',
        { duration: 6000 },
      );
    }
  }

  private buildDemoTicks(n = 60): SimEegTick[] {
    return Array.from({ length: n }, (_, i) => {
      const t = i / (n - 1);
      const focus = 0.5 + 0.4 * Math.sin(2 * Math.PI * 1.5 * t);
      return {
        focus,
        calm: 0.6 + 0.3 * Math.cos(2 * Math.PI * t),
        load: 0.4 + 0.2 * Math.sin(2 * Math.PI * 0.7 * t),
        fatigue: 0.1 + 0.4 * t,
        inFlow: focus > 0.8,
      };
    });
  }

  protected playDemo(): void {
    this.bridge.transferSession({
      sessionId: 'demo',
      taskLabel: 'Demo Replay',
      durationMs: 30_000,
      eegTicks: this.buildDemoTicks(60),
    });
  }

  protected readonly progressPct = computed(() => {
    const total = this.bridge.totalTicks();
    if (total <= 0) return 0;
    return Math.min(100, Math.round((this.bridge.tick() / total) * 100));
  });
}
