# Linux session handover: DAgger correction cycle, Run D mid-training (2026-08-12)

## Why this doc exists

Mid-session, training Run D (see below) is paused via `docker pause` and the user
asked whether the machine can be powered off. **Short answer: not yet, without
losing all training progress.** See "Critical: do not power off" below before
doing anything destructive.

## Update: training stopped cleanly, safe to power off

Run D was resumed from pause, ran to step ~21,279/30,000, then stopped
(`docker stop c09750a4f8a2`) before power-off. **`checkpoints/020000` is
confirmed complete and usable** (`pretrained_model/model.safetensors` +
configs all present) -- this is a real, disk-persisted checkpoint, safe to
power off after. Steps 20,000-21,279 (the last ~10 minutes of training beyond
the checkpoint) are lost; the run did not reach its 030000 final checkpoint.

**Next session: resume training from 020000 rather than restarting from
scratch.** Two ways to continue, pick one:
- Fine-tune further from the checkpoint as a new `--base`:
  `--base outputs/train/smolvla_grasp_v1_dagger1_30000/checkpoints/020000/pretrained_model`
  with fewer remaining steps (e.g. `--steps 10000` for the last third), OR
- Just eval `checkpoints/020000` as-is first -- it's a real 20k-step SmolVLA
  fine-tune on the DAgger-corrected dataset, may already be informative before
  spending more GPU time getting to 30k.

### How to check / resume / stop (reference, from when it was still running)

```bash
docker ps -a --filter "id=c09750a4f8a2" --format "{{.ID}} {{.Status}}"   # now Exited
docker pause / docker unpause <id>    # only useful while a container is Up
docker stop <id>                       # clean stop (what was actually done)
```

**If restarting training from scratch is preferred instead**, relaunch with:
```bash
cd so-arm100
docker run --rm --gpus all --ipc=host \
  -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
  lerobot-train:latest \
  python robot_learning/loop.py train \
    --dataset grasp_v1_dagger1 --base lerobot/smolvla_base \
    --steps 30000 --batch-size 32 --device cuda
```
**`--ipc=host` is required** -- without it, the DataLoader crashes almost
immediately with `RuntimeError: unable to allocate shared memory(shm)`. This is
the first real multi-worker training job run through the `lerobot-train` Docker
image (earlier A/B/C training happened natively on Windows, not in this
container), so this gotcha hadn't surfaced before today.

## What happened this session (in order)

1. **Confirmed the post-reboot driver fix** (`nvidia-smi` clean, CUDA passthrough
   verified) and re-verified follower=`/dev/ttyACM1`/leader=`/dev/ttyACM0` via the
   unplug test -- see `linux-session-handover-2026-08-12-post-driver-reboot.md`
   for that part.
2. **Ran hardware eval for all three §19-21 checkpoints (A/B/C).** All scored
   **0/20**. Fixed a `rollout_latest` FileExistsError collision along the way by
   giving each run a distinct `--tag` (`run_a`/`run_b`/`run_c`).
3. **Built `robot_learning/extract_eval_frames.py`** (new, uncommitted): pulls the
   last frame of each episode from a rollout dataset's own recorded video via
   PyAV, so eval success/failure can be verified from footage instead of trusting
   only live eye-scoring. Also `extract_one_frame.py`, a small debug helper for
   grabbing a frame at an arbitrary timestamp (used to inspect mid-episode
   behavior).
4. **Key qualitative finding, confirmed by video review of A/B/C**: every
   checkpoint shares the same failure mode -- the policy reaches and grasps the
   piece successfully (confirmed via mid-episode frames, including via the wrist
   camera which clearly shows both the grasped piece and the target hole
   simultaneously, ruling out an occlusion/sensing explanation), but never
   transports it to the puzzle board. It sets the piece back down near its start
   position instead. This held regardless of eval loss (0.016 to 1.296) -- **held-out
   loss does not predict hardware success on this task.** Diagnosis: classic
   behavior-cloning covariate shift -- the "just grasped, need to travel" state is
   underrepresented in demo frames, so the policy has no recovery behavior once
   its own execution drifts slightly off the demonstrated trajectory.
   Full writeup: `docs/handover-windows-to-linux-2026-08-12.md`, "Scoring method"
   section.
5. **Ran a DAgger correction session** (`robot_learning/loop.py dagger`, new
   script `run_dagger_c.sh`) on checkpoint C, targeting exactly the transport
   failure. 10/10 correction episodes saved (4,172 frames) to
   `rollout_dagger_transport`. Spot-checked 4 episodes via the frame-extraction
   tool -- all show clean, successful insertions.
6. **Merged the corrections into a trainable dataset** (`grasp_v1_dagger1`:
   circle_grasp_v1_mixed_10r_100s + the DAgger corrections, 120 episodes, 66,124
   frames). This needed three schema fixes, all handled by new script
   `robot_learning/tag_source_type.py` (uncommitted) plus one direct `info.json`
   metadata edit:
   - `episode_source_type_id` (real/synthetic provenance tag, present on the
     mixed dataset, absent on the DAgger dataset) -- added as `REAL_HUMAN` (0),
     since these corrections are genuinely real hardware data.
   - `observation.images.wrist` -- present on the DAgger dataset (because
     `cmd_dagger`/`cmd_eval` record whatever `CONFIG['cameras']` has configured
     on the robot, currently both), absent on A/B/C (all built from the
     app-recording pipeline, overview-only). Dropped from the corrections since
     the policy being corrected never consumed a wrist camera input. **Note: this
     means A, B, and C are NOT confounded by camera setup -- all three are
     identically single-camera, this was purely an artifact of how `cmd_dagger`
     records vs. how the app-recording pipeline built the original datasets.**
   - Video encoder metadata (`info.json`'s per-feature `info` dict) differed
     between the offline export pipeline and live `lerobot-rollout` recording
     (extra encoder bookkeeping fields, one differently-named key). Purely
     descriptive, not a pixel-data difference (both AV1/yuv420p/720x1280/30fps) --
     normalized to match A/B/C's schema so `aggregate_datasets`'s strict
     `validate_all_metadata` would pass.
   - Also found and worked around: `loop.py`'s `cmd_build`/`cmd_merge` hardcode
     `CONFIG["venv_bin"] / "python"` (`~/lerobot/.venv/bin/python`), which doesn't
     exist in the `lerobot-train` Docker image (only the `lerobot-*` console
     scripts do). Called `merge_datasets.py`/`tag_source_type.py` directly with
     `python3` instead. **This will bite the next person who runs `loop.py merge`
     or `loop.py build` through this Docker image -- worth fixing in `loop.py`
     itself if it comes up again** (e.g. `bin_path` could fall back to `python3`
     on PATH when the venv one is missing).
7. **Launched Run D**: SmolVLA base fine-tuned on `grasp_v1_dagger1`, same recipe
   as A/B/C (30k steps, batch 32) for a fair comparison. First attempt crashed
   immediately on the shared-memory issue above; second attempt (with
   `--ipc=host`) is the one currently paused at step ~11,000.

## Unresolved: React app can't arm hardware motion

Separate from the Python/loop.py pipeline -- there's a React app
(`so-arm100/`, `npm run dev` -> `tsx server.ts`, port 3000) that connects
directly to the follower arm via the browser's Web Serial API (no Python
bridge) for manual jogging / sequence authoring. `ConnectionBar.tsx` /
`App.tsx` / `src/utils/feetech.ts` implement this.

**Symptom**: "Verify Servos" doesn't lead to "Arm Motion" becoming available,
even after trying both `/dev/ttyACM*` ports in the browser's port picker.

**Ruled out so far**:
- Dev server is up (port 3000), hardware ports are free (nothing else holds
  `/dev/ttyACM0`/`1`), user is in the `dialout` group, device permissions are
  correct (`crw-rw---- root dialout`).
- `requestPort()` has no VID/PID filter, so the picker should list all serial
  devices.
- `.env.local`'s `VITE_FEETECH_CALIBRATION` was diffed field-by-field against
  the live `~/.cache/huggingface/lerobot/calibration/robots/so100_follower/white.json`
  -- **exact match**, so the calibration conversion itself is not the bug.
- Tried connecting to the other USB port (in case of a leader/follower mixup in
  the picker, which bit the Python side earlier this session) -- **still fails**,
  so it is probably not simply a swapped-port selection.

**Not yet tried**: reading the app's live console log (there's an in-app
"Serial Console Log" via the terminal icon in the header, and/or browser
devtools console) to see the actual found/matched servo counts from
`handleVerifyFeetechBus` in `App.tsx` (~line 494) -- it logs a
PING-per-servo and a separate limits/offset register match per servo, so the
console should say exactly which servos failed to match and how. A
`claude-in-chrome` session was started to debug this live (browser tools
confirmed the native OS port-picker dialog can't be automated -- it needs a
real user click) but was paused before finishing; picking this back up should
start with reading that console log rather than re-guessing.

## Checklist for next session

1. Decide on the power-off tradeoff above before touching the machine.
2. If resuming: `docker unpause c09750a4f8a2`, watch for step 20,000 (first
   checkpoint) and step 30,000 (done).
3. Once Run D's `checkpoints/030000` exists, eval it on hardware the same way as
   A/B/C (`robot_learning/loop.py eval`, review with `extract_eval_frames.py`).
   This is the actual test of whether the DAgger correction round fixed the
   transport failure. Add a "Run D" row to the results table in
   `docs/handover-windows-to-linux-2026-08-12.md`.
4. Pick back up the React app hardware-connect debugging (see above) --
   start with the in-app console log / browser devtools console, not another
   guess-and-check port cycle.
