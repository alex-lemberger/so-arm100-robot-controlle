import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject, from, catchError, map as rxMap, of } from 'rxjs';
import { take } from 'rxjs/operators';
import { BrainMetrics, SessionData, CorrelationData } from '../../shared/components/layout/dashboard-layout/dashboard.model';
import { environment } from '../../environments/environment';
import { SupabaseClientService } from '../../core/supabase/supabase-client.service';
import { EngagementSource } from '../../core/engagement/engagement-source';

export interface EngagementProvenance {
  isProxy: boolean | null;
}

const FOCUS_METRIC_SCALING_FACTOR = 100000;

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly provenance$ = new BehaviorSubject<EngagementProvenance>({ isProxy: null });

  constructor(
    private readonly supabase: SupabaseClientService,
    engagementSource: EngagementSource,
  ) {
    engagementSource.getInteractionMetrics().pipe(
      take(1),
    ).subscribe(metrics => {
      this.provenance$.next({ isProxy: metrics.isProxy });
    }).add(() => {});

    if (environment.engagementTier === 'standard') {
      this.provenance$.next({ isProxy: true });
    } else {
      this.provenance$.next({ isProxy: false });
    }
  }

  getProvenance$: Observable<EngagementProvenance> = this.provenance$.asObservable();

  fetchMetrics(userId: string, dateRange?: { start: Date; end: Date }): Observable<BrainMetrics> {
    if (environment.useMockData) return this.getMockBrainMetrics();

    let days = 7;
    if (dateRange?.start && dateRange?.end) {
      days = Math.ceil(Math.abs(dateRange.end.getTime() - dateRange.start.getTime()) / (1000 * 60 * 60 * 24));
    }
    const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

    return from(
      this.supabase.client
        .from('learning_sessions')
        .select('average_focus, average_calm')
        .eq('user_id', userId)
        .eq('status', 'completed')
        .gte('started_at', since)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          const rows = data ?? [];
          const avgFocus = rows.length
            ? rows.reduce((a, r) => a + (r.average_focus ?? 0), 0) / rows.length
            : 0;
          return {
            value: avgFocus * FOCUS_METRIC_SCALING_FACTOR,
            changePercentage: 0,
            previousValue: 0,
          } as BrainMetrics;
        }),
    ).pipe(
      catchError(error => {
        console.error('Error fetching metrics:', error);
        return of({ value: 0, changePercentage: 0, previousValue: 0 });
      }),
    );
  }

  fetchSessionData(userId: string): Observable<SessionData> {
    if (environment.useMockData) return this.getMockSessionData();

    return from(
      this.supabase.client
        .from('learning_sessions')
        .select('average_focus, average_calm')
        .eq('user_id', userId)
        .order('started_at', { ascending: false })
        .limit(1)
        .single()
        .then(({ data, error }) => {
          if (error || !data) return { focus: 0, meditation: 0, flow: 0 };
          const focus = data.average_focus ?? 0;
          const calm = data.average_calm ?? 0;
          return {
            focus,
            meditation: calm,
            flow: ((focus + calm) / 2) * 100,
          } as SessionData;
        }),
    ).pipe(
      catchError(error => {
        console.error('Error fetching session data:', error);
        return of({ focus: 0, meditation: 0, flow: 0 });
      }),
    );
  }

  fetchCorrelationData(userId: string): Observable<CorrelationData[]> {
    if (environment.useMockData) return this.getMockCorrelationData();

    return from(
      this.supabase.client
        .from('learning_sessions')
        .select('started_at, average_focus, average_calm')
        .eq('user_id', userId)
        .order('started_at', { ascending: false })
        .limit(6)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []).map(row => ({
            date: String(new Date(row.started_at).getDate()).padStart(2, '0'),
            current: row.average_focus ?? 0,
            previous: row.average_calm ?? 0,
          })) as CorrelationData[];
        }),
    ).pipe(
      catchError(error => {
        console.error('Error fetching correlation data:', error);
        return of([]);
      }),
    );
  }

  private getMockBrainMetrics(): Observable<BrainMetrics> {
    return of({
      value: Math.floor(Math.random() * 100) * FOCUS_METRIC_SCALING_FACTOR,
      changePercentage: Math.floor(Math.random() * 20) - 10,
      previousValue: Math.floor(Math.random() * 100) * FOCUS_METRIC_SCALING_FACTOR,
    });
  }

  private getMockSessionData(): Observable<SessionData> {
    return of({
      focus: Math.floor(Math.random() * 100),
      meditation: Math.floor(Math.random() * 100),
      flow: Math.floor(Math.random() * 100),
    });
  }

  getMockCorrelationData(): Observable<CorrelationData[]> {
    const mockData: CorrelationData[] = [
      { date: 'Mon', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Tue', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Wed', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Thu', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Fri', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Sat', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
      { date: 'Sun', current: Math.floor(Math.random() * (95 - 60 + 1)) + 60, previous: Math.floor(Math.random() * (90 - 50 + 1)) + 50 },
    ];
    return of(mockData);
  }
}