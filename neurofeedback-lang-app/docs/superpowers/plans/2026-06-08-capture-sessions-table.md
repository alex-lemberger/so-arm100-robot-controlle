# Capture Sessions Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show completed capture sessions in a full-width table below the dashboard grid, supporting both real Supabase data and in-memory mock sessions for UI testing.

**Architecture:** `CaptureHistoryService` (new) holds a `BehaviorSubject<CaptureRow[]>`. In real mode it queries Supabase on dashboard init; in mock mode `CaptureSessionService` pushes rows directly after each session completes. `CaptureSessionsTableComponent` (new) injects the service and renders the table. `DashboardComponent` calls `load()` and hosts the new component.

**Tech Stack:** Angular 19 standalone, RxJS `BehaviorSubject`, `toSignal`, Supabase JS client, DM Mono font, plain SVG/CSS (no Material table).

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/app/modules/capture/models/capture-session.model.ts` | Add `CaptureRow` interface |
| Create | `src/app/modules/capture/services/capture-history.service.ts` | `sessions$`, `load()`, `addMockSession()` |
| Modify | `src/app/modules/capture/services/capture-session.service.ts` | Store session metadata fields; call `historyService.addMockSession()` in mock branch |
| Create | `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts` | Table UI with loading/empty states |
| Modify | `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` | Inject history service, call `load()`, import table component |
| Modify | `src/app/shared/components/layout/dashboard-layout/dashboard.component.html` | Add `<app-capture-sessions-table>` below `.dash__grid` |

---

## Task 1: Add `CaptureRow` type to model

**Files:**
- Modify: `src/app/modules/capture/models/capture-session.model.ts`

- [ ] **Step 1: Add `CaptureRow` interface**

At the bottom of `src/app/modules/capture/models/capture-session.model.ts`, add:

```typescript
export interface CaptureRow {
  id: string;
  worker_id: string;
  task_type: string;
  task_label: string;
  shop_id: string;
  status: CaptureSessionStatus | 'uploading';
  created_at: string;
  ended_at: string | null;
  eeg_tick_count: number;
  video_path: string | null;
  imu_left_path: string | null;
  imu_right_path: string | null;
  eeg_path: string | null;
}
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

---

## Task 2: `CaptureHistoryService`

**Files:**
- Create: `src/app/modules/capture/services/capture-history.service.ts`

- [ ] **Step 1: Create the service**

```typescript
// src/app/modules/capture/services/capture-history.service.ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';
import { CaptureModeService } from './capture-mode.service';
import { CaptureRow } from '../models/capture-session.model';

@Injectable({ providedIn: 'root' })
export class CaptureHistoryService {
  private supabase = inject(SupabaseClientService);
  private mode = inject(CaptureModeService);

  private readonly _sessions$ = new BehaviorSubject<CaptureRow[]>([]);
  readonly sessions$ = this._sessions$.asObservable();

  load(): void {
    if (this.mode.isMock()) return;
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
    this._sessions$.next([row, ...this._sessions$.value]);
  }
}
```

Note: add `import { inject } from '@angular/core';` — it is missing from the snippet above; the full import line should be:

```typescript
import { Injectable, inject } from '@angular/core';
```

- [ ] **Step 2: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/models/capture-session.model.ts \
        src/app/modules/capture/services/capture-history.service.ts
git commit -m "feat(capture): add CaptureRow type and CaptureHistoryService"
```

---

## Task 3: Wire mock session into `CaptureSessionService`

**Files:**
- Modify: `src/app/modules/capture/services/capture-session.service.ts`

The service currently stores only `currentSessionId`. `startSession()` receives `workerToken`, `taskType`, `taskLabel`, `shopId` as parameters but they go out of scope — `stopSession()` cannot access them. Fix: promote them to private fields, then push a `CaptureRow` in the mock branch.

- [ ] **Step 1: Add private fields and import `CaptureHistoryService`**

At the top of the class (after `private eegTickCount = 0;`), add four new private fields:

```typescript
private sessionStart = 0;
private workerToken = '';
private taskType = '';
private taskLabel = '';
private shopId = '';
```

Add to the constructor imports section (alongside existing inject calls):

```typescript
private historyService = inject(CaptureHistoryService);
```

Add the import at the top of the file:

```typescript
import { CaptureHistoryService } from './capture-history.service';
```

Also add `environment` import if not already present:

```typescript
import { environment } from '../../../environments/environment';
```

- [ ] **Step 2: Assign fields in `startSession()`**

In `startSession()`, immediately after `this.eegTickCount = 0;`, add:

```typescript
this.sessionStart = Date.now();
this.workerToken = workerToken;
this.taskType = taskType;
this.taskLabel = taskLabel;
this.shopId = shopId;
```

Also remove the `const sessionStart = Date.now();` line that currently follows — replace it with `this.imuService.startRecording(this.sessionStart);` (the field is now used).

- [ ] **Step 3: Push mock row in `stopSession()`**

In `stopSession()`, find the existing mock branch:

```typescript
if (this.mode.isMock()) {
  this.store.dispatch(new CaptureActions.UploadComplete());
  return;
}
```

Replace it with:

```typescript
if (this.mode.isMock()) {
  this.historyService.addMockSession({
    id: sessionId,
    worker_id: this.workerToken,
    task_type: this.taskType,
    task_label: this.taskLabel,
    shop_id: this.shopId,
    status: 'complete',
    created_at: new Date(this.sessionStart).toISOString(),
    ended_at: new Date().toISOString(),
    eeg_tick_count: this.eegTickCount,
    video_path: null,
    imu_left_path: null,
    imu_right_path: null,
    eeg_path: null,
  });
  this.store.dispatch(new CaptureActions.UploadComplete());
  return;
}
```

- [ ] **Step 4: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/services/capture-session.service.ts
git commit -m "feat(capture): store session metadata fields and push mock row to CaptureHistoryService"
```

---

## Task 4: `CaptureSessionsTableComponent`

**Files:**
- Create: `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts`

- [ ] **Step 1: Create the component**

```typescript
// src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts
import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureHistoryService } from '../../services/capture-history.service';
import { CaptureRow } from '../../models/capture-session.model';
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
  imports: [CommonModule, MatIconModule],
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
              <th>Datum/Zeit</th>
              <th>Aufgabe</th>
              <th>Dauer</th>
              <th>Status</th>
              <th class="num">EEG Ticks</th>
              <th>Video</th>
              <th>IMU L</th>
              <th>IMU R</th>
              <th>EEG</th>
            </tr>
          </thead>
          <tbody>
            @for (row of sessions(); track row.id) {
              <tr>
                <td>{{ formatDate(row.created_at) }}</td>
                <td>{{ row.task_label }}</td>
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
                <td>{{ fileCell(row.video_path) }}</td>
                <td>{{ fileCell(row.imu_left_path) }}</td>
                <td>{{ fileCell(row.imu_right_path) }}</td>
                <td>{{ fileCell(row.eeg_path) }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [`
    .tbl-wrap { overflow-x: auto; }
    .tbl {
      width: 100%; border-collapse: collapse;
      font-size: 13px; color: #e8edf5;
    }
    thead th {
      color: #9aa8c4; font-weight: 600;
      text-transform: uppercase; font-size: 11px;
      letter-spacing: .06em; padding: 0 12px 12px;
      text-align: left; white-space: nowrap;
    }
    tbody tr { border-top: 1px solid #2a3545; }
    tbody td { padding: 10px 12px; white-space: nowrap; }
    .num { font-family: 'DM Mono', monospace; text-align: right; }
    .chip {
      padding: 2px 8px; border-radius: 20px;
      font-size: 11px; font-weight: 600;
      background: #2a3545; color: #9aa8c4;
    }
    .chip--green { background: #1b3a2a; color: #48bb78; }
    .chip--red   { background: #3a1b1b; color: #e53e3e; }
    .chip--amber { background: #3a2e1b; color: #f6ad55; }
    .file-link {
      color: #64b5f6; display: inline-flex;
      align-items: center; gap: 2px; text-decoration: none;
    }
    .file-link mat-icon { font-size: 14px; height: 14px; width: 14px; }
    .empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 8px; padding: 40px 0; color: #4a5568;
    }
    .empty__icon { font-size: 32px; height: 32px; width: 32px; }
    .empty__text { font-size: 14px; }
  `],
})
export class CaptureSessionsTableComponent {
  private historyService = inject(CaptureHistoryService);
  protected sessions = toSignal(this.historyService.sessions$, { initialValue: [] as CaptureRow[] });

  protected formatDate = formatDate;
  protected formatDuration = formatDuration;

  protected fileCell(path: string | null): string {
    return path ? '↗' : '—';
  }

  protected storageUrl(path: string | null): string | null {
    return storageUrl(path);
  }
}
```

Note on file links: the template above uses plain text `↗` / `—` for simplicity. If you want clickable links, replace the `fileCell()` text cells with:

```html
<td>
  @if (storageUrl(row.video_path); as url) {
    <a class="file-link" [href]="url" target="_blank" rel="noopener">
      <mat-icon>open_in_new</mat-icon>
    </a>
  } @else { — }
</td>
```

Repeat for `imu_left_path`, `imu_right_path`, `eeg_path`. Use the clickable version — it matches the spec.

- [ ] **Step 2: Replace file cells with clickable links**

In the template above, replace all four file `<td>` cells (Video, IMU L, IMU R, EEG) with the clickable pattern. Final template for those four cells:

```html
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
```

- [ ] **Step 3: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 4: Commit**

```bash
git add src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts
git commit -m "feat(capture): add CaptureSessionsTableComponent"
```

---

## Task 5: Wire into Dashboard

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.html`

- [ ] **Step 1: Inject service and import component in `dashboard.component.ts`**

Add two imports at the top:

```typescript
import { CaptureHistoryService } from '../../../../modules/capture/services/capture-history.service';
import { CaptureSessionsTableComponent } from '../../../../modules/capture/components/capture-sessions-table/capture-sessions-table.component';
```

Add `CaptureSessionsTableComponent` to the `imports` array of `@Component`:

```typescript
imports: [
  CommonModule,
  MatIconModule,
  MatSnackBarModule,
  MetricRingComponent,
  EegWaveformComponent,
  WeeklyBarChartComponent,
  CaptureSessionsTableComponent,   // ← add
],
```

In the class body, inject the service and call `load()`:

```typescript
private captureHistory = inject(CaptureHistoryService);

constructor(...) {
  // existing constructor body unchanged
  this.captureHistory.load();
}
```

If the component uses `inject()` at field level (no explicit constructor), add:

```typescript
private captureHistory = inject(CaptureHistoryService);
```

and call `this.captureHistory.load()` inside any existing constructor, or add a constructor if none exists:

```typescript
constructor() {
  this.captureHistory.load();
}
```

- [ ] **Step 2: Add table section to `dashboard.component.html`**

At the very end of `dashboard.component.html`, after the closing `</div>` of `.dash__grid`, add:

```html
<section class="card captures-section">
  <h2 class="card__title">Aufzeichnungen</h2>
  <app-capture-sessions-table />
</section>
```

- [ ] **Step 3: Add `captures-section` spacing to `dashboard.component.scss`**

Open `src/app/shared/components/layout/dashboard-layout/dashboard.component.scss` and add at the bottom:

```scss
.captures-section {
  margin-top: 24px;
  padding: 28px 32px;
}
```

- [ ] **Step 4: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 5: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/dashboard.component.ts \
        src/app/shared/components/layout/dashboard-layout/dashboard.component.html \
        src/app/shared/components/layout/dashboard-layout/dashboard.component.scss
git commit -m "feat(dashboard): add capture sessions table below grid"
```

---

## Task 6: Manual verification

**Files:** none (browser test)

- [ ] **Step 1: Start dev server with mock mode**

Ensure `src/app/environments/environment.ts` has `device: 'mock'`. Then:

```bash
npm start
```

- [ ] **Step 2: Run a mock session**

1. Log into app, navigate to `/capture`
2. Toggle **Mock ON** on consent screen
3. Click "Weiter" through all wizard steps (gloves + camera connect instantly)
4. Connect EEG (`test@example.com` / `password123`) — wait for signal quality gate (~4.5 s)
5. Select any task, start recording, wait 5 s, click "Aufzeichnung beenden"

- [ ] **Step 3: Verify table on dashboard**

Navigate to `/dashboard`. Expected:
- "Aufzeichnungen" section visible below the two-column grid
- One row: correct date, task label, duration (`mm:ss`), status chip `complete` (green), EEG tick count, all file columns show `—` (mock)

- [ ] **Step 4: Run a second mock session**

Repeat Step 2 with a different task. Navigate to `/dashboard`. Expected: two rows, newest at top.

- [ ] **Step 5: Restore environment if changed**

If `device` was temporarily set to `'mock'`, restore original value.
