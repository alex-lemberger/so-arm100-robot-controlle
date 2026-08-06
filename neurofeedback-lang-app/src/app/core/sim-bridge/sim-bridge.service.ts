import { Injectable, computed, signal } from '@angular/core';
import { environment } from '../../environments/environment';

export interface SimEegTick {
  focus: number;
  calm: number;
  load: number | null;
  fatigue: number | null;
  inFlow: boolean;
}

export interface SimReplayPayload {
  sessionId: string;
  taskLabel: string;
  durationMs: number;
  eegTicks: SimEegTick[];
}

export type SimStatus = 'disconnected' | 'connecting' | 'idle' | 'replaying' | 'paused';

interface SimSnapshot {
  status: SimStatus;
  tick: number;
  totalTicks: number;
  joints: number[];
  currentEegTick: SimEegTick | null;
  activeSessionId: string | null;
}

const INITIAL: SimSnapshot = {
  status: 'disconnected', tick: 0, totalTicks: 0, joints: [], currentEegTick: null, activeSessionId: null,
};

@Injectable({ providedIn: 'root' })
export class SimBridgeService {
  private readonly _snap = signal<SimSnapshot>(INITIAL);
  private readonly _launching = signal<boolean>(false);
  readonly launching = computed(() => this._launching());

  readonly isCloudSim: boolean = environment.simWsUrl !== '';
  readonly status = computed(() => this._snap().status);
  readonly tick = computed(() => this._snap().tick);
  readonly totalTicks = computed(() => this._snap().totalTicks);
  readonly joints = computed(() => this._snap().joints);
  readonly currentEegTick = computed(() => this._snap().currentEegTick);
  readonly activeSessionId = computed(() => this._snap().activeSessionId);

  private ws: WebSocket | null = null;
  private retries = 0;
  private get maxRetries() { return this.isCloudSim ? 25 : 3; }
  private get retryMs()    { return this.isCloudSim ? 5000 : 3000; }
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private _connectUrl = '';

  connect(url?: string): void {
    this.retries = 0;
    this.clearRetry();
    this.ws?.close();
    this._connectUrl = url || environment.simWsUrl || 'ws://localhost:8765';
    this._snap.update(s => ({ ...s, status: 'connecting' }));
    this._openWs();
  }

  private _openWs(): void {
    const ws = new WebSocket(this._connectUrl);
    this.ws = ws;

    ws.onopen = () => {
      this.retries = 0;
    };

    ws.onmessage = (ev: MessageEvent) => {
      if (this.ws !== ws) return;
      try {
        const msg = JSON.parse(ev.data as string);
        const newStatus = msg.status as SimStatus;
        const clearsSession = newStatus === 'idle' || newStatus === 'disconnected';
        this._snap.update(s => ({
          status: newStatus,
          tick: msg.tick ?? 0,
          totalTicks: msg.totalTicks ?? 0,
          joints: msg.q ?? [],
          currentEegTick: msg.eegTick ?? null,
          activeSessionId: clearsSession ? null : s.activeSessionId,
        }));
      } catch { /* ignore malformed */ }
    };

    ws.onerror = () => { /* onclose follows; suppress unhandled error event */ };

    ws.onclose = () => {
      if (this.ws !== ws) return;
      if (this.retries < this.maxRetries) {
        this.retries++;
        this._snap.update(s => ({ ...s, status: 'connecting' }));
        this.retryTimer = setTimeout(() => this._openWs(), this.retryMs);
      } else {
        this._snap.update(s => ({ ...s, status: 'disconnected' }));
      }
    };
  }

  disconnect(): void {
    this.clearRetry();
    this.ws?.close();
    this.ws = null;
    this._snap.set(INITIAL);
  }

  async launchSim(launcherPort = 3001): Promise<void> {
    this._launching.set(true);
    try {
      const res = await fetch(`http://localhost:${launcherPort}/sim/start`, { method: 'POST' });
      const body = await res.json() as { ok: boolean; error?: string };
      if (!body.ok) throw new Error(body.error ?? 'Launcher returned error');
      setTimeout(() => this.connect(), 2000);
    } finally {
      this._launching.set(false);
    }
  }

  stopSim(launcherPort = 3001): void {
    fetch(`http://localhost:${launcherPort}/sim/stop`, { method: 'POST' }).catch(() => {});
  }

  transferSession(payload: SimReplayPayload): boolean {
    const sent = this.send({ cmd: 'replay', ...payload });
    if (sent) this._snap.update(s => ({ ...s, activeSessionId: payload.sessionId }));
    return sent;
  }

  pause(): void { this.send({ cmd: 'pause' }); }
  resume(): void { this.send({ cmd: 'resume' }); }
  stop(): void { this.send({ cmd: 'stop' }); }
  reset(): void { this.send({ cmd: 'reset' }); }

  private send(msg: object): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
      return true;
    }
    return false;
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}
