# Linux session handover: pre-reboot, 2026-08-14

## Why this doc exists

Session ended with a planned reboot (needed to clear a stuck Chrome serial
port lock — see below). Two things are mid-flight: a training run that
will be lost, and a leader-calibration fix that isn't confirmed yet.
**Read `docs/RUNBOOK.md` first** for anything about ports/docker
commands/gotchas in general — this doc is just what to do next, right now.

## Checklist for next session (in order)

1. **Re-verify ports.** Run `./verify_ports.sh` from `so-arm100/` before
   trusting `robot_learning/loop.py`'s `CONFIG` — a reboot can reshuffle
   `/dev/ttyACM*` assignment. As of before the reboot: follower=`ttyACM1`,
   leader=`ttyACM0`.

2. **Re-verify the leader's calibration was actually fixed.** The leader
   arm's on-servo registers were found to hold the *follower's*
   calibration instead of its own (`black_20260801`) — a regression from
   a 2026-08-12 incident that was diagnosed then but never actually
   fixed. A fix was attempted this session
   (`lerobot-calibrate --teleop.type=so100_leader --teleop.port=/dev/ttyACM0
   --teleop.id=black_20260801`, plain ENTER at the prompt to restore the
   saved file) but got interrupted by the Chrome serial-lock issue before
   it could be confirmed. Check with a read-only script before trusting
   leader teleoperation or the React app's leader connection again:

   ```bash
   docker run --rm --gpus all \
     --device=/dev/ttyACM0 --device=/dev/ttyACM1 \
     -v "$HOME/.cache/huggingface/lerobot/calibration:/root/.cache/huggingface/lerobot/calibration" \
     -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
     lerobot-train:latest \
     python3 -c "
   from lerobot.teleoperators.so_leader.config_so_leader import SOLeaderTeleopConfig
   from lerobot.teleoperators.so_leader.so_leader import SOLeader
   cfg = SOLeaderTeleopConfig(port='/dev/ttyACM0', id='black_20260801')
   leader = SOLeader(cfg)
   leader.bus.connect()
   live = leader.bus.read_calibration()
   for m, c in leader.calibration.items():
       l = live[m]
       ok = 'OK' if (l.homing_offset==c.homing_offset and l.range_min==c.range_min and l.range_max==c.range_max) else 'MISMATCH'
       print(f'{m:14s} {ok}  live={l.homing_offset},{l.range_min},{l.range_max}  file={c.homing_offset},{c.range_min},{c.range_max}')
   leader.bus.disconnect()
   "
   ```
   If it still says MISMATCH, re-run the `lerobot-calibrate` command above
   and make sure to press plain ENTER (not `c`) when prompted.

3. **Relaunch the clean Run D retrain — it was lost to the reboot with no
   checkpoint saved.** Was healthy at step 800/30000 (loss 0.219, ~3
   step/s) when paused for the reboot, but `save_freq=20000` meant
   nothing had been checkpointed yet, so there's nothing to resume from.
   Just relaunch the exact same command:

   ```bash
   cd so-arm100
   docker run -d --gpus all --ipc=host \
     -v "$(pwd)/..:$(pwd)/.." -w "$(pwd)" \
     --name train_dagger1_clean30k \
     lerobot-train:latest \
     python robot_learning/loop.py train \
       --dataset grasp_v1_dagger1 --base lerobot/smolvla_base \
       --steps 30000 --batch-size 32 --device cuda \
       --job smolvla_grasp_v1_dagger1_clean30000
   ```
   This is a single continuous 30k-step run (not a `--base`+`--steps`
   resume) specifically to avoid the LR-scheduler mismatch that likely
   broke the original Run D (`num_decay_steps` staying at 30000 for a
   10000-step resume job). Confirm it's healthy by checking for
   `step:[0-9]+ smpl:` log lines and ~90%+ GPU util — a wall of
   `libtorchcodec`/`libavutil.so` tracebacks at startup is a **known
   benign fallback to PyAV**, not a crash, don't let it look alarming.

   Once it reaches `checkpoints/030000/`, eval it exactly like A/B/C
   (fresh `--tag`, full 20 episodes) — this is the actual test of the
   LR-schedule hypothesis for Run D's original frozen-arm failure.

## What NOT to re-litigate (already resolved this session)

- **Docker calibration mount bug**: fixed, centralized in `hw_docker.sh`.
  Never hand-write a `docker run` for hardware — always
  `./hw_docker.sh <command>` or copy an existing `run_eval_*.sh`.
- **Checkpoint 020000 diagnostic path**: abandoned on purpose, not
  forgotten. It's an intermediate (20k/30k step) snapshot, an inherently
  confounded test case — don't re-eval it to test the LR-schedule
  hypothesis, use the clean retrain above instead.
- **Overload error / arm shaking on checkpoint 020000**: traced to a
  known-low 5.2V servo supply reading (same signature as a 2026-08-05
  incident), but user explicitly said not to chase it as new hardware
  degradation since nothing physically changed — the undertrained
  checkpoint is the more likely explanation, not hardware.
- **GitHub**: `gh` CLI is installed and authenticated as `alex-lemberger`
  on this Linux machine now — no more Windows round-trips needed to push.

## Chrome serial port gotcha (why the reboot was needed)

Chrome's WebSerial `SerialPort` handle can outlive an in-page "Disconnect"
click AND a serial-permissions reset in Chrome settings — only a full
Chrome quit (all windows) reliably releases the OS-level lock. If a
`docker run`/Python process mysteriously can't get exclusive access to
`/dev/ttyACM*` right after using the React app, check
`fuser -v /dev/ttyACM*` for a stray `chrome` PID before suspecting
anything else.

Full detail on all of the above (root-cause diagnosis, exact evidence) is
in Claude's cross-session memory — ask Claude to recall project status if
something here needs more context than this doc gives.
