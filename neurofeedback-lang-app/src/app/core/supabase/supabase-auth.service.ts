// src/app/core/supabase/supabase-auth.service.ts
import { Injectable } from '@angular/core';
import { Session, User } from '@supabase/supabase-js';
import { BehaviorSubject, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { environment } from '../../environments/environment';
import { SupabaseClientService } from './supabase-client.service';

// Fake session used in mock/local mode so the app renders without a live Supabase
// backend. Cast through unknown — we only ever read `.user` downstream.
const MOCK_USER = {
  id: 'mock-user',
  email: 'local@mock.dev',
  aud: 'authenticated',
  role: 'authenticated',
  app_metadata: {},
  user_metadata: {},
  created_at: new Date(0).toISOString(),
} as unknown as User;

const MOCK_SESSION = {
  access_token: 'mock-access-token',
  refresh_token: 'mock-refresh-token',
  token_type: 'bearer',
  expires_in: 3600,
  user: MOCK_USER,
} as unknown as Session;

@Injectable({ providedIn: 'root' })
export class SupabaseAuthService {
  private readonly _session = new BehaviorSubject<Session | null>(null);
  readonly session$: Observable<Session | null> = this._session.asObservable();
  readonly user$: Observable<User | null> = this.session$.pipe(
    map(s => s?.user ?? null),
  );

  private readonly mock: boolean = environment.useMockData;

  constructor(private readonly supabase: SupabaseClientService) {
    if (this.mock) {
      // Local mode: skip the real backend entirely, hand out a fake session so
      // AppComponent renders the app instead of the login wall.
      this._session.next(MOCK_SESSION);
      return;
    }
    this.supabase.client.auth.getSession().then(({ data }) => {
      this._session.next(data.session);
    });
    this.supabase.client.auth.onAuthStateChange((_event, session) => {
      this._session.next(session);
    });
  }

  get currentUser(): User | null {
    return this._session.value?.user ?? null;
  }

  async signIn(email: string, password: string): Promise<void> {
    if (this.mock) {
      this._session.next(MOCK_SESSION);
      return;
    }
    const { error } = await this.supabase.client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }

  async signOut(): Promise<void> {
    if (this.mock) {
      this._session.next(null);
      return;
    }
    const { error } = await this.supabase.client.auth.signOut();
    if (error) throw error;
  }
}
