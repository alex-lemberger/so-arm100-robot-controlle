// src/app/modules/capture/components/live-capture/live-capture.component.ts
import { Component, inject, OnDestroy, ElementRef, ViewChild, AfterViewInit, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Store } from '@ngxs/store';
import { toSignal } from '@angular/core/rxjs-interop';
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
import { ImuService } from '../../services/imu.service';
import { VideoRecorderService } from '../../services/video-recorder.service';
import { CaptureSessionService } from '../../services/capture-session.service';
import { MetricRingComponent } from '../../../../shared/components/layout/dashboard-layout/widgets/metric-ring.component';

@Component({
  selector: 'app-live-capture',
  standalone: true,
  imports: [CommonModule, MetricRingComponent],
  template: `
    <div class="live-card">
      <div class="status-row">
        <span class="rec-dot"></span>
        <span class="rec-label">REC</span>
        <span class="timecode">{{ timecode() }}</span>
        <span class="chip" [class.chip--ok]="leftOk()">L {{ leftOk() ? '✓' : '!' }}</span>
        <span class="chip" [class.chip--ok]="rightOk()">R {{ rightOk() ? '✓' : '!' }}</span>
      </div>

      <div class="rings-row">
        <app-metric-ring [value]="focus()" label="Focus" icon="psychology" color="#1976D2" paleColor="#E3F2FD" />
        <app-metric-ring [value]="calm()" label="Calm" icon="self_improvement" color="#388E3C" paleColor="#E8F5E9" />
      </div>

      <video #videoPreview class="video-preview" autoplay muted playsinline></video>

      <button class="btn-stop" [disabled]="stopping()" (click)="stop()">
        {{ stopping() ? 'Wird beendet…' : '■ Aufzeichnung beenden' }}
      </button>
    </div>
  `,
  styles: [`
    :host { display: block; width: 100%; }
    .live-card { background: #1a2535; border-radius: 16px; padding: 32px; width: 100%; max-width: 520px; margin: 0 auto; box-sizing: border-box; color: #e8edf5; display: flex; flex-direction: column; gap: 24px; }
    .status-row { display: flex; align-items: center; gap: 10px; }
    .rec-dot { width: 10px; height: 10px; border-radius: 50%; background: #ef5350; animation: blink 1s step-start infinite; }
    .rec-label { font-size: 12px; font-weight: 700; color: #ef5350; letter-spacing: .1em; }
    .timecode { font-family: var(--c-mono, 'DM Mono', monospace); font-size: 15px; font-weight: 600; color: #e8edf5; letter-spacing: .05em; flex: 1; }
    .chip { padding: 4px 10px; border-radius: 20px; font-size: 12px; background: #2a3545; color: #9aa8c4; }
    .chip--ok { background: #1b3a2a; color: #4caf50; }
    .rings-row { display: flex; justify-content: center; gap: 32px; }
    .video-preview { width: 100%; border-radius: 10px; background: #111; max-height: 200px; object-fit: cover; }
    .btn-stop { width: 100%; padding: 16px; border-radius: 10px; border: 2px solid #ef5350; background: transparent; color: #ef5350; font-size: 16px; font-weight: 600; cursor: pointer; }
    .btn-stop:disabled { opacity: 0.4; cursor: not-allowed; }
    @keyframes blink { 50% { opacity: 0; } }
  `],
})
export class LiveCaptureComponent implements AfterViewInit, OnDestroy {
  @ViewChild('videoPreview') videoRef!: ElementRef<HTMLVideoElement>;

  private store = inject(Store);
  private brainDevice = inject(BrainDevice);
  private imuService = inject(ImuService);
  private videoService = inject(VideoRecorderService);
  private captureService = inject(CaptureSessionService);

  protected focus = toSignal(this.brainDevice.focus$, { initialValue: null });
  protected calm = toSignal(this.brainDevice.calm$, { initialValue: null });
  protected leftOk = toSignal(this.imuService.leftConnected$, { initialValue: false });
  protected rightOk = toSignal(this.imuService.rightConnected$, { initialValue: false });
  protected stopping = toSignal(
    this.store.select((s: any) => s.capture?.status === 'uploading'),
    { initialValue: false },
  );

  private readonly elapsed = signal(0);
  private timerId: ReturnType<typeof setInterval> | null = null;

  protected readonly timecode = computed(() => {
    const s = this.elapsed();
    const mm = Math.floor(s / 60).toString().padStart(2, '0');
    const ss = (s % 60).toString().padStart(2, '0');
    return `${mm}:${ss}`;
  });

  constructor() {
    this.timerId = setInterval(() => this.elapsed.update(n => n + 1), 1000);
  }

  ngAfterViewInit(): void {
    const stream = this.videoService.previewStream;
    if (stream) this.videoRef.nativeElement.srcObject = stream;
  }

  ngOnDestroy(): void {
    if (this.timerId !== null) clearInterval(this.timerId);
  }

  async stop(): Promise<void> {
    await this.captureService.stopSession();
  }
}