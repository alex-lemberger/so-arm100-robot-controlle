# Supabase Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `@angular/fire` entirely with `@supabase/supabase-js` — migrating auth, Firestore data, and Storage — in one big-bang PR with no live data to preserve.

**Architecture:** New `SupabaseClientService` provides the singleton Supabase client. A `SupabaseAuthService` wraps auth state as an Observable. A purpose-built `SupabaseCaptureService` owns all capture DB + storage operations. Language-learning services (`ExerciseService`, `LearningSessionService`, `DashboardService`) inject the client directly for their table queries.

**Tech Stack:** `@supabase/supabase-js` v2, Angular 19, NGXS, Supabase cloud (Frankfurt region).

---

## File Map

| Status | File | Responsibility |
|--------|------|----------------|
| NEW | `src/app/core/supabase/supabase-client.service.ts` | Singleton Supabase client |
| NEW | `src/app/core/supabase/supabase-auth.service.ts` | Auth state Observable + signIn/signOut |
| NEW | `src/app/modules/capture/services/supabase-capture.service.ts` | All capture DB + storage ops |
| NEW | `src/app/modules/capture/services/supabase-capture.service.spec.ts` | Unit tests for capture service |
| MODIFY | `src/app/environments/environment.ts` | Replace firebase config with supabase |
| MODIFY | `src/main.ts` | Remove all Firebase providers |
| MODIFY | `src/app/shared/models/session.model.ts` | Remove Firestore Timestamp |
| MODIFY | `src/app/modules/capture/models/capture-session.model.ts` | Remove Firestore Timestamp |
| MODIFY | `src/app/app.component.ts` | Firebase Auth → SupabaseAuthService |
| MODIFY | `src/app/core/auth/login/login.component.ts` | Firebase Auth → SupabaseAuthService |
| MODIFY | `src/app/core/auth/logout-menu/logout-menu.component.ts` | Firebase Auth → SupabaseAuthService |
| MODIFY | `src/app/shared/components/layout/header/header.component.ts` | Firebase Auth → SupabaseAuthService |
| MODIFY | `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` | Firebase Auth → SupabaseAuthService |
| MODIFY | `src/app/modules/capture/services/capture-session.service.ts` | Firestore → SupabaseCaptureService |
| MODIFY | `src/app/modules/capture/services/capture-session.service.spec.ts` | Update mock injection |
| MODIFY | `src/app/modules/capture/services/capture-upload.service.ts` | Firebase Storage → SupabaseCaptureService |
| MODIFY | `src/app/core/neurofeedback/services/learning-session.service.ts` | FirestoreService → Supabase direct |
| MODIFY | `src/app/modules/language-learning/services/exercise.service.ts` | FirestoreService → Supabase direct |
| MODIFY | `src/app/dashboard/services/dashboard.service.ts` | FirestoreService → Supabase direct |
| MODIFY | `package.json` | Add @supabase/supabase-js, remove @angular/fire |
| DELETE | `src/app/core/neurofeedback/services/firestore.service.ts` | Replaced by per-service Supabase calls |

**Build verification command** (use throughout — `ng test` is broken per CLAUDE.md):
```bash
ng build --configuration development
```

---

## Task 1: Install Packages and Configure Environment

**Files:**
- Modify: `package.json`
- Modify: `src/app/environments/environment.ts`

- [ ] **Step 1: Install Supabase client**

```bash
npm install @supabase/supabase-js
```

Expected: `@supabase/supabase-js` appears in `package.json` dependencies.

- [ ] **Step 2: Update environment.ts**

Replace the entire file contents:

```typescript
export const environment = {
  production: false,
  useMockData: true,
  device: 'muse' as 'mock' | 'neurosity' | 'muse',
  wordpressApiUrl: 'https://your-wordpress-site.com/wp-json/wp/v2/posts',
  neurosityDeviceId: 'YOUR_DEVICE_ID',
  supabase: {
    url: 'https://REPLACE_WITH_PROJECT_REF.supabase.co',
    anonKey: 'REPLACE_WITH_ANON_KEY',
  },
  shopId: 'pilot-shop-01',
  collections: {
    metrics: 'metrics',
    sessions: 'sessions',
    correlation: 'correlation',
    exercises: 'exercises',
  },
};
```

Note: `url` and `anonKey` are filled during Task 14 (Supabase project setup). The app uses `useMockData: true` so the real Supabase connection is not exercised until you flip that flag.

- [ ] **Step 3: Verify TypeScript knows about the new field**

```bash
ng build --configuration development 2>&1 | grep -i "supabase\|error" | head -20
```

Expected: build fails on `provideFirestore`/`provideStorage` imports — that is correct at this stage. The point is `environment.supabase` should NOT be among the errors.

---

## Task 2: SupabaseClientService and SupabaseAuthService

**Files:**
- Create: `src/app/core/supabase/supabase-client.service.ts`
- Create: `src/app/core/supabase/supabase-auth.service.ts`

- [ ] **Step 1: Create the Supabase client service**

```typescript
// src/app/core/supabase/supabase-client.service.ts
import { Injectable } from '@angular/core';
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class SupabaseClientService {
  readonly client: SupabaseClient = createClient(
    environment.supabase.url,
    environment.supabase.anonKey,
  );
}
```

- [ ] **Step 2: Create the auth service**

```typescript
// src/app/core/supabase/supabase-auth.service.ts
import { Injectable } from '@angular/core';
import { Session, User } from '@supabase/supabase-js';
import { BehaviorSubject, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { SupabaseClientService } from './supabase-client.service';

@Injectable({ providedIn: 'root' })
export class SupabaseAuthService {
  private readonly _session = new BehaviorSubject<Session | null>(null);
  readonly session$: Observable<Session | null> = this._session.asObservable();
  readonly user$: Observable<User | null> = this.session$.pipe(
    map(s => s?.user ?? null),
  );

  constructor(private readonly supabase: SupabaseClientService) {
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
    const { error } = await this.supabase.client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }

  async signOut(): Promise<void> {
    const { error } = await this.supabase.client.auth.signOut();
    if (error) throw error;
  }
}
```

- [ ] **Step 3: Verify both files compile**

```bash
ng build --configuration development 2>&1 | grep "supabase-client\|supabase-auth\|error TS" | head -20
```

Expected: no errors referencing these two new files.

---

## Task 3: Migrate Auth Components

**Files:**
- Modify: `src/app/app.component.ts`
- Modify: `src/app/core/auth/login/login.component.ts`
- Modify: `src/app/core/auth/logout-menu/logout-menu.component.ts`
- Modify: `src/app/shared/components/layout/header/header.component.ts`

- [ ] **Step 1: Update AppComponent**

Replace the entire file:

```typescript
// src/app/app.component.ts
import { MatToolbarModule } from '@angular/material/toolbar';
import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Observable, of } from 'rxjs';
import { catchError, map, startWith } from 'rxjs/operators';
import { User } from '@supabase/supabase-js';
import { SupabaseAuthService } from './core/supabase/supabase-auth.service';
import { LoginComponent } from './core/auth/login/login.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatButtonModule,
    MatProgressBarModule,
    LoginComponent,
    MatToolbarModule,
  ],
  template: `
    <mat-progress-bar
      *ngIf="isLoading$ | async"
      mode="indeterminate"
      class="loading-bar">
    </mat-progress-bar>
    <main>
      <ng-container *ngIf="user$ | async; else loginTemplate">
        <router-outlet></router-outlet>
      </ng-container>
      <ng-template #loginTemplate>
        <app-login></app-login>
      </ng-template>
    </main>
  `,
  styleUrls: ['./app.component.scss'],
})
export class AppComponent {
  user$: Observable<User | null>;
  isLoading$: Observable<boolean>;

  constructor(private authService: SupabaseAuthService) {
    this.user$ = this.authService.user$;
    this.isLoading$ = this.user$.pipe(
      map(() => false),
      startWith(true),
      catchError(() => of(false)),
    );
  }
}
```

- [ ] **Step 2: Update LoginComponent**

Replace the entire file:

```typescript
// src/app/core/auth/login/login.component.ts
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { SupabaseAuthService } from '../../supabase/supabase-auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatInputModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
  ],
  template: `
    <mat-card class="login-card">
      <h2>Login</h2>
      <form (ngSubmit)="login()">
        <mat-form-field appearance="fill" class="full-width">
          <mat-label>Email</mat-label>
          <input matInput type="email" [(ngModel)]="email" name="email" required />
        </mat-form-field>
        <mat-form-field appearance="fill" class="full-width">
          <mat-label>Password</mat-label>
          <input matInput type="password" [(ngModel)]="password" name="password" required />
        </mat-form-field>
        <button mat-raised-button color="primary" type="submit">Login</button>
      </form>
      <p *ngIf="errorMessage" class="error-message">{{ errorMessage }}</p>
    </mat-card>
  `,
  styles: [`
    .login-card { max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }
    .full-width { width: 100%; margin-bottom: 20px; }
    .error-message { color: red; margin-top: 10px; }
  `],
})
export class LoginComponent {
  email = '';
  password = '';
  errorMessage: string | null = null;

  constructor(private authService: SupabaseAuthService) {}

  async login() {
    try {
      await this.authService.signIn(this.email, this.password);
    } catch (error: any) {
      this.errorMessage = error.message;
    }
  }
}
```

- [ ] **Step 3: Update LogoutMenuComponent**

Replace the entire file:

```typescript
// src/app/core/auth/logout-menu/logout-menu.component.ts
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { Observable } from 'rxjs';
import { User } from '@supabase/supabase-js';
import { SupabaseAuthService } from '../../supabase/supabase-auth.service';

@Component({
  selector: 'app-logout-menu',
  standalone: true,
  imports: [CommonModule, MatButtonModule],
  template: `
    <div *ngIf="user$ | async as user">
      <span>Welcome, {{ user?.email }}</span>
      <button mat-button color="warn" (click)="logout()">Logout</button>
    </div>
  `,
  styles: [`span { margin-right: 16px; }`],
})
export class LogoutMenuComponent {
  user$: Observable<User | null>;

  constructor(private authService: SupabaseAuthService) {
    this.user$ = this.authService.user$;
  }

  logout() {
    this.authService.signOut();
  }
}
```

- [ ] **Step 4: Update HeaderComponent**

Replace the entire file:

```typescript
// src/app/shared/components/layout/header/header.component.ts
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { FormsModule } from '@angular/forms';
import { SupabaseAuthService } from '../../../../core/supabase/supabase-auth.service';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    CommonModule,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatMenuModule,
    FormsModule,
  ],
  template: `
    <mat-toolbar class="header">
      <div class="logo-wrapper"></div>
      <div class="user-container">
        <button mat-button [matMenuTriggerFor]="userMenu" class="user-button">
          <mat-icon>account_circle</mat-icon>
          {{ authService.currentUser?.email || 'User' }}
        </button>
        <mat-menu #userMenu="matMenu">
          <button mat-menu-item (click)="signOut()">
            <mat-icon>exit_to_app</mat-icon>
            <span>Sign Out</span>
          </button>
        </mat-menu>
      </div>
    </mat-toolbar>
  `,
  styles: [`
    .header { display: flex; align-items: center; padding: 0 24px; background: white;
              border-bottom: 1px solid #EEF2FA; height: 56px; }
    .logo-wrapper { width: 150px; height: 36px; background-image: url('/img/logo.svg');
                    background-repeat: no-repeat; background-size: contain;
                    background-position: left center; }
    .user-container { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    .user-button { display: flex; align-items: center; gap: 8px; }
  `],
})
export class HeaderComponent {
  constructor(public authService: SupabaseAuthService) {}

  async signOut() {
    await this.authService.signOut();
  }
}
```

- [ ] **Step 5: Verify build (auth errors only, not Firebase errors)**

```bash
ng build --configuration development 2>&1 | grep "error TS" | head -20
```

Expected: only errors from files not yet migrated (Firestore/FirestoreService). No errors in app.component, login, logout-menu, header.

---

## Task 4: Migrate DashboardComponent Auth

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`

- [ ] **Step 1: Replace Auth injection in DashboardComponent**

In `dashboard.component.ts`, make these targeted changes:

1. Remove this import:
```typescript
import { Auth } from '@angular/fire/auth';
```

2. Add this import:
```typescript
import { SupabaseAuthService } from '../../../../core/supabase/supabase-auth.service';
```

3. Replace this field declaration:
```typescript
private readonly auth = inject(Auth);
```
with:
```typescript
private readonly authService = inject(SupabaseAuthService);
```

4. Replace the constructor body:
```typescript
constructor() {
  this.auth.onAuthStateChanged((user) => {
    this.userId = user?.uid ?? null;
    const email = user?.email ?? null;
    this.userName.set(email ? capitalize(email.split('@')[0]) : 'there');
  });
}
```
with:
```typescript
constructor() {
  this.authService.session$.subscribe(session => {
    this.userId = session?.user?.id ?? null;
    const email = session?.user?.email ?? null;
    this.userName.set(email ? capitalize(email.split('@')[0]) : 'there');
  });
}
```

- [ ] **Step 2: Verify dashboard compiles**

```bash
ng build --configuration development 2>&1 | grep "dashboard.component\|error TS" | head -20
```

Expected: no errors in `dashboard.component.ts`.

- [ ] **Step 3: Commit auth migration**

```bash
git add src/app/core/supabase/ src/app/app.component.ts src/app/core/auth/ src/app/shared/components/layout/header/ src/app/shared/components/layout/dashboard-layout/dashboard.component.ts src/app/environments/environment.ts
git commit -m "feat(auth): replace Firebase Auth with SupabaseAuthService"
```

---

## Task 5: Fix Models (Remove Firestore Timestamps)

**Files:**
- Modify: `src/app/shared/models/session.model.ts`
- Modify: `src/app/modules/capture/models/capture-session.model.ts`

- [ ] **Step 1: Update session.model.ts**

Replace the entire file:

```typescript
// src/app/shared/models/session.model.ts
export interface LearningSession {
  id: string;
  userId: string;
  startTime: string;
  endTime?: string;
  averageFocus: number;
  averageCalm: number;
  status: 'active' | 'completed' | 'interrupted';
  brainMetrics: BrainMetricSnapshot[];
}

export interface BrainMetricSnapshot {
  timestamp: string;
  focus: number;
  calm: number;
}
```

- [ ] **Step 2: Update capture-session.model.ts**

Replace the entire file:

```typescript
// src/app/modules/capture/models/capture-session.model.ts
export type CaptureSessionStatus =
  | 'recording'
  | 'uploading'
  | 'complete'
  | 'failed';

export interface CaptureSession {
  sessionId: string;
  workerId: string;
  taskType: string;
  taskLabel: string;
  startTime: string;
  endTime?: string;
  status: CaptureSessionStatus;
  videoPath?: string;
  imuLeftPath?: string;
  imuRightPath?: string;
  eegTickCount: number;
  consentVersion: string;
  shopId: string;
}

export interface EegTick {
  t: string;
  focus: number;
  calm: number;
  inFlow: boolean;
}

export interface ImuFrame {
  t: number;
  ax: number; ay: number; az: number;
  gx: number; gy: number; gz: number;
}

export const TASK_TYPES: string[] = [
  'engine_assembly',
  'electrical_repair',
  'plumbing_installation',
  'hvac_service',
  'brake_replacement',
  'welding',
  'carpentry',
  'other',
];

export const CONSENT_VERSION = '1.0';
```

- [ ] **Step 3: Verify models compile**

```bash
ng build --configuration development 2>&1 | grep "session.model\|capture-session.model\|error TS" | head -20
```

Expected: no errors from the two model files.

- [ ] **Step 4: Commit model changes**

```bash
git add src/app/shared/models/session.model.ts src/app/modules/capture/models/capture-session.model.ts
git commit -m "refactor(models): replace Firestore Timestamp with ISO string"
```

---

## Task 6: Create SupabaseCaptureService

**Files:**
- Create: `src/app/modules/capture/services/supabase-capture.service.ts`
- Create: `src/app/modules/capture/services/supabase-capture.service.spec.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// src/app/modules/capture/services/supabase-capture.service.spec.ts
import { SupabaseCaptureService } from './supabase-capture.service';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

function makeSupabaseClient(overrides: Partial<any> = {}) {
  const fromResult = {
    insert: jasmine.createSpy('insert').and.returnValue(Promise.resolve({ error: null })),
    update: jasmine.createSpy('update').and.returnValue({ eq: jasmine.createSpy('eq').and.returnValue(Promise.resolve({ error: null })) }),
    delete: jasmine.createSpy('delete').and.returnValue({ eq: jasmine.createSpy('eq').and.returnValue(Promise.resolve({ error: null })) }),
  };
  const storageResult = {
    upload: jasmine.createSpy('upload').and.returnValue(Promise.resolve({ error: null })),
    list: jasmine.createSpy('list').and.returnValue(Promise.resolve({ data: [] })),
    remove: jasmine.createSpy('remove').and.returnValue(Promise.resolve({ error: null })),
  };
  return {
    from: jasmine.createSpy('from').and.returnValue(fromResult),
    storage: {
      from: jasmine.createSpy('storageFrom').and.returnValue(storageResult),
    },
    _fromResult: fromResult,
    _storageResult: storageResult,
    ...overrides,
  };
}

function makeService(clientOverrides?: Partial<any>): { service: SupabaseCaptureService; mockClient: any } {
  const mockClient = makeSupabaseClient(clientOverrides);
  const mockSupabase = { client: mockClient } as unknown as SupabaseClientService;
  const service = new SupabaseCaptureService(mockSupabase);
  return { service, mockClient };
}

describe('SupabaseCaptureService', () => {
  describe('startSession', () => {
    it('inserts a capture row and returns a UUID', async () => {
      const { service, mockClient } = makeService();

      const id = await service.startSession('worker-1', 'welding', 'Weld frame joint', 'shop-01', '1.0');

      expect(mockClient.from).toHaveBeenCalledWith('captures');
      expect(mockClient._fromResult.insert).toHaveBeenCalledWith(
        jasmine.objectContaining({
          worker_id: 'worker-1',
          task_type: 'welding',
          task_label: 'Weld frame joint',
          shop_id: 'shop-01',
          consent_version: '1.0',
          status: 'recording',
          eeg_tick_count: 0,
        }),
      );
      expect(typeof id).toBe('string');
      expect(id.length).toBe(36); // UUID format
    });

    it('throws when Supabase returns an error', async () => {
      const { service, mockClient } = makeService();
      mockClient._fromResult.insert.and.returnValue(Promise.resolve({ error: { message: 'network error' } }));

      await expectAsync(
        service.startSession('w', 'welding', 'label', 'shop', '1.0'),
      ).toBeRejectedWithError('network error');
    });
  });

  describe('writeEegTick', () => {
    it('inserts an eeg_ticks row fire-and-forget', (done) => {
      const { service, mockClient } = makeService();

      service.writeEegTick('session-1', 0.8, 0.6, true);

      setTimeout(() => {
        expect(mockClient.from).toHaveBeenCalledWith('eeg_ticks');
        expect(mockClient._fromResult.insert).toHaveBeenCalledWith(
          jasmine.objectContaining({ session_id: 'session-1', focus: 0.8, calm: 0.6, in_flow: true }),
        );
        done();
      }, 10);
    });
  });

  describe('updateSession', () => {
    it('calls update on captures table with patch', async () => {
      const { service, mockClient } = makeService();

      await service.updateSession('session-1', { status: 'uploading' });

      expect(mockClient.from).toHaveBeenCalledWith('captures');
      expect(mockClient._fromResult.update).toHaveBeenCalledWith({ status: 'uploading' });
    });
  });

  describe('deleteSession', () => {
    it('removes storage objects then deletes the session row', async () => {
      const { service, mockClient } = makeService();
      mockClient._storageResult.list.and.returnValue(Promise.resolve({
        data: [{ name: 'video.webm' }, { name: 'imu_left.bin' }],
      }));

      await service.deleteSession('session-1');

      expect(mockClient._storageResult.list).toHaveBeenCalledWith('session-1');
      expect(mockClient._storageResult.remove).toHaveBeenCalledWith([
        'session-1/video.webm',
        'session-1/imu_left.bin',
      ]);
      expect(mockClient._fromResult.delete).toHaveBeenCalled();
    });
  });
});
```

- [ ] **Step 2: Verify the test file compiles (service doesn't exist yet — build should flag it)**

```bash
ng build --configuration development 2>&1 | grep "supabase-capture" | head -10
```

Expected: error that `SupabaseCaptureService` cannot be found (confirm the spec is wired up).

- [ ] **Step 3: Implement SupabaseCaptureService**

```typescript
// src/app/modules/capture/services/supabase-capture.service.ts
import { Injectable } from '@angular/core';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

interface CaptureRow {
  id?: string;
  worker_id?: string;
  task_type?: string;
  task_label?: string;
  shop_id?: string;
  consent_version?: string;
  status?: string;
  eeg_tick_count?: number;
  ended_at?: string;
  video_path?: string;
  imu_left_path?: string;
  imu_right_path?: string;
}

@Injectable({ providedIn: 'root' })
export class SupabaseCaptureService {
  constructor(private readonly supabase: SupabaseClientService) {}

  async startSession(
    workerToken: string,
    taskType: string,
    taskLabel: string,
    shopId: string,
    consentVersion: string,
  ): Promise<string> {
    const sessionId = crypto.randomUUID();
    const { error } = await this.supabase.client
      .from('captures')
      .insert({
        id: sessionId,
        worker_id: workerToken,
        task_type: taskType,
        task_label: taskLabel,
        shop_id: shopId,
        consent_version: consentVersion,
        status: 'recording',
        eeg_tick_count: 0,
      });
    if (error) throw new Error(error.message);
    return sessionId;
  }

  async updateSession(sessionId: string, patch: CaptureRow): Promise<void> {
    const { error } = await this.supabase.client
      .from('captures')
      .update(patch)
      .eq('id', sessionId);
    if (error) throw new Error(error.message);
  }

  writeEegTick(sessionId: string, focus: number, calm: number, inFlow: boolean): void {
    this.supabase.client
      .from('eeg_ticks')
      .insert({ session_id: sessionId, focus, calm, in_flow: inFlow })
      .then(({ error }) => {
        if (error) console.error('EEG tick write failed:', error.message);
      });
  }

  async uploadFile(
    path: string,
    data: Blob,
    onProgress: (bytes: number) => void,
  ): Promise<void> {
    onProgress(0);
    const objectPath = path.replace(/^captures\//, '');
    const { error } = await this.supabase.client.storage
      .from('captures')
      .upload(objectPath, data, { upsert: true });
    if (error) throw new Error(error.message);
    onProgress(data.size);
  }

  async deleteSession(sessionId: string): Promise<void> {
    const { data: objects } = await this.supabase.client.storage
      .from('captures')
      .list(sessionId);
    if (objects?.length) {
      await this.supabase.client.storage
        .from('captures')
        .remove(objects.map(o => `${sessionId}/${o.name}`));
    }
    const { error } = await this.supabase.client
      .from('captures')
      .delete()
      .eq('id', sessionId);
    if (error) throw new Error(error.message);
  }
}
```

- [ ] **Step 4: Verify service compiles**

```bash
ng build --configuration development 2>&1 | grep "supabase-capture\|error TS" | head -20
```

Expected: no errors in `supabase-capture.service.ts` or its spec.

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/services/supabase-capture.service.ts src/app/modules/capture/services/supabase-capture.service.spec.ts
git commit -m "feat(capture): add SupabaseCaptureService replacing Firestore/Storage"
```

---

## Task 7: Migrate CaptureSessionService

**Files:**
- Modify: `src/app/modules/capture/services/capture-session.service.ts`
- Modify: `src/app/modules/capture/services/capture-session.service.spec.ts`

- [ ] **Step 1: Replace the entire CaptureSessionService**

```typescript
// src/app/modules/capture/services/capture-session.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { Store } from '@ngxs/store';
import { Subscription, combineLatest } from 'rxjs';
import { filter, withLatestFrom } from 'rxjs/operators';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { FlowDetectorService } from '../../../core/neurofeedback/services/flow-detector.service';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { SupabaseCaptureService } from './supabase-capture.service';
import { CaptureActions } from '../state/capture.actions';
import { CONSENT_VERSION } from '../models/capture-session.model';

@Injectable({ providedIn: 'root' })
export class CaptureSessionService implements OnDestroy {
  private eegSub: Subscription | null = null;
  private uploadSub: Subscription | null = null;
  private currentSessionId: string | null = null;
  private eegTickCount = 0;

  constructor(
    private store: Store,
    private supabaseCapture: SupabaseCaptureService,
    private brainDevice: BrainDevice,
    private imuService: ImuService,
    private videoService: VideoRecorderService,
    private uploadService: CaptureUploadService,
    private flowDetector: FlowDetectorService,
  ) {}

  async startSession(
    workerToken: string,
    taskType: string,
    taskLabel: string,
    shopId: string,
  ): Promise<string> {
    this.eegTickCount = 0;
    try {
      const sessionId = await this.supabaseCapture.startSession(
        workerToken, taskType, taskLabel, shopId, CONSENT_VERSION,
      );
      this.currentSessionId = sessionId;
      const sessionStart = Date.now();
      this.imuService.startRecording(sessionStart);
      this.videoService.startRecording();
      this.eegSub = this.startEegSubscription(sessionId);
      this.store.dispatch(new CaptureActions.StartRecording(sessionId));
      return sessionId;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.cleanupRecordingState();
      this.store.dispatch(new CaptureActions.UploadFailed(message));
      throw err;
    }
  }

  async stopSession(): Promise<void> {
    if (!this.currentSessionId) return;
    const sessionId = this.currentSessionId;

    this.store.dispatch(new CaptureActions.StopRecording());
    this.uploadSub?.unsubscribe();
    this.uploadSub = this.uploadService.progress$.subscribe(progress => {
      this.store.dispatch(new CaptureActions.UploadProgress(progress));
    });

    try {
      this.eegSub?.unsubscribe();
      this.eegSub = null;

      const imuBuffers = this.imuService.stopRecording();
      const videoBlob = await this.videoService.stopRecording();

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'uploading',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      });

      const paths = await this.uploadService.uploadSession(
        sessionId, videoBlob, imuBuffers.left, imuBuffers.right,
      );

      await this.supabaseCapture.updateSession(sessionId, {
        status: 'complete',
        video_path: paths.videoPath,
        imu_left_path: paths.imuLeftPath,
        imu_right_path: paths.imuRightPath,
      });

      this.store.dispatch(new CaptureActions.UploadComplete());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await this.supabaseCapture.updateSession(sessionId, {
        status: 'failed',
        ended_at: new Date().toISOString(),
        eeg_tick_count: this.eegTickCount,
      }).catch(console.error);
      this.store.dispatch(new CaptureActions.UploadFailed(message));
    } finally {
      this.uploadSub?.unsubscribe();
      this.uploadSub = null;
      this.currentSessionId = null;
    }
  }

  protected startEegSubscription(sessionId: string): Subscription {
    return combineLatest([this.brainDevice.focus$, this.brainDevice.calm$])
      .pipe(
        filter(([f, c]) => f !== null && c !== null),
        withLatestFrom(this.flowDetector.inFlow$),
      )
      .subscribe(([[focus, calm], inFlow]) => {
        this.writeEegTick(sessionId, focus!, calm!, inFlow);
      });
  }

  private writeEegTick(sessionId: string, focus: number, calm: number, inFlow: boolean): void {
    this.eegTickCount++;
    this.supabaseCapture.writeEegTick(sessionId, focus, calm, inFlow);
  }

  ngOnDestroy(): void {
    this.cleanupRecordingState();
  }

  private cleanupRecordingState(): void {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.uploadSub?.unsubscribe();
    this.uploadSub = null;
    this.imuService.stopRecording();
    this.currentSessionId = null;
  }
}
```

- [ ] **Step 2: Update the spec to inject SupabaseCaptureService instead of Firestore**

Replace the entire spec file:

```typescript
// src/app/modules/capture/services/capture-session.service.spec.ts
import { BehaviorSubject } from 'rxjs';
import { CaptureSessionService } from './capture-session.service';
import { FlowDetectorService } from '../../../core/neurofeedback/services/flow-detector.service';
import { BrainDevice } from '../../../core/neurofeedback/brain-device';
import { ImuService } from './imu.service';
import { VideoRecorderService } from './video-recorder.service';
import { CaptureUploadService } from './capture-upload.service';
import { SupabaseCaptureService } from './supabase-capture.service';
import { Store } from '@ngxs/store';

function makeService(
  inFlow$: BehaviorSubject<boolean>,
  focus$: BehaviorSubject<number | null>,
  calm$: BehaviorSubject<number | null>,
): CaptureSessionService {
  return new CaptureSessionService(
    { dispatch: jasmine.createSpy() } as unknown as Store,
    jasmine.createSpyObj<SupabaseCaptureService>('SupabaseCaptureService', [
      'startSession', 'updateSession', 'writeEegTick', 'uploadFile', 'deleteSession',
    ]),
    { focus$, calm$ } as unknown as BrainDevice,
    {
      startRecording: jasmine.createSpy(),
      stopRecording: jasmine.createSpy().and.returnValue({ left: new Float32Array(), right: new Float32Array() }),
    } as unknown as ImuService,
    { startRecording: jasmine.createSpy() } as unknown as VideoRecorderService,
    { progress$: new BehaviorSubject(0) } as unknown as CaptureUploadService,
    { inFlow$ } as unknown as FlowDetectorService,
  );
}

describe('CaptureSessionService — FlowDetectorService wiring', () => {
  let inFlow$: BehaviorSubject<boolean>;
  let focus$: BehaviorSubject<number | null>;
  let calm$: BehaviorSubject<number | null>;
  let service: CaptureSessionService;
  let writeEegTickSpy: jasmine.Spy;

  beforeEach(() => {
    inFlow$ = new BehaviorSubject<boolean>(false);
    focus$ = new BehaviorSubject<number | null>(null);
    calm$ = new BehaviorSubject<number | null>(null);
    service = makeService(inFlow$, focus$, calm$);
    writeEegTickSpy = spyOn(service as any, 'writeEegTick');
  });

  it('passes inFlow: false when flow detector emits false', () => {
    (service as any).startEegSubscription('session-1');
    focus$.next(0.9);
    calm$.next(0.6);
    expect(writeEegTickSpy).toHaveBeenCalledWith('session-1', 0.9, 0.6, false);
  });

  it('passes inFlow: true when flow detector emits true', () => {
    inFlow$.next(true);
    (service as any).startEegSubscription('session-1');
    focus$.next(0.9);
    calm$.next(0.6);
    expect(writeEegTickSpy).toHaveBeenCalledWith('session-1', 0.9, 0.6, true);
  });

  it('does not write a tick when focus is null', () => {
    (service as any).startEegSubscription('session-1');
    calm$.next(0.6);
    expect(writeEegTickSpy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Verify**

```bash
ng build --configuration development 2>&1 | grep "capture-session\|error TS" | head -20
```

Expected: no errors in `capture-session.service.ts` or its spec.

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/services/capture-session.service.ts src/app/modules/capture/services/capture-session.service.spec.ts
git commit -m "feat(capture): migrate CaptureSessionService from Firestore to SupabaseCaptureService"
```

---

## Task 8: Migrate CaptureUploadService

**Files:**
- Modify: `src/app/modules/capture/services/capture-upload.service.ts`

- [ ] **Step 1: Replace the entire CaptureUploadService**

```typescript
// src/app/modules/capture/services/capture-upload.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SupabaseCaptureService } from './supabase-capture.service';

@Injectable({ providedIn: 'root' })
export class CaptureUploadService {
  private progressSubject = new BehaviorSubject<number>(0);
  readonly progress$ = this.progressSubject.asObservable();

  constructor(private supabaseCapture: SupabaseCaptureService) {}

  async uploadSession(
    sessionId: string,
    video: Blob,
    imuLeft: Float32Array,
    imuRight: Float32Array,
  ): Promise<{ videoPath: string; imuLeftPath: string; imuRightPath: string }> {
    this.progressSubject.next(0);

    const videoExtension = video.type.includes('webm') ? 'webm' : 'mp4';
    const videoPath = `captures/${sessionId}/video.${videoExtension}`;
    const imuLeftPath = `captures/${sessionId}/imu_left.bin`;
    const imuRightPath = `captures/${sessionId}/imu_right.bin`;

    let videoBytes = 0, imuLeftBytes = 0, imuRightBytes = 0;
    const totalBytes = video.size + imuLeft.byteLength + imuRight.byteLength;

    const updateProgress = () => {
      const done = videoBytes + imuLeftBytes + imuRightBytes;
      this.progressSubject.next(totalBytes === 0 ? 100 : Math.round((done / totalBytes) * 100));
    };

    await Promise.all([
      this.supabaseCapture.uploadFile(videoPath, video,
        n => { videoBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuLeftPath, new Blob([imuLeft]),
        n => { imuLeftBytes = n; updateProgress(); }),
      this.supabaseCapture.uploadFile(imuRightPath, new Blob([imuRight]),
        n => { imuRightBytes = n; updateProgress(); }),
    ]);

    this.progressSubject.next(100);
    return { videoPath, imuLeftPath, imuRightPath };
  }
}
```

- [ ] **Step 2: Verify**

```bash
ng build --configuration development 2>&1 | grep "capture-upload\|error TS" | head -20
```

Expected: no errors in `capture-upload.service.ts`.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/services/capture-upload.service.ts
git commit -m "feat(capture): migrate CaptureUploadService from Firebase Storage to SupabaseCaptureService"
```

---

## Task 9: Migrate LearningSessionService

**Files:**
- Modify: `src/app/core/neurofeedback/services/learning-session.service.ts`

- [ ] **Step 1: Replace the entire LearningSessionService**

```typescript
// src/app/core/neurofeedback/services/learning-session.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BrainDevice } from '../brain-device';
import { BehaviorSubject, Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { SupabaseClientService } from '../../core/supabase/supabase-client.service';

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
    private device: BrainDevice,
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
    this.metricsSubscription = this.device.focus$.subscribe(focus => {
      if (focus !== null) {
        this.updateMetrics(sessionId, focus, this._sessionState.value.currentCalm);
      }
    });
    this.device.calm$.subscribe(calm => {
      if (calm !== null) {
        this.updateMetrics(sessionId, this._sessionState.value.currentFocus, calm);
      }
    });
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
```

Note: `SupabaseClientService` is in `core/supabase/` but `LearningSessionService` is in `core/neurofeedback/services/`. The relative import path is `../../core/supabase/supabase-client.service` — wait, from `core/neurofeedback/services/` the path to `core/supabase/` is `../../supabase/`. Fix the import:

```typescript
import { SupabaseClientService } from '../../supabase/supabase-client.service';
```

Use `../../supabase/supabase-client.service` (not `../../core/supabase`).

- [ ] **Step 2: Verify**

```bash
ng build --configuration development 2>&1 | grep "learning-session\|error TS" | head -20
```

Expected: no errors in `learning-session.service.ts`.

- [ ] **Step 3: Commit**

```bash
git add src/app/core/neurofeedback/services/learning-session.service.ts
git commit -m "feat(learning): migrate LearningSessionService from FirestoreService to Supabase"
```

---

## Task 10: Migrate ExerciseService

**Files:**
- Modify: `src/app/modules/language-learning/services/exercise.service.ts`

- [ ] **Step 1: Replace the entire ExerciseService**

```typescript
// src/app/modules/language-learning/services/exercise.service.ts
import { Injectable } from '@angular/core';
import { from, Observable, of, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { ExerciseBase, SpeakingExercise, ExerciseType } from '../../../shared/models/exercise.model';
import { ExerciseSource } from './exercise-source.interface';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

@Injectable({ providedIn: 'root' })
export class ExerciseService implements ExerciseSource {
  constructor(private readonly supabase: SupabaseClientService) {}

  getExercises(): Observable<ExerciseBase[]> {
    return from(
      this.supabase.client.from('exercises').select('*').then(({ data, error }) => {
        if (error) throw new Error(error.message);
        return (data ?? []) as ExerciseBase[];
      }),
    ).pipe(catchError(this.handleError<ExerciseBase[]>('getExercises', [])));
  }

  getExercise(id: string): Observable<ExerciseBase> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('id', id).single()
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          if (!data) throw new Error(`Exercise with id ${id} not found`);
          return data as ExerciseBase;
        }),
    ).pipe(
      catchError(error => {
        console.error(`getExercise failed for id ${id}:`, error);
        return throwError(() => error);
      }),
    );
  }

  getExercisesByType(type: ExerciseType): Observable<ExerciseBase[]> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('type', type)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as ExerciseBase[];
        }),
    ).pipe(catchError(this.handleError<ExerciseBase[]>('getExercisesByType', [])));
  }

  getSpeakingExercises(): Observable<SpeakingExercise[]> {
    return from(
      this.supabase.client.from('exercises').select('*').eq('type', ExerciseType.SPEAKING)
        .then(({ data, error }) => {
          if (error) throw new Error(error.message);
          return (data ?? []) as SpeakingExercise[];
        }),
    ).pipe(catchError(this.handleError<SpeakingExercise[]>('getSpeakingExercises', [])));
  }

  getCollection(collectionPath: string): Observable<ExerciseBase[]> {
    return this.getExercises();
  }

  pauseExercise(exerciseId: string): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ status: 'paused', last_paused_at: new Date().toISOString() })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  resumeExercise(exerciseId: string): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ status: 'active' })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  navigateToPrevious(exerciseId: string, exercises: ExerciseBase[]): Observable<string | null> {
    if (!exercises?.length) return of(null);
    const sorted = [...exercises].sort((a, b) => a.title.localeCompare(b.title));
    const idx = sorted.findIndex(ex => ex.id === exerciseId);
    if (idx === -1) return of(null);
    return of(idx > 0 ? sorted[idx - 1].id : sorted[sorted.length - 1].id);
  }

  navigateToNext(exerciseId: string, exercises: ExerciseBase[]): Observable<string | null> {
    if (!exercises?.length) return of(null);
    const sorted = [...exercises].sort((a, b) => a.title.localeCompare(b.title));
    const idx = sorted.findIndex(ex => ex.id === exerciseId);
    if (idx === -1) return of(null);
    return of(idx < sorted.length - 1 ? sorted[idx + 1].id : sorted[0].id);
  }

  updateProgress(exerciseId: string, progress: number): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ progress_current: progress })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  updateFocusMetrics(exerciseId: string, metrics: any): Observable<void> {
    return from(
      this.supabase.client.from('exercises')
        .update({ focus_metrics: metrics })
        .eq('id', exerciseId)
        .then(({ error }) => { if (error) throw new Error(error.message); }),
    );
  }

  private handleError<T>(operation = 'operation', result?: T) {
    return (error: any): Observable<T> => {
      console.error(`${operation} failed:`, error.message);
      return result !== undefined ? of(result as T) : throwError(() => new Error(error));
    };
  }
}
```

- [ ] **Step 2: Verify**

```bash
ng build --configuration development 2>&1 | grep "exercise.service\|error TS" | head -20
```

Expected: no errors in `exercise.service.ts`.

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/language-learning/services/exercise.service.ts
git commit -m "feat(exercises): migrate ExerciseService from FirestoreService to Supabase"
```

---

## Task 11: Migrate DashboardService

**Files:**
- Modify: `src/app/dashboard/services/dashboard.service.ts`

- [ ] **Step 1: Replace the entire DashboardService**

```typescript
// src/app/dashboard/services/dashboard.service.ts
import { Injectable } from '@angular/core';
import { Observable, from, catchError, of } from 'rxjs';
import { map } from 'rxjs/operators';
import { BrainMetrics, SessionData, CorrelationData } from '../../shared/components/layout/dashboard-layout/dashboard.model';
import { environment } from '../../environments/environment';
import { SupabaseClientService } from '../../core/supabase/supabase-client.service';

const FOCUS_METRIC_SCALING_FACTOR = 100000;

@Injectable({ providedIn: 'root' })
export class DashboardService {
  constructor(private readonly supabase: SupabaseClientService) {}

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
```

- [ ] **Step 2: Verify**

```bash
ng build --configuration development 2>&1 | grep "dashboard.service\|error TS" | head -20
```

Expected: no errors in `dashboard.service.ts`.

- [ ] **Step 3: Commit**

```bash
git add src/app/dashboard/services/dashboard.service.ts
git commit -m "feat(dashboard): migrate DashboardService from FirestoreService to Supabase"
```

---

## Task 12: Remove FirestoreService and All Remaining Firebase

**Files:**
- Delete: `src/app/core/neurofeedback/services/firestore.service.ts`
- Modify: `src/main.ts`
- Modify: `package.json`

- [ ] **Step 1: Delete FirestoreService**

```bash
rm src/app/core/neurofeedback/services/firestore.service.ts
```

- [ ] **Step 2: Update main.ts — remove all Firebase providers**

Replace the entire file:

```typescript
// src/main.ts
import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';
import { provideAnimations } from '@angular/platform-browser/animations';
import { importProvidersFrom, DestroyRef } from '@angular/core';
import { MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { environment } from './app/environments/environment';
import { provideRouter } from '@angular/router';
import { routes } from './app/app.routes';
import { MockNeurosityService } from './app/core/neurofeedback/services/mock-neurosity.service';
import { NeurosityService } from './app/core/neurofeedback/services/neurosity.service';
import { MuseDeviceService } from './app/core/neurofeedback/services/muse-device.service';
import { BrainDevice } from './app/core/neurofeedback/brain-device';
import { provideStore } from '@ngxs/store';
import { withNgxsReduxDevtoolsPlugin } from '@ngxs/devtools-plugin';
import { withNgxsLoggerPlugin } from '@ngxs/logger-plugin';
import { ExerciseState } from './app/modules/language-learning/state/exercise.state';
import { CaptureState } from './app/modules/capture/state/capture.state';
import { provideHttpClient } from '@angular/common/http';

bootstrapApplication(AppComponent, {
  providers: [
    provideRouter(routes),
    provideAnimations(),
    provideHttpClient(),
    importProvidersFrom(
      MatSnackBarModule,
      MatDialogModule,
      MatIconModule,
      MatTableModule,
    ),
    provideStore([ExerciseState, CaptureState], withNgxsReduxDevtoolsPlugin(), withNgxsLoggerPlugin()),
    {
      provide: BrainDevice,
      useFactory: (destroyRef: DestroyRef) => {
        if (environment.device === 'muse') {
          const svc = new MuseDeviceService();
          destroyRef.onDestroy(() => svc.ngOnDestroy());
          return svc;
        }
        if (environment.device === 'neurosity') return new NeurosityService();
        return new MockNeurosityService();
      },
      deps: [DestroyRef],
    },
  ],
}).catch(err => console.error(err));
```

- [ ] **Step 3: Full build verification**

```bash
ng build --configuration development 2>&1 | tail -20
```

Expected: `Build at: ... - Hash: ... - Time: ...ms` with 0 errors. If there are remaining `@angular/fire` import errors in files not yet updated, fix them before proceeding.

- [ ] **Step 4: Uninstall @angular/fire**

```bash
npm uninstall @angular/fire firebase
```

- [ ] **Step 5: Final build after package removal**

```bash
ng build --configuration development 2>&1 | tail -20
```

Expected: clean build. `@angular/fire` should not appear anywhere in errors.

- [ ] **Step 6: Verify no remaining Firebase references**

```bash
grep -r "angular/fire\|firebase" src/ --include="*.ts" | grep -v ".spec.ts" | grep -v "firestore.service.ts"
```

Expected: no output. (The deleted `firestore.service.ts` is already gone.)

- [ ] **Step 7: Commit**

```bash
git add src/main.ts src/app/core/neurofeedback/services/ package.json package-lock.json
git commit -m "feat(infra): remove @angular/fire entirely, complete Supabase migration"
```

---

## Task 13: Commit Spec Updates to Reflect Full Migration

- [ ] **Step 1: Commit updated spec and plan docs**

```bash
git add docs/superpowers/specs/2026-06-06-supabase-migration-design.md docs/superpowers/plans/2026-06-06-supabase-migration.md
git commit -m "docs: add Supabase migration spec and implementation plan"
```

---

## Task 14: Supabase Project Setup (Dashboard)

These steps are done in the Supabase dashboard and cannot be automated. Complete them before switching `useMockData` to `false` or running field tests.

- [ ] **Step 1: Create Supabase project**

1. Go to [supabase.com](https://supabase.com) → New project
2. Name: `neurofeedback-handwerk` (or similar)
3. Region: **Frankfurt (eu-central-1)**
4. Save the database password somewhere secure

- [ ] **Step 2: Copy credentials into environment.ts**

From Project Settings → API:
- Copy `Project URL` → `environment.supabase.url`
- Copy `anon public` key → `environment.supabase.anonKey`

- [ ] **Step 3: Run schema SQL**

In the SQL Editor, run:

```sql
-- Capture tables
CREATE TABLE captures (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id       TEXT        NOT NULL,
  task_type       TEXT        NOT NULL,
  task_label      TEXT        NOT NULL,
  shop_id         TEXT        NOT NULL,
  consent_version TEXT        NOT NULL,
  status          TEXT        NOT NULL,
  eeg_tick_count  INTEGER     NOT NULL DEFAULT 0,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at        TIMESTAMPTZ,
  video_path      TEXT,
  imu_left_path   TEXT,
  imu_right_path  TEXT
);

CREATE TABLE eeg_ticks (
  id          BIGSERIAL   PRIMARY KEY,
  session_id  UUID        NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  focus       FLOAT4      NOT NULL,
  calm        FLOAT4      NOT NULL,
  in_flow     BOOLEAN     NOT NULL
);

CREATE INDEX eeg_ticks_session_time ON eeg_ticks(session_id, recorded_at);

-- Language-learning tables
CREATE TABLE exercises (
  id               UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  type             TEXT    NOT NULL,
  title            TEXT    NOT NULL,
  duration         INTEGER NOT NULL DEFAULT 0,
  progress_current INTEGER NOT NULL DEFAULT 0,
  progress_total   INTEGER NOT NULL DEFAULT 0,
  focus_level      FLOAT4  NOT NULL DEFAULT 0,
  status           TEXT,
  phrase           TEXT,
  audio_url        TEXT,
  question         TEXT,
  options          JSONB,
  remaining_plays  INTEGER,
  sentence         TEXT,
  verb             TEXT,
  word             TEXT
);

CREATE TABLE learning_sessions (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       TEXT        NOT NULL,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at      TIMESTAMPTZ,
  average_focus FLOAT4      NOT NULL DEFAULT 0,
  average_calm  FLOAT4      NOT NULL DEFAULT 0,
  status        TEXT        NOT NULL DEFAULT 'active',
  brain_metrics JSONB       NOT NULL DEFAULT '[]'
);
```

- [ ] **Step 4: Configure RLS**

In the SQL Editor, run:

```sql
ALTER TABLE captures       ENABLE ROW LEVEL SECURITY;
ALTER TABLE eeg_ticks      ENABLE ROW LEVEL SECURITY;
ALTER TABLE exercises      ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_sessions ENABLE ROW LEVEL SECURITY;

-- Capture: anon can insert and update (session ID is the capability token)
CREATE POLICY "anon insert captures"
  ON captures FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "anon update captures"
  ON captures FOR UPDATE TO anon USING (true);

CREATE POLICY "anon insert eeg_ticks"
  ON eeg_ticks FOR INSERT TO anon WITH CHECK (true);

-- Exercises: authenticated reads only
CREATE POLICY "auth read exercises"
  ON exercises FOR SELECT TO authenticated USING (true);

-- Learning sessions: users own their rows
CREATE POLICY "auth insert learning_sessions"
  ON learning_sessions FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY "auth read own learning_sessions"
  ON learning_sessions FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);

CREATE POLICY "auth update own learning_sessions"
  ON learning_sessions FOR UPDATE TO authenticated
  USING (user_id = auth.uid()::text);
```

- [ ] **Step 5: Create Storage bucket**

In Storage → New bucket:
- Name: `captures`
- Public: **OFF**

Add bucket policy (Storage → Policies → `captures` bucket):
```sql
CREATE POLICY "anon upload captures"
  ON storage.objects FOR INSERT TO anon
  WITH CHECK (bucket_id = 'captures');
```

- [ ] **Step 6: Create a test user**

In Authentication → Users → Invite user — create a test account for local login verification.

- [ ] **Step 7: Smoke test**

1. `npm start`
2. Navigate to `http://localhost:4200`
3. Login with the test user — confirm the dashboard loads (mock data visible)
4. Navigate to `/capture` — confirm the capture flow initializes without console errors
5. Check browser console for any `@angular/fire` remnants (should be none)
