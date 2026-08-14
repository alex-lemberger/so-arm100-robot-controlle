# Linux Hardware Setup — start here after the physical move (2026-08-11)

## Why this doc exists

User decided to consolidate real-robot work and Isaac Sim work onto this Linux
workstation (RTX 5070) instead of moving the arm's USB cables to reach it (the earlier
"blocked on longer USB cables" plan) — the PC itself is being physically relocated to
where the robot already sits instead. That requires a shutdown, physical move, and
restart. **This doc is what the next session should read first, right after that
restart**, before touching either Isaac Sim or the real arm.

Everything Isaac-side (Docker images, replay/synthetic-gen/export pipeline, Datasets
A/B/C) is unaffected by the move and already covered in `docs/current_system.md` +
`linux-session-handover-2026-08-11.md`. This doc is only about the NEW part: getting
the physical SO-ARM100 (follower + leader) working through this machine for the first
time.

---

## What's already true on this machine (checked 2026-08-11, before the move)

- **`real-robot:latest` (62GB Docker image) already has everything needed for
  hardware control**: `pyserial`, the Feetech servo SDK (`scservo_sdk`), OpenCV
  (4.11.0), `lerobot`'s `FeetechMotorsBus`, and all the CLI tools —
  `lerobot-teleoperate`, `lerobot-record`, `lerobot-find-port`,
  `lerobot-find-cameras`, `lerobot-calibrate`. Confirmed by running each inside the
  container. No new image needs building.
- **This machine has no native Python environment** (established earlier, still
  true) — so unlike Mac, where hardware scripts run via `~/lerobot/.venv/bin/python`
  natively, on Linux everything must run through `real-robot:latest` with explicit
  USB device passthrough (`docker run --device=/dev/ttyUSB0 ...`).
- **User `alex` is NOT in the `dialout` group.** Serial port access
  (`/dev/ttyUSB0` / `/dev/ttyACM0`, typically group `dialout`, mode 660) will fail
  with permission denied until this is fixed. Fix with either:
  ```bash
  sudo usermod -aG dialout alex   # then log out/in (or reboot) for it to take effect
  ```
  or a udev rule if you'd rather not add the user to that group.
- **Two things on this machine are decoys — do NOT reuse them:**
  - `teleop-docker:latest` (28.8GB Docker image) and
    `~/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/leader_arm_1.json`
    are both leftovers from the unrelated third-party `Sim-to-Real-SO-101-Workshop`
    repo (dated 2026-07-15, predates this project). That's the **SO-101** arm, not
    our **SO-100** — same trap already documented for the Isaac USD assets in
    `docs/current_system.md`. Don't calibrate against or connect through either of
    these for our robot.

## What needs to come over from Mac (the real robot's actual config)

**Done, 2026-08-11**: user copied both calibration files into
`so-arm100/docs/calibration/` as a staging drop (via the shared drive), from where
they were placed at LeRobot's actual read path,
`~/.cache/huggingface/lerobot/calibration/`:

| What | Path | Notes |
|---|---|---|
| Follower calibration | `robots/so_follower/white.json` | id=`white`. In place. |
| Leader calibration | `teleoperators/so_leader/black_20260801.json` | id=`black_20260801`, type=`so100_leader`. In place. |

**Watch out**: the staging drop also included `teleoperators/so_leader/black.json` --
an OLDER leader calibration (mtime 2026-07-10 vs `black_20260801.json`'s 2026-08-05)
with different homing offsets. `robot_learning/loop.py` uses id=`black_20260801`
specifically -- that's the correct one, already in place above. `black.json` was
deliberately NOT copied into the LeRobot cache; it's still sitting in
`so-arm100/docs/calibration/teleoperators/so_leader/` if you ever need to check it,
but don't calibrate against it by accident.

Port paths and camera indices are **not portable across machines** — Mac uses
`/dev/cu.usbmodemXXXXXXXX` (e.g. follower was `/dev/cu.usbmodem5AE60582701`, leader
`/dev/cu.usbmodem5B140329561`); Linux will assign `/dev/ttyUSB0`/`/dev/ttyACM0` or
similar instead, in whatever order the OS enumerates them. Camera indices
(overview=1, wrist=0 on Mac, verified 2026-08-08) will likely also renumber. Both
need to be re-detected fresh on Linux — don't assume the Mac values.

## Checklist for the next session, in order

1. ~~**Confirm the physical move landed cleanly**~~ — **done, 2026-08-11**:
   `nvidia-smi` (RTX 5070, driver 580.159.03) and `docker run --rm hello-world`
   both work fine.
2. ~~**Fix `dialout` group membership**~~ — **done, 2026-08-11**: `alex` is in
   `dialout`.
3. ~~**Plug in the follower/leader, find the new ports**~~ — **done, 2026-08-11**.
   `lerobot-find-port` itself couldn't be used non-interactively (it needs a real
   TTY for the unplug-and-press-Enter step; failed with `EOFError` when run
   without one). Identified ports manually instead by diffing
   `ls /dev/ttyACM*` before/after unplugging each arm:
   - Follower: **`/dev/ttyACM0`**
   - Leader: **`/dev/ttyACM1`**
   - No `/dev/ttyUSB*` shows up on this machine — both arms enumerate as
     `ttyACM*`. Adjust `--device` flags accordingly (not `ttyUSB0` as
     originally guessed above).
4. ~~Copy the two calibration files from Mac~~ — **done**, see above.
5. ~~**Find camera indices**~~ — **done, 2026-08-11**, via
   `lerobot-find-cameras opencv` with a volume-mounted output dir (so the
   captured images survive `--rm`) and visually matching each snapshot:
   - Overview (workspace shot): **`/dev/video0`**
   - Wrist (looking up between gripper fingers): **`/dev/video2`**
   - `/dev/video1` and `/dev/video3` are just metadata nodes for the same two
     physical UVC cameras — only the even-numbered ones are real capture
     devices.
6. ~~**Run the existing read-only probe**~~ — **done, 2026-08-11, PASS**. Two
   bugs had to be fixed first, both the same class of issue — this lerobot
   version renamed things and older references still used the old names:
   - `robot_learning/probe_native_hardware.py` imported
     `lerobot.robots.so_follower`; the installed package has it at
     `lerobot.robots.so100_follower` (fixed in the script).
   - The calibration files copied from Mac lived under
     `calibration/robots/so_follower/white.json` and
     `calibration/teleoperators/so_leader/black_20260801.json`; this lerobot
     version reads calibration from `.../robots/so100_follower/<id>.json` and
     `.../teleoperators/so100_leader/<id>.json` instead. Fixed by copying (not
     moving — originals left in place, harmless) both files into
     correctly-named sibling directories. **If calibration ever needs
     re-copying from Mac, copy into the `so100_follower`/`so100_leader`
     directories, not `so_follower`/`so_leader`.**
   Command used (run from `so-arm100/`):
   ```bash
   docker run --rm --device=/dev/ttyACM0 --device=/dev/ttyACM1 \
     --device=/dev/video0 --device=/dev/video2 \
     -v "$(pwd)/..:$(pwd)/.." \
     -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
     -w "$(pwd)" \
     real-robot:latest python robot_learning/probe_native_hardware.py \
     --port /dev/ttyACM0 --id white --overview-index 0 --wrist-index 2 \
     --width 640 --height 480
   ```
   Result: sane joint readings on all 6 motors, both camera frames non-black
   (mean ~163-165), `PASS: follower and both cameras reachable through
   LeRobot's native API.`
7. ~~**Try `lerobot-teleoperate`**~~ — **done, 2026-08-11, PASS**. Leader
   movement mirrored cleanly onto the follower. Command used (needs `-it` for
   a real TTY, same as `lerobot-find-port`):
   ```bash
   docker run --rm -it --device=/dev/ttyACM0 --device=/dev/ttyACM1 \
     -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
     real-robot:latest lerobot-teleoperate \
     --robot.type=so100_follower --robot.port=/dev/ttyACM0 --robot.id=white \
     --teleop.type=so100_leader --teleop.port=/dev/ttyACM1 --teleop.id=black_20260801
   ```
   **Hardware setup is now fully verified on Linux end-to-end** (ports,
   calibration, cameras, read-only probe, and live teleoperation). Ready for
   the §20-23 failure-driven-correction loop (real eval → failure capture →
   human correction via teleop → simulation augmentation → retrain) mentioned
   in the intro above.

## Once hardware works: what the combined machine actually unlocks

This is the point of the move — with both Isaac Sim and the real arm on one
machine, the §20-23 loop (real eval → failure capture → human correction via
teleop → simulation augmentation → retrain) no longer needs a Mac↔Linux handover
per iteration. That loop, and real-world evaluation of whatever comes out of the
§19-21 training comparison (Windows), are the natural next pipeline steps once
hardware is verified working here.
