# Spec: Sim Launcher + Play Button

**Date:** 2026-06-11  
**Status:** Approved

## Goal

Add a "Launch Sim" button to the Angular dashboard that spawns the MuJoCo WebSocket server, and a "Play" button that starts a 30-second demo replay — so the sim can be started and played without touching a terminal.

## Architecture

### 1. `tools/sim-launcher.js` (new file, Node.js)

Tiny Express HTTP server on port `3001`. Runs in the `~/handwerk-robot-sim` directory alongside Angular.

**Endpoints:**
- `POST /sim/start` — kills any existing tracked process, spawns `<repo>/.venv/bin/mjpython sim/ws_server.py --model h1` with `cwd: ~/handwerk-robot-sim`. Returns `{ ok: true, pid }` or `{ ok: false, error }`.
- `POST /sim/stop` — kills tracked process if alive. Returns `{ ok: true }`.

**Details:**
- CORS header `Access-Control-Allow-Origin: http://localhost:4200` on all responses.
- Subprocess stdout/stderr piped to launcher's stdout (visible in terminal).
- PID stored in module-level variable; cleared on process exit.
- No persistent state file — launcher process lifetime = terminal session.
- Port configurable via `SIM_LAUNCHER_PORT` env var, default `3001`.
- Requires only `express` (already in devDeps or added). No other dependencies.

### 2. `package.json` scripts

```json
"sim-launcher": "node tools/sim-launcher.js",
"dev": "concurrently \"npm start\" \"npm run sim-launcher\""
```

Add `concurrently` as devDependency if not present.

### 3. `SimBridgeService` additions

Two new methods using `fetch` (no `HttpClient` — keeps service self-contained):

```ts
launchSim(): void  // POST http://localhost:3001/sim/start, then connect() after 2s
stopSim(): void    // POST http://localhost:3001/sim/stop
```

`launchSim()` sets internal `_launching` signal to `true` while waiting; clears on connect/error.

### 4. `SimControlComponent` changes

**Disconnected state** — replace existing "Reconnect" button with:
- "Launch Sim" button (primary style) → calls `bridge.launchSim()`
- While launching: spinner + "Starting…" label
- After 2s: bridge auto-calls `connect()` → status transitions to `idle`

**Idle state** — add "Play Demo" button alongside existing idle message:
- Calls `bridge.transferSession(demoPaylod)` with synthetic ticks
- Demo payload: 60 ticks, `durationMs: 30000`, EEG values from sine waves (focus 0.5+0.4sin, calm 0.6+0.3cos, fatigue 0.3+0.2sin half-speed, inFlow = focus > 0.8)
- `sessionId: 'demo'`, `taskLabel: 'Demo Replay'`
- Inline helper `buildDemoTicks(n=60)` in the component — no shared service

## Data Flow

```
User clicks "Launch Sim"
  → SimBridgeService.launchSim()
    → fetch POST localhost:3001/sim/start
      → launcher spawns mjpython (pid stored)
    → setTimeout 2000ms → bridge.connect()
      → WebSocket opens to ws://localhost:8765
        → status: disconnected → idle

User clicks "Play Demo"
  → SimControlComponent.playDemo()
    → buildDemoTicks(60) → SimBridgeService.transferSession(...)
      → WS send {cmd:'replay', ...}
        → Python: status replaying → Angular: status replaying
          → progress bar + EEG overlay + pause/stop controls visible
```

## Error Handling

- `launchSim()` fetch fails (launcher not running): show snackbar "Launcher not running — start with `npm run dev`". `_launching` clears.
- WS fails to connect after 2s: auto-retry logic already in `SimBridgeService` (3 retries, 3s each).
- `stopSim()` is fire-and-forget; no error UI needed.

## Files Touched

| File | Change |
|------|--------|
| `tools/sim-launcher.js` | **New** — Express launcher server |
| `package.json` | Add `sim-launcher`, `dev` scripts; add `concurrently` devDep |
| `src/app/core/sim-bridge/sim-bridge.service.ts` | Add `launchSim()`, `stopSim()`, `_launching` signal |
| `src/app/shared/components/layout/dashboard-layout/widgets/sim-control.component.ts` | Replace Reconnect with Launch Sim; add Play Demo button + `buildDemoTicks()` |

## Out of Scope

- No health-check polling of the launcher server.
- No "stop sim" button in UI (process dies when launcher terminal closes or `npm run dev` is killed).
- No Windows support (mjpython path and process killing are Unix-only).
- No changes to capture sessions table Transfer button — that path remains unchanged.
