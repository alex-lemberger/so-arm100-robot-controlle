import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';
import { MuseClient } from 'muse-js';
import { BrainDevice, DeviceState, DeviceStatus, EegReading } from '../brain-device';
import { bandPowers } from './muse-eeg-utils';

@Injectable()
export class MuseDeviceService extends BrainDevice implements OnDestroy {
  readonly focus$ = new BehaviorSubject<number | null>(null);
  readonly calm$  = new BehaviorSubject<number | null>(null);
  readonly state$ = new BehaviorSubject<DeviceState>({ isLoggedIn: false, error: null });
  readonly extras$ = new BehaviorSubject<Record<string, number>>({});

  // Typed as minimal interface to avoid muse-js's bundled RxJS version conflict
  private eegSub: { unsubscribe(): void } | null = null;
  private rawEegSub: { unsubscribe(): void } | null = null;
  private readonly _rawEeg$ = new Subject<EegReading>();
  readonly rawEeg$ = this._rawEeg$.asObservable();

  private readonly WINDOW = 256;
  private readonly STEP   = 64;
  private readonly SAMPLE_RATE = 256;
  private readonly EEG_ELECTRODE = 1;  // AF7 — left frontal

  constructor(protected readonly client: MuseClient = new MuseClient()) {
    super();
  }

  async connect(): Promise<void> {
    if (this.state$.value.isLoggedIn) return;
    try {
      await this.client.connect();
      await this.client.start();
      this.setupEegPipeline();
      this.setupRawEegStream();
      this.state$.next({ isLoggedIn: true, error: null });
    } catch (err) {
      const error = err instanceof Error ? err.message : 'Connection failed';
      this.state$.next({ isLoggedIn: false, error });
      throw err;
    }
  }

  async disconnect(): Promise<void> {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.rawEegSub?.unsubscribe();
    this.rawEegSub = null;
    await this.client.disconnect();
    this.focus$.next(null);
    this.calm$.next(null);
    this.extras$.next({});
    this.state$.next({ isLoggedIn: false, error: null });
  }

  // Fix #1: resolved guard prevents double-resolve and orphaned subscription
  async getStatus(): Promise<DeviceStatus> {
    return new Promise((resolve) => {
      const isOnline = this.state$.value.isLoggedIn;
      let resolved = false;
      const sub = this.client.telemetryData.subscribe(t => {
        if (resolved) return;
        resolved = true;
        sub.unsubscribe();
        resolve({
          state: isOnline ? 'online' : 'offline',
          battery: { level: t.batteryLevel / 100, charging: false },
        });
      });
      setTimeout(() => {
        if (resolved) return;
        resolved = true;
        sub.unsubscribe();
        resolve({ state: isOnline ? 'online' : 'offline' });
      }, 2000);
    });
  }

  // Fix #2: sync cleanup is immediate; BLE teardown is best-effort
  ngOnDestroy(): void {
    this.eegSub?.unsubscribe();
    this.eegSub = null;
    this.rawEegSub?.unsubscribe();
    this.rawEegSub = null;
    try { this.client.disconnect(); } catch { /* best-effort */ }
  }

  // Fix #3: post-loop slice instead of per-sample O(N) shift
  protected setupEegPipeline(): void {
    let sampleBuffer: number[] = [];
    let stepCount = 0;

    this.eegSub = this.client.eegReadings.subscribe(reading => {
      if (reading.electrode !== this.EEG_ELECTRODE) return;
      for (const sample of reading.samples) {
        sampleBuffer.push(sample);
        stepCount++;
      }
      if (sampleBuffer.length > this.WINDOW) {
        sampleBuffer = sampleBuffer.slice(-this.WINDOW);
      }
      if (stepCount >= this.STEP && sampleBuffer.length >= this.WINDOW) {
        stepCount = 0;
        this.emitBandPowers(sampleBuffer.slice());
      }
    });
  }

  protected setupRawEegStream(): void {
    this.rawEegSub = this.client.eegReadings.subscribe((reading: any) => {
      this._rawEeg$.next({
        electrode: reading.electrode,
        samples: reading.samples,
        timestamp: reading.timestamp ?? Date.now(),
      });
    });
  }

  // Fix #5: clamp negative band powers before normalising
  private emitBandPowers(window: number[]): void {
    const p = bandPowers(window, this.SAMPLE_RATE);
    const theta = Math.max(0, p.theta);
    const alpha = Math.max(0, p.alpha);
    const beta  = Math.max(0, p.beta);
    const total = theta + alpha + beta;
    if (total <= 0) return;
    this.focus$.next(beta  / total);
    this.calm$.next( alpha / total);
    this.extras$.next({
      theta: theta / total,
      alpha: alpha / total,
      beta:  beta  / total,
    });
  }
}
