import { Observable } from 'rxjs';

export interface EegReading {
  electrode: number;  // 0–3: TP9, AF7, AF8, TP10
  samples: number[];  // raw microvolts
  timestamp: number;  // ms since epoch
}

export interface DeviceState {
  isLoggedIn: boolean;   // connected/authenticated
  error: string | null;
}

export interface DeviceStatus {
  state: string;         // 'online' | 'offline' | ...
  battery?: { level: number; charging: boolean };
  sampling?: { rate: number };
}

/**
 * Vendor-neutral neurofeedback device contract.
 * Doubles as the Angular DI token (abstract class = runtime token + type).
 * Implementations: NeurosityService (real), MockNeurosityService (synthetic).
 */
export abstract class BrainDevice {
  /** Focus probability stream, 0–1, null until data arrives. */
  abstract readonly focus$: Observable<number | null>;
  /** Calm probability stream, 0–1, null until data arrives. */
  abstract readonly calm$: Observable<number | null>;
  /** Connection/auth state. */
  abstract readonly state$: Observable<DeviceState>;
  /** Optional device-specific extra metrics (alpha/beta/theta, signal quality, …). */
  abstract readonly extras$?: Observable<Record<string, number>>;
  /** Raw per-electrode EEG readings. Only devices that expose raw EEG implement this. */
  abstract readonly rawEeg$?: Observable<EegReading>;

  /** Connect/authenticate. Credentials optional (USB/BT devices need none). */
  abstract connect(credentials?: { email: string; password: string }): Promise<void>;
  /** Disconnect and stop streams. */
  abstract disconnect(): Promise<void>;
  /** One-shot device status snapshot. */
  abstract getStatus(): Promise<DeviceStatus>;
}
