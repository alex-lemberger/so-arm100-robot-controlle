// src/app/modules/capture/services/capture-history.service.ts
import { Injectable, inject } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';
import { CaptureModeService } from './capture-mode.service';
import { CaptureRow } from '../models/capture-session.model';

const MOCK_STORAGE_KEY = 'mock_capture_sessions';

@Injectable({ providedIn: 'root' })
export class CaptureHistoryService {
  private supabase = inject(SupabaseClientService);
  private mode = inject(CaptureModeService);

  private readonly _sessions$ = new BehaviorSubject<CaptureRow[]>([]);
  readonly sessions$ = this._sessions$.asObservable();

  load(): void {
    if (this.mode.isMock()) {
      const raw = localStorage.getItem(MOCK_STORAGE_KEY);
      this._sessions$.next(raw ? (JSON.parse(raw) as CaptureRow[]) : []);
      return;
    }
    this.supabase.client
      .from('captures')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(50)
      .then(({ data, error }) => {
        if (error) {
          console.error('[CaptureHistoryService] load failed:', error.message);
          return;
        }
        this._sessions$.next((data ?? []) as CaptureRow[]);
      });
  }

  addMockSession(row: CaptureRow): void {
    const updated = [row, ...this._sessions$.value];
    this._sessions$.next(updated);
    localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(updated));
  }
}