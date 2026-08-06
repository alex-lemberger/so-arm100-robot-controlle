import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { PipelineApiService } from '../../../core/pipeline/pipeline-api.service';
import { JobStatus, JobSummary, PipelineStatus } from '../../../core/pipeline/pipeline.models';

const POLL_MS = 3000;
// Local dev launcher (tools/sim-launcher.js, started by `npm run dev`) that can spawn htdp serve.
const LAUNCHER_URL = 'http://localhost:3001';
const LAUNCH_POLL_MS = 2000;
const LAUNCH_MAX_POLLS = 40; // ~80s — first run does `uv sync` which can be slow

@Injectable({ providedIn: 'root' })
export class LabState {
  private readonly api: PipelineApiService;
  constructor(api?: PipelineApiService) { this.api = api ?? inject(PipelineApiService); }

  private readonly _status = signal<PipelineStatus | null>(null);
  private readonly _jobs = signal<JobSummary[]>([]);
  private readonly _connection = signal<'online' | 'offline' | 'unknown'>('unknown');
  private readonly _logLines = signal<string[]>([]);
  private readonly _progress = signal<{ current: number; total: number } | null>(null);
  private readonly _watchedStatus = signal<JobStatus | null>(null);
  private readonly _launching = signal<boolean>(false);

  readonly status = computed(() => this._status());
  readonly jobs = computed(() => this._jobs());
  readonly connection = computed(() => this._connection());
  readonly logLines = computed(() => this._logLines());
  readonly progress = computed(() => this._progress());
  readonly watchedJobStatus = computed(() => this._watchedStatus());
  readonly launching = computed(() => this._launching());

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private logSub: Subscription | null = null;

  async refresh(): Promise<void> {
    try {
      const [status, jobs] = await Promise.all([this.api.getStatus(), this.api.listJobs()]);
      this._status.set(status);
      this._jobs.set(jobs);
      this._connection.set('online');
    } catch {
      this._connection.set('offline');
    }
  }

  /**
   * Ask the local dev launcher to spawn `uv sync --extra serve && uv run htdp serve`,
   * then poll status until the server answers. Requires the launcher to be running
   * (`npm run dev`, not `npm start`).
   */
  async startServer(): Promise<void> {
    if (this._launching()) return;
    this._launching.set(true);
    try {
      const res = await fetch(`${LAUNCHER_URL}/htdp/start`, { method: 'POST' });
      const body = (await res.json()) as { ok: boolean; error?: string };
      if (!body.ok) throw new Error(body.error ?? 'launcher returned an error');
      for (let i = 0; i < LAUNCH_MAX_POLLS; i++) {
        await new Promise(r => setTimeout(r, LAUNCH_POLL_MS));
        await this.refresh();
        if (this._connection() === 'online') return;
      }
    } catch {
      this._connection.set('offline');
    } finally {
      this._launching.set(false);
    }
  }

  startPolling(): void {
    if (this.pollTimer !== null) return;
    void this.refresh();
    this.pollTimer = setInterval(() => void this.refresh(), POLL_MS);
  }

  stopPolling(): void {
    if (this.pollTimer !== null) { clearInterval(this.pollTimer); this.pollTimer = null; }
    this.logSub?.unsubscribe();
    this.logSub = null;
  }

  async run(kind: string, args: Record<string, unknown>): Promise<string> {
    const id = await this.api.startJob(kind, args);
    this.watch(id);
    void this.refresh();
    return id;
  }

  watch(jobId: string): void {
    this.logSub?.unsubscribe();
    this._logLines.set([]);
    this._progress.set(null);
    this._watchedStatus.set('running');
    this.logSub = this.api.jobLogs(jobId).subscribe({
      next: msg => {
        if (msg.type === 'log' && msg.line !== undefined) {
          this._logLines.update(l => [...l.slice(-500), msg.line!]);
        } else if (msg.type === 'progress' && msg.current !== undefined && msg.total !== undefined) {
          this._progress.set({ current: msg.current, total: msg.total });
        } else if (msg.type === 'status' && msg.status) {
          this._watchedStatus.set(msg.status);
          void this.refresh();
        }
      },
      error: () => this._watchedStatus.set(null),
    });
  }

  async cancel(jobId: string): Promise<void> {
    await this.api.cancelJob(jobId);
    void this.refresh();
  }
}
