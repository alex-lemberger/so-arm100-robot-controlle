# Learned-policy control of the physical SO-ARM100

**Date:** 2026-08-03
**Status:** Approved design, pending implementation plan

## Goal

Fine-tune a pretrained vision-language-action model on a small number of
self-recorded demonstrations, then execute it on the physical follower arm from
inside this app, without weakening any existing hardware safety guarantee.

The first task is **cube into bin**, deliberately matched to the borrowed
dataset's task string (`"Pick up the cube and place it in the box."`).

## Non-goals

- No prompting between different tasks. The model is language-conditioned, but
  it is trained on one task, so the prompt does not select behavior. Multi-task
  prompting is a later project requiring demonstrations per task.
- No autonomous operation without a human holding the dead-man control.
- No in-app episode recording. Recording stays in `lerobot-record`.
- No replacement of the existing four-condition arming gate. This work layers on
  top of it.

## Background: why not zero-shot

The original idea was to drive the arm from the existing checkpoint without
recording anything. Three findings ruled that out:

1. The trained ACT checkpoint declares only `observation.state` plus two image
   inputs (`outputs/train/act_so100_pickplace_500/.../config.json`). It has no
   language input, so it cannot accept a prompt.
2. The borrowed dataset contains exactly one task (`meta/info.json`:
   `total_tasks: 1`). Even a language-conditioned model trained on it alone would
   learn to ignore the text.
3. The checkpoint was trained for 500 steps on a different physical arm with
   different camera placement, at 15.335 mean absolute error. Its behavior does
   not transfer to this setup.

The leverage therefore comes from **`lerobot/smolvla_base`'s pretrained weights**,
not from the borrowed episodes. The borrowed episodes are retained as a format
reference, a smoke-test fixture, and an optional co-training arm (§4).

## 1. Data collection

Record with the native LeRobot recorder. Both arms are already calibrated:
follower `white` on `/dev/cu.usbmodem5AE60582701`, leader `black_20260801` on
`/dev/cu.usbmodem5B140329561`.

```bash
HF_DATASETS_CACHE=.cache/hf-datasets \
.venv-lerobot/bin/lerobot-record \
  --robot.type=so100_follower \
  --robot.port=/dev/cu.usbmodem5AE60582701 \
  --robot.id=white \
  --teleop.type=so100_leader \
  --teleop.port=/dev/cu.usbmodem5B140329561 \
  --teleop.id=black_20260801 \
  --dataset.repo_id=local/cube_bin \
  --dataset.root=data/local/cube_bin \
  --dataset.num_episodes=40 \
  --dataset.single_task="Pick up the cube and place it in the box." \
  --dataset.push_to_hub=false
```

**Episode count: 40** (minimum 30). The original plan of 10 was revised upward.
Data quantity for this exact physical setup is the largest single determinant of
success, and recording is cheap now that the rig works — roughly one evening.

**Camera names must be `top` and `wrist`** to match the borrowed dataset and keep
the co-training option open. `top` is the external overview camera.

**Scene setup.** A ~3–4 cm rigid block, not a sphere: balls roll, so approach
error displaces the object mid-grasp. Foam or soft plastic is preferred — it
tolerates gripper over-closure. The bin should have a wide mouth so that
releasing anywhere above it succeeds. Both object and bin must be fully visible
in the overview *and* wrist views throughout the episode.

**Demonstration quality.** Vary the cube's start position across episodes to
cover the workspace. Keep the arm's starting pose consistent — the policy's
first action is conditioned on it, and the runner enforces a start-pose check
(§5).

## 2. Training

```bash
HF_DATASETS_CACHE=.cache/hf-datasets \
.venv-lerobot/bin/lerobot-train \
  --dataset.repo_id=local/cube_bin \
  --dataset.root=data/local/cube_bin \
  --dataset.video_backend=pyav \
  --dataset.eval_split=0.15 \
  --policy.path=lerobot/smolvla_base \
  --policy.push_to_hub=false \
  --output_dir=outputs/train/smolvla_cube_bin \
  --job_name=smolvla_cube_bin \
  --wandb.enable=false
```

**Compute.** `torch 2.11.0` reports MPS available on this machine, so local
training works. (The claim in `AGENTS.md` that no accelerator is present is stale
and must be corrected.) However, SmolVLA is roughly 450M parameters and MPS
training is slow enough to ruin the iteration loop. **Preferred: rent a GPU for
the training run.** The dataset is small enough to upload, an hour of a 4090 or
A100 costs single-digit dollars, and it turns an overnight run into ~30 minutes.
MPS remains the fallback.

**Held-out split.** `--dataset.eval_split=0.15` reserves episodes for offline
evaluation. Report mean absolute error on the held-out split before any physical
execution.

## 3. Action-frame mapping

This is the highest-risk component and gets its own module,
`src/utils/policyFrame.ts`, with its own tests.

The policy emits actions in LeRobot's SO-100 convention. The app uses a different
one. The existing `robot_learning/generate_policy_preview.py:65` maps them by
zipping positionally and clamping, which is incorrect and currently renders a
geometrically distorted preview.

### The exact formulas

Read from the installed LeRobot source, not inferred:

`lerobot/robots/so_follower/so_follower.py:50-59` — per-joint normalization mode:

| Index | LeRobot motor | Mode |
|---|---|---|
| 0 | `shoulder_pan` | `DEGREES` |
| 1 | `shoulder_lift` | `DEGREES` |
| 2 | `elbow_flex` | `DEGREES` |
| 3 | `wrist_flex` | `DEGREES` |
| 4 | `wrist_roll` | `DEGREES` |
| 5 | `gripper` | **`RANGE_0_100`** |

`lerobot/motors/motors_bus.py:854-911` — the conversions, where
`mid = (range_min + range_max) / 2` and `max_res = 4095` for the STS3215:

```
DEGREES       ticks → deg    deg   = (ticks - mid) * 360 / max_res
              deg → ticks    ticks = deg * max_res / 360 + mid

RANGE_0_100   ticks → pct    pct   = (ticks - min) / (max - min) * 100
                             (drive_mode inverts: 100 - pct)
              pct → ticks    ticks = pct / 100 * (max - min) + min
```

The app's own convention (`App.tsx:54-77`) maps each joint's `minAngle..maxAngle`
linearly onto `minTick..maxTick` from `VITE_FEETECH_CALIBRATION`.

Because both conventions bottom out in raw servo ticks, and because the app's
`minTick`/`maxTick` were copied from the same LeRobot calibration that supplies
`range_min`/`range_max`, the two compose exactly:

```
policy action ──DEGREES/RANGE_0_100──► raw ticks ──► SYNC_WRITE   [hardware]
                                            └──app convention──► JointState [3D twin]
```

The hardware path goes straight to ticks and never round-trips through the app's
`JointState`, avoiding a lossy double conversion.

### Two known gotchas

- **Gripper `drive_mode`.** The `RANGE_0_100` branch inverts when `drive_mode` is
  set, but `VITE_FEETECH_CALIBRATION` does not store `drive_mode`. Read it from
  the LeRobot calibration file for the `white` profile and either extend the env
  schema or hard-code the verified value. A silently inverted gripper opens when
  it should close.
- **`DEGREES` ignores `drive_mode`** in this LeRobot version, so joints 1–5 are
  unaffected. Do not add an inversion there.

### Acceptance test — blocking

Take one recorded episode. Push its `action` column through the mapping into the
3D twin and play it beside that episode's `top` video. **The twin must visibly
reproduce the recorded motion.** Nothing touches hardware until this matches.

The same fix is applied to `generate_policy_preview.py`.

## 4. Co-training experiment (optional)

Because the task string now matches the borrowed dataset, co-training is worth a
cheap A/B rather than being near-pointless:

- **Run A** — `local/cube_bin` only
- **Run B** — `local/cube_bin` + `svla_so100_pickplace`

Compare offline MAE on the held-out split of **your** episodes. Take the winner.
Expect A to win or tie: the borrowed data shares task semantics but differs in
camera extrinsics and physical arm, and mismatched visual statistics commonly
hurt. Do not spend more than one comparison on this.

## 5. Runtime architecture

```
┌─ Python, .venv-lerobot ────────────────────────────────┐
│ robot_learning/policy_server.py        (port 8765)     │
│   loads checkpoint + pre/post processors once          │
│   POST /act  {images{top,wrist}, state[6], task}       │
│           →  {actions: [[6], ...]}                     │
└────────────────────────────────────────────────────────┘
                      ▲ proxied by express at /api/policy/act
┌─ Browser ──────────────────────────────────────────────┐
│ PolicyRunnerPanel.tsx                                  │
│   READ present position ×6  → measured state           │
│   grab frame from each camera                          │
│   POST → receive action chunk                          │
│   map → clamp → queueHardwareMotion  (existing 20 Hz)  │
│                       └─► existing 4-condition gate    │
└────────────────────────────────────────────────────────┘
```

The policy never touches the serial port. It is a pure `observation → action`
function behind HTTP, which keeps every existing safety guarantee intact and
makes the policy swappable.

### Server

- Plain `http.server` or FastAPI in `.venv-lerobot`. Loads the checkpoint and
  `make_pre_post_processors` once at startup, mirroring
  `generate_policy_preview.py:38-47`.
- Images arrive as base64 JPEG at 640×480 to match the training resolution
  (~130 KB per request for both cameras — acceptable at the inference rates
  below).
- Express proxies `/api/policy/act` → `127.0.0.1:8765/act` so the browser stays
  same-origin. Bind the Python server to loopback only.
- `GET /api/policy/status` reports loaded checkpoint path and device, surfaced in
  the UI so it is never ambiguous which policy is armed.

### Control loop

- **Execute 15 actions per inference**, not the full predicted chunk. A full ACT
  or SmolVLA chunk is ~100 steps ≈ 3.3 s at 30 Hz — far too long to run blind.
  15 steps ≈ 0.5 s. Configurable.
- **Pipeline one chunk deep**: request the next chunk as soon as the current one
  begins executing. Sequential request-then-execute would stall the arm for the
  duration of every inference and produce visibly jerky motion.
- Measured-state reads cost ~6 round trips (~30 ms) and share the bus with
  outgoing `SYNC_WRITE` traffic. Acceptable at these rates; revisit if the bus
  saturates.

## 6. Safety

Autonomous rollout differs categorically from teleoperation: no human vets each
target. The existing gate authorizes a *session*, so the following are layered on
top of it, not instead of it.

| Guard | Behavior |
|---|---|
| Dead-man | **Gamepad R2 held.** Spring-loaded, so release is a physical reflex, and unlike a held key it cannot auto-repeat or stick. |
| Release / blur / `visibilitychange` | Clear queue, halt immediately |
| Per-tick delta clamp | Max °/joint/tick, default 4° (≈80 °/s at 20 Hz), configurable |
| Episode timeout | Hard stop at 45 s (a cube-into-bin episode runs ~15–20 s) |
| Start-pose check | Refuse to start if the arm is far from the training initial-state distribution |
| Joint limits | Existing `SO_ARM100_SERVOS` clamps, applied after mapping |
| E-stop | Unchanged; additionally aborts the rollout and disarms |
| Existing four-condition gate | Still fully required. The policy path cannot bypass `isMotionArmed` or `isCalibrationVerified`. |

Clamps are applied **before** `queueHardwareMotion`, so a bad prediction is
bounded at the source rather than relying on downstream coalescing.

There is no keyboard dead-man. `Space` is already bound to play/pause
(`App.tsx:653`) and a held letter key is a poor dead-man regardless.

## 7. Targeted refactor

`GamepadVisionOverlay.tsx` is 516 lines doing three jobs: gamepad polling, camera
management, and episode recording. The runner needs the camera half, and opening
the same devices twice would fail.

Extract camera acquisition into `src/hooks/useCameras.ts`, consumed by both the
existing recorder and the new runner. No other refactoring.

## 8. Files

**New**
- `robot_learning/policy_server.py`
- `src/utils/policyFrame.ts`
- `src/components/PolicyRunnerPanel.tsx`
- `src/hooks/useCameras.ts`

**Modified**
- `server.ts` — proxy route + policy status endpoint
- `src/App.tsx` — sixth control tab, dead-man wiring, rollout state
- `src/components/GamepadVisionOverlay.tsx` — consume `useCameras`
- `robot_learning/generate_policy_preview.py` — correct the frame mapping
- `AGENTS.md` — MPS availability, new task, policy runner safety rules
- `.env.example` — gripper `drive_mode`, policy server URL
- `README.md` — recording and training workflow
- `.gitignore` — **add `/data/local/`**. Currently only `/data/external/` and
  `/data/experiments/` are ignored, so 40 episodes of recorded video would
  otherwise be committed. Fix this before the first recording run.

## 9. Testing

1. **Unit** — mapping round-trip identity (`app → ticks → lerobot → ticks → app`),
   gripper `drive_mode` inversion, per-tick clamp behavior, dead-man release
   semantics.
2. **Integration (blocking)** — the episode-replay-versus-video test in §3.
3. **Offline** — held-out MAE for the fine-tuned checkpoint, reported before any
   physical run.
4. **Simulation** — full rollout loop against `connectionType='simulation'`, no
   hardware, confirming inference rate and loop timing.
5. **Physical** — only after 1–4: dead-man held, low speed, clear workspace,
   small first motion, hand on the power switch.

Run `npm run lint` and `npm run build` before handoff.

## 10. Risks

| Risk | Mitigation |
|---|---|
| 40 episodes still insufficient | Pipeline makes additional batches cheap; record more. This is the expected failure mode and the expected fix. |
| Mapping wrong in a way the twin does not reveal | Replay test uses real recorded actions against real video; clamps bound the damage; first physical run is slow and supervised. |
| Gripper inverted via `drive_mode` | Explicitly verified against the LeRobot calibration file, with a unit test. |
| MPS training too slow to iterate | Rent a GPU. |
| Insertion-style precision task attempted too early | Deliberately deferred; cube-into-bin is the first target. |
| Policy behaves erratically near workspace edge | Start-pose check, joint clamps, per-tick delta clamp, 45 s timeout, dead-man. |

## Open decisions deferred to implementation

None. Every parameter above has a concrete default; tuning happens against real
measurements during bring-up.
