// src/app/modules/capture/services/supabase-capture.service.ts
import { Injectable } from '@angular/core';
import { SupabaseClientService } from '../../../core/supabase/supabase-client.service';

interface CaptureRow {
  id?: string;
  worker_id?: string;
  task_type?: string;
  task_label?: string;
  shop_id?: string;
  consent_version?: string;
  status?: string;
  eeg_tick_count?: number;
  ended_at?: string;
  video_path?: string;
  imu_left_path?: string;
  imu_right_path?: string;
  eeg_path?: string | null;
}

@Injectable({ providedIn: 'root' })
export class SupabaseCaptureService {
  constructor(private readonly supabase: SupabaseClientService) {}

  async startSession(
    workerToken: string,
    taskType: string,
    taskLabel: string,
    shopId: string,
    consentVersion: string,
  ): Promise<string> {
    const sessionId = crypto.randomUUID();
    const { error } = await this.supabase.client
      .from('captures')
      .insert({
        id: sessionId,
        worker_id: workerToken,
        task_type: taskType,
        task_label: taskLabel,
        shop_id: shopId,
        consent_version: consentVersion,
        status: 'recording',
        eeg_tick_count: 0,
      });
    if (error) throw new Error(error.message);
    return sessionId;
  }

  async updateSession(sessionId: string, patch: CaptureRow): Promise<void> {
    const { error } = await this.supabase.client
      .from('captures')
      .update(patch)
      .eq('id', sessionId);
    if (error) throw new Error(error.message);
  }

  writeEegTick(
    sessionId: string,
    focus: number,
    calm: number,
    inFlow: boolean,
    load: number | null,
    fatigue: number | null,
    signalOk: boolean | null,
  ): void {
    this.supabase.client
      .from('eeg_ticks')
      .insert({ session_id: sessionId, focus, calm, in_flow: inFlow, load, fatigue, signal_ok: signalOk })
      .then(({ error }) => {
        if (error) console.error('EEG tick write failed:', error.message);
      });
  }

  async uploadFile(
    path: string,
    data: Blob,
    onProgress: (bytes: number) => void,
  ): Promise<void> {
    onProgress(0);
    const objectPath = path.replace(/^captures\//, '');
    const { error } = await this.supabase.client.storage
      .from('captures')
      .upload(objectPath, data, { upsert: true });
    if (error) throw new Error(error.message);
    onProgress(data.size);
  }

  async fetchEegTicks(sessionId: string): Promise<{ focus: number; calm: number; inFlow: boolean | null; load: number | null; fatigue: number | null }[]> {
    const { data, error } = await this.supabase.client
      .from('eeg_ticks')
      .select('focus, calm, in_flow, load, fatigue')
      .eq('session_id', sessionId);
    if (error) throw new Error(error.message);
    return (data ?? []).map((r: any) => ({
      focus: r.focus,
      calm: r.calm,
      inFlow: r.in_flow,
      load: r.load,
      fatigue: r.fatigue,
    }));
  }

  async deleteSession(sessionId: string): Promise<void> {
    const { data: objects } = await this.supabase.client.storage
      .from('captures')
      .list(sessionId);
    if (objects?.length) {
      await this.supabase.client.storage
        .from('captures')
        .remove(objects.map(o => `${sessionId}/${o.name}`));
    }
    const { error } = await this.supabase.client
      .from('captures')
      .delete()
      .eq('id', sessionId);
    if (error) throw new Error(error.message);
  }
}