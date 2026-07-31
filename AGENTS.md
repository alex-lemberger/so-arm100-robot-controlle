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
- Keep the verification → calibration-register match → explicit **Arm Motion** sequence mandatory. Begin any new control feature with small, slow moves and a clear workspace.
- The app's E-stop currently clears playback and queued commands. It is not a confirmed physical power cut unless controller-specific hardware stop/torque commands are configured and tested.

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
