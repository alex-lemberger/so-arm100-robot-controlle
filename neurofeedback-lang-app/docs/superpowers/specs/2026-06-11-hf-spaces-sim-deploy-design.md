# HF Spaces Sim Deploy Design

**Date:** 2026-06-11  
**Goal:** Deploy `handwerk-robot-sim` WebSocket server to Hugging Face Spaces (Docker) so the MuJoCo H1 sim is publicly accessible for online showcases — without touching a terminal.

---

## Problem

`ws_server.py` uses `mujoco.viewer.launch_passive` (GUI window) and binds to `localhost`. Neither works on a headless cloud VM. The Angular app hardcodes `ws://localhost:8765` and shows a "Launch Sim" button that spawns a local Node.js process — neither makes sense in prod.

---

## Architecture

### Python sim — headless mode

Two new CLI args added to `sim/ws_server.py`:

- `--headless` — skips `mujoco.viewer.launch_passive`; replaces the `with viewer:` loop with a plain `while True:` loop. Local dev unchanged (no flag = viewer opens as before).
- `--host` — WebSocket bind host. Defaults to `localhost`. Dockerfile passes `0.0.0.0`.

Note: `mjpython` is a macOS launcher for the passive viewer. Dockerfile uses `python3` directly — safe because `--headless` never opens a viewer.

### HF Spaces Docker setup

New files in `handwerk-robot-sim/`:

**`README.md`** (HF Space metadata frontmatter):
```yaml
---
sdk: docker
app_port: 7860
---
```

**`Dockerfile`**:
- Base: `python:3.11-slim`
- System deps: `libgl1`, `libegl1`, `libglib2.0-0` (MuJoCo headless rendering)
- Pip: `mujoco`, `mink`, `websockets`, `numpy`, `pin` (Pinocchio for mink IK)
- Copies `sim/` and `models/`
- CMD: `python3 sim/ws_server.py --model h1_hand --headless --host 0.0.0.0 --port 7860`

**`requirements.txt`**: pinned versions for reproducible builds.

Deploy by pushing to HF Space git remote:
```
git remote add space https://huggingface.co/spaces/{username}/handwerk-sim
git push space main
```

Resulting WS URL: `wss://{username}-handwerk-sim.hf.space`

### Angular changes

**`environment.ts`**: add `simWsUrl: ''` (empty = local)  
**`environment.prod.ts`**: add `simWsUrl: 'wss://{username}-handwerk-sim.hf.space'`

**`sim-bridge.service.ts`**:
- `connect()` default URL: `environment.simWsUrl || 'ws://localhost:8765'`
- Export `isCloudSim = environment.simWsUrl !== ''`

**`sim-control.component.ts`**:
- Hide "Launch Sim" button when `isCloudSim`
- Show "Connect" button instead — calls `simBridge.connect()` directly, no launcher roundtrip

`tools/sim-launcher.js` and local npm scripts unchanged.

---

## Error Handling

HF Spaces sleeps after ~1hr inactivity. Cold start ~30s. `SimBridgeService` already retries 3× at 3s intervals — covers the wake-up lag. Existing snackbar + disconnect state in `SimControlComponent` handles WS failures.

No auth on the WS endpoint — public space, anyone can send commands. Acceptable for showcase; worst case a visitor sends `reset`.

---

## File Map

| Repo | File | Action |
|---|---|---|
| `handwerk-robot-sim` | `sim/ws_server.py` | Modify — add `--headless` + `--host` args |
| `handwerk-robot-sim` | `Dockerfile` | Create |
| `handwerk-robot-sim` | `requirements.txt` | Create |
| `handwerk-robot-sim` | `README.md` | Create/modify — HF frontmatter |
| `neurofeedback-lang-app` | `src/environments/environment.ts` | Modify — add `simWsUrl: ''` |
| `neurofeedback-lang-app` | `src/environments/environment.prod.ts` | Modify — add `simWsUrl` |
| `neurofeedback-lang-app` | `src/app/core/sim-bridge/sim-bridge.service.ts` | Modify — env-driven WS URL + `isCloudSim` |
| `neurofeedback-lang-app` | `sim-control.component.ts` | Modify — hide Launch Sim, show Connect in prod |
