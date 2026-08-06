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
  mjpython sim/ws_server.py [--model h1|ur5e] [--port 8765] [--headless] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import threading
import time
from typing import Any

import mujoco
import numpy as np
import websockets
from websockets import ServerConnection

try:
    from .trowel_h1 import troweling_targets as h1_targets
except ImportError:
    from trowel_h1 import troweling_targets as h1_targets  # type: ignore[no-redef]

try:
    from .trowel_h1_hand import troweling_targets as h1_hand_targets, HOME as _H1_HAND_HOME
except ImportError:
    from trowel_h1_hand import troweling_targets as h1_hand_targets, HOME as _H1_HAND_HOME  # type: ignore[no-redef]

try:
    try:
        from .ik import H1IkSolver, wall_zigzag
    except ImportError:
        from ik import H1IkSolver, wall_zigzag  # type: ignore[no-redef]
    _IK_AVAILABLE = True
except ImportError:
    # mink not installed (e.g. cloud/Docker deploy) — h1_hand model doesn't need IK
    _IK_AVAILABLE = False
    H1IkSolver = None  # type: ignore[assignment,misc]
    def wall_zigzag(*a, **kw):  # type: ignore[misc]
        return []

# Neutral standing pose matching the XML keyframe (CoM over feet, arms at sides).
# Used for idle/pause/warmup. troweling_targets() adds arm motion on top of its own HOME.
_H1_STAND = np.zeros(19)
_H1_STAND[2] = -0.4   # left_hip_pitch
_H1_STAND[3] =  0.8   # left_knee
_H1_STAND[4] = -0.4   # left_ankle
_H1_STAND[7] = -0.4   # right_hip_pitch
_H1_STAND[8] =  0.8   # right_knee
_H1_STAND[9] = -0.4   # right_ankle

# Boustrophedon wall grid — empty when mink not installed (h1_hand doesn't use IK).
_WALL_WAYPOINTS = list(wall_zigzag(
    origin=(0.55, -0.25, 1.4),
    width=0.5,
    height=0.5,
    rows=4,
    step=0.15,
))
_SECS_PER_WP = 1.5   # seconds at base speed to dwell on each waypoint

# ---------------------------------------------------------------------------
# Shared state (main thread writes, WS thread reads via broadcast queue)
# ---------------------------------------------------------------------------
_cmd_q: queue.Queue[dict] = queue.Queue()
_broadcast_q: queue.Queue[str] = queue.Queue()

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
    'wp_progress': 0.0,     # waypoint progress (float) for IK
    'ik_solver': None,      # H1IkSolver instance for current session
}

# ---------------------------------------------------------------------------
# WebSocket server (background asyncio thread)
# ---------------------------------------------------------------------------
_clients: set[ServerConnection] = set()


async def _handler(ws: ServerConnection) -> None:
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


async def _process_request(connection, request):
    """Return HTTP 200 for non-WS requests (HF health checks / browser visits)."""
    if request.headers.get('upgrade', '').lower() != 'websocket':
        from websockets.http11 import Response
        from websockets.datastructures import Headers
        body = b'handwerk-sim OK'
        return Response(
            200, 'OK',
            Headers([('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))]),
            body,
        )
    return None


async def _ws_main(host: str, port: int) -> None:
    import logging
    logging.getLogger('websockets.server').setLevel(logging.CRITICAL)
    async with websockets.serve(_handler, host, port, process_request=_process_request):
        await _broadcast_loop()


def _start_ws_thread(host: str, port: int) -> None:
    asyncio.run(_ws_main(host, port))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _snap(state: dict) -> str:
    with _lock:
        return json.dumps({
            'status': state['status'],
            'tick': state['tick'],
            'totalTicks': state['total_ticks'],
            'q': [round(v, 4) for v in state['q']],
            'eegTick': state['eeg_tick'],
        })


def _process_commands(state: dict, model: mujoco.MjModel,
                      root_qpos: np.ndarray) -> None:
    while True:
        try:
            cmd = _cmd_q.get_nowait()
        except queue.Empty:
            break
        action = cmd.get('cmd')
        with _lock:
            if action == 'replay':
                state['replay_ticks'] = cmd.get('eegTicks', [])
                state['total_ticks'] = len(state['replay_ticks'])
                raw_dur = float(cmd.get('durationMs', 0))
                # Guard: if duration missing/zero, spread ticks at 500ms each
                state['duration_ms'] = raw_dur if raw_dur > 0 else state['total_ticks'] * 500.0
                state['tick'] = 0
                state['elapsed_ms'] = 0.0
                state['status'] = 'replaying'
                print(f'[replay] {state["total_ticks"]} ticks, {state["duration_ms"]:.0f}ms')
                
                state['wp_progress'] = 0.0
                if _IK_AVAILABLE:
                    state['ik_solver'] = H1IkSolver(model, root_qpos)
                    print(f'[ik] {len(_WALL_WAYPOINTS)} waypoints loaded')
                    _bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "right_elbow_link")
                    print(f'[ik-diag] right_elbow_link body_id={_bid}')
                else:
                    state['ik_solver'] = None
                    print('[ik] mink not available — IK disabled')
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
            else:
                print(f'[ws_server] Unknown command: {action!r}')


# ---------------------------------------------------------------------------
# H1 PD controller — converts target joint angles to torques.
# Gains tuned to H1 ctrlranges; freejoint root uses qpos[7:] / qvel[6:].
# ---------------------------------------------------------------------------

# Gravity-compensated PD controller for H1 torque motors.
# ff = qfrc_bias cancels gravity; PD term only needs to correct tracking error.
# Gains are tuned for stability with gravity compensation active.
_H1_KP = np.array([
    100, 100, 200, 200,  20,   # left leg:  yaw, roll, pitch, knee, ankle
    100, 100, 200, 200,  20,   # right leg
    200,                        # torso
     40,  40,  18,  18,        # left arm:  pitch, roll, yaw, elbow
     40,  40,  18,  18,        # right arm
], dtype=float)

_H1_KD = np.array([
    50, 50, 50, 50, 10,   # left leg
    50, 50, 50, 50, 10,   # right leg
    50,                    # torso
    10, 10,  5,  5,       # left arm
    10, 10,  5,  5,       # right arm
], dtype=float)


def _h1_pd(model: mujoco.MjModel, data: mujoco.MjData, target_q: np.ndarray) -> np.ndarray:
    q   = data.qpos[7 : 7 + model.nu]
    dq  = data.qvel[6 : 6 + model.nu]
    ff  = data.qfrc_bias[6 : 6 + model.nu]  # gravity + Coriolis feedforward
    ctrl = _H1_KP * (target_q - q) - _H1_KD * dq + ff
    lo = model.actuator_ctrlrange[:, 0]
    hi = model.actuator_ctrlrange[:, 1]
    return np.clip(ctrl, lo, hi)


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
MIN_SPEED = 0.4  # minimum speed as a fraction of base speed (1.0)

def _main_loop(model: mujoco.MjModel, data: mujoco.MjData, args: argparse.Namespace) -> None:
    """Main simulation loop with or without viewer."""
    if args.headless:
        # For headless mode, we'll handle viewer ourselves
        print(f'Model: {args.model}. Running in headless mode...')
        
        # Initialize simulation state
        state = _shared
        sim_tick = 0
        start_time = time.time()
        prev_status = 'idle'

        # Process initial commands to set up model for running
        _process_commands(state, model, data.qpos[0:7].copy())

        # Run the main simulation loop without viewer
        while True:  # Exit condition handled by commands from Angular
            step_start = time.time()
            
            # Process any pending commands
            _process_commands(state, model, data.qpos[0:7].copy())

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

            use_h1_hand = (args.model == 'h1_hand')
            use_pd = (args.model == 'h1')

            # Simulation step with different physics based on model type
            if use_h1_hand:
                # H1 + hand: full physics via mj_step, all position actuators
                if status == 'replaying' and eeg is not None:
                    fatigue = eeg.get('fatigue')
                    in_flow = eeg.get('inFlow', False)
                    targets = h1_hand_targets(t, fatigue=fatigue, in_flow=in_flow)
                    data.ctrl[:model.nu] = targets[:model.nu]
                elif status == 'idle':
                    data.ctrl[:model.nu] = _H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu])
                mujoco.mj_step(model, data)

            elif status == 'replaying':
                if eeg is not None:
                    fatigue = eeg.get('fatigue') or 0.0
                    in_flow = eeg.get('inFlow', False)
                    if args.model != 'h1':
                        targets = _ur5e_targets(t)
                if use_pd:
                    if eeg is not None:
                        # IK path: advance waypoint pointer + solve
                        speed = 1.0 - fatigue * (1.0 - MIN_SPEED)
                        with _lock:
                            state['wp_progress'] += model.opt.timestep * speed / _SECS_PER_WP
                            wp_idx = min(int(state['wp_progress']), len(_WALL_WAYPOINTS) - 1)
                            solver: H1IkSolver = state['ik_solver']

                        solver.sync_from(data)
                        solver.set_target(np.array(_WALL_WAYPOINTS[wp_idx]))
                        solver.step(model.opt.timestep)
                        solver.sync_to(data)

                        # Overlay scripted torso yaw (joint 10 in 19-DOF array → qpos[17])
                        torso_yaw = h1_targets(t, fatigue=fatigue, in_flow=in_flow)[10]
                        data.qpos[7 + 10] = torso_yaw

                        # Log once per waypoint change
                        with _lock:
                            _logged_wp = state.get('_logged_wp', -1)
                        if wp_idx != _logged_wp:
                            mujoco.mj_forward(model, data)
                            body_id = mujoco.mj_name2id(
                                model, mujoco.mjtObj.mjOBJ_BODY, "right_elbow_link"
                            )
                            err = np.linalg.norm(
                                data.xpos[body_id] - np.array(_WALL_WAYPOINTS[wp_idx])
                            )
                            print(f'[ik] wp {wp_idx}/{len(_WALL_WAYPOINTS)} err={err:.4f}m  arm_q={data.qpos[22:26].round(3).tolist()}')
                            with _lock:
                                state['_logged_wp'] = wp_idx

                    mujoco.mj_forward(model, data)
                else:
                    targets = _ur5e_targets(t) if args.model != 'h1' else None
                    data.ctrl[:model.nu] = targets[:model.nu] if eeg is not None and targets is not None else (_H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu]))
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
                    data.ctrl[:model.nu] = _H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu])
                    mujoco.mj_step(model, data)

            with _lock:
                state['q'] = data.ctrl[:model.nu].tolist()
            sim_tick += 1

            if sim_tick % 10 == 0:
                _broadcast_q.put(_snap(state))

            elapsed = time.time() - step_start
            sleep = model.opt.timestep - elapsed
            if sleep > 0:
                time.sleep(sleep)
    else:
        # Run with viewer (original behavior)
        print(f'WebSocket server running on ws://{args.host}:{args.port}')
        print(f'Model: {args.model}. Waiting for Angular to connect...')
        
        state = _shared
        sim_tick = 0
        start_time = time.time()
        prev_status = 'idle'

        with mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                step_start = time.time()
                _process_commands(state, model, data.qpos[0:7].copy())

                with _lock:
                    status = state['status']

                prev_status = status

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

                use_h1_hand = (args.model == 'h1_hand')
                use_pd = (args.model == 'h1')

                if use_h1_hand:
                    # H1 + hand: full physics via mj_step, all position actuators
                    if status == 'replaying' and eeg is not None:
                        fatigue = eeg.get('fatigue')
                        in_flow = eeg.get('inFlow', False)
                        targets = h1_hand_targets(t, fatigue=fatigue, in_flow=in_flow)
                        data.ctrl[:model.nu] = targets[:model.nu]
                    elif status == 'idle':
                        data.ctrl[:model.nu] = _H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu])
                    mujoco.mj_step(model, data)

                elif status == 'replaying':
                    if eeg is not None:
                        fatigue = eeg.get('fatigue') or 0.0
                        in_flow = eeg.get('inFlow', False)
                        if args.model != 'h1':
                            targets = _ur5e_targets(t)
                    if use_pd:
                        if eeg is not None:
                            # IK path: advance waypoint pointer + solve
                            speed = 1.0 - fatigue * (1.0 - MIN_SPEED)
                            with _lock:
                                state['wp_progress'] += model.opt.timestep * speed / _SECS_PER_WP
                                wp_idx = min(int(state['wp_progress']), len(_WALL_WAYPOINTS) - 1)
                                solver: H1IkSolver = state['ik_solver']

                            solver.sync_from(data)
                            solver.set_target(np.array(_WALL_WAYPOINTS[wp_idx]))
                            solver.step(model.opt.timestep)
                            solver.sync_to(data)

                            # Overlay scripted torso yaw (joint 10 in 19-DOF array → qpos[17])
                            torso_yaw = h1_targets(t, fatigue=fatigue, in_flow=in_flow)[10]
                            data.qpos[7 + 10] = torso_yaw

                            # Log once per waypoint change
                            with _lock:
                                _logged_wp = state.get('_logged_wp', -1)
                            if wp_idx != _logged_wp:
                                mujoco.mj_forward(model, data)
                                body_id = mujoco.mj_name2id(
                                    model, mujoco.mjtObj.mjOBJ_BODY, "right_elbow_link"
                                )
                                err = np.linalg.norm(
                                    data.xpos[body_id] - np.array(_WALL_WAYPOINTS[wp_idx])
                                )
                                print(f'[ik] wp {wp_idx}/{len(_WALL_WAYPOINTS)} err={err:.4f}m  arm_q={data.qpos[22:26].round(3).tolist()}')
                                with _lock:
                                    state['_logged_wp'] = wp_idx

                        mujoco.mj_forward(model, data)
                    else:
                        targets = _ur5e_targets(t) if args.model != 'h1' else None
                        data.ctrl[:model.nu] = targets[:model.nu] if eeg is not None and targets is not None else (_H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu]))
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
                        data.ctrl[:model.nu] = _H1_HAND_HOME[:model.nu] if args.model == 'h1_hand' else (_H1_STAND[:model.nu] if args.model == 'h1' else _UR5E_HOME[:model.nu])
                        mujoco.mj_step(model, data)

                viewer.sync()

                with _lock:
                    state['q'] = data.ctrl[:model.nu].tolist()
                sim_tick += 1

                if sim_tick % 10 == 0:
                    _broadcast_q.put(_snap(state))

                elapsed = time.time() - step_start
                sleep = model.opt.timestep - elapsed
                if sleep > 0:
                    time.sleep(sleep)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', choices=['h1', 'ur5e', 'h1_hand'], default='h1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--headless', action='store_true', help='Run without GUI')
    parser.add_argument('--host', default='localhost', help='Host address to bind to')
    args = parser.parse_args()

    _model_paths = {
        'h1':      'models/h1/scene.xml',
        'ur5e':    'models/ur5e/scene.xml',
        'h1_hand': 'models/h1_hand/scene.xml',
    }
    model_path = _model_paths[args.model]
    home = _H1_HAND_HOME if args.model == 'h1_hand' else (_H1_STAND if args.model == 'h1' else _UR5E_HOME)

    if not os.path.exists(model_path):
        raise SystemExit(f'Model not found: {model_path}. Run ./setup_model.sh first.')

    model = mujoco.MjModel.from_xml_path(model_path)
    data = mujoco.MjData(model)
    if model.nkey > 0:
        mujoco.mj_resetDataKeyframe(model, data, 0)  # standing pose from XML keyframe
    _h1_root_qpos = data.qpos[0:7].copy()   # root pose frozen for IK
    use_pd = (args.model == 'h1')        # H1 kinematic (mj_forward, writes qpos)
    use_h1_hand = (args.model == 'h1_hand')  # H1+hand physics (mj_step, position actuators)

    ws_thread = threading.Thread(target=_start_ws_thread, args=(args.host, args.port), daemon=True)
    ws_thread.start()

    # This is where we call our new _main_loop function
    _main_loop(model, data, args)


if __name__ == '__main__':
    main()
