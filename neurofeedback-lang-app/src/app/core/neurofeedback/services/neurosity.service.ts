// neurosity.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject, Observable } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

import { environment } from '../../../environments/environment';
import { BrainDevice, DeviceState, DeviceStatus, EegReading } from '../brain-device';

@Injectable()
export class NeurosityService extends BrainDevice implements OnDestroy {
  private notion: any; // Using any because the SDK does not export a stable client interface.
  private destroy$ = new Subject<void>();
  private rawEegSub: { unsubscribe(): void } | null = null;
  private readonly _rawEeg$ = new Subject<EegReading>();
  readonly rawEeg$ = this._rawEeg$.asObservable();

  public readonly focus$ = new BehaviorSubject<number | null>(null);
  public readonly calm$ = new BehaviorSubject<number | null>(null);
  public readonly extras$ = undefined;

  private _state = new BehaviorSubject<DeviceState>({
    isLoggedIn: false,
    error: null
  });

  public readonly state$ = this._state.asObservable();

  constructor() {
    super();
    // NOTE: the Notion SDK is loaded lazily in ensureNotion() — never at module
    // eval / construction. @neurosity/sdk's browser bundle is a Parcel build
    // that throws `parcelRequire is not defined` if it loads at app boot, so it
    // must only be pulled in (as a separate chunk) when a real device connects.
  }

  /** Lazily import @neurosity/sdk and instantiate the Notion client on first use. */
  private async ensureNotion(): Promise<void> {
    if (this.notion) {
      return;
    }
    const { Notion } = await import('@neurosity/sdk');
    this.notion = new Notion({
      deviceId: environment.neurosityDeviceId
    });
  }

  async connect(credentials?: { email: string; password: string }): Promise<void> {
    if (!credentials) {
      throw new Error('Neurosity device requires email/password credentials');
    }
    if (this._state.value.isLoggedIn) {
      return;
    }
    try {
      await this.ensureNotion();
      await this.notion.login({
        email: credentials.email,
        password: credentials.password,
      });
      this._state.next({ isLoggedIn: true, error: null });
      await this.setupSubscriptions();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Login failed';
      this._state.next({ isLoggedIn: false, error: errorMessage });
      throw new Error(errorMessage);
    }
  }

  private async setupSubscriptions(): Promise<void> {
    try {
      await this.notion.whenReady();

      // Handle focus subscription
      new Observable<any>(observer => {
        const subscription = this.notion.focus().subscribe(observer);
        return () => subscription.unsubscribe();
      })
        .pipe(takeUntil(this.destroy$))
        .subscribe({
          next: (focus) => {
            this.focus$.next(focus.probability);
          },
          error: (error) => {
            console.error('Focus subscription error:', error);
            this._state.next({
              ...this._state.value,
              error: 'Focus monitoring failed'
            });
          }
        });

      // Handle calm subscription
      new Observable<any>(observer => {
        const subscription = this.notion.calm().subscribe(observer);
        return () => subscription.unsubscribe();
      })
        .pipe(takeUntil(this.destroy$))
        .subscribe({
          next: (calm) => {
            this.calm$.next(calm.probability);
          },
          error: (error) => {
            console.error('Calm subscription error:', error);
            this._state.next({
              ...this._state.value,
              error: 'Calm monitoring failed'
            });
          }
        });

      // Handle raw EEG subscription
      new Observable<any>(observer => {
        const subscription = this.notion.eeg().subscribe(observer);
        return () => subscription.unsubscribe();
      })
        .pipe(takeUntil(this.destroy$))
        .subscribe({
          next: (reading) => {
            this._rawEeg$.next({
              electrode: reading.electrode,
              samples: reading.samples,
              timestamp: reading.timestamp ?? Date.now(),
            });
          },
          error: (error) => {
            console.error('EEG subscription error:', error);
            this._state.next({
              ...this._state.value,
              error: 'EEG monitoring failed'
            });
          }
        });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to setup device connections';
      this._state.next({
        ...this._state.value,
        error: errorMessage
      });
      throw new Error(errorMessage);
    }
  }

  async disconnect(): Promise<void> {
    if (!this.notion) {
      this._state.next({
        isLoggedIn: false,
        error: null
      });
      this.focus$.next(null);
      this.calm$.next(null);
      return;
    }

    try {
      await this.notion.logout();
      this._state.next({
        isLoggedIn: false,
        error: null
      });
      this.focus$.next(null);
      this.calm$.next(null);
      this.rawEegSub?.unsubscribe();
      this.rawEegSub = null;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Logout failed';
      this._state.next({
        ...this._state.value,
        error: errorMessage
      });
      throw new Error(errorMessage);
    }
  }

  async getStatus(): Promise<DeviceStatus> {
    await this.ensureNotion();
    // notion.status() is typed `any` by the SDK; shape assumed to match DeviceStatus per Neurosity docs.
    const status = await this.notion.status();
    return status as DeviceStatus;
  }

  ngOnDestroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.rawEegSub?.unsubscribe();
    this.rawEegSub = null;
  }
}
