import {
  Component, OnDestroy, computed, inject, signal,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { User } from '@supabase/supabase-js';

import { LearningSessionService } from '../../../../core/neurofeedback/services/learning-session.service';
import { BrainDevice } from '../../../../core/neurofeedback/brain-device';
import { FlowDetectorService } from '../../../../core/neurofeedback/services/flow-detector.service';
import { MetricRingComponent } from './widgets/metric-ring.component';
import { EegWaveformComponent } from './widgets/eeg-waveform.component';
import { WeeklyBarChartComponent, WeeklyBar } from './widgets/weekly-bar-chart.component';
import { SupabaseAuthService } from '../../../../core/supabase/supabase-auth.service';
import { CaptureHistoryService } from '../../../../modules/capture/services/capture-history.service';
import { CaptureSessionsTableComponent } from '../../../../modules/capture/components/capture-sessions-table/capture-sessions-table.component';
import { CaptureRow } from '../../../../modules/capture/models/capture-session.model';
import { EngagementSource } from '../../../../core/engagement/engagement-source';
import { environment } from '../../../../environments/environment';
import { SimBridgeService } from '../../../../core/sim-bridge/sim-bridge.service';

interface PracticeItem {
  id: number;
  title: string;
  lang: string;
  duration: string;
  status: 'active' | 'queued' | 'done';
}

/** Calm accent — a restful teal, deliberately distinct from the azure focus hue. */
const CALM = { main: '#2E9E85', pale: '#E0F5F1' } as const;

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatSnackBarModule,
    MetricRingComponent,
    EegWaveformComponent,
    WeeklyBarChartComponent,
    CaptureSessionsTableComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.scss'],
})
export class DashboardComponent implements OnDestroy {
  private readonly authService = inject(SupabaseAuthService);
  private readonly device = inject(BrainDevice);
  private readonly learningSession = inject(LearningSessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly flowDetector = inject(FlowDetectorService);
  private readonly captureHistory = inject(CaptureHistoryService);
  private readonly engagementSource = inject(EngagementSource);
  private readonly simBridge = inject(SimBridgeService);
  readonly captureSessions = toSignal(this.captureHistory.sessions$, { initialValue: [] as CaptureRow[] });
  readonly captureSessionCount = computed(() => this.captureSessions().length);

  /** true when metrics come from interaction heuristics, false for biometric. */
  readonly isProxy = signal(true);

  readonly CALM = CALM;
  readonly focusColor = '#1976D2';
  readonly focusPale = '#E3F2FD';

  /**
   * Live engagement streams (0–1, null until data). Sourced from EngagementSource,
   * so Standard tier shows interaction-cadence focus (no headset; calm is null)
   * and Premium shows the headset's biometric focus/calm.
   */
  readonly focus = toSignal(this.engagementSource.focus$, { initialValue: null as number | null });
  readonly calm = toSignal(this.engagementSource.calm$, { initialValue: null as number | null });

  readonly deviceState = toSignal(this.device.state$, { initialValue: { isLoggedIn: false, error: null } });
  readonly deviceConnected = computed(() => this.deviceState().isLoggedIn);
  readonly deviceError = computed(() => this.deviceState().error);
  readonly connectBusy = signal(false);

  readonly inFlow = toSignal(this.flowDetector.inFlow$, { initialValue: false });
  readonly flowSeconds = signal(0);
  readonly elapsed = signal(0);
  
  // Convert timer and greeting logic to computed signals
  readonly timer = computed(() => {
    const s = this.elapsed();
    const h = String(Math.floor(s / 3600)).padStart(2, '0');
    const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    const sec = String(s % 60).padStart(2, '0');
    return `${h}:${m}:${sec}`;
  });

  readonly greeting = computed(() => {
    const h = new Date().getHours();
    return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  });
  
  readonly userName = signal('there');
  readonly today = new Date().toLocaleDateString('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric',
  });

  // Convert flow percent to computed signal
  readonly flowPercent = computed(() => {
    const e = this.elapsed();
    return e > 0 ? Math.round((this.flowSeconds() / e) * 100) : 0;
  });

  readonly sessionActive = signal(false);
  readonly busy = signal(false);
  private timerId?: ReturnType<typeof setInterval>;
  private userId: string | null = null;

  /** Today's practice queue — first item is the one in progress. */
  readonly exercises: PracticeItem[] = [
    { id: 1, title: 'Vocabulary in Context', lang: 'Japanese · N4', duration: '8 min', status: 'active' },
    { id: 2, title: 'Sentence Construction', lang: 'Japanese · N4', duration: '12 min', status: 'queued' },
    { id: 3, title: 'Listening & Recall', lang: 'Japanese · N4', duration: '10 min', status: 'queued' },
  ];

  /** Weekly trend — Mon–Sun; future days are zero and render ghosted. */
  readonly weekly: WeeklyBar[] = [
    { day: 'M', focus: .71, calm: .62 },
    { day: 'T', focus: .74, calm: .67 },
    { day: 'W', focus: .68, calm: .58 },
    { day: 'T', focus: .79, calm: .71 },
    { day: 'F', focus: .75, calm: .64 },
    { day: 'Sa', focus: 0, calm: 0 },
    { day: 'Su', focus: 0, calm: 0 },
  ];
  readonly todayIndex = 4;

  readonly avgFocus = mean(this.weekly.map((d) => d.focus));
  readonly avgCalm = mean(this.weekly.map((d) => d.calm));

  readonly goalPercent = 74;
  readonly goalCirc = 2 * Math.PI * 18;
  readonly goalOffset = this.goalCirc * (1 - 0.74);

  constructor() {
    this.isProxy.set(environment.engagementTier === 'standard');
    this.authService.session$.pipe(takeUntilDestroyed()).subscribe(session => {
      this.userId = session?.user?.id ?? null;
      const email = session?.user?.email ?? null;
      this.userName.set(email ? capitalize(email.split('@')[0]) : 'there');
    });
    this.captureHistory.load();
    this.simBridge.connect();
  }

  async connectDevice(): Promise<void> {
    if (this.connectBusy()) return;
    this.connectBusy.set(true);
    try {
      await this.device.connect();
    } catch (err) {
      this.notify(this.deviceState().error ?? 'Connection failed');
    } finally {
      this.connectBusy.set(false);
    }
  }

  async disconnectDevice(): Promise<void> {
    await this.device.disconnect();
  }

  async startSession(): Promise<void> {
    if (this.busy()) { return; }
    this.busy.set(true);
    try {
      if (this.userId) {
        await this.learningSession.startSession(this.userId);
      }
      this.elapsed.set(0);
      this.flowSeconds.set(0);
      this.sessionActive.set(true);
      this.startTimer();
    } catch {
      this.notify('Could not start the session');
    } finally {
      this.busy.set(false);
    }
  }

  async endSession(): Promise<void> {
    if (this.busy()) { return; }
    this.busy.set(true);
    try {
      await this.learningSession.endSession();
    } catch {
      this.notify('Could not end the session cleanly');
    } finally {
      this.stopTimer();
      this.sessionActive.set(false);
      this.busy.set(false);
    }
  }

  private startTimer(): void {
    this.stopTimer();
    this.timerId = setInterval(() => {
      this.elapsed.update((s) => s + 1);
      if (this.inFlow()) { 
        this.flowSeconds.update((s) => s + 1); 
      }
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timerId) { clearInterval(this.timerId); this.timerId = undefined; }
  }

  private notify(message: string): void {
    this.snackBar.open(message, 'Close', { duration: 3000, verticalPosition: 'top' });
  }

  ngOnDestroy(): void {
    this.stopTimer();
    this.simBridge.disconnect();
  }
}

function mean(values: number[]): string {
  const live = values.filter((v) => v > 0);
  if (!live.length) { return '0.00'; }
  return (live.reduce((a, b) => a + b, 0) / live.length).toFixed(2);
}
function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}
