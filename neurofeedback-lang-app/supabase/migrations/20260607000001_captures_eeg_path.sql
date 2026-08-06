-- supabase/migrations/20260607000001_captures_eeg_path.sql
ALTER TABLE captures ADD COLUMN IF NOT EXISTS eeg_path TEXT;