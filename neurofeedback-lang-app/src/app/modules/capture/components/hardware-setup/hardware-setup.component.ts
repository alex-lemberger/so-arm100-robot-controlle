// src/app/modules/capture/components/hardware-setup/hardware-setup.component.ts
import { Component, computed, effect, inject, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { combineLatest, map } from 'rxjs';
import { ImuService } from '../../services/imu.service';
import { VideoRecorderService } from '../../services/video-recorder.service';
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
import { CaptureActions } from '../../state/capture.actions';
import { environment } from '../../../../environments/environment';
import { EegSignalQualityService } from '../../services/eeg-signal-quality.service';

@Component({
  selector: 'app-hardware-setup',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule],
  template: `
    <div class="setup-card">
      <div class="setup-header">
        <p class="step-kicker">Schritt {{ currentStepNumber() }} von {{ steps.length }}</p>
        <h2 class="setup-title">{{ currentStep().title }}</h2>
        <p class="setup-body">{{ currentStep().body }}</p>
      </div>

      <div class="stepper" aria-label="Hardware Fortschritt">
        @for (step of steps; track step.key; let index = $index) {
          <span class="step-dot"
                [class.step-dot--active]="index === currentStepIndex()"
                [class.step-dot--done]="index < currentStepIndex()">
          </span>
        }
      </div>

      @switch (currentStep().key) {
        @case ('prep') {
          <div class="prep-panel">
            <mat-icon class="step-icon">checklist</mat-icon>
            <p class="prep-copy">
              Bereiten Sie die Handschuhe, Kamera und das EEG Headset vor.
              Die App führt jedes Gerät einzeln durch den Verbindungsprozess.
            </p>
          </div>
        }
        @case ('left') {
          <div class="device-step">
            <mat-icon class="step-icon step-icon--hand-left">back_hand</mat-icon>
            @if (!bluetoothSupported) {
              <p class="setup-error">
                Web Bluetooth wird von diesem Browser nicht unterstützt.
                Bitte Chrome auf Android verwenden.
              </p>
            }
            <div class="device-status">
              <span class="device-label">Linker Handschuh</span>
              <span class="chip" [class.chip--ok]="leftOk()">{{ leftOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
            </div>
            <button class="btn-primary" [disabled]="leftOk() || connecting() || !bluetoothSupported" (click)="connectLeft()">
              Linken Handschuh verbinden
            </button>
          </div>
        }
        @case ('right') {
          <div class="device-step">
            <mat-icon class="step-icon">back_hand</mat-icon>
            @if (!bluetoothSupported) {
              <p class="setup-error">
                Web Bluetooth wird von diesem Browser nicht unterstützt.
                Bitte Chrome auf Android verwenden.
              </p>
            }
            <div class="device-status">
              <span class="device-label">Rechter Handschuh</span>
              <span class="chip" [class.chip--ok]="rightOk()">{{ rightOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
            </div>
            <button class="btn-primary" [disabled]="rightOk() || connecting() || !bluetoothSupported" (click)="connectRight()">
              Rechten Handschuh verbinden
            </button>
          </div>
        }
        @case ('camera') {
          <div class="device-step">
            <mat-icon class="step-icon">videocam</mat-icon>
            <div class="device-status">
              <span class="device-label">Kamera</span>
              <span class="chip" [class.chip--ok]="cameraOk()">{{ cameraOk() ? '✓ Bereit' : 'Nicht bereit' }}</span>
            </div>
            <button class="btn-primary" [disabled]="cameraOk() || connecting()" (click)="connectCamera()">
              Kamerazugriff erlauben
            </button>
          </div>
        }
        @case ('eeg') {
          <div class="device-step">
            <mat-icon class="step-icon">headset</mat-icon>
            <div class="device-status">
              <span class="device-label">EEG Headset</span>
              <span class="chip" [class.chip--ok]="eegOk()">{{ eegOk() ? '✓ Verbunden' : 'Nicht verbunden' }}</span>
            </div>
          @if (!eegOk()) {
            <div class="eeg-credentials">
              <input class="field-input" type="email" [(ngModel)]="eegEmail" placeholder="EEG E-Mail" />
              <input class="field-input" type="password" [(ngModel)]="eegPassword" placeholder="EEG Passwort" />
            </div>
          }
            <button class="btn-primary" [disabled]="eegOk() || connecting()" (click)="connectEeg()">
              EEG Headset verbinden
            </button>

            @if (eegOk() && hasRawEeg) {
              <div class="electrode-row">
                @for (eq of eegQuality(); track eq.electrode) {
                  <div class="electrode-item">
                    <span class="electrode-dot"
                          [class.electrode-dot--unknown]="eq.state === 'unknown'"
                          [class.electrode-dot--poor]="eq.state === 'poor'"
                          [class.electrode-dot--good]="eq.state === 'good'">
                    </span>
                    <span class="electrode-label">{{ eq.name }}</span>
                  </div>
                }
              </div>
              <p class="quality-label"
                 [class.quality-label--good]="eegGateOpen()"
                 [class.quality-label--warn]="isQualityWarning()">
                {{ eegQualityLabel() }}
              </p>
            }
          </div>
        }
        @case ('review') {
          <div class="review-panel">
            <mat-icon class="step-icon step-icon--ok">task_alt</mat-icon>
            <h3>Bereit für Aufgabenwahl</h3>
            <div class="summary-row">
              <span>Linker Handschuh</span>
              <span class="chip chip--ok">✓ Verbunden</span>
            </div>
            <div class="summary-row">
              <span>Rechter Handschuh</span>
              <span class="chip chip--ok">✓ Verbunden</span>
            </div>
            <div class="summary-row">
              <span>Kamera</span>
              <span class="chip chip--ok">✓ Bereit</span>
            </div>
            <div class="summary-row">
              <span>EEG Headset</span>
              <span class="chip chip--ok">✓ Verbunden</span>
            </div>
          </div>
        }
      }

      @if (connectError()) {
        <p class="setup-error">{{ connectError() }}</p>
      }

      <div class="wizard-actions">
        <button class="btn-secondary" [disabled]="currentStepIndex() === 0 || connecting()" (click)="back()">
          Zurück
        </button>
        @if (isReviewStep()) {
          <button class="btn-primary" [disabled]="!allReady() || connecting()" (click)="advance()">
            Zur Aufgabenwahl
          </button>
        } @else {
          <button class="btn-secondary" [disabled]="!canContinue() || connecting()" (click)="next()">
            Weiter
          </button>
        }
      </div>
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; }
    .setup-card {
      width: 100%; max-width: 620px; margin: 0 auto;
      background: #1a2535;
      border-radius: 16px;
      padding: 40px;
      color: #e8edf5;
      box-sizing: border-box;
    }
    .setup-header { margin-bottom: 24px; }
    .step-kicker {
      margin: 0 0 8px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: #64b5f6;
    }
    .setup-title { font-size: 22px; margin: 0 0 12px; }
    .setup-body { color: #9aa8c4; line-height: 1.6; margin: 0; }
    .stepper { display: flex; gap: 8px; margin-bottom: 28px; }
    .step-dot {
      height: 6px;
      flex: 1;
      border-radius: 999px;
      background: #2a3545;
    }
    .step-dot--active { background: #64b5f6; }
    .step-dot--done { background: #1b6a46; }
    .prep-panel, .device-step, .review-panel {
      min-height: 176px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      justify-content: center;
    }
    .step-icon {
      font-size: 48px; width: 48px; height: 48px;
      color: #64b5f6; align-self: center;
    }
    .step-icon--hand-left { transform: scaleX(-1); }
    .step-icon--ok { color: #48bb78; }
    .prep-copy { margin: 0; color: #c7d2e4; line-height: 1.7; }
    .device-status, .summary-row { display: flex; align-items: center; gap: 12px; }
    .device-label { flex: 1; font-size: 14px; color: #9aa8c4; }
    .chip { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #2a3545; color: #9aa8c4; }
    .chip--ok { background: #1b3a2a; color: #4caf50; }
    .eeg-credentials { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .field-input {
      width: 100%; padding: 8px 10px; border-radius: 8px;
      border: 1px solid #2a3f5f; background: #111c2a; color: #e8edf5;
      font-size: 13px; box-sizing: border-box;
    }
    .review-panel h3 { margin: 0; font-size: 18px; }
    .wizard-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 32px; }
    .btn-primary,
    .btn-secondary {
      width: 100%;
      padding: 14px;
      border-radius: 10px;
      font-size: 15px;
      cursor: pointer;
    }
    .btn-primary { border: none; background: #1976D2; color: #fff; }
    .btn-secondary { border: 1px solid #2a3f5f; background: transparent; color: #c7d2e4; }
    .btn-primary:disabled,
    .btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }
    .setup-error { color: #ef5350; font-size: 13px; margin-bottom: 16px; }
    .electrode-row {
      display: flex;
      gap: 20px;
      justify-content: center;
      margin-top: 8px;
    }
    .electrode-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }
    .electrode-dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #2a3545;
      transition: background 0.3s;
    }
    .electrode-dot--unknown { background: #4a5568; }
    .electrode-dot--poor    { background: #e53e3e; }
    .electrode-dot--good    { background: #48bb78; }
    .electrode-label {
      font-size: 10px;
      color: #9aa8c4;
      font-family: 'DM Mono', monospace;
    }
    .quality-label {
      text-align: center;
      font-size: 13px;
      color: #9aa8c4;
      margin: 4px 0 0;
    }
    .quality-label--warn { color: #f6ad55; }
    .quality-label--good { color: #48bb78; }
    @media (max-width: 520px) {
      .eeg-credentials { grid-template-columns: 1fr; }
      .setup-card { padding: 28px; }
      .wizard-actions { grid-template-columns: 1fr; }
    }
  `],
})
export class HardwareSetupComponent implements OnDestroy {
  private store = inject(Store);
  private imuService = inject(ImuService);
  private videoService = inject(VideoRecorderService);
  private brainDevice = inject(BrainDevice);
  private eegQualityService = inject(EegSignalQualityService);

  protected bluetoothSupported = this.imuService.isSupported;
  protected leftOk = toSignal(this.imuService.leftConnected$, { initialValue: false });
  protected rightOk = toSignal(this.imuService.rightConnected$, { initialValue: false });
  protected cameraOk = toSignal(this.videoService.cameraReady$, { initialValue: false });
  protected eegOk = toSignal(
    this.brainDevice.state$.pipe(map((s) => s.isLoggedIn)),
    { initialValue: false },
  );
  protected eegEmail = environment.device === 'mock' ? 'test@example.com' : '';
  protected eegPassword = environment.device === 'mock' ? 'password123' : '';
  protected connecting = signal(false);
  protected connectError = signal<string | null>(null);
  protected currentStepIndex = signal(0);
  protected steps = [
    {
      key: 'prep',
      title: 'Sitzung vorbereiten',
      body: 'Prüfen Sie kurz die Arbeitsumgebung. Danach verbindet der Assistent jedes Aufnahmegerät einzeln.',
    },
    {
      key: 'left',
      title: 'Linken Handschuh verbinden',
      body: 'Schalten Sie den linken Handschuh ein und wählen Sie ihn im Bluetooth Dialog aus.',
    },
    {
      key: 'right',
      title: 'Rechten Handschuh verbinden',
      body: 'Schalten Sie den rechten Handschuh ein und verbinden Sie ihn als zweites Gerät.',
    },
    {
      key: 'camera',
      title: 'Kamera aktivieren',
      body: 'Erlauben Sie den Kamerazugriff für die Videoaufnahme des Handwerksprozesses.',
    },
    {
      key: 'eeg',
      title: 'EEG Headset verbinden',
      body: 'Verbinden Sie das EEG Headset. In Mock Mode sind Testdaten vorausgefüllt.',
    },
    {
      key: 'review',
      title: 'Hardware prüfen',
      body: 'Alle Geräte sind bereit. Starten Sie nun die Auswahl der Aufnahmeaufgabe.',
    },
  ] as const;
  protected currentStep = computed(() => this.steps[this.currentStepIndex()]);
  protected currentStepNumber = computed(() => this.currentStepIndex() + 1);
  protected isReviewStep = computed(() => this.currentStep().key === 'review');

  protected allReady = toSignal(
    combineLatest([
      this.imuService.leftConnected$,
      this.imuService.rightConnected$,
      this.videoService.cameraReady$,
      this.brainDevice.state$.pipe(map((s) => s.isLoggedIn)),
    ]).pipe(map(([l, r, cam, eeg]) => l && r && cam && eeg)),
    { initialValue: false },
  );

  protected readonly hasRawEeg = !!this.brainDevice.rawEeg$;
  protected eegGateOpen = toSignal(this.eegQualityService.gateOpen$, { initialValue: false });
  protected eegQuality = toSignal(this.eegQualityService.quality$, { initialValue: [] });
  protected eegQualityLabel = computed(() => {
    if (this.eegGateOpen()) return 'Signal bereit ✓';
    const qualityArray = this.eegQuality() || [];
    const goodCount = qualityArray.filter(q => q.state === 'good').length;
    return goodCount >= 3 ? 'Stabilisierung…' : 'Elektroden prüfen';
  });

  protected isQualityWarning = computed(() => {
    const qualityArray = this.eegQuality() || [];
    const goodCount = qualityArray.filter(q => q.state === 'good').length;
    return !this.eegGateOpen() && goodCount >= 3;
  });

  constructor() {
    // Start/stop signal quality monitoring when EEG connection status changes
    effect(() => {
      if (this.eegOk()) {
        this.eegQualityService.startMonitoring(this.brainDevice.rawEeg$);
      } else {
        this.eegQualityService.stopMonitoring();
      }
    });
  }

  ngOnDestroy(): void {
    this.eegQualityService.stopMonitoring();
  }

  canContinue(): boolean {
    switch (this.currentStep().key) {
      case 'prep':
        return true;
      case 'left':
        return this.leftOk();
      case 'right':
        return this.rightOk();
      case 'camera':
        return this.cameraOk();
      case 'eeg':
        return this.eegOk() && this.eegGateOpen();
      case 'review':
        return this.allReady();
    }
  }

  next(): void {
    if (!this.canContinue()) return;
    this.connectError.set(null);
    this.currentStepIndex.update((index) => Math.min(index + 1, this.steps.length - 1));
  }

  back(): void {
    this.connectError.set(null);
    this.currentStepIndex.update((index) => Math.max(index - 1, 0));
  }

  async connectLeft(): Promise<void> {
    await this.connect(() => this.imuService.connect('left'));
  }

  async connectRight(): Promise<void> {
    await this.connect(() => this.imuService.connect('right'));
  }

  async connectCamera(): Promise<void> {
    await this.connect(() => this.videoService.requestCamera());
  }

  async connectEeg(): Promise<void> {
    const credentials = this.eegEmail && this.eegPassword
      ? { email: this.eegEmail, password: this.eegPassword }
      : undefined;
    await this.connect(() => this.brainDevice.connect(credentials));
  }

  advance(): void {
    this.store.dispatch(new CaptureActions.AdvanceToTask());
  }

  private async connect(fn: () => Promise<void>): Promise<void> {
    this.connecting.set(true);
    this.connectError.set(null);
    try {
      await fn();
    } catch (e) {
      this.connectError.set(e instanceof Error ? e.message : 'Verbindung fehlgeschlagen.');
    } finally {
      this.connecting.set(false);
    }
  }
}
