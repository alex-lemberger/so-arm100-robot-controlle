# Robot Sim WebSocket Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full demo pipeline — Angular capture session → "Transfer to Sim" button → WebSocket → MuJoCo Unitree H1 humanoid plays EEG-modulated troweling motion — controllable from the Angular dashboard.

**Architecture:** A single `mjpython` process (`sim/ws_server.py`) runs the MuJoCo viewer on the main thread and a `websockets` asyncio server on a background thread. Commands (replay/pause/resume/stop/reset) arrive via WebSocket; state broadcasts (status, tick, joints, live EEG tick) flow back every 10 sim steps. Angular's `SimBridgeService` wraps the native WebSocket into signals; the `sim-control` dashboard widget and `CaptureSessionsTableComponent` transfer button consume it.

**Tech Stack:** Python 3.12 · MuJoCo 3.x · `websockets` · `mjpython` · Angular 19 · NGXS · Angular Material · Jasmine/Karma

**Spec:** `docs/superpowers/specs/2026-06-09-robot-sim-websocket-bridge-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `handwerk-robot-sim/setup_model.sh` | Modify | Add H1 model fetch from menagerie |
| `handwerk-robot-sim/requirements.txt` | Modify | Add `websockets>=12` |
| `handwerk-robot-sim/sim/trowel_h1.py` | Create | Scripted H1 troweling targets + EEG modulation |
| `handwerk-robot-sim/sim/ws_server.py` | Create | MuJoCo viewer loop + WS server entry point |
| `src/app/core/sim-bridge/sim-bridge.service.ts` | Create | WS client, signals, commands |
| `src/app/core/sim-bridge/sim-bridge.service.spec.ts` | Create | Unit tests for SimBridgeService |
| `src/app/modules/capture/services/supabase-capture.service.ts` | Modify | Add `fetchEegTicks(sessionId)` |
| `src/app/modules/capture/services/supabase-capture.service.spec.ts` | Modify | Test `fetchEegTicks` |
| `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts` | Modify | Add "Transfer to Sim" button |
| `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts` | Create | Connection status + playback controls + EEG overlay widget |
| `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts` | Modify | Import + render sim-control widget |

---

## Task 1: Python — H1 model setup

**Files:**
- Modify: `handwerk-robot-sim/setup_model.sh`
- Modify: `handwerk-robot-sim/requirements.txt`

- [ ] **Step 1: Add `websockets` to requirements.txt**

Replace contents of `handwerk-robot-sim/requirements.txt`:

```
mujoco>=3.1
numpy>=1.24
websockets>=12.0
```

- [ ] **Step 2: Add H1 fetch to setup_model.sh**

Replace `handwerk-robot-sim/setup_model.sh`:

```bash
#!/usr/bin/env bash
# Fetch UR5e and Unitree H1 models from MuJoCo Menagerie.
set -euo pipefail

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --depth 1 https://github.com/google-deepmind/mujoco_menagerie.git "$TMP/menagerie"

rm -rf models/ur5e
mkdir -p models
cp -r "$TMP/menagerie/universal_robots_ur5e" models/ur5e
echo "UR5e model -> models/ur5e/ (scene.xml, ur5e.xml + assets)"

rm -rf models/h1
cp -r "$TMP/menagerie/unitree_h1" models/h1
echo "H1 model -> models/h1/ (scene.xml, h1.xml + assets)"
```

- [ ] **Step 3: Fetch the models**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
pip install -r requirements.txt
chmod +x setup_model.sh && ./setup_model.sh
```

Expected: `models/h1/` created containing `scene.xml`, `h1.xml`, and an `assets/` folder.

- [ ] **Step 4: Confirm H1 actuator order**

```bash
grep -A1 'name=' models/h1/h1.xml | grep 'joint\|actuator' | head -60
```

The Unitree H1 has 19 actuators in this order (verify against output):
```
0  left_hip_yaw        5  right_hip_yaw       10 torso
1  left_hip_roll       6  right_hip_roll      11 left_shoulder_pitch
2  left_hip_pitch      7  right_hip_pitch     12 left_shoulder_roll
3  left_knee           8  right_knee          13 left_shoulder_yaw
4  left_ankle          9  right_ankle         14 left_elbow
                                              15 right_shoulder_pitch
                                              16 right_shoulder_roll
                                              17 right_shoulder_yaw
                                              18 right_elbow
```

Record the verified indices — they are used in Task 2.

- [ ] **Step 5: Commit**

```bash
cd ~/handwerk-robot-sim
git init  # only if not already a git repo; otherwise skip
git add setup_model.sh requirements.txt
git commit -m "chore: add H1 model fetch + websockets dependency"
```

---

## Task 2: Python — sim/trowel_h1.py

**Files:**
- Create: `handwerk-robot-sim/sim/trowel_h1.py`

- [ ] **Step 1: Create trowel_h1.py**

```python
"""Scripted troweling targets for the Unitree H1 humanoid.

Drives right-arm joints + torso lean through a sine-wave troweling pass.
EEG modulation: fatigue scales sweep speed; inFlow is returned as a flag
for the viewer to use as a visual cue.

Joint indices (confirm against models/h1/h1.xml, see Task 1 Step 4):
  10 torso
  15 right_shoulder_pitch
  16 right_shoulder_roll
  18 right_elbow
"""
from __future__ import annotations
import numpy as np

N_JOINTS = 19

# Standing home pose — legs slightly bent for balance, right arm ready.
HOME = np.zeros(N_JOINTS)
HOME[2] = -0.4   # left_hip_pitch
HOME[3] = 0.8    # left_knee
HOME[4] = -0.4   # left_ankle
HOME[7] = -0.4   # right_hip_pitch
HOME[8] = 0.8    # right_knee
HOME[9] = -0.4   # right_ankle
HOME[10] = 0.05  # torso: slight forward lean
HOME[15] = 0.5   # right_shoulder_pitch: arm forward
HOME[16] = -0.4  # right_shoulder_roll: arm slightly in
HOME[18] = 0.6   # right_elbow: bent for trowel grip

# Base motion parameters (tune on first run).
SWEEP_HZ_BASE = 0.15   # horizontal pass
ZIG_HZ = 1.2           # elbow zigzag within pass
SWEEP_AMP = 0.45       # shoulder_roll sweep amplitude (rad)
ZIG_AMP = 0.30         # elbow zigzag amplitude (rad)
TORSO_AMP = 0.06       # torso sway amplitude (rad)

# Fatigue modulation: at fatigue=1.0 sweep slows to this fraction of base.
MIN_SPEED_FACTOR = 0.4


def troweling_targets(
    t: float,
    fatigue: float | None = None,
    in_flow: bool = False,
) -> np.ndarray:
    """Return H1 joint targets for time t (seconds).

    fatigue: 0.0–1.0; slows the sweep when high.
    in_flow: returned for caller use (e.g. viewer tint) — does not affect joints.
    """
    speed = 1.0 - (fatigue or 0.0) * (1.0 - MIN_SPEED_FACTOR)
    hz = SWEEP_HZ_BASE * speed

    q = HOME.copy()
    q[10] += TORSO_AMP * np.sin(2 * np.pi * hz * t)
    q[15] += 0.15 * np.sin(2 * np.pi * hz * t)           # shoulder pitch follows sweep
    q[16] += SWEEP_AMP * np.sin(2 * np.pi * hz * t)      # main lateral sweep
    q[18] += ZIG_AMP * np.sin(2 * np.pi * ZIG_HZ * t)    # elbow zigzag
    return q
```

- [ ] **Step 2: Smoke-test (no viewer)**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
python - <<'EOF'
from sim.trowel_h1 import troweling_targets
import numpy as np
q = troweling_targets(1.0, fatigue=0.5, in_flow=True)
assert q.shape == (19,), f"expected (19,), got {q.shape}"
q2 = troweling_targets(1.0, fatigue=1.0)
q3 = troweling_targets(1.0, fatigue=0.0)
# high fatigue → smaller sweep than low fatigue (sweep_hz lower → sin value differs at t=1)
print("trowel_h1 OK:", q)
EOF
```

Expected: prints `trowel_h1 OK:` followed by an array.

- [ ] **Step 3: Commit**

```bash
git add sim/trowel_h1.py
git commit -m "feat: H1 scripted troweling targets with EEG modulation"
```

---

## Task 3: Python — sim/ws_server.py

**Files:**
- Create: `handwerk-robot-sim/sim/ws_server.py`

- [ ] **Step 1: Create ws_server.py**

```python
"""MuJoCo H1 troweling sim with WebSocket control bridge.

Main thread: MuJoCo passive viewer loop.
Background thread: asyncio WebSocket server on ws://localhost:8765.

Commands (Angular → Python):
  {"cmd": "replay", "sessionId": "...", "taskLabel": "...",
   "eegTicks": [...], "durationMs": N}
  {"cmd": "pause"} {"cmd": "resume"} {"cmd": "stop"} {"cmd": "reset"}

State broadcast (Python → Angular, every 10 sim ticks):
  {"status": "idle|replaying|paused", "tick": N, "totalTicks": N,
   "q": [...], "eegTick": {focus, calm, load, fatigue, inFlow} | null}

Run:
  mjpython sim/ws_server.py [--model h1|ur5e] [--port 8765]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import queue
import threading
import time
from typing import Any

import mujoco
import mujoco.viewer
import numpy as np
import websockets
from websockets.server import WebSocketServerProtocol

from sim.trowel_h1 import HOME as H1_HOME, troweling_targets as h1_targets

# ---------------------------------------------------------------------------
# Shared state (main thread writes, WS thread reads via broadcast queue)
# ---------------------------------------------------------------------------
_cmd_q: queue.SimpleQueue[dict] = queue.SimpleQueue()
_broadcast_q: queue.SimpleQueue[str] = queue.SimpleQueue()

_lock = threading.Lock()
_shared: dict[str, Any] = {
    'status': 'idle',       # 'idle' | 'replaying' | 'paused'
    'tick': 0,
    'total_ticks': 0,
    'q': [],
    'eeg_tick': None,       # current EegTick dict | None
    'replay_ticks': [],     # list of eeg tick dicts
    'duration_ms': 0.0,
    'elapsed_ms': 0.0,
}

# ---------------------------------------------------------------------------
# WebSocket server (background asyncio thread)
# ---------------------------------------------------------------------------
_clients: set[WebSocketServerProtocol] = set()


async def _handler(ws: WebSocketServerProtocol) -> None:
    _clients.add(ws)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
                _cmd_q.put(msg)
            except json.JSONDecodeError:
                pass
    finally:
        _clients.discard(ws)


async def _broadcast_loop() -> None:
    while True:
        msgs: list[str] = []
        try:
            while True:
                msgs.append(_broadcast_q.get_nowait())
        except queue.Empty:
            pass
        if msgs and _clients:
            last = msgs[-1]  # only latest state matters
            await asyncio.gather(
                *[ws.send(last) for ws in list(_clients)],
                return_exceptions=True,
            )
        await asyncio.sleep(0.01)


async def _ws_main(port: int) -> None:
    async with websockets.serve(_handler, 'localhost', port):
        await _broadcast_loop()


def _start_ws_thread(port: int) -> None:
    asyncio.run(_ws_main(port))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _snap(state: dict) -> str:
    with _lock:
        eeg = state['eeg_tick']
    return json.dumps({
        'status': state['status'],
        'tick': state['tick'],
        'totalTicks': state['total_ticks'],
        'q': [round(v, 4) for v in state['q']],
        'eegTick': eeg,
    })


def _current_eeg(state: dict) -> dict | None:
    ticks = state['replay_ticks']
    if not ticks or state['total_ticks'] == 0:
        return None
    idx = min(state['tick'], len(ticks) - 1)
    return ticks[idx]


def _process_commands(state: dict) -> None:
    while not _cmd_q.empty():
        try:
            cmd = _cmd_q.get_nowait()
        except queue.Empty:
            break
        action = cmd.get('cmd')
        with _lock:
            if action == 'replay':
                state['replay_ticks'] = cmd.get('eegTicks', [])
                state['total_ticks'] = len(state['replay_ticks'])
                state['duration_ms'] = float(cmd.get('durationMs', 0))
                state['tick'] = 0
                state['elapsed_ms'] = 0.0
                state['status'] = 'replaying'
            elif action == 'pause' and state['status'] == 'replaying':
                state['status'] = 'paused'
            elif action == 'resume' and state['status'] == 'paused':
                state['status'] = 'replaying'
            elif action in ('stop', 'reset'):
                state['status'] = 'idle'
                state['tick'] = 0
                state['replay_ticks'] = []
                state['total_ticks'] = 0
                state['eeg_tick'] = None


# ---------------------------------------------------------------------------
# UR5e fallback (scripted zigzag, reuses zigzag_demo pattern)
# ---------------------------------------------------------------------------
_UR5E_HOME = np.array([0.0, -1.57, 1.57, -1.57, -1.57, 0.0])


def _ur5e_targets(t: float) -> np.ndarray:
    q = _UR5E_HOME.copy()
    q[0] += 0.6 * np.sin(2 * np.pi * 0.15 * t)
    q[2] += 0.35 * np.sin(2 * np.pi * 1.2 * t)
    q[3] += 0.175 * np.sin(2 * np.pi * 1.2 * t)
    return q


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['h1', 'ur5e'], default='h1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()

    model_path = f'models/{"h1/scene.xml" if args.model == "h1" else "ur5e/scene.xml"}'
    home = H1_HOME if args.model == 'h1' else _UR5E_HOME

    import os
    if not os.path.exists(model_path):
        raise SystemExit(f'Model not found: {model_path}. Run ./setup_model.sh first.')

    model = mujoco.MjModel.from_xml_path(model_path)
    data = mujoco.MjData(model)
    data.ctrl[:model.nu] = home[:model.nu]

    ws_thread = threading.Thread(target=_start_ws_thread, args=(args.port,), daemon=True)
    ws_thread.start()
    print(f'WebSocket server running on ws://localhost:{args.port}')
    print(f'Model: {args.model}. Waiting for Angular to connect...')

    state = _shared
    sim_tick = 0
    start_time = time.time()
    tick_interval_ms = 0.0

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            step_start = time.time()
            _process_commands(state)

            with _lock:
                status = state['status']

            t = time.time() - start_time

            if status == 'replaying':
                ticks = state['replay_ticks']
                total = state['total_ticks']
                if total > 0:
                    # Advance EEG tick proportionally to duration
                    dur = state['duration_ms']
                    tick_interval_ms = dur / total if total > 0 else 100.0
                    state['elapsed_ms'] += model.opt.timestep * 1000
                    new_idx = min(int(state['elapsed_ms'] / tick_interval_ms), total - 1)
                    state['tick'] = new_idx
                    eeg = ticks[new_idx]
                    state['eeg_tick'] = eeg
                    if new_idx >= total - 1:
                        state['status'] = 'idle'
                else:
                    eeg = None

                fatigue = (eeg or {}).get('fatigue') or 0.0
                in_flow = (eeg or {}).get('inFlow', False)

                if args.model == 'h1':
                    targets = h1_targets(t, fatigue=fatigue, in_flow=in_flow)
                else:
                    targets = _ur5e_targets(t)
                data.ctrl[:model.nu] = targets[:model.nu]

            elif status == 'paused':
                pass  # hold current ctrl

            else:  # idle
                data.ctrl[:model.nu] = home[:model.nu]

            mujoco.mj_step(model, data)
            viewer.sync()

            state['q'] = data.ctrl[:model.nu].tolist()
            sim_tick += 1

            if sim_tick % 10 == 0:
                _broadcast_q.put(_snap(state))

            elapsed = time.time() - step_start
            sleep = model.opt.timestep - elapsed
            if sleep > 0:
                time.sleep(sleep)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify it starts without errors**

```bash
cd ~/handwerk-robot-sim
source .venv/bin/activate
mjpython sim/ws_server.py --model h1
```

Expected: MuJoCo viewer opens, H1 stands at home pose, terminal prints:
```
WebSocket server running on ws://localhost:8765
Model: h1. Waiting for Angular to connect...
```
Close the viewer window to stop. If model XML missing, an error + exit is expected.

- [ ] **Step 3: Verify `replay` command via wscat or Python**

In a second terminal (with venv active):
```bash
pip install websockets  # if wscat not available
python - <<'EOF'
import asyncio, json, websockets

async def test():
    async with websockets.connect('ws://localhost:8765') as ws:
        payload = {
            'cmd': 'replay',
            'sessionId': 'test-1',
            'taskLabel': 'Plastering',
            'durationMs': 5000,
            'eegTicks': [
                {'focus': 0.7, 'calm': 0.6, 'load': 0.3, 'fatigue': 0.2, 'inFlow': False},
                {'focus': 0.8, 'calm': 0.7, 'load': 0.2, 'fatigue': 0.1, 'inFlow': True},
            ] * 50,
        }
        await ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        assert data['status'] in ('replaying', 'idle'), f"unexpected: {data}"
        print('OK:', data['status'], 'tick:', data['tick'])

asyncio.run(test())
EOF
```

Expected: `OK: replaying tick: 0` (or `idle` if 100 ticks already played through).

- [ ] **Step 4: Commit**

```bash
git add sim/ws_server.py
git commit -m "feat: MuJoCo H1 WebSocket server with EEG-modulated replay"
```

---

## Task 4: Angular — SimBridgeService (TDD)

**Files:**
- Create: `src/app/core/sim-bridge/sim-bridge.service.spec.ts`
- Create: `src/app/core/sim-bridge/sim-bridge.service.ts`

- [ ] **Step 1: Write the failing spec**

Create `src/app/core/sim-bridge/sim-bridge.service.spec.ts`:

```typescript
import { SimBridgeService, SimReplayPayload } from './sim-bridge.service';

function makeWsMock(): jasmine.SpyObj<WebSocket> & { readyState: number } {
  const ws = jasmine.createSpyObj<WebSocket>('WebSocket', ['send', 'close']);
  (ws as any).readyState = WebSocket.CONNECTING;
  return ws as any;
}

describe('SimBridgeService', () => {
  let service: SimBridgeService;
  let wsMock: ReturnType<typeof makeWsMock>;

  beforeEach(() => {
    wsMock = makeWsMock();
    spyOn(window, 'WebSocket').and.returnValue(wsMock as any);
    service = new SimBridgeService();
    service.connect();
    // Simulate open
    (wsMock as any).readyState = WebSocket.OPEN;
    wsMock.onopen?.({} as Event);
  });

  afterEach(() => service.disconnect());

  it('status is disconnected before connect', () => {
    const fresh = new SimBridgeService();
    expect(fresh.status()).toBe('disconnected');
  });

  it('status becomes idle on open + idle message', () => {
    wsMock.onmessage?.({ data: JSON.stringify({ status: 'idle', tick: 0, totalTicks: 0, q: [], eegTick: null }) } as MessageEvent);
    expect(service.status()).toBe('idle');
  });

  it('status becomes replaying on replaying message', () => {
    wsMock.onmessage?.({ data: JSON.stringify({ status: 'replaying', tick: 5, totalTicks: 100, q: [], eegTick: { focus: 0.8, calm: 0.6, load: 0.3, fatigue: 0.2, inFlow: true } }) } as MessageEvent);
    expect(service.status()).toBe('replaying');
    expect(service.tick()).toBe(5);
    expect(service.totalTicks()).toBe(100);
    expect(service.currentEegTick()?.inFlow).toBeTrue();
  });

  it('transferSession sends replay command with payload', () => {
    const payload: SimReplayPayload = {
      sessionId: 'sess-1',
      taskLabel: 'Plastering',
      durationMs: 5000,
      eegTicks: [{ focus: 0.7, calm: 0.6, load: 0.3, fatigue: 0.2, inFlow: false }],
    };
    service.transferSession(payload);
    expect(wsMock.send).toHaveBeenCalledOnceWith(JSON.stringify({ cmd: 'replay', ...payload }));
  });

  it('pause/resume/stop send correct commands', () => {
    service.pause();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'pause' }));
    service.resume();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'resume' }));
    service.stop();
    expect(wsMock.send).toHaveBeenCalledWith(JSON.stringify({ cmd: 'stop' }));
  });

  it('status becomes disconnected after WS close', () => {
    wsMock.onclose?.({} as CloseEvent);
    expect(service.status()).toBe('disconnected');
  });

  it('does not send when not open', () => {
    (wsMock as any).readyState = WebSocket.CLOSED;
    service.pause();
    expect(wsMock.send).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
ng test --include='**/sim-bridge.service.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: errors about `SimBridgeService` not found.

- [ ] **Step 3: Implement SimBridgeService**

Create `src/app/core/sim-bridge/sim-bridge.service.ts`:

```typescript
import { Injectable, signal } from '@angular/core';

export interface SimEegTick {
  focus: number;
  calm: number;
  load: number | null;
  fatigue: number | null;
  inFlow: boolean;
}

export interface SimReplayPayload {
  sessionId: string;
  taskLabel: string;
  durationMs: number;
  eegTicks: SimEegTick[];
}

export type SimStatus = 'disconnected' | 'idle' | 'replaying' | 'paused';

@Injectable({ providedIn: 'root' })
export class SimBridgeService {
  readonly status = signal<SimStatus>('disconnected');
  readonly tick = signal<number>(0);
  readonly totalTicks = signal<number>(0);
  readonly joints = signal<number[]>([]);
  readonly currentEegTick = signal<SimEegTick | null>(null);

  private ws: WebSocket | null = null;
  private retries = 0;
  private readonly maxRetries = 3;
  private readonly retryMs = 3000;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;

  connect(url = 'ws://localhost:8765'): void {
    this.clearRetry();
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      this.retries = 0;
    };

    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(ev.data as string);
        this.status.set(msg.status as SimStatus);
        this.tick.set(msg.tick ?? 0);
        this.totalTicks.set(msg.totalTicks ?? 0);
        this.joints.set(msg.q ?? []);
        this.currentEegTick.set(msg.eegTick ?? null);
      } catch { /* ignore malformed */ }
    };

    ws.onclose = () => {
      this.status.set('disconnected');
      if (this.retries < this.maxRetries) {
        this.retries++;
        this.retryTimer = setTimeout(() => this.connect(url), this.retryMs);
      }
    };
  }

  disconnect(): void {
    this.clearRetry();
    this.ws?.close();
    this.ws = null;
    this.status.set('disconnected');
  }

  transferSession(payload: SimReplayPayload): void {
    this.send({ cmd: 'replay', ...payload });
  }

  pause(): void { this.send({ cmd: 'pause' }); }
  resume(): void { this.send({ cmd: 'resume' }); }
  stop(): void { this.send({ cmd: 'stop' }); }
  reset(): void { this.send({ cmd: 'reset' }); }

  private send(msg: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
  }
}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
ng test --include='**/sim-bridge.service.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: all 7 specs pass.

- [ ] **Step 5: Verify build**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 6: Commit**

```bash
git add src/app/core/sim-bridge/
git commit -m "feat(sim-bridge): SimBridgeService with signals + reconnect"
```

---

## Task 5: Angular — SupabaseCaptureService.fetchEegTicks (TDD)

**Files:**
- Modify: `src/app/modules/capture/services/supabase-capture.service.spec.ts`
- Modify: `src/app/modules/capture/services/supabase-capture.service.ts`

- [ ] **Step 1: Add failing test**

Add this `describe` block to `supabase-capture.service.spec.ts` (inside the outer `describe('SupabaseCaptureService', ...)`, after the `deleteSession` block):

```typescript
  describe('fetchEegTicks', () => {
    it('returns mapped EEG ticks for a session', async () => {
      const { service, mockClient } = makeService();
      const rows = [
        { focus: 0.8, calm: 0.6, in_flow: true,  load: 0.3, fatigue: 0.2 },
        { focus: 0.7, calm: 0.5, in_flow: false, load: 0.4, fatigue: 0.3 },
      ];
      mockClient._fromResult.insert.and.returnValue(Promise.resolve({ data: rows, error: null }));
      // Override: from() returns a select-capable object for this test
      const selectResult = { eq: jasmine.createSpy('eq').and.returnValue({ order: jasmine.createSpy('order').and.returnValue(Promise.resolve({ data: rows, error: null })) }) };
      mockClient.from.and.returnValue({ select: jasmine.createSpy('select').and.returnValue(selectResult) } as any);

      const ticks = await service.fetchEegTicks('sess-1');

      expect(ticks).toEqual([
        { focus: 0.8, calm: 0.6, inFlow: true,  load: 0.3, fatigue: 0.2 },
        { focus: 0.7, calm: 0.5, inFlow: false, load: 0.4, fatigue: 0.3 },
      ]);
    });

    it('throws when Supabase returns an error', async () => {
      const { service, mockClient } = makeService();
      const errResult = { eq: jasmine.createSpy().and.returnValue({ order: jasmine.createSpy().and.returnValue(Promise.resolve({ data: null, error: { message: 'db error' } })) }) };
      mockClient.from.and.returnValue({ select: jasmine.createSpy().and.returnValue(errResult) } as any);

      await expectAsync(service.fetchEegTicks('sess-1')).toBeRejectedWithError('db error');
    });
  });
```

- [ ] **Step 2: Add `fetchEegTicks` to SupabaseCaptureService**

Add after `deleteSession` in `src/app/modules/capture/services/supabase-capture.service.ts`:

```typescript
  async fetchEegTicks(sessionId: string): Promise<{ focus: number; calm: number; inFlow: boolean; load: number | null; fatigue: number | null }[]> {
    const { data, error } = await this.supabase.client
      .from('eeg_ticks')
      .select('focus, calm, in_flow, load, fatigue')
      .eq('session_id', sessionId)
      .order('t', { ascending: true });
    if (error) throw new Error(error.message);
    return (data ?? []).map((r: any) => ({
      focus: r.focus,
      calm: r.calm,
      inFlow: r.in_flow,
      load: r.load,
      fatigue: r.fatigue,
    }));
  }
```

- [ ] **Step 3: Run tests**

```bash
ng test --include='**/supabase-capture.service.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: all specs pass (including the 2 new ones).

- [ ] **Step 4: Verify build**

```bash
ng build --configuration development 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
git add src/app/modules/capture/services/supabase-capture.service.ts \
        src/app/modules/capture/services/supabase-capture.service.spec.ts
git commit -m "feat(capture): add fetchEegTicks to SupabaseCaptureService"
```

---

## Task 6: Angular — Transfer button in CaptureSessionsTableComponent

**Files:**
- Modify: `src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts`

- [ ] **Step 1: Replace CaptureSessionsTableComponent**

Replace the full file content with:

```typescript
import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { toSignal } from '@angular/core/rxjs-interop';
import { CaptureHistoryService } from '../../services/capture-history.service';
import { SupabaseCaptureService } from '../../services/supabase-capture.service';
import { SimBridgeService } from '../../../../core/sim-bridge/sim-bridge.service';
import { CaptureRow } from '../../models/capture-session.model';
import { environment } from '../../../../environments/environment';

function formatDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
}

function formatDuration(created: string, ended: string | null): string {
  if (!ended) return '—';
  const ms = new Date(ended).getTime() - new Date(created).getTime();
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60).toString().padStart(2, '0');
  const s = (totalSec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function durationMs(created: string, ended: string | null): number {
  if (!ended) return 0;
  return new Date(ended).getTime() - new Date(created).getTime();
}

function storageUrl(path: string | null): string | null {
  if (!path) return null;
  return `${environment.supabase.url}/storage/v1/object/public/captures/${path}`;
}

@Component({
  selector: 'app-capture-sessions-table',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule],
  template: `
    <div class="tbl-wrap">
      @if (sessions().length === 0) {
        <div class="empty">
          <mat-icon class="empty__icon">history</mat-icon>
          <span class="empty__text">Noch keine Aufzeichnungen</span>
        </div>
      } @else {
        <table class="tbl">
          <thead>
            <tr>
              <th>Datum/Zeit</th>
              <th>Aufgabe</th>
              <th>Dauer</th>
              <th>Status</th>
              <th class="num">EEG Ticks</th>
              <th>Video</th>
              <th>IMU L</th>
              <th>IMU R</th>
              <th>EEG</th>
              <th>Sim</th>
            </tr>
          </thead>
          <tbody>
            @for (row of sessions(); track row.id) {
              <tr>
                <td>{{ formatDate(row.created_at) }}</td>
                <td>{{ row.task_label }}</td>
                <td class="num">{{ formatDuration(row.created_at, row.ended_at) }}</td>
                <td>
                  <span class="chip"
                        [class.chip--green]="row.status === 'complete'"
                        [class.chip--red]="row.status === 'failed'"
                        [class.chip--amber]="row.status === 'recording' || row.status === 'uploading'">
                    {{ row.status }}
                  </span>
                </td>
                <td class="num">{{ row.eeg_tick_count }}</td>
                <td>
                  @if (storageUrl(row.video_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.imu_left_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.imu_right_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (storageUrl(row.eeg_path); as url) {
                    <a class="file-link" [href]="url" target="_blank" rel="noopener">
                      <mat-icon>open_in_new</mat-icon>
                    </a>
                  } @else { <span>—</span> }
                </td>
                <td>
                  @if (simBridge.status() !== 'disconnected' && row.status === 'complete') {
                    <button mat-icon-button
                            class="transfer-btn"
                            [disabled]="simBridge.status() === 'replaying' || simBridge.status() === 'paused' || transferring() === row.id"
                            [title]="'Transfer to Sim'"
                            (click)="transfer(row)">
                      <mat-icon>play_circle</mat-icon>
                    </button>
                  } @else {
                    <span>—</span>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }
    .tbl-wrap { overflow-x: auto; }
    .tbl { width: 100%; border-collapse: collapse; }
    thead tr { background: #f4f7fb; }
    thead th {
      padding: 11px 16px;
      font-size: 11px; font-weight: 600; letter-spacing: .06em;
      text-transform: uppercase; color: #9aa8c4;
      text-align: left; white-space: nowrap;
      border-bottom: 1px solid #dde5f2;
    }
    thead th.num { text-align: right; }
    thead th:first-child { padding-left: 24px; }
    thead th:last-child  { padding-right: 24px; }
    tbody tr { border-bottom: 1px solid #eef2fa; transition: background .1s; }
    tbody tr:last-child { border-bottom: none; }
    tbody tr:hover { background: #f8fafd; }
    tbody td { padding: 11px 16px; white-space: nowrap; color: #18253f; font-size: 13px; }
    tbody td:first-child { padding-left: 24px; }
    tbody td:last-child  { padding-right: 24px; }
    .num { font-family: 'DM Mono', ui-monospace, monospace; color: #5a6a8e; text-align: right; }
    .chip {
      padding: 3px 9px; border-radius: 20px;
      font-size: 11px; font-weight: 600; display: inline-block;
      background: #eef2f9; color: #9aa8c4;
    }
    .chip--green { background: #e8f5ee; color: #2e7d32; }
    .chip--red   { background: #fce8e8; color: #c62828; }
    .chip--amber { background: #fff3e0; color: #e65100; }
    .file-link {
      color: #1976d2; display: inline-flex;
      align-items: center; gap: 2px; text-decoration: none; opacity: .8;
    }
    .file-link:hover { opacity: 1; }
    .file-link mat-icon { font-size: 14px; height: 14px; width: 14px; }
    .transfer-btn { color: #1976d2; }
    .transfer-btn[disabled] { color: #9aa8c4; }
    .empty {
      display: flex; flex-direction: column; align-items: center;
      gap: 10px; padding: 48px 24px; color: #9aa8c4;
    }
    .empty__icon { font-size: 36px; height: 36px; width: 36px; }
    .empty__text { font-size: 14px; }
  `],
})
export class CaptureSessionsTableComponent {
  private readonly historyService = inject(CaptureHistoryService);
  private readonly supabaseCapture = inject(SupabaseCaptureService);
  private readonly snackBar = inject(MatSnackBar);
  protected readonly simBridge = inject(SimBridgeService);
  protected readonly sessions = toSignal(this.historyService.sessions$, { initialValue: [] as CaptureRow[] });
  protected readonly transferring = signal<string | null>(null);

  protected readonly formatDate = formatDate;
  protected readonly formatDuration = formatDuration;

  protected storageUrl(path: string | null): string | null {
    return storageUrl(path);
  }

  protected async transfer(row: CaptureRow): Promise<void> {
    this.transferring.set(row.id);
    try {
      const eegTicks = await this.supabaseCapture.fetchEegTicks(row.id);
      this.simBridge.transferSession({
        sessionId: row.id,
        taskLabel: row.task_label,
        durationMs: durationMs(row.created_at, row.ended_at),
        eegTicks,
      });
    } catch {
      this.snackBar.open('Failed to fetch session data', 'Close', { duration: 3000, verticalPosition: 'top' });
    } finally {
      this.transferring.set(null);
    }
  }
}
```

- [ ] **Step 2: Verify build**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 3: Commit**

```bash
git add src/app/modules/capture/components/capture-sessions-table/capture-sessions-table.component.ts
git commit -m "feat(capture): add Transfer to Sim button in sessions table"
```

---

## Task 7: Angular — sim-control widget (TDD)

**Files:**
- Create: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts`
- Create: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`

- [ ] **Step 1: Write the failing spec**

Create `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts`:

```typescript
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { SimControlComponent } from './sim-control.component';
import { SimBridgeService } from '../../../../../core/sim-bridge/sim-bridge.service';
import { signal } from '@angular/core';

function makeBridgeSpy() {
  return {
    status: signal<any>('disconnected'),
    tick: signal(0),
    totalTicks: signal(0),
    currentEegTick: signal(null),
    connect: jasmine.createSpy('connect'),
    pause: jasmine.createSpy('pause'),
    resume: jasmine.createSpy('resume'),
    stop: jasmine.createSpy('stop'),
  };
}

describe('SimControlComponent', () => {
  let fixture: ComponentFixture<SimControlComponent>;
  let bridge: ReturnType<typeof makeBridgeSpy>;

  beforeEach(async () => {
    bridge = makeBridgeSpy();
    await TestBed.configureTestingModule({
      imports: [SimControlComponent],
      providers: [{ provide: SimBridgeService, useValue: bridge }],
    }).compileComponents();
    fixture = TestBed.createComponent(SimControlComponent);
    fixture.detectChanges();
  });

  it('shows offline state when disconnected', () => {
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Sim offline');
  });

  it('hides playback controls when idle', () => {
    bridge.status.set('idle');
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBe(0);
  });

  it('shows playback controls when replaying', () => {
    bridge.status.set('replaying');
    bridge.tick.set(10);
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBeGreaterThan(0);
  });

  it('shows playback controls when paused', () => {
    bridge.status.set('paused');
    fixture.detectChanges();
    const btns = fixture.nativeElement.querySelectorAll('[data-playback="true"]');
    expect(btns.length).toBeGreaterThan(0);
  });

  it('calls bridge.pause() on pause button click', () => {
    bridge.status.set('replaying');
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-pause"]');
    btn?.click();
    expect(bridge.pause).toHaveBeenCalled();
  });

  it('calls bridge.resume() on resume button click', () => {
    bridge.status.set('paused');
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-resume"]');
    btn?.click();
    expect(bridge.resume).toHaveBeenCalled();
  });

  it('calls bridge.stop() on stop button click', () => {
    bridge.status.set('replaying');
    bridge.totalTicks.set(100);
    fixture.detectChanges();
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-stop"]');
    btn?.click();
    expect(bridge.stop).toHaveBeenCalled();
  });

  it('calls bridge.connect() on reconnect button click', () => {
    const btn: HTMLButtonElement = fixture.nativeElement.querySelector('[data-testid="btn-reconnect"]');
    btn?.click();
    expect(bridge.connect).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
ng test --include='**/sim-control.component.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: errors about `SimControlComponent` not found.

- [ ] **Step 3: Create sim-control.component.ts**

Create `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`:

```typescript
import { Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { SimBridgeService } from '../../../../../core/sim-bridge/sim-bridge.service';

@Component({
  selector: 'app-sim-control',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatButtonModule],
  template: `
    <div class="sim">
      <div class="sim__header">
        <span class="sim__dot" [class.sim__dot--on]="status() !== 'disconnected'"></span>
        <span class="sim__title">Robot Sim</span>
      </div>

      @if (status() === 'disconnected') {
        <div class="sim__offline">
          <span>Sim offline</span>
          <button mat-stroked-button data-testid="btn-reconnect" (click)="bridge.connect()">
            Reconnect
          </button>
        </div>
      }

      @if (status() === 'idle') {
        <div class="sim__idle">Ready — transfer a session from the table below</div>
      }

      @if (status() === 'replaying' || status() === 'paused') {
        <div class="sim__progress-wrap">
          <div class="sim__progress-bar">
            <div class="sim__progress-fill" [style.width.%]="progressPct()"></div>
          </div>
          <span class="sim__tick">{{ bridge.tick() }} / {{ bridge.totalTicks() }}</span>
        </div>

        <div class="sim__eeg">
          @if (bridge.currentEegTick(); as t) {
            <span class="sim__metric" title="Focus">F <span class="sim__val">{{ (t.focus * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Calm">C <span class="sim__val">{{ (t.calm * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Load">L <span class="sim__val">{{ ((t.load ?? 0) * 100) | number:'1.0-0' }}</span></span>
            <span class="sim__metric" title="Fatigue">Fa <span class="sim__val">{{ ((t.fatigue ?? 0) * 100) | number:'1.0-0' }}</span></span>
            @if (t.inFlow) {
              <span class="sim__flow-badge">Flow</span>
            }
          }
        </div>

        <div class="sim__controls">
          @if (status() === 'replaying') {
            <button mat-icon-button data-playback="true" data-testid="btn-pause" (click)="bridge.pause()" title="Pause">
              <mat-icon>pause</mat-icon>
            </button>
          }
          @if (status() === 'paused') {
            <button mat-icon-button data-playback="true" data-testid="btn-resume" (click)="bridge.resume()" title="Resume">
              <mat-icon>play_arrow</mat-icon>
            </button>
          }
          <button mat-icon-button data-playback="true" data-testid="btn-stop" (click)="bridge.stop()" title="Stop">
            <mat-icon>stop</mat-icon>
          </button>
        </div>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }
    .sim { padding: 16px 20px; background: #fff; border-radius: 12px; border: 1px solid #dde5f2; }
    .sim__header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
    .sim__dot { width: 8px; height: 8px; border-radius: 50%; background: #cdd5e0; }
    .sim__dot--on { background: #2e7d32; }
    .sim__title { font-size: 12px; font-weight: 600; color: #9aa8c4; text-transform: uppercase; letter-spacing: .06em; }
    .sim__label { font-size: 12px; color: #18253f; margin-left: auto; }
    .sim__offline { display: flex; align-items: center; gap: 12px; color: #9aa8c4; font-size: 13px; }
    .sim__idle { font-size: 12px; color: #9aa8c4; }
    .sim__progress-wrap { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
    .sim__progress-bar { flex: 1; height: 4px; background: #eef2fa; border-radius: 2px; overflow: hidden; }
    .sim__progress-fill { height: 100%; background: #1976d2; border-radius: 2px; transition: width .2s; }
    .sim__tick { font-family: 'DM Mono', monospace; font-size: 11px; color: #9aa8c4; white-space: nowrap; }
    .sim__eeg { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
    .sim__metric { font-size: 11px; color: #9aa8c4; }
    .sim__val { font-family: 'DM Mono', monospace; color: #18253f; }
    .sim__flow-badge { font-size: 10px; font-weight: 700; background: #e8f5ee; color: #2e7d32; padding: 2px 7px; border-radius: 10px; }
    .sim__controls { display: flex; gap: 4px; }
  `],
})
export class SimControlComponent {
  protected readonly bridge = inject(SimBridgeService);
  protected readonly status = this.bridge.status;

  protected readonly progressPct = computed(() => {
    const total = this.bridge.totalTicks();
    return total > 0 ? Math.round((this.bridge.tick() / total) * 100) : 0;
  });
}
```

- [ ] **Step 4: Run tests**

```bash
ng test --include='**/sim-control.component.spec.ts' --watch=false --browsers=ChromeHeadless 2>&1 | tail -20
```

Expected: all 8 specs pass.

- [ ] **Step 5: Verify build**

```bash
ng build --configuration development 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts \
        src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.spec.ts
git commit -m "feat(dashboard): SimControlComponent widget with playback controls"
```

---

## Task 8: Angular — Wire sim-control into dashboard

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.ts`
- Modify: `src/app/shared/components/layout/dashboard-layout/dashboard.component.html` (if exists) or inline template

- [ ] **Step 1: Add SimControlComponent and SimBridgeService to DashboardComponent**

In `dashboard.component.ts`:

1. Add import at top:
```typescript
import { SimControlComponent } from './widgets/sim-control.component';
import { SimBridgeService } from '../../../../core/sim-bridge/sim-bridge.service';
```

2. Add `SimControlComponent` to the `imports` array in `@Component`.

3. Inject `SimBridgeService` in the class body and call `connect()` in `ngOnInit` (or constructor):
```typescript
private readonly simBridge = inject(SimBridgeService);

constructor() {
  // existing constructor body ...
  this.simBridge.connect();
}
```

- [ ] **Step 2: Add sim-control to the dashboard template**

In `dashboard.component.html` (or the inline template), add `<app-sim-control>` above `<app-capture-sessions-table>`:

```html
<app-sim-control></app-sim-control>
<app-capture-sessions-table></app-capture-sessions-table>
```

- [ ] **Step 3: Verify build**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: `Application bundle generation complete.`

- [ ] **Step 4: Manual smoke test**

```bash
# Terminal 1 — start sim
cd ~/handwerk-robot-sim && source .venv/bin/activate && mjpython sim/ws_server.py

# Terminal 2 — start Angular
cd ~/neurofeedback-lang-app && npm start
```

Open `http://localhost:4200/dashboard`. Expected:
- Sim control widget shows "Robot Sim" with green dot (connected)
- Status shows "Ready — transfer a session from the table below"
- Sessions table shows "Transfer to Sim" button (play_circle icon) on completed sessions
- Clicking Transfer causes MuJoCo H1 to start moving; dashboard shows tick progress + EEG values
- Pause/Stop buttons appear during replay

- [ ] **Step 5: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/dashboard.component.ts \
        src/app/shared/components/layout/dashboard-layout/dashboard.component.html
git commit -m "feat(dashboard): wire SimControlComponent + auto-connect on init"
```
