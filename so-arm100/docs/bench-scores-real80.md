# Bench trials: circle_insert_real80_30k / checkpoints/030000

Every trial run against the 80-episode checkpoint on 2026-08-21. Grasp and
transport come from `scripts/grasp_verdict.py` reading the manifest; **the
insertion column is human observation only** and cannot be recovered later —
there is no video, the per-chunk stills are 1.7s apart, and the gripper occludes
the piece in the release frame.

## The distinction that matters

"Seated in the pocket" is not one outcome. A piece **placed** over the pocket and
released is the task. A piece **slid** in after an off-target release is the
policy getting away with it, and counting the two together hides exactly the
5-7mm insertion error the 21 place-phase episodes were recorded to remove.
This was not being distinguished until Alex pointed it out at fixed04.

## Trials

| trial | start y | grasp | transport | insertion | notes |
| --- | --- | --- | --- | --- | --- |
| bench1 | 0.537 | ok | ok | **placed** | |
| bench2 | 0.514 | ok | ok | **placed** | |
| bench3 | 0.409 | never closed | — | — | out of distribution in x (0.585); hovered 8 chunks |
| bench4 | 0.537 | ok | ok | *unrecorded* | seated; placed-vs-slid never asked |
| bench5 | 0.460 | missed | — | — | closed high: shoulder -3.2, elbow 35.9 |
| bench6 | 0.407 | missed | — | — | closed high: shoulder +0.2, elbow 29.1 |
| bench7 | 0.533 | missed | — | — | in-band start AND in-band posture; unexplained |
| fixed01 | 0.575 | missed | — | — | closed folded back: shoulder -13.9, elbow 43.5 |
| fixed02 | 0.58 | ok | ok | **slid** | |
| fixed03 | 0.45 | ok | ok | **missed** | grasped below the "floor" the gate would have blocked |
| fixed04 | ~0.49 | ok | ok | **slid** | gate misread framing entirely (locked onto the pocket) |

## Score

Of 10 trials that ran (bench3 excluded as out-of-distribution):

- **grasped: 6** — bench1, bench2, bench4, fixed02, fixed03, fixed04
- **missed the grasp: 4** — bench5, bench6, bench7, fixed01
- **seated: 5**, of which **placed: 2** (bench1, bench2), **slid: 2**
  (fixed02, fixed04), **unrecorded: 1** (bench4)

So the headline is not "5 of 10". Precise placement is confirmed in **2 trials**,
both of them the earliest ones run.

## What the start-y numbers are worth

Weak. `home_arm.py`'s blob detector mistook the board's pocket for the peg on
fixed04, reporting x=0.07 when the piece was plainly at x≈0.44 — so the live
gate readings cannot be trusted without checking the wrist frame. The values
above for bench1-fixed01 come from measuring `chunk-00/wrist.png` directly with
the pocket region excluded, which is the more reliable method. fixed03 grasping
from y=0.45 also contradicts the `WORKING_WRIST_Y_MIN = 0.50` floor.
