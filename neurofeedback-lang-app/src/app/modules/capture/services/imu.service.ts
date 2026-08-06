import { Injectable, inject } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { ImuFrame } from '../models/capture-session.model';
import { CaptureModeService } from './capture-mode.service';

const SERVICE_UUID        = '12345678-1234-1234-1234-123456789abc';
const CHARACTERISTIC_UUID = '12345678-1234-1234-1234-123456789abd';

type Hand = 'left' | 'right';

interface GloveDevice {
  device: BluetoothDevice;
  server: BluetoothRemoteGATTServer;
  characteristic: BluetoothRemoteGATTCharacteristic;
}

@Injectable({ providedIn: 'root' })
export class ImuService {
  private mode = inject(CaptureModeService);
  private gloves: Partial<Record<Hand, GloveDevice>> = {};

  private leftConnected  = new BehaviorSubject<boolean>(false);
  private rightConnected = new BehaviorSubject<boolean>(false);

  readonly leftConnected$  = this.leftConnected.asObservable();
  readonly rightConnected$ = this.rightConnected.asObservable();
  readonly error$ = new BehaviorSubject<Partial<Record<Hand, string | null>>>({});

  private leftFrames:  ImuFrame[] = [];
  private rightFrames: ImuFrame[] = [];
  private sessionStart = 0;
  private recording    = false;

  get isSupported(): boolean {
    return this.mode.isMock() || 'bluetooth' in navigator;
  }

  async connect(hand: Hand): Promise<void> {
    if (this.mode.isMock()) {
      await new Promise(r => setTimeout(r, 500));
      this.connected(hand).next(true);
      this.setError(hand, null);
      return;
    }
    const namePrefix = hand === 'left' ? 'GloveLeft' : 'GloveRight';
    let device: BluetoothDevice;
    try {
      device = await navigator.bluetooth.requestDevice({
        filters: [{ namePrefix }],
        optionalServices: [SERVICE_UUID],
      });
    } catch (err: any) {
      if (err?.name === 'NotFoundError') return; // user cancelled
      throw err;
    }

    const server         = await device.gatt!.connect();
    const service        = await server.getPrimaryService(SERVICE_UUID);
    const characteristic = await service.getCharacteristic(CHARACTERISTIC_UUID);

    device.addEventListener('gattserverdisconnected', () => this.onDisconnected(hand, device));

    await characteristic.startNotifications();
    characteristic.addEventListener('characteristicvaluechanged', (evt) =>
      this.onCharacteristicChanged(evt, hand)
    );

    this.gloves[hand] = { device, server, characteristic };
    this.connected(hand).next(true);
    this.setError(hand, null);
  }

  startRecording(sessionStartMs: number): void {
    this.sessionStart = sessionStartMs;
    this.leftFrames   = [];
    this.rightFrames  = [];
    this.recording    = true;
  }

  stopRecording(): { left: Float32Array; right: Float32Array } {
    this.recording = false;
    return {
      left:  this.framesToBinary(this.leftFrames),
      right: this.framesToBinary(this.rightFrames),
    };
  }

  async disconnect(): Promise<void> {
    for (const hand of ['left', 'right'] as Hand[]) {
      const glove = this.gloves[hand];
      if (glove?.server.connected) glove.server.disconnect();
      this.gloves[hand] = undefined;
    }
    this.leftConnected.next(false);
    this.rightConnected.next(false);
  }

  // Extracted for testability
  onCharacteristicChanged(event: Event, hand: Hand): void {
    if (!this.recording) return;
    const frame = this.parseFrame(event, hand);
    if (hand === 'left') this.leftFrames.push(frame);
    else this.rightFrames.push(frame);
  }

  private async onDisconnected(hand: Hand, device: BluetoothDevice): Promise<void> {
    try {
      await device.gatt!.connect();
      const server         = device.gatt!;
      const service        = await server.getPrimaryService(SERVICE_UUID);
      const characteristic = await service.getCharacteristic(CHARACTERISTIC_UUID);
      await characteristic.startNotifications();
      characteristic.addEventListener('characteristicvaluechanged', (evt) =>
        this.onCharacteristicChanged(evt, hand)
      );
      if (this.gloves[hand]) {
        this.gloves[hand]!.server         = server;
        this.gloves[hand]!.characteristic = characteristic;
      }
    } catch {
      this.gloves[hand] = undefined;
      this.connected(hand).next(false);
      this.setError(hand, 'Connection lost');
    }
  }

  private parseFrame(event: Event, _hand: Hand): ImuFrame {
    const view = (event.target as BluetoothRemoteGATTCharacteristic).value!;
    return {
      t:  Date.now() - this.sessionStart,
      ax: view.getInt16(0,  true) / 100,
      ay: view.getInt16(2,  true) / 100,
      az: view.getInt16(4,  true) / 100,
      gx: view.getInt16(6,  true) / 100,
      gy: view.getInt16(8,  true) / 100,
      gz: view.getInt16(10, true) / 100,
    };
  }

  private framesToBinary(frames: ImuFrame[]): Float32Array {
    const buf = new Float32Array(frames.length * 7);
    frames.forEach((f, i) => {
      buf[i * 7 + 0] = f.t;
      buf[i * 7 + 1] = f.ax;
      buf[i * 7 + 2] = f.ay;
      buf[i * 7 + 3] = f.az;
      buf[i * 7 + 4] = f.gx;
      buf[i * 7 + 5] = f.gy;
      buf[i * 7 + 6] = f.gz;
    });
    return buf;
  }

  private connected(hand: Hand): BehaviorSubject<boolean> {
    return hand === 'left' ? this.leftConnected : this.rightConnected;
  }

  private setError(hand: Hand, msg: string | null): void {
    this.error$.next({ ...this.error$.value, [hand]: msg });
  }
}
