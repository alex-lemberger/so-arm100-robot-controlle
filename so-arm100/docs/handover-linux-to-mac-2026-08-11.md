# Handover: Linux Isaac Sim session → Mac (2026-08-11)

## What was done on Linux

Continuation of `linux-session-handover-2026-08-11.md` (Tasks 4-6, Stage 1 replay
validation). This session completed the rest of AGENTS_NEW.md's Stage 1 pipeline:

| Task | What | Status |
|---|---|---|
| Task 7 | Table + object scene (`configs/simulation.yaml`, `src/isaac/scene_setup.py`) | Done, verified no physics interference with the passing baseline |
| Task 9 | Synthetic generation (`scripts/generate_synthetic.py`) | Done — 100 synthetic episodes from 10 real parents |
| — | Camera rendering bug (parked in the 6-8-11 session) | **Fixed** — was broken look-at math, not the render binding. `src/isaac/camera_capture.py` |
| Task 18 | Mixed-dataset export (`scripts/export_lerobot_dataset.py`) | Done — real LeRobot-format datasets, run to completion |

**Datasets A/B/C for the §19-21 training comparison all exist now**, on this Linux
machine's disk (gitignored, `data/local/`, not in the repo):

| Dataset | Episodes | Frames | Path |
|---|---|---|---|
| A | 10 real | 5,632 | `data/local/datasets/circle_grasp_v1_real10` |
| B | 50 real | 26,078 | `data/local/datasets/circle_grasp_v1_real50` |
| C | 10 real + 100 synthetic | 61,952 | `data/local/datasets/circle_grasp_v1_mixed_10r_100s` |

These are for the **Windows** training machine (§19-21 policy training), not Mac — a
separate Linux→Windows handover will be needed when that's picked up. Nothing here
needs to move to Mac.

## What to copy to Mac

**Nothing.** Unlike the 2026-08-07 Windows→Mac handover (which moved a large
checkpoint folder by hand), everything this session produced is either:

- **Code** — new/changed files under `so-arm100/{scripts,src/isaac,src/bridge,
  src/kinematics,src/augmentation,configs,docs}`. Small, not yet committed (see
  below) — once pushed, a plain `git pull` on Mac gets it all. None of it runs on
  Mac anyway (it's Isaac Sim / Docker / Linux-GPU specific); it's there for
  reference/continuity, not for Mac to execute.
- **Data** — Datasets A/B/C above, which are gitignored and belong to the
  Linux→Windows leg, not Linux→Mac.

**Not yet committed/pushed** — this session never ran `git commit`. If you want this
work backed up / visible from Mac, say so explicitly (per my own working rules I
don't commit or push without being asked) and I'll stage just the so-arm100-relevant
new/changed files above — there's a large pile of unrelated pre-existing modified
files in this repo (`handwerk-robot-sim/`, `htdp-capture/`, etc.) that predate this
session and I will not touch.

## Known blocker: arm relocation to Linux

Separately discussed this session: moving the physical SO-ARM100 from Mac to this
Linux workstation (to consolidate real-robot + Isaac Sim work for the §20-23
failure-driven-correction loop) is blocked on longer USB cables. Not resolved yet —
the Mac↔Linux split for real-robot work is still in place for now.

## What to do next

- **On Windows** (whenever picked up): train the same policy architecture on
  Datasets A, B, and C, evaluate on the real robot, compare success rates —
  the project's primary research metric (AGENTS_NEW.md §19-21). Needs its own
  Linux→Windows data handover first (copy the three `data/local/datasets/*`
  folders above).
- **On Mac**: no specific pipeline task is queued for Mac from this session --
  the next pipeline milestone (training comparison) runs on Windows. If you're
  picking Mac up for something else (more real recordings, hardware eval of an
  existing checkpoint, etc.), that's independent of this handover.
