# Linux session handover: mid-eval, blocked on a driver-mismatch reboot (2026-08-12)

## Why this doc exists

Mid-way through the §19-21 hardware eval session (see
`handover-windows-to-linux-2026-08-12.md` for how we got here), `nvidia-smi` started
failing with `Driver/library version mismatch`. Root cause: `unattended-upgrades` (or
similar) upgraded `nvidia-driver-580-open` from 580.159.03 to 580.173.02 via apt at
`2026-08-12 10:36:13`, live, mid-session, without reloading the kernel module. Confirmed
via `cat /proc/driver/nvidia/version` (still reports the old 580.159.03 kernel module)
vs `dpkg -l | grep nvidia-driver` (580.173.02 installed) and `/var/log/apt/history.log`.
Fix requires a reboot (`sudo reboot` -- no passwordless sudo on this box, has to be run
by the user, not by Claude). **A reboot was requested but not yet confirmed done when
this doc was written** -- next session, confirm `nvidia-smi` works before anything else.

## State BEFORE the reboot (should still all be true after, but verify)

- **`lerobot-train:latest` Docker image is built and fully verified.** Loads a
  Windows-trained SmolVLA checkpoint, all hardware-path imports resolve (deepdiff,
  scservo_sdk/feetech-servo-sdk, pyserial, opencv, SO100Follower), CUDA passthrough
  confirmed (before the driver broke). `so-arm100/Dockerfile.lerobot` is the source;
  5 build iterations were needed to get here -- see
  [[project-isaac-hardware-gotchas]] memory for the full bug list (wrong base image
  tag, wrong pip package name, missing deepdiff, venv_bin path mismatch, unnecessary
  hardware/evdev/gcc detour). **Untracked in git** (`git status` shows `??
  Dockerfile.lerobot`) -- not committed.
- **`robot_learning/loop.py`'s `CONFIG` was fixed twice this session and needs
  RE-VERIFICATION after the reboot, not blind trust:**
  - Ports: currently set to follower=`/dev/ttyACM1`, leader=`/dev/ttyACM0`. This is
    the OPPOSITE of what `docs/linux-hardware-setup-2026-08-11.md` found on
    2026-08-11 (follower=ttyACM0, leader=ttyACM1) -- USB enumeration order flipped
    once already between 08-11 and today, discovered the hard way (an eval run threw
    `Overload error` while trying to disable torque on what the code thought was the
    follower; turned out to be the physical leader). **A reboot is exactly the kind
    of event that can reshuffle this again.** Before trusting `CONFIG` or running
    eval: `ls /dev/ttyACM*`, physically unplug the follower arm's USB cable, `ls
    /dev/ttyACM*` again -- whichever node disappeared is the follower. Update
    `CONFIG` in `loop.py` if it doesn't match what's currently there.
  - Cameras: `fourcc: "MJPG"` added to both `overview` (`/dev/video0`) and `wrist`
    (`/dev/video2`) -- uncompressed YUYV can't hit 30fps at 1280x720 over USB (maxes
    at 10fps), MJPG can. This should NOT need re-verification (not port/enumeration
    related), but if camera indices also shift after reboot, re-run
    `lerobot-find-cameras opencv` the way 08-11's setup doc did.
- **Calibration is fine.** Confirmed by directly diffing the two calibration JSON
  files (`~/.cache/huggingface/lerobot/calibration/robots/so100_follower/white.json`
  vs `.../teleoperators/so100_leader/black_20260801.json`) -- both still distinct,
  both still dated 2026-08-11 (untouched by today's session). The "Writing
  calibration file associated with id X to the motors" log line pushes the JSON's
  values onto the physical servo's EEPROM registers, not the reverse -- so even
  though the mis-wired eval run briefly pushed the follower's (`white`) calibration
  onto the physical leader's servos, a single correct `lerobot-teleoperate` connect
  (which the user ran and confirmed "ok working") re-pushes the leader's own
  correct offsets back. No file corruption occurred at any point.
- **Training (§19) is done** -- Windows finished all three runs (A/B/C). Eval loss:
  A=1.296 (overfit), B=0.818, C=0.016. See `handover-windows-to-linux-2026-08-12.md`
  for the full table and checkpoint paths.
- **A convenience script exists**: `so-arm100/run_eval_a.sh` runs the Run A eval
  command (single short command, avoids terminal line-wrap corrupting a long pasted
  `docker run` one-liner -- happened twice this session). Written but not yet
  successfully completed a full run -- every attempt so far has been blocked by one
  fixable issue after another (missing deps, wrong ports, camera fps, now the driver).

## Checklist for next session, in order

1. Confirm the reboot happened and fixed the driver:
   ```bash
   nvidia-smi   # should show the RTX 5070 cleanly, no version-mismatch error
   docker run --rm --gpus all lerobot-train:latest python -c \
     "import torch; print(torch.cuda.is_available())"   # should print True
   ```
2. Re-verify the follower/leader port mapping with the unplug test (see above) --
   do NOT assume `loop.py`'s current `/dev/ttyACM1`=follower still holds.
3. If ports changed, edit `CONFIG` in `robot_learning/loop.py` (and
   `run_eval_a.sh` if the docker `--device` flags need to change, though they
   list both ports so order doesn't matter there).
4. Run `./run_eval_a.sh` from `so-arm100/`. This is Run A (10 real demos,
   `smolvla_grasp_v1_real10_30000`, checkpoint 030000) -- expected to perform
   poorly (eval loss 1.296, likely overfit) which is itself useful: confirms the
   eval loop works before spending time on B/C.
5. User scores each episode by eye (k/N success) -- no auto-scoring exists. Fill
   in the results table in `handover-windows-to-linux-2026-08-12.md`.
6. Repeat for B (`smolvla_grasp_v1_real50_30000`) and C
   (`smolvla_grasp_v1_mixed_10r_100s_30000`), both checkpoint 030000. Consider
   copying `run_eval_a.sh` to `run_eval_b.sh`/`run_eval_c.sh` with the checkpoint
   path swapped, for the same paste-safety reason.
7. This table is the answer to `AGENTS_NEW.md` §32, the project's primary
   research question.

**How to apply:** Read this doc first if resuming this session's work. Don't re-debug
anything already listed above as fixed -- check [[project-isaac-hardware-gotchas]]
memory first if something looks like a repeat of one of these bugs.
