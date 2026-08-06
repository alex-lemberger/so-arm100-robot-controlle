# SO-ARM100 Robot Controller

Local web dashboard for controlling and monitoring an SO-ARM100 robot, with joint controls, kinematics tools, sequence editing, telemetry, a 3D view, and local AI sequence generation.

## Run locally

Prerequisites: Node.js and [Ollama](https://ollama.com/).

```bash
npm install
ollama serve
ollama pull ornith:9b
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Configuration

The server defaults to Ollama at `http://127.0.0.1:11434` with model `ornith:9b`. Override these values in `.env.local`:

```env
OLLAMA_BASE_URL="http://127.0.0.1:11434"
OLLAMA_MODEL="ornith:9b"

# Optional, controller-specific raw safety commands. Verify these with the
# robot controller documentation before enabling physical hardware control.
VITE_ESTOP_COMMAND=""
VITE_TORQUE_ENABLE_COMMAND=""
VITE_TORQUE_DISABLE_COMMAND=""
```

The frontend sends sequence-generation requests to `/api/ollama/generate-sequence`. The server requests structured JSON from Ollama and repairs common malformed JSON responses before returning them.

Hardware position commands are coalesced to 20 Hz while the UI continues to animate smoothly. The software E-stop always clears queued motion. It sends a physical E-stop command only when `VITE_ESTOP_COMMAND` is configured with the exact protocol command for your controller.

## Direct STS3215 USB control

Direct USB WebSerial now uses Feetech binary packets, not the old placeholder ASCII format. Select the correct half-duplex TTL adapter at **1,000,000 baud**, then click **Verify Servos**. The scan only sends `PING` and present-position `READ` requests to IDs 1–6, so it does not command motion.

Physical position packets are deliberately locked until the scan finds all six servos and a real, arm-specific calibration is in `.env.local`:

```env
# Replace every value with limits measured from this particular arm.
# Include the homingOffset stored by LeRobot as well as each measured range.
VITE_FEETECH_CALIBRATION='{"base":{"minTick":123,"maxTick":3970,"homingOffset":0},"shoulder":{"minTick":3850,"maxTick":210,"homingOffset":0},"elbow":{"minTick":180,"maxTick":3910,"homingOffset":0},"wristPitch":{"minTick":3700,"maxTick":290,"homingOffset":0},"wristRoll":{"minTick":120,"maxTick":3980,"homingOffset":0},"gripper":{"minTick":700,"maxTick":2800,"homingOffset":0}}'
```

The values above are shape-only examples and **must not be used** on a real arm. Restart the dev server after changing `.env.local`, verify all six servos again, then use **Arm Motion** and make one small, slow adjustment first. The app checks the stored travel limits and homing offsets against this calibration before it enables arming. It does not guess servo direction, offsets, or mechanical travel limits.

## Validation

```bash
npm run lint
npm run build
```
