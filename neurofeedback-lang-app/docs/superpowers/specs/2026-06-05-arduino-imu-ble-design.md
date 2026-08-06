# Arduino Nano 33 BLE Sense — IMU BLE Protocol Design

**Date:** 2026-06-05
**Status:** Approved, pending implementation plan

## Goal

Define the BLE GATT protocol for two Arduino Nano 33 BLE Sense sensors (left/right glove) and the matching Angular `ImuService` integration. Replaces placeholder UUIDs and stub parser in the existing service. No model, upload, or capture-flow changes required.

## Scope

**In scope:**
- Arduino firmware BLE GATT profile (service UUID, characteristic UUID, packet layout, 50 Hz sample loop)
- `ImuService` changes: real UUIDs, `namePrefix` device filter, corrected `parseFrame()`, one-shot auto-reconnect, `error$` subject
- Unit tests for `ImuService` using a fake Web Bluetooth stub (no hardware)

**Out of scope:**
- Magnetometer data (accel + gyro only)
- Hardware-side timestamps (app-side session clock used, consistent with `ImuFrame.t`)
- Finger-level tracking (wrist/hand motion only for Phase 1)
- Firmware unit tests (validated manually with nRF Connect BLE scanner)
- Any changes to `ImuFrame`, `CaptureSession`, upload pipeline, or capture UI

## Hardware

Arduino Nano 33 BLE Sense with LSM9DS1 IMU (accelerometer + gyroscope).
Two devices per session: one per hand, mounted on gloves or wrist straps.
Libraries: `ArduinoBLE`, `Arduino_LSM9DS1`.

---

## 1. Firmware GATT Profile

### BLE Advertisement

Each device advertises a fixed local name:
- Left glove: `GloveLeft`
- Right glove: `GloveRight`

The Angular `requestDevice()` filter matches on `namePrefix` — no MAC addresses hardcoded.

### UUIDs

| Role | UUID |
|------|------|
| IMU Service | `12345678-1234-1234-1234-123456789abc` |
| IMU Notify Characteristic | `12345678-1234-1234-1234-123456789abd` |

Same UUIDs on both gloves — the device name distinguishes left from right.

### Packet Layout

12 bytes per notification. All fields are signed 16-bit little-endian integers, scaled by ×100 to preserve two decimal places of precision without floating point.

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0 | 2 | ax | ÷100 | m/s² |
| 2 | 2 | ay | ÷100 | m/s² |
| 4 | 2 | az | ÷100 | m/s² |
| 6 | 2 | gx | ÷100 | °/s |
| 8 | 2 | gy | ÷100 | °/s |
| 10 | 2 | gz | ÷100 | °/s |

12 bytes fits within the minimum BLE MTU (20 bytes). No timestamp in packet — timestamp assigned app-side as `Date.now() - sessionStart`.

### Firmware Loop

```
setup():
  IMU.begin() — accelerometer + gyroscope only
  IMU.setAccelODR(50)  // 50 Hz output data rate
  IMU.setGyroODR(50)
  BLE.begin()
  BLE.setLocalName("GloveLeft")  // or "GloveRight"
  BLE.setAdvertisedService(imuService)
  imuService.addCharacteristic(imuCharacteristic)
  BLE.addService(imuService)
  BLE.advertise()

loop() — runs at 50 Hz (delay 20 ms):
  BLE.poll()
  if IMU.accelerationAvailable() && IMU.gyroscopeAvailable():
    read ax, ay, az, gx, gy, gz
    pack as 6× Int16 little-endian ×100
    imuCharacteristic.writeValue(packet, 12)
```

---

## 2. Angular `ImuService` Changes

File: `src/app/modules/capture/services/imu.service.ts`

### Constants

Replace placeholder UUIDs:

```ts
const SERVICE_UUID        = '12345678-1234-1234-1234-123456789abc';
const CHARACTERISTIC_UUID = '12345678-1234-1234-1234-123456789abd';
```

### Device Filter

```ts
const device = await navigator.bluetooth.requestDevice({
  filters: [{ namePrefix: hand === 'left' ? 'GloveLeft' : 'GloveRight' }],
  optionalServices: [SERVICE_UUID],
});
```

`namePrefix` ensures the pairing dialog shows only the correct glove.

### `parseFrame()`

```ts
private parseFrame(event: Event, hand: Hand): ImuFrame {
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
```

### `error$` Subject

New public observable surfaces connection errors to the capture UI:

```ts
readonly error$ = new BehaviorSubject<Partial<Record<Hand, string | null>>>({});
```

### Auto-Reconnect

One reconnect attempt on `gattserverdisconnected`. If it fails, emits `false` on the connected subject and sets `error$`:

```ts
device.addEventListener('gattserverdisconnected', async () => {
  try {
    await device.gatt!.connect();
    // re-subscribe to characteristic notifications
  } catch {
    this.gloves[hand] = undefined;
    (hand === 'left' ? this.leftConnected : this.rightConnected).next(false);
    this.error$.next({ ...this.error$.value, [hand]: 'Connection lost' });
  }
});
```

### Error Handling

| Scenario | Behaviour |
|----------|-----------|
| User cancels pairing dialog | `NotFoundError` swallowed; connected subject unchanged |
| BLE drops mid-session | One reconnect attempt; on failure emit `false` + `error$` |
| `connect()` called when already connected | No-op (existing guard) |

---

## 3. Testing Strategy

Tests run without hardware using a fake Web Bluetooth stub injected via `TestBed`.

**Test cases:**
- `parseFrame()` correctly divides Int16 values by 100 for all 6 axes
- Negative values (e.g. −1g) parsed correctly
- Frames only accumulate while `recording = true`; ignored before `startRecording()` and after `stopRecording()`
- `stopRecording()` returns `Float32Array` with correct 7-float-per-frame layout (`t, ax, ay, az, gx, gy, gz`)
- `gattserverdisconnected` triggers one reconnect attempt
- If reconnect fails, `leftConnected$` / `rightConnected$` emits `false` and `error$` is set
- `NotFoundError` on `requestDevice()` leaves connected state unchanged and does not throw

**Firmware validation** — manual bench test with nRF Connect (iOS/Android BLE scanner):
- Verify service UUID advertised
- Subscribe to characteristic, confirm 12-byte packets at ~50 Hz
- Confirm Int16 values match expected scale for known sensor orientations

---

## 4. Binary Upload Format

Unchanged. `framesToBinary()` already produces the correct layout:

```
Per frame: [t, ax, ay, az, gx, gy, gz] — 7 × Float32 = 28 bytes
File: imu_left.bin / imu_right.bin uploaded to Firebase Storage
```

---

## Done Criteria

- Arduino firmware advertises `GloveLeft` / `GloveRight`, sends 12-byte IMU packets at 50 Hz, verified with nRF Connect
- `ImuService` connects to correct glove by name prefix, parses packets correctly
- `error$` surfaces connection loss to capture UI
- One-shot auto-reconnect on drop
- All `ImuService` unit tests pass without hardware
- `ng build --configuration development` passes
