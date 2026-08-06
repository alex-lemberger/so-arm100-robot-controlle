// src/app/modules/capture/services/eeg-signal-quality.service.ts
import { Injectable } from '@angular/core';
import { Observable, BehaviorSubject, Subscription } from 'rxjs';
import { EegReading } from '../../../core/neurofeedback/brain-device';

export type ContactState = 'unknown' | 'poor' | 'good';

export interface ElectrodeQuality {
  electrode: number;
  name: string;
  state: ContactState;
}

const ELECTRODE_NAMES = ['TP9', 'AF7', 'AF8', 'TP10'];
const BUFFER_SIZE = 256;
const MIN_SAMPLES = 128;
const MIN_VARIANCE = 5;       // µV² — below = flat / no contact
const MAX_VARIANCE = 2000;    // µV² — above = excessive artifact noise
const GOOD_COUNT_THRESHOLD = 3;
const GATE_DURATION_MS = 3000;

@Injectable({ providedIn: 'root' })
export class EegSignalQualityService {
  private buffers: number[][] = [[], [], [], []];
  private sub: Subscription | null = null;
  private goodSince: number | null = null;

  private readonly _quality$ = new BehaviorSubject<ElectrodeQuality[]>(
    ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
  );
  private readonly _gateOpen$ = new BehaviorSubject<boolean>(false);

  readonly quality$ = this._quality$.asObservable();
  readonly gateOpen$ = this._gateOpen$.asObservable();

  startMonitoring(rawEeg$: Observable<EegReading> | undefined): void {
    this.stopMonitoring();
    if (!rawEeg$) {
      this._gateOpen$.next(true);
      return;
    }
    this.buffers = [[], [], [], []];
    this.goodSince = null;
    this._gateOpen$.next(false);
    this._quality$.next(
      ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
    );
    this.sub = rawEeg$.subscribe(reading => {
      if (reading.electrode < 0 || reading.electrode >= 4) return;
      const buf = this.buffers[reading.electrode];
      buf.push(...reading.samples);
      if (buf.length > BUFFER_SIZE) {
        this.buffers[reading.electrode] = buf.slice(-BUFFER_SIZE);
      }
      this.evaluate();
    });
  }

  stopMonitoring(): void {
    this.sub?.unsubscribe();
    this.sub = null;
    this.goodSince = null;
    this.buffers = [[], [], [], []];
    this._gateOpen$.next(false);
    this._quality$.next(
      ELECTRODE_NAMES.map((name, electrode) => ({ electrode, name, state: 'unknown' as ContactState })),
    );
  }

  private evaluate(): void {
    const qualities = this.buffers.map((buf, electrode) => ({
      electrode,
      name: ELECTRODE_NAMES[electrode],
      state: this.classify(buf),
    }));
    this._quality$.next(qualities);

    const goodCount = qualities.filter(q => q.state === 'good').length;
    const now = Date.now();

    if (goodCount >= GOOD_COUNT_THRESHOLD) {
      if (this.goodSince === null) {
        this.goodSince = now;
      } else if (now - this.goodSince >= GATE_DURATION_MS) {
        this._gateOpen$.next(true);
      }
    } else {
      this.goodSince = null;
      this._gateOpen$.next(false);
    }
  }

  private classify(buf: number[]): ContactState {
    if (buf.length < MIN_SAMPLES) return 'unknown';
    if (buf.some(s => isNaN(s))) return 'poor';
    const mean = buf.reduce((s, x) => s + x, 0) / buf.length;
    const variance = buf.reduce((s, x) => s + (x - mean) ** 2, 0) / buf.length;
    return variance < MIN_VARIANCE || variance > MAX_VARIANCE ? 'poor' : 'good';
  }
}