-- supabase/migrations/20260607000000_storage_policies_captures.sql
-- Approach A: anon writes, path-restricted. No auth required (workers are anonymous).
-- Before field test: flip TO anon → TO authenticated and add auth.uid() scope (Approach B).

DO $$
DECLARE
  path_pattern TEXT := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$';
BEGIN
  -- Enable RLS on storage.objects if not already enabled
  -- (Supabase enables this by default, but belt-and-suspenders)
END $$;

CREATE POLICY "anon_upload" ON storage.objects
  FOR INSERT TO anon
  WITH CHECK (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_upsert" ON storage.objects
  FOR UPDATE TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_list" ON storage.objects
  FOR SELECT TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );

CREATE POLICY "anon_delete" ON storage.objects
  FOR DELETE TO anon
  USING (
    bucket_id = 'captures'
    AND name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(video\.(mp4|webm)|imu_(left|right)\.bin|eeg\.bin)$'
  );