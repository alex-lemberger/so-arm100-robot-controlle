// core/services/mock-neurosity.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, Subject, Subscription, interval } from 'rxjs';
import { takeUntil } from 'rxjs/operators';
import { BrainDevice, DeviceState, DeviceStatus, EegReading } from '../brain-device';

@Injectable()
export class MockNeurosityService extends BrainDevice implements OnDestroy {
  private destroy$ = new Subject<void>();
  private streamSub?: Subscription;
  private mockUpdateInterval = 1000; // Update every second

  // Mock credentials for testing
  private mockCredentials = {
    email: 'test@example.com',
    password: 'password123'
  };

  // BehaviorSubjects for metrics
  public readonly focus$ = new BehaviorSubject<number | null>(null);
  public readonly calm$ = new BehaviorSubject<number | null>(null);
  public readonly extras$ = undefined;
  public readonly rawEeg$: Observable<EegReading>;

  private _state = new BehaviorSubject<DeviceState>({
    isLoggedIn: false,
    error: null
  });

  public readonly state$ = this._state.asObservable();

  // Parameters for generating realistic data
  private baselineFocus = 70;  // Base focus level
  private baselineCalm = 65;   // Base calm level
  private variance = 10;       // Maximum variance
  private trend = 0;          // Current trend
  private trendStrength = 0.3; // How strongly trend affects next value
  private noiseStrength = 0.7; // How strongly random noise affects next value

  constructor() {
    super();
    this.focus$.next(null);
    this.calm$.next(null);

    // Create a simulated raw EEG stream
    this.rawEeg$ = new Observable<EegReading>(subscriber => {
      const start = Date.now();
      const id = setInterval(() => {
        const elapsed = Date.now() - start;
        const phase2 = elapsed >= 1500;
        const tick = Math.floor(elapsed / 50);
        for (let electrode = 0; electrode < 4; electrode++) {
          const samples: number[] = phase2
            ? Array.from({ length: 12 }, (_, i) => 20 * Math.sin((tick * 12 + i) * 0.1))
            : Array(12).fill(0);
          subscriber.next({ electrode, samples, timestamp: Date.now() });
        }
      }, 50);
      return () => clearInterval(id);
    });
  }

  private generateRealisticValue(baseline: number): number {
    // Update trend with some randomness
    this.trend = this.trend * 0.8 + (Math.random() - 0.5) * 2 * this.trendStrength;

    // Generate new value using trend and noise
    let newValue = baseline +
      this.trend * this.variance +
      (Math.random() - 0.5) * this.variance * this.noiseStrength;

    // Add occasional "events" to make data more interesting
    if (Math.random() < 0.05) { // 5% chance of an "event"
      newValue += (Math.random() - 0.5) * this.variance * 2;
    }

    // Ensure value stays within realistic bounds (0-100)
    newValue = Math.min(Math.max(newValue, 0), 100);

    return Number(newValue.toFixed(2));
  }

  private startMockDataStream(): void {
    this.streamSub?.unsubscribe();
    this.streamSub = interval(this.mockUpdateInterval)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        const focusValue = this.generateRealisticValue(this.baselineFocus);
        const calmValue = this.generateRealisticValue(this.baselineCalm);
        this.focus$.next(focusValue / 100);
        this.calm$.next(calmValue / 100);
      });
  }

  async connect(credentials?: { email: string; password: string }): Promise<void> {
    if (this._state.value.isLoggedIn) {
      return;
    }
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        if (
          credentials?.email === this.mockCredentials.email &&
          credentials?.password === this.mockCredentials.password
        ) {
          this._state.next({ isLoggedIn: true, error: null });
          this.startMockDataStream();
          resolve();
        } else {
          this._state.next({ isLoggedIn: false, error: 'Invalid credentials' });
          reject(new Error('Invalid credentials'));
        }
      }, 1000);
    });
  }

  async disconnect(): Promise<void> {
    return new Promise((resolve) => {
      setTimeout(() => {
        this.streamSub?.unsubscribe();
        this._state.next({ isLoggedIn: false, error: null });
        this.focus$.next(null);
        this.calm$.next(null);
        resolve();
      }, 500);
    });
  }

  async getStatus(): Promise<DeviceStatus> {
    return Promise.resolve({
      state: 'online',
      battery: {
        level: 85,
        charging: false
      },
      sampling: {
        rate: 256
      }
    });
  }

  ngOnDestroy() {
    this.streamSub?.unsubscribe();
    this.destroy$.next();
    this.destroy$.complete();
  }
}

