# Session handover — 2026-08-17

Durable facts are in `docs/RUNBOOK.md`, which gained a **"Before every session"**
section today — read that first. This is what happened, what it cost, and what is
still not done.

## The headline

The session set out to improve the policy and spent five hours re-establishing a bench
that had been working that morning. **The hardware was healthy the entire time.**

Root cause: at some point a `c` was answered at lerobot's calibration prompt —

> `Press ENTER to use provided calibration file associated with the id white, or type 'c' and press ENTER to run calibration:`

— which ran a *fresh* calibration, wrote newly measured values into the follower's servo
EEPROM, and was interrupted before saving. So every calibration file on disk kept its
Aug 11 values while the hardware drifted away from them. Everything downstream followed
from that: the app's "Calibration mismatch on S1..S6" was **correct**, and read like a
software bug for hours.

The generalisable lesson, in Alex's words: hardware state is not software state. It is
persistent, invisible to git, owned exclusively by one process, and changed by the act of
touching it. Treat the robot like a production database, not a library — never assume its
state, query it. Hence `./preflight.sh`.

## Do this first

```bash
./preflight.sh          # GO/NO-GO: port ownership, device identity, calibration, cameras
```

Then in the app: **reload the page** — the follower now auto-connects and self-verifies
(commit `c5039fe`). This is **untested in a browser**; typecheck passes but Chrome was
holding the port when it was written. Expected console output:

```
Auto-connect: N granted adapter(s) found; identifying the follower by its calibration.
Auto-connect: follower identified by its own calibration. Verifying the bus…
Verified 6/6 Feetech servos: ...
Auto-connect done. Motion is NOT armed -- arm it yourself with the arm in view.
```

If serial permissions were reset, it says so and you grant the port by hand **once**.

Then, before committing to 60 episodes:

```bash
# record ONE episode in the app, then:
python robot_learning/loop.py build --name circle_insert_smoke
```

`GamepadVisionOverlay.tsx:436` records that **two previous sessions lost a whole batch**
to a defect found at dataset-build time. Smoke-test one episode through the conversion
and check `observation.state` holds real measured ticks, that frame counts and timestamps
line up with the video, and that the two camera streams are not swapped.

## Decisions made this session — do not re-litigate

- **Re-record from scratch, CIRCLE ONLY.** ~60 episodes, one prompt
  (`Insert the circle piece into its matching hole.`), every episode ending **seated**.
- **Placement varied BY HAND, by eye. Not surveyed, not in millimetres.** This is
  standard LeRobot practice; ~50 episodes/task is the documented floor. `POSITION_GRID`
  now cycles `near/mid/far × left/centre/right`, moving the piece every episode.
- **Recording happens in the REACT APP**, not `loop.py record`. Alex was explicit twice.
  `loop.py build` converts app recordings into a LeRobot dataset.
- **The mm/homography apparatus is PARKED.** `workspace_frame.py`,
  `scripts/calibrate_workspace.py`, `calibrate_workspace.sh`,
  `tests/test_workspace_frame.py` — built, tested, still **untracked**. It only answers
  "does success depend on object position in millimetres", which is diagnostic
  scaffolding, not a training requirement. Do not resume it unasked.
- **Arms are identified by USB adapter serial, never by `/dev/ttyACM*` number.**

## What was measured

| | |
|---|---|
| Both arms, PING + register reads | **6/6 at 1,000,000 baud**, stable over repeated runs |
| DTR/RTS | irrelevant — 6/6 in all four combinations |
| Follower calibration vs `white.json` | **matches, register by register** (repaired this session) |
| All six EEPROMs | `Lock=0`, **left UNLOCKED** — a warning, not a blocker |
| Port mapping | **flipped**: follower white = `ttyACM0`, leader = `ttyACM1` |
| USB stability | **one** enumeration event all session (the deliberate replug) |
| `circle_grasp_v1` contents | 50 eps `Insert the circle piece…`, 31 eps `Pick up the circle piece` |

Insertion **is** demonstrated in the old data — 26,078 of its 31,541 frames. The
foundation was never missing, only thin and single-shape.

## What was built and fixed

| commit | |
|---|---|
| `669b0a2` | `POSITION_GRID` varied left/right only — never near/far. Now 3×3, moves every episode |
| `9210d88` | wrist peg check demanded hue>60; the peg's green measures **44**, so it matched 8 pixels in a whole frame and reported the peg missing |
| `1c49749` | `logMessage` wrote only to an in-app drawer — the app was silent in devtools. Plus unplug detection, dead-read-loop teardown, wire tracing |
| `9caea12` | Disconnect leaked the port descriptor; Chrome held `ttyACM0` for 20 min after it |
| `bc938d8` | ports were hardcoded in **three** files; `teleop_check.sh` and `home_arm.py` now read `loop.py CONFIG` |
| `814ccf9` | leader badge collapsed 3 states into `LEADER_UNVERIFIED`; Verify hid `0/6`; a 20 Hz caption over a 30 Hz loop |
| `07eb7f4` | **`./preflight.sh`** + `scripts/preflight_bus.py`; `teleop_check.sh` ENTER-not-`c` banner |
| `c5039fe` | follower auto-connects and self-identifies on load |

## What NOT to re-litigate

- **The hardware is fine.** Servo power, bus cable, baud rate, adapter choice, DTR/RTS —
  all measured and eliminated. Do not chase them again.
- **The app's serial logic is correct.** Connect, write, read, parse and dispatch were all
  read and confirmed against a live wire trace.
- **`teleop_check.sh` did not corrupt the calibration.** It was blamed; that was wrong —
  its values are byte-identical to `white.json`.
- **The peg detector's hue floor must be 30, not 60.** Still unfixed in
  `scripts/analyse_placement_generalization.py` and `robot_learning/align_board.py`.
- **Device-node mtime is NOT creation time.** Misread as evidence twice. Use
  `journalctl -k` for real enumeration events.

### Four theories that data killed — don't redo them

1. `teleop_check.sh` overwrote the calibration (files are identical)
2. Half-duplex packet echo resolving the promises (no echoes on the wire; every TX got one clean status reply)
3. Chrome handing out a phantom/stale port (its fd was newer than the device node)
4. USB re-enumeration on teleop shutdown (no kernel events at all)

## The one open problem

**Chrome's WebSerial versus this CH-series adapter (`1a86:55d3`) at 1 Mbaud.** `open()`
succeeds, the first `read()` throws *"The device has been lost"*, and the connection is
dead. Reproducible, and independent of the hardware.

- The only **proven** recovery is a **physical replug of the adapter**, after which the
  app worked and read every register correctly.
- It correlates with **alternating between the app and the Python stack** in one session.
  Pick one stack per session.
- Not diagnosed. `chrome://device-log` is the obvious next look and has never been read —
  it holds Chrome's own errno. Cannot be opened by an agent; a human must.

## Still not done

- **The 60 episodes.** Nothing was recorded today.
- **Insertion is not measured.** `analyse_placement_generalization.py` tops out at
  `transport` (peg left the table region with the gripper closed). It cannot see whether
  the piece was *seated*, which is the whole task definition. This gap matters more than
  it looks: a run that carries the peg and drops it scores identically to a success.
- **Re-lock the servo EEPROMs** (`Lock=1`), or accept the warning. Left undone
  deliberately — it is a hardware write, and the bus had just thrown a comms error.
- **The gripper glitch.** `Incorrect status packet` on `id_=6` during the calibration
  write. Transient, worked immediately after. Servo 6 is last in the daisy chain; if it
  recurs, check that cable before suspecting anything else.

## Traps that cost real time today

- **ENTER, never `c`** at lerobot's calibration prompt.
- **One stack owns a port at a time.** Symptoms look nothing alike: `Failed to open
  serial port`, `The device has been lost`, `Errno 16 Device or resource busy`,
  `Could not connect on port`. All the same problem. **Check `docker ps` too** — a
  container held the port for eight minutes while a host `/proc` scan said "free".
- **A single hardware read can be plausibly wrong.** One un-flushed, unvalidated read
  returned calibration values that looked exactly right, were wrong, and were trusted as
  ground truth for an hour. `preflight_bus.py` now reads everything twice and reports
  `UNSTABLE` rather than picking one.
- **Secure primary state before theorising.** Every wrong turn today was a
  secondary-layer theory standing on unverified primary state.
