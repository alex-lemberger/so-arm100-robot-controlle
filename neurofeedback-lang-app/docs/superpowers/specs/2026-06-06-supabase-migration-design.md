# Supabase Migration Design

**Date:** 2026-06-06  
**Status:** Approved  
**Scope:** Full Firebase removal — captures, EEG ticks, file storage, language-learning exercises, learning sessions, and Firebase Auth all migrated to Supabase.

## Context

Firebase/Firestore cannot support GDPR deletion cleanly — removing a capture session requires recursive subcollection traversal. EEG ticks are time-series data stored as documents, making windowed aggregation (needed for phase 2 dataset processing) awkward. The app is pre-production with no live data, so a big-bang full removal is the right call now rather than accumulating a partial migration debt. Supabase (PostgreSQL + S3-compatible storage + Auth, EU Frankfurt region) replaces Firebase entirely.

## Approach

Big-bang replacement. One PR removes `@angular/fire` and the Firebase config entirely and wires Supabase throughout. No parallel write, no feature flags.

## Shared Client

A single `SupabaseClientService` (`core/supabase/supabase-client.service.ts`) creates and exposes the `@supabase/supabase-js` client via `createClient(url, anonKey)`. All other Supabase-using services inject this. Registered `providedIn: 'root'`. No Angular provider boilerplate needed in `main.ts`.

`main.ts` changes:
- Remove `provideFirebaseApp`, `provideAuth`, `provideFirestore`, `provideStorage`
- Remove all `@angular/fire/*` imports

`environment.ts` changes:
- Remove `firebase` config block
- Add `supabase: { url: string, anonKey: string }`

---

## Database Schema

### Capture tables

```sql
CREATE TABLE captures (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  worker_id       TEXT        NOT NULL,
  task_type       TEXT        NOT NULL,
  task_label      TEXT        NOT NULL,
  shop_id         TEXT        NOT NULL,
  consent_version TEXT        NOT NULL,
  status          TEXT        NOT NULL,   -- recording | uploading | complete | failed
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
```

### Language-learning tables

```sql
CREATE TABLE exercises (
  id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  type          TEXT    NOT NULL,   -- speaking | listening | grammar | vocabulary
  title         TEXT    NOT NULL,
  duration      INTEGER NOT NULL,
  progress_current INTEGER NOT NULL DEFAULT 0,
  progress_total   INTEGER NOT NULL DEFAULT 0,
  focus_level   FLOAT4  NOT NULL DEFAULT 0,
  status        TEXT,               -- active | paused | completed
  phrase        TEXT,               -- speaking exercises
  audio_url     TEXT,
  question      TEXT,               -- listening exercises
  options       JSONB,              -- listening / grammar / vocabulary
  remaining_plays INTEGER,
  sentence      TEXT,               -- grammar exercises
  verb          TEXT,
  word          TEXT                -- vocabulary exercises
);

CREATE TABLE learning_sessions (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       TEXT        NOT NULL,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at      TIMESTAMPTZ,
  average_focus FLOAT4      NOT NULL DEFAULT 0,
  average_calm  FLOAT4      NOT NULL DEFAULT 0,
  status        TEXT        NOT NULL,   -- active | completed | interrupted
  brain_metrics JSONB       NOT NULL DEFAULT '[]'
);
```

`brain_metrics` stored as JSONB for now (array of `{timestamp, focus, calm}`). Extracted to a proper table when queried in phase 2.

TimescaleDB hypertable conversion (`SELECT create_hypertable('eeg_ticks', 'recorded_at')`) is a one-command migration when phase 2 needs windowed queries — no schema change required.

---

## Storage

One Supabase bucket: `captures`. Path layout:

```
captures/{sessionId}/video.{webm|mp4}
captures/{sessionId}/imu_left.bin
captures/{sessionId}/imu_right.bin
```

---

## Auth & Row-Level Security

Replace Firebase Auth with Supabase Auth (`supabase.auth.signInWithPassword` / `signOut` / `onAuthStateChange`).

**Auth components:**

- `AppComponent` — replace `authState(Auth)` Observable with Supabase `onAuthStateChange` wrapped in a `BehaviorSubject<Session | null>`
- `LoginComponent` — replace `signInWithEmailAndPassword(auth, email, password)` with `supabase.auth.signInWithPassword({ email, password })`
- `LogoutMenuComponent` — replace `authState(auth)` with session signal; `auth.signOut()` → `supabase.auth.signOut()`

**RLS policies:**

```sql
-- Captures: anon insert + update (session ID acts as capability token)
ALTER TABLE captures  ENABLE ROW LEVEL SECURITY;
ALTER TABLE eeg_ticks ENABLE ROW LEVEL SECURITY;
ALTER TABLE exercises ENABLE ROW LEVEL SECURITY;
ALTER TABLE learning_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon insert captures"
  ON captures FOR INSERT TO anon WITH CHECK (true);

CREATE POLICY "anon update captures"
  ON captures FOR UPDATE TO anon USING (true);

CREATE POLICY "anon insert eeg_ticks"
  ON eeg_ticks FOR INSERT TO anon WITH CHECK (true);

-- Exercises: authenticated users read; admin writes via dashboard
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

No SELECT policy on `captures` or `eeg_ticks` for anon = blocked by default. Operator access via Supabase dashboard.

---

## Service Architecture

### `SupabaseClientService` (new)
`src/app/core/supabase/supabase-client.service.ts`  
Creates `createClient(url, anonKey)` once. Exposes `client` property. All other services inject this.

### `SupabaseCaptureService` (new)
`src/app/modules/capture/services/supabase-capture.service.ts`

```ts
class SupabaseCaptureService {
  startSession(workerToken, taskType, taskLabel, shopId, consentVersion): Promise<string>
  updateSession(sessionId: string, patch: Partial<CaptureRow>): Promise<void>
  writeEegTick(sessionId, focus, calm, inFlow): void   // fire-and-forget
  uploadFile(path, data: Blob, onProgress: (bytes: number) => void): Promise<void>
  deleteSession(sessionId: string): Promise<void>      // GDPR: storage + CASCADE delete
}
```

`uploadFile` uses `XMLHttpRequest` for byte-level progress events. Progress reporting matches current `CaptureUploadService` contract.

### `ExerciseService` (updated)
Remove `FirestoreService` injection. Call `SupabaseClientService.client.from('exercises')` directly. The `ExerciseSource` interface contract is unchanged.

### `DashboardService` (updated)
Remove `FirestoreService` injection. Replace `getAverageMetrics` / `getUserSessions` calls with direct `from('learning_sessions')` Supabase queries. `useMockData` branch unchanged.

### `FirestoreService` (deleted)
No longer needed. Delete the file.

### `session.model.ts` (updated)
Remove `import { Timestamp } from '@angular/fire/firestore'`.  
`startTime: Timestamp` → `startTime: string` (ISO 8601).  
`endTime?: Timestamp` → `endTime?: string`.  
`BrainMetricSnapshot.timestamp: Timestamp` → `timestamp: string`.

### `capture-session.model.ts` (updated)
Remove `import { Timestamp } from '@angular/fire/firestore'`.  
`startTime: Timestamp` → `startTime: string`.  
`endTime?: Timestamp` → `endTime?: string`.  
`EegTick.t: Timestamp` → `t: string`.

---

## Error Handling

Matches existing patterns — no new abstractions:

- `startSession` throws on Supabase error → `CaptureSessionService` catches, dispatches `CaptureActions.UploadFailed`
- `writeEegTick` fire-and-forget → `.catch(console.error)` only
- `updateSession` errors → caught by existing try/catch in `CaptureSessionService.stopSession()`
- Upload failures propagate as rejections up to `CaptureSessionService`
- Auth errors → `LoginComponent` displays `error.message` (unchanged pattern)

---

## GDPR Deletion

`SupabaseCaptureService.deleteSession(sessionId)`:
1. `supabase.storage.from('captures').list('captures/{sessionId}/')` → collect paths
2. `supabase.storage.from('captures').remove([...paths])` → delete files
3. `DELETE FROM captures WHERE id = $1` → deletes session row + all `eeg_ticks` via CASCADE

One SQL statement, atomic. Operator UI (out of scope) calls this primitive.

---

## Out of Scope

- TimescaleDB hypertable conversion (one SQL command when phase 2 needs it)
- Operator admin UI for session management / GDPR export
- Failed-session cleanup automation
- Supabase Realtime subscriptions (not needed — capture writes are one-directional)
- OAuth / social login (email+password is sufficient for current use)

---

## Files Touched

| File | Change |
|------|--------|
| `package.json` | add `@supabase/supabase-js`; remove `@angular/fire` |
| `environment.ts` | replace `firebase` block with `supabase: { url, anonKey }` |
| `main.ts` | remove all `provideFirebaseApp / Auth / Firestore / Storage` |
| `core/supabase/supabase-client.service.ts` | **new** — singleton client |
| `modules/capture/services/supabase-capture.service.ts` | **new** — all capture DB + storage ops |
| `modules/capture/services/capture-session.service.ts` | swap `Firestore` → `SupabaseCaptureService` |
| `modules/capture/services/capture-upload.service.ts` | swap `Storage` → `SupabaseCaptureService` |
| `modules/capture/models/capture-session.model.ts` | remove `Timestamp`, use `string` |
| `shared/models/session.model.ts` | remove `Timestamp`, use `string` |
| `core/neurofeedback/services/firestore.service.ts` | **delete** |
| `modules/language-learning/services/exercise.service.ts` | swap `FirestoreService` → direct Supabase |
| `dashboard/services/dashboard.service.ts` | swap `FirestoreService` → direct Supabase |
| `core/auth/login/login.component.ts` | Firebase Auth → Supabase Auth |
| `core/auth/logout-menu/logout-menu.component.ts` | Firebase Auth → Supabase Auth |
| `app.component.ts` | `authState(Auth)` → Supabase session observable |
| `worker-consent.component.ts` | indirect — compiles clean once model fixed |
| Supabase dashboard | create project (Frankfurt), run schema SQL, configure RLS, create storage bucket |
