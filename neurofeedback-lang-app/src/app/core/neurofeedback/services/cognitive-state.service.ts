import { Injectable, inject } from '@angular/core';
import { BehaviorSubject, Subscription } from 'rxjs';
import { BrainDevice } from '../brain-device';
import { CognitiveState, initialCognitiveState, stepCognitive } from '../cognitive-metrics';

/**
 * Derives cognitive-state labels (load, fatigue, signalOk) from the device's
 * EEG band-power stream (`BrainDevice.extras$`). Mirrors FlowDetectorService:
 * pure logic in cognitive-metrics, thin streaming glue here.
 */
@Injectable({ providedIn: 'root' })
export class CognitiveStateService {
  private readonly device = inject(BrainDevice);

  private state: CognitiveState = initialCognitiveState();
  private startMs = 0;
  private sub: Subscription | null = null;

  private readonly _load = new BehaviorSubject<number | null>(null);
  private readonly _fatigue = new BehaviorSubject<number | null>(null);
  private readonly _signalOk = new BehaviorSubject<boolean>(false);

  readonly load$ = this._load.asObservable();
  readonly fatigue$ = this._fatigue.asObservable();
  readonly signalOk$ = this._signalOk.asObservable();

  /** Reset the baseline and begin consuming the band-power stream. */
  startSession(now: number = Date.now()): void {
    this.state = initialCognitiveState();
    this.startMs = now;
    this._load.next(null);
    this._fatigue.next(null);
    this._signalOk.next(false);
    this.sub?.unsubscribe();
    this.sub = this.device.extras$?.subscribe(bands => this.ingest(bands)) ?? null;
  }

  /** Stop consuming the stream. */
  endSession(): void {
    this.sub?.unsubscribe();
    this.sub = null;
  }

  private ingest(bands: Record<string, number>): void {
    this.state = stepCognitive(this.state, bands, Date.now() - this.startMs);
    this._load.next(this.state.load);
    this._fatigue.next(this.state.fatigue);
    this._signalOk.next(this.state.signalOk);
  }
}
