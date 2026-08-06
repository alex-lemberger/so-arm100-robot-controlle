import { Injectable, OnDestroy } from '@angular/core';
import { EngagementSource } from '../../engagement/engagement-source';
import { BehaviorSubject, Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SupabaseClientService } from '../../supabase/supabase-client.service';

interface SessionState {
  isActive: boolean;
  sessionId: string | null;
  currentFocus: number;
  currentCalm: number;
  averageFocus: number;
  averageCalm: number;
  duration: number;
}

@Injectable({ providedIn: 'root' })
export class LearningSessionService implements OnDestroy {
  private destroy$ = new Subject<void>();
  private metricsSubscription?: Subscription;
  private sessionUpdateInterval?: Subscription;
  private metricsList: { focus: number; calm: number }[] = [];

  private _sessionState = new BehaviorSubject<SessionState>({
    isActive: false,
    sessionId: null,
    currentFocus: 0,
    currentCalm: 0,
    averageFocus: 0,
    averageCalm: 0,
    duration: 0,
  });

  public sessionState$ = this._sessionState.asObservable();

  constructor(
    private readonly supabase: SupabaseClientService,
    private source: EngagementSource,
  ) {}

  async startSession(userId: string): Promise<void> {
    if (this._sessionState.value.isActive) {
      throw new Error('Session already in progress');
    }
    const { data, error } = await this.supabase.client
      .from('learning_sessions')
      .insert({ user_id: userId, status: 'active' })
      .select('id')
      .single();
    if (error) throw new Error(error.message);
    const sessionId = data.id as string;

    this._sessionState.next({ ...this._sessionState.value, isActive: true, sessionId });
    this.metricsList = [];
    this.startMetricsCollection(sessionId);
    this.startSessionUpdates();
  }

  private startMetricsCollection(sessionId: string): void {
    this.metricsSubscription = new Subscription();
    this.metricsSubscription.add(
      this.source.focus$.subscribe(focus => {
        if (focus !== null) {
          this.updateMetrics(sessionId, focus, this._sessionState.value.currentCalm);
        }
      })
    );
    this.metricsSubscription.add(
      this.source.calm$.subscribe(calm => {
        if (calm !== null) {
          this.updateMetrics(sessionId, this._sessionState.value.currentFocus, calm);
        }
      })
    );
  }

  private startSessionUpdates(): void {
    this.sessionUpdateInterval = interval(1000)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        const s = this._sessionState.value;
        this._sessionState.next({ ...s, duration: s.duration + 1 });
      });
  }

  private async updateMetrics(sessionId: string, focus: number, calm: number): Promise<void> {
    this.metricsList.push({ focus, calm });
    const averageFocus = this.metricsList.reduce((a, c) => a + c.focus, 0) / this.metricsList.length;
    const averageCalm = this.metricsList.reduce((a, c) => a + c.calm, 0) / this.metricsList.length;

    this._sessionState.next({
      ...this._sessionState.value,
      currentFocus: focus,
      currentCalm: calm,
      averageFocus,
      averageCalm,
    });

    const { data: current, error: fetchErr } = await this.supabase.client
      .from('learning_sessions')
      .select('brain_metrics')
      .eq('id', sessionId)
      .single();
    if (fetchErr) { console.error('Failed to fetch metrics:', fetchErr.message); return; }

    const metrics = [
      ...(current.brain_metrics ?? []),
      { timestamp: new Date().toISOString(), focus, calm },
    ];
    const { error } = await this.supabase.client
      .from('learning_sessions')
      .update({ brain_metrics: metrics, average_focus: averageFocus, average_calm: averageCalm })
      .eq('id', sessionId);
    if (error) console.error('Failed to update metrics:', error.message);
  }

  async endSession(): Promise<void> {
    const s = this._sessionState.value;
    if (!s.isActive || !s.sessionId) throw new Error('No active session to end');

    const { error } = await this.supabase.client
      .from('learning_sessions')
      .update({
        status: 'completed',
        ended_at: new Date().toISOString(),
        average_focus: s.averageFocus,
        average_calm: s.averageCalm,
      })
      .eq('id', s.sessionId);
    if (error) throw new Error(error.message);

    this.metricsSubscription?.unsubscribe();
    this.sessionUpdateInterval?.unsubscribe();
    this._sessionState.next({
      isActive: false, sessionId: null,
      currentFocus: 0, currentCalm: 0,
      averageFocus: 0, averageCalm: 0, duration: 0,
    });
  }

  async interruptSession(): Promise<void> {
    const s = this._sessionState.value;
    if (!s.isActive || !s.sessionId) return;

    await this.supabase.client
      .from('learning_sessions')
      .update({ status: 'interrupted', ended_at: new Date().toISOString() })
      .eq('id', s.sessionId);

    this.metricsSubscription?.unsubscribe();
    this.sessionUpdateInterval?.unsubscribe();
    this._sessionState.next({
      isActive: false, sessionId: null,
      currentFocus: 0, currentCalm: 0,
      averageFocus: 0, averageCalm: 0, duration: 0,
    });
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.metricsSubscription?.unsubscribe();
    this.sessionUpdateInterval?.unsubscribe();
    if (this._sessionState.value.isActive) this.interruptSession();
  }
}
