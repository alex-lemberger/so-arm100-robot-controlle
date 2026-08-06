# Capture Sessions Table — Design Spec

**Date:** 2026-06-08  
**Goal:** Show completed capture sessions in a table below the dashboard grid. Supports real Supabase data in production and in-memory mock sessions for UI testing.

---

## Architecture

### `CaptureHistoryService`

`Injectable({ providedIn: 'root' })`. Single source of truth for session history.

```
sessions$: BehaviorSubject<CaptureRow[]>   // starts empty
load(): void                               // fetches from Supabase (real) or no-op (mock)
addMockSession(row: CaptureRow): void      // called by CaptureSessionService in mock mode
```

**Real mode:** `load()` runs `SELECT * FROM captures ORDER BY created_at DESC LIMIT 50`. Pushes result to `sessions$`. Errors are swallowed and logged — a failed history fetch must not break the dashboard.

**Mock mode:** `load()` is a no-op. `addMockSession()` prepends a new row to the current `sessions$` value so newly completed mock sessions appear at the top without a page reload.

---

### `CaptureRow` type

Add to `src/app/modules/capture/models/capture-session.model.ts`:

```typescript
export interface CaptureRow {
  id: string;
  worker_id: string;
  task_type: string;
  task_label: string;
  shop_id: string;
  status: CaptureSessionStatus | 'uploading';
  created_at: string;          // ISO string
  ended_at: string | null;
  eeg_tick_count: number;
  video_path: string | null;
  imu_left_path: string | null;
  imu_right_path: string | null;
  eeg_path: string | null;
}
```

---

### `CaptureSessionService` mock branch

`startSession()` currently stores only `currentSessionId`. Promote four locals to private fields:

```typescript
private sessionStart = 0;
private workerToken = '';
private taskType = '';
private taskLabel = '';
```

Set them at the top of `startSession()` alongside `currentSessionId`.

In `stopSession()`, just before dispatching `UploadComplete` in mock mode, build and push a `CaptureRow`:

```typescript
if (this.mode.isMock()) {
  this.historyService.addMockSession({
    id: sessionId,
    worker_id: this.workerToken,
    task_type: this.taskType,
    task_label: this.taskLabel,
    shop_id: environment.shopId,
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

---

### `CaptureSessionsTableComponent`

**File:** `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts`  
Standalone, no Material table dependency — plain `<table>` with dashboard-matching styles.

**Columns:**

| # | Header | Source | Format |
|---|--------|--------|--------|
| 1 | Date/Time | `created_at` | `DD.MM.YYYY HH:mm` |
| 2 | Task | `task_label` | plain text |
| 3 | Duration | `ended_at - created_at` | `mm:ss` or `—` if null |
| 4 | Status | `status` | colored chip |
| 5 | EEG Ticks | `eeg_tick_count` | DM Mono |
| 6 | Video | `video_path` | `open_in_new` icon → Supabase URL, or `—` |
| 7 | IMU L | `imu_left_path` | same |
| 8 | IMU R | `imu_right_path` | same |
| 9 | EEG | `eeg_path` | same |

**Status chip colors:**
- `complete` → `#48bb78` (green)
- `failed` → `#e53e3e` (red)
- `recording` / `uploading` → `#f6ad55` (amber)

**File links:** Supabase Storage public URL = `${supabaseUrl}/storage/v1/object/public/captures/${path}`. Opens in new tab. Mock sessions show `—` for all file columns.

**Empty state:** centered text "Noch keine Aufzeichnungen" with a `history` Material icon above it.

**Loading state:** three skeleton rows (`.skeleton` class with opacity pulse animation) shown while `isLoading` signal is `true`.

**Inputs:** none — component injects `CaptureHistoryService` directly.

---

### Dashboard integration

**`dashboard.component.ts`:** inject `CaptureHistoryService`, call `load()` in constructor.

**`dashboard.component.html`:** add below `.dash__grid`:

```html
<section class="card captures-section">
  <h2 class="card__title">Aufzeichnungen</h2>
  <app-capture-sessions-table />
</section>
```

Add `CaptureSessionsTableComponent` to the `imports` array of `DashboardComponent`.

---

## Styling

Matches existing dashboard card conventions:
- Container: `background: #1a2535`, `border-radius: 16px`, `padding: 28px 32px`
- Table: `width: 100%`, `border-collapse: collapse`, `font-size: 13px`
- Header row: `color: #9aa8c4`, `font-weight: 600`, `text-transform: uppercase`, `font-size: 11px`, `letter-spacing: .06em`
- Data rows: `color: #e8edf5`, `border-top: 1px solid #2a3545`
- Numeric columns: `font-family: 'DM Mono', monospace`
- Chip: `padding: 2px 8px`, `border-radius: 20px`, `font-size: 11px`

---

## Files

| Action | Path |
|--------|------|
| Modify | `src/app/modules/capture/models/capture-session.model.ts` |
| Create | `src/app/modules/capture/services/capture-history.service.ts` |
| Modify | `src/app/modules/capture/services/capture-session.service.ts` |
| Create | `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts` |
| Modify | `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` |
| Modify | `src/app/shared/components/layout/dashboard-layout/dashboard.component.html` |

---

## Out of scope

- Pagination (limit 50 is sufficient for POC)
- Delete / archive sessions
- Filtering or sorting
- Real-time subscription to new Supabase rows
