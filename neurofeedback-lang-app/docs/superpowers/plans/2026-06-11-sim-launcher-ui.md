# Sim Launcher + Play Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Launch Sim" button that spawns the MuJoCo WebSocket server via a local Node.js HTTP launcher, and a "Play Demo" button that starts a 30-second synthetic EEG replay — without touching a terminal.

**Architecture:** A tiny Node.js HTTP server (`tools/sim-launcher.js`) runs on port 3001 alongside Angular. It exposes `POST /sim/start` (spawns `mjpython` subprocess) and `POST /sim/stop` (kills it). `SimBridgeService` adds `launchSim()` / `stopSim()` methods that call the launcher then auto-connect the WebSocket after 2 seconds. `SimControlComponent` replaces the "Reconnect" button with "Launch Sim" (disconnected state) and adds "Play Demo" (idle state) that sends 60 synthetic EEG ticks over 30 seconds.

**Tech Stack:** Node.js built-in `http` + `child_process` (no extra packages for launcher), Angular 19 signals, `concurrently` (new devDep), `MatSnackBar` for error display.

---

## File Map

| File | Action | What it does |
|------|--------|-------------|
| `tools/sim-launcher.js` | **Create** | HTTP server that spawns/kills the mjpython process |
| `package.json` | **Modify** | Add `sim-launcher` + `dev` scripts; add `concurrently` devDep |
| `src/app/core/sim-bridge/sim-bridge.service.ts` | **Modify** | Add `_launching` signal + `launchSim()` + `stopSim()` |
| `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts` | **Modify** | Replace Reconnect with Launch Sim; add Play Demo + `buildDemoTicks()` |

---

## Task 1: Create the Node.js Launcher Server

**Files:**
- Create: `tools/sim-launcher.js`

This server runs on `http://localhost:3001`. Angular calls it to start/stop the Python sim. It uses only Node.js built-ins — no `npm install` needed for this task.

- [ ] **Step 1.1: Confirm `tools/` directory does not yet exist**

```bash
ls /Users/alexanderlemberger/neurofeedback-lang-app/tools 2>&1
```

Expected output: `ls: /Users/alexanderlemberger/neurofeedback-lang-app/tools: No such file or directory`

If it exists, skip step 1.2 and go to step 1.3.

- [ ] **Step 1.2: Create the `tools/` directory**

```bash
mkdir /Users/alexanderlemberger/neurofeedback-lang-app/tools
```

No output expected.

- [ ] **Step 1.3: Create `tools/sim-launcher.js`**

Create the file `/Users/alexanderlemberger/neurofeedback-lang-app/tools/sim-launcher.js` with exactly this content:

```js
'use strict';
const http = require('http');
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

const PORT = Number(process.env.SIM_LAUNCHER_PORT ?? 3001);
const SIM_DIR = path.join(os.homedir(), 'handwerk-robot-sim');
const MJPYTHON = path.join(SIM_DIR, '.venv/bin/mjpython');

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': 'http://localhost:4200',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Content-Type': 'application/json',
};

let simProc = null;

function killSim() {
  if (simProc) {
    simProc.kill('SIGTERM');
    simProc = null;
  }
}

const server = http.createServer((req, res) => {
  Object.entries(CORS_HEADERS).forEach(([k, v]) => res.setHeader(k, v));

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  if (req.method === 'POST' && req.url === '/sim/start') {
    killSim();
    try {
      simProc = spawn(MJPYTHON, ['sim/ws_server.py', '--model', 'h1'], {
        cwd: SIM_DIR,
        stdio: 'inherit',
      });
      simProc.on('exit', () => { simProc = null; });
      res.writeHead(200);
      res.end(JSON.stringify({ ok: true, pid: simProc.pid }));
    } catch (err) {
      res.writeHead(500);
      res.end(JSON.stringify({ ok: false, error: String(err.message) }));
    }
    return;
  }

  if (req.method === 'POST' && req.url === '/sim/stop') {
    killSim();
    res.writeHead(200);
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'Not found' }));
});

process.on('exit', killSim);
process.on('SIGINT', () => { killSim(); process.exit(0); });
process.on('SIGTERM', () => { killSim(); process.exit(0); });

server.listen(PORT, () => console.log(`[sim-launcher] http://localhost:${PORT}`));
```

- [ ] **Step 1.4: Verify the file exists and has the right size**

```bash
wc -l /Users/alexanderlemberger/neurofeedback-lang-app/tools/sim-launcher.js
```

Expected: `65` (approximately — line count should be in the 60–70 range)

- [ ] **Step 1.5: Verify launcher starts without error**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
node tools/sim-launcher.js &
SIM_LAUNCHER_PID=$!
sleep 1
echo "Launcher PID: $SIM_LAUNCHER_PID"
```

Expected output in terminal:
```
[sim-launcher] http://localhost:3001
Launcher PID: <some number>
```

- [ ] **Step 1.6: Test the `/sim/stop` endpoint (safe — doesn't spawn anything)**

```bash
curl -s -X POST http://localhost:3001/sim/stop
```

Expected: `{"ok":true}`

- [ ] **Step 1.7: Stop the background launcher**

```bash
kill $SIM_LAUNCHER_PID 2>/dev/null; sleep 1
curl -s http://localhost:3001/sim/stop 2>&1 | head -3
```

Expected: connection refused error (launcher is down). This confirms it was actually running before.

---

## Task 2: Add npm Scripts

**Files:**
- Modify: `package.json`

- [ ] **Step 2.1: Install `concurrently`**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
npm install --save-dev concurrently
```

Expected last line of output: something like `added 5 packages` or similar. No errors.

- [ ] **Step 2.2: Confirm `concurrently` is now in `package.json`**

```bash
grep "concurrently" /Users/alexanderlemberger/neurofeedback-lang-app/package.json
```

Expected: `"concurrently": "^<version>"` — any version is fine.

- [ ] **Step 2.3: Add two scripts to `package.json`**

Open `package.json`. Find this exact block (lines 4–11):

```json
  "scripts": {
    "ng": "ng",
    "start": "ng serve",
    "build": "ng build",
    "watch": "ng build --watch --configuration development",
    "test": "ng test",
    "check:citations": "node scripts/check-citations.mjs"
  },
```

Replace it with:

```json
  "scripts": {
    "ng": "ng",
    "start": "ng serve",
    "build": "ng build",
    "watch": "ng build --watch --configuration development",
    "test": "ng test",
    "check:citations": "node scripts/check-citations.mjs",
    "sim-launcher": "node tools/sim-launcher.js",
    "dev": "concurrently --names \"ng,sim\" --prefix-colors \"blue,green\" \"npm start\" \"npm run sim-launcher\""
  },
```

- [ ] **Step 2.4: Verify the scripts were added correctly**

```bash
node -e "const p=require('./package.json'); console.log(Object.keys(p.scripts).join(', '))"
```

Expected output:
```
ng, start, build, watch, test, check:citations, sim-launcher, dev
```

- [ ] **Step 2.5: Verify `npm run sim-launcher` works**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
npm run sim-launcher &
SIM_PID=$!
sleep 1
curl -s -X POST http://localhost:3001/sim/stop
kill $SIM_PID 2>/dev/null
```

Expected curl output: `{"ok":true}`

---

## Task 3: Add `launchSim()` and `stopSim()` to SimBridgeService

**Files:**
- Modify: `src/app/core/sim-bridge/sim-bridge.service.ts`

Current file has 122 lines. Read it before making changes:

```bash
cat -n /Users/alexanderlemberger/neurofeedback-lang-app/src/app/core/sim-bridge/sim-bridge.service.ts | head -40
```

Expected: you see the `@Injectable` class with `private readonly _snap = signal<SimSnapshot>(INITIAL);` on line 35.

- [ ] **Step 3.1: Add `_launching` signal on the line after `_snap`**

Find this exact line in `sim-bridge.service.ts` (line 35):

```ts
  private readonly _snap = signal<SimSnapshot>(INITIAL);
```

Replace it with:

```ts
  private readonly _snap = signal<SimSnapshot>(INITIAL);
  private readonly _launching = signal<boolean>(false);
  readonly launching = computed(() => this._launching());
```

- [ ] **Step 3.2: Verify the signal was added**

```bash
grep -n "_launching\|launching" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/core/sim-bridge/sim-bridge.service.ts
```

Expected output (line numbers may vary slightly):
```
35:  private readonly _snap = signal<SimSnapshot>(INITIAL);
36:  private readonly _launching = signal<boolean>(false);
37:  readonly launching = computed(() => this._launching());
```

- [ ] **Step 3.3: Add `launchSim()` method after the `connect()` method**

Find this exact block in `sim-bridge.service.ts` (ends around line 88):

```ts
  disconnect(): void {
```

Insert the following TWO new methods immediately BEFORE `disconnect()`:

```ts
  async launchSim(launcherPort = 3001): Promise<void> {
    this._launching.set(true);
    try {
      const res = await fetch(`http://localhost:${launcherPort}/sim/start`, { method: 'POST' });
      const body = await res.json() as { ok: boolean; error?: string };
      if (!body.ok) throw new Error(body.error ?? 'Launcher returned error');
      setTimeout(() => this.connect(), 2000);
    } finally {
      this._launching.set(false);
    }
  }

  stopSim(launcherPort = 3001): void {
    fetch(`http://localhost:${launcherPort}/sim/stop`, { method: 'POST' }).catch(() => {});
  }

  disconnect(): void {
```

(Include the `disconnect(): void {` line in the replacement so the edit is unambiguous.)

- [ ] **Step 3.4: Verify methods were added**

```bash
grep -n "launchSim\|stopSim\|disconnect" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/core/sim-bridge/sim-bridge.service.ts
```

Expected (line numbers approximate):
```
89:  async launchSim(launcherPort = 3001): Promise<void> {
100:  stopSim(launcherPort = 3001): void {
104:  disconnect(): void {
```

- [ ] **Step 3.5: TypeScript compile check**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
ng build --configuration development 2>&1 | tail -8
```

Expected: last line contains `Application bundle generation complete` with no `ERROR` lines above it.

If there are TypeScript errors, read the full error message carefully and fix the indicated line in `sim-bridge.service.ts` before proceeding.

---

## Task 4: Update SimControlComponent — Launch Sim Button

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`

Current file is 98 lines. This task only changes the disconnected-state template block and adds `MatSnackBarModule` + snackbar injection + `launchSim()` method.

- [ ] **Step 4.1: Add `MatSnackBarModule` to the import statement**

Find this exact line near the top of `sim-control.component.ts` (line 4):

```ts
import { MatButtonModule } from '@angular/material/button';
```

Replace it with:

```ts
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
```

- [ ] **Step 4.2: Add `MatSnackBarModule` to the component `imports` array**

Find this exact line in the `@Component` decorator:

```ts
  imports: [CommonModule, MatIconModule, MatButtonModule],
```

Replace it with:

```ts
  imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule],
```

- [ ] **Step 4.3: Verify the two import changes**

```bash
grep -n "MatSnackBar\|imports:" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
```

Expected:
```
5:import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
10:  imports: [CommonModule, MatIconModule, MatButtonModule, MatSnackBarModule],
```

- [ ] **Step 4.4: Add `snackBar` injection to the class body**

Find this exact line in the class body (around line 89):

```ts
  protected readonly bridge = inject(SimBridgeService);
```

Replace it with:

```ts
  protected readonly bridge = inject(SimBridgeService);
  private readonly snackBar = inject(MatSnackBar);
```

- [ ] **Step 4.5: Add `launchSim()` method to the class**

Find this exact method at the bottom of the class:

```ts
  protected readonly progressPct = computed(() => {
```

Insert the following new method BEFORE `progressPct`:

```ts
  protected async launchSim(): Promise<void> {
    try {
      await this.bridge.launchSim();
    } catch {
      this.snackBar.open(
        'Launcher not running — start with: npm run dev',
        'OK',
        { duration: 6000 },
      );
    }
  }

  protected readonly progressPct = computed(() => {
```

(Include the `protected readonly progressPct = computed(() => {` line so the edit is unambiguous.)

- [ ] **Step 4.6: Replace the disconnected-state template block**

Find this exact block in the template:

```html
      @if (status() === 'disconnected') {
        <div class="sim__offline">
          <span>Sim offline</span>
          <button mat-stroked-button data-testid="btn-reconnect" (click)="bridge.connect()">
            Reconnect
          </button>
        </div>
      }
```

Replace it with:

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

- [ ] **Step 4.7: Verify the template change**

```bash
grep -n "Launch Sim\|btn-launch\|btn-reconnect" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
```

Expected:
```
<line>:          <button mat-stroked-button data-testid="btn-launch"
<line>:            {{ bridge.launching() ? '…' : 'Launch Sim' }}
```

`btn-reconnect` should NOT appear.

- [ ] **Step 4.8: TypeScript compile check**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
ng build --configuration development 2>&1 | tail -8
```

Expected: `Application bundle generation complete` — no `ERROR` lines.

---

## Task 5: Update SimControlComponent — Play Demo Button

**Files:**
- Modify: `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts`

- [ ] **Step 5.1: Add `SimEegTick` to the import from `sim-bridge.service.ts`**

Find this exact import line:

```ts
import { SimBridgeService } from '../../../../../core/sim-bridge/sim-bridge.service';
```

Replace it with:

```ts
import { SimBridgeService, SimEegTick } from '../../../../../core/sim-bridge/sim-bridge.service';
```

- [ ] **Step 5.2: Add `buildDemoTicks()` private method**

Find this exact line (just above the closing `}` of the class):

```ts
  protected readonly progressPct = computed(() => {
```

Insert the following private method BEFORE `progressPct`:

```ts
  private buildDemoTicks(n = 60): SimEegTick[] {
    return Array.from({ length: n }, (_, i) => {
      const t = i / (n - 1);
      const focus = 0.5 + 0.4 * Math.sin(2 * Math.PI * 1.5 * t);
      return {
        focus,
        calm: 0.6 + 0.3 * Math.cos(2 * Math.PI * t),
        load: 0.4 + 0.2 * Math.sin(2 * Math.PI * 0.7 * t),
        fatigue: 0.1 + 0.4 * t,
        inFlow: focus > 0.8,
      };
    });
  }

  protected readonly progressPct = computed(() => {
```

- [ ] **Step 5.3: Add `playDemo()` method**

Find this block (just added in step 4.5):

```ts
  protected async launchSim(): Promise<void> {
```

Insert the following AFTER the closing `}` of `launchSim()` and BEFORE `private buildDemoTicks`:

```ts
  protected playDemo(): void {
    this.bridge.transferSession({
      sessionId: 'demo',
      taskLabel: 'Demo Replay',
      durationMs: 30_000,
      eegTicks: this.buildDemoTicks(60),
    });
  }
```

- [ ] **Step 5.4: Verify all three methods exist**

```bash
grep -n "launchSim\|playDemo\|buildDemoTicks" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
```

Expected (3 lines, order: launchSim → playDemo → buildDemoTicks):
```
<line>:  protected async launchSim(): Promise<void> {
<line>:  protected playDemo(): void {
<line>:  private buildDemoTicks(n = 60): SimEegTick[] {
```

- [ ] **Step 5.5: Replace the idle-state template block**

Find this exact block in the template:

```html
      @if (status() === 'idle') {
        <div class="sim__idle">Ready — transfer a session from the table below</div>
      }
```

Replace it with:

```html
      @if (status() === 'idle') {
        <div class="sim__idle">
          <span>Ready</span>
          <button mat-stroked-button data-testid="btn-play-demo" (click)="playDemo()">
            <mat-icon>play_arrow</mat-icon>
            Play Demo
          </button>
        </div>
      }
```

- [ ] **Step 5.6: Update `.sim__idle` style to flex layout**

Find this exact style line:

```css
    .sim__idle { font-size: 12px; color: #9aa8c4; }
```

Replace it with:

```css
    .sim__idle { display: flex; align-items: center; gap: 12px; font-size: 12px; color: #9aa8c4; }
```

- [ ] **Step 5.7: Verify idle template change**

```bash
grep -n "btn-play-demo\|playDemo\|Play Demo" /Users/alexanderlemberger/neurofeedback-lang-app/src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
```

Expected (3 hits):
```
<line>:          <button mat-stroked-button data-testid="btn-play-demo" (click)="playDemo()">
<line>:            Play Demo
<line>:  protected playDemo(): void {
```

- [ ] **Step 5.8: Final TypeScript compile check**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
ng build --configuration development 2>&1 | tail -8
```

Expected: `Application bundle generation complete` — no `ERROR` lines.

If there are errors, read the error output, identify which line is wrong, fix it, and re-run.

---

## Task 6: End-to-End Verification

- [ ] **Step 6.1: Start the full dev environment**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
npm run dev
```

Expected: two colored prefixes appear in terminal:
```
[ng]  Angular Live Development Server is listening on localhost:4200
[sim] [sim-launcher] http://localhost:3001
```

Leave this running. Open a second terminal for subsequent steps.

- [ ] **Step 6.2: Confirm Angular is up**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:4200
```

Expected: `200`

- [ ] **Step 6.3: Confirm launcher is up**

```bash
curl -s -X POST http://localhost:3001/sim/stop
```

Expected: `{"ok":true}`

- [ ] **Step 6.4: Test Launch Sim flow in browser**

1. Open `http://localhost:4200/dashboard` in Chrome
2. Find the **Robot Sim** card (top-right of dashboard)
3. Confirm it shows "Sim offline" and a **Launch Sim** button
4. Click **Launch Sim**
5. Button briefly shows "…" and is disabled
6. MuJoCo viewer window opens showing H1 humanoid standing
7. After ~2 seconds, Robot Sim card shows "Ready" and a **Play Demo** button

- [ ] **Step 6.5: Test Play Demo flow**

1. Click **Play Demo** in the Robot Sim card
2. Card shows progress bar + tick counter + EEG metrics (F / C / L / Fa)
3. Pause (⏸) and Stop (⏹) buttons appear
4. In the MuJoCo viewer: robot torso turns, arm moves toward wall plane
5. After ~30 seconds, replay ends and card returns to "Ready"

- [ ] **Step 6.6: Test error path (launcher not running)**

1. Stop just the launcher: `kill $(lsof -ti:3001)` in second terminal
2. In the Angular app, reload the page (the WS will disconnect)
3. SimControl shows "Sim offline" + "Launch Sim"
4. Click **Launch Sim**
5. A snackbar appears at the bottom: `Launcher not running — start with: npm run dev`
6. Snackbar has an "OK" button to dismiss

- [ ] **Step 6.7: Commit all changes**

```bash
cd /Users/alexanderlemberger/neurofeedback-lang-app
git add \
  tools/sim-launcher.js \
  package.json \
  package-lock.json \
  src/app/core/sim-bridge/sim-bridge.service.ts \
  src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts
git commit -m "feat(sim): launcher server + Launch Sim and Play Demo buttons"
```

Expected: commit created on `master` branch.
