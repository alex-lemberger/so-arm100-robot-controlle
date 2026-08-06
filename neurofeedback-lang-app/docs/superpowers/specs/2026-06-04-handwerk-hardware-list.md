# Handwerk Capture Platform — Hardware List

Date: 2026-06-04

## Recommendation

Use **two MbientLab MetaMotionS sensors mounted on work gloves or wrist straps**
as the Phase 1 IMU hardware.

This is the best fit for the current `/capture` implementation because the app
expects one left-hand and one right-hand BLE IMU stream, not a full proprietary
mocap pipeline. The goal for Phase 1 is to validate consent, synchronized EEG,
hand/wrist IMU, video, upload, and data quality with the least hardware risk.

## Pilot Hardware Kit

### Required

| Role | Recommended hardware | Quantity | Why |
|---|---:|---:|---|
| Hand/wrist IMU | MbientLab MetaMotionS with case | 2 active + 1 spare | BLE IMU with accelerometer, gyroscope, magnetometer, sensor fusion, onboard logging, and Android compatibility. |
| EEG | Neurosity Crown | 1 | Already integrated through the app's `BrainDevice` abstraction; supports focus/calm streams used by capture. |
| Capture device | Android tablet running Chrome | 1 | Chrome on Android supports Web Bluetooth; tablet camera can be used through `getUserMedia`. |
| Gloves | Durable work gloves, thin enough for dexterity | 2 pairs | Holds the IMU modules in a repeatable worker-friendly position. |
| Mounting | Velcro straps, elastic wrist straps, 3D-printed sensor clips, or sewn pouches | 1 kit | Keeps sensor orientation consistent and prevents impact damage. |
| Video support | Tablet stand or clamp mount | 1 | Reduces camera shake and keeps the work surface visible. |
| Power | USB power bank, tablet charger, sensor charging cables | 1 kit | Prevents pilot sessions from failing due to battery. |
| Connectivity | Stable Wi-Fi or LTE hotspot | 1 | Required for Firebase Auth, Firestore writes, and Storage uploads. |

### Sensor Placement

Start with one sensor per hand:

- Left sensor: back of left hand or wrist, fixed orientation.
- Right sensor: back of right hand or wrist, fixed orientation.
- Label each sensor physically as `LEFT` and `RIGHT`.
- Record the sensor axis orientation in the pilot log before the first session.

If wrist-level data is insufficient, expand to a v2 glove with additional
MetaMotionS modules on fingers or tools. Do not start there; it increases
pairing, synchronization, battery, and mounting complexity.

## Why MetaMotionS First

MetaMotionS is a compact BLE motion sensor board that supports long-running raw
sensor logging/streaming, 3-axis accelerometer, 3-axis gyroscope, magnetometer,
sensor fusion, onboard memory, and Android BLE use. MbientLab also documents its
BLE/API protocol and provides app/API paths for accessing sensor data.

This aligns with our current data model:

```ts
interface ImuFrame {
  t: number;
  ax: number; ay: number; az: number;
  gx: number; gy: number; gz: number;
}
```

## Integration Implications

The current `ImuService` still uses placeholder UUIDs and assumes a simple
notification characteristic. MetaMotionS integration will require implementing
the MetaWear/MetaMotion protocol commands to:

- discover the sensor service/characteristics,
- configure accelerometer and gyroscope sampling rates,
- start streaming or logging,
- subscribe to notifications,
- parse raw accelerometer and gyroscope payloads,
- normalize units into the app's `ImuFrame` structure,
- handle reconnects and stale subscriptions.

Target pilot settings:

- Sampling rate: `50 Hz` per hand for accelerometer and gyroscope.
- Upload format: keep the current `Float32Array` frame layout:
  `t, ax, ay, az, gx, gy, gz`.
- Timestamp source: app-side session clock for v1; hardware timestamping can be
  evaluated later if drift becomes measurable.

## Alternatives

| Option | Fit | Pros | Cons | When to choose |
|---|---|---|---|---|
| **MbientLab MetaMotionS** | Best Phase 1 fit | Small, BLE, raw IMU, Android compatible, documented APIs/protocol, onboard logging. | Requires MetaWear protocol work; not a true finger-tracking glove. | Default pilot choice. |
| **Movesense Sensor** | Good alternative | BLE wearable sensor, Android SDK, accelerometer/gyroscope, body-worn design. | Web Bluetooth integration may need custom protocol work; less aligned with current two-glove framing. | If MetaMotion availability or protocol work blocks us. |
| **Shimmer3 IMU** | Research-grade alternative | Strong sensor/research ecosystem, Android APIs, high-quality IMU data. | More expensive, more research-equipment workflow, may not fit browser-first Web Bluetooth cleanly. | If pilot data quality matters more than hardware cost and browser simplicity. |
| **ST SensorTile / BlueST devices** | Engineering alternative | Lower-cost BLE inertial sensors with SDK support. | More firmware/protocol work; less polished as a field wearable. | If we accept more embedded work for lower unit cost. |
| **Rokoko Smartgloves** | Not Phase 1 default | Mature glove product, finger/hand mocap, high frame-rate animation workflow. | Proprietary pipeline, optimized for Rokoko Studio/integrations, not simple raw browser BLE capture. | Later, if buyer demand requires high-fidelity finger pose. |
| **MANUS Metagloves** | Premium mocap option | Professional hand tracking, low latency, strong realtime integrations. | Expensive, proprietary, overkill for first raw telemetry pilot. | Later, if robotics buyers require premium hand-pose capture. |
| **Custom ESP32 + IMU glove** | Long-term custom option | Full control over BLE GATT, payloads, casing, sampling, and cost at scale. | Requires hardware, firmware, calibration, charging, safety, and QA work. | After proving data value with off-the-shelf sensors. |

## Hardware Decision

Phase 1 should proceed with:

1. **2x MbientLab MetaMotionS sensors** for active left/right hand capture.
2. **1x spare MetaMotionS sensor** for pilot continuity.
3. **1x Neurosity Crown** for EEG focus/calm capture.
4. **1x Android tablet running Chrome** for Web Bluetooth, camera, and upload.
5. **Work gloves plus repeatable sensor mounts** for field usability.

## Procurement Notes

- Buy at least one spare IMU sensor before field testing.
- Choose mounts that survive vibration, sweat, dust, and accidental impacts.
- Keep sensor labels and app hand assignment consistent.
- Test Web Bluetooth pairing with two simultaneous MetaMotionS devices before
  relying on a pilot session.
- Validate the tablet camera angle and lighting with actual task benches.

## Open Questions

- Which exact Android tablet model will be used for the pilot?
- Will capture workers authenticate with Firebase, or do we need anonymous route
  access for the `/capture` flow?
- Are wrist-level IMU signals sufficient, or do robotics buyers require finger
  articulation?
- Do we need hardware-side logging as a fallback when BLE streaming drops?
- What minimum session length must the battery setup support?

## Sources Checked

- MbientLab MetaMotionS product page: https://mbientlab.com/store/metamotions/
- MbientLab API specification: https://docs.mbientlab.com/api-specification/
- MbientLab tutorials/API overview: https://mbientlab.com/tutorials
- Google Chrome Web Bluetooth support on Android: https://support.google.com/chrome/answer/6362090
- Neurosity SDK docs: https://docs.neurosity.co/
- Movesense Android developer guide: https://www.movesense.com/docs/mobile/android/main/
- Movesense sensor docs: https://www.movesense.com/docs/
- ST BlueST SDK: https://www.st.com/en/embedded-software/bluest-sdk.html
- Rokoko Smartgloves product page: https://www.rokoko.com/products/smartgloves
- MANUS Quantum Metagloves product page: https://www.manus-meta.com/products/quantum-metagloves
