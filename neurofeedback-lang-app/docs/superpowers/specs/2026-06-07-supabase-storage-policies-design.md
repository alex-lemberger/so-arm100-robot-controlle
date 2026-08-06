# Supabase Storage Policies — Capture Bucket

**Date:** 2026-06-07
**Status:** Approved

## Context

The capture platform uploads four files per session to a Supabase Storage bucket named `captures`:

- `{sessionId}/video.{mp4|webm}` — up to ~500 MB
- `{sessionId}/imu_left.bin` — up to ~10 MB
- `{sessionId}/imu_right.bin` — up to ~10 MB
- `{sessionId}/eeg.bin` — raw Muse 2 electrode samples (4 ch × ~256 Hz × Float32); complements the `eeg_ticks` table which stores derived focus/calm/inFlow at ~1 Hz

Workers are anonymous (no Supabase Auth). The app uses the anon key. No playback UI exists; files are consumed offline by buyers via service key. Replaces Firebase `storage.rules` (never deployed; project was on Spark plan).

## Bucket

`captures` — private (not public). No public URL access. Created during Supabase migration.

## Approach A — Anon writes, path-restricted (POC)

Four RLS policies on `storage.objects`, all scoped to `bucket_id = 'captures'`, all granted to the `anon` role.

| Operation | Policy name       | Purpose                                      |
|-----------|-------------------|----------------------------------------------|
| INSERT    | `anon_upload`     | Initial file upload                          |
| UPDATE    | `anon_upsert`     | Re-upload (code uses `upsert: true`)         |
| SELECT    | `anon_list`       | `deleteSession` calls `list()` before remove |
| DELETE    | `anon_delete`     | `deleteSession` calls `remove()`             |

All four share the same path guard:

```sql
name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
```

Size and content-type enforcement is not available in Supabase Storage RLS; enforced at SDK/client level.

Service key bypasses RLS entirely — dashboard and offline pipeline use service key.

## Approach B — Pre-field-test gate

Before first real-data collection session:

1. Add `signInAnonymously()` in `WorkerConsentComponent` after consent is given.
2. Flip all four policies from `TO anon` → `TO authenticated`.
3. Add `auth.uid() = (storage.foldername(name))[1]` — or derive session ownership from the `captures` DB row — so each worker can only touch their own session folder.

Zero structural change to bucket, paths, or upload code.

## Deliverable

SQL migration file: `supabase/migrations/YYYYMMDDHHMMSS_storage_policies_captures.sql`

Applied via Supabase CLI (`supabase db push`) or pasted into dashboard SQL editor.
