# Arduino IMU BLE Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Arduino Nano 33 BLE Sense GATT firmware and wire the matching Angular `ImuService` with real UUIDs, correct packet parser, `error$` subject, and one-shot auto-reconnect.

**Architecture:** Two independent deliverables — (1) Arduino firmware that advertises a custom GATT service and sends 12-byte IMU packets at 50 Hz, (2) Angular `ImuService` changes that replace placeholder UUIDs/parser with the real protocol and add resilience. Tests for the Angular side use a fake Web Bluetooth stub (no hardware). Firmware is validated manually with nRF Connect.

**Tech Stack:** Arduino IDE + ArduinoBLE + Arduino_LSM9DS1 (firmware); Angular 19, Karma + Jasmine (service tests).

---

## Reference: design spec

`docs/superpowers/specs/2026-06-05-arduino-imu-ble-design.md`

## File structure

- **Create** `arduino/glove-imu/glove-imu.ino` — Arduino firmware (one sketch, deploy to both gloves with name changed per device)
- **Modify** `src/app/modules/capture/services/imu.service.ts` — real UUIDs, `namePrefix` filter, `parseFrame()`, `error$`, auto-reconnect
- **Create** `src/app/modules/capture/services/imu.service.spec.ts` — Web Bluetooth stub tests
- **Modify** `src/app/modules/capture/components/hardware-setup/hardware-setup.component.spec.ts` — add `error$` to `FakeImuService`

---

## Task 1: Arduino firmware

**Files:**
- Create: `arduino/glove-imu/glove-imu.ino`

### Step 1: Create the Arduino sketch directory and file

- [ ] Create `arduino/glove-imu/glove-imu.ino` with the following content:

```cpp
#include <ArduinoBLE.h>
#include <Arduino_LSM9DS1.h>

// Custom IMU service and notify characteristic UUIDs
#define SERVICE_UUID        "12345678-1234-1234-1234-123456789abc"
#define CHARACTERISTIC_UUID "12345678-1234-1234-1234-123456789abd"

// CHANGE THIS before flashing to the right-hand glove:
//   #define GLOVE_NAME "GloveRight"
#define GLOVE_NAME "GloveLeft"

BLEService imuService(SERVICE_UUID);
BLECharacteristic imuCharacteristic(CHARACTERISTIC_UUID, BLENotify, 12);

void setup() {
  Serial.begin(9600);

  if (!IMU.begin()) {
    Serial.println("IMU init failed");
    while (1);
  }

  if (!BLE.begin()) {
    Serial.println("BLE init failed");
    while (1);
  }

  BLE.setLocalName(GLOVE_NAME);
  BLE.setAdvertisedService(imuService);
  imuService.addCharacteristic(imuCharacteristic);
  BLE.addService(imuService);
  BLE.advertise();

  Serial.print("BLE advertising as: ");
  Serial.println(GLOVE_NAME);
}

void loop() {
  BLE.poll();

  if (IMU.accelerationAvailable() && IMU.gyroscopeAvailable()) {
    float ax, ay, az, gx, gy, gz;
    IMU.readAcceleration(ax, ay, az);
    IMU.readGyroscope(gx, gy, gz);

    // Pack as 6 × Int16 little-endian, scaled ×100
    uint8_t packet[12];
    int16_t values[6] = {
      (int16_t)(ax * 100),
      (int16_t)(ay * 100),
      (int16_t)(az * 100),
      (int16_t)(gx * 100),
      (int16_t)(gy * 100),
      (int16_t)(gz * 100),
    };
    memcpy(packet, values, 12);
    imuCharacteristic.writeValue(packet, 12);
  }

  delay(20); // ~50 Hz
}
```

### Step 2: Verify firmware manually with nRF Connect

- [ ] Flash to Arduino Nano 33 BLE Sense via Arduino IDE (requires `ArduinoBLE` and `Arduino_LSM9DS1` libraries installed)
- [ ] Open nRF Connect on iOS or Android
- [ ] Scan — confirm device named `GloveLeft` appears
- [ ] Connect → find service `12345678-1234-1234-1234-123456789abc`
- [ ] Subscribe to characteristic `12345678-1234-1234-1234-123456789abd`
- [ ] Confirm 12-byte packets arriving at ~50 Hz
- [ ] Confirm values change when moving the sensor
- [ ] Flash second Arduino with `GLOVE_NAME "GloveRight"`, repeat verification

### Step 3: Commit

- [ ] Run:
```bash
git add arduino/
git commit -m "feat: Arduino Nano 33 BLE Sense IMU firmware — 50 Hz GATT notify"
```

---

## Task 2: `ImuService` — real UUIDs, namePrefix filter, corrected `parseFrame()` (TDD)

**Files:**
- Create: `src/app/modules/capture/services/imu.service.spec.ts`
- Modify: `src/app/modules/capture/services/imu.service.ts`

### Step 1: Write the failing tests

- [ ] Create `src/app/modules/capture/services/imu.service.spec.ts`:

```ts
import { ImuService } from './imu.service';

/** Build a 12-byte DataView simulating an Arduino IMU packet. */
function makePacket(ax: number, ay: number, az: number,
                    gx: number, gy: number, gz: number): DataView {
  const buf = new ArrayBuffer(12);
  const view = new DataView(buf);
  view.setInt16(0,  Math.round(ax * 100), true);
  view.setInt16(2,  Math.round(ay * 100), true);
  view.setInt16(4,  Math.round(az * 100), true);
  view.setInt16(6,  Math.round(gx * 100), true);
  view.setInt16(8,  Math.round(gy * 100), true);
  view.setInt16(10, Math.round(gz * 100), true);
  return view;
}

/** Fake BluetoothRemoteGATTCharacteristic with a settable value. */
function fakeCharacteristicEvent(view: DataView): Event {
  const target = { value: view } as unknown as EventTarget;
  return { target } as unknown as Event;
}

describe('ImuService — parseFrame', () => {
  let service: ImuService;

  beforeEach(() => {
    service = new ImuService();
    // Expose parseFrame for direct testing
    (service as any).sessionStart = 0;
  });

  it('parses positive accel and gyro values correctly', () => {
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(1.23, 4.56, 7.89, 10.11, 12.13, 14.15)),
      'left'
    );
    expect(frame.ax).toBeCloseTo(1.23, 1);
    expect(frame.ay).toBeCloseTo(4.56, 1);
    expect(frame.az).toBeCloseTo(7.89, 1);
    expect(frame.gx).toBeCloseTo(10.11, 1);
    expect(frame.gy).toBeCloseTo(12.13, 1);
    expect(frame.gz).toBeCloseTo(14.15, 1);
  });

  it('parses negative values correctly', () => {
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(-1.0, -2.0, -3.0, -4.0, -5.0, -6.0)),
      'left'
    );
    expect(frame.ax).toBeCloseTo(-1.0, 1);
    expect(frame.gz).toBeCloseTo(-6.0, 1);
  });

  it('assigns t as offset from sessionStart', () => {
    (service as any).sessionStart = Date.now() - 500;
    const frame = (service as any).parseFrame(
      fakeCharacteristicEvent(makePacket(0, 0, 0, 0, 0, 0)),
      'left'
    );
    expect(frame.t).toBeGreaterThanOrEqual(490);
    expect(frame.t).toBeLessThan(600);
  });
});

describe('ImuService — recording', () => {
  let service: ImuService;

  beforeEach(() => {
    service = new ImuService();
  });

  it('ignores frames before startRecording()', () => {
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    expect(result.left.length).toBe(0);
  });

  it('accumulates left frames only while recording', () => {
    service.startRecording(Date.now());
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    // 2 frames × 7 floats = 14
    expect(result.left.length).toBe(14);
    expect(result.right.length).toBe(0);
  });

  it('stopRecording() produces correct Float32Array layout per frame', () => {
    service.startRecording(0);
    const evt = fakeCharacteristicEvent(makePacket(1.0, 2.0, 3.0, 4.0, 5.0, 6.0));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    // t=0 index, ax=1 index, ay=2, az=3, gx=4, gy=5, gz=6
    expect(result.left[1]).toBeCloseTo(1.0, 1); // ax
    expect(result.left[2]).toBeCloseTo(2.0, 1); // ay
    expect(result.left[6]).toBeCloseTo(6.0, 1); // gz
  });

  it('does not accumulate frames after stopRecording()', () => {
    service.startRecording(Date.now());
    service.stopRecording();
    const evt = fakeCharacteristicEvent(makePacket(1, 2, 3, 4, 5, 6));
    (service as any).onCharacteristicChanged(evt, 'left');
    const result = service.stopRecording();
    expect(result.left.length).toBe(0);
  });
});
```

### Step 2: Run tests to verify they fail

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/imu.service.spec.ts'
```
Expected: FAIL — `onCharacteristicChanged` not found, `parseFrame` stub returns wrong values.

### Step 3: Implement UUIDs, filter, `parseFrame`, and extract `onCharacteristicChanged`

- [ ] Replace the full content of `src/app/modules/capture/services/imu.service.ts`:

```ts
import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { ImuFrame } from '../models/capture-session.model';

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
    return 'bluetooth' in navigator;
  }

  async connect(hand: Hand): Promise<void> {
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
      // Re-subscribe to notifications after reconnect
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
```

### Step 4: Run tests to verify they pass

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/imu.service.spec.ts'
```
Expected: PASS (7 specs).

### Step 5: Commit

- [ ] Run:
```bash
git add src/app/modules/capture/services/imu.service.ts \
        src/app/modules/capture/services/imu.service.spec.ts
git commit -m "feat: ImuService — real UUIDs, namePrefix filter, corrected parseFrame"
```

---

## Task 3: `ImuService` — `error$` and auto-reconnect tests

**Files:**
- Modify: `src/app/modules/capture/services/imu.service.spec.ts` — append reconnect + error$ specs

### Step 1: Append failing reconnect and error$ tests

- [ ] Append to `imu.service.spec.ts` (after the existing `describe` blocks):

```ts
describe('ImuService — error$ and reconnect', () => {
  let service: ImuService;
  let mockBluetooth: jasmine.SpyObj<Bluetooth>;
  let mockDevice: any;
  let mockServer: any;
  let mockCharacteristic: any;

  beforeEach(() => {
    mockCharacteristic = {
      startNotifications: jasmine.createSpy().and.returnValue(Promise.resolve()),
      addEventListener:   jasmine.createSpy(),
    };
    mockServer = {
      connected:         true,
      getPrimaryService: jasmine.createSpy().and.returnValue(Promise.resolve({
        getCharacteristic: jasmine.createSpy().and.returnValue(Promise.resolve(mockCharacteristic)),
      })),
      disconnect:        jasmine.createSpy(),
    };
    mockDevice = {
      gatt:             mockServer,
      addEventListener: jasmine.createSpy(),
    };
    mockServer.connect = jasmine.createSpy().and.returnValue(Promise.resolve(mockServer));
    mockDevice.gatt.connect = jasmine.createSpy().and.returnValue(Promise.resolve(mockServer));

    mockBluetooth = jasmine.createSpyObj('Bluetooth', ['requestDevice']);
    mockBluetooth.requestDevice.and.returnValue(Promise.resolve(mockDevice));
    (navigator as any).bluetooth = mockBluetooth;

    service = new ImuService();
  });

  it('error$ starts empty', () => {
    expect(service.error$.value).toEqual({});
  });

  it('NotFoundError on requestDevice leaves connected state false and does not throw', async () => {
    mockBluetooth.requestDevice.and.returnValue(
      Promise.reject(Object.assign(new Error('User cancelled'), { name: 'NotFoundError' }))
    );
    await expectAsync(service.connect('left')).toBeResolved();
    expect(service.error$.value['left']).toBeUndefined();
  });

  it('connect() clears error$ for the hand on success', async () => {
    service['error$'].next({ left: 'Connection lost' });
    await service.connect('left');
    expect(service.error$.value['left']).toBeNull();
  });

  it('onDisconnected sets error$ and emits false on leftConnected$ when reconnect fails', async () => {
    await service.connect('left');
    mockDevice.gatt.connect.and.returnValue(Promise.reject(new Error('BT gone')));

    let connected: boolean | undefined;
    service.leftConnected$.subscribe(v => connected = v);

    await (service as any).onDisconnected('left', mockDevice);

    expect(connected).toBe(false);
    expect(service.error$.value['left']).toBe('Connection lost');
  });
});
```

### Step 2: Run to verify new specs fail

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/imu.service.spec.ts'
```
Expected: 7 existing specs pass; 4 new reconnect/error$ specs fail.

### Step 3: Run all specs to verify all pass (implementation already done in Task 2)

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/imu.service.spec.ts'
```
Expected: PASS (11 specs total).

### Step 4: Commit

- [ ] Run:
```bash
git add src/app/modules/capture/services/imu.service.spec.ts
git commit -m "test: ImuService — error\$ and reconnect specs"
```

---

## Task 4: Update `FakeImuService` in hardware-setup spec

**Files:**
- Modify: `src/app/modules/capture/components/hardware-setup/hardware-setup.component.spec.ts`

The existing `FakeImuService` in the component spec doesn't have `error$`. The component will fail to compile if it tries to read `error$` from the injected service. Add it to the fake.

### Step 1: Add `error$` to `FakeImuService`

- [ ] Open `src/app/modules/capture/components/hardware-setup/hardware-setup.component.spec.ts`
- [ ] Find the `FakeImuService` class and add the `error$` field:

```ts
class FakeImuService {
  isSupported = true;
  leftConnected  = new BehaviorSubject(false);
  rightConnected = new BehaviorSubject(false);
  leftConnected$  = this.leftConnected.asObservable();
  rightConnected$ = this.rightConnected.asObservable();
  error$ = new BehaviorSubject<Partial<Record<'left' | 'right', string | null>>>({});
  connect    = jasmine.createSpy('connect').and.returnValue(Promise.resolve());
  disconnect = jasmine.createSpy('disconnect').and.returnValue(Promise.resolve());
  startRecording = jasmine.createSpy('startRecording');
  stopRecording  = jasmine.createSpy('stopRecording').and.returnValue({ left: new Float32Array(), right: new Float32Array() });
}
```

### Step 2: Run hardware-setup component specs

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless --include='**/hardware-setup.component.spec.ts'
```
Expected: PASS (all existing specs).

### Step 3: Commit

- [ ] Run:
```bash
git add src/app/modules/capture/components/hardware-setup/hardware-setup.component.spec.ts
git commit -m "fix: add error\$ to FakeImuService in hardware-setup spec"
```

---

## Task 5: Final verification and build

### Step 1: Run all IMU-related specs together

- [ ] Run:
```bash
npx ng test --watch=false --browsers=ChromeHeadless \
  --include='**/imu.service.spec.ts' \
  --include='**/hardware-setup.component.spec.ts'
```
Expected: PASS (11 + existing hardware-setup specs).

### Step 2: Verify build

- [ ] Run:
```bash
npx ng build --configuration development
```
Expected: `Application bundle generation complete.`

### Step 3: Commit docs update

- [ ] Run:
```bash
git add docs/superpowers/plans/2026-06-05-arduino-imu-ble.md
git commit -m "docs: Arduino IMU BLE implementation plan"
git push origin master
```

---

## Done criteria

- Arduino firmware flashes, advertises `GloveLeft` / `GloveRight`, sends 12-byte IMU packets at ~50 Hz (verified with nRF Connect)
- `ImuService` uses real service/characteristic UUIDs, `namePrefix` filter, correct Int16 parser
- `error$` surfaces connection loss per hand
- One-shot auto-reconnect on `gattserverdisconnected`
- `NotFoundError` (user cancelled pairing) silently ignored
- 11 `ImuService` specs pass without hardware
- `ng build --configuration development` passes
