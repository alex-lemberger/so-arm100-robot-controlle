import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { Job, JobLogMessage, JobSummary, PipelineStatus } from './pipeline.models';

@Injectable({ providedIn: 'root' })
export class PipelineApiService {
  private readonly base = environment.pipelineApiUrl;

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`${this.base}${path}`, init);
    if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
    return (await res.json()) as T;
  }

  getStatus(): Promise<PipelineStatus> { return this.json('/status'); }

  async listJobs(): Promise<JobSummary[]> {
    const body = await this.json<{ jobs: JobSummary[] }>('/jobs');
    return body.jobs;
  }

  getJob(id: string): Promise<Job> { return this.json(`/jobs/${id}`); }

  async startJob(kind: string, args: Record<string, unknown>): Promise<string> {
    const body = await this.json<{ job_id: string }>('/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, args }),
    });
    return body.job_id;
  }

  async cancelJob(id: string): Promise<boolean> {
    const body = await this.json<{ cancelled: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' });
    return body.cancelled;
  }

  jobLogs(id: string): Observable<JobLogMessage> {
    const wsBase = this.base.replace(/^http/, 'ws');
    return new Observable<JobLogMessage>(sub => {
      const ws = new WebSocket(`${wsBase}/jobs/${id}/logs`);
      ws.onmessage = ev => {
        try { sub.next(JSON.parse(ev.data as string) as JobLogMessage); } catch { /* ignore */ }
      };
      ws.onerror = () => sub.error(new Error('job log ws error'));
      ws.onclose = () => sub.complete();
      return () => ws.close();
    });
  }
}
