# AGENTS.md

## Project overview

This repository contains a Vite + React + TypeScript interface for controlling and monitoring an SO-ARM100 robot. The UI includes joint controls, kinematics/IK tools, sequence editing, telemetry, gamepad/vision overlays, and a 3D arm view.

## Development

- Install dependencies with `npm install`.
- Start the local development server with `npm run dev`.
- Run the TypeScript check with `npm run lint`.
- Create a production build with `npm run build`.
- The AI sequence generator uses a local Ollama server; no cloud API key is required.
- Start Ollama with `ollama serve` and make sure `ollama list` includes `ornith:9b`.
- The default model is `ornith:9b`; override it with `OLLAMA_MODEL` in `.env.local`.
- The local AI endpoint is `POST /api/ollama/generate-sequence`.
- Hardware position updates are rate-limited to 20 Hz; keep UI animation and hardware transport decoupled.
- Direct WebSerial uses binary Feetech STS packets. It must first verify non-motion PING/READ replies from IDs 1–6, and physical position packets must remain locked until an explicit, per-arm `VITE_FEETECH_CALIBRATION` is valid and the user arms motion.
- Do not reintroduce the old ASCII `#1P...` format for direct WebSerial; it remains a WebSocket-bridge-only compatibility path.
- E-stop and torque commands are controller-specific. Only configure `VITE_ESTOP_COMMAND`, `VITE_TORQUE_ENABLE_COMMAND`, and `VITE_TORQUE_DISABLE_COMMAND` after verifying the robot protocol.
- Keep local environment files such as `.env.local` uncommitted; never commit secrets.

## Verified hardware setup

- The connected follower arm is the LeRobot calibration profile `white` (not the separate leader-arm profile `black`). Its saved calibration lives outside this repository under LeRobot's local cache; the copied `VITE_FEETECH_CALIBRATION` remains local in `.env.local`.
- Direct WebSerial at 1,000,000 baud successfully verified Feetech servo IDs 1–6, matched the follower calibration registers, and moved the physical arm through this app on 2026-08-01.
- On 2026-08-01 the leader was calibrated successfully with LeRobot as profile `black_20260801` on `/dev/cu.usbmodem5B140329561`; the follower remains `white` on `/dev/cu.usbmodem5AE60582701`. The leader calibration is stored outside this repository and copied only to local `.env.local` as `VITE_LEADER_FEETECH_CALIBRATION`.
- The app reached `LEADER_READY`, passive leader telemetry changed correctly, and explicit leader-to-follower mirroring was tested successfully. A stale LeRobot calibration process may retain the leader port after calibration; release that process before reconnecting from Chrome.
- Both arms were recalibrated on 2026-08-05 (same profiles `black_20260801` / `white`, same ports — confirmed unchanged with `lerobot-find-port`, do not suspect USB port reassignment as a first guess if a connection problem comes up) because wrist pitch (S4) had never actually been swept on either arm — it now has a real bounded range on both. Wrist roll (S5) still calibrates to `minTick=0/maxTick=4095` on both arms; confirmed by hand to be the joint's genuine near-360° range with a mechanical stop at the encoder wrap point, not an incomplete calibration. Use `~/lerobot/.venv/bin/lerobot-calibrate` (`--teleop.type=so100_leader` / `--robot.type=so100_follower`), not the project's `.venv-lerobot` (that env postdates the original calibration and lacks `feetech-servo-sdk`). When `lerobot-calibrate` offers to reuse an existing calibration file, you must type `c` and press Enter to actually recalibrate — bare Enter silently keeps the old file and rewrites nothing.
- After recalibrating either arm, **both** `VITE_LEADER_FEETECH_CALIBRATION` and `VITE_FEETECH_CALIBRATION` need to stay in sync with the live LeRobot calibration files — the app's calibration-register-match check silently keeps **Arm Motion** disabled if either side is stale. Restart `npm run dev` and hard-refresh the browser after editing `.env.local`; Vite does not hot-reload env changes. Chrome can also hold a serial port open after clicking disconnect in-app (check with `lsof /dev/cu.usbmodemXXXXXXX`); the tab must be fully closed, not just navigated away from, to release it.
- Keep the verification → calibration-register match → explicit **Arm Motion** sequence mandatory. Begin any new control feature with small, slow moves and a clear workspace. A servo's STS3215 `Status` register (address 65) can be read directly and safely (non-motion) via `scservo_sdk` to check for overload/voltage/overheat error flags if a joint faults during testing — a 2026-08-05 follower wrist-roll overload traced to a fast/large commanded jump plus a low (5.2V) supply-voltage reading, not a mechanical or calibration problem.
- The app's E-stop currently clears playback and queued commands. It is not a confirmed physical power cut unless controller-specific hardware stop/torque commands are configured and tested.

## Vision and learning direction

- The planned perception setup is two cameras: an existing external camera for a stable overview, plus an incoming wrist camera for gripper/object alignment. Keep their names consistent as `overview` and `wrist` when adding recording support.
- The current Ollama integration is a language-based keyframe planner, not a VLA. Do not describe it as a vision-language-action policy.
- The intended learning path is task-specific imitation learning: record synchronized overview/wrist frames, robot state, and commanded joint actions from leader-arm or gamepad demonstrations; train and evaluate a policy under conservative physical safety limits.
- A future learned policy should handle visual motor control, while Ollama remains optional high-level task planning. Validate with simulation and constrained, supervised physical tests before autonomous execution.

## Current dataset and policy state (2026-08-03)

- The primary downloaded dataset is `data/external/svla_so100_pickplace/`, sourced from [lerobot/svla_so100_pickplace](https://huggingface.co/datasets/lerobot/svla_so100_pickplace). It is LeRobot format with 50 SO-100 episodes, 19,631 frames, 30 FPS, 6D state/action data, and synchronized `top` plus `wrist` videos. Treat `top` as the external `overview` camera.
- A second comparison dataset is `data/external/so100_dataset50ep/`, sourced from [RasmusP/so100_dataset50ep](https://huggingface.co/datasets/RasmusP/so100_dataset50ep). It contains laptop/phone views and is not the preferred wrist-camera source.
- LeRobot is installed only in the ignored `.venv-lerobot/` Python 3.12 environment. Redirect its cache with `HF_DATASETS_CACHE=.cache/hf-datasets`; PyTorch currently reports no MPS/CUDA accelerator in this environment, so verified training used CPU.
- A local ACT baseline was trained from the primary dataset with a 40-episode train / 10-episode held-out split for 500 steps. Its checkpoint is under the ignored `outputs/train/act_so100_pickplace_500/checkpoints/000500/pretrained_model/` directory. Hub and W&B publishing are disabled.
- Offline evaluation of the checkpoint on 100 held-out samples produced mean absolute error 15.335 action units and zero out-of-limit predictions when the saved LeRobot processors are used. This is an undertrained baseline, not a deployment-ready policy.
- The Dataset Lab UI provides read-only dataset metadata and top/wrist video playback. `robot_learning/generate_policy_preview.py` creates `outputs/policy-preview.json`; the Dataset Lab can load that preview into the 3D view and Sequence Studio. Preview joints are clamped to the existing SO-ARM100 limits.
- The policy preview is offline-only. Do not connect it to WebSerial or claim autonomous physical control. The current pretrained task is cube-to-box placement, not the target circle-piece-to-matching-hole task; task-specific demonstrations and fine-tuning are still required.

## Code conventions

- Keep components in `src/components/` and shared types in `src/types.ts`.
- Put reusable robot math and transformation logic in `src/utils/`.
- Keep provider-specific AI behavior in `server.ts`; keep the frontend calling the local app endpoint rather than Ollama directly.
- Prefer small, typed React components and existing project patterns.
- Keep UI styling consistent with the existing design system in `src/index.css`.
- Avoid changing robot-control behavior without checking limits, units, and failure states.

## Validation

Before handing off changes, run `npm run lint` and, when relevant, `npm run build`. For changes to controls, kinematics, networking, or telemetry, manually exercise the affected flow in the development app.

For AI changes, verify that Ollama is running, the configured model is installed, and generated sequence output remains valid JSON matching the keyframe schema. Preserve the server-side JSON repair fallback for local-model responses.

For hardware changes, preserve command coalescing and never claim that torque has been disabled unless a verified hardware command has been sent. Never guess servo offsets, direction, or travel ranges from generic joint limits.

## Git hygiene

- Make focused commits with clear messages.
- Do not commit `.env.local`, API keys, generated `dist/` output, or dependency directories.
