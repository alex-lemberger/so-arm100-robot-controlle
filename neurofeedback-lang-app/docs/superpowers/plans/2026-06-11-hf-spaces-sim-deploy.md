# HF Spaces Sim Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the MuJoCo H1 hand sim WebSocket server to Hugging Face Spaces (Docker) so the robot sim is publicly accessible for online showcases.

**Architecture:** Add `--headless` + `--host` flags to `ws_server.py` so it runs without a GUI on Linux. Wrap the sim loop in `_main_loop()` called with either `viewer.sync` (local dev) or a no-op (headless). Dockerize `handwerk-robot-sim` and push to a HF Space. Angular reads `environment.simWsUrl` to decide WS URL and whether to show "Launch Sim" vs "Connect".

**Tech Stack:** Python 3.11, MuJoCo, mink, websockets, Docker, Hugging Face Spaces (Docker SDK), Angular 19 environments + fileReplacements.

---

## File Map

| Repo | File | Action |
|---|---|---|
| `handwerk-robot-sim` | `sim/ws_server.py` | Modify — add `--headless`/`--host`, extract `_main_loop()` |
| `handwerk-robot-sim` | `Dockerfile` | Create |
| `handwerk-robot-sim` | `README.md` | Modify — prepend HF Space frontmatter |
| `neurofeedback-lang-app` | `src/app/environments/environment.ts` | Modify — add `simWsUrl: ''` |
| `neurofeedback-lang-app` | `src/app/environments/environment.prod.ts` | Create |
| `neurofeedback-lang-app` | `angular.json` | Modify — add `fileReplacements` to production config |
| `neurofeedback-lang-app` | `src/app/core/sim-bridge/sim-bridge.service.ts` | Modify — env-driven WS URL, add `isCloudSim` |
| `neurofeedback-lang-app` | `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts` | Modify — hide Launch Sim / show Connect in cloud mode |

---

## Task 1: Add `--headless` and `--host` to ws_server.py

**Repo:** `handwerk-robot-sim`  
**File:** `sim/ws_server.py`

The goal is to make the sim run without `mujoco.viewer.launch_passive` (which needs a display) by extracting the loop body into `_main_loop()` and branching on `args.headless`. Local dev behaviour is unchanged — omitting `--headless` still opens the viewer as before.

- [ ] **Step 1.1: Open `sim/ws_server.py` and locate the `argparse` block inside `main()`**

Find this block (around line 160 in `main()`):
```python
parser = argparse.ArgumentParser()
parser.add_argument('--model', choices=['h1', 'ur5e', 'h1_hand'], default='h1')
parser.add_argument('--port', type=int, default=8765)
args = parser.parse_args()
```

Replace with:
```python
parser = argparse.ArgumentParser()
parser.add_argument('--model', choices=['h1', 'ur5e', 'h1_hand'], default='h1')
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--headless', action='store_true',
                    help='Skip the MuJoCo viewer — required for headless cloud deploy')
parser.add_argument('--host', default='localhost',
                    help='WebSocket bind host (use 0.0.0.0 for cloud)')
args = parser.parse_args()
```

- [ ] **Step 1.2: Update the WebSocket bind host in `_ws_main()`**

Find this line inside `_ws_main()`:
```python
async with websockets.serve(_handler, 'localhost', port):
```

Replace with:
```python
async with websockets.serve(_handler, _ws_host, port):
```

Then find `_start_ws_thread`:
```python
def _start_ws_thread(port: int) -> None:
    asyncio.run(_ws_main(port))
```

Replace with:
```python
_ws_host: str = 'localhost'  # overwritten in main() before thread starts

def _start_ws_thread(port: int) -> None:
    asyncio.run(_ws_main(port))
```

And add `global _ws_host` assignment inside `main()`, right after `args = parser.parse_args()`:
```python
global _ws_host
_ws_host = args.host
```

- [ ] **Step 1.3: Add the `_main_loop()` function**

Add the following function **immediately before the `def main():` line**:

```python
def _main_loop(
    state: dict,
    model: mujoco.MjModel,
    data: mujoco.MjData,
    root_qpos: np.ndarray,
    use_pd: bool,
    use_h1_hand: bool,
    sync_fn,
    running_fn,
) -> None:
    """Core sim loop. sync_fn=viewer.sync (local) or lambda:None (headless)."""
    sim_tick = 0
    start_time = time.time()

    while running_fn():
        step_start = time.time()
        _process_commands(state, model, root_qpos)

        with _lock:
            status = state['status']

        t = time.time() - start_time
        eeg = None
        if status == 'replaying':
            with _lock:
                ticks = state['replay_ticks']
                total = state['total_ticks']
                if total > 0:
                    dur = state['duration_ms']
                    tick_interval_ms = dur / total if total > 0 else 100.0
                    state['elapsed_ms'] += model.opt.timestep * 1000
                    new_idx = min(int(state['elapsed_ms'] / tick_interval_ms), total - 1)
                    state['tick'] = new_idx
                    eeg = ticks[new_idx]
                    state['eeg_tick'] = eeg
                    if new_idx >= total - 1:
                        state['status'] = 'idle'
                        eeg = None

        if use_h1_hand:
            if status == 'replaying' and eeg is not None:
                fatigue = eeg.get('fatigue')
                in_flow = eeg.get('inFlow', False)
                targets = h1_hand_targets(t, fatigue=fatigue, in_flow=in_flow)
                data.ctrl[:model.nu] = targets[:model.nu]
            elif status == 'idle':
                data.ctrl[:model.nu] = _H1_HAND_HOME[:model.nu]
            mujoco.mj_step(model, data)

        elif status == 'replaying':
            if eeg is not None:
                fatigue = eeg.get('fatigue') or 0.0
                in_flow = eeg.get('inFlow', False)
                if not use_pd:
                    targets = _ur5e_targets(t)
            if use_pd:
                if eeg is not None:
                    speed = 1.0 - fatigue * (1.0 - MIN_SPEED)
                    with _lock:
                        state['wp_progress'] += model.opt.timestep * speed / _SECS_PER_WP
                        wp_idx = min(int(state['wp_progress']), len(_WALL_WAYPOINTS) - 1)
                        solver: H1IkSolver = state['ik_solver']

                    solver.sync_from(data)
                    solver.set_target(np.array(_WALL_WAYPOINTS[wp_idx]))
                    solver.step(model.opt.timestep)
                    solver.sync_to(data)

                    torso_yaw = h1_targets(t, fatigue=fatigue, in_flow=in_flow)[10]
                    data.qpos[7 + 10] = torso_yaw

                    with _lock:
                        _logged_wp = state.get('_logged_wp', -1)
                    if wp_idx != _logged_wp:
                        mujoco.mj_forward(model, data)
                        body_id = mujoco.mj_name2id(
                            model, mujoco.mjtObj.mjOBJ_BODY, 'right_elbow_link'
                        )
                        err = np.linalg.norm(
                            data.xpos[body_id] - np.array(_WALL_WAYPOINTS[wp_idx])
                        )
                        print(f'[ik] wp {wp_idx}/{len(_WALL_WAYPOINTS)} err={err:.4f}m  arm_q={data.qpos[22:26].round(3).tolist()}')
                        with _lock:
                            state['_logged_wp'] = wp_idx

                mujoco.mj_forward(model, data)
            else:
                data.ctrl[:model.nu] = targets[:model.nu] if eeg is not None else _UR5E_HOME[:model.nu]
                mujoco.mj_step(model, data)

        elif status == 'paused':
            if use_pd:
                mujoco.mj_forward(model, data)
            else:
                mujoco.mj_step(model, data)

        else:  # idle
            if use_pd:
                mujoco.mj_resetDataKeyframe(model, data, 0)
                mujoco.mj_forward(model, data)
            else:
                data.ctrl[:model.nu] = _UR5E_HOME[:model.nu]
                mujoco.mj_step(model, data)

        sync_fn()

        with _lock:
            state['q'] = data.ctrl[:model.nu].tolist()
        sim_tick += 1

        if sim_tick % 10 == 0:
            _broadcast_q.put(_snap(state))

        elapsed = time.time() - step_start
        sleep_time = model.opt.timestep - elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)
```

- [ ] **Step 1.4: Replace the viewer block at the end of `main()` with headless/viewer branching**

Find this block at the end of `main()` (the `with mujoco.viewer.launch_passive(...)` section):

```python
    if use_pd:
        mujoco.mj_forward(model, data)  # populate derived quantities before viewer opens

    state = _shared
    sim_tick = 0
    start_time = time.time()
    prev_status = 'idle'

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            step_start = time.time()
            _process_commands(state, model, _h1_root_qpos)
            # ... (entire loop body)
```

Replace that entire block (from `if use_pd:` down to the end of `main()`) with:

```python
    if use_pd:
        mujoco.mj_forward(model, data)  # populate derived quantities

    state = _shared

    if args.headless:
        print('Headless mode — no viewer. Ctrl-C to stop.')
        _main_loop(state, model, data, _h1_root_qpos, use_pd, use_h1_hand,
                   sync_fn=lambda: None, running_fn=lambda: True)
    else:
        with mujoco.viewer.launch_passive(model, data) as viewer:
            _main_loop(state, model, data, _h1_root_qpos, use_pd, use_h1_hand,
                       sync_fn=viewer.sync, running_fn=viewer.is_running)
```

- [ ] **Step 1.5: Verify the refactor compiles and runs headlessly**

In `~/handwerk-robot-sim`, run:
```bash
source .venv/bin/activate
python3 -c "import sim.ws_server; print('import OK')"
```
Expected output: `import OK` (no errors)

Then start the headless server in background and confirm it accepts a WS connection:
```bash
mjpython sim/ws_server.py --model h1_hand --headless --port 8766 &
sleep 2
python3 -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:8766') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        print('Got:', json.loads(msg)['status'])
asyncio.run(test())
"
kill %1
```
Expected output: `Got: idle`

- [ ] **Step 1.6: Verify local viewer still works (smoke test only — don't leave running)**

```bash
mjpython sim/ws_server.py --model h1_hand --port 8765
```
Expected: MuJoCo viewer window opens, terminal prints `WebSocket server running on ws://localhost:8765`. Close the window immediately after confirming.

- [ ] **Step 1.7: Commit**

```bash
git add sim/ws_server.py
git commit -m "feat(sim): add --headless and --host flags; extract _main_loop()"
```

---

## Task 2: Dockerize handwerk-robot-sim for HF Spaces

**Repo:** `handwerk-robot-sim`  
**Files:** `Dockerfile` (create), `README.md` (modify)

- [ ] **Step 2.1: Prepend HF Space frontmatter to `README.md`**

Open `README.md`. The current content starts with `# Handwerk Robot Sim — v1`. Prepend exactly this block at the very top (before the `#` heading), including the blank line after the closing `---`:

```
---
sdk: docker
app_port: 7860
---

```

So the file now starts:
```
---
sdk: docker
app_port: 7860
---

# Handwerk Robot Sim — v1
...
```

- [ ] **Step 2.2: Create `Dockerfile` in the repo root (`~/handwerk-robot-sim/Dockerfile`)**

```dockerfile
FROM python:3.11-slim

# GL libraries needed by mujoco package at import time even in headless mode
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY models/ models/
COPY sim/ sim/

EXPOSE 7860

CMD ["python3", "sim/ws_server.py", \
     "--model", "h1_hand", \
     "--headless", \
     "--host", "0.0.0.0", \
     "--port", "7860"]
```

- [ ] **Step 2.3: Verify the Dockerfile builds locally (Docker must be installed)**

```bash
cd ~/handwerk-robot-sim
docker build -t handwerk-sim-test .
```

Expected: build completes with `Successfully built ...`. This will take 5–10 minutes on first run (downloading Python image + installing mujoco/mink).

If `pin` (pinocchio) fails to install, add this line to `requirements.txt` before `mink`:
```
pin>=2.7.0
```
Then re-run `docker build`.

- [ ] **Step 2.4: Verify the container starts and accepts a WebSocket connection**

In one terminal:
```bash
docker run --rm -p 7860:7860 handwerk-sim-test
```
Expected output (within 5s):
```
WebSocket server running on ws://0.0.0.0:7860
Model: h1_hand. Waiting for Angular to connect...
Headless mode — no viewer. Ctrl-C to stop.
```

In a second terminal:
```bash
python3 -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:7860') as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print('Status:', json.loads(msg)['status'])
asyncio.run(test())
"
```
Expected: `Status: idle`

Stop the container with Ctrl-C.

- [ ] **Step 2.5: Commit**

```bash
git add Dockerfile README.md
git commit -m "feat(deploy): Dockerfile + HF Spaces config for headless sim"
```

---

## Task 3: Add `simWsUrl` to Angular environments

**Repo:** `neurofeedback-lang-app`  
**Files:** `src/app/environments/environment.ts`, `src/app/environments/environment.prod.ts` (create), `angular.json`

- [ ] **Step 3.1: Add `simWsUrl` field to `environment.ts`**

Open `src/app/environments/environment.ts`. The current last field before `};` is:
```typescript
  collections: {
    metrics: 'metrics',
    sessions: 'sessions',
    correlation: 'correlation',
    exercises: 'exercises',
  },
};
```

Add `simWsUrl` as the last field (before `};`):
```typescript
  collections: {
    metrics: 'metrics',
    sessions: 'sessions',
    correlation: 'correlation',
    exercises: 'exercises',
  },
  simWsUrl: '',
};
```

- [ ] **Step 3.2: Create `src/app/environments/environment.prod.ts`**

Create the file with all the same fields as `environment.ts`, but `production: true` and `simWsUrl` set to a placeholder. You will update the URL in Task 6 once the HF Space is live:

```typescript
export const environment = {
  production: true,
  useMockData: true,
  device: 'mock' as 'mock' | 'neurosity' | 'muse',
  engagementTier: 'standard' as 'standard' | 'premium',
  wordpressApiUrl: 'https://your-wordpress-site.com/wp-json/wp/v2/posts',
  neurosityDeviceId: 'YOUR_DEVICE_ID',
  supabase: {
    url: 'https://hmiwxefpxbvjstsdywxb.supabase.co',
    anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtaXd4ZWZweGJ2anN0c2R5d3hiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3ODY0NTksImV4cCI6MjA5NjM2MjQ1OX0.COhFY0HVtUKU3lFd8PBpF5sLckD4jZS1qPpbVTwzJ6M',
  },
  shopId: 'pilot-shop-01',
  collections: {
    metrics: 'metrics',
    sessions: 'sessions',
    correlation: 'correlation',
    exercises: 'exercises',
  },
  simWsUrl: 'PLACEHOLDER_FILL_IN_TASK_6',
};
```

- [ ] **Step 3.3: Add `fileReplacements` to the production build config in `angular.json`**

Open `angular.json`. Find the `"production"` key inside `projects > neurofeedback-lang-app > architect > build > configurations`:

```json
"production": {
  "budgets": [
```

Replace with (add `fileReplacements` before `budgets`):

```json
"production": {
  "fileReplacements": [
    {
      "replace": "src/app/environments/environment.ts",
      "with": "src/app/environments/environment.prod.ts"
    }
  ],
  "budgets": [
```

- [ ] **Step 3.4: Verify the production build compiles**

```bash
cd ~/neurofeedback-lang-app
ng build --configuration production 2>&1 | tail -5
```

Expected: build completes, last lines show something like:
```
✓ Building...
Application bundle generation complete.
```
No TypeScript errors.

- [ ] **Step 3.5: Commit**

```bash
git add src/app/environments/environment.ts src/app/environments/environment.prod.ts angular.json
git commit -m "feat(env): add simWsUrl field + production environment file"
```

---

## Task 4: Update `SimBridgeService` to use env-driven WS URL

**Repo:** `neurofeedback-lang-app`  
**File:** `src/app/core/sim-bridge/sim-bridge.service.ts`

- [ ] **Step 4.1: Add environment import at the top of the file**

Open `src/app/core/sim-bridge/sim-bridge.service.ts`. After the existing `import` lines, add:

```typescript
import { environment } from '../../environments/environment';
```

Confirm the relative path: `sim-bridge.service.ts` is at `src/app/core/sim-bridge/`, and `environment.ts` is at `src/app/environments/`. So the path is `../../environments/environment`. Adjust if different.

- [ ] **Step 4.2: Add `isCloudSim` property to the service class**

Inside the `SimBridgeService` class, after the existing signal declarations, add:

```typescript
readonly isCloudSim: boolean = environment.simWsUrl !== '';
```

- [ ] **Step 4.3: Update `connect()` to default to the env URL**

Find the current `connect()` method signature:
```typescript
connect(url = 'ws://localhost:8765'): void {
```

Replace with:
```typescript
connect(url = environment.simWsUrl || 'ws://localhost:8765'): void {
```

- [ ] **Step 4.4: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 4.5: Commit**

```bash
git add src/app/core/sim-bridge/sim-bridge.service.ts
git commit -m "feat(sim-bridge): env-driven WS URL + isCloudSim flag"
```

---

## Task 5: Update `SimControlComponent` for cloud-aware UI

**Repo:** `neurofeedback-lang-app`  
**File:** `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`

When `isCloudSim` is true, the "Launch Sim" button (which spawns a local Node.js process) is hidden. A "Connect" button appears instead that calls `bridge.connect()` directly.

- [ ] **Step 5.1: Add `isCloudSim` to the component class**

Open the file. In the class body, after the existing injections/signals:
```typescript
export class SimControlComponent {
  protected readonly bridge = inject(SimBridgeService);
  private readonly snackBar = inject(MatSnackBar);
  protected readonly status = this.bridge.status;
```

Add:
```typescript
  protected readonly isCloudSim = this.bridge.isCloudSim;
```

- [ ] **Step 5.2: Update the `disconnected` template block**

Find the existing disconnected block in the `template`:
```html
@if (status() === 'disconnected') {
  <div class="sim__offline">
    <span>{{ bridge.launching() ? 'Starting…' : 'Sim offline' }}</span>
    <button mat-stroked-button data-testid="btn-launch"
            [disabled]="bridge.launching()"
            (click)="launchSim()">
      {{ bridge.launching() ? '…' : 'Launch Sim' }}
    </button>
  </div>
}
```

Replace with:
```html
@if (status() === 'disconnected') {
  <div class="sim__offline">
    <span>Sim offline</span>
    @if (!isCloudSim) {
      <button mat-stroked-button data-testid="btn-launch"
              [disabled]="bridge.launching()"
              (click)="launchSim()">
        {{ bridge.launching() ? '…' : 'Launch Sim' }}
      </button>
    }
    @if (isCloudSim) {
      <button mat-stroked-button data-testid="btn-connect"
              (click)="bridge.connect()">
        Connect
      </button>
    }
  </div>
}
```

- [ ] **Step 5.3: Verify compilation**

```bash
ng build --configuration development 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 5.4: Verify prod build still works**

```bash
ng build --configuration production 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 5.5: Commit**

```bash
git add src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
git commit -m "feat(sim-control): show Connect button in cloud mode, hide Launch Sim"
```

---

## Task 6: Create HF Space and deploy

This task requires a Hugging Face account. Replace `YOUR_HF_USERNAME` throughout with your actual HF username.

- [ ] **Step 6.1: Create the HF Space (manual — do this in a browser)**

1. Go to https://huggingface.co/new-space
2. Fill in:
   - **Owner:** your username
   - **Space name:** `handwerk-sim`
   - **License:** MIT
   - **SDK:** Docker
   - **Visibility:** Public
3. Click "Create Space". HF will show an empty space with a git URL.

The space git URL will be: `https://huggingface.co/spaces/YOUR_HF_USERNAME/handwerk-sim`

- [ ] **Step 6.2: Add the HF Space as a git remote in `handwerk-robot-sim`**

```bash
cd ~/handwerk-robot-sim
git remote add space https://huggingface.co/spaces/YOUR_HF_USERNAME/handwerk-sim
git remote -v
```

Expected output includes:
```
space  https://huggingface.co/spaces/YOUR_HF_USERNAME/handwerk-sim (fetch)
space  https://huggingface.co/spaces/YOUR_HF_USERNAME/handwerk-sim (push)
```

- [ ] **Step 6.3: Push to HF Space**

```bash
git push space main
```

If HF requires authentication, use your HF username and an access token (generate at https://huggingface.co/settings/tokens — select "Write" scope). When prompted:
- Username: your HF username
- Password: your HF access token (not your account password)

HF will start building the Docker image automatically. Watch the build log at:
`https://huggingface.co/spaces/YOUR_HF_USERNAME/handwerk-sim`

Build takes 5–10 minutes. Wait until the space shows "Running" status (green dot).

- [ ] **Step 6.4: Confirm the deployed WS server is reachable**

```bash
python3 -c "
import asyncio, websockets, json
async def test():
    url = 'wss://YOUR_HF_USERNAME-handwerk-sim.hf.space'
    print(f'Connecting to {url} ...')
    async with websockets.connect(url) as ws:
        msg = await asyncio.wait_for(ws.recv(), timeout=30)
        print('Status:', json.loads(msg)['status'])
asyncio.run(test())
"
```

Expected (may take ~30s on cold start): `Status: idle`

Note the exact WS URL shown — it follows the pattern `wss://USERNAME-SPACENAME.hf.space`. If the space name contains underscores, HF converts them to hyphens.

- [ ] **Step 6.5: Update `environment.prod.ts` with the real HF URL**

Open `src/app/environments/environment.prod.ts`. Replace the placeholder:
```typescript
simWsUrl: 'PLACEHOLDER_FILL_IN_TASK_6',
```
With the real URL (use `wss://` not `ws://` — HF Spaces always use TLS):
```typescript
simWsUrl: 'wss://YOUR_HF_USERNAME-handwerk-sim.hf.space',
```

- [ ] **Step 6.6: Rebuild Angular production to embed the real URL**

```bash
cd ~/neurofeedback-lang-app
ng build --configuration production 2>&1 | tail -5
```

Expected: clean build, no errors.

- [ ] **Step 6.7: Commit the URL update**

```bash
git add src/app/environments/environment.prod.ts
git commit -m "feat(env): set live HF Spaces WS URL in production environment"
```

---

## Self-Review Checklist (completed inline)

- **Spec coverage:** All 8 files from the spec file map are covered. `--headless`/`--host` ✓. Dockerfile ✓. HF frontmatter ✓. `simWsUrl` in both env files ✓. `fileReplacements` in `angular.json` ✓. `isCloudSim` + `connect()` default ✓. Launch Sim hidden / Connect shown ✓.
- **Placeholder scan:** One intentional placeholder `PLACEHOLDER_FILL_IN_TASK_6` and `YOUR_HF_USERNAME` — both resolved in Task 6 steps. No other TBDs.
- **Type consistency:** `isCloudSim: boolean` defined in Task 4, consumed in Task 5. `environment.simWsUrl: string` added in Task 3, consumed in Task 4. All consistent.
- **`mjpython` vs `python3`:** `mjpython` is macOS-only. Dockerfile uses `python3` throughout. Local dev still uses `mjpython`. ✓
- **WS bind order:** `_ws_host` global is set before `ws_thread.start()` in `main()`, so the thread reads the correct host. ✓
