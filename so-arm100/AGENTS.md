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

## Current dataset and policy state (2026-08-06)

- The primary downloaded dataset is `data/external/svla_so100_pickplace/`, sourced from [lerobot/svla_so100_pickplace](https://huggingface.co/datasets/lerobot/svla_so100_pickplace). It is LeRobot format with 50 SO-100 episodes, 19,631 frames, 30 FPS, 6D state/action data, and synchronized `top` plus `wrist` videos. Treat `top` as the external `overview` camera. This is a different task (cube-to-box) on different hardware from this project's actual target task below — kept as a format reference, not the dataset to train on.
- A second comparison dataset is `data/external/so100_dataset50ep/`, sourced from [RasmusP/so100_dataset50ep](https://huggingface.co/datasets/RasmusP/so100_dataset50ep). It contains laptop/phone views and is not the preferred wrist-camera source.
- **The actual target-task dataset is `data/local/lerobot_dataset/`** (gitignored): 29 real episodes, 20,001 frames, built from the app's own recorded teleoperation demonstrations (`data/local/episodes/`, via the in-app "Wireless Tele-Op & Vision" recorder → `POST /api/episodes` → `robot_learning/generate_episode_contact_sheets.py` for human curation review → `robot_learning/build_lerobot_dataset.py` to convert). Task string: `"Pick up a shape piece and insert it into its matching hole on the puzzle board."` Camera keys are `observation.images.overview`/`observation.images.wrist` (not `top`) to match this app's own naming. fps 30, `observation.state[t] = action[t-1]` (one-step shift — recordings only capture commanded targets, not measured follower position).
- **This dataset's action values are already in the app's own `JointState` degrees/percent convention**, not LeRobot's raw-servo-tick-derived convention (`build_lerobot_dataset.py`'s `joints_to_action()` packs `metadata.json`'s commanded-target values straight in, with no pass through LeRobot's tick-based `DEGREES`/`RANGE_0_100` formulas). This means any policy trained on it predicts actions that map back to `JointState` fields with just renaming (inverse of `JOINT_NAME_MAP`) and limit-clamping — no LeRobot motor-bus tick-conversion module is needed for this dataset's checkpoints, unlike what earlier planning (the 2026-08-03 design spec) assumed for a `lerobot-record`-sourced dataset. Verified by replaying a recorded episode's dataset action column back through the inverse mapping and confirming an exact numeric match against the original recorded values at multiple points in the episode.
- LeRobot is installed in the ignored `.venv-lerobot/` Python 3.12 environment (also needs the `lerobot[smolvla]` extra — `transformers` — installed separately for SmolVLA work; not part of the base `lerobot` install). **MPS is available on this machine** (M2 Max, confirmed via `torch.backends.mps.is_available()` → `True`) — the earlier claim that no accelerator was present was stale; use `--policy.device=mps`, not `cpu`, for real training runs. Redirect the HF datasets cache with `HF_DATASETS_CACHE=.cache/hf-datasets`.
- **Keep the machine awake for long training runs.** A 2000-step SmolVLA run on 2026-08-06 took ~5 hours wall-clock instead of the ~1 hour its per-step rate predicted — the log shows normal ~2s/step behavior for roughly the first half, then a huge slowdown (30-98s/step) consistent with the machine sleeping/idling for an extended unattended stretch. Use `caffeinate` or disable display/system sleep for any run expected to take more than a few minutes unattended.
- A local ACT baseline was trained from the primary (borrowed) dataset with a 40-episode train / 10-episode held-out split for 500 steps. Its checkpoint is under the ignored `outputs/train/act_so100_pickplace_500/checkpoints/000500/pretrained_model/` directory. Offline evaluation on 100 held-out samples produced mean absolute error 15.335 action units — an undertrained baseline, not deployment-ready. A second ACT smoke run (10 steps, loss 86.6→21.8) was later trained on the real target-task dataset at `outputs/train/act_shape_sort_smoke/checkpoints/000010/` purely to verify the training pipeline works — also not deployment-ready, and ACT has no language input regardless (`observation.state` plus two images only), so it cannot respond to a prompt at all.
- **SmolVLA fine-tuning** (`lerobot/smolvla_base`, language-conditioned, ~450M params) is the actual prompt-responsive policy. Checkpoints: `outputs/train/smolvla_shape_sort_500/checkpoints/000500/` (500 steps, final loss ~0.13-0.2) and `outputs/train/smolvla_shape_sort_2000/checkpoints/002000/` (2000 steps, final loss 0.127). **The pretrained checkpoint expects exactly 3 named camera inputs** (`camera1`/`camera2`/`camera3`); this dataset has 2. Fix used at both train and inference time: `--rename_map='{"observation.images.overview":"observation.images.camera1","observation.images.wrist":"observation.images.camera2"}' --policy.empty_cameras=1`. At inference, only `camera1`/`camera2` need to be supplied in the observation batch — `SmolVLAPolicy.forward()` (`modeling_smolvla.py:340-376`) automatically blank-pads exactly one missing declared camera; you do not need to fabricate a `camera3` or `empty_camera_0` tensor yourself.
- **Extending training beyond a finished checkpoint needs reconfiguring, not just adding steps.** `lerobot-train`'s LR schedule is tuned to decay to near-zero by the configured `--steps` target (`lr:2.5e-06` by step 2000, down from ~1e-4 early on) — running more steps against the same finished config will not continue learning meaningfully. A longer run needs its own schedule configured for the new target step count from the start.
- `robot_learning/run_policy_prompt.py` runs a SmolVLA checkpoint once against a live camera snapshot pair + current joint state + a typed prompt, and writes a Sequence Studio-compatible keyframe JSON (`--output`, default `outputs/policy-prompt-sequence.json`) — load it into Sequence Studio, preview in the 3D twin, then arm and play through the existing Arm Motion gate exactly like any other sequence. No new hardware-control code or safety gate was built; this deliberately reuses the existing recorder/Sequence Studio/arming pipeline instead of the standalone policy-server/dead-man-switch runtime the 2026-08-03 design spec described (that fuller runtime was explicitly not built — deferred, not started).
- **Verified on real hardware on 2026-08-06**: prompting both checkpoints with `"pick the green disc and put it into place"` against a real starting scene produced genuine task-relevant behavior — the arm oriented toward and looked at the named object — but neither checkpoint completed an actual pick. This is expected: 29 episodes and ≤2000 steps is light for a 450M-parameter VLA fine-tune. Next steps (not started): record more demonstrations, and/or a longer run with its own properly-configured LR schedule.
- The Dataset Lab UI provides read-only dataset metadata and top/wrist video playback for the *borrowed* `svla_so100_pickplace` dataset only. `robot_learning/generate_policy_preview.py` creates `outputs/policy-preview.json` from that dataset's ACT checkpoint; the Dataset Lab can load that preview into the 3D view and Sequence Studio. It has not been updated to point at the real target-task dataset/checkpoints.

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
