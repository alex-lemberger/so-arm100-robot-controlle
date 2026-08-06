# Robot Sim WebSocket Bridge — v2 Design

**Date:** 2026-06-09  
**Status:** Approved (updated)

## Goal

Full end-to-end demo pipeline: worker completes a capture session → clicks "Transfer to Sim" in the sessions table → Angular streams EEG tick data to MuJoCo → Unitree H1 humanoid plays a troweling motion modulated by the session's cognitive state (fatigue slows motion, inFlow triggers visual cue). Angular controls playback. No hardware required — mock EEG data is realistic enough to tell the story; real IMU retargeting is deferred to v3.

## Demo Flow

```
1. User selects task (e.g. "Plastering") in capture module dropdown
2. User starts recording → capture session runs (mock or real)
3. Session stops + saves to Supabase (EEG ticks: focus/calm/load/fatigue/inFlow)
4. Sessions table shows completed session with "Transfer to Sim" button
5. User clicks button → Angular sends session payload over WebSocket
6. MuJoCo H1 begins replay: scripted zigzag modulated by EEG ticks
7. Angular playback controls: Pause / Resume / Stop
8. Dashboard sim-control widget shows live tick, cognitive state, inFlow indicator
```

## Scope

- Python: `sim/ws_server.py` — single `mjpython` entry point (replaces `zigzag_demo.py` for demo use)
- Python: `sim/trowel_h1.py` — scripted H1 troweling, EEG-modulated
- Python: `setup_model.sh` — updated to also fetch Unitree H1 from `mujoco_menagerie`
- Angular: `SimBridgeService` (`core/sim-bridge/`)
- Angular: "Transfer to Sim" button in `CaptureSessionsTableComponent`
- Angular: `sim-control` dashboard widget (connection status + playback controls + EEG overlay)

`zigzag_demo.py` and the UR5e model kept as reference / `--model ur5e` alternative.

## Architecture

### Python — `sim/ws_server.py`

Single `mjpython` process:

- **Main thread:** MuJoCo passive viewer loop — loads model, runs `mj_step`, `viewer.sync()` each tick. Real-time pacing via `model.opt.timestep`.
- **Background thread:** `asyncio` WebSocket server on `ws://localhost:8765`. Thread-safe shared state via `threading.Lock` + shared dict; inbound commands via `queue.Queue`.
- **CLI flag:** `--model h1` (default) | `--model ur5e`

**State machine:**

```
IDLE → REPLAYING → PAUSED → REPLAYING
                 → IDLE (stop or replay ends)
```

Reset returns to IDLE + home pose. In IDLE, joints hold home pose (no motion).

**WebSocket protocol:**

Commands — Angular → Python:

| Command | Payload |
|---------|---------|
| `replay` | `{"cmd":"replay","sessionId":"...","taskLabel":"...","eegTicks":[...],"durationMs":N}` |
| `pause` | `{"cmd":"pause"}` |
| `resume` | `{"cmd":"resume"}` |
| `stop` | `{"cmd":"stop"}` |
| `reset` | `{"cmd":"reset"}` |

State broadcast — Python → Angular (every 10 sim ticks, ~30 Hz):

```json
{
  "status": "idle | replaying | paused",
  "tick": 42,
  "totalTicks": 300,
  "q": [float, ...],
  "eegTick": { "focus": 0.8, "calm": 0.6, "load": 0.4, "fatigue": 0.3, "inFlow": true }
}
```

Unknown commands: logged + ignored.

**Exit:** model XML missing → log clear error + exit immediately.

### Python — `sim/trowel_h1.py`

Scripted troweling for Unitree H1:
- Targets right-arm joints + slight torso lean (joint indices from `models/h1/h1.xml`)
- Sine-wave pattern identical to `zigzag_demo.py` in structure
- **EEG modulation:**
  - `fatigue` (0–1) → `SWEEP_HZ` scales down linearly (high fatigue = slower sweep, min 40% of base)
  - `inFlow = true` → viewer background tint (MuJoCo `mjv_defaultOption` rgba) shifts to a highlight colour
- Returns full `qpos`-length `np.ndarray`; main loop writes to `data.ctrl`

### Angular — `SimBridgeService`

**Location:** `src/app/core/sim-bridge/sim-bridge.service.ts`, `providedIn: 'root'`

**Signals:**
- `status: Signal<'disconnected' | 'idle' | 'replaying' | 'paused'>`
- `tick: Signal<number>`
- `totalTicks: Signal<number>`
- `joints: Signal<number[]>`
- `currentEegTick: Signal<EegTick | null>`

**Methods:**
- `connect()` / `disconnect()`
- `transferSession(session: SimReplayPayload)` — sends `replay` command with EEG tick array
- `pause()` / `resume()` / `stop()` / `reset()`

**`SimReplayPayload` type:**
```ts
interface SimReplayPayload {
  sessionId: string;
  taskLabel: string;
  durationMs: number;
  eegTicks: Pick<EegTick, 'focus' | 'calm' | 'load' | 'fatigue' | 'inFlow'>[];
}
```

**Reconnect:** unexpected WS close → retry after 3 s, max 3 attempts, then `status = 'disconnected'`.

No mock mode — local dev/demo tool only.

### Angular — `CaptureSessionsTableComponent`

Add "Transfer to Sim" action button per completed session row:
- Visible only when `simBridge.status() !== 'disconnected'`
- On click: fetches EEG ticks for that session from Supabase (`eeg_ticks` WHERE `session_id = ?`), then calls `simBridge.transferSession(...)`
- Disabled while a replay is already in progress (`status === 'replaying' | 'paused'`)
- Button label: "Transfer to Sim" (icon: `play_circle`)

### Angular — `sim-control` widget

**Location:** `src/app/shared/components/layout/dashboard-layout/widgets/sim-control/`

Follows existing widget pattern: `input()` signals, Angular Material, no D3.

**UI:**
- Connection status dot (green = connected, grey = disconnected) + "Sim offline / Reconnect" when disconnected
- Progress bar: `tick / totalTicks` (hidden when idle)
- Playback buttons: Pause / Resume / Stop — shown only when `status === 'replaying' | 'paused'`
- Live EEG overlay: focus, calm, load, fatigue bars + inFlow badge (DM Mono font)
- Task label + session ID header during replay

Wired into dashboard layout alongside existing arc rings / EEG waveform widgets.

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Sim not running when Angular loads | `status = 'disconnected'`; widget shows reconnect button |
| "Transfer to Sim" clicked while disconnected | Button disabled — not reachable |
| EEG tick fetch fails | Toast error; no WS command sent |
| MuJoCo XML missing | `ws_server.py` exits with clear log |
| Unknown WS command | Python logs + ignores |
| Angular navigates away mid-replay | `disconnect()` in `ngOnDestroy`; sim keeps running in Python |
| WS drops mid-replay | Auto-reconnect (3 s, max 3 retries); replay continues in Python |

## Testing

- **`SimBridgeService` spec:** mock native `WebSocket`; verify signals update on all incoming status values; verify `transferSession()` serialises payload; verify reconnect logic.
- **`sim-control` widget spec:** stub `SimBridgeService`; verify playback buttons hidden when idle, shown when replaying; progress bar visibility.
- **`CaptureSessionsTableComponent` spec:** stub `SimBridgeService`; verify transfer button hidden when disconnected, disabled when replaying.
- **Python:** manual verification only.
- **TypeScript gate:** `ng build --configuration development`.

## Roadmap Position

```
v1    scripted UR5e zigzag (done)
v2    THIS SPEC — H1 humanoid + WS bridge + session transfer + EEG-modulated replay
v2.5  real IK via sim/ik.py (wall-plane Cartesian waypoints instead of scripted joints)
v3    retarget real captured IMU motion → true skill replay (hardware required)
```

## Files to Create / Modify

| File | Action |
|------|--------|
| `handwerk-robot-sim/sim/ws_server.py` | Create |
| `handwerk-robot-sim/sim/trowel_h1.py` | Create |
| `handwerk-robot-sim/setup_model.sh` | Modify (add H1 fetch) |
| `handwerk-robot-sim/requirements.txt` | Modify (add `websockets`) |
| `src/app/core/sim-bridge/sim-bridge.service.ts` | Create |
| `src/app/core/sim-bridge/sim-bridge.service.spec.ts` | Create |
| `src/app/modules/capture/components/capture-sessions-table/` | Modify (add transfer button) |
| `src/app/shared/components/layout/dashboard-layout/widgets/sim-control/` | Create (component + spec) |
| Dashboard layout component | Modify (add sim-control widget) |
