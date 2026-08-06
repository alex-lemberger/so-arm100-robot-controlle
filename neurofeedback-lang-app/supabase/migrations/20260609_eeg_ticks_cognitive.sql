-- Cognitive-state labels for capture ticks. Nullable + idempotent: existing rows stay valid.
alter table public.eeg_ticks
  add column if not exists load      real,
  add column if not exists fatigue   real,
  add column if not exists signal_ok boolean;
