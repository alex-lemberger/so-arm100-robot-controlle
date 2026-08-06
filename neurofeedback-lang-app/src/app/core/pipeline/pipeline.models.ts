// Mirrors src/htdp/serve/models.py — keep in sync (contract per spec).
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

export interface CountBlock { count: number; }
export interface Tiers { raw: CountBlock; processed: CountBlock; releases: CountBlock; }
export interface PolicyInfo { present: boolean; path?: string | null; mtime_s?: number | null; }

export interface PipelineStatus {
  data_dir: string;
  tiers: Tiers;
  demos?: CountBlock | null;
  policy: PolicyInfo;
  running_job: string | null;
}

export interface Job {
  id: string;
  kind: string;
  args: Record<string, unknown>;
  status: JobStatus;
  exit_code?: number | null;
  created_s: number;
  started_s?: number | null;
  ended_s?: number | null;
  error?: string | null;
}

export interface JobSummary {
  id: string; kind: string; status: JobStatus; created_s: number;
}

export interface JobLogMessage {
  type: 'log' | 'progress' | 'status';
  line?: string;
  current?: number;
  total?: number;
  status?: JobStatus;
  exit_code?: number;
}
